"""
Controller pour la gestion des examens selon la logique sénégalaise
"""
from collections import OrderedDict

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.db.models import Q, Prefetch
from django.utils.translation import gettext as _
from datetime import datetime, timedelta
import json
import re

from ..model.etablissement_model import Etablissement
from ..model.session_examen_model import SessionExamen
from ..model.creneau_examen_model import CreneauExamen
from ..model.periode_model import PeriodeScolaire
from ..model.classe_model import Classe
from ..model.matiere_model import Matiere
from ..model.professeur_model import Professeur
from ..model.salle_model import Salle
from ..utils.decorators_permissions import require_permission


def _libelle_niveau_classe_superieur_py(classe):
    """
    Libellé court du niveau (LMD / académique), aligné sur niveau_classe_superieur.html.
    """
    if classe.niveau_lmd == 'AUTRE' and classe.niveau_libelle:
        return classe.niveau_libelle.strip()
    if classe.niveau_lmd:
        return str(classe.niveau_lmd)
    if classe.academic_level_id:
        return f"{classe.academic_level.code} — {classe.academic_level.nom}"
    return str(_("Niveau non renseigné"))


def _build_matieres_session_superieur_meta(etablissement):
    """
    Métadonnées pour le formulaire de session (supérieur) : matières rattachées aux classes
    via M2M matière.classes ou via module.classes. Utilisé côté JS pour filtrer selon les classes cochées.
    """
    classes_sup = (
        Classe.objects.filter(etablissement=etablissement, actif=True, niveau='superieur')
        .select_related('department', 'academic_level')
        .order_by('nom')
    )
    all_ids = set(classes_sup.values_list('id', flat=True))
    id_to_classe = {c.id: c for c in classes_sup}
    if not all_ids:
        return []

    matieres = (
        Matiere.objects.filter(etablissement=etablissement, actif=True)
        .filter(Q(niveau='superieur') | Q(niveau='tous'))
        .select_related('department', 'module')
        .prefetch_related('classes', 'module__classes')
        .order_by('nom')
    )

    out = []
    for m in matieres:
        raw = set(m.get_classe_ids_pour_affectation_superieur())
        if raw:
            applicable = raw & all_ids
        else:
            applicable = set(all_ids)
        if not applicable:
            continue
        par_classe = []
        for cid in sorted(applicable):
            c = id_to_classe.get(cid)
            if not c:
                continue
            par_classe.append(
                {
                    'classe_id': cid,
                    'classe_nom': c.nom,
                    'niveau_label': _libelle_niveau_classe_superieur_py(c),
                }
            )
        out.append(
            {
                'id': m.id,
                'nom': m.nom,
                'code': m.code,
                'classe_ids': sorted(applicable),
                'par_classe': par_classe,
            }
        )
    return out


def _valider_matieres_session_superieur(classes_selectionnees, matieres):
    """
    Vérifie que chaque matière est enseignée / rattachée à au moins une des classes sélectionnées.
    Retourne (True, None) ou (False, message d'erreur).
    """
    if not classes_selectionnees:
        return False, _("Sélectionnez au moins une classe avant les matières.")
    ids_sel = {c.id for c in classes_selectionnees}
    for m in matieres:
        applicable = set(m.get_classe_ids_pour_affectation_superieur())
        if not applicable:
            continue
        if not (applicable & ids_sel):
            return False, _("La matière « %(nom)s » ne correspond à aucune des classes sélectionnées.") % {
                'nom': m.nom
            }
    return True, None


