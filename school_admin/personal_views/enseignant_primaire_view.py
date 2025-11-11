# school_admin/personal_views/enseignant_primaire_view.py

"""
Vues spécifiques pour les enseignants du primaire.
Système parallèle avec gestion multi-matières.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q, Avg
from django.db import transaction
from datetime import datetime, timedelta, date
from decimal import Decimal
import logging
from collections import defaultdict

from ..model.professeur_model import Professeur
from ..model.classe_model import Classe
from ..model.eleve_model import Eleve
from ..model.matiere_model import Matiere
from ..model.periode_model import PeriodeScolaire
from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from ..model.evaluation_primaire_model import EvaluationPrimaire
from ..model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire
from ..model.note_examen_model import NoteExamen
from ..model.presence_model import Presence, ListePresence
from ..model.sanction_model import Sanction
from ..model.emploi_du_temps_model import EmploiDuTemps, CreneauEmploiDuTemps
from ..services.parent_notification_service import ParentNotificationService
from ..services.directeur_notification_service import DirecteurNotificationService
from ..services.eleve_notification_service import EleveNotificationService
from ..model.notification_enseignant_model import NotificationEnseignant
from ..utils.calcul_moyennes_primaire import (
    calculer_moyenne_matiere,
    calculer_moyenne_generale,
    calculer_moyenne_classe_matiere,
    calculer_toutes_moyennes_classe,
    get_appreciation_moyenne,
    get_repartition_moyennes_classe,
    calculer_moyenne_avec_mode
)

logger = logging.getLogger(__name__)


def dashboard_enseignant_primaire(request):
    """
    Tableau de bord pour les enseignants du primaire.
    Affiche les classes, matières enseignées, et statistiques.
    """
    logger.info(f"Dashboard enseignant primaire - User: {request.user}")
    
    # Vérifier que l'utilisateur est bien un professeur
    if not isinstance(request.user, Professeur):
        logger.warning(f"Accès refusé au dashboard enseignant primaire - Type d'utilisateur: {type(request.user).__name__}")
        messages.error(request, "Accès non autorisé. Cette page est réservée aux enseignants.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Vérifier que le professeur est bien de niveau primaire
    if professeur.niveau_enseignement != 'primaire':
        messages.warning(request, "Vous n'êtes pas un enseignant du primaire. Redirection vers le tableau de bord standard.")
        return redirect('enseignant:dashboard_enseignant')
    
    # Récupérer les affectations primaires du professeur
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe').prefetch_related('matieres')
    
    total_classes = affectations.count()
    
    # Compter le nombre total d'élèves
    total_eleves = 0
    for affectation in affectations:
        total_eleves += affectation.classe.nombre_eleves
    
    # Compter le nombre total de matières enseignées (uniques)
    matieres_enseignees = set()
    for affectation in affectations:
        matieres_enseignees.update(affectation.matieres.all())
    total_matieres = len(matieres_enseignees)
    
    # Évaluations à venir (7 prochains jours)
    date_debut = date.today()
    date_fin = date_debut + timedelta(days=7)
    
    evaluations_a_venir = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        date_evaluation__gte=date_debut,
        date_evaluation__lte=date_fin,
        actif=True
    ).count()
    
    # Préparer les données des classes
    classes_data = []
    for affectation in affectations[:3]:  # Limiter à 3 pour le dashboard
        classe = affectation.classe
        matieres_classe = list(affectation.matieres.all())
        
        # Calculer les heures par semaine
        creneaux_classe = CreneauEmploiDuTemps.objects.filter(
            emploi_du_temps__classe=classe,
            emploi_du_temps__est_actif=True,
            emploi_du_temps__statut_publication='publie',
            professeur=professeur
        )
        
        heures_semaine = sum(creneau.duree_minutes / 60 for creneau in creneaux_classe)
        
        # Progression fictive
        mois_ecoule = datetime.now().month - 9
        if mois_ecoule < 0:
            mois_ecoule += 12
        progression = min(int(mois_ecoule / 9 * 100), 100)
        
        classes_data.append({
            'classe': classe,
            'nombre_eleves': classe.nombre_eleves,
            'heures_semaine': round(heures_semaine, 1),
            'progression': progression,
            'est_principal': affectation.is_principal,
            'matieres': matieres_classe,
            'nombre_matieres': len(matieres_classe)
        })
    
    # Emploi du temps d'aujourd'hui
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
    
    classes_professeur = [affectation.classe for affectation in affectations]
    emplois_actifs = EmploiDuTemps.objects.filter(classe__in=classes_professeur, est_actif=True)
    emplois_publies = emplois_actifs.filter(statut_publication='publie')
    emploi_publie_disponible = emplois_publies.exists()
    
    if emploi_publie_disponible:
        creneaux_aujourdhui = CreneauEmploiDuTemps.objects.filter(
            professeur=professeur,
            jour=jour_actuel,
            emploi_du_temps__in=emplois_publies
        ).select_related('emploi_du_temps__classe', 'matiere', 'salle').order_by('heure_debut')
    else:
        creneaux_aujourdhui = []
    
    # Prochaines évaluations (détaillées)
    prochaines_evaluations = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        date_evaluation__gte=date_debut,
        actif=True
    ).select_related('classe', 'matiere', 'periode_scolaire').order_by('date_evaluation')[:5]
    
    # Compter les annonces destinées aux enseignants
    from ..model.annonce_model import Annonce
    from django.db.models import Q
    
    nombre_annonces = Annonce.objects.filter(
        Q(etablissement=professeur.etablissement) &
        Q(statut='publiee') &
        Q(actif=True) &
        (Q(destinataires__contains=['tous']) | 
         Q(destinataires__contains=['enseignants']))
    ).count()
    
    notifications_non_lues = NotificationEnseignant.objects.filter(
        enseignant=professeur, statut='non_lu'
    ).count()
    
    context = {
        'professeur': professeur,
        'total_classes': total_classes,
        'total_eleves': total_eleves,
        'total_matieres': total_matieres,
        'evaluations_a_venir': evaluations_a_venir,
        'classes_data': classes_data,
        'creneaux_aujourdhui': creneaux_aujourdhui,
        'prochaines_evaluations': prochaines_evaluations,
        'messages_non_lus': 0,  # À implémenter plus tard
        'nombre_annonces': nombre_annonces,
        'emploi_publie': emploi_publie_disponible,
        'emploi_non_publie': (not emploi_publie_disponible) and emplois_actifs.exists(),
        'notifications_enseignant_non_lues': notifications_non_lues,
    }
    
    return render(request, 'school_admin/enseignant/primaire/dashboard_primaire.html', context)


def gestion_classes_primaire(request):
    """
    Gestion des classes pour les enseignants du primaire.
    Affiche toutes les classes avec les matières enseignées.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Récupérer les affectations
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe').prefetch_related('matieres')
    
    # Regrouper les classes par catégorie (comme dans le système de base)
    import re
    classes_grouped = {}
    total_matieres = 0
    
    for affectation in affectations:
        matieres = list(affectation.matieres.all())
        total_matieres += len(matieres)
        
        classe = affectation.classe
        
        # Extraire la catégorie (ex: "CE1" de "CE1 - A", "CE1 - B", etc.)
        nom = classe.nom
        # Pattern pour extraire le niveau et la section
        match = re.match(r'^(.+?)\s*-?\s*([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1).strip()  # "CI", "CP", "CE1", "CE2", "CM1", "CM2"
            section = match.group(2)    # "A", "B", "C", etc.
        else:
            # Si pas de pattern trouvé, utiliser le niveau comme catégorie
            categorie = classe.niveau
            section = ""
        
        # Initialiser le groupe si nécessaire
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'nombre_classes': 0,
                'total_eleves': 0,
                'total_capacite': 0,
                'classes': []
            }
        
        # Calculer les statistiques de la classe
        nombre_evaluations = EvaluationPrimaire.objects.filter(
            professeur=professeur,
            classe=affectation.classe,
            actif=True
        ).count()
        
        # Calculer la moyenne de la classe (exemple simplifié)
        moyenne_classe = None  # À implémenter avec les calculs de moyennes
        
        # Ajouter la classe au groupe
        classes_grouped[categorie]['nombre_classes'] += 1
        classes_grouped[categorie]['total_eleves'] += affectation.classe.nombre_eleves
        classes_grouped[categorie]['total_capacite'] += affectation.classe.capacite_max
        classes_grouped[categorie]['classes'].append({
            'classe': affectation.classe,
            'affectation': affectation,
            'matieres': matieres,
            'nombre_eleves': affectation.classe.nombre_eleves,
            'capacite_max': affectation.classe.capacite_max,
            'nombre_evaluations': nombre_evaluations,
            'moyenne_classe': moyenne_classe,
            'presence_taux': None,  # À implémenter
            'taux_occupation': int((affectation.classe.nombre_eleves / affectation.classe.capacite_max) * 100) if affectation.classe.capacite_max > 0 else 0,
            'est_principal': affectation.statut == 'principal',
        })
    
    # Calculer le taux d'occupation moyen par catégorie
    for categorie, data in classes_grouped.items():
        if data['total_capacite'] > 0:
            data['taux_moyen'] = int((data['total_eleves'] / data['total_capacite']) * 100)
        else:
            data['taux_moyen'] = 0
    
    # Statistiques globales
    total_classes = affectations.count()
    total_eleves = sum(aff.classe.nombre_eleves for aff in affectations)
    
    # Compter les affectations principales et polyvalentes
    affectations_principales = affectations.filter(statut='principal').count()
    affectations_polyvalentes = affectations.filter(statut='polyvalent').count()
    
    context = {
        'professeur': professeur,
        'classes_grouped': classes_grouped,
        'total_classes': total_classes,
        'total_eleves': total_eleves,
        'total_matieres': total_matieres,
        'affectations_principales': affectations_principales,
        'affectations_polyvalentes': affectations_polyvalentes,
    }
    
    return render(request, 'school_admin/enseignant/primaire/gestion_classes_primaire.html', context)


