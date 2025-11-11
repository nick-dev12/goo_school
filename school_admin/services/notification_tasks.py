"""
Tâches asynchrones liées aux notifications.
"""

from __future__ import annotations

import logging
import threading
from typing import Iterable, Sequence, TYPE_CHECKING

from django.db import transaction
from django.urls import reverse


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from school_admin.model.lien_familial_model import LienFamilial


def schedule_annonce_notification(annonce_id: int) -> None:
    """
    Programme l'envoi des notifications d'annonce une fois la transaction validée.
    """

    def _run_async() -> None:
        try:
            _send_annonce_notifications(annonce_id)
        except Exception as exc:  # pragma: no cover - suivi log
            logger.exception("Erreur lors de l'envoi des notifications d'annonce %s: %s", annonce_id, exc)

    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_async,
            name=f"annonce-notification-{annonce_id}",
            daemon=True,
        ).start()
    )


def _send_annonce_notifications(annonce_id: int) -> None:
    """
    Envoie les notifications d'une annonce publiée.
    """
    from school_admin.model.annonce_model import Annonce
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.professeur_model import Professeur
    from school_admin.model.lien_familial_model import LienFamilial
    from school_admin.services.firebase_service import FirebaseService

    try:
        annonce = (
            Annonce.objects.select_related("etablissement")
            .get(id=annonce_id, actif=True)
        )
    except Annonce.DoesNotExist:
        logger.warning("Annonce %s inexistante : notifications abandonnées", annonce_id)
        return

    if annonce.statut != "publiee":
        logger.info("Annonce %s non publiée, aucune notification envoyée", annonce_id)
        return

    destinataires = (
        annonce.destinataires
        if isinstance(annonce.destinataires, list)
        else [annonce.destinataires]
    )

    try:
        redirect_url_parent = reverse("school_admin:annonces_parent")
    except Exception:
        redirect_url_parent = "/parent/annonces/"

    try:
        redirect_url_enseignant = reverse("enseignant:annonces_enseignant")
    except Exception:
        redirect_url_enseignant = "/enseignant/annonces/"

    try:
        redirect_url_eleve = reverse("eleve:annonces_eleve")
    except Exception:
        redirect_url_eleve = "/eleve/annonces/"

    etab_nom = getattr(annonce.etablissement, "nom", "Votre établissement")

    notify_parents = "tous" in destinataires or "parents" in destinataires
    notify_enseignants = "tous" in destinataires or "enseignants" in destinataires
    notify_eleves = "tous" in destinataires or "eleves" in destinataires

    if notify_parents:
        liens = (
            LienFamilial.objects.select_related("eleve", "parent")
            .filter(
                eleve__etablissement=annonce.etablissement,
                actif=True,
                statut="valide",
                parent__actif=True,
            )
        )
        _notify_parent_links(
            liens,
            titre=f"[{etab_nom}] Annonce : {annonce.titre}",
            message=annonce.contenu[:200],
            redirect_url=redirect_url_parent,
            source=annonce,
            push_data_type="annonce_parent",
            payload_extra={
                "annonce_id": str(annonce.id),
                "etablissement_id": str(annonce.etablissement_id),
            },
        )

    if notify_enseignants:
        enseignants = list(
            Professeur.objects.filter(etablissement=annonce.etablissement, actif=True)
        )
        _notify_users_push(
            enseignants,
            titre=f"[{etab_nom}] {annonce.titre}",
            message=annonce.contenu[:150],
            redirect_url=redirect_url_enseignant,
            data_type="annonce",
            extra_data={
                "annonce_id": str(annonce.id),
                "etablissement_id": str(annonce.etablissement_id),
            },
        )

        try:
            from school_admin.services.enseignant_notification_service import (
                EnseignantNotificationService,
            )

            for prof in enseignants:
                try:
                    EnseignantNotificationService.notify_annonce(
                        enseignant=prof,
                        annonce=annonce,
                        source=annonce,
                    )
                except Exception:  # pragma: no cover
                    logger.exception(
                        "Échec notification enseignant %s pour annonce %s",
                        getattr(prof, "id", "N/A"),
                        annonce_id,
                    )
        except Exception:  # pragma: no cover
            logger.exception(
                "Erreur lors de la notification des enseignants pour l'annonce %s",
                annonce_id,
            )

    if notify_eleves:
        eleves = list(
            Eleve.objects.filter(etablissement=annonce.etablissement, actif=True)
        )
        _notify_users_push(
            eleves,
            titre=f"[{etab_nom}] {annonce.titre}",
            message=annonce.contenu[:150],
            redirect_url=redirect_url_eleve,
            data_type="annonce",
            extra_data={
                "annonce_id": str(annonce.id),
                "etablissement_id": str(annonce.etablissement_id),
            },
        )

        try:
            from school_admin.services.eleve_notification_service import (
                EleveNotificationService,
            )

            for eleve in eleves:
                try:
                    EleveNotificationService.notify_annonce(
                        eleve=eleve,
                        annonce=annonce,
                        source=annonce,
                    )
                except Exception:  # pragma: no cover
                    logger.exception(
                        "Échec notification élève %s pour annonce %s",
                        getattr(eleve, "id", "N/A"),
                        annonce_id,
                    )
        except Exception:  # pragma: no cover
            logger.exception(
                "Erreur lors de la notification élèves pour l'annonce %s",
                annonce_id,
            )


