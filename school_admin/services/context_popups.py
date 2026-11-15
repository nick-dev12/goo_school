"""Situations utiles à l'arrivée dans un espace ; aucune écriture lors du calcul."""
import hashlib
import json
from datetime import timedelta
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, F
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from school_admin.model.context_popup_model import ContextPopupState


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def url(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ''


def stage_for(deadline, today=None):
    """Seuil de rappel d'une échéance : j-3, j-1, j, puis trois relances de retard au plus."""
    days = (deadline - (today or timezone.localdate())).days
    if days > 1:
        return 'j-3'
    if days == 1:
        return 'j-1'
    if days == 0:
        return 'j'
    return f'retard-{min((-days - 1) // 3, 2)}'


def due_label(deadline, today=None):
    days = (deadline - (today or timezone.localdate())).days
    if days == 0:
        return "Aujourd'hui"
    if days == 1:
        return 'Demain'
    if days > 1:
        return f'Dans {days} jours'
    return "En retard d'un jour" if days == -1 else f'En retard de {-days} jours'


def card(key, title, text, href, label, version, priority=30, context='', tone='info', deadline=None,
         code='', icon='', family='', group=None, count=None, push=True, eleve_id=None, once=False):
    """Carte normalisée : la même définition sert au popup, à la cloche et au push planifié."""
    if not href or not href.startswith('/') or href.startswith('//'):
        return None
    today = timezone.localdate()
    if group is None:
        group = 'soon' if deadline and (deadline - today).days > 1 else 'now'
    return dict(key=key, title=title, text=text, url=href, action=label, version=digest(version),
                priority=priority, context=context, tone=tone,
                deadline=deadline.isoformat() if deadline else None,
                due=due_label(deadline, today) if deadline else '',
                late=bool(deadline and deadline < today),
                stage=stage_for(deadline, today) if deadline else '',
                code=code, icon=icon or tone, family=family, group=group, count=count,
                push=bool(push and group != 'news'), eleve_id=eleve_id, once=once)


def year_for(etab):
    from school_admin.model.annee_scolaire_model import AnneeScolaire
    return AnneeScolaire.get_session_active(etab) if etab else None


def school_context(eleve, year):
    from school_admin.model.inscription_eleve_model import InscriptionEleve
    inscription = InscriptionEleve.objects.filter(eleve=eleve, etablissement=eleve.etablissement, annee_scolaire=year).select_related('classe').first()
    return inscription.classe if inscription else None


def student_situations(eleve, parent=False):
    from school_admin.model.exercice_maison_model import ExerciceMaison
    from school_admin.model.evaluation_model import Evaluation
    from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
    from school_admin.model.convocation_model import Convocation
    from school_admin.services.recouvrement import resume_dette_eleve
    today = timezone.localdate()
    year = year_for(eleve.etablissement)
    classe = school_context(eleve, year) if year else None
    if not classe:
        return []
    ctx = f'{eleve.prenom} · {classe.nom} · {year.libelle}'
    prefix = f'child:{eleve.pk}:year:{year.pk}'
    result = []
    devoir_url = url('school_admin:dashboard_enfant', eleve.pk) if parent else url('eleve:devoirs_eleve')
    for devoir in ExerciceMaison.objects.filter(classe=classe, annee_scolaire=year, etablissement=eleve.etablissement,
            actif=True, date_rendu__gte=today, date_rendu__lte=today + timedelta(days=3)).order_by('date_rendu')[:3]:
        days = (devoir.date_rendu - today).days
        threshold = 'today' if days == 0 else 'soon'
        result.append(card(f'{prefix}:homework:{devoir.pk}', 'Un devoir à préparer',
            f'{devoir.titre} — à rendre le {devoir.date_rendu:%d/%m}.', devoir_url, 'Voir le devoir',
            [devoir.titre, devoir.description, devoir.date_rendu, threshold], 80 if days <= 1 else 55,
            ctx, 'work', devoir.date_rendu, code='PAR-04' if parent else 'ELV-01', icon='devoir',
            family='devoirs', eleve_id=eleve.pk))
    primaire = (classe.niveau or '').lower() == 'primaire'
    model = EvaluationPrimaire if primaire else Evaluation
    for evaluation in model.objects.filter(classe=classe, annee_scolaire=year, actif=True,
            date_evaluation__gte=today, date_evaluation__lte=today + timedelta(days=3)).select_related('matiere').order_by('date_evaluation')[:2]:
        target = devoir_url if parent else url('eleve:notes_evaluations')
        result.append(card(f'{prefix}:evaluation:{model.__name__}:{evaluation.pk}', 'Une évaluation approche',
            f'{evaluation.titre} — {evaluation.date_evaluation:%d/%m}.', target, 'Voir les évaluations',
            [evaluation.titre, evaluation.date_evaluation, evaluation.matiere_id], 60, ctx, 'work', evaluation.date_evaluation,
            code='PAR-04' if parent else 'ELV-02', icon='evaluation', family='evaluations', eleve_id=eleve.pk))
    for convocation in Convocation.objects.filter(eleve=eleve, etablissement=eleve.etablissement, actif=True,
            date_convocation__gte=today, date_convocation__lte=today + timedelta(days=7)).order_by('date_convocation')[:1]:
        target = url('school_admin:dashboard_enfant', eleve.pk) if parent else url('eleve:convocations_eleve')
        result.append(card(f'{prefix}:convocation:{convocation.pk}', 'Une convocation à consulter',
            f'{convocation.objet} — le {convocation.date_convocation:%d/%m}, {convocation.heure_convocation:%H:%M}.' if convocation.heure_convocation else f'{convocation.objet} — le {convocation.date_convocation:%d/%m}.',
            target, 'Voir la convocation', [convocation.objet, convocation.date_convocation, convocation.heure_convocation, convocation.lieu], 95, ctx, 'important', convocation.date_convocation,
            code='PAR-03' if parent else 'ELV-04', icon='convocation', family='convocations', eleve_id=eleve.pk))
    if parent and eleve.etablissement.module_comptabilite:
        resume = resume_dette_eleve(eleve, eleve.etablissement, year)
        due = [charge for charge in resume.charges if charge.reste > 0 and charge.date_echeance and charge.date_echeance <= today + timedelta(days=3)]
        if due:
            first = min(charge.date_echeance for charge in due)
            stage = 'late' if first < today else 'today' if first == today else 'soon'
            amount = sum(charge.reste for charge in due)
            result.append(card(f'{prefix}:fees', 'Une échéance de scolarité',
                f'{amount:,.0f} {eleve.etablissement.devise_monnaie or "FCFA"} restent à régler pour les échéances proches ou dépassées. Prochaine date : {first:%d/%m}.',
                url('school_admin:scolarite_parent'), 'Voir la scolarité',
                [stage, [(charge.kind, charge.objet_id, charge.reste, charge.date_echeance) for charge in due]],
                75, ctx, 'finance', first, code='PAR-01', icon='scolarite', family='scolarite', eleve_id=eleve.pk))
    try:
        from school_admin.services.rappels.famille import situations
        result.extend(situations(eleve, year, classe, parent, ctx, prefix))
    except Exception:  # une source indisponible ne doit pas masquer les autres rappels
        import logging
        logging.getLogger(__name__).exception('Rappels élève/parent indisponibles (%s)', eleve.pk)
    return result


def recent_notifications(user, role, children=None):
    from django.apps import apps
    model_name, owner, route = {
        'eleve': ('NotificationEleve', 'eleve', 'eleve:notifications_eleve'),
        'parent': ('NotificationParent', 'parent', 'school_admin:notifications_parent'),
        'professeur': ('NotificationEnseignant', 'enseignant', 'enseignant:notifications_enseignant'),
        'etablissement': ('NotificationDirecteur', 'etablissement', 'directeur:notifications_directeur'),
    }[role]
    year = year_for(getattr(user, 'etablissement', None) if role != 'etablissement' else user)
    qs = apps.get_model('school_admin', model_name).objects.filter(**{owner: user}, lu=False,
            date_creation__gte=timezone.now() - timedelta(days=7)).exclude(statut='archive')
    if role == 'parent':
        qs = qs.filter(eleve_id__in=[child.pk for child in children])
    elif year:
        qs = qs.filter(Q(annee_scolaire=year) | Q(annee_scolaire__isnull=True))
    result = []
    for notification in qs.order_by('-date_creation')[:20]:
        if notification.type_notification in ('scolarite', 'evaluation', 'presence'):
            continue  # Situations datées/financières recalculées, pas recyclées depuis une ancienne alerte.
        if (notification.donnees or {}).get('rappel'):
            continue  # Rappel déjà porté par sa situation métier.
        source = notification.source_object
        if notification.source_object_id and source is None:
            continue
        if source is not None and (getattr(source, 'actif', True) is False or
                (hasattr(source, 'statut') and source._meta.model_name == 'annonce' and source.statut != 'publiee')):
            continue
        if role == 'parent' and notification.annee_scolaire_id:
            if notification.annee_scolaire_id != getattr(year_for(notification.eleve.etablissement), 'pk', None):
                continue
        context = f'{notification.eleve.prenom}' if role == 'parent' else 'Votre espace'
        if notification.type_notification == 'information' and any(word in notification.titre.lower() for word in ('frais', 'devoir', 'évaluation')):
            continue  # Les situations correspondantes sont résolues directement depuis le métier.
        key = f'notification:{role}:{notification.pk}'
        if (notification.type_notification == 'bulletin' and role in ('eleve', 'parent')
                and notification.date_creation <= timezone.now() - timedelta(days=2)):
            target = url('school_admin:dashboard_enfant', notification.eleve_id) if role == 'parent' else url('eleve:bulletin_eleve')
            result.append(card(key, 'Un bulletin à consulter', notification.message[:280], target,
                'Voir le bulletin', [notification.pk, 'bulletin-rappel'], 68, context, 'work',
                code='PAR-06' if role == 'parent' else 'ELV-05', icon='evaluation', family='notes', once=True,
                eleve_id=notification.eleve_id if role == 'parent' else None))
            continue
        result.append(card(key, notification.titre, notification.message[:280], url(route), 'Consulter',
            [notification.titre, notification.message, notification.donnees],
            70 if notification.type_notification in ('sanction', 'justification_note', 'releve') else 35,
            context, 'info', code='NOTIF', icon='cloche', family='nouveautes', group='news',
            eleve_id=notification.eleve_id if role == 'parent' else None))
    return result


def staff_situations(user, etab, director):
    from school_admin.utils.decorators_permissions import check_permission
    from school_admin.model.preinscription_model import PreinscriptionEleve
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent
    from school_admin.model.comptabilite_eleve_model import FraisInscription, FraisAnnexe, Mensualite
    year = year_for(etab)
    if not year:
        return []
    result = []
    ctx = f'{etab.nom} · {year.libelle}'
    if director or check_permission(user, 'eleves_inscrire'):
        rows = list(PreinscriptionEleve.objects.filter(etablissement=etab, statut='en_attente').values_list('pk', flat=True))
        if rows:
            item = card(f'etab:{etab.pk}:preinscriptions', 'Des préinscriptions à examiner', f'{len(rows)} demande(s) attendent une décision.',
                url('directeur:liste_preinscriptions'), 'Examiner les demandes', sorted(rows), 85, ctx, 'work',
                code='DIR-01' if director else 'ADM-01', icon='dossier', family='inscriptions', count=len(rows))
            if item:
                item['evidence'] = {str(pk): 'pending' for pk in rows}
            result.append(item)
        rows = list(DemandeLiaisonParent.objects.filter(parent_demandeur__etablissement=etab, annee_scolaire=year, statut='en_attente').values_list('pk', flat=True))
        if rows:
            item = card(f'etab:{etab.pk}:year:{year.pk}:liaisons', 'Des accès parent à vérifier', f'{len(rows)} demande(s) de liaison attendent une validation.',
                url('directeur:demandes_liaison_liste'), 'Vérifier les demandes', sorted(rows), 80, ctx, 'work',
                code='DIR-02' if director else 'ADM-01', icon='famille', family='inscriptions', count=len(rows))
            if item:
                item['evidence'] = {str(pk): 'pending' for pk in rows}
            result.append(item)
    if etab.module_comptabilite and (director or check_permission(user, 'comptabilite_voir')):
        late = []
        for model in (FraisInscription, FraisAnnexe, Mensualite):
            qs = model.objects.filter(etablissement=etab, annee_scolaire=year, date_echeance__lt=timezone.localdate(), montant__gt=F('montant_paye')).exclude(statut='clos')
            late.extend((model.__name__, *row) for row in qs.values_list('pk', 'eleve_id', 'montant', 'montant_paye'))
        if late:
            item = card(f'etab:{etab.pk}:year:{year.pk}:late-fees', 'Des dossiers de scolarité à suivre',
                f'{len({row[2] for row in late})} élève(s) ont une échéance dépassée avec un reste à payer.',
                url('directeur:liste_impayes_directeur'), 'Voir les dossiers', sorted(late), 65, ctx, 'finance',
                code='DIR-07' if director else 'ADM-04', icon='scolarite', family='scolarite',
                count=len({row[2] for row in late}))
            if item:
                item['evidence'] = {f'{row[0]}:{row[1]}': digest(row[2:]) for row in late}
            result.append(item)
    if not director and check_permission(user, 'eleves_liste'):
        from school_admin.model.inscription_eleve_model import InscriptionEleve
        rows = list(InscriptionEleve.objects.filter(etablissement=etab, annee_scolaire=year,
            date_creation__gte=timezone.now() - timedelta(days=7)).values_list('pk', flat=True))
        if rows:
            item = card(f'etab:{etab.pk}:year:{year.pk}:new-enrolments', 'Des inscriptions récentes',
                f'{len(rows)} inscription(s) ont été enregistrées ces sept derniers jours.',
                url('secretaire:liste_eleves'), 'Consulter les dossiers', sorted(rows), 40, ctx, 'work',
                code='ADM-00', icon='dossier', family='inscriptions', group='news', count=len(rows))
            if item:
                item['evidence'] = {str(pk): 'created' for pk in rows}
            result.append(item)
    try:
        from school_admin.services.rappels.etablissement import situations
        result.extend(situations(user, etab, year, director))
    except Exception:  # une source indisponible ne doit pas masquer les autres rappels
        import logging
        logging.getLogger(__name__).exception('Rappels établissement indisponibles (%s)', etab.pk)
    return result


def teacher_situations(user):
    from school_admin.model.evaluation_model import Evaluation
    from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
    today = timezone.localdate()
    year = year_for(user.etablissement)
    if not year:
        return []
    result = []
    for model, namespace in ((Evaluation, 'enseignant'), (EvaluationPrimaire, 'enseignant_primaire')):
        for evaluation in model.objects.filter(professeur=user, classe__etablissement=user.etablissement,
                annee_scolaire=year, actif=True, date_evaluation__gte=today,
                date_evaluation__lte=today + timedelta(days=2)).select_related('classe').order_by('date_evaluation')[:3]:
            result.append(card(f'teacher:{user.pk}:year:{year.pk}:evaluation:{model.__name__}:{evaluation.pk}',
                'Une évaluation à préparer', f'{evaluation.titre} — le {evaluation.date_evaluation:%d/%m}.',
                url(f'{namespace}:liste_evaluations'), 'Ouvrir les évaluations',
                [evaluation.titre, evaluation.date_evaluation, evaluation.classe_id], 55,
                f'{evaluation.classe.nom} · {year.libelle}', 'work', evaluation.date_evaluation,
                code='PROF-06', icon='evaluation', family='evaluations'))
    try:
        from school_admin.services.rappels.professeur import situations
        result.extend(situations(user, year))
    except Exception:  # une source indisponible ne doit pas masquer les autres rappels
        import logging
        logging.getLogger(__name__).exception('Rappels professeur indisponibles (%s)', user.pk)
    return result


def _tag(items, etab_id):
    for item in items:
        if item:
            item['etab'] = etab_id
    return items


def candidates(user):
    if getattr(user, 'actif', True) is False:
        return []
    role = user._meta.model_name
    result = []
    if role == 'parent':
        from school_admin.model.lien_familial_model import LienFamilial
        children = list({link.eleve_id: link.eleve for link in LienFamilial.objects.filter(parent=user, actif=True,
            statut='valide', eleve__actif=True).select_related('eleve__etablissement')}.values())
        for child in children:
            result.extend(_tag(student_situations(child, parent=True), child.etablissement_id))
        result.extend(recent_notifications(user, role, children))
        try:
            from school_admin.services.rappels.famille import parent_situations
            result.extend(parent_situations(user))
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Rappels parent indisponibles (%s)', user.pk)
    elif role == 'eleve':
        result.extend(_tag(student_situations(user), user.etablissement_id))
        result.extend(recent_notifications(user, role))
    elif role == 'professeur':
        result.extend(_tag(teacher_situations(user), user.etablissement_id))
        result.extend(recent_notifications(user, role))
    elif role == 'etablissement':
        result.extend(_tag(staff_situations(user, user, True), user.pk))
        result.extend(recent_notifications(user, role))
    elif role == 'personneladministratif' and user.etablissement:
        result.extend(_tag(staff_situations(user, user.etablissement, False), user.etablissement_id))
    return sorted({item['key']: item for item in result if item}.values(), key=lambda item: (-item['priority'], item['key']))


def greeting(user):
    """Salutation de la synthèse : prénom et rôle, selon le moment de la journée."""
    role = user._meta.model_name
    name = getattr(user, 'directeur_prenom', '') if role == 'etablissement' else getattr(user, 'prenom', '')
    hour = timezone.localtime().hour
    return {'hello': 'Bonsoir' if hour >= 18 or hour < 4 else 'Bonjour', 'name': (name or '').strip().split(' ')[0],
            'role': role}


def progress(user):
    """Avancement des tâches du jour (professeur) : {'done', 'total', 'label'} ou None."""
    if user._meta.model_name != 'professeur':
        return None
    try:
        from school_admin.services.rappels.professeur import progression
        return progression(user)
    except Exception:
        return None


def snoozed_keys(user, items):
    """Situations reportées (« Plus tard ») et pas encore revenues."""
    return set(ContextPopupState.objects.filter(
        content_type=ContentType.objects.get_for_model(user), object_id=user.pk,
        key__in=[item['key'] for item in items], snooze_until__gt=timezone.now()).values_list('key', flat=True))


def eligible(user, repeat=False, items=None):
    content_type = ContentType.objects.get_for_model(user)
    items = candidates(user) if items is None else items
    states = {state.key: state for state in ContextPopupState.objects.filter(content_type=content_type, object_id=user.pk, key__in=[item['key'] for item in items])}
    now = timezone.now()
    result = []
    for item in items:
        state = states.get(item['key'])
        if state and state.snooze_until and state.snooze_until > now:
            continue
        if not repeat and state and state.seen_version == item['version']:
            continue
        if not repeat and state and item.get('evidence') and all(state.evidence.get(key) == value for key, value in item['evidence'].items()):
            continue
        result.append(item)
    return result