def gestion_eleves_primaire(request):
    """
    Gestion des élèves pour les enseignants du primaire.
    Structure identique au système standard avec onglets par catégorie.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Récupérer toutes les classes du professeur
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe')
    
    classes = [aff.classe for aff in affectations]
    
    # Grouper les classes par catégorie (CI, CP, CE1, CE2, CM1, CM2)
    import re
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    
    eleves_par_categorie = {}
    for affectation in affectations:
        classe = affectation.classe
        
        # Extraire la catégorie (ex: "CE1" de "CE1 - A")
        match = re.match(r'^(CI|CP|CE1|CE2|CM1|CM2)', classe.nom)
        if match:
            categorie = match.group(1)
        else:
            categorie = classe.niveau or "Autre"
        
        if categorie not in eleves_par_categorie:
            eleves_par_categorie[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves de cette classe avec statistiques
        eleves_classe = Eleve.objects.filter(
            classe=classe,
            actif=True
        ).select_related('classe').order_by('nom', 'prenom')
        
        # Calculer les statistiques pour chaque élève
        eleves_data = []
        for eleve in eleves_classe:
            # Compter les absences (30 derniers jours)
            date_limite = datetime.now().date() - timedelta(days=30)
            nombre_absences = Presence.objects.filter(
                eleve=eleve,
                statut='absent',
                date__gte=date_limite
            ).count()
            
            # Compter les sanctions
            nombre_sanctions = Sanction.objects.filter(
                eleve=eleve
            ).count()
            
            eleves_data.append({
                'eleve': eleve,
                'nombre_absences': nombre_absences,
                'nombre_sanctions': nombre_sanctions
            })
        
        eleves_par_categorie[categorie]['classes'].append({
            'classe': classe,
            'eleves': eleves_data,
            'nombre_eleves': eleves_classe.count()
        })
        eleves_par_categorie[categorie]['total_eleves'] += eleves_classe.count()
    
    # Trier les catégories dans l'ordre logique
    ordre_classes = ['CI', 'CP', 'CE1', 'CE2', 'CM1', 'CM2']
    eleves_par_categorie_ordered = {k: eleves_par_categorie[k] for k in ordre_classes if k in eleves_par_categorie}
    
    # Statistiques globales
    total_classes = len(classes)
    total_eleves = sum(aff.classe.nombre_eleves for aff in affectations)
    
    context = {
        'professeur': professeur,
        'eleves_par_categorie': eleves_par_categorie_ordered,
        'total_classes': total_classes,
        'total_eleves': total_eleves,
        'today': datetime.now().date()
    }
    
    return render(request, 'school_admin/enseignant/primaire/gestion_eleves_primaire.html', context)


def gestion_notes_primaire(request):
    """
    Gestion des notes multi-matières pour les enseignants du primaire.
    Système à 3 niveaux : Classes -> Matières -> Relevé de notes.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Récupérer les paramètres de navigation
    classe_id = request.GET.get('classe')
    matiere_id = request.GET.get('matiere')
    periode_id = request.GET.get('periode')
    
    # Récupérer toutes les périodes
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Période active par défaut
    if periode_id:
        periode_selectionnee = get_object_or_404(PeriodeScolaire, id=periode_id)
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Récupérer les affectations et grouper les classes par type
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe').prefetch_related('matieres')
    
    # Grouper les classes par catégorie (CI, CP, CE1, CE2, CM1, CM2)
    import re
    classes_grouped = {}
    for affectation in affectations:
        classe = affectation.classe
        # Extraire la catégorie (ex: "CE1" de "CE1 - A")
        match = re.match(r'^(CI|CP|CE1|CE2|CM1|CM2)', classe.nom)
        if match:
            categorie = match.group(1)
        else:
            categorie = classe.niveau or "Autre"
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = []
        
        classes_grouped[categorie].append({
            'classe': classe,
            'affectation': affectation,
            'nombre_eleves': classe.nombre_eleves
        })
    
    # Trier les catégories dans l'ordre logique
    ordre_classes = ['CI', 'CP', 'CE1', 'CE2', 'CM1', 'CM2']
    classes_grouped_ordered = {k: classes_grouped[k] for k in ordre_classes if k in classes_grouped}
    
    # Si une classe est sélectionnée, préparer les données des matières
    matieres_data = []
    classe_selectionnee = None
    affectation_selectionnee = None
    
    if classe_id:
        classe_selectionnee = get_object_or_404(Classe, id=classe_id)
        affectation_selectionnee = AffectationProfesseurPrimaire.objects.filter(
            professeur=professeur,
            classe=classe_selectionnee,
            actif=True
        ).prefetch_related('matieres').first()
        
        if affectation_selectionnee:
            from ..model.session_examen_model import SessionExamen
            
            for matiere in affectation_selectionnee.matieres.all():
                # Compter les évaluations normales pour cette matière
                nb_evaluations = EvaluationPrimaire.objects.filter(
                    professeur=professeur,
                    classe=classe_selectionnee,
                    matiere=matiere,
                    periode_scolaire=periode_selectionnee,
                    actif=True
                ).count()
                
                # Compter aussi les sessions d'examens (pas les créneaux)
                nb_examens = SessionExamen.objects.filter(
                    classes=classe_selectionnee,
                    periode=periode_selectionnee,
                    matieres=matiere,
                    actif=True
                ).distinct().count()
                
                matieres_data.append({
                    'matiere': matiere,
                    'nombre_evaluations': nb_evaluations + nb_examens  # Total des évaluations + examens
                })
    
    # Si une matière est sélectionnée, préparer le relevé de notes
    releve_data = []
    matiere_selectionnee = None
    evaluations_matiere = []
    
    if classe_id and matiere_id:
        matiere_selectionnee = get_object_or_404(Matiere, id=matiere_id)
        classe_selectionnee = get_object_or_404(Classe, id=classe_id)
        
        # Récupérer toutes les évaluations normales pour cette matière et période
        evaluations_list = list(EvaluationPrimaire.objects.filter(
            classe=classe_selectionnee,
            professeur=professeur,
            matiere=matiere_selectionnee,
            periode_scolaire=periode_selectionnee,
            actif=True
        ).order_by('date_evaluation'))
        
        # Récupérer les sessions d'examens pour cette matière et période (PAS les créneaux!)
        from ..model.session_examen_model import SessionExamen
        
        sessions_examens_list = list(SessionExamen.objects.filter(
            classes=classe_selectionnee,
            periode=periode_selectionnee,
            matieres=matiere_selectionnee,
            actif=True
        ).distinct().order_by('date_debut'))
        
        # Ajouter des numéros distincts pour devoirs, interrogations et examens
        compteur_devoirs = 0
        compteur_interrogations = 0
        compteur_examens = 0
        evaluations_matiere = []
        
        # Traiter les évaluations normales
        for eval in evaluations_list:
            eval_dict = {
                'obj': eval,
                'id': eval.id,
                'titre': eval.titre,
                'bareme': eval.bareme,
                'date_evaluation': eval.date_evaluation,
                'est_examen': False
            }
            
            if eval.bareme == 20:
                compteur_devoirs += 1
                eval_dict['type_label'] = f'Devoir {compteur_devoirs}'
                eval_dict['numero'] = compteur_devoirs
            else:
                compteur_interrogations += 1
                eval_dict['type_label'] = f'Interrogation {compteur_interrogations}'
                eval_dict['numero'] = compteur_interrogations
            
            evaluations_matiere.append(eval_dict)
        
        # Traiter les examens (basés sur les sessions, pas les créneaux)
        for session in sessions_examens_list:
            compteur_examens += 1
            eval_dict = {
                'obj': session,
                'id': f'examen_{session.id}',
                'session_id': session.id,
                'titre': session.nom_examen,
                'bareme': 20,  # Les examens sont sur 20
                'date_evaluation': session.date_debut,
                'est_examen': True,
                'type_label': f'Examen {compteur_examens}',
                'numero': compteur_examens
            }
            
            evaluations_matiere.append(eval_dict)
        
        # Récupérer tous les élèves de la classe
        eleves = Eleve.objects.filter(
            classe=classe_selectionnee,
            actif=True
        ).order_by('nom', 'prenom')
        
        for eleve in eleves:
            # Récupérer la moyenne ENREGISTRÉE (pas calculée)
            moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                matiere=matiere_selectionnee,
                periode_scolaire=periode_selectionnee
            ).first()
            
            moyenne = moyenne_obj.moyenne if moyenne_obj and moyenne_obj.moyenne is not None else None
            appreciation = moyenne_obj.appreciation if moyenne_obj else None
            
            # Récupérer les notes pour chaque évaluation (normales + examens)
            from ..model.note_examen_model import NoteExamen
            
            notes_evaluations = {}
            for eval_dict in evaluations_matiere:
                # Si c'est un examen, chercher dans NoteExamen (basé sur session)
                if eval_dict.get('est_examen'):
                    note_obj = NoteExamen.objects.filter(
                        eleve=eleve,
                        session_examen_id=eval_dict['session_id'],
                        matiere=matiere_selectionnee
                    ).first()
                else:
                    # Sinon, chercher dans NotePrimaire
                    note_obj = NotePrimaire.objects.filter(
                        eleve=eleve,
                        evaluation_primaire_id=eval_dict['id']
                    ).first()
                
                # Ajouter la couleur basée sur la note normalisée
                if note_obj and note_obj.note is not None and not note_obj.absent:
                    # Calculer la note sur 20
                    note_sur_20 = (float(note_obj.note) / float(eval_dict['bareme'])) * 20
                    
                    # Déterminer la couleur
                    if note_sur_20 >= 16:
                        couleur = '#10b981'  # Vert - Excellent
                    elif note_sur_20 >= 14:
                        couleur = '#3b82f6'  # Bleu - Très bien
                    elif note_sur_20 >= 12:
                        couleur = '#8b5cf6'  # Violet - Bien
                    elif note_sur_20 >= 10:
                        couleur = '#f59e0b'  # Orange - Assez bien
                    elif note_sur_20 >= 8:
                        couleur = '#f97316'  # Orange foncé - Passable
                    else:
                        couleur = '#ef4444'  # Rouge - Insuffisant
                    
                    notes_evaluations[eval_dict['id']] = {
                        'note_obj': note_obj,
                        'couleur': couleur,
                        'note_sur_20': round(note_sur_20, 2)
                    }
                else:
                    notes_evaluations[eval_dict['id']] = {
                        'note_obj': note_obj,
                        'couleur': None,
                        'note_sur_20': None
                    }
            
            releve_data.append({
                'eleve': eleve,
                'moyenne': moyenne,
                'appreciation': appreciation,
                'notes_evaluations': notes_evaluations
            })
        
        # Trier les élèves par moyenne décroissante (les meilleures en premier)
        releve_data.sort(key=lambda x: x['moyenne'] if x['moyenne'] is not None else -1, reverse=True)
    
    # Statistiques globales
    total_classes = affectations.count()
    total_eleves = sum(aff.classe.nombre_eleves for aff in affectations)
    
    # Vérifier si on demande le relevé complet
    show_releve_complet = request.GET.get('releve_complet') == '1'
    resultats_releve_complet = []
    matieres_releve_complet = []
    releve_deja_soumis = False
    
    if show_releve_complet and classe_selectionnee and affectation_selectionnee:
        # Calculer toutes les moyennes pour le relevé complet
        from ..utils.calcul_moyennes_primaire import calculer_toutes_moyennes_classe
        resultats_releve_complet = calculer_toutes_moyennes_classe(classe_selectionnee, periode_selectionnee)
        matieres_releve_complet = list(affectation_selectionnee.matieres.all().order_by('nom'))
        
        # Vérifier si le relevé a déjà été soumis pour LES MATIÈRES DE CE PROFESSEUR
        releve_deja_soumis = MoyenneMatierePrimaire.objects.filter(
            classe=classe_selectionnee,
            periode_scolaire=periode_selectionnee,
            matiere__in=affectation_selectionnee.matieres.all(),  # Filtrer par matières du professeur
            soumis=True
        ).exists()
    
    context = {
        'professeur': professeur,
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'classes_grouped': classes_grouped_ordered,
        'classe_selectionnee': classe_selectionnee,
        'affectation_selectionnee': affectation_selectionnee,
        'matieres_data': matieres_data,
        'matiere_selectionnee': matiere_selectionnee,
        'releve_data': releve_data,
        'evaluations_matiere': evaluations_matiere,
        'total_classes': total_classes,
        'total_eleves': total_eleves,
        'show_releve_complet': show_releve_complet,
        'resultats_releve_complet': resultats_releve_complet,
        'matieres_releve_complet': matieres_releve_complet,
        'releve_deja_soumis': releve_deja_soumis,
    }
    
    return render(request, 'school_admin/enseignant/primaire/gestion_notes_primaire.html', context)


