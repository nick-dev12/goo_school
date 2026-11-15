from django.db import models
from django.utils import timezone


class PushDelivery(models.Model):
    dedup_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    body = models.TextField()
    data = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default='pending', db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
