# school_admin/personal_views/enseignant_view.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from ..decorators import login_required_with_redirect
from ..model.professeur_model import Professeur
from ..services.parent_notification_service import ParentNotificationService
from ..services.directeur_notification_service import DirecteurNotificationService
from ..services.eleve_notification_service import EleveNotificationService
from ..model.notification_enseignant_model import NotificationEnseignant
import logging

logger = logging.getLogger(__name__)



def dashboard_enseignant(request):
    """
    Tableau de bord pour les enseignants/professeurs
    """
    logger.info(f"Dashboard enseignant - User: {request.user}, Type: {type(request.user).__name__}, Authenticated: {request.user.is_authenticated}")
    
    # Vérifier que l'utilisateur est bien un professeur
    if not isinstance(request.user, Professeur):
        logger.warning(f"Accès refusé au dashboard enseignant - Type d'utilisateur: {type(request.user).__name__}")
        messages.error(request, "Accès non autorisé. Cette page est réservée aux enseignants.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from datetime import datetime, timedelta
    from django.db.models import Count, Q
    from ..model.affectation_model import AffectationProfesseur
    from ..model.evaluation_model import Evaluation, Note
    from ..model.emploi_du_temps_model import EmploiDuTemps, CreneauEmploiDuTemps
    from ..model.eleve_model import Eleve
    
    # ===== INDICATEURS CLÉS =====
    
    # 1. Classes assignées
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe', 'matiere').prefetch_related('classe__eleves')
    
    total_classes = affectations.count()
    
    # 2. Élèves encadrés
    total_eleves = 0
    for affectation in affectations:
        total_eleves += affectation.classe.nombre_eleves
    
    # 3. Évaluations planifiées (dans les 7 prochains jours)
    date_debut = datetime.now().date()
    date_fin = date_debut + timedelta(days=7)
    
    evaluations_a_venir = Evaluation.objects.filter(
        professeur=professeur,
        date_evaluation__gte=date_debut,
        date_evaluation__lte=date_fin,
        actif=True
    ).count()
    
    # 4. Messages non lus (pour l'instant 0, à implémenter plus tard)
    messages_non_lus = 0
    
    # ===== LISTE DES CLASSES AVEC DÉTAILS =====
    classes_data = []
    for affectation in affectations[:3]:  # Limiter à 3 pour le dashboard
        classe = affectation.classe
        
        # Calculer les heures par semaine
        creneaux_classe = CreneauEmploiDuTemps.objects.filter(
            emploi_du_temps__classe=classe,
            emploi_du_temps__est_actif=True,
            emploi_du_temps__statut_publication='publie',
            professeur=professeur
        ).select_related('periode_etablissement')
        
        heures_semaine = 0
        for creneau in creneaux_classe:
            heures_semaine += creneau.duree_minutes / 60
        
        # Progression fictive basée sur la date (pour avoir quelque chose de dynamique)
        mois_ecoule = datetime.now().month - 9  # Septembre = mois 1
        if mois_ecoule < 0:
            mois_ecoule += 12
        progression = min(int(mois_ecoule / 9 * 100), 100)  # 9 mois d'école
        
        classes_data.append({
            'classe': classe,
            'matiere': affectation.matiere if affectation.matiere else professeur.matiere_principale,
            'nombre_eleves': classe.nombre_eleves,
            'heures_semaine': round(heures_semaine, 1),
            'progression': progression,
            'est_principal': affectation.is_principal,
        })
    
    # ===== EMPLOI DU TEMPS D'AUJOURD'HUI =====
    jours_mapping = {
        0: 'lundi',
        1: 'mardi',
        2: 'mercredi',
        3: 'jeudi',
        4: 'vendredi',
        5: 'samedi',
        6: 'dimanche',
    }
    
    jour_actuel = jours_mapping.get(datetime.now().weekday(), 'lundi')
    date_actuelle = datetime.now()
    
    classes_professeur = [affectation.classe for affectation in affectations]
    emplois_actifs = EmploiDuTemps.objects.filter(classe__in=classes_professeur, est_actif=True)
    emplois_publies = emplois_actifs.filter(statut_publication='publie')
    emploi_publie_disponible = emplois_publies.exists()
    
    if emploi_publie_disponible:
        creneaux_aujourdhui = CreneauEmploiDuTemps.objects.filter(
            professeur=professeur,
            jour=jour_actuel,
            emploi_du_temps__in=emplois_publies
        ).select_related('emploi_du_temps__classe', 'matiere', 'salle', 'periode_etablissement').order_by('periode_etablissement__ordre', 'heure_debut')
    else:
        creneaux_aujourdhui = []
    
    # Ajouter icônes et couleurs aux créneaux d'aujourd'hui
    from ..controllers.emploi_du_temps_controller import get_matiere_config
    for creneau in creneaux_aujourdhui:
        matiere_nom = creneau.matiere.nom if creneau.matiere else "Sans matière"
        icone, couleur = get_matiere_config(matiere_nom)
        creneau.matiere_icone = icone
        creneau.matiere_couleur = couleur
    
    # ===== DEVOIRS À CORRIGER =====
    # Récupérer les évaluations avec des notes manquantes
    evaluations_avec_notes = Evaluation.objects.filter(
        professeur=professeur,
        date_evaluation__lte=date_debut,
        actif=True
    ).annotate(
        nombre_notes=Count('notes')
    ).select_related('classe')
    
    devoirs_a_corriger = []
    for evaluation in evaluations_avec_notes[:3]:  # Limiter à 3
        classe = evaluation.classe
        nombre_eleves = classe.nombre_eleves
        nombre_notes = evaluation.nombre_notes
        
        if nombre_notes < nombre_eleves:
            pourcentage_correction = int((nombre_notes / nombre_eleves * 100)) if nombre_eleves > 0 else 0
            devoirs_a_corriger.append({
                'evaluation': evaluation,
                'classe': classe,
                'nombre_notes': nombre_notes,
                'nombre_eleves': nombre_eleves,
                'pourcentage_correction': pourcentage_correction,
            })
    
    # ===== PROCHAINES ÉVALUATIONS =====
    prochaines_evaluations = Evaluation.objects.filter(
        professeur=professeur,
        date_evaluation__gt=date_debut,
        actif=True
    ).select_related('classe').order_by('date_evaluation')[:3]
    
    evaluations_data = []
    for evaluation in prochaines_evaluations:
        jours_restants = (evaluation.date_evaluation - date_debut).days
        
        if jours_restants <= 3:
            statut = 'ready'
            statut_label = 'Prêt'
        else:
            statut = 'upcoming'
            statut_label = 'À préparer'
        
        evaluations_data.append({
            'evaluation': evaluation,
            'jours_restants': jours_restants,
            'statut': statut,
            'statut_label': statut_label,
        })
    
    notifications_non_lues = NotificationEnseignant.objects.filter(
        enseignant=professeur, statut='non_lu'
    ).count()
    
    context = {
        'professeur': professeur,
        
        # Indicateurs
        'total_classes': total_classes,
        'total_eleves': total_eleves,
        'evaluations_a_venir': evaluations_a_venir,
        'messages_non_lus': messages_non_lus,
        'notifications_enseignant_non_lues': notifications_non_lues,
        
        # Classes
        'classes_data': classes_data,
        
        # Emploi du temps
        'jour_actuel': jour_actuel,
        'jour_actuel_display': jour_actuel.capitalize(),
        'date_actuelle': date_actuelle,
        'creneaux_aujourdhui': creneaux_aujourdhui,
        'emploi_publie': emploi_publie_disponible,
        'emploi_non_publie': (not emploi_publie_disponible) and emplois_actifs.exists(),
        
        # Devoirs et évaluations
        'devoirs_a_corriger': devoirs_a_corriger,
        'evaluations_data': evaluations_data,
    }
    
    return render(request, 'school_admin/enseignant/dashboard_enseignant.html', context)


def gestion_classes_enseignant(request):
    """
    Page de gestion des classes pour l'enseignant avec regroupement par catégorie
    """
    logger.info(f"Gestion classes - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    logger.info(f"Type établissement: {professeur.etablissement.type_etablissement if professeur.etablissement else 'None'}")
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        logger.info("Redirection vers enseignant_primaire:gestion_classes")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Récupérer toutes les affectations actives du professeur
    from ..model.affectation_model import AffectationProfesseur
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe', 'classe__etablissement').prefetch_related('classe__eleves').order_by('classe__nom')
    
    # Créer une liste de données pour chaque classe
    classes_data = []
    for affectation in affectations:
        classe = affectation.classe
        nombre_eleves = classe.nombre_eleves
        taux_occupation = (nombre_eleves / classe.capacite_max * 100) if classe.capacite_max > 0 else 0
        
        classes_data.append({
            'affectation': affectation,
            'classe': classe,
            'matiere': affectation.matiere,  # Matière enseignée pour cette affectation
            'nombre_eleves': nombre_eleves,
            'capacite_max': classe.capacite_max,
            'taux_occupation': round(taux_occupation, 1),
            'est_principal': affectation.is_principal,
            'statut_display': affectation.statut_display,
        })
    
    # Regrouper les classes par catégorie (niveau)
    import re
    classes_grouped = {}
    
    for classe_data in classes_data:
        classe = classe_data['classe']
        nom = classe.nom
        
        # Pattern pour extraire le niveau et la lettre/section
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "6ème", "5ème", "Terminale", etc.
            section = match.group(2)    # "A", "B", "C", "1", "2", etc.
        else:
            # Si pas de pattern trouvé, utiliser le nom complet comme catégorie
            categorie = nom
            section = ""
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'total_capacite': 0,
                'nombre_classes': 0
            }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += classe_data['nombre_eleves']
        classes_grouped[categorie]['total_capacite'] += classe_data['capacite_max']
        classes_grouped[categorie]['nombre_classes'] += 1
    
    # Calculer le taux moyen pour chaque catégorie
    for categorie, data in classes_grouped.items():
        if data['total_capacite'] > 0:
            data['taux_moyen'] = round((data['total_eleves'] / data['total_capacite']) * 100, 1)
        else:
            data['taux_moyen'] = 0
    
    # Statistiques globales
    stats = {
        'total_classes': len(classes_data),
        'total_eleves': sum(cd['nombre_eleves'] for cd in classes_data),
        'classes_principales': sum(1 for cd in classes_data if cd['est_principal']),
        'classes_classiques': sum(1 for cd in classes_data if not cd['est_principal']),
    }
    
    context = {
        'professeur': professeur,
        'classes_grouped': classes_grouped,
        'stats': stats,
        'total_classes': stats['total_classes'],
    }
    
    return render(request, 'school_admin/enseignant/gestion_classes.html', context)


def gestion_eleves_enseignant(request):
    """
    Page de gestion des élèves pour l'enseignant avec regroupement par catégorie de classe
    """
    logger.info(f"Gestion élèves - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.affectation_model import AffectationProfesseur
    import re
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Récupérer toutes les affectations actives du professeur
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe').prefetch_related('classe__eleves').order_by('classe__nom')
    
    # Regrouper les classes par catégorie
    classes_grouped = {}
    total_eleves = 0
    
    for affectation in affectations:
        classe = affectation.classe
        nom = classe.nom
        
        # Pattern pour extraire le niveau et la lettre/section
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)
            section = match.group(2)
        else:
            categorie = nom
            section = ""
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0,
            }
        
        # Récupérer les élèves actifs de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        # Ajouter le nombre d'absences et sanctions pour chaque élève
        # IMPORTANT : Filtrer par matière et par professeur selon le rôle
        from ..model.presence_model import Presence
        from ..model.sanction_model import Sanction
        from django.db.models import Q
        
        matiere_affectation = affectation.matiere if affectation.matiere else professeur.matiere_principale
        
        eleves_avec_absences = []
        for eleve in eleves:
            # Filtrer les absences selon le rôle et la matière
            if affectation.is_principal:
                # Professeur principal : voir TOUTES les absences de la classe
                nombre_absences = Presence.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    statut='absent'
                ).count()
            else:
                # Professeur classique : voir uniquement SES absences pour SA matière
                filters_abs = {
                    'eleve': eleve,
                    'professeur': professeur,
                    'statut': 'absent'
                }
                if matiere_affectation:
                    filters_abs['matiere'] = matiere_affectation
                else:
                    filters_abs['matiere__isnull'] = True
                
                nombre_absences = Presence.objects.filter(**filters_abs).count()
            
            nombre_sanctions = Sanction.get_nombre_sanctions(eleve)
            eleves_avec_absences.append({
                'eleve': eleve,
                'nombre_absences': nombre_absences,
                'nombre_sanctions': nombre_sanctions
            })
        
        classe_data = {
            'classe': classe,
            'affectation': affectation,
            'matiere': matiere_affectation,  # Matière enseignée pour cette affectation
            'eleves': eleves_avec_absences,
            'nombre_eleves': eleves.count(),
            'est_principal': affectation.is_principal,
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
        total_eleves += eleves.count()
    
    # Statistiques globales
    stats = {
        'total_classes': affectations.count(),
        'total_eleves': total_eleves,
    }
    
    context = {
        'professeur': professeur,
        'classes_grouped': classes_grouped,
        'stats': stats,
    }
    
    return render(request, 'school_admin/enseignant/gestion_eleves.html', context)


def gestion_notes_enseignant(request):
    """
    Page de gestion des notes pour l'enseignant avec regroupement par catégorie et périodes
    """
    logger.info(f"Gestion notes - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.affectation_model import AffectationProfesseur
    from ..model.moyenne_model import Moyenne
    from ..model.evaluation_model import Evaluation
    from ..model.periode_model import PeriodeScolaire
    import re
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        return redirect('enseignant_primaire:gestion_notes')
    
    # Récupérer toutes les périodes scolaires de l'établissement
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer l'ID de la période sélectionnée (depuis GET ou par défaut la période en cours)
    periode_id = request.GET.get('periode', '')
    periode_active_obj = None
    
    if periode_id:
        try:
            periode_active_obj = periodes_scolaires.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    # Si aucune période sélectionnée, prendre la période en cours ou la première
    if not periode_active_obj:
        # Rechercher la période en cours manuellement (est_en_cours est une propriété)
        for periode in periodes_scolaires:
            if periode.est_en_cours:
                periode_active_obj = periode
                break
        if not periode_active_obj:
            periode_active_obj = periodes_scolaires.first()
    
    # Récupérer toutes les affectations actives du professeur
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe', 'classe__etablissement').prefetch_related('classe__eleves').order_by('classe__nom')
    
    # Regrouper les classes par catégorie
    classes_grouped = {}
    total_eleves = 0
    
    for affectation in affectations:
        classe = affectation.classe
        nom = classe.nom
        
        # Pattern pour extraire le niveau et la lettre/section
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)
            section = match.group(2)
        else:
            categorie = nom
            section = ""
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0,
            }
        
        # Récupérer les élèves actifs de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        # Déterminer la matière enseignée pour cette affectation
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
        
        # Récupérer les évaluations pour cette classe, matière et période
        evaluations_liste = []
        if periode_active_obj and matiere_enseignee:
            evaluations_interrogations = Evaluation.objects.filter(
                classe=classe,
                professeur=professeur,
                type_evaluation='interrogation',
                periode_scolaire=periode_active_obj,
                actif=True,
                matiere=matiere_enseignee
            ).order_by('date_evaluation')
            
            evaluations_devoirs = Evaluation.objects.filter(
                classe=classe,
                professeur=professeur,
                type_evaluation__in=['controle', 'devoir_maison'],
                periode_scolaire=periode_active_obj,
                actif=True,
                matiere=matiere_enseignee
            ).order_by('date_evaluation')
            
            # Construire la liste des évaluations avec clés pour le template
            for i, eval_obj in enumerate(evaluations_interrogations, 1):
                evaluations_liste.append({
                    'key': f'interro_{i}',
                    'evaluation': eval_obj,
                    'type': 'interrogation',
                    'index': i,
                })
            
            for i, eval_obj in enumerate(evaluations_devoirs, 1):
                evaluations_liste.append({
                    'key': f'devoir_{i}',
                    'evaluation': eval_obj,
                    'type': 'devoir',
                    'index': i,
                })
        
        # Récupérer toutes les notes pour ces évaluations
        from ..model.evaluation_model import Note
        notes_par_eleve_et_eval = {}
        if evaluations_liste:
            eval_ids = [e['evaluation'].id for e in evaluations_liste]
            notes = Note.objects.filter(
                evaluation_id__in=eval_ids,
                matiere=matiere_enseignee
            ).select_related('evaluation', 'eleve')
            
            for note in notes:
                eval_id = note.evaluation.id
                eleve_id = note.eleve.id
                if eleve_id not in notes_par_eleve_et_eval:
                    notes_par_eleve_et_eval[eleve_id] = {}
                notes_par_eleve_et_eval[eleve_id][eval_id] = note
        
        # Récupérer les moyennes pour cette classe et cette période
        # Note: Le système de moyennes utilise encore l'ancien format
        # On peut filtrer par date à la place si période_active_obj existe
        if periode_active_obj:
            moyennes = Moyenne.objects.filter(
                classe=classe,
                professeur=professeur,
                matiere=matiere_enseignee,
                actif=True
            ).select_related('eleve')
        else:
            moyennes = Moyenne.objects.none()
        
        # Créer un dictionnaire des moyennes par élève
        moyennes_par_eleve = {}
        for moy in moyennes:
            moyennes_par_eleve[moy.eleve.id] = moy
        
        # Ajouter les moyennes et notes aux élèves (et la note d'examen si disponible)
        eleves_avec_moyennes = []
        total_moyennes = 0
        count_moyennes = 0
        # Trouver la session d'examen pour cette classe/matière/période
        session_examen_classe = None
        if periode_active_obj:
            from ..model.session_examen_model import SessionExamen
            from ..model.note_examen_model import NoteExamen
            sessions_possibles = SessionExamen.objects.filter(
                etablissement=professeur.etablissement,
                classes=classe,
                matieres=matiere_enseignee,
                periode=periode_active_obj,
                actif=True
            ).order_by('-date_debut')
            if sessions_possibles.exists():
                # Prioriser une session avec des notes saisies
                for sess in sessions_possibles:
                    if NoteExamen.objects.filter(session_examen=sess, matiere=matiere_enseignee, classe=classe, actif=True).exists():
                        session_examen_classe = sess
                        break
                if not session_examen_classe:
                    session_examen_classe = sessions_possibles.first()
        for eleve in eleves:
            moyenne_obj = moyennes_par_eleve.get(eleve.id)
            # Récupérer les notes de cet élève pour les évaluations
            notes_eleve = notes_par_eleve_et_eval.get(eleve.id, {})
            # Récupérer la note d'examen si une session est disponible
            note_examen_dict = None
            if session_examen_classe:
                from ..model.note_examen_model import NoteExamen
                note_exam_obj = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session_examen_classe,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                ).first()
                if note_exam_obj and note_exam_obj.note is not None and not note_exam_obj.absent:
                    note_examen_dict = {
                        'note': float(note_exam_obj.note),
                        'bareme': float(note_exam_obj.bareme) if hasattr(note_exam_obj, 'bareme') else 20.0
                    }
            eleves_avec_moyennes.append({
                'eleve': eleve,
                'moyenne': moyenne_obj,
                'notes': notes_eleve,
                'note_examen': note_examen_dict
            })
            if moyenne_obj:
                total_moyennes += float(moyenne_obj.moyenne)
                count_moyennes += 1
        
        # Calculer la moyenne de classe
        moyenne_classe = round(total_moyennes / count_moyennes, 2) if count_moyennes > 0 else None
        
        classe_data = {
            'classe': classe,
            'affectation': affectation,
            'matiere': affectation.matiere,  # Matière enseignée pour cette affectation
            'eleves': eleves_avec_moyennes,
            'evaluations': evaluations_liste,  # Ajouter la liste des évaluations
            'nombre_eleves': eleves.count(),
            'est_principal': affectation.is_principal,
            'moyenne_classe': moyenne_classe,
            'has_examen': True if session_examen_classe else False,
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
        total_eleves += eleves.count()
    
    # Statistiques globales
    stats = {
        'total_classes': affectations.count(),
        'total_eleves': total_eleves,
    }
    
    # Récupérer les sessions d'examens pour les classes du professeur
    from ..model.session_examen_model import SessionExamen
    
    # Récupérer toutes les classes du professeur
    classes_prof = [aff.classe for aff in affectations]
    
    # Trouver les sessions d'examens qui concernent:
    # 1. Les classes du professeur
    # 2. La matière du professeur
    # 3. La période active
    sessions_examens_par_classe = {}
    
    if professeur.matiere_principale and periode_active_obj:
        for classe in classes_prof:
            sessions = SessionExamen.objects.filter(
                etablissement=professeur.etablissement,
                classes=classe,
                matieres=professeur.matiere_principale,
                periode=periode_active_obj,
                actif=True
            ).distinct()
            
            if sessions.exists():
                sessions_examens_par_classe[classe.id] = sessions.first()
    
    context = {
        'professeur': professeur,
        'classes_grouped': classes_grouped,
        'stats': stats,
        'matiere_principale': professeur.matiere_principale,
        'periode_active': periode_active_obj,
        'periodes_scolaires': periodes_scolaires,
        'sessions_examens_par_classe': sessions_examens_par_classe,
    }
    
    return render(request, 'school_admin/enseignant/gestion_notes.html', context)


def gestion_presence_enseignant(request):
    """
    Page de transition pour la gestion de présence pour l'enseignant avec regroupement par catégorie
    Même structure que gestion_notes_enseignant mais pour la présence
    """
    logger.info(f"Gestion présence - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.affectation_model import AffectationProfesseur
    from ..model.presence_model import Presence
    import re
    from django.db.models import Q, Count
    from django.utils import timezone
    from datetime import timedelta
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        return redirect('enseignant_primaire:gestion_presence')
    
    # Récupérer toutes les affectations actives du professeur
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe', 'classe__etablissement').prefetch_related('classe__eleves').order_by('classe__nom')
    
    # Regrouper les classes par catégorie
    classes_grouped = {}
    total_eleves = 0
    
    # Calculer la date de début de l'année scolaire (septembre)
    debut_annee = timezone.now().replace(month=9, day=1, hour=0, minute=0, second=0, microsecond=0)
    if timezone.now().month < 9:
        debut_annee = debut_annee.replace(year=debut_annee.year - 1)
    
    for affectation in affectations:
        classe = affectation.classe
        nom = classe.nom
        
        # Pattern pour extraire le niveau et la lettre/section
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)
            section = match.group(2)
        else:
            categorie = nom
            section = ""
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0,
            }
        
        # Récupérer les élèves actifs de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        # Déterminer la matière enseignée pour cette affectation
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
        
        # Calculer les statistiques de présence pour chaque élève
        # IMPORTANT : Si professeur principal → voir TOUTES les présences, sinon uniquement les siennes
        # IMPORTANT : Filtrer par matière pour différencier les présences de chaque matière
        eleves_avec_presence = []
        for eleve in eleves:
            # Déterminer si on filtre par professeur ou pas
            if affectation.is_principal:
                # Professeur principal : voir TOUTES les présences de la classe (toutes matières)
                presences = Presence.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    date__gte=debut_annee
                )
            else:
                # Professeur classique : voir uniquement SES présences pour SA matière
                filters_presence = {
                    'eleve': eleve,
                    'professeur': professeur,
                    'date__gte': debut_annee
                }
                # Filtrer par matière si elle existe
                if matiere_enseignee:
                    filters_presence['matiere'] = matiere_enseignee
                else:
                    filters_presence['matiere__isnull'] = True
                
                presences = Presence.objects.filter(**filters_presence)
            
            # Compter les présences par statut
            nombre_presences = presences.filter(statut='present').count()
            nombre_absences = presences.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
            nombre_retards = presences.filter(statut='retard').count()
            nombre_jours = presences.values('date').distinct().count()
            
            eleves_avec_presence.append({
                'eleve': eleve,
                'nombre_presences': nombre_presences,
                'nombre_absences': nombre_absences,
                'nombre_retards': nombre_retards,
                'nombre_jours': nombre_jours,
            })
        
        classe_data = {
            'classe': classe,
            'affectation': affectation,
            'matiere': matiere_enseignee,
            'eleves': eleves_avec_presence,
            'nombre_eleves': eleves.count(),
            'est_principal': affectation.is_principal,
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
        total_eleves += eleves.count()
    
    # Statistiques globales
    stats = {
        'total_classes': affectations.count(),
        'total_eleves': total_eleves,
    }
    
    context = {
        'professeur': professeur,
        'classes_grouped': classes_grouped,
        'stats': stats,
        'matiere_principale': professeur.matiere_principale,
    }
    
    return render(request, 'school_admin/enseignant/gestion_presence.html', context)


def eleves_en_difficulte_enseignant(request):
    """
    Page pour afficher les élèves en difficulté (moyenne < 9) pour l'enseignant
    Même structure que gestion_notes_enseignant mais filtré sur les élèves avec moyenne < 9
    """
    logger.info(f"Élèves en difficulté - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.affectation_model import AffectationProfesseur
    from ..model.moyenne_model import Moyenne
    from ..model.evaluation_model import Evaluation
    from ..model.periode_model import PeriodeScolaire
    import re
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        periode_id = request.GET.get('periode', '')
        if periode_id:
            return redirect(f'/enseignant/primaire/eleves-difficulte/?periode={periode_id}')
        return redirect('enseignant_primaire:eleves_en_difficulte')
    
    # Récupérer toutes les périodes scolaires de l'établissement
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer l'ID de la période sélectionnée (depuis GET ou par défaut la période en cours)
    periode_id = request.GET.get('periode', '')
    periode_active_obj = None
    
    if periode_id:
        try:
            periode_active_obj = periodes_scolaires.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    # Si aucune période sélectionnée, prendre la période en cours ou la première
    if not periode_active_obj:
        # Rechercher la période en cours manuellement (est_en_cours est une propriété)
        for periode in periodes_scolaires:
            if periode.est_en_cours:
                periode_active_obj = periode
                break
        if not periode_active_obj:
            periode_active_obj = periodes_scolaires.first()
    
    # Récupérer toutes les affectations actives du professeur
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe', 'classe__etablissement').prefetch_related('classe__eleves').order_by('classe__nom')
    
    # Regrouper les classes par catégorie
    classes_grouped = {}
    total_eleves = 0
    total_eleves_difficulte = 0
    
    for affectation in affectations:
        classe = affectation.classe
        nom = classe.nom
        
        # Pattern pour extraire le niveau et la lettre/section
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)
            section = match.group(2)
        else:
            categorie = nom
            section = ""
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0,
            }
        
        # Récupérer les élèves actifs de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        # Déterminer la matière enseignée pour cette affectation
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
        
        # Récupérer les évaluations pour cette classe, matière et période
        evaluations_liste = []
        if periode_active_obj and matiere_enseignee:
            evaluations_interrogations = Evaluation.objects.filter(
                classe=classe,
                professeur=professeur,
                type_evaluation='interrogation',
                periode_scolaire=periode_active_obj,
                actif=True,
                matiere=matiere_enseignee
            ).order_by('date_evaluation')
            
            evaluations_devoirs = Evaluation.objects.filter(
                classe=classe,
                professeur=professeur,
                type_evaluation__in=['controle', 'devoir_maison'],
                periode_scolaire=periode_active_obj,
                actif=True,
                matiere=matiere_enseignee
            ).order_by('date_evaluation')
            
            # Construire la liste des évaluations avec clés pour le template
            for i, eval_obj in enumerate(evaluations_interrogations, 1):
                evaluations_liste.append({
                    'key': f'interro_{i}',
                    'evaluation': eval_obj,
                    'type': 'interrogation',
                    'index': i,
                })
            
            for i, eval_obj in enumerate(evaluations_devoirs, 1):
                evaluations_liste.append({
                    'key': f'devoir_{i}',
                    'evaluation': eval_obj,
                    'type': 'devoir',
                    'index': i,
                })
        
        # Récupérer toutes les notes pour ces évaluations
        from ..model.evaluation_model import Note
        notes_par_eleve_et_eval = {}
        if evaluations_liste:
            eval_ids = [e['evaluation'].id for e in evaluations_liste]
            notes = Note.objects.filter(
                evaluation_id__in=eval_ids,
                matiere=matiere_enseignee
            ).select_related('evaluation', 'eleve')
            
            for note in notes:
                eval_id = note.evaluation.id
                eleve_id = note.eleve.id
                if eleve_id not in notes_par_eleve_et_eval:
                    notes_par_eleve_et_eval[eleve_id] = {}
                notes_par_eleve_et_eval[eleve_id][eval_id] = note
        
        # Récupérer les moyennes pour cette classe et cette période
        if periode_active_obj:
            moyennes = Moyenne.objects.filter(
                classe=classe,
                professeur=professeur,
                matiere=matiere_enseignee,
                actif=True
            ).select_related('eleve')
        else:
            moyennes = Moyenne.objects.none()
        
        # Créer un dictionnaire des moyennes par élève
        moyennes_par_eleve = {}
        for moy in moyennes:
            moyennes_par_eleve[moy.eleve.id] = moy
        
        # Filtrer les élèves en difficulté (moyenne < 9)
        eleves_difficulte = []
        total_moyennes = 0
        count_moyennes = 0
        
        # Trouver la session d'examen pour cette classe/matière/période
        session_examen_classe = None
        if periode_active_obj:
            from ..model.session_examen_model import SessionExamen
            from ..model.note_examen_model import NoteExamen
            sessions_possibles = SessionExamen.objects.filter(
                etablissement=professeur.etablissement,
                classes=classe,
                matieres=matiere_enseignee,
                periode=periode_active_obj,
                actif=True
            ).order_by('-date_debut')
            if sessions_possibles.exists():
                # Prioriser une session avec des notes saisies
                for sess in sessions_possibles:
                    if NoteExamen.objects.filter(session_examen=sess, matiere=matiere_enseignee, classe=classe, actif=True).exists():
                        session_examen_classe = sess
                        break
                if not session_examen_classe:
                    session_examen_classe = sessions_possibles.first()
        
        for eleve in eleves:
            moyenne_obj = moyennes_par_eleve.get(eleve.id)
            
            # Ne garder que les élèves avec moyenne < 9
            if moyenne_obj and moyenne_obj.moyenne < 9:
                # Récupérer les notes de cet élève pour les évaluations
                notes_eleve = notes_par_eleve_et_eval.get(eleve.id, {})
                # Récupérer la note d'examen si une session est disponible
                note_examen_dict = None
                if session_examen_classe:
                    from ..model.note_examen_model import NoteExamen
                    note_exam_obj = NoteExamen.objects.filter(
                        eleve=eleve,
                        session_examen=session_examen_classe,
                        matiere=matiere_enseignee,
                        classe=classe,
                        actif=True
                    ).first()
                    if note_exam_obj and note_exam_obj.note is not None and not note_exam_obj.absent:
                        note_examen_dict = {
                            'note': float(note_exam_obj.note),
                            'bareme': float(note_exam_obj.bareme) if hasattr(note_exam_obj, 'bareme') else 20.0
                        }
                
                eleves_difficulte.append({
                    'eleve': eleve,
                    'moyenne': moyenne_obj,
                    'notes': notes_eleve,
                    'note_examen': note_examen_dict
                })
                total_moyennes += float(moyenne_obj.moyenne)
                count_moyennes += 1
        
        # Calculer la moyenne des élèves en difficulté
        moyenne_classe_difficulte = round(total_moyennes / count_moyennes, 2) if count_moyennes > 0 else None
        
        # N'ajouter la classe que si elle a des élèves en difficulté
        if eleves_difficulte:
            classe_data = {
                'classe': classe,
                'affectation': affectation,
                'matiere': matiere_enseignee,
                'eleves': eleves_difficulte,
                'evaluations': evaluations_liste,
                'nombre_eleves': len(eleves_difficulte),
                'nombre_total_eleves': eleves.count(),
                'est_principal': affectation.is_principal,
                'moyenne_classe': moyenne_classe_difficulte,
                'has_examen': True if session_examen_classe else False,
            }
            
            classes_grouped[categorie]['classes'].append(classe_data)
            classes_grouped[categorie]['total_eleves'] += len(eleves_difficulte)
            total_eleves_difficulte += len(eleves_difficulte)
    
    # Supprimer les catégories vides
    classes_grouped = {k: v for k, v in classes_grouped.items() if v['classes']}
    
    # Statistiques globales
    stats = {
        'total_classes': len([c for data in classes_grouped.values() for c in data['classes']]),
        'total_eleves': total_eleves_difficulte,
    }
    
    context = {
        'professeur': professeur,
        'classes_grouped': classes_grouped,
        'stats': stats,
        'matiere_principale': professeur.matiere_principale,
        'periode_active': periode_active_obj,
        'periodes_scolaires': periodes_scolaires,
    }
    
    return render(request, 'school_admin/enseignant/eleves_en_difficulte.html', context)