def creer_evaluation_primaire(request, classe_id):
    """
    Créer une évaluation pour une matière spécifique.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Vérifier que le professeur enseigne dans cette classe
    try:
        affectation = AffectationProfesseurPrimaire.objects.get(
            professeur=professeur,
            classe=classe,
            actif=True
        )
    except AffectationProfesseurPrimaire.DoesNotExist:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Récupérer les matières enseignées par le professeur dans cette classe
    matieres = affectation.matieres.all()
    
    # Récupérer les périodes
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                titre = request.POST.get('titre')
                description = request.POST.get('description', '')
                type_evaluation = request.POST.get('type_evaluation')
                matiere_id = request.POST.get('matiere')
                date_evaluation = request.POST.get('date_evaluation')
                bareme = request.POST.get('bareme', 20)
                periode_id = request.POST.get('periode')
                duree = request.POST.get('duree', '')
                
                # Validation
                if not all([titre, type_evaluation, matiere_id, date_evaluation, periode_id]):
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect(request.path)
                
                matiere = get_object_or_404(Matiere, id=matiere_id)
                periode = get_object_or_404(PeriodeScolaire, id=periode_id)
                
                # Vérifier que le professeur enseigne cette matière
                if matiere not in matieres:
                    messages.error(request, "Vous n'enseignez pas cette matière dans cette classe.")
                    return redirect(request.path)
                
                # Créer l'évaluation
                evaluation = EvaluationPrimaire.objects.create(
                    titre=titre,
                    description=description,
                    type_evaluation=type_evaluation,
                    matiere=matiere,
                    classe=classe,
                    professeur=professeur,
                    date_evaluation=date_evaluation,
                    bareme=bareme,
                    periode_scolaire=periode,
                    duree=int(duree) if duree else None,
                    actif=True
                )
                
                # Créer automatiquement les notes pour tous les élèves
                eleves = Eleve.objects.filter(classe=classe, actif=True)
                for eleve in eleves:
                    NotePrimaire.objects.create(
                        eleve=eleve,
                        evaluation_primaire=evaluation,
                        absent=False
                    )
                
                messages.success(request, f"Évaluation '{titre}' créée avec succès pour {matiere.nom}.")
                return redirect('enseignant_primaire:noter_eleves', classe_id=classe.id)
                
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'évaluation: {e}")
            messages.error(request, f"Une erreur est survenue: {str(e)}")
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'matieres': matieres,
        'periodes': periodes,
    }
    
    return render(request, 'school_admin/enseignant/primaire/creer_evaluation_primaire.html', context)


def noter_eleves_primaire(request, classe_id):
    """
    Noter les élèves par matière avec onglets dynamiques.
    Structure identique au système de base mais avec support multi-matières.
    """
    logger.info(f"Noter élèves primaire - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Vérifier l'affectation
    affectation = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Récupérer toutes les périodes scolaires de l'établissement
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer l'ID de la période sélectionnée (depuis GET ou par défaut la période en cours)
    periode_id = request.GET.get('periode', '')
    periode_selectionnee = None
    
    if periode_id:
        try:
            periode_selectionnee = periodes.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    # Si aucune période sélectionnée, prendre la première active
    if not periode_selectionnee:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Récupérer les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Préparer les données UNIQUEMENT pour les matières qui ont des évaluations OU des examens
    matieres_data = []
    for matiere in affectation.matieres.all():
        # Récupérer toutes les évaluations normales pour cette matière et période
        evaluations = list(EvaluationPrimaire.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=matiere,
            periode_scolaire=periode_selectionnee,
            actif=True
        ).order_by('date_evaluation'))
        
        # Récupérer aussi les sessions d'examens pour cette matière et période
        from ..model.session_examen_model import SessionExamen
        
        # Récupérer les sessions d'examen pour cette matière (PAS les créneaux !)
        sessions_examens = SessionExamen.objects.filter(
            classes=classe,
            periode=periode_selectionnee,
            matieres=matiere,
            actif=True
        ).distinct().order_by('date_debut')
        
        # Créer des pseudo-évaluations à partir des SESSIONS d'examens (pas des créneaux)
        evaluations_examens = []
        for session in sessions_examens:
            # Créer un objet qui simule une EvaluationPrimaire pour compatibilité
            class PseudoEvaluationExamen:
                def __init__(self, session):
                    self.id = f"examen_{session.id}"
                    self.session_id = session.id
                    self.titre = f"{session.nom_examen}"
                    self.type_evaluation = 'examen'
                    self.bareme = 20  # Les examens sont généralement sur 20
                    self.date_evaluation = session.date_debut
                    self.actif = True
                    self.est_examen = True
                    
            evaluations_examens.append(PseudoEvaluationExamen(session))
        
        # Fusionner les évaluations normales et les examens
        toutes_evaluations = evaluations + evaluations_examens
        
        # NE PAS ajouter la matière si elle n'a aucune évaluation NI examen
        if not toutes_evaluations:
            continue
        
        # Récupérer les notes existantes pour cette matière (évaluations + examens)
        from ..model.note_examen_model import NoteExamen
        
        notes_existantes = {}
        for eleve in eleves:
            notes_existantes[eleve.id] = {}
            
            # Notes des évaluations normales
            for evaluation in evaluations:
                note_obj = NotePrimaire.objects.filter(
                    eleve=eleve, 
                    evaluation_primaire=evaluation
                ).first()
                
                # Créer automatiquement la note si elle n'existe pas
                if not note_obj:
                    note_obj = NotePrimaire.objects.create(
                        eleve=eleve,
                        evaluation_primaire=evaluation,
                        absent=False
                    )
                
                notes_existantes[eleve.id][evaluation.id] = note_obj
            
            # Notes des examens
            for eval_examen in evaluations_examens:
                # Chercher la note d'examen basée sur (eleve, session, matiere)
                session = SessionExamen.objects.get(id=eval_examen.session_id)
                note_examen_obj = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session,
                    matiere=matiere
                ).first()
                
                # Si la note n'existe pas (cas d'élève ajouté après la création de la session)
                # On la crée maintenant
                if not note_examen_obj:
                    note_examen_obj, created = NoteExamen.objects.get_or_create(
                        eleve=eleve,
                        session_examen=session,
                        matiere=matiere,
                        defaults={
                            'classe': classe,
                            'professeur': professeur,
                            'absent': False,
                            'note': None,
                            'bareme': 20,
                        }
                    )
                
                # Créer un objet compatible avec NotePrimaire pour l'affichage
                class NoteExamenWrapper:
                    def __init__(self, note_examen):
                        self.id = f"examen_{note_examen.id}"
                        self.note_examen_id = note_examen.id
                        self.note = note_examen.note
                        self.absent = note_examen.absent
                        self.est_note_examen = True
                
                notes_existantes[eleve.id][eval_examen.id] = NoteExamenWrapper(note_examen_obj)
        
        # Récupérer les moyennes ENREGISTRÉES (pas les calculer automatiquement)
        moyennes = {}
        matiere_soumise = False
        for eleve in eleves:
            moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                matiere=matiere,
                periode_scolaire=periode_selectionnee
            ).first()
            if moyenne_obj:
                if moyenne_obj.moyenne is not None:
                    moyennes[eleve.id] = moyenne_obj.moyenne
                if moyenne_obj.soumis:
                    matiere_soumise = True
        
        # Compter le nombre de notes retenues pour chaque évaluation
        notes_retenues_par_eval = {}
        for evaluation in toutes_evaluations:
            if hasattr(evaluation, 'est_examen') and evaluation.est_examen:
                # Pour les examens - utiliser session_id au lieu de creneau_id
                nb_retenues = NoteExamen.objects.filter(
                    session_examen_id=evaluation.session_id,
                    matiere=matiere,
                    retenue=True,
                    absent=False
                ).exclude(note__isnull=True).count()
            else:
                # Pour les évaluations normales
                nb_retenues = NotePrimaire.objects.filter(
                    evaluation_primaire=evaluation,
                    retenue=True,
                    absent=False
                ).exclude(note__isnull=True).count()
            
            notes_retenues_par_eval[evaluation.id] = nb_retenues
        
        matieres_data.append({
            'matiere': matiere,
            'evaluations': toutes_evaluations,  # Inclut à la fois les évaluations normales et les examens
            'notes_existantes': notes_existantes,
            'moyennes': moyennes,
            'soumise': matiere_soumise,
            'notes_retenues_par_eval': notes_retenues_par_eval
        })
    
    # Vérifier si le relevé global est soumis (au moins une matière soumise)
    releve_global_soumis = any(m['soumise'] for m in matieres_data)
    
    # Traitement du formulaire POST (sauvegarde des notes OU calcul des moyennes)
    if request.method == 'POST':
        matiere_id = request.GET.get('matiere')
        action = request.POST.get('action', 'enregistrer')  # 'enregistrer' ou 'calculer'
        
        if not matiere_id:
            messages.error(request, "Matière non spécifiée.")
            return redirect('enseignant_primaire:noter_eleves', classe_id=classe_id)
        
        try:
            matiere = Matiere.objects.get(id=matiere_id)
        except Matiere.DoesNotExist:
            messages.error(request, "Matière invalide.")
            return redirect('enseignant_primaire:noter_eleves', classe_id=classe_id)
        
        # VÉRIFIER SI LE RELEVÉ A DÉJÀ ÉTÉ SOUMIS
        releve_soumis = MoyenneMatierePrimaire.objects.filter(
            classe=classe,
            matiere=matiere,
            periode_scolaire=periode_selectionnee,
            soumis=True
        ).exists()
        
        if releve_soumis:
            messages.error(request, f"⚠️ Le relevé de notes pour {matiere.nom} a déjà été soumis. Modification impossible.")
            return redirect(f"{request.path}?periode={periode_selectionnee.id}&matiere={matiere_id}")
        
        # ACTION 1: CALCULER LES MOYENNES
        if action == 'calculer':
            try:
                # Récupérer le mode de calcul et la pondération sélectionnés
                mode_calcul = request.POST.get('mode_calcul', 'toutes')  # toutes, 2_meilleures, 3_meilleures, 4_meilleures
                ponderation = request.POST.get('ponderation_examen', '50_50')  # 40_60, 50_50, 30_70
                
                # Récupérer les évaluations sélectionnées par l'enseignant
                evaluations_selectionnees = request.POST.getlist('evaluations_selectionnees')
                
                # Validation : au moins une évaluation doit être sélectionnée
                if not evaluations_selectionnees:
                    error_message = "⚠️ Veuillez sélectionner au moins une évaluation pour calculer les moyennes."
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                        return JsonResponse({'success': False, 'message': error_message})
                    messages.error(request, error_message)
                    return redirect(f"{request.path}?periode={periode_selectionnee.id}&matiere={matiere_id}")
                
                moyennes_calculees = 0
                moyennes_dict = {}
                notes_retenues_dict = {}
                
                for eleve in eleves:
                    # Calculer et enregistrer la moyenne selon le mode et la pondération choisis
                    moyenne_calculee = calculer_moyenne_avec_mode(
                        eleve, 
                        matiere, 
                        periode_selectionnee, 
                        mode_calcul,
                        ponderation,
                        evaluations_selectionnees  # Passer les évaluations sélectionnées
                    )
                    
                    if moyenne_calculee is not None:
                        # Enregistrer la moyenne
                        appreciation = get_appreciation_moyenne(moyenne_calculee)
                        MoyenneMatierePrimaire.objects.update_or_create(
                            eleve=eleve,
                            matiere=matiere,
                            periode_scolaire=periode_selectionnee,
                            defaults={
                                'classe': eleve.classe,
                                'moyenne': moyenne_calculee,
                                'appreciation': appreciation
                            }
                        )
                        moyennes_calculees += 1
                        moyennes_dict[eleve.id] = f"{moyenne_calculee:.2f}".replace('.', ',')
                
                # Compter les notes retenues par évaluation
                for eval_id_str in evaluations_selectionnees:
                    if eval_id_str.startswith('examen_'):
                        session_id = int(eval_id_str.replace('examen_', ''))
                        from ..model.note_examen_model import NoteExamen
                        count = NoteExamen.objects.filter(
                            session_examen_id=session_id,
                            matiere=matiere,
                            eleve__in=eleves,
                            retenue=True
                        ).count()
                        notes_retenues_dict[eval_id_str] = count
                    else:
                        count = NotePrimaire.objects.filter(
                            evaluation_primaire_id=int(eval_id_str),
                            eleve__in=eleves,
                            retenue=True
                        ).count()
                        notes_retenues_dict[eval_id_str] = count
                
                # Message détaillé selon le mode et la pondération
                mode_messages = {
                    'toutes': 'toutes les notes',
                    '2_meilleures': 'les 2 meilleures notes',
                    '3_meilleures': 'les 3 meilleures notes',
                    '4_meilleures': 'les 4 meilleures notes',
                }
                
                ponderation_messages = {
                    '40_60': '(40% devoirs, 60% examen)',
                    '50_50': '(50% devoirs, 50% examen)',
                    '30_70': '(30% devoirs, 70% examen)',
                }
                
                message_calcul = f"Moyennes calculées avec {mode_messages.get(mode_calcul, 'toutes les notes')}"
                if ponderation in ponderation_messages:
                    message_calcul += f" {ponderation_messages[ponderation]}"
                message_calcul += f" pour {moyennes_calculees} élève(s) en {matiere.nom} !"
                
                # Envoyer des notifications push personnalisées aux élèves
                if moyennes_calculees > 0:
                    try:
                        from school_admin.services.firebase_service import FirebaseService
                        
                        # Envoyer une notification personnalisée à chaque élève avec sa moyenne
                        notifications_envoyees = 0
                        for eleve in eleves:
                            # Récupérer la moyenne de l'élève
                            try:
                                moyenne_obj = MoyenneMatierePrimaire.objects.get(
                                    eleve=eleve,
                                    matiere=matiere,
                                    periode_scolaire=periode_selectionnee
                                )
                                
                                # Préparer la notification personnalisée
                                title = f"📊 Nouvelle moyenne - {matiere.nom}"
                                body = f"Vous avez {moyenne_obj.moyenne:.2f}/20 de moyenne en {matiere.nom}"
                                data = {
                                    'type': 'moyenne',
                                    'matiere_id': str(matiere.id),
                                    'matiere_nom': matiere.nom,
                                    'classe_id': str(classe.id),
                                    'periode_id': str(periode_selectionnee.id),
                                    'moyenne': str(moyenne_obj.moyenne),
                                    'url': '/eleve/notes-evaluations/'
                                }
                                
                                # Envoyer la notification à cet élève
                                result = FirebaseService.send_notification_to_multiple_users(
                                    users=[eleve],
                                    title=title,
                                    body=body,
                                    data=data
                                )
                                
                                if result['success_count'] > 0:
                                    notifications_envoyees += 1
                                try:
                                    ParentNotificationService.notify_moyenne(
                                        eleve=eleve,
                                        moyenne_obtenue=moyenne_obj.moyenne,
                                        matiere_nom=matiere.nom,
                                        periode_nom=getattr(periode_selectionnee, 'nom_periode', None),
                                        source=moyenne_obj,
                                    )
                                except Exception as notification_error:
                                    logger.error(
                                        "Erreur lors de la notification parent pour la moyenne: %s",
                                        notification_error,
                                        exc_info=True,
                                    )
                                    
                            except MoyenneMatierePrimaire.DoesNotExist:
                                logger.warning(f"Moyenne non trouvée pour {eleve.nom_complet}")
                                continue
                        
                        logger.info(f"Notifications moyennes personnalisées envoyées: {notifications_envoyees}/{moyennes_calculees} élèves")
                        
                    except Exception as e:
                        logger.error(f"Erreur lors de l'envoi des notifications de moyennes: {str(e)}")
                        # Ne pas bloquer le calcul des moyennes si les notifications échouent
                
                # Répondre en JSON si c'est une requête AJAX
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                    return JsonResponse({
                        'success': True,
                        'message': message_calcul,
                        'moyennes': moyennes_dict,
                        'notes_retenues': notes_retenues_dict
                    })
                
                messages.success(request, message_calcul)
                
            except Exception as e:
                logger.error(f"Erreur lors du calcul des moyennes: {e}")
                error_message = f"Erreur lors du calcul des moyennes: {str(e)}"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                    return JsonResponse({'success': False, 'message': error_message})
                messages.error(request, error_message)
            
            return redirect(f"{request.path}?periode={periode_selectionnee.id}&matiere={matiere_id}")
        
        # ACTION 2: ARRONDIR LES MOYENNES
        if action == 'arrondir':
            try:
                from ..utils.calcul_moyennes_primaire import arrondir_note_intelligemment
                
                moyennes_arrondies = 0
                moyennes_dict = {}
                
                for eleve in eleves:
                    # Récupérer la moyenne existante
                    moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                        eleve=eleve,
                        matiere=matiere,
                        periode_scolaire=periode_selectionnee
                    ).first()
                    
                    if moyenne_obj and moyenne_obj.moyenne is not None:
                        # Arrondir la moyenne
                        moyenne_arrondie = arrondir_note_intelligemment(moyenne_obj.moyenne)
                        
                        # Si la moyenne a changé, la mettre à jour
                        if moyenne_arrondie != moyenne_obj.moyenne:
                            moyenne_obj.moyenne = moyenne_arrondie
                            moyenne_obj.appreciation = get_appreciation_moyenne(moyenne_arrondie)
                            moyenne_obj.save()
                            moyennes_arrondies += 1
                        
                        moyennes_dict[eleve.id] = f"{moyenne_obj.moyenne:.2f}".replace('.', ',')
                
                if moyennes_arrondies > 0:
                    success_msg = f"✓ {moyennes_arrondies} moyenne(s) arrondie(s) avec succès pour {matiere.nom} !"
                else:
                    success_msg = "Aucune moyenne n'a été modifiée (déjà arrondies ou aucune moyenne enregistrée)."
                
                # Répondre en JSON si c'est une requête AJAX
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                    return JsonResponse({
                        'success': True,
                        'message': success_msg,
                        'moyennes': moyennes_dict,
                        'arrondies': moyennes_arrondies
                    })
                
                if moyennes_arrondies > 0:
                    messages.success(request, success_msg)
                else:
                    messages.info(request, success_msg)
                    
            except Exception as e:
                logger.error(f"Erreur lors de l'arrondi des moyennes: {e}")
                error_message = f"Erreur lors de l'arrondi: {str(e)}"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                    return JsonResponse({'success': False, 'message': error_message})
                messages.error(request, error_message)
            
            return redirect(f"{request.path}?periode={periode_selectionnee.id}&matiere={matiere_id}")
        
        # ACTION 3: ENREGISTRER LES NOTES
        # Récupérer les évaluations normales pour cette matière
        evaluations = EvaluationPrimaire.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=matiere,
            periode_scolaire=periode_selectionnee,
            actif=True
        )
        
        # Récupérer les sessions d'examen (PAS les créneaux!)
        sessions_examens = SessionExamen.objects.filter(
            classes=classe,
            periode=periode_selectionnee,
            matieres=matiere,
            actif=True
        ).distinct()
        
        notes_enregistrees = 0
        errors = []
        notes_dict = {}  # Dictionnaire pour stocker les notes enregistrées
        eleves_avec_notes_modifiees = {}  # Dictionnaire pour traquer les élèves avec notes modifiées {eleve: [notes]}
        
        try:
            with transaction.atomic():
                for eleve in eleves:
                    # Enregistrer les notes des évaluations normales
                    for evaluation in evaluations:
                        # Récupérer la note saisie
                        note_value = request.POST.get(f'note_{eleve.id}_{evaluation.id}', '').strip()
                        
                        # Récupérer ou créer l'objet Note
                        note_obj, created = NotePrimaire.objects.get_or_create(
                            eleve=eleve,
                            evaluation_primaire=evaluation,
                            defaults={'absent': False}
                        )
                        
                        if note_value:
                            try:
                                note_decimal = Decimal(note_value)
                                
                                # Valider que la note est dans les limites
                                if note_decimal < 0 or note_decimal > evaluation.bareme:
                                    errors.append(f"Note invalide pour {eleve.nom_complet}: {note_decimal} (max: {evaluation.bareme})")
                                    continue
                                
                                # Vérifier si la note a changé
                                note_a_change = (
                                    created or 
                                    note_obj.note != note_decimal or 
                                    note_obj.absent != False
                                )
                                
                                note_obj.note = note_decimal
                                note_obj.absent = False
                                # Ne pas marquer comme retenue ici, cela sera fait lors du calcul
                                note_obj.save()
                                
                                # Incrémenter seulement si la note a vraiment changé
                                if note_a_change:
                                    notes_enregistrees += 1
                                    # Ajouter cet élève à la liste des élèves à notifier
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
                                            matiere_nom=matiere.nom,
                                            note_obtenue=note_decimal,
                                            bareme=evaluation.bareme,
                                            evaluation_nom=evaluation.titre,
                                            professeur_nom=getattr(professeur, 'nom_complet', str(professeur)),
                                            date_evaluation=getattr(evaluation, 'date_evaluation', None),
                                            source=note_obj,
                                        )
                                    except Exception as notification_error:
                                        logger.error(
                                            "Erreur lors de la notification parent pour la note d'évaluation: %s",
                                            notification_error,
                                            exc_info=True,
                                        )
                                
                                # Ajouter au dictionnaire pour AJAX
                                notes_dict[f'note_{eleve.id}_{evaluation.id}'] = str(note_decimal).replace('.', ',')
                                
                            except (ValueError, TypeError):
                                errors.append(f"Valeur invalide pour {eleve.nom_complet}: {note_value}")
                    
                    # Enregistrer les notes d'examens
                    for session in sessions_examens:
                        # Récupérer la note saisie (format: note_{eleve_id}_examen_{session_id})
                        # Le template utilise eval.id qui est "examen_{session.id}"
                        note_value = request.POST.get(f'note_{eleve.id}_examen_{session.id}', '').strip()
                        
                        # Récupérer ou créer l'objet NoteExamen basé sur (eleve, session, matiere)
                        note_examen_obj, created = NoteExamen.objects.get_or_create(
                            eleve=eleve,
                            session_examen=session,
                            matiere=matiere,
                            defaults={
                                'professeur': professeur,
                                'classe': classe,
                                'absent': False,
                                'bareme': 20,
                            }
                        )
                        
                        if note_value:
                            try:
                                note_decimal = Decimal(note_value)
                                
                                # Valider que la note est dans les limites (examens sur 20)
                                if note_decimal < 0 or note_decimal > 20:
                                    errors.append(f"Note d'examen invalide pour {eleve.nom_complet}: {note_decimal} (max: 20)")
                                    continue
                                
                                # Vérifier si la note a changé
                                note_a_change = (
                                    created or 
                                    note_examen_obj.note != note_decimal or 
                                    note_examen_obj.absent != False
                                )
                                
                                note_examen_obj.note = note_decimal
                                note_examen_obj.absent = False
                                # Ne pas marquer comme retenue ici, cela sera fait lors du calcul
                                note_examen_obj.save()
                                
                                # Incrémenter seulement si la note a vraiment changé
                                if note_a_change:
                                    notes_enregistrees += 1
                                    # Ajouter cet élève à la liste des élèves à notifier
                                    if eleve not in eleves_avec_notes_modifiees:
                                        eleves_avec_notes_modifiees[eleve] = []
                                    eleves_avec_notes_modifiees[eleve].append({
                                        'type': 'examen',
                                        'nom': session.nom_examen,
                                        'note': note_decimal,
                                        'bareme': 20
                                    })

                                    try:
                                        ParentNotificationService.notify_note(
                                            eleve=eleve,
                                            matiere_nom=matiere.nom,
                                            note_obtenue=note_decimal,
                                            bareme=getattr(note_examen_obj, 'bareme', 20),
                                            evaluation_nom=session.nom_examen,
                                            professeur_nom=getattr(professeur, 'nom_complet', str(professeur)),
                                            date_evaluation=getattr(session, 'date_debut', None),
                                            source=note_examen_obj,
                                        )
                                    except Exception as notification_error:
                                        logger.error(
                                            "Erreur lors de la notification parent pour la note d'examen: %s",
                                            notification_error,
                                            exc_info=True,
                                        )
                                
                                # Ajouter au dictionnaire pour AJAX
                                notes_dict[f'note_{eleve.id}_examen_{session.id}'] = str(note_decimal).replace('.', ',')
                                
                            except (ValueError, TypeError):
                                errors.append(f"Valeur invalide pour {eleve.nom_complet}: {note_value}")
            
            # Préparer la réponse
            if errors:
                error_msg = "; ".join(errors[:3])  # Limiter à 3 erreurs
                if len(errors) > 3:
                    error_msg += f" (et {len(errors)-3} autre(s))"
            else:
                error_msg = None
            
            if notes_enregistrees > 0:
                success_msg = f"{notes_enregistrees} note(s) enregistrée(s) avec succès pour {matiere.nom} !"
                
                # Envoyer des notifications push personnalisées uniquement aux élèves concernés
                if eleves_avec_notes_modifiees:
                    try:
                        from school_admin.services.firebase_service import FirebaseService
                        
                        notifications_envoyees = 0
                        for eleve, notes_modifiees in eleves_avec_notes_modifiees.items():
                            # Préparer un message personnalisé avec les notes modifiées
                            if len(notes_modifiees) == 1:
                                # Une seule note modifiée
                                note_info = notes_modifiees[0]
                                title = f"📚 Nouvelle note - {matiere.nom}"
                                body = f"Vous avez {note_info['note']}/{note_info['bareme']} en {matiere.nom} ({note_info['nom']})"
                            else:
                                # Plusieurs notes modifiées
                                title = f"📚 Nouvelles notes - {matiere.nom}"
                                body = f"{len(notes_modifiees)} notes enregistrées en {matiere.nom}"
                            
                            data = {
                                'type': 'notes',
                                'matiere_id': str(matiere.id),
                                'matiere_nom': matiere.nom,
                                'classe_id': str(classe.id),
                                'nombre_notes': str(len(notes_modifiees)),
                                'url': '/eleve/notes-evaluations/'
                            }
                            
                            # Envoyer la notification à cet élève spécifique
                            result = FirebaseService.send_notification_to_multiple_users(
                                users=[eleve],
                                title=title,
                                body=body,
                                data=data
                            )
                            
                            if result['success_count'] > 0:
                                notifications_envoyees += 1
                        
                        logger.info(f"Notifications personnalisées envoyées: {notifications_envoyees}/{len(eleves_avec_notes_modifiees)} élèves")
                        
                    except Exception as e:
                        logger.error(f"Erreur lors de l'envoi des notifications: {str(e)}")
                        # Ne pas bloquer l'enregistrement des notes si les notifications échouent
            else:
                success_msg = "Aucune note n'a été modifiée."
            
            # Répondre en JSON si c'est une requête AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                return JsonResponse({
                    'success': notes_enregistrees > 0,
                    'message': success_msg,
                    'errors': errors,
                    'notes_enregistrees': notes_dict  # Renvoyer le dictionnaire de notes
                })
            
            # Sinon, afficher les messages et rediriger
            if errors:
                for error in errors:
                    messages.warning(request, error)
            
            if notes_enregistrees > 0:
                messages.success(request, success_msg)
            else:
                messages.info(request, success_msg)
                
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement des notes: {e}")
            error_message = f"Erreur lors de l'enregistrement: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
        
        return redirect(f"{request.path}?periode={periode_selectionnee.id}&matiere={matiere_id}")
    
    # Appliquer le verrouillage global à toutes les matières si le relevé est soumis
    if releve_global_soumis:
        for matiere_data in matieres_data:
            matiere_data['soumise'] = True
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'matieres_data': matieres_data,
        'eleves': eleves,
        'releve_global_soumis': releve_global_soumis,
    }
    
    return render(request, 'school_admin/enseignant/primaire/noter_eleves_primaire.html', context)


def voir_releve_primaire(request, classe_id):
    """
    Redirige vers la page de gestion des notes avec le relevé complet en modal.
    Cette vue est conservée pour maintenir la compatibilité des URLs.
    """
    periode_id = request.GET.get('periode', '')
    
    if periode_id:
        return redirect(f'/enseignant/primaire/notes/?periode={periode_id}&classe={classe_id}&releve_complet=1')
    else:
        return redirect(f'/enseignant/primaire/notes/?classe={classe_id}&releve_complet=1')


def soumettre_releve_primaire(request, classe_id):
    """
    Soumet le relevé de notes complet (marque toutes les moyennes comme soumises).
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    if request.method != 'POST':
        messages.error(request, "Méthode non autorisée.")
        return redirect('enseignant_primaire:gestion_notes')
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Vérifier l'affectation
    try:
        affectation = AffectationProfesseurPrimaire.objects.get(
            professeur=professeur,
            classe=classe,
            actif=True
        )
    except AffectationProfesseurPrimaire.DoesNotExist:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Récupérer la période
    periode_id = request.POST.get('periode_id')
    if not periode_id:
        messages.error(request, "Période non spécifiée.")
        return redirect('enseignant_primaire:gestion_notes')
    
    periode = get_object_or_404(PeriodeScolaire, id=periode_id)
    
    try:
        from django.utils import timezone
        from django.db import transaction
        from ..model.creneau_examen_model import CreneauExamen
        from ..model.note_examen_model import NoteExamen
        from ..model.session_examen_model import SessionExamen
        
        # Récupérer les matières enseignées par ce professeur dans cette classe
        matieres_professeur = affectation.matieres.all()
        
        # Récupérer UNIQUEMENT les moyennes des matières enseignées par ce professeur
        moyennes = MoyenneMatierePrimaire.objects.filter(
            classe=classe,
            periode_scolaire=periode,
            matiere__in=matieres_professeur
        )
        
        # Vérifier si déjà soumis
        if moyennes.filter(soumis=True).exists():
            messages.warning(request, f"Le relevé pour {periode.nom_periode} a déjà été soumis.")
        else:
            with transaction.atomic():
                # ÉTAPE 1 : Marquer comme "absent" toutes les notes non saisies
                eleves = Eleve.objects.filter(classe=classe)
                
                # Récupérer toutes les évaluations pour cette classe et période
                # FILTRÉES par les matières du professeur
                evaluations_normales = EvaluationPrimaire.objects.filter(
                    classe=classe,
                    professeur=professeur,
                    periode_scolaire=periode,
                    matiere__in=matieres_professeur,
                    actif=True
                )
                
                # Récupérer toutes les sessions d'examens pour cette classe et période
                sessions_examens = SessionExamen.objects.filter(
                    classes=classe,
                    periode=periode,
                    actif=True
                ).prefetch_related('matieres').distinct()
                
                nb_absents_marques = 0
                
                # Pour chaque élève, vérifier les notes manquantes
                for eleve in eleves:
                    # Vérifier les évaluations normales
                    for evaluation in evaluations_normales:
                        note_existe = NotePrimaire.objects.filter(
                            eleve=eleve,
                            evaluation_primaire=evaluation
                        ).exists()
                        
                        if not note_existe:
                            # Créer une note avec absent=True
                            NotePrimaire.objects.create(
                                eleve=eleve,
                                evaluation_primaire=evaluation,
                                note=None,
                                absent=True
                            )
                            nb_absents_marques += 1
                    
                    # Vérifier les examens
                    for session in sessions_examens:
                        # Pour chaque matière de la session, FILTRER par les matières du professeur
                        for matiere in session.matieres.all():
                            # Ne traiter que les matières enseignées par ce professeur
                            if matiere not in matieres_professeur:
                                continue
                            
                            # Utiliser get_or_create basé sur (eleve, session, matiere)
                            note_examen_obj, created = NoteExamen.objects.get_or_create(
                                eleve=eleve,
                                session_examen=session,
                                matiere=matiere,
                                defaults={
                                    'note': None,
                                    'absent': True,
                                    'professeur': professeur,
                                    'classe': classe,
                                    'bareme': 20,
                                }
                            )
                            # Si la note existait déjà et n'était pas marquée absente, on la met à jour
                            if not created and not note_examen_obj.absent:
                                note_examen_obj.absent = True
                                note_examen_obj.save()
                                nb_absents_marques += 1
                            elif created:
                                nb_absents_marques += 1
                
                # ÉTAPE 2 : Marquer toutes les moyennes comme soumises
                nb_soumises = moyennes.update(
                    soumis=True,
                    date_soumission=timezone.now()
                )
                
                try:
                    DirecteurNotificationService.notify_releve_submission(
                        classe=classe,
                        professeur=professeur,
                        periode=periode,
                        matieres=[m.nom for m in matieres_professeur],
                        source=None,
                    )
                except Exception as notification_error:
                    logger.error(
                        "Erreur lors de la notification directeur pour le relevé primaire: %s",
                        notification_error,
                        exc_info=True,
                    )
                
                messages.success(request, f"✓ Relevé soumis pour {periode.nom_periode} ! {nb_soumises} moyenne(s) verrouillée(s), {nb_absents_marques} absence(s) enregistrée(s).")
        
    except Exception as e:
        logger.error(f"Erreur lors de la soumission du relevé: {e}")
        messages.error(request, f"Erreur lors de la soumission : {str(e)}")
    
    return redirect(f'/enseignant/primaire/notes/?periode={periode_id}&classe={classe_id}')


