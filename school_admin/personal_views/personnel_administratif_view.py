# school_admin/personal_views/personnel_administratif_view.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.etablissement_model import Etablissement


@login_required
def dashboard_personnel_administratif(request):
    """
    Dashboard pour le personnel administratif
    """
    # Vérifier que l'utilisateur est du personnel administratif
    if not isinstance(request.user, PersonnelAdministratif):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    personnel = request.user
    etablissement = personnel.etablissement
    
    # Statistiques du personnel
    stats = {
        'nom_complet': personnel.nom_complet,
        'fonction': personnel.get_fonction_display(),
        'etablissement': etablissement.nom,
        'date_creation': personnel.date_creation,
        'actif': personnel.actif,
        'numero_employe': personnel.numero_employe,
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
        'personnel': personnel,
        'etablissement': etablissement,
        'stats': stats,
        'etablissement_stats': etablissement_stats,
    }
    
    return render(request, 'school_admin/personnel_administratif/dashboard_personnel_administratif.html', context)


@login_required
def profil_personnel_administratif(request):
    """
    Profil du personnel administratif
    """
    # Vérifier que l'utilisateur est du personnel administratif
    if not isinstance(request.user, PersonnelAdministratif):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    personnel = request.user
    
    if request.method == 'POST':
        # Mise à jour des informations personnelles
        personnel.nom = request.POST.get('nom', personnel.nom)
        personnel.prenom = request.POST.get('prenom', personnel.prenom)
        personnel.telephone = request.POST.get('telephone', personnel.telephone)
        personnel.email = request.POST.get('email', personnel.email)
        
        # Vérifier si le mot de passe est fourni
        new_password = request.POST.get('password', '')
        if new_password:
            if len(new_password) >= 8:
                personnel.set_password(new_password)
                messages.success(request, "Mot de passe mis à jour avec succès.")
            else:
                messages.error(request, "Le mot de passe doit contenir au moins 8 caractères.")
                return render(request, 'school_admin/personnel_administratif/profil_personnel_administratif.html', {'personnel': personnel})
        
        personnel.save()
        messages.success(request, "Profil mis à jour avec succès.")
        return redirect('personnel_administratif:profil')
    
    context = {
        'personnel': personnel,
    }
    
    return render(request, 'school_admin/personnel_administratif/profil_personnel_administratif.html', context)


@login_required
def liste_eleves_personnel(request):
    """
    Liste des élèves pour le personnel administratif
    """
    # Vérifier que l'utilisateur est du personnel administratif
    if not isinstance(request.user, PersonnelAdministratif):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    personnel = request.user
    etablissement = personnel.etablissement
    
    # Ici, vous pouvez ajouter la logique pour récupérer les élèves
    # Pour l'instant, on simule avec des données vides
    eleves = []
    
    context = {
        'personnel': personnel,
        'etablissement': etablissement,
        'eleves': eleves,
    }
    
    return render(request, 'school_admin/personnel_administratif/liste_eleves.html', context)


@login_required
def liste_enseignants_personnel(request):
    """
    Liste des enseignants pour le personnel administratif
    """
    # Vérifier que l'utilisateur est du personnel administratif
    if not isinstance(request.user, PersonnelAdministratif):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    personnel = request.user
    etablissement = personnel.etablissement
    
    # Ici, vous pouvez ajouter la logique pour récupérer les enseignants
    # Pour l'instant, on simule avec des données vides
    enseignants = []
    
    context = {
        'personnel': personnel,
        'etablissement': etablissement,
        'enseignants': enseignants,
    }
    
    return render(request, 'school_admin/personnel_administratif/liste_enseignants.html', context)