def noter_examen_enseignant(request, classe_id, session_id=None):
    """
    Page pour noter les élèves d'une classe pour un examen spécifique
    Gère les onglets par période et les sous-onglets par session
    """
    logger.info(f"Noter examen - User: {request.user}, Classe ID: {classe_id}, Session ID: {session_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.classe_model import Classe
    from ..model.session_examen_model import SessionExamen
    from ..model.note_examen_model import NoteExamen
    from ..model.periode_model import PeriodeScolaire
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    from django.utils import timezone
    from decimal import Decimal
    from collections import defaultdict
    
    # Vérifier que la classe existe
    classe = get_object_or_404(Classe, id=classe_id, etablissement=professeur.etablissement)
    
    # Récupérer toutes les périodes scolaires
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer toutes les sessions d'examen pour cette classe et cette matière
    toutes_sessions = SessionExamen.objects.filter(
        etablissement=professeur.etablissement,
        classes=classe,
        matieres=professeur.matiere_principale,
        actif=True
    ).select_related('periode').order_by('-date_debut')
    
    # Organiser les sessions par période
    sessions_par_periode = defaultdict(list)
    for session in toutes_sessions:
        sessions_par_periode[session.periode.id].append(session)
    
    # Déterminer la période et session actives
    periode_id = request.GET.get('periode')
    if not periode_id and toutes_sessions.exists():
        # Par défaut, sélectionner la période de la première session
        periode_id = str(toutes_sessions.first().periode.id)
    
    periode_active = None
    if periode_id:
        try:
            periode_active = periodes_scolaires.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    # Si session_id n'est pas fourni, prendre la première session de la période active
    if not session_id and periode_active and periode_active.id in sessions_par_periode:
        session_examen = sessions_par_periode[periode_active.id][0]
    elif session_id:
        session_examen = get_object_or_404(SessionExamen, id=session_id, etablissement=professeur.etablissement)
    else:
        # Aucune session trouvée
        messages.warning(request, "Aucune session d'examen trouvée pour cette classe.")
        return redirect('enseignant:gestion_notes')
    
    # Vérifier que la matière du professeur fait partie de la session
    if professeur.matiere_principale not in session_examen.matieres.all():
        messages.error(request, "Votre matière ne fait pas partie de cette session d'examen.")
        return redirect('enseignant:gestion_notes')
    
    # Vérifier que la classe fait partie de la session
    if classe not in session_examen.classes.all():
        messages.error(request, "Cette classe ne fait pas partie de cette session d'examen.")
        return redirect('enseignant:gestion_notes')
    
    # Récupérer les élèves actifs de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Barème par défaut (peut être modifié selon les besoins)
    bareme = Decimal('20.00')
    
    # Fonction pour générer un commentaire automatique basé sur la note
    def generer_commentaire_auto(note_sur_20):
        if note_sur_20 is None:
            return ""
        elif note_sur_20 >= 18:
            return "Excellent travail ! Résultats exceptionnels."
        elif note_sur_20 >= 16:
            return "Très bon travail ! Continue ainsi."
        elif note_sur_20 >= 14:
            return "Bon travail. Résultats satisfaisants."
        elif note_sur_20 >= 12:
            return "Travail correct. Peut mieux faire."
        elif note_sur_20 >= 10:
            return "Résultat moyen. Doit fournir plus d'efforts."
        elif note_sur_20 >= 8:
            return "Résultat fragile. Nécessite du travail supplémentaire."
        else:
            return "Résultat insuffisant. Besoin de soutien important."
    
    # Vérifier si les notes ont déjà été soumises
    premiere_note = NoteExamen.objects.filter(
        session_examen=session_examen,
        matiere=professeur.matiere_principale,
        classe=classe
    ).first()
    notes_soumises = premiere_note.soumis if premiere_note else False
    
    # Traitement du formulaire
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Vérifier si les notes sont déjà soumises
        if notes_soumises and action != 'soumettre':
            messages.error(request, "Les notes ont déjà été soumises et ne peuvent plus être modifiées.")
            return redirect('enseignant:noter_examen', classe_id=classe.id, session_id=session_examen.id)
        
        try:
            with transaction.atomic():
                bareme_str = request.POST.get('bareme', '20').replace(',', '.')
                bareme_post = Decimal(bareme_str)
                notes_enregistrees = 0
                
                for eleve in eleves:
                    note_value = request.POST.get(f'note_{eleve.id}', '').strip().replace(',', '.')
                    absent = request.POST.get(f'absent_{eleve.id}') == 'on'
                    commentaire_perso = request.POST.get(f'commentaire_{eleve.id}', '').strip()
                    
                    # Récupérer ou créer la note d'examen
                    note_examen, created = NoteExamen.objects.get_or_create(
                        eleve=eleve,
                        session_examen=session_examen,
                        matiere=professeur.matiere_principale,
                        defaults={
                            'professeur': professeur,
                            'classe': classe,
                            'bareme': bareme_post,
                            'absent': absent
                        }
                    )
                    
                    # Si déjà soumis, ne pas modifier
                    if note_examen.soumis and action != 'soumettre':
                        continue
                    
                    # Mettre à jour si elle existe déjà
                    if not created:
                        note_examen.professeur = professeur
                        note_examen.classe = classe
                        note_examen.bareme = bareme_post
                        note_examen.absent = absent
                    
                    # Enregistrer la note ou marquer absent
                    if absent:
                        note_examen.note = None
                        note_examen.absent = True
                        note_examen.commentaire = commentaire_perso if commentaire_perso else "Absent à l'examen"
                    elif note_value:
                        note_examen.note = Decimal(note_value)
                        note_examen.absent = False
                        # Calculer note_sur_20 pour le commentaire
                        note_sur_20_calc = (note_examen.note / bareme_post) * 20
                        # Utiliser le commentaire personnalisé ou générer automatiquement
                        note_examen.commentaire = commentaire_perso if commentaire_perso else generer_commentaire_auto(note_sur_20_calc)
                    
                    # Si action est "soumettre", marquer comme soumis
                    if action == 'soumettre':
                        note_examen.soumis = True
                        note_examen.date_soumission = timezone.now()
                    
                    note_examen.save()
                    notes_enregistrees += 1
                
                if action == 'soumettre':
                    messages.success(request, f"Notes soumises avec succès ! Les notes sont maintenant verrouillées et ne peuvent plus être modifiées.")
                else:
                    messages.success(request, f"{notes_enregistrees} note(s) d'examen enregistrée(s) avec succès pour {classe.nom} - {professeur.matiere_principale.nom}.")
                
                # Rediriger vers la même page avec les paramètres de période
                from django.urls import reverse
                url = reverse('enseignant:noter_examen_session', kwargs={'classe_id': classe.id, 'session_id': session_examen.id})
                if periode_active:
                    url += f"?periode={periode_active.id}"
                return redirect(url)
                
        except Exception as e:
            messages.error(request, f"Erreur lors de l'enregistrement des notes : {str(e)}")
    
    # Récupérer les notes existantes
    notes_existantes_list = NoteExamen.objects.filter(
        session_examen=session_examen,
        matiere=professeur.matiere_principale,
        classe=classe,
        actif=True
    ).select_related('eleve')
    
    notes_existantes = {note.eleve.id: note for note in notes_existantes_list}
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'session_examen': session_examen,
        'matiere': professeur.matiere_principale,
        'eleves': eleves,
        'bareme': bareme,
        'notes_existantes': notes_existantes,
        'notes_soumises': notes_soumises,
        'periodes_scolaires': periodes_scolaires,
        'periode_active': periode_active or session_examen.periode,
        'sessions_par_periode': dict(sessions_par_periode),
        'toutes_sessions': toutes_sessions,
    }
    
    return render(request, 'school_admin/enseignant/noter_examen.html', context)


