"""
Actions assistant : élèves, professeurs, personnel, caisse, paie, filières.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from school_admin.services.assistant_actions import (
    ActionSpec,
    _emit,
    _err,
    _find_classe,
    _find_eleve,
    _incomplete,
    _ok,
    _parse_date,
    _parse_money,
    _pending,
    _reverse,
    register_action,
)


def _find_professeur(ctx, query):
    from school_admin.model.professeur_model import Professeur

    raw = (query or '').strip()
    if not raw:
        return None
    return Professeur.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
    ).filter(
        Q(nom__icontains=raw) | Q(prenom__icontains=raw) | Q(numero_employe__icontains=raw)
    ).first()


def _find_personnel(ctx, query):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif

    raw = (query or '').strip()
    if not raw:
        return None
    return PersonnelAdministratif.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
    ).filter(
        Q(nom__icontains=raw) | Q(prenom__icontains=raw)
    ).first()


def _find_matiere(ctx, query):
    from school_admin.model.matiere_model import Matiere

    raw = (query or '').strip()
    if not raw:
        return None
    return Matiere.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
    ).filter(Q(nom__icontains=raw) | Q(code__icontains=raw)).first()


def _ask_next_field(action, extras, prompts):
    """Une question à la fois, en conservant les champs déjà dictés."""
    manquants = [key for key in prompts if not extras.get(key)]
    if not manquants:
        return None
    first = manquants[0]
    kept = {
        key: value
        for key, value in extras.items()
        if value not in (None, '', [], ())
        and key not in ('statut', 'manquants', 'message', 'action', 'erreur', 'resume')
    }
    return _incomplete(action, [first], prompts[first], **kept)


def _niveau_enseignement(etablissement):
    mapping = {
        'primary': 'primaire',
        'collège': 'college',
        'college': 'college',
        'lycée': 'lycee',
        'lycee': 'lycee',
        'superieur': 'superieur',
    }
    return mapping.get((etablissement.type_etablissement or '').lower(), 'primaire')


def prepare_inscrire_eleve(ctx, args):
    nom = (args.get('nom') or '').strip()
    prenom = (args.get('prenom') or '').strip()
    classe = _find_classe(ctx, args.get('classe'))
    sexe = (args.get('sexe') or '').strip().upper()
    if sexe in ('MASCULIN', 'GARCON', 'GARÇON', 'HOMME'):
        sexe = 'M'
    if sexe in ('FEMININ', 'FÉMININ', 'FILLE', 'FEMME'):
        sexe = 'F'
    naissance = _parse_date(args.get('date_naissance'))
    lieu = (args.get('lieu_naissance') or args.get('lieu') or '').strip()
    parent_nom = (args.get('parent_nom') or '').strip()
    parent_prenom = (args.get('parent_prenom') or '').strip()
    parent_tel = (args.get('parent_telephone') or args.get('telephone') or '').strip()
    parent_lien = (args.get('parent_lien') or 'tuteur').strip().lower()
    if parent_lien not in ('mere', 'père', 'pere', 'tuteur'):
        parent_lien = 'tuteur'
    if parent_lien == 'père':
        parent_lien = 'pere'
    extras = {
        'nom': nom,
        'prenom': prenom,
        'classe': classe.nom if classe else (args.get('classe') or ''),
        'sexe': sexe if sexe in ('M', 'F') else '',
        'date_naissance': naissance.isoformat() if naissance else (args.get('date_naissance') or ''),
        'lieu_naissance': lieu,
        'parent_nom': parent_nom,
        'parent_prenom': parent_prenom,
        'parent_telephone': parent_tel,
        'parent_lien': parent_lien,
        'nationalite': (args.get('nationalite') or '').strip(),
    }
    if classe:
        extras['classe_id'] = classe.id
    asked = _ask_next_field(
        'inscrire_eleve',
        extras,
        {
            'nom': 'Quel est le nom de famille de l’élève ?',
            'prenom': 'Quel est son prénom ?',
            'classe': 'Dans quelle classe l’inscrire ?',
            'sexe': 'Sexe : garçon ou fille ?',
            'date_naissance': 'Quelle est sa date de naissance (jour/mois/année) ?',
            'lieu_naissance': 'Où est-il né ?',
            'parent_nom': 'Nom de famille du parent responsable ?',
            'parent_prenom': 'Prénom du parent responsable ?',
            'parent_telephone': 'Numéro de téléphone du parent ?',
        },
    )
    if asked:
        return asked
    return _pending(
        'inscrire_eleve',
        f'inscrit {prenom} {nom} en {classe.nom}',
        nom=nom,
        prenom=prenom,
        classe_id=classe.id,
        classe_nom=classe.nom,
        sexe=sexe,
        date_naissance=naissance.isoformat(),
        lieu_naissance=lieu,
        nationalite=(args.get('nationalite') or 'Camerounaise').strip(),
        parent_nom=parent_nom,
        parent_prenom=parent_prenom,
        parent_telephone=parent_tel,
        parent_lien=parent_lien,
        url=_reverse('secretaire:liste_eleves'),
    )


def apply_inscrire_eleve(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.lien_familial_model import LienFamilial
    from school_admin.model.parent_model import Parent
    from school_admin.personal_views.secretaire_view import _archiver_inscription_eleve_parent
    from school_admin.services.live_serializers import serialize_eleve_inscrit_item
    from school_admin.utils.formatting_utils import formater_nom, formater_prenom

    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active.')
    classe = Classe.objects.filter(
        pk=draft.get('classe_id'), etablissement=ctx.etablissement, actif=True
    ).first()
    if not classe:
        return _err('Classe introuvable.')
    naissance = _parse_date(draft.get('date_naissance'))
    if not naissance:
        return _err('Date de naissance invalide.')
    with transaction.atomic():
        matricule = Eleve.generer_matricule_eleve(ctx.etablissement)
        mot_de_passe = Eleve.generer_mot_de_passe()
        eleve = Eleve(
            nom=formater_nom(draft.get('nom')),
            prenom=formater_prenom(draft.get('prenom')),
            date_naissance=naissance,
            lieu_naissance=draft.get('lieu_naissance'),
            sexe=draft.get('sexe'),
            nationalite=draft.get('nationalite') or 'Camerounaise',
            numero_eleve=matricule,
            matricule_eleve=matricule,
            etablissement=ctx.etablissement,
            classe=classe,
            date_inscription=date.today(),
            statut='nouvelle',
            parent_nom=formater_nom(draft.get('parent_nom')),
            parent_prenom=formater_prenom(draft.get('parent_prenom')),
            parent_telephone=draft.get('parent_telephone'),
            parent_lien=draft.get('parent_lien') or 'tuteur',
            mot_de_passe_provisoire=mot_de_passe,
            mot_de_passe_eleve_modifie=False,
            username=matricule,
            is_active=True,
        )
        eleve.set_password(mot_de_passe)
        eleve.save()
        parent = Parent.objects.filter(
            telephone=draft.get('parent_telephone'),
            etablissement=ctx.etablissement,
        ).first()
        if parent is None:
            matricule_parent = Parent.generer_matricule_parent(ctx.etablissement)
            mot_parent = Parent.generer_mot_de_passe()
            parent = Parent(
                matricule_parental=matricule_parent,
                type_parent=draft.get('parent_lien') or 'tuteur',
                nom=formater_nom(draft.get('parent_nom')),
                prenom=formater_prenom(draft.get('parent_prenom')),
                telephone=draft.get('parent_telephone'),
                etablissement=ctx.etablissement,
                mot_de_passe_provisoire=mot_parent,
                username=matricule_parent,
                is_active=True,
            )
            parent.set_password(mot_parent)
            parent.save()
        LienFamilial.objects.get_or_create(
            parent=parent,
            eleve=eleve,
            defaults={
                'type_lien': draft.get('parent_lien') or 'tuteur',
                'statut': 'valide',
                'est_inscripteur': True,
                'actif': True,
            },
        )
        _archiver_inscription_eleve_parent(
            eleve=eleve,
            parent=parent,
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
            date_inscription=date.today(),
        )
        if getattr(ctx.etablissement, 'module_comptabilite', False):
            from school_admin.utils.comptabilite_utils import creer_frais_inscription

            try:
                creer_frais_inscription(eleve, ctx.annee_scolaire, 'inscription')
            except Exception:
                pass
        item = serialize_eleve_inscrit_item(eleve, classe, 'tous')
        _emit(ctx, 'eleve.inscrit', item)
    return _ok(
        f'{eleve.nom_complet} est inscrit en {classe.nom}. Matricule {matricule}.',
        id=eleve.id,
        matricule=matricule,
        url=_reverse('secretaire:detail_eleve', args=[eleve.id]),
    )


def prepare_desactiver_eleve(ctx, args):
    eleve = _find_eleve(ctx, args.get('query') or args.get('nom'))
    if not eleve:
        return _incomplete('desactiver_eleve', ['query'], 'Quel élève dois-je désactiver ?')
    return _pending(
        'desactiver_eleve',
        f'désactive {eleve.nom_complet}',
        id=eleve.id,
        nom=eleve.nom_complet,
    )


def apply_desactiver_eleve(ctx, draft):
    from school_admin.model.eleve_model import Eleve

    eleve = Eleve.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not eleve:
        return _err('Élève introuvable.')
    eleve.actif = False
    eleve.is_active = False
    eleve.save(update_fields=['actif', 'is_active'] if hasattr(eleve, 'actif') else ['is_active'])
    _emit(ctx, 'eleve.inscrit', {'id': eleve.id, 'action': 'desactive'})
    return _ok(f'{eleve.nom_complet} a été désactivé.')


def prepare_creer_professeur(ctx, args):
    nom = (args.get('nom') or '').strip()
    prenom = (args.get('prenom') or '').strip()
    telephone = (args.get('telephone') or '').strip()
    sexe = (args.get('sexe') or 'M').strip().upper()
    if sexe not in ('M', 'F'):
        sexe = 'M'
    matiere = _find_matiere(ctx, args.get('matiere'))
    extras = {
        'nom': nom,
        'prenom': prenom,
        'telephone': telephone,
        'sexe': sexe,
        'email': (args.get('email') or '').strip(),
        'matiere': matiere.nom if matiere else (args.get('matiere') or ''),
    }
    if matiere:
        extras['matiere_id'] = matiere.id
    prompts = {
        'nom': 'Quel est le nom de famille du professeur ?',
        'prenom': 'Quel est son prénom ?',
        'telephone': 'Quel est son numéro de téléphone ?',
    }
    if ctx.etablissement.type_etablissement != 'primary':
        prompts['matiere'] = 'Quelle est sa matière principale ?'
    asked = _ask_next_field('creer_professeur', extras, prompts)
    if asked:
        return asked
    return _pending(
        'creer_professeur',
        f'ajoute le professeur {prenom} {nom}',
        nom=nom,
        prenom=prenom,
        telephone=telephone,
        sexe=sexe,
        email=(args.get('email') or '').strip() or None,
        matiere_id=matiere.id if matiere else None,
        matiere_nom=matiere.nom if matiere else None,
        url=_reverse('professeur:liste_professeurs'),
    )


def apply_creer_professeur(ctx, draft):
    from school_admin.controllers.professeur_controller import ProfesseurController
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.professeur_model import Professeur
    from school_admin.services.live_serializers import serialize_professeur_liste_item

    with transaction.atomic():
        matricule = ProfesseurController.generate_matricule_professeur(ctx.etablissement)
        mot = ''.join(str(timezone.now().microsecond % 10) for _ in range(4))
        matiere = None
        if draft.get('matiere_id'):
            matiere = Matiere.objects.filter(
                pk=draft['matiere_id'], etablissement=ctx.etablissement
            ).first()
        professeur = Professeur(
            nom=draft.get('nom'),
            prenom=draft.get('prenom'),
            sexe=draft.get('sexe') or 'M',
            email=draft.get('email') or None,
            telephone=draft.get('telephone'),
            matiere_principale=matiere,
            niveau_enseignement=_niveau_enseignement(ctx.etablissement),
            numero_employe=matricule,
            username=matricule,
            etablissement=ctx.etablissement,
            mot_de_passe_provisoire=mot,
        )
        professeur.set_password(mot)
        professeur.save()
        item = serialize_professeur_liste_item(professeur)
        _emit(ctx, 'professeur.cree', item)
    return _ok(
        f'Professeur {professeur.nom_complet} ajouté. Matricule {matricule}.',
        id=professeur.id,
        matricule=matricule,
        url=_reverse('professeur:detail_professeur', args=[professeur.id]),
    )


def prepare_desactiver_professeur(ctx, args):
    prof = _find_professeur(ctx, args.get('query') or args.get('nom'))
    if not prof:
        return _incomplete('desactiver_professeur', ['query'], 'Quel professeur dois-je désactiver ?')
    return _pending(
        'desactiver_professeur',
        f'désactive {prof.nom_complet}',
        id=prof.id,
        nom=prof.nom_complet,
    )


def apply_desactiver_professeur(ctx, draft):
    from school_admin.model.professeur_model import Professeur

    prof = Professeur.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not prof:
        return _err('Professeur introuvable.')
    prof.actif = False
    prof.is_active = False
    prof.save(update_fields=['actif', 'is_active'])
    _emit(ctx, 'professeur.cree', {'id': prof.id, 'action': 'desactive'})
    return _ok(f'{prof.nom_complet} a été désactivé.')


def prepare_creer_personnel(ctx, args):
    nom = (args.get('nom') or '').strip()
    prenom = (args.get('prenom') or '').strip()
    telephone = (args.get('telephone') or '').strip()
    fonction = _normalize_fonction(args.get('fonction'))
    sexe = (args.get('sexe') or 'M').strip().upper()
    if sexe not in ('M', 'F'):
        sexe = 'M'
    extras = {
        'nom': nom,
        'prenom': prenom,
        'telephone': telephone,
        'fonction': fonction,
        'sexe': sexe,
        'email': (args.get('email') or '').strip(),
    }
    asked = _ask_next_field(
        'creer_personnel',
        extras,
        {
            'nom': 'Quel est le nom de famille du membre du personnel ?',
            'prenom': 'Quel est son prénom ?',
            'telephone': 'Quel est son numéro de téléphone ?',
        },
    )
    if asked:
        return asked
    return _pending(
        'creer_personnel',
        f'ajoute {prenom} {nom} ({fonction})',
        nom=nom,
        prenom=prenom,
        telephone=telephone,
        fonction=fonction,
        sexe=sexe,
        email=(args.get('email') or '').strip() or None,
        url=_reverse('personnel:liste_personnel'),
    )


def _normalize_fonction(raw):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif

    value = (raw or 'secretaire').strip().lower().replace('é', 'e').replace('è', 'e')
    aliases = {
        'secretaire': 'secretaire',
        'secrétaire': 'secretaire',
        'caissier': 'caissier',
        'caissiere': 'caissier',
        'comptable': 'comptable',
        'gestionnaire': 'gestionnaire',
        'surveillant': 'surveillant',
        'administrateur': 'administrateur',
        'intendant': 'intendant',
        'censeur': 'censeur',
    }
    if value in aliases:
        return aliases[value]
    codes = {code for code, _label in PersonnelAdministratif.TYPE_FONCTION_CHOICES}
    if value in codes:
        return value
    for code, label in PersonnelAdministratif.TYPE_FONCTION_CHOICES:
        if value == (label or '').lower().replace('é', 'e').replace('è', 'e'):
            return code
    return 'secretaire'


def apply_creer_personnel(ctx, draft):
    from school_admin.controllers.personnel_controller import PersonnelController
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.services.live_serializers import serialize_personnel_liste_item
    from school_admin.utils.permissions_personnel import (
        PERMISSIONS_DISPONIBLES,
        get_permissions_par_fonction,
    )

    fonction = _normalize_fonction(draft.get('fonction'))
    defaults = set(get_permissions_par_fonction(fonction))
    permissions = {key: key in defaults for key in PERMISSIONS_DISPONIBLES}
    with transaction.atomic():
        numero = PersonnelController.generate_numero_employe(fonction, ctx.etablissement)
        mot = PersonnelController.generate_mot_de_passe_provisoire()
        personnel = PersonnelAdministratif(
            nom=draft.get('nom'),
            prenom=draft.get('prenom'),
            sexe=draft.get('sexe') or 'M',
            email=draft.get('email') or None,
            telephone=draft.get('telephone'),
            fonction=fonction,
            username=numero,
            numero_employe=numero,
            etablissement=ctx.etablissement,
            mot_de_passe_provisoire=mot,
            permissions=permissions,
        )
        personnel.set_password(mot)
        personnel.save()
        item = serialize_personnel_liste_item(personnel)
        _emit(ctx, 'personnel.cree', item)
    return _ok(
        f'{personnel.nom_complet} a été ajouté au personnel.',
        id=personnel.id,
        url=_reverse('personnel:detail_personnel', args=[personnel.id]),
    )


def prepare_ajouter_depense(ctx, args):
    montant = _parse_money(args.get('montant'))
    libelle = (args.get('libelle') or args.get('motif_libelle') or '').strip()
    motif = (args.get('motif') or 'autre').strip()
    if not montant:
        return _incomplete('ajouter_depense', ['montant'], 'Quel montant pour cette dépense ?')
    return _pending(
        'ajouter_depense',
        f'enregistre une dépense de {montant}' + (f' ({libelle})' if libelle else ''),
        montant=str(montant),
        libelle=libelle,
        motif=motif,
        date_depense=(_parse_date(args.get('date')) or date.today()).isoformat(),
        url=_reverse('directeur:caisse_mois_directeur'),
    )


def apply_ajouter_depense(ctx, draft):
    from school_admin.model.caisse_etablissement_model import DepenseEtablissement

    montant = _parse_money(draft.get('montant'))
    if not montant:
        return _err('Montant invalide.')
    motifs_ok = {code for code, _label in DepenseEtablissement.MOTIF_CHOICES}
    motif = draft.get('motif') if draft.get('motif') in motifs_ok else 'autre'
    depense = DepenseEtablissement.objects.create(
        etablissement=ctx.etablissement,
        annee_scolaire=ctx.annee_scolaire,
        date_depense=_parse_date(draft.get('date_depense')) or date.today(),
        motif=motif,
        libelle=(draft.get('libelle') or '')[:160],
        montant=montant,
    )
    _emit(ctx, 'caisse.mise_a_jour', {'id': depense.id, 'action': 'ajoutee'})
    return _ok(
        f'Dépense de {montant} enregistrée.',
        id=depense.id,
        url=_reverse('directeur:caisse_mois_directeur'),
    )


def prepare_supprimer_depense(ctx, args):
    from school_admin.model.caisse_etablissement_model import DepenseEtablissement

    query = (args.get('query') or args.get('libelle') or '').strip()
    qs = DepenseEtablissement.objects.filter(etablissement=ctx.etablissement)
    depense = None
    if query.isdigit():
        depense = qs.filter(pk=int(query)).first()
    if depense is None and query:
        depense = qs.filter(libelle__icontains=query).order_by('-date_depense').first()
    if depense is None:
        depense = qs.order_by('-id').first()
    if not depense:
        return _incomplete('supprimer_depense', ['query'], 'Quelle dépense dois-je supprimer ?')
    return _pending(
        'supprimer_depense',
        f'supprime la dépense {depense.libelle or depense.montant}',
        id=depense.id,
        libelle=depense.libelle,
    )


def apply_supprimer_depense(ctx, draft):
    from school_admin.model.caisse_etablissement_model import DepenseEtablissement

    depense = DepenseEtablissement.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not depense:
        return _err('Dépense introuvable.')
    depense_id = depense.id
    depense.delete()
    _emit(ctx, 'caisse.mise_a_jour', {'id': depense_id, 'action': 'supprimee'})
    return _ok('Dépense supprimée.', url=_reverse('directeur:caisse_mois_directeur'))


def prepare_marquer_paie(ctx, args):
    prof = _find_professeur(ctx, args.get('query') or args.get('professeur'))
    if not prof:
        return _incomplete('marquer_paie', ['query'], 'Quel professeur dois-je marquer comme payé ?')
    return _pending(
        'marquer_paie',
        f'marque la paie de {prof.nom_complet}',
        id=prof.id,
        nom=prof.nom_complet,
        retenue_pct=str(args.get('retenue_pct') or '0'),
        url=_reverse('directeur:detail_volume_horaire', args=[prof.id]),
    )


def apply_marquer_paie(ctx, draft):
    from school_admin.controllers.volume_horaire_controller import VolumeHoraireController
    from school_admin.model.caisse_etablissement_model import PaieProfesseurPeriode
    from school_admin.model.professeur_model import Professeur
    from school_admin.services.caisse import net_apres_retenue
    from school_admin.utils.volume_horaire import resoudre_periode

    prof = Professeur.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not prof:
        return _err('Professeur introuvable.')
    periode = resoudre_periode(
        'mois',
        reference=date.today(),
        annee_scolaire=ctx.annee_scolaire,
    )
    creneaux = list(
        VolumeHoraireController._creneaux_publies(
            ctx.etablissement, ctx.annee_scolaire, professeur=prof
        )
    )
    resultat, _abs, _rempl = VolumeHoraireController._resultat_avec_absences(
        creneaux, periode, prof, ctx.etablissement
    )
    if resultat.montant is None:
        return _err('Renseignez d’abord le tarif horaire sur la fiche du professeur.')
    try:
        retenue = Decimal(str(draft.get('retenue_pct') or '0').replace(',', '.'))
    except (InvalidOperation, ValueError):
        retenue = Decimal('0')
    net = net_apres_retenue(resultat.montant, retenue)
    paie, created = PaieProfesseurPeriode.objects.get_or_create(
        professeur=prof,
        date_debut=periode.date_debut,
        date_fin=periode.date_fin,
        defaults={
            'etablissement': ctx.etablissement,
            'annee_scolaire': ctx.annee_scolaire,
            'heures': resultat.heures,
            'montant_brut': resultat.montant,
            'retenue_pct': retenue,
            'montant_net': net,
        },
    )
    _emit(ctx, 'paie.mise_a_jour', {'id': paie.id, 'professeur_id': prof.id})
    if not created:
        return _ok(f'Cette période est déjà marquée comme payée pour {prof.nom_complet}.')
    return _ok(
        f'Paie enregistrée pour {prof.nom_complet} : {net}.',
        url=_reverse('directeur:detail_volume_horaire', args=[prof.id]),
    )


def prepare_creer_filiere(ctx, args):
    if ctx.etablissement.type_etablissement != 'superieur':
        return _err('Les spécialités ne sont disponibles qu’en établissement supérieur.')
    nom = (args.get('nom') or args.get('query') or '').strip()
    if not nom:
        return _incomplete('creer_filiere', ['nom'], 'Quel nom pour la spécialité ?')
    sigle = (args.get('sigle') or '').strip()
    if not sigle:
        parts = [part for part in nom.split() if part]
        sigle = (
            parts[0][:4] if len(parts) == 1 else ''.join(part[0] for part in parts)
        ).upper()
    return _pending(
        'creer_filiere',
        f'crée la spécialité {nom}',
        nom=nom,
        sigle=sigle,
        domaine=(args.get('domaine') or '').strip() or None,
        mention=(args.get('mention') or '').strip() or None,
        url=_reverse('administrateur_etablissement:liste_filieres'),
    )


def apply_creer_filiere(ctx, draft):
    from school_admin.controllers.classe_controller import ClasseController
    from school_admin.model.academic_structure_model import Department

    nom = (draft.get('nom') or '').strip()
    if Department.objects.filter(etablissement=ctx.etablissement, nom__iexact=nom).exists():
        return _err(f'Une spécialité « {nom} » existe déjà.')
    sigle, err = ClasseController._validate_department_sigle(
        ctx.etablissement, draft.get('sigle') or ''
    )
    if err:
        return _err(err)
    dept = Department.objects.create(
        nom=nom,
        sigle=sigle,
        etablissement=ctx.etablissement,
        domaine=draft.get('domaine'),
        mention=draft.get('mention'),
    )
    _emit(ctx, 'filiere.mise_a_jour', {'id': dept.id, 'nom': dept.nom})
    return _ok(
        f'Spécialité {dept.nom} créée.',
        id=dept.id,
        url=_reverse('administrateur_etablissement:liste_filieres'),
    )


_STAFF_ACTIONS = (
    ActionSpec(
        'inscrire_eleve',
        'Inscrit un élève (nom, prénom, classe, sexe, naissance, parent).',
        {
            'nom': {'type': 'string'},
            'prenom': {'type': 'string'},
            'classe': {'type': 'string'},
            'sexe': {'type': 'string', 'enum': ['M', 'F']},
            'date_naissance': {'type': 'string'},
            'lieu_naissance': {'type': 'string'},
            'nationalite': {'type': 'string'},
            'parent_nom': {'type': 'string'},
            'parent_prenom': {'type': 'string'},
            'parent_telephone': {'type': 'string'},
            'parent_lien': {'type': 'string', 'enum': ['pere', 'mere', 'tuteur']},
        },
        prepare=prepare_inscrire_eleve,
        apply=apply_inscrire_eleve,
    ),
    ActionSpec(
        'desactiver_eleve',
        'Désactive le compte d’un élève.',
        {'query': {'type': 'string'}},
        destructive=True,
        prepare=prepare_desactiver_eleve,
        apply=apply_desactiver_eleve,
    ),
    ActionSpec(
        'creer_professeur',
        'Ajoute un professeur (nom, prénom, téléphone, matière).',
        {
            'nom': {'type': 'string'},
            'prenom': {'type': 'string'},
            'telephone': {'type': 'string'},
            'sexe': {'type': 'string', 'enum': ['M', 'F']},
            'email': {'type': 'string'},
            'matiere': {'type': 'string'},
        },
        prepare=prepare_creer_professeur,
        apply=apply_creer_professeur,
    ),
    ActionSpec(
        'desactiver_professeur',
        'Désactive un professeur.',
        {'query': {'type': 'string'}},
        destructive=True,
        prepare=prepare_desactiver_professeur,
        apply=apply_desactiver_professeur,
    ),
    ActionSpec(
        'creer_personnel',
        'Ajoute un membre du personnel administratif.',
        {
            'nom': {'type': 'string'},
            'prenom': {'type': 'string'},
            'telephone': {'type': 'string'},
            'fonction': {'type': 'string'},
            'sexe': {'type': 'string', 'enum': ['M', 'F']},
            'email': {'type': 'string'},
        },
        prepare=prepare_creer_personnel,
        apply=apply_creer_personnel,
    ),
    ActionSpec(
        'ajouter_depense',
        'Enregistre une dépense dans la caisse du mois.',
        {
            'montant': {'type': 'string'},
            'libelle': {'type': 'string'},
            'motif': {'type': 'string'},
            'date': {'type': 'string'},
        },
        prepare=prepare_ajouter_depense,
        apply=apply_ajouter_depense,
    ),
    ActionSpec(
        'supprimer_depense',
        'Supprime une dépense de caisse.',
        {'query': {'type': 'string'}, 'libelle': {'type': 'string'}},
        destructive=True,
        prepare=prepare_supprimer_depense,
        apply=apply_supprimer_depense,
    ),
    ActionSpec(
        'marquer_paie',
        'Marque la paie d’un professeur pour la période en cours.',
        {'query': {'type': 'string'}, 'professeur': {'type': 'string'}, 'retenue_pct': {'type': 'string'}},
        prepare=prepare_marquer_paie,
        apply=apply_marquer_paie,
    ),
    ActionSpec(
        'creer_filiere',
        'Crée une spécialité / filière (établissement supérieur).',
        {
            'nom': {'type': 'string'},
            'sigle': {'type': 'string'},
            'domaine': {'type': 'string'},
            'mention': {'type': 'string'},
        },
        prepare=prepare_creer_filiere,
        apply=apply_creer_filiere,
    ),
)

for _spec in _STAFF_ACTIONS:
    register_action(_spec)
