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
      """
      logout(request)
      return redirect('school_admin:connexion_compte_user')
    