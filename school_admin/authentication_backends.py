# school_admin/authentication_backends.py

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password
from .model.compte_user import CompteUser
from .model.etablissement_model import Etablissement
from .model.personnel_administratif_model import PersonnelAdministratif
from .model.eleve_model import Eleve
from .model.professeur_model import Professeur


class MultiUserBackend(BaseBackend):
    """
    Backend d'authentification personnalisé qui gère à la fois
    les CompteUser et les Etablissement
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authentifie un utilisateur en vérifiant dans tous les modèles d'utilisateurs
        """
        if username is None or password is None:
            return None
        
        # Essayer d'abord avec PersonnelAdministratif (priorité pour les établissements)
        try:
            personnel = PersonnelAdministratif.objects.get(username=username)
            if personnel.check_password(password) and personnel.actif:
                return personnel
        except PersonnelAdministratif.DoesNotExist:
            pass
        
        # Essayer avec Etablissement
        try:
            etablissement = Etablissement.objects.get(username=username)
            if etablissement.check_password(password):
                return etablissement
        except Etablissement.DoesNotExist:
            pass
        
        # Essayer avec CompteUser
        try:
            user = CompteUser.objects.get(username=username)
            if user.check_password(password):
                return user
        except CompteUser.DoesNotExist:
            pass
        
        # Essayer avec Eleve
        try:
            eleve = Eleve.objects.get(username=username)
            if eleve.check_password(password):
                return eleve
        except Eleve.DoesNotExist:
            pass
        
        # Essayer avec Professeur
        try:
            professeur = Professeur.objects.get(username=username)
            if professeur.check_password(password) and professeur.actif:
                return professeur
        except Professeur.DoesNotExist:
            pass
        
        return None
    
    def get_user(self, user_id):
        """
        Récupère un utilisateur par son ID en vérifiant tous les modèles
        IMPORTANT: L'ordre doit être optimisé pour éviter les conflits d'ID
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug(f"get_user appelé avec user_id: {user_id}")
        
        # Essayer avec Professeur d'abord (nouveau modèle)
        try:
            user = Professeur.objects.get(pk=user_id)
            logger.debug(f"Utilisateur trouvé dans Professeur: {user.email}")
            return user
        except Professeur.DoesNotExist:
            pass
        
        # Essayer avec PersonnelAdministratif
        try:
            user = PersonnelAdministratif.objects.get(pk=user_id)
            logger.debug(f"Utilisateur trouvé dans PersonnelAdministratif: {user.email}")
            return user
        except PersonnelAdministratif.DoesNotExist:
            pass
        
        # Essayer avec Etablissement
        try:
            user = Etablissement.objects.get(pk=user_id)
            logger.debug(f"Utilisateur trouvé dans Etablissement: {user.email}")
            return user
        except Etablissement.DoesNotExist:
            pass
        
        # Essayer avec Eleve
        try:
            user = Eleve.objects.get(pk=user_id)
            logger.debug(f"Utilisateur trouvé dans Eleve: {user.email}")
            return user
        except Eleve.DoesNotExist:
            pass
        
        # Essayer avec CompteUser en dernier
        try:
            user = CompteUser.objects.get(pk=user_id)
            logger.debug(f"Utilisateur trouvé dans CompteUser: {user.email}")
            return user
        except CompteUser.DoesNotExist:
            pass
        
        logger.warning(f"Aucun utilisateur trouvé avec l'ID: {user_id}")
        return None
