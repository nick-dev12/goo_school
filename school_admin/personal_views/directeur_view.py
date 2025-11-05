from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.utils import timezone
from ..model.etablissement_model import Etablissement
from ..model.facturation_model import Facturation
from ..model.eleve_model import Eleve
from ..model.demande_liaison_model import DemandeLiaisonParent
from ..model.lien_familial_model import LienFamilial


@login_required
def dashboard_directeur(request):
    """
    Vue du tableau de bord pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les informations de l'établissement
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..model.professeur_model import Professeur
    from ..model.moyenne_model import Moyenne
    from datetime import datetime, timedelta
    from django.db.models import Avg, Count
    
    # === STATISTIQUES DES ÉLÈVES ===
    eleves = Eleve.objects.filter(etablissement=etablissement, actif=True)
    nombre_eleves_total = eleves.count()
    
    # Calculer le pourcentage de croissance (approximation basée sur les dates d'inscription récentes)
    date_annee_derniere = datetime.now() - timedelta(days=365)
    eleves_annee_derniere = Eleve.objects.filter(
        etablissement=etablissement, 
        date_inscription__lte=date_annee_derniere,
        actif=True
    ).count()
    if eleves_annee_derniere > 0:
        croissance_eleves = round(((nombre_eleves_total - eleves_annee_derniere) / eleves_annee_derniere) * 100, 1)
    else:
        croissance_eleves = 0
    
    # === STATISTIQUES DES ENSEIGNANTS ===
    nombre_enseignants = Professeur.objects.filter(etablissement=etablissement, actif=True).count()
    
    # === STATISTIQUES DU PERSONNEL ADMINISTRATIF ===
    nombre_personnel_admin = PersonnelAdministratif.objects.filter(
        etablissement=etablissement,
        actif=True
    ).count()
    
    # Calculer le changement de personnel cette année
    personnel_annee_derniere = PersonnelAdministratif.objects.filter(
        etablissement=etablissement,
        date_creation__lte=date_annee_derniere,
        actif=True
    ).count()
    changement_personnel = nombre_personnel_admin - personnel_annee_derniere
    
    # === STATISTIQUES DES CLASSES ===
    nombre_classes = Classe.objects.filter(etablissement=etablissement, actif=True).count()
    
    # === ÉVALUATIONS EN COURS ===
    # Récupérer les évaluations/devoirs de la semaine en cours
    date_debut_semaine = datetime.now() - timedelta(days=datetime.now().weekday())
    
    # Pour établissements primaires
    if etablissement.type_etablissement == 'primary':
        from ..model.evaluation_primaire_model import EvaluationPrimaire
        evaluations_semaine = EvaluationPrimaire.objects.filter(
            professeur__etablissement=etablissement,
            date_evaluation__gte=date_debut_semaine,
            actif=True
        ).count()
    else:
        # Pour collège/lycée (0 si pas de modèle Evaluation)
        evaluations_semaine = 0
    
    # === BULLETINS PUBLIÉS ===
    # Compter les moyennes soumises ce trimestre (approximation des bulletins)
    moyennes_soumises = Moyenne.objects.filter(
        eleve__etablissement=etablissement,
        soumis=True,
        actif=True
    ).count()
    
    # === ALERTES ===
    # Compter les élèves avec un taux de présence < 80% ou moyenne < 10
    from ..model.presence_model import Presence
    from django.db.models import Q
    
    alertes_count = 0
    
    # Alertes de présence (élèves avec beaucoup d'absences ce mois)
    date_debut_mois = datetime.now().replace(day=1)
    eleves_avec_absences = 0
    for eleve in eleves[:100]:  # Limiter pour la performance
        absences = Presence.objects.filter(
            eleve=eleve,
            date__gte=date_debut_mois,
            statut__in=['absent', 'absent_justifie']
        ).count()
        if absences >= 5:
            eleves_avec_absences += 1
    
    alertes_count = eleves_avec_absences
    
    # === TAUX DE RÉUSSITE ===
    # Calculer le taux basé sur les moyennes >= 10/20
    moyennes_valides = Moyenne.objects.filter(
        eleve__etablissement=etablissement,
        soumis=True,
        actif=True
    ).exclude(moyenne__isnull=True)
    
    if moyennes_valides.exists():
        moyennes_reussies = moyennes_valides.filter(moyenne__gte=10).count()
        total_moyennes = moyennes_valides.count()
        taux_reussite = round((moyennes_reussies / total_moyennes) * 100) if total_moyennes > 0 else 0
    else:
        taux_reussite = 0
    
    # === RESSOURCES PÉDAGOGIQUES ===
    # 0 si pas encore de table dédiée
    ressources_pedagogiques = 0
    
    # === DISTINCTIONS ===
    # 0 si pas encore de table dédiée
    distinctions = 0
    
    # === DERNIERS ÉLÈVES INSCRITS ===
    derniers_eleves = eleves.order_by('-date_inscription')[:2]
    
    # === DERNIERS PERSONNELS AJOUTÉS ===
    derniers_personnels = PersonnelAdministratif.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('-date_creation')[:2]
    
    # === DERNIÈRES MOYENNES PUBLIÉES ===
    dernieres_moyennes = Moyenne.objects.filter(
        eleve__etablissement=etablissement,
        soumis=True,
        actif=True
    ).select_related('eleve', 'classe', 'matiere').order_by('-date_calcul')[:2]
    
    # === DERNIÈRES ÉVALUATIONS ===
    if etablissement.type_etablissement == 'primary':
        from ..model.evaluation_primaire_model import EvaluationPrimaire
        dernieres_evaluations = EvaluationPrimaire.objects.filter(
            professeur__etablissement=etablissement,
            actif=True
        ).select_related('classe', 'matiere').order_by('-date_evaluation')[:2]
    else:
        from ..model.evaluation_model import Evaluation
        dernieres_evaluations = Evaluation.objects.filter(
            professeur__etablissement=etablissement,
            actif=True
        ).select_related('classe', 'matiere').order_by('-date_evaluation')[:2]
    
    # Préparer le contexte avec les données de l'établissement
    context = {
        'etablissement': etablissement,
        
        # Statistiques principales
        'stats': {
            'nombre_eleves': nombre_eleves_total,
            'croissance_eleves': croissance_eleves,
            'nombre_enseignants': nombre_enseignants,
            'nombre_personnel_admin': nombre_personnel_admin,
            'changement_personnel': changement_personnel,
            'nombre_classes': nombre_classes,
            'evaluations_semaine': evaluations_semaine,
            'bulletins_publies': moyennes_soumises,
            'alertes': alertes_count,
            'taux_reussite': taux_reussite,
            'ressources_pedagogiques': ressources_pedagogiques,
            'distinctions': distinctions,
        },
        
        # Dernières activités
        'derniers_eleves': derniers_eleves,
        'derniers_personnels': derniers_personnels,
        'dernieres_moyennes': dernieres_moyennes,
        'dernieres_evaluations': dernieres_evaluations,
    }
    
    return render(request, 'school_admin/directeur/dashboard_directeur.html', context)


@login_required
def facturation_directeur(request):
    """
    Vue de la page de facturation pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer toutes les factures de l'établissement
    facturations = Facturation.objects.filter(etablissement=etablissement).order_by('-date_creation')
    
    # Filtres
    statut_filter = request.GET.get('statut', '')
    type_filter = request.GET.get('type', '')
    
    if statut_filter:
        facturations = facturations.filter(statut=statut_filter)
    if type_filter:
        facturations = facturations.filter(type_facture=type_filter)
    
    # Statistiques détaillées
    stats = {
        'total_factures': facturations.count(),
        'montant_total': facturations.aggregate(total=Sum('montant_total'))['total'] or 0,
        'en_attente': facturations.filter(statut='en_attente').count(),
        'payees': facturations.filter(statut='paye').count(),
        'en_retard': facturations.filter(statut='en_retard').count(),
        'annulees': facturations.filter(statut='annule').count(),
    }
    
    # Montants par statut
    montants_par_statut = {}
    for statut, _ in Facturation.STATUT_CHOICES:
        montant = facturations.filter(statut=statut).aggregate(total=Sum('montant_total'))['total'] or 0
        montants_par_statut[statut] = montant
    
    # Factures urgentes (en retard ou échéance proche)
    factures_urgentes = []
    for facture in facturations.filter(statut__in=['en_attente', 'en_retard']):
        if facture.est_urgente or facture.est_en_retard():
            factures_urgentes.append(facture)
    
    # Modules activés et inactifs
    modules_info = {
        'gestion_eleves': {'nom': 'Gestion des élèves', 'actif': etablissement.module_gestion_eleves, 'prix': 0},
        'notes_evaluations': {'nom': 'Notes et évaluations', 'actif': etablissement.module_notes_evaluations, 'prix': 0},
        'emploi_temps': {'nom': 'Emploi du temps', 'actif': etablissement.module_emploi_temps, 'prix': 0},
        'gestion_personnel': {'nom': 'Gestion du personnel', 'actif': etablissement.module_gestion_personnel, 'prix': 0},
        'surveillance': {'nom': 'Surveillance et sécurité', 'actif': etablissement.module_surveillance, 'prix': 0},
        'communication': {'nom': 'Communication parents', 'actif': etablissement.module_communication, 'prix': 0},
        'orientation': {'nom': 'Orientation scolaire', 'actif': etablissement.module_orientation, 'prix': 0},
        'formation': {'nom': 'Formation continue', 'actif': etablissement.module_formation, 'prix': 0},
        'transport_scolaire': {'nom': 'Transport scolaire', 'actif': etablissement.module_transport_scolaire, 'prix': 0},
        'cantine': {'nom': 'Gestion de la cantine', 'actif': etablissement.module_cantine, 'prix': 0},
        'bibliotheque': {'nom': 'Gestion de la bibliothèque', 'actif': etablissement.module_bibliotheque, 'prix': 0},
        'sante': {'nom': 'Suivi médical', 'actif': etablissement.module_sante, 'prix': 0},
        'activites': {'nom': 'Activités extra-scolaires', 'actif': etablissement.module_activites, 'prix': 0},
        'comptabilite': {'nom': 'Comptabilité', 'actif': etablissement.module_comptabilite, 'prix': 0},
        'censeurs': {'nom': 'Censeurs', 'actif': etablissement.module_censeurs, 'prix': 0},
    }
    
    # Calculer le montant total théorique
    nombre_eleves_total = Eleve.objects.filter(etablissement=etablissement).count()
    montant_par_eleve = etablissement.montant_par_eleve
    montant_total_theorique = nombre_eleves_total * montant_par_eleve
    
    # Statistiques du personnel
    from ..model.personnel_administratif_model import PersonnelAdministratif
    nombre_personnel_admin = PersonnelAdministratif.objects.filter(etablissement=etablissement).count()
    nombre_enseignants = 0  # À implémenter quand le modèle enseignant sera créé
    nombre_classes = 0  # À implémenter quand le modèle classe sera créé
    
    context = {
        'etablissement': etablissement,
        'facturations': facturations,
        'stats': stats,
        'montants_par_statut': montants_par_statut,
        'factures_urgentes': factures_urgentes,
        'modules_info': modules_info,
        'statut_choices': Facturation.STATUT_CHOICES,
        'type_choices': Facturation.TYPE_FACTURE_CHOICES,
        'statut_filter': statut_filter,
        'type_filter': type_filter,
        'montant_par_eleve': montant_par_eleve,
        'nombre_eleves_total': nombre_eleves_total,
        'montant_total_theorique': montant_total_theorique,
        'nombre_personnel_admin': nombre_personnel_admin,
        'nombre_enseignants': nombre_enseignants,
        'nombre_classes': nombre_classes,
    }
    
    return render(request, 'school_admin/directeur/facturation_directeur.html', context)


