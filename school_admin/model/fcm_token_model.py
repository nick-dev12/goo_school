"""
Modèle pour stocker les tokens FCM des utilisateurs
"""
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class FCMToken(models.Model):
    """Token FCM pour les notifications push"""
    
    # Relation générique pour supporter tous types d'utilisateurs
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    user = GenericForeignKey('content_type', 'object_id')
    
    # Token FCM
    token = models.CharField(max_length=500, unique=True)
    
    # Informations sur le dispositif
    device_type = models.CharField(max_length=50, blank=True, null=True)  # 'web', 'android', 'ios'
    device_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'fcm_tokens'
        verbose_name = 'Token FCM'
        verbose_name_plural = 'Tokens FCM'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        return f"FCM Token for {self.user} - {self.token[:20]}..."

