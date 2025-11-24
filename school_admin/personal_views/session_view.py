"""
Vues pour la gestion des sessions (années scolaires)
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
import logging

from ..model.etablissement_model import Etablissement
from ..model.annee_scolaire_model import AnneeScolaire
from ..utils.session_utils import (
    get_session_active,
    get_session_consultee,
    set_session_consultee,
    should_redirect_to_new_session,
    mark_session_info_shown
)

logger = logging.getLogger(__name__)


@login_required
def changer_session(request):
    """
    Permet à l'utilisateur de changer la session consultée
    """
    # Vérifier le type d'utilisateur
    etablissement = None
    if isinstance(request.user, Etablissement):
        etablissement = request.user
    elif hasattr(request.user, 'etablissement'):
        etablissement = request.user.etablissement
    
    if not etablissement:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    if request.method == 'POST':
        annee_id = request.POST.get('annee_scolaire_id')
        
        if annee_id:
            try:
                annee_scolaire = get_object_or_404(
                    AnneeScolaire,
                    pk=annee_id,
                    etablissement=etablissement
                )
                set_session_consultee(request, annee_scolaire)
                messages.success(
                    request,
                    f"Vous consultez maintenant la session {annee_scolaire.libelle}."
                )
            except Exception as e:
                logger.error(f"Erreur lors du changement de session: {e}", exc_info=True)
                messages.error(request, "Erreur lors du changement de session.")
        else:
            # Réinitialiser à la session active
            set_session_consultee(request, None)
            messages.info(request, "Vous consultez maintenant la session active.")
    
    # Rediriger vers la page précédente ou le dashboard
    redirect_url = request.GET.get('next', 'directeur:dashboard_directeur')
    
    # Adapter selon le type d'utilisateur
    if not isinstance(request.user, Etablissement):
        if hasattr(request.user, 'etablissement'):
            # Professeur, élève, parent
            if hasattr(request.user, 'matiere_principale'):  # Professeur
                redirect_url = 'enseignant:gestion_notes'
            elif hasattr(request.user, 'classe'):  # Élève
                redirect_url = 'eleve:dashboard_eleve'
            elif hasattr(request.user, 'liens_enfants'):  # Parent
                redirect_url = 'parent:dashboard_parent'
    
    return redirect(redirect_url)


@login_required
def session_active_info(request):
    """
    Affiche un message informatif lors de la redirection vers une nouvelle session
    """
    # Vérifier le type d'utilisateur
    etablissement = None
    if isinstance(request.user, Etablissement):
        etablissement = request.user
    elif hasattr(request.user, 'etablissement'):
        etablissement = request.user.etablissement
    
    if not etablissement:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    should_redirect, session_ouverte = should_redirect_to_new_session(request, etablissement)
    
    if not should_redirect or not session_ouverte:
        # Pas de redirection nécessaire, aller au dashboard
        return redirect('directeur:dashboard_directeur')
    
    # Marquer que l'info a été montrée
    mark_session_info_shown(request, session_ouverte)
    
    # Récupérer toutes les sessions disponibles
    sessions_disponibles = AnneeScolaire.get_annees_etablissement(etablissement)
    session_active = get_session_active(request, etablissement)
    
    context = {
        'etablissement': etablissement,
        'session_ouverte': session_ouverte,
        'session_active': session_active,
        'sessions_disponibles': sessions_disponibles,
    }
    
    return render(request, 'school_admin/common/session_active_info.html', context)

