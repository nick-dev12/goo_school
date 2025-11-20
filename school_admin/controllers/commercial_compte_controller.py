from django.shortcuts import render, redirect 
from django.contrib import messages
from ..model.compte_user import CompteUser
from django.contrib.auth import logout



class CommercialCompteController:
    
    """
    Contrôleur pour la gestion des comptes commerciaux
    """
    
    @staticmethod
    def get_user_compte_commercial(request):
        """
        Vue pour la création d'un compte commercial
        """
        
        #recupere les informations du compte commercial connecte
        user = request.user
        if user.is_authenticated and user.fonction == 'commercial':
            return user
        else:
            return None
        
        return render(request, 'school_admin/commercial/register.html')
    
    @staticmethod
    def update_user_compte_commercial(request):
        """
        Vue pour la mise à jour d'un compte commercial
        """
        return render(request, 'school_admin/commercial/update.html')
  
  
    @staticmethod
    def logout_user_commercial(request):
      """
      Déconnexion d'un compte commercial
      Nettoie complètement la session et affiche un message de confirmation
      """
      from school_admin.authentication_backends import _user_type_context
      
      # Nettoyer le type d'utilisateur de la session
      if '_auth_user_type' in request.session:
          del request.session['_auth_user_type']
      
      # Nettoyer le thread-local
      if hasattr(_user_type_context, 'user_type'):
          delattr(_user_type_context, 'user_type')
      
      # Déconnecter l'utilisateur
      logout(request)
      
      # Ajouter un message de succès APRÈS logout()
      messages.success(request, "Déconnexion réussie. Vous avez été déconnecté avec succès.")
      
      return redirect('school_admin:connexion_compte_user')
    