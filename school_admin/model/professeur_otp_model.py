import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


class ProfesseurOtpCode(models.Model):
    """
    Code OTP généré pour la connexion d'un professeur.
    """

    MAX_ATTEMPTS = 5
    DEFAULT_VALIDITY_MINUTES = 5

    professeur = models.ForeignKey(
        "school_admin.Professeur",
        on_delete=models.CASCADE,
        related_name="otp_codes",
        null=True,
        blank=True,
    )
    phone_number = models.CharField(max_length=30)
    code = models.CharField(max_length=6)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Code OTP Professeur"
        verbose_name_plural = "Codes OTP Professeurs"

    def __str__(self) -> str:
        cible = self.professeur if self.professeur else self.phone_number
        return f"OTP {self.code} pour {cible}"

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def remaining_seconds(self) -> int:
        delta = self.expires_at - timezone.now()
        return max(int(delta.total_seconds()), 0)

    @classmethod
    def build_expiration(cls) -> timezone.datetime:
        return timezone.now() + timedelta(minutes=cls.DEFAULT_VALIDITY_MINUTES)

