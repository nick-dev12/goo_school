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
    from school_admin.services.task_dispatcher import run_after_commit

    run_after_commit(
        _send_annonce_notifications,
        'school_admin.tasks.celery_tasks.send_annonce_notifications_task',
        annonce_id,
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
    from school_admin.services.task_dispatcher import run_after_commit

    run_after_commit(
        _send_emploi_publication,
        'school_admin.tasks.celery_tasks.send_emploi_publication_task',
        emploi_id,
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
    # Récupérer tous les créneaux de l'emploi du temps avec leurs professeurs
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
    
    creneaux = CreneauEmploiDuTemps.objects.filter(
        emploi_du_temps=emploi,
        professeur__isnull=False
    ).select_related('professeur')
    
    # Identifier tous les professeurs qui ont des créneaux dans cet emploi
    # Seuls ces professeurs doivent être notifiés
    professeurs_avec_creneaux = set()
    for creneau in creneaux:
        if creneau.professeur and creneau.professeur.actif:
            professeurs_avec_creneaux.add(creneau.professeur)
    
    # Envoyer les notifications uniquement aux professeurs qui ont des créneaux dans cet emploi
    if professeurs_avec_creneaux:
        _notify_users_push(
            list(professeurs_avec_creneaux),
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


def schedule_evaluation_notification(evaluation_id: int) -> None:
    """
    Programme l'envoi asynchrone des notifications lors de la création d'une évaluation.
    """
    def _run_async() -> None:
        try:
            _send_evaluation_notifications(evaluation_id)
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "Erreur lors de l'envoi des notifications d'évaluation %s: %s",
                evaluation_id,
                exc,
            )

    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_async,
            name=f"evaluation-notification-{evaluation_id}",
            daemon=True,
        ).start()
    )