def _build_groupes_classes_examens(etablissement, est_superieur):
    """
    Construit les groupes affichés dans les onglets / formulaires de session d'examen.

    - Établissement supérieur : regroupement par filière (Department), classes LMD explicites.
    - Autres : regroupement par « niveau » déduit du nom de classe (comportement historique).
    """
    classes = (
        Classe.objects.filter(etablissement=etablissement, actif=True)
        .select_related('department', 'academic_level')
        .order_by('niveau', 'nom')
    )

    if est_superieur:
        classes = classes.filter(niveau='superieur')
        groupes = OrderedDict()
        sans = [c for c in classes if c.department_id is None]
        if sans:
            groupes['sans_filiere'] = {
                'label': 'Sans filière',
                'classes': sans,
            }
        by_dept = {}
        for c in classes:
            if c.department_id:
                by_dept.setdefault(c.department_id, []).append(c)
        for dept_id in sorted(
            by_dept.keys(),
            key=lambda did: (by_dept[did][0].department.nom.lower() if by_dept[did][0].department else ''),
        ):
            dept = by_dept[dept_id][0].department
            groupes[f'dept_{dept_id}'] = {
                'label': dept.nom if dept else f'Filière {dept_id}',
                'classes': by_dept[dept_id],
            }
        return groupes

    groupes_classes = {}
    for classe in classes:
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
        if match:
            niveau = match.group(1)
        else:
            niveau = classe.nom

        if niveau not in groupes_classes:
            groupes_classes[niveau] = {
                'label': niveau,
                'niveau': niveau,
                'classes': [],
            }

        groupes_classes[niveau]['classes'].append(classe)

    return groupes_classes


def _classes_depuis_formulaire_session(etablissement, post):
    """
    Retourne (liste de Classe, message d'erreur ou None).
    Supérieur : IDs explicites (cases à cocher par classe).
    Autres : clés de groupe « niveau » (même logique que l'affichage).
    """
    est_superieur = etablissement.type_etablissement == 'superieur'

    if est_superieur:
        raw_ids = post.getlist('classes_concernees')
        ids = []
        for x in raw_ids:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                continue
        ids = list(dict.fromkeys(ids))
        if not ids:
            return None, "Veuillez sélectionner au moins une classe."
        qs = Classe.objects.filter(
            id__in=ids,
            etablissement=etablissement,
            actif=True,
            niveau='superieur',
        ).select_related('department', 'academic_level')
        if qs.count() != len(ids):
            return None, "Sélection de classes invalide (identifiants incorrects)."
        return list(qs.order_by('nom')), None

    groupes_keys = post.getlist('groupes_classes')
    if not groupes_keys:
        return None, "Veuillez sélectionner au moins un groupe de classes."

    classes_out = []
    seen = set()
    for classe in Classe.objects.filter(etablissement=etablissement, actif=True):
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
        if match:
            niveau = match.group(1)
        else:
            niveau = classe.nom
        if niveau in groupes_keys and classe.id not in seen:
            classes_out.append(classe)
            seen.add(classe.id)

    if not classes_out:
        return None, "Aucune classe trouvée pour les groupes sélectionnés."

    return classes_out, None


def _appliquer_formulaire_session(session, post, etablissement, prefixe_matieres='matieres'):
    """
    Remplit une session depuis le formulaire (création ou modification) et la valide.
    Renvoie (classes, matieres, erreurs). Rien n'est enregistré ici.
    """
    from django.core.exceptions import ValidationError
    from ..services.examens_planning import messages_validation

    erreurs = []
    nom_examen = post.get('nom_examen', '').strip()
    periode_id = post.get('periode_id')
    date_debut_str, date_fin_str = post.get('date_debut'), post.get('date_fin')
    matieres_ids = post.getlist(prefixe_matieres) or post.getlist('matieres') or post.getlist('matieres_ids')
    if not all([nom_examen, periode_id, date_debut_str, date_fin_str]):
        return None, None, ["Nom, période et dates sont obligatoires."]
    if not matieres_ids:
        return None, None, ["Sélectionnez au moins une matière."]
    classes, err_classes = _classes_depuis_formulaire_session(etablissement, post)
    if err_classes:
        return None, None, [err_classes]
    periode = PeriodeScolaire.objects.filter(id=periode_id, etablissement=etablissement).first()
    if periode is None:
        return None, None, ["Période invalide."]
    matieres = list(Matiere.objects.filter(id__in=matieres_ids, etablissement=etablissement))
    if len(matieres) != len(set(matieres_ids)):
        return None, None, [_("Sélection de matières invalide.")]
    if etablissement.type_etablissement == 'superieur':
        ok_m, err_m = _valider_matieres_session_superieur(classes, matieres)
        if not ok_m:
            return None, None, [err_m]
    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None, None, ["Dates invalides."]

    type_session = post.get('type_session') or session.type_session or SessionExamen.TYPE_COMPOSITION
    if type_session not in dict(SessionExamen.TYPE_CHOICES):
        type_session = SessionExamen.TYPE_COMPOSITION
    session.nom_examen = nom_examen
    session.periode = periode
    session.date_debut, session.date_fin = date_debut, date_fin
    session.description = post.get('description', '').strip()
    session.type_session = type_session
    if 'compte_bulletin_present' in post:
        session.compte_bulletin = post.get('compte_bulletin') == 'on'
        session._compte_bulletin_explicite = True
    if 'est_publie_present' in post:
        session.est_publie = post.get('est_publie') == 'on'
    try:
        session.full_clean(exclude=['etablissement', 'annee_scolaire', 'duree_totale'])
    except ValidationError as exc:
        erreurs.extend(messages_validation(exc))
    return classes, matieres, erreurs


