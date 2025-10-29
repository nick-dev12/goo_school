# school_admin/personal_views/enseignant_view.py

from django.shortcuts import render, redirect
from django.contrib import messages
from ..decorators import login_required_with_redirect
from ..model.professeur_model import Professeur
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
    from ..model.emploi_du_temps_model import CreneauEmploiDuTemps
    from ..model.eleve_model import Eleve
    
    # ===== INDICATEURS CLÉS =====
    
    # 1. Classes assignées
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe').prefetch_related('classe__eleves')
    
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
    
    creneaux_aujourdhui = CreneauEmploiDuTemps.objects.filter(
        professeur=professeur,
        jour=jour_actuel
    ).select_related('emploi_du_temps__classe', 'matiere', 'salle', 'periode_etablissement').order_by('periode_etablissement__ordre', 'heure_debut')
    
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
    
    context = {
        'professeur': professeur,
        
        # Indicateurs
        'total_classes': total_classes,
        'total_eleves': total_eleves,
        'evaluations_a_venir': evaluations_a_venir,
        'messages_non_lus': messages_non_lus,
        
        # Classes
        'classes_data': classes_data,
        
        # Emploi du temps
        'jour_actuel': jour_actuel,
        'jour_actuel_display': jour_actuel.capitalize(),
        'date_actuelle': date_actuelle,
        'creneaux_aujourdhui': creneaux_aujourdhui,
        
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
        from ..model.presence_model import Presence
        from ..model.sanction_model import Sanction
        eleves_avec_absences = []
        for eleve in eleves:
            nombre_absences = Presence.get_nombre_absences(eleve)
            nombre_sanctions = Sanction.get_nombre_sanctions(eleve)
            eleves_avec_absences.append({
                'eleve': eleve,
                'nombre_absences': nombre_absences,
                'nombre_sanctions': nombre_sanctions
            })
        
        classe_data = {
            'classe': classe,
            'affectation': affectation,
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
        
        # Récupérer les moyennes pour cette classe et cette période
        # Note: Le système de moyennes utilise encore l'ancien format
        # On peut filtrer par date à la place si période_active_obj existe
        if periode_active_obj:
            moyennes = Moyenne.objects.filter(
                classe=classe,
                professeur=professeur,
                matiere=professeur.matiere_principale,
                actif=True
            ).select_related('eleve')
        else:
            moyennes = Moyenne.objects.none()
        
        # Créer un dictionnaire des moyennes par élève
        moyennes_par_eleve = {}
        for moy in moyennes:
            moyennes_par_eleve[moy.eleve.id] = moy
        
        # Ajouter les moyennes aux élèves
        eleves_avec_moyennes = []
        total_moyennes = 0
        count_moyennes = 0
        for eleve in eleves:
            moyenne_obj = moyennes_par_eleve.get(eleve.id)
            eleves_avec_moyennes.append({
                'eleve': eleve,
                'moyenne': moyenne_obj
            })
            if moyenne_obj:
                total_moyennes += float(moyenne_obj.moyenne)
                count_moyennes += 1
        
        # Calculer la moyenne de classe
        moyenne_classe = round(total_moyennes / count_moyennes, 2) if count_moyennes > 0 else None
        
        classe_data = {
            'classe': classe,
            'affectation': affectation,
            'eleves': eleves_avec_moyennes,
            'nombre_eleves': eleves.count(),
            'est_principal': affectation.is_principal,
            'moyenne_classe': moyenne_classe,
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
    affectation = get_object_or_404(
        AffectationProfesseur,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
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
    
    # Récupérer ou créer le relevé de notes pour cette classe/professeur/matière/période
    from ..model.releve_notes_model import ReleveNotes
    
    if periode_active_obj:
        releve_notes, created = ReleveNotes.objects.get_or_create(
            classe=classe,
            professeur=professeur,
            matiere=professeur.matiere_principale,
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
    if periode_active_obj:
        evaluations_interrogations = list(Evaluation.objects.filter(
            classe=classe,
            professeur=professeur,
            type_evaluation='interrogation',
            periode_scolaire=periode_active_obj,
            actif=True
        ).order_by('date_evaluation'))
        
        evaluations_devoirs = list(Evaluation.objects.filter(
            classe=classe,
            professeur=professeur,
            type_evaluation__in=['controle', 'devoir_maison'],
            periode_scolaire=periode_active_obj,
            actif=True
        ).order_by('date_evaluation'))
    else:
        evaluations_interrogations = []
        evaluations_devoirs = []
    
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
    moyennes_enregistrees = {}
    
    if periode_active_obj:
        # Récupérer les moyennes pour cette période (stockée en string avec l'ID)
        moyennes_db = Moyenne.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=professeur.matiere_principale,
            periode=str(periode_active_obj.id),
            actif=True
        )
        
        for moyenne in moyennes_db:
            moyennes_enregistrees[moyenne.eleve.id] = {
                'moyenne': float(moyenne.moyenne),
                'nombre_notes': moyenne.nombre_notes
            }
        
        logger.info(f"Moyennes chargées: {len(moyennes_enregistrees)} pour la période {periode_active_obj.nom_periode}")
    
    # Traitement du formulaire POST
    if request.method == 'POST':
        # Vérifier si le relevé est soumis (verrouillé)
        if releve_notes.soumis:
            messages.error(request, "Le relevé de notes a été soumis et ne peut plus être modifié.")
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
        
        logger.info(f"POST data: {request.POST}")
        
        # Vérifier qu'au moins une évaluation existe
        if not any(evaluations_map.values()):
            messages.error(request, "Vous devez d'abord créer au moins une évaluation avant de saisir des notes !")
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
        
        # Vérifier quelles colonnes sont sélectionnées
        colonnes_selectionnees = []
        for key in ['interro_1', 'interro_2', 'interro_3', 'devoir_1', 'devoir_2', 'devoir_3']:
            if request.POST.get(f'select_{key}') == 'on':
                colonnes_selectionnees.append(key)
        
        if not colonnes_selectionnees:
            messages.warning(request, "Veuillez sélectionner au moins une colonne de notes à saisir.")
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
        
        # Validation et enregistrement des notes
        errors = []
        notes_enregistrees = 0
        
        try:
            with transaction.atomic():
                for eleve in eleves:
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
                                
                                # Validation : ne pas saisir de notes /20 dans les interrogations
                                if colonne.startswith('interro') and note_decimal > 10:
                                    errors.append(f"{eleve.nom_complet} : Note trop élevée pour une interrogation (max 10)")
                                    continue
                                
                                # Validation : ne pas dépasser le barème
                                if note_decimal > evaluation.bareme:
                                    errors.append(f"{eleve.nom_complet} : Note supérieure au barème ({evaluation.bareme})")
                                    continue
                                
                                # Enregistrer ou mettre à jour la note
                                note_obj, created = Note.objects.update_or_create(
                                    eleve=eleve,
                                    evaluation=evaluation,
                                    defaults={
                                        'note': note_decimal,
                                        'absent': False
                                    }
                                )
                                notes_enregistrees += 1
                                
                            except (ValueError, Exception) as e:
                                logger.error(f"Erreur saisie note pour {eleve.nom_complet}: {str(e)}")
                                errors.append(f"{eleve.nom_complet} : Valeur invalide")
                
                if errors:
                    messages.warning(request, f"{notes_enregistrees} notes enregistrées. Erreurs : " + " | ".join(errors[:5]))
                else:
                    messages.success(request, f"✓ {notes_enregistrees} notes enregistrées avec succès !")
                
        except Exception as e:
            logger.error(f"Erreur transaction notes: {str(e)}")
            messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
        
        return redirect('enseignant:noter_eleves', classe_id=classe_id)
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'eleves': eleves,
        'matiere': professeur.matiere_principale,
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
    affectation = get_object_or_404(
        AffectationProfesseur,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
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
                    evaluation = Evaluation.objects.create(
                        titre=titre,
                        description=description,
                        type_evaluation=type_evaluation,
                        classe=classe,
                        professeur=professeur,
                        date_evaluation=date_evaluation,
                        bareme=bareme_float,
                        periode_scolaire=periode_scolaire,
                        duree=int(duree) if duree else None,
                        actif=True
                    )
                    
                    logger.info(f"Évaluation créée: {evaluation.id} - {evaluation.titre}")
                    messages.success(request, f"L'évaluation '{evaluation.titre}' a été créée avec succès !")
                    return redirect('enseignant:gestion_notes')
                    
            except Exception as e:
                logger.error(f"Erreur lors de la création de l'évaluation: {str(e)}")
                errors['general'] = f"Erreur lors de la création de l'évaluation : {str(e)}"
        
        # Stocker les erreurs et les données dans le contexte
        periodes_scolaires = PeriodeScolaire.objects.filter(
            etablissement=professeur.etablissement,
            est_active=True
        ).order_by('date_debut')
        
        context = {
            'professeur': professeur,
            'classe': classe,
            'affectation': affectation,
            'matiere': professeur.matiere_principale,
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
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'matiere': professeur.matiere_principale,
        'periodes_scolaires': periodes_scolaires,
        'errors': {},
        'form_data': {},
    }
    
    return render(request, 'school_admin/enseignant/creer_evaluation.html', context)


def liste_evaluations_enseignant(request):
    """
    Page pour afficher toutes les évaluations programmées de l'enseignant
    """
    logger.info(f"Liste évaluations - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.evaluation_model import Evaluation
    from ..model.affectation_model import AffectationProfesseur
    import re
    
    # Récupérer toutes les évaluations du professeur
    evaluations = Evaluation.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe').order_by('-date_evaluation')
    
    # Récupérer les affectations pour le regroupement
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe').order_by('classe__nom')
    
    # Regrouper les évaluations par catégorie de classe
    evaluations_grouped = {}
    
    for affectation in affectations:
        classe = affectation.classe
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
        
        # Récupérer les évaluations de cette classe
        evals_classe = evaluations.filter(classe=classe)
        
        classe_data = {
            'classe': classe,
            'evaluations': evals_classe,
            'nombre_evaluations': evals_classe.count(),
        }
        
        evaluations_grouped[categorie]['classes'].append(classe_data)
    
    # Statistiques globales
    stats = {
        'total_evaluations': evaluations.count(),
        'total_classes': affectations.count(),
    }
    
    context = {
        'professeur': professeur,
        'evaluations_grouped': evaluations_grouped,
        'stats': stats,
        'matiere_principale': professeur.matiere_principale,
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
    affectation = get_object_or_404(
        AffectationProfesseur,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Récupérer les colonnes sélectionnées et la période depuis la requête
    try:
        body = json.loads(request.body) if request.body else {}
        colonnes_selectionnees = body.get('colonnes_selectionnees', [])
        periode_id = body.get('periode', '')
        nombre_meilleures_notes = body.get('nombre_meilleures_notes', 'toutes')  # 'toutes', '2', '3', etc.
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
    
    # Mapper les évaluations pour la période
    evaluations_interrogations = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        type_evaluation='interrogation',
        periode_scolaire=periode_active,
        actif=True
    ).order_by('date_evaluation')[:3]
    
    evaluations_devoirs = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        type_evaluation__in=['controle', 'devoir_maison'],
        periode_scolaire=periode_active,
        actif=True
    ).order_by('date_evaluation')[:3]
    
    evaluations_map = {
        'interro_1': evaluations_interrogations[0] if len(evaluations_interrogations) > 0 else None,
        'interro_2': evaluations_interrogations[1] if len(evaluations_interrogations) > 1 else None,
        'interro_3': evaluations_interrogations[2] if len(evaluations_interrogations) > 2 else None,
        'devoir_1': evaluations_devoirs[0] if len(evaluations_devoirs) > 0 else None,
        'devoir_2': evaluations_devoirs[1] if len(evaluations_devoirs) > 1 else None,
        'devoir_3': evaluations_devoirs[2] if len(evaluations_devoirs) > 2 else None,
    }
    
    moyennes_calculees = []
    
    try:
        with transaction.atomic():
            for eleve in eleves:
                # Récupérer uniquement les notes des colonnes sélectionnées
                evaluations_selectionnees = []
                for colonne in colonnes_selectionnees:
                    evaluation = evaluations_map.get(colonne)
                    if evaluation:
                        evaluations_selectionnees.append(evaluation)
                
                if not evaluations_selectionnees:
                    continue
                
                # Récupérer les notes pour ces évaluations
                notes = Note.objects.filter(
                    eleve=eleve,
                    evaluation__in=evaluations_selectionnees,
                    absent=False
                )
                
                if notes.count() == 0:
                    continue
                
                # Séparer les interrogations et les devoirs
                notes_interrogations = []
                notes_devoirs = []
                
                for note in notes:
                    note_sur_20 = (float(note.note) / float(note.evaluation.bareme)) * 20
                    note_data = {
                        'note_sur_20': note_sur_20,
                        'evaluation_id': note.evaluation.id,
                        'note_originale': float(note.note),
                        'bareme': float(note.evaluation.bareme),
                        'type': note.evaluation.type_evaluation
                    }
                    
                    if note.evaluation.type_evaluation == 'interrogation':
                        notes_interrogations.append(note_data)
                    else:
                        notes_devoirs.append(note_data)
                
                # Créer les notes composées (2 interrogations = 1 devoir)
                notes_composees = []
                evaluations_retenues_ids = []
                
                # Mode spécial : multiplier une interrogation par 2
                if nombre_meilleures_notes == 'interro_x2':
                    if notes_interrogations:
                        # Prendre la meilleure interrogation et la multiplier par 2
                        meilleure_interro = max(notes_interrogations, key=lambda x: x['note_sur_20'])
                        notes_composees.append({
                            'note_sur_20': meilleure_interro['note_sur_20'],
                            'evaluations_ids': [meilleure_interro['evaluation_id']],
                            'type': 'interro_x2',
                            'description': f"Interrogation × 2"
                        })
                        evaluations_retenues_ids.append(meilleure_interro['evaluation_id'])
                    
                    # Ajouter tous les devoirs
                    for dev in notes_devoirs:
                        notes_composees.append({
                            'note_sur_20': dev['note_sur_20'],
                            'evaluations_ids': [dev['evaluation_id']],
                            'type': 'devoir',
                            'description': 'Devoir'
                        })
                        evaluations_retenues_ids.append(dev['evaluation_id'])
                    
                    # Prendre toutes les notes composées
                    notes_sur_20 = [n['note_sur_20'] for n in notes_composees]
                
                else:
                    # Créer les paires d'interrogations
                    paires_interrogations = []
                    for i in range(0, len(notes_interrogations), 2):
                        if i + 1 < len(notes_interrogations):
                            # Paire complète
                            interro1 = notes_interrogations[i]
                            interro2 = notes_interrogations[i + 1]
                            note_paire = interro1['note_sur_20'] + interro2['note_sur_20']
                            paires_interrogations.append({
                                'note_sur_20': note_paire / 2,  # Moyenne des 2 pour avoir sur 20
                                'evaluations_ids': [interro1['evaluation_id'], interro2['evaluation_id']],
                                'type': 'paire_interro',
                                'description': f"Interro 1+2"
                            })
                        else:
                            # Interrogation seule (multiplier par 2)
                            interro = notes_interrogations[i]
                            paires_interrogations.append({
                                'note_sur_20': interro['note_sur_20'],
                                'evaluations_ids': [interro['evaluation_id']],
                                'type': 'interro_seule',
                                'description': f"Interro × 2"
                            })
                    
                    # Ajouter les paires d'interrogations aux notes composées
                    notes_composees.extend(paires_interrogations)
                    
                    # Ajouter les devoirs individuels
                    for dev in notes_devoirs:
                        notes_composees.append({
                            'note_sur_20': dev['note_sur_20'],
                            'evaluations_ids': [dev['evaluation_id']],
                            'type': 'devoir',
                            'description': 'Devoir'
                        })
                    
                    # Sélectionner les meilleures notes composées
                    if nombre_meilleures_notes.isdigit():
                        nb_notes = int(nombre_meilleures_notes)
                        if nb_notes > 0 and nb_notes < len(notes_composees):
                            # Trier par ordre décroissant et prendre les N meilleures
                            notes_composees_triees = sorted(notes_composees, key=lambda x: x['note_sur_20'], reverse=True)
                            notes_selectionnees = notes_composees_triees[:nb_notes]
                            notes_sur_20 = [n['note_sur_20'] for n in notes_selectionnees]
                            # Collecter tous les IDs d'évaluations utilisées
                            for n in notes_selectionnees:
                                evaluations_retenues_ids.extend(n['evaluations_ids'])
                            logger.info(f"{eleve.nom_complet}: {len(notes_composees_triees)} notes composées -> {nb_notes} meilleures")
                        else:
                            notes_sur_20 = [n['note_sur_20'] for n in notes_composees]
                            for n in notes_composees:
                                evaluations_retenues_ids.extend(n['evaluations_ids'])
                    else:
                        notes_sur_20 = [n['note_sur_20'] for n in notes_composees]
                        for n in notes_composees:
                            evaluations_retenues_ids.extend(n['evaluations_ids'])
                
                # Calculer la moyenne
                moyenne_calculee = sum(notes_sur_20) / len(notes_sur_20) if notes_sur_20 else 0
                
                # Préparer les détails des notes pour affichage simplifié
                # Format : [{"titre": "Devoir 1", "note": 18.5, "bareme": 20}, ...]
                details_notes_eleve = []
                for idx, note_composee in enumerate(notes_composees if nombre_meilleures_notes != 'toutes' else notes_composees, start=1):
                    if nombre_meilleures_notes.isdigit():
                        nb_notes = int(nombre_meilleures_notes)
                        # Trier et prendre les N meilleures
                        notes_composees_triees = sorted(notes_composees, key=lambda x: x['note_sur_20'], reverse=True)
                        notes_selectionnees_details = notes_composees_triees[:nb_notes]
                    else:
                        notes_selectionnees_details = notes_composees
                    
                    break  # On prépare une seule fois
                
                # Créer les détails simplifiés
                for idx, note_composee in enumerate(notes_selectionnees_details if nombre_meilleures_notes.isdigit() else notes_composees, start=1):
                    detail = {
                        'titre': f"Devoir {idx}",
                        'note': round(note_composee['note_sur_20'], 2),
                        'bareme': 20,
                        'evaluations_ids': note_composee['evaluations_ids'],
                        'type': note_composee['type']
                    }
                    details_notes_eleve.append(detail)
                
                # Enregistrer ou mettre à jour la moyenne pour la période
                # Note: Le modèle Moyenne utilise encore l'ancien système (periode string)
                # On stocke l'ID de la période en string en attendant la migration
                moyenne_obj, created = Moyenne.objects.update_or_create(
                    eleve=eleve,
                    classe=classe,
                    matiere=professeur.matiere_principale,
                    periode=str(periode_id) if periode_id else 'trimestre1',
                    defaults={
                        'professeur': professeur,
                        'moyenne': Decimal(str(round(moyenne_calculee, 2))),
                        'nombre_notes': len(notes_sur_20),  # Utiliser le nombre de notes sélectionnées
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
                
                logger.info(f"Moyenne calculée pour {eleve.nom_complet}: {moyenne_obj.moyenne}/20 ({notes.count()} notes) - Colonnes: {colonnes_selectionnees}")
        
        return JsonResponse({
            'success': True,
            'moyennes': moyennes_calculees,
            'total_eleves': len(moyennes_calculees),
            'colonnes_utilisees': colonnes_selectionnees,
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
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    affectation = get_object_or_404(
        AffectationProfesseur,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Récupérer l'ID de la période depuis les paramètres
    periode_id = request.GET.get('periode', '')
    
    # Récupérer le relevé de notes
    try:
        if periode_id:
            periode_active = PeriodeScolaire.objects.get(id=periode_id, etablissement=professeur.etablissement)
            releve_notes = ReleveNotes.objects.get(
                classe=classe,
                professeur=professeur,
                matiere=professeur.matiere_principale,
                periode_scolaire=periode_active
            )
        else:
            messages.error(request, "Veuillez sélectionner une période.")
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
        
        if releve_notes.soumis:
            messages.warning(request, "Ce relevé de notes a déjà été soumis.")
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
        
        # Soumettre le relevé
        releve_notes.soumettre()
        
        logger.info(f"Relevé soumis - Classe: {classe.nom}, Période: {periode_active.nom_periode}, Professeur: {professeur.nom_complet}")
        messages.success(request, f"✓ Relevé de notes soumis avec succès pour {periode_active.nom_periode} ! Les notes sont maintenant verrouillées.")
        
    except PeriodeScolaire.DoesNotExist:
        messages.error(request, "Période scolaire introuvable.")
    except ReleveNotes.DoesNotExist:
        messages.error(request, "Relevé de notes introuvable pour cette période.")
    except Exception as e:
        logger.error(f"Erreur soumission relevé: {str(e)}")
        messages.error(request, f"Erreur lors de la soumission : {str(e)}")
    
    # Rediriger en conservant le paramètre de période
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
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from datetime import date
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    affectation = get_object_or_404(
        AffectationProfesseur,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Date du jour
    today = date.today()
    
    # Vérifier s'il existe déjà une liste de présence pour aujourd'hui
    liste_presence, created = ListePresence.objects.get_or_create(
        classe=classe,
        date=today,
        defaults={
            'professeur': professeur,
            'etablissement': classe.etablissement
        }
    )
    
    # Récupérer tous les élèves actifs de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les présences déjà enregistrées pour aujourd'hui
    presences_existantes = Presence.objects.filter(
        classe=classe,
        date=today
    ).select_related('eleve')
    
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
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'eleves_avec_presence': eleves_avec_presence,
        'liste_presence': liste_presence,
        'today': today,
        'nombre_eleves': eleves.count(),
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
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from datetime import date
    from django.db import transaction
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    affectation = get_object_or_404(
        AffectationProfesseur,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Date du jour
    today = date.today()
    
    try:
        with transaction.atomic():
            # Récupérer ou créer la liste de présence
            liste_presence, created = ListePresence.objects.get_or_create(
                classe=classe,
                date=today,
                defaults={
                    'professeur': professeur,
                    'etablissement': classe.etablissement
                }
            )
            
            # Si déjà validée, interdire la modification
            if liste_presence.validee:
                messages.warning(request, "La liste de présence a déjà été validée pour aujourd'hui.")
                return redirect('enseignant:liste_presence', classe_id=classe_id)
            
            # Parcourir les données POST pour enregistrer les présences
            nombre_presents = 0
            nombre_absents = 0
            
            for key, value in request.POST.items():
                if key.startswith('presence_'):
                    eleve_id = key.replace('presence_', '')
                    try:
                        eleve = Eleve.objects.get(id=eleve_id, classe=classe, actif=True)
                        
                        # Créer ou mettre à jour la présence
                        presence, created = Presence.objects.update_or_create(
                            eleve=eleve,
                            classe=classe,
                            date=today,
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
    
    # Récupérer les évaluations de la matière du professeur pour cette période
    evaluations = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        periode_scolaire=periode_selectionnee,
        actif=True
    ).order_by('date_evaluation') if periode_selectionnee else []
    
    # Récupérer les notes de l'élève pour ces évaluations
    notes_objs = Note.objects.filter(
        eleve=eleve,
        evaluation__in=evaluations
    ).select_related('evaluation')
    
    # Créer un dictionnaire des notes indexé par evaluation_id
    notes_dict = {note.evaluation.id: note for note in notes_objs}
    
    # Récupérer la moyenne enregistrée pour cette matière et période
    # Le champ "periode" dans Moyenne stocke l'ID de la période en string
    moyenne_obj = Moyenne.objects.filter(
        eleve=eleve,
        professeur=professeur,
        periode=str(periode_selectionnee.id) if periode_selectionnee else None,
        actif=True
    ).first() if periode_selectionnee else None
    
    moyenne = moyenne_obj.moyenne if moyenne_obj else None
    
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
    
    presences_query = Presence.objects.filter(
        eleve=eleve,
        date__gte=debut_annee,
        date__lte=fin_annee
    ).select_related('eleve', 'classe')
    
    # Calculer les statistiques globales
    total_presences = presences_query.count()
    nombre_absences = presences_query.filter(statut__in=['absent', 'absent_justifie']).count()
    nombre_retards = presences_query.filter(statut='retard').count()
    nombre_presents = presences_query.filter(statut='present').count()
    taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
    
    # Récupérer les listes de présences validées pour cette classe
    listes_validees = ListePresence.objects.filter(
        classe=eleve.classe,
        validee=True,
        date__gte=debut_annee,
        date__lte=fin_annee
    ).values_list('date', flat=True)
    
    # Extraire les mois uniques qui ont des listes validées
    mois_avec_presences = set()
    for date_presence in listes_validees:
        mois_avec_presences.add((date_presence.year, date_presence.month))
    
    # Créer une liste de mois disponibles
    mois_disponibles = []
    noms_mois = [
        'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]
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
    
    # Statistiques du mois
    total_presences_mois = presences.count()
    nombre_absences_mois = presences.filter(statut__in=['absent', 'absent_justifie']).count()
    nombre_retards_mois = presences.filter(statut='retard').count()
    nombre_presents_mois = presences.filter(statut='present').count()
    taux_presence_mois = round((nombre_presents_mois / total_presences_mois * 100), 2) if total_presences_mois > 0 else 0
    
    context = {
        'professeur': professeur,
        'eleve': eleve,
        'classe': classe,
        'affectation': affectation,
        'onglet_actif': onglet_actif,
        # Onglet Notes
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'evaluations': evaluations,
        'notes_dict': notes_dict,
        'moyenne': moyenne,
        'nombre_notes': len(notes_dict),
        # Onglet Présences
        'presences': presences,
        'total_presences': total_presences,
        'nombre_absences': nombre_absences,
        'nombre_retards': nombre_retards,
        'nombre_presents': nombre_presents,
        'taux_presence': taux_presence,
        # Données pour les onglets de mois
        'mois_disponibles': mois_disponibles,
        'mois_selectionne': mois_selectionne,
        'total_presences_mois': total_presences_mois,
        'nombre_absences_mois': nombre_absences_mois,
        'nombre_retards_mois': nombre_retards_mois,
        'nombre_presents_mois': nombre_presents_mois,
        'taux_presence_mois': taux_presence_mois,
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
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier que le professeur est affecté à cette classe
    affectation = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_classes')
    
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
    presences_mois = Presence.objects.filter(
        classe=classe,
        date__gte=premier_jour_mois,
        date__lte=dernier_jour_mois
    )
    
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
    ).order_by('-date')
    
    # Générer la liste des 12 derniers mois pour les onglets
    mois_disponibles = []
    for i in range(12):
        mois_calc = today.month - i
        annee_calc = today.year
        while mois_calc <= 0:
            mois_calc += 12
            annee_calc -= 1
        mois_disponibles.append({
            'mois': mois_calc,
            'annee': annee_calc,
            'nom': date(annee_calc, mois_calc, 1).strftime('%B %Y'),
            'nom_court': date(annee_calc, mois_calc, 1).strftime('%b %Y')
        })
    
    # === STATISTIQUES DES ÉVALUATIONS ===
    # Filtre par période (GET parameter)
    periode_filtre = request.GET.get('periode_eval', 'toutes')
    
    evaluations = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        actif=True
    )
    
    # Filtrer par période si spécifiée
    if periode_filtre != 'toutes':
        evaluations = evaluations.filter(periode=periode_filtre)
    
    evaluations = evaluations.order_by('-date_evaluation')
    
    nombre_evaluations_total = evaluations.count()
    nombre_evaluations_mois = evaluations.filter(
        date_evaluation__gte=debut_mois,
        date_evaluation__lte=today
    ).count()
    
    # Dernières évaluations (filtrées)
    dernieres_evaluations = evaluations.filter(date_evaluation__lt=today).order_by('-date_evaluation')[:5]
    
    # Prochaines évaluations (filtrées)
    prochaines_evaluations = evaluations.filter(date_evaluation__gte=today).order_by('date_evaluation')[:5]
    
    # Périodes disponibles
    PERIODES_EVAL = [
        ('toutes', 'Toutes les périodes'),
        ('trimestre1', '1er Trimestre'),
        ('trimestre2', '2ème Trimestre'),
        ('trimestre3', '3ème Trimestre'),
        ('semestre1', '1er Semestre'),
        ('semestre2', '2ème Semestre'),
    ]
    
    # === ÉLÈVES AVEC STATISTIQUES ===
    eleves_avec_stats = []
    for eleve in eleves:
        # Absences
        nombre_absences = Presence.objects.filter(
            eleve=eleve,
            statut='absent'
        ).count()
        
        # Moyennes (dernière période)
        from ..model.moyenne_model import Moyenne
        derniere_moyenne = Moyenne.objects.filter(
            eleve=eleve,
            professeur=professeur,
            actif=True
        ).order_by('-date_calcul').first()
        
        # Notes
        from ..model.evaluation_model import Note
        nombre_notes = Note.objects.filter(
            eleve=eleve,
            evaluation__professeur=professeur
        ).count()
        
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
        'PERIODES_EVAL': PERIODES_EVAL,
        'periode_filtre': periode_filtre,
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
    creneaux_professeur = CreneauEmploiDuTemps.objects.filter(
        professeur=professeur
    ).select_related('emploi_du_temps', 'emploi_du_temps__classe', 'matiere', 'salle', 'periode_etablissement').order_by('jour', 'periode_etablissement__ordre', 'heure_debut')
    
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
    }
    
    return render(request, 'school_admin/enseignant/emploi_du_temps.html', context)

