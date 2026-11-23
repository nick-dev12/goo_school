"""
Assistant IA — actions sur la structure pédagogique : filières, classes, modules (UE) et matières (EC).

Ces actions remplacent ou complètent celles de assistant_actions / assistant_dossiers / assistant_superieur
pour suivre les mêmes règles que les écrans :
- une matière (EC) du supérieur appartient à un module (UE) et à des classes de ce module ;
- les crédits d'un module se règlent classe par classe ; le nombre saisi sur une matière est son
  poids dans le module (services/credits_lmd) ;
- une matière commune à plusieurs filières n'a pas de filière unique ;
- une classe du supérieur a une filière et un niveau LMD.

Le module est importé en dernier (fin de assistant_superieur) : ses enregistrements remplacent les
anciennes définitions portant le même nom.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q

from school_admin.services import assistant_actions as base
from school_admin.services.assistant_actions import (
    ActionSpec,
    _emit,
    _err,
    _find_classe,
    _incomplete,
    _ok,
    _pending,
    _reverse,
    register_action,
)

logger = logging.getLogger(__name__)

_STR = {'type': 'string'}
_CLASSE = {'type': 'string', 'description': 'Nom de la classe'}
_CLASSES = {'type': 'string', 'description': 'Une ou plusieurs classes, séparées par des virgules'}


def _sup(ctx):
    return getattr(ctx.etablissement, 'type_etablissement', None) == 'superieur'


def _decimal(raw, mini=Decimal('0'), maxi=Decimal('60')):
    if raw in (None, ''):
        return None
    try:
        valeur = Decimal(str(raw).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        return 'invalide'
    if not valeur.is_finite() or valeur < mini or valeur > maxi:
        return 'invalide'
    return valeur


def _fmt(valeur):
    if valeur is None:
        return '—'
    texte = f'{Decimal(str(valeur)):f}'
    return texte.rstrip('0').rstrip('.') if '.' in texte else texte


def _find_module(ctx, query):
    from school_admin.services.assistant_dossiers import _find_module as trouver
    return trouver(ctx, query)


def _find_filiere(ctx, query):
    from school_admin.services.assistant_dossiers import _find_filiere as trouver
    return trouver(ctx, query)


def _classes_demandees(ctx, raw):
    """Classes citées (« L1 A, L1 B ») ; renvoie (classes, noms introuvables)."""
    trouvees, inconnues = [], []
    for morceau in [m.strip() for m in str(raw or '').replace(' et ', ',').split(',') if m.strip()]:
        classe = _find_classe(ctx, morceau)
        if classe is None:
            inconnues.append(morceau)
        elif classe not in trouvees:
            trouvees.append(classe)
    return trouvees, inconnues


def _cle_niveau(classe):
    if classe.niveau_lmd == 'AUTRE':
        return (classe.niveau_libelle or 'AUTRE').strip()
    return classe.niveau_lmd or ''


def _filiere_unique(classes):
    ids = {c.department_id for c in classes if c.department_id}
    return next(iter(ids)) if len(ids) == 1 else None


def _noms(classes):
    return ', '.join(c.nom for c in classes)


# --------------------------------------------------------------------------- classes
def prepare_creer_classe(ctx, args):
    """Supérieur : une classe a une filière et un niveau LMD (sinon ses modules ne s'y rattachent pas)."""
    args = args if isinstance(args, dict) else {}
    if not _sup(ctx):
        return base.prepare_creer_classe(ctx, args)
    from school_admin.services.assistant_superieur import normalize_niveau_lmd

    nom = (args.get('nom') or args.get('query') or '').strip()
    if not nom:
        return _incomplete('creer_classe', ['nom'], 'Quel nom pour la nouvelle classe ?')
    filiere = _find_filiere(ctx, args.get('filiere') or args.get('specialite') or args.get('department'))
    if not filiere:
        return _incomplete('creer_classe', ['filiere'], f'À quelle filière rattacher la classe « {nom} » ?', nom=nom)
    niveau_lmd = normalize_niveau_lmd(args.get('niveau_lmd') or args.get('niveau'))
    if not niveau_lmd:
        return _incomplete('creer_classe', ['niveau_lmd'],
                           f'Quel niveau pour « {nom} » : L1, L2, L3, M1, M2… ?', nom=nom, filiere=filiere.nom)
    try:
        capacite = int(args.get('capacite') or args.get('capacite_max') or 30)
    except (TypeError, ValueError):
        return _err('Capacité invalide.')
    return _pending('creer_classe', f'crée la classe {nom} ({filiere.nom}, {niveau_lmd}, {capacite} places)',
                    nom=nom, niveau='superieur', cycle='superieur', capacite_max=capacite,
                    department_id=filiere.id, niveau_lmd=niveau_lmd,
                    url=_reverse('administrateur_etablissement:liste_classes'))


def apply_creer_classe(ctx, draft):
    if not _sup(ctx):
        return base.apply_creer_classe(ctx, draft)
    from school_admin.model.academic_structure_model import Department
    from school_admin.model.classe_model import Classe

    filiere = Department.objects.filter(pk=draft.get('department_id'), etablissement=ctx.etablissement).first()
    if not filiere or not draft.get('niveau_lmd'):
        return _err('Filière ou niveau LMD manquant.')
    if Classe.objects.filter(etablissement=ctx.etablissement, nom__iexact=(draft.get('nom') or '').strip()).exists():
        return _err(f'Une classe « {draft.get("nom")} » existe déjà.')
    with transaction.atomic():
        resultat = base.apply_creer_classe(ctx, {**draft, 'niveau': 'superieur'})
        if resultat.get('id'):
            Classe.objects.filter(pk=resultat['id']).update(department=filiere, niveau_lmd=draft['niveau_lmd'])
    if resultat.get('id'):
        resultat['message'] = f'Classe {draft.get("nom")} créée ({filiere.nom}, {draft["niveau_lmd"]}).'
    return resultat


# --------------------------------------------------------------------------- matières (EC)
def prepare_creer_matiere(ctx, args):
    from school_admin.model.module_model import ModuleClasse

    args = args if isinstance(args, dict) else {}
    nom = (args.get('nom') or args.get('query') or '').strip()
    if not nom:
        return _incomplete('creer_matiere', ['nom'], 'Quel nom pour la matière (EC) ?')
    coefficient = _decimal(args.get('coefficient'), Decimal('0.1'), Decimal('20'))
    if coefficient == 'invalide':
        return _err('Le coefficient doit être un nombre entre 0,1 et 20.')
    poids = _decimal(args.get('poids') or args.get('credits'))
    if poids == 'invalide':
        return _err('Le poids doit être un nombre entre 0 et 60.')
    classes, inconnues = _classes_demandees(ctx, args.get('classes') or args.get('classe'))
    if inconnues:
        return _err(f'Classe introuvable : {", ".join(inconnues)}.')

    if not _sup(ctx):
        resume = f'crée la matière {nom}'
        if classes:
            resume += f' pour {_noms(classes)}'
        resume += f' (coefficient {_fmt(coefficient or 1)})'
        return _pending('creer_matiere', resume, nom=nom, code=(args.get('code') or '').strip().upper(),
                        coefficient=str(coefficient or 1), classe_ids=[c.id for c in classes],
                        url=_reverse('matiere:liste_matieres'))

    module = _find_module(ctx, args.get('module') or args.get('ue'))
    if not module:
        return _incomplete('creer_matiere', ['module'],
                           f'Dans quel module (UE) ajouter la matière (EC) « {nom} » ?', nom=nom)
    classes_module = [mc.classe for mc in ModuleClasse.objects.filter(module=module).select_related('classe')]
    if not classes_module:
        return _err(f'Le module (UE) {module.nom} n’est rattaché à aucune classe : '
                    'rattachez-le d’abord (affecter_module_classe).')
    if classes:
        hors = [c for c in classes if c not in classes_module]
        if hors:
            return _err(f'{_noms(hors)} ne suit pas le module (UE) {module.nom}. '
                        f'Classes du module : {_noms(classes_module)}.')
    else:
        classes = classes_module
    if len({_cle_niveau(c) for c in classes}) > 1:
        return _incomplete('creer_matiere', ['classe'],
                           f'Le module (UE) {module.nom} est suivi à plusieurs niveaux ({_noms(classes_module)}). '
                           'Pour quelle(s) classe(s) créer cette matière (EC) ?', nom=nom, module=module.nom)
    resume = (f'crée la matière (EC) {nom} dans le module (UE) {module.nom} pour {_noms(classes)} '
              f'(coefficient {_fmt(coefficient or 1)}'
              + (f', poids {_fmt(poids)}' if poids is not None else ', crédits du module partagés à parts égales')
              + ')')
    return _pending('creer_matiere', resume, nom=nom, module_id=module.id, classe_ids=[c.id for c in classes],
                    coefficient=str(coefficient or 1), poids=str(poids) if poids is not None else None,
                    url=_reverse('matiere:detail_module', args=[module.id]))


@transaction.atomic
def apply_creer_matiere(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.module_model import Module

    nom = (draft.get('nom') or '').strip()
    classes = list(Classe.objects.filter(pk__in=draft.get('classe_ids') or [], etablissement=ctx.etablissement))
    coefficient = Decimal(str(draft.get('coefficient') or 1))
    champs = {'nom': nom[:100], 'etablissement': ctx.etablissement, 'coefficient': coefficient}
    if draft.get('code'):
        champs['code'] = draft['code'][:20]
    if _sup(ctx):
        module = Module.objects.filter(pk=draft.get('module_id'), etablissement=ctx.etablissement).first()
        ids = set(draft.get('classe_ids') or [])
        classes = _classes_programme(ctx, ids, verrouiller=True)
        if not module or not classes or len(classes) != len(ids):
            return _err('Module (UE) ou classes introuvables.')
        from school_admin.model.module_model import ModuleClasse

        liens = {
            lien.classe_id: lien for lien in ModuleClasse.objects.filter(module=module, classe__in=classes)
            .select_related('periode')
        }
        for classe in classes:
            if classe.pk not in liens:
                return _err(f'{classe.nom} ne suit plus ce module (UE).')
            erreur = _erreur_programme(ctx, classe, liens[classe.pk].periode)
            if erreur:
                return _err(erreur)
        if Matiere.objects.filter(module=module, nom__iexact=nom, classes__in=classes).exists():
            return _err(f'La matière (EC) {nom} existe déjà dans {module.nom} pour ces classes.')
        if _filiere_unique(classes) is None:
            existante = Matiere.objects.filter(etablissement=ctx.etablissement, nom__iexact=nom,
                                               department__isnull=True).select_related('module').first()
            if existante:
                return _err(f'Une matière (EC) commune « {existante.nom} » existe déjà'
                            + (f' dans le module (UE) {existante.module.nom}' if existante.module_id else '')
                            + ' : donnez un autre nom (ex. « ' + nom + ' – ' + module.nom + ' »).')
        champs.update(module=module, niveau='superieur', department_id=_filiere_unique(classes),
                      niveau_lmd_key=_cle_niveau(classes[0])[:20],
                      credits=Decimal(str(draft['poids'])) if draft.get('poids') not in (None, '') else None)
    elif Matiere.objects.filter(etablissement=ctx.etablissement, nom__iexact=nom).exists():
        return _err(f'La matière {nom} existe déjà.')
    from django.db import IntegrityError
    try:
        with transaction.atomic():
            matiere = Matiere.objects.create(**champs)
            if classes:
                matiere.classes.set(classes)
    except IntegrityError:
        return _err(f'Une matière nommée « {nom} » existe déjà à cet endroit : choisissez un autre nom.')
    try:
        from school_admin.services.live_serializers import serialize_matiere_item
        _emit(ctx, 'matiere.creee', serialize_matiere_item(matiere, est_superieur=_sup(ctx)))
    except Exception:
        logger.exception('Diffusion matière créée')
    if _sup(ctx):
        from school_admin.services.credits_lmd import credits_ec
        detail = ', '.join(f'{c.nom} : {_fmt(credits_ec(matiere, c))} crédits' for c in classes)
        return _ok(f'Matière (EC) {matiere.nom} créée dans le module (UE) {matiere.module.nom} ({detail}).',
                   id=matiere.id, url=_reverse('matiere:detail_matiere', args=[matiere.id]))
    return _ok(f'Matière {matiere.nom} créée.', id=matiere.id, url=_reverse('matiere:detail_matiere', args=[matiere.id]))


_CHAMPS_MATIERE = {
    'coefficient': ('coefficient', Decimal('0.1'), Decimal('20')),
    'poids': ('credits', Decimal('0'), Decimal('60')),
    'heures_cm': ('volume_cm', 0, 999),
    'heures_td': ('volume_td', 0, 999),
    'heures_tp': ('volume_tp', 0, 999),
    'heures_tpe': ('volume_tpe', 0, 999),
}


def prepare_modifier_matiere(ctx, args):
    from school_admin.model.matiere_model import Matiere

    args = args if isinstance(args, dict) else {}
    requete = (args.get('query') or args.get('matiere') or '').strip()
    qs = Matiere.objects.filter(etablissement=ctx.etablissement).filter(Q(nom__icontains=requete) | Q(code__iexact=requete))
    module_filtre = _find_module(ctx, args.get('module_actuel')) if args.get('module_actuel') else None
    if module_filtre:
        qs = qs.filter(module=module_filtre)
    candidats = list(qs.select_related('module')[:6]) if requete else []
    exacts = [m for m in candidats if m.nom.lower() == requete.lower()]
    candidats = exacts or candidats
    if not candidats:
        return _incomplete('modifier_matiere', ['query'], 'Quelle matière (EC) modifier ?')
    if len(candidats) > 1:
        liste = '; '.join(f'{m.nom} ({m.module.nom if m.module_id else "sans module"})' for m in candidats)
        return _incomplete('modifier_matiere', ['module_actuel'],
                           f'Plusieurs matières correspondent : {liste}. Dans quel module (UE) ?', query=requete)
    matiere = candidats[0]
    changements, lignes = {}, []
    nouveau_nom = (args.get('nouveau_nom') or '').strip()
    if nouveau_nom and nouveau_nom != matiere.nom:
        changements['nom'] = nouveau_nom[:100]
        lignes.append(f'nom « {nouveau_nom} »')
    for cle, (champ, mini, maxi) in _CHAMPS_MATIERE.items():
        if args.get(cle) in (None, ''):
            continue
        valeur = _decimal(args.get(cle), Decimal(str(mini)), Decimal(str(maxi)))
        if valeur == 'invalide':
            return _err(f'Valeur invalide pour {cle.replace("_", " ")}.')
        changements[champ] = str(valeur)
        lignes.append(f'{cle.replace("_", " ")} {_fmt(valeur)}')
    if args.get('module'):
        if not _sup(ctx):
            return _err('Les modules (UE) concernent uniquement le supérieur.')
        module = _find_module(ctx, args.get('module'))
        if not module:
            return _err(f'Module (UE) introuvable : {args.get("module")}.')
        if module.pk != matiere.module_id:
            changements['module_id'] = module.pk
            lignes.append(f'rattachée au module (UE) {module.nom}')
    if not changements:
        return _incomplete('modifier_matiere', ['champs'],
                           f'Que changer pour {matiere.nom} : nom, coefficient, poids, heures ou module (UE) ?',
                           query=matiere.nom)
    return _pending('modifier_matiere', f'modifie la matière (EC) {matiere.nom} : ' + ', '.join(lignes),
                    id=matiere.id, changements=changements,
                    url=_reverse('matiere:detail_matiere', args=[matiere.id]))


@transaction.atomic
def apply_modifier_matiere(ctx, draft):
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.module_model import Module

    matiere = Matiere.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not matiere:
        return _err('Matière introuvable.')
    changements = draft.get('changements') or {}
    if _sup(ctx) and {'module_id', 'coefficient', 'credits'} & changements.keys():
        from school_admin.model.module_model import ModuleClasse

        explicit = matiere.classes.values_list('pk', flat=True)
        facultatives = matiere.module.classes.values_list('pk', flat=True) if matiere.module_id else []
        classes = _classes_programme(ctx, explicit if explicit.exists() else facultatives, verrouiller=True)
        module_ids = {matiere.module_id, changements.get('module_id')} - {None}
        periodes = {}
        for lien in ModuleClasse.objects.filter(module_id__in=module_ids, classe__in=classes).select_related('periode'):
            periodes.setdefault(lien.classe_id, []).append(lien.periode)
        for classe in classes:
            erreur = _erreur_programme(ctx, classe, *periodes.get(classe.pk, []))
            if erreur:
                return _err(erreur)
    if changements.get('module_id'):
        module = Module.objects.filter(pk=changements['module_id'], etablissement=ctx.etablissement).first()
        if not module:
            return _err('Module (UE) introuvable.')
        classes = _classes_programme(ctx, matiere.classes.values_list('pk', flat=True), verrouiller=True)
        classes_destination = set(module.classes.values_list('pk', flat=True))
        if not classes or any(classe.pk not in classes_destination for classe in classes):
            return _err('Le module de destination doit être rattaché à toutes les classes de cette matière.')
        matiere.module = module
    for champ in ('nom', 'coefficient', 'credits', 'volume_cm', 'volume_td', 'volume_tp', 'volume_tpe'):
        if champ in changements:
            valeur = changements[champ]
            if champ.startswith('volume_'):
                valeur = int(Decimal(str(valeur)))
            elif champ != 'nom':
                valeur = Decimal(str(valeur))
            setattr(matiere, champ, valeur)
    matiere.save()
    try:
        from school_admin.services.live_serializers import serialize_matiere_item
        _emit(ctx, 'matiere.modifiee', serialize_matiere_item(matiere, est_superieur=_sup(ctx)))
    except Exception:
        logger.exception('Diffusion matière modifiée')
    return _ok(f'Matière {matiere.nom} mise à jour.', id=matiere.id,
               url=_reverse('matiere:detail_matiere', args=[matiere.id]))


# --------------------------------------------------------------------------- modules (UE)
def _semestre_module(ctx, classe, periode_id):
    from school_admin.model.periode_model import PeriodeScolaire

    if not periode_id or not ctx.annee_scolaire:
        return None
    periodes = PeriodeScolaire.objects.filter(
        etablissement=ctx.etablissement, type_periode='semestre',
    ).filter(
        Q(annee_scolaire_fk=ctx.annee_scolaire)
        | Q(annee_scolaire_fk__isnull=True, annee_scolaire=ctx.annee_scolaire.libelle)
    )
    du_niveau = periodes.filter(niveau_lmd=classe.niveau_lmd or '')
    if classe.niveau_lmd and not du_niveau.exists():
        du_niveau = periodes.filter(niveau_lmd='')
    return du_niveau.filter(pk=periode_id).first()


def _erreur_programme(ctx, classe, *periodes):
    from school_admin.model.deliberation_model import Deliberation
    from school_admin.services.deliberations import periode_verrouillee

    annee = ctx.annee_scolaire
    if annee is None or not annee.est_active:
        return "Sélectionnez l’année scolaire active pour modifier le programme."
    if any(
        periode.annee_scolaire_fk_id not in (None, annee.id)
        or (periode.annee_scolaire_fk_id is None and periode.annee_scolaire != annee.libelle)
        for periode in periodes if periode is not None
    ):
        return f"Le semestre du module pour {classe.nom} appartient à une autre année."
    if (any(periode_verrouillee(classe, periode) for periode in periodes)
            or Deliberation.objects.filter(
                classe=classe, annee_scolaire=annee, periode__isnull=True,
                statut=Deliberation.STATUT_CLOTUREE,
            ).exists()):
        return (f"Le programme de {classe.nom} est verrouillé par une délibération clôturée. "
                "Ouvrez Examens et jury pour vérifier les résultats avant toute correction.")
    return None


def _classes_programme(ctx, ids, *, verrouiller=False):
    from school_admin.model.classe_model import Classe

    qs = Classe.objects.filter(
        pk__in=ids, etablissement=ctx.etablissement, actif=True, niveau='superieur',
    ).order_by('pk')
    return list(qs.select_for_update() if verrouiller else qs)


def _ajouter_filieres(module, classes):
    """Le module est rattaché aux filières de ses classes (module commun si plusieurs)."""
    from school_admin.controllers.module_controller import _sync_module_departments

    ids = {str(d.pk) for d in module.get_linked_departments()}
    ids |= {str(c.department_id) for c in classes if c.department_id}
    if ids:
        _sync_module_departments(module, sorted(ids))


def prepare_creer_module(ctx, args):
    from school_admin.services.assistant_superieur import _find_periode, _parse_credits, normalize_niveau_lmd

    args = args if isinstance(args, dict) else {}
    if not _sup(ctx):
        return _err('Les modules (UE) concernent uniquement le supérieur.')
    nom = (args.get('nom') or args.get('query') or '').strip()
    if not nom:
        return _incomplete('creer_module', ['nom'], 'Quel nom pour le module (UE) ?')
    classes, inconnues = _classes_demandees(ctx, args.get('classes') or args.get('classe'))
    if inconnues:
        return _err(f'Classe introuvable : {", ".join(inconnues)}.')
    filiere = _find_filiere(ctx, args.get('filiere') or args.get('specialite') or args.get('department'))
    if not classes and not filiere:
        return _incomplete('creer_module', ['classe'],
                           f'Pour quelle(s) classe(s) créer le module (UE) « {nom} » ?', nom=nom)
    credits = _parse_credits(args.get('credits'))
    if classes and credits is None:
        return _incomplete('creer_module', ['credits'],
                           f'Combien de crédits vaut « {nom} » en {_noms(classes)} ?', nom=nom, classes=_noms(classes))
    periodes = {}
    texte_periode = args.get('periode') or args.get('semestre')
    for classe in classes:
        periode = _find_periode(ctx, texte_periode, niveau_lmd=classe.niveau_lmd) if texte_periode else None
        if texte_periode and (not periode or not _semestre_module(ctx, classe, periode.pk)):
            return _incomplete('creer_module', ['periode'], f'Quel semestre pour {classe.nom} ?', nom=nom)
        erreur = _erreur_programme(ctx, classe, periode)
        if erreur:
            return _err(erreur)
        periodes[classe.id] = periode.id if periode else None
    niveau_lmd = normalize_niveau_lmd(args.get('niveau_lmd') or args.get('niveau')) or (
        classes[0].niveau_lmd if classes and len({c.niveau_lmd for c in classes}) == 1 else '')
    numero_ue = (args.get('numero_ue') or args.get('ue') or '').strip()[:80]
    resume = f'crée le module (UE) {nom}'
    if classes:
        resume += f' pour {_noms(classes)} ({_fmt(credits)} crédits'
        resume += f', {texte_periode}' if texte_periode else ', semestre à choisir'
        resume += ')'
    else:
        resume += f' ({filiere.nom}, sans classe pour l’instant)'
    return _pending('creer_module', resume, nom=nom, department_id=filiere.id if filiere else None,
                    classe_ids=[c.id for c in classes], periodes=periodes,
                    credits=str(credits) if credits is not None else None,
                    numero_ue=numero_ue, niveau_lmd=niveau_lmd or '', url=_reverse('matiere:liste_matieres'))


def apply_creer_module(ctx, draft):
    from school_admin.controllers.module_controller import _sync_module_departments
    from school_admin.model.module_model import Module, ModuleClasse
    from school_admin.services.assistant_superieur import _parse_credits

    if not _sup(ctx):
        return _err('Les modules (UE) concernent uniquement le supérieur.')
    nom = (draft.get('nom') or '').strip()
    ids = set(draft.get('classe_ids') or [])
    credits = _parse_credits(draft.get('credits'))
    if not nom or (ids and credits is None):
        return _err('Nom ou crédits du module (UE) manquants.')
    with transaction.atomic():
        classes = _classes_programme(ctx, ids, verrouiller=True)
        if len(classes) != len(ids):
            return _err('Une des classes du module (UE) n’est plus disponible.')
        periodes = {str(k): v for k, v in (draft.get('periodes') or {}).items()}
        for classe in classes:
            periode_id = periodes.get(str(classe.id))
            periode = _semestre_module(ctx, classe, periode_id)
            if periode_id and periode is None:
                return _err(f'Le semestre choisi ne correspond plus à {classe.nom} pour cette année.')
            erreur = _erreur_programme(ctx, classe, periode)
            if erreur:
                return _err(erreur)
            periodes[str(classe.id)] = periode
        rang = Module.objects.filter(etablissement=ctx.etablissement).count() + 1
        code = f'MOD-{rang:04d}'
        while Module.objects.filter(etablissement=ctx.etablissement, code=code).exists():
            rang += 1
            code = f'MOD-{rang:04d}'
        module = Module.objects.create(nom=nom[:200], code=code, etablissement=ctx.etablissement,
                                       department_id=draft.get('department_id') or _filiere_unique(classes),
                                       niveau_lmd=draft.get('niveau_lmd') or None)
        if draft.get('department_id'):
            _sync_module_departments(module, [str(draft['department_id'])])
        for classe in classes:
            ModuleClasse.objects.create(module=module, classe=classe, credits=credits or 0,
                                        periode=periodes[str(classe.id)],
                                        numero_ue=(draft.get('numero_ue') or '')[:80])
        _ajouter_filieres(module, classes)
    _emit(ctx, 'matiere.creee', {'id': module.id, 'nom': module.nom, 'action': 'module'})
    detail = f' pour {_noms(classes)} ({_fmt(credits)} crédits)' if classes else ''
    return _ok(f'Module (UE) {module.nom} créé{detail}. Ajoutez-y maintenant ses matières (EC).',
               id=module.id, url=_reverse('matiere:detail_module', args=[module.id]))


def _controler_lien_module(ctx, draft, *, verrouiller=False):
    from school_admin.model.module_model import Module, ModuleClasse

    if not _sup(ctx):
        return None, None, 'Cet outil concerne uniquement le supérieur.'
    classes = _classes_programme(ctx, [draft.get('classe_id')], verrouiller=verrouiller)
    module = Module.objects.filter(pk=draft.get('module_id'), etablissement=ctx.etablissement).first()
    if not classes or not module:
        return None, None, 'Module (UE) ou classe introuvable.'
    classe = classes[0]
    lien = ModuleClasse.objects.filter(module=module, classe=classe).select_related('periode').first()
    precedente = lien.periode if lien else None
    periode = precedente
    if draft.get('periode_id'):
        periode = _semestre_module(ctx, classe, draft['periode_id'])
        if periode is None:
            return None, None, f'Le semestre choisi ne correspond pas à {classe.nom} pour cette année.'
    erreur = _erreur_programme(ctx, classe, precedente, periode)
    return lien or ModuleClasse(module=module, classe=classe), periode, erreur


def prepare_affecter_module_classe(ctx, args):
    from school_admin.services.assistant_superieur import prepare_affecter_module_classe as ancien

    draft = ancien(ctx, args)
    if draft.get('statut') == 'en_attente_confirmation':
        _, _, erreur = _controler_lien_module(ctx, draft)
        if erreur:
            return _err(erreur)
        draft['resume'] += ' ; ce réglage peut rendre les moyennes déjà calculées à recalculer'
    return draft


@transaction.atomic
def apply_affecter_module_classe(ctx, draft):
    from school_admin.services.assistant_superieur import _parse_credits

    lien, periode, erreur = _controler_lien_module(ctx, draft, verrouiller=True)
    credits = _parse_credits(draft.get('credits'))
    if erreur or credits is None:
        return _err(erreur or 'Crédits du module (UE) invalides.')
    cree = lien.pk is None
    lien.credits = credits
    if draft.get('numero_ue'):
        lien.numero_ue = draft['numero_ue'][:80]
    lien.periode = periode
    lien.save()
    _ajouter_filieres(lien.module, [lien.classe])
    message = (f'Module (UE) {lien.module.nom} {"rattaché à" if cree else "mis à jour pour"} {lien.classe.nom} '
               f'({_fmt(credits)} crédits'
               + (f', {periode.nom_periode}' if periode else ', semestre à choisir') + ').')
    return _ok(message, id=lien.pk, created=cree)


def prepare_fixer_credits_module(ctx, args):
    from school_admin.services.assistant_superieur import prepare_fixer_credits_module as ancien

    draft = ancien(ctx, args)
    if draft.get('statut') == 'en_attente_confirmation':
        _, _, erreur = _controler_lien_module(ctx, draft)
        if erreur:
            return _err(erreur)
        draft['resume'] += ' ; les résultats déjà calculés pourront nécessiter un recalcul'
    return draft


@transaction.atomic
def apply_fixer_credits_module(ctx, draft):
    from school_admin.services.assistant_superieur import apply_fixer_credits_module as ancien

    _, _, erreur = _controler_lien_module(ctx, draft, verrouiller=True)
    if erreur:
        return _err(erreur)
    resultat = ancien(ctx, draft)
    if resultat.get('statut') == 'ok':
        resultat['message'] += ' Les crédits de ses matières (EC) sont répartis selon leurs poids.'
    return resultat


def prepare_retirer_module_classe(ctx, args):
    from school_admin.model.module_model import ModuleClasse

    args = args if isinstance(args, dict) else {}
    if not _sup(ctx):
        return _err('Les modules (UE) concernent uniquement le supérieur.')
    module = _find_module(ctx, args.get('module') or args.get('query'))
    if not module:
        return _incomplete('retirer_module_classe', ['module'], 'Quel module (UE) retirer ?')
    classe = _find_classe(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete('retirer_module_classe', ['classe'], f'De quelle classe retirer {module.nom} ?',
                           module=module.nom)
    lien = ModuleClasse.objects.filter(module=module, classe=classe).select_related('periode').first()
    if lien is None:
        return _err(f'{module.nom} n’est pas rattaché à {classe.nom}.')
    erreur = _erreur_programme(ctx, classe, lien.periode)
    if erreur:
        return _err(erreur)
    return _pending('retirer_module_classe',
                    f'retire le module (UE) {module.nom} de {classe.nom} (ses matières (EC) ne seront plus suivies '
                    'par cette classe ; les notes déjà saisies sont conservées)',
                    module_id=module.id, classe_id=classe.id, url=_reverse('matiere:detail_module', args=[module.id]))


@transaction.atomic
def apply_retirer_module_classe(ctx, draft):
    lien, _, erreur = _controler_lien_module(ctx, draft, verrouiller=True)
    if erreur or lien.pk is None:
        return _err(erreur or 'Ce module (UE) n’est plus rattaché à cette classe.')
    module, classe = lien.module, lien.classe
    lien.delete()
    for matiere in module.matieres.filter(classes=classe):
        matiere.classes.remove(classe)
    _emit(ctx, 'matiere.modifiee', {'id': module.id, 'nom': module.nom, 'action': 'module'})
    return _ok(f'Module (UE) {module.nom} retiré de {classe.nom}.')


def prepare_supprimer_module(ctx, args):
    from school_admin.services.assistant_dossiers import prepare_supprimer_module as ancien

    resultat = ancien(ctx, args)
    if resultat.get('statut') == 'en_attente_confirmation':
        from school_admin.model.matiere_model import Matiere
        n = Matiere.objects.filter(module_id=resultat.get('id')).count()
        resultat['resume'] = (f'supprime le module (UE) {resultat.get("nom")}'
                              + (f' ; ses {n} matière(s) (EC) restent, sans module : elles ne compteront plus '
                                 'dans les crédits tant qu’elles ne sont pas rattachées à un autre module' if n else ''))
    return resultat


# --------------------------------------------------------------------------- affectation d'un enseignant
def prepare_affecter_professeur(ctx, args):
    """Supérieur : la matière retenue doit être enseignée dans la classe (homonymes d'autres filières écartés)."""
    from school_admin.model.classe_model import Classe
    from school_admin.model.matiere_model import Matiere
    from school_admin.services.assistant_dossiers import prepare_affecter_professeur as ancien

    demandee = (args.get('matiere') or '').strip() if isinstance(args, dict) else ''
    if demandee and not Matiere.objects.filter(etablissement=ctx.etablissement, actif=True).filter(
            Q(nom__icontains=demandee) | Q(code__iexact=demandee)).exists():
        return _err(f'Aucune matière ne s’appelle « {demandee} ». Vérifiez le nom de la matière (EC).')
    resultat = ancien(ctx, args)
    if not _sup(ctx) or resultat.get('statut') != 'en_attente_confirmation' or resultat.get('operation') == 'remove':
        return resultat
    if not resultat.get('matiere_id') or not resultat.get('classe_id'):
        return resultat
    from school_admin.model.professeur_model import Professeur

    classe = Classe.objects.get(pk=resultat['classe_id'])
    matiere = Matiere.objects.get(pk=resultat['matiere_id'])
    prof = Professeur.objects.get(pk=resultat['professeur_id'])
    siennes = set(prof.matieres_secondaires.values_list('pk', flat=True))
    if prof.matiere_principale_id:
        siennes.add(prof.matiere_principale_id)
    de_la_classe = Matiere.pour_classe_superieur(classe)
    cherche = (args.get('matiere') or '').strip() if isinstance(args, dict) else ''
    noms = {matiere.nom.lower()}
    if cherche:
        noms.add(cherche.lower())
    candidates = [m for m in de_la_classe
                  if m.nom.lower() in noms or (cherche and cherche.lower() in m.nom.lower())]
    if matiere.classe_est_compatible_affectation_superieur(classe) and matiere not in candidates:
        candidates.insert(0, matiere)
    if not candidates:
        enseignees = ', '.join(de_la_classe.values_list('nom', flat=True)[:12])
        return _err(f'{matiere.nom} n’est pas une matière (EC) de {classe.nom}. '
                    f'Matières (EC) de cette classe : {enseignees or "aucune"}.')
    retenue = next((m for m in candidates if m.pk in siennes), None)
    if retenue is None:
        return _err(f'{prof.nom_complet} n’a pas {candidates[0].nom} ({classe.nom}) parmi ses matières. '
                    'Ajoutez-la d’abord à sa fiche (matière principale ou secondaire), puis refaites l’affectation.')
    resultat['matiere_id'] = retenue.id
    resultat['resume'] += f' pour la matière (EC) {retenue.nom}'
    return resultat


def apply_affecter_professeur(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.matiere_model import Matiere
    from school_admin.services.assistant_dossiers import apply_affecter_professeur as ancien

    if _sup(ctx) and draft.get('operation') != 'remove' and draft.get('matiere_id'):
        classe = Classe.objects.filter(pk=draft.get('classe_id'), etablissement=ctx.etablissement).first()
        matiere = Matiere.objects.filter(pk=draft['matiere_id'], etablissement=ctx.etablissement).first()
        if classe and matiere and not matiere.classe_est_compatible_affectation_superieur(classe):
            return _err(f'{matiere.nom} n’est pas une matière (EC) de {classe.nom}.')
    from django.core.exceptions import ValidationError
    try:
        return ancien(ctx, draft)
    except ValidationError as exc:
        return _err(' '.join(exc.messages))


# --------------------------------------------------------------------------- enregistrement
def _remplacer(nom, description=None, properties=None, required=None, prepare=None, apply=None, destructive=None):
    ancien = base.ACTION_SPECS.get(nom)
    if ancien is None and (properties is None or prepare is None or apply is None):
        return  # l'action d'origine n'est pas encore chargée : enregistrer() sera rappelée
    register_action(ActionSpec(
        nom,
        description or ancien.description,
        properties if properties is not None else ancien.properties,
        required=ancien.required if required is None else required,
        destructive=ancien.destructive if destructive is None else destructive,
        prepare=prepare or ancien.prepare,
        apply=apply or ancien.apply,
        choices=getattr(ancien, 'choices', None) if ancien else None,
    ))


def enregistrer():
    """Enregistre les actions de structure (appelée par chaque module qui en définit d'anciennes versions)."""
    if 'creer_classe' not in base.ACTION_SPECS:
        return
    _remplacer('creer_classe',
               'Crée une classe. Supérieur : indiquer la filière et le niveau LMD (L1, L2, L3, M1…).',
               {**base.ACTION_SPECS['creer_classe'].properties,
                'filiere': {'type': 'string', 'description': 'Supérieur : filière (spécialité) de la classe'},
                'niveau_lmd': {'type': 'string', 'description': 'Supérieur : L1, L2, L3, M1, M2, BTS1…'}},
               prepare=prepare_creer_classe, apply=apply_creer_classe)

    _remplacer('creer_matiere',
               ('Crée une matière. Supérieur : une matière (EC) est créée DANS un module (UE) et pour des classes '
                'de ce module (toutes par défaut), avec un coefficient et un poids facultatif qui partage les '
                'crédits du module entre ses matières.'),
               {'nom': _STR, 'code': _STR,
                'module': {'type': 'string', 'description': 'Supérieur : module (UE) de la matière'},
                'classes': _CLASSES,
                'coefficient': {'type': 'string', 'description': 'Coefficient (1 par défaut)'},
                'poids': {'type': 'string', 'description': 'Supérieur : poids dans le module (UE), en crédits'}},
               required=('nom',), prepare=prepare_creer_matiere, apply=apply_creer_matiere)

    register_action(ActionSpec(
        'modifier_matiere',
        ('Modifie une matière (EC) : nouveau nom, coefficient, poids dans le module (UE), heures (CM, TD, TP, '
         'travail personnel) ou module (UE) de rattachement. Les crédits par classe se recalculent seuls.'),
        {'query': {'type': 'string', 'description': 'Matière à modifier'},
         'module_actuel': {'type': 'string', 'description': 'Module actuel, si plusieurs matières portent ce nom'},
         'nouveau_nom': _STR,
         'coefficient': _STR, 'poids': _STR,
         'heures_cm': _STR, 'heures_td': _STR, 'heures_tp': _STR, 'heures_tpe': _STR,
         'module': {'type': 'string', 'description': 'Nouveau module (UE) de rattachement'}},
        required=('query',),
        prepare=prepare_modifier_matiere,
        apply=apply_modifier_matiere,
    ))

    _remplacer('creer_module',
               ('Crée un module (UE) pour une ou plusieurs classes, avec ses crédits, son semestre et son numéro. '
                'Un module suivi par des classes de plusieurs filières devient commun à ces filières.'),
               {'nom': _STR, 'classes': _CLASSES,
                'filiere': {'type': 'string', 'description': 'Filière, si le module n’a pas encore de classe'},
                'credits': {'type': 'string', 'description': 'Crédits du module dans ces classes'},
                'periode': {'type': 'string', 'description': 'Semestre (ex. Semestre 1)'},
                'numero_ue': _STR, 'niveau_lmd': _STR},
               required=('nom',), prepare=prepare_creer_module, apply=apply_creer_module)

    _remplacer('affecter_module_classe',
               ('Rattache un module (UE) à une classe ou met à jour ses crédits, son semestre et son numéro pour '
                'cette classe (ce qui n’est pas précisé est conservé).'),
               prepare=prepare_affecter_module_classe, apply=apply_affecter_module_classe)

    _remplacer('fixer_credits_module',
               ('Change les crédits d’un module (UE) pour une classe. Les crédits de ses matières (EC) suivent '
                'leurs poids ; une délibération déjà clôturée verrouille ce réglage.'),
               prepare=prepare_fixer_credits_module, apply=apply_fixer_credits_module)

    register_action(ActionSpec(
        'retirer_module_classe',
        'Retire un module (UE) d’une classe : ses matières (EC) ne sont plus suivies par cette classe.',
        {'module': _STR, 'query': _STR, 'classe': _CLASSE},
        destructive=True,
        prepare=prepare_retirer_module_classe,
        apply=apply_retirer_module_classe,
    ))

    _remplacer('supprimer_module', prepare=prepare_supprimer_module)

    _remplacer('affecter_professeur', prepare=prepare_affecter_professeur, apply=apply_affecter_professeur)


enregistrer()
