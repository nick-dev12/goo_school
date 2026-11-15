"""Rappels de l'élève (ELV-xx) et du parent (PAR-xx), en complément de ``student_situations``.

Devoirs, évaluations, convocations et échéances de scolarité sont définis dans
``services/context_popups.py`` ; ce module ajoute les examens, les absences, les moratoires,
les cours du lendemain et le suivi des demandes de liaison.
"""
from datetime import timedelta

from django.utils import timezone

from school_admin.services.context_popups import card, url

HEURE_COURS_DEMAIN = 17
JOURS = ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')


def _add(result, item, evidence=None):
    if item:
        if evidence is not None:
            item['evidence'] = evidence
        result.append(item)


def situations(eleve, year, classe, parent, ctx, prefix, maintenant=None):
    """Cartes complémentaires d'un élève, pour lui-même ou pour l'un de ses parents."""
    maintenant = maintenant or timezone.now()
    today = timezone.localdate(maintenant)
    etab = eleve.etablissement
    enfant = url('school_admin:dashboard_enfant', eleve.pk)
    result = []

    # --- ELV-03 / PAR-09 : épreuves d'examen publiées dans les 7 jours ------------------------
    from school_admin.model.creneau_examen_model import CreneauExamen
    from school_admin.services.examens_planning import classes_concernees
    epreuves = []
    for creneau in CreneauExamen.objects.filter(
            session_examen__classes=classe, session_examen__annee_scolaire=year,
            session_examen__est_publie=True, session_examen__est_annule=False, session_examen__actif=True,
            actif=True, est_annule=False, date_examen__gte=today, date_examen__lte=today + timedelta(days=7),
    ).select_related('session_examen__etablissement', 'matiere').order_by('date_examen', 'heure_debut')[:30]:
        if any(c.pk == classe.pk for c in classes_concernees(creneau.session_examen, creneau.matiere)):
            epreuves.append(creneau)
    if epreuves:
        premiere = epreuves[0]
        matiere = getattr(premiere.matiere, 'nom', 'épreuve')
        texte = (f'{matiere} le {premiere.date_examen:%d/%m} à {premiere.heure_debut:%H:%M}.'
                 if len(epreuves) == 1 else
                 f'{len(epreuves)} épreuves dans les 7 jours ; la première : {matiere} le '
                 f'{premiere.date_examen:%d/%m} à {premiere.heure_debut:%H:%M}.')
        _add(result, card(f'{prefix}:examens:{premiere.session_examen_id}',
                          'Des épreuves d’examen approchent' if len(epreuves) > 1 else 'Une épreuve d’examen approche',
                          texte, enfant if parent else url('eleve:emploi_du_temps'), 'Voir le planning',
                          [(e.pk, e.date_examen, e.heure_debut) for e in epreuves], 85, ctx, 'important',
                          premiere.date_examen, code='PAR-09' if parent else 'ELV-03', icon='planning',
                          family='planning', count=len(epreuves), eleve_id=eleve.pk))

    if parent:
        # --- PAR-05 : absences non justifiées des 7 derniers jours ---------------------------
        from school_admin.model.presence_model import Presence
        jours = sorted(set(Presence.objects.filter(
            eleve=eleve, etablissement=etab, annee_scolaire=year, statut='absent',
            date__gte=today - timedelta(days=7), date__lt=today).values_list('date', flat=True)))
        if jours:
            quand = f'le {jours[-1]:%d/%m}' if len(jours) == 1 else f'sur {len(jours)} jours, dont le {jours[-1]:%d/%m}'
            _add(result, card(f'{prefix}:absences', 'Une absence à justifier',
                              f'{eleve.prenom} a été noté(e) absent(e) {quand}, sans justification enregistrée.',
                              enfant, 'Voir les absences', jours, 72, ctx, 'important', code='PAR-05',
                              icon='appel', family='presences', count=len(jours), eleve_id=eleve.pk),
                 {jour.isoformat(): 'absent' for jour in jours})

        # --- PAR-02 : échéance d'un moratoire accordé ----------------------------------------
        if etab.module_comptabilite:
            from school_admin.model.recouvrement_model import EcheanceMoratoire
            echeances = list(EcheanceMoratoire.objects.filter(
                moratoire__eleve=eleve, moratoire__etablissement=etab, moratoire__annee_scolaire=year,
                moratoire__statut='actif', date_echeance__gte=today,
                date_echeance__lte=today + timedelta(days=3)).exclude(statut='paye').order_by('date_echeance'))
            if echeances:
                premiere = echeances[0]
                devise = etab.devise_monnaie or 'FCFA'
                _add(result, card(f'{prefix}:moratoire:{premiere.pk}', 'Une échéance de votre échéancier',
                                  f'{premiere.get_reste_a_payer():,.0f} {devise} sont à régler le '
                                  f'{premiere.date_echeance:%d/%m} pour respecter l’échéancier accordé.',
                                  url('school_admin:scolarite_parent'), 'Voir la scolarité',
                                  [premiere.pk, premiere.date_echeance, premiere.montant_paye], 78, ctx, 'finance',
                                  premiere.date_echeance, code='PAR-02', icon='scolarite', family='scolarite',
                                  eleve_id=eleve.pk))
    else:
        # --- ELV-06 : mes cours de demain (option de l'établissement, à partir de 17 h) ------
        from school_admin.services.rappels.moteur import parametres
        params = parametres(etab.pk)
        if params and params.rappel_cours_demain and timezone.localtime(maintenant).hour >= HEURE_COURS_DEMAIN:
            from school_admin.services.pointage import creneaux_publies
            demain = today + timedelta(days=1)
            cours = []
            for creneau in creneaux_publies(etab, year).filter(emploi_du_temps__classe=classe,
                                                               jour=JOURS[demain.weekday()]):
                periode = creneau.periode_etablissement
                debut = creneau.heure_debut or (periode.heure_debut if periode else None)
                if debut and not (periode and getattr(periode, 'est_pause', False)):
                    cours.append((debut, getattr(creneau.matiere, 'nom', 'Cours')))
            if cours:
                cours.sort()
                _add(result, card(f'{prefix}:demain:{demain.isoformat()}', 'Tes cours de demain',
                                  f'{len(cours)} cours, à partir de {cours[0][0]:%H:%M} avec {cours[0][1]}.',
                                  url('eleve:emploi_du_temps'), 'Voir mon emploi du temps', cours, 28, ctx, 'info',
                                  demain, code='ELV-06', icon='planning', family='planning', count=len(cours),
                                  eleve_id=eleve.pk))
    return result