def _send_evaluation_notifications(evaluation_id: int) -> None:
    """
    Envoie les notifications suite à la création d'une évaluation.
    Notifie les élèves et leurs parents.
    """
    from django.utils.formats import date_format
    from django.utils.dateparse import parse_date
    from datetime import datetime, date
    from school_admin.model.evaluation_model import Evaluation
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.inscription_eleve_model import InscriptionEleve
    from school_admin.model.classe_model import Classe
    from school_admin.services.eleve_notification_service import EleveNotificationService
    from school_admin.services.parent_notification_service import ParentNotificationService
    from school_admin.services.firebase_service import FirebaseService
    from django.db.models.functions import Lower

    try:
        evaluation = Evaluation.objects.select_related(
            'classe',
            'classe__etablissement',
            'professeur',
            'matiere',
            'annee_scolaire'
        ).get(id=evaluation_id, actif=True)
    except Evaluation.DoesNotExist:
        logger.warning("Évaluation %s inexistante : notifications abandonnées", evaluation_id)
        return

    classe = evaluation.classe
    etablissement = classe.etablissement if hasattr(classe, 'etablissement') else None
    matiere = evaluation.matiere
    annee_scolaire = evaluation.annee_scolaire

    # Récupérer les élèves de la classe pour l'année scolaire
    eleves = []
    if annee_scolaire and etablissement:
        inscriptions = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire,
            classe=classe,
            etablissement=etablissement
        ).select_related('eleve').order_by(Lower('eleve__nom'), Lower('eleve__prenom'))
        
        eleves_ids = [inscription.eleve_id for inscription in inscriptions if inscription.eleve and inscription.eleve.actif]
        eleves = list(Eleve.objects.filter(id__in=eleves_ids, actif=True).order_by(Lower('nom'), Lower('prenom')))
    else:
        # Fallback : élèves directement liés à la classe
        eleves = list(Eleve.objects.filter(classe=classe, actif=True).order_by(Lower('nom'), Lower('prenom')))

    if not eleves:
        logger.info("Aucun élève trouvé pour la classe %s, aucune notification envoyée", classe.id)
        return

    # Préparer les données de notification
    date_obj = evaluation.date_evaluation
    if isinstance(date_obj, str):
        parsed = parse_date(date_obj)
        date_obj = parsed or date_obj
    date_claire = date_format(date_obj, "l d F Y", use_l10n=True) if isinstance(date_obj, (datetime, date)) else str(date_obj)
    classe_nom = classe.nom
    matiere_nom = matiere.nom if matiere else ""
    professeur_nom = getattr(evaluation.professeur, 'nom_complet', str(evaluation.professeur))
    
    payload_base = {
        'evaluation_id': evaluation.id,
        'classe': classe_nom,
        'matiere': matiere_nom,
        'date': date_claire,
        'professeur': professeur_nom,
    }

    # Envoyer les notifications pour chaque élève
    for eleve in eleves:
        eleve_nom = getattr(eleve, 'nom_complet', f"{eleve.nom} {eleve.prenom}") if hasattr(eleve, 'nom_complet') else f"{eleve.nom} {eleve.prenom}"
        
        # Notification élève
        try:
            EleveNotificationService.notify_custom(
                eleve=eleve,
                titre=f"Évaluation en {matiere_nom}",
                message=f"Une évaluation de {matiere_nom} est programmée pour la classe {classe_nom} le {date_claire}.",
                payload={**payload_base, 'eleve': eleve_nom},
                source=evaluation,
                type_notification="evaluation",
            )
        except Exception as notify_error:
            logger.error(
                "Erreur notification élève pour évaluation %s (élève %s) : %s",
                evaluation.id,
                eleve.id,
                notify_error,
                exc_info=True,
            )
        
        # Push notification élève
        try:
            FirebaseService.send_notification_to_multiple_users(
                users=[eleve],
                title=f"📘 Évaluation en {matiere_nom}",
                body=f"{classe_nom} : évaluation prévue le {date_claire}.",
                data={
                    'type': 'evaluation',
                    'classe': classe_nom,
                    'matiere': matiere_nom,
                    'date': date_claire,
                    'evaluation_id': str(evaluation.id),
                },
            )
        except Exception as push_error:
            logger.error(
                "Erreur envoi push élève pour évaluation %s (élève %s) : %s",
                evaluation.id,
                eleve.id,
                push_error,
                exc_info=True,
            )
        
        # Notification parent
        try:
            ParentNotificationService.notify_custom(
                eleve=eleve,
                type_notification="evaluation",
                titre=f"Évaluation en {matiere_nom}",
                message=f"Votre enfant {eleve_nom} en {classe_nom} a une évaluation programmée le {date_claire} en {matiere_nom}.",
                payload={**payload_base, 'eleve': eleve_nom},
                source=evaluation,
                push_title=f"Évaluation prévue en {matiere_nom}",
                push_body=f"{eleve_nom} en {classe_nom} passera une évaluation le {date_claire}.",
                push_data={
                    'type': 'evaluation',
                    'classe': classe_nom,
                    'matiere': matiere_nom,
                    'date': date_claire,
                    'evaluation_id': str(evaluation.id),
                    'eleve_id': str(eleve.id),
                },
            )
        except Exception as parent_notify_error:
            logger.error(
                "Erreur notification parent pour évaluation %s (élève %s) : %s",
                evaluation.id,
                eleve.id,
                parent_notify_error,
                exc_info=True,
            )

    logger.info(
        "Notifications d'évaluation %s envoyées pour %d élève(s)",
        evaluation.id,
        len(eleves),
    )


def schedule_evaluation_primaire_notification(evaluation_id: int) -> None:
    """
    Programme l'envoi asynchrone des notifications lors de la création d'une évaluation primaire.
    """
    def _run_async() -> None:
        try:
            _send_evaluation_primaire_notifications(evaluation_id)
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "Erreur lors de l'envoi des notifications d'évaluation primaire %s: %s",
                evaluation_id,
                exc,
            )

    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_async,
            name=f"evaluation-primaire-notification-{evaluation_id}",
            daemon=True,
        ).start()
    )


