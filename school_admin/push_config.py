from django.conf import settings

DEFAULT_WEB_CONFIG = {
    'apiKey': 'AIzaSyCSvm0VNdvnLqdIFPdDs4DPYDjHvDsO4_Q',
    'authDomain': 'gestion-scolaire-6945a.firebaseapp.com',
    'projectId': 'gestion-scolaire-6945a',
    'storageBucket': 'gestion-scolaire-6945a.firebasestorage.app',
    'messagingSenderId': '983006440407',
    'appId': '1:983006440407:web:8cbfc916f43b745a7e7992',
}


def public_config():
    return {'firebase': getattr(settings, 'FIREBASE_WEB_CONFIG', DEFAULT_WEB_CONFIG),
            'vapidKey': getattr(settings, 'FIREBASE_VAPID_PUBLIC_KEY', 'BOcifkSIQA0dwy2S50hgj2uXz0DzPliCQZsNplPZCwNonprBCJdORq_T5VPYmophqkHkcZjeWYVhoBEKnlPDsgE')}
