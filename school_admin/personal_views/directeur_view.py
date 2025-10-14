from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from ..model.etablissement_model import Etablissement
from ..model.facturation_model import Facturation
from ..model.eleve_model import Eleve


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
    
    # Statistiques des élèves
    nombre_eleves_total = Eleve.objects.filter(etablissement=etablissement).count()
    nombre_eleves_actifs = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
    
    # Statistiques du personnel
    from ..model.personnel_administratif_model import PersonnelAdministratif
    nombre_personnel_admin = PersonnelAdministratif.objects.filter(etablissement=etablissement).count()
    nombre_enseignants = 0  # À implémenter quand le modèle enseignant sera créé
    nombre_classes = 0  # À implémenter quand le modèle classe sera créé
    
    # Statistiques de facturation
    facturations = Facturation.objects.filter(etablissement=etablissement)
    montant_total_facture = facturations.aggregate(total=Sum('montant_total'))['total'] or 0
    nombre_factures = facturations.count()
    factures_en_attente = facturations.filter(statut='en_attente').count()
    factures_payees = facturations.filter(statut='paye').count()
    factures_en_retard = facturations.filter(statut='en_retard').count()
    
    # Dernières factures
    dernieres_factures = facturations.order_by('-date_creation')[:5]
    
    # Modules activés et inactifs
    modules_info = {
        'gestion_eleves': {'nom': 'Gestion des élèves', 'actif': etablissement.module_gestion_eleves},
        'notes_evaluations': {'nom': 'Notes et évaluations', 'actif': etablissement.module_notes_evaluations},
        'emploi_temps': {'nom': 'Emploi du temps', 'actif': etablissement.module_emploi_temps},
        'gestion_personnel': {'nom': 'Gestion du personnel', 'actif': etablissement.module_gestion_personnel},
        'surveillance': {'nom': 'Surveillance et sécurité', 'actif': etablissement.module_surveillance},
        'communication': {'nom': 'Communication parents', 'actif': etablissement.module_communication},
        'orientation': {'nom': 'Orientation scolaire', 'actif': etablissement.module_orientation},
        'formation': {'nom': 'Formation continue', 'actif': etablissement.module_formation},
        'transport_scolaire': {'nom': 'Transport scolaire', 'actif': etablissement.module_transport_scolaire},
        'cantine': {'nom': 'Gestion de la cantine', 'actif': etablissement.module_cantine},
        'bibliotheque': {'nom': 'Gestion de la bibliothèque', 'actif': etablissement.module_bibliotheque},
        'sante': {'nom': 'Suivi médical', 'actif': etablissement.module_sante},
        'activites': {'nom': 'Activités extra-scolaires', 'actif': etablissement.module_activites},
        'comptabilite': {'nom': 'Comptabilité', 'actif': etablissement.module_comptabilite},
        'censeurs': {'nom': 'Censeurs', 'actif': etablissement.module_censeurs},
    }
    
    # Préparer le contexte avec les données de l'établissement
    context = {
        'etablissement': etablissement,
        'nom_etablissement': etablissement.nom,
        'type_etablissement': etablissement.get_type_etablissement_display(),
        'code_etablissement': etablissement.code_etablissement,
        'directeur_nom_complet': f"{etablissement.directeur_prenom} {etablissement.directeur_nom}",
        'adresse_complete': f"{etablissement.adresse}, {etablissement.ville}, {etablissement.pays}",
        
        # Modules
        'modules_info': modules_info,
        'modules_actifs': {k: v['actif'] for k, v in modules_info.items()},
        
        # Statistiques élèves
        'nombre_eleves_total': nombre_eleves_total,
        'nombre_eleves_actifs': nombre_eleves_actifs,
        'nombre_personnel_admin': nombre_personnel_admin,
        'nombre_enseignants': nombre_enseignants,
        'nombre_classes': nombre_classes,
        
        # Statistiques facturation
        'montant_total_facture': montant_total_facture,
        'nombre_factures': nombre_factures,
        'factures_en_attente': factures_en_attente,
        'factures_payees': factures_payees,
        'factures_en_retard': factures_en_retard,
        'dernieres_factures': dernieres_factures,
        'statut_paiement': etablissement.get_statut_paiement_display(),
        'montant_total_facturation': etablissement.montant_total_facturation,
        'nombre_eleves_factures': etablissement.nombre_eleves_factures,
        
        # Dates
        'date_creation': etablissement.date_creation,
        'derniere_modification': etablissement.date_modification,
        'date_derniere_facturation': etablissement.date_derniere_facturation,
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
def gestion_etablissement(request):
    """
    Vue de la page de gestion de l'établissement pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
   
    return render(request, 'school_admin/directeur/gestion_etablissement.html')