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
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.dateparse import parse_date
from datetime import datetime, date
from urllib.parse import urlencode
from django.db.utils import ProgrammingError, OperationalError
from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from ..model.exercice_maison_model import ExerciceMaison
from ..model.justification_note_model import JustificationNote
from ..model.eleve_model import Eleve
from ..model.inscription_eleve_model import InscriptionEleve
from django.db.models.functions import Lower

logger = logging.getLogger(__name__)


def _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active=None):
    """
    Récupère les élèves d'une classe depuis InscriptionEleve pour l'année scolaire active.
    Retourne un queryset d'élèves actifs inscrits dans cette classe pour l'année active.
    
    Args:
        classe: L'objet Classe
        etablissement: L'établissement
        annee_scolaire_active: L'année scolaire active (optionnel)
    
    Returns:
        QuerySet d'élèves
    """
    if annee_scolaire_active:
        # Récupérer directement les inscriptions pour cette classe et cette année scolaire
        inscriptions = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire_active,
            classe=classe,
            etablissement=etablissement
        ).select_related('eleve').order_by(Lower('eleve__nom'), Lower('eleve__prenom'))
        
        # Récupérer les élèves depuis les inscriptions (filtrer uniquement les actifs)
        eleves_ids = [inscription.eleve_id for inscription in inscriptions if inscription.eleve and inscription.eleve.actif]
        
        # Créer un queryset à partir de la liste pour maintenir la compatibilité
        return Eleve.objects.filter(id__in=eleves_ids, actif=True).order_by(Lower('nom'), Lower('prenom'))
    else:
        # Comportement par défaut : tous les élèves actifs de la classe
        return Eleve.objects.filter(classe=classe, actif=True).order_by(Lower('nom'), Lower('prenom'))


def _get_classe_eleve_active(eleve, annee_scolaire_active, etablissement=None):
    """
    Récupère la classe de l'élève pour l'année scolaire active depuis InscriptionEleve.
    Retourne None si l'élève n'est pas inscrit pour cette année.
    
    Args:
        eleve: L'objet Eleve
        annee_scolaire_active: L'objet AnneeScolaire active
        etablissement: L'établissement (optionnel, utilise eleve.etablissement si non fourni)
    
    Returns:
        Classe ou None
    """
    if not annee_scolaire_active:
        # Fallback sur eleve.classe si pas d'année scolaire active
        return eleve.classe
    
    if not etablissement:
        etablissement = eleve.etablissement
    
    if not etablissement:
        return eleve.classe
    
    try:
        inscription = InscriptionEleve.objects.filter(
            eleve=eleve,
            annee_scolaire=annee_scolaire_active,
            etablissement=etablissement
        ).select_related('classe').first()
        
        if inscription and inscription.classe:
            return inscription.classe
    except Exception:
        pass
    
    # Fallback sur eleve.classe si aucune inscription trouvée
    return eleve.classe

# Constante pour les types d'établissements secondaires (lycée, collège, etc.)
TYPES_ETABLISSEMENT_SECONDAIRE = [
    'lycée', 'collège', 'collège_lycée', 'lycee_college', 
    'mixte', 'lycee', 'college'
]

