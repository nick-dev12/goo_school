"""Guide de consultation des examens : aucun calcul ni écriture en GET."""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_safe

from ..model.annee_scolaire_model import AnneeScolaire
from ..model.affectation_model import AffectationProfesseur
from ..model.classe_model import Classe
from ..model.creneau_examen_model import CreneauExamen
from ..model.deliberation_model import DecisionJury, Deliberation
from ..model.matiere_model import Matiere
from django.db.models import Q

from ..model.module_model import ModuleClasse
from ..model.note_examen_model import NoteExamen
from ..model.periode_model import PeriodeScolaire, semestres_choices_pour_niveau
from ..model.session_examen_model import SessionExamen
from ..services import deliberations
from ..services.deliberations import controle_resultats
from ..services.diplomes import diplome_de
from ..services.maquette import maquette_classe, module_ids_exclus
from ..utils.decorators_permissions import _get_user_etablissement, require_permission


def _controle(classe, periodes, annee):
    try:
        return controle_resultats(classe, periodes, annee)
    except deliberations.DeliberationErreur as exc:
        return {'pret': False, 'problemes': [str(exc)],
                'etudiants': 0, 'manquants': 0, 'perimes': 0}


def construire_etapes(classe, periodes, annee, portee, session):
    """Observe les enregistrements du contexte, sans préparer de décisions."""
    controle = _controle(classe, periodes, annee)
    problemes = list(controle.get('problemes', []))
    annuel_complet = True
    if portee == 'annuelle':
        attendus_semestres = {nom for nom, _ in semestres_choices_pour_niveau(classe.niveau_lmd)}
        configures = {p.nom_periode for p in periodes}
        absents = attendus_semestres - configures
        annuel_complet = bool(attendus_semestres) and not absents
        if not annuel_complet:
            problemes.append('Année incomplète : semestres à configurer : ' +
                             (', '.join(sorted(absents)) if absents else 'niveau LMD à préciser') + '.')
            controle = {**controle, 'pret': False, 'problemes': problemes}
    programme = list(ModuleClasse.objects.filter(
        classe=classe, periode__in=periodes, module__etablissement=classe.etablissement,
        module__actif=True).select_related('module', 'periode'))
    ecs = list(Matiere.objects.filter(module_id__in=[m.module_id for m in programme],
                                      etablissement=classe.etablissement, actif=True
                                      ).filter(Q(classes=classe) | Q(classes__isnull=True)).distinct())
    par_module = {mc.module_id: {m.id for m in ecs if m.module_id == mc.module_id}
                  for mc in programme}
    programme_ok = annuel_complet and bool(periodes) and all(
        any(mc.periode_id == p.id for mc in programme) for p in periodes)
    programme_ok = programme_ok and bool(programme) and all(
        mc.credits > 0 and par_module[mc.module_id] for mc in programme)
    sessions_qs = SessionExamen.objects.filter(
        etablissement=classe.etablissement, classes=classe, periode__in=periodes,
        annee_scolaire=annee, actif=True, est_annule=False, compte_bulletin=True)
    if session == Deliberation.SESSION_RATTRAPAGE:
        sessions_qs = sessions_qs.filter(type_session=SessionExamen.TYPE_RATTRAPAGE)
    else:
        sessions_qs = sessions_qs.exclude(type_session=SessionExamen.TYPE_RATTRAPAGE)
    sessions = list(sessions_qs.prefetch_related('matieres').distinct())
    attendus = {(mc.periode_id, mid) for mc in programme for mid in par_module[mc.module_id]}
    couverts = set()
    planning_ok = programme_ok and bool(sessions)
    for s in sessions:
        matieres = {matiere.id for matiere in s.matieres.all()}
        prevues = {mid for pid, mid in attendus if pid == s.periode_id}
        planifiees = set(CreneauExamen.objects.filter(session_examen=s).values_list('matiere_id', flat=True))
        planning_ok = planning_ok and bool(matieres) and matieres <= prevues and matieres <= planifiees and s.est_publie
        couverts.update((s.periode_id, mid) for mid in matieres)
    planning_ok = planning_ok and attendus <= couverts

    etudiants = deliberations.etudiants(classe, annee)
    exclusions = {eleve.id: module_ids_exclus(eleve, classe, annee) for eleve in etudiants}
    credits_attendus = []
    for eleve in etudiants:
        exclus = exclusions[eleve.id]
        credits_attendus.append({'eleve': eleve, 'credits': sum(
            mc.credits for mc in programme if mc.module_id not in exclus)})
    enseignants = {}
    for affectation in AffectationProfesseur.objects.filter(
            classe=classe, annee_scolaire=annee, actif=True,
            professeur__etablissement=classe.etablissement).select_related('professeur'):
        enseignants.setdefault(affectation.matiere_id, []).append(str(affectation.professeur))
    notes = {(n.session_examen_id, n.eleve_id, n.matiere_id): n for n in NoteExamen.objects.filter(
        classe=classe, annee_scolaire=annee, session_examen__in=sessions,
        eleve_id__in=[e.id for e in etudiants]).select_related('professeur')}
    manquants, nb_attendus, nb_saisis, nb_soumis, nb_absents = [], 0, 0, 0, 0
    for eleve in etudiants:
        exclus = exclusions[eleve.id]
        suivies = {m.id for m in ecs if m.module_id not in exclus}
        for s in sessions:
            for m in s.matieres.all():
                if m.id not in suivies:
                    continue
                nb_attendus += 1
                n = notes.get((s.id, eleve.id, m.id))
                saisie = n is not None and (n.note is not None or n.absent)
                nb_saisis += int(saisie)
                nb_soumis += int(saisie and n.soumis)
                nb_absents += int(n is not None and n.absent)
                if not saisie or not n.soumis:
                    manquants.append({'eleve': eleve, 'matiere': m, 'session': s,
                                      'enseignant': str(n.professeur) if n else ', '.join(enseignants.get(m.id, [])),
                                      'motif': 'À soumettre' if saisie else 'À saisir'})
    notes_ok = planning_ok and nb_attendus > 0 and not manquants
    resultats_ok = programme_ok and controle.get('pret') is True
    perimes = bool(controle.get('perimes'))
    ds = list(Deliberation.objects.filter(
        etablissement=classe.etablissement, classe=classe, annee_scolaire=annee,
        periode=None if portee == 'annuelle' else periodes[0], session=session)) if periodes else []
    d = ds[0] if ds else None
    jury_ok = bool(d and d.president.strip() and d.date_deliberation)
    if d:
        decisions = list(d.decisions.all())
        jury_ok = jury_ok and {x.eleve_id for x in decisions} == {e.id for e in etudiants} and bool(etudiants)
        jury_ok = jury_ok and all(not x.points_jury or x.motif_jury.strip() for x in decisions)
        jury_ok = jury_ok and all(x.decision != DecisionJury.INCOMPLET and x.credits_total > 0
                                 for x in decisions)
    if d and d.est_cloturee and controle.get('perimes'):
        # Clôturée : notes verrouillées, le recalcul est refusé tant qu'on ne rouvre pas.
        anciennes = controle.get('anciennes', 0)
        if (anciennes == controle['perimes'] and not controle.get('manquants')
                and len(controle.get('problemes', [])) == 1):
            # Seules des moyennes antérieures à la migration 0256 (sans empreinte) : décisions
            # figées avant le contrôle, ne pas réclamer un recalcul impossible.
            resultats_ok, perimes = programme_ok, False
            problemes = ['Délibération clôturée avant la mise à jour du contrôle des résultats : '
                         'les décisions restent valables et figées.']
            controle = {**controle, 'pret': True, 'problemes': problemes, 'perimes': 0}
        else:
            problemes = problemes + ['Des données ont changé après la clôture : rouvrez la délibération, '
                                     'recalculez les moyennes dans Bulletins, puis clôturez de nouveau.']
    final_ok = resultats_ok and jury_ok and bool(d and d.est_cloturee)
    query = urlencode({'classe_id': classe.id, 'annee_id': annee.id,
                       'periode_id': periodes[0].id if portee != 'annuelle' and periodes else '',
                       'portee': portee, 'session': session})

    def lien(nom, args=None):
        if not annee.est_active and nom not in ('detail_deliberation','pv_deliberation'):
            return '#ep-historique'
        return reverse('directeur:' + nom, args=args) + '?' + query

    jury_url = lien('detail_deliberation', [d.id]) if d else lien('liste_deliberations')
    controles_programme = [
        {'semestre': bilan['periode'].nom_periode, 'points': bilan['controles']}
        for bilan in maquette_classe(classe, periodes) if bilan['controles']
    ]
    url_modules = (reverse('matiere:liste_matieres') + '?tab=modules') if annee.est_active else '#ep-historique'
    etapes = [
        ('Préparer le programme', programme_ok, 'Prêt',
         f'{len(programme)} blocs de matières (UE), {len(ecs)} matières/cours (EC). Vérifiez les crédits, les matières et les réglages de chaque UE.',
         'Ouvrir les modules et UE', url_modules),
        ('Organiser les examens', planning_ok, 'Terminé',
         f'{len(sessions)} sessions : vérifier la couverture des matières, les épreuves planifiées et la publication du calendrier.',
         'Voir les sessions et le calendrier', lien('gestion_examens')),
        ('Vérifier les notes', notes_ok, 'Prêt',
         f'{nb_saisis}/{nb_attendus} notes ou absences saisies ; {nb_soumis} soumises ; {nb_absents} absences. Les lignes vides ne comptent pas comme notes.',
         'Voir les saisies manquantes', '#saisies'),
        ('Préparer les résultats', resultats_ok, 'Prêt',
         'Complétude et fraîcheur vérifiées par le contrôle des résultats.' if resultats_ok else 'Résultats incomplets, non calculés ou non vérifiés. Consultez les problèmes ci-dessous.',
         'Préparer les moyennes dans Bulletins', lien('bulletins_notes')),
        ('Préparer le jury', resultats_ok and jury_ok, 'Prêt',
         'Vérifier président, membres, date, décisions provisoires et motifs des points de jury.',
         'Examiner le jury', jury_url),
        ('Valider les documents', final_ok, 'Terminé',
         'PV définitif et décisions publiées après clôture ; avant clôture, le PV reste provisoire.',
         'Imprimer le PV définitif' if final_ok else 'Vérifier avant clôture et publication',
         lien('pv_deliberation', [d.id]) if final_ok else jury_url),
    ]
    return {'etapes': [{'titre': t, 'etat': ok_label if ok else ('À recalculer' if perimes and i >= 3 else 'À compléter'),
                        'pret': bool(ok), 'explication': exp, 'action': action, 'url': url}
                       for i, (t, ok, ok_label, exp, action, url) in enumerate(etapes)],
            'controle': controle, 'problemes': problemes, 'controles_programme': controles_programme, 'saisies_manquantes': manquants,
            'credits_attendus': credits_attendus,
            'documents_prets': final_ok and portee == 'annuelle' and bool(diplome_de(classe)),
            'attestations_url': lien('diplomes_classe', [classe.id])}