def imprimer_releve_primaire(request, classe_id):
    """
    Imprimer le relevé de notes (version PDF).
    """
    # Réutiliser la logique de voir_releve_primaire mais avec un template d'impression
    if not isinstance(request.user, Professeur):
        return HttpResponse("Accès non autorisé", status=403)
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id)
    
    try:
        affectation = AffectationProfesseurPrimaire.objects.get(
            professeur=professeur,
            classe=classe,
            actif=True
        )
    except AffectationProfesseurPrimaire.DoesNotExist:
        return HttpResponse("Vous n'êtes pas affecté à cette classe.", status=403)
    
    periode_id = request.GET.get('periode')
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    
    if periode_id:
        periode_selectionnee = get_object_or_404(PeriodeScolaire, id=periode_id)
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    resultats = calculer_toutes_moyennes_classe(classe, periode_selectionnee)
    matieres = list(affectation.matieres.all().order_by('nom'))
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'periode_selectionnee': periode_selectionnee,
        'matieres': matieres,
        'resultats': resultats,
        'etablissement': professeur.etablissement,
        'date_impression': date.today(),
    }
    
    return render(request, 'school_admin/enseignant/primaire/imprimer_releve_primaire.html', context)


def liste_evaluations_primaire(request):
    """
    Liste de toutes les évaluations avec filtres par matière, période, classe.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Filtres
    matiere_id = request.GET.get('matiere')
    periode_id = request.GET.get('periode')
    classe_id = request.GET.get('classe')
    
    # Récupérer toutes les évaluations du professeur
    evaluations = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe', 'matiere', 'periode_scolaire').order_by('-date_evaluation')
    
    # Appliquer les filtres
    if matiere_id:
        evaluations = evaluations.filter(matiere_id=matiere_id)
    if periode_id:
        evaluations = evaluations.filter(periode_scolaire_id=periode_id)
    if classe_id:
        evaluations = evaluations.filter(classe_id=classe_id)
    
    # Récupérer les options de filtres
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).prefetch_related('matieres')
    
    matieres_enseignees = set()
    classes_enseignees = []
    for affectation in affectations:
        matieres_enseignees.update(affectation.matieres.all())
        classes_enseignees.append(affectation.classe)
    
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    context = {
        'professeur': professeur,
        'evaluations': evaluations,
        'matieres_enseignees': sorted(matieres_enseignees, key=lambda m: m.nom),
        'classes_enseignees': classes_enseignees,
        'periodes': periodes,
        'matiere_selectionnee': matiere_id,
        'periode_selectionnee': periode_id,
        'classe_selectionnee': classe_id,
    }
    
    return render(request, 'school_admin/enseignant/primaire/liste_evaluations_primaire.html', context)


def calculer_moyennes_classe_primaire(request, classe_id):
    """
    Calculer et enregistrer toutes les moyennes d'une classe.
    """
    if not isinstance(request.user, Professeur):
        return JsonResponse({'success': False, 'error': 'Accès non autorisé'})
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id)
    
    try:
        affectation = AffectationProfesseurPrimaire.objects.get(
            professeur=professeur,
            classe=classe,
            actif=True
        )
    except AffectationProfesseurPrimaire.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Vous n\'êtes pas affecté à cette classe'})
    
    periode_id = request.POST.get('periode_id')
    periode = get_object_or_404(PeriodeScolaire, id=periode_id)
    
    try:
        # Calculer toutes les moyennes
        eleves = Eleve.objects.filter(classe=classe, actif=True)
        matieres = affectation.matieres.all()
        
        moyennes_calculees = 0
        for eleve in eleves:
            for matiere in matieres:
                moyenne_obj, created = MoyenneMatierePrimaire.calculer_et_enregistrer(eleve, matiere, periode)
                if created or moyenne_obj:
                    moyennes_calculees += 1
        
        # Envoyer des notifications push personnalisées aux élèves
        if moyennes_calculees > 0 and eleves.exists():
            try:
                from school_admin.services.firebase_service import FirebaseService
                
                # Envoyer une notification personnalisée à chaque élève avec ses moyennes
                notifications_envoyees = 0
                for eleve in eleves:
                    # Récupérer toutes les moyennes de l'élève pour cette période
                    moyennes_eleve = MoyenneMatierePrimaire.objects.filter(
                        eleve=eleve,
                        periode_scolaire=periode
                    )
                    
                    if moyennes_eleve.exists():
                        # Calculer la moyenne générale
                        total_moyennes = sum([m.moyenne for m in moyennes_eleve if m.moyenne])
                        nombre_matieres = moyennes_eleve.count()
                        moyenne_generale = total_moyennes / nombre_matieres if nombre_matieres > 0 else 0
                        
                        # Préparer la notification personnalisée
                        title = f"📊 Vos moyennes - {periode.nom_periode}"
                        body = f"Vous avez {moyenne_generale:.2f}/20 de moyenne générale pour {periode.nom_periode}"
                        data = {
                            'type': 'moyennes_generales',
                            'classe_id': str(classe.id),
                            'periode_id': str(periode.id),
                            'moyenne_generale': str(moyenne_generale),
                            'url': '/eleve/notes-evaluations/'
                        }
                        
                        # Envoyer la notification à cet élève
                        result = FirebaseService.send_notification_to_multiple_users(
                            users=[eleve],
                            title=title,
                            body=body,
                            data=data
                        )
                        
                        if result['success_count'] > 0:
                            notifications_envoyees += 1
                
                logger.info(f"Notifications moyennes personnalisées envoyées: {notifications_envoyees}/{eleves.count()} élèves")
                
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi des notifications de moyennes: {str(e)}")
                # Ne pas bloquer le calcul des moyennes si les notifications échouent
        
        return JsonResponse({
            'success': True,
            'message': f'Moyennes calculées pour {eleves.count()} élèves et {matieres.count()} matières'
        })
        
    except Exception as e:
        logger.error(f"Erreur lors du calcul des moyennes: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


# Vues pour la gestion des présences (logique identique mais avec template primaire)
def liste_presence_primaire(request, classe_id):
    """
    Page pour prendre la liste de présence d'une classe (version primaire).
    Gestion de 3 appels maximum par jour.
    """
    logger.info(f"Liste présence primaire - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Vérifier l'affectation primaire
    affectation = get_object_or_404(
        AffectationProfesseurPrimaire,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Date du jour
    from datetime import date
    from ..model.presence_model import Presence, ListePresence
    today = date.today()
    
    # Récupérer le numéro d'appel demandé (par défaut, le prochain disponible)
    numero_appel_demande = request.GET.get('appel', None)
    
    # Compter le nombre d'appels déjà effectués aujourd'hui
    appels_du_jour = ListePresence.objects.filter(
        classe=classe,
        date=today,
        validee=True
    ).order_by('numero_appel')
    
    nombre_appels_valides = appels_du_jour.count()
    
    # Déterminer le prochain numéro d'appel disponible
    if numero_appel_demande:
        prochain_numero_appel = int(numero_appel_demande)
    else:
        if nombre_appels_valides == 0:
            prochain_numero_appel = 1
        elif nombre_appels_valides < 3:
            # Récupérer le dernier numéro d'appel et ajouter 1
            dernier_appel = appels_du_jour.last()
            prochain_numero_appel = dernier_appel.numero_appel + 1 if dernier_appel else 1
        else:
            prochain_numero_appel = None  # Maximum atteint
    
    # Vérifier si le maximum d'appels est atteint
    limite_atteinte = nombre_appels_valides >= 3
    
    # Vérifier s'il existe déjà une liste de présence non validée pour ce numéro d'appel
    liste_presence_actuelle = None
    if prochain_numero_appel:
        liste_presence_actuelle = ListePresence.objects.filter(
            classe=classe,
            date=today,
            numero_appel=prochain_numero_appel,
            validee=False
        ).first()
        
        # Si aucune liste non validée n'existe et qu'on n'a pas atteint la limite, en créer une
        if not liste_presence_actuelle and not limite_atteinte:
            liste_presence_actuelle = ListePresence.objects.create(
                classe=classe,
                date=today,
                numero_appel=prochain_numero_appel,
                professeur=professeur,
                etablissement=classe.etablissement
            )
    
    # Récupérer tous les élèves actifs de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les présences pour l'appel en cours (si existe)
    eleves_avec_presence = []
    if liste_presence_actuelle:
        # Récupérer les présences liées à cet appel spécifique
        presences_existantes = Presence.objects.filter(
            classe=classe,
            date=today,
            numero_appel=prochain_numero_appel
        ).select_related('eleve')
        
        # Créer un dictionnaire des présences existantes
        presences_dict = {p.eleve.id: p for p in presences_existantes}
        
        # Construire la liste des élèves avec leur statut
        for eleve in eleves:
            presence = presences_dict.get(eleve.id)
            eleves_avec_presence.append({
                'eleve': eleve,
                'presence': presence,
                'statut': presence.statut if presence else 'present'
            })
    else:
        # Aucune liste actuelle (limite atteinte)
        for eleve in eleves:
            eleves_avec_presence.append({
                'eleve': eleve,
                'presence': None,
                'statut': 'present'
            })
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'eleves_avec_presence': eleves_avec_presence,
        'liste_presence': liste_presence_actuelle,
        'today': today,
        'nombre_eleves': eleves.count(),
        'numero_appel_actuel': prochain_numero_appel,
        'nombre_appels_valides': nombre_appels_valides,
        'limite_atteinte': limite_atteinte,
        'appels_du_jour': appels_du_jour,
    }
    
    return render(request, 'school_admin/enseignant/primaire/liste_presence_primaire.html', context)


def valider_presence_primaire(request, classe_id):
    """
    Enregistre et valide la liste de présence (version primaire).
    Gère les appels multiples avec numéro d'appel.
    """
    logger.info(f"Validation présence primaire - User: {request.user}, Classe ID: {classe_id}")
    
    if request.method != 'POST':
        return redirect('enseignant_primaire:liste_presence', classe_id=classe_id)
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Vérifier l'affectation primaire
    affectation = get_object_or_404(
        AffectationProfesseurPrimaire,
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Date du jour
    from datetime import date
    from ..model.presence_model import Presence, ListePresence
    from django.utils import timezone
    today = date.today()
    
    # Récupérer le numéro d'appel depuis le formulaire
    numero_appel = int(request.POST.get('numero_appel', 1))
    
    try:
        with transaction.atomic():
            # Récupérer la liste de présence pour ce numéro d'appel
            liste_presence = get_object_or_404(
                ListePresence,
                classe=classe,
                date=today,
                numero_appel=numero_appel
            )
            
            # Si déjà validée, interdire la modification
            if liste_presence.validee:
                messages.warning(request, f"L'appel n°{numero_appel} a déjà été validé pour aujourd'hui.")
                return redirect('enseignant_primaire:liste_presence', classe_id=classe_id)
            
            # Parcourir les données POST pour enregistrer les présences
            nombre_presents = 0
            nombre_absents = 0
            nombre_retards = 0
            
            for key, value in request.POST.items():
                if key.startswith('presence_'):
                    eleve_id = key.replace('presence_', '')
                    try:
                        eleve = Eleve.objects.get(id=eleve_id, classe=classe, actif=True)
                        
                        # Créer ou mettre à jour la présence avec le numéro d'appel
                        presence, created = Presence.objects.update_or_create(
                            eleve=eleve,
                            classe=classe,
                            date=today,
                            numero_appel=numero_appel,
                            defaults={
                                'professeur': professeur,
                                'etablissement': classe.etablissement,
                                'statut': value
                            }
                        )
                        
                        # Compter les présents, absents et retards
                        if value == 'present':
                            nombre_presents += 1
                        elif value in ['absent', 'absent_justifie']:
                            nombre_absents += 1
                        elif value == 'retard':
                            nombre_retards += 1
                    
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
                f"✓ Appel n°{numero_appel} validé avec succès ! {nombre_presents} présent(s), {nombre_absents} absent(s), {nombre_retards} retard(s)."
            )
            
            # Envoyer des notifications push aux élèves
            try:
                from school_admin.services.firebase_service import FirebaseService
                
                # Récupérer toutes les présences de cette liste
                presences = Presence.objects.filter(
                    classe=classe,
                    date=today,
                    numero_appel=numero_appel
                )
                
                # Préparer la date en clair avec heure
                from django.utils import timezone
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

                    if statut == 'present':
                        emoji = "✅"
                        title = "📋 Appel de classe"
                        body = (
                            f"Vous avez été présent(e) lors de l'appel du {date_claire}."
                        )
                    elif statut == 'absent':
                        emoji = "❌"
                        title = "⚠️ Absence enregistrée"
                        body = (
                            f"Vous avez été absent(e) lors de l'appel du {date_claire}."
                        )
                    elif statut == 'absent_justifie':
                        emoji = "📝"
                        title = "📋 Absence justifiée"
                        body = (
                            f"Votre absence du {date_claire} a été enregistrée comme justifiée."
                        )
                    elif statut == 'retard':
                        emoji = "⏰"
                        title = "⏰ Retard enregistré"
                        body = (
                            f"Vous avez été en retard lors de l'appel du {date_claire}."
                        )
                    else:
                        continue
                    
                    data = {
                        'type': 'presence',
                        'presence_id': str(presence.id),
                        'statut': statut,
                        'date': today.isoformat(),
                        'numero_appel': str(numero_appel),
                        'classe': classe.nom,
                        'url': '/eleve/dashboard/'
                    }
                    
                    # Envoyer la notification à l'élève
                    result = FirebaseService.send_notification_to_multiple_users(
                        [presence.eleve], title, body, data
                    )
                    
                    if result['success_count'] > 0:
                        logger.info(f"Notification de présence envoyée à {presence.eleve.nom_complet} - Statut: {presence.statut}")
                    else:
                        logger.warning(f"Échec de l'envoi de notification de présence à {presence.eleve.nom_complet}")

                    try:
                        EleveNotificationService.notify_presence(
                            presence,
                            titre=title,
                            message=body,
                            payload=data,
                        )
                    except Exception:
                        logger.exception(
                            "Échec notification élève %s pour présence (primaire)",
                            getattr(presence.eleve, "id", "N/A"),
                        )

                    try:
                        ParentNotificationService.notify_presence(
                            presence,
                            date_description=date_claire,
                        )
                    except Exception:
                        logger.exception(
                            "Échec notification parent pour présence (primaire) %s",
                            getattr(presence, "id", "N/A"),
                        )

            except Exception as e:
                logger.error(f"Erreur lors de l'envoi des notifications de présence: {str(e)}")
            
    except Exception as e:
        logger.error(f"Erreur lors de la validation de la présence: {str(e)}")
        messages.error(request, f"Erreur lors de la validation : {str(e)}")
    
    return redirect('enseignant_primaire:liste_presence', classe_id=classe_id)


def modifier_presence_eleve_primaire(request, presence_id):
    """
    Modifier une présence (réutilise la logique standard).
    """
    from ..personal_views.enseignant_view import modifier_presence_eleve
    return modifier_presence_eleve(request, presence_id)


def historique_presence_eleve_primaire(request, eleve_id):
    """
    Historique des présences d'un élève (réutilise la logique standard).
    """
    from ..personal_views.enseignant_view import historique_presence_eleve
    return historique_presence_eleve(request, eleve_id)


def justifier_absence_eleve_primaire(request):
    """
    Justifier une absence (réutilise la logique standard).
    """
    from ..personal_views.enseignant_view import justifier_absence_eleve
    return justifier_absence_eleve(request)


# Vues pour la gestion des sanctions (réutilisation de la logique existante)
def soumettre_sanction_eleve_primaire(request):
    """
    Traite le formulaire de soumission d'une sanction (version primaire).
    """
    logger.info(f"Soumission sanction primaire - User: {request.user}")
    
    if request.method != 'POST':
        messages.error(request, "Méthode non autorisée.")
        return redirect('enseignant_primaire:gestion_eleves')
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.sanction_model import Sanction
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
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Récupérer l'élève et la classe
    eleve = get_object_or_404(Eleve, id=eleve_id, actif=True)
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier l'affectation primaire
    affectation = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas autorisé à sanctionner cet élève.")
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Convertir la date
    try:
        date_sanction = datetime.strptime(date_sanction_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, "Format de date invalide.")
        return redirect('enseignant_primaire:gestion_eleves')
    
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
        
        logger.info(f"Sanction primaire créée - Élève: {eleve.nom_complet}, Type: {type_sanction}, Raison: {raison}")
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
                    "Échec notification élève %s pour sanction (primaire)",
                    getattr(eleve, "id", "N/A"),
                )

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi des notifications de sanction: {str(e)}")

        try:
            DirecteurNotificationService.notify_sanction(sanction)
        except Exception as notification_error:
            logger.error(
                "Erreur lors de la notification directeur pour la sanction (primaire): %s",
                notification_error,
                exc_info=True,
            )

        try:
            ParentNotificationService.notify_sanction(sanction)
        except Exception as notification_error:
            logger.error(
                "Erreur lors de la notification parent pour la sanction: %s",
                notification_error,
                exc_info=True,
            )
        
    except Exception as e:
        logger.error(f"Erreur création sanction primaire: {str(e)}")
        messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
    
    return redirect('enseignant_primaire:gestion_eleves')


def historique_sanctions_eleve_primaire(request, eleve_id):
    """
    Historique des sanctions d'un élève (réutilise la logique standard).
    """
    from ..personal_views.enseignant_view import historique_sanctions_eleve
    return historique_sanctions_eleve(request, eleve_id)


def liste_sanctions_classe_primaire(request, classe_id):
    """
    Page de la liste de toutes les sanctions d'une classe (version primaire).
    """
    logger.info(f"Liste sanctions classe primaire - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.sanction_model import Sanction
    from django.db.models import Count
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier l'affectation primaire
    affectation = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_eleves')
    
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
    
    return render(request, 'school_admin/enseignant/primaire/liste_sanctions_classe_primaire.html', context)


# Vues pour le détail de l'élève et de la classe
def detail_eleve_primaire(request, eleve_id):
    """
    Détail d'un élève avec notes multi-matières.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    eleve = get_object_or_404(Eleve, id=eleve_id)
    
    # Vérifier que le professeur enseigne dans la classe de l'élève
    try:
        affectation = AffectationProfesseurPrimaire.objects.get(
            professeur=professeur,
            classe=eleve.classe,
            actif=True
        )
    except AffectationProfesseurPrimaire.DoesNotExist:
        messages.error(request, "Vous n'enseignez pas dans la classe de cet élève.")
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Récupérer l'onglet sélectionné
    onglet = request.GET.get('onglet', 'informations')
    
    # Récupérer la période pour les notes
    periode_id = request.GET.get('periode')
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    if periode_id:
        periode_selectionnee = get_object_or_404(PeriodeScolaire, id=periode_id)
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Données pour l'onglet notes
    if onglet == 'notes' and periode_selectionnee:
        matieres = affectation.matieres.all()
        notes_par_matiere = []
        
        for matiere in matieres:
            # Récupérer toutes les évaluations et notes
            evaluations = EvaluationPrimaire.objects.filter(
                classe=eleve.classe,
                matiere=matiere,
                periode_scolaire=periode_selectionnee,
                actif=True
            ).order_by('date_evaluation')
            
            notes_objs = NotePrimaire.objects.filter(
                eleve=eleve,
                evaluation_primaire__in=evaluations
            ).select_related('evaluation_primaire')
            
            # Créer un dictionnaire des notes indexé par evaluation_id
            notes_dict = {note.evaluation_primaire.id: note for note in notes_objs}
            
            # Récupérer les sessions d'examen (PAS les créneaux!) pour cette matière et période
            from ..model.session_examen_model import SessionExamen
            sessions_examen = SessionExamen.objects.filter(
                classes=eleve.classe,
                periode=periode_selectionnee,
                matieres=matiere,
                actif=True
            ).distinct()
            
            # Récupérer les notes d'examen basées sur (eleve, session, matiere)
            notes_examen_objs = NoteExamen.objects.filter(
                eleve=eleve,
                session_examen__in=sessions_examen,
                matiere=matiere
            ).select_related('session_examen')
            
            # Ajouter les notes d'examen au dictionnaire avec un préfixe "examen_"
            for note_examen in notes_examen_objs:
                notes_dict[f'examen_{note_examen.session_examen.id}'] = note_examen
            
            # Créer une liste combinée d'évaluations et d'examens
            evaluations_list = list(evaluations)
            for session in sessions_examen:
                # Créer un pseudo-objet pour l'examen
                class PseudoExamen:
                    def __init__(self, session):
                        self.id = f'examen_{session.id}'
                        self.session_id = session.id
                        self.titre = f"Examen {session.nom_examen}"
                        self.bareme = 20  # Les examens sont toujours sur 20
                        self.date_evaluation = session.date_debut
                        self.est_examen = True
                        self.type_evaluation = 'examen'
                    
                    def get_type_evaluation_display(self):
                        return "Examen"
                
                evaluations_list.append(PseudoExamen(session))
            
            # Récupérer la moyenne enregistrée
            moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                matiere=matiere,
                periode_scolaire=periode_selectionnee
            ).first()
            
            moyenne = moyenne_obj.moyenne if moyenne_obj else None
            
            notes_par_matiere.append({
                'matiere': matiere,
                'evaluations': evaluations_list,
                'notes': notes_dict,
                'moyenne': moyenne,
                'appreciation': get_appreciation_moyenne(moyenne)
            })
        
        # Calculer la moyenne générale
        moyenne_generale_data = calculer_moyenne_generale(eleve, periode_selectionnee)
    else:
        notes_par_matiere = []
        moyenne_generale_data = None
    
    # Récupérer toutes les présences pour les statistiques
    from datetime import date, timedelta
    from ..model.presence_model import ListePresence
    from collections import defaultdict
    import calendar
    
    # Récupérer toutes les présences de l'année scolaire en cours
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
    
    # Calculer les statistiques globales (par DATE unique, pas par appel)
    total_jours = presences_query.values('date').distinct().count()
    nombre_absences = presences_query.filter(statut__in=['absent', 'absent_justifie']).count()
    nombre_retards = presences_query.filter(statut='retard').count()
    nombre_presents = presences_query.filter(statut='present').count()
    total_presences = presences_query.count()
    taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
    
    # Données pour l'onglet présences
    if onglet == 'presences':
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
        
        presences_list = presences_query.filter(
            date__gte=premier_jour,
            date__lte=dernier_jour
        ).order_by('-date', 'numero_appel')
        
        # Regrouper les présences par date
        presences_par_date = defaultdict(list)
        for presence in presences_list:
            presences_par_date[presence.date].append(presence)
        
        # Convertir en liste triée par date décroissante
        presences = []
        for date_presence in sorted(presences_par_date.keys(), reverse=True):
            presences.append({
                'date': date_presence,
                'appels': presences_par_date[date_presence]
            })
        
        # Statistiques du mois - compter les APPELS, pas les jours
        # Car un élève peut avoir des statuts différents selon les appels du même jour
        nombre_presents_mois = presences_list.filter(statut='present').count()
        nombre_absences_mois = presences_list.filter(statut__in=['absent', 'absent_justifie']).count()
        nombre_retards_mois = presences_list.filter(statut='retard').count()
        total_presences_mois = presences_list.count()
        taux_presence_mois = round((nombre_presents_mois / total_presences_mois * 100), 2) if total_presences_mois > 0 else 0
    else:
        presences = []
        mois_disponibles = []
        mois_selectionne = None
        total_presences_mois = 0
        nombre_absences_mois = 0
        nombre_retards_mois = 0
        nombre_presents_mois = 0
        taux_presence_mois = 0
    
    # Données pour l'onglet sanctions
    if onglet == 'sanctions':
        sanctions = Sanction.objects.filter(
            eleve=eleve
        ).order_by('-date_sanction')[:20]
    else:
        sanctions = []
    
    context = {
        'professeur': professeur,
        'eleve': eleve,
        'classe': eleve.classe,
        'affectation': affectation,
        'onglet_actif': onglet,
        'onglet': onglet,
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'notes_par_matiere': notes_par_matiere,
        'moyenne_generale_data': moyenne_generale_data,
        'presences': presences,
        'sanctions': sanctions,
        'nombre_notes': sum(len(data['notes']) for data in notes_par_matiere),
        'nombre_absences': nombre_absences,
        'nombre_retards': nombre_retards,
        'nombre_presents': nombre_presents,
        'total_presences': total_presences,
        'taux_presence': taux_presence,
        # Données pour les onglets de mois
        'mois_disponibles': mois_disponibles if onglet == 'presences' else [],
        'mois_selectionne': mois_selectionne if onglet == 'presences' else None,
        'total_presences_mois': total_presences_mois if onglet == 'presences' else 0,
        'nombre_absences_mois': nombre_absences_mois if onglet == 'presences' else 0,
        'nombre_retards_mois': nombre_retards_mois if onglet == 'presences' else 0,
        'nombre_presents_mois': nombre_presents_mois if onglet == 'presences' else 0,
        'taux_presence_mois': taux_presence_mois if onglet == 'presences' else 0,
    }
    
    return render(request, 'school_admin/enseignant/primaire/detail_eleve_primaire.html', context)