MOTIFS_JUSTIFICATION_SECONDAIRE = OrderedDict([
    ("note_mal_enregistree", "Note mal enregistrée"),
    ("erreur_de_saisie", "Erreur de saisie"),
    ("copie_devoir_apportee", "Copie de devoir apportée après saisie"),
    ("maladie_absence", "Absence justifiée pour raison médicale"),
    ("force_majeure", "Cas de force majeure (pluie, catastrophe, grève)"),
    ("probleme_technique", "Problème technique ou défaillance matérielle"),
    ("retard_correction", "Correction ou transmission tardive"),
    ("situation_familiale", "Situation familiale (décès, événement familial, etc.)"),
    ("difficulte_transport", "Difficultés de transport (accident, panne, etc.)"),
    ("evenement_religieux", "Événement religieux ou culturel"),
    ("probleme_sante", "Problème de santé (sans certificat médical)"),
    ("raison_personnelle", "Raison personnelle justifiée"),
    ("autre", "Autre motif (voir détails)")
])



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
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # ===== INDICATEURS CLÉS =====
    
    # 1. Classes assignées (filtrées par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('classe', 'matiere').prefetch_related('classe__eleves')
    
    total_classes = affectations.count()
    
    # 2. Élèves encadrés (filtrés par année scolaire active)
    from ..model.inscription_eleve_model import InscriptionEleve
    total_eleves = 0
    if annee_scolaire_active:
        for affectation in affectations:
            # Compter les élèves inscrits pour l'année scolaire active dans cette classe
            eleves_inscrits = InscriptionEleve.objects.filter(
                annee_scolaire=annee_scolaire_active,
                classe=affectation.classe,
                etablissement=etablissement
            ).count()
            total_eleves += eleves_inscrits
    else:
        # Comportement par défaut : utiliser nombre_eleves de la classe
        for affectation in affectations:
            total_eleves += affectation.classe.nombre_eleves
    
    # 3. Évaluations planifiées (dans les 7 prochains jours) - filtrées par année scolaire active
    date_debut = datetime.now().date()
    date_fin = date_debut + timedelta(days=7)
    
    evaluations_a_venir_queryset = Evaluation.objects.filter(
        professeur=professeur,
        date_evaluation__gte=date_debut,
        date_evaluation__lte=date_fin,
        actif=True
    )
    if annee_scolaire_active:
        evaluations_a_venir_queryset = evaluations_a_venir_queryset.filter(annee_scolaire=annee_scolaire_active)
    evaluations_a_venir = evaluations_a_venir_queryset.count()
    
    # 4. Messages non lus (pour l'instant 0, à implémenter plus tard)
    messages_non_lus = 0
    
    # ===== LISTE DES CLASSES AVEC DÉTAILS =====
    classes_data = []
    for affectation in affectations[:3]:  # Limiter à 3 pour le dashboard
        classe = affectation.classe
        
        # Calculer les heures par semaine (filtrées par année scolaire active)
        creneaux_classe_queryset = CreneauEmploiDuTemps.objects.filter(
            emploi_du_temps__classe=classe,
            emploi_du_temps__est_actif=True,
            emploi_du_temps__statut_publication='publie',
            professeur=professeur
        )
        if annee_scolaire_active:
            creneaux_classe_queryset = creneaux_classe_queryset.filter(
                emploi_du_temps__annee_scolaire_fk=annee_scolaire_active
            )
        creneaux_classe = creneaux_classe_queryset.select_related('periode_etablissement')
        
        heures_semaine = 0
        for creneau in creneaux_classe:
            heures_semaine += creneau.duree_minutes / 60
        
        # Progression fictive basée sur la date (pour avoir quelque chose de dynamique)
        mois_ecoule = datetime.now().month - 9  # Septembre = mois 1
        if mois_ecoule < 0:
            mois_ecoule += 12
        progression = min(int(mois_ecoule / 9 * 100), 100)  # 9 mois d'école
        
        # Calculer le nombre d'élèves filtré par année scolaire active
        if annee_scolaire_active:
            nombre_eleves_classe = InscriptionEleve.objects.filter(
                annee_scolaire=annee_scolaire_active,
                classe=classe,
                etablissement=etablissement
            ).count()
        else:
            nombre_eleves_classe = classe.nombre_eleves
        
        classes_data.append({
            'classe': classe,
            'matiere': affectation.matiere if affectation.matiere else professeur.matiere_principale,
            'nombre_eleves': nombre_eleves_classe,
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
    emplois_actifs_queryset = EmploiDuTemps.objects.filter(classe__in=classes_professeur, est_actif=True)
    if annee_scolaire_active:
        emplois_actifs_queryset = emplois_actifs_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    emplois_actifs = emplois_actifs_queryset
    emplois_publies = emplois_actifs.filter(statut_publication='publie')
    emploi_publie_disponible = emplois_publies.exists()
    
    if emploi_publie_disponible:
        creneaux_aujourdhui_queryset = CreneauEmploiDuTemps.objects.filter(
            professeur=professeur,
            jour=jour_actuel,
            emploi_du_temps__in=emplois_publies
        )
        if annee_scolaire_active:
            creneaux_aujourdhui_queryset = creneaux_aujourdhui_queryset.filter(
                emploi_du_temps__annee_scolaire_fk=annee_scolaire_active
            )
        creneaux_aujourdhui = creneaux_aujourdhui_queryset.select_related('emploi_du_temps__classe', 'matiere', 'salle', 'periode_etablissement').order_by('periode_etablissement__ordre', 'heure_debut')
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
    # Récupérer les évaluations avec des notes manquantes (filtrées par année scolaire active)
    evaluations_avec_notes_queryset = Evaluation.objects.filter(
        professeur=professeur,
        date_evaluation__lte=date_debut,
        actif=True
    )
    if annee_scolaire_active:
        evaluations_avec_notes_queryset = evaluations_avec_notes_queryset.filter(annee_scolaire=annee_scolaire_active)
    evaluations_avec_notes = evaluations_avec_notes_queryset.annotate(
        nombre_notes=Count('notes')
    ).select_related('classe')
    
    devoirs_a_corriger = []
    for evaluation in evaluations_avec_notes[:3]:  # Limiter à 3
        classe = evaluation.classe
        # Calculer le nombre d'élèves filtré par année scolaire active
        if annee_scolaire_active:
            nombre_eleves = InscriptionEleve.objects.filter(
                annee_scolaire=annee_scolaire_active,
                classe=classe,
                etablissement=etablissement
            ).count()
        else:
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
    # Filtrées par année scolaire active
    prochaines_evaluations_queryset = Evaluation.objects.filter(
        professeur=professeur,
        date_evaluation__gt=date_debut,
        actif=True
    )
    if annee_scolaire_active:
        prochaines_evaluations_queryset = prochaines_evaluations_queryset.filter(annee_scolaire=annee_scolaire_active)
    prochaines_evaluations = prochaines_evaluations_queryset.select_related('classe').order_by('date_evaluation')[:3]
    
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
    
    # Notifications non lues (filtrées par année scolaire active)
    notifications_queryset = NotificationEnseignant.objects.filter(
        enseignant=professeur, statut='non_lu'
    )
    if annee_scolaire_active:
        notifications_queryset = notifications_queryset.filter(annee_scolaire=annee_scolaire_active)
    notifications_non_lues = notifications_queryset.count()
    
    context = {
        'professeur': professeur,
        'annee_scolaire_active': annee_scolaire_active,
        
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
    
    # Récupérer l'année scolaire active
    from ..utils.session_utils import get_session_active
    from ..model.inscription_eleve_model import InscriptionEleve
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer toutes les affectations actives du professeur (filtrées par année scolaire active)
    from ..model.affectation_model import AffectationProfesseur
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('classe', 'classe__etablissement').prefetch_related('classe__eleves').order_by('classe__nom')
    
    # Créer une liste de données pour chaque classe
    classes_data = []
    for affectation in affectations:
        classe = affectation.classe
        # Calculer le nombre d'élèves filtré par année scolaire active
        if annee_scolaire_active:
            nombre_eleves = InscriptionEleve.objects.filter(
                annee_scolaire=annee_scolaire_active,
                classe=classe,
                etablissement=etablissement
            ).count()
        else:
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
        'annee_scolaire_active': annee_scolaire_active,
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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer toutes les affectations actives du professeur (filtrées par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('classe').prefetch_related('classe__eleves').order_by('classe__nom')
    
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
        
        # Récupérer les élèves actifs de cette classe via InscriptionEleve
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        # Ajouter le nombre d'absences et sanctions pour chaque élève
        # IMPORTANT : Filtrer par matière et par professeur selon le rôle
        from ..model.presence_model import Presence
        from ..model.sanction_model import Sanction
        from django.db.models import Q
        
        # Pour les établissements secondaires, utiliser la matière de l'affectation
        # Pour le primaire, utiliser la matière principale du professeur ou None
        est_secondaire_classe = classe.etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
        matiere_affectation = affectation.matiere if affectation.matiere else (professeur.matiere_principale if not est_secondaire_classe else None)
        
        eleves_avec_absences = []
        for eleve in eleves:
            # Filtrer les absences selon le rôle et la matière (filtrées par année scolaire active)
            if affectation.is_principal:
                # Professeur principal : voir TOUTES les absences de la classe
                absences_queryset = Presence.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    statut='absent'
                )
                if annee_scolaire_active:
                    absences_queryset = absences_queryset.filter(annee_scolaire=annee_scolaire_active)
                nombre_absences = absences_queryset.count()
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
                    # Pour le primaire, les présences n'ont pas de matière
                    filters_abs['matiere__isnull'] = True
                
                absences_queryset = Presence.objects.filter(**filters_abs)
                if annee_scolaire_active:
                    absences_queryset = absences_queryset.filter(annee_scolaire=annee_scolaire_active)
                nombre_absences = absences_queryset.count()
            
            # Filtrer les sanctions par année scolaire active
            sanctions_queryset = Sanction.objects.filter(eleve=eleve)
            if annee_scolaire_active:
                sanctions_queryset = sanctions_queryset.filter(annee_scolaire=annee_scolaire_active)
            nombre_sanctions = sanctions_queryset.count()
            
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
        'annee_scolaire_active': annee_scolaire_active,
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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        return redirect('enseignant_primaire:gestion_notes')
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer toutes les périodes scolaires de l'établissement (filtrées par année scolaire active)
    periodes_scolaires_queryset = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_scolaires_queryset = periodes_scolaires_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes_scolaires = periodes_scolaires_queryset.order_by('date_debut')
    
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
    
    # Récupérer toutes les affectations actives du professeur (filtrées par année scolaire)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = (
        affectations_queryset
        .select_related('classe', 'classe__etablissement')
        .prefetch_related('classe__eleves')
        .order_by('classe__nom')
    )
    
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
        
        # Récupérer les élèves actifs de cette classe via InscriptionEleve
        eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
        
        # Déterminer la matière enseignée pour cette affectation
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
        
        # Récupérer les évaluations pour cette classe, matière et période
        evaluations_liste = []
        if periode_active_obj and matiere_enseignee:
            # Récupérer toutes les évaluations
            toutes_evaluations = Evaluation.objects.filter(
                classe=classe,
                professeur=professeur,
                periode_scolaire=periode_active_obj,
                actif=True,
                matiere=matiere_enseignee
            ).order_by('date_evaluation')
            if annee_scolaire_active:
                toutes_evaluations = toutes_evaluations.filter(annee_scolaire=annee_scolaire_active)
            
            # Classer par barème : <= 10 = interrogation, > 10 = devoir
            for i, eval_obj in enumerate(toutes_evaluations, 1):
                if eval_obj.bareme <= 10:
                    evaluations_liste.append({
                        'key': f'interro_{i}',
                        'evaluation': eval_obj,
                        'type': 'interrogation',
                        'index': i,
                    })
                else:
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
            if annee_scolaire_active:
                notes = notes.filter(annee_scolaire=annee_scolaire_active)
            
            for note in notes:
                eval_id = note.evaluation.id
                eleve_id = note.eleve.id
                if eleve_id not in notes_par_eleve_et_eval:
                    notes_par_eleve_et_eval[eleve_id] = {}
                notes_par_eleve_et_eval[eleve_id][eval_id] = note
        
        # Récupérer les moyennes pour cette classe et cette période (filtrées par année scolaire active)
        # Note: Le système de moyennes utilise encore l'ancien format
        # On peut filtrer par date à la place si période_active_obj existe
        if periode_active_obj:
            moyennes_queryset = Moyenne.objects.filter(
                classe=classe,
                professeur=professeur,
                matiere=matiere_enseignee,
                actif=True
            )
            if annee_scolaire_active:
                moyennes_queryset = moyennes_queryset.filter(annee_scolaire=annee_scolaire_active)
            moyennes = moyennes_queryset.select_related('eleve')
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
            # Récupérer la note d'examen si une session est disponible (filtrée par année scolaire active)
            note_examen_dict = None
            if session_examen_classe:
                from ..model.note_examen_model import NoteExamen
                note_exam_queryset = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session_examen_classe,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                )
                if annee_scolaire_active:
                    note_exam_queryset = note_exam_queryset.filter(annee_scolaire=annee_scolaire_active)
                note_exam_obj = note_exam_queryset.first()
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
            sessions_queryset = SessionExamen.objects.filter(
                etablissement=professeur.etablissement,
                classes=classe,
                matieres=professeur.matiere_principale,
                periode=periode_active_obj,
                actif=True
            )
            if annee_scolaire_active:
                sessions_queryset = sessions_queryset.filter(annee_scolaire=annee_scolaire_active)
            sessions = sessions_queryset.distinct()
            
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
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/gestion_notes.html', context)
def justifications_notes_enseignant(request):
    """
    Page permettant aux enseignants (collège/lycée) de soumettre des justifications de notes.
    """
    logger.info("Justifications de notes - User: %s", request.user)

    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    professeur = request.user

    # Rediriger les enseignants du primaire vers leur espace dédié
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        messages.error(request, "La justification de notes est gérée dans l'espace primaire.")
        return redirect('enseignant_primaire:gestion_notes')

    if not professeur.etablissement:
        messages.error(request, "Votre profil n'est pas rattaché à un établissement.")
        return redirect('enseignant:gestion_notes')

    # Récupérer l'année scolaire active
    from ..utils.session_utils import get_session_active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)

    from ..model.affectation_model import AffectationProfesseur
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Evaluation, Note
    from django.db import transaction
    from decimal import Decimal, InvalidOperation
    from django.urls import reverse
    import json
    import re

    # Fonction helper pour les redirections avec paramètre periode
    def _redirect_with_periode():
        redirect_url = reverse('enseignant:justifications_notes')
        periode_id_param = request.POST.get('periode') or request.GET.get('periode')
        if periode_id_param:
            redirect_url = f"{redirect_url}?periode={periode_id_param}"
        return redirect(redirect_url)

    # Traitement de la soumission du formulaire
    if request.method == 'POST':
        note_id = request.POST.get('note_id')
        note_type = request.POST.get('note_type', 'evaluation')  # 'evaluation' ou 'examen'
        nouvelle_note_raw = request.POST.get('nouvelle_note')
        motif_code = request.POST.get('motif')
        description = (request.POST.get('description') or '').strip()

        if not note_id:
            messages.error(request, "Veuillez sélectionner la note à justifier.")
            return _redirect_with_periode()

        note = None
        note_examen = None
        
        if note_type == 'examen':
            from ..model.note_examen_model import NoteExamen
            try:
                note_examen = NoteExamen.objects.select_related(
                    'session_examen',
                    'creneau_examen',
                    'matiere',
                    'classe',
                    'eleve',
                ).get(id=note_id, professeur=professeur)
            except NoteExamen.DoesNotExist:
                messages.error(request, "Impossible de trouver la note d'examen sélectionnée.")
                return _redirect_with_periode()
        else:
            try:
                note = Note.objects.select_related(
                    'evaluation',
                    'evaluation__classe',
                    'evaluation__matiere',
                    'eleve',
                ).get(id=note_id, evaluation__professeur=professeur)
            except Note.DoesNotExist:
                messages.error(request, "Impossible de trouver la note sélectionnée.")
                return _redirect_with_periode()

        if not motif_code or motif_code not in MOTIFS_JUSTIFICATION_SECONDAIRE:
            messages.error(request, "Veuillez sélectionner un motif de justification valide.")
            return _redirect_with_periode()
        motif = MOTIFS_JUSTIFICATION_SECONDAIRE[motif_code]

        try:
            nouvelle_note = Decimal(str(nouvelle_note_raw).replace(',', '.'))
        except (InvalidOperation, TypeError):
            messages.error(request, "La nouvelle note proposée est invalide.")
            return _redirect_with_periode()

        if nouvelle_note < 0:
            messages.error(request, "La note proposée ne peut pas être négative.")
            return _redirect_with_periode()

        bareme = None
        if note:
            bareme = note.evaluation.bareme if note.evaluation else None
        elif note_examen:
            bareme = note_examen.bareme
        
        if bareme is not None and nouvelle_note > bareme:
            messages.error(
                request,
                f"La note proposée ne peut pas dépasser le barème ({bareme})."
            )
            return _redirect_with_periode()

        justification_obj = None

        with transaction.atomic():
            if note:
                justification = JustificationNote.objects.filter(
                    note=note,
                    statut=JustificationNote.STATUT_EN_ATTENTE
                ).first()
                ancienne_note_val = note.note
                classe_obj = note.evaluation.classe
                matiere_obj = note.matiere or note.evaluation.matiere
                eleve_obj = note.eleve
                evaluation_obj = note.evaluation
            else:
                justification = JustificationNote.objects.filter(
                    note_examen=note_examen,
                    statut=JustificationNote.STATUT_EN_ATTENTE
                ).first()
                ancienne_note_val = note_examen.note
                classe_obj = note_examen.classe
                matiere_obj = note_examen.matiere
                eleve_obj = note_examen.eleve
                evaluation_obj = None

            if justification:
                justification.ancienne_note = ancienne_note_val
                justification.nouvelle_note = nouvelle_note
                justification.motif = motif
                justification.description = description
                justification.professeur = professeur
                justification.etablissement = professeur.etablissement
                justification.matiere = matiere_obj
                justification.classe = classe_obj
                justification.eleve = eleve_obj
                if note:
                    justification.note = note
                    justification.evaluation = evaluation_obj
                    justification.note_examen = None
                else:
                    justification.note_examen = note_examen
                    justification.note = None
                    justification.evaluation = None
                justification.annee_scolaire = annee_scolaire_active
                justification.save()
                justification_obj = justification
                messages.success(request, "Votre demande de justification a été mise à jour.")
            else:
                creation_kwargs = {
                    'classe': classe_obj,
                    'eleve': eleve_obj,
                    'matiere': matiere_obj,
                    'professeur': professeur,
                    'etablissement': professeur.etablissement,
                    'ancienne_note': ancienne_note_val,
                    'nouvelle_note': nouvelle_note,
                    'motif': motif,
                    'description': description,
                    'annee_scolaire': annee_scolaire_active,
                }
                if note:
                    creation_kwargs['note'] = note
                    creation_kwargs['evaluation'] = evaluation_obj
                else:
                    creation_kwargs['note_examen'] = note_examen
                
                justification_obj = JustificationNote.objects.create(**creation_kwargs)
                messages.success(request, "Votre demande de justification a été envoyée à la direction.")

        if justification_obj:
            from ..services.notification_tasks import schedule_justification_note_directeur_notification
            schedule_justification_note_directeur_notification(justification_obj.id)

        # Rediriger en gardant le paramètre periode
        return _redirect_with_periode()

    # Récupérer les périodes scolaires
    from ..model.periode_model import PeriodeScolaire
    periodes_queryset = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_queryset.order_by('date_debut')
    
    # Sélectionner la période (GET paramètre ou période active par défaut)
    periode_id = request.GET.get('periode')
    periode_active = None
    if periodes.exists():
        if periode_id:
            try:
                periode_active = periodes.get(id=periode_id)
            except PeriodeScolaire.DoesNotExist:
                pass
        if not periode_active:
            periode_active = periodes.filter(est_active=True).first() or periodes.first()

    # Construction des données d'affichage
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('classe', 'matiere').prefetch_related('classe__eleves').order_by('classe__nom')

    classes_grouped = {}
    total_eleves = 0
    notes_payload = {}

    for affectation in affectations:
        classe = affectation.classe
        nom = classe.nom

        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)

        if match:
            categorie = match.group(1)
        else:
            categorie = nom

        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0,
            }

        eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
        total_eleves += eleves.count()
        classes_grouped[categorie]['total_eleves'] += eleves.count()

        matiere_affectation = affectation.matiere if affectation.matiere else professeur.matiere_principale
        from ..model.evaluation_model import Evaluation

        evaluations_liste = []
        if matiere_affectation:
            # Récupérer toutes les évaluations
            toutes_evaluations_queryset = Evaluation.objects.filter(
                classe=classe,
                professeur=professeur,
                actif=True,
                matiere=matiere_affectation
            )
            if annee_scolaire_active:
                toutes_evaluations_queryset = toutes_evaluations_queryset.filter(annee_scolaire=annee_scolaire_active)
            if periode_active:
                toutes_evaluations_queryset = toutes_evaluations_queryset.filter(periode_scolaire=periode_active)
            toutes_evaluations = toutes_evaluations_queryset.order_by('date_evaluation')

            # Classer par barème : <= 10 = interrogation, > 10 = devoir
            for i, eval_obj in enumerate(toutes_evaluations, 1):
                if eval_obj.bareme <= 10:
                    evaluations_liste.append({
                        'key': f'interro_{i}',
                        'evaluation': eval_obj,
                        'type': 'interrogation',
                        'index': i,
                    })
                else:
                    evaluations_liste.append({
                        'key': f'devoir_{i}',
                        'evaluation': eval_obj,
                        'type': 'devoir',
                        'index': i,
                    })

        evaluation_ids = [item['evaluation'].id for item in evaluations_liste]

        notes_query = Note.objects.filter(
            evaluation__classe=classe,
            evaluation__professeur=professeur,
            evaluation_id__in=evaluation_ids
        )
        if annee_scolaire_active:
            notes_query = notes_query.filter(annee_scolaire=annee_scolaire_active)
        notes_query = notes_query.select_related(
            'evaluation',
            'evaluation__matiere',
            'eleve'
        ).prefetch_related('justifications').order_by('eleve__nom', 'evaluation__date_evaluation')

        # Récupérer les notes d'examen pour cette classe et matière
        from ..model.note_examen_model import NoteExamen
        from ..model.session_examen_model import SessionExamen
        notes_examen_query = NoteExamen.objects.filter(
            classe=classe,
            professeur=professeur,
            actif=True
        )
        if matiere_affectation:
            notes_examen_query = notes_examen_query.filter(matiere=matiere_affectation)
        if annee_scolaire_active:
            notes_examen_query = notes_examen_query.filter(annee_scolaire=annee_scolaire_active)
        if periode_active:
            # Filtrer par période via la session d'examen
            session_ids = SessionExamen.objects.filter(
                periode=periode_active,
                actif=True
            ).values_list('id', flat=True)
            notes_examen_query = notes_examen_query.filter(session_examen_id__in=session_ids)
        notes_examen_query = notes_examen_query.select_related(
            'session_examen',
            'creneau_examen',
            'matiere',
            'eleve'
        ).prefetch_related('justifications').order_by('eleve__nom', 'session_examen__date_debut')

        notes_par_eleve = {}
        for note in notes_query:
            notes_map = notes_par_eleve.setdefault(note.eleve_id, {})
            justifications = sorted(
                list(note.justifications.all()),
                key=lambda j: j.date_creation,
                reverse=True
            )
            derniere_justification = justifications[0] if justifications else None
            notes_map[f"eval_{note.evaluation_id}"] = {
                'note': note,
                'note_examen': None,
                'justification': derniere_justification,
                'type': 'evaluation',
            }
        
        for note_examen in notes_examen_query:
            notes_map = notes_par_eleve.setdefault(note_examen.eleve_id, {})
            justifications = sorted(
                list(note_examen.justifications.all()),
                key=lambda j: j.date_creation,
                reverse=True
            )
            derniere_justification = justifications[0] if justifications else None
            notes_map[f"examen_{note_examen.id}"] = {
                'note': None,
                'note_examen': note_examen,
                'justification': derniere_justification,
                'type': 'examen',
            }

        eleves_data = []
        for eleve in eleves:
            notes_map = notes_par_eleve.get(eleve.id, {})
            derniere_justification_globale = None
            for entry in notes_map.values():
                justification = entry['justification']
                if justification:
                    if (
                        derniere_justification_globale is None
                        or justification.date_creation > derniere_justification_globale.date_creation
                    ):
                        derniere_justification_globale = justification

            if notes_map:
                eleve_payload = notes_payload.setdefault(str(eleve.id), [])
                for entry in notes_map.values():
                    note_obj = entry.get('note')
                    note_examen_obj = entry.get('note_examen')
                    justification = entry['justification']
                    entry_type = entry.get('type', 'evaluation')
                    
                    if entry_type == 'examen' and note_examen_obj:
                        session_examen = note_examen_obj.session_examen
                        creneau = note_examen_obj.creneau_examen
                        session_label = session_examen.nom if session_examen else "Examen"
                        if creneau:
                            session_label += f" - {creneau.nom}"
                        label = f"Examen: {session_label} ({note_examen_obj.note if note_examen_obj.note is not None else 'N/A'}/{note_examen_obj.bareme})"
                        if session_examen and session_examen.date_debut:
                            label += f" - {date_format(session_examen.date_debut, 'd/m/Y')}"
                        matiere_obj = note_examen_obj.matiere
                        eleve_payload.append({
                            'id': note_examen_obj.id,
                            'note_type': 'examen',
                            'evaluation_id': None,
                            'classe_id': str(classe.id),
                            'matiere_id': str(matiere_obj.id) if matiere_obj else "",
                            'label': label,
                            'bareme': str(note_examen_obj.bareme),
                            'valeur': str(note_examen_obj.note) if note_examen_obj.note is not None else "",
                            'statut': justification.statut if justification else "",
                        })
                    elif note_obj:
                        evaluation = note_obj.evaluation
                        label = f"{evaluation.titre} ({note_obj.note}/{evaluation.bareme}) - {date_format(evaluation.date_evaluation, 'd/m/Y')}"
                        matiere_obj = note_obj.matiere or evaluation.matiere
                        eleve_payload.append({
                            'id': note_obj.id,
                            'note_type': 'evaluation',
                            'evaluation_id': evaluation.id,
                            'classe_id': str(classe.id),
                            'matiere_id': str(matiere_obj.id) if matiere_obj else "",
                            'label': label,
                            'bareme': str(evaluation.bareme),
                            'valeur': str(note_obj.note) if note_obj.note is not None else "",
                            'statut': justification.statut if justification else "",
                        })

            eleves_data.append({
                'eleve': eleve,
                'notes': notes_map,
                'derniere_justification': derniere_justification_globale,
            })

        classes_grouped[categorie]['classes'].append({
            'classe': classe,
            'matiere': matiere_affectation,
            'eleves': eleves_data,
            'nombre_eleves': eleves.count(),
            'est_principal': affectation.is_principal,
            'evaluations': evaluations_liste,
        })

    stats = {
        'total_classes': affectations.count(),
        'total_eleves': total_eleves,
    }

    notes_json = json.dumps(notes_payload, ensure_ascii=False)

    context = {
        'professeur': professeur,
        'classes_grouped': classes_grouped,
        'stats': stats,
        'notes_json': notes_json,
        'motifs_justification': MOTIFS_JUSTIFICATION_SECONDAIRE,
        'periodes': periodes,
        'periode_active': periode_active,
        'annee_scolaire_active': annee_scolaire_active,
    }

    return render(request, 'school_admin/enseignant/justifications_notes.html', context)
