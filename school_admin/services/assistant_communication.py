"""Outils « assistant personnel » de la direction : rappels programmés, messages ciblés, courriers libres,
notifications, impressions et suites de sanctions.

Les écritures restent soumises à la carte de confirmation « oui / modifier / annuler ».
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from school_admin.services.assistant_actions import (
    ActionSpec,
    _err,
    _incomplete,
    _ok,
    _pending,
    _reverse,
    register_action,
)
from school_admin.services.assistant_gestion import _sans_accents, _schema

_STR = {'type': 'string'}
JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
MOIS = {'janvier': 1, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6, 'juillet': 7, 'aout': 8,
        'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12}


# --------------------------------------------------------------------------- dates parlées
def parser_quand(texte, maintenant=None):
    """« demain à 9 h », « lundi 10h30 », « dans 2 heures », « le 25/11 à 14 h », « ce soir »,
    « 2026-11-25 09:00 »… → datetime locale avec fuseau, ou None si rien de compris."""
    maintenant = timezone.localtime(maintenant or timezone.now())
    t = _sans_accents(texte or '').strip()
    if not t:
        return None
    m = re.search(r'dans\s+(\d+|une?|deux|trois)\s*(minute|min|heure|h\b|jour|semaine)', t)
    if m:
        n = {'un': 1, 'une': 1, 'deux': 2, 'trois': 3}.get(m.group(1)) or int(m.group(1))
        unite = m.group(2)
        delta = (timedelta(minutes=n) if unite.startswith('min') else
                 timedelta(hours=n) if unite.startswith('h') else
                 timedelta(weeks=n) if unite.startswith('sem') else timedelta(days=n))
        return maintenant + delta
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})[t ](\d{1,2}):(\d{2})', t)
    if m:
        return timezone.make_aware(datetime(*(int(x) for x in m.groups())))

    jour = None
    if 'apres-demain' in t or 'apres demain' in t:
        jour = maintenant.date() + timedelta(days=2)
    elif 'demain' in t:
        jour = maintenant.date() + timedelta(days=1)
    elif "aujourd" in t or 'ce soir' in t or 'ce matin' in t or 'cet apres' in t or 'tout a l' in t:
        jour = maintenant.date()
    if jour is None:
        m = re.search(r'\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b', t)
        if m:
            annee = int(m.group(3)) if m.group(3) else maintenant.year
            annee = annee + 2000 if annee < 100 else annee
            try:
                jour = datetime(annee, int(m.group(2)), int(m.group(1))).date()
            except ValueError:
                return None
            if not m.group(3) and jour < maintenant.date():
                jour = jour.replace(year=jour.year + 1)
    if jour is None:
        for nom, numero in MOIS.items():
            m = re.search(r'\b(\d{1,2})(?:er)?\s+' + nom, t)
            if m:
                jour = datetime(maintenant.year, numero, int(m.group(1))).date()
                if jour < maintenant.date():
                    jour = jour.replace(year=jour.year + 1)
                break
    if jour is None:
        for i, nom in enumerate(JOURS):
            if re.search(r'\b' + nom + r'\b', t):
                ecart = (i - maintenant.weekday()) % 7 or 7
                if 'prochain' not in t and i == maintenant.weekday():
                    ecart = 7
                jour = maintenant.date() + timedelta(days=ecart)
                break

    heure = None
    m = re.search(r'\b(\d{1,2})\s*(?:h|heures?|:)\s*(\d{2})?\b', t)
    if m and int(m.group(1)) < 24:
        heure = time(int(m.group(1)), int(m.group(2) or 0))
    elif 'midi' in t:
        heure = time(12, 0)
    elif 'ce soir' in t or 'soir' in t:
        heure = time(18, 0)
    elif 'matin' in t:
        heure = time(8, 0)
    elif 'apres-midi' in t or 'apres midi' in t:
        heure = time(15, 0)
    if jour is None and heure is None:
        return None
    if jour is None:
        jour = maintenant.date()
        if heure <= maintenant.time():
            jour += timedelta(days=1)
    heure = heure or time(8, 0)
    return timezone.make_aware(datetime.combine(jour, heure))


def _jour_parle(dt):
    local = timezone.localtime(dt)
    jours = JOURS[local.weekday()]
    return f"{jours} {local:%d/%m/%Y} à {local:%H:%M}"


def _qs_rappels(ctx):
    from school_admin.model.rappel_model import RappelPersonnel

    return RappelPersonnel.objects.filter(etablissement=ctx.etablissement, personnel=getattr(ctx, 'personnel', None))


# =========================================================================== rappels personnels
def tool_mes_rappels(ctx, args):
    a_venir = _qs_rappels(ctx).filter(envoye=False).order_by('echeance')[:20]
    return {
        'rappels': [{'id': r.id, 'quand': _jour_parle(r.echeance), 'texte': r.texte} for r in a_venir],
        'nb': len(a_venir),
    }


def prepare_creer_rappel(ctx, args):
    texte = (args.get('texte') or args.get('objet') or '').strip()
    quand_txt = (args.get('quand') or args.get('date') or '').strip()
    if not texte:
        return _incomplete('creer_rappel', ['texte'], 'De quoi dois-je vous rappeler ?', quand=quand_txt)
    quand = parser_quand(quand_txt)
    if quand is None:
        return _incomplete('creer_rappel', ['quand'], 'Quand dois-je vous le rappeler ? (par exemple « demain à 9 h »)',
                           texte=texte)
    if quand <= timezone.now():
        return _err('Ce moment est déjà passé : donnez une date et une heure à venir.')
    return _pending('creer_rappel', f"vous rappelle « {texte} » {_jour_parle(quand)}",
                    texte=texte[:300], echeance=quand.isoformat())


def apply_creer_rappel(ctx, draft):
    from school_admin.model.rappel_model import RappelPersonnel

    try:
        echeance = datetime.fromisoformat(draft.get('echeance'))
    except (TypeError, ValueError):
        return _err('Date du rappel invalide.')
    if timezone.is_naive(echeance):
        echeance = timezone.make_aware(echeance)
    rappel = RappelPersonnel.objects.create(
        etablissement=ctx.etablissement, personnel=getattr(ctx, 'personnel', None),
        texte=(draft.get('texte') or '')[:300], echeance=echeance)
    return _ok(f"C’est noté : je vous le rappelle {_jour_parle(echeance)}.", id=rappel.id)


def prepare_supprimer_rappel(ctx, args):
    qs = _qs_rappels(ctx).filter(envoye=False)
    raw = (args.get('query') or '').strip()
    rappel = None
    if raw.isdigit():
        rappel = qs.filter(pk=int(raw)).first()
    if rappel is None and raw:
        for mot in raw.split():
            if len(mot) > 2:
                qs = qs.filter(texte__icontains=mot)
        rappel = qs.order_by('echeance').first()
    if rappel is None:
        return _incomplete('supprimer_rappel', ['query'], 'Quel rappel dois-je supprimer ?')
    return _pending('supprimer_rappel', f"supprime le rappel « {rappel.texte} » prévu {_jour_parle(rappel.echeance)}",
                    id=rappel.id)


def apply_supprimer_rappel(ctx, draft):
    rappel = _qs_rappels(ctx).filter(pk=draft.get('id'), envoye=False).first()
    if not rappel:
        return _err('Rappel introuvable ou déjà envoyé.')
    rappel.delete()
    return _ok('Rappel supprimé.')


# =========================================================================== messages ciblés
CIBLES = {
    'parents_eleve': "aux parents d'un élève",
    'parents_classe': "aux parents d'une classe",
    'enseignant': 'à un enseignant',
    'enseignants_classe': "aux enseignants d'une classe",
    'tous_enseignants': 'à tous les enseignants',
    'personnel': "à un membre du personnel",
    'tout_personnel': "à tout le personnel administratif",
}


def _cible(args):
    t = _sans_accents(args.get('cible') or '')
    if t in CIBLES:
        return t
    if 'parent' in t:
        return 'parents_classe' if args.get('classe') and not args.get('eleve') else 'parents_eleve'
    if 'enseignant' in t or 'prof' in t:
        if 'tous' in t or 'tout' in t:
            return 'tous_enseignants'
        return 'enseignants_classe' if args.get('classe') and not args.get('nom') else 'enseignant'
    if 'personnel' in t or 'administra' in t:
        return 'tout_personnel' if ('tout' in t or not args.get('nom')) else 'personnel'
    return None


def _destinataires(ctx, cible, args):
    """Liste de (utilisateur, élève ou None) et libellé lisible des destinataires."""
    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.lien_familial_model import LienFamilial
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur
    from school_admin.services.assistant_tools import _find_classe, _find_eleve

    if cible in ('parents_eleve', 'parents_classe'):
        if cible == 'parents_eleve':
            eleve = _find_eleve(ctx, args.get('eleve') or args.get('nom'))
            if not eleve:
                return None, "Quel élève ?"
            eleves, libelle = [eleve], f"parents de {eleve.nom_complet}"
        else:
            classe = _find_classe(ctx, args.get('classe'))
            if not classe:
                return None, 'Quelle classe ?'
            eleves = list(Eleve.objects.filter(classe=classe, etablissement=ctx.etablissement, actif=True))
            libelle = f"parents de la classe {classe.nom}"
        liens = LienFamilial.objects.filter(eleve__in=eleves, actif=True, statut='valide').select_related('parent', 'eleve')
        return [(l.parent, l.eleve) for l in liens], libelle
    profs = Professeur.objects.filter(etablissement=ctx.etablissement, actif=True)
    if cible == 'enseignant':
        nom = (args.get('nom') or '').strip()
        for m in nom.split():
            profs = profs.filter(Q(nom__icontains=m) | Q(prenom__icontains=m))
        prof = profs.first() if nom else None
        return ([(prof, None)], prof.nom_complet) if prof else (None, 'Quel enseignant ?')
    if cible == 'enseignants_classe':
        classe = _find_classe(ctx, args.get('classe'))
        if not classe:
            return None, 'Quelle classe ?'
        ids = AffectationProfesseur.objects.filter(classe=classe, actif=True).values_list('professeur_id', flat=True)
        return [(p, None) for p in profs.filter(pk__in=ids)], f"enseignants de la classe {classe.nom}"
    if cible == 'tous_enseignants':
        return [(p, None) for p in profs], 'tous les enseignants'
    pers = PersonnelAdministratif.objects.filter(etablissement=ctx.etablissement, actif=True)
    if cible == 'personnel':
        nom = (args.get('nom') or '').strip()
        for m in nom.split():
            pers = pers.filter(Q(nom__icontains=m) | Q(prenom__icontains=m))
        p = pers.first() if nom else None
        return ([(p, None)], p.nom_complet) if p else (None, 'Quel membre du personnel ?')
    return [(p, None) for p in pers], 'tout le personnel administratif'


def prepare_envoyer_message(ctx, args):
    cible = _cible(args)
    if cible is None:
        return _incomplete('envoyer_message', ['cible'],
                           'À qui dois-je envoyer ce message : parents d’un élève, parents d’une classe, un enseignant, '
                           'les enseignants ou le personnel ?')
    message = (args.get('message') or args.get('contenu') or '').strip()
    if not message:
        return _incomplete('envoyer_message', ['message'], 'Que dois-je écrire ?', cible=cible)
    liste, libelle = _destinataires(ctx, cible, args)
    if liste is None:
        return _incomplete('envoyer_message', ['eleve' if 'parent' in cible else 'nom'], libelle, cible=cible,
                           message=message)
    if not liste:
        return _err(f"Personne à prévenir pour {libelle} (aucun compte relié).")
    titre = (args.get('titre') or 'Message de la direction').strip()[:180]
    nb = len({(type(u), u.pk) for u, _e in liste})
    return _pending('envoyer_message',
                    f"envoie le message « {titre} » {CIBLES[cible]} ({libelle}, {nb} destinataire(s)) : {message[:300]}",
                    cible=cible, titre=titre, message=message[:4000],
                    eleve=args.get('eleve') or '', classe=args.get('classe') or '', nom=args.get('nom') or '')


def apply_envoyer_message(ctx, draft):
    from school_admin.model.notification_enseignant_model import NotificationEnseignant
    from school_admin.model.notification_parent_model import NotificationParent
    from school_admin.model.rappel_model import NotificationPersonnel
    from school_admin.services.push_delivery import enqueue

    liste, libelle = _destinataires(ctx, draft.get('cible'), draft)
    if not liste:
        return _err('Aucun destinataire trouvé.')
    titre, message = draft.get('titre') or 'Message de la direction', draft.get('message') or ''
    donnees = {'source': 'assistant', 'type': 'message_direction'}
    destinataires = []
    for user, eleve in liste:
        role = user._meta.model_name
        if role == 'parent':
            NotificationParent.objects.create(parent=user, eleve=eleve, annee_scolaire=ctx.annee_scolaire,
                                              titre=titre, message=message, type_notification='information',
                                              donnees=donnees)
        elif role == 'professeur':
            NotificationEnseignant.objects.create(enseignant=user, annee_scolaire=ctx.annee_scolaire, titre=titre,
                                                  message=message, type_notification='information', donnees=donnees)
        elif role == 'personneladministratif':
            NotificationPersonnel.objects.create(personnel=user, titre=titre, message=message,
                                                 type_notification='information', donnees=donnees)
        destinataires.append(user)
    if destinataires:
        enqueue(destinataires, titre, message[:400], {'type': 'message_direction'})
    return _ok(f"Message envoyé à {libelle} ({len({(type(u), u.pk) for u in destinataires})} personne(s)).")


# =========================================================================== notifications
def _mes_notifications(ctx):
    from school_admin.model.notification_directeur_model import NotificationDirecteur
    from school_admin.model.rappel_model import NotificationPersonnel

    if getattr(ctx, 'personnel', None) is not None:
        return NotificationPersonnel.objects.filter(personnel=ctx.personnel, lu=False)
    return NotificationDirecteur.objects.filter(etablissement=ctx.etablissement, lu=False)


def prepare_marquer_notifications_lues(ctx, args):
    nb = _mes_notifications(ctx).count()
    if not nb:
        return _err('Vous n’avez aucune notification non lue.')
    return _pending('marquer_notifications_lues', f"marque vos {nb} notification(s) non lue(s) comme lues")


def apply_marquer_notifications_lues(ctx, draft):
    nb = _mes_notifications(ctx).update(lu=True, statut='lu', date_lecture=timezone.now())
    return _ok(f"{nb} notification(s) marquée(s) comme lues.")


# =========================================================================== courriers libres
TYPES_COURRIER = {'lettre': 'lettre', 'note': 'note_service', 'service': 'note_service', 'compte': 'compte_rendu',
                  'rendu': 'compte_rendu', 'pv': 'compte_rendu', 'proces': 'compte_rendu'}


def tool_courriers(ctx, args):
    from school_admin.model.rappel_model import CourrierEtablissement

    return {
        'courriers': [{'id': c.id, 'objet': c.objet, 'type': c.get_type_courrier_display(),
                       'destinataire': c.destinataire, 'date': c.date_creation.date().isoformat(),
                       'url': _reverse('directeur:courrier_detail', [c.id])}
                      for c in CourrierEtablissement.objects.filter(etablissement=ctx.etablissement)[:15]],
        'url': _reverse('directeur:courriers'),
    }


def prepare_rediger_courrier(ctx, args):
    objet = (args.get('objet') or '').strip()
    contenu = (args.get('contenu') or '').strip()
    if not objet:
        return _incomplete('rediger_courrier', ['objet'], 'Quel est l’objet du courrier ?')
    if len(contenu) < 20:
        return _incomplete('rediger_courrier', ['contenu'],
                           'Rédige le texte complet du courrier (paragraphes séparés par une ligne vide), puis rappelle '
                           'rediger_courrier avec ce contenu.', objet=objet)
    t = _sans_accents(args.get('type') or '')
    type_courrier = next((v for k, v in TYPES_COURRIER.items() if k in t), 'lettre')
    destinataire = (args.get('destinataire') or '').strip()[:200]
    return _pending('rediger_courrier',
                    f"prépare le courrier « {objet} »{' pour ' + destinataire if destinataire else ''} "
                    f"({len(contenu.split())} mots), prêt à imprimer avec l’en-tête de l’école",
                    type_courrier=type_courrier, objet=objet[:200], destinataire=destinataire,
                    contenu=contenu[:8000], signataire=(args.get('signataire') or '').strip()[:160])


def apply_rediger_courrier(ctx, draft):
    from school_admin.model.rappel_model import CourrierEtablissement

    personnel = getattr(ctx, 'personnel', None)
    courrier = CourrierEtablissement.objects.create(
        etablissement=ctx.etablissement, type_courrier=draft.get('type_courrier') or 'lettre',
        objet=draft.get('objet') or 'Courrier', destinataire=draft.get('destinataire') or '',
        contenu=draft.get('contenu') or '', signataire=draft.get('signataire') or '',
        redige_par=personnel.nom_complet if personnel else 'Direction')
    return _ok('Courrier prêt : je l’ouvre pour l’impression.', id=courrier.id,
               url=_reverse('directeur:courrier_detail', [courrier.id]), titre=courrier.objet)


# =========================================================================== impressions
DOCUMENTS = {
    'liste_eleves': ('secretaire:imprimer_liste_eleves', 'eleves_liste', 'Liste des élèves'),
    'liste_nominative': ('directeur:imprimer_liste_nominative', 'eleves_liste', 'Liste nominative'),
    'liste_presence': ('directeur:imprimer_liste_presence', 'presences_liste', 'Feuille de présence du mois'),
    'emploi_du_temps': ('administrateur_etablissement:imprimer_emploi_du_temps', 'classes_detail', 'Emploi du temps'),
    'fiches_inscription': ('directeur:imprimer_fiches_classe', 'eleves_liste', "Fiches d'inscription"),
    'releve_notes': ('directeur:imprimer_releve_notes', 'notes_liste', 'Relevé de notes de la classe'),
    'bulletins': ('directeur:imprimer_bulletins_classe', 'bulletins_voir', 'Bulletins de la classe'),
    'impayes': ('directeur:liste_impayes_directeur', 'comptabilite_voir', 'Liste des impayés'),
}


def tool_imprimer_document(ctx, args):
    from school_admin.services.assistant_tools import _find_classe
    from school_admin.utils.permissions_personnel import has_permission

    t = _sans_accents(args.get('document') or '')
    cle = next((k for k in DOCUMENTS if k in t.replace(' ', '_')), None)
    if cle is None:
        mots = (('presence', 'liste_presence'), ('appel', 'liste_presence'), ('nominative', 'liste_nominative'),
                ('emploi', 'emploi_du_temps'), ('fiche', 'fiches_inscription'), ('releve', 'releve_notes'),
                ('note', 'releve_notes'), ('bulletin', 'bulletins'), ('impaye', 'impayes'), ('eleve', 'liste_eleves'))
        cle = next((v for k, v in mots if k in t), None)
    if cle is None:
        return {'erreur': 'Quel document ? ' + ', '.join(v[2] for v in DOCUMENTS.values()) + '.'}
    route, permission, titre = DOCUMENTS[cle]
    personnel = getattr(ctx, 'personnel', None)
    if personnel is not None and not has_permission(personnel, permission):
        return {'erreur': "Vous n’avez pas l’autorisation d’imprimer ce document."}
    if cle == 'impayes':
        return {'statut': 'ok', 'titre': titre, 'url': _reverse(route), 'ouvrir': True}
    classe = _find_classe(ctx, args.get('classe'))
    if not classe:
        return {'erreur': 'Pour quelle classe ?'}
    if cle == 'liste_presence':
        aujourd_hui = timezone.localdate()
        url = _reverse(route, [classe.id, aujourd_hui.month, aujourd_hui.year])
    else:
        url = _reverse(route, [classe.id])
    if not url:
        return {'erreur': 'Ce document n’est pas disponible.'}
    return {'statut': 'ok', 'titre': f"{titre} — {classe.nom}", 'url': url, 'ouvrir': True}


# =========================================================================== sanctions
def _trouver_sanction(ctx, args, executee=None):
    from school_admin.model.sanction_model import Sanction
    from school_admin.services.assistant_tools import _find_eleve

    eleve = _find_eleve(ctx, args.get('eleve') or args.get('query'))
    if not eleve:
        return None, None
    qs = Sanction.objects.filter(etablissement=ctx.etablissement, eleve=eleve)
    if executee is not None:
        qs = qs.filter(executee=executee)
    return eleve, qs.order_by('-date_sanction', '-id').first()


def prepare_lever_sanction(ctx, args):
    eleve, sanction = _trouver_sanction(ctx, args, executee=False)
    if eleve is None:
        return _incomplete('lever_sanction', ['eleve'], 'La sanction de quel élève ?')
    if sanction is None:
        return _err(f"{eleve.nom_complet} n’a pas de sanction en cours.")
    motif = (args.get('motif') or '').strip()
    if not motif:
        return _incomplete('lever_sanction', ['motif'], 'Pour quelle raison la lever (sanction purgée, bonne conduite…) ?',
                           eleve=eleve.nom_complet)
    return _pending('lever_sanction',
                    f"lève la sanction de {eleve.nom_complet} ({sanction.get_type_sanction_display()} du "
                    f"{sanction.date_sanction:%d/%m/%Y}) : elle est notée terminée, motif « {motif} ». Elle reste dans l’historique.",
                    id=sanction.id, motif=motif[:200])


def apply_lever_sanction(ctx, draft):
    from school_admin.model.sanction_model import Sanction

    sanction = Sanction.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not sanction:
        return _err('Sanction introuvable.')
    maintenant = timezone.now()
    note = f"Levée le {timezone.localtime(maintenant):%d/%m/%Y} : {draft.get('motif') or ''}".strip()
    sanction.executee = True
    sanction.date_execution = maintenant
    sanction.description = f"{sanction.description}\n{note}".strip() if sanction.description else note
    sanction.save(update_fields=['executee', 'date_execution', 'description', 'date_modification'])
    return _ok(f"Sanction de {sanction.eleve.nom_complet} levée.")


def prepare_supprimer_sanction(ctx, args):
    eleve, sanction = _trouver_sanction(ctx, args)
    if eleve is None:
        return _incomplete('supprimer_sanction', ['eleve'], 'La sanction de quel élève faut-il supprimer ?')
    if sanction is None:
        return _err(f"{eleve.nom_complet} n’a aucune sanction.")
    return _pending('supprimer_sanction',
                    f"supprime définitivement la sanction de {eleve.nom_complet} "
                    f"({sanction.get_type_sanction_display()} du {sanction.date_sanction:%d/%m/%Y}), donnée par erreur",
                    id=sanction.id)


def apply_supprimer_sanction(ctx, draft):
    from school_admin.model.sanction_model import Sanction

    sanction = Sanction.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not sanction:
        return _err('Sanction introuvable.')
    nom = sanction.eleve.nom_complet
    sanction.delete()
    return _ok(f"Sanction de {nom} supprimée.")


# =========================================================================== enregistrement
COMMUNICATION_READ_HANDLERS = {
    'get_mes_rappels': tool_mes_rappels,
    'get_courriers': tool_courriers,
    'imprimer_document': tool_imprimer_document,
}

COMMUNICATION_READ_SCHEMA = [
    _schema('get_mes_rappels', "Rappels personnels à venir de la personne connectée.", {}),
    _schema('get_courriers', "Derniers courriers rédigés (lettres, notes de service, comptes rendus) avec leur lien d’impression.", {}),
    _schema('imprimer_document',
            "Ouvre un document prêt à imprimer : liste des élèves, liste nominative, feuille de présence du mois, "
            "emploi du temps, fiches d’inscription, relevé de notes, bulletins d’une classe, ou liste des impayés.",
            {'document': {'type': 'string', 'description': 'liste_eleves, liste_nominative, liste_presence, emploi_du_temps, '
                                                           'fiches_inscription, releve_notes, bulletins ou impayes'},
             'classe': {'type': 'string', 'description': 'Nom ou code de la classe'}}, ('document',)),
]

SPECS = [
    ActionSpec('creer_rappel',
               "Programme un rappel pour la personne connectée (« rappelle-moi lundi à 9 h d’appeler le fournisseur »). "
               "Il arrive à l’heure dite en notification et sur le téléphone.",
               {'texte': {'type': 'string', 'description': 'Ce qu’il faut rappeler'},
                'quand': {'type': 'string', 'description': 'demain à 9 h, lundi 10h30, dans 2 heures, le 25/11 à 14 h…'}},
               required=('texte', 'quand'), prepare=prepare_creer_rappel, apply=apply_creer_rappel),
    ActionSpec('supprimer_rappel', "Supprime un rappel personnel à venir.",
               {'query': {'type': 'string', 'description': 'Texte ou numéro du rappel'}},
               required=('query',), prepare=prepare_supprimer_rappel, apply=apply_supprimer_rappel),
    ActionSpec('envoyer_message',
               "Envoie un message (notification + téléphone) ciblé : aux parents d’un élève, aux parents d’une classe, "
               "à un enseignant, aux enseignants d’une classe, à tous les enseignants, à un membre du personnel ou à tout "
               "le personnel. Rédige toi-même un message clair et poli si l’utilisateur ne le dicte pas.",
               {'cible': {'type': 'string', 'description': ', '.join(CIBLES)}, 'eleve': _STR, 'classe': _STR,
                'nom': {'type': 'string', 'description': 'Enseignant ou membre du personnel visé'},
                'titre': _STR, 'message': _STR},
               required=('cible', 'message'), prepare=prepare_envoyer_message, apply=apply_envoyer_message),
    ActionSpec('marquer_notifications_lues', "Marque toutes les notifications non lues de la personne connectée comme lues.",
               {}, prepare=prepare_marquer_notifications_lues, apply=apply_marquer_notifications_lues),
    ActionSpec('rediger_courrier',
               "Rédige un courrier libre imprimable avec l’en-tête de l’école : lettre, note de service ou compte rendu. "
               "Écris toi-même le texte complet (formule d’appel, paragraphes séparés par une ligne vide, formule de "
               "politesse) à partir de la demande.",
               {'type': {'type': 'string', 'description': 'lettre, note_service ou compte_rendu'}, 'objet': _STR,
                'destinataire': _STR, 'contenu': {'type': 'string', 'description': 'Texte complet du courrier'},
                'signataire': {'type': 'string', 'description': 'Ex. « Le Directeur »'}},
               required=('objet', 'contenu'), prepare=prepare_rediger_courrier, apply=apply_rediger_courrier),
    ActionSpec('lever_sanction',
               "Lève la sanction en cours d’un élève (purgée, bonne conduite) : elle est notée terminée avec le motif "
               "et reste dans l’historique.",
               {'eleve': _STR, 'motif': _STR}, required=('eleve',), prepare=prepare_lever_sanction,
               apply=apply_lever_sanction),
    ActionSpec('supprimer_sanction', "Supprime définitivement la dernière sanction d’un élève, donnée par erreur.",
               {'eleve': _STR}, required=('eleve',), destructive=True, prepare=prepare_supprimer_sanction,
               apply=apply_supprimer_sanction),
]

for _spec in SPECS:
    register_action(_spec)