@login_required
def gestion_pedagogique(request):
    """
    Vue de la page de gestion pédagogique pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
   
    return render(request, 'school_admin/directeur/gestion_pedagogique.html')


@login_required
def gestion_eleves(request):
    """
    Vue de la page de gestion des élèves pour les directeurs d'établissement
    """
      # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
  
    return render(request, 'school_admin/directeur/gestion_eleves.html')


@login_required
def notes_et_resultats(request):
    """
    Page de visualisation des notes et résultats par classe et par matière
    Adaptée pour le primaire et le collège/lycée
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Note, Evaluation
    from ..model.releve_notes_model import ReleveNotes
    from ..model.affectation_model import AffectationProfesseur
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from ..model.note_primaire_model import MoyenneMatierePrimaire
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    import re
    from collections import defaultdict
    
    # Détecter le type d'établissement
    est_primaire = etablissement.type_etablissement in ['primaire', 'primary']
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau numérique
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "6eme", "5eme", "CM1", etc.
        else:
            categorie = nom
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'nombre_classes': 0,
            }
        
        if est_primaire:
            # LOGIQUE PRIMAIRE
            # Récupérer tous les élèves de la classe
            eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
            
            # Récupérer la période active
            periode_active = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True
            ).first()
            
            # Récupérer toutes les matières du primaire de l'établissement
            # (peu importe si un professeur est affecté ou non)
            matieres = Matiere.objects.filter(
                etablissement=etablissement,
                niveau__in=['primaire', 'tous']
            ).order_by('nom')
            
            # Préparer les données pour chaque élève avec toutes les matières
            eleves_data = []
            for eleve in eleves:
                eleve_info = {
                    'eleve': eleve,
                    'matieres': {},
                    'nombre_matieres_avec_moyenne': 0,
                }
                
                # Pour chaque matière, récupérer la moyenne si elle existe
                for matiere in matieres:
                    moyenne_obj = None
                    if periode_active:
                        moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            periode_scolaire=periode_active
                        ).first()
                    
                    # CONDITION PRIMAIRE : Le champ soumis est directement sur MoyenneMatierePrimaire
                    moyenne_soumise = moyenne_obj and moyenne_obj.soumis
                    
                    # CONDITION : Afficher la moyenne SEULEMENT si elle est soumise
                    eleve_info['matieres'][matiere.nom] = {
                        'moyenne': moyenne_obj.moyenne if moyenne_soumise else None,
                        'nombre_notes': moyenne_obj.nombre_notes if moyenne_obj else 0,
                        'releve_soumis': moyenne_soumise,
                    }
                    
                    if moyenne_obj and moyenne_obj.moyenne and moyenne_soumise:
                        eleve_info['nombre_matieres_avec_moyenne'] += 1
                
                eleves_data.append(eleve_info)
            
            classe_info = {
                'classe': classe,
                'eleves_data': eleves_data,
                'matieres': [m.nom for m in matieres],
                'nombre_eleves': eleves.count(),
                'est_primaire': True,
            }
        else:
            # LOGIQUE COLLÈGE/LYCÉE - Utilisation du modèle Moyenne
            from ..model.moyenne_model import Moyenne
            
            # Récupérer la période active
            periode_active = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True
            ).first()
            
            # Récupérer TOUTES les matières de l'établissement pour collège/lycée
            toutes_matieres = Matiere.objects.filter(
                etablissement=etablissement,
                niveau__in=['college', 'lycee', 'tous'],
                actif=True
            ).order_by('nom')
            
            # Récupérer tous les élèves de la classe
            eleves = Eleve.objects.filter(classe=classe, actif=True)
            
            # Préparer les données pour chaque élève
            eleves_data = []
            for eleve in eleves:
                eleve_info = {
                    'eleve': eleve,
                    'matieres_moyennes': {},
                }
                
                # Pour chaque matière, récupérer la moyenne si elle existe
                for matiere in toutes_matieres:
                    moyenne_obj = None
                    if periode_active:
                        moyenne_obj = Moyenne.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            periode=str(periode_active.id),
                            actif=True
                        ).first()
                    
                    # Afficher la moyenne SEULEMENT si elle est soumise
                    moyenne_soumise = moyenne_obj and moyenne_obj.soumis
                    moyenne_value = moyenne_obj.moyenne if moyenne_soumise and moyenne_obj.moyenne else None
                    
                    eleve_info['matieres_moyennes'][matiere.nom] = {
                        'moyenne': moyenne_value,
                        'soumis': moyenne_soumise,
                    }
                
                eleves_data.append(eleve_info)
            
            # Calculer une moyenne temporaire pour le tri (basée sur les moyennes disponibles)
            for eleve_info in eleves_data:
                moyennes_valides = [
                    data['moyenne'] for data in eleve_info['matieres_moyennes'].values()
                    if data['moyenne'] is not None
                ]
                eleve_info['moyenne_tri'] = (
                    round(sum(moyennes_valides) / len(moyennes_valides), 2)
                    if moyennes_valides else None
                )
            
            # Trier par moyenne décroissante (None en dernier)
            eleves_data.sort(key=lambda x: (x['moyenne_tri'] is None, -x['moyenne_tri'] if x['moyenne_tri'] is not None else 0))
            
            classe_info = {
                'classe': classe,
                'eleves_data': eleves_data,
                'matieres': list(toutes_matieres),
                'nombre_eleves': eleves.count(),
                'est_primaire': False,
            }
        
        classes_grouped[categorie]['classes'].append(classe_info)
        classes_grouped[categorie]['total_eleves'] += classe_info['nombre_eleves']
        classes_grouped[categorie]['nombre_classes'] += 1
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': classes_grouped,
        'est_primaire': est_primaire,
    }
    
    return render(request, 'school_admin/directeur/notes_et_resultats.html', context)