def exercices_maison_enseignant(request):
    """
    Page de consultation et de programmation des exercices de maison (collège/lycée).
    """
    logger.info("Exercices maison - User: %s", request.user)

    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    professeur = request.user

    from ..model.affectation_model import AffectationProfesseur
    from ..model.periode_model import PeriodeScolaire
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from django.db.models import Count
    import re

    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)

    # Récupérer les périodes scolaires (filtrées par année scolaire active)
    periodes_queryset = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_queryset.order_by('date_debut')

    periode_id = request.GET.get('periode')
    if periode_id:
        try:
            periode_selectionnee = periodes.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            messages.error(request, "Période scolaire invalide.")
            return redirect(request.path)
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()

    # Récupérer les affectations (filtrées par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('classe', 'matiere').order_by('classe__nom', 'matiere__nom')

    if not affectations.exists():
        messages.info(request, "Vous n'êtes affecté à aucune classe.")
        return render(
            request,
            'school_admin/enseignant/exercices_maison.html',
            {
                'professeur': professeur,
                'periodes': periodes,
                'periode_selectionnee': periode_selectionnee,
                'classes_grouped': {},
                'classes_categories': [],
                'classe_selectionnee': None,
                'matieres_disponibles': [],
                'matiere_selectionnee': None,
                'exercices': [],
                'aujourdhui': date.today(),
            }
        )

    # Préparer les classes et matières disponibles
    classes_map = {}
    for affectation in affectations:
        entry = classes_map.setdefault(affectation.classe_id, {
            'classe': affectation.classe,
            'matieres': [],
        })
        if affectation.matiere and all(m.id != affectation.matiere.id for m in entry['matieres']):
            entry['matieres'].append(affectation.matiere)

    classe_ids = list(classes_map.keys())
    try:
        exercices_counts_qs = ExerciceMaison.objects.filter(
            professeur=professeur,
            classe_id__in=classe_ids,
            actif=True
        )
        if annee_scolaire_active:
            exercices_counts_qs = exercices_counts_qs.filter(annee_scolaire=annee_scolaire_active)
        if periode_selectionnee:
            exercices_counts_qs = exercices_counts_qs.filter(periode_scolaire=periode_selectionnee)

        exercices_counts = {
            item['classe_id']: item['total']
            for item in exercices_counts_qs.values('classe_id').annotate(total=Count('id'))
        }
    except (ProgrammingError, OperationalError) as exc:
        exercices_counts = {}
        logger.warning(
            "Table ExerciceMaison indisponible : %s",
            exc,
        )

    classes_grouped = {}
    for classe_id, data in classes_map.items():
        classe = data['classe']
        matieres = sorted(data['matieres'], key=lambda m: m.nom)
        if not matieres and professeur.matiere_principale:
            matieres = [professeur.matiere_principale]
        data['matieres'] = matieres

        match = re.match(r'^(.+?)(?:\s*-\s*[A-Z0-9]+)?$', classe.nom)
        if match:
            categorie = match.group(1).strip()
        else:
            categorie = classe.niveau or classe.nom

        if categorie not in classes_grouped:
            classes_grouped[categorie] = {'classes': []}

        classes_grouped[categorie]['classes'].append({
            'classe': classe,
            'matieres': matieres,
            'exercices_count': exercices_counts.get(classe_id, 0),
        })

    classes_categories = sorted(classes_grouped.keys(), key=lambda x: x.lower())
    classes_options = []
    for categorie in classes_categories:
        for item in classes_grouped.get(categorie, {}).get('classes', []):
            classes_options.append({
                'classe': item['classe'],
                'categorie': categorie,
                'matieres': item['matieres'],
            })
    categories_data = [
        {
            'nom': categorie,
            'classes': classes_grouped.get(categorie, {}).get('classes', []),
        }
        for categorie in classes_categories
    ]
    classes_options_json = []
    classes_seen = set()
    for data in classes_grouped.values():
        for item in data['classes']:
            classe_obj = item['classe']
            if classe_obj.id in classes_seen:
                continue
            classes_seen.add(classe_obj.id)
            classes_options_json.append({
                'id': classe_obj.id,
                'nom': classe_obj.nom,
                'matieres': [{'id': m.id, 'nom': m.nom} for m in item['matieres']],
            })

    stats = {
        'total_classes': len({item['classe'].id for item in classes_options}),
        'total_exercices': sum(exercices_counts.values()),
    }

    classe_id = request.GET.get('classe')
    if classe_id and classe_id.isdigit() and int(classe_id) in classes_map:
        classe_selectionnee = classes_map[int(classe_id)]['classe']
        matieres_disponibles = classes_map[int(classe_id)]['matieres']
    else:
        first_entry = next(iter(classes_map.values()))
        classe_selectionnee = first_entry['classe']
        matieres_disponibles = first_entry['matieres']

    matiere_id = request.GET.get('matiere')
    matiere_selectionnee = None
    if matiere_id and matieres_disponibles:
        matiere_selectionnee = next(
            (m for m in matieres_disponibles if str(m.id) == matiere_id),
            None
        )
        if matiere_selectionnee is None and matieres_disponibles:
            messages.error(request, "Matière sélectionnée invalide.")
            return redirect(request.path)
    elif matieres_disponibles:
        matiere_selectionnee = matieres_disponibles[0]

    if request.method == 'POST':
        titre = request.POST.get('titre', '').strip()
        description = request.POST.get('description', '').strip()
        classe_post = request.POST.get('classe')
        matiere_post = request.POST.get('matiere')
        periode_post = request.POST.get('periode')
        date_rendu_str = request.POST.get('date_rendu', '').strip()
        exercice_id = request.POST.get('exercice_id')

        if not all([titre, classe_post, matiere_post, date_rendu_str]):
            messages.error(request, "Merci de renseigner tous les champs obligatoires.")
            return redirect(request.get_full_path())

        try:
            classe_obj = classes_map[int(classe_post)]['classe']
            matieres_obj = classes_map[int(classe_post)]['matieres']
        except (KeyError, ValueError):
            messages.error(request, "Classe invalide.")
            return redirect(request.get_full_path())

        matiere_obj = next(
            (m for m in matieres_obj if str(m.id) == matiere_post),
            None
        )
        if matiere_obj is None:
            messages.error(request, "Matière invalide.")
            return redirect(request.get_full_path())

        periode_obj = None
        if periode_post:
            try:
                periode_obj = periodes.get(id=periode_post)
            except PeriodeScolaire.DoesNotExist:
                messages.error(request, "Période sélectionnée invalide.")
                return redirect(request.get_full_path())

        date_rendu = parse_date(date_rendu_str)
        if date_rendu is None:
            messages.error(request, "La date de rendu est invalide.")
            return redirect(request.get_full_path())

        action_message = "programmé"
        try:
            if exercice_id:
                try:
                    exercice = ExerciceMaison.objects.get(
                        id=exercice_id,
                        professeur=professeur,
                        classe_id__in=classe_ids,
                    )
                except ExerciceMaison.DoesNotExist:
                    messages.error(request, "Exercice introuvable ou non autorisé.")
                    return redirect(request.get_full_path())

                exercice.etablissement = classe_obj.etablissement
                exercice.classe = classe_obj
                exercice.matiere = matiere_obj
                exercice.periode_scolaire = periode_obj
                exercice.titre = titre
                exercice.description = description
                exercice.date_rendu = date_rendu
                exercice.actif = True
                if annee_scolaire_active:
                    exercice.annee_scolaire = annee_scolaire_active
                exercice.save()
                action_message = "mis à jour"
            else:
                exercice = ExerciceMaison.objects.create(
                    etablissement=classe_obj.etablissement,
                    professeur=professeur,
                    classe=classe_obj,
                    matiere=matiere_obj,
                    periode_scolaire=periode_obj,
                    titre=titre,
                    description=description,
                    date_rendu=date_rendu,
                    actif=True,
                    annee_scolaire=annee_scolaire_active,
                )
        except Exception as creation_error:
            logger.error(
                "Erreur lors de l'enregistrement d'un exercice de maison: %s",
                creation_error,
                exc_info=True,
            )
            messages.error(request, f"Erreur lors de l'enregistrement de l'exercice : {creation_error}")
            return redirect(request.get_full_path())

        # Programmer l'envoi des notifications en arrière-plan (uniquement pour les nouveaux exercices)
        if not exercice_id:
            from ..services.notification_tasks import schedule_exercice_maison_notification
            schedule_exercice_maison_notification(exercice.id)
            logger.info(f"Envoi des notifications programmé en arrière-plan pour l'exercice de maison {exercice.id}")

        messages.success(request, f"Exercice de maison « {titre} » {action_message} avec succès.")

        query_params = {
            'classe': classe_obj.id,
            'matiere': matiere_obj.id,
        }
        if periode_obj:
            query_params['periode'] = periode_obj.id
        query_string = urlencode(query_params)
        redirect_url = f"{request.path}?{query_string}" if query_string else request.path
        return redirect(redirect_url)

    exercices = []
    if classe_selectionnee and matiere_selectionnee:
        try:
            exercices_qs = ExerciceMaison.objects.filter(
                professeur=professeur,
                classe=classe_selectionnee,
                matiere=matiere_selectionnee,
                actif=True,
            )
            if annee_scolaire_active:
                exercices_qs = exercices_qs.filter(annee_scolaire=annee_scolaire_active)
            if periode_selectionnee:
                exercices_qs = exercices_qs.filter(periode_scolaire=periode_selectionnee)
            exercices = list(exercices_qs.select_related('classe', 'matiere', 'periode_scolaire', 'professeur').order_by('-date_rendu', '-date_creation'))
        except (ProgrammingError, OperationalError) as exc:
            exercices = []
            logger.warning(
                "Impossible de récupérer les exercices : %s",
                exc,
            )

    today = timezone.now().date()
    exercices_cards = []
    exercices_json = []
    for exercice in exercices:
        delta = (exercice.date_rendu - today).days
        if delta < 0:
            status_class = 'retard'
            abs_delta = abs(delta)
            status_label = f"En retard de {abs_delta} jour{'s' if abs_delta > 1 else ''}"
            status_icon = 'fas fa-exclamation-triangle'
        elif delta == 0:
            status_class = 'jour'
            status_label = "À rendre aujourd'hui"
            status_icon = 'fas fa-calendar-day'
        elif delta == 1:
            status_class = 'bientot'
            status_label = "À rendre demain"
            status_icon = 'fas fa-hourglass-half'
        elif delta <= 3:
            status_class = 'proche'
            status_label = f"Dans {delta} jours"
            status_icon = 'fas fa-hourglass-start'
        else:
            status_class = 'planifie'
            status_label = f"Dans {delta} jours"
            status_icon = 'fas fa-clock'

        exercices_cards.append({
            'id': exercice.id,
            'classe_id': exercice.classe_id,
            'classe_nom': exercice.classe.nom if exercice.classe else "",
            'matiere_id': exercice.matiere_id,
            'matiere_nom': exercice.matiere.nom if exercice.matiere else "Matière non définie",
            'periode_id': exercice.periode_scolaire_id,
            'periode_nom': exercice.periode_scolaire.nom_periode if exercice.periode_scolaire else "Sans période",
            'titre': exercice.titre,
            'description': exercice.description or "",
            'date_rendu': exercice.date_rendu,
            'date_rendu_iso': exercice.date_rendu.isoformat(),
            'date_creation': exercice.date_creation,
            'professeur_nom': getattr(exercice.professeur, 'nom_complet', str(exercice.professeur)),
            'status_class': status_class,
            'status_label': status_label,
            'status_icon': status_icon,
            'jours_restant': delta,
            'jours_restant_abs': abs(delta),
        })

        exercices_json.append({
            'id': exercice.id,
            'classe_id': exercice.classe_id,
            'matiere_id': exercice.matiere_id,
            'periode_id': exercice.periode_scolaire_id,
            'titre': exercice.titre,
            'description': exercice.description or "",
            'date_rendu': exercice.date_rendu.isoformat(),
        })

    context = {
        'professeur': professeur,
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'classes_grouped': classes_grouped,
        'classes_categories': classes_categories,
        'classes_options': classes_options,
        'categories_data': categories_data,
        'classes_options_json': classes_options_json,
        'classe_selectionnee': classe_selectionnee,
        'matieres_disponibles': matieres_disponibles,
        'matiere_selectionnee': matiere_selectionnee,
        'exercices': exercices,
        'exercices_cards': exercices_cards,
        'exercices_json': exercices_json,
        'aujourdhui': today,
        'stats': stats,
        'annee_scolaire_active': annee_scolaire_active,
    }

    return render(request, 'school_admin/enseignant/exercices_maison.html', context)
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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    from django.db.models import Q, Count
    from django.utils import timezone
    from datetime import timedelta
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        return redirect('enseignant_primaire:gestion_presence')
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer toutes les affectations actives du professeur (filtrées par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('classe', 'classe__etablissement').prefetch_related('classe__eleves').order_by('classe__nom')
    
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
        
        # Récupérer les élèves actifs de cette classe via InscriptionEleve
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        # Déterminer la matière enseignée pour cette affectation
        # Pour les établissements secondaires, utiliser la matière de l'affectation
        # Pour le primaire, utiliser la matière principale du professeur ou None
        est_secondaire_classe = classe.etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
        matiere_enseignee = affectation.matiere if affectation.matiere else (professeur.matiere_principale if not est_secondaire_classe else None)
        
        # Calculer les statistiques de présence pour chaque élève
        # IMPORTANT : Si professeur principal → voir TOUTES les présences, sinon uniquement les siennes
        # IMPORTANT : Filtrer par matière pour différencier les présences de chaque matière
        eleves_avec_presence = []
        for eleve in eleves:
            # Déterminer si on filtre par professeur ou pas
            if affectation.is_principal:
                # Professeur principal : voir TOUTES les présences de la classe (toutes matières)
                presences_queryset = Presence.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    date__gte=debut_annee
                )
                if annee_scolaire_active:
                    presences_queryset = presences_queryset.filter(annee_scolaire=annee_scolaire_active)
                presences = presences_queryset
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
                    # Pour le primaire, les présences n'ont pas de matière
                    filters_presence['matiere__isnull'] = True
                
                presences_queryset = Presence.objects.filter(**filters_presence)
                if annee_scolaire_active:
                    presences_queryset = presences_queryset.filter(annee_scolaire=annee_scolaire_active)
                presences = presences_queryset
            
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
        'annee_scolaire_active': annee_scolaire_active,
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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    
    # Rediriger les enseignants du primaire vers leur page dédiée
    if professeur.etablissement and professeur.etablissement.type_etablissement == 'primary':
        periode_id = request.GET.get('periode', '')
        if periode_id:
            return redirect(f'/enseignant/primaire/eleves-difficulte/?periode={periode_id}')
        return redirect('enseignant_primaire:eleves_en_difficulte')
    
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)

    # Récupérer toutes les périodes scolaires de l'établissement
    periodes_queryset = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes_scolaires = periodes_queryset.order_by('date_debut')
    
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
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = (
        affectations_queryset
        .select_related('classe', 'classe__etablissement')
        .prefetch_related('classe__eleves')
        .order_by('classe__nom')
    )
    
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
        
        # Récupérer les élèves actifs de cette classe via InscriptionEleve
        eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
        
        # Déterminer la matière enseignée pour cette affectation
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
        
        # Récupérer les évaluations pour cette classe, matière et période
        evaluations_liste = []
        if periode_active_obj and matiere_enseignee:
            # Récupérer toutes les évaluations
            toutes_evaluations = Evaluation.objects.filter(
                classe=classe,
                professeur=professeur,
                periode_scolaire=periode_active_obj,
                actif=True,
                matiere=matiere_enseignee
            ).order_by('date_evaluation')
            
            # Classer par barème : <= 10 = interrogation, > 10 = devoir
            for i, eval_obj in enumerate(toutes_evaluations, 1):
                if eval_obj.bareme <= 10:
                    evaluations_liste.append({
                        'key': f'interro_{i}',
                        'evaluation': eval_obj,
                        'type': 'interrogation',
                        'index': i,
                    })
                else:
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
            moyennes_queryset = Moyenne.objects.filter(
                classe=classe,
                professeur=professeur,
                matiere=matiere_enseignee,
                actif=True
            )
            if annee_scolaire_active:
                moyennes_queryset = moyennes_queryset.filter(annee_scolaire=annee_scolaire_active)
            moyennes = moyennes_queryset.select_related('eleve')
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    from ..utils.session_utils import get_session_active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    
    # Récupérer les élèves actifs de la classe via InscriptionEleve
    eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
    
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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    from decimal import Decimal, InvalidOperation
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer l'ID de la matière si fourni dans l'URL
    matiere_id = request.GET.get('matiere')
    
    # Récupérer l'affectation appropriée (filtrée par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('matiere')
    
    # Si une matière est spécifiée, filtrer par cette matière
    if matiere_id:
        affectations = affectations.filter(matiere_id=matiere_id)
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_notes')
    
    # Prendre la première affectation correspondante
    affectation = affectations.first()
    
    # Récupérer toutes les périodes scolaires de l'établissement (filtrées par année scolaire active)
    periodes_scolaires_queryset = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_scolaires_queryset = periodes_scolaires_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes_scolaires = periodes_scolaires_queryset.order_by('date_debut')
    
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
    
    # Récupérer les élèves de la classe (filtrés par année scolaire active)
    eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)

    # Récupérer toutes les évaluations de la classe pour ce professeur pour la période active
    # FILTRER PAR MATIÈRE pour ne prendre que les évaluations de la bonne matière
    if periode_active_obj:
        # Récupérer toutes les évaluations (filtrées par année scolaire active)
        toutes_evaluations_queryset = Evaluation.objects.filter(
            classe=classe,
            professeur=professeur,
            periode_scolaire=periode_active_obj,
            actif=True,
            matiere=matiere_enseignee  # Filtrer par matière
        )
        if annee_scolaire_active:
            toutes_evaluations_queryset = toutes_evaluations_queryset.filter(annee_scolaire=annee_scolaire_active)
        toutes_evaluations = list(toutes_evaluations_queryset.order_by('date_evaluation'))
        
        # Classer par barème : <= 10 = interrogation, > 10 = devoir
        evaluations_interrogations = [e for e in toutes_evaluations if e.bareme <= 10]
        evaluations_devoirs = [e for e in toutes_evaluations if e.bareme > 10]
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
    
    # Récupérer les notes existantes pour chaque élève (avec statut retenue)
    notes_existantes = {}
    notes_objets = {}  # Pour stocker les objets Note complets avec le statut retenue
    for eleve in eleves:
        notes_existantes[eleve.id] = {}
        notes_objets[eleve.id] = {}
        for key, evaluation in evaluations_map.items():
            if evaluation:
                note_obj = Note.objects.filter(eleve=eleve, evaluation=evaluation).first()
                if note_obj:
                    notes_existantes[eleve.id][key] = note_obj.note
                    notes_objets[eleve.id][key] = note_obj  # Stocker l'objet complet
    
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
            action = request.POST.get('action')
            if not action and 'submit_notes' in request.POST:
                action = 'enregistrer'
            if not action:
                action = 'enregistrer'
            
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
            
            from ..model.session_examen_model import SessionExamen
            from ..model.note_examen_model import NoteExamen

            session_examen_post = None
            if periode_active_obj:
                sessions_possibles_queryset = SessionExamen.objects.filter(
                    etablissement=professeur.etablissement,
                    classes=classe,
                    matieres=matiere_enseignee,
                    periode=periode_active_obj,
                    actif=True
                )
                if annee_scolaire_active:
                    sessions_possibles_queryset = sessions_possibles_queryset.filter(annee_scolaire=annee_scolaire_active)
                sessions_possibles = sessions_possibles_queryset.order_by('-date_debut')
                
                if sessions_possibles.exists():
                    for session in sessions_possibles:
                        notes_count_queryset = NoteExamen.objects.filter(
                            session_examen=session,
                            matiere=matiere_enseignee,
                            classe=classe,
                            actif=True
                        )
                        if annee_scolaire_active:
                            notes_count_queryset = notes_count_queryset.filter(annee_scolaire=annee_scolaire_active)
                        notes_count = notes_count_queryset.count()
                        if notes_count > 0:
                            session_examen_post = session
                            break
                    if not session_examen_post:
                        session_examen_post = sessions_possibles.first()
            
            if action == 'publier':
                try:
                    publication_time = timezone.now()
                    notes_publiees_total = 0
                    eleves_notifies = 0

                    def format_decimal(value):
                        if value is None:
                            return "-"
                        try:
                            dec = Decimal(str(value))
                        except (InvalidOperation, ValueError, TypeError):
                            return str(value)
                        if dec == dec.quantize(Decimal('1')):
                            return format(dec.quantize(Decimal('1')), 'f')
                        formatted = format(dec.quantize(Decimal('0.01')), 'f')
                        if formatted.endswith('0'):
                            formatted = formatted.rstrip('0').rstrip('.')
                        return formatted

                    with transaction.atomic():
                        for eleve in eleves:
                            notes_a_publier = []

                            for key, evaluation in evaluations_map.items():
                                if not evaluation:
                                    continue
                                note_obj = Note.objects.filter(eleve=eleve, evaluation=evaluation).first()
                                if (
                                    note_obj
                                    and note_obj.note is not None
                                    and not note_obj.absent
                                    and (note_obj.note_publiee is None or note_obj.note_publiee != note_obj.note)
                                ):
                                    notes_a_publier.append({
                                        'type': 'evaluation',
                                        'note_obj': note_obj,
                                        'valeur': note_obj.note,
                                        'bareme': evaluation.bareme,
                                        'titre': evaluation.titre,
                                        'date': getattr(evaluation, 'date_evaluation', None),
                                        'matiere_nom': (evaluation.matiere.nom if evaluation.matiere else matiere_enseignee.nom),
                                    })

                            if session_examen_post:
                                note_examen_obj = NoteExamen.objects.filter(
                                    eleve=eleve,
                                    session_examen=session_examen_post,
                                    matiere=matiere_enseignee
                                ).first()
                                if (
                                    note_examen_obj
                                    and note_examen_obj.note is not None
                                    and not note_examen_obj.absent
                                    and (note_examen_obj.note_publiee is None or note_examen_obj.note_publiee != note_examen_obj.note)
                                ):
                                    notes_a_publier.append({
                                        'type': 'examen',
                                        'note_obj': note_examen_obj,
                                        'valeur': note_examen_obj.note,
                                        'bareme': getattr(note_examen_obj, 'bareme', 20),
                                        'titre': getattr(
                                            session_examen_post,
                                            'titre',
                                            getattr(session_examen_post, 'nom_examen', 'Examen')
                                        ),
                                        'date': getattr(session_examen_post, 'date_debut', None),
                                        'matiere_nom': matiere_enseignee.nom,
                                    })

                            if not notes_a_publier:
                                continue

                            eleves_notifies += 1

                            for note_info in notes_a_publier:
                                valeur = note_info['valeur']
                                bareme_note = note_info['bareme']
                                titre_note = note_info['titre']
                                matiere_nom = note_info['matiere_nom']

                                valeur_affiche = format_decimal(valeur)
                                bareme_affiche = format_decimal(bareme_note)

                                message_eleve = (
                                    f"Tu as {valeur_affiche}/{bareme_affiche} en {matiere_nom} ({titre_note}). "
                                    "Les notes ont été publiées."
                                )
                                details = {
                                    "message": message_eleve,
                                    "note": valeur_affiche,
                                    "bareme": bareme_affiche,
                                    "evaluation": titre_note,
                                    "type": note_info['type'],
                                }

                                note_source = note_info['note_obj']

                                try:
                                    EleveNotificationService.notify_note(
                                        eleve=eleve,
                                        matiere_nom=matiere_nom,
                                        details=details,
                                        source=note_source,
                                    )
                                except Exception as notification_error:
                                    logger.error(
                                        "Erreur lors de la notification élève pour la publication des notes: %s",
                                        notification_error,
                                        exc_info=True,
                                    )

                                try:
                                    ParentNotificationService.notify_note(
                                        eleve=eleve,
                                        matiere_nom=matiere_nom,
                                        note_obtenue=valeur,
                                        bareme=bareme_note,
                                        evaluation_nom=titre_note,
                                        professeur_nom=getattr(professeur, 'nom_complet', str(professeur)),
                                        date_evaluation=note_info['date'],
                                        source=note_source,
                                    )
                                except Exception as notification_error:
                                    logger.error(
                                        "Erreur lors de la notification parent pour la publication des notes: %s",
                                        notification_error,
                                        exc_info=True,
                                    )

                                if isinstance(note_source, Note):
                                    note_source.note_publiee = note_source.note
                                    note_source.date_publication = publication_time
                                    note_source.statut_publication = Note.STATUT_PUBLIEE
                                    note_source.save(update_fields=['note_publiee', 'date_publication', 'statut_publication'])
                                else:
                                    note_source.note_publiee = note_source.note
                                    note_source.date_publication = publication_time
                                    note_source.statut_publication = NoteExamen.STATUT_PUBLIEE
                                    note_source.save(update_fields=['note_publiee', 'date_publication', 'statut_publication', 'note_sur_20'])

                                notes_publiees_total += 1

                    if notes_publiees_total > 0:
                        messages.success(
                            request,
                            f"✓ {notes_publiees_total} note(s) publiée(s). Notifications envoyées à {eleves_notifies} élève(s)."
                        )
                    else:
                        messages.info(request, "Aucune nouvelle note à publier. Toutes les notes étaient déjà visibles.")

                except Exception as e:
                    logger.error(f"Erreur lors de la publication des notes: {e}")
                    messages.error(request, f"Erreur lors de la publication des notes : {str(e)}")

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
            
            if action == 'enregistrer':
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
                                                'matiere': matiere_note,
                                                'annee_scolaire': annee_scolaire_active
                                            }
                                        )
                                        
                                        # Si la note existait déjà, mettre à jour l'année scolaire
                                        if not created and annee_scolaire_active:
                                            note_obj.annee_scolaire = annee_scolaire_active
                                            note_obj.save(update_fields=['annee_scolaire'])
                                        
                                        # Vérifier si la note a réellement changé
                                        note_a_change = (
                                            created or 
                                            (note_existante and note_existante.note != note_decimal) or 
                                            (note_existante and note_existante.absent != False)
                                        )
                                        
                                        if note_a_change:
                                            notes_enregistrees += 1
                                    
                                        if note_obj.note_publiee is None:
                                            note_obj.statut_publication = Note.STATUT_BROUILLON
                                        elif note_obj.note_publiee != note_obj.note:
                                            note_obj.statut_publication = Note.STATUT_MODIFIEE
                                        else:
                                            note_obj.statut_publication = Note.STATUT_PUBLIEE
                                        note_obj.save(update_fields=['statut_publication'])
                                    
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
                                                'absent': False,
                                                'annee_scolaire': annee_scolaire_active
                                            }
                                        )
                                        
                                        # Mettre à jour la note
                                        note_examen_obj.note = note_examen_decimal
                                        note_examen_obj.absent = False
                                        note_examen_obj.professeur = professeur
                                        note_examen_obj.classe = classe
                                        if annee_scolaire_active:
                                            note_examen_obj.annee_scolaire = annee_scolaire_active
                                        
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
                                    
                                        if note_examen_obj.note_publiee is None:
                                            note_examen_obj.statut_publication = NoteExamen.STATUT_BROUILLON
                                        elif note_examen_obj.note_publiee != note_examen_obj.note:
                                            note_examen_obj.statut_publication = NoteExamen.STATUT_MODIFIEE
                                        else:
                                            note_examen_obj.statut_publication = NoteExamen.STATUT_PUBLIEE
                                        note_examen_obj.save(update_fields=['statut_publication'])
                                        
                                    except (ValueError, Exception) as e:
                                        logger.error(f"Erreur saisie note d'examen pour {eleve.nom_complet}: {str(e)}")
                                        errors.append(f"{eleve.nom_complet} : Valeur invalide pour la note d'examen")
                    
                    if errors:
                        messages.warning(request, f"{notes_enregistrees} notes enregistrées. Erreurs : " + " | ".join(errors[:5]))
                    else:
                        messages.success(request, f"✓ {notes_enregistrees} notes enregistrées avec succès !")

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
        # Récupérer toutes les sessions pour cette période/classe/matière (filtrées par année scolaire active)
        sessions_possibles_queryset = SessionExamen.objects.filter(
            etablissement=professeur.etablissement,
            classes=classe,
            matieres=matiere_enseignee,
            periode=periode_active_obj,
            actif=True
        )
        if annee_scolaire_active:
            sessions_possibles_queryset = sessions_possibles_queryset.filter(annee_scolaire=annee_scolaire_active)
        sessions_possibles = sessions_possibles_queryset.order_by('-date_debut')
        
        # Prioriser la session qui a déjà des notes enregistrées (filtrées par année scolaire active)
        for session in sessions_possibles:
            notes_count_queryset = NoteExamen.objects.filter(
                session_examen=session,
                matiere=matiere_enseignee,
                classe=classe,
                actif=True
            )
            if annee_scolaire_active:
                notes_count_queryset = notes_count_queryset.filter(annee_scolaire=annee_scolaire_active)
            notes_count = notes_count_queryset.count()
            if notes_count > 0:
                session_examen = session
                break
        
        # Si aucune session avec notes, prendre la première
        if not session_examen and sessions_possibles.exists():
            session_examen = sessions_possibles.first()
        
        # Récupérer les notes d'examen pour chaque élève (filtrées par année scolaire active)
        if session_examen:
            for eleve in eleves:
                note_examen_queryset = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session_examen,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                )
                if annee_scolaire_active:
                    note_examen_queryset = note_examen_queryset.filter(annee_scolaire=annee_scolaire_active)
                note_examen = note_examen_queryset.first()
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
        'notes_objets': notes_objets,  # Objets Note complets avec statut retenue
        'moyennes_enregistrees': moyennes_enregistrees,
        'has_evaluations': len(evaluations_liste) > 0,
        'releve_notes': releve_notes,
        'periode_active': periode_active_obj,
        'periodes_scolaires': periodes_scolaires,
        'notes_retenues_par_eval': notes_retenues_par_eval,
        'session_examen': session_examen,
        'notes_examen_par_eleve': notes_examen_par_eleve,
        'total_evaluations_count': total_evaluations_count,
        'annee_scolaire_active': annee_scolaire_active,
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
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer l'ID de la matière si fourni dans l'URL
    matiere_id = request.GET.get('matiere')
    
    # Récupérer l'affectation appropriée (filtrée par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('matiere')
    
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
        date_evaluation = request.POST.get('date_evaluation', '')
        bareme = request.POST.get('bareme', '20')
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
                        classe=classe,
                        professeur=professeur,
                        matiere=matiere_enseignee,
                        date_evaluation=date_evaluation,
                        bareme=bareme_float,
                        periode_scolaire=periode_scolaire,
                        actif=True,
                        annee_scolaire=annee_scolaire_active
                    )
                    
                    logger.info(f"Évaluation créée: {evaluation.id} - {evaluation.titre}")
                    
                    # Programmer l'envoi des notifications en arrière-plan
                    from ..services.notification_tasks import schedule_evaluation_notification
                    schedule_evaluation_notification(evaluation.id)
                    logger.info(f"Envoi des notifications programmé en arrière-plan pour l'évaluation {evaluation.id}")
                    
                    messages.success(request, f"L'évaluation '{evaluation.titre}' a été créée avec succès !")
                    if matiere_id:
                        return redirect(f"/enseignant/notes/?matiere={matiere_id}")
                    return redirect('enseignant:gestion_notes')
                    
            except Exception as e:
                logger.error(f"Erreur lors de la création de l'évaluation: {str(e)}")
                errors['general'] = f"Erreur lors de la création de l'évaluation : {str(e)}"
        
        # Stocker les erreurs et les données dans le contexte
        periodes_scolaires_queryset = PeriodeScolaire.objects.filter(
            etablissement=professeur.etablissement,
            est_active=True
        )
        if annee_scolaire_active:
            periodes_scolaires_queryset = periodes_scolaires_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
        periodes_scolaires = periodes_scolaires_queryset.order_by('date_debut')
        
        # Compter le nombre d'élèves actifs dans la classe via InscriptionEleve
        nombre_eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active).count()
        
        context = {
            'professeur': professeur,
            'classe': classe,
            'affectation': affectation,
            'matiere': matiere_enseignee,
            'nombre_eleves': nombre_eleves,
            'periodes_scolaires': periodes_scolaires,
            'errors': errors,
            'form_data': request.POST,
            'aujourdhui': date.today().isoformat(),
        }
        
        return render(request, 'school_admin/enseignant/creer_evaluation.html', context)
    
    # GET request
    periodes_scolaires_queryset = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_scolaires_queryset = periodes_scolaires_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes_scolaires = periodes_scolaires_queryset.order_by('date_debut')
    
    # Compter le nombre d'élèves actifs dans la classe
    from ..model.eleve_model import Eleve
    eleves_queryset = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    nombre_eleves = eleves_queryset.count()
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'matiere': matiere_enseignee,
        'nombre_eleves': nombre_eleves,
        'periodes_scolaires': periodes_scolaires,
        'errors': {},
        'form_data': {'date_evaluation': date.today().isoformat()},
        'annee_scolaire_active': annee_scolaire_active,
        'aujourdhui': date.today().isoformat(),
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
    from ..utils.session_utils import get_session_active
    import re
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, "etablissement") else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)

    # Récupérer toutes les périodes scolaires actives
    periodes_scolaires_queryset = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_scolaires_queryset = periodes_scolaires_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes_scolaires = periodes_scolaires_queryset.order_by('date_debut')
    
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
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('classe', 'matiere').order_by('classe__nom')
    
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
        if annee_scolaire_active:
            evals_query = evals_query.filter(annee_scolaire=annee_scolaire_active)
        
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
    if annee_scolaire_active:
        toutes_evaluations = toutes_evaluations.filter(annee_scolaire=annee_scolaire_active)
    
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
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/liste_evaluations.html', context)