def _notify_parent_links(
    liens: Iterable["LienFamilial"],
    titre: str,
    message: str,
    redirect_url: str,
    source,
    push_data_type: str = "annonce_parent",
    payload_extra: dict | None = None,
) -> None:
    """
    Envoie des notifications personnalisées aux parents via les liens familiaux.
    """
    from school_admin.services.parent_notification_service import ParentNotificationService

    for lien in liens:
        try:
            message_personnalise = (
                message.format(enfant=lien.eleve.nom_complet)
                if message and "{enfant}" in message
                else message
            )

            payload = {
                "url": redirect_url,
            }
            if payload_extra:
                payload.update(payload_extra)

            push_data = {
                "type": push_data_type,
                "url": redirect_url,
            }
            if payload_extra:
                push_data.update(payload_extra)

            ParentNotificationService.notify_custom(
                eleve=lien.eleve,
                type_notification="information",
                titre=titre,
                message=message_personnalise,
                payload=payload,
                source=source,
                push_title=titre,
                push_body=message_personnalise,
                push_data=push_data,
            )
        except Exception:  # pragma: no cover - suivre log
            logger.exception(
                "Échec notification parent pour lien %s (objet %s)",
                lien.id,
                getattr(source, "id", "N/A"),
            )


def _notify_users_push(
    users: Sequence[object],
    titre: str,
    message: str,
    redirect_url: str,
    data_type: str = "annonce",
    extra_data: dict | None = None,
) -> None:
    """
    Envoie une notification push générique aux utilisateurs fournis.
    """
    from school_admin.services.firebase_service import FirebaseService

    if not users:
        return

    try:
        FirebaseService.send_notification_to_multiple_users(
            users=users,
            title=titre,
            body=message,
            data={
                "type": data_type,
                "url": redirect_url,
                **(extra_data or {}),
            },
        )
    except Exception:  # pragma: no cover - suivi
        logger.exception("Erreur lors de l'envoi push aux utilisateurs")


def schedule_emploi_publication(emploi_id: int) -> None:
    """
    Programme l'envoi des notifications lors de la publication d'un emploi du temps.
    """

    def _run_async() -> None:
        try:
            _send_emploi_publication(emploi_id)
        except Exception as exc:  # pragma: no cover
            logger.exception("Erreur lors de la notification emploi du temps %s: %s", emploi_id, exc)

    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_async,
            name=f"emploi-publication-{emploi_id}",
            daemon=True,
        ).start()
    )


def _send_emploi_publication(emploi_id: int) -> None:
    """
    Envoie les notifications suite à la publication d'un emploi du temps.
    """
    from school_admin.model.emploi_du_temps_model import EmploiDuTemps
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.professeur_model import Professeur
    from school_admin.model.lien_familial_model import LienFamilial

    try:
        emploi = (
            EmploiDuTemps.objects.select_related("classe__etablissement")
            .get(id=emploi_id)
        )
    except EmploiDuTemps.DoesNotExist:
        logger.warning("Emploi du temps %s introuvable pour notification", emploi_id)
        return

    classe = emploi.classe
    etablissement = classe.etablissement
    etab_nom = getattr(etablissement, "nom", "Votre établissement")

    titre_general = f"[{etab_nom}] Emploi du temps mis à jour - {classe.nom}"
    message_general = "L'emploi du temps a été modifié et mis à jour. Veuillez regarder les nouveaux programmes."

    redirect_teacher = reverse("enseignant:emploi_du_temps")
    redirect_student = reverse("eleve:emploi_du_temps")
    try:
        redirect_parent = reverse("school_admin:notifications_parent")
    except Exception:
        redirect_parent = "/parent/notifications/"

    # Notifications enseignants
    enseignants = list(classe.professeurs.filter(actif=True))
    _notify_users_push(
        enseignants,
        titre=titre_general,
        message=message_general,
        redirect_url=redirect_teacher,
        data_type="emploi_du_temps",
        extra_data={
            "emploi_id": str(emploi.id),
            "classe_id": str(classe.id),
        },
    )

    # Notifications élèves
    eleves = list(Eleve.objects.filter(classe=classe, actif=True))
    _notify_users_push(
        eleves,
        titre=titre_general,
        message=message_general,
        redirect_url=redirect_student,
        data_type="emploi_du_temps",
        extra_data={
            "emploi_id": str(emploi.id),
            "classe_id": str(classe.id),
        },
    )

    # Notifications parents
    liens = (
        LienFamilial.objects.select_related("eleve", "parent")
        .filter(
            eleve__classe=classe,
            actif=True,
            statut="valide",
            parent__actif=True,
        )
    )
    _notify_parent_links(
        liens,
        titre=titre_general,
        message="L'emploi du temps a été modifié et mis à jour pour {enfant}. Veuillez regarder les nouveaux programmes.",
        redirect_url=redirect_parent,
        source=emploi,
        push_data_type="emploi_parent",
        payload_extra={
            "emploi_id": str(emploi.id),
            "classe_id": str(classe.id),
        },
    )


