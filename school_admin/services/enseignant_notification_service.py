"""Service utilitaire pour les notifications destinées aux enseignants."""

from __future__ import annotations

import logging
from typing import Optional

from django.urls import reverse
from django.utils import timezone

from school_admin.model.notification_enseignant_model import NotificationEnseignant
from school_admin.model.professeur_model import Professeur

logger = logging.getLogger(__name__)


class EnseignantNotificationService:
    """Service centralisant la création des notifications enseignants."""

    @classmethod
    def _dispatch(
        cls,
        enseignant: Optional[Professeur],
        type_notification: str,
        titre: str,
        message: str,
        payload: Optional[dict] = None,
        source=None,
        push_title: Optional[str] = None,
        push_body: Optional[str] = None,
        push_data: Optional[dict] = None,
    ) -> dict:
        if not enseignant or not isinstance(enseignant, Professeur):
            logger.debug("Notification enseignant ignorée : enseignant invalide")
            return {"created": 0, "push": None}

        notification = NotificationEnseignant.objects.create(
            enseignant=enseignant,
            titre=titre,
            message=message,
            type_notification=type_notification,
            donnees=payload or {},
            source_object=source,
            date_evenement=timezone.now(),
        )

        try:
            default_redirect_url = reverse("enseignant:notifications_enseignant")
        except Exception:
            default_redirect_url = "/enseignant/notifications/"

        payload_with_url = payload.copy() if payload else {}
        payload_with_url.setdefault("redirect_url", default_redirect_url)
        payload_with_url.setdefault("url", default_redirect_url)

        pushdata_with_url = push_data.copy() if push_data else {}
        pushdata_with_url.setdefault("redirect_url", default_redirect_url)
        pushdata_with_url.setdefault("url", default_redirect_url)

        push_result = None
        if push_title and push_body:
            try:
                from school_admin.services.firebase_service import FirebaseService

                push_result = FirebaseService.send_notification_to_multiple_users(
                    [enseignant],
                    push_title,
                    push_body,
                    pushdata_with_url,
                )

                if push_result.get("success_count", 0) > 0:
                    notification.notification_push_envoyee = True
                    notification.save(update_fields=["notification_push_envoyee", "date_modification"])
            except Exception as exc:  # pragma: no cover
                logger.error(
                    "Erreur lors de l'envoi de la notification push enseignant: %s",
                    exc,
                    exc_info=True,
                )

        return {"created": 1, "push": push_result}

    @classmethod
    def notify_annonce(cls, enseignant: Professeur, annonce, *, source=None) -> dict:
        etab_nom = getattr(annonce.etablissement, "nom", "Votre établissement")
        titre = f"[{etab_nom}] Nouvelle annonce"
        message = annonce.titre

        payload = {
            "annonce_id": getattr(annonce, "id", None),
            "titre": annonce.titre,
        }

        push_title = None
        push_body = None
        push_data = None

        return cls._dispatch(
            enseignant,
            type_notification="annonce",
            titre=titre,
            message=message,
            payload=payload,
            source=source or annonce,
            push_title=push_title,
            push_body=push_body,
            push_data=push_data,
        )