def _poids_cc_types(regle):
    from ..model.evaluation_model import Evaluation
    poids = regle.poids_cc or {}
    return [(t, l, poids.get(t, 0)) for t, l in Evaluation.TYPE_EVALUATION_CHOICES]


def _creneau_depuis_post(session, post, etablissement, annee_scolaire, champ_date='date_examen'):
    """Construit un créneau (non enregistré) ; renvoie (creneau, erreurs)."""
    date_str = post.get(champ_date) or post.get('jour_semaine') or post.get('date_examen')
    h1, h2, matiere_id = post.get('heure_debut'), post.get('heure_fin'), post.get('matiere_id')
    if not all([date_str, h1, h2, matiere_id]):
        return None, ["Date, horaires et matière sont obligatoires."]
    try:
        date_examen = datetime.strptime(date_str, '%Y-%m-%d').date()
        heure_debut = datetime.strptime(h1, '%H:%M').time()
        heure_fin = datetime.strptime(h2, '%H:%M').time()
    except (TypeError, ValueError):
        return None, ["Date ou horaire invalide."]
    matiere = Matiere.objects.filter(id=matiere_id, etablissement=etablissement).first()
    if matiere is None:
        return None, ["Matière invalide."]
    surveillant = None
    if post.get('surveillant_id'):
        surveillant = Professeur.objects.filter(id=post.get('surveillant_id'), etablissement=etablissement).first()
    salle = None
    if post.get('salle_id'):
        salle = Salle.objects.filter(id=post.get('salle_id'), etablissement=etablissement).first()
    creneau = CreneauExamen(
        session_examen=session, matiere=matiere, date_examen=date_examen,
        heure_debut=heure_debut, heure_fin=heure_fin, surveillant=surveillant, salle=salle,
        consignes_specifiques=post.get('consignes_specifiques', '').strip(),
        annee_scolaire=annee_scolaire,
    )
    if CreneauExamen.objects.filter(session_examen=session, matiere=matiere, actif=True, est_annule=False).exists():
        return None, [f"L'épreuve de {matiere.nom} est déjà planifiée dans cette session : supprimez l'ancien créneau pour la déplacer."]
    return creneau, []


def _enregistrer_creneau(request, session, etablissement, annee_scolaire):
    """Contrôle puis enregistre un créneau ; messages pour l'utilisateur. Renvoie True si créé."""
    from ..services.examens_planning import verifier_creneau

    creneau, erreurs = _creneau_depuis_post(session, request.POST, etablissement, annee_scolaire)
    if creneau is not None:
        erreurs, avertissements = verifier_creneau(creneau)
    if erreurs:
        for e in erreurs:
            messages.error(request, e)
        return False
    creneau.save()
    for a in avertissements:
        messages.warning(request, a)
    messages.success(request, f"Épreuve planifiée : {creneau.matiere.nom} le {creneau.date_examen:%d/%m/%Y} "
                              f"de {creneau.heure_debut:%H:%M} à {creneau.heure_fin:%H:%M}.")
    return True


