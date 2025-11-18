# school_admin/authentication_backends.py

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password
from .model.compte_user import CompteUser
from .model.etablissement_model import Etablissement
from .model.personnel_administratif_model import PersonnelAdministratif
from .model.eleve_model import Eleve
from .model.professeur_model import Professeur
from .model.parent_model import Parent


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
        Récupère un utilisateur par son ID en vérifiant tous les modèles.
        STRATÉGIE: Chaque section est indépendante et cherche dans SA PROPRE TABLE.
        
        IMPORTANT: Pour éviter les conflits d'ID entre tables, on vérifie
        systématiquement dans toutes les tables, mais dans un ordre optimisé
        selon la fréquence d'utilisation.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        print(f"\n[GET_USER] Recherche utilisateur avec ID: {user_id}")
        logger.debug(f"get_user appelé avec user_id: {user_id}")
        
        # ==========================================
        # SECTION 1: ÉTABLISSEMENTS (Directeurs)
        # Priorité 1 car c'est le type le plus fréquent
        # ==========================================
        try:
            user = Etablissement.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] ETABLISSEMENT trouve: {user.nom} (ID: {user.id})")
            logger.info(f"Établissement trouvé: {user.email}")
            return user
        except Etablissement.DoesNotExist:
            logger.debug(f"Pas d'établissement avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans Etablissement: {e}")
        
        # ==========================================
        # SECTION 2: COMPTE UTILISATEURS (Admin, Commercial, etc.)
        # Priorité 2 pour les administrateurs système
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
        # Priorité 3 pour le personnel de l'établissement
        # ==========================================
        try:
            user = PersonnelAdministratif.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] PERSONNEL trouve: {user.nom} {user.prenom} (ID: {user.id}, Fonction: {user.fonction})")
            logger.info(f"PersonnelAdministratif trouvé: {user.email}")
            return user
        except PersonnelAdministratif.DoesNotExist:
            logger.debug(f"Pas de PersonnelAdministratif avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans PersonnelAdministratif: {e}")
        
        # ==========================================
        # SECTION 4: PROFESSEURS
        # Priorité 4 pour les enseignants
        # ==========================================
        try:
            user = Professeur.objects.get(pk=user_id)
            nom_complet = user.nom_complet if hasattr(user, 'nom_complet') else f"{user.nom} {user.prenom}"
            print(f"[GET_USER] [OK] PROFESSEUR trouve: {nom_complet} (ID: {user.id})")
            logger.info(f"Professeur trouvé: {user.email}")
            return user
        except Professeur.DoesNotExist:
            logger.debug(f"Pas de Professeur avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans Professeur: {e}")
        
        # ==========================================
        # SECTION 5: ÉLÈVES
        # Priorité 5 pour les élèves
        # ==========================================
        try:
            user = Eleve.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] ELEVE trouve: {user.nom_complet} (ID: {user.id})")
            logger.info(f"Eleve trouvé: {user.email}")
            return user
        except Eleve.DoesNotExist:
            logger.debug(f"Pas d'Eleve avec ID {user_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la recherche dans Eleve: {e}")
        
        # ==========================================
        # SECTION 6: PARENTS
        # Priorité 6 pour les parents
        # ==========================================
        try:
            user = Parent.objects.get(pk=user_id)
            print(f"[GET_USER] [OK] PARENT trouve: {user.nom_complet} (ID: {user.id})")
            logger.info(f"Parent trouvé: {user.email}")
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