def detail_classe_primaire(request, classe_id):
    """
    Page de détails complets d'une classe pour un enseignant primaire
    Affiche toutes les informations : élèves, statistiques, évaluations, etc.
    """
    logger.info(f"Détails classe primaire - User: {request.user}, Classe ID: {classe_id}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Récupérer l'onglet actif (pour restauration après filtrage)
    onglet_actif = request.GET.get('onglet', 'eleves')
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier que le professeur est affecté à cette classe
    affectation = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_classes')
    
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
    
    # Récupérer tous les mois distincts avec présence pour déterminer les mois disponibles
    presences_dates = Presence.objects.filter(
        classe=classe
    ).dates('date', 'month', order='DESC')
    
    # Filtre par mois (GET parameter)
    mois_filtre = request.GET.get('mois', None)
    annee_filtre = request.GET.get('annee', None)
    
    # Si aucun mois n'est spécifié, utiliser le premier mois disponible (le plus récent)
    if mois_filtre is None or annee_filtre is None:
        if presences_dates.exists():
            premier_mois = presences_dates.first()
            mois_filtre = premier_mois.month
            annee_filtre = premier_mois.year
        else:
            # Si aucune présence n'existe, utiliser le mois actuel
            mois_filtre = today.month
            annee_filtre = today.year
    else:
        try:
            mois_filtre = int(mois_filtre)
            annee_filtre = int(annee_filtre)
        except (ValueError, TypeError):
            if presences_dates.exists():
                premier_mois = presences_dates.first()
                mois_filtre = premier_mois.month
                annee_filtre = premier_mois.year
            else:
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
    listes_presence_query = ListePresence.objects.filter(
        classe=classe,
        validee=True,
        date__gte=premier_jour_mois,
        date__lte=dernier_jour_mois
    ).order_by('-date', 'numero_appel')
    
    # Regrouper les listes de présence par date
    from collections import defaultdict
    listes_par_date = defaultdict(list)
    for liste in listes_presence_query:
        listes_par_date[liste.date].append(liste)
    
    # Convertir en liste triée par date décroissante
    listes_presence_validees = []
    for date_liste in sorted(listes_par_date.keys(), reverse=True):
        listes_presence_validees.append({
            'date': date_liste,
            'listes': listes_par_date[date_liste]
        })
    
    # Générer la liste des mois qui ont des présences enregistrées
    mois_disponibles = []
    for date_presence in presences_dates:
        mois_disponibles.append({
            'mois': date_presence.month,
            'annee': date_presence.year,
            'nom': date_presence.strftime('%B %Y'),
            'nom_court': date_presence.strftime('%b %Y')
        })
    
    # === STATISTIQUES DES ÉVALUATIONS ===
    # Récupérer toutes les matières enseignées dans cette classe
    matieres_enseignees = list(affectation.matieres.all().order_by('nom'))
    
    # Filtre par matière (GET parameter)
    matiere_eval_id = request.GET.get('matiere_eval', '')
    matiere_eval_active = None
    
    if matiere_eval_id == 'toutes':
        matiere_eval_active = None
    elif matiere_eval_id:
        try:
            matiere_eval_active = next((m for m in matieres_enseignees if str(m.id) == matiere_eval_id), None)
        except:
            pass
    else:
        # Par défaut, sélectionner la première matière
        matiere_eval_active = matieres_enseignees[0] if matieres_enseignees else None
    
    # Filtre par période (GET parameter)
    periode_eval_id = request.GET.get('periode_eval', '')
    
    # Périodes disponibles
    periodes_scolaires = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
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
    
    evaluations = EvaluationPrimaire.objects.filter(
        classe=classe,
        professeur=professeur,
        actif=True
    )
    
    # Filtrer par matière si spécifiée
    if matiere_eval_active:
        evaluations = evaluations.filter(matiere=matiere_eval_active)
    
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
        nombre_absences = Presence.objects.filter(
            eleve=eleve,
            statut='absent'
        ).count()
        
        # Retards
        nombre_retards = Presence.objects.filter(
            eleve=eleve,
            statut='retard'
        ).count()
        
        # Sanctions
        from ..model.sanction_model import Sanction
        nombre_sanctions = Sanction.objects.filter(
            eleve=eleve
        ).count()
        
        # Notes
        nombre_notes = NotePrimaire.objects.filter(
            eleve=eleve,
            evaluation_primaire__professeur=professeur
        ).count()
        
        eleves_avec_stats.append({
            'eleve': eleve,
            'nombre_absences': nombre_absences,
            'nombre_retards': nombre_retards,
            'nombre_sanctions': nombre_sanctions,
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
        'periodes_scolaires_eval': periodes_scolaires,
        'periode_eval_active': periode_eval_active,
        'matieres_enseignees': matieres_enseignees,
        'matiere_eval_active': matiere_eval_active,
    }
    
    return render(request, 'school_admin/enseignant/primaire/detail_classe_primaire.html', context)


def parametres_profil_primaire(request):
    """
    Page des paramètres du profil de l'enseignant primaire
    """
    logger.info(f"Paramètres profil primaire - User: {request.user}")
    
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
            logger.info(f"Infos mises à jour - Professeur primaire: {professeur.nom_complet}")
            
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
                logger.info(f"Mot de passe changé - Professeur primaire: {professeur.nom_complet}")
        
        return redirect('enseignant_primaire:parametres_profil')
    
    # Statistiques pour enseignant primaire
    nombre_classes = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).count()
    
    # Récupérer toutes les affectations primaires pour avoir les matières
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).prefetch_related('matieres')
    
    # Récupérer toutes les matières enseignées
    matieres_enseignees = set()
    for affectation in affectations:
        matieres_enseignees.update(affectation.matieres.all())
    
    nombre_evaluations = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).count()
    
    nombre_notes = NotePrimaire.objects.filter(
        evaluation_primaire__professeur=professeur
    ).count()
    
    nombre_sanctions = Sanction.objects.filter(
        professeur=professeur
    ).count()
    
    # Dernières activités (évaluations primaires)
    dernieres_evaluations = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).order_by('-date_creation')[:5]
    
    context = {
        'professeur': professeur,
        'nombre_classes': nombre_classes,
        'nombre_matieres': len(matieres_enseignees),
        'matieres_enseignees': list(matieres_enseignees),
        'nombre_evaluations': nombre_evaluations,
        'nombre_notes': nombre_notes,
        'nombre_sanctions': nombre_sanctions,
        'dernieres_evaluations': dernieres_evaluations,
    }
    
    return render(request, 'school_admin/enseignant/primaire/parametres_profil_primaire.html', context)