def _build_grille_emploi_examens(session, creneaux_list):
    """
    Construit la grille horaire (dates × plages) pour une session d'examen.
    """
    from datetime import timedelta

    heures_uniques = set()
    dates_uniques = set()

    if session and session.date_debut and session.date_fin:
        date_courante = session.date_debut
        while date_courante <= session.date_fin:
            dates_uniques.add(date_courante)
            date_courante += timedelta(days=1)

    for creneau in creneaux_list:
        dates_uniques.add(creneau.date_examen)
        heures_uniques.add((creneau.heure_debut, creneau.heure_fin))

    dates_triees = sorted(dates_uniques)
    heures_triees = sorted(heures_uniques, key=lambda x: x[0])

    plages_horaires = []
    if heures_triees:
        heure_min = min(h[0] for h in heures_triees)
        heure_max = max(h[1] for h in heures_triees)
        heure_actuelle = heure_min
        while heure_actuelle < heure_max:
            dt = datetime.combine(datetime.today(), heure_actuelle)
            dt_suivant = dt + timedelta(hours=1)
            heure_suivante = dt_suivant.time()
            plages_horaires.append({
                'debut': heure_actuelle,
                'fin': heure_suivante,
                'label': f"{heure_actuelle.strftime('%H:%M')} - {heure_suivante.strftime('%H:%M')}",
            })
            heure_actuelle = heure_suivante

    jours_semaine_fr = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    grille_emploi = {}
    for date in dates_triees:
        grille_emploi[date] = {
            'date_obj': date,
            'jour_semaine': jours_semaine_fr[date.weekday()],
            'plages': {plage['label']: [] for plage in plages_horaires},
        }

    cellules_masquees = {}
    for creneau in creneaux_list:
        date = creneau.date_examen
        debut_dt = datetime.combine(datetime.today(), creneau.heure_debut)
        fin_dt = datetime.combine(datetime.today(), creneau.heure_fin)
        duree_heures = (fin_dt - debut_dt).total_seconds() / 3600
        rowspan = max(1, int(duree_heures))

        for idx, plage in enumerate(plages_horaires):
            if plage['debut'] != creneau.heure_debut:
                continue
            if date in grille_emploi:
                grille_emploi[date]['plages'][plage['label']].append({
                    'creneau': creneau,
                    'rowspan': rowspan,
                })
            if date not in cellules_masquees:
                cellules_masquees[date] = {}
            for i in range(1, rowspan):
                if idx + i < len(plages_horaires):
                    cellules_masquees[date][plages_horaires[idx + i]['label']] = True
            break

    return {
        'grille_emploi': grille_emploi,
        'plages_horaires': plages_horaires,
        'dates_triees': dates_triees,
        'cellules_masquees': cellules_masquees,
    }


