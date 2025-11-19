"""
Backend SMTP personnalisé pour gérer les certificats SSL auto-signés
"""
import ssl
import smtplib
from django.core.mail.backends.smtp import EmailBackend


class CustomSMTPEmailBackend(EmailBackend):
    """
    Backend SMTP personnalisé qui désactive la vérification du certificat SSL
    pour les serveurs avec certificats auto-signés ou non valides
    """
    
    def open(self):
        """
        Établit une connexion SMTP avec vérification SSL désactivée
        """
        if self.connection:
            return False
        try:
            # Créer un contexte SSL sans vérification du certificat
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            if self.use_ssl:
                # Connexion SSL directe
                self.connection = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
            else:
                # Connexion SMTP standard avec TLS optionnel
                self.connection = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                if self.use_tls:
                    self.connection.starttls(context=context)
            
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except Exception:
            if not self.fail_silently:
                raise

