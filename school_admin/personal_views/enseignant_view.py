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
        )
        
        heures_semaine = 0
        for creneau in creneaux_classe:
            duree = (creneau.heure_fin.hour * 60 + creneau.heure_fin.minute) - \
                    (creneau.heure_debut.hour * 60 + creneau.heure_debut.minute)
            heures_semaine += duree / 60
        
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
    ).select_related('emploi_du_temps__classe', 'matiere', 'salle').order_by('heure_debut')
    
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
    import re
    
    # Récupérer la période sélectionnée (depuis GET ou par défaut trimestre1)
    periode_active = request.GET.get('periode', 'trimestre1')
    
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
        moyennes = Moyenne.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=professeur.matiere_principale,
            periode=periode_active,
            actif=True
        ).select_related('eleve')
        
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
    
    context = {
        'professeur': professeur,
        'classes_grouped': classes_grouped,
        'stats': stats,
        'matiere_principale': professeur.matiere_principale,
        'periode_active': periode_active,
        'PERIODES': Evaluation.PERIODE_CHOICES,
    }
    
    return render(request, 'school_admin/enseignant/gestion_notes.html', context)


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
    
    # Récupérer la période sélectionnée (depuis GET ou par défaut trimestre1)
    periode_active = request.GET.get('periode', 'trimestre1')
    
    # Récupérer ou créer le relevé de notes pour cette classe/professeur/matière/période
    from ..model.releve_notes_model import ReleveNotes
    releve_notes, created = ReleveNotes.objects.get_or_create(
        classe=classe,
        professeur=professeur,
        matiere=professeur.matiere_principale,
        periode=periode_active,
        defaults={
            'etablissement': classe.etablissement,
            'soumis': False
        }
    )
    
    # Récupérer tous les relevés pour afficher les onglets
    tous_releves = ReleveNotes.objects.filter(
        classe=classe,
        professeur=professeur,
        matiere=professeur.matiere_principale
    ).order_by('periode')
    
    # Récupérer les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer toutes les évaluations de la classe pour ce professeur pour la période active
    evaluations_interrogations = list(Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        type_evaluation='interrogation',
        periode=periode_active,
        actif=True
    ).order_by('date_evaluation'))
    
    evaluations_devoirs = list(Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        type_evaluation__in=['controle', 'devoir_maison'],
        periode=periode_active,
        actif=True
    ).order_by('date_evaluation'))
    
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
    for eleve in eleves:
        moyenne_obj = Moyenne.objects.filter(
            eleve=eleve,
            classe=classe,
            matiere=professeur.matiere_principale,
            periode=periode_active,
            actif=True
        ).first()
        if moyenne_obj:
            moyennes_enregistrees[eleve.id] = {
                'moyenne': moyenne_obj.moyenne,
                'nombre_notes': moyenne_obj.nombre_notes,
                'appreciation': moyenne_obj.appreciation
            }
    
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
        'tous_releves': tous_releves,
        'periode_active': periode_active,
        'PERIODES': Evaluation.PERIODE_CHOICES,
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
        periode = request.POST.get('periode', 'trimestre1')
        
        # Validation
        if not titre:
            errors['titre'] = "Le titre est obligatoire."
        if not date_evaluation:
            errors['date_evaluation'] = "La date est obligatoire."
        
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
                        periode=periode,
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
        context = {
            'professeur': professeur,
            'classe': classe,
            'affectation': affectation,
            'matiere': professeur.matiere_principale,
            'errors': errors,
            'form_data': request.POST,
        }
        
        return render(request, 'school_admin/enseignant/creer_evaluation.html', context)
    
    # GET request
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'matiere': professeur.matiere_principale,
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
        periode = body.get('periode', 'trimestre1')
    except:
        colonnes_selectionnees = []
        periode = 'trimestre1'
    
    logger.info(f"Colonnes sélectionnées: {colonnes_selectionnees}")
    
    # Si aucune colonne sélectionnée, retourner une erreur
    if not colonnes_selectionnees:
        return JsonResponse({
            'success': False,
            'error': 'Veuillez sélectionner au moins une colonne pour calculer les moyennes'
        }, status=400)
    
    # Récupérer les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True)
    
    # Mapper les évaluations pour la période
    evaluations_interrogations = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        type_evaluation='interrogation',
        periode=periode,
        actif=True
    ).order_by('date_evaluation')[:3]
    
    evaluations_devoirs = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        type_evaluation__in=['controle', 'devoir_maison'],
        periode=periode,
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
                
                # Convertir toutes les notes sur 20
                notes_sur_20 = []
                for note in notes:
                    note_sur_20 = (float(note.note) / float(note.evaluation.bareme)) * 20
                    notes_sur_20.append(note_sur_20)
                
                # Calculer la moyenne
                moyenne_calculee = sum(notes_sur_20) / len(notes_sur_20)
                
                # Enregistrer ou mettre à jour la moyenne pour la période
                moyenne_obj, created = Moyenne.objects.update_or_create(
                    eleve=eleve,
                    classe=classe,
                    matiere=professeur.matiere_principale,
                    periode=periode,
                    defaults={
                        'professeur': professeur,
                        'moyenne': Decimal(str(round(moyenne_calculee, 2))),
                        'nombre_notes': notes.count(),
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
    
    # Récupérer le relevé de notes
    try:
        releve_notes = ReleveNotes.objects.get(
            classe=classe,
            professeur=professeur,
            matiere=professeur.matiere_principale,
            periode='trimestre1'
        )
        
        if releve_notes.soumis:
            messages.warning(request, "Ce relevé de notes a déjà été soumis.")
            return redirect('enseignant:noter_eleves', classe_id=classe_id)
        
        # Soumettre le relevé
        releve_notes.soumettre()
        
        logger.info(f"Relevé soumis - Classe: {classe.nom}, Professeur: {professeur.nom_complet}")
        messages.success(request, f"✓ Relevé de notes soumis avec succès ! Les notes sont maintenant verrouillées.")
        
    except ReleveNotes.DoesNotExist:
        messages.error(request, "Relevé de notes introuvable.")
    except Exception as e:
        logger.error(f"Erreur soumission relevé: {str(e)}")
        messages.error(request, f"Erreur lors de la soumission : {str(e)}")
    
    return redirect('enseignant:noter_eleves', classe_id=classe_id)


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
    # Récupérer toutes les notes de l'élève pour cette matière
    notes = Note.objects.filter(
        eleve=eleve,
        evaluation__professeur=professeur
    ).select_related('evaluation').order_by('-evaluation__date_evaluation')
    
    # Récupérer les moyennes par période
    moyennes = Moyenne.objects.filter(
        eleve=eleve,
        professeur=professeur,
        actif=True
    ).order_by('periode')
    
    # === ONGLET PRÉSENCES ===
    # Récupérer toutes les présences de l'élève (30 derniers jours)
    date_debut = date.today() - timedelta(days=30)
    presences = Presence.objects.filter(
        eleve=eleve,
        date__gte=date_debut
    ).order_by('-date')
    
    # Statistiques de présence
    total_presences = presences.count()
    nombre_absences = presences.filter(statut__in=['absent', 'absent_justifie']).count()
    nombre_retards = presences.filter(statut='retard').count()
    nombre_presents = presences.filter(statut='present').count()
    taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
    
    context = {
        'professeur': professeur,
        'eleve': eleve,
        'classe': classe,
        'onglet_actif': onglet_actif,
        # Onglet Notes
        'notes': notes,
        'moyennes': moyennes,
        'nombre_notes': notes.count(),
        # Onglet Présences
        'presences': presences,
        'total_presences': total_presences,
        'nombre_absences': nombre_absences,
        'nombre_retards': nombre_retards,
        'nombre_presents': nombre_presents,
        'taux_presence': taux_presence,
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
    ).select_related('emploi_du_temps', 'emploi_du_temps__classe', 'matiere', 'salle').order_by('jour', 'heure_debut')
    
    # Organiser les créneaux par jour
    jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
    creneaux_par_jour = defaultdict(list)
    
    for creneau in creneaux_professeur:
        creneaux_par_jour[creneau.jour].append(creneau)
    
    # Statistiques
    total_heures = 0
    for creneau in creneaux_professeur:
        duree = (creneau.heure_fin.hour * 60 + creneau.heure_fin.minute) - (creneau.heure_debut.hour * 60 + creneau.heure_debut.minute)
        total_heures += duree / 60
    
    nombre_classes = affectations.count()
    nombre_creneaux = creneaux_professeur.count()
    
    context = {
        'professeur': professeur,
        'jours_semaine': jours_semaine,
        'creneaux_par_jour': dict(creneaux_par_jour),
        'nombre_classes': nombre_classes,
        'nombre_creneaux': nombre_creneaux,
        'total_heures': round(total_heures, 1),
    }
    
    return render(request, 'school_admin/enseignant/emploi_du_temps.html', context)