def supprimer_evaluation_enseignant(request, evaluation_id):
    """
    Supprime une évaluation existante.
    """
    if request.method != 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Méthode non autorisée.'})
        messages.error(request, "Méthode non autorisée.")
        return redirect('enseignant:liste_evaluations')
    
    if not isinstance(request.user, Professeur):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Accès non autorisé.'})
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.evaluation_model import Evaluation
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    from django.http import JsonResponse
    
    try:
        evaluation = get_object_or_404(Evaluation, id=evaluation_id, professeur=professeur, actif=True)
        titre_evaluation = evaluation.titre
        
        with transaction.atomic():
            # Marquer l'évaluation comme inactive (soft delete)
            evaluation.actif = False
            evaluation.save()
        
        logger.info(f"Évaluation {evaluation_id} supprimée par {professeur.nom_complet}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f"L'évaluation '{titre_evaluation}' a été supprimée avec succès.",
            })
        
        messages.success(request, f"L'évaluation '{titre_evaluation}' a été supprimée avec succès.")
        return redirect('enseignant:liste_evaluations')
        
    except Evaluation.DoesNotExist:
        error_message = "Évaluation introuvable ou vous n'avez pas la permission de la supprimer."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_message})
        messages.error(request, error_message)
        return redirect('enseignant:liste_evaluations')
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de l'évaluation {evaluation_id}: {e}", exc_info=True)
        error_message = f"Une erreur est survenue lors de la suppression : {str(e)}"
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_message})
        messages.error(request, error_message)
        return redirect('enseignant:liste_evaluations')


