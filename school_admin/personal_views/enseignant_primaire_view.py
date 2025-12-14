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
from django.db.utils import ProgrammingError, OperationalError
from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
import logging
import json
from collections import defaultdict, OrderedDict
from urllib.parse import urlencode
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.dateparse import parse_date
from django.utils.dateparse import parse_date

from ..model.professeur_model import Professeur
from ..model.classe_model import Classe
from ..model.eleve_model import Eleve
from ..model.matiere_model import Matiere
from ..model.periode_model import PeriodeScolaire
from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from ..model.evaluation_primaire_model import EvaluationPrimaire
from ..model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire
from ..model.exercice_maison_model import ExerciceMaison
from ..model.justification_note_model import JustificationNote
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
from ..utils.session_utils import get_session_active
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

MOTIFS_JUSTIFICATION_PRIMAIRE = OrderedDict([
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
    # Récupérer les affectations primaires du professeur
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.select_related('classe').prefetch_related('matieres')
    classe_ids = [aff.classe_id for aff in affectations]
    
    total_classes = affectations.count()
    
    # Compter le nombre total d'élèves via InscriptionEleve
    if annee_scolaire_active:
        classe_ids = [aff.classe_id for aff in affectations]
        total_eleves = InscriptionEleve.objects.filter(
            classe_id__in=classe_ids,
            annee_scolaire=annee_scolaire_active
        ).count()
    else:
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
    
    evaluations_a_venir_qs = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        date_evaluation__gte=date_debut,
        date_evaluation__lte=date_fin,
        actif=True
    )
    if annee_scolaire_active:
        evaluations_a_venir_qs = evaluations_a_venir_qs.filter(annee_scolaire=annee_scolaire_active)
    evaluations_a_venir = evaluations_a_venir_qs.count()
    
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
        if annee_scolaire_active:
            creneaux_classe = creneaux_classe.filter(emploi_du_temps__annee_scolaire_fk=annee_scolaire_active)
        
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
    if annee_scolaire_active:
        emplois_actifs = emplois_actifs.filter(annee_scolaire_fk=annee_scolaire_active)
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
    prochaines_evaluations_qs = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        date_evaluation__gte=date_debut,
        actif=True
    )
    if annee_scolaire_active:
        prochaines_evaluations_qs = prochaines_evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
    prochaines_evaluations = prochaines_evaluations_qs.select_related('classe', 'matiere', 'periode_scolaire').order_by('date_evaluation')[:5]
    
    # Compter les annonces destinées aux enseignants
    from ..model.annonce_model import Annonce
    from django.db.models import Q
    
    annonces_qs = Annonce.objects.filter(
        Q(etablissement=professeur.etablissement) &
        Q(statut='publiee') &
        Q(actif=True) &
        (Q(destinataires__contains=['tous']) | 
         Q(destinataires__contains=['enseignants']))
    )
    if annee_scolaire_active:
        annonces_qs = annonces_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_annonces = annonces_qs.count()
    
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
    # Récupérer les affectations
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.select_related('classe').prefetch_related('matieres')
    
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
        evaluations_qs = EvaluationPrimaire.objects.filter(
            professeur=professeur,
            classe=affectation.classe,
            actif=True
        )
        if annee_scolaire_active:
            evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
        nombre_evaluations = evaluations_qs.count()
        
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
    # Calculer le nombre total d'élèves via InscriptionEleve
    if annee_scolaire_active:
        classe_ids = [aff.classe_id for aff in affectations]
        total_eleves = InscriptionEleve.objects.filter(
            classe_id__in=classe_ids,
            annee_scolaire=annee_scolaire_active
        ).count()
    else:
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
    # Récupérer toutes les classes du professeur
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.select_related('classe')
    
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
        
        # Récupérer les élèves de cette classe avec statistiques via InscriptionEleve
        if annee_scolaire_active:
            eleves_classe = Eleve.objects.filter(
                classe=classe,
                actif=True,
                id__in=InscriptionEleve.objects.filter(
                    classe=classe,
                    annee_scolaire=annee_scolaire_active
                ).values_list('eleve_id', flat=True)
            ).select_related('classe').order_by('nom', 'prenom')
        else:
            eleves_classe = Eleve.objects.filter(
                classe=classe,
                actif=True
            ).select_related('classe').order_by('nom', 'prenom')
        
        # Calculer les statistiques pour chaque élève
        eleves_data = []
        for eleve in eleves_classe:
            # Compter les absences (30 derniers jours)
            date_limite = datetime.now().date() - timedelta(days=30)
            presence_qs = Presence.objects.filter(
                eleve=eleve,
                statut='absent',
                date__gte=date_limite
            )
            if annee_scolaire_active:
                presence_qs = presence_qs.filter(annee_scolaire=annee_scolaire_active)
            nombre_absences = presence_qs.count()
            
            # Compter les sanctions
            sanction_qs = Sanction.objects.filter(eleve=eleve)
            if annee_scolaire_active:
                sanction_qs = sanction_qs.filter(annee_scolaire=annee_scolaire_active)
            nombre_sanctions = sanction_qs.count()
            
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
    eleves_par_categorie_ordered = {}
    for categorie in ordre_classes:
        if categorie in eleves_par_categorie:
            eleves_par_categorie_ordered[categorie] = eleves_par_categorie[categorie]
    # Ajouter les autres catégories (ex: noms personnalisés, niveau "primaire", etc.)
    for categorie, data in eleves_par_categorie.items():
        if categorie not in eleves_par_categorie_ordered:
            eleves_par_categorie_ordered[categorie] = data
    
    # Statistiques globales
    total_classes = len(classes)
    # Calculer le nombre total d'élèves via InscriptionEleve
    if annee_scolaire_active:
        classe_ids = [aff.classe_id for aff in affectations]
        total_eleves = InscriptionEleve.objects.filter(
            classe_id__in=classe_ids,
            annee_scolaire=annee_scolaire_active
        ).count()
    else:
        total_eleves = sum(aff.classe.nombre_eleves for aff in affectations)
    
    context = {
        'professeur': professeur,
        'eleves_par_categorie': eleves_par_categorie_ordered,
        'total_classes': total_classes,
        'total_eleves': total_eleves,
        'today': datetime.now().date(),
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
    # Récupérer les paramètres de navigation
    classe_id = request.GET.get('classe')
    matiere_id = request.GET.get('matiere')
    periode_id = request.GET.get('periode')
    
    # Récupérer toutes les périodes
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')
    
    # Période active par défaut
    if periode_id:
        periode_selectionnee = get_object_or_404(PeriodeScolaire, id=periode_id)
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Récupérer les affectations et grouper les classes par type
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.select_related('classe').prefetch_related('matieres')
    
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
    classes_grouped_ordered = {}
    for categorie in ordre_classes:
        if categorie in classes_grouped:
            classes_grouped_ordered[categorie] = classes_grouped[categorie]
    # Ajouter les autres catégories (ex: noms personnalisés, niveau "primaire", etc.)
    for categorie, data in classes_grouped.items():
        if categorie not in classes_grouped_ordered:
            classes_grouped_ordered[categorie] = data
    
    # Si une classe est sélectionnée, préparer les données des matières
    matieres_data = []
    classe_selectionnee = None
    affectation_selectionnee = None
    
    if classe_id:
        classe_selectionnee = get_object_or_404(Classe, id=classe_id)
        affectation_selectionnee_qs = AffectationProfesseurPrimaire.objects.filter(
            professeur=professeur,
            classe=classe_selectionnee,
            actif=True
        )
        if annee_scolaire_active:
            affectation_selectionnee_qs = affectation_selectionnee_qs.filter(annee_scolaire=annee_scolaire_active)
        affectation_selectionnee = affectation_selectionnee_qs.prefetch_related('matieres').first()
        
        if affectation_selectionnee:
            from ..model.session_examen_model import SessionExamen
            
            for matiere in affectation_selectionnee.matieres.all():
                # Compter les évaluations normales pour cette matière
                evaluations_qs = EvaluationPrimaire.objects.filter(
                    professeur=professeur,
                    classe=classe_selectionnee,
                    matiere=matiere,
                    periode_scolaire=periode_selectionnee,
                    actif=True
                )
                if annee_scolaire_active:
                    evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
                nb_evaluations = evaluations_qs.count()
                
                # Compter aussi les sessions d'examens (pas les créneaux)
                examens_qs = SessionExamen.objects.filter(
                    classes=classe_selectionnee,
                    periode=periode_selectionnee,
                    matieres=matiere,
                    actif=True
                )
                if annee_scolaire_active:
                    examens_qs = examens_qs.filter(annee_scolaire=annee_scolaire_active)
                nb_examens = examens_qs.distinct().count()
                
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
        evaluations_qs = EvaluationPrimaire.objects.filter(
            classe=classe_selectionnee,
            professeur=professeur,
            matiere=matiere_selectionnee,
            periode_scolaire=periode_selectionnee,
            actif=True
        )
        if annee_scolaire_active:
            evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
        evaluations_list = list(evaluations_qs.order_by('date_evaluation'))
        
        # Récupérer les sessions d'examens pour cette matière et période (PAS les créneaux!)
        from ..model.session_examen_model import SessionExamen
        
        sessions_examens_qs = SessionExamen.objects.filter(
            classes=classe_selectionnee,
            periode=periode_selectionnee,
            matieres=matiere_selectionnee,
            actif=True
        )
        if annee_scolaire_active:
            sessions_examens_qs = sessions_examens_qs.filter(annee_scolaire=annee_scolaire_active)
        sessions_examens_list = list(sessions_examens_qs.distinct().order_by('date_debut'))
        
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
        
        # Récupérer tous les élèves de la classe via InscriptionEleve
        if annee_scolaire_active:
            eleves = Eleve.objects.filter(
                classe=classe_selectionnee,
                actif=True,
                id__in=InscriptionEleve.objects.filter(
                    classe=classe_selectionnee,
                    annee_scolaire=annee_scolaire_active
                ).values_list('eleve_id', flat=True)
            ).order_by('nom', 'prenom')
        else:
            eleves = Eleve.objects.filter(
                classe=classe_selectionnee,
                actif=True
            ).order_by('nom', 'prenom')
        
        for eleve in eleves:
            # Récupérer la moyenne ENREGISTRÉE (pas calculée)
            moyenne_qs = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                matiere=matiere_selectionnee,
                periode_scolaire=periode_selectionnee
            )
            if annee_scolaire_active:
                moyenne_qs = moyenne_qs.filter(annee_scolaire=annee_scolaire_active)
            moyenne_obj = moyenne_qs.first()
            
            moyenne = moyenne_obj.moyenne if moyenne_obj and moyenne_obj.moyenne is not None else None
            appreciation = moyenne_obj.appreciation if moyenne_obj else None
            
            # Récupérer les notes pour chaque évaluation (normales + examens)
            from ..model.note_examen_model import NoteExamen
            
            notes_evaluations = {}
            for eval_dict in evaluations_matiere:
                # Si c'est un examen, chercher dans NoteExamen (basé sur session)
                if eval_dict.get('est_examen'):
                    note_examen_qs = NoteExamen.objects.filter(
                        eleve=eleve,
                        session_examen_id=eval_dict['session_id'],
                        matiere=matiere_selectionnee
                    )
                    if annee_scolaire_active:
                        note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                    note_obj = note_examen_qs.first()
                else:
                    # Sinon, chercher dans NotePrimaire
                    note_primaire_qs = NotePrimaire.objects.filter(
                        eleve=eleve,
                        evaluation_primaire_id=eval_dict['id']
                    )
                    if annee_scolaire_active:
                        note_primaire_qs = note_primaire_qs.filter(annee_scolaire=annee_scolaire_active)
                    note_obj = note_primaire_qs.first()
                
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
    # Calculer le nombre total d'élèves via InscriptionEleve
    if annee_scolaire_active:
        classe_ids = [aff.classe_id for aff in affectations]
        total_eleves = InscriptionEleve.objects.filter(
            classe_id__in=classe_ids,
            annee_scolaire=annee_scolaire_active
        ).count()
    else:
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
        releve_qs = MoyenneMatierePrimaire.objects.filter(
            classe=classe_selectionnee,
            periode_scolaire=periode_selectionnee,
            matiere__in=affectation_selectionnee.matieres.all(),  # Filtrer par matières du professeur
            soumis=True
        )
        if annee_scolaire_active:
            releve_qs = releve_qs.filter(annee_scolaire=annee_scolaire_active)
        releve_deja_soumis = releve_qs.exists()
    
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
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/primaire/gestion_notes_primaire.html', context)


