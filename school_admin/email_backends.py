"""Compatibilité des imports ; TLS standard avec vérification du certificat."""
from django.core.mail.backends.smtp import EmailBackend


class CustomSMTPEmailBackend(EmailBackend):
    """Ancien nom conservé, sans désactiver la sécurité du backend Django."""