def emploi_du_temps_primaire(request):
    """
    Emploi du temps (réutilise la logique standard).
    """
    from ..personal_views.enseignant_view import emploi_du_temps_enseignant
    return emploi_du_temps_enseignant(request)


def gestion_presence_primaire(request):
    """
    Page de transition pour la gestion de présence pour l'enseignant primaire
    Même structure que gestion_notes_primaire mais pour la présence
    """
    logger.info(f"Gestion présence primaire - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from django.utils import timezone
    from datetime import timedelta
    import re
    
    # Récupérer toutes les affectations actives du professeur primaire
    affectations = AffectationProfesseurPrimaire.objects.filter(
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
        match = re.match(r'^(.+?)\s+-\s+([A-Z0-9]+)', nom)
        
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
        
        # Calculer les statistiques de présence pour chaque élève
        # IMPORTANT : Filtrer par le professeur pour afficher uniquement ses appels
        eleves_avec_presence = []
        for eleve in eleves:
            # Récupérer toutes les présences de l'élève enregistrées par CE professeur depuis le début de l'année
            presences = Presence.objects.filter(
                eleve=eleve,
                professeur=professeur,
                date__gte=debut_annee
            )
            
            # Compter les présences par statut
            nombre_presences = presences.filter(statut='present').count()
            nombre_absences = presences.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
            nombre_retards = presences.filter(statut='retard').count()
            # Compter le nombre de DATES uniques (plusieurs appels le même jour = 1 jour)
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
            'eleves': eleves_avec_presence,
            'nombre_eleves': eleves.count(),
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
    
    return render(request, 'school_admin/enseignant/primaire/gestion_presence_primaire.html', context)


def eleves_en_difficulte_primaire(request):
    """
    Page pour afficher les élèves en difficulté (moyenne < 9) pour l'enseignant primaire
    Même structure que gestion_notes_primaire mais filtré sur les élèves avec moyenne < 9
    """
    logger.info(f"Élèves en difficulté primaire - User: {request.user}, Type: {type(request.user).__name__}")
    
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    import re
    
    # Récupérer les paramètres de navigation
    periode_id = request.GET.get('periode')
    
    # Récupérer toutes les périodes
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Période active par défaut
    if periode_id:
        periode_selectionnee = get_object_or_404(PeriodeScolaire, id=periode_id)
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Récupérer les affectations et grouper les classes par type
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    ).select_related('classe').prefetch_related('matieres')
    
    # Grouper les classes par catégorie (CI, CP, CE1, CE2, CM1, CM2)
    classes_grouped = {}
    total_eleves_difficulte = 0
    
    for affectation in affectations:
        classe = affectation.classe
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+-\s+([A-Z0-9]+)', nom)
        
        if match:
            categorie = match.group(1)
        else:
            categorie = nom.split('-')[0].strip() if '-' in nom else nom
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0,
            }
        
        # Récupérer toutes les matières de cette affectation
        matieres = affectation.matieres.all()
        
        # Récupérer les élèves actifs de la classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        # Pour chaque élève, récupérer ses moyennes dans toutes les matières
        eleves_difficulte = []
        
        for eleve in eleves:
            # Récupérer toutes les moyennes de cet élève pour la période
            moyennes = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                periode_scolaire=periode_selectionnee
            )
            
            # Calculer la moyenne générale
            if moyennes.exists():
                moyenne_generale = moyennes.aggregate(Avg('moyenne'))['moyenne__avg']
                
                # Ne garder que les élèves avec moyenne < 9
                if moyenne_generale and moyenne_generale < 9:
                    # Récupérer le détail des moyennes par matière
                    moyennes_matieres = {}
                    for moy in moyennes:
                        moyennes_matieres[moy.matiere.id] = {
                            'moyenne': moy.moyenne,
                            'matiere': moy.matiere
                        }
                    
                    eleves_difficulte.append({
                        'eleve': eleve,
                        'moyenne_generale': round(moyenne_generale, 2),
                        'moyennes_matieres': moyennes_matieres,
                    })
        
        # N'ajouter la classe que si elle a des élèves en difficulté
        if eleves_difficulte:
            classe_data = {
                'classe': classe,
                'affectation': affectation,
                'matieres': list(matieres),
                'eleves': eleves_difficulte,
                'nombre_eleves': len(eleves_difficulte),
                'nombre_total_eleves': eleves.count(),
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
        'periode_selectionnee': periode_selectionnee,
        'periodes': periodes,
    }
    
    return render(request, 'school_admin/enseignant/primaire/eleves_en_difficulte_primaire.html', context)


