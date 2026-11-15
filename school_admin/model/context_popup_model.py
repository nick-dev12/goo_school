from django.db import models


class ContextPopupState(models.Model):
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    key = models.CharField(max_length=190)
    seen_version = models.CharField(max_length=64, blank=True)
    evidence = models.JSONField(default=dict)
    snooze_until = models.DateTimeField(null=True, blank=True)
    last_shown = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['content_type', 'object_id', 'key'], name='unique_context_popup_state')]


class ContextPopupVisit(models.Model):
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    login_key = models.CharField(max_length=64)
    cards = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['content_type', 'object_id', 'login_key'], name='unique_context_popup_visit')]