def modifier_evaluation_enseignant(request, evaluation_id):
    """
    Modifie une évaluation existante pour les enseignants secondaires.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.evaluation_model import Evaluation
    from ..model.classe_model import Classe
    from ..model.affectation_model import AffectationProfesseur
    from ..model.periode_model import PeriodeScolaire
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    from django.http import JsonResponse
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, professeur=professeur, actif=True)
    classe = evaluation.classe
    
    # Vérifier que le professeur est affecté à cette classe
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    if not affectations.exists():
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "Vous n'êtes pas affecté à cette classe."})
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:liste_evaluations')
    
    # Récupérer les matières et périodes
    matieres_enseignees = [aff.matiere for aff in affectations if aff.matiere]
    if not matieres_enseignees and professeur.matiere_principale:
        matieres_enseignees = [professeur.matiere_principale]
    
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
                matiere_id = request.POST.get('matiere')
                date_evaluation = request.POST.get('date_evaluation')
                bareme = request.POST.get('bareme', 20)
                periode_id = request.POST.get('periode_scolaire')
                
                # Validation
                if not all([titre, matiere_id, date_evaluation]):
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': 'Tous les champs obligatoires doivent être remplis.'})
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('enseignant:liste_evaluations')
                
                from ..model.matiere_model import Matiere
                matiere = get_object_or_404(Matiere, id=matiere_id)
                
                # Vérifier que le professeur enseigne cette matière
                if matiere not in matieres_enseignees:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': "Vous n'enseignez pas cette matière dans cette classe."})
                    messages.error(request, "Vous n'enseignez pas cette matière dans cette classe.")
                    return redirect('enseignant:liste_evaluations')
                
                periode_scolaire = None
                if periode_id:
                    try:
                        periode_scolaire = periodes.get(id=periode_id)
                    except PeriodeScolaire.DoesNotExist:
                        pass
                
                # Mettre à jour l'évaluation
                evaluation.titre = titre
                evaluation.description = description
                evaluation.matiere = matiere
                evaluation.date_evaluation = date_evaluation
                evaluation.bareme = bareme
                evaluation.periode_scolaire = periode_scolaire
                evaluation.save()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f"Évaluation '{titre}' modifiée avec succès.",
                        'redirect_url': '/enseignant/evaluations/'
                    })
                
                messages.success(request, f"Évaluation '{titre}' modifiée avec succès.")
                return redirect('enseignant:liste_evaluations')
                
        except Exception as e:
            logger.error(f"Erreur lors de la modification de l'évaluation: {e}")
            error_message = f"Une erreur est survenue: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
    
    # Pour les requêtes AJAX (chargement du formulaire)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        html = render_to_string('school_admin/enseignant/partials/modal_modifier_evaluation.html', {
            'evaluation': evaluation,
            'matieres': matieres_enseignees,
            'periodes': periodes,
        }, request=request)
        return JsonResponse({'html': html})
    
    # Pour les requêtes normales (redirection)
    return redirect('enseignant:liste_evaluations')


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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from django.http import JsonResponse
    from django.db import transaction
    from decimal import Decimal, InvalidOperation
    import json
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer l'affectation (peut y en avoir plusieurs si plusieurs matières, filtrée par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('matiere')
    
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
    
    # Récupérer la période scolaire (filtrée par année scolaire active)
    from ..model.periode_model import PeriodeScolaire
    periode_active = None
    if periode_id:
        try:
            periode_queryset = PeriodeScolaire.objects.filter(id=periode_id, etablissement=professeur.etablissement)
            if annee_scolaire_active:
                periode_queryset = periode_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
            periode_active = periode_queryset.first()
            if not periode_active:
                return JsonResponse({
                    'success': False,
                    'error': 'Période scolaire invalide'
                }, status=400)
        except PeriodeScolaire.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Période scolaire invalide'
            }, status=400)
    
    # Récupérer les élèves de la classe (filtrés par année scolaire active)
    if annee_scolaire_active:
        # Filtrer les élèves par année scolaire active via InscriptionEleve
        eleves_ids_inscrits = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire_active,
            classe=classe,
            etablissement=etablissement
        ).values_list('eleve_id', flat=True)
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    else:
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    
    # Mapper les évaluations pour la période (même logique que dans noter_eleves_enseignant)
    # Récupérer toutes les évaluations (filtrées par année scolaire active)
    toutes_evaluations_queryset = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        periode_scolaire=periode_active,
        actif=True
    )
    if annee_scolaire_active:
        toutes_evaluations_queryset = toutes_evaluations_queryset.filter(annee_scolaire=annee_scolaire_active)
    toutes_evaluations = list(toutes_evaluations_queryset.order_by('date_evaluation'))
    
    # Classer par barème : <= 10 = interrogation, > 10 = devoir
    evaluations_interrogations = [e for e in toutes_evaluations if e.bareme <= 10]
    evaluations_devoirs = [e for e in toutes_evaluations if e.bareme > 10]
    
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
    
    # Chercher les sessions d'examen possibles pour cette classe, matière et période (filtrées par année scolaire active)
    # Ne chercher que si la période est définie
    if periode_active:
        sessions_possibles_queryset = SessionExamen.objects.filter(
            etablissement=professeur.etablissement,
            classes=classe,
            matieres=matiere_enseignee,
            periode=periode_active,
            actif=True
        )
        if annee_scolaire_active:
            sessions_possibles_queryset = sessions_possibles_queryset.filter(annee_scolaire=annee_scolaire_active)
        sessions_possibles = sessions_possibles_queryset.order_by('-date_debut')
        
        # Prioriser une session qui a déjà des notes enregistrées (filtrées par année scolaire active)
        if sessions_possibles.exists():
            for session in sessions_possibles:
                notes_count_queryset = NoteExamen.objects.filter(
                    session_examen=session,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                )
                if annee_scolaire_active:
                    notes_count_queryset = notes_count_queryset.filter(annee_scolaire=annee_scolaire_active)
                notes_count = notes_count_queryset.count()
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
                
                # Récupérer les notes pour ces évaluations (filtrées par année scolaire active)
                # IMPORTANT : Filtrer aussi par matière pour éviter les notes d'autres matières
                notes_queryset = Note.objects.filter(
                    eleve=eleve,
                    evaluation__in=evaluations_selectionnees,
                    absent=False,
                    matiere=matiere_enseignee  # Filtrer par matière
                )
                if annee_scolaire_active:
                    notes_queryset = notes_queryset.filter(annee_scolaire=annee_scolaire_active)
                notes = notes_queryset.select_related('evaluation') if evaluations_selectionnees else Note.objects.none()
                
                logger.info(f"Notes trouvées pour {eleve.nom_complet}: {notes.count()}")
                for note in notes:
                    logger.info(f"  - Évaluation: {note.evaluation.titre}, Note: {note.note}/{note.evaluation.bareme}")
                
                # Récupérer automatiquement la note d'examen si elle existe (incluse par défaut, filtrée par année scolaire active)
                note_examen = None
                if session_examen:
                    note_examen_queryset = NoteExamen.objects.filter(
                        eleve=eleve,
                        session_examen=session_examen,
                        matiere=matiere_enseignee,
                        classe=classe,
                        absent=False,
                        actif=True
                    )
                    if annee_scolaire_active:
                        note_examen_queryset = note_examen_queryset.filter(annee_scolaire=annee_scolaire_active)
                    note_examen = note_examen_queryset.first()
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
                        'evaluation_titre': note.evaluation.titre
                    }
                    
                    logger.info(f"Note convertie pour {eleve.nom_complet}: {note.note}/{note.evaluation.bareme} = {note_sur_20:.2f}/20")
                    
                    # Classer selon le barème : <= 10 = interrogation, > 10 = devoir
                    if note.evaluation.bareme <= 10:
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
                        'actif': True,
                        'annee_scolaire': annee_scolaire_active
                    }
                )
                
                # Si la moyenne existait déjà, mettre à jour l'année scolaire
                if not created and annee_scolaire_active:
                    moyenne_obj.annee_scolaire = annee_scolaire_active
                    moyenne_obj.save(update_fields=['annee_scolaire'])
                
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
                        periode_nom=getattr(periode_active, 'nom_periode', None),
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
    from decimal import Decimal, InvalidOperation
    
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
    
    # Récupérer les élèves via InscriptionEleve
    from ..utils.session_utils import get_session_active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
    
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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Vérifier l'affectation et récupérer la matière enseignée (filtrée par année scolaire active)
    matiere_id = request.GET.get('matiere', '')
    matiere_enseignee = None
    
    if matiere_id:
        try:
            matiere_enseignee = Matiere.objects.get(id=matiere_id, etablissement=professeur.etablissement)
        except Matiere.DoesNotExist:
            pass
    
    # Si pas de matière spécifiée, utiliser la matière principale
    if not matiere_enseignee:
        affectation_queryset = AffectationProfesseur.objects.filter(
            professeur=professeur,
            classe=classe,
            actif=True
        )
        if annee_scolaire_active:
            affectation_queryset = affectation_queryset.filter(annee_scolaire=annee_scolaire_active)
        affectation = get_object_or_404(affectation_queryset)
        matiere_enseignee = affectation.matiere if affectation.matiere else professeur.matiere_principale
    
    # Récupérer la période active (filtrée par année scolaire active)
    periode_id = request.GET.get('periode', '')
    periode_active = None
    
    if periode_id:
        try:
            periode_queryset = PeriodeScolaire.objects.filter(
                id=periode_id,
                etablissement=professeur.etablissement,
                est_active=True
            )
            if annee_scolaire_active:
                periode_queryset = periode_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
            periode_active = periode_queryset.first()
        except PeriodeScolaire.DoesNotExist:
            pass
    
    if not periode_active:
        periodes_queryset = PeriodeScolaire.objects.filter(
            etablissement=professeur.etablissement,
            est_active=True
        )
        if annee_scolaire_active:
            periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
        periodes = periodes_queryset.order_by('date_debut')
        for p in periodes:
            if p.est_en_cours:
                periode_active = p
                break
        if not periode_active:
            periode_active = periodes.first()
    
    # Récupérer tous les élèves (filtrés par année scolaire active)
    eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    
    # Récupérer les moyennes et construire le relevé
    eleves_data = []
    
    for eleve in eleves:
        moyenne_obj = None
        if periode_active:
            moyenne_queryset = Moyenne.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=matiere_enseignee,
                periode=str(periode_active.id),
                actif=True
            )
            if annee_scolaire_active:
                moyenne_queryset = moyenne_queryset.filter(annee_scolaire=annee_scolaire_active)
            moyenne_obj = moyenne_queryset.first()
        
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
        
        # Récupérer la note d'examen si disponible (filtrée par année scolaire active)
        if periode_active:
            sessions_examens_queryset = SessionExamen.objects.filter(
                etablissement=professeur.etablissement,
                classes=classe,
                matieres=matiere_enseignee,
                periode=periode_active,
                actif=True
            )
            if annee_scolaire_active:
                sessions_examens_queryset = sessions_examens_queryset.filter(annee_scolaire=annee_scolaire_active)
            sessions_examens = sessions_examens_queryset
            
            for session in sessions_examens:
                note_examen_queryset = NoteExamen.objects.filter(
                    session_examen=session,
                    eleve=eleve,
                    matiere=matiere_enseignee,
                    classe=classe,
                    actif=True
                )
                if annee_scolaire_active:
                    note_examen_queryset = note_examen_queryset.filter(annee_scolaire=annee_scolaire_active)
                note_examen = note_examen_queryset.first()
                
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
        'annee_scolaire_active': annee_scolaire_active,
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

    # Récupérer les élèves via InscriptionEleve
    from ..utils.session_utils import get_session_active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
    
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
    from decimal import Decimal, InvalidOperation
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
    
    # Récupérer les élèves via InscriptionEleve
    from ..utils.session_utils import get_session_active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
    
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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from datetime import date
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Vérifier que la classe existe et que le professeur y est affecté
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer toutes les affectations pour cette classe (filtrées par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Vérifier si c'est un établissement secondaire (lycée, collège, collège_lycée)
    etablissement = classe.etablissement
    est_secondaire = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
    
    # Récupérer la matière depuis GET si fournie (PRIORITÉ au paramètre URL)
    matiere_id = request.GET.get('matiere', '').strip()
    matiere_selectionnee = None
    affectation_utilisee = None
    
    # PRIORITÉ 1: Si un paramètre matiere est fourni dans l'URL, l'utiliser
    if matiere_id:
        try:
            matiere_selectionnee = Matiere.objects.get(id=int(matiere_id), etablissement=etablissement)
            # Vérifier que cette matière correspond à une affectation du professeur
            affectation_utilisee = affectations.filter(matiere=matiere_selectionnee).first()
            if not affectation_utilisee:
                messages.error(request, f"Vous n'êtes pas affecté à cette classe pour la matière {matiere_selectionnee.nom}.")
                return redirect('enseignant:gestion_eleves')
        except (Matiere.DoesNotExist, ValueError, TypeError):
            messages.error(request, "Matière non trouvée ou invalide.")
            return redirect('enseignant:gestion_eleves')
    
    # PRIORITÉ 2: Si établissement secondaire et plusieurs affectations, nécessite la sélection d'une matière
    if est_secondaire and affectations.count() > 1:
        if not matiere_selectionnee:
            # Afficher la page avec sélection de matière
            matieres_affectations = []
            for aff in affectations:
                if aff.matiere:
                    matieres_affectations.append({
                        'id': aff.matiere.id,
                        'nom': aff.matiere.nom,
                        'affectation': aff
                    })
            
            eleves_queryset = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
            context = {
                'professeur': professeur,
                'classe': classe,
                'matieres_affectations': matieres_affectations,
                'today': date.today(),
                'nombre_eleves': eleves_queryset.count(),
            }
            return render(request, 'school_admin/enseignant/selection_matiere_presence.html', context)
    else:
        # Pour les établissements primaires ou une seule affectation
        # Si pas de matière sélectionnée depuis l'URL, utiliser celle de l'affectation
        if not matiere_selectionnee:
            affectation_utilisee = affectations.first()
            if affectation_utilisee and affectation_utilisee.matiere:
                matiere_selectionnee = affectation_utilisee.matiere
        else:
            # Si une matière a été fournie dans l'URL, vérifier qu'elle correspond à une affectation
            affectation_utilisee = affectations.filter(matiere=matiere_selectionnee).first()
            if not affectation_utilisee and est_secondaire:
                # Pour les établissements secondaires, la matière doit correspondre à une affectation
                messages.error(request, f"Vous n'êtes pas affecté à cette classe pour la matière {matiere_selectionnee.nom}.")
                return redirect('enseignant:gestion_eleves')
    
    # Date du jour
    today = date.today()
    
    # Vérifier si une soumission existe déjà dans SoumissionListePresence
    # IMPORTANT: Filtrer par année scolaire active pour éviter les conflits entre années
    from ..model.presence_model import SoumissionListePresence
    soumission_existante = None
    if matiere_selectionnee or not est_secondaire:
        filters_soumission = {
            'classe': classe,
            'professeur': professeur,
            'matiere': matiere_selectionnee if matiere_selectionnee else None,
            'date': today
        }
        # Filtrer par année scolaire active
        if annee_scolaire_active:
            filters_soumission['annee_scolaire'] = annee_scolaire_active
        else:
            # Si pas d'année scolaire active, chercher uniquement celles sans année scolaire
            filters_soumission['annee_scolaire__isnull'] = True
        soumission_existante = SoumissionListePresence.objects.filter(**filters_soumission).first()
    
    # Vérifier s'il existe déjà une liste de présence pour aujourd'hui et cette matière
    # ATTENTION: Ne créer/récupérer la liste que si une matière a été sélectionnée OU si ce n'est pas un établissement secondaire
    # IMPORTANT: Filtrer par année scolaire active pour éviter les conflits entre années
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
        
        # Filtrer par année scolaire active
        if annee_scolaire_active:
            filters['annee_scolaire'] = annee_scolaire_active
        else:
            # Si pas d'année scolaire active, chercher uniquement celles sans année scolaire
            filters['annee_scolaire__isnull'] = True
        
        # Pour éviter les doublons, chercher d'abord une ListePresence existante
        liste_presence = ListePresence.objects.filter(**filters).first()
        
        # Si pas trouvée et qu'on est dans un établissement secondaire, chercher aussi sans matière
        # (pour éviter de créer un doublon) - MAIS toujours filtrer par année scolaire
        if not liste_presence and est_secondaire and matiere_selectionnee:
            filters_sans_matiere = {
                'classe': classe,
                'date': today,
                'matiere__isnull': True
            }
            if annee_scolaire_active:
                filters_sans_matiere['annee_scolaire'] = annee_scolaire_active
            else:
                filters_sans_matiere['annee_scolaire__isnull'] = True
            liste_presence = ListePresence.objects.filter(**filters_sans_matiere).first()
            
            # Si on trouve une ListePresence sans matière, la mettre à jour avec la matière
            if liste_presence:
                liste_presence.matiere = matiere_selectionnee
                liste_presence.save()
        
        # Si toujours pas trouvée, créer une nouvelle ListePresence avec l'année scolaire active
        if not liste_presence:
            liste_presence = ListePresence.objects.create(
                classe=classe,
                date=today,
                professeur=professeur,
                etablissement=classe.etablissement,
                matiere=matiere_selectionnee,
                annee_scolaire=annee_scolaire_active
            )
        
        # Si la liste est déjà validée, rediriger avec un message
        if liste_presence.validee:
            matiere_msg = f" pour la matière {matiere_selectionnee.nom}" if matiere_selectionnee else ""
            messages.info(request, f"La liste de présence{matiere_msg} a déjà été validée pour aujourd'hui.")
    
    # Si on est ici, c'est qu'une matière a été sélectionnée ou que ce n'est pas un établissement secondaire
    # Récupérer tous les élèves actifs de la classe (filtrés par année scolaire active)
    eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    
    # IMPORTANT: Récupérer les présences déjà enregistrées pour aujourd'hui et CETTE matière spécifique
    # Pour les établissements secondaires, on DOIT filtrer par matière
    filters_presence = {
        'classe': classe,
        'date': today,
        'numero_appel': 1  # Pour lycée/collège, on garde 1 appel par jour par matière
    }
    
    # Filtrer par année scolaire active
    if annee_scolaire_active:
        filters_presence['annee_scolaire'] = annee_scolaire_active
    
    # Pour les établissements secondaires, la matière est OBLIGATOIRE
    if est_secondaire:
        if matiere_selectionnee:
            filters_presence['matiere'] = matiere_selectionnee
        else:
            # Si établissement secondaire sans matière, erreur
            messages.error(request, "La matière est obligatoire pour les établissements secondaires.")
            return redirect('enseignant:gestion_eleves')
    else:
        # Pour le primaire, pas de matière
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
    
    # Déterminer si le formulaire doit être désactivé
    formulaire_desactive = False
    message_soumission = None
    
    if soumission_existante:
        formulaire_desactive = True
        matiere_msg = f" pour la matière {matiere_selectionnee.nom}" if matiere_selectionnee else ""
        message_soumission = f"Les présences{matiere_msg} ont déjà été soumises pour aujourd'hui."
        messages.warning(request, message_soumission)
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'eleves_avec_presence': eleves_avec_presence,
        'liste_presence': liste_presence,
        'today': today,
        'nombre_eleves': eleves.count(),
        'matiere': matiere_selectionnee,
        'est_secondaire': est_secondaire,
        'soumission_existante': soumission_existante,
        'formulaire_desactive': formulaire_desactive,
        'message_soumission': message_soumission,
        'annee_scolaire_active': annee_scolaire_active,
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
    from ..model.presence_model import Presence, ListePresence, SoumissionListePresence
    from ..model.matiere_model import Matiere
    from ..model.etablissement_model import Etablissement
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from datetime import date
    from django.db import transaction
    
    # Récupérer les données des champs cachés
    classe_id_post = request.POST.get('classe_id', '').strip()
    professeur_id_post = request.POST.get('professeur_id', '').strip()
    etablissement_id_post = request.POST.get('etablissement_id', '').strip()
    matiere_id_post = request.POST.get('matiere_id', '').strip()
    
    # Validation des données reçues
    if not classe_id_post or not professeur_id_post or not etablissement_id_post:
        logger.error(f"Données manquantes dans la soumission - Classe: {classe_id_post}, Prof: {professeur_id_post}, Etab: {etablissement_id_post}")
        messages.error(request, "Données manquantes. Veuillez réessayer.")
        return redirect('enseignant:liste_presence', classe_id=classe_id)
    
    # Vérifier que les IDs correspondent
    try:
        classe = get_object_or_404(Classe, id=int(classe_id_post))
        professeur_obj = get_object_or_404(Professeur, id=int(professeur_id_post))
        etablissement = get_object_or_404(Etablissement, id=int(etablissement_id_post))
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = None
        if etablissement:
            annee_scolaire_active = get_session_active(request, etablissement)
    except (ValueError, TypeError) as e:
        logger.error(f"Erreur de conversion des IDs - {str(e)}")
        messages.error(request, "Données invalides. Veuillez réessayer.")
        return redirect('enseignant:liste_presence', classe_id=classe_id)
    
    # Vérifier que le professeur connecté correspond
    if professeur.id != professeur_obj.id:
        logger.warning(f"Tentative de soumission par un autre professeur - User: {request.user.id}, Prof ID: {professeur_id_post}")
        messages.error(request, "Erreur d'authentification.")
        return redirect('enseignant:gestion_eleves')
    
    # Vérifier que la classe correspond à l'établissement
    if classe.etablissement.id != etablissement.id:
        logger.error(f"Incohérence classe/établissement - Classe: {classe.id}, Etab: {etablissement.id}")
        messages.error(request, "Données incohérentes. Veuillez réessayer.")
        return redirect('enseignant:gestion_eleves')
    
    # Vérifier que le professeur est affecté à cette classe
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer la matière si fournie
    matiere_selectionnee = None
    est_secondaire = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
    
    if matiere_id_post:
        try:
            matiere_selectionnee = Matiere.objects.get(id=int(matiere_id_post), etablissement=etablissement)
        except (Matiere.DoesNotExist, ValueError, TypeError) as e:
            logger.warning(f"Matière non trouvée ou invalide - ID: {matiere_id_post}, Erreur: {str(e)}")
            if est_secondaire:
                messages.error(request, "Matière non trouvée ou invalide.")
                return redirect('enseignant:liste_presence', classe_id=classe_id)
    
    # Pour les établissements secondaires, la matière est obligatoire
    if est_secondaire and not matiere_selectionnee:
        messages.error(request, "La matière est obligatoire pour les établissements secondaires.")
        return redirect('enseignant:liste_presence', classe_id=classe_id)
    
    # Date du jour
    today = date.today()
    numero_appel = 1  # Par défaut, premier appel
    
    try:
        with transaction.atomic():
            # Vérifier si une soumission existe déjà pour cette combinaison
            # IMPORTANT: Filtrer par année scolaire active pour éviter les conflits entre années
            # Utiliser matiere=None si pas de matière pour le primaire
            filters_soumission = {
                'classe': classe,
                'professeur': professeur,
                'matiere': matiere_selectionnee if matiere_selectionnee else None,
                'date': today
            }
            # Filtrer par année scolaire active
            if annee_scolaire_active:
                filters_soumission['annee_scolaire'] = annee_scolaire_active
            else:
                # Si pas d'année scolaire active, chercher uniquement celles sans année scolaire
                filters_soumission['annee_scolaire__isnull'] = True
            soumission_existante = SoumissionListePresence.objects.filter(**filters_soumission).first()
            
            if soumission_existante:
                matiere_msg = f" pour la matière {matiere_selectionnee.nom}" if matiere_selectionnee else ""
                messages.warning(
                    request, 
                    f"La liste de présence{matiere_msg} a déjà été soumise pour aujourd'hui."
                )
                # Rediriger avec le paramètre matiere si applicable
                from django.urls import reverse
                if matiere_selectionnee:
                    url = reverse('enseignant:liste_presence', args=[classe_id]) + f'?matiere={matiere_selectionnee.id}'
                    return redirect(url)
                return redirect('enseignant:liste_presence', classe_id=classe_id)
            
            # Parcourir les données POST pour enregistrer les présences
            nombre_presents = 0
            nombre_absents = 0
            presences_creees = []
            
            # Log pour déboguer
            logger.info(f"Validation présence - POST keys: {list(request.POST.keys())}")
            logger.info(f"Validation présence - Nombre d'éléments POST: {len(request.POST)}")
            
            # Récupérer tous les élèves de la classe pour s'assurer qu'on traite tous les élèves
            eleves_classe = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
            logger.info(f"Validation présence - Nombre d'élèves dans la classe: {eleves_classe.count()}")
            
            # Parcourir les données POST pour enregistrer les présences
            presences_post = {}
            for key, value in request.POST.items():
                if key.startswith('presence_'):
                    eleve_id = key.replace('presence_', '')
                    presences_post[eleve_id] = value
                    logger.info(f"Traitement présence - Key: {key}, Value: {value}, Eleve ID: {eleve_id}")
            
            logger.info(f"Validation présence - Nombre de présences dans POST: {len(presences_post)}")
            
            # Traiter chaque élève de la classe
            for eleve in eleves_classe:
                eleve_id_str = str(eleve.id)
                statut = presences_post.get(eleve_id_str, 'present')  # Par défaut 'present' si non spécifié
                
                try:
                    # Créer ou mettre à jour la présence
                    # Le unique_together est (eleve, classe, date, numero_appel, matiere)
                    presence, created = Presence.objects.update_or_create(
                        eleve=eleve,
                        classe=classe,
                        date=today,
                        numero_appel=numero_appel,
                        matiere=matiere_selectionnee,
                        defaults={
                            'professeur': professeur,
                            'etablissement': etablissement,
                            'statut': statut,
                            'annee_scolaire': annee_scolaire_active
                        }
                    )
                    
                    # Si la présence existait déjà, mettre à jour le statut et s'assurer que la matière est correcte
                    if not created:
                        presence.professeur = professeur
                        presence.etablissement = etablissement
                        presence.statut = statut
                        # S'assurer que la matière est toujours correcte (important pour les établissements secondaires)
                        if matiere_selectionnee and not presence.matiere:
                            presence.matiere = matiere_selectionnee
                        # S'assurer que l'année scolaire active est toujours correcte
                        if annee_scolaire_active:
                            presence.annee_scolaire = annee_scolaire_active
                        presence.save()
                    
                    presences_creees.append(presence)
                    
                    # Compter les présents et absents
                    if statut == 'present':
                        nombre_presents += 1
                    elif statut in ['absent', 'absent_justifie']:
                        nombre_absents += 1
                    
                    logger.info(f"Présence enregistrée - Élève: {eleve.nom_complet}, Statut: {statut}, Créée: {created}")
                    
                except Eleve.DoesNotExist:
                    logger.warning(f"Élève {eleve.id} non trouvé ou inactif")
                    continue
                except Exception as e:
                    logger.error(f"Erreur lors de l'enregistrement de la présence pour l'élève {eleve.id}: {str(e)}")
                    continue
            
            # Créer l'enregistrement de soumission avec l'année scolaire active
            soumission = SoumissionListePresence.objects.create(
                classe=classe,
                professeur=professeur,
                etablissement=etablissement,
                matiere=matiere_selectionnee,
                date=today,
                date_soumission=timezone.now(),
                annee_scolaire=annee_scolaire_active
            )
            
            logger.info(
                f"Liste de présence soumise avec succès - Classe: {classe.nom}, "
                f"Matière: {matiere_selectionnee.nom if matiere_selectionnee else 'N/A'}, "
                f"Présents: {nombre_presents}, Absents: {nombre_absents}"
            )
            
            # Programmer l'envoi des notifications en arrière-plan
            if presences_creees:
                presence_ids = [p.id for p in presences_creees]
                from ..services.notification_tasks import schedule_presence_notifications
                schedule_presence_notifications(presence_ids)
                logger.info(f"Envoi des notifications programmé en arrière-plan pour {len(presence_ids)} présence(s)")
            
            matiere_msg = f" pour la matière {matiere_selectionnee.nom}" if matiere_selectionnee else ""
            messages.success(
                request,
                f"Liste de présence{matiere_msg} soumise avec succès ! "
                f"{nombre_presents} présent(s), {nombre_absents} absent(s)."
            )
            
    except Exception as e:
        logger.error(f"Erreur lors de la soumission de la liste de présence: {str(e)}", exc_info=True)
        messages.error(request, f"Erreur lors de la soumission : {str(e)}")
    
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
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from datetime import date, timedelta
    
    # Récupérer l'élève
    eleve = get_object_or_404(Eleve, id=eleve_id, actif=True)
    
    # Récupérer l'établissement et l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    if not etablissement and hasattr(eleve, 'etablissement'):
        etablissement = eleve.etablissement
    
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe active de l'élève pour l'année scolaire active
    classe = _get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    if not classe:
        messages.error(request, "Cet élève n'est pas inscrit dans une classe pour l'année scolaire active.")
        return redirect('enseignant:gestion_eleves')
    
    # Vérifier que le professeur est affecté à cette classe et récupérer toutes les affectations (matières, filtrées par année scolaire active)
    from ..model.affectation_model import AffectationProfesseur
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset
    
    if not affectations.exists():
        messages.error(request, "Vous n'êtes pas affecté à cette classe pour l'année scolaire active.")
        return redirect('enseignant:gestion_eleves')
    
    # Vérifier le type d'établissement
    if not etablissement:
        etablissement = classe.etablissement
    est_secondaire = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
    
    # Récupérer toutes les matières enseignées dans cette classe
    matieres_list = []
    for aff in affectations:
        matiere = aff.matiere if aff.matiere else professeur.matiere_principale
        if matiere and matiere not in matieres_list:
            matieres_list.append(matiere)
    
    # Si aucune matière trouvée via affectations, utiliser la matière principale du professeur
    if not matieres_list and professeur.matiere_principale:
        matieres_list.append(professeur.matiere_principale)
    
    # Récupérer la matière sélectionnée depuis l'URL (MÉTHODE SIMPLE)
    # Pas de vérification d'établissement ou d'affectation : on utilise directement la matière de l'URL
    matiere_id = request.GET.get('matiere')
    matiere_selectionnee = None
    
    from ..model.matiere_model import Matiere
    
    if matiere_id:
        try:
            matiere_selectionnee = Matiere.objects.get(id=int(matiere_id))
            # S'assurer que la matière soit dans la liste pour l'affichage
            if matiere_selectionnee not in matieres_list:
                matieres_list.append(matiere_selectionnee)
        except (Matiere.DoesNotExist, ValueError, TypeError):
            matiere_selectionnee = None
    
    # IMPORTANT: Toujours traiter TOUTES les matières pour construire presences_par_matiere
    # Le paramètre matiere de l'URL servira uniquement à déterminer quelle matière afficher dans le template
    matieres_a_traiter = matieres_list
    
    # Récupérer l'onglet actif (par défaut: notes)
    onglet_actif = request.GET.get('onglet', 'notes')
    
    # === ONGLET NOTES ===
    from ..model.periode_model import PeriodeScolaire
    
    # Récupérer toutes les périodes scolaires (filtrées par année scolaire active)
    periodes_queryset = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_queryset.order_by('date_debut')
    
    # Récupérer la période sélectionnée
    periode_id = request.GET.get('periode')
    if periode_id:
        periode_selectionnee = PeriodeScolaire.objects.filter(id=periode_id).first()
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Créer un dictionnaire de données par matière pour les notes
    notes_par_matiere = {}
    for matiere in matieres_list:
        # Récupérer les évaluations de cette matière pour cette période (filtrées par année scolaire active)
        evaluations_queryset = Evaluation.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=matiere,
            periode_scolaire=periode_selectionnee,
            actif=True
        )
        if annee_scolaire_active:
            evaluations_queryset = evaluations_queryset.filter(annee_scolaire=annee_scolaire_active)
        evaluations = evaluations_queryset.order_by('date_evaluation') if periode_selectionnee else []
        
        # Récupérer les notes de l'élève pour ces évaluations (filtrées par année scolaire active)
        notes_objs_queryset = Note.objects.filter(
            eleve=eleve,
            evaluation__in=evaluations,
            matiere=matiere
        )
        if annee_scolaire_active:
            notes_objs_queryset = notes_objs_queryset.filter(annee_scolaire=annee_scolaire_active)
        notes_objs = notes_objs_queryset.select_related('evaluation')
        
        # Créer un dictionnaire des notes indexé par evaluation_id
        notes_dict = {note.evaluation.id: note for note in notes_objs}
        
        # Récupérer la moyenne enregistrée pour cette matière et période (filtrée par année scolaire active)
        moyenne_queryset = Moyenne.objects.filter(
            eleve=eleve,
            professeur=professeur,
            matiere=matiere,
            periode=str(periode_selectionnee.id) if periode_selectionnee else None,
            actif=True
        )
        if annee_scolaire_active:
            moyenne_queryset = moyenne_queryset.filter(annee_scolaire=annee_scolaire_active)
        moyenne_obj = moyenne_queryset.first() if periode_selectionnee else None
        
        moyenne = moyenne_obj.moyenne if moyenne_obj else None
        
        # Récupérer la note d'examen pour cette matière/période si une session existe (filtrée par année scolaire active)
        note_examen_dict = None
        if periode_selectionnee:
            from ..model.session_examen_model import SessionExamen
            from ..model.note_examen_model import NoteExamen
            session_examen_qs_queryset = SessionExamen.objects.filter(
                etablissement=professeur.etablissement,
                classes=classe,
                matieres=matiere,
                periode=periode_selectionnee,
                actif=True
            )
            if annee_scolaire_active:
                session_examen_qs_queryset = session_examen_qs_queryset.filter(annee_scolaire=annee_scolaire_active)
            session_examen_qs = session_examen_qs_queryset.order_by('-date_debut')
            session_examen_sel = None
            if session_examen_qs.exists():
                for sess in session_examen_qs:
                    note_examen_check_queryset = NoteExamen.objects.filter(
                        session_examen=sess,
                        matiere=matiere,
                        classe=classe,
                        actif=True
                    )
                    if annee_scolaire_active:
                        note_examen_check_queryset = note_examen_check_queryset.filter(annee_scolaire=annee_scolaire_active)
                    if note_examen_check_queryset.exists():
                        session_examen_sel = sess
                        break
                if not session_examen_sel:
                    session_examen_sel = session_examen_qs.first()
            if session_examen_sel:
                note_exam_queryset = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session_examen_sel,
                    matiere=matiere,
                    classe=classe,
                    actif=True
                )
                if annee_scolaire_active:
                    note_exam_queryset = note_exam_queryset.filter(annee_scolaire=annee_scolaire_active)
                note_exam_obj = note_exam_queryset.first()
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
    # Récupération simple et directe des présences depuis la table Presence (filtrées par année scolaire active)
    from ..model.presence_model import Presence
    from datetime import date
    import calendar
    
    presences_all = Presence.objects.none()
    presences = []
    total_presences = 0
    nombre_presents = 0
    nombre_absences = 0
    nombre_absences_justifiees = 0
    nombre_retards = 0
    taux_presence = 0
    mois_disponibles = []
    mois_selectionne = request.GET.get('mois')  # Format: "2024-11" ou "2024-11"
    
    # Si une matière est sélectionnée, récupérer toutes les présences
    if matiere_selectionnee:
        # Filtres de base : élève, matière, professeur, classe
        filters_presence = {
            'eleve': eleve,
            'matiere': matiere_selectionnee,
            'professeur': professeur,
            'classe': classe,
        }
        
        # Récupérer TOUTES les présences (filtrées par année scolaire active)
        presences_all_queryset = Presence.objects.filter(
            **filters_presence
        )
        if annee_scolaire_active:
            presences_all_queryset = presences_all_queryset.filter(annee_scolaire=annee_scolaire_active)
        presences_all = presences_all_queryset.select_related('matiere', 'eleve').order_by('-date')
        
        # Extraire les mois uniques qui ont des présences
        mois_avec_presences = set()
        presences_list_all = list(presences_all[:1000])  # Limiter pour les performances
        for presence in presences_list_all:
            mois_avec_presences.add((presence.date.year, presence.date.month))
        
        # Créer la liste des mois disponibles (triés du plus récent au plus ancien)
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
        
        # Filtrer par mois sélectionné si un mois est spécifié
        if mois_selectionne:
            try:
                annee_str, mois_str = mois_selectionne.split('-')
                annee_filtre = int(annee_str)
                mois_filtre = int(mois_str)
                
                # Filtrer les présences pour ce mois
                presences = [
                    p for p in presences_list_all
                    if p.date.year == annee_filtre and p.date.month == mois_filtre
                ]
            except (ValueError, IndexError):
                # Si le format est invalide, utiliser toutes les présences
                presences = presences_list_all
        else:
            # Si aucun mois sélectionné, utiliser toutes les présences
            presences = presences_list_all
        
        # Calculer les statistiques sur les présences filtrées
        total_presences = len(presences)
        nombre_presents = sum(1 for p in presences if p.statut == 'present')
        nombre_absences = sum(1 for p in presences if p.statut == 'absent')
        nombre_absences_justifiees = sum(1 for p in presences if p.statut == 'absent_justifie')
        nombre_retards = sum(1 for p in presences if p.statut == 'retard')
        taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
    
    # === ONGLET SANCTIONS ===
    from ..model.sanction_model import Sanction
    sanctions_queryset = Sanction.objects.filter(
        eleve=eleve,
        classe=classe
    )
    if annee_scolaire_active:
        sanctions_queryset = sanctions_queryset.filter(annee_scolaire=annee_scolaire_active)
    sanctions = sanctions_queryset.order_by('-date_sanction', '-date_creation')
    
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
        # Onglet Présences - données simples et directes
        'presences': presences,
        'total_presences': total_presences,
        'nombre_absences': nombre_absences,
        'nombre_absences_justifiees': nombre_absences_justifiees,
        'nombre_retards': nombre_retards,
        'nombre_presents': nombre_presents,
        'taux_presence': taux_presence,
        'mois_disponibles': mois_disponibles,
        'mois_selectionne': mois_selectionne,
        'presences_data': {'presences': presences} if (presences or mois_disponibles) else None,  # Pour compatibilité avec le template
        # Onglet Sanctions
        'sanctions': sanctions,
        'nombre_sanctions': nombre_sanctions,
        'nombre_sanctions_graves': nombre_sanctions_graves,
        'annee_scolaire_active': annee_scolaire_active,
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
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from datetime import date, timedelta
    
    # Récupérer l'élève
    eleve = get_object_or_404(Eleve, id=eleve_id, actif=True)
    
    # Récupérer l'établissement et l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    if not etablissement and hasattr(eleve, 'etablissement'):
        etablissement = eleve.etablissement
    
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe active de l'élève pour l'année scolaire active
    classe = _get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    if not classe:
        messages.error(request, "Cet élève n'est pas inscrit dans une classe pour l'année scolaire active.")
        return redirect('enseignant:gestion_eleves')
    
    # Vérifier que le professeur est affecté à cette classe pour l'année scolaire active
    from ..model.affectation_model import AffectationProfesseur
    affectation_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_queryset = affectation_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_queryset.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe pour l'année scolaire active.")
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
    
    # Récupération avec option de filtrage (filtrée par année scolaire active)
    periode_filtree = request.GET.get('periode', 'annee')
    
    if periode_filtree == '30jours':
        date_debut = today - timedelta(days=30)
        presences_queryset = Presence.objects.filter(
            eleve=eleve,
            date__gte=date_debut
        )
        if annee_scolaire_active:
            presences_queryset = presences_queryset.filter(annee_scolaire=annee_scolaire_active)
        presences = presences_queryset.order_by('-date')
    elif periode_filtree == '7jours':
        date_debut = today - timedelta(days=7)
        presences_queryset = Presence.objects.filter(
            eleve=eleve,
            date__gte=date_debut
        )
        if annee_scolaire_active:
            presences_queryset = presences_queryset.filter(annee_scolaire=annee_scolaire_active)
        presences = presences_queryset.order_by('-date')
    else:  # annee
        presences_queryset = Presence.objects.filter(
            eleve=eleve,
            date__gte=debut_annee,
            date__lte=fin_annee
        )
        if annee_scolaire_active:
            presences_queryset = presences_queryset.filter(annee_scolaire=annee_scolaire_active)
        presences = presences_queryset.order_by('-date')
    
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
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    from django.db.models import Count, Q, Avg
    from datetime import date, timedelta
    
    # Récupérer l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
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
    
    # Vérifier que le professeur est affecté à cette classe (filtré par année scolaire active)
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset
    
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
    # Filtrer les élèves par année scolaire active
    # Récupérer les élèves via InscriptionEleve
    eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
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
    
    # Présences du mois filtré (filtrées par année scolaire active)
    # IMPORTANT : Filtrer selon le rôle du professeur
    if affectation.is_principal:
        # Professeur principal : voir TOUTES les présences de la classe
        presences_mois_queryset = Presence.objects.filter(
            classe=classe,
            date__gte=premier_jour_mois,
            date__lte=dernier_jour_mois
        )
        if annee_scolaire_active:
            presences_mois_queryset = presences_mois_queryset.filter(annee_scolaire=annee_scolaire_active)
        presences_mois = presences_mois_queryset
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
        if annee_scolaire_active:
            filters_pres['annee_scolaire'] = annee_scolaire_active
        
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
    
    # Générer la liste des mois avec des présences (filtré par matière et rôle et année scolaire active)
    # IMPORTANT : Afficher uniquement les mois qui ont des données
    if affectation.is_principal:
        # Professeur principal : tous les mois avec des présences dans la classe
        mois_avec_presences_queryset = Presence.objects.filter(classe=classe)
        if annee_scolaire_active:
            mois_avec_presences_queryset = mois_avec_presences_queryset.filter(annee_scolaire=annee_scolaire_active)
        mois_avec_presences = mois_avec_presences_queryset.dates('date', 'month', order='DESC')
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
        if annee_scolaire_active:
            filters_mois['annee_scolaire'] = annee_scolaire_active
        
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
    # Récupérer toutes les périodes scolaires actives (filtrées par année scolaire active)
    from ..model.periode_model import PeriodeScolaire
    periodes_scolaires_queryset = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_scolaires_queryset = periodes_scolaires_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes_scolaires = periodes_scolaires_queryset.order_by('date_debut')
    
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
    
    evaluations_queryset = Evaluation.objects.filter(
        classe=classe,
        professeur=professeur,
        actif=True
    )
    
    # Filtrer par année scolaire active
    if annee_scolaire_active:
        evaluations_queryset = evaluations_queryset.filter(annee_scolaire=annee_scolaire_active)
    
    # Filtrer par matière si spécifiée
    if matiere_enseignee:
        evaluations_queryset = evaluations_queryset.filter(matiere=matiere_enseignee)
    
    # Filtrer par période si spécifiée
    if periode_eval_active:
        evaluations_queryset = evaluations_queryset.filter(periode_scolaire=periode_eval_active)
    
    evaluations = evaluations_queryset.select_related('matiere', 'periode_scolaire').order_by('-date_evaluation')
    
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
        # Absences (filtrées par année scolaire active)
        # IMPORTANT : Filtrer par matière et par professeur selon le rôle
        if affectation.is_principal:
            # Professeur principal : voir TOUTES les absences de la classe
            absences_queryset = Presence.objects.filter(
                eleve=eleve,
                classe=classe,
                statut='absent'
            )
            if annee_scolaire_active:
                absences_queryset = absences_queryset.filter(annee_scolaire=annee_scolaire_active)
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
            if annee_scolaire_active:
                filters_abs['annee_scolaire'] = annee_scolaire_active
            
            absences_queryset = Presence.objects.filter(**filters_abs)
        
        nombre_absences = absences_queryset.count()
        
        # Moyennes (dernière période, filtrées par année scolaire active)
        from ..model.moyenne_model import Moyenne
        moyenne_queryset = Moyenne.objects.filter(
            eleve=eleve,
            professeur=professeur,
            actif=True
        )
        if annee_scolaire_active:
            moyenne_queryset = moyenne_queryset.filter(annee_scolaire=annee_scolaire_active)
        if matiere_enseignee:
            moyenne_queryset = moyenne_queryset.filter(matiere=matiere_enseignee)
        derniere_moyenne = moyenne_queryset.order_by('-date_calcul').first()
        
        # Notes (filtrées par année scolaire active)
        from ..model.evaluation_model import Note
        notes_queryset = Note.objects.filter(
            eleve=eleve,
            evaluation__professeur=professeur
        )
        if annee_scolaire_active:
            notes_queryset = notes_queryset.filter(annee_scolaire=annee_scolaire_active)
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
        'annee_scolaire_active': annee_scolaire_active,
        
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
    from ..utils.session_utils import get_session_active
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
    
    # Récupérer l'année scolaire active
    etablissement = classe.etablissement if hasattr(classe, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
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
            date_sanction=date_sanction,
            annee_scolaire=annee_scolaire_active
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
    from ..utils.session_utils import get_session_active
    from django.shortcuts import get_object_or_404
    
    # Récupérer l'élève
    eleve = get_object_or_404(Eleve, id=eleve_id, actif=True)
    
    # Récupérer l'établissement et l'année scolaire active
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    if not etablissement and hasattr(eleve, 'etablissement'):
        etablissement = eleve.etablissement
    
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe active de l'élève pour l'année scolaire active
    classe = _get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    if not classe:
        messages.error(request, "Cet élève n'est pas inscrit dans une classe pour l'année scolaire active.")
        return redirect('enseignant:gestion_eleves')
    
    # Vérifier que le professeur est affecté à cette classe (filtrée par année scolaire active)
    from ..model.affectation_model import AffectationProfesseur
    affectation_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_queryset = affectation_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_queryset.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe pour l'année scolaire active.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer toutes les sanctions de l'élève (filtrées par année scolaire active)
    sanctions_queryset = Sanction.objects.filter(eleve=eleve)
    if annee_scolaire_active:
        sanctions_queryset = sanctions_queryset.filter(annee_scolaire=annee_scolaire_active)
    sanctions = sanctions_queryset.order_by('-date_sanction', '-date_creation')
    
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
    from ..utils.session_utils import get_session_active
    
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    affectation_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_queryset = affectation_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_queryset.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant:gestion_eleves')
    
    # Récupérer toutes les sanctions de la classe
    sanctions_queryset = Sanction.objects.filter(
        classe=classe
    )
    if annee_scolaire_active:
        sanctions_queryset = sanctions_queryset.filter(annee_scolaire=annee_scolaire_active)
    sanctions = sanctions_queryset.select_related('eleve', 'professeur').order_by('-date_sanction', '-date_creation')
    
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
        'annee_scolaire_active': annee_scolaire_active,
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
            from django.contrib.auth import update_session_auth_hash
            
            old_password = request.POST.get('old_password', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()
            
            # Validation des champs obligatoires
            validation_errors = []
            
            if not old_password:
                validation_errors.append("L'ancien mot de passe est obligatoire.")
            
            if not new_password:
                validation_errors.append("Le nouveau mot de passe est obligatoire.")
            elif len(new_password) < 8:
                validation_errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
            
            if not confirm_password:
                validation_errors.append("La confirmation du mot de passe est obligatoire.")
            elif new_password and confirm_password and new_password != confirm_password:
                validation_errors.append("Les nouveaux mots de passe ne correspondent pas.")
            
            # Si des erreurs de validation existent, les afficher et arrêter
            if validation_errors:
                for error in validation_errors:
                    messages.error(request, error)
            # Vérifier le mot de passe actuel seulement si toutes les validations précédentes sont passées
            elif not check_password(old_password, professeur.password):
                messages.error(request, "L'ancien mot de passe est incorrect.")
            else:
                # Toutes les validations sont passées, changer le mot de passe
                professeur.password = make_password(new_password)
                professeur.save()
                # Maintenir la session active après changement de mot de passe
                update_session_auth_hash(request, professeur)
                messages.success(request, "Mot de passe modifié avec succès.")
                logger.info(f"Mot de passe changé - Professeur: {professeur.nom_complet}")
        
        return redirect('enseignant:parametres_profil')
    
    # Statistiques
    from ..model.affectation_model import AffectationProfesseur
    from ..model.evaluation_model import Evaluation, Note
    from ..model.sanction_model import Sanction
    from django.db.models import Count
    from ..utils.session_utils import get_session_active
    
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)

    affectations_qs = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_qs = affectations_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_classes = affectations_qs.count()

    evaluations_qs = Evaluation.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_evaluations = evaluations_qs.count()

    notes_qs = Note.objects.filter(evaluation__professeur=professeur)
    if annee_scolaire_active and hasattr(Note, "annee_scolaire"):
        notes_qs = notes_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_notes = notes_qs.count()

    sanctions_qs = Sanction.objects.filter(professeur=professeur)
    if annee_scolaire_active and hasattr(Sanction, "annee_scolaire"):
        sanctions_qs = sanctions_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_sanctions = sanctions_qs.count()

    # Dernières activités
    dernieres_evaluations = evaluations_qs.order_by('-date_creation')[:5]
    
    context = {
        'professeur': professeur,
        'nombre_classes': nombre_classes,
        'nombre_evaluations': nombre_evaluations,
        'nombre_notes': nombre_notes,
        'nombre_sanctions': nombre_sanctions,
        'dernieres_evaluations': dernieres_evaluations,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/parametres_profil.html', context)


def historique_annees_enseignant(request):
    """
    Liste les années scolaires précédentes avec un résumé rapide pour l'enseignant.
    """
    logger.info("Historique années scolaires - Enseignant")

    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    professeur = request.user
    etablissement = getattr(professeur, 'etablissement', None)

    if not etablissement:
        messages.error(request, "Établissement introuvable.")
        return redirect('enseignant:parametres_profil')

    from django.utils import timezone
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..model.affectation_model import AffectationProfesseur
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active

    annee_active = get_session_active(request, etablissement)

    annees_queryset = AnneeScolaire.objects.filter(
        etablissement=etablissement
    ).order_by('-date_debut', '-date_fin')

    if annee_active:
        annees_queryset = annees_queryset.exclude(pk=annee_active.pk)

    historique_data = []

    for annee in annees_queryset:
        affectations = AffectationProfesseur.objects.filter(
            professeur=professeur,
            annee_scolaire=annee
        ).select_related('classe')

        classe_ids = list(affectations.values_list('classe_id', flat=True))
        total_eleves = 0

        if classe_ids:
            total_eleves = InscriptionEleve.objects.filter(
                annee_scolaire=annee,
                classe_id__in=classe_ids
            ).count()

        historique_data.append({
            'annee': annee,
            'total_classes': affectations.count(),
            'total_eleves': total_eleves,
        })

    context = {
        'professeur': professeur,
        'etablissement': etablissement,
        'historique_data': historique_data,
    }

    return render(request, 'school_admin/enseignant/historique_annees.html', context)


def detail_historique_annee_enseignant(request, annee_id):
    """
    Affiche le détail complet d'une année scolaire précédente pour l'enseignant.
    """
    logger.info("Détail historique année scolaire - Enseignant")

    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    professeur = request.user
    etablissement = getattr(professeur, 'etablissement', None)

    if not etablissement:
        messages.error(request, "Établissement introuvable.")
        return redirect('enseignant:parametres_profil')

    from ..model.annee_scolaire_model import AnneeScolaire
    from ..model.affectation_model import AffectationProfesseur
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..model.presence_model import Presence
    from ..model.evaluation_model import Evaluation, Note
    from ..model.sanction_model import Sanction
    from django.db.models import Q, Avg, Case, When, Value, FloatField, F, Count
    from django.db.models import ExpressionWrapper

    annee = get_object_or_404(
        AnneeScolaire,
        pk=annee_id,
        etablissement=etablissement
    )

    if getattr(annee, 'est_active', False):
        messages.info(
            request,
            "Cette session est encore active. Désactivez-la depuis l'administration pour consulter son historique complet."
        )
        return redirect('enseignant:historique_annees')

    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        annee_scolaire=annee
    ).select_related('classe', 'matiere')

    classe_ids = list(affectations.values_list('classe_id', flat=True))
    inscriptions_queryset = InscriptionEleve.objects.filter(
        annee_scolaire=annee,
        classe_id__in=classe_ids
    )

    presences_queryset = Presence.objects.filter(
        professeur=professeur,
        annee_scolaire=annee
    )

    nombre_absences = presences_queryset.filter(
        statut__in=['absent', 'absent_justifie']
    ).count()
    nombre_presences = presences_queryset.filter(statut='present').count()

    nombre_devoirs = Evaluation.objects.filter(
        professeur=professeur,
        annee_scolaire=annee
    ).count()

    nombre_sanctions = Sanction.objects.filter(
        professeur=professeur,
        annee_scolaire=annee
    ).count()

    total_eleves = inscriptions_queryset.count()
    total_classes = affectations.count()

    classe_details = []
    note_expression = Case(
        When(
            evaluation__bareme__gt=0,
            then=ExpressionWrapper(
                (F('note') / F('evaluation__bareme')) * Value(20),
                output_field=FloatField()
            )
        ),
        default=Value(0),
        output_field=FloatField()
    )

    for affectation in affectations:
        classe = affectation.classe
        matiere_cible = affectation.matiere or professeur.matiere_principale

        inscriptions_classe = InscriptionEleve.objects.filter(
            annee_scolaire=annee,
            classe=classe
        ).order_by('nom', 'prenom')

        notes_queryset = Note.objects.filter(
            evaluation__professeur=professeur,
            evaluation__classe=classe,
            annee_scolaire=annee
        )

        if matiere_cible:
            notes_queryset = notes_queryset.filter(
                Q(evaluation__matiere=matiere_cible) | Q(matiere=matiere_cible)
            )

        notes_queryset = notes_queryset.exclude(eleve__isnull=True)

        presence_stats = presences_queryset.filter(
            classe=classe
        ).values('eleve_id').annotate(
            absences=Count('id', filter=Q(statut__in=['absent', 'absent_justifie'])),
            presences=Count('id', filter=Q(statut='present'))
        )
        presence_map = {
            item['eleve_id']: {
                'absences': item['absences'],
                'presences': item['presences']
            }
            for item in presence_stats
        }

        sanction_stats = Sanction.objects.filter(
            professeur=professeur,
            annee_scolaire=annee,
            classe=classe
        ).values('eleve_id').annotate(total=Count('id'))
        sanction_map = {item['eleve_id']: item['total'] for item in sanction_stats}

        moyennes_eleves = notes_queryset.values('eleve_id').annotate(
            moyenne=Avg(note_expression)
        )
        moyennes_map = {
            item['eleve_id']: round(item['moyenne'], 2) if item['moyenne'] is not None else None
            for item in moyennes_eleves
        }

        eleves_infos = []
        for inscription in inscriptions_classe:
            moyenne = None
            if inscription.eleve_id:
                moyenne = moyennes_map.get(inscription.eleve_id)

            stats_presence = presence_map.get(inscription.eleve_id, {'absences': 0, 'presences': 0})
            eleves_infos.append({
                'nom': inscription.nom,
                'prenom': inscription.prenom,
                'matricule': inscription.matricule_eleve or inscription.numero_eleve,
                'moyenne': moyenne,
                'absences': stats_presence.get('absences', 0),
                'presences': stats_presence.get('presences', 0),
                'sanctions': sanction_map.get(inscription.eleve_id, 0),
            })

        classe_details.append({
            'classe': classe,
            'matiere_nom': matiere_cible.nom if matiere_cible else "Non renseignée",
            'nombre_eleves': inscriptions_classe.count(),
            'eleves': eleves_infos,
        })

    context = {
        'professeur': professeur,
        'annee': annee,
        'total_classes': total_classes,
        'total_eleves': total_eleves,
        'nombre_presences': nombre_presences,
        'nombre_absences': nombre_absences,
        'nombre_devoirs': nombre_devoirs,
        'nombre_sanctions': nombre_sanctions,
        'classe_details': classe_details,
    }

    return render(request, 'school_admin/enseignant/historique_annee_detail.html', context)


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
    from ..utils.session_utils import get_session_active
    from collections import defaultdict
    
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    affectations_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_queryset = affectations_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations_queryset.select_related('classe')
    
    # Récupérer tous les créneaux du professeur
    classes_ids = affectations.values_list('classe', flat=True)
    emplois_actifs_queryset = EmploiDuTemps.objects.filter(classe__in=classes_ids, est_actif=True)
    if annee_scolaire_active:
        emplois_actifs_queryset = emplois_actifs_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    emplois_actifs = emplois_actifs_queryset
    emplois_publies = emplois_actifs.filter(statut_publication='publie')
    emploi_publie_disponible = emplois_publies.exists()
    
    if emploi_publie_disponible:
        creneaux_professeur_queryset = CreneauEmploiDuTemps.objects.filter(
            professeur=professeur,
            emploi_du_temps__in=emplois_publies
        )
        if annee_scolaire_active:
            creneaux_professeur_queryset = creneaux_professeur_queryset.filter(
                emploi_du_temps__annee_scolaire_fk=annee_scolaire_active
            )
        creneaux_professeur = creneaux_professeur_queryset.select_related('emploi_du_temps', 'emploi_du_temps__classe', 'matiere', 'salle').order_by('jour', 'heure_debut')
    else:
        creneaux_professeur = CreneauEmploiDuTemps.objects.none()
    
    # Organiser les créneaux en grille comme pour le directeur (nouvelle structure)
    from ..controllers.emploi_du_temps_controller import get_matiere_config
    from datetime import datetime, timedelta
    jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
    
    # Créer une plage horaire pour chaque heure de début unique des créneaux
    heures_debut_uniques = sorted(list(set(creneau.heure_debut for creneau in creneaux_professeur)))
    
    plages_horaires = []
    for heure_debut in heures_debut_uniques:
        # Pour chaque heure de début, créer une plage de 1h
        dt_debut = datetime.combine(datetime.today(), heure_debut)
        dt_fin = dt_debut + timedelta(hours=1)
        heure_fin = dt_fin.time()
        
        plages_horaires.append({
            'debut': heure_debut,
            'fin': heure_fin,
            'label': f"{heure_debut.strftime('%H:%M')} - {heure_fin.strftime('%H:%M')}"
        })
    
    # Trier les plages horaires par heure de début (plus tôt en haut)
    plages_horaires.sort(key=lambda p: p['debut'])
    
    # Créer la grille d'emploi du temps (structure similaire aux examens)
    grille_emploi = {}
    for jour in jours_semaine:
        grille_emploi[jour] = {
            'jour': jour,
            'plages': {}
        }
        for plage in plages_horaires:
            grille_emploi[jour]['plages'][plage['label']] = []
    
    # Remplir la grille avec les créneaux
    cellules_masquees = {}
    for creneau in creneaux_professeur:
        jour = creneau.jour
        
        # Trouver la plage horaire correspondante (celle qui commence exactement à l'heure de début du créneau)
        plage_index = -1
        for idx, plage in enumerate(plages_horaires):
            # Le créneau commence exactement à cette plage horaire
            if plage['debut'] == creneau.heure_debut:
                plage_index = idx
                
                # Calculer le rowspan (nombre de plages horaires que le créneau occupe)
                # On compte combien de plages horaires sont couvertes par le créneau
                rowspan = 1
                creneau_fin = creneau.heure_fin
                
                # Parcourir les plages suivantes pour voir combien sont couvertes
                for i in range(1, len(plages_horaires) - plage_index):
                    if plage_index + i < len(plages_horaires):
                        plage_suivante = plages_horaires[plage_index + i]
                        # Si le créneau se termine après le début de la plage suivante, il couvre cette plage
                        if creneau_fin > plage_suivante['debut']:
                            rowspan += 1
                        else:
                            break
                
                if jour in grille_emploi:
                    # Ajouter icône et couleur au créneau
                    matiere_nom = creneau.matiere.nom if creneau.matiere else "Sans matière"
                    icone, couleur = get_matiere_config(matiere_nom)
                    creneau.matiere_icone = icone
                    creneau.matiere_couleur = couleur
                    
                    grille_emploi[jour]['plages'][plage['label']].append({
                        'creneau': creneau,
                        'rowspan': rowspan
                    })
                
                # Marquer les cellules suivantes comme masquées
                if jour not in cellules_masquees:
                    cellules_masquees[jour] = {}
                
                for i in range(1, rowspan):
                    if plage_index + i < len(plages_horaires):
                        plage_suivante = plages_horaires[plage_index + i]
                        cellules_masquees[jour][plage_suivante['label']] = True
                break
    
    # Statistiques
    total_heures = 0
    for creneau in creneaux_professeur:
        debut_dt = datetime.combine(datetime.today(), creneau.heure_debut)
        fin_dt = datetime.combine(datetime.today(), creneau.heure_fin)
        duree_heures = (fin_dt - debut_dt).total_seconds() / 3600
        total_heures += duree_heures
    
    nombre_classes = affectations.count()
    nombre_creneaux = creneaux_professeur.count()
    
    context = {
        'professeur': professeur,
        'jours_semaine': jours_semaine,
        'grille_emploi': grille_emploi,
        'plages_horaires': plages_horaires,
        'cellules_masquees': cellules_masquees,
        'nombre_classes': nombre_classes,
        'nombre_creneaux': nombre_creneaux,
        'total_heures': round(total_heures, 1),
        'etablissement': professeur.etablissement,
        'emploi_publie': emploi_publie_disponible,
        'emploi_non_publie': (not emploi_publie_disponible) and emplois_actifs.exists(),
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    from ..utils.session_utils import get_session_active
    from ..model.inscription_eleve_model import InscriptionEleve
    etablissement = professeur.etablissement if hasattr(professeur, 'etablissement') else None
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Récupérer la matière depuis les paramètres GET
    matiere_id = request.GET.get('matiere', None)
    matiere = None
    if matiere_id:
        matiere = get_object_or_404(Matiere, id=matiere_id)
    
    # Vérifier que le professeur enseigne cette matière à cette classe (filtré par année scolaire active)
    affectation_queryset = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        matiere=matiere,
        actif=True
    )
    if annee_scolaire_active:
        affectation_queryset = affectation_queryset.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_queryset.first()
    
    if not affectation:
        messages.error(request, "Vous n'enseignez pas cette matière à cette classe.")
        return redirect('enseignant:gestion_presence')
    
    # Déterminer la semaine à afficher (semaine en cours par défaut)
    today = date.today()
    
    # Calculer le lundi de la semaine en cours
    lundi = today - timedelta(days=today.weekday())
    samedi = lundi + timedelta(days=5)
    
    # Récupérer les élèves (filtrés par année scolaire active)
    eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    
    # Récupérer les présences de la semaine pour tous les élèves (filtrées par année scolaire active)
    # IMPORTANT : Si professeur principal → voir TOUTES les présences, sinon uniquement les siennes
    # IMPORTANT : Filtrer par matière
    if affectation.is_principal:
        # Professeur principal : voir TOUTES les présences de la classe (toutes matières)
        presences_semaine_queryset = Presence.objects.filter(
            classe=classe,
            date__gte=lundi,
            date__lte=samedi
        )
        if annee_scolaire_active:
            presences_semaine_queryset = presences_semaine_queryset.filter(annee_scolaire=annee_scolaire_active)
        presences_semaine = presences_semaine_queryset.select_related('eleve')
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
        
        presences_semaine_queryset = Presence.objects.filter(**filters_impression)
        if annee_scolaire_active:
            presences_semaine_queryset = presences_semaine_queryset.filter(annee_scolaire=annee_scolaire_active)
        presences_semaine = presences_semaine_queryset.select_related('eleve')
    
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
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/imprimer_tableau_presence.html', context)


def notifications_enseignant(request):
    """Affiche les notifications reçues par l'enseignant."""
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    from django.utils import timezone
    import logging

    logger = logging.getLogger(__name__)

    enseignant = request.user

    # Base query pour toutes les notifications de l'enseignant (SANS FILTRE de lecture)
    notifications_query = NotificationEnseignant.objects.filter(enseignant=enseignant)
    
    # Récupérer TOUTES les notifications non lues pour les marquer comme lues
    notifications_non_lues = notifications_query.filter(lu=False)
    notification_ids_non_lues = list(notifications_non_lues.values_list('id', flat=True))
    
    # Marquer TOUTES les notifications non lues comme lues quand on visite la page
    if notification_ids_non_lues:
        NotificationEnseignant.objects.filter(id__in=notification_ids_non_lues).update(
            lu=True,
            statut='lu',
            date_lecture=timezone.now(),
            date_modification=timezone.now(),
        )
    
    # Récupérer TOUTES les notifications pour l'affichage (de la plus récente à la plus ancienne)
    # AUCUN FILTRE - Afficher toutes les notifications, lues ou non lues
    notifications = list(notifications_query.order_by('-date_creation'))
    
    # Compter les notifications non lues restantes (après marquage)
    notifications_non_lues_count = notifications_query.filter(lu=False).count()
    
    # Log pour débogage
    logger.info(
        f"Notifications pour enseignant {enseignant.id} ({enseignant.nom_complet}): "
        f"Total={notifications_query.count()}, "
        f"Non lues avant marquage={len(notification_ids_non_lues)}, "
        f"Non lues après marquage={notifications_non_lues_count}, "
        f"À afficher={len(notifications)}"
    )

    context = {
        'professeur': enseignant,
        'notifications': notifications,
        'notifications_enseignant_non_lues': notifications_non_lues_count,
    }

    return render(
        request,
        'school_admin/enseignant/notifications_enseignant.html',
        context,
    )


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