@login_required
@require_permission('examens_voir')
def gestion_examens(request):
    """
    Page principale de gestion des examens avec onglets par période et groupes de classes
    """
    from ..utils.decorators_permissions import _get_user_etablissement
    result = _get_user_etablissement(request, 'examens_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de gérer les examens.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    est_superieur = etablissement.type_etablissement == 'superieur'

    # Création d'une session d'examen
    if request.method == 'POST':
        session = SessionExamen(etablissement=etablissement, annee_scolaire=annee_scolaire_active)
        classes, matieres, erreurs = _appliquer_formulaire_session(session, request.POST, etablissement)
        if erreurs:
            for e in erreurs:
                messages.error(request, e)
            return redirect('directeur:gestion_examens')
        with transaction.atomic():
            session.save()
            session.classes.set(classes)
            session.matieres.set(matieres)
        messages.success(request, f"Session « {session.nom_examen} » ({session.get_type_session_display().lower()}) créée "
                                  f"pour {len(classes)} classe(s) et {len(matieres)} matière(s). Planifiez maintenant les épreuves.")
        return redirect('directeur:configurer_creneaux_examen', session_id=session.id)

    # Récupérer toutes les périodes scolaires de l'établissement filtrées par année scolaire active
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    
    periodes = periodes.order_by('date_debut')
    
    groupes_classes = _build_groupes_classes_examens(etablissement, est_superieur)
    
    # Récupérer toutes les matières
    matieres = Matiere.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('nom')
    
    # Récupérer les sessions d'examens filtrées par année scolaire active
    sessions = SessionExamen.objects.filter(
        etablissement=etablissement,
        actif=True
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        sessions = sessions.filter(annee_scolaire=annee_scolaire_active)
    
    sessions = sessions.select_related('periode', 'etablissement').prefetch_related(
        Prefetch(
            'classes',
            queryset=Classe.objects.select_related('academic_level', 'department').order_by('nom'),
        ),
        'matieres',
    ).order_by('-date_creation')
    
    # Grouper les sessions par période
    sessions_par_periode = {}
    for session in sessions:
        periode_id = session.periode.id
        if periode_id not in sessions_par_periode:
            sessions_par_periode[periode_id] = {
                'periode': session.periode,
                'sessions': []
            }
        sessions_par_periode[periode_id]['sessions'].append(session)
    
    matieres_session_superieur_meta = (
        _build_matieres_session_superieur_meta(etablissement) if est_superieur else []
    )

    from ..templatetags.exam_filters import has_classe_groupe_examen

    periodes_avec_stats = []
    for periode in periodes:
        periode_sessions = sessions_par_periode.get(periode.id, {}).get('sessions', [])
        groupe_counts = {}
        for cle in groupes_classes:
            groupe_counts[cle] = sum(
                1 for s in periode_sessions if has_classe_groupe_examen(s, cle)
            )
        periodes_avec_stats.append({
            'periode': periode,
            'session_count': len(periode_sessions),
            'groupe_counts': groupe_counts,
        })

    stats_generales = {
        'total_sessions': sessions.count(),
        'total_periodes': periodes.count(),
        'total_groupes': len(groupes_classes),
    }

    from ..utils.directeur_ui_tabs import resolve_examens_tab_selection

    groupe_keys = list(groupes_classes.keys())
    initial_periode_id, initial_groupe_key, initial_groupe_index = resolve_examens_tab_selection(
        request, periodes_avec_stats, groupe_keys
    )

    from ..services.examens import regles as _regles_examen
    from ..services.examens_planning import avancement_session
    for session in sessions:
        session.avancement = avancement_session(session)

    context = {
        'regles_examen': _regles_examen(etablissement),
        'poids_cc_types': _poids_cc_types(_regles_examen(etablissement)),
        'types_session': SessionExamen.TYPE_CHOICES,
        'etablissement': etablissement,
        'periodes': periodes,
        'periodes_avec_stats': periodes_avec_stats,
        'groupes_classes': groupes_classes,
        'initial_periode_id': initial_periode_id,
        'initial_groupe_key': initial_groupe_key,
        'initial_groupe_index': initial_groupe_index,
        'matieres': matieres,
        'sessions_par_periode': sessions_par_periode,
        'stats_generales': stats_generales,
        'annee_scolaire_active': annee_scolaire_active,
        'est_superieur': est_superieur,
        'matieres_session_superieur_meta': matieres_session_superieur_meta,
    }
    
    return render(request, 'school_admin/directeur/gestion_examens.html', context)


@login_required
@require_permission('examens_voir')
def emploi_du_temps_examens(request):
    """
    Page d'emploi du temps des examens avec affichage en grille comme un emploi du temps classique
    """
    from ..utils.decorators_permissions import _get_user_etablissement
    result = _get_user_etablissement(request, 'examens_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de gérer l'emploi du temps des examens.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    # Ajout d'un créneau depuis l'emploi du temps
    if request.method == 'POST':
        session_examen = get_object_or_404(SessionExamen, id=request.POST.get('session_examen_id'), etablissement=etablissement)
        _enregistrer_creneau(request, session_examen, etablissement, annee_scolaire_active)
        return redirect(f"{request.path}?session={session_examen.id}")

    # Récupérer les sessions d'examens filtrées par année scolaire active
    sessions_examens = SessionExamen.objects.filter(
        etablissement=etablissement,
        actif=True
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        sessions_examens = sessions_examens.filter(annee_scolaire=annee_scolaire_active)
    
    sessions_examens = sessions_examens.select_related('periode').prefetch_related('classes', 'matieres').order_by('-date_creation')
    
    # Récupérer les créneaux d'examens filtrés par année scolaire active
    creneaux = CreneauExamen.objects.filter(
        session_examen__etablissement=etablissement,
        actif=True
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        creneaux = creneaux.filter(annee_scolaire=annee_scolaire_active)
    
    creneaux = creneaux.select_related('session_examen', 'session_examen__periode', 'matiere', 'surveillant', 'salle').order_by('date_examen', 'heure_debut')

    creneaux_par_session = {}
    for creneau in creneaux:
        creneaux_par_session.setdefault(creneau.session_examen_id, []).append(creneau)

    sessions_avec_grille = []
    for session in sessions_examens:
        session_creneaux = creneaux_par_session.get(session.id, [])
        grille_data = _build_grille_emploi_examens(session, session_creneaux)
        sessions_avec_grille.append({
            'session': session,
            'creneaux_count': len(session_creneaux),
            **grille_data,
        })

    stats_generales = {
        'total_sessions': sessions_examens.count(),
        'total_creneaux': creneaux.count(),
        'sessions_publiees': sessions_examens.filter(est_publie=True).count(),
    }

    from ..utils.directeur_ui_tabs import resolve_session_tab_selection

    session_ids = [item['session'].id for item in sessions_avec_grille]
    initial_session_id = resolve_session_tab_selection(request, session_ids)

    # Récupérer les matières, professeurs et salles
    matieres = Matiere.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
    professeurs = Professeur.objects.filter(etablissement=etablissement, actif=True).order_by('nom', 'prenom')
    salles = Salle.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
    
    from ..model.personnel_administratif_model import PersonnelAdministratif
    context = {
        'etablissement': etablissement,
        'sessions_avec_grille': sessions_avec_grille,
        'initial_session_id': initial_session_id,
        'stats_generales': stats_generales,
        'sessions_examens': sessions_examens,
        'matieres': matieres,
        'professeurs': professeurs,
        'salles': salles,
        'annee_scolaire_active': annee_scolaire_active,
        'is_directeur': is_directeur,
        'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
        'personnel': personnel,
    }

    return render(request, 'school_admin/directeur/emploi_du_temps_examens.html', context)


@login_required
@require_permission('examens_voir')
def configurer_creneaux_examen(request, session_id):
    """
    Page de configuration des créneaux pour une session d'examen spécifique
    """
    from ..utils.decorators_permissions import _get_user_etablissement
    result = _get_user_etablissement(request, 'examens_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    session = get_object_or_404(SessionExamen, id=session_id, etablissement=etablissement)
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de configurer les créneaux.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    # Ajout d'un créneau
    if request.method == 'POST':
        _enregistrer_creneau(request, session, etablissement, annee_scolaire_active)
        return redirect('directeur:configurer_creneaux_examen', session_id=session_id)

    # Récupérer les créneaux existants pour cette session
    creneaux = CreneauExamen.objects.filter(
        session_examen=session,
        actif=True
    ).select_related('matiere', 'surveillant', 'salle').order_by('date_examen', 'heure_debut')
    
    # Récupérer les professeurs et salles
    professeurs = Professeur.objects.filter(etablissement=etablissement, actif=True).order_by('nom', 'prenom')
    salles = Salle.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
    
    # Générer la liste des jours de la semaine dans la période de la session
    from datetime import timedelta
    jours_disponibles = []
    date_courante = session.date_debut
    jours_semaine_fr = {
        0: 'Lundi',
        1: 'Mardi',
        2: 'Mercredi',
        3: 'Jeudi',
        4: 'Vendredi',
        5: 'Samedi',
        6: 'Dimanche'
    }
    
    while date_courante <= session.date_fin:
        jour_semaine = date_courante.weekday()
        jours_disponibles.append({
            'date': date_courante,
            'nom_jour': jours_semaine_fr[jour_semaine],
            'date_iso': date_courante.strftime('%Y-%m-%d'),
            'date_affichage': date_courante.strftime('%d/%m/%Y')
        })
        date_courante += timedelta(days=1)
    
    from ..services.examens_planning import avancement_session, classes_concernees
    creneaux = list(creneaux)
    for c in creneaux:
        c.classes_epreuve = classes_concernees(session, c.matiere)
    avancement = avancement_session(session)
    matieres_session = list(session.matieres.all().order_by('nom'))
    planifiees = {c.matiere_id for c in creneaux}
    context = {
        'avancement': avancement,
        'matieres_a_planifier': [m for m in matieres_session if m.id not in planifiees],
        'matieres_session': matieres_session,
        'etablissement': etablissement,
        'session': session,
        'creneaux': creneaux,
        'professeurs': professeurs,
        'salles': salles,
        'jours_disponibles': jours_disponibles,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/configurer_creneaux_examen.html', context)


@login_required
@require_permission('examens_voir')
def modifier_session_examen(request, session_id):
    """
    Modifier une session d'examen existante
    """
    from ..utils.decorators_permissions import _get_user_etablissement
    result = _get_user_etablissement(request, 'examens_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    session = get_object_or_404(SessionExamen, id=session_id, etablissement=etablissement)
    
    if request.method == 'POST':
        classes, matieres, erreurs = _appliquer_formulaire_session(session, request.POST, etablissement, 'matieres_ids')
        if erreurs:
            for e in erreurs:
                messages.error(request, e)
            return redirect('directeur:gestion_examens')
        with transaction.atomic():
            session.save()
            session.classes.set(classes)
            session.matieres.set(matieres)
        messages.success(request, f"Session « {session.nom_examen} » modifiée.")
        return redirect('directeur:gestion_examens')

    # Si GET, rediriger vers la page de gestion
    return redirect('directeur:gestion_examens')


@login_required
@require_permission('examens_voir')
def supprimer_session_examen(request, session_id):
    """
    Supprimer une session d'examen et tous ses créneaux associés (CASCADE)
    """
    from ..utils.decorators_permissions import _get_user_etablissement
    result = _get_user_etablissement(request, 'examens_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    
    try:
        session = get_object_or_404(SessionExamen, id=session_id, etablissement=etablissement)
        
        # Compter les créneaux avant suppression
        nb_creneaux = session.creneaux.count()
        nom_session = session.nom_examen
        
        # La suppression des créneaux se fait automatiquement grâce au CASCADE
        session.delete()
        
        messages.success(request, f"Session '{nom_session}' et ses {nb_creneaux} créneau(x) supprimé(s) avec succès.")
        
    except Exception as e:
        messages.error(request, f"Erreur lors de la suppression de la session : {str(e)}")
    
    return redirect('directeur:gestion_examens')

@login_required
@require_permission('examens_voir')
def publier_session_examen(request, session_id):
    """Publie / retire une session : seules les sessions publiées sont visibles des élèves et parents."""
    from ..utils.decorators_permissions import _get_user_etablissement
    etablissement = _get_user_etablissement(request, 'examens_voir')[0]
    if etablissement is None or request.method != 'POST':
        return redirect('directeur:gestion_examens')
    session = get_object_or_404(SessionExamen, id=session_id, etablissement=etablissement)
    session.est_publie = not session.est_publie
    session.save(update_fields=['est_publie'])
    messages.success(request, f"« {session.nom_examen} » " + (
        "est publiée : élèves et parents voient le calendrier." if session.est_publie
        else "n'est plus visible des élèves et parents."))
    return redirect(request.POST.get('next') or 'directeur:gestion_examens')


@login_required
@require_permission('examens_voir')
def supprimer_creneau_examen(request, creneau_id):
    """Supprime une épreuve planifiée (POST)."""
    from ..utils.decorators_permissions import _get_user_etablissement
    etablissement = _get_user_etablissement(request, 'examens_voir')[0]
    if etablissement is None:
        return redirect('directeur:gestion_examens')
    creneau = get_object_or_404(CreneauExamen, id=creneau_id, session_examen__etablissement=etablissement)
    session_id = creneau.session_examen_id
    if request.method == 'POST':
        nom = creneau.matiere.nom
        creneau.delete()
        messages.success(request, f"Épreuve de {nom} retirée du planning.")
    return redirect(request.POST.get('next') or reverse('directeur:configurer_creneaux_examen', args=[session_id]))


@login_required
@require_permission('examens_voir')
def regles_examens(request):
    """Règles de calcul de l'établissement (absences, rattrapage, validation, note éliminatoire, compensation)."""
    from decimal import Decimal, InvalidOperation
    from ..services.examens import regles as _regles_examen
    from ..utils.decorators_permissions import _get_user_etablissement
    etablissement = _get_user_etablissement(request, 'examens_voir')[0]
    if etablissement is None or request.method != 'POST':
        return redirect('directeur:gestion_examens')
    r = _regles_examen(etablissement)
    post = request.POST
    if post.get('absence_injustifiee') in ('zero', 'neutre'):
        r.absence_injustifiee = post['absence_injustifiee']
    if post.get('regle_rattrapage') in ('meilleure', 'remplace'):
        r.regle_rattrapage = post['regle_rattrapage']
    try:
        seuil = Decimal((post.get('seuil_validation') or '10').replace(',', '.'))
        elim_brut = (post.get('note_eliminatoire') or '').replace(',', '.').strip()
        elim = Decimal(elim_brut) if elim_brut else None
    except InvalidOperation:
        messages.error(request, "Valeurs numériques invalides.")
        return redirect('directeur:gestion_examens')
    if not (0 < seuil <= 20) or (elim is not None and not (0 <= elim < seuil)):
        messages.error(request, "La moyenne de validation doit être entre 0 et 20, et la note éliminatoire inférieure à celle-ci.")
        return redirect('directeur:gestion_examens')
    r.seuil_validation, r.note_eliminatoire = seuil, elim
    r.compensation_semestrielle = post.get('compensation_semestrielle') == 'on'
    if 'pourcentage_passage_conditionnel' in post:
        r.compensation_annuelle = post.get('compensation_annuelle') == 'on'
        try:
            pct = int(post.get('pourcentage_passage_conditionnel') or 100)
            pts = Decimal((post.get('points_jury_max') or '0').replace(',', '.'))
        except (ValueError, InvalidOperation):
            messages.error(request, "Valeurs numériques invalides.")
            return redirect('directeur:gestion_examens')
        if not (50 <= pct <= 100) or not (0 <= pts <= 2):
            messages.error(request, "Passage conditionnel entre 50 et 100 % ; points de jury entre 0 et 2.")
            return redirect('directeur:gestion_examens')
        r.pourcentage_passage_conditionnel, r.points_jury_max = pct, pts
        from ..model.evaluation_model import Evaluation
        poids = {}
        for t, _ in Evaluation.TYPE_EVALUATION_CHOICES:
            try:
                v = int(post.get(f'poids_cc_{t}') or 0)
            except ValueError:
                v = 0
            if v > 0:
                poids[t] = min(v, 100)
        r.poids_cc = poids
    r.save()
    messages.success(request, "Règles d'examen enregistrées. Recalculez les moyennes pour les appliquer aux bulletins.")
    return redirect('directeur:gestion_examens')