def justifications_notes_primaire(request):
    """
    Page permettant aux enseignants du primaire de soumettre des justifications de notes.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    professeur = request.user

    if professeur.niveau_enseignement != 'primaire':
        messages.warning(request, "Cette section est réservée aux enseignants du primaire.")
        from django.urls import reverse
        return redirect(reverse('enseignant:justifications_notes'))

    if not professeur.etablissement:
        messages.error(request, "Votre profil n'est pas rattaché à un établissement.")
        return redirect('enseignant_primaire:gestion_notes')
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")

    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from ..model.evaluation_primaire_model import EvaluationPrimaire
    from ..model.note_primaire_model import NotePrimaire
    from ..model.periode_model import PeriodeScolaire
    import re

    # Fonction helper pour les redirections
    def _redirect_with_params():
        from django.urls import reverse
        redirect_url = reverse('enseignant_primaire:justifications_notes')
        params = []
        periode_id_param = request.POST.get('periode') or request.GET.get('periode')
        if periode_id_param:
            params.append(f"periode={periode_id_param}")
        classe_id_param = request.POST.get('classe') or request.GET.get('classe')
        if classe_id_param:
            params.append(f"classe={classe_id_param}")
        matiere_id_param = request.POST.get('matiere') or request.GET.get('matiere')
        if matiere_id_param:
            params.append(f"matiere={matiere_id_param}")
        if params:
            redirect_url = f"{redirect_url}?{'&'.join(params)}"
        return redirect(redirect_url)

    # Traitement du formulaire de justification
    if request.method == 'POST':
        note_id = request.POST.get('note_id')
        note_type = request.POST.get('note_type', 'evaluation')  # 'evaluation' ou 'examen'
        nouvelle_note_raw = request.POST.get('nouvelle_note')
        motif_code = request.POST.get('motif')
        description = (request.POST.get('description') or '').strip()

        if not note_id:
            messages.error(request, "Veuillez sélectionner la note à justifier.")
            return _redirect_with_params()

        note = None
        note_primaire = None
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
                return _redirect_with_params()
        else:
            try:
                note_primaire = NotePrimaire.objects.select_related(
                    'evaluation_primaire',
                    'evaluation_primaire__classe',
                    'evaluation_primaire__matiere',
                    'eleve',
                ).get(id=note_id, evaluation_primaire__professeur=professeur)
            except NotePrimaire.DoesNotExist:
                messages.error(request, "Impossible de trouver la note sélectionnée.")
                return _redirect_with_params()

        if not motif_code or motif_code not in MOTIFS_JUSTIFICATION_PRIMAIRE:
            messages.error(request, "Veuillez sélectionner un motif de justification valide.")
            return _redirect_with_params()
        motif = MOTIFS_JUSTIFICATION_PRIMAIRE[motif_code]

        try:
            nouvelle_note = Decimal(str(nouvelle_note_raw).replace(',', '.'))
        except (InvalidOperation, TypeError):
            messages.error(request, "La nouvelle note proposée est invalide.")
            return _redirect_with_params()

        if nouvelle_note < 0:
            messages.error(request, "La note proposée ne peut pas être négative.")
            return _redirect_with_params()

        bareme = None
        if note_primaire:
            bareme = note_primaire.evaluation_primaire.bareme if note_primaire.evaluation_primaire else None
        elif note_examen:
            bareme = note_examen.bareme
        
        if bareme is not None and nouvelle_note > bareme:
            messages.error(
                request,
                f"La note proposée ne peut pas dépasser le barème ({bareme})."
            )
            return _redirect_with_params()

        justification_obj = None

        with transaction.atomic():
            if note_primaire:
                justification = JustificationNote.objects.filter(
                    note_primaire=note_primaire,
                    statut=JustificationNote.STATUT_EN_ATTENTE
                ).first()
                ancienne_note_val = note_primaire.note
                classe_obj = note_primaire.evaluation_primaire.classe
                matiere_obj = note_primaire.evaluation_primaire.matiere
                eleve_obj = note_primaire.eleve
                evaluation_primaire_obj = note_primaire.evaluation_primaire
            else:
                justification = JustificationNote.objects.filter(
                    note_examen=note_examen,
                    statut=JustificationNote.STATUT_EN_ATTENTE
                ).first()
                ancienne_note_val = note_examen.note
                classe_obj = note_examen.classe
                matiere_obj = note_examen.matiere
                eleve_obj = note_examen.eleve
                evaluation_primaire_obj = None

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
                if note_primaire:
                    justification.note_primaire = note_primaire
                    justification.evaluation_primaire = evaluation_primaire_obj
                    justification.note_examen = None
                else:
                    justification.note_examen = note_examen
                    justification.note_primaire = None
                    justification.evaluation_primaire = None
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
                if note_primaire:
                    creation_kwargs['note_primaire'] = note_primaire
                    creation_kwargs['evaluation_primaire'] = evaluation_primaire_obj
                else:
                    creation_kwargs['note_examen'] = note_examen
                
                justification_obj = JustificationNote.objects.create(**creation_kwargs)
                messages.success(request, "Votre demande de justification a été envoyée à la direction.")

        if justification_obj:
            from ..services.notification_tasks import schedule_justification_note_directeur_notification
            schedule_justification_note_directeur_notification(justification_obj.id)

        # Rediriger en gardant les paramètres periode, classe et matiere
        return _redirect_with_params()

    # Préparation des données d'affichage
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')

    periode_id = request.GET.get('periode')
    periode_selectionnee = None
    if periodes.exists():
        if periode_id:
            periode_selectionnee = periodes.filter(id=periode_id).first()
        if not periode_selectionnee:
            periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()

    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.select_related('classe').prefetch_related('matieres')

    if not affectations.exists():
        messages.info(request, "Aucune classe affectée. Contactez l'administration.")
        return render(
            request,
            'school_admin/enseignant/primaire/justifications_notes_primaire.html',
            {
                'professeur': professeur,
                'periodes': periodes,
                'periode_selectionnee': periode_selectionnee,
                'classes_grouped': OrderedDict(),
                'stats': {'total_classes': 0, 'total_eleves': 0},
                'notes_json': json.dumps({}),
                'motifs_justification': MOTIFS_JUSTIFICATION_PRIMAIRE,
            }
        )

    # Récupérer les paramètres de sélection
    classe_id = request.GET.get('classe')
    matiere_id = request.GET.get('matiere')
    
    classe_selectionnee = None
    matiere_selectionnee = None
    if classe_id:
        try:
            classe_selectionnee = Classe.objects.get(id=classe_id)
        except Classe.DoesNotExist:
            pass
    if matiere_id:
        try:
            matiere_selectionnee = Matiere.objects.get(id=matiere_id)
        except Matiere.DoesNotExist:
            pass

    # Regrouper les classes par catégorie
    classes_grouped = {}
    classes_vues = set()
    total_eleves = 0
    notes_payload = {}

    for affectation in affectations:
        classe = affectation.classe
        match = re.match(r'^(CI|CP|CE1|CE2|CM1|CM2)', classe.nom or "")
        if match:
            categorie = match.group(1)
        else:
            categorie = classe.niveau or "Autres"

        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0,
            }

        # Récupérer les élèves via InscriptionEleve
        eleves_classe = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
        nombre_eleves = eleves_classe.count()
        
        # Vérifier si cette classe a déjà été ajoutée
        classe_existante = None
        for classe_data in classes_grouped[categorie]['classes']:
            if classe_data['classe'].id == classe.id:
                classe_existante = classe_data
                break
        
        if not classe_existante:
            if classe.id not in classes_vues:
                classes_vues.add(classe.id)
                classes_grouped[categorie]['total_eleves'] += nombre_eleves
                total_eleves += nombre_eleves
            
            matieres_affectation = list(affectation.matieres.all().order_by('nom'))
            
            # Préparer les données des matières pour cette classe
            matieres_data = []
            for matiere in matieres_affectation:
                evaluations_qs = EvaluationPrimaire.objects.filter(
                    professeur=professeur,
                    classe=classe,
                    matiere=matiere,
                    actif=True
                )
                if annee_scolaire_active:
                    evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
                if periode_selectionnee:
                    evaluations_qs = evaluations_qs.filter(periode_scolaire=periode_selectionnee)
                evaluations_qs = evaluations_qs.order_by('date_evaluation')
                
                nb_evaluations = evaluations_qs.count()
                matieres_data.append({
                    'matiere': matiere,
                    'nombre_evaluations': nb_evaluations,
                })
            
            classes_grouped[categorie]['classes'].append({
                'classe': classe,
                'matieres': matieres_data,
                'nombre_eleves': nombre_eleves,
                'est_principal': getattr(affectation, 'is_principal', False),
            })

    # Si une classe et une matière sont sélectionnées, préparer les données du tableau
    releve_data = []
    evaluations_matiere = []
    
    if classe_selectionnee and matiere_selectionnee:
        # Vérifier que le professeur est bien affecté à cette classe et matière
        affectation_selectionnee_qs = AffectationProfesseurPrimaire.objects.filter(
            professeur=professeur,
            classe=classe_selectionnee,
            matieres=matiere_selectionnee,
            actif=True
        )
        if annee_scolaire_active:
            affectation_selectionnee_qs = affectation_selectionnee_qs.filter(annee_scolaire=annee_scolaire_active)
        affectation_selectionnee = affectation_selectionnee_qs.first()
        
        if affectation_selectionnee:
            # Récupérer toutes les évaluations pour cette matière et période
            evaluations_qs = EvaluationPrimaire.objects.filter(
                professeur=professeur,
                classe=classe_selectionnee,
                matiere=matiere_selectionnee,
                actif=True
            )
            if annee_scolaire_active:
                evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
            if periode_selectionnee:
                evaluations_qs = evaluations_qs.filter(periode_scolaire=periode_selectionnee)
            evaluations_qs = evaluations_qs.order_by('date_evaluation')
            
            evaluations_liste = list(evaluations_qs)
            
            # Ajouter des numéros distincts pour devoirs et interrogations
            compteur_devoirs = 0
            compteur_interrogations = 0
            
            for eval in evaluations_liste:
                eval_dict = {
                    'obj': eval,
                    'id': eval.id,
                    'titre': eval.titre,
                    'bareme': eval.bareme,
                    'date_evaluation': eval.date_evaluation,
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
            
            # Récupérer tous les élèves de la classe via InscriptionEleve
            if annee_scolaire_active:
                eleves = Eleve.objects.filter(
                    classe=classe_selectionnee,
                    actif=True,
                    id__in=InscriptionEleve.objects.filter(
                        classe=classe_selectionnee,
                        annee_scolaire=annee_scolaire_active
                    ).values_list('eleve_id', flat=True)
                ).order_by('nom', 'prenom')
            else:
                eleves = Eleve.objects.filter(
                    classe=classe_selectionnee,
                    actif=True
                ).order_by('nom', 'prenom')
            
            # Récupérer les notes d'examen pour cette classe et matière
            from ..model.note_examen_model import NoteExamen
            from ..model.session_examen_model import SessionExamen
            notes_examen_query = NoteExamen.objects.filter(
                classe=classe_selectionnee,
                professeur=professeur,
                matiere=matiere_selectionnee,
                actif=True
            )
            if annee_scolaire_active:
                notes_examen_query = notes_examen_query.filter(annee_scolaire=annee_scolaire_active)
            if periode_selectionnee:
                # Filtrer par période via la session d'examen
                session_ids = SessionExamen.objects.filter(
                    periode=periode_selectionnee,
                    actif=True
                ).values_list('id', flat=True)
                notes_examen_query = notes_examen_query.filter(session_examen_id__in=session_ids)
            notes_examen_query = notes_examen_query.select_related(
                'session_examen',
                'creneau_examen',
                'matiere',
                'eleve'
            ).prefetch_related('justifications').order_by('eleve__nom', 'session_examen__date_debut')

            for eleve in eleves:
                notes_evaluations = {}
                derniere_justification_globale = None
                
                for eval_dict in evaluations_matiere:
                    note_primaire_qs = NotePrimaire.objects.filter(
                        eleve=eleve,
                        evaluation_primaire_id=eval_dict['id']
                    )
                    if annee_scolaire_active:
                        note_primaire_qs = note_primaire_qs.filter(annee_scolaire=annee_scolaire_active)
                    note_obj = note_primaire_qs.select_related('evaluation_primaire').prefetch_related('justifications').first()
                    
                    if note_obj:
                        justifications = sorted(
                            list(note_obj.justifications.all()),
                            key=lambda j: j.date_creation,
                            reverse=True
                        )
                        derniere_justification = justifications[0] if justifications else None
                        
                        if derniere_justification:
                            if (
                                derniere_justification_globale is None
                                or derniere_justification.date_creation > derniere_justification_globale.date_creation
                            ):
                                derniere_justification_globale = derniere_justification
                        
                        # Ajouter à notes_payload pour le JavaScript
                        payload = notes_payload.setdefault(str(eleve.id), [])
                        label = f"{eval_dict['titre']} ({note_obj.note}/{eval_dict['bareme']}) - {date_format(eval_dict['date_evaluation'], 'd/m/Y')}"
                        payload.append({
                            'id': note_obj.id,
                            'note_type': 'evaluation',
                            'evaluation_id': eval_dict['id'],
                            'classe_id': str(classe_selectionnee.id),
                            'matiere_id': str(matiere_selectionnee.id),
                            'label': label,
                            'bareme': str(eval_dict['bareme']),
                            'valeur': str(note_obj.note) if note_obj.note is not None else "",
                            'statut': derniere_justification.statut if derniere_justification else "",
                        })
                        
                        notes_evaluations[eval_dict['id']] = {
                            'note_obj': note_obj,
                            'justification': derniere_justification,
                        }
                    else:
                        notes_evaluations[eval_dict['id']] = {
                            'note_obj': None,
                            'justification': None,
                        }
                
                # Ajouter les notes d'examen pour cet élève
                notes_examen_eleve = notes_examen_query.filter(eleve=eleve)
                for note_examen_obj in notes_examen_eleve:
                    justifications = sorted(
                        list(note_examen_obj.justifications.all()),
                        key=lambda j: j.date_creation,
                        reverse=True
                    )
                    derniere_justification = justifications[0] if justifications else None
                    
                    if derniere_justification:
                        if (
                            derniere_justification_globale is None
                            or derniere_justification.date_creation > derniere_justification_globale.date_creation
                        ):
                            derniere_justification_globale = derniere_justification
                    
                    # Ajouter à notes_payload pour le JavaScript
                    payload = notes_payload.setdefault(str(eleve.id), [])
                    session_examen = note_examen_obj.session_examen
                    creneau = note_examen_obj.creneau_examen
                    session_label = session_examen.nom if session_examen else "Examen"
                    if creneau:
                        session_label += f" - {creneau.nom}"
                    label = f"Examen: {session_label} ({note_examen_obj.note if note_examen_obj.note is not None else 'N/A'}/{note_examen_obj.bareme})"
                    if session_examen and session_examen.date_debut:
                        label += f" - {date_format(session_examen.date_debut, 'd/m/Y')}"
                    payload.append({
                        'id': note_examen_obj.id,
                        'note_type': 'examen',
                        'evaluation_id': None,
                        'classe_id': str(classe_selectionnee.id),
                        'matiere_id': str(matiere_selectionnee.id),
                        'label': label,
                        'bareme': str(note_examen_obj.bareme),
                        'valeur': str(note_examen_obj.note) if note_examen_obj.note is not None else "",
                        'statut': derniere_justification.statut if derniere_justification else "",
                    })
                
                releve_data.append({
                    'eleve': eleve,
                    'notes_evaluations': notes_evaluations,
                    'derniere_justification': derniere_justification_globale,
                })

    ordre_categories = ['CI', 'CP', 'CE1', 'CE2', 'CM1', 'CM2']
    ordered_categories = [cat for cat in ordre_categories if cat in classes_grouped]
    ordered_categories += [cat for cat in classes_grouped.keys() if cat not in ordered_categories]

    classes_grouped_ordered = OrderedDict()
    for categorie in ordered_categories:
        classes_grouped_ordered[categorie] = classes_grouped[categorie]

    stats = {
        'total_classes': len(classes_vues),
        'total_eleves': total_eleves,
    }

    notes_json = json.dumps(notes_payload, ensure_ascii=False)

    context = {
        'professeur': professeur,
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'classes_grouped': classes_grouped_ordered,
        'classe_selectionnee': classe_selectionnee,
        'matiere_selectionnee': matiere_selectionnee,
        'releve_data': releve_data,
        'evaluations_matiere': evaluations_matiere,
        'stats': stats,
        'notes_json': notes_json,
        'motifs_justification': MOTIFS_JUSTIFICATION_PRIMAIRE,
        'annee_scolaire_active': annee_scolaire_active,
    }

    return render(request, 'school_admin/enseignant/primaire/justifications_notes_primaire.html', context)


def exercices_maison_primaire(request):
    """
    Consultation et programmation des exercices de maison pour les enseignants du primaire.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    professeur = request.user

    if professeur.niveau_enseignement != 'primaire':
        messages.warning(
            request,
            "Cette section est réservée aux enseignants du primaire.",
        )
        return redirect('enseignant:dashboard_enseignant')
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")

    # Récupération des périodes scolaires actives de l'établissement
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')

    periode_id = request.GET.get('periode')
    if periode_id:
        try:
            periode_selectionnee = periodes.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            messages.error(request, "Période scolaire invalide.")
            return redirect(request.path)
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()

    # Récupération des affectations primaires
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.select_related('classe').prefetch_related('matieres')

    if not affectations.exists():
        messages.info(request, "Aucune classe affectée. Contactez la direction.")
        return render(
            request,
            'school_admin/enseignant/primaire/exercices_maison_primaire.html',
            {
                'professeur': professeur,
                'periodes': periodes,
                'periode_selectionnee': periode_selectionnee,
                'classes_grouped': {},
                'classes_categories': [],
                'classe_selectionnee': None,
                'matiere_selectionnee': None,
                'matieres_disponibles': [],
                'exercices': [],
                'aujourdhui': date.today(),
            }
        )

    classe_ids = [aff.classe_id for aff in affectations]
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
            "Table ExerciceMaison indisponible (primaire) : %s",
            exc,
        )

    import re
    classes_grouped = {}
    for affectation in affectations:
        classe = affectation.classe
        matieres = list(affectation.matieres.all().order_by('nom'))
        match = re.match(r'^(CI|CP|CE1|CE2|CM1|CM2)', classe.nom)
        if match:
            categorie = match.group(1)
        else:
            categorie = classe.niveau or "Autre"

        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': []
            }

        classes_grouped[categorie]['classes'].append({
            'classe': classe,
            'matieres': matieres,
            'exercices_count': exercices_counts.get(classe.id, 0),
        })

    ordre_classes = ['CI', 'CP', 'CE1', 'CE2', 'CM1', 'CM2']
    classes_categories = [cat for cat in ordre_classes if cat in classes_grouped]
    classes_categories += [cat for cat in classes_grouped.keys() if cat not in classes_categories]
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
    classe_selectionnee = None
    affectation_selectionnee = None
    if classe_id:
        try:
            classe_selectionnee = next(
                aff.classe for aff in affectations if str(aff.classe_id) == classe_id
            )
            affectation_selectionnee = next(
                aff for aff in affectations if aff.classe_id == classe_selectionnee.id
            )
        except StopIteration:
            messages.error(request, "Classe sélectionnée invalide.")
            return redirect(request.path)
    else:
        affectation_selectionnee = affectations.first()
        classe_selectionnee = affectation_selectionnee.classe

    matieres_disponibles = list(affectation_selectionnee.matieres.all().order_by('nom')) if affectation_selectionnee else []

    matiere_id = request.GET.get('matiere')
    matiere_selectionnee = None
    if matiere_id and affectation_selectionnee:
        matiere_selectionnee = next(
            (m for m in matieres_disponibles if str(m.id) == matiere_id),
            None
        )
        if matiere_selectionnee is None:
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
            classe_obj = next(
                aff.classe for aff in affectations if str(aff.classe_id) == classe_post
            )
            affectation_post = next(
                aff for aff in affectations if aff.classe_id == classe_obj.id
            )
        except StopIteration:
            messages.error(request, "Classe invalide.")
            return redirect(request.get_full_path())

        matiere_obj = next(
            (m for m in affectation_post.matieres.all() if str(m.id) == matiere_post),
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
                "Erreur lors de l'enregistrement d'un exercice de maison (primaire): %s",
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
            exercices_qs = exercices_qs.select_related('classe', 'matiere', 'periode_scolaire', 'professeur')
            exercices = list(exercices_qs.order_by('-date_rendu', '-date_creation'))
        except (ProgrammingError, OperationalError) as exc:
            exercices = []
            logger.warning(
                "Impossible de récupérer les exercices (primaire) : %s",
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

    return render(request, 'school_admin/enseignant/primaire/exercices_maison_primaire.html', context)


def creer_evaluation_primaire(request, classe_id):
    """
    Créer une évaluation pour une matière spécifique.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id)
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Vérifier que le professeur enseigne dans cette classe
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    try:
        affectation = affectation_qs.get()
    except AffectationProfesseurPrimaire.DoesNotExist:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Récupérer les matières enseignées par le professeur dans cette classe
    matieres = affectation.matieres.all()
    
    # Récupérer les périodes
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                titre = request.POST.get('titre')
                description = request.POST.get('description', '')
                matiere_id = request.POST.get('matiere')
                date_evaluation = request.POST.get('date_evaluation')
                bareme = request.POST.get('bareme', 20)
                periode_id = request.POST.get('periode')
                
                # Validation
                if not all([titre, matiere_id, date_evaluation, periode_id]):
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
                    matiere=matiere,
                    classe=classe,
                    professeur=professeur,
                    date_evaluation=date_evaluation,
                    bareme=bareme,
                    periode_scolaire=periode,
                    actif=True,
                    annee_scolaire=annee_scolaire_active,
                )
                
                # Créer automatiquement les notes pour tous les élèves via InscriptionEleve
                eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
                for eleve in eleves:
                    NotePrimaire.objects.create(
                        eleve=eleve,
                        evaluation_primaire=evaluation,
                        absent=False,
                        annee_scolaire=annee_scolaire_active,
                    )
                    
                # Programmer l'envoi des notifications en arrière-plan
                from ..services.notification_tasks import schedule_evaluation_primaire_notification
                schedule_evaluation_primaire_notification(evaluation.id)
                logger.info(f"Envoi des notifications programmé en arrière-plan pour l'évaluation primaire {evaluation.id}")
                
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
        'form_data': request.POST if request.method == 'POST' else {},
        'aujourdhui': timezone.now().date().isoformat(),
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Vérifier l'affectation
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_qs.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Récupérer toutes les périodes scolaires de l'établissement
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')
    
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
    
    # Récupérer les élèves de la classe via InscriptionEleve
    eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
    
    # Préparer les données UNIQUEMENT pour les matières qui ont des évaluations OU des examens
    matieres_data = []
    for matiere in affectation.matieres.all():
        # Récupérer toutes les évaluations normales pour cette matière et période
        evaluations_qs = EvaluationPrimaire.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=matiere,
            periode_scolaire=periode_selectionnee,
            actif=True
        )
        if annee_scolaire_active:
            evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
        evaluations = list(evaluations_qs.order_by('date_evaluation'))
        
        # Récupérer aussi les sessions d'examens pour cette matière et période
        from ..model.session_examen_model import SessionExamen
        
        # Récupérer les sessions d'examen pour cette matière (PAS les créneaux !)
        sessions_examens_qs = SessionExamen.objects.filter(
            classes=classe,
            periode=periode_selectionnee,
            matieres=matiere,
            actif=True
        )
        if annee_scolaire_active:
            sessions_examens_qs = sessions_examens_qs.filter(annee_scolaire=annee_scolaire_active)
        sessions_examens = sessions_examens_qs.distinct().order_by('date_debut')
        
        # Créer des pseudo-évaluations à partir des SESSIONS d'examens (pas des créneaux)
        evaluations_examens = []
        for session in sessions_examens:
            # Créer un objet qui simule une EvaluationPrimaire pour compatibilité
            class PseudoEvaluationExamen:
                def __init__(self, session):
                    self.id = f"examen_{session.id}"
                    self.session_id = session.id
                    self.titre = f"{session.nom_examen}"
                    self.bareme = 20  # Les examens sont généralement sur 20
                    self.date_evaluation = session.date_debut
                    self.actif = True
                    self.est_examen = True
                    self.session = session
                    
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
                note_primaire_qs = NotePrimaire.objects.filter(
                    eleve=eleve, 
                    evaluation_primaire=evaluation
                )
                if annee_scolaire_active:
                    note_primaire_qs = note_primaire_qs.filter(annee_scolaire=annee_scolaire_active)
                note_obj = note_primaire_qs.first()
                
                # Créer automatiquement la note si elle n'existe pas
                if not note_obj:
                    note_obj = NotePrimaire.objects.create(
                        eleve=eleve,
                        evaluation_primaire=evaluation,
                        absent=False,
                        annee_scolaire=annee_scolaire_active,
                    )
                
                notes_existantes[eleve.id][evaluation.id] = note_obj
            
            # Notes des examens
            for eval_examen in evaluations_examens:
                # Chercher la note d'examen basée sur (eleve, session, matiere)
                session = eval_examen.session if hasattr(eval_examen, 'session') else SessionExamen.objects.get(id=eval_examen.session_id)
                note_examen_qs = NoteExamen.objects.filter(
                    eleve=eleve,
                    session_examen=session,
                    matiere=matiere
                )
                if annee_scolaire_active:
                    note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                note_examen_obj = note_examen_qs.first()
                
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
                            'annee_scolaire': annee_scolaire_active,
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
                        self.retenue = note_examen.retenue
                        self.bareme = note_examen.bareme
                        self.note_sur_20 = note_examen.note_sur_20
                        self.session_id = note_examen.session_examen_id
                
                notes_existantes[eleve.id][eval_examen.id] = NoteExamenWrapper(note_examen_obj)
        
        # Récupérer les moyennes ENREGISTRÉES (pas les calculer automatiquement)
        moyennes = {}
        matiere_soumise = False
        for eleve in eleves:
            moyenne_qs = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                matiere=matiere,
                periode_scolaire=periode_selectionnee
            )
            if annee_scolaire_active:
                moyenne_qs = moyenne_qs.filter(annee_scolaire=annee_scolaire_active)
            moyenne_obj = moyenne_qs.first()
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
                note_examen_qs = NoteExamen.objects.filter(
                    session_examen_id=evaluation.session_id,
                    matiere=matiere,
                    retenue=True,
                    absent=False
                )
                if annee_scolaire_active:
                    note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                nb_retenues = note_examen_qs.exclude(note__isnull=True).count()
            else:
                # Pour les évaluations normales
                note_primaire_qs = NotePrimaire.objects.filter(
                    evaluation_primaire=evaluation,
                    retenue=True,
                    absent=False
                )
                if annee_scolaire_active:
                    note_primaire_qs = note_primaire_qs.filter(annee_scolaire=annee_scolaire_active)
                nb_retenues = note_primaire_qs.exclude(note__isnull=True).count()
            
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
        releve_qs = MoyenneMatierePrimaire.objects.filter(
            classe=classe,
            matiere=matiere,
            periode_scolaire=periode_selectionnee,
            soumis=True
        )
        if annee_scolaire_active:
            releve_qs = releve_qs.filter(annee_scolaire=annee_scolaire_active)
        releve_soumis = releve_qs.exists()
        
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
                    moyenne_calculee, evaluations_utilisees_effectives = calculer_moyenne_avec_mode(
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
                                'classe': classe,
                                'moyenne': moyenne_calculee,
                                'appreciation': appreciation,
                                'mode_calcul': mode_calcul,
                                'evaluations_utilisees': evaluations_utilisees_effectives or evaluations_selectionnees,
                                'ponderation': ponderation,
                                'nombre_notes': len(evaluations_utilisees_effectives or evaluations_selectionnees),
                                'annee_scolaire': annee_scolaire_active,
                            }
                        )
                        moyennes_calculees += 1
                        moyennes_dict[eleve.id] = f"{moyenne_calculee:.2f}".replace('.', ',')
                
                # Compter les notes retenues par évaluation
                for eval_id_str in evaluations_selectionnees:
                    if eval_id_str.startswith('examen_'):
                        session_id = int(eval_id_str.replace('examen_', ''))
                        from ..model.note_examen_model import NoteExamen
                        note_examen_qs = NoteExamen.objects.filter(
                            session_examen_id=session_id,
                            matiere=matiere,
                            eleve__in=eleves,
                            retenue=True
                        )
                        if annee_scolaire_active:
                            note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                        count = note_examen_qs.count()
                        notes_retenues_dict[eval_id_str] = count
                    else:
                        note_primaire_qs = NotePrimaire.objects.filter(
                            evaluation_primaire_id=int(eval_id_str),
                            eleve__in=eleves,
                            retenue=True
                        )
                        if annee_scolaire_active:
                            note_primaire_qs = note_primaire_qs.filter(annee_scolaire=annee_scolaire_active)
                        count = note_primaire_qs.count()
                        notes_retenues_dict[eval_id_str] = count
                
                # Message détaillé selon le mode et la pondération
                mode_messages = {
                    'toutes': 'toutes les notes',
                    '1_meilleure': 'la meilleure note',
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
        
        if action == 'publier':
            try:
                publication_time = timezone.now()
                notes_publiees_total = 0
                eleves_notifies = 0
                notifications_eleves = 0
                notifications_parents = 0

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

                        for evaluation in evaluations:
                            note_primaire_qs = NotePrimaire.objects.filter(
                                eleve=eleve,
                                evaluation_primaire=evaluation
                            )
                            if annee_scolaire_active:
                                note_primaire_qs = note_primaire_qs.filter(annee_scolaire=annee_scolaire_active)
                            note_obj = note_primaire_qs.first()
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
                                })

                        for session in sessions_examens:
                            note_examen_qs = NoteExamen.objects.filter(
                                eleve=eleve,
                                session_examen=session,
                                matiere=matiere
                            )
                            if annee_scolaire_active:
                                note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                            note_examen_obj = note_examen_qs.first()
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
                                    'titre': getattr(session, 'nom_examen', getattr(session, 'titre', 'Examen')),
                                    'date': getattr(session, 'date_debut', None),
                                })

                        if not notes_a_publier:
                            continue

                        eleves_notifies += 1

                        for note_info in notes_a_publier:
                            valeur = note_info['valeur']
                            bareme_note = note_info['bareme']
                            titre_note = note_info['titre']
                            valeur_affiche = format_decimal(valeur)
                            bareme_affiche = format_decimal(bareme_note)

                            details = {
                                "message": f"Tu as {valeur_affiche}/{bareme_affiche} en {matiere.nom} ({titre_note}).",
                                "note": valeur_affiche,
                                "bareme": bareme_affiche,
                                "evaluation": titre_note,
                                "type": note_info['type'],
                            }

                            try:
                                EleveNotificationService.notify_note(
                                    eleve=eleve,
                                    matiere_nom=matiere.nom,
                                    details=details,
                                    source=note_info['note_obj'],
                                )
                                notifications_eleves += 1
                            except Exception as notification_error:
                                logger.error(
                                    "Erreur lors de la notification élève pour la publication des notes: %s",
                                    notification_error,
                                    exc_info=True,
                                )

                            try:
                                ParentNotificationService.notify_note(
                                    eleve=eleve,
                                    matiere_nom=matiere.nom,
                                    note_obtenue=valeur,
                                    bareme=bareme_note,
                                    evaluation_nom=titre_note,
                                    professeur_nom=getattr(professeur, 'nom_complet', str(professeur)),
                                    date_evaluation=note_info['date'],
                                    source=note_info['note_obj'],
                                )
                                notifications_parents += 1
                            except Exception as notification_error:
                                logger.error(
                                    "Erreur lors de la notification parent pour la publication des notes: %s",
                                    notification_error,
                                    exc_info=True,
                                )

                            note_publication = note_info['note_obj']
                            note_publication.note_publiee = valeur
                            note_publication.date_publication = publication_time
                            if isinstance(note_publication, NotePrimaire):
                                note_publication.statut_publication = NotePrimaire.STATUT_PUBLIEE
                                update_fields = ['note_publiee', 'date_publication', 'statut_publication']
                            else:
                                note_publication.statut_publication = NoteExamen.STATUT_PUBLIEE
                                update_fields = ['note_publiee', 'date_publication', 'statut_publication', 'note_sur_20']
                            note_publication.save(update_fields=update_fields)
                            notes_publiees_total += 1

                if notes_publiees_total > 0:
                    messages.success(
                        request,
                        f"✓ {notes_publiees_total} note(s) publiée(s). Notifications envoyées à {eleves_notifies} élève(s).",
                    )
                else:
                    messages.info(request, "Aucune nouvelle note à publier. Toutes les notes étaient déjà visibles.")

            except Exception as e:
                logger.error(f"Erreur lors de la publication des notes: {e}")
                messages.error(request, f"Erreur lors de la publication des notes : {str(e)}")

            return redirect(f"{request.path}?periode={periode_selectionnee.id}&matiere={matiere_id}")

        if action == 'enregistrer':
            notes_enregistrees = 0
            errors = []
            notes_dict = {}
            
            try:
                with transaction.atomic():
                    for eleve in eleves:
                        for evaluation in evaluations:
                            note_value = request.POST.get(f'note_{eleve.id}_{evaluation.id}', '').strip()
                            note_obj, created = NotePrimaire.objects.get_or_create(
                                eleve=eleve,
                                evaluation_primaire=evaluation,
                                defaults={
                                    'absent': False,
                                    'annee_scolaire': annee_scolaire_active,
                                }
                            )
                            if note_value:
                                try:
                                    note_decimal = Decimal(note_value.replace(',', '.'))
                                    if note_decimal < 0 or note_decimal > evaluation.bareme:
                                        errors.append(f"Note invalide pour {eleve.nom_complet}: {note_decimal} (max: {evaluation.bareme})")
                                        continue
                                    note_a_change = (
                                        created or
                                        note_obj.note != note_decimal or
                                        note_obj.absent != False
                                    )
                                    note_obj.note = note_decimal
                                    note_obj.absent = False
                                    if note_obj.note_publiee is None:
                                        note_obj.statut_publication = NotePrimaire.STATUT_BROUILLON
                                    elif note_obj.note_publiee != note_decimal:
                                        note_obj.statut_publication = NotePrimaire.STATUT_MODIFIEE
                                    else:
                                        note_obj.statut_publication = NotePrimaire.STATUT_PUBLIEE
                                    note_obj.save(update_fields=['note', 'absent', 'statut_publication'])
                                    if note_a_change:
                                        notes_enregistrees += 1
                                    notes_dict[f'note_{eleve.id}_{evaluation.id}'] = str(note_decimal).replace('.', ',')
                                except (ValueError, TypeError):
                                    errors.append(f"Valeur invalide pour {eleve.nom_complet}: {note_value}")
                    for session in sessions_examens:
                        note_value = request.POST.get(f'note_{eleve.id}_examen_{session.id}', '').strip()
                        note_examen_obj, created = NoteExamen.objects.get_or_create(
                            eleve=eleve,
                            session_examen=session,
                            matiere=matiere,
                            defaults={
                                'professeur': professeur,
                                'classe': classe,
                                'absent': False,
                                'bareme': 20,
                                'annee_scolaire': annee_scolaire_active,
                            }
                        )
                        if note_value:
                            try:
                                note_decimal = Decimal(note_value.replace(',', '.'))
                                if note_decimal < 0 or note_decimal > 20:
                                    errors.append(f"Note d'examen invalide pour {eleve.nom_complet}: {note_decimal} (max: 20)")
                                    continue
                                note_a_change = (
                                    created or
                                    note_examen_obj.note != note_decimal or
                                    note_examen_obj.absent != False
                                )
                                note_examen_obj.note = note_decimal
                                note_examen_obj.absent = False
                                if note_examen_obj.note_publiee is None:
                                    note_examen_obj.statut_publication = NoteExamen.STATUT_BROUILLON
                                elif note_examen_obj.note_publiee != note_decimal:
                                    note_examen_obj.statut_publication = NoteExamen.STATUT_MODIFIEE
                                else:
                                    note_examen_obj.statut_publication = NoteExamen.STATUT_PUBLIEE
                                note_examen_obj.save(update_fields=['note', 'absent', 'note_sur_20', 'statut_publication'])
                                if note_a_change:
                                    notes_enregistrees += 1
                                notes_dict[f'note_{eleve.id}_examen_{session.id}'] = str(note_decimal).replace('.', ',')
                            except (ValueError, TypeError):
                                errors.append(f"Valeur invalide pour {eleve.nom_complet}: {note_value}")
            except Exception as e:
                logger.error(f"Erreur lors de l'enregistrement des notes: {e}")
                error_message = f"Erreur lors de l'enregistrement: {str(e)}"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                    return JsonResponse({'success': False, 'message': error_message})
                messages.error(request, error_message)
                return redirect(f"{request.path}?periode={periode_selectionnee.id}&matiere={matiere_id}")
            
            if notes_enregistrees > 0:
                success_msg = f"{notes_enregistrees} note(s) enregistrée(s) avec succès pour {matiere.nom} !"
            else:
                success_msg = "Aucune note n'a été modifiée."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken'):
                return JsonResponse({
                    'success': notes_enregistrees > 0,
                    'message': success_msg,
                    'errors': errors,
                    'notes_enregistrees': notes_dict
                })
            if errors:
                for error in errors:
                    messages.warning(request, error)
            if notes_enregistrees > 0:
                messages.success(request, success_msg)
            else:
                messages.info(request, success_msg)
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_notes')
    
    # Vérifier l'affectation
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    try:
        affectation = affectation_qs.get()
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
        
        # Récupérer les matières enseignées par ce professeur dans cette classe
        matieres_professeur = affectation.matieres.all()
        
        # Récupérer UNIQUEMENT les moyennes des matières enseignées par ce professeur
        moyennes = MoyenneMatierePrimaire.objects.filter(
            classe=classe,
            periode_scolaire=periode,
            matiere__in=matieres_professeur
        )
        if annee_scolaire_active:
            moyennes = moyennes.filter(annee_scolaire=annee_scolaire_active)
        
        # Vérifier si déjà soumis
        if moyennes.filter(soumis=True).exists():
            messages.warning(request, f"Le relevé pour {periode.nom_periode} a déjà été soumis.")
        else:
            with transaction.atomic():
                # UNIQUEMENT : Marquer toutes les moyennes comme soumises
                # Aucun calcul de moyenne, aucune modification de notes, aucune modification d'absences
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
                
                messages.success(request, f"✓ Relevé soumis pour {periode.nom_periode} ! {nb_soumises} moyenne(s) verrouillée(s).")
        
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        return HttpResponse("Aucune année scolaire active n'est définie pour votre établissement.", status=403)
    
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    try:
        affectation = affectation_qs.get()
    except AffectationProfesseurPrimaire.DoesNotExist:
        return HttpResponse("Vous n'êtes pas affecté à cette classe.", status=403)
    
    periode_id = request.GET.get('periode')
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
    # Filtres
    matiere_id = request.GET.get('matiere')
    periode_id = request.GET.get('periode')
    classe_id = request.GET.get('classe')
    
    # Récupérer toutes les évaluations du professeur
    evaluations = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        evaluations = evaluations.filter(annee_scolaire=annee_scolaire_active)
    
    # Appliquer les filtres
    if matiere_id:
        evaluations = evaluations.filter(matiere_id=matiere_id)
    if periode_id:
        evaluations = evaluations.filter(periode_scolaire_id=periode_id)
    if classe_id:
        evaluations = evaluations.filter(classe_id=classe_id)
    
    evaluations = evaluations.select_related('classe', 'matiere', 'periode_scolaire').order_by('-date_evaluation')
    
    # Récupérer les options de filtres
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.prefetch_related('matieres')
    
    matieres_enseignees = set()
    classes_enseignees = []
    for affectation in affectations:
        matieres_enseignees.update(affectation.matieres.all())
        classes_enseignees.append(affectation.classe)
    
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')
    
    context = {
        'professeur': professeur,
        'evaluations': evaluations,
        'matieres_enseignees': sorted(matieres_enseignees, key=lambda m: m.nom),
        'classes_enseignees': classes_enseignees,
        'periodes': periodes,
        'matiere_selectionnee': matiere_id,
        'periode_selectionnee': periode_id,
        'classe_selectionnee': classe_id,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/primaire/liste_evaluations_primaire.html', context)


def supprimer_evaluation_primaire(request, evaluation_id):
    """
    Supprime une évaluation primaire existante.
    """
    if request.method != 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': False, 'message': 'Méthode non autorisée.'})
        messages.error(request, "Méthode non autorisée.")
        return redirect('enseignant_primaire:liste_evaluations')
    
    if not isinstance(request.user, Professeur):
        from django.http import JsonResponse
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Accès non autorisé.'})
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    from ..model.evaluation_primaire_model import EvaluationPrimaire
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    from django.http import JsonResponse
    
    try:
        evaluation = get_object_or_404(EvaluationPrimaire, id=evaluation_id, professeur=professeur, actif=True)
        titre_evaluation = evaluation.titre
        
        with transaction.atomic():
            # Marquer l'évaluation comme inactive (soft delete)
            evaluation.actif = False
            evaluation.save()
        
        logger.info(f"Évaluation primaire {evaluation_id} supprimée par {professeur.nom_complet}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f"L'évaluation '{titre_evaluation}' a été supprimée avec succès.",
            })
        
        messages.success(request, f"L'évaluation '{titre_evaluation}' a été supprimée avec succès.")
        return redirect('enseignant_primaire:liste_evaluations')
        
    except EvaluationPrimaire.DoesNotExist:
        error_message = "Évaluation introuvable ou vous n'avez pas la permission de la supprimer."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_message})
        messages.error(request, error_message)
        return redirect('enseignant_primaire:liste_evaluations')
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de l'évaluation primaire {evaluation_id}: {e}", exc_info=True)
        error_message = f"Une erreur est survenue lors de la suppression : {str(e)}"
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_message})
        messages.error(request, error_message)
        return redirect('enseignant_primaire:liste_evaluations')


def evaluations_classe_primaire(request, classe_id):
    """
    Affiche toutes les évaluations créées par le professeur pour une classe donnée.
    Navigation par onglets pour les périodes.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_notes')
    
    # Vérifier que le professeur est affecté à cette classe
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_qs.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_notes')
    
    # Récupérer toutes les périodes scolaires de l'établissement
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')
    
    # Récupérer la période sélectionnée depuis l'URL
    periode_id = request.GET.get('periode')
    periode_selectionnee = None
    
    if periode_id:
        try:
            periode_selectionnee = periodes.get(id=periode_id)
        except PeriodeScolaire.DoesNotExist:
            pass
    
    # Si aucune période sélectionnée, utiliser la première active
    if not periode_selectionnee:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Récupérer toutes les évaluations créées par ce professeur pour cette classe
    evaluations_query = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        evaluations_query = evaluations_query.filter(annee_scolaire=annee_scolaire_active)
    evaluations_query = evaluations_query.select_related('matiere', 'periode_scolaire').order_by('-date_evaluation')
    
    # Filtrer par période si une période est sélectionnée
    if periode_selectionnee:
        evaluations = evaluations_query.filter(periode_scolaire=periode_selectionnee)
    else:
        evaluations = evaluations_query
    
    # Grouper les évaluations par matière
    evaluations_par_matiere = {}
    for evaluation in evaluations:
        matiere = evaluation.matiere
        if matiere.id not in evaluations_par_matiere:
            evaluations_par_matiere[matiere.id] = {
                'matiere': matiere,
                'evaluations': []
            }
        evaluations_par_matiere[matiere.id]['evaluations'].append(evaluation)
    
    # Statistiques globales
    total_evaluations = evaluations.count()
    evaluations_passees = evaluations.filter(date_evaluation__lt=date.today()).count()
    evaluations_a_venir = evaluations.filter(date_evaluation__gte=date.today()).count()
    
    # Récupérer les matières pour le formulaire de modification
    matieres = affectation.matieres.all()
    
    context = {
        'professeur': professeur,
        'classe': classe,
        'affectation': affectation,
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'evaluations': evaluations,
        'evaluations_par_matiere': evaluations_par_matiere,
        'total_evaluations': total_evaluations,
        'evaluations_passees': evaluations_passees,
        'evaluations_a_venir': evaluations_a_venir,
        'matieres': matieres,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/primaire/evaluations_classe_primaire.html', context)


def modifier_evaluation_primaire(request, evaluation_id):
    """
    Modifie une évaluation existante.
    """
    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    etablissement = professeur.etablissement
    annee_scolaire_active = get_session_active(request, etablissement)
    
    evaluation = get_object_or_404(EvaluationPrimaire, id=evaluation_id, professeur=professeur, actif=True)
    if annee_scolaire_active:
        evaluation = get_object_or_404(EvaluationPrimaire, id=evaluation_id, professeur=professeur, actif=True, annee_scolaire=annee_scolaire_active)
    classe = evaluation.classe
    
    # Vérifier que le professeur est affecté à cette classe
    affectation_query = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_query = affectation_query.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_query.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_notes')
    
    # Récupérer les matières et périodes
    matieres = affectation.matieres.all()
    periodes_query = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_query = periodes_query.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_query.order_by('date_debut')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                titre = request.POST.get('titre')
                description = request.POST.get('description', '')
                matiere_id = request.POST.get('matiere')
                date_evaluation = request.POST.get('date_evaluation')
                bareme = request.POST.get('bareme', 20)
                periode_id = request.POST.get('periode')
                
                # Validation
                if not all([titre, matiere_id, date_evaluation, periode_id]):
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': 'Tous les champs obligatoires doivent être remplis.'})
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('enseignant_primaire:evaluations_classe', classe_id=classe.id)
                
                matiere = get_object_or_404(Matiere, id=matiere_id)
                periode = get_object_or_404(PeriodeScolaire, id=periode_id)
                
                # Vérifier que le professeur enseigne cette matière
                if matiere not in matieres:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': "Vous n'enseignez pas cette matière dans cette classe."})
                    messages.error(request, "Vous n'enseignez pas cette matière dans cette classe.")
                    return redirect('enseignant_primaire:evaluations_classe', classe_id=classe.id)
                
                # Mettre à jour l'évaluation
                evaluation.titre = titre
                evaluation.description = description
                evaluation.matiere = matiere
                evaluation.date_evaluation = date_evaluation
                evaluation.bareme = bareme
                evaluation.periode_scolaire = periode
                if annee_scolaire_active:
                    evaluation.annee_scolaire = annee_scolaire_active
                evaluation.save()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f"Évaluation '{titre}' modifiée avec succès.",
                        'redirect_url': f"/enseignant/primaire/evaluations-classe/{classe.id}/?periode={periode.id}"
                    })
                
                messages.success(request, f"Évaluation '{titre}' modifiée avec succès.")
                return redirect('enseignant_primaire:evaluations_classe', classe_id=classe.id)
                
        except Exception as e:
            logger.error(f"Erreur lors de la modification de l'évaluation: {e}")
            error_message = f"Une erreur est survenue: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
    
    # Pour les requêtes AJAX (chargement du formulaire)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        html = render_to_string('school_admin/enseignant/primaire/partials/modal_modifier_evaluation.html', {
            'evaluation': evaluation,
            'matieres': matieres,
            'periodes': periodes,
            'annee_scolaire_active': annee_scolaire_active,
        }, request=request)
        return JsonResponse({'html': html})
    
    # Pour les requêtes normales (redirection)
    return redirect('enseignant_primaire:evaluations_classe', classe_id=classe.id)


