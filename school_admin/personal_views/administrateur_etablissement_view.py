from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.etablissement_model import Etablissement


@login_required
def dashboard_administrateur_etablissement(request):
    """
    Dashboard pour l'administrateur d'établissement
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif
    if not isinstance(user, PersonnelAdministratif):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Statistiques du personnel
    stats = {
        'nom_complet': user.nom_complet,
        'fonction': user.get_fonction_display(),
        'etablissement': etablissement.nom,
        'date_creation': user.date_creation,
        'actif': user.actif,
        'numero_employe': user.numero_employe,
    }
    
    # Statistiques de l'établissement
    etablissement_stats = {
        'nom': etablissement.nom,
        'type': etablissement.get_type_etablissement_display(),
        'code': etablissement.code_etablissement,
        'ville': etablissement.ville,
        'pays': etablissement.pays,
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'stats': stats,
        'etablissement_stats': etablissement_stats,
    }
    
    return render(request, 'school_admin/directeur/administrateur_etablissement/dashboard_administrateur_etablissement.html', context)