@login_required
def imprimer_tableau_presence(request, classe_id):
    """
    Génère un tableau de présence hebdomadaire imprimable pour une classe spécifique.
    Format : Semaine du lundi au vendredi avec colonnes Matin/Après-midi
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier que le professeur est affecté à cette classe
    affectation = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    ).first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_presence')
    
    # Déterminer la semaine à afficher (semaine en cours par défaut)
    today = date.today()
    
    # Calculer le lundi de la semaine en cours
    lundi = today - timedelta(days=today.weekday())
    samedi = lundi + timedelta(days=5)
    
    classes_data = []
    
    # Traiter uniquement la classe sélectionnée
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer les présences de la semaine pour tous les élèves
    # IMPORTANT : Filtrer par professeur pour afficher uniquement ses appels
    presences_semaine = Presence.objects.filter(
        classe=classe,
        professeur=professeur,
        date__gte=lundi,
        date__lte=samedi
    ).select_related('eleve')
    
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
    
    classes_data.append({
        'classe': classe,
        'eleves': eleves_data
    })
    
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
    
    return render(request, 'school_admin/enseignant/primaire/imprimer_tableau_presence.html', context)


def annonces_enseignant_primaire(request):
    """
    Affiche les annonces destinées aux enseignants du primaire.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    # Vérifier que le professeur est bien de niveau primaire
    if professeur.niveau_enseignement != 'primaire':
        messages.warning(request, "Vous n'êtes pas un enseignant du primaire.")
        return redirect('enseignant:dashboard_enseignant')
    
    from ..model.annonce_model import Annonce
    from django.db.models import Q
    from datetime import timedelta
    
    # Récupérer les annonces publiées destinées aux enseignants ou à tous
    annonces = Annonce.objects.filter(
        Q(etablissement=professeur.etablissement) &
        Q(statut='publiee') &
        Q(actif=True) &
        (Q(destinataires__contains=['tous']) | 
         Q(destinataires__contains=['enseignants']))
    ).order_by('-date_publication', '-date_creation')
    
    # Filtrer par date si demandé
    filtre_periode = request.GET.get('periode', '')
    today = date.today()
    
    if filtre_periode:
        if filtre_periode == 'semaine':
            date_debut = today - timedelta(days=7)
            annonces = annonces.filter(date_publication__gte=date_debut)
        elif filtre_periode == 'mois':
            date_debut = today - timedelta(days=30)
            annonces = annonces.filter(date_publication__gte=date_debut)
        elif filtre_periode == 'trimestre':
            date_debut = today - timedelta(days=90)
            annonces = annonces.filter(date_publication__gte=date_debut)
    
    # Statistiques
    total_annonces = annonces.count()
    date_semaine = today - timedelta(days=7)
    annonces_cette_semaine = annonces.filter(
        date_publication__gte=date_semaine
    ).count() if annonces.exists() else 0
    
    context = {
        'professeur': professeur,
        'annonces': annonces,
        'total_annonces': total_annonces,
        'annonces_cette_semaine': annonces_cette_semaine,
        'filtre_periode': filtre_periode,
    }
    
    return render(request, 'school_admin/enseignant/primaire/annonces_enseignant.html', context)

