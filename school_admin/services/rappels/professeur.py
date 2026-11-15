"""Rappels du professeur (PROF-xx), primaire comme secondaire et supérieur.

Chaque règle part d'une donnée vérifiable (emploi du temps publié, appel soumis, cahier de texte,
notes saisies, relevés) et disparaît d'elle-même dès que l'action est faite.
"""
from datetime import datetime, timedelta

from django.db.models import Count
from django.utils import timezone

from school_admin.services.context_popups import card, url

HEURE_COURS_DEMAIN = 17   # la synthèse « mes cours de demain » n'existe qu'à partir de cette heure
DELAI_APPEL_MIN = 30      # un appel est attendu 30 minutes après la fin du cours


def est_primaire(professeur):
    return professeur.niveau_enseignement in ('maternelle', 'primaire')


def _add(result, item, evidence=None):
    if item:
        if evidence is not None:
            item['evidence'] = evidence
        result.append(item)


def _noms(classes, limite=3):
    noms = sorted({classe.nom for classe in classes})
    return ', '.join(noms[:limite]) + (f' et {len(noms) - limite} autre(s)' if len(noms) > limite else '')


def _cours_termines(professeur, year, du, au, maintenant):
    """Cours de l'emploi du temps publié déjà terminés (avec leur entrée de cahier éventuelle)."""
    from school_admin.services.cahier_texte import cours_du_professeur
    today = timezone.localdate(maintenant)
    limite = (timezone.localtime(maintenant) - timedelta(minutes=DELAI_APPEL_MIN)).time()
    cours = []
    for c in cours_du_professeur(professeur, du, au, year):
        fin = c['fin'] or c['debut']
        if c['date'] < today or (c['date'] == today and fin <= limite):
            cours.append(c)
    return cours


def _appels_du_jour(professeur, year, maintenant):
    """(classes sans appel, classes dont le cours est terminé) pour aujourd'hui."""
    from school_admin.model.presence_model import SoumissionListePresence
    today = timezone.localdate(maintenant)
    classes = {c['classe'].pk: c['classe'] for c in _cours_termines(professeur, year, today, today, maintenant)}
    if not classes:
        return [], []
    faits = set(SoumissionListePresence.objects.filter(
        professeur=professeur, date=today, classe_id__in=list(classes)).values_list('classe_id', flat=True))
    return [classe for pk, classe in classes.items() if pk not in faits], list(classes.values())


def _utilise_appel(professeur, year):
    from school_admin.model.presence_model import SoumissionListePresence
    return SoumissionListePresence.objects.filter(professeur=professeur, annee_scolaire=year).exists()


def _utilise_cahier(professeur):
    from school_admin.model.cahier_texte_model import CahierTexte
    return CahierTexte.objects.filter(etablissement=professeur.etablissement).exists()


def progression(professeur, maintenant=None):
    """Tâches du jour déjà faites : {'done', 'total', 'label'} ou None s'il n'y a rien à suivre."""
    from school_admin.services.context_popups import year_for
    maintenant = maintenant or timezone.now()
    year = year_for(professeur.etablissement)
    if not year:
        return None
    today = timezone.localdate(maintenant)
    done = total = 0
    morceaux = []
    if _utilise_appel(professeur, year):
        manquants, classes = _appels_du_jour(professeur, year, maintenant)
        if classes:
            total += len(classes)
            done += len(classes) - len(manquants)
            morceaux.append(f'{len(classes) - len(manquants)}/{len(classes)} appel(s)')
    if _utilise_cahier(professeur):
        cours = _cours_termines(professeur, year, today, today, maintenant)
        if cours:
            faits = sum(1 for c in cours if c['entree'])
            total += len(cours)
            done += faits
            morceaux.append(f'{faits}/{len(cours)} cahier(s) de texte')
    if not total:
        return None
    return {'done': done, 'total': total, 'label': 'Aujourd’hui : ' + ' · '.join(morceaux)}


def situations(professeur, year, maintenant=None):
    from school_admin.services.dashboard.teacher import _affectations, _effectifs

    maintenant = maintenant or timezone.now()
    today = timezone.localdate(maintenant)
    etab = professeur.etablissement
    primaire = est_primaire(professeur)
    ns = 'enseignant_primaire' if primaire else 'enseignant'
    base = f'teacher:{professeur.pk}:year:{year.pk}'
    ctx = year.libelle
    result = []

    # --- PROF-01 : appel non fait pour un cours terminé aujourd'hui --------------------------
    if _utilise_appel(professeur, year):
        manquants, _classes = _appels_du_jour(professeur, year, maintenant)
        if manquants:
            cible = url(f'{ns}:liste_presence', manquants[0].pk) if len(manquants) == 1 else url(f'{ns}:gestion_presence')
            _add(result, card(f'{base}:appel:{today.isoformat()}', 'Un appel à faire',
                              f'L’appel n’est pas enregistré pour {_noms(manquants)}.', cible, 'Faire l’appel',
                              sorted(c.pk for c in manquants), 92, ctx, 'important', today, code='PROF-01',
                              icon='appel', family='presences', count=len(manquants)))

    # --- PROF-02 / PROF-03 : cahier de texte -------------------------------------------------
    if _utilise_cahier(professeur):
        from school_admin.model.cahier_texte_model import CahierTexte
        cours = _cours_termines(professeur, year, today - timedelta(days=7), today, maintenant)
        sans = [c for c in cours if not c['entree']]
        if sans:
            jours = sorted({c['date'] for c in sans})
            _add(result, card(f'{base}:cahier', 'Le cahier de texte à compléter',
                              f'{len(sans)} cours des 7 derniers jours n’ont pas de séance renseignée '
                              f'({_noms([c["classe"] for c in sans])}).',
                              url(f'{ns}:cahier_texte'), 'Remplir le cahier', [len(sans), jours], 66, ctx, 'work',
                              code='PROF-02', icon='cahier', family='cahier', count=len(sans)),
                 {jour.isoformat(): 'missing' for jour in jours})
        brouillons = CahierTexte.objects.filter(professeur=professeur, annee_scolaire=year,
                                                statut='brouillon').count()
        if brouillons:
            _add(result, card(f'{base}:cahier-brouillons', 'Des séances à valider',
                              f'{brouillons} séance(s) du cahier de texte sont encore en brouillon : les élèves '
                              'et les familles ne les voient pas.',
                              url(f'{ns}:cahier_texte'), 'Valider les séances', ['brouillons'], 52, ctx, 'work',
                              code='PROF-03', icon='cahier', family='cahier', count=brouillons))

    # --- PROF-04 : notes à saisir ------------------------------------------------------------
    affectations = list(_affectations(professeur, year, primaire))
    classes = {aff.classe_id: aff.classe for aff in affectations}
    if classes:
        if primaire:
            from school_admin.model.evaluation_primaire_model import EvaluationPrimaire as EvalModel
            from school_admin.model.note_primaire_model import NotePrimaire as NoteModel
            fk = 'evaluation_primaire'
        else:
            from school_admin.model.evaluation_model import Evaluation as EvalModel, Note as NoteModel
            fk = 'evaluation'
        evals = list(EvalModel.objects.filter(
            professeur=professeur, actif=True, annee_scolaire=year, classe_id__in=list(classes),
            date_evaluation__lte=today - timedelta(days=3), date_evaluation__gte=today - timedelta(days=45),
        ).select_related('classe').order_by('date_evaluation'))
        if evals:
            effectifs = _effectifs(list(classes.values()), etab, year)
            saisies = dict(NoteModel.objects.filter(**{f'{fk}_id__in': [e.pk for e in evals]})
                           .values(f'{fk}_id').annotate(n=Count('id')).values_list(f'{fk}_id', 'n'))
            incompletes = [e for e in evals
                           if effectifs.get(e.classe_id) and saisies.get(e.pk, 0) < len(effectifs[e.classe_id])]
            if incompletes:
                premiere = incompletes[0]
                texte = (f'« {premiere.titre} » ({premiere.classe.nom}, {premiere.date_evaluation:%d/%m}) attend '
                         'ses notes.' if len(incompletes) == 1 else
                         f'{len(incompletes)} évaluations passées n’ont pas toutes leurs notes, dont '
                         f'« {premiere.titre} » ({premiere.classe.nom}).')
                _add(result, card(f'{base}:notes', 'Des notes à saisir', texte,
                                  url(f'{ns}:noter_eleves', premiere.classe_id), 'Saisir les notes',
                                  sorted(e.pk for e in incompletes), 74, ctx, 'work', code='PROF-04',
                                  icon='notes', family='notes', count=len(incompletes)),
                     {f'{EvalModel.__name__}:{e.pk}': 'incomplete' for e in incompletes})

    # --- PROF-05 : relevé à soumettre avant la fin de période --------------------------------
    from school_admin.model.releve_notes_model import ReleveNotes
    releves = list(ReleveNotes.objects.filter(
        professeur=professeur, annee_scolaire=year, soumis=False, actif=True,
        periode_scolaire__date_fin__gte=today - timedelta(days=14),
        periode_scolaire__date_fin__lte=today + timedelta(days=7),
    ).select_related('periode_scolaire', 'classe').order_by('periode_scolaire__date_fin'))
    if releves:
        fin = releves[0].periode_scolaire.date_fin
        _add(result, card(f'{base}:releves:{releves[0].periode_scolaire_id}', 'Un relevé de notes à soumettre',
                          f'{len(releves)} relevé(s) restent à soumettre à la direction pour '
                          f'« {releves[0].periode_scolaire.nom_periode} » (fin le {fin:%d/%m}) : '
                          f'{_noms([r.classe for r in releves])}.',
                          url(f'{ns}:gestion_notes'), 'Soumettre le relevé', [fin, sorted(r.pk for r in releves)],
                          80, ctx, 'work', fin, code='PROF-05', icon='notes', family='notes', count=len(releves)))

    # --- PROF-07 : devoirs à ramasser aujourd'hui --------------------------------------------
    from school_admin.model.exercice_maison_model import ExerciceMaison
    devoirs = list(ExerciceMaison.objects.filter(professeur=professeur, annee_scolaire=year, actif=True,
                                                 date_rendu=today).select_related('classe'))
    if devoirs:
        _add(result, card(f'{base}:devoirs:{today.isoformat()}', 'Des devoirs à ramasser aujourd’hui',
                          f'{len(devoirs)} devoir(s) sont à rendre ce jour : {_noms([d.classe for d in devoirs])}.',
                          url(f'{ns}:exercices_maison'), 'Voir les devoirs', sorted(d.pk for d in devoirs), 58,
                          ctx, 'work', today, code='PROF-07', icon='devoir', family='devoirs', count=len(devoirs)))

    # --- PROF-08 : notes d'examen saisies mais non soumises ----------------------------------
    if not primaire:
        from school_admin.model.note_examen_model import NoteExamen
        rows = list(NoteExamen.objects.filter(
            professeur=professeur, annee_scolaire=year, soumis=False,
            session_examen__actif=True, session_examen__est_annule=False,
            session_examen__date_fin__lt=today - timedelta(days=2),
            session_examen__date_fin__gte=today - timedelta(days=45),
        ).values_list('session_examen_id', 'classe_id').distinct())
        if rows:
            _add(result, card(f'{base}:examens', 'Des notes d’examen à soumettre',
                              f'Des notes d’examen sont saisies mais pas encore soumises pour {len(rows)} classe(s).',
                              url(f'{ns}:noter_examen', rows[0][1]), 'Soumettre les notes', sorted(rows), 76, ctx,
                              'work', code='PROF-08', icon='evaluation', family='notes', count=len(rows)),
                 {f'{session}:{classe}': 'unsubmitted' for session, classe in rows})

    # --- PROF-11 : pointage des cours du jour ------------------------------------------------
    from school_admin.services.pointage import date_activation
    activation = date_activation(etab)
    if activation and activation <= today:
        from school_admin.model.pointage_model import SeanceCours
        heure = timezone.localtime(maintenant).time()
        a_terminer = list(SeanceCours.objects.filter(professeur=professeur, date=today, statut='en_cours',
                                                     heure_fin__lt=heure).select_related('classe'))
        if a_terminer:
            _add(result, card(f'{base}:pointage:{today.isoformat()}', 'Un cours à terminer',
                              f'Le cours de {_noms([s.classe for s in a_terminer])} est toujours ouvert : terminez-le '
                              'pour qu’il soit compté.',
                              url(f'{ns}:pointage'), 'Terminer le cours', sorted(s.pk for s in a_terminer), 88, ctx,
                              'important', today, code='PROF-11', icon='planning', family='planning',
                              count=len(a_terminer)))

    # --- PROF-10 : mes cours de demain (option de l'établissement, à partir de 17 h) ---------
    from school_admin.services.rappels.moteur import parametres
    params = parametres(etab.pk)
    if params and params.rappel_cours_demain and timezone.localtime(maintenant).hour >= HEURE_COURS_DEMAIN:
        from school_admin.services.cahier_texte import cours_du_professeur
        demain = today + timedelta(days=1)
        cours = sorted(cours_du_professeur(professeur, demain, demain, year), key=lambda c: c['debut'])
        if cours:
            premier = cours[0]
            _add(result, card(f'{base}:demain:{demain.isoformat()}', 'Vos cours de demain',
                              f'{len(cours)} cours, à partir de {premier["debut"]:%H:%M} avec {premier["classe"].nom}.',
                              url(f'{ns}:emploi_du_temps'), 'Voir mon planning',
                              [(c['classe'].pk, c['debut']) for c in cours], 30, ctx, 'info', demain,
                              code='PROF-10', icon='planning', family='planning', count=len(cours)))
    return result
