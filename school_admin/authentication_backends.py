# school_admin/authentication_backends.py

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password
from .model.compte_user import CompteUser
from .model.etablissement_model import Etablissement


class MultiUserBackend(BaseBackend):
    """
    Backend d'authentification personnalisé qui gère à la fois
    les CompteUser et les Etablissement
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authentifie un utilisateur en vérifiant d'abord dans CompteUser,
        puis dans Etablissement
        """
        if username is None or password is None:
            return None
        
        # Essayer d'abord avec CompteUser
        try:
            user = CompteUser.objects.get(username=username)
            if user.check_password(password):
                return user
        except CompteUser.DoesNotExist:
            pass
        
        # Essayer ensuite avec Etablissement
        try:
            etablissement = Etablissement.objects.get(username=username)
            if etablissement.check_password(password):
                return etablissement
        except Etablissement.DoesNotExist:
            pass
        
        return None
    
    def get_user(self, user_id):
        """
        Récupère un utilisateur par son ID en vérifiant les deux modèles
        """
        # Essayer d'abord CompteUser
        try:
            return CompteUser.objects.get(pk=user_id)
        except CompteUser.DoesNotExist:
            pass
        
        # Essayer ensuite Etablissement
        try:
            return Etablissement.objects.get(pk=user_id)
        except Etablissement.DoesNotExist:
            pass
        
        return None