def _send_evaluation_primaire_notifications(evaluation_id: int) -> None:
    """
    Envoie les notifications suite à la création d'une évaluation primaire.
    Notifie les élèves et leurs parents.
    """
    from django.utils.formats import date_format
    from django.utils.dateparse import parse_date
    from datetime import datetime, date
    from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.inscription_eleve_model import InscriptionEleve
    from school_admin.model.classe_model import Classe
    from school_admin.services.eleve_notification_service import EleveNotificationService
    from school_admin.services.parent_notification_service import ParentNotificationService
    from school_admin.services.firebase_service import FirebaseService
    from django.db.models.functions import Lower

    try:
        evaluation = EvaluationPrimaire.objects.select_related(
            'classe',
            'classe__etablissement',
            'professeur',
            'matiere',
            'annee_scolaire'
        ).get(id=evaluation_id, actif=True)
    except EvaluationPrimaire.DoesNotExist:
        logger.warning("Évaluation primaire %s inexistante : notifications abandonnées", evaluation_id)
        return

    classe = evaluation.classe
    etablissement = classe.etablissement if hasattr(classe, 'etablissement') else None
    matiere = evaluation.matiere
    annee_scolaire = evaluation.annee_scolaire

    # Récupérer les élèves de la classe pour l'année scolaire
    eleves = []
    if annee_scolaire and etablissement:
        inscriptions = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire,
            classe=classe,
            etablissement=etablissement
        ).select_related('eleve').order_by(Lower('eleve__nom'), Lower('eleve__prenom'))
        
        eleves_ids = [inscription.eleve_id for inscription in inscriptions if inscription.eleve and inscription.eleve.actif]
        eleves = list(Eleve.objects.filter(id__in=eleves_ids, actif=True).order_by(Lower('nom'), Lower('prenom')))
    else:
        # Fallback : élèves directement liés à la classe
        eleves = list(Eleve.objects.filter(classe=classe, actif=True).order_by(Lower('nom'), Lower('prenom')))

    if not eleves:
        logger.info("Aucun élève trouvé pour la classe %s, aucune notification envoyée", classe.id)
        return

    # Préparer les données de notification
    date_obj = evaluation.date_evaluation
    if isinstance(date_obj, str):
        parsed = parse_date(date_obj)
        date_obj = parsed or date_obj
    date_claire = date_format(date_obj, "l d F Y", use_l10n=True) if isinstance(date_obj, (datetime, date)) else str(date_obj)
    classe_nom = classe.nom
    matiere_nom = matiere.nom if matiere else ""
    professeur_nom = getattr(evaluation.professeur, 'nom_complet', str(evaluation.professeur))
    
    payload_base = {
        'evaluation_id': evaluation.id,
        'classe': classe_nom,
        'matiere': matiere_nom,
        'date': date_claire,
        'professeur': professeur_nom,
    }

    # Envoyer les notifications pour chaque élève
    for eleve in eleves:
        eleve_nom = getattr(eleve, 'nom_complet', f"{eleve.nom} {eleve.prenom}") if hasattr(eleve, 'nom_complet') else f"{eleve.nom} {eleve.prenom}"
        
        # Notification élève
        try:
            EleveNotificationService.notify_custom(
                eleve=eleve,
                titre=f"Évaluation en {matiere_nom}",
                message=f"Une évaluation de {matiere_nom} est programmée pour la classe {classe_nom} le {date_claire}. Prépare-toi !",
                payload={**payload_base, 'eleve': eleve_nom},
                source=evaluation,
                type_notification="evaluation",
            )
        except Exception as notify_error:
            logger.error(
                "Erreur notification élève pour évaluation primaire %s (élève %s) : %s",
                evaluation.id,
                eleve.id,
                notify_error,
                exc_info=True,
            )
        
        # Push notification élève
        try:
            FirebaseService.send_notification_to_multiple_users(
                users=[eleve],
                title=f"📘 Évaluation en {matiere_nom}",
                body=f"{classe_nom} : évaluation prévue le {date_claire}.",
                data={
                    'type': 'evaluation',
                    'classe': classe_nom,
                    'matiere': matiere_nom,
                    'date': date_claire,
                    'evaluation_id': str(evaluation.id),
                },
            )
        except Exception as push_error:
            logger.error(
                "Erreur envoi push élève pour évaluation primaire %s (élève %s) : %s",
                evaluation.id,
                eleve.id,
                push_error,
                exc_info=True,
            )
        
        # Notification parent
        try:
            ParentNotificationService.notify_custom(
                eleve=eleve,
                type_notification="evaluation",
                titre=f"Évaluation en {matiere_nom}",
                message=f"Votre enfant {eleve_nom} en {classe_nom} a une évaluation programmée le {date_claire} en {matiere_nom}.",
                payload={**payload_base, 'eleve': eleve_nom},
                source=evaluation,
                push_title=f"Évaluation prévue en {matiere_nom}",
                push_body=f"{eleve_nom} en {classe_nom} passera une évaluation le {date_claire}.",
                push_data={
                    'type': 'evaluation',
                    'classe': classe_nom,
                    'matiere': matiere_nom,
                    'date': date_claire,
                    'evaluation_id': str(evaluation.id),
                    'eleve_id': str(eleve.id),
                },
            )
        except Exception as parent_notify_error:
            logger.error(
                "Erreur notification parent pour évaluation primaire %s (élève %s) : %s",
                evaluation.id,
                eleve.id,
                parent_notify_error,
                exc_info=True,
            )

    logger.info(
        "Notifications d'évaluation primaire %s envoyées pour %d élève(s)",
        evaluation.id,
        len(eleves),
    )


