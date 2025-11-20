# school_admin/authentication_backends.py

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password
import threading
from .model.compte_user import CompteUser
from .model.etablissement_model import Etablissement
from .model.personnel_administratif_model import PersonnelAdministratif
from .model.eleve_model import Eleve
from .model.professeur_model import Professeur
from .model.parent_model import Parent

# Thread-local storage pour passer le type d'utilisateur à get_user()
_user_type_context = threading.local()


class MultiUserBackend(BaseBackend):
    """
    Backend d'authentification personnalisé qui gère plusieurs types d'utilisateurs
    de manière indépendante pour éviter les conflits d'ID.
    
    STRATÉGIE ANTI-CONFLIT:
    - Chaque type d'utilisateur est stocké dans sa propre table
    - Un identifiant unique est créé : "TYPE:ID" pour éviter les collisions
    - La méthode get_user() décode cet identifiant pour retrouver le bon utilisateur
    """
    
    # Préfixes pour identifier le type d'utilisateur
    USER_TYPE_PREFIXES = {
        'etablissement': 'ETAB',
        'compte_user': 'USER',
        'personnel': 'PERS',
        'professeur': 'PROF',
        'eleve': 'ELEV',
        'parent': 'PARE',
    }
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authentifie un utilisateur en vérifiant dans tous les modèles d'utilisateurs.
        Chaque section est indépendante pour éviter les conflits.
        """
        if username is None or password is None:
            return None
        
        # ==========================================
        # SECTION 1: ÉTABLISSEMENTS (Directeurs)
        # ==========================================
        try:
            etablissement = Etablissement.objects.get(username=username)
            if etablissement.check_password(password):
                # Stocker le type dans l'objet pour get_user()
                etablissement._auth_user_type = 'etablissement'
                return etablissement
        except Etablissement.DoesNotExist:
            pass
        
        # ==========================================
        # SECTION 2: COMPTE UTILISATEURS (Admin, Commercial, etc.)
        # ==========================================
        try:
            user = CompteUser.objects.get(username=username)
            if user.check_password(password):
                user._auth_user_type = 'compte_user'
                return user
        except CompteUser.DoesNotExist:
            pass
        
        # ==========================================
        # SECTION 3: PERSONNEL ADMINISTRATIF
        # ==========================================
        try:
            personnel = PersonnelAdministratif.objects.get(username=username)
            if personnel.check_password(password) and personnel.actif:
                personnel._auth_user_type = 'personnel'
                return personnel
        except PersonnelAdministratif.DoesNotExist:
            pass
        
        # ==========================================
        # SECTION 4: PROFESSEURS
        # ==========================================
        try:
            professeur = Professeur.objects.get(numero_employe=username)
            if professeur.check_password(password) and professeur.actif:
                professeur._auth_user_type = 'professeur'
                return professeur
        except Professeur.DoesNotExist:
            pass
        
        # ==========================================
        # SECTION 5: ÉLÈVES
        # ==========================================
        try:
            eleve = Eleve.objects.get(username=username)
            if eleve.check_password(password) and eleve.actif:
                eleve._auth_user_type = 'eleve'
                return eleve
        except Eleve.DoesNotExist:
            pass
        
        # ==========================================
        # SECTION 6: PARENTS (matricule_parental)
        # ==========================================
        try:
            parent = Parent.objects.get(matricule_parental=username)
            if parent.check_password(password) and parent.is_active:
                parent._auth_user_type = 'parent'
                return parent
        except Parent.DoesNotExist:
            pass
        
        return None
    
    def get_user(self, user_id):
        """
        Récupère un utilisateur par son ID en utilisant le type stocké dans la session.
        STRATÉGIE: Utilise le type d'utilisateur stocké dans le thread-local (passé par le middleware)
        pour chercher directement dans la bonne table, évitant ainsi les conflits d'ID entre tables.
        Si le type n'est pas disponible, cherche dans toutes les tables dans un ordre optimisé.
        """
        import logging
        
        logger = logging.getLogger(__name__)
        
        print(f"\n[GET_USER] Recherche utilisateur avec ID: {user_id}")
        logger.debug(f"get_user appelé avec user_id: {user_id}")
        
        # Récupérer le type d'utilisateur depuis le thread-local (passé par le middleware)
        user_type = getattr(_user_type_context, 'user_type', None)
        
        if user_type:
            logger.debug(f"Type d'utilisateur trouvé dans le contexte: {user_type}")
            # Chercher directement dans la bonne table selon le type
            user = self._get_user_by_type(user_id, user_type, logger)
            if user:
                return user
            else:
                logger.warning(f"Utilisateur de type {user_type} avec ID {user_id} non trouvé, recherche dans toutes les tables")
        
        # Si le type n'est pas disponible ou si l'utilisateur n'a pas été trouvé,
        # chercher dans toutes les tables dans un ordre optimisé
        # IMPORTANT: Chaque section est indépendante et cherche dans SA PROPRE TABLE uniquement
        
        # ==========================================
        # SECTION 1: ÉTABLISSEMENTS (Directeurs)
        # ==========================================
        try:
            user = Etablissement.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] ETABLISSEMENT trouve: {user.nom} (ID: {user.id})")
            logger.info(f"Établissement trouvé: {getattr(user, 'email', 'N/A')}")
            return user
        except Etablissement.DoesNotExist:
            logger.debug(f"Pas d'établissement avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans Etablissement: {e}")
        
        # ==========================================
        # SECTION 2: COMPTE UTILISATEURS (Admin, Commercial, etc.)
        # ==========================================
        try:
            user = CompteUser.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] COMPTE_USER trouve: {user.email} (ID: {user.id}, Fonction: {user.fonction})")
            logger.info(f"CompteUser trouvé: {user.email}")
            return user
        except CompteUser.DoesNotExist:
            logger.debug(f"Pas de CompteUser avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans CompteUser: {e}")
        
        # ==========================================
        # SECTION 3: PERSONNEL ADMINISTRATIF
        # ==========================================
        try:
            user = PersonnelAdministratif.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] PERSONNEL trouve: {user.nom} {user.prenom} (ID: {user.id}, Fonction: {user.fonction})")
            logger.info(f"PersonnelAdministratif trouvé: {getattr(user, 'email', 'N/A')}")
            return user
        except PersonnelAdministratif.DoesNotExist:
            logger.debug(f"Pas de PersonnelAdministratif avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans PersonnelAdministratif: {e}")
        
        # ==========================================
        # SECTION 4: PROFESSEURS
        # ==========================================
        try:
            user = Professeur.objects.get(pk=user_id)
            nom_complet = user.nom_complet if hasattr(user, 'nom_complet') else f"{user.nom} {user.prenom}"
            print(f"[GET_USER] [OK] PROFESSEUR trouve: {nom_complet} (ID: {user.id})")
            logger.info(f"Professeur trouvé: {getattr(user, 'email', 'N/A')}")
            return user
        except Professeur.DoesNotExist:
            logger.debug(f"Pas de Professeur avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans Professeur: {e}")
        
        # ==========================================
        # SECTION 5: ÉLÈVES
        # ==========================================
        try:
            user = Eleve.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] ELEVE trouve: {user.nom_complet} (ID: {user.id})")
            logger.info(f"Eleve trouvé: {getattr(user, 'email', 'N/A')}")
            return user
        except Eleve.DoesNotExist:
            logger.debug(f"Pas d'Eleve avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans Eleve: {e}")
        
        # ==========================================
        # SECTION 6: PARENTS
        # ==========================================
        try:
            user = Parent.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] PARENT trouve: {user.nom_complet} (ID: {user.id})")
            logger.info(f"Parent trouvé: {getattr(user, 'email', 'N/A')}")
            return user
        except Parent.DoesNotExist:
            logger.debug(f"Pas de Parent avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans Parent: {e}")
        
        # ==========================================
        # AUCUN UTILISATEUR TROUVÉ
        # ==========================================
        logger.warning(f"[ERREUR] Aucun utilisateur trouve avec l'ID: {user_id} dans AUCUNE table")
        print(f"[GET_USER] [ERREUR] Aucun utilisateur avec ID {user_id} dans aucune des 6 tables")
        return None
    
    def _get_user_by_type(self, user_id, user_type, logger):
        """
        Récupère un utilisateur par son ID et son type.
        Chaque section est indépendante et cherche dans SA PROPRE TABLE uniquement.
        """
        if user_type == 'etablissement':
            try:
                return Etablissement.objects.get(pk=user_id)
            except Etablissement.DoesNotExist:
                return None
        
        elif user_type == 'compte_user':
            try:
                return CompteUser.objects.get(pk=user_id)
            except CompteUser.DoesNotExist:
                return None
        
        elif user_type == 'personnel':
            try:
                return PersonnelAdministratif.objects.get(pk=user_id)
            except PersonnelAdministratif.DoesNotExist:
                return None
        
        elif user_type == 'professeur':
            try:
                return Professeur.objects.get(pk=user_id)
            except Professeur.DoesNotExist:
                return None
        
        elif user_type == 'eleve':
            try:
                return Eleve.objects.get(pk=user_id)
            except Eleve.DoesNotExist:
                return None
        
        elif user_type == 'parent':
            try:
                return Parent.objects.get(pk=user_id)
            except Parent.DoesNotExist:
                return None
        
        return None