@login_required
def suivi_presence(request):
    """
    Page de suivi des présences par classe et par mois
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.presence_model import Presence
    import re
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau numérique
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "6eme", "5eme", etc.
        else:
            categorie = nom
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'nombre_classes': 0,
            }
        
        # Récupérer tous les élèves de la classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        # Récupérer les mois distincts où il y a des données de présence pour cette classe
        presences_classe = Presence.objects.filter(classe=classe).values('date__month', 'date__year').distinct().order_by('date__year', 'date__month')
        
        # Créer une liste des mois disponibles
        mois_disponibles = []
        for p in presences_classe:
            date_mois = datetime(p['date__year'], p['date__month'], 1)
            mois_disponibles.append({
                'numero': p['date__month'],
                'annee': p['date__year'],
                'nom': date_mois.strftime('%B'),
                'nom_court': date_mois.strftime('%b'),
            })
        
        # Pour chaque mois, calculer les statistiques de présence pour chaque élève
        mois_presences = {}
        
        for mois in mois_disponibles:
            eleves_presences = []
            
            for eleve in eleves:
                # Récupérer les présences de l'élève pour ce mois
                presences = Presence.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    date__month=mois['numero'],
                    date__year=mois['annee']
                )
                
                total_jours = presences.count()
                presents = presences.filter(statut='present').count()
                absents = presences.filter(statut='absent').count()
                absents_justifies = presences.filter(statut='absent_justifie').count()
                retards = presences.filter(statut='retard').count()
                
                # Calculer le taux de présence
                if total_jours > 0:
                    taux_presence = round((presents / total_jours) * 100, 2)
                else:
                    taux_presence = None
                
                eleves_presences.append({
                    'eleve': eleve,
                    'total_jours': total_jours,
                    'presents': presents,
                    'absents': absents,
                    'absents_justifies': absents_justifies,
                    'retards': retards,
                    'taux_presence': taux_presence,
                })
            
            # Trier par taux de présence décroissant (None en dernier)
            eleves_presences.sort(key=lambda x: (x['taux_presence'] is None, -x['taux_presence'] if x['taux_presence'] is not None else 0))
            
            mois_presences[f"{mois['numero']}_{mois['annee']}"] = {
                'mois': mois,
                'eleves_presences': eleves_presences,
            }
        
        classe_info = {
            'classe': classe,
            'mois_presences': mois_presences,
            'mois_disponibles': mois_disponibles,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_info)
        classes_grouped[categorie]['total_eleves'] += classe_info['nombre_eleves']
        classes_grouped[categorie]['nombre_classes'] += 1
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': classes_grouped,
    }
    
    return render(request, 'school_admin/directeur/suivi_presence.html', context)


@login_required
def gestion_etablissement(request):
    """
    Vue de la page de gestion de l'établissement pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
   
    return render(request, 'school_admin/directeur/gestion_etablissement.html')