@login_required
@require_permission('examens_voir')
@require_safe
def parcours_examens(request):
    etablissement = _get_user_etablissement(request, 'examens_voir')[0]
    if etablissement is None or etablissement.type_etablissement != 'superieur':
        return HttpResponseForbidden('Ce guide concerne les examens du supérieur.')
    for cle in ('annee_id', 'classe_id', 'periode_id'):
        valeur = request.GET.get(cle)
        if valeur and (not valeur.isascii() or not valeur.isdigit() or len(valeur) > 18):
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest('Identifiant de contexte invalide.')
    annees = AnneeScolaire.objects.filter(etablissement=etablissement).order_by('-date_debut')
    annee_id = request.GET.get('annee_id')
    annee = get_object_or_404(annees, pk=annee_id) if annee_id else annees.filter(est_active=True).first()
    classes = Classe.objects.filter(etablissement=etablissement, actif=True, niveau='superieur').select_related('department').order_by('nom')
    classe_id = request.GET.get('classe_id')
    classe = get_object_or_404(classes, pk=classe_id) if classe_id else None
    portee = request.GET.get('portee', 'semestre')
    session = request.GET.get('session', Deliberation.SESSION_NORMALE)
    if portee not in ('semestre', 'annuelle') or session not in dict(Deliberation.SESSION_CHOICES):
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest('Portée ou session invalide.')
    periodes = PeriodeScolaire.objects.filter(etablissement=etablissement, annee_scolaire_fk=annee, type_periode='semestre') if annee else PeriodeScolaire.objects.none()
    if classe:
        periodes = periodes.filter(niveau_lmd=classe.niveau_lmd)
    periodes = periodes.order_by('date_debut')
    periode_id = request.GET.get('periode_id')
    periode = get_object_or_404(periodes, pk=periode_id) if periode_id and portee == 'semestre' else None
    selection = list(periodes) if portee == 'annuelle' else ([periode] if periode else [])
    context = {'etablissement': etablissement, 'annees': annees, 'annee': annee,
               'classes': classes, 'classe': classe, 'periodes': periodes, 'periode': periode,
               'portee': portee, 'session': session, 'sessions': Deliberation.SESSION_CHOICES}
    if classe and annee and (selection or portee == 'annuelle'):
        context.update(construire_etapes(classe, selection, annee, portee, session))
    return render(request, 'school_admin/directeur/examens_parcours.html', context)