def schedule_exercice_maison_notification(exercice_id: int) -> None:
    """
    Programme l'envoi asynchrone des notifications lors de la création d'un exercice de maison.
    Fonctionne pour les enseignants du secondaire et du primaire.
    """
    def _run_async() -> None:
        try:
            _send_exercice_maison_notifications(exercice_id)
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "Erreur lors de l'envoi des notifications d'exercice de maison %s: %s",
                exercice_id,
                exc,
            )

    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_async,
            name=f"exercice-maison-notification-{exercice_id}",
            daemon=True,
        ).start()
    )


def _send_exercice_maison_notifications(exercice_id: int) -> None:
    """
    Envoie les notifications suite à la création d'un exercice de maison.
    Notifie les élèves et leurs parents.
    Fonctionne pour les enseignants du secondaire et du primaire.
    """
    from django.utils.formats import date_format
    from school_admin.model.exercice_maison_model import ExerciceMaison
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.inscription_eleve_model import InscriptionEleve
    from school_admin.services.eleve_notification_service import EleveNotificationService
    from school_admin.services.parent_notification_service import ParentNotificationService
    from django.db.models.functions import Lower

    try:
        exercice = ExerciceMaison.objects.select_related(
            'classe',
            'classe__etablissement',
            'professeur',
            'matiere',
            'annee_scolaire'
        ).get(id=exercice_id, actif=True)
    except ExerciceMaison.DoesNotExist:
        logger.warning("Exercice de maison %s inexistant : notifications abandonnées", exercice_id)
        return

    classe = exercice.classe
    etablissement = classe.etablissement if hasattr(classe, 'etablissement') else None
    matiere = exercice.matiere
    annee_scolaire = exercice.annee_scolaire

    # Récupérer les élèves de la classe pour l'année scolaire
    eleves = []
    if annee_scolaire and etablissement:
        inscriptions = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire,
            classe=classe,
            etablissement=etablissement
        ).select_related('eleve').order_by(Lower('eleve__nom'), Lower('eleve__prenom'))
        
        eleves_ids = [inscription.eleve_id for inscription in inscriptions if inscription.eleve and inscription.eleve.actif]
        eleves = list(Eleve.objects.filter(id__in=eleves_ids, actif=True).order_by(Lower('nom'), Lower('prenom')))
    else:
        # Fallback : élèves directement liés à la classe
        eleves = list(Eleve.objects.filter(classe=classe, actif=True).order_by(Lower('nom'), Lower('prenom')))

    if not eleves:
        logger.info("Aucun élève trouvé pour la classe %s, aucune notification envoyée", classe.id)
        return

    # Préparer les données de notification
    date_claire = date_format(exercice.date_rendu, "l d F Y", use_l10n=True)
    classe_nom = classe.nom
    matiere_nom = matiere.nom if matiere else ""
    
    payload_base = {
        'exercice_id': exercice.id,
        'classe': classe_nom,
        'matiere': matiere_nom,
        'date_rendu': date_claire,
        'titre': exercice.titre,
    }

    # Envoyer les notifications pour chaque élève
    for eleve in eleves:
        eleve_nom = getattr(eleve, 'nom_complet', f"{eleve.nom} {eleve.prenom}") if hasattr(eleve, 'nom_complet') else f"{eleve.nom} {eleve.prenom}"
        
        # Notification élève
        try:
            push_title = f"📝 Nouvel exercice en {matiere_nom}"
            push_body = f"Exercice \"{exercice.titre}\" à rendre le {date_claire}."
            push_data = {
                'type': 'exercice_maison',
                'classe': classe_nom,
                'matiere': matiere_nom,
                'date_rendu': date_claire,
                'exercice_id': str(exercice.id),
                'titre': exercice.titre,
            }
            
            EleveNotificationService._dispatch(
                eleve=eleve,
                type_notification="information",
                titre=f"Exercice en {matiere_nom}",
                message=f"Exercice \"{exercice.titre}\" à rendre le {date_claire} pour {classe_nom}.",
                payload={**payload_base, 'eleve': eleve_nom},
                source=exercice,
                push_title=push_title,
                push_body=push_body,
                push_data=push_data,
            )
        except Exception as notify_error:
            logger.error(
                "Erreur notification élève pour exercice %s (élève %s) : %s",
                exercice.id,
                eleve.id,
                notify_error,
                exc_info=True,
            )
        
        # Notification parent
        try:
            parent_push_title = f"📝 Nouvel exercice en {matiere_nom}"
            parent_push_body = f"Votre enfant {eleve_nom} doit rendre l'exercice \"{exercice.titre}\" le {date_claire}."
            parent_push_data = {
                'type': 'exercice_maison',
                'classe': classe_nom,
                'matiere': matiere_nom,
                'date_rendu': date_claire,
                'exercice_id': str(exercice.id),
                'eleve_id': str(eleve.id),
                'titre': exercice.titre,
            }
            
            ParentNotificationService.notify_custom(
                eleve=eleve,
                type_notification="information",
                titre=f"Exercice en {matiere_nom}",
                message=f"Votre enfant {eleve_nom} en {classe_nom} doit rendre l'exercice \"{exercice.titre}\" le {date_claire}.",
                payload={**payload_base, 'eleve': eleve_nom},
                source=exercice,
                push_title=parent_push_title,
                push_body=parent_push_body,
                push_data=parent_push_data,
            )
        except Exception as parent_notify_error:
            logger.error(
                "Erreur notification parent pour exercice %s (élève %s) : %s",
                exercice.id,
                eleve.id,
                parent_notify_error,
                exc_info=True,
            )

    logger.info(
        "Notifications d'exercice de maison %s envoyées pour %d élève(s)",
        exercice.id,
        len(eleves),
    )