@login_required
def gestion_periodes_scolaires(request):
    """
    Vue pour la gestion des périodes scolaires (trimestres, semestres)
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer l'année scolaire en cours (septembre N à août N+1)
    from datetime import date
    aujourdhui = date.today()
    if aujourdhui.month >= 9:
        annee_debut = aujourdhui.year
    else:
        annee_debut = aujourdhui.year - 1
    annee_scolaire_actuelle = f"{annee_debut}-{annee_debut + 1}"
    
    # Gestion de l'ajout d'une nouvelle période
    if request.method == 'POST':
        from ..model.periode_model import PeriodeScolaire
        from django.db import transaction
        from datetime import datetime
        
        try:
            with transaction.atomic():
                nom_periode = request.POST.get('nom_periode', '').strip()
                type_periode = request.POST.get('type_periode', 'trimestre')
                date_debut_str = request.POST.get('date_debut', '')
                date_fin_str = request.POST.get('date_fin', '')
                annee_scolaire = request.POST.get('annee_scolaire', annee_scolaire_actuelle)
                est_active = request.POST.get('est_active') == 'on'
                
                # Validations
                if not all([nom_periode, date_debut_str, date_fin_str, annee_scolaire]):
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('directeur:gestion_periodes_scolaires')
                
                # Convertir les dates string en objets date
                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                
                # Créer la période
                periode = PeriodeScolaire.objects.create(
                    etablissement=etablissement,
                    nom_periode=nom_periode,
                    type_periode=type_periode,
                    date_debut=date_debut,
                    date_fin=date_fin,
                    annee_scolaire=annee_scolaire,
                    est_active=est_active
                )
                
                messages.success(request, f"La période '{periode.nom_periode}' a été créée avec succès.")
                return redirect('directeur:gestion_periodes_scolaires')
                
        except ValidationError as e:
            messages.error(request, f"Erreur de validation : {e}")
            return redirect('directeur:gestion_periodes_scolaires')
        except Exception as e:
            messages.error(request, f"Erreur lors de la création de la période : {str(e)}")
            return redirect('directeur:gestion_periodes_scolaires')
    
    # Récupérer toutes les périodes de l'établissement
    from ..model.periode_model import PeriodeScolaire
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement
    ).order_by('-annee_scolaire', 'date_debut')
    
    # Grouper les périodes par année scolaire
    periodes_par_annee = {}
    for periode in periodes:
        if periode.annee_scolaire not in periodes_par_annee:
            periodes_par_annee[periode.annee_scolaire] = []
        periodes_par_annee[periode.annee_scolaire].append(periode)
    
    context = {
        'user': etablissement,
        'etablissement': etablissement,
        'periodes': periodes,
        'periodes_par_annee': periodes_par_annee,
        'annee_scolaire_actuelle': annee_scolaire_actuelle,
    }
    
    return render(request, 'school_admin/directeur/gestion_periodes_scolaires.html', context)


@login_required
def api_details_notes_matiere(request):
    """
    API pour récupérer les détails des notes d'une matière pour une classe
    Retourne les notes retenues, la note d'examen et la moyenne pour chaque élève
    """
    from django.http import JsonResponse
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    from ..model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire
    from ..model.evaluation_primaire_model import EvaluationPrimaire
    from ..model.note_examen_model import NoteExamen
    from ..model.session_examen_model import SessionExamen
    from ..model.creneau_examen_model import CreneauExamen
    
    # Vérifier que c'est une requête AJAX
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Requête invalide'}, status=400)
    
    # Récupérer les paramètres
    classe_id = request.GET.get('classe_id')
    matiere_nom = request.GET.get('matiere_nom')
    periode_id = request.GET.get('periode_id')
    
    if not all([classe_id, matiere_nom, periode_id]):
        return JsonResponse({'success': False, 'message': 'Paramètres manquants'}, status=400)
    
    try:
        # Récupérer les objets
        classe = Classe.objects.get(id=classe_id)
        matiere = Matiere.objects.get(nom=matiere_nom, etablissement=classe.etablissement)
        periode = PeriodeScolaire.objects.get(id=periode_id)
        
        # Récupérer tous les élèves de la classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        eleves_data = []
        for eleve in eleves:
            # Récupérer la moyenne
            moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=matiere,
                periode_scolaire=periode
            ).first()
            
            # Si pas de moyenne, passer cet élève
            if not moyenne_obj or not moyenne_obj.moyenne:
                continue
            
            # Récupérer TOUTES les notes de l'élève pour cette matière
            # On affiche toutes les notes (retenues ou non) pour la transparence
            notes_evaluations = NotePrimaire.objects.filter(
                eleve=eleve,
                evaluation_primaire__classe=classe,
                evaluation_primaire__matiere=matiere,
                evaluation_primaire__periode_scolaire=periode,
                absent=False
            ).select_related('evaluation_primaire').order_by('-note')
            
            notes_retenues_list = []
            for note in notes_evaluations:
                # Utiliser la propriété note_sur_20 qui calcule la note sur 20
                try:
                    note_valeur = note.note_sur_20
                    if note_valeur is not None:
                        notes_retenues_list.append({
                            'titre': note.evaluation_primaire.titre,
                            'note': float(note_valeur),
                            'bareme': 20,
                            'date': note.evaluation_primaire.date_evaluation.strftime('%d/%m/%Y') if note.evaluation_primaire.date_evaluation else '',
                            'retenue': note.retenue
                        })
                except Exception:
                    pass
            
            # Récupérer la note d'examen si elle existe (basée sur session)
            note_examen = None
            # Trouver les sessions d'examen pour cette classe et matière
            sessions = SessionExamen.objects.filter(
                etablissement=classe.etablissement,
                periode=periode,
                classes=classe,
                matieres=matiere,
                actif=True
            ).distinct()
            
            for session in sessions:
                # Récupérer la note d'examen de l'élève basée sur (eleve, session, matiere)
                note_examen_obj = NoteExamen.objects.filter(
                    session_examen=session,
                    eleve=eleve,
                    matiere=matiere
                ).first()
                
                if note_examen_obj and not note_examen_obj.absent and note_examen_obj.note:
                    note_examen = float(note_examen_obj.note)
                    break
            
            # Initiales de l'élève
            initiales = ''
            if eleve.prenom:
                initiales = eleve.prenom[0].upper()
            if eleve.nom:
                initiales += eleve.nom[0].upper()
            
            eleves_data.append({
                'nom': eleve.nom_complet,
                'initiales': initiales,
                'notes_retenues': notes_retenues_list,
                'note_examen': note_examen,
                'moyenne': float(moyenne_obj.moyenne)
            })
        
        # Trier par moyenne décroissante
        eleves_data.sort(key=lambda x: x['moyenne'], reverse=True)
        
        return JsonResponse({
            'success': True,
            'eleves': eleves_data,
            'matiere': matiere_nom,
            'classe': classe.nom,
            'periode': periode.nom_periode
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def api_details_notes_matiere_secondaire(request):
    """
    API pour récupérer les détails des notes d'une matière pour une classe (SECONDAIRE)
    Retourne les notes retenues, la note d'examen et la moyenne pour chaque élève
    Spécifique aux établissements de type lycée, collège, collège+lycée
    """
    from django.http import JsonResponse
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    from ..model.evaluation_model import Note
    from ..model.note_examen_model import NoteExamen
    from ..model.moyenne_model import Moyenne
    
    # Vérifier que c'est une requête AJAX
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Requête invalide'}, status=400)
    
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        return JsonResponse({'success': False, 'message': 'Accès non autorisé'}, status=403)
    
    etablissement = request.user
    
    # Vérifier que c'est un établissement secondaire
    if etablissement.type_etablissement not in ['lycée', 'collège', 'collège_lycée']:
        return JsonResponse({'success': False, 'message': 'Cette fonctionnalité est réservée aux établissements secondaires'}, status=403)
    
    # Récupérer les paramètres
    classe_id = request.GET.get('classe_id')
    matiere_nom = request.GET.get('matiere_nom')
    
    if not all([classe_id, matiere_nom]):
        return JsonResponse({'success': False, 'message': 'Paramètres manquants'}, status=400)
    
    try:
        # Récupérer les objets
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
        matiere = Matiere.objects.get(nom=matiere_nom, etablissement=etablissement)
        
        # Récupérer la période active
        periode = PeriodeScolaire.objects.filter(
            etablissement=etablissement,
            est_active=True
        ).first()
        
        if not periode:
            return JsonResponse({'success': False, 'message': 'Aucune période active trouvée'}, status=404)
        
        # Récupérer tous les élèves de la classe avec leurs moyennes
        eleves = Eleve.objects.filter(classe=classe, actif=True)
        
        eleves_data = []
        for eleve in eleves:
            # Récupérer la moyenne pour cette matière
            moyenne_obj = Moyenne.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=matiere,
                periode=str(periode.id),
                actif=True,
                soumis=True  # Seulement les moyennes soumises
            ).first()
            
            # Si pas de moyenne soumise, passer cet élève
            if not moyenne_obj or not moyenne_obj.moyenne:
                continue
            
            # Récupérer toutes les notes retenues pour cette matière
            notes_evaluations = Note.objects.filter(
                eleve=eleve,
                evaluation__matiere=matiere,
                evaluation__periode_scolaire=periode,
                retenue=True,
                absent=False
            ).select_related('evaluation').order_by('evaluation__date_evaluation')
            
            notes_retenues_list = []
            for note in notes_evaluations:
                notes_retenues_list.append({
                    'titre': note.evaluation.titre,
                    'note': float(note.note_sur_20),
                    'bareme': 20,
                    'date': note.evaluation.date_evaluation.strftime('%d/%m/%Y') if note.evaluation.date_evaluation else ''
                })
            
            # Récupérer la note d'examen pour cette matière
            note_examen_obj = NoteExamen.objects.filter(
                eleve=eleve,
                matiere=matiere,
                session_examen__periode=periode,
                session_examen__actif=True
            ).select_related('session_examen').first()
            
            note_examen = None
            if note_examen_obj and not note_examen_obj.absent:
                note_examen = float(note_examen_obj.note)
            
            # Ajouter les données de l'élève
            eleves_data.append({
                'id': eleve.id,
                'nom': eleve.nom_complet,
                'initiales': f"{eleve.prenom[0]}{eleve.nom[0]}" if eleve.prenom and eleve.nom else eleve.nom[:2].upper(),
                'notes_retenues': notes_retenues_list,
                'note_examen': note_examen,
                'moyenne': float(moyenne_obj.moyenne)
            })
        
        # Trier les élèves par moyenne décroissante
        eleves_data.sort(key=lambda x: x['moyenne'], reverse=True)
        
        return JsonResponse({
            'success': True,
            'eleves': eleves_data,
            'matiere': matiere_nom,
            'classe': classe.nom,
            'periode': periode.nom_periode
        })
        
    except Classe.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Classe non trouvée'}, status=404)
    except Matiere.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Matière non trouvée'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def imprimer_releve_notes(request, classe_id):
    """
    Vue pour l'impression du relevé de notes d'une classe
    Affiche un tableau professionnel avec en-tête de l'établissement et toutes les notes par matière
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Note, Evaluation
    from ..model.releve_notes_model import ReleveNotes
    from ..model.affectation_model import AffectationProfesseur
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from ..model.note_primaire_model import MoyenneMatierePrimaire
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    from collections import defaultdict
    
    try:
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:notes_et_resultats')
    
    # Détecter le type d'établissement
    est_primaire = etablissement.type_etablissement == 'primary'
    
    # Récupérer la période scolaire active
    periode = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    ).first()
    
    if not periode:
        messages.warning(request, "Aucune période scolaire active trouvée.")
        return redirect('directeur:notes_et_resultats')
    
    eleves = Eleve.objects.filter(classe=classe).order_by('nom', 'prenom')
    
    if est_primaire:
        # LOGIQUE PRIMAIRE
        # Récupérer TOUTES les matières de la classe
        matieres = classe.matieres.filter(actif=True).order_by('nom')
        
        # Si aucune matière n'est associée, récupérer les matières du niveau
        if not matieres.exists():
            matieres = Matiere.objects.filter(
                niveau__in=[classe.niveau, 'tous'],
                etablissement=etablissement,
                actif=True
            ).order_by('nom')
        
        # Préparer les données des élèves avec leurs moyennes par matière
        eleves_data = []
        for eleve in eleves:
            eleve_info = {
                'eleve': eleve,
                'matieres': {},
                'nombre_matieres_avec_moyenne': 0,
                'moyenne_generale': 0,
            }
            
            somme_moyennes = 0
            nombre_moyennes = 0
            
            for matiere in matieres:
                # Récupérer la moyenne de l'élève pour cette matière
                moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    periode_scolaire=periode
                ).first()
                
                # Vérifier si le relevé a été soumis
                releve_obj = ReleveNotes.objects.filter(
                    matiere=matiere,
                    classe=classe,
                    periode_scolaire=periode,
                    soumis=True
                ).first()
                
                moyenne_soumise = releve_obj is not None
                moyenne_value = moyenne_obj.moyenne if moyenne_obj and moyenne_soumise else None
                
                eleve_info['matieres'][matiere.nom] = {
                    'moyenne': moyenne_value,
                    'nombre_notes': moyenne_obj.nombre_notes if moyenne_obj else 0,
                    'releve_soumis': moyenne_soumise,
                }
                
                if moyenne_value is not None:
                    eleve_info['nombre_matieres_avec_moyenne'] += 1
                    somme_moyennes += float(moyenne_value)
                    nombre_moyennes += 1
            
            # Calculer la moyenne générale
            if nombre_moyennes > 0:
                eleve_info['moyenne_generale'] = round(somme_moyennes / nombre_moyennes, 2)
            
            eleves_data.append(eleve_info)
        
        # Trier les élèves par moyenne générale décroissante (pour le classement)
        eleves_data.sort(key=lambda x: x['moyenne_generale'] if x['moyenne_generale'] else 0, reverse=True)
        
        context = {
            'etablissement': etablissement,
            'classe': classe,
            'periode': periode,
            'eleves_data': eleves_data,
            'matieres': matieres,
            'nombre_eleves': eleves.count(),
            'nombre_matieres': matieres.count(),
            'est_primaire': True,
        }
    else:
        # LOGIQUE COLLÈGE/LYCÉE
        from ..model.moyenne_model import Moyenne
        from ..model.note_examen_model import NoteExamen
        
        # Récupérer TOUTES les matières de la classe
        matieres = classe.matieres.filter(actif=True).order_by('nom')
        
        # Si aucune matière n'est associée, récupérer les matières du niveau
        if not matieres.exists():
            matieres = Matiere.objects.filter(
                niveau__in=[classe.niveau, 'tous'],
                etablissement=etablissement,
                actif=True
            ).order_by('nom')
        
        # Préparer les données des élèves avec leurs moyennes par matière
        eleves_data = []
        for eleve in eleves:
            eleve_info = {
                'eleve': eleve,
                'matieres_moyennes': {},
                'moyenne_generale': 0,
                'total_coefficients': 0,
            }
            
            somme_ponderee = 0
            total_coefficients = 0
            
            for matiere in matieres:
                # Récupérer la moyenne de l'élève pour cette matière
                moyenne_obj = Moyenne.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    matiere=matiere,
                    periode=str(periode.id),
                    actif=True
                ).first()
                
                # Afficher la moyenne SEULEMENT si elle est soumise
                moyenne_soumise = moyenne_obj and moyenne_obj.soumis
                moyenne_value = moyenne_obj.moyenne if moyenne_soumise and moyenne_obj.moyenne else None
                
                eleve_info['matieres_moyennes'][matiere.nom] = {
                    'moyenne': moyenne_value,
                    'coefficient': matiere.coefficient,
                    'soumis': moyenne_soumise,
                }
                
                if moyenne_value is not None:
                    somme_ponderee += moyenne_value * matiere.coefficient
                    total_coefficients += matiere.coefficient
            
            # Calculer la moyenne générale
            if total_coefficients > 0:
                eleve_info['moyenne_generale'] = round(somme_ponderee / total_coefficients, 2)
                eleve_info['total_coefficients'] = total_coefficients
            
            eleves_data.append(eleve_info)
        
        # Trier les élèves par moyenne générale décroissante
        eleves_data.sort(key=lambda x: x['moyenne_generale'] if x['moyenne_generale'] else 0, reverse=True)
        
        context = {
            'etablissement': etablissement,
            'classe': classe,
            'periode': periode,
            'eleves_data': eleves_data,
            'matieres': matieres,
            'nombre_eleves': eleves.count(),
            'nombre_matieres': matieres.count(),
            'est_primaire': False,
        }
    
    return render(request, 'school_admin/directeur/imprimer_releve_notes.html', context)


