# school_admin/personal_views/eleve_view.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from ..model.eleve_model import Eleve
from ..model.etablissement_model import Etablissement


@login_required
def dashboard_eleve(request):
    """
    Dashboard pour les élèves
    """
    # Vérifier que l'utilisateur est un élève
    if not isinstance(request.user, Eleve):
        messages.error(request, "Accès non autorisé. Vous devez être un élève.")
        return redirect('school_admin:connexion_compte_user')
    
    eleve = request.user
    etablissement = eleve.etablissement
    
    # Statistiques de l'élève
    stats = {
        'nom_complet': eleve.nom_complet,
        'numero_eleve': eleve.numero_eleve,
        'classe': eleve.classe.nom if eleve.classe else "Non assigné",
        'etablissement': etablissement.nom,
        'date_inscription': eleve.date_inscription,
        'statut': eleve.get_statut_display(),
        'age': eleve.age,
        'actif': eleve.actif,
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
        'eleve': eleve,
        'etablissement': etablissement,
        'stats': stats,
        'etablissement_stats': etablissement_stats,
    }
    
    return render(request, 'school_admin/eleve/dashboard_eleve.html', context)