def schedule_presence_notifications(presence_ids: list[int]) -> None:
    """
    Programme l'envoi asynchrone des notifications lors de la validation d'une liste de présence.
    Fonctionne pour les enseignants du secondaire et du primaire.
    """
    if not presence_ids:
        return
        
    def _run_async() -> None:
        try:
            _send_presence_notifications(presence_ids)
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "Erreur lors de l'envoi des notifications de présence: %s",
                exc,
            )

    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_async,
            name=f"presence-notifications-{len(presence_ids)}",
            daemon=True,
        ).start()
    )


def _send_presence_notifications(presence_ids: list[int]) -> None:
    """
    Envoie les notifications suite à la validation d'une liste de présence.
    Notifie les élèves et leurs parents.
    Fonctionne pour les enseignants du secondaire et du primaire.
    """
    from django.utils import timezone
    from django.utils.formats import date_format
    from school_admin.model.presence_model import Presence
    from school_admin.services.eleve_notification_service import EleveNotificationService
    from school_admin.services.parent_notification_service import ParentNotificationService
    from school_admin.services.firebase_service import FirebaseService
    import locale

    try:
        presences = Presence.objects.filter(id__in=presence_ids).select_related(
            'eleve',
            'classe',
            'matiere'
        )
    except Presence.DoesNotExist:
        logger.warning("Aucune présence trouvée avec les IDs fournis: %s", presence_ids)
        return

    if not presences.exists():
        logger.warning("Aucune présence trouvée avec les IDs fournis: %s", presence_ids)
        return

    # Récupérer les informations communes depuis la première présence
    first_presence = presences.first()
    classe = first_presence.classe
    date_presence = first_presence.date
    numero_appel = getattr(first_presence, 'numero_appel', 1)
    matiere = first_presence.matiere

    # Préparer la date en clair avec heure
    try:
        locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_TIME, 'French_France.1252')
        except:
            pass

    now = timezone.now()
    try:
        # Format: lundi 12 juillet 2025 à 12h00
        jour_semaine = now.strftime('%A')
        jour = now.strftime('%d')
        mois = now.strftime('%B')
        annee = now.strftime('%Y')
        heure = now.strftime('%H')
        minute = now.strftime('%M')
        date_claire = f"{jour_semaine} {jour} {mois} {annee} à {heure}h{minute}"
    except:
        date_claire = date_format(now, "l d F Y à H:i", use_l10n=True)

    # Envoyer les notifications pour chaque présence
    for presence in presences:
        try:
            presence.refresh_from_db(fields=["statut", "date_modification"])
        except Exception:
            pass

        statut = presence.statut
        eleve = presence.eleve

        # Déterminer le titre et le corps du message selon le statut
        if statut == 'present':
            title = "📋 Appel de classe"
            body = f"Vous avez été présent(e) lors de l'appel du {date_claire}."
        elif statut == 'absent':
            title = "⚠️ Absence enregistrée"
            body = f"Vous avez été absent(e) lors de l'appel du {date_claire}."
        elif statut == 'absent_justifie':
            title = "📋 Absence justifiée"
            body = f"Votre absence du {date_claire} a été enregistrée comme justifiée."
        elif statut == 'retard':
            title = "⏰ Retard enregistré"
            body = f"Vous avez été en retard lors de l'appel du {date_claire}."
        else:
            continue  # Statut inconnu, ignorer

        data = {
            'type': 'presence',
            'presence_id': str(presence.id),
            'statut': statut,
            'date': date_presence.isoformat(),
            'numero_appel': str(numero_appel),
            'classe': classe.nom,
            'url': '/eleve/dashboard/'
        }
        
        if matiere:
            data['matiere'] = matiere.nom
            data['matiere_id'] = str(matiere.id)

        # Notification élève via Firebase
        try:
            result = FirebaseService.send_notification_to_multiple_users(
                [eleve], title, body, data
            )
            if result.get('success_count', 0) > 0:
                logger.info(f"Notification de présence envoyée à {eleve.nom_complet} - Statut: {statut}")
            else:
                logger.warning(f"Échec de l'envoi de notification de présence à {eleve.nom_complet}")
        except Exception as push_error:
            logger.error(
                "Erreur envoi push élève pour présence %s (élève %s) : %s",
                presence.id,
                eleve.id,
                push_error,
                exc_info=True,
            )

        # Notification élève via EleveNotificationService
        try:
            EleveNotificationService.notify_presence(
                presence,
                titre=title,
                message=body,
                payload=data,
            )
        except Exception as notify_error:
            logger.error(
                "Erreur notification élève pour présence %s (élève %s) : %s",
                presence.id,
                eleve.id,
                notify_error,
                exc_info=True,
            )

        # Notification parent
        try:
            ParentNotificationService.notify_presence(
                presence,
                date_description=date_claire,
            )
        except Exception as parent_notify_error:
            logger.error(
                "Erreur notification parent pour présence %s (élève %s) : %s",
                presence.id,
                eleve.id,
                parent_notify_error,
                exc_info=True,
            )

    logger.info(
        "Notifications de présence envoyées pour %d présence(s)",
        len(presence_ids),
    )