@login_required
def gestion_administrative(request):
    """
    Page de gestion administrative pour les directeurs
    Génération de documents administratifs (certificats, attestations, etc.)
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    context = {
        'etablissement': etablissement,
    }
    
    return render(request, 'school_admin/directeur/gestion_administrative.html', context)


@login_required
def certificat_scolarite_liste(request):
    """
    Page listant tous les élèves pour générer des certificats de scolarité
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    import re
    from collections import defaultdict
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
    }
    
    return render(request, 'school_admin/directeur/certificat_scolarite_liste.html', context)


@login_required
def generer_certificat_scolarite(request, eleve_id):
    """
    Génère un certificat de scolarité pour un élève spécifique
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:certificat_scolarite_liste')
    
    # Informations pour le certificat
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
    }
    
    return render(request, 'school_admin/directeur/generer_certificat_scolarite.html', context)


@login_required
def convocation_liste(request):
    """
    Page listant tous les élèves pour générer des convocations
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    import re
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
    }
    
    return render(request, 'school_admin/directeur/convocation_liste.html', context)


@login_required
def generer_convocation(request, eleve_id):
    """
    Affiche le formulaire de convocation pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:convocation_liste')
    
    if request.method == 'POST':
        # Traiter le formulaire et sauvegarder dans la base de données
        objet = request.POST.get('objet', '')
        motif = request.POST.get('motif', '')
        date_convocation_str = request.POST.get('date_convocation', '')
        heure_convocation_str = request.POST.get('heure_convocation', '')
        lieu = request.POST.get('lieu', 'Bureau du Directeur')
        
        # Validation simple
        if not all([objet, motif, date_convocation_str, heure_convocation_str]):
            messages.error(request, "Veuillez remplir tous les champs obligatoires.")
            context = {
                'etablissement': etablissement,
                'eleve': eleve,
                'form_data': request.POST,
            }
            return render(request, 'school_admin/directeur/formulaire_convocation.html', context)
        
        try:
            # Convertir les chaînes en objets date et time
            from datetime import datetime as dt
            date_convocation = dt.strptime(date_convocation_str, '%Y-%m-%d').date()
            heure_convocation = dt.strptime(heure_convocation_str, '%H:%M').time()
            
            # Créer et sauvegarder la convocation
            from ..model.convocation_model import Convocation
            convocation = Convocation.objects.create(
                eleve=eleve,
                etablissement=etablissement,
                objet=objet,
                motif=motif,
                date_convocation=date_convocation,
                heure_convocation=heure_convocation,
                lieu=lieu,
                statut='en_attente'
            )
            
            messages.success(request, "Convocation créée avec succès.")
            return redirect('directeur:voir_convocations_eleve', eleve_id=eleve_id)
            
        except ValueError as e:
            messages.error(request, f"Erreur dans le format de la date ou de l'heure: {e}")
            context = {
                'etablissement': etablissement,
                'eleve': eleve,
                'form_data': request.POST,
            }
            return render(request, 'school_admin/directeur/formulaire_convocation.html', context)
    
    # Afficher le formulaire
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
    }
    
    return render(request, 'school_admin/directeur/formulaire_convocation.html', context)


@login_required
def voir_convocations_eleve(request, eleve_id):
    """
    Affiche toutes les convocations d'un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from ..model.convocation_model import Convocation
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer toutes les convocations de l'élève
    convocations = Convocation.objects.filter(
        eleve=eleve,
        actif=True
    ).order_by('-date_convocation', '-heure_convocation')
    
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'convocations': convocations,
    }
    
    return render(request, 'school_admin/directeur/voir_convocations_eleve.html', context)