def calculer_moyennes_classe_primaire(request, classe_id):
    """
    Calculer et enregistrer toutes les moyennes d'une classe.
    """
    if not isinstance(request.user, Professeur):
        return JsonResponse({'success': False, 'error': 'Accès non autorisé'})
    
    professeur = request.user
    etablissement = professeur.etablissement
    annee_scolaire_active = get_session_active(request, etablissement)
    classe = get_object_or_404(Classe, id=classe_id)
    
    try:
        affectation_query = AffectationProfesseurPrimaire.objects.filter(
            professeur=professeur,
            classe=classe,
            actif=True
        )
        if annee_scolaire_active:
            affectation_query = affectation_query.filter(annee_scolaire=annee_scolaire_active)
        affectation = affectation_query.get()
    except AffectationProfesseurPrimaire.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Vous n\'êtes pas affecté à cette classe'})
    
    periode_id = request.POST.get('periode_id')
    periode = get_object_or_404(PeriodeScolaire, id=periode_id)
    if annee_scolaire_active:
        periode = get_object_or_404(PeriodeScolaire, id=periode_id, annee_scolaire_fk=annee_scolaire_active)
    
    try:
        # Calculer toutes les moyennes
        # Récupérer les élèves via InscriptionEleve
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        matieres = affectation.matieres.all()
        
        moyennes_calculees = 0
        for eleve in eleves:
            for matiere in matieres:
                moyenne_obj, created = MoyenneMatierePrimaire.calculer_et_enregistrer(
                    eleve,
                    matiere,
                    periode,
                    mode_calcul='toutes',
                    evaluations_utilisees=[],
                    ponderation='50_50',
                )
                if created or moyenne_obj:
                    # S'assurer que l'année scolaire est définie
                    if annee_scolaire_active and moyenne_obj:
                        moyenne_obj.annee_scolaire = annee_scolaire_active
                        moyenne_obj.save()
                    moyennes_calculees += 1
        
        # Envoyer des notifications push personnalisées aux élèves
        if moyennes_calculees > 0 and eleves.exists():
            try:
                from school_admin.services.firebase_service import FirebaseService
                
                # Envoyer une notification personnalisée à chaque élève avec ses moyennes
                notifications_envoyees = 0
                for eleve in eleves:
                    # Récupérer toutes les moyennes de l'élève pour cette période
                    moyennes_eleve_query = MoyenneMatierePrimaire.objects.filter(
                        eleve=eleve,
                        periode_scolaire=periode
                    )
                    if annee_scolaire_active:
                        moyennes_eleve_query = moyennes_eleve_query.filter(annee_scolaire=annee_scolaire_active)
                    moyennes_eleve = moyennes_eleve_query
                    
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Vérifier l'affectation primaire
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    affectation = get_object_or_404(affectation_qs)
    
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
    )
    if annee_scolaire_active:
        appels_du_jour = appels_du_jour.filter(annee_scolaire=annee_scolaire_active)
    appels_du_jour = appels_du_jour.order_by('numero_appel')
    
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
        liste_presence_qs = ListePresence.objects.filter(
            classe=classe,
            date=today,
            numero_appel=prochain_numero_appel,
            validee=False
        )
        if annee_scolaire_active:
            liste_presence_qs = liste_presence_qs.filter(annee_scolaire=annee_scolaire_active)
        liste_presence_actuelle = liste_presence_qs.first()
        
        # Si aucune liste non validée n'existe et qu'on n'a pas atteint la limite, en créer une
        if not liste_presence_actuelle and not limite_atteinte:
            liste_presence_actuelle = ListePresence.objects.create(
                classe=classe,
                date=today,
                numero_appel=prochain_numero_appel,
                professeur=professeur,
                etablissement=classe.etablissement,
                annee_scolaire=annee_scolaire_active,
            )
    
    # Récupérer tous les élèves actifs de la classe via InscriptionEleve
    eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
    
    # Récupérer les présences pour l'appel en cours (si existe)
    eleves_avec_presence = []
    if liste_presence_actuelle:
        # Récupérer les présences liées à cet appel spécifique
        presences_qs = Presence.objects.filter(
            classe=classe,
            date=today,
            numero_appel=prochain_numero_appel
        )
        if annee_scolaire_active:
            presences_qs = presences_qs.filter(annee_scolaire=annee_scolaire_active)
        presences_existantes = presences_qs.select_related('eleve')
        
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:liste_presence', classe_id=classe_id)
    
    # Vérifier l'affectation primaire
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    affectation = get_object_or_404(affectation_qs)
    
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
            liste_presence_qs = ListePresence.objects.filter(
                classe=classe,
                date=today,
                numero_appel=numero_appel
            )
            if annee_scolaire_active:
                liste_presence_qs = liste_presence_qs.filter(annee_scolaire=annee_scolaire_active)
            liste_presence = get_object_or_404(liste_presence_qs)
            
            # Si déjà validée, interdire la modification
            if liste_presence.validee:
                messages.warning(request, f"L'appel n°{numero_appel} a déjà été validé pour aujourd'hui.")
                return redirect('enseignant_primaire:liste_presence', classe_id=classe_id)
            
            # Parcourir les données POST pour enregistrer les présences
            nombre_presents = 0
            nombre_absents = 0
            nombre_retards = 0
            
            # Log pour déboguer
            logger.info(f"Validation présence primaire - POST keys: {list(request.POST.keys())}")
            logger.info(f"Validation présence primaire - Nombre d'éléments POST: {len(request.POST)}")
            
            # Récupérer tous les élèves de la classe pour s'assurer qu'on traite tous les élèves
            eleves_classe = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
            logger.info(f"Validation présence primaire - Nombre d'élèves dans la classe: {eleves_classe.count()}")
            
            # Parcourir les données POST pour récupérer les statuts
            presences_post = {}
            for key, value in request.POST.items():
                if key.startswith('presence_'):
                    eleve_id = key.replace('presence_', '')
                    presences_post[eleve_id] = value
                    logger.info(f"Traitement présence primaire - Key: {key}, Value: {value}, Eleve ID: {eleve_id}")
            
            logger.info(f"Validation présence primaire - Nombre de présences dans POST: {len(presences_post)}")
            
            # Traiter chaque élève de la classe
            for eleve in eleves_classe:
                eleve_id_str = str(eleve.id)
                statut = presences_post.get(eleve_id_str, 'present')  # Par défaut 'present' si non spécifié
                
                try:
                    # Créer ou mettre à jour la présence avec le numéro d'appel
                    presence, created = Presence.objects.update_or_create(
                        eleve=eleve,
                        classe=classe,
                        date=today,
                        numero_appel=numero_appel,
                        matiere=None,  # Pas de matière pour le primaire
                        defaults={
                            'professeur': professeur,
                            'etablissement': classe.etablissement,
                            'statut': statut,
                            'annee_scolaire': annee_scolaire_active,
                        }
                    )
                    
                    # Si la présence existait déjà, mettre à jour le statut et s'assurer que l'année scolaire est correcte
                    if not created:
                        presence.statut = statut
                        if annee_scolaire_active:
                            presence.annee_scolaire = annee_scolaire_active
                        presence.save()
                    
                    # Compter les présents, absents et retards
                    if statut == 'present':
                        nombre_presents += 1
                    elif statut in ['absent', 'absent_justifie']:
                        nombre_absents += 1
                    elif statut == 'retard':
                        nombre_retards += 1
                    
                    logger.info(f"Présence primaire enregistrée - Élève: {eleve.nom_complet}, Statut: {statut}, Créée: {created}")
                    
                except Eleve.DoesNotExist:
                    logger.warning(f"Élève {eleve.id} non trouvé ou inactif")
                    continue
                except Exception as e:
                    logger.error(f"Erreur lors de l'enregistrement de la présence pour l'élève {eleve.id}: {str(e)}")
                    continue
            
            # Valider la liste de présence
            liste_presence.validee = True
            liste_presence.date_validation = timezone.now()
            liste_presence.nombre_presents = nombre_presents
            liste_presence.nombre_absents = nombre_absents
            liste_presence.save()
            
            # Récupérer les IDs des présences créées/mises à jour pour les notifications
            presences_ids = []
            try:
                presences_qs = Presence.objects.filter(
                    classe=classe,
                    date=today,
                    numero_appel=numero_appel
                )
                if annee_scolaire_active:
                    presences_qs = presences_qs.filter(annee_scolaire=annee_scolaire_active)
                presences_ids = list(presences_qs.values_list('id', flat=True))
            except Exception as e:
                logger.error(f"Erreur lors de la récupération des IDs de présence: {str(e)}")
            
            # Programmer l'envoi des notifications en arrière-plan
            if presences_ids:
                from ..services.notification_tasks import schedule_presence_notifications
                schedule_presence_notifications(presences_ids)
                logger.info(f"Envoi des notifications programmé en arrière-plan pour {len(presences_ids)} présence(s)")
            
            messages.success(
                request, 
                f"✓ Appel n°{numero_appel} validé avec succès ! {nombre_presents} présent(s), {nombre_absents} absent(s), {nombre_retards} retard(s)."
            )
            
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Vérifier l'affectation primaire
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_qs.first()
    
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
            date_sanction=date_sanction,
            annee_scolaire=annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
    from ..model.sanction_model import Sanction
    from django.db.models import Count
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier l'affectation primaire
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_qs.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Récupérer toutes les sanctions de la classe
    sanctions = Sanction.objects.filter(
        classe=classe
    )
    if annee_scolaire_active:
        sanctions = sanctions.filter(annee_scolaire=annee_scolaire_active)
    sanctions = sanctions.select_related('eleve', 'professeur').order_by('-date_sanction', '-date_creation')
    
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Récupérer la classe active de l'élève depuis InscriptionEleve
    classe_active = _get_classe_eleve_active(eleve, annee_scolaire_active, professeur.etablissement)
    
    if not classe_active:
        messages.error(request, "Cet élève n'est pas inscrit dans une classe pour l'année scolaire active.")
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Vérifier que le professeur enseigne dans la classe active de l'élève
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe_active,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    try:
        affectation = affectation_qs.get()
    except AffectationProfesseurPrimaire.DoesNotExist:
        messages.error(request, "Vous n'êtes pas affecté à cette classe pour l'année scolaire active.")
        return redirect('enseignant_primaire:gestion_eleves')
    
    # Récupérer l'onglet sélectionné
    onglet = request.GET.get('onglet', 'informations')
    
    # Récupérer la période pour les notes
    periode_id = request.GET.get('periode')
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')
    
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
            evaluations_qs = EvaluationPrimaire.objects.filter(
                classe=classe_active,
                matiere=matiere,
                periode_scolaire=periode_selectionnee,
                actif=True
            )
            if annee_scolaire_active:
                evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
            evaluations = evaluations_qs.order_by('date_evaluation')
            
            notes_objs_qs = NotePrimaire.objects.filter(
                eleve=eleve,
                evaluation_primaire__in=evaluations
            )
            if annee_scolaire_active:
                notes_objs_qs = notes_objs_qs.filter(annee_scolaire=annee_scolaire_active)
            notes_objs = notes_objs_qs.select_related('evaluation_primaire')
            
            # Créer un dictionnaire des notes indexé par evaluation_id
            notes_dict = {note.evaluation_primaire.id: note for note in notes_objs}
            
            # Récupérer les sessions d'examen (PAS les créneaux!) pour cette matière et période
            from ..model.session_examen_model import SessionExamen
            sessions_examen_qs = SessionExamen.objects.filter(
                classes=classe_active,
                periode=periode_selectionnee,
                matieres=matiere,
                actif=True
            )
            if annee_scolaire_active:
                sessions_examen_qs = sessions_examen_qs.filter(annee_scolaire=annee_scolaire_active)
            sessions_examen = sessions_examen_qs.distinct()
            
            # Récupérer les notes d'examen basées sur (eleve, session, matiere)
            notes_examen_objs_qs = NoteExamen.objects.filter(
                eleve=eleve,
                session_examen__in=sessions_examen,
                matiere=matiere
            )
            if annee_scolaire_active:
                notes_examen_objs_qs = notes_examen_objs_qs.filter(annee_scolaire=annee_scolaire_active)
            notes_examen_objs = notes_examen_objs_qs.select_related('session_examen')
            
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
                
                evaluations_list.append(PseudoExamen(session))
            
            # Récupérer la moyenne enregistrée
            moyenne_qs = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                matiere=matiere,
                periode_scolaire=periode_selectionnee
            )
            if annee_scolaire_active:
                moyenne_qs = moyenne_qs.filter(annee_scolaire=annee_scolaire_active)
            moyenne_obj = moyenne_qs.first()
            
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
    )
    if annee_scolaire_active:
        presences_query = presences_query.filter(annee_scolaire=annee_scolaire_active)
    presences_query = presences_query.select_related('eleve', 'classe')
    
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
        listes_validees_qs = ListePresence.objects.filter(
            classe=classe_active,
            validee=True,
            date__gte=debut_annee,
            date__lte=fin_annee
        )
        if annee_scolaire_active:
            listes_validees_qs = listes_validees_qs.filter(annee_scolaire=annee_scolaire_active)
        listes_validees = listes_validees_qs.values_list('date', flat=True)
        
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
        sanctions_qs = Sanction.objects.filter(eleve=eleve)
        if annee_scolaire_active:
            sanctions_qs = sanctions_qs.filter(annee_scolaire=annee_scolaire_active)
        sanctions = sanctions_qs.order_by('-date_sanction')[:20]
    else:
        sanctions = []
    
    context = {
        'professeur': professeur,
        'eleve': eleve,
        'classe': classe_active,
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # Récupérer l'onglet actif (pour restauration après filtrage)
    onglet_actif = request.GET.get('onglet', 'eleves')
    
    # Récupérer la classe
    classe = get_object_or_404(Classe, id=classe_id, actif=True)
    
    # Vérifier que le professeur est affecté à cette classe
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_qs.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_classes')
    
    # === STATISTIQUES GÉNÉRALES ===
    # Récupérer les élèves via InscriptionEleve
    eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
    nombre_eleves = eleves.count()
    taux_occupation = round((nombre_eleves / classe.capacite_max * 100), 1) if classe.capacite_max > 0 else 0
    
    # Répartition par genre
    nombre_garcons = eleves.filter(sexe='M').count()
    nombre_filles = eleves.filter(sexe='F').count()
    
    # === STATISTIQUES DE PRÉSENCE ===
    today = date.today()
    debut_mois = date(today.year, today.month, 1)
    
    # Récupérer tous les mois distincts avec présence pour déterminer les mois disponibles
    presences_dates_qs = Presence.objects.filter(classe=classe)
    if annee_scolaire_active:
        presences_dates_qs = presences_dates_qs.filter(annee_scolaire=annee_scolaire_active)
    presences_dates = presences_dates_qs.dates('date', 'month', order='DESC')
    
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
    if annee_scolaire_active:
        presences_mois = presences_mois.filter(annee_scolaire=annee_scolaire_active)
    
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
    )
    if annee_scolaire_active:
        listes_presence_query = listes_presence_query.filter(annee_scolaire=annee_scolaire_active)
    listes_presence_query = listes_presence_query.order_by('-date', 'numero_appel')
    
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
    )
    if annee_scolaire_active:
        periodes_scolaires = periodes_scolaires.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes_scolaires = periodes_scolaires.order_by('date_debut')
    
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
    if annee_scolaire_active:
        evaluations = evaluations.filter(annee_scolaire=annee_scolaire_active)
    
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
        presence_abs_qs = Presence.objects.filter(
            eleve=eleve,
            statut='absent'
        )
        if annee_scolaire_active:
            presence_abs_qs = presence_abs_qs.filter(annee_scolaire=annee_scolaire_active)
        nombre_absences = presence_abs_qs.count()
        
        # Retards
        presence_ret_qs = Presence.objects.filter(
            eleve=eleve,
            statut='retard'
        )
        if annee_scolaire_active:
            presence_ret_qs = presence_ret_qs.filter(annee_scolaire=annee_scolaire_active)
        nombre_retards = presence_ret_qs.count()
        
        # Sanctions
        from ..model.sanction_model import Sanction
        sanction_qs = Sanction.objects.filter(eleve=eleve)
        if annee_scolaire_active:
            sanction_qs = sanction_qs.filter(annee_scolaire=annee_scolaire_active)
        nombre_sanctions = sanction_qs.count()
        
        # Notes
        note_qs = NotePrimaire.objects.filter(
            eleve=eleve,
            evaluation_primaire__professeur=professeur
        )
        if annee_scolaire_active:
            note_qs = note_qs.filter(annee_scolaire=annee_scolaire_active)
        nombre_notes = note_qs.count()
        
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
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
                logger.info(f"Mot de passe changé - Professeur primaire: {professeur.nom_complet}")
        
        return redirect('enseignant_primaire:parametres_profil')
    
    # Statistiques pour enseignant primaire
    affectations_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations_qs = affectations_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_classes = affectations_qs.count()
    
    # Récupérer toutes les affectations primaires pour avoir les matières
    affectations = affectations_qs.prefetch_related('matieres')
    
    # Récupérer toutes les matières enseignées
    matieres_enseignees = set()
    for affectation in affectations:
        matieres_enseignees.update(affectation.matieres.all())
    
    evaluations_qs = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        evaluations_qs = evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_evaluations = evaluations_qs.count()
    
    notes_qs = NotePrimaire.objects.filter(
        evaluation_primaire__professeur=professeur
    )
    if annee_scolaire_active:
        notes_qs = notes_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_notes = notes_qs.count()
    
    sanctions_qs = Sanction.objects.filter(
        professeur=professeur
    )
    if annee_scolaire_active:
        sanctions_qs = sanctions_qs.filter(annee_scolaire=annee_scolaire_active)
    nombre_sanctions = sanctions_qs.count()
    
    # Dernières activités (évaluations primaires)
    dernieres_evaluations_qs = EvaluationPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        dernieres_evaluations_qs = dernieres_evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
    dernieres_evaluations = dernieres_evaluations_qs.order_by('-date_creation')[:5]
    
    context = {
        'professeur': professeur,
        'nombre_classes': nombre_classes,
        'nombre_matieres': len(matieres_enseignees),
        'matieres_enseignees': list(matieres_enseignees),
        'nombre_evaluations': nombre_evaluations,
        'nombre_notes': nombre_notes,
        'nombre_sanctions': nombre_sanctions,
        'dernieres_evaluations': dernieres_evaluations,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/primaire/parametres_profil_primaire.html', context)


def historique_annees_primaire(request):
    """
    Liste les années scolaires précédentes (ou inactives) pour les enseignants du primaire.
    """
    logger.info("Historique années scolaires primaire - User: %s", request.user)

    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    professeur = request.user
    etablissement = getattr(professeur, 'etablissement', None)

    if not etablissement:
        messages.error(request, "Établissement introuvable.")
        return redirect('enseignant_primaire:parametres_profil')

    from ..model.annee_scolaire_model import AnneeScolaire
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
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
        affectations = AffectationProfesseurPrimaire.objects.filter(
            professeur=professeur,
            annee_scolaire=annee
        )

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

    return render(
        request,
        'school_admin/enseignant/primaire/historique_annees_primaire.html',
        context
    )


def detail_historique_annee_primaire(request, annee_id):
    """
    Affiche le détail complet d'une année scolaire précédente pour un enseignant primaire.
    """
    logger.info("Détail historique année scolaire primaire - User: %s", request.user)

    if not isinstance(request.user, Professeur):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    professeur = request.user
    etablissement = getattr(professeur, 'etablissement', None)

    if not etablissement:
        messages.error(request, "Établissement introuvable.")
        return redirect('enseignant_primaire:parametres_profil')

    from ..model.annee_scolaire_model import AnneeScolaire
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..model.presence_model import Presence
    from ..model.evaluation_primaire_model import EvaluationPrimaire
    from ..model.note_primaire_model import NotePrimaire
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
        return redirect('enseignant_primaire:historique_annees')

    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        annee_scolaire=annee
    ).prefetch_related('matieres').select_related('classe')

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

    nombre_evaluations = EvaluationPrimaire.objects.filter(
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
            evaluation_primaire__bareme__gt=0,
            then=ExpressionWrapper(
                (F('note') / F('evaluation_primaire__bareme')) * Value(20),
                output_field=FloatField()
            )
        ),
        default=Value(0),
        output_field=FloatField()
    )

    for affectation in affectations:
        classe = affectation.classe
        matieres = list(affectation.matieres.all())
        matieres_label = ", ".join(matiere.nom for matiere in matieres) if matieres else "Polyvalent"

        inscriptions_classe = InscriptionEleve.objects.filter(
            annee_scolaire=annee,
            classe=classe
        ).order_by('nom', 'prenom')

        notes_queryset = NotePrimaire.objects.filter(
            evaluation_primaire__professeur=professeur,
            evaluation_primaire__classe=classe,
            annee_scolaire=annee,
            absent=False
        ).exclude(note__isnull=True)

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
                'moyenne': moyenne,
                'absences': stats_presence.get('absences', 0),
                'presences': stats_presence.get('presences', 0),
                'sanctions': sanction_map.get(inscription.eleve_id, 0),
            })

        classe_details.append({
            'classe': classe,
            'matieres_label': matieres_label,
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
        'nombre_evaluations': nombre_evaluations,
        'nombre_sanctions': nombre_sanctions,
        'classe_details': classe_details,
    }

    return render(
        request,
        'school_admin/enseignant/primaire/historique_annee_detail_primaire.html',
        context
    )


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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
    from django.utils import timezone
    from datetime import timedelta
    import re
    
    # Récupérer toutes les affectations actives du professeur primaire
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.select_related('classe', 'classe__etablissement').prefetch_related('classe__eleves').order_by('classe__nom')
    
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
        
        # Récupérer les élèves actifs de cette classe via InscriptionEleve
        eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
        
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
            if annee_scolaire_active:
                presences = presences.filter(annee_scolaire=annee_scolaire_active)
            
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
    import re
    
    # Récupérer les paramètres de navigation
    periode_id = request.GET.get('periode')
    
    # Récupérer toutes les périodes
    periodes = PeriodeScolaire.objects.filter(
        etablissement=professeur.etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes = periodes.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes.order_by('date_debut')
    
    # Période active par défaut
    if periode_id:
        periode_selectionnee = get_object_or_404(PeriodeScolaire, id=periode_id)
    else:
        periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
    
    # Récupérer les affectations et grouper les classes par type
    affectations = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        actif=True
    )
    if annee_scolaire_active:
        affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
    affectations = affectations.select_related('classe').prefetch_related('matieres')
    
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
        
        # Récupérer les élèves actifs de la classe via InscriptionEleve
        eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
        
        # Pour chaque élève, récupérer ses moyennes dans toutes les matières
        eleves_difficulte = []
        
        for eleve in eleves:
            # Récupérer toutes les moyennes de cet élève pour la période
            moyennes_qs = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                periode_scolaire=periode_selectionnee
            )
            if annee_scolaire_active:
                moyennes_qs = moyennes_qs.filter(annee_scolaire=annee_scolaire_active)
            moyennes = moyennes_qs
            
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre établissement.")
        return redirect('enseignant_primaire:gestion_presence')
    
    # Vérifier que le professeur est affecté à cette classe
    affectation_qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    if annee_scolaire_active:
        affectation_qs = affectation_qs.filter(annee_scolaire=annee_scolaire_active)
    affectation = affectation_qs.first()
    
    if not affectation:
        messages.error(request, "Vous n'êtes pas affecté à cette classe.")
        return redirect('enseignant_primaire:gestion_presence')
    
    # Déterminer la semaine à afficher (semaine en cours par défaut)
    today = date.today()
    
    # Calculer le lundi de la semaine en cours
    lundi = today - timedelta(days=today.weekday())
    samedi = lundi + timedelta(days=5)
    
    classes_data = []
    
    # Traiter uniquement la classe sélectionnée via InscriptionEleve
    eleves = _get_eleves_classe_par_inscription(classe, professeur.etablissement, annee_scolaire_active)
    
    # Récupérer les présences de la semaine pour tous les élèves
    # IMPORTANT : Filtrer par professeur pour afficher uniquement ses appels
    presences_semaine = Presence.objects.filter(
        classe=classe,
        professeur=professeur,
        date__gte=lundi,
        date__lte=samedi
    )
    if annee_scolaire_active:
        presences_semaine = presences_semaine.filter(annee_scolaire=annee_scolaire_active)
    presences_semaine = presences_semaine.select_related('eleve')
    
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, professeur.etablissement)
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre établissement.")
    
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
    )
    if annee_scolaire_active:
        annonces = annonces.filter(annee_scolaire=annee_scolaire_active)
    annonces = annonces.order_by('-date_publication', '-date_creation')
    
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
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/enseignant/primaire/annonces_enseignant.html', context)

