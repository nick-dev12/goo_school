from django.contrib.auth.signals import user_logged_out, user_logged_in
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from school_admin.model.fcm_token_model import FCMToken


@receiver(user_logged_out)
def detach_push_device(sender, request, user, **kwargs):
    if request is None or user is None:
        return
    token_id = request.session.pop('fcm_token_id', None)
    if token_id:
        FCMToken.objects.filter(pk=token_id, content_type=ContentType.objects.get_for_model(user), object_id=user.pk).delete()


@receiver(user_logged_in)
def detach_previous_account(sender, request, user, **kwargs):
    token_id = request.session.get('fcm_token_id')
    if token_id:
        current_type = ContentType.objects.get_for_model(user)
        FCMToken.objects.filter(pk=token_id).exclude(content_type=current_type, object_id=user.pk).delete()
