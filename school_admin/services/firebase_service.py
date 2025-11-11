"""
Service Firebase pour l'envoi de notifications push
"""
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)


class FirebaseService:
    """Service pour gérer les notifications Firebase Cloud Messaging"""
    
    _initialized = False
    
    @classmethod
    def initialize(cls):
        """Initialise Firebase Admin SDK"""
        if not cls._initialized:
            try:
                # Chemin vers le fichier de credentials
                cred_path = os.path.join(settings.BASE_DIR, 'firebase', 'gestion-scolaire-6945a-e1fb73fd49c4.json')
                
                if not os.path.exists(cred_path):
                    logger.error(f"Fichier credentials Firebase introuvable: {cred_path}")
                    return False
                
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                cls._initialized = True
                logger.info("Firebase Admin SDK initialisé avec succès")
                return True
            except Exception as e:
                logger.error(f"Erreur lors de l'initialisation Firebase: {str(e)}")
                return False
        return True
    
    @classmethod
    def send_notification(cls, token, title, body, data=None):
        """
        Envoie une notification à un seul token
        
        Args:
            token (str): Token FCM du dispositif
            title (str): Titre de la notification
            body (str): Corps de la notification
            data (dict): Données supplémentaires
            
        Returns:
            bool: True si succès, False sinon
        """
        if not cls.initialize():
            return False
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=token,
            )
            
            response = messaging.send(message)
            logger.info(f"Notification envoyée avec succès: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de la notification: {str(e)}")
            return False
    
    @classmethod
    def send_multicast(cls, tokens, title, body, data=None):
        """
        Envoie une notification à plusieurs tokens
        
        Args:
            tokens (list): Liste de tokens FCM
            title (str): Titre de la notification
            body (str): Corps de la notification
            data (dict): Données supplémentaires
            
        Returns:
            dict: Résultat de l'envoi (success_count, failure_count, responses)
        """
        if not cls.initialize():
            return {'success_count': 0, 'failure_count': len(tokens), 'responses': []}
        
        if not tokens:
            logger.warning("Aucun token fourni pour l'envoi multicast")
            return {'success_count': 0, 'failure_count': 0, 'responses': []}
        
        try:
            # Créer les messages pour chaque token
            messages = []
            for token in tokens:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data=data or {},
                    token=token,
                )
                messages.append(message)
            
            # Envoyer tous les messages
            batch_response = messaging.send_each(messages)
            logger.info(f"Notifications envoyées: {batch_response.success_count} succès, {batch_response.failure_count} échecs")
            
            # Nettoyer les tokens invalides
            if batch_response.failure_count > 0:
                cls._clean_invalid_tokens(tokens, batch_response.responses)
            
            return {
                'success_count': batch_response.success_count,
                'failure_count': batch_response.failure_count,
                'responses': batch_response.responses
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi multicast: {str(e)}")
            import traceback
            logger.error(f"Traceback complet: {traceback.format_exc()}")
            return {'success_count': 0, 'failure_count': len(tokens), 'responses': [], 'error': str(e)}
    
    @classmethod
    def _clean_invalid_tokens(cls, tokens, responses):
        """Désactive les tokens invalides dans la base de données"""
        from school_admin.model.fcm_token_model import FCMToken
        
        for idx, response in enumerate(responses):
            if not response.success:
                error = response.exception
                if error and ('not-registered' in str(error) or 'invalid-registration-token' in str(error)):
                    # Désactiver le token invalide
                    try:
                        FCMToken.objects.filter(token=tokens[idx]).update(is_active=False)
                        logger.info(f"Token invalide désactivé: {tokens[idx][:20]}...")
                    except Exception as e:
                        logger.error(f"Erreur lors de la désactivation du token: {str(e)}")
    
    @classmethod
    def send_notification_to_user(cls, user, title, body, data=None):
        """
        Envoie une notification à un utilisateur (tous ses dispositifs actifs)
        
        Args:
            user: Instance de l'utilisateur (Eleve, Parent, Professeur, etc.)
            title (str): Titre de la notification
            body (str): Corps de la notification
            data (dict): Données supplémentaires
            
        Returns:
            dict: Résultat de l'envoi
        """
        from school_admin.model.fcm_token_model import FCMToken
        from django.contrib.contenttypes.models import ContentType
        
        try:
            content_type = ContentType.objects.get_for_model(user)
            tokens_obj = FCMToken.objects.filter(
                content_type=content_type,
                object_id=user.id,
                is_active=True
            )
            
            if not tokens_obj.exists():
                logger.warning(f"Aucun token FCM trouvé pour l'utilisateur {user}")
                return {'success_count': 0, 'failure_count': 0, 'responses': []}
            
            tokens = [t.token for t in tokens_obj]
            return cls.send_multicast(tokens, title, body, data)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi notification à l'utilisateur: {str(e)}")
            return {'success_count': 0, 'failure_count': 0, 'responses': []}
    
    @classmethod
    def send_notification_to_multiple_users(cls, users, title, body, data=None):
        """
        Envoie une notification à plusieurs utilisateurs
        
        Args:
            users (list): Liste d'instances utilisateurs
            title (str): Titre de la notification
            body (str): Corps de la notification
            data (dict): Données supplémentaires
            
        Returns:
            dict: Résultat de l'envoi
        """
        from school_admin.model.fcm_token_model import FCMToken
        from django.contrib.contenttypes.models import ContentType
        
        all_tokens = []
        
        for user in users:
            try:
                content_type = ContentType.objects.get_for_model(user)
                tokens_obj = FCMToken.objects.filter(
                    content_type=content_type,
                    object_id=user.id,
                    is_active=True
                )
                all_tokens.extend([t.token for t in tokens_obj])
            except Exception as e:
                logger.error(f"Erreur lors de la récupération des tokens pour {user}: {str(e)}")
        
        if not all_tokens:
            logger.warning("Aucun token FCM trouvé pour les utilisateurs")
            return {'success_count': 0, 'failure_count': 0, 'responses': []}
        
        # Supprimer les doublons tout en conservant l'ordre
        unique_tokens = list(dict.fromkeys(all_tokens))
        
        return cls.send_multicast(unique_tokens, title, body, data)

