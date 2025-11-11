"""Service centralisant la création des notifications pour les élèves."""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from django.utils import timezone
from django.urls import reverse

from school_admin.model.notification_eleve_model import NotificationEleve
from school_admin.model.eleve_model import Eleve

logger = logging.getLogger(__name__)


class EleveNotificationService:
    """Service utilitaire pour notifier les élèves."""

    @classmethod
    def _dispatch(
        cls,
        eleve: Optional[Eleve],
        type_notification: str,
        titre: str,
        message: str,
        payload: Optional[dict] = None,
        source=None,
        push_title: Optional[str] = None,
        push_body: Optional[str] = None,
        push_data: Optional[dict] = None,
    ) -> dict:
        if not eleve or not isinstance(eleve, Eleve):
            logger.debug("Notification élève ignorée : élève invalide")
            return {"created": 0, "push": None}

        notification = NotificationEleve.objects.create(
            eleve=eleve,
            titre=titre,
            message=message,
            type_notification=type_notification,
            donnees=payload or {},
            source_object=source,
            date_evenement=timezone.now(),
        )

        try:
            default_redirect_url = reverse("eleve:notifications_eleve")
        except Exception:
            default_redirect_url = "/eleve/notifications/"

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
                    [eleve],
                    push_title,
                    push_body,
                    pushdata_with_url,
                )

                if push_result.get("success_count", 0) > 0:
                    notification.notification_push_envoyee = True
                    notification.save(update_fields=["notification_push_envoyee", "date_modification"])
            except Exception as exc:  # pragma: no cover
                logger.error(
                    "Erreur lors de l'envoi de la notification push élève: %s",
                    exc,
                    exc_info=True,
                )

        return {"created": 1, "push": push_result}

    @classmethod
    def notify_annonce(cls, eleve: Eleve, annonce, *, source=None) -> dict:
        etab_nom = getattr(annonce.etablissement, "nom", "Votre établissement")
        titre = f"[{etab_nom}] Nouvelle annonce"
        message = annonce.titre

        payload = {
            "annonce_id": getattr(annonce, "id", None),
            "titre": annonce.titre,
        }

        return cls._dispatch(
            eleve,
            type_notification="annonce",
            titre=titre,
            message=message,
            payload=payload,
            source=source or annonce,
        )

    @classmethod
    def notify_bulletin(cls, eleve: Eleve, *, periode_nom: str, source=None) -> dict:
        titre = "Bulletin disponible"
        message = f"Le bulletin de {periode_nom} est disponible dans votre espace."

        payload = {
            "periode_nom": periode_nom,
        }

        return cls._dispatch(
            eleve,
            type_notification="bulletin",
            titre=titre,
            message=message,
            payload=payload,
            source=source,
        )

    @classmethod
    def notify_note(cls, eleve: Eleve, *, matiere_nom: str, details: dict, source=None) -> dict:
        titre = f"Nouvelle note en {matiere_nom}"
        message = details.get("message") or "Une nouvelle note est disponible."

        payload = {
            "matiere": matiere_nom,
            **details,
        }

        return cls._dispatch(
            eleve,
            type_notification="note",
            titre=titre,
            message=message,
            payload=payload,
            source=source,
        )

    @classmethod
    def notify_sanction(cls, eleve: Eleve, sanction) -> dict:
        gravite_label = (
            sanction.get_gravite_display()
            if hasattr(sanction, "get_gravite_display")
            else getattr(sanction, "gravite", "").title()
        )
        type_label = (
            sanction.get_type_sanction_display()
            if hasattr(sanction, "get_type_sanction_display")
            else getattr(sanction, "type_sanction", "Sanction")
        )

        titre = "Sanction disciplinaire"
        message = f"Sanction {gravite_label.lower()} : {type_label}."

        payload = {
            "sanction_id": getattr(sanction, "id", None),
            "gravite": getattr(sanction, "gravite", None),
            "type_sanction": getattr(sanction, "type_sanction", None),
            "date_sanction": getattr(sanction, "date_sanction", None).isoformat()
            if getattr(sanction, "date_sanction", None)
            else None,
        }

        return cls._dispatch(
            eleve,
            type_notification="sanction",
            titre=titre,
            message=message,
            payload=payload,
            source=sanction,
        )

    @classmethod
    def notify_custom(
        cls,
        eleve: Eleve,
        *,
        titre: str,
        message: str,
        payload: Optional[dict] = None,
        source=None,
    ) -> dict:
        return cls._dispatch(
            eleve,
            type_notification="information",
            titre=titre,
            message=message,
            payload=payload,
            source=source,
        )

    @classmethod
    def notify_presence(
        cls,
        presence,
        *,
        titre: Optional[str] = None,
        message: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> dict:
        eleve = getattr(presence, "eleve", None)
        if not eleve:
            return {"created": 0, "push": None}

        statut = getattr(presence, "statut", "")
        classe = getattr(eleve, "classe", None)
        classe_nom = getattr(classe, "nom", "sa classe")

        if titre is None or message is None:
            if statut == "present":
                titre = "Appel de classe"
                message = f"Vous avez été présent(e) pour {classe_nom} lors de l'appel."
            elif statut == "absent":
                titre = "Absence enregistrée"
                message = f"Vous avez été absent(e) pour {classe_nom} lors de l'appel."
            elif statut == "absent_justifie":
                titre = "Absence justifiée"
                message = f"Votre absence pour {classe_nom} a été enregistrée comme justifiée."
            elif statut == "retard":
                titre = "Retard enregistré"
                message = f"Vous avez été en retard pour {classe_nom} lors de l'appel."
            else:
                titre = "Appel de classe"
                message = f"Votre statut a été mis à jour pour {classe_nom}."

        base_payload = {
            "type": "presence",
            "presence_id": getattr(presence, "id", None),
            "statut": statut,
            "classe": classe_nom,
        }
        if payload:
            base_payload.update(payload)

        return cls._dispatch(
            eleve,
            type_notification="presence",
            titre=titre,
            message=message,
            payload=base_payload,
            source=presence,
        )

    @classmethod
    def notify_convocation(cls, convocation) -> dict:
        eleve = getattr(convocation, "eleve", None)
        if not eleve:
            return {"created": 0, "push": None}

        classe_nom = getattr(getattr(eleve, "classe", None), "nom", "sa classe")
        objet = getattr(convocation, "objet", "Convocation")
        motif = getattr(convocation, "motif", "")
        lieu = getattr(convocation, "lieu", "Bureau du Directeur")
        date_convocation = getattr(convocation, "date_convocation", None)
        heure_convocation = getattr(convocation, "heure_convocation", None)

        try:
            date_str = date_convocation.strftime("%d/%m/%Y") if date_convocation else ""
        except Exception:
            date_str = str(date_convocation) if date_convocation else ""

        try:
            heure_str = heure_convocation.strftime("%Hh%M") if heure_convocation else ""
        except Exception:
            heure_str = str(heure_convocation) if heure_convocation else ""

        titre = "Nouvelle convocation"
        message_parts = [f"Vous êtes convoqué(e) le {date_str}"]
        if heure_str:
            message_parts[-1] += f" à {heure_str}"
        message_parts[-1] += f" au {lieu}."
        message_parts.append(f"Objet : {objet}.")
        if motif:
            message_parts.append(f"Motif : {motif}.")
        message_parts.append(f"Classe : {classe_nom}.")
        message = " ".join(filter(None, message_parts))

        payload = {
            "convocation_id": getattr(convocation, "id", None),
            "objet": objet,
            "motif": motif,
            "lieu": lieu,
            "date": date_str,
            "heure": heure_str,
            "classe": classe_nom,
        }

        push_data = {
            "type": "convocation",
            "convocation_id": str(getattr(convocation, "id", "")),
            "eleve_id": str(getattr(eleve, "id", "")),
            "classe": classe_nom,
        }

        return cls._dispatch(
            eleve,
            type_notification="convocation",
            titre=titre,
            message=message,
            payload=payload,
            source=convocation,
            push_title=titre,
            push_body=message,
            push_data=push_data,
        )