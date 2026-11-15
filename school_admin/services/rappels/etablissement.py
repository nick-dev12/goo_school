"""Rappels de la direction (DIR-xx) et du personnel administratif (ADM-xx).

Chaque règle part d'une donnée métier vérifiable et ne s'affiche qu'avec la permission
qui ouvre la page cible. Les mêmes cartes servent au popup, à la cloche et au push planifié.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from school_admin.services.context_popups import card, digest, url


def _add(result, item, evidence=None):
    if item:
        if evidence is not None:
            item['evidence'] = evidence
        result.append(item)


def _jours_ouvres(today, n=5):
    dates, cursor = [], today
    while len(dates) < n:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    return dates


def situations(user, etab, year, director):
    """Cartes complémentaires de l'établissement pour ce compte (directeur ou personnel)."""
    from school_admin.utils.decorators_permissions import check_permission

    def may(*keys):
        return director or any(check_permission(user, key) for key in keys)

    def code(numero_dir, numero_adm=None):
        return f'DIR-{numero_dir:02d}' if director or numero_adm is None else f'ADM-{numero_adm:02d}'

    today = timezone.localdate()
    ctx = f'{etab.nom} · {year.libelle}'
    base = f'etab:{etab.pk}:year:{year.pk}'
    result = []

    from school_admin.model.periode_model import PeriodeScolaire
    periodes = list(PeriodeScolaire.objects.filter(etablissement=etab, annee_scolaire=year))
    en_cours = [p for p in periodes if p.date_debut <= today <= p.date_fin]

    # --- Notes -----------------------------------------------------------------------------
    if may('notes_justifications_voir'):
        from school_admin.model.justification_note_model import JustificationNote
        rows = list(JustificationNote.objects.filter(
            etablissement=etab, annee_scolaire=year,
            statut=JustificationNote.STATUT_EN_ATTENTE).values_list('pk', flat=True))
        if rows:
            _add(result, card(f'{base}:justifications', 'Des justifications de note à traiter',
                              f'{len(rows)} demande(s) de modification de note attendent votre décision.',
                              url('directeur:justifications_notes'), 'Traiter les demandes', sorted(rows), 82, ctx,
                              'work', code=code(3, 9), icon='notes', family='notes', count=len(rows)),
                 {str(pk): 'pending' for pk in rows})

    if may('notes_liste'):
        from school_admin.model.releve_notes_model import ReleveNotes
        proches = [p for p in periodes if today - timedelta(days=14) <= p.date_fin <= today + timedelta(days=7)]
        if proches:
            periode = min(proches, key=lambda p: p.date_fin)
            rows = list(ReleveNotes.objects.filter(
                etablissement=etab, annee_scolaire=year, periode_scolaire=periode, soumis=False,
                actif=True).values_list('pk', flat=True))
            if rows:
                _add(result, card(f'{base}:releves:{periode.pk}', 'Des relevés de notes non soumis',
                                  f'{len(rows)} relevé(s) ne sont pas encore soumis pour « {periode.nom_periode} » '
                                  f'(fin le {periode.date_fin:%d/%m}).',
                                  url('directeur:notes_et_resultats'), 'Voir les relevés',
                                  [periode.pk, periode.date_fin], 78, ctx, 'work', periode.date_fin,
                                  code=code(4, 9), icon='notes', family='notes', count=len(rows)))

    if may('bulletins_voir'):
        from school_admin.model.moyenne_periode_model import MoyennePeriode
        for periode in periodes:
            if not (today - timedelta(days=45) <= periode.date_fin <= today - timedelta(days=3)):
                continue
            qs = MoyennePeriode.objects.filter(etablissement=etab, annee_scolaire=year, periode=periode,
                                               est_moyenne_generale=True)
            attente = qs.filter(est_publie=False).count()
            if attente:
                _add(result, card(f'{base}:bulletins:{periode.pk}', 'Des bulletins prêts à publier',
                                  f'{attente} bulletin(s) de « {periode.nom_periode} » sont calculés mais pas encore '
                                  'visibles par les familles.',
                                  url('directeur:bulletins_notes'), 'Publier les bulletins', [periode.pk], 74, ctx,
                                  'work', code=code(5, 9), icon='evaluation', family='notes', count=attente))

    # --- Présences -------------------------------------------------------------------------
    if may('presences_liste') and en_cours:
        from school_admin.model.classe_model import Classe
        from school_admin.model.presence_model import SoumissionListePresence
        dates = _jours_ouvres(today)
        classes = set(Classe.objects.filter(etablissement=etab, actif=True).values_list('pk', flat=True))
        couvertes = set(SoumissionListePresence.objects.filter(
            etablissement=etab, annee_scolaire=year, date__gte=min(dates),
            date__lte=today).values_list('classe_id', flat=True))
        manquantes = sorted(classes - couvertes)
        # Une école qui n'utilise pas l'appel numérique n'est pas relancée chaque jour.
        if manquantes and couvertes:
            _add(result, card(f'{base}:appels', 'Des classes sans appel',
                              f'{len(manquantes)} classe(s) n’ont aucun appel sur les 5 derniers jours ouvrés.',
                              url('directeur:suivi_presence'), 'Voir le suivi des présences', manquantes, 62, ctx,
                              'important', code=code(6, 7), icon='appel', family='presences', count=len(manquantes)),
                 {str(pk): 'missing' for pk in manquantes})

    # --- Cahier de texte et pointage ---------------------------------------------------------
    if may('professeurs_detail', 'pointage_controle'):
        from school_admin.model.cahier_texte_model import CahierTexte
        rows = list(CahierTexte.objects.filter(etablissement=etab, annee_scolaire=year,
                                               demande_statut='en_attente').values_list('pk', flat=True))
        if rows:
            _add(result, card(f'{base}:cahier-demandes', 'Des demandes sur le cahier de texte',
                              f'{len(rows)} enseignant(s) demandent à modifier une séance déjà validée.',
                              url('directeur:cahiers_texte'), 'Traiter les demandes', sorted(rows), 60, ctx, 'work',
                              code=code(9, 9), icon='cahier', family='cahier', count=len(rows)),
                 {str(pk): 'pending' for pk in rows})

    if may('pointage_controle'):
        from school_admin.model.pointage_model import SeanceCours
        rows = list(SeanceCours.objects.filter(
            etablissement=etab, annee_scolaire=year, statut__in=('a_verifier', 'contestee'),
            date__gte=today - timedelta(days=45)).values_list('pk', 'statut'))
        if rows:
            contestees = sum(1 for _, statut in rows if statut == 'contestee')
            detail = f' dont {contestees} contestée(s)' if contestees else ''
            _add(result, card(f'{base}:pointage', 'Des séances de cours à contrôler',
                              f'{len(rows)} séance(s) attendent votre décision{detail}.',
                              url('directeur:pointage_controle'), 'Contrôler les séances', sorted(rows), 64, ctx,
                              'work', code=code(10, 10), icon='planning', family='planning', count=len(rows)),
                 {str(pk): statut for pk, statut in rows})

    # --- Vie scolaire ------------------------------------------------------------------------
    if may('sanctions_liste'):
        from school_admin.model.convocation_model import Convocation
        rows = list(Convocation.objects.filter(etablissement=etab, actif=True,
                                               date_convocation=today).values_list('pk', flat=True))
        if rows:
            _add(result, card(f'{base}:convocations:{today.isoformat()}', 'Des convocations aujourd’hui',
                              f'{len(rows)} convocation(s) sont prévues ce jour.',
                              url('directeur:convocation_liste'), 'Voir les convocations', sorted(rows), 70, ctx,
                              'important', today, code=code(11, 8), icon='convocation', family='convocations',
                              count=len(rows)))

    if may('examens_voir'):
        from school_admin.model.session_examen_model import SessionExamen
        for session in SessionExamen.objects.filter(
                etablissement=etab, annee_scolaire=year, actif=True, est_annule=False,
                date_debut__gte=today, date_debut__lte=today + timedelta(days=7)).order_by('date_debut')[:2]:
            etat = '' if session.est_publie else ' Le planning n’est pas encore publié.'
            _add(result, card(f'{base}:examen:{session.pk}', 'Une session d’examen approche',
                              f'« {session.nom_examen} » commence le {session.date_debut:%d/%m}.{etat}',
                              url('directeur:gestion_examens'), 'Vérifier le planning',
                              [session.nom_examen, session.date_debut, session.est_publie], 72, ctx, 'important',
                              session.date_debut, code=code(12), icon='planning', family='planning'))

        from school_admin.model.deliberation_model import Deliberation
        rows = list(Deliberation.objects.filter(
            etablissement=etab, annee_scolaire=year, statut=Deliberation.STATUT_BROUILLON,
            periode__date_fin__lt=today - timedelta(days=7)).values_list('pk', flat=True))
        if rows:
            _add(result, card(f'{base}:deliberations', 'Des délibérations à clôturer',
                              f'{len(rows)} délibération(s) sont restées en cours après la fin de leur période.',
                              url('directeur:liste_deliberations'), 'Ouvrir les délibérations', sorted(rows), 58,
                              ctx, 'work', code=code(13), icon='evaluation', family='notes', count=len(rows)),
                 {str(pk): 'draft' for pk in rows})

    # --- Calendrier (direction) --------------------------------------------------------------
    if director:
        for periode in en_cours:
            if periode.date_fin <= today + timedelta(days=7):
                _add(result, card(f'{base}:fin-periode:{periode.pk}', 'Une période se termine',
                                  f'« {periode.nom_periode} » se termine le {periode.date_fin:%d/%m} : relevés, '
                                  'moyennes et bulletins sont à préparer.',
                                  url('directeur:gestion_periodes_scolaires'), 'Préparer la clôture',
                                  [periode.pk, periode.date_fin], 50, ctx, 'info', periode.date_fin,
                                  code='DIR-14', icon='planning', family='planning'))

        from school_admin.model.facturation_model import Facturation
        limite = timezone.now() + timedelta(days=7)
        facture = Facturation.objects.filter(etablissement=etab, date_echeance__lte=limite).exclude(
            statut__in=('paye', 'annule')).order_by('date_echeance').first()
        if facture and facture.date_echeance:
            echeance = timezone.localtime(facture.date_echeance).date()
            _add(result, card(f'etab:{etab.pk}:facture:{facture.pk}', 'Votre abonnement Aria à régler',
                              f'La facture {facture.numero_facture} arrive à échéance le {echeance:%d/%m}.',
                              url('directeur:facturation_directeur'), 'Voir la facture',
                              [facture.pk, facture.statut, echeance], 68, etab.nom, 'finance', echeance,
                              code='DIR-17', icon='scolarite', family='scolarite'))

    # --- Finances ----------------------------------------------------------------------------
    if etab.module_comptabilite and may('comptabilite_voir'):
        from school_admin.model.recouvrement_model import EcheanceMoratoire, Moratoire
        rows = list(Moratoire.objects.filter(
            etablissement=etab, annee_scolaire=year, statut='rompu',
            date_rupture__gte=timezone.now() - timedelta(days=7)).values_list('pk', flat=True))
        if rows:
            _add(result, card(f'{base}:moratoires-rompus', 'Des moratoires rompus',
                              f'{len(rows)} échéancier(s) accordé(s) à des familles n’ont pas été respectés cette '
                              'semaine.', url('directeur:liste_impayes_directeur'), 'Ouvrir les dossiers',
                              sorted(rows), 76, ctx, 'finance', code=code(8, 5), icon='scolarite',
                              family='scolarite', count=len(rows)),
                 {str(pk): 'broken' for pk in rows})
        rows = list(EcheanceMoratoire.objects.filter(
            moratoire__etablissement=etab, moratoire__annee_scolaire=year, moratoire__statut='actif',
            date_echeance__gte=today, date_echeance__lte=today + timedelta(days=3)).exclude(
            statut='paye').values_list('pk', 'date_echeance'))
        if rows:
            premiere = min(row[1] for row in rows)
            _add(result, card(f'{base}:moratoires-echeances', 'Des échéances de moratoire à encaisser',
                              f'{len(rows)} échéance(s) d’échéancier arrivent d’ici trois jours.',
                              url('directeur:liste_impayes_directeur'), 'Voir les échéances', sorted(rows), 56, ctx,
                              'finance', premiere, code=code(8, 5), icon='scolarite', family='scolarite',
                              count=len(rows)))

    if etab.module_comptabilite and may('comptabilite_bilans'):
        from school_admin.model.caisse_etablissement_model import DepenseEtablissement
        rows = list(DepenseEtablissement.objects.filter(etablissement=etab, annee_scolaire=year,
                                                        statut='brouillon').values_list('pk', flat=True))
        if rows:
            _add(result, card(f'{base}:depenses', 'Des dépenses à valider',
                              f'{len(rows)} dépense(s) sont enregistrées en brouillon.',
                              url('directeur:caisse_mois_directeur'), 'Valider les dépenses', sorted(rows), 48, ctx,
                              'finance', code=code(16, 6), icon='scolarite', family='scolarite', count=len(rows)),
                 {str(pk): 'draft' for pk in rows})

        from school_admin.model.finances_model import EcheancePret
        echeances = EcheancePret.objects.filter(
            etablissement=etab, pret__statut='en_cours', date_echeance__lte=today + timedelta(days=3),
            date_echeance__gte=today - timedelta(days=60)).annotate(
            regle=Count('remboursements', filter=Q(remboursements__statut='validee'))).filter(regle=0)
        rows = list(echeances.order_by('date_echeance').values_list('pk', 'date_echeance')[:20])
        if rows:
            _add(result, card(f'etab:{etab.pk}:prets', 'Une échéance de prêt à régler',
                              f'{len(rows)} échéance(s) de prêt de l’établissement sont à payer.',
                              url('directeur:cg_prets'), 'Voir les prêts', sorted(rows), 66, ctx, 'finance',
                              rows[0][1], code=code(15, 6), icon='scolarite', family='scolarite', count=len(rows)))

    # --- Dossiers élèves (secrétariat) -------------------------------------------------------
    if not director and may('eleves_modifier'):
        from school_admin.model.eleve_model import Eleve
        rows = list(Eleve.objects.filter(etablissement=etab, actif=True,
                                         classe__isnull=True).values_list('pk', flat=True))
        if rows:
            _add(result, card(f'etab:{etab.pk}:sans-classe', 'Des élèves sans classe',
                              f'{len(rows)} élève(s) n’ont pas de classe : ils n’apparaissent dans aucune liste '
                              'd’appel ni aucun bulletin.', url('secretaire:liste_eleves'), 'Compléter les dossiers',
                              sorted(rows), 60, ctx, 'work', code='ADM-02', icon='dossier', family='inscriptions',
                              count=len(rows)),
                 {str(pk): 'no-class' for pk in rows})
    return result