def noter_eleves_enseignant(request, classe_id):
    """
    Page pour noter les élèves d'une classe
    Gère les onglets par période (trimestres/semestres)
    """
    logger.info(f"Noter élèves - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.evaluation_model import Evaluation, Note
    from ..model.periode_model import PeriodeScolaire
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    from decimal import Decimal
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer l'ID de la matière si fourni dans l'URL
    matiere_id = request.GET.get('matiere')
    
    # Récupérer l'affectation appropriée
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).select_related('matiere')
    
    # Si une matière est spécifiée, filtrer par cette matière
    if matiere_id:
        affectations = affectations.filter(matiere_id=matiere_id)
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_notes')
    
    # Prendre la première affectation correspondante
    affectation = affectations.first()
    
    # Récupérer toutes les périodes scolaires de l'établissement
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer l'ID de la période sélectionnée (depuis GET ou par défaut la période en cours)
    periode_id = request.GET.get('periode', '')
    periode_active_obj = None
    
    if periode_id:
        try:
            periode_active_obj = periodes_scolaires.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    # Si aucune période sélectionnée, prendre la période en cours ou la première
    if not periode_active_obj:
        # Rechercher la période en cours manuellement (est_en_cours est une propriété)
        for periode in periodes_scolaires:
            if periode.est_en_cours:
                periode_active_obj = periode
                break
        if not periode_active_obj:
            periode_active_obj = periodes_scolaires.first()
    
    # Déterminer la matière enseignée (avant tout usage)
    # Utiliser la matière de l'affectation si elle existe, sinon la matière principale
    matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale

    # Récupérer ou créer le relevé de notes pour cette classe/professeur/matière/période
    from ..model.releve_notes_model import ReleveNotes
    
    if periode_active_obj:
        releve_notes, created = ReleveNotes.objects.get_or_create(
            classe=classe,
            professeur=professeur,
            matiere=matiere_enseignee,
            periode_scolaire=periode_active_obj,
            defaults={
                'etablissement': classe.etablissement,
                'soumis': False
            }
        )
    else:
        # Créer un objet fictif si aucune période
        class FakeReleveNotes:
            soumis = False
        releve_notes = FakeReleveNotes()
    
    # Récupérer les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')

    # Récupérer toutes les évaluations de la classe pour ce professeur pour la période active
    # FILTRER PAR MATIÈRE pour ne prendre que les évaluations de la bonne matière
    if periode_active_obj:
        evaluations_interrogations = list(Evaluation.objects.filter(
            classe=classe,
            professeur=professeur,
            type_evaluation='interrogation',
            periode_scolaire=periode_active_obj,
            actif=True,
            matiere=matiere_enseignee  # Filtrer par matière
        ).order_by('date_evaluation'))
        
        evaluations_devoirs = list(Evaluation.objects.filter(
            classe=classe,
            professeur=professeur,
            type_evaluation__in=['controle', 'devoir_maison'],
            periode_scolaire=periode_active_obj,
            actif=True,
            matiere=matiere_enseignee  # Filtrer par matière
        ).order_by('date_evaluation'))
    else:
        evaluations_interrogations = []
        evaluations_devoirs = []
    
    logger.info(f"Vue noter_eleves - Matière: {matiere_enseignee.nom}, Interrogations: {len(evaluations_interrogations)}, Devoirs: {len(evaluations_devoirs)}")
    
    # Créer la liste complète des évaluations avec leur clé
    evaluations_liste = []
    for i, eval in enumerate(evaluations_interrogations, 1):
        evaluations_liste.append({
            'key': f'interro_{i}',
            'evaluation': eval,
            'type': 'interrogation',
            'index': i,
            'titre_court': f'Interro {i}'
        })
    
    for i, eval in enumerate(evaluations_devoirs, 1):
        evaluations_liste.append({
            'key': f'devoir_{i}',
            'evaluation': eval,
            'type': 'devoir',
            'index': i,
            'titre_court': f'Devoir {i}'
        })
    
    # Garder aussi le mapping pour compatibilité
    evaluations_map = {}
    for item in evaluations_liste:
        evaluations_map[item['key']] = item['evaluation']
    
    # Récupérer les notes existantes pour chaque élève
    notes_existantes = {}
    for eleve in eleves:
        notes_existantes[eleve.id] = {}
        for key, evaluation in evaluations_map.items():
            if evaluation:
                note_obj = Note.objects.filter(eleve=eleve, evaluation=evaluation).first()
                if note_obj:
                    notes_existantes[eleve.id][key] = note_obj.note
    
    # Récupérer les moyennes enregistrées
    from ..model.moyenne_model import Moyenne
    # Récupérer les moyennes enregistrées (APRÈS avoir déterminé matiere_enseignee)
    moyennes_enregistrees = {}
    
    if periode_active_obj:
        # Récupérer les moyennes pour cette période et cette matière spécifique
        # IMPORTANT: Utiliser matiere_enseignee et non professeur.matiere_principale
        moyennes_db = Moyenne.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=matiere_enseignee,  # Utiliser la matière de l'affectation/matière spécifiée
            periode=str(periode_active_obj.id),
            actif=True
        )
        
        for moyenne in moyennes_db:
            moyennes_enregistrees[moyenne.eleve.id] = {
                'moyenne': float(moyenne.moyenne),
                'nombre_notes': moyenne.nombre_notes
            }
        
        logger.info(f"Moyennes chargées pour matière {matiere_enseignee.nom}: {len(moyennes_enregistrees)} pour la période {periode_active_obj.nom_periode}")
    
        # Utiliser la matière de l'affectation si elle existe, sinon la matière principale
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
        
        # Traitement du formulaire POST
        if request.method == 'POST':
            # Vérifier si le relevé est soumis (verrouillé)
            if releve_notes.soumis:
                messages.error(request, "Le relevé de notes a été soumis et ne peut plus être modifié.")
                if matiere_id:
                    return redirect(f'/enseignant/noter/{classe_id}/?matiere={matiere_id}')
                return redirect('enseignant:noter_eleves', classe_id=classe_id)
            
            logger.info(f"POST data: {request.POST}")
            
            # Vérifier qu'au moins une évaluation existe
            if not any(evaluations_map.values()):
                messages.error(request, "Vous devez d'abord créer au moins une évaluation avant de saisir des notes !")
                if matiere_id:
                    return redirect(f'/enseignant/noter/{classe_id}/?matiere={matiere_id}')
                return redirect('enseignant:noter_eleves', classe_id=classe_id)
            
            # Colonnes à traiter pour l'enregistrement des notes
            # Règle demandée: la saisie ne dépend PAS d'une sélection; on enregistre toutes les colonnes présentes
            # On garde la sélection uniquement pour le calcul des moyennes (géré côté JS / endpoint dédié)
            colonnes_selectionnees = [key for key, eval_obj in evaluations_map.items() if eval_obj]
            
            # Validation et enregistrement des notes
            errors = []
            notes_enregistrees = 0
            eleves_avec_notes_modifiees = {}  # Dictionnaire pour suivre les élèves avec notes modifiées
            
            # Vérifier s'il y a une session d'examen pour cette période/classe/matière
            from ..model.session_examen_model import SessionExamen
            from ..model.note_examen_model import NoteExamen
            
            session_examen_post = None
            if periode_active_obj:
                sessions_possibles = SessionExamen.objects.filter(
                    etablissement=professeur.etablissement,
                    classes=classe,
                    matieres=matiere_enseignee,
                    periode=periode_active_obj,
                    actif=True
                ).order_by('-date_debut')
                
                if sessions_possibles.exists():
                    session_examen_post = sessions_possibles.first()
            
            try:
                with transaction.atomic():
                    for eleve in eleves:
                        # Enregistrer les notes des évaluations normales
                        for colonne in colonnes_selectionnees:
                            evaluation = evaluations_map.get(colonne)
                            
                            if not evaluation:
                                errors.append(f"Aucune évaluation programmée pour {colonne.replace('_', ' ').title()}")
                                continue
                            
                            # Récupérer la note saisie
                            note_value = request.POST.get(f'note_{eleve.id}_{colonne}', '').strip()
                            
                            if note_value:
                                try:
                                    note_decimal = Decimal(note_value.replace(',', '.'))
                                    
                                    # Récupérer la matière de l'évaluation (ou de l'affectation)
                                    matiere_note = None
                                    if evaluation and evaluation.matiere:
                                        matiere_note = evaluation.matiere
                                    else:
                                        # Fallback sur la matière de l'affectation
                                        matiere_note = matiere_enseignee
                                    
                                    # Validation : ne pas saisir de notes /20 dans les interrogations
                                    if colonne.startswith('interro') and note_decimal > 10:
                                        errors.append(f"{eleve.nom_complet} : Note trop élevée pour une interrogation (max 10)")
                                        continue
                                    
                                    # Validation : ne pas dépasser le barème
                                    if note_decimal > evaluation.bareme:
                                        errors.append(f"{eleve.nom_complet} : Note supérieure au barème ({evaluation.bareme})")
                                        continue
                                    
                                    # Récupérer la note existante pour vérifier si elle a changé
                                    note_existante = Note.objects.filter(eleve=eleve, evaluation=evaluation).first()
                                    
                                    # Enregistrer ou mettre à jour la note
                                    note_obj, created = Note.objects.update_or_create(
                                        eleve=eleve,
                                        evaluation=evaluation,
                                        defaults={
                                            'note': note_decimal,
                                            'absent': False,
                                            'matiere': matiere_note
                                        }
                                    )
                                    
                                    # Vérifier si la note a réellement changé
                                    note_a_change = (
                                        created or 
                                        (note_existante and note_existante.note != note_decimal) or 
                                        (note_existante and note_existante.absent != False)
                                    )
                                    
                                    if note_a_change:
                                        notes_enregistrees += 1
                                        # Ajouter l'élève à la liste des élèves avec notes modifiées
                                        if eleve not in eleves_avec_notes_modifiees:
                                            eleves_avec_notes_modifiees[eleve] = []
                                        eleves_avec_notes_modifiees[eleve].append({
                                            'type': 'evaluation',
                                            'nom': evaluation.titre,
                                            'note': note_decimal,
                                            'bareme': evaluation.bareme
                                        })

                                        try:
                                            ParentNotificationService.notify_note(
                                                eleve=eleve,
                                                matiere_nom=(matiere_note.nom if matiere_note else matiere_enseignee.nom),
                                                note_obtenue=note_decimal,
                                                bareme=evaluation.bareme,
                                                evaluation_nom=evaluation.titre,
                                                professeur_nom=getattr(professeur, 'nom_complet', str(professeur)),
                                                date_evaluation=getattr(evaluation, 'date_evaluation', None),
                                                source=note_obj,
                                            )
                                        except Exception as notification_error:
                                            logger.error(
                                                "Erreur lors de la notification parent pour la note d'évaluation (collège/lycée): %s",
                                                notification_error,
                                                exc_info=True,
                                            )
                                    
                                except (ValueError, Exception) as e:
                                    logger.error(f"Erreur saisie note pour {eleve.nom_complet}: {str(e)}")
                                    errors.append(f"{eleve.nom_complet} : Valeur invalide")
                        
                        # Enregistrer la note d'examen si une session existe
                        if session_examen_post:
                            note_examen_value = request.POST.get(f'note_examen_{eleve.id}', '').strip()
                            
                            if note_examen_value:
                                try:
                                    note_examen_decimal = Decimal(note_examen_value.replace(',', '.'))
                                    
                                    # Validation : la note d'examen doit être entre 0 et 20
                                    if note_examen_decimal < 0 or note_examen_decimal > 20:
                                        errors.append(f"{eleve.nom_complet} : Note d'examen invalide (doit être entre 0 et 20)")
                                        continue
                                    
                                    # Récupérer la note existante pour vérifier si elle a changé
                                    note_examen_existante = NoteExamen.objects.filter(
                                        eleve=eleve,
                                        session_examen=session_examen_post,
                                        matiere=matiere_enseignee
                                    ).first()
                                    
                                    # Récupérer ou créer la note d'examen
                                    note_examen_obj, created = NoteExamen.objects.get_or_create(
                                        eleve=eleve,
                                        session_examen=session_examen_post,
                                        matiere=matiere_enseignee,
                                        defaults={
                                            'professeur': professeur,
                                            'classe': classe,
                                            'bareme': 20,
                                            'absent': False
                                        }
                                    )
                                    
                                    # Mettre à jour la note
                                    note_examen_obj.note = note_examen_decimal
                                    note_examen_obj.absent = False
                                    note_examen_obj.professeur = professeur
                                    note_examen_obj.classe = classe
                                    
                                    # Calculer note_sur_20
                                    note_examen_obj.note_sur_20 = note_examen_decimal  # Déjà sur 20
                                    note_examen_obj.save()
                                    
                                    # Vérifier si la note a réellement changé
                                    note_a_change = (
                                        created or 
                                        (note_examen_existante and note_examen_existante.note != note_examen_decimal) or 
                                        (note_examen_existante and note_examen_existante.absent != False)
                                    )
                                    
                                    if note_a_change:
                                        notes_enregistrees += 1
                                        # Ajouter l'élève à la liste des élèves avec notes modifiées
                                        if eleve not in eleves_avec_notes_modifiees:
                                            eleves_avec_notes_modifiees[eleve] = []
                                        eleves_avec_notes_modifiees[eleve].append({
                                            'type': 'examen',
                                            'nom': session_examen_post.titre,
                                            'note': note_examen_decimal,
                                            'bareme': 20
                                        })

                                        try:
                                            ParentNotificationService.notify_note(
                                                eleve=eleve,
                                                matiere_nom=matiere_enseignee.nom,
                                                note_obtenue=note_examen_decimal,
                                                bareme=getattr(note_examen_obj, 'bareme', 20),
                                                evaluation_nom=getattr(
                                                    session_examen_post,
                                                    'titre',
                                                    getattr(session_examen_post, 'nom_examen', 'Examen'),
                                                ),
                                                professeur_nom=getattr(professeur, 'nom_complet', str(professeur)),
                                                date_evaluation=getattr(session_examen_post, 'date_debut', None),
                                                source=note_examen_obj,
                                            )
                                        except Exception as notification_error:
                                            logger.error(
                                                "Erreur lors de la notification parent pour la note d'examen (collège/lycée): %s",
                                                notification_error,
                                                exc_info=True,
                                            )
                                    
                                except (ValueError, Exception) as e:
                                    logger.error(f"Erreur saisie note d'examen pour {eleve.nom_complet}: {str(e)}")
                                    errors.append(f"{eleve.nom_complet} : Valeur invalide pour la note d'examen")
                    
                    if errors:
                        messages.warning(request, f"{notes_enregistrees} notes enregistrées. Erreurs : " + " | ".join(errors[:5]))
                    else:
                        messages.success(request, f"✓ {notes_enregistrees} notes enregistrées avec succès !")
                    
                    # Envoyer des notifications push aux élèves dont les notes ont été modifiées
                    if eleves_avec_notes_modifiees:
                        try:
                            from school_admin.services.firebase_service import FirebaseService
                            
                            for eleve, notes_modifiees in eleves_avec_notes_modifiees.items():
                                # Construire le message personnalisé pour cet élève
                                if len(notes_modifiees) == 1:
                                    note_info = notes_modifiees[0]
                                    title = f"📚 Nouvelle note - {matiere_enseignee.nom}"
                                    body = f"Vous avez {note_info['note']}/{note_info['bareme']} pour {note_info['nom']}"
                                else:
                                    title = f"📚 {len(notes_modifiees)} nouvelles notes - {matiere_enseignee.nom}"
                                    notes_texte = ", ".join([f"{n['note']}/{n['bareme']}" for n in notes_modifiees[:2]])
                                    body = f"Nouvelles notes: {notes_texte}..."
                                
                                data = {
                                    'type': 'notes',
                                    'matiere_id': str(matiere_enseignee.id),
                                    'matiere_nom': matiere_enseignee.nom,
                                    'classe_id': str(classe.id),
                                    'url': '/eleve/notes-evaluations/'
                                }
                                
                                # Envoyer la notification à cet élève spécifique
                                result = FirebaseService.send_notification_to_multiple_users(
                                    [eleve], title, body, data
                                )
                                
                                if result['success_count'] > 0:
                                    logger.info(f"Notification envoyée à {eleve.nom_complet} : {body}")
                                    
                                try:
                                    EleveNotificationService.notify_note(
                                        eleve=eleve,
                                        matiere_nom=matiere_enseignee.nom,
                                        details={
                                            "message": body,
                                            "notes": notes_modifiees,
                                        },
                                        source=None,
                                    )
                                except Exception:
                                    logger.exception(
                                        "Échec notification élève %s pour note",
                                        getattr(eleve, "id", "N/A"),
                                    )
                        
                        except Exception as e:
                            logger.error(f"Erreur lors de l'envoi des notifications: {str(e)}")
                    
            except Exception as e:
                logger.error(f"Erreur transaction notes: {str(e)}")
                messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
            
            if matiere_id:
                return redirect(f'/enseignant/noter/{classe_id}/?matiere={matiere_id}')
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
    
    # Compter le nombre de notes retenues pour chaque évaluation
    notes_retenues_par_eval = {}
    for item in evaluations_liste:
        evaluation = item['evaluation']
        # Compter les notes retenues pour cette évaluation (non absentes, avec une note, et retenue=True)
        nb_retenues = Note.objects.filter(
            evaluation=evaluation,
            retenue=True,
            absent=False
        ).exclude(note__isnull=True).count()
        notes_retenues_par_eval[item['key']] = nb_retenues
    
    # Récupérer la session d'examen pour cette période/classe/matière
    from ..model.session_examen_model import SessionExamen
    from ..model.note_examen_model import NoteExamen
    
    session_examen = None
    notes_examen_par_eleve = {}
    
    if periode_active_obj:
        # Récupérer toutes les sessions pour cette période/classe/matière
        sessions_possibles = SessionExamen.objects.filter(
            etablissement=professeur.etablissement,
            classes=classe,
            matieres=matiere_enseignee,
            periode=periode_active_obj,
            actif=True
        ).order_by('-date_debut')
        
        # Prioriser la session qui a déjà des notes enregistrées
        for session in sessions_possibles:
            notes_count = NoteExamen.objects.filter(
                session_examen=session,
                matiere=matiere_enseignee,
                classe=classe,
                actif=True
            ).count()
            if notes_count > 0:
                session_examen = session
                break
        
        # Si aucune session avec notes, prendre la première
        if not session_examen and sessions_possibles.exists():
            session_examen = sessions_possibles.first()
        
        # Récupérer les notes d'examen pour chaque élève
        if session_examen:
            for eleve in eleves:
                note_examen = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session_examen,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                ).first()
                notes_examen_par_eleve[eleve.id] = note_examen
    
    # Calculer le nombre total d'évaluations (incluant l'examen si présent)
    total_evaluations_count = len(evaluations_liste)
    if session_examen:
        total_evaluations_count += 1
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'eleves': eleves,
        'matiere': matiere_enseignee,
        'evaluations_map': evaluations_map,
        'evaluations_liste': evaluations_liste,
        'evaluations_interrogations': evaluations_interrogations,
        'evaluations_devoirs': evaluations_devoirs,
        'notes_existantes': notes_existantes,
        'moyennes_enregistrees': moyennes_enregistrees,
        'has_evaluations': len(evaluations_liste) > 0,
        'releve_notes': releve_notes,
        'periode_active': periode_active_obj,
        'periodes_scolaires': periodes_scolaires,
        'notes_retenues_par_eval': notes_retenues_par_eval,
        'session_examen': session_examen,
        'notes_examen_par_eleve': notes_examen_par_eleve,
        'total_evaluations_count': total_evaluations_count,
    }
    
    return render(request, 'school_admin/enseignant/noter_eleves.html', context)


def creer_evaluation_enseignant(request, classe_id):
    """
    Page pour créer une nouvelle évaluation pour une classe
    """
    logger.info(f"Créer évaluation - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.evaluation_model import Evaluation
    from ..model.periode_model import PeriodeScolaire
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer l'ID de la matière si fourni dans l'URL
    matiere_id = request.GET.get('matiere')
    
    # Récupérer l'affectation appropriée
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).select_related('matiere')
    
    # Si une matière est spécifiée, filtrer par cette matière
    if matiere_id:
        affectations = affectations.filter(matiere_id=matiere_id)
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_notes')
    
    # Prendre la première affectation correspondante
    affectation = affectations.first()
    
    # Déterminer la matière à utiliser : celle de l'affectation si elle existe, sinon la matière principale
    matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
    
    # Traitement du formulaire POST
    if request.method == 'POST':
        logger.info(f"POST data: {request.POST}")
        
        # Validation des données
        errors = {}
        form_data = {}
        
        # Récupérer les données du formulaire
        titre = request.POST.get('titre', '').strip()
        description = request.POST.get('description', '').strip()
        type_evaluation = request.POST.get('type_evaluation', 'controle')
        date_evaluation = request.POST.get('date_evaluation', '')
        bareme = request.POST.get('bareme', '20')
        duree = request.POST.get('duree', '')
        periode_scolaire_id = request.POST.get('periode_scolaire', '')
        
        # Validation
        if not titre:
            errors['titre'] = "Le titre est obligatoire."
        if not date_evaluation:
            errors['date_evaluation'] = "La date est obligatoire."
        
        # Valider la période scolaire
        periode_scolaire = None
        if periode_scolaire_id:
            try:
                periode_scolaire = PeriodeScolaire.objects.get(id=periode_scolaire_id, etablissement=professeur.etablissement)
            except PeriodeScolaire.DoesNotExist:
                errors['periode_scolaire'] = "Période scolaire invalide."
        
        try:
            bareme_float = float(bareme)
            if bareme_float <= 0:
                errors['bareme'] = "Le barème doit être supérieur à 0."
        except ValueError:
            errors['bareme'] = "Le barème doit être un nombre valide."
        
        if duree:
            try:
                duree_int = int(duree)
                if duree_int <= 0:
                    errors['duree'] = "La durée doit être supérieure à 0."
            except ValueError:
                errors['duree'] = "La durée doit être un nombre entier."
        
        # Si pas d'erreurs, créer l'évaluation
        if not errors:
            try:
                with transaction.atomic():
                    # Utiliser la matière depuis le POST si fournie, sinon celle de l'affectation
                    matiere_id_post = request.POST.get('matiere')
                    if matiere_id_post:
                        try:
                            from ..model.matiere_model import Matiere
                            matiere_enseignee = Matiere.objects.get(id=matiere_id_post)
                        except Matiere.DoesNotExist:
                            matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
                    else:
                        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
                    
                    evaluation = Evaluation.objects.create(
                        titre=titre,
                        description=description,
                        type_evaluation=type_evaluation,
                        classe=classe,
                        professeur=professeur,
                        matiere=matiere_enseignee,
                        date_evaluation=date_evaluation,
                        bareme=bareme_float,
                        periode_scolaire=periode_scolaire,
                        duree=int(duree) if duree else None,
                        actif=True
                    )
                    
                    logger.info(f"Évaluation créée: {evaluation.id} - {evaluation.titre}")
                    messages.success(request, f"L'évaluation '{evaluation.titre}' a été créée avec succès !")
                    if matiere_id:
                        return redirect(f"/enseignant/notes/?matiere={matiere_id}")
                    return redirect('enseignant:gestion_notes')
                    
            except Exception as e:
                logger.error(f"Erreur lors de la création de l'évaluation: {str(e)}")
                errors['general'] = f"Erreur lors de la création de l'évaluation : {str(e)}"
        
        # Stocker les erreurs et les données dans le contexte
        periodes_scolaires = PeriodeScolaire.objects.filter(
            etablissement=professeur.etablissement,
            est_active=True
        ).order_by('date_debut')
        
        # Compter le nombre d'élèves actifs dans la classe
        from ..model.eleve_model import Eleve
        nombre_eleves = Eleve.objects.filter(classe=classe, actif=True).count()
        
        context = {
            'professeur': professeur,
            'classe': classe,
            'affectation': affectation,
            'matiere': matiere_enseignee,
            'nombre_eleves': nombre_eleves,
            'periodes_scolaires': periodes_scolaires,
            'errors': errors,
            'form_data': request.POST,
        }
        
        return render(request, 'school_admin/enseignant/creer_evaluation.html', context)
    
    # GET request
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Compter le nombre d'élèves actifs dans la classe
    from ..model.eleve_model import Eleve
    nombre_eleves = Eleve.objects.filter(classe=classe, actif=True).count()
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'matiere': matiere_enseignee,
        'nombre_eleves': nombre_eleves,
        'periodes_scolaires': periodes_scolaires,
        'errors': {},
        'form_data': {},
    }
    
    return render(request, 'school_admin/enseignant/creer_evaluation.html', context)