def schedule_bulletin_publication(classe_id: int, periode_id: int, etablissement_id: int) -> None:
    """
    Programme l'envoi asynchrone des notifications de publication de bulletins.
    """

    def _run_async() -> None:
        try:
            _send_bulletin_publication(classe_id, periode_id, etablissement_id)
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "Erreur lors de l'envoi des notifications de publication des bulletins (classe %s, période %s): %s",
                classe_id,
                periode_id,
                exc,
            )

    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_async,
            name=f"bulletin-publication-{classe_id}-{periode_id}",
            daemon=True,
        ).start()
    )


def _send_bulletin_publication(classe_id: int, periode_id: int, etablissement_id: int) -> None:
    """
    Envoie les notifications suite à la publication des bulletins d'une classe.
    """
    from django.urls import reverse
    from school_admin.model.classe_model import Classe
    from school_admin.model.periode_model import PeriodeScolaire
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.lien_familial_model import LienFamilial
    from school_admin.services.parent_notification_service import ParentNotificationService  # noqa

    try:
        classe = Classe.objects.select_related("etablissement").get(id=classe_id)
    except Classe.DoesNotExist:
        logger.warning("Classe %s introuvable pour notification de bulletin", classe_id)
        return

    if classe.etablissement_id != etablissement_id:
        logger.warning(
            "Classe %s ne correspond pas à l'établissement %s, abandon de l'envoi des notifications de bulletins",
            classe_id,
            etablissement_id,
        )
        return

    try:
        periode = PeriodeScolaire.objects.get(id=periode_id, etablissement_id=etablissement_id)
    except PeriodeScolaire.DoesNotExist:
        logger.warning("Période %s introuvable pour les notifications de bulletin", periode_id)
        return

    etab_nom = getattr(classe.etablissement, "nom", "Votre établissement")
    periode_nom = getattr(periode, "nom_periode", None) or getattr(periode, "nom", "la période")

    titre_general = f"[{etab_nom}] Bulletins disponibles - {classe.nom}"
    message_eleve = f"Les bulletins de {periode_nom} sont disponibles dans votre espace."
    redirect_eleves = reverse("eleve:notes_evaluations")

    eleves = list(Eleve.objects.filter(classe=classe, actif=True))
    _notify_users_push(
        eleves,
        titre=titre_general,
        message=message_eleve,
        redirect_url=redirect_eleves,
        data_type="bulletin",
        extra_data={
            "classe_id": str(classe.id),
            "periode_id": str(periode.id),
        },
    )

    liens = (
        LienFamilial.objects.select_related("eleve", "parent")
        .filter(
            eleve__classe=classe,
            actif=True,
            statut="valide",
            parent__actif=True,
        )
    )
    try:
        redirect_parent = reverse("school_admin:notifications_parent")
    except Exception:
        redirect_parent = "/parent/notifications/"

    _notify_parent_links(
        liens,
        titre=titre_general,
        message=f"Le bulletin de {{enfant}} pour {periode_nom} est disponible.",
        redirect_url=redirect_parent,
        source=periode,
        push_data_type="bulletin_parent",
        payload_extra={
            "classe_id": str(classe.id),
            "periode_id": str(periode.id),
        },
    )

    try:
        from school_admin.services.eleve_notification_service import EleveNotificationService

        for eleve in eleves:
            try:
                EleveNotificationService.notify_bulletin(
                    eleve=eleve,
                    periode_nom=periode_nom,
                    source=periode,
                )
            except Exception:  # pragma: no cover
                logger.exception(
                    "Échec notification élève %s pour bulletin", getattr(eleve, "id", "N/A")
                )
    except Exception:  # pragma: no cover
        logger.exception("Erreur lors de la notification élèves pour les bulletins")


