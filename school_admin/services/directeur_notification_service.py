"""Service centralisant la construction et l'envoi des notifications destinées aux directeurs."""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from django.urls import reverse
from django.utils import timezone

from school_admin.model.etablissement_model import Etablissement
from school_admin.model.notification_directeur_model import NotificationDirecteur

logger = logging.getLogger(__name__)


class DirecteurNotificationService:
    """Service utilitaire pour notifier les directeurs."""

    @classmethod
    def _dispatch(
        cls,
        etablissement: Optional[Etablissement],
        type_notification: str,
        titre: str,
        message: str,
        payload: Optional[dict] = None,
        source=None,
        push_title: Optional[str] = None,
        push_body: Optional[str] = None,
        push_data: Optional[dict] = None,
    ) -> dict:
        if not etablissement or not isinstance(etablissement, Etablissement):
            logger.debug("Notification directeur ignorée : établissement invalide")
            return {"created": 0, "push": None}

        notification = NotificationDirecteur.objects.create(
            etablissement=etablissement,
            titre=titre,
            message=message,
            type_notification=type_notification,
            donnees=payload or {},
            source_object=source,
            date_evenement=timezone.now(),
        )

        try:
            default_redirect_url = reverse("directeur:notifications_directeur")
        except Exception:
            default_redirect_url = "/directeur/notifications/"

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
                    [etablissement],
                    push_title,
                    push_body,
                    pushdata_with_url,
                )

                if push_result.get("success_count", 0) > 0:
                    notification.notification_push_envoyee = True
                    notification.save(update_fields=["notification_push_envoyee", "date_modification"])
            except Exception as exc:  # pragma: no cover
                logger.error(
                    "Erreur lors de l'envoi de la notification push directeur: %s",
                    exc,
                    exc_info=True,
                )

        return {"created": 1, "push": push_result}

    @classmethod
    def notify_releve_submission(
        cls,
        *,
        classe,
        professeur,
        periode,
        matieres: Iterable[str],
        source=None,
    ) -> dict:
        etablissement = getattr(classe, "etablissement", None) or getattr(professeur, "etablissement", None)
        if not etablissement:
            return {"created": 0, "push": None}

        periode_nom = getattr(periode, "nom_periode", None) or getattr(periode, "nom", "la période")
        matieres_list = [m for m in matieres if m]
        if not matieres_list:
            matieres_str = "les matières attribuées"
        elif len(matieres_list) == 1:
            matieres_str = matieres_list[0]
        else:
            apercu = ", ".join(matieres_list[:3])
            reste = len(matieres_list) - 3
            matieres_str = apercu if reste <= 0 else f"{apercu} et {reste} autre(s)"

        professeur_nom = getattr(professeur, "nom_complet", None)
        if not professeur_nom and professeur is not None:
            professeur_nom = str(professeur)
        if not professeur_nom:
            professeur_nom = "Professeur"

        titre = f"Relevé soumis - {classe.nom}"
        message = (
            f"{professeur_nom} a soumis le relevé de {matieres_str} "
            f"pour la classe {classe.nom} ({periode_nom})."
        )

        payload = {
            "classe_id": getattr(classe, "id", None),
            "classe_nom": getattr(classe, "nom", None),
            "professeur_id": getattr(professeur, "id", None),
            "professeur_nom": professeur_nom,
            "periode_id": getattr(periode, "id", None),
            "periode_nom": periode_nom,
            "matieres": list(matieres_list),
        }

        push_title = f"📊 Relevé soumis - {classe.nom}"
        push_body = message
        push_data = {
            "type": "releve_soumis",
            "classe_id": str(getattr(classe, "id", "")),
            "periode_id": str(getattr(periode, "id", "")),
        }

        return cls._dispatch(
            etablissement,
            type_notification="releve",
            titre=titre,
            message=message,
            payload=payload,
            source=source,
            push_title=push_title,
            push_body=push_body,
            push_data=push_data,
        )

    @classmethod
    def notify_sanction(cls, sanction) -> dict:
        if not sanction:
            return {"created": 0, "push": None}

        etablissement = getattr(sanction, "etablissement", None)
        if not etablissement:
            return {"created": 0, "push": None}

        eleve = getattr(sanction, "eleve", None)
        classe = getattr(sanction, "classe", None)
        professeur = getattr(sanction, "professeur", None)

        eleve_nom = getattr(eleve, "nom_complet", "Élève") if eleve else "Élève"
        classe_nom = getattr(classe, "nom", "classe") if classe else "classe"
        professeur_nom = (
            getattr(professeur, "nom_complet", None)
            if professeur
            else getattr(sanction, "attribue_par_nom", "Un enseignant")
        )
        if not professeur_nom and professeur is not None:
            professeur_nom = str(professeur)
        if not professeur_nom:
            professeur_nom = "Un enseignant"

        gravite_code = getattr(sanction, "gravite", "") or ""
        gravite_label = (
            sanction.get_gravite_display() if hasattr(sanction, "get_gravite_display") else gravite_code
        ) or "Moyenne"
        type_label = (
            sanction.get_type_sanction_display()
            if hasattr(sanction, "get_type_sanction_display")
            else getattr(sanction, "type_sanction", "Sanction")
        ) or "Sanction"

        message = (
            f"{professeur_nom} a infligé une sanction {gravite_label.lower()} "
            f"({type_label}) à {eleve_nom} dans {classe_nom}."
        )

        payload = {
            "sanction_id": getattr(sanction, "id", None),
            "eleve_id": getattr(eleve, "id", None),
            "eleve_nom": eleve_nom,
            "classe_id": getattr(classe, "id", None),
            "classe_nom": classe_nom,
            "professeur_id": getattr(professeur, "id", None) if professeur else None,
            "professeur_nom": professeur_nom,
            "gravite": gravite_code,
            "type_sanction": getattr(sanction, "type_sanction", None),
            "date_sanction": (
                getattr(sanction, "date_sanction", None).isoformat()
                if getattr(sanction, "date_sanction", None)
                else None
            ),
        }

        push_title = (
            f"🚨 Sanction - {eleve_nom}"
            if gravite_code in ["grave", "tres_grave"]
            else f"⚠️ Sanction - {eleve_nom}"
        )
        push_body = message
        push_data = {
            "type": "sanction",
            "sanction_id": str(getattr(sanction, "id", "")),
            "classe_id": str(getattr(classe, "id", "")) if classe else "",
        }

        return cls._dispatch(
            etablissement,
            type_notification="sanction",
            titre=f"Sanction - {eleve_nom}",
            message=message,
            payload=payload,
            source=sanction,
            push_title=push_title,
            push_body=push_body,
            push_data=push_data,
        )