def liste_evaluations_enseignant(request):
    """
    Page pour afficher toutes les évaluations programmées de l'enseignant
    Filtrées par matière selon l'affectation et regroupées par période
    """
    logger.info(f"Liste évaluations - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.evaluation_model import Evaluation
    from ..model.affectation_model import AffectationProfesseur
    from ..model.periode_model import PeriodeScolaire
    import re
    
    # Récupérer toutes les périodes scolaires actives
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Période sélectionnée (None si "Toutes" est sélectionnée)
    periode_id = request.GET.get('periode', '')
    periode_active = None
    
    # Si "toutes" est spécifié, on ne filtre pas par période (periode_active reste None)
    if periode_id == 'toutes':
        periode_active = None
    # Si une période ID est spécifiée, la récupérer
    elif periode_id:
        try:
            periode_active = periodes_scolaires.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    # Sinon, si aucune période n'est spécifiée, utiliser la période en cours par défaut
    elif periodes_scolaires.exists():
        for periode in periodes_scolaires:
            if periode.est_en_cours:
                periode_active = periode
                break
        if not periode_active:
            periode_active = periodes_scolaires.first()
    
    # Récupérer les affectations avec les matières
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe', 'matiere').order_by('classe__nom')
    
    # Regrouper les évaluations par catégorie de classe ET par période
    evaluations_grouped = {}
    
    for affectation in affectations:
        classe = affectation.classe
        matiere_affectation = affectation.matiere if affectation.matiere else professeur.matiere_principale
        
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        if match:
            categorie = match.group(1)
        else:
            categorie = nom
        
        if categorie not in evaluations_grouped:
            evaluations_grouped[categorie] = {
                'classes': [],
            }
        
        # Récupérer les évaluations de cette classe et cette matière
        evals_query = Evaluation.objects.filter(
            professeur=professeur,
            classe=classe,
            actif=True
        )
        
        # Filtrer par matière si spécifiée dans l'évaluation
        if matiere_affectation:
            evals_query = evals_query.filter(matiere=matiere_affectation)
        
        # Filtrer par période si une période est sélectionnée
        if periode_active:
            evals_query = evals_query.filter(periode_scolaire=periode_active)
        
        evals_classe = evals_query.select_related('matiere', 'periode_scolaire').order_by('-date_evaluation')
        
        classe_data = {
            'classe': classe,
            'matiere': matiere_affectation,
            'evaluations': evals_classe,
            'nombre_evaluations': evals_classe.count(),
            'affectation': affectation,
        }
        
        evaluations_grouped[categorie]['classes'].append(classe_data)
    
    # Calculer les statistiques globales
    toutes_evaluations = Evaluation.objects.filter(
        professeur=professeur,
        actif=True
    )
    
    if periode_active:
        toutes_evaluations = toutes_evaluations.filter(periode_scolaire=periode_active)
    
    stats = {
        'total_evaluations': toutes_evaluations.count(),
        'total_classes': affectations.count(),
    }
    
    context = {
        'professeur': professeur,
        'evaluations_grouped': evaluations_grouped,
        'stats': stats,
        'matiere_principale': professeur.matiere_principale,
        'periodes_scolaires': periodes_scolaires,
        'periode_active': periode_active,
    }
    
    return render(request, 'school_admin/enseignant/liste_evaluations.html', context)


def calculer_moyennes_classe(request, classe_id):
    """
    Calcule et enregistre les moyennes de tous les élèves d'une classe
    Utilise uniquement les colonnes sélectionnées par l'enseignant
    """
    logger.info(f"Calcul moyennes - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        return JsonResponse({'success': False, 'error': 'Accès non autorisé'}, status=403)
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.evaluation_model import Evaluation, Note
    from ..model.moyenne_model import Moyenne
    from django.shortcuts import get_object_or_404
    from django.http import JsonResponse
    from django.db import transaction
    from decimal import Decimal
    import json
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer l'affectation (peut y en avoir plusieurs si plusieurs matières)
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).select_related('matiere')
    
    if not affectations.exists():
        return JsonResponse({'success': False, 'error': 'Vous n\'êtes pas affecté à cette classe.'}, status=403)
    
    # Permettre de cibler la bonne matière si fournie par le frontend
    matiere_id_body = None
    try:
        body_peek = json.loads(request.body) if request.body else {}
        matiere_id_body = body_peek.get('matiere')
    except Exception:
        matiere_id_body = None

    if matiere_id_body:
        affectations = affectations.filter(matiere_id=matiere_id_body)
    affectation = affectations.first()
    matiere_enseignee = affectation.matiere if affectation and affectation.matiere else professeur.matiere_principale
    
    # Récupérer les colonnes sélectionnées et la période depuis la requête
    try:
        body = json.loads(request.body) if request.body else {}
        colonnes_selectionnees = body.get('colonnes_selectionnees', [])
        periode_id = body.get('periode', '')
        nombre_meilleures_notes = body.get('nombre_meilleures_notes', 'toutes')  # 'toutes', '2', '3', etc.
        # si la matière arrive ici également, synchroniser
        if body.get('matiere') and not matiere_id_body:
            matiere_id_body = body.get('matiere')
    except:
        colonnes_selectionnees = []
        periode_id = ''
        nombre_meilleures_notes = 'toutes'
    
    logger.info(f"Colonnes sélectionnées: {colonnes_selectionnees}, Période ID: {periode_id}, Meilleures notes: {nombre_meilleures_notes}")
    
    # Si aucune colonne sélectionnée, retourner une erreur
    if not colonnes_selectionnees:
        return JsonResponse({
            'success': False,
            'error': 'Veuillez sélectionner au moins une colonne pour calculer les moyennes'
        }, status=400)
    
    # Récupérer la période scolaire
    from ..model.periode_model import PeriodeScolaire
    periode_active = None
    if periode_id:
        try:
            periode_active = PeriodeScolaire.objects.get(id=periode_id, etablissement=professeur.etablissement)
        except PeriodeScolaire.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Période scolaire invalide'
            }, status=400)
    
    # Récupérer les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True)
    
    # Mapper les évaluations pour la période (même logique que dans noter_eleves_enseignant)
    evaluations_interrogations = list(Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        type_evaluation='interrogation',
        periode_scolaire=periode_active,
        actif=True
    ).order_by('date_evaluation'))
    
    evaluations_devoirs = list(Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        type_evaluation__in=['controle', 'devoir_maison'],
        periode_scolaire=periode_active,
        actif=True
    ).order_by('date_evaluation'))
    
    # Filtrer par matière pour s'assurer qu'on ne prend que les bonnes évaluations
    evaluations_interrogations = [e for e in evaluations_interrogations if e.matiere == matiere_enseignee]
    evaluations_devoirs = [e for e in evaluations_devoirs if e.matiere == matiere_enseignee]
    
    # Créer les clés de la même manière que dans noter_eleves_enseignant
    # IMPORTANT : L'ordre et le numérotage doivent être identiques
    evaluations_liste = []
    for i, eval in enumerate(evaluations_interrogations, 1):
        evaluations_liste.append({
            'key': f'interro_{i}',
            'evaluation': eval,
            'type': 'interrogation',
        })
    
    for i, eval in enumerate(evaluations_devoirs, 1):
        evaluations_liste.append({
            'key': f'devoir_{i}',
            'evaluation': eval,
            'type': 'devoir',
        })
    
    # Créer le mapping key -> evaluation
    evaluations_map = {}
    for item in evaluations_liste:
        evaluations_map[item['key']] = item['evaluation']
    
    logger.info(f"Évaluations filtrées - Interrogations: {len(evaluations_interrogations)}, Devoirs: {len(evaluations_devoirs)}")
    logger.info(f"Clés générées: {[item['key'] for item in evaluations_liste]}")
    logger.info(f"Colonnes sélectionnées reçues: {colonnes_selectionnees}")
    
    # Récupérer automatiquement la session d'examen si elle existe (incluse par défaut dans le calcul)
    session_examen = None
    from ..model.session_examen_model import SessionExamen
    from ..model.note_examen_model import NoteExamen
    
    # Chercher les sessions d'examen possibles pour cette classe, matière et période
    # Ne chercher que si la période est définie
    if periode_active:
        sessions_possibles = SessionExamen.objects.filter(
            etablissement=professeur.etablissement,
            classes=classe,
            matieres=matiere_enseignee,
            periode=periode_active,
            actif=True
        ).order_by('-date_debut')
        
        # Prioriser une session qui a déjà des notes enregistrées
        if sessions_possibles.exists():
            for session in sessions_possibles:
                notes_count = NoteExamen.objects.filter(
                    session_examen=session,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                ).count()
                if notes_count > 0:
                    session_examen = session
                    break
            
            # Si aucune session avec notes, prendre la première
            if not session_examen:
                session_examen = sessions_possibles.first()
            
            logger.info(f"Session d'examen trouvée: {session_examen.id if session_examen else None}")
    
    moyennes_calculees = []
    
    try:
        with transaction.atomic():
            for eleve in eleves:
                # Récupérer uniquement les notes des colonnes sélectionnées
                evaluations_selectionnees = []
                colonnes_evaluations = [c for c in colonnes_selectionnees if not c.startswith('examen_')]
                for colonne in colonnes_evaluations:
                    evaluation = evaluations_map.get(colonne)
                    if evaluation:
                        evaluations_selectionnees.append(evaluation)
                
                # Si aucune évaluation normale et pas d'examen, on passe
                if not evaluations_selectionnees and not session_examen:
                    continue
                
                # Récupérer les notes pour ces évaluations
                # IMPORTANT : Filtrer aussi par matière pour éviter les notes d'autres matières
                notes = Note.objects.filter(
                    eleve=eleve,
                    evaluation__in=evaluations_selectionnees,
                    absent=False,
                    matiere=matiere_enseignee  # Filtrer par matière
                ).select_related('evaluation') if evaluations_selectionnees else Note.objects.none()
                
                logger.info(f"Notes trouvées pour {eleve.nom_complet}: {notes.count()}")
                for note in notes:
                    logger.info(f"  - Évaluation: {note.evaluation.titre}, Note: {note.note}/{note.evaluation.bareme}")
                
                # Récupérer automatiquement la note d'examen si elle existe (incluse par défaut)
                note_examen = None
                if session_examen:
                    note_examen = NoteExamen.objects.filter(
                        eleve=eleve,
                        session_examen=session_examen,
                        matiere=matiere_enseignee,
                        classe=classe,
                        absent=False,
                        actif=True
                    ).first()
                    if note_examen and note_examen.note:
                        logger.info(f"Note d'examen trouvée pour {eleve.nom_complet}: {note_examen.note}/20 (inclus automatiquement)")
                    elif note_examen:
                        logger.warning(f"Note d'examen trouvée pour {eleve.nom_complet} mais sans note (absent?)")
                
                # Séparer les interrogations et les devoirs
                notes_interrogations = []
                notes_devoirs = []
                
                for note in notes:
                    # Vérifier que la note existe et n'est pas None
                    if note.note is None:
                        logger.warning(f"Note None pour {eleve.nom_complet} - Évaluation {note.evaluation.titre}")
                        continue
                    
                    note_sur_20 = (float(note.note) / float(note.evaluation.bareme)) * 20
                    note_data = {
                        'note_sur_20': note_sur_20,
                        'evaluation_id': note.evaluation.id,
                        'note_originale': float(note.note),
                        'bareme': float(note.evaluation.bareme),
                        'type': note.evaluation.type_evaluation,
                        'evaluation_titre': note.evaluation.titre
                    }
                    
                    logger.info(f"Note convertie pour {eleve.nom_complet}: {note.note}/{note.evaluation.bareme} = {note_sur_20:.2f}/20")
                    
                    if note.evaluation.type_evaluation == 'interrogation':
                        notes_interrogations.append(note_data)
                    else:
                        notes_devoirs.append(note_data)
                
                # Si aucune note normale et pas de note d'examen, on passe
                if notes.count() == 0 and (not note_examen or not note_examen.note):
                    logger.warning(f"Aucune note trouvée pour {eleve.nom_complet} dans les évaluations sélectionnées")
                    continue
                
                # Nouveau calcul demandé: moyenne des meilleures notes continues,
                # puis moyenne finale = (moyenne_continu + note_examen) / 2 si examen existe
                evaluations_retenues_ids = []
                # Construire la liste des notes continues (évaluations sélectionnées, ramenées sur 20)
                notes_continues = []
                for note in notes:
                    if note.note is None:
                        continue
                    note_sur_20 = (float(note.note) / float(note.evaluation.bareme)) * 20
                    notes_continues.append({
                        'note_sur_20': note_sur_20,
                        'evaluation_id': note.evaluation.id,
                    })

                # Sélection des meilleures notes continues si demandé
                notes_continues_triees = sorted(notes_continues, key=lambda x: x['note_sur_20'], reverse=True)
                if nombre_meilleures_notes.isdigit():
                    k = int(nombre_meilleures_notes)
                    selection_continues = notes_continues_triees[:k] if k > 0 else []
                else:
                    selection_continues = notes_continues_triees  # toutes

                # Marquer les évaluations retenues
                evaluations_retenues_ids = [n['evaluation_id'] for n in selection_continues]

                # Moyenne du continu
                if selection_continues:
                    moyenne_continu = sum(n['note_sur_20'] for n in selection_continues) / len(selection_continues)
                else:
                    moyenne_continu = 0

                # Intégration de la note d'examen (si existe) selon la règle: (continu + examen)/2
                if note_examen and note_examen.note is not None:
                    moyenne_calculee = (moyenne_continu + float(note_examen.note)) / 2
                    logger.info(f"{eleve.nom_complet}: moyenne_continu={moyenne_continu:.2f}, examen={float(note_examen.note):.2f} -> finale={moyenne_calculee:.2f}")
                else:
                    moyenne_calculee = moyenne_continu
                    logger.info(f"{eleve.nom_complet}: moyenne_continu={moyenne_continu:.2f} (pas d'examen) -> finale={moyenne_calculee:.2f}")
                
                # ÉTAPE IMPORTANTE : Réinitialiser toutes les notes CONTINUES de cet élève (toutes évaluations de la matière) à retenue=False
                Note.objects.filter(
                    eleve=eleve,
                    matiere=matiere_enseignee
                ).update(retenue=False)
                
                # Marquer les notes retenues comme retenue=True
                # (evaluations_retenues_ids est déjà collecté dans le code ci-dessus)
                if evaluations_retenues_ids:
                    Note.objects.filter(
                        eleve=eleve,
                        evaluation_id__in=evaluations_retenues_ids,
                        absent=False
                    ).exclude(note__isnull=True).update(retenue=True)
                
                # Préparer les détails des notes pour affichage simplifié (UNIQUEMENT les continues retenues)
                details_notes_eleve = []
                for idx, n in enumerate(selection_continues, start=1):
                    details_notes_eleve.append({
                        'titre': f"Note {idx}",
                        'note': round(n['note_sur_20'], 2),
                        'bareme': 20,
                        'evaluations_ids': [n['evaluation_id']],
                        'type': 'continue'
                    })
                
                # Enregistrer ou mettre à jour la moyenne pour la période
                # Note: Le modèle Moyenne utilise encore l'ancien système (periode string)
                # On stocke l'ID de la période en string en attendant la migration
                moyenne_obj, created = Moyenne.objects.update_or_create(
                    eleve=eleve,
                    classe=classe,
                    matiere=matiere_enseignee,
                    periode=str(periode_id) if periode_id else 'trimestre1',
                    defaults={
                        'professeur': professeur,
                        'moyenne': Decimal(str(round(moyenne_calculee, 2))),
                        'nombre_notes': (len(selection_continues) + (1 if (note_examen and note_examen.note is not None) else 0)),
                        'mode_calcul': nombre_meilleures_notes,
                        'evaluations_utilisees': evaluations_retenues_ids,
                        'details_notes': details_notes_eleve,
                        'actif': True
                    }
                )
                
                moyennes_calculees.append({
                    'eleve_id': eleve.id,
                    'eleve_nom': eleve.nom_complet,
                    'moyenne': float(moyenne_obj.moyenne),
                    'nombre_notes': moyenne_obj.nombre_notes,
                    'created': created
                })
                
                try:
                    ParentNotificationService.notify_moyenne(
                        eleve=eleve,
                        moyenne_obtenue=moyenne_obj.moyenne,
                        matiere_nom=matiere_enseignee.nom,
                        periode_nom=getattr(periode_active_obj, 'nom_periode', None),
                        source=moyenne_obj,
                    )
                except Exception as notification_error:
                    logger.error(
                        "Erreur lors de la notification parent pour la moyenne (collège/lycée): %s",
                        notification_error,
                        exc_info=True,
                    )

                logger.info(f"Moyenne calculée pour {eleve.nom_complet}: {moyenne_obj.moyenne}/20 ({notes.count()} notes) - Colonnes: {colonnes_selectionnees}")
        
        # Compter les notes retenues par évaluation pour la mise à jour de l'affichage
        notes_retenues_par_eval = {}
        for item_key in colonnes_selectionnees:
            evaluation = evaluations_map.get(item_key)
            if evaluation:
                nb_retenues = Note.objects.filter(
                    evaluation=evaluation,
                    retenue=True,
                    absent=False
                ).exclude(note__isnull=True).count()
                notes_retenues_par_eval[item_key] = nb_retenues
        
        # Ajouter automatiquement le comptage de l'examen si une session d'examen existe
        if session_examen:
            # Forcer l'examen à "Retenue" côté interface: on renvoie un compteur positif
            # afin que tout script d'UI l'affiche comme retenu par défaut
            examen_key = f'examen_{session_examen.id}'
            notes_retenues_par_eval[examen_key] = eleves.count() or 1
        
        # Envoyer des notifications push aux élèves pour les informer de leurs moyennes
        if len(moyennes_calculees) > 0:
            try:
                from school_admin.services.firebase_service import FirebaseService
                
                # Envoyer une notification personnalisée à chaque élève avec sa moyenne
                for moyenne_info in moyennes_calculees:
                    try:
                        eleve = Eleve.objects.get(id=moyenne_info['eleve_id'])
                        moyenne_val = moyenne_info['moyenne']
                        
                        # Message personnalisé avec la moyenne de l'élève
                        title = f"📊 Moyenne disponible - {matiere_enseignee.nom}"
                        body = f"Vous avez {moyenne_val:.2f}/20 de moyenne en {matiere_enseignee.nom}"
                        data = {
                            'type': 'moyenne',
                            'matiere_id': str(matiere_enseignee.id),
                            'matiere_nom': matiere_enseignee.nom,
                            'classe_id': str(classe.id),
                            'moyenne': str(moyenne_val),
                            'url': '/eleve/notes-evaluations/'
                        }
                        
                        # Envoyer la notification à cet élève spécifique
                        result = FirebaseService.send_notification_to_multiple_users(
                            [eleve], title, body, data
                        )
                        
                        if result['success_count'] > 0:
                            logger.info(f"Notification de moyenne envoyée à {eleve.nom_complet} : {moyenne_val:.2f}/20")
                            
                        try:
                            EleveNotificationService.notify_note(
                                eleve=eleve,
                                matiere_nom=matiere_enseignee.nom,
                                details={
                                    "message": body,
                                    "moyenne": moyenne_val,
                                },
                                source=None,
                            )
                        except Exception:
                            logger.exception(
                                "Échec notification élève %s pour moyenne",
                                getattr(eleve, "id", "N/A"),
                            )
                        
                    except Eleve.DoesNotExist:
                        logger.error(f"Élève {moyenne_info['eleve_id']} non trouvé pour l'envoi de notification")
                    except Exception as e:
                        logger.error(f"Erreur lors de l'envoi de notification à l'élève {moyenne_info['eleve_id']}: {str(e)}")
                        
            except Exception as e:
                logger.error(f"Erreur générale lors de l'envoi des notifications de moyennes: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'moyennes': moyennes_calculees,
            'total_eleves': len(moyennes_calculees),
            'colonnes_utilisees': colonnes_selectionnees,
            'notes_retenues': notes_retenues_par_eval,
            'message': f'{len(moyennes_calculees)} moyenne(s) calculée(s) avec {len(colonnes_selectionnees)} colonne(s) sélectionnée(s) !'
        })
        
    except Exception as e:
        logger.error(f"Erreur calcul moyennes: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors du calcul : {str(e)}'
        }, status=500)


