import uuid
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def start_popup_visit(sender, request, **kwargs):
    request.session['context_popup_login'] = uuid.uuid4().hex