def parent_situations(parent, maintenant=None):
    """PAR-08 : suite donnée aux demandes de liaison du parent (7 derniers jours)."""
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent

    maintenant = maintenant or timezone.now()
    result = []
    for demande in DemandeLiaisonParent.objects.filter(
            parent_demandeur=parent, statut__in=('approuvee', 'refusee'),
            date_traitement__gte=maintenant - timedelta(days=7)).select_related('eleve_valide')[:5]:
        enfant = f'{demande.prenom_eleve} {demande.nom_eleve}'.strip()
        if demande.statut == 'approuvee' and demande.eleve_valide_id:
            item = card(f'parent:{parent.pk}:liaison:{demande.pk}:approuvee', 'Votre accès est validé',
                        f'Vous pouvez maintenant suivre {enfant} : notes, absences, devoirs et scolarité.',
                        url('school_admin:dashboard_enfant', demande.eleve_valide_id), 'Voir son suivi',
                        [demande.pk, demande.statut], 88, enfant, 'finance', code='PAR-08', icon='famille',
                        family='inscriptions', once=True, eleve_id=demande.eleve_valide_id)
        elif demande.statut == 'refusee':
            motif = f' Motif : {demande.motif_refus.strip()[:160]}' if (demande.motif_refus or '').strip() else ''
            item = card(f'parent:{parent.pk}:liaison:{demande.pk}:refusee', 'Votre demande n’a pas été acceptée',
                        f'L’établissement n’a pas validé la liaison avec {enfant}.{motif}',
                        url('school_admin:demande_liaison_enfant'), 'Refaire une demande',
                        [demande.pk, demande.statut], 70, enfant, 'important', code='PAR-08', icon='famille',
                        family='inscriptions', once=True, push=False)
        else:
            continue
        if item:
            item['etab'] = getattr(parent, 'etablissement_id', None)
            result.append(item)
    return result