def soumettre_releve_notes(request, classe_id):
    """
    Soumet le relevé de notes (verrouillage définitif)
    """
    logger.info(f"Soumission relevé - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.releve_notes_model import ReleveNotes
    from ..model.periode_model import PeriodeScolaire
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    
    # Vérifier que la classe existe
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer la période et la matière depuis les paramètres
    periode_id = request.GET.get('periode', '')
    matiere_id = request.GET.get('matiere', '')
    
    # Récupérer le relevé de notes
    try:
        if periode_id:
            periode_active = PeriodeScolaire.objects.get(id=periode_id, etablissement=professeur.etablissement)
            # Déterminer la matière à soumettre
            from ..model.matiere_model import Matiere
            matiere_submit = None
            if matiere_id:
                matiere_submit = Matiere.objects.filter(id=matiere_id, etablissement=professeur.etablissement).first()
            # Rechercher l'affectation correspondante (le prof peut avoir plusieurs matières dans la même classe)
            affectation_qs = AffectationProfesseur.objects.filter(
                professeur=professeur,
                classe=classe,
                actif=True
            )
            if matiere_submit:
                affectation_qs = affectation_qs.filter(matiere=matiere_submit)
            affectation = affectation_qs.first()
            if not affectation:
                messages.error(request, "Affectation introuvable pour cette classe/matière.")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({'success': False, 'error': 'Affectation introuvable'}, status=404)
                return redirect('enseignant:gestion_notes')
            if not matiere_submit:
                # fallback sur l'affectation trouvée
                matiere_submit = affectation.matiere if getattr(affectation, 'matiere', None) else professeur.matiere_principale
            # Récupérer ou créer le relevé (assure l'existence même si non créé via autre écran)
            releve_notes, _created = ReleveNotes.objects.get_or_create(
                classe=classe,
                professeur=professeur,
                matiere=matiere_submit,
                periode_scolaire=periode_active,
                defaults={
                    'etablissement': professeur.etablissement,
                    'soumis': False,
                    'actif': True,
                }
            )
        else:
            messages.error(request, "Veuillez sélectionner une période.")
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
        
        if releve_notes.soumis:
            messages.warning(request, "Ce relevé de notes a déjà été soumis.")
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
        
        # Soumettre le relevé
        releve_notes.soumettre()

        # Marquer les moyennes de la période comme soumises pour la classe/matière
        from ..model.moyenne_model import Moyenne
        Moyenne.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=matiere_submit,
            periode=str(periode_active.id),
            actif=True
        ).update(soumis=True)
        
        logger.info(f"Relevé soumis - Classe: {classe.nom}, Période: {periode_active.nom_periode}, Professeur: {professeur.nom_complet}")
        success_msg = f"✓ Relevé de notes soumis avec succès pour {periode_active.nom_periode} ! Les notes sont maintenant verrouillées."
        
        try:
            DirecteurNotificationService.notify_releve_submission(
                classe=classe,
                professeur=professeur,
                periode=periode_active,
                matieres=[matiere_submit.nom if matiere_submit else None],
                source=releve_notes,
            )
        except Exception as notification_error:
            logger.error(
                "Erreur lors de la notification directeur pour le relevé soumis: %s",
                notification_error,
                exc_info=True,
            )
        
        # Si appel AJAX, renvoyer JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': True, 'message': success_msg})
        messages.success(request, success_msg)
        
    except PeriodeScolaire.DoesNotExist:
        messages.error(request, "Période scolaire introuvable.")
    except ReleveNotes.DoesNotExist:
        messages.error(request, "Relevé de notes introuvable pour cette période.")
    except Exception as e:
        logger.error(f"Erreur soumission relevé: {str(e)}")
        messages.error(request, f"Erreur lors de la soumission : {str(e)}")
    
    # Rediriger en conservant la période (flux non-AJAX)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({'success': False, 'error': 'Erreur lors de la soumission'}, status=400)
    if periode_id:
        return redirect(f'/enseignant/noter/{classe_id}/?periode={periode_id}')
    return redirect('enseignant:noter_eleves', classe_id=classe_id)


def voir_releve_notes(request, classe_id):
    """
    Page pour afficher le relevé de notes d'une classe pour une période donnée
    """
    logger.info(f"Voir relevé - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.evaluation_model import Evaluation, Note
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.releve_notes_model import ReleveNotes
    from django.shortcuts import get_object_or_404
    from decimal import Decimal
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    affectation = get_object_or_404(
        AffectationProfesseur,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Récupérer toutes les périodes scolaires
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer la période sélectionnée
    periode_id = request.GET.get('periode', '')
    periode_active_obj = None
    
    if periode_id:
        try:
            periode_active_obj = periodes_scolaires.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    if not periode_active_obj:
        for periode in periodes_scolaires:
            if periode.est_en_cours:
                periode_active_obj = periode
                break
        if not periode_active_obj:
            periode_active_obj = periodes_scolaires.first()
    
    # Récupérer le relevé de notes
    releve_notes = None
    if periode_active_obj:
        releve_notes = ReleveNotes.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=professeur.matiere_principale,
            periode_scolaire=periode_active_obj
        ).first()
    
    # Récupérer les élèves
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les moyennes pour déterminer le mode de calcul
    from ..model.moyenne_model import Moyenne
    
    mode_calcul_utilise = 'toutes'
    nombre_devoirs_affichage = 0
    
    # Vérifier si au moins un élève a une moyenne calculée
    premiere_moyenne = None
    if periode_active_obj:
        premiere_moyenne = Moyenne.objects.filter(
            classe=classe,
            matiere=professeur.matiere_principale,
            periode=str(periode_active_obj.id),
            actif=True
        ).first()
        
        if premiere_moyenne and hasattr(premiere_moyenne, 'mode_calcul'):
            mode_calcul_utilise = premiere_moyenne.mode_calcul
            # Déterminer combien de colonnes "Devoir" afficher
            if mode_calcul_utilise.isdigit():
                nombre_devoirs_affichage = int(mode_calcul_utilise)
            elif mode_calcul_utilise == 'interro_x2':
                # Compter les devoirs réels dans details_notes
                if hasattr(premiere_moyenne, 'details_notes') and premiere_moyenne.details_notes:
                    nombre_devoirs_affichage = len(premiere_moyenne.details_notes)
    
    # Créer les colonnes d'affichage génériques
    colonnes_devoirs = []
    for i in range(1, nombre_devoirs_affichage + 1):
        colonnes_devoirs.append({
            'index': i,
            'titre': f"Devoir {i}",
            'bareme': 20
        })
    
    # Récupérer les notes d'examen pour cette période
    from ..model.note_examen_model import NoteExamen
    from ..model.session_examen_model import SessionExamen
    
    # Trouver s'il y a une session d'examen pour cette période
    session_examen = None
    if periode_active_obj:
        # Récupérer toutes les sessions pour cette période/classe/matière
        sessions_possibles = SessionExamen.objects.filter(
            etablissement=professeur.etablissement,
            classes=classe,
            matieres=professeur.matiere_principale,
            periode=periode_active_obj,
            actif=True
        ).order_by('-date_debut')
        
        # Prioriser la session qui a déjà des notes enregistrées
        for session in sessions_possibles:
            notes_count = NoteExamen.objects.filter(
                session_examen=session,
                matiere=professeur.matiere_principale,
                classe=classe,
                actif=True
            ).count()
            if notes_count > 0:
                session_examen = session
                break
        
        # Si aucune session avec notes, prendre la première
        if not session_examen and sessions_possibles.exists():
            session_examen = sessions_possibles.first()
    
    # Créer un tableau avec les notes de chaque élève
    # Utiliser les details_notes de chaque moyenne pour affichage simplifié
    
    eleves_avec_notes = []
    for eleve in eleves:
        # Récupérer la moyenne enregistrée pour cet élève
        moyenne_obj = None
        moyenne = None
        appreciation = None
        notes_simplifiees = []  # Liste des notes à afficher (Devoir 1, Devoir 2, etc.)
        note_examen_obj = None
        
        if periode_active_obj:
            moyenne_obj = Moyenne.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=professeur.matiere_principale,
                periode=str(periode_active_obj.id),
                actif=True
            ).first()
            
            if moyenne_obj:
                moyenne = float(moyenne_obj.moyenne)
                appreciation = moyenne_obj.appreciation if hasattr(moyenne_obj, 'appreciation') else None
                
                # Utiliser les details_notes pour affichage
                if hasattr(moyenne_obj, 'details_notes') and moyenne_obj.details_notes:
                    notes_simplifiees = moyenne_obj.details_notes
            
            # Récupérer la note d'examen si elle existe
            if session_examen:
                note_examen_obj = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session_examen,
                    matiere=professeur.matiere_principale,
                    classe=classe,
                    actif=True
                ).first()
        
        eleves_avec_notes.append({
            'eleve': eleve,
            'notes_simplifiees': notes_simplifiees,  # Notes avec titres simplifiés (Devoir 1, Devoir 2, etc.)
            'moyenne': moyenne,
            'appreciation': appreciation,
            'nombre_notes': len(notes_simplifiees),
            'note_examen': note_examen_obj  # Ajouter la note d'examen
        })
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'matiere': professeur.matiere_principale,
        'periode_active': periode_active_obj,
        'periodes_scolaires': periodes_scolaires,
        'releve_notes': releve_notes,
        'colonnes_devoirs': colonnes_devoirs,  # Colonnes génériques : Devoir 1, Devoir 2, etc.
        'eleves_avec_notes': eleves_avec_notes,
        'mode_calcul_utilise': mode_calcul_utilise,
        'session_examen': session_examen,  # Session d'examen pour afficher la colonne
    }
    
    return render(request, 'school_admin/enseignant/voir_releve_notes.html', context)


def imprimer_releve_notes_enseignant(request, classe_id):
    """
    Génère une page d'impression du relevé de notes pour une classe (pour un enseignant)
    Affiche uniquement la matière enseignée par le professeur dans cette classe
    """
    logger.info(f"Impression relevé enseignant - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.moyenne_model import Moyenne
    from ..model.note_examen_model import NoteExamen
    from ..model.session_examen_model import SessionExamen
    from ..model.matiere_model import Matiere
    from django.shortcuts import get_object_or_404
    from datetime import datetime
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Vérifier l'affectation et récupérer la matière enseignée
    matiere_id = request.GET.get('matiere', '')
    matiere_enseignee = None
    
    if matiere_id:
        try:
            matiere_enseignee = Matiere.objects.get(id=matiere_id, etablissement=professeur.etablissement)
        except Matiere.DoesNotExist:
            pass
    
    # Si pas de matière spécifiée, utiliser la matière principale
    if not matiere_enseignee:
        affectation = get_object_or_404(
            AffectationProfesseur,
            professeur=professeur,
            classe=classe,
            actif=True
        )
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
    
    # Récupérer la période active
    periode_id = request.GET.get('periode', '')
    periode_active = None
    
    if periode_id:
        try:
            periode_active = PeriodeScolaire.objects.get(id=periode_id, etablissement=professeur.etablissement, est_active=True)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    if not periode_active:
        periodes = PeriodeScolaire.objects.filter(etablissement=professeur.etablissement, est_active=True).order_by('date_debut')
        for p in periodes:
            if p.est_en_cours:
                periode_active = p
                break
        if not periode_active:
            periode_active = periodes.first()
    
    # Récupérer tous les élèves
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les moyennes et construire le relevé
    eleves_data = []
    
    for eleve in eleves:
        moyenne_obj = None
        if periode_active:
            moyenne_obj = Moyenne.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=matiere_enseignee,
                periode=str(periode_active.id),
                actif=True
            ).first()
        
        # Construire les données de l'élève
        eleve_data = {
            'eleve': eleve,
            'notes_details': [],
            'note_examen': None,
            'moyenne': moyenne_obj.moyenne if moyenne_obj else None,
            'appreciation': None,
        }
        
        # Récupérer les notes détaillées depuis details_notes
        if moyenne_obj and moyenne_obj.details_notes:
            for note_detail in moyenne_obj.details_notes:
                eleve_data['notes_details'].append({
                    'titre': note_detail.get('titre', ''),
                    'note': note_detail.get('note', ''),
                    'bareme': note_detail.get('bareme', 20),
                })
        
        # Récupérer la note d'examen si disponible
        if periode_active:
            sessions_examens = SessionExamen.objects.filter(
                etablissement=professeur.etablissement,
                classes=classe,
                matieres=matiere_enseignee,
                periode=periode_active,
                actif=True
            )
            
            for session in sessions_examens:
                note_examen = NoteExamen.objects.filter(
                    session_examen=session,
                    eleve=eleve,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                ).first()
                
                if note_examen and note_examen.note is not None:
                    eleve_data['note_examen'] = note_examen.note_sur_20
                    eleve_data['appreciation'] = note_examen.commentaire
                    break
        
        eleves_data.append(eleve_data)
    
    # Trier par moyenne décroissante
    eleves_data.sort(key=lambda x: (x['moyenne'] is None, -x['moyenne'] if x['moyenne'] is not None else 0))
    
    context = {
        'etablissement': professeur.etablissement,
        'classe': classe,
        'matiere': matiere_enseignee,
        'periode': periode_active,
        'professeur': professeur,
        'eleves_data': eleves_data,
        'date_generation': datetime.now(),
        'nombre_eleves': eleves.count(),
    }
    
    return render(request, 'school_admin/enseignant/imprimer_releve_notes_enseignant.html', context)


def api_releve_notes_modal(request, classe_id):
    """
    API endpoint pour récupérer les données du relevé de notes avec uniquement les notes retenues
    Retourne les données en JSON pour affichage dans un modal
    """
    from django.http import JsonResponse
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.moyenne_model import Moyenne
    from ..model.note_examen_model import NoteExamen
    from ..model.session_examen_model import SessionExamen
    from django.shortcuts import get_object_or_404
    
    if not isinstance(request.user, Professeur):
        return JsonResponse({'success': False, 'error': 'Accès non autorisé'}, status=403)
    
    professeur = request.user
    
    # Récupérer les paramètres
    periode_id = request.GET.get('periode', '')
    matiere_id = request.GET.get('matiere', '')
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer l'affectation (gérer le cas où il y a plusieurs affectations)
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        return JsonResponse({'success': False, 'error': 'Affectation non trouvée'}, status=404)
    
    # Déterminer la matière
    matiere_enseignee = None
    if matiere_id:
        try:
            from ..model.matiere_model import Matiere
            matiere_enseignee = Matiere.objects.get(id=matiere_id, etablissement=professeur.etablissement)
        except Matiere.DoesNotExist:
            pass
    
    if not matiere_enseignee:
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
    
    # Récupérer la période
    periode_active_obj = None
    if periode_id:
        try:
            periode_active_obj = PeriodeScolaire.objects.get(
                id=periode_id,
                etablissement=professeur.etablissement,
                est_active=True
            )
        except PeriodeScolaire.DoesNotExist:
            pass
    
    if not periode_active_obj:
        periode_active_obj = PeriodeScolaire.objects.filter(
            etablissement=professeur.etablissement,
            est_active=True,
            est_en_cours=True
        ).first()
        if not periode_active_obj:
            periode_active_obj = PeriodeScolaire.objects.filter(
                etablissement=professeur.etablissement,
                est_active=True
            ).order_by('date_debut').first()
    
    if not periode_active_obj:
        return JsonResponse({'success': False, 'error': 'Aucune période active trouvée'}, status=404)
    
    # Récupérer le relevé pour connaître l'état de soumission
    from ..model.releve_notes_model import ReleveNotes
    releve_obj = ReleveNotes.objects.filter(
        classe=classe,
        professeur=professeur,
        matiere=matiere_enseignee,
        periode_scolaire=periode_active_obj
    ).first()
    releve_soumis = bool(releve_obj and releve_obj.soumis)

    # Récupérer les élèves
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les moyennes et notes retenues pour chaque élève
    eleves_data = []
    max_notes_count = 0  # Pour déterminer le nombre de colonnes nécessaires
    
    # Récupérer la session d'examen pour cette période/classe/matière
    session_examen = None
    if periode_active_obj:
        sessions_possibles = SessionExamen.objects.filter(
            etablissement=professeur.etablissement,
            classes=classe,
            matieres=matiere_enseignee,
            periode=periode_active_obj,
            actif=True
        ).order_by('-date_debut')
        
        # Prioriser la session qui a déjà des notes enregistrées
        for session in sessions_possibles:
            notes_count = NoteExamen.objects.filter(
                session_examen=session,
                matiere=matiere_enseignee,
                classe=classe,
                actif=True
            ).count()
            if notes_count > 0:
                session_examen = session
                break
        
        if not session_examen and sessions_possibles.exists():
            session_examen = sessions_possibles.first()
    
    for eleve in eleves:
        moyenne_obj = None
        moyenne = None
        appreciation = None
        notes_retenues = []  # Notes retenues pour cet élève
        note_examen = None
        
        if periode_active_obj:
            # Récupérer la moyenne en utilisant periode comme string
            moyenne_obj = Moyenne.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=matiere_enseignee,
                periode=str(periode_active_obj.id),
                actif=True
            ).first()
            
            if moyenne_obj:
                moyenne = float(moyenne_obj.moyenne)
                appreciation = moyenne_obj.appreciation if hasattr(moyenne_obj, 'appreciation') else None
                
                # Récupérer les notes retenues depuis details_notes
                if hasattr(moyenne_obj, 'details_notes') and moyenne_obj.details_notes:
                    # Filtrer toute entrée d'examen résiduelle (anciens enregistrements)
                    notes_retenues = [n for n in moyenne_obj.details_notes if not (isinstance(n, dict) and n.get('type') == 'examen')]
                    max_notes_count = max(max_notes_count, len(notes_retenues))
            
            # Récupérer la note d'examen si elle existe
            if session_examen:
                note_examen_obj = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session_examen,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                ).first()
                if note_examen_obj:
                    note_examen = {
                        'note': float(note_examen_obj.note),
                        'bareme': float(note_examen_obj.bareme) if hasattr(note_examen_obj, 'bareme') else 20.0
                    }
        
        eleves_data.append({
            'id': eleve.id,
            'nom': eleve.nom,
            'prenom': eleve.prenom,
            'nom_complet': eleve.nom_complet,
            'notes_retenues': notes_retenues,  # Liste des notes retenues
            'moyenne': moyenne,
            'appreciation': appreciation,
            'note_examen': note_examen
        })
    
    # Créer les colonnes dynamiques (Évaluation 1, Évaluation 2, etc.)
    colonnes = []
    for i in range(1, max_notes_count + 1):
        colonnes.append({
            'index': i,
            'titre': f'Évaluation {i}'
        })
    
    return JsonResponse({
        'success': True,
        'classe': {
            'id': classe.id,
            'nom': classe.nom
        },
        'matiere': {
            'id': matiere_enseignee.id,
            'nom': matiere_enseignee.nom
        },
        'periode': {
            'id': periode_active_obj.id,
            'nom': periode_active_obj.nom_periode
        },
        'colonnes': colonnes,
        'eleves': eleves_data,
        'a_session_examen': session_examen is not None,
        'releve_soumis': releve_soumis
    })


def imprimer_releve_notes(request, classe_id):
    """
    Page d'impression professionnelle du relevé de notes
    """
    logger.info(f"Imprimer relevé - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.evaluation_model import Evaluation, Note
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.releve_notes_model import ReleveNotes
    from ..model.moyenne_model import Moyenne
    from django.shortcuts import get_object_or_404
    from decimal import Decimal
    from datetime import datetime
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    affectation = get_object_or_404(
        AffectationProfesseur,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Récupérer toutes les périodes scolaires
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer la période sélectionnée
    periode_id = request.GET.get('periode', '')
    periode_active_obj = None
    
    if periode_id:
        try:
            periode_active_obj = periodes_scolaires.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    if not periode_active_obj:
        for periode in periodes_scolaires:
            if periode.est_en_cours:
                periode_active_obj = periode
                break
        if not periode_active_obj:
            periode_active_obj = periodes_scolaires.first()
    
    # Récupérer le relevé de notes
    releve_notes = None
    if periode_active_obj:
        releve_notes = ReleveNotes.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=professeur.matiere_principale,
            periode_scolaire=periode_active_obj
        ).first()
    
    # Récupérer les élèves
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les moyennes pour déterminer le mode de calcul
    mode_calcul_utilise = 'toutes'
    nombre_devoirs_affichage = 0
    
    # Vérifier si au moins un élève a une moyenne calculée
    premiere_moyenne = None
    if periode_active_obj:
        premiere_moyenne = Moyenne.objects.filter(
            classe=classe,
            matiere=professeur.matiere_principale,
            periode=str(periode_active_obj.id),
            actif=True
        ).first()
        
        if premiere_moyenne and hasattr(premiere_moyenne, 'mode_calcul'):
            mode_calcul_utilise = premiere_moyenne.mode_calcul
            # Déterminer combien de colonnes "Devoir" afficher
            if mode_calcul_utilise.isdigit():
                nombre_devoirs_affichage = int(mode_calcul_utilise)
            elif mode_calcul_utilise == 'interro_x2':
                # Compter les devoirs réels dans details_notes
                if hasattr(premiere_moyenne, 'details_notes') and premiere_moyenne.details_notes:
                    nombre_devoirs_affichage = len(premiere_moyenne.details_notes)
    
    # Créer les colonnes d'affichage génériques
    colonnes_devoirs = []
    for i in range(1, nombre_devoirs_affichage + 1):
        colonnes_devoirs.append({
            'index': i,
            'titre': f"Devoir {i}",
            'bareme': 20
        })
    
    # Créer un tableau avec les notes de chaque élève
    # Utiliser les details_notes de chaque moyenne pour affichage simplifié
    eleves_avec_notes = []
    for eleve in eleves:
        # Récupérer la moyenne enregistrée pour cet élève
        moyenne_obj = None
        moyenne = None
        appreciation = None
        notes_simplifiees = []  # Liste des notes à afficher (Devoir 1, Devoir 2, etc.)
        
        if periode_active_obj:
            moyenne_obj = Moyenne.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=professeur.matiere_principale,
                periode=str(periode_active_obj.id),
                actif=True
            ).first()
            
            if moyenne_obj:
                moyenne = float(moyenne_obj.moyenne)
                appreciation = moyenne_obj.appreciation if hasattr(moyenne_obj, 'appreciation') else None
                
                # Utiliser les details_notes pour affichage
                if hasattr(moyenne_obj, 'details_notes') and moyenne_obj.details_notes:
                    notes_simplifiees = moyenne_obj.details_notes
        
        eleves_avec_notes.append({
            'eleve': eleve,
            'notes_simplifiees': notes_simplifiees,  # Notes avec titres simplifiés (Devoir 1, Devoir 2, etc.)
            'moyenne': moyenne,
            'appreciation': appreciation,
            'nombre_notes': len(notes_simplifiees)
        })
    
    # Calculer la moyenne de classe
    moyennes_valides = [e['moyenne'] for e in eleves_avec_notes if e['moyenne'] is not None]
    moyenne_classe = round(sum(moyennes_valides) / len(moyennes_valides), 2) if moyennes_valides else None
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'matiere': professeur.matiere_principale,
        'periode_active': periode_active_obj,
        'releve_notes': releve_notes,
        'colonnes_devoirs': colonnes_devoirs,  # Colonnes génériques : Devoir 1, Devoir 2, etc.
        'eleves_avec_notes': eleves_avec_notes,
        'mode_calcul_utilise': mode_calcul_utilise,
        'moyenne_classe': moyenne_classe,
        'etablissement': professeur.etablissement,
        'date_impression': datetime.now(),
    }
    
    return render(request, 'school_admin/enseignant/imprimer_releve_notes.html', context)