@login_required
def apercu_convocation(request, convocation_id):
    """
    Génère l'aperçu de la convocation pour impression
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.convocation_model import Convocation
    from datetime import datetime
    
    try:
        convocation = Convocation.objects.select_related('eleve', 'eleve__classe').get(
            id=convocation_id,
            etablissement=etablissement
        )
    except Convocation.DoesNotExist:
        messages.error(request, "Convocation non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Informations pour la convocation
    context = {
        'etablissement': etablissement,
        'eleve': convocation.eleve,
        'convocation': convocation,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
    }
    
    return render(request, 'school_admin/directeur/apercu_convocation.html', context)


@login_required
def convocation_classe(request, classe_id):
    """
    Formulaire pour convoquer toute une classe
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.convocation_model import Convocation
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(
        classe=classe,
        etablissement=etablissement,
        actif=True
    ).order_by('nom', 'prenom')
    
    if request.method == 'POST':
        # Traiter le formulaire et créer les convocations pour tous les élèves
        objet = request.POST.get('objet', '')
        motif = request.POST.get('motif', '')
        date_convocation_str = request.POST.get('date_convocation', '')
        heure_convocation_str = request.POST.get('heure_convocation', '')
        lieu = request.POST.get('lieu', 'Bureau du Directeur')
        
        # Validation simple
        if not all([objet, motif, date_convocation_str, heure_convocation_str]):
            messages.error(request, "Veuillez remplir tous les champs obligatoires.")
            context = {
                'etablissement': etablissement,
                'classe': classe,
                'eleves': eleves,
                'nombre_eleves': eleves.count(),
                'form_data': request.POST,
            }
            return render(request, 'school_admin/directeur/formulaire_convocation_classe.html', context)
        
        try:
            # Convertir les chaînes en objets date et time
            from datetime import datetime as dt
            date_convocation = dt.strptime(date_convocation_str, '%Y-%m-%d').date()
            heure_convocation = dt.strptime(heure_convocation_str, '%H:%M').time()
            
            # Créer les convocations pour tous les élèves de la classe
            convocations_creees = []
            for eleve in eleves:
                convocation = Convocation.objects.create(
                    eleve=eleve,
                    etablissement=etablissement,
                    objet=objet,
                    motif=motif,
                    date_convocation=date_convocation,
                    heure_convocation=heure_convocation,
                    lieu=lieu,
                    statut='en_attente',
                    convocation_classe=True  # Marquer comme convocation de classe
                )
                convocations_creees.append(convocation)
            
            messages.success(request, f"{len(convocations_creees)} convocation(s) créée(s) avec succès pour la classe {classe.nom}.")
            return redirect('directeur:convocations_classe_liste', classe_id=classe_id)
            
        except ValueError as e:
            messages.error(request, f"Erreur dans le format de la date ou de l'heure: {e}")
            context = {
                'etablissement': etablissement,
                'classe': classe,
                'eleves': eleves,
                'nombre_eleves': eleves.count(),
                'form_data': request.POST,
            }
            return render(request, 'school_admin/directeur/formulaire_convocation_classe.html', context)
    
    # Afficher le formulaire
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleves': eleves,
        'nombre_eleves': eleves.count(),
    }
    
    return render(request, 'school_admin/directeur/formulaire_convocation_classe.html', context)