def schedule_justification_note_directeur_notification(justification_id: int) -> None:
    """
    Programme l'envoi de la notification au directeur pour une justification de note
    une fois la transaction validée.
    """
    def _run_async() -> None:
        try:
            _send_justification_note_directeur_notification(justification_id)
        except Exception as exc:
            logger.exception(
                "Erreur lors de l'envoi de la notification directeur pour justification %s: %s",
                justification_id,
                exc
            )

    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_async,
            name=f"justification-note-directeur-{justification_id}",
            daemon=True,
        ).start()
    )


def _send_justification_note_directeur_notification(justification_id: int) -> None:
    """
    Envoie la notification au directeur pour une justification de note.
    """
    from school_admin.model.justification_note_model import JustificationNote
    from school_admin.services.directeur_notification_service import DirecteurNotificationService

    try:
        justification = JustificationNote.objects.select_related(
            'etablissement',
            'professeur',
            'eleve',
            'classe',
            'matiere',
            'evaluation',
            'evaluation_primaire',
            'note_examen',
        ).get(id=justification_id)
    except JustificationNote.DoesNotExist:
        logger.warning("JustificationNote %s introuvable pour notification directeur", justification_id)
        return

    try:
        DirecteurNotificationService.notify_justification_note(justification)
        logger.info(
            "Notification directeur envoyée pour justification de note %s",
            justification_id
        )
    except Exception as notification_error:
        logger.error(
            "Erreur lors de la notification directeur pour justification %s: %s",
            justification_id,
            notification_error,
            exc_info=True,
        )