def liste_presence_enseignant(request, classe_id):
    """
    Page pour prendre la liste de présence d'une classe
    """
    logger.info(f"Liste présence - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.affectation_model import AffectationProfesseur
    from ..model.presence_model import Presence, ListePresence
    from ..model.matiere_model import Matiere
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from datetime import date
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer toutes les affectations pour cette classe
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Vérifier si c'est un établissement secondaire (lycée, collège, collège_lycée)
    etablissement = classe.etablissement
    est_secondaire = etablissement.type_etablissement in ['lycée', 'collège', 'collège_lycée']
    
    # Récupérer la matière depuis GET si fournie
    matiere_id = request.GET.get('matiere', '')
    matiere_selectionnee = None
    affectation_utilisee = None
    
    # Si établissement secondaire et plusieurs affectations, nécessite la sélection d'une matière
    if est_secondaire and affectations.count() > 1:
        if matiere_id:
            try:
                matiere_selectionnee = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
                affectation_utilisee = affectations.filter(matiere=matiere_selectionnee).first()
            except Matiere.DoesNotExist:
                messages.error(request, "Matière non trouvée.")
                return redirect('enseignant:gestion_eleves')
        else:
            # Afficher la page avec sélection de matière
            matieres_affectations = []
            for aff in affectations:
                if aff.matiere:
                    matieres_affectations.append({
                        'id': aff.matiere.id,
                        'nom': aff.matiere.nom,
                        'affectation': aff
                    })
            
            context = {
                'professeur': professeur,
                'classe': classe,
                'matieres_affectations': matieres_affectations,
                'today': date.today(),
                'nombre_eleves': Eleve.objects.filter(classe=classe, actif=True).count(),
            }
            return render(request, 'school_admin/enseignant/selection_matiere_presence.html', context)
    else:
        # Pour les établissements primaires ou une seule affectation, utiliser la première
        affectation_utilisee = affectations.first()
        if affectation_utilisee and affectation_utilisee.matiere:
            matiere_selectionnee = affectation_utilisee.matiere
        elif matiere_id:
            try:
                matiere_selectionnee = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
            except Matiere.DoesNotExist:
                pass
    
    # Date du jour
    today = date.today()
    
    # Vérifier s'il existe déjà une liste de présence pour aujourd'hui et cette matière
    # ATTENTION: Ne créer/récupérer la liste que si une matière a été sélectionnée OU si ce n'est pas un établissement secondaire
    liste_presence = None
    if matiere_selectionnee or not est_secondaire:
        filters = {
            'classe': classe,
            'date': today,
        }
        if matiere_selectionnee:
            filters['matiere'] = matiere_selectionnee
        else:
            filters['matiere__isnull'] = True
        
        liste_presence, created = ListePresence.objects.get_or_create(
            **filters,
            defaults={
                'professeur': professeur,
                'etablissement': classe.etablissement,
                'matiere': matiere_selectionnee
            }
        )
        
        # Si la liste est déjà validée, rediriger avec un message
        if liste_presence.validee:
            matiere_msg = f" pour la matière {matiere_selectionnee.nom}" if matiere_selectionnee else ""
            messages.info(request, f"La liste de présence{matiere_msg} a déjà été validée pour aujourd'hui.")
    
    # Si on est ici, c'est qu'une matière a été sélectionnée ou que ce n'est pas un établissement secondaire
    # Récupérer tous les élèves actifs de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les présences déjà enregistrées pour aujourd'hui et cette matière
    filters_presence = {
        'classe': classe,
        'date': today,
        'numero_appel': 1  # Pour lycée/collège, on garde 1 appel par jour par matière
    }
    if matiere_selectionnee:
        filters_presence['matiere'] = matiere_selectionnee
    else:
        filters_presence['matiere__isnull'] = True
    
    presences_existantes = Presence.objects.filter(**filters_presence).select_related('eleve')
    
    # Créer un dictionnaire des présences existantes
    presences_dict = {p.eleve.id: p for p in presences_existantes}
    
    # Construire la liste des élèves avec leur statut de présence
    eleves_avec_presence = []
    for eleve in eleves:
        presence = presences_dict.get(eleve.id)
        eleves_avec_presence.append({
            'eleve': eleve,
            'presence': presence,
            'statut': presence.statut if presence else 'present'
        })
    
    # Créer une liste_presence vide si elle n'existe pas encore (pour l'affichage)
    if not liste_presence:
        liste_presence = ListePresence(classe=classe, date=today, professeur=professeur, etablissement=classe.etablissement, matiere=matiere_selectionnee)
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'eleves_avec_presence': eleves_avec_presence,
        'liste_presence': liste_presence,
        'today': today,
        'nombre_eleves': eleves.count(),
        'matiere': matiere_selectionnee,
        'est_secondaire': est_secondaire,
    }
    
    return render(request, 'school_admin/enseignant/liste_presence.html', context)


def valider_presence_enseignant(request, classe_id):
    """
    Enregistre et valide la liste de présence
    """
    logger.info(f"Validation présence - User: {request.user}, Classe ID: {classe_id}")
    
    if request.method != 'POST':
        return redirect('enseignant:liste_presence', classe_id=classe_id)
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.affectation_model import AffectationProfesseur
    from ..model.presence_model import Presence, ListePresence
    from ..model.matiere_model import Matiere
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from datetime import date
    from django.db import transaction
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    etablissement = classe.etablissement
    
    # Récupérer toutes les affectations pour cette classe
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer la matière depuis POST
    matiere_id = request.POST.get('matiere', '')
    matiere_selectionnee = None
    
    est_secondaire = etablissement.type_etablissement in ['lycée', 'collège', 'collège_lycée']
    
    if est_secondaire and affectations.count() > 1:
        if not matiere_id:
            messages.error(request, "Vous devez sélectionner une matière.")
            return redirect('enseignant:liste_presence', classe_id=classe_id)
        
        try:
            matiere_selectionnee = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
            return redirect('enseignant:liste_presence', classe_id=classe_id)
    
    # Date du jour
    today = date.today()
    
    try:
        with transaction.atomic():
            # Vérifier s'il existe déjà une liste validée pour aujourd'hui et cette matière
            filters = {
                'classe': classe,
                'date': today,
            }
            if matiere_selectionnee:
                filters['matiere'] = matiere_selectionnee
            else:
                filters['matiere__isnull'] = True
            
            liste_presence = ListePresence.objects.filter(**filters).first()
            
            if liste_presence and liste_presence.validee:
                messages.warning(request, f"La liste de présence{' pour ' + matiere_selectionnee.nom + ' ' if matiere_selectionnee else ''}a déjà été validée pour aujourd'hui.")
                return redirect('enseignant:liste_presence', classe_id=classe_id)
            
            # Créer ou mettre à jour la liste de présence
            if not liste_presence:
                liste_presence = ListePresence.objects.create(
                    classe=classe,
                    date=today,
                    professeur=professeur,
                    etablissement=etablissement,
                    matiere=matiere_selectionnee
                )
            elif not liste_presence.matiere and matiere_selectionnee:
                liste_presence.matiere = matiere_selectionnee
                liste_presence.save()
            
            # Parcourir les données POST pour enregistrer les présences
            nombre_presents = 0
            nombre_absents = 0
            
            for key, value in request.POST.items():
                if key.startswith('presence_'):
                    eleve_id = key.replace('presence_', '')
                    try:
                        eleve = Eleve.objects.get(id=eleve_id, classe=classe, actif=True)
                        
                        # Créer ou mettre à jour la présence
                        # IMPORTANT : Inclure matiere et numero_appel pour différencier par matière
                        presence, created = Presence.objects.update_or_create(
                            eleve=eleve,
                            classe=classe,
                            date=today,
                            numero_appel=1,  # Pour lycée/collège, on garde 1 appel par jour par matière
                            matiere=matiere_selectionnee,
                            defaults={
                                'professeur': professeur,
                                'etablissement': classe.etablissement,
                                'statut': value
                            }
                        )
                        
                        # Compter les présents et absents
                        if value == 'present':
                            nombre_presents += 1
                        elif value in ['absent', 'absent_justifie']:
                            nombre_absents += 1
                    
                    except Eleve.DoesNotExist:
                        logger.warning(f"Élève {eleve_id} non trouvé ou inactif")
                        continue
            
            # Valider la liste de présence
            liste_presence.validee = True
            liste_presence.date_validation = timezone.now()
            liste_presence.nombre_presents = nombre_presents
            liste_presence.nombre_absents = nombre_absents
            liste_presence.save()
            
            messages.success(
                request, 
                f"Liste de présence validée avec succès ! {nombre_presents} présent(s), {nombre_absents} absent(s)."
            )
            
            # Envoyer des notifications push aux élèves
            try:
                from school_admin.services.firebase_service import FirebaseService
                
                # Récupérer toutes les présences de cette liste
                filters_presence = {
                    'classe': classe,
                    'date': today,
                    'numero_appel': 1
                }
                if matiere_selectionnee:
                    filters_presence['matiere'] = matiere_selectionnee
                else:
                    filters_presence['matiere__isnull'] = True
                
                presences = Presence.objects.filter(**filters_presence)
                
                # Préparer la date en clair avec heure
                import locale
                try:
                    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
                except:
                    try:
                        locale.setlocale(locale.LC_TIME, 'French_France.1252')
                    except:
                        pass
                
                now = timezone.now()
                # Format: lundi 12 juillet 2025 à 12h00
                jour_semaine = now.strftime('%A')
                jour = now.strftime('%d')
                mois = now.strftime('%B')
                annee = now.strftime('%Y')
                heure = now.strftime('%H')
                minute = now.strftime('%M')
                date_claire = f"{jour_semaine} {jour} {mois} {annee} à {heure}h{minute}"
                
                for presence in presences:
                    try:
                        presence.refresh_from_db(fields=["statut", "date_modification"])
                    except Exception:
                        pass

                    statut = presence.statut
                    matiere_texte = (
                        f" en {matiere_selectionnee.nom}" if matiere_selectionnee else ""
                    )

                    if statut == 'present':
                        emoji = "✅"
                        title = "📋 Appel de classe"
                        body = (
                            f"Vous avez été présent(e){matiere_texte} lors de l'appel du {date_claire}."
                        )
                    elif statut == 'absent':
                        emoji = "❌"
                        title = "⚠️ Absence enregistrée"
                        body = (
                            f"Vous avez été absent(e){matiere_texte} lors de l'appel du {date_claire}."
                        )
                    elif statut == 'absent_justifie':
                        emoji = "📝"
                        title = "📋 Absence justifiée"
                        body = (
                            f"Votre absence{matiere_texte} du {date_claire} a été enregistrée comme justifiée."
                        )
                    elif statut == 'retard':
                        emoji = "⏰"
                        title = "⏰ Retard enregistré"
                        body = (
                            f"Vous avez été en retard{matiere_texte} lors de l'appel du {date_claire}."
                        )
                    else:
                        continue

                    data = {
                        'type': 'presence',
                        'presence_id': str(presence.id),
                        'statut': statut,
                        'date': today.isoformat(),
                        'classe': classe.nom,
                        'url': '/eleve/dashboard/'
                    }

                    if matiere_selectionnee:
                        data['matiere'] = matiere_selectionnee.nom

                    # Notification push directe
                    result = FirebaseService.send_notification_to_multiple_users(
                        [presence.eleve], title, body, data
                    )

                    if result['success_count'] > 0:
                        logger.info(
                            "Notification de présence envoyée à %s - Statut: %s",
                            presence.eleve.nom_complet,
                            statut,
                        )
                    else:
                        logger.warning(
                            "Échec de l'envoi de notification de présence à %s",
                            presence.eleve.nom_complet,
                        )

                    try:
                        EleveNotificationService.notify_presence(
                            presence,
                            titre=title,
                            message=body,
                            payload=data,
                        )
                    except Exception:
                        logger.exception(
                            "Échec notification élève %s pour présence",
                            getattr(presence.eleve, "id", "N/A"),
                        )

                    try:
                        ParentNotificationService.notify_presence(
                            presence,
                            date_description=date_claire,
                        )
                    except Exception:
                        logger.exception(
                            "Échec notification parent pour présence %s",
                            getattr(presence, "id", "N/A"),
                        )

            except Exception as e:
                logger.error(f"Erreur lors de l'envoi des notifications de présence: {str(e)}")
            
    except Exception as e:
        logger.error(f"Erreur lors de la validation de la présence: {str(e)}")
        messages.error(request, f"Erreur lors de la validation : {str(e)}")
    
    return redirect('enseignant:gestion_eleves')