@login_required
def convocations_classe_liste(request, classe_id):
    """
    Affiche toutes les convocations de classe (regroupées par convocation, pas par élève)
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.convocation_model import Convocation
    from collections import defaultdict
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer toutes les convocations de classe pour cette classe
    # On regroupe par (objet, motif, date, heure, lieu) pour éviter les doublons
    convocations_classe = Convocation.objects.filter(
        eleve__classe=classe,
        etablissement=etablissement,
        actif=True,
        convocation_classe=True
    ).select_related('eleve').order_by('-date_convocation', '-heure_convocation')
    
    # Regrouper les convocations identiques (même objet, date, heure, lieu)
    convocations_groupees = {}
    for conv in convocations_classe:
        cle = f"{conv.objet}_{conv.date_convocation}_{conv.heure_convocation}_{conv.lieu}"
        if cle not in convocations_groupees:
            convocations_groupees[cle] = {
                'convocation': conv,
                'eleves': [],
                'nombre_eleves': 0
            }
        convocations_groupees[cle]['eleves'].append(conv.eleve)
        convocations_groupees[cle]['nombre_eleves'] += 1
    
    # Convertir en liste pour le template
    convocations_list = list(convocations_groupees.values())
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'convocations': convocations_list,
        'nombre_convocations': len(convocations_list),
    }
    
    return render(request, 'school_admin/directeur/convocations_classe_liste.html', context)


@login_required
def imprimer_convocations_classe(request, classe_id):
    """
    Imprime toutes les convocations de classe d'une seule session (toutes les convocations d'une même date/heure)
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.convocation_model import Convocation
    from datetime import datetime
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer l'ID de la convocation depuis les paramètres GET
    convocation_id = request.GET.get('convocation_id')
    
    if not convocation_id:
        messages.error(request, "ID de convocation manquant.")
        return redirect('directeur:convocations_classe_liste', classe_id=classe_id)
    
    try:
        # Récupérer la convocation de référence
        convocation_ref = Convocation.objects.get(id=convocation_id, actif=True, convocation_classe=True)
        
        # Récupérer toutes les convocations identiques (même objet, date, heure, lieu)
        convocations = Convocation.objects.filter(
            eleve__classe=classe,
            etablissement=etablissement,
            actif=True,
            convocation_classe=True,
            objet=convocation_ref.objet,
            date_convocation=convocation_ref.date_convocation,
            heure_convocation=convocation_ref.heure_convocation,
            lieu=convocation_ref.lieu
        ).select_related('eleve', 'eleve__classe').order_by('eleve__nom', 'eleve__prenom')
        
    except Convocation.DoesNotExist:
        messages.error(request, "Convocation non trouvée.")
        return redirect('directeur:convocations_classe_liste', classe_id=classe_id)
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'convocations': convocations,
        'convocation_ref': convocation_ref,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',
    }
    
    return render(request, 'school_admin/directeur/imprimer_convocations_classe.html', context)


@login_required
def attestation_reussite_liste(request):
    """
    Page listant tous les élèves pour générer des attestations de réussite
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    import re
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
    }
    
    return render(request, 'school_admin/directeur/attestation_reussite_liste.html', context)


@login_required
def generer_attestation_reussite(request, eleve_id):
    """
    Génère une attestation de réussite pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:attestation_reussite_liste')
    
    # Informations pour l'attestation
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
    }
    
    return render(request, 'school_admin/directeur/generer_attestation_reussite.html', context)


@login_required
def attestation_conduite_liste(request):
    """
    Page listant tous les élèves pour générer des attestations de conduite
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    import re
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
    }
    
    return render(request, 'school_admin/directeur/attestation_conduite_liste.html', context)


@login_required
def generer_attestation_conduite(request, eleve_id):
    """
    Génère une attestation de conduite pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:attestation_conduite_liste')
    
    # Informations pour l'attestation
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
    }
    
    return render(request, 'school_admin/directeur/generer_attestation_conduite.html', context)


@login_required
def fiche_inscription_liste(request):
    """
    Page listant tous les élèves pour générer des fiches d'inscription/réinscription
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    import re
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
    }
    
    return render(request, 'school_admin/directeur/fiche_inscription_liste.html', context)


@login_required
def generer_fiche_inscription(request, eleve_id):
    """
    Génère une fiche d'inscription/réinscription pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:fiche_inscription_liste')
    
    # Informations pour la fiche
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
    }
    
    return render(request, 'school_admin/directeur/generer_fiche_inscription.html', context)


@login_required
def imprimer_fiches_classe(request, classe_id):
    """
    Génère toutes les fiches d'inscription pour une classe entière
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from datetime import datetime
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:fiche_inscription_liste')
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(
        classe=classe,
        actif=True
    ).order_by('nom', 'prenom')
    
    if not eleves.exists():
        messages.warning(request, "Aucun élève dans cette classe.")
        return redirect('directeur:fiche_inscription_liste')
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleves': eleves,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',
    }
    
    return render(request, 'school_admin/directeur/imprimer_fiches_classe.html', context)


@login_required
def certificat_radiation_liste(request):
    """
    Page listant tous les élèves pour générer des certificats de radiation/transfert
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    import re
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
    }
    
    return render(request, 'school_admin/directeur/certificat_radiation_liste.html', context)


@login_required
def generer_certificat_radiation(request, eleve_id):
    """
    Génère un certificat de radiation/transfert pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:certificat_radiation_liste')
    
    # Informations pour le certificat
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
    }
    
    return render(request, 'school_admin/directeur/generer_certificat_radiation.html', context)


@login_required
def imprimer_liste_nominative(request, classe_id):
    """
    Génère une liste nominative imprimable des élèves d'une classe
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from datetime import datetime
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:liste_eleves')
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(
        classe=classe,
        actif=True
    ).order_by('nom', 'prenom')
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleves': eleves,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',
        'nombre_eleves': eleves.count(),
    }
    
    return render(request, 'school_admin/directeur/imprimer_liste_nominative.html', context)


