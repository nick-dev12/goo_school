from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from ..model.etablissement_model import Etablissement


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
    
    # Préparer le contexte avec les données de l'établissement
    context = {
        'etablissement': etablissement,
        'nom_etablissement': etablissement.nom,
        'type_etablissement': etablissement.get_type_etablissement_display(),
        'code_etablissement': etablissement.code_etablissement,
        'directeur_nom_complet': f"{etablissement.directeur_prenom} {etablissement.directeur_nom}",
        'adresse_complete': f"{etablissement.adresse}, {etablissement.ville}, {etablissement.pays}",
        
        # Modules activés
        'modules_actifs': {
            'gestion_eleves': etablissement.module_gestion_eleves,
            'notes_evaluations': etablissement.module_notes_evaluations,
            'emploi_temps': etablissement.module_emploi_temps,
            'gestion_personnel': etablissement.module_gestion_personnel,
            'surveillance': etablissement.module_surveillance,
            'communication': etablissement.module_communication,
            'orientation': etablissement.module_orientation,
            'formation': etablissement.module_formation,
            'transport_scolaire': etablissement.module_transport_scolaire,
            'cantine': etablissement.module_cantine,
            'bibliotheque': etablissement.module_bibliotheque,
            'sante': etablissement.module_sante,
            'activites': etablissement.module_activites,
            'comptabilite': etablissement.module_comptabilite,
            'censeurs': etablissement.module_censeurs,
        },
        
        # Statistiques simples
        'date_creation': etablissement.date_creation,
        'derniere_modification': etablissement.date_modification,
    }
    
    return render(request, 'school_admin/directeur/dashboard_directeur.html', context)