def detail_eleve_enseignant(request, eleve_id):
    """
    Page de détails d'un élève avec onglets (Notes, Présences, Informations)
    """
    logger.info(f"Détail élève - User: {request.user}, Élève ID: {eleve_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Evaluation, Note
    from ..model.moyenne_model import Moyenne
    from ..model.presence_model import Presence
    from django.shortcuts import get_object_or_404
    from datetime import date, timedelta
    
    # Récupérer l'élève
    eleve = get_object_or_404(Eleve, id=eleve_id, actif=True)
    classe = eleve.classe
    
    # Vérifier que le professeur est affecté à cette classe et récupérer toutes les affectations (matières)
    from ..model.affectation_model import AffectationProfesseur
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer toutes les matières enseignées dans cette classe
    matieres_list = []
    for aff in affectations:
        matiere = aff.matiere if aff.matiere else professeur.matiere_principale
        if matiere and matiere not in matieres_list:
            matieres_list.append(matiere)
    
    # Si aucune matière trouvée via affectations, utiliser la matière principale du professeur
    if not matieres_list and professeur.matiere_principale:
        matieres_list.append(professeur.matiere_principale)
    
    # Récupérer la matière sélectionnée (si plusieurs matières)
    matiere_id = request.GET.get('matiere')
    matiere_selectionnee = None
    if matiere_id:
        from ..model.matiere_model import Matiere
        try:
            matiere_selectionnee = Matiere.objects.get(id=matiere_id)
            if matiere_selectionnee not in matieres_list:
                matiere_selectionnee = None
        except Matiere.DoesNotExist:
            pass
    
    # Si une seule matière ou aucune sélectionnée, utiliser la première
    if not matiere_selectionnee and matieres_list:
        matiere_selectionnee = matieres_list[0]
    
    # Récupérer l'onglet actif (par défaut: notes)
    onglet_actif = request.GET.get('onglet', 'notes')
    
    # === ONGLET NOTES ===
    from ..model.periode_model import PeriodeScolaire
    
    # Récupérer toutes les périodes scolaires
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer la période sélectionnée
    periode_id = request.GET.get('periode')
    if periode_id:
        periode_selectionnee = PeriodeScolaire.objects.filter(id=periode_id).first()
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Créer un dictionnaire de données par matière pour les notes
    notes_par_matiere = {}
    for matiere in matieres_list:
        # Récupérer les évaluations de cette matière pour cette période
        evaluations = Evaluation.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=matiere,
            periode_scolaire=periode_selectionnee,
            actif=True
        ).order_by('date_evaluation') if periode_selectionnee else []
        
        # Récupérer les notes de l'élève pour ces évaluations
        notes_objs = Note.objects.filter(
            eleve=eleve,
            evaluation__in=evaluations,
            matiere=matiere
        ).select_related('evaluation')
        
        # Créer un dictionnaire des notes indexé par evaluation_id
        notes_dict = {note.evaluation.id: note for note in notes_objs}
        
        # Récupérer la moyenne enregistrée pour cette matière et période
        moyenne_obj = Moyenne.objects.filter(
            eleve=eleve,
            professeur=professeur,
            matiere=matiere,
            periode=str(periode_selectionnee.id) if periode_selectionnee else None,
            actif=True
        ).first() if periode_selectionnee else None
        
        moyenne = moyenne_obj.moyenne if moyenne_obj else None
        
        # Récupérer la note d'examen pour cette matière/période si une session existe
        note_examen_dict = None
        if periode_selectionnee:
            from ..model.session_examen_model import SessionExamen
            from ..model.note_examen_model import NoteExamen
            session_examen_qs = SessionExamen.objects.filter(
                etablissement=professeur.etablissement,
                classes=classe,
                matieres=matiere,
                periode=periode_selectionnee,
                actif=True
            ).order_by('-date_debut')
            session_examen_sel = None
            if session_examen_qs.exists():
                for sess in session_examen_qs:
                    if NoteExamen.objects.filter(session_examen=sess, matiere=matiere, classe=classe, actif=True).exists():
                        session_examen_sel = sess
                        break
                if not session_examen_sel:
                    session_examen_sel = session_examen_qs.first()
            if session_examen_sel:
                note_exam_obj = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session_examen_sel,
                    matiere=matiere,
                    classe=classe,
                    actif=True
                ).first()
                if note_exam_obj and note_exam_obj.note is not None and not note_exam_obj.absent:
                    note_examen_dict = {
                        'note': float(note_exam_obj.note),
                        'bareme': float(note_exam_obj.bareme) if hasattr(note_exam_obj, 'bareme') else 20.0
                    }
        
        notes_par_matiere[matiere.id] = {
            'matiere': matiere,
            'evaluations': evaluations,
            'notes_dict': notes_dict,
            'moyenne': moyenne,
            'nombre_notes': len(notes_dict),
            'note_examen': note_examen_dict,
        }
    
    # Pour compatibilité avec l'ancien code, garder les données de la matière sélectionnée
    if matiere_selectionnee and matiere_selectionnee.id in notes_par_matiere:
        notes_data = notes_par_matiere[matiere_selectionnee.id]
        evaluations = notes_data['evaluations']
        notes_dict = notes_data['notes_dict']
        moyenne = notes_data['moyenne']
        nombre_notes = notes_data['nombre_notes']
    elif notes_par_matiere:
        # Utiliser la première matière disponible
        first_matiere_id = list(notes_par_matiere.keys())[0]
        notes_data = notes_par_matiere[first_matiere_id]
        matiere_selectionnee = notes_data['matiere']
        evaluations = notes_data['evaluations']
        notes_dict = notes_data['notes_dict']
        moyenne = notes_data['moyenne']
        nombre_notes = notes_data['nombre_notes']
    else:
        evaluations = []
        notes_dict = {}
        moyenne = None
        nombre_notes = 0
    
    # === ONGLET PRÉSENCES ===
    # Récupérer toutes les présences de l'année scolaire en cours
    from ..model.presence_model import ListePresence
    import calendar
    
    today = date.today()
    if today.month >= 9:
        debut_annee = date(today.year, 9, 1)
        fin_annee = date(today.year + 1, 6, 30)
    else:
        debut_annee = date(today.year - 1, 9, 1)
        fin_annee = date(today.year, 6, 30)
    
    # Créer un dictionnaire de données par matière pour les présences
    presences_par_matiere = {}
    mois_disponibles_par_matiere = {}
    
    for matiere in matieres_list:
        # Récupérer les listes de présence pour cette matière
        listes_presence_matiere = ListePresence.objects.filter(
            classe=classe,
            matiere=matiere,
            validee=True,
            date__gte=debut_annee,
            date__lte=fin_annee
        )
        
        # Extraire les dates des listes de présence pour cette matière
        dates_listes = listes_presence_matiere.values_list('date', flat=True)
        
        # Récupérer les présences pour ces dates
        presences_query = Presence.objects.filter(
            eleve=eleve,
            classe=classe,
            date__in=list(dates_listes),
            date__gte=debut_annee,
            date__lte=fin_annee
        ).select_related('eleve', 'classe').order_by('-date')
        
        # Calculer les statistiques globales pour cette matière
        total_presences = presences_query.count()
        nombre_absences = presences_query.filter(statut__in=['absent', 'absent_justifie']).count()
        nombre_retards = presences_query.filter(statut='retard').count()
        nombre_presents = presences_query.filter(statut='present').count()
        taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
        
        # Extraire les mois uniques qui ont des listes validées pour cette matière
        mois_avec_presences = set()
        for date_presence in dates_listes:
            mois_avec_presences.add((date_presence.year, date_presence.month))
        
        # Créer une liste de mois disponibles pour cette matière
        noms_mois = [
            'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]
        mois_disponibles = []
        for annee, mois in sorted(mois_avec_presences, reverse=True):
            mois_disponibles.append({
                'annee': annee,
                'mois': mois,
                'nom': noms_mois[mois - 1],
                'annee_mois': f"{annee}-{mois:02d}"
            })
        
        # Récupérer le mois sélectionné (par défaut: le plus récent)
        mois_selectionne = request.GET.get('mois')
        if mois_selectionne and '-' in mois_selectionne:
            annee_sel, mois_sel = mois_selectionne.split('-')
            annee_sel = int(annee_sel)
            mois_sel = int(mois_sel)
        elif mois_disponibles:
            annee_sel = mois_disponibles[0]['annee']
            mois_sel = mois_disponibles[0]['mois']
        else:
            annee_sel = today.year
            mois_sel = today.month
        
        # Filtrer les présences pour le mois sélectionné
        premier_jour = date(annee_sel, mois_sel, 1)
        dernier_jour = date(annee_sel, mois_sel, calendar.monthrange(annee_sel, mois_sel)[1])
        
        presences = presences_query.filter(
            date__gte=premier_jour,
            date__lte=dernier_jour
        ).order_by('-date')
        
        # Statistiques du mois pour cette matière
        total_presences_mois = presences.count()
        nombre_absences_mois = presences.filter(statut__in=['absent', 'absent_justifie']).count()
        nombre_retards_mois = presences.filter(statut='retard').count()
        nombre_presents_mois = presences.filter(statut='present').count()
        taux_presence_mois = round((nombre_presents_mois / total_presences_mois * 100), 2) if total_presences_mois > 0 else 0
        
        presences_par_matiere[matiere.id] = {
            'matiere': matiere,
            'presences': presences,
            'total_presences': total_presences,
            'nombre_absences': nombre_absences,
            'nombre_retards': nombre_retards,
            'nombre_presents': nombre_presents,
            'taux_presence': taux_presence,
            'mois_disponibles': mois_disponibles,
            'total_presences_mois': total_presences_mois,
            'nombre_absences_mois': nombre_absences_mois,
            'nombre_retards_mois': nombre_retards_mois,
            'nombre_presents_mois': nombre_presents_mois,
            'taux_presence_mois': taux_presence_mois,
        }
        mois_disponibles_par_matiere[matiere.id] = mois_disponibles
    
    # Pour compatibilité avec l'ancien code, garder les données de la matière sélectionnée
    mois_selectionne = None  # Sera calculé pour la matière sélectionnée
    if matiere_selectionnee and matiere_selectionnee.id in presences_par_matiere:
        presences_data = presences_par_matiere[matiere_selectionnee.id]
        presences = presences_data['presences']
        total_presences = presences_data['total_presences']
        nombre_absences = presences_data['nombre_absences']
        nombre_retards = presences_data['nombre_retards']
        nombre_presents = presences_data['nombre_presents']
        taux_presence = presences_data['taux_presence']
        mois_disponibles = presences_data['mois_disponibles']
        total_presences_mois = presences_data['total_presences_mois']
        nombre_absences_mois = presences_data['nombre_absences_mois']
        nombre_retards_mois = presences_data['nombre_retards_mois']
        nombre_presents_mois = presences_data['nombre_presents_mois']
        taux_presence_mois = presences_data['taux_presence_mois']
        # Calculer mois_selectionne pour la matière sélectionnée
        mois_selectionne_param = request.GET.get('mois')
        if mois_selectionne_param and '-' in mois_selectionne_param:
            mois_selectionne = mois_selectionne_param
        elif mois_disponibles:
            mois_selectionne = mois_disponibles[0]['annee_mois']
    elif presences_par_matiere:
        # Utiliser la première matière disponible
        first_matiere_id = list(presences_par_matiere.keys())[0]
        presences_data = presences_par_matiere[first_matiere_id]
        matiere_selectionnee = presences_data['matiere']
        presences = presences_data['presences']
        total_presences = presences_data['total_presences']
        nombre_absences = presences_data['nombre_absences']
        nombre_retards = presences_data['nombre_retards']
        nombre_presents = presences_data['nombre_presents']
        taux_presence = presences_data['taux_presence']
        mois_disponibles = presences_data['mois_disponibles']
        total_presences_mois = presences_data['total_presences_mois']
        nombre_absences_mois = presences_data['nombre_absences_mois']
        nombre_retards_mois = presences_data['nombre_retards_mois']
        nombre_presents_mois = presences_data['nombre_presents_mois']
        taux_presence_mois = presences_data['taux_presence_mois']
        # Calculer mois_selectionne pour la matière sélectionnée
        mois_selectionne_param = request.GET.get('mois')
        if mois_selectionne_param and '-' in mois_selectionne_param:
            mois_selectionne = mois_selectionne_param
        elif mois_disponibles:
            mois_selectionne = mois_disponibles[0]['annee_mois']
    else:
        presences = []
        total_presences = 0
        nombre_absences = 0
        nombre_retards = 0
        nombre_presents = 0
        taux_presence = 0
        mois_disponibles = []
        total_presences_mois = 0
        nombre_absences_mois = 0
        nombre_retards_mois = 0
        nombre_presents_mois = 0
        taux_presence_mois = 0
    
    # === ONGLET SANCTIONS ===
    from ..model.sanction_model import Sanction
    sanctions = Sanction.objects.filter(
        eleve=eleve,
        classe=classe
    ).order_by('-date_sanction', '-date_creation')
    
    nombre_sanctions = sanctions.count()
    nombre_sanctions_graves = sanctions.filter(gravite__in=['grave', 'tres_grave']).count()
    
    context = {
        'professeur': professeur,
        'eleve': eleve,
        'classe': classe,
        'matieres_list': matieres_list,
        'matiere_selectionnee': matiere_selectionnee,
        'affectation': affectations.first(),  # Pour compatibilité
        'onglet_actif': onglet_actif,
        # Onglet Notes - données par matière
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'notes_par_matiere': notes_par_matiere,
        # Pour compatibilité avec l'ancien template
        'evaluations': evaluations,
        'notes_dict': notes_dict,
        'moyenne': moyenne,
        'nombre_notes': nombre_notes,
        # Onglet Présences - données par matière
        'presences_par_matiere': presences_par_matiere,
        'mois_disponibles_par_matiere': mois_disponibles_par_matiere,
        # Pour compatibilité avec l'ancien template
        'presences': presences,
        'total_presences': total_presences,
        'nombre_absences': nombre_absences,
        'nombre_retards': nombre_retards,
        'nombre_presents': nombre_presents,
        'taux_presence': taux_presence,
        'mois_disponibles': mois_disponibles,
        'mois_selectionne': mois_selectionne,
        'total_presences_mois': total_presences_mois,
        'nombre_absences_mois': nombre_absences_mois,
        'nombre_retards_mois': nombre_retards_mois,
        'nombre_presents_mois': nombre_presents_mois,
        'taux_presence_mois': taux_presence_mois,
        # Onglet Sanctions
        'sanctions': sanctions,
        'nombre_sanctions': nombre_sanctions,
        'nombre_sanctions_graves': nombre_sanctions_graves,
    }
    
    return render(request, 'school_admin/enseignant/detail_eleve.html', context)


def modifier_presence_eleve(request, presence_id):
    """
    Modifier une présence existante d'un élève
    """
    logger.info(f"Modification présence - User: {request.user}, Présence ID: {presence_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    if request.method != 'POST':
        messages.error(request, "Méthode non autorisée.")
        return redirect('enseignant:gestion_eleves')
    
    professeur = request.user
    from ..model.presence_model import Presence, ListePresence
    from django.shortcuts import get_object_or_404
    
    # Récupérer la présence
    presence = get_object_or_404(Presence, id=presence_id)
    eleve = presence.eleve
    
    # Vérifier que le professeur est affecté à cette classe
    from ..model.affectation_model import AffectationProfesseur
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=presence.classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas autorisé à modifier cette présence.")
        return redirect('enseignant:detail_eleve', eleve_id=eleve.id)
    
    # Vérifier que la liste de présence n'est pas validée
    liste_presence = ListePresence.objects.filter(
        classe=presence.classe,
        date=presence.date
    ).first()
    
    if liste_presence and liste_presence.validee:
        messages.warning(request, "Impossible de modifier une liste de présence déjà validée.")
        return redirect('enseignant:detail_eleve', eleve_id=eleve.id)
    
    # Modifier le statut
    nouveau_statut = request.POST.get('statut')
    if nouveau_statut in ['present', 'absent', 'retard', 'absent_justifie']:
        ancien_statut = presence.statut
        presence.statut = nouveau_statut
        presence.save()
        
        # Recalculer les statistiques de la liste
        if liste_presence:
            liste_presence.calculer_statistiques()
        
        messages.success(
            request,
            f"Présence modifiée : {presence.get_statut_display()}"
        )
    else:
        messages.error(request, "Statut invalide.")
    
    from django.http import HttpResponseRedirect
    from django.urls import reverse
    url = reverse('enseignant:detail_eleve', kwargs={'eleve_id': eleve.id}) + '?onglet=presences'
    return HttpResponseRedirect(url)


def historique_presence_eleve(request, eleve_id):
    """
    Page d'historique complet des présences/absences d'un élève
    Permet de justifier les absences
    """
    logger.info(f"Historique présence - User: {request.user}, Élève ID: {eleve_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.presence_model import Presence
    from django.shortcuts import get_object_or_404
    from datetime import date, timedelta
    
    # Récupérer l'élève
    eleve = get_object_or_404(Eleve, id=eleve_id, actif=True)
    classe = eleve.classe
    
    # Vérifier que le professeur est affecté à cette classe
    from ..model.affectation_model import AffectationProfesseur
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer toutes les présences de l'élève (par défaut: année scolaire)
    # Pour l'année scolaire sénégalaise: septembre → juin
    today = date.today()
    if today.month >= 9:
        debut_annee = date(today.year, 9, 1)
        fin_annee = date(today.year + 1, 6, 30)
    else:
        debut_annee = date(today.year - 1, 9, 1)
        fin_annee = date(today.year, 6, 30)
    
    # Récupération avec option de filtrage
    periode_filtree = request.GET.get('periode', 'annee')
    
    if periode_filtree == '30jours':
        date_debut = today - timedelta(days=30)
        presences = Presence.objects.filter(
            eleve=eleve,
            date__gte=date_debut
        ).order_by('-date')
    elif periode_filtree == '7jours':
        date_debut = today - timedelta(days=7)
        presences = Presence.objects.filter(
            eleve=eleve,
            date__gte=date_debut
        ).order_by('-date')
    else:  # annee
        presences = Presence.objects.filter(
            eleve=eleve,
            date__gte=debut_annee,
            date__lte=fin_annee
        ).order_by('-date')
    
    # Statistiques globales
    total_presences = presences.count()
    nombre_presents = presences.filter(statut='present').count()
    nombre_absences = presences.filter(statut='absent').count()
    nombre_absences_justifiees = presences.filter(statut='absent_justifie').count()
    nombre_retards = presences.filter(statut='retard').count()
    
    # Absences non justifiées (statut = 'absent' ET pas de type_justificatif)
    absences_non_justifiees = presences.filter(
        statut='absent',
        type_justificatif__isnull=True
    ).order_by('-date')
    
    # Taux de présence
    taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
    
    context = {
        'professeur': professeur,
        'eleve': eleve,
        'classe': classe,
        'presences': presences,
        'absences_non_justifiees': absences_non_justifiees,
        'total_presences': total_presences,
        'nombre_presents': nombre_presents,
        'nombre_absences': nombre_absences,
        'nombre_absences_justifiees': nombre_absences_justifiees,
        'nombre_retards': nombre_retards,
        'taux_presence': taux_presence,
        'periode_filtree': periode_filtree,
        'TYPE_JUSTIFICATIF_CHOICES': Presence.TYPE_JUSTIFICATIF_CHOICES,
    }
    
    return render(request, 'school_admin/enseignant/historique_presence_eleve.html', context)


def justifier_absence_eleve(request):
    """
    Traite le formulaire de justification d'absence
    """
    logger.info(f"Justification absence - User: {request.user}")
    
    if request.method != 'POST':
        messages.error(request, "Méthode non autorisée.")
        return redirect('enseignant:gestion_eleves')
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.presence_model import Presence
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    
    # Récupérer les données du formulaire
    presence_id = request.POST.get('presence_id')
    type_justificatif = request.POST.get('type_justificatif')
    
    if not presence_id or not type_justificatif:
        messages.error(request, "Données manquantes.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer la présence
    presence = get_object_or_404(Presence, id=presence_id)
    eleve = presence.eleve
    
    # Vérifier que le professeur est affecté à cette classe
    from ..model.affectation_model import AffectationProfesseur
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=presence.classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas autorisé à justifier cette absence.")
        return redirect('enseignant:historique_presence', eleve_id=eleve.id)
    
    # Vérifier que c'est bien une absence non justifiée
    if presence.statut != 'absent':
        messages.warning(request, "Cette présence n'est pas une absence.")
        return redirect('enseignant:historique_presence', eleve_id=eleve.id)
    
    if presence.type_justificatif:
        messages.warning(request, "Cette absence a déjà été justifiée.")
        return redirect('enseignant:historique_presence', eleve_id=eleve.id)
    
    # Enregistrer la justification
    try:
        presence.type_justificatif = type_justificatif
        presence.statut = 'absent_justifie'
        presence.justificatif_valide = True
        presence.date_justification = timezone.now()
        presence.save()
        
        logger.info(f"Absence justifiée - Élève: {eleve.nom_complet}, Date: {presence.date}, Type: {type_justificatif}")
        messages.success(
            request,
            f"Absence du {presence.date.strftime('%d/%m/%Y')} justifiée avec succès : {presence.get_type_justificatif_display()}"
        )
    except Exception as e:
        logger.error(f"Erreur justification absence: {str(e)}")
        messages.error(request, f"Erreur lors de la justification : {str(e)}")
    
    from django.http import HttpResponseRedirect
    from django.urls import reverse
    url = reverse('enseignant:historique_presence', kwargs={'eleve_id': eleve.id})
    return HttpResponseRedirect(url)


def detail_classe_enseignant(request, classe_id):
    """
    Page de détails complets d'une classe pour un enseignant
    Affiche toutes les informations : élèves, statistiques, évaluations, etc.
    """
    logger.info(f"Détails classe - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Evaluation
    from ..model.affectation_model import AffectationProfesseur
    from ..model.presence_model import Presence, ListePresence
    from django.shortcuts import get_object_or_404
    from django.db.models import Count, Q, Avg
    from datetime import date, timedelta
    
    # Récupérer l'onglet actif (pour restauration après filtrage)
    onglet_actif = request.GET.get('onglet', 'eleves')
    
    # Récupérer le paramètre matière si présent
    matiere_id = request.GET.get('matiere')
    matiere_selectionnee = None
    if matiere_id:
        from ..model.matiere_model import Matiere
        try:
            matiere_selectionnee = Matiere.objects.get(id=matiere_id)
        except Matiere.DoesNotExist:
            pass
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier que le professeur est affecté à cette classe
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Si une matière est spécifiée, filtrer par matière
    if matiere_selectionnee:
        affectation = affectations.filter(matiere=matiere_selectionnee).first()
    else:
        affectation = affectations.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_classes')
    
    # Déterminer la matière à utiliser pour le filtrage
    matiere_enseignee = matiere_selectionnee if matiere_selectionnee else (affectation.matiere if affectation.matiere else None)
    
    # === STATISTIQUES GÉNÉRALES ===
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    nombre_eleves = eleves.count()
    taux_occupation = round((nombre_eleves / classe.capacite_max * 100), 1) if classe.capacite_max > 0 else 0
    
    # Répartition par genre
    nombre_garcons = eleves.filter(sexe='M').count()
    nombre_filles = eleves.filter(sexe='F').count()
    
    # === STATISTIQUES DE PRÉSENCE ===
    today = date.today()
    debut_mois = date(today.year, today.month, 1)
    
    # Filtre par mois (GET parameter)
    mois_filtre = request.GET.get('mois', str(today.month))
    annee_filtre = request.GET.get('annee', str(today.year))
    
    try:
        mois_filtre = int(mois_filtre)
        annee_filtre = int(annee_filtre)
    except (ValueError, TypeError):
        mois_filtre = today.month
        annee_filtre = today.year
    
    # Calculer le premier et dernier jour du mois filtré
    from calendar import monthrange
    premier_jour_mois = date(annee_filtre, mois_filtre, 1)
    dernier_jour_mois = date(annee_filtre, mois_filtre, monthrange(annee_filtre, mois_filtre)[1])
    
    # Présences du mois filtré
    # IMPORTANT : Filtrer selon le rôle du professeur
    if affectation.is_principal:
        # Professeur principal : voir TOUTES les présences de la classe
        presences_mois = Presence.objects.filter(
            classe=classe,
            date__gte=premier_jour_mois,
            date__lte=dernier_jour_mois
        )
    else:
        # Professeur classique : voir uniquement SES présences pour SA matière
        filters_pres = {
            'classe': classe,
            'professeur': professeur,
            'date__gte': premier_jour_mois,
            'date__lte': dernier_jour_mois
        }
        if matiere_enseignee:
            filters_pres['matiere'] = matiere_enseignee
        else:
            filters_pres['matiere__isnull'] = True
        
        presences_mois = Presence.objects.filter(**filters_pres)
    
    total_presences_mois = presences_mois.count()
    nombre_presents_mois = presences_mois.filter(statut='present').count()
    nombre_absences_mois = presences_mois.filter(statut='absent').count()
    nombre_absences_justifiees_mois = presences_mois.filter(statut='absent_justifie').count()
    nombre_retards_mois = presences_mois.filter(statut='retard').count()
    
    taux_presence_mois = round((nombre_presents_mois / total_presences_mois * 100), 1) if total_presences_mois > 0 else 0
    
    # Listes de présence validées du mois filtré
    listes_presence_validees = ListePresence.objects.filter(
        classe=classe,
        validee=True,
        date__gte=premier_jour_mois,
        date__lte=dernier_jour_mois
    )
    # Filtrer par matière si spécifiée
    if matiere_enseignee:
        listes_presence_validees = listes_presence_validees.filter(matiere=matiere_enseignee)
    listes_presence_validees = listes_presence_validees.order_by('-date')
    
    # Générer la liste des mois avec des présences (filtré par matière et rôle)
    # IMPORTANT : Afficher uniquement les mois qui ont des données
    if affectation.is_principal:
        # Professeur principal : tous les mois avec des présences dans la classe
        mois_avec_presences = Presence.objects.filter(
            classe=classe
        ).dates('date', 'month', order='DESC')
    else:
        # Professeur classique : uniquement les mois avec SES présences pour SA matière
        filters_mois = {
            'classe': classe,
            'professeur': professeur
        }
        if matiere_enseignee:
            filters_mois['matiere'] = matiere_enseignee
        else:
            filters_mois['matiere__isnull'] = True
        
        mois_avec_presences = Presence.objects.filter(**filters_mois).dates('date', 'month', order='DESC')
    
    mois_disponibles = []
    for date_mois in mois_avec_presences:
        mois_disponibles.append({
            'mois': date_mois.month,
            'annee': date_mois.year,
            'nom': date_mois.strftime('%B %Y'),
            'nom_court': date_mois.strftime('%b %Y')
        })
    
    # === STATISTIQUES DES ÉVALUATIONS ===
    # Récupérer toutes les périodes scolaires actives
    from ..model.periode_model import PeriodeScolaire
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Filtre par période (GET parameter)
    periode_eval_id = request.GET.get('periode_eval', '')
    periode_eval_active = None
    
    # Si "toutes" est spécifié, on ne filtre pas par période
    if periode_eval_id == 'toutes':
        periode_eval_active = None
    # Si une période ID est spécifiée, la récupérer
    elif periode_eval_id:
        try:
            periode_eval_active = periodes_scolaires.get(id=periode_eval_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    # Sinon, utiliser la période en cours par défaut
    elif periodes_scolaires.exists():
        for periode in periodes_scolaires:
            if periode.est_en_cours:
                periode_eval_active = periode
                break
        if not periode_eval_active:
            periode_eval_active = periodes_scolaires.first()
    
    evaluations = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        actif=True
    )
    
    # Filtrer par matière si spécifiée
    if matiere_enseignee:
        evaluations = evaluations.filter(matiere=matiere_enseignee)
    
    # Filtrer par période si spécifiée
    if periode_eval_active:
        evaluations = evaluations.filter(periode_scolaire=periode_eval_active)
    
    evaluations = evaluations.select_related('matiere', 'periode_scolaire').order_by('-date_evaluation')
    
    nombre_evaluations_total = evaluations.count()
    nombre_evaluations_mois = evaluations.filter(
        date_evaluation__gte=debut_mois,
        date_evaluation__lte=today
    ).count()
    
    # Dernières évaluations (filtrées)
    dernieres_evaluations = evaluations.filter(date_evaluation__lt=today).order_by('-date_evaluation')[:5]
    
    # Prochaines évaluations (filtrées)
    prochaines_evaluations = evaluations.filter(date_evaluation__gte=today).order_by('date_evaluation')[:5]
    
    # === ÉLÈVES AVEC STATISTIQUES ===
    eleves_avec_stats = []
    for eleve in eleves:
        # Absences
        # IMPORTANT : Filtrer par matière et par professeur selon le rôle
        if affectation.is_principal:
            # Professeur principal : voir TOUTES les absences de la classe
            absences_queryset = Presence.objects.filter(
                eleve=eleve,
                classe=classe,
                statut='absent'
            )
        else:
            # Professeur classique : voir uniquement SES absences pour SA matière
            filters_abs = {
                'eleve': eleve,
                'classe': classe,
                'professeur': professeur,
                'statut': 'absent'
            }
            if matiere_enseignee:
                filters_abs['matiere'] = matiere_enseignee
            else:
                filters_abs['matiere__isnull'] = True
            
            absences_queryset = Presence.objects.filter(**filters_abs)
        
        nombre_absences = absences_queryset.count()
        
        # Moyennes (dernière période)
        from ..model.moyenne_model import Moyenne
        moyenne_queryset = Moyenne.objects.filter(
            eleve=eleve,
            professeur=professeur,
            actif=True
        )
        if matiere_enseignee:
            moyenne_queryset = moyenne_queryset.filter(matiere=matiere_enseignee)
        derniere_moyenne = moyenne_queryset.order_by('-date_calcul').first()
        
        # Notes
        from ..model.evaluation_model import Note
        notes_queryset = Note.objects.filter(
            eleve=eleve,
            evaluation__professeur=professeur
        )
        if matiere_enseignee:
            notes_queryset = notes_queryset.filter(matiere=matiere_enseignee)
        nombre_notes = notes_queryset.count()
        
        eleves_avec_stats.append({
            'eleve': eleve,
            'nombre_absences': nombre_absences,
            'derniere_moyenne': derniere_moyenne.moyenne if derniere_moyenne else None,
            'nombre_notes': nombre_notes
        })
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'matiere': matiere_enseignee,
        'eleves': eleves_avec_stats,
        'onglet_actif': onglet_actif,
        
        # Statistiques générales
        'nombre_eleves': nombre_eleves,
        'nombre_garcons': nombre_garcons,
        'nombre_filles': nombre_filles,
        'taux_occupation': taux_occupation,
        
        # Statistiques de présence
        'total_presences_mois': total_presences_mois,
        'nombre_presents_mois': nombre_presents_mois,
        'nombre_absences_mois': nombre_absences_mois,
        'nombre_absences_justifiees_mois': nombre_absences_justifiees_mois,
        'nombre_retards_mois': nombre_retards_mois,
        'taux_presence_mois': taux_presence_mois,
        'listes_presence_validees': listes_presence_validees,
        'mois_disponibles': mois_disponibles,
        'mois_filtre': mois_filtre,
        'annee_filtre': annee_filtre,
        
        # Statistiques des évaluations
        'nombre_evaluations_total': nombre_evaluations_total,
        'nombre_evaluations_mois': nombre_evaluations_mois,
        'dernieres_evaluations': dernieres_evaluations,
        'prochaines_evaluations': prochaines_evaluations,
        'periodes_scolaires_eval': periodes_scolaires,
        'periode_eval_active': periode_eval_active,
    }
    
    return render(request, 'school_admin/enseignant/detail_classe.html', context)


def soumettre_sanction_eleve(request):
    """
    Traite le formulaire de soumission d'une sanction
    """
    logger.info(f"Soumission sanction - User: {request.user}")
    
    if request.method != 'POST':
        messages.error(request, "Méthode non autorisée.")
        return redirect('enseignant:gestion_eleves')
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.classe_model import Classe
    from ..model.sanction_model import Sanction
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from datetime import datetime
    
    # Récupérer les données du formulaire
    eleve_id = request.POST.get('eleve_id')
    classe_id = request.POST.get('classe_id')
    type_sanction = request.POST.get('type_sanction')
    raison = request.POST.get('raison')
    gravite = request.POST.get('gravite', 'moyenne')
    description = request.POST.get('description', '')
    date_sanction_str = request.POST.get('date_sanction')
    
    # Validation des données
    if not all([eleve_id, classe_id, type_sanction, raison, date_sanction_str]):
        messages.error(request, "Données manquantes.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer l'élève et la classe
    eleve = get_object_or_404(Eleve, id=eleve_id, actif=True)
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier que le professeur est affecté à cette classe
    from ..model.affectation_model import AffectationProfesseur
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas autorisé à sanctionner cet élève.")
        return redirect('enseignant:gestion_eleves')
    
    # Convertir la date
    try:
        date_sanction = datetime.strptime(date_sanction_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, "Format de date invalide.")
        return redirect('enseignant:gestion_eleves')
    
    # Créer la sanction
    try:
        sanction = Sanction.objects.create(
            eleve=eleve,
            classe=classe,
            professeur=professeur,
            etablissement=classe.etablissement,
            type_sanction=type_sanction,
            raison=raison,
            gravite=gravite,
            description=description,
            date_sanction=date_sanction
        )
        
        logger.info(f"Sanction créée - Élève: {eleve.nom_complet}, Type: {type_sanction}, Raison: {raison}")
        messages.success(
            request,
            f"Sanction '{sanction.get_type_sanction_display()}' enregistrée avec succès pour {eleve.nom_complet}."
        )
        
        # Envoyer les notifications push
        try:
            from school_admin.services.firebase_service import FirebaseService
            
            # Déterminer le message selon la gravité
            if gravite == 'tres_grave':
                emoji = "🚨"
                gravite_texte = "très grave"
            elif gravite == 'grave':
                emoji = "⚠️"
                gravite_texte = "grave"
            elif gravite == 'moyenne':
                emoji = "⚡"
                gravite_texte = "moyenne"
            else:
                emoji = "📋"
                gravite_texte = "légère"

            # Notification élève
            eleve_title = f"{emoji} Sanction disciplinaire"
            eleve_body = f"Vous avez reçu une sanction de gravité {gravite_texte} : {sanction.get_type_sanction_display()}"
            eleve_data = {
                'type': 'sanction',
                'sanction_id': str(sanction.id),
                'type_sanction': type_sanction,
                'raison': raison,
                'gravite': gravite,
                'date': date_sanction.isoformat(),
                'url': '/eleve/dashboard/'
            }

            eleve_result = FirebaseService.send_notification_to_multiple_users(
                [eleve], eleve_title, eleve_body, eleve_data
            )

            if eleve_result['success_count'] > 0:
                logger.info(f"Notification de sanction envoyée à {eleve.nom_complet}")
            else:
                logger.warning(f"Échec de l'envoi de notification de sanction à {eleve.nom_complet}")

            try:
                EleveNotificationService.notify_sanction(eleve, sanction)
            except Exception:
                logger.exception(
                    "Échec notification élève %s pour sanction", getattr(eleve, "id", "N/A")
                )

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi des notifications de sanction: {str(e)}")

        try:
            DirecteurNotificationService.notify_sanction(sanction)
        except Exception as notification_error:
            logger.error(
                "Erreur lors de la notification directeur pour la sanction: %s",
                notification_error,
                exc_info=True,
            )

        try:
            ParentNotificationService.notify_sanction(sanction)
        except Exception as notification_error:
            logger.error(
                "Erreur lors de la notification parent pour la sanction (collège/lycée): %s",
                notification_error,
                exc_info=True,
            )
        
    except Exception as e:
        logger.error(f"Erreur création sanction: {str(e)}")
        messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
    
    return redirect('enseignant:gestion_eleves')


def historique_sanctions_eleve(request, eleve_id):
    """
    Page d'historique complet des sanctions d'un élève
    """
    logger.info(f"Historique sanctions - User: {request.user}, Élève ID: {eleve_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.eleve_model import Eleve
    from ..model.sanction_model import Sanction
    from django.shortcuts import get_object_or_404
    
    # Récupérer l'élève
    eleve = get_object_or_404(Eleve, id=eleve_id, actif=True)
    classe = eleve.classe
    
    # Vérifier que le professeur est affecté à cette classe
    from ..model.affectation_model import AffectationProfesseur
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer toutes les sanctions de l'élève
    sanctions = Sanction.objects.filter(eleve=eleve).order_by('-date_sanction', '-date_creation')
    
    # Statistiques
    total_sanctions = sanctions.count()
    sanctions_legeres = sanctions.filter(gravite='legere').count()
    sanctions_moyennes = sanctions.filter(gravite='moyenne').count()
    sanctions_graves = sanctions.filter(gravite='grave').count()
    sanctions_tres_graves = sanctions.filter(gravite='tres_grave').count()
    
    # Sanctions par type
    sanctions_par_type = {}
    for type_code, type_nom in Sanction.TYPE_SANCTION_CHOICES:
        count = sanctions.filter(type_sanction=type_code).count()
        if count > 0:
            sanctions_par_type[type_nom] = count
    
    context = {
        'professeur': professeur,
        'eleve': eleve,
        'classe': classe,
        'sanctions': sanctions,
        'total_sanctions': total_sanctions,
        'sanctions_legeres': sanctions_legeres,
        'sanctions_moyennes': sanctions_moyennes,
        'sanctions_graves': sanctions_graves,
        'sanctions_tres_graves': sanctions_tres_graves,
        'sanctions_par_type': sanctions_par_type,
    }
    
    return render(request, 'school_admin/enseignant/historique_sanctions_eleve.html', context)


def liste_sanctions_classe(request, classe_id):
    """
    Page de la liste de toutes les sanctions d'une classe
    """
    logger.info(f"Liste sanctions classe - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.classe_model import Classe
    from ..model.sanction_model import Sanction
    from django.shortcuts import get_object_or_404
    from django.db.models import Count
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier que le professeur est affecté à cette classe
    from ..model.affectation_model import AffectationProfesseur
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer toutes les sanctions de la classe
    sanctions = Sanction.objects.filter(
        classe=classe
    ).select_related('eleve', 'professeur').order_by('-date_sanction', '-date_creation')
    
    # Statistiques globales
    total_sanctions = sanctions.count()
    sanctions_legeres = sanctions.filter(gravite='legere').count()
    sanctions_moyennes = sanctions.filter(gravite='moyenne').count()
    sanctions_graves = sanctions.filter(gravite='grave').count()
    sanctions_tres_graves = sanctions.filter(gravite='tres_grave').count()
    
    # Sanctions par type
    sanctions_par_type = {}
    for type_code, type_nom in Sanction.TYPE_SANCTION_CHOICES:
        count = sanctions.filter(type_sanction=type_code).count()
        if count > 0:
            sanctions_par_type[type_nom] = count
    
    # Sanctions par élève (top 5)
    from ..model.eleve_model import Eleve
    eleves_sanctions = sanctions.values('eleve').annotate(
        nombre=Count('id')
    ).order_by('-nombre')[:5]
    
    top_eleves_sanctions = []
    for item in eleves_sanctions:
        eleve = Eleve.objects.get(id=item['eleve'])
        top_eleves_sanctions.append({
            'eleve': eleve,
            'nombre_sanctions': item['nombre']
        })
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'sanctions': sanctions,
        'total_sanctions': total_sanctions,
        'sanctions_legeres': sanctions_legeres,
        'sanctions_moyennes': sanctions_moyennes,
        'sanctions_graves': sanctions_graves,
        'sanctions_tres_graves': sanctions_tres_graves,
        'sanctions_par_type': sanctions_par_type,
        'top_eleves_sanctions': top_eleves_sanctions,
    }
    
    return render(request, 'school_admin/enseignant/liste_sanctions_classe.html', context)


def parametres_profil_enseignant(request):
    """
    Page des paramètres du profil de l'enseignant
    """
    logger.info(f"Paramètres profil - User: {request.user}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Gestion POST pour mise à jour des informations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_info':
            # Mise à jour des informations personnelles
            telephone = request.POST.get('telephone')
            adresse = request.POST.get('adresse')
            
            if telephone:
                professeur.telephone = telephone
            if adresse:
                professeur.adresse = adresse
            
            professeur.save()
            messages.success(request, "Informations mises à jour avec succès.")
            logger.info(f"Infos mises à jour - Professeur: {professeur.nom_complet}")
            
        elif action == 'change_password':
            # Changement de mot de passe
            from django.contrib.auth.hashers import check_password, make_password
            
            old_password = request.POST.get('old_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            if not old_password or not new_password or not confirm_password:
                messages.error(request, "Tous les champs sont requis.")
            elif not check_password(old_password, professeur.password):
                messages.error(request, "L'ancien mot de passe est incorrect.")
            elif new_password != confirm_password:
                messages.error(request, "Les nouveaux mots de passe ne correspondent pas.")
            elif len(new_password) < 6:
                messages.error(request, "Le mot de passe doit contenir au moins 6 caractères.")
            else:
                professeur.password = make_password(new_password)
                professeur.save()
                messages.success(request, "Mot de passe modifié avec succès.")
                logger.info(f"Mot de passe changé - Professeur: {professeur.nom_complet}")
        
        return redirect('enseignant:parametres_profil')
    
    # Statistiques
    from ..model.affectation_model import AffectationProfesseur
    from ..model.evaluation_model import Evaluation, Note
    from ..model.sanction_model import Sanction
    from django.db.models import Count
    
    nombre_classes = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).count()
    
    nombre_evaluations = Evaluation.objects.filter(
        professeur=professeur,
        actif=True
    ).count()
    
    nombre_notes = Note.objects.filter(
        evaluation__professeur=professeur
    ).count()
    
    nombre_sanctions = Sanction.objects.filter(
        professeur=professeur
    ).count()
    
    # Dernières activités
    dernieres_evaluations = Evaluation.objects.filter(
        professeur=professeur,
        actif=True
    ).order_by('-date_creation')[:5]
    
    context = {
        'professeur': professeur,
        'nombre_classes': nombre_classes,
        'nombre_evaluations': nombre_evaluations,
        'nombre_notes': nombre_notes,
        'nombre_sanctions': nombre_sanctions,
        'dernieres_evaluations': dernieres_evaluations,
    }
    
    return render(request, 'school_admin/enseignant/parametres_profil.html', context)


def emploi_du_temps_enseignant(request):
    """
    Page affichant l'emploi du temps du professeur
    """
    logger.info(f"Emploi du temps - User: {request.user}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Récupérer toutes les classes du professeur
    from ..model.affectation_model import AffectationProfesseur
    from ..model.emploi_du_temps_model import EmploiDuTemps, CreneauEmploiDuTemps
    from collections import defaultdict
    
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe')
    
    # Récupérer tous les créneaux du professeur
    classes_ids = affectations.values_list('classe', flat=True)
    emplois_actifs = EmploiDuTemps.objects.filter(classe__in=classes_ids, est_actif=True)
    emplois_publies = emplois_actifs.filter(statut_publication='publie')
    emploi_publie_disponible = emplois_publies.exists()
    
    if emploi_publie_disponible:
        creneaux_professeur = CreneauEmploiDuTemps.objects.filter(
            professeur=professeur,
            emploi_du_temps__in=emplois_publies
        ).select_related('emploi_du_temps', 'emploi_du_temps__classe', 'matiere', 'salle', 'periode_etablissement').order_by('jour', 'periode_etablissement__ordre', 'heure_debut')
    else:
        creneaux_professeur = CreneauEmploiDuTemps.objects.none()
    
    # Récupérer la configuration horaire de l'établissement
    from ..model.configuration_horaire_model import ConfigurationHoraire, PeriodeEtablissement
    from ..controllers.emploi_du_temps_controller import get_matiere_config
    config_horaire = ConfigurationHoraire.objects.filter(etablissement=professeur.etablissement, actif=True).first()
    
    # Organiser les créneaux par période et par jour (comme dans le contrôleur directeur)
    jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
    
    periodes_affichage = []
    
    if config_horaire:
        # Utiliser les périodes de l'établissement
        periodes = config_horaire.periodes.filter(actif=True).order_by('ordre')
        
        # Créer un dictionnaire pour regrouper les créneaux par groupe_creneau
        creneaux_groupes = {}
        for creneau in creneaux_professeur:
            if creneau.groupe_creneau:
                if creneau.groupe_creneau not in creneaux_groupes:
                    creneaux_groupes[creneau.groupe_creneau] = []
                creneaux_groupes[creneau.groupe_creneau].append(creneau)
        
        for periode in periodes:
            periode_info = {
                'nom': periode.nom,
                'heure_debut': periode.heure_debut,
                'heure_fin': periode.heure_fin,
                'duree': periode.duree_minutes,
                'est_pause': periode.est_pause,
                'type_periode': periode.type_periode,
                'creneaux_par_jour': {},
            }
            
            # Pour chaque jour, trouver le créneau correspondant à cette période
            for jour in jours_semaine:
                if periode.est_pause:
                    # C'est une pause: créer un créneau virtuel
                    periode_info['creneaux_par_jour'][jour] = {
                        'est_pause': True,
                        'est_virtual': True,
                        'nom_pause': periode.nom,
                        'type_periode': periode.type_periode
                    }
                else:
                    # Chercher un créneau qui utilise cette période
                    creneau = creneaux_professeur.filter(
                        jour=jour,
                        periode_etablissement=periode
                    ).first()
                    
                    if creneau:
                        # Pour les créneaux groupés, on affiche le premier créneau dans toutes les périodes du groupe
                        if creneau.groupe_creneau:
                            groupe_creneaux = creneaux_groupes.get(creneau.groupe_creneau, [])
                            groupe_creneaux_jour = [c for c in groupe_creneaux if c.jour == jour]
                            groupe_creneaux_jour.sort(key=lambda c: c.periode_etablissement.ordre)
                            
                            if groupe_creneaux_jour:
                                creneau = groupe_creneaux_jour[0]
                        
                        # Ajouter icône et couleur au créneau
                        matiere_nom = creneau.matiere.nom if creneau.matiere else "Sans matière"
                        icone, couleur = get_matiere_config(matiere_nom)
                        creneau.matiere_icone = icone
                        creneau.matiere_couleur = couleur
                        
                        periode_info['creneaux_par_jour'][jour] = creneau
                    else:
                        periode_info['creneaux_par_jour'][jour] = None
            
            periodes_affichage.append(periode_info)
    
    # Statistiques
    total_heures = 0
    for creneau in creneaux_professeur:
        total_heures += creneau.duree_minutes / 60
    
    nombre_classes = affectations.count()
    nombre_creneaux = creneaux_professeur.count()
    
    context = {
        'professeur': professeur,
        'jours_semaine': jours_semaine,
        'periodes_affichage': periodes_affichage,
        'config_horaire': config_horaire,
        'nombre_classes': nombre_classes,
        'nombre_creneaux': nombre_creneaux,
        'total_heures': round(total_heures, 1),
        'etablissement': professeur.etablissement,
        'emploi_publie': emploi_publie_disponible,
        'emploi_non_publie': (not emploi_publie_disponible) and emplois_actifs.exists(),
    }
    
    return render(request, 'school_admin/enseignant/emploi_du_temps.html', context)


def imprimer_tableau_presence_enseignant(request, classe_id):
    """
    Génère un tableau de présence hebdomadaire imprimable pour une classe et matière spécifique.
    Format : Semaine du lundi au vendredi avec compteurs P/A/R
    """
    from ..model.classe_model import Classe
    from ..model.matiere_model import Matiere
    from ..model.affectation_model import AffectationProfesseur
    from ..model.eleve_model import Eleve
    from ..model.presence_model import Presence
    from collections import defaultdict
    from datetime import date, timedelta
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Redirection pour les professeurs primaires
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        return redirect('enseignant_primaire:imprimer_tableau_presence', classe_id=classe_id)
    
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Récupérer la matière depuis les paramètres GET
    matiere_id = request.GET.get('matiere', None)
    matiere = None
    if matiere_id:
        matiere = get_object_or_404(Matiere, id=matiere_id)
    
    # Vérifier que le professeur enseigne cette matière à cette classe
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        matiere=matiere,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'enseignez pas cette matière à cette classe.")
        return redirect('enseignant:gestion_presence')
    
    # Déterminer la semaine à afficher (semaine en cours par défaut)
    today = date.today()
    
    # Calculer le lundi de la semaine en cours
    lundi = today - timedelta(days=today.weekday())
    samedi = lundi + timedelta(days=5)
    
    # Récupérer les élèves
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les présences de la semaine pour tous les élèves
    # IMPORTANT : Si professeur principal → voir TOUTES les présences, sinon uniquement les siennes
    # IMPORTANT : Filtrer par matière
    if affectation.is_principal:
        # Professeur principal : voir TOUTES les présences de la classe (toutes matières)
        presences_semaine = Presence.objects.filter(
            classe=classe,
            date__gte=lundi,
            date__lte=samedi
        ).select_related('eleve')
    else:
        # Professeur classique : voir uniquement SES présences pour SA matière
        filters_impression = {
            'classe': classe,
            'professeur': professeur,
            'date__gte': lundi,
            'date__lte': samedi
        }
        if matiere:
            filters_impression['matiere'] = matiere
        else:
            filters_impression['matiere__isnull'] = True
        
        presences_semaine = Presence.objects.filter(**filters_impression).select_related('eleve')
    
    # Organiser les présences par élève et par date
    presences_dict = defaultdict(lambda: defaultdict(list))
    for presence in presences_semaine:
        presences_dict[presence.eleve.id][presence.date].append(presence)
    
    # Préparer les données pour chaque élève
    eleves_data = []
    for eleve in eleves:
        eleve_presences = {}
        total_absences = 0
        
        # Pour chaque jour de la semaine (lundi à samedi)
        for i in range(6):
            jour = lundi + timedelta(days=i)
            jour_presences = presences_dict[eleve.id].get(jour, [])
            
            # Compter les statuts pour le jour
            nb_presents = 0
            nb_absents = 0
            nb_retards = 0
            
            for presence in jour_presences:
                if presence.statut == 'present':
                    nb_presents += 1
                elif presence.statut in ['absent', 'absent_justifie']:
                    nb_absents += 1
                    total_absences += 1
                elif presence.statut == 'retard':
                    nb_retards += 1
            
            eleve_presences[i] = {
                'presents': nb_presents,
                'absents': nb_absents,
                'retards': nb_retards
            }
        
        eleves_data.append({
            'eleve': eleve,
            'presences': eleve_presences,
            'total_absences': total_absences
        })
    
    classes_data = [{
        'classe': classe,
        'matiere': matiere,
        'eleves': eleves_data
    }]
    
    # Jours de la semaine (lundi à samedi)
    jours_semaine = []
    jours_noms = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi']
    for i in range(6):
        jour = lundi + timedelta(days=i)
        jours_semaine.append({
            'nom': jours_noms[i],
            'date': jour,
            'index': i
        })
    
    context = {
        'professeur': professeur,
        'classes_data': classes_data,
        'lundi': lundi,
        'samedi': samedi,
        'jours_semaine': jours_semaine,
        'date_impression': today,
    }
    
    return render(request, 'school_admin/enseignant/imprimer_tableau_presence.html', context)


def notifications_enseignant(request):
    """Affiche les notifications reçues par l'enseignant."""
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    from django.utils import timezone

    enseignant = request.user

    notifications = list(
        NotificationEnseignant.objects.filter(enseignant=enseignant)
        .order_by('-date_creation')
    )
    notification_ids = [notification.id for notification in notifications]

    if notification_ids:
        NotificationEnseignant.objects.filter(id__in=notification_ids).update(
            statut='lu',
            date_lecture=timezone.now(),
            date_modification=timezone.now(),
        )

    notifications_non_lues = NotificationEnseignant.objects.filter(
        enseignant=enseignant, statut='non_lu'
    ).count()

    context = {
        'professeur': enseignant,
        'notifications': notifications,
        'notifications_enseignant_non_lues': notifications_non_lues,
    }

    response = render(
        request,
        'school_admin/enseignant/notifications_enseignant.html',
        context,
    )

    if notification_ids:
        NotificationEnseignant.objects.filter(id__in=notification_ids).delete()

    return response


def annonces_enseignant(request):
    """Affiche toutes les annonces publiées destinées à l'enseignant."""
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    enseignant = request.user

    from ..model.annonce_model import Annonce
    from django.db.models import Q

    annonces = (
        Annonce.objects.filter(
            etablissement=enseignant.etablissement,
            statut='publiee',
            actif=True,
        )
        .filter(
            Q(destinataires__contains=['tous']) |
            Q(destinataires__contains=['enseignants'])
        )
        .select_related('auteur_personnel', 'auteur_directeur')
        .order_by('-date_publication', '-date_creation')
    )

    context = {
        'professeur': enseignant,
        'annonces': annonces,
    }

    return render(request, 'school_admin/enseignant/annonces_enseignant.html', context)