@login_required
def imprimer_liste_presence(request, classe_id, mois_numero, mois_annee):
    """
    Génère une liste de présence imprimable pour une classe et un mois donné
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.presence_model import Presence
    from datetime import datetime
    from django.db.models import Q
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:suivi_presence')
    
    # Créer un objet mois avec les informations
    date_mois = datetime(mois_annee, mois_numero, 1)
    mois = {
        'numero': mois_numero,
        'annee': mois_annee,
        'nom': date_mois.strftime('%B').capitalize(),
    }
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Calculer les statistiques de présence pour chaque élève
    eleves_presences = []
    
    for eleve in eleves:
        presences = Presence.objects.filter(
            eleve=eleve,
            classe=classe,
            date__month=mois_numero,
            date__year=mois_annee
        )
        
        total_jours = presences.count()
        presents = presences.filter(statut='present').count()
        absents = presences.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
        absents_justifies = presences.filter(statut='absent_justifie').count()
        retards = presences.filter(statut='retard').count()
        
        # Calculer le taux de présence
        if total_jours > 0:
            taux_presence = (presents / total_jours) * 100
        else:
            taux_presence = 0
        
        eleves_presences.append({
            'eleve': eleve,
            'total_jours': total_jours,
            'presents': presents,
            'absents': absents,
            'absents_justifies': absents_justifies,
            'retards': retards,
            'taux_presence': round(taux_presence, 2)
        })
    
    # Trier par taux de présence décroissant
    eleves_presences.sort(key=lambda x: x['taux_presence'], reverse=True)
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'mois': mois,
        'eleves_presences': eleves_presences,
        'date_generation': datetime.now(),
        'nombre_eleves': len(eleves_presences),
    }
    
    return render(request, 'school_admin/directeur/imprimer_liste_presence.html', context)


def demandes_liaison_liste(request):
    """
    Liste des demandes de liaison parent-enfant pour le directeur
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer toutes les demandes pour les élèves de cet établissement
    demandes = DemandeLiaisonParent.objects.filter(
        eleve_valide__etablissement=etablissement
    ).select_related(
        'parent_demandeur',
        'eleve_valide',
        'eleve_valide__classe',
        'traite_par'
    ).order_by('-date_demande')
    
    # Compter les demandes par statut
    stats = {
        'total': demandes.count(),
        'en_attente': demandes.filter(statut='en_attente').count(),
        'bloquee': demandes.filter(statut='bloquee').count(),
        'reussie': demandes.filter(statut='reussie').count(),
        'echec': demandes.filter(statut='echec').count(),
        'approuvee': demandes.filter(statut='approuvee').count(),
        'refusee': demandes.filter(statut='refusee').count(),
    }
    
    context = {
        'etablissement': etablissement,
        'demandes': demandes,
        'stats': stats,
    }
    
    return render(request, 'school_admin/directeur/demandes_liaison_liste.html', context)


def approuver_demande_liaison(request, demande_id):
    """
    Approuver une demande de liaison parent-enfant
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer la demande
    demande = get_object_or_404(
        DemandeLiaisonParent,
        id=demande_id,
        eleve_valide__etablissement=etablissement
    )
    
    try:
        # Vérifier si un lien existe déjà
        # Vérifier si un LienFamilial existe déjà (actif ou non)
        lien_existant = LienFamilial.objects.filter(
            parent=demande.parent_demandeur,
            eleve=demande.eleve_valide
        ).first()
        
        if lien_existant:
            # Le lien existe déjà, on le réactive s'il était désactivé
            if not lien_existant.actif:
                lien_existant.actif = True
                lien_existant.statut = 'valide'
                lien_existant.save()
                print(f"[APPROBATION] Lien réactivé - Parent: {demande.parent_demandeur.nom_complet}, Élève: {demande.eleve_valide.nom_complet}")
            
            # Mettre à jour le statut de la demande
            demande.statut = 'approuvee'
            demande.date_traitement = timezone.now()
            demande.save()
            
            messages.success(
                request,
                f"✅ Demande approuvée avec succès ! Le lien entre {demande.parent_demandeur.nom_complet} et {demande.eleve_valide.nom_complet} a été créé."
            )
        else:
            # Si la demande est bloquée, la remettre en attente temporairement
            if demande.statut == 'bloquee':
                demande.statut = 'en_attente'
                demande.save()
            
            # Approuver la demande et créer le lien
            lien = demande.approuver(traite_par=None)
            demande.statut = 'approuvee'
            demande.save()
            
            messages.success(
                request,
                f"✅ Demande approuvée avec succès ! Le lien entre {demande.parent_demandeur.nom_complet} et {demande.eleve_valide.nom_complet} a été créé."
            )
    except Exception as e:
        messages.error(request, f"❌ Erreur lors de l'approbation : {str(e)}")
    
    return redirect('directeur:demandes_liaison_liste')


def rejeter_demande_liaison(request, demande_id):
    """
    Rejeter une demande de liaison parent-enfant
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer la demande
    demande = get_object_or_404(
        DemandeLiaisonParent,
        id=demande_id,
        eleve_valide__etablissement=etablissement
    )
    
    try:
        # Rejeter la demande
        motif = request.POST.get('motif_refus', 'Demande refusée par l\'établissement')
        demande.refuser(traite_par=None, motif=motif)
        demande.statut = 'refusee'
        demande.motif_refus = motif
        demande.save()
        
        messages.success(
            request,
            f"✅ Demande rejetée. Le parent {demande.parent_demandeur.nom_complet} sera notifié."
        )
    except Exception as e:
        messages.error(request, f"❌ Erreur lors du rejet : {str(e)}")
    
    return redirect('directeur:demandes_liaison_liste')


def desapprouver_demande_liaison(request, demande_id):
    """
    Désapprouver une demande de liaison parent-enfant
    Supprime le lien familial et remet la demande en attente
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer la demande
    demande = get_object_or_404(
        DemandeLiaisonParent,
        id=demande_id,
        eleve_valide__etablissement=etablissement
    )
    
    try:
        # Vérifier que la demande a été approuvée ou réussie
        if demande.statut not in ['reussie', 'approuvee']:
            messages.warning(request, "Cette demande n'a pas été approuvée.")
            return redirect('directeur:demandes_liaison_liste')
        
        # Supprimer le lien familial correspondant
        lien = LienFamilial.objects.filter(
            parent=demande.parent_demandeur,
            eleve=demande.eleve_valide,
            actif=True
        ).first()
        
        if lien:
            lien.actif = False
            lien.save()
            print(f"[DÉSAPPROBATION] Lien désactivé - Parent: {demande.parent_demandeur.nom_complet}, Élève: {demande.eleve_valide.nom_complet}")
        
        # Remettre la demande en attente
        demande.statut = 'en_attente'
        demande.date_traitement = None
        demande.save()
        
        messages.success(
            request,
            f"✅ La liaison entre {demande.parent_demandeur.nom_complet} et {demande.eleve_valide.nom_complet} a été désapprouvée."
        )
    except Exception as e:
        messages.error(request, f"❌ Erreur lors de la désapprobation : {str(e)}")
    
    return redirect('directeur:demandes_liaison_liste')