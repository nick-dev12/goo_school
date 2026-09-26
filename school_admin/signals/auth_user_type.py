"""Persiste le type d'utilisateur dans la session à chaque login."""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from school_admin.authentication_backends import persist_auth_user_type


@receiver(user_logged_in)
def persist_auth_user_type_on_login(sender, request, user, **kwargs):
    persist_auth_user_type(request, user)
