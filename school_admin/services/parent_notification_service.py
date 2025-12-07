"""
Service centralisant la construction et l'envoi des notifications destinées aux parents.
Les notifications sont persistées en base et envoyées via FCM lorsque des tokens sont disponibles.
"""

import logging
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from django.utils import timezone
from django.urls import reverse
from school_admin.model.notification_parent_model import NotificationParent
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.parent_model import Parent
from school_admin.model.eleve_model import Eleve

logger = logging.getLogger(__name__)


class ParentNotificationService:
    """
    Service centralisant la construction et l'envoi des notifications destinées aux parents.
    """
    
    @staticmethod
    def _get_redirect_url(type_notification: str, payload: Optional[dict] = None, eleve: Optional[Eleve] = None) -> str:
        """
        Génère l'URL de redirection appropriée selon le type de notification pour les parents.
        
        Args:
            type_notification: Le type de notification (evaluation, note, bulletin, etc.)
            payload: Les données de la notification (peut contenir des IDs spécifiques)
            eleve: L'élève concerné (pour les redirections vers le dashboard enfant)
        
        Returns:
            L'URL de redirection appropriée
        """
        try:
            if type_notification == "evaluation":
                # Rediriger vers le dashboard enfant (qui affiche les devoirs)
                if eleve:
                    return reverse("school_admin:dashboard_enfant", kwargs={"eleve_id": eleve.id})
                return reverse("school_admin:dashboard_parent")
            elif type_notification == "note":
                # Rediriger vers le dashboard enfant (qui affiche les notes)
                if eleve:
                    return reverse("school_admin:dashboard_enfant", kwargs={"eleve_id": eleve.id})
                return reverse("school_admin:dashboard_parent")
            elif type_notification == "bulletin":
                # Rediriger vers le dashboard enfant (qui affiche le bulletin)
                if eleve:
                    return reverse("school_admin:dashboard_enfant", kwargs={"eleve_id": eleve.id})
                return reverse("school_admin:dashboard_parent")
            elif type_notification == "presence":
                # Rediriger vers le dashboard enfant (qui affiche les présences)
                if eleve:
                    return reverse("school_admin:dashboard_enfant", kwargs={"eleve_id": eleve.id})
                return reverse("school_admin:dashboard_parent")
            elif type_notification == "sanction":
                # Rediriger vers le dashboard enfant (qui affiche les sanctions)
                if eleve:
                    return reverse("school_admin:dashboard_enfant", kwargs={"eleve_id": eleve.id})
                return reverse("school_admin:dashboard_parent")
            else:
                # Par défaut, rediriger vers le dashboard parent
                return reverse("school_admin:dashboard_parent")
        except Exception:
            # En cas d'erreur, retourner l'URL par défaut
            return "/parent/dashboard/"
    
    """Service utilitaire pour notifier les parents au sujet de leurs enfants."""

    @staticmethod
    def _get_parents_for_eleve(eleve: Eleve) -> Sequence[Parent]:
        """Retourne la liste des parents actifs et validés liés à un élève."""

        if eleve is None:
            return []

        parents_set = set()

        liens = LienFamilial.objects.select_related("parent").filter(
            eleve=eleve,
            actif=True,
            statut="valide",
            parent__actif=True,
        )
        for lien in liens:
            parents_set.add(lien.parent)

        try:
            parent_inscripteur = getattr(eleve, "parent_inscripteur", None)
        except Exception:
            parent_inscripteur = None

        if parent_inscripteur and parent_inscripteur.actif:
            parents_set.add(parent_inscripteur)

        if not parents_set:
            logger.debug("Aucun parent lié trouvé pour l'élève %s", eleve)

        return list(parents_set)

    @staticmethod
    def _format_classe(eleve: Eleve) -> str:
        if getattr(eleve, "classe", None) and eleve.classe:
            return eleve.classe.nom
        return "sa classe"

    @staticmethod
    def _format_score(note: Optional[Decimal], bareme: Optional[Decimal] = None) -> str:
        if note is None:
            return "-"
        # Convertir Decimal en float puis formatter à deux décimales lorsque nécessaire
        value = float(note) if isinstance(note, Decimal) else note
        score = f"{value:.2f}" if isinstance(value, float) else str(value)
        if bareme:
            bareme_value = float(bareme) if isinstance(bareme, Decimal) else bareme
            score = f"{score}/{bareme_value:g}" if isinstance(bareme_value, (int, float)) else f"{score}/{bareme_value}"
        return score

    @staticmethod
    def _format_date(date_obj) -> str:
        if not date_obj:
            return ""
        try:
            return timezone.localtime(date_obj).strftime("%d/%m/%Y à %Hh%M")
        except (ValueError, AttributeError, TypeError):
            try:
                return date_obj.strftime("%d/%m/%Y")
            except Exception:
                return str(date_obj)

    @classmethod
    def _dispatch(
        cls,
        eleve: Eleve,
        type_notification: str,
        titre: str,
        message: str,
        payload: Optional[dict] = None,
        source=None,
        push_title: Optional[str] = None,
        push_body: Optional[str] = None,
        push_data: Optional[dict] = None,
    ) -> dict:
        """
        Créé les notifications pour tous les parents liés et envoie une notification push si possible.
        Retourne un dictionnaire contenant des informations de suivi.
        """

        parents = cls._get_parents_for_eleve(eleve)
        if not parents:
            return {"created": 0, "push": None}

        # Générer l'URL de redirection appropriée selon le type de notification
        redirect_url = cls._get_redirect_url(type_notification, payload, eleve)
        
        # Ajouter l'URL de redirection au payload
        payload_with_url = payload.copy() if payload else {}
        payload_with_url['redirect_url'] = redirect_url
        payload_with_url['url'] = redirect_url

        notifications = []
        for parent in parents:
            notification = NotificationParent.objects.create(
                parent=parent,
                eleve=eleve,
                titre=titre,
                message=message,
                type_notification=type_notification,
                donnees=payload_with_url,
                date_evenement=timezone.now(),
                source_object=source,
            )
            notifications.append(notification)

        pushdata_with_url = push_data.copy() if push_data else {}
        pushdata_with_url['redirect_url'] = redirect_url
        pushdata_with_url['url'] = redirect_url

        push_result = None
        if push_title and push_body:
            try:
                from school_admin.services.firebase_service import FirebaseService

                push_result = FirebaseService.send_notification_to_multiple_users(
                    parents,
                    push_title,
                    push_body,
                    pushdata_with_url,
                )
                if push_result.get("success_count", 0) > 0:
                    NotificationParent.objects.filter(
                        id__in=[notif.id for notif in notifications]
                    ).update(notification_push_envoyee=True)
            except Exception as exc:
                logger.error("Erreur lors de l'envoi de la notification push parent: %s", exc, exc_info=True)

        return {
            "created": len(notifications),
            "push": push_result,
        }

    # Evènements publics -----------------------------------------------------------------

    @classmethod
    def notify_presence(cls, presence, *, date_description: Optional[str] = None) -> dict:
        eleve = getattr(presence, "eleve", None)
        if not eleve:
            return {"created": 0, "push": None}

        classe_nom = cls._format_classe(eleve)
        statut_label = presence.get_statut_display() if hasattr(presence, "get_statut_display") else str(getattr(presence, "statut", ""))
        date_presence = getattr(presence, "date", None)
        if date_description:
            date_str = date_description
        else:
            try:
                date_str = timezone.localtime(getattr(presence, "date_modification", timezone.now())).strftime("%A %d %B %Y à %Hh%M")
            except Exception:
                date_str = date_presence.strftime("%d/%m/%Y") if date_presence else timezone.now().strftime("%d/%m/%Y")
        appel = getattr(presence, "numero_appel", "1")

        titre = f"Suivi de présence - {classe_nom}"
        message = (
            f"Votre enfant {eleve.nom_complet} en {classe_nom} a été marqué {statut_label.lower()} le {date_str} (appel n°{appel})."
        )

        payload = {
            "presence_id": getattr(presence, "id", None),
            "statut": getattr(presence, "statut", None),
            "date": date_str,
            "numero_appel": appel,
            "classe": classe_nom,
        }

        push_title = f"Présence de {eleve.prenom}" if hasattr(eleve, "prenom") else titre
        push_body = message
        push_data = {
            "type": "parent_presence",
            "eleve_id": str(eleve.id),
            "presence_id": str(getattr(presence, "id", "")),
            "classe": classe_nom,
        }

        return cls._dispatch(
            eleve,
            "presence",
            titre,
            message,
            payload=payload,
            source=presence,
            push_title=push_title,
            push_body=push_body,
            push_data=push_data,
        )

    @classmethod
    def notify_convocation(cls, convocation) -> dict:
        eleve = getattr(convocation, "eleve", None)
        if not eleve:
            return {"created": 0, "push": None}

        classe_nom = cls._format_classe(eleve)
        objet = getattr(convocation, "objet", "Convocation")
        motif = getattr(convocation, "motif", "")
        lieu = getattr(convocation, "lieu", "Bureau du Directeur")
        date_convocation = getattr(convocation, "date_convocation", None)
        heure_convocation = getattr(convocation, "heure_convocation", None)

        date_str = cls._format_date(date_convocation)
        heure_str = ""
        if heure_convocation:
            try:
                heure_str = heure_convocation.strftime("%Hh%M")
            except Exception:
                heure_str = str(heure_convocation)

        titre = f"Convocation pour {eleve.prenom}" if getattr(eleve, "prenom", None) else "Convocation élève"
        message_parts = [
            f"{eleve.nom_complet} est convoqué(e) le {date_str}",
        ]
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
            "type": "parent_convocation",
            "convocation_id": str(getattr(convocation, "id", "")),
            "eleve_id": str(getattr(eleve, "id", "")),
            "classe": classe_nom,
        }

        return cls._dispatch(
            eleve,
            "convocation",
            titre,
            message,
            payload=payload,
            source=convocation,
            push_title=titre,
            push_body=message,
            push_data=push_data,
        )

    @classmethod
    def notify_note(
        cls,
        eleve: Eleve,
        matiere_nom: str,
        note_obtenue,
        bareme=None,
        evaluation_nom: Optional[str] = None,
        professeur_nom: Optional[str] = None,
        date_evaluation=None,
        source=None,
    ) -> dict:
        classe_nom = cls._format_classe(eleve)
        note_str = cls._format_score(note_obtenue, bareme)
        evaluation_label = f" ({evaluation_nom})" if evaluation_nom else ""
        professeur_label = f" avec {professeur_nom}" if professeur_nom else ""
        date_label = ""
        if date_evaluation:
            date_label = f" le {cls._format_date(date_evaluation)}"

        titre = f"Nouvelle note - {matiere_nom}"
        message = (
            f"Votre enfant {eleve.nom_complet} en {classe_nom} a obtenu la note de {note_str} en {matiere_nom}{evaluation_label}{professeur_label}{date_label}."
        )

        payload = {
            "matiere": matiere_nom,
            "note": note_str,
            "evaluation": evaluation_nom,
            "professeur": professeur_nom,
            "date_evaluation": cls._format_date(date_evaluation) if date_evaluation else None,
        }

        push_data = {
            "type": "parent_note",
            "eleve_id": str(eleve.id),
            "matiere": matiere_nom,
            "note": note_str,
        }

        return cls._dispatch(
            eleve,
            "note",
            titre,
            message,
            payload=payload,
            source=source,
            push_title=titre,
            push_body=message,
            push_data=push_data,
        )

    @classmethod
    def notify_note_justifiee(
        cls,
        eleve: Eleve,
        *,
        matiere_nom: str,
        nouvelle_note,
        bareme=None,
        evaluation_nom: Optional[str] = None,
        source=None,
    ) -> dict:
        classe_nom = cls._format_classe(eleve)
        note_str = cls._format_score(nouvelle_note, bareme)
        evaluation_label = f" ({evaluation_nom})" if evaluation_nom else ""

        titre = f"Note mise à jour - {matiere_nom}"
        message = (
            f"La note de votre enfant {eleve.nom_complet} en {classe_nom} "
            f"pour {matiere_nom}{evaluation_label} a été mise à jour à {note_str} "
            "suite à une justification validée par la direction."
        )

        payload = {
            "matiere": matiere_nom,
            "note": note_str,
            "evaluation": evaluation_nom,
            "type": "justification_note",
        }

        push_data = {
            "type": "parent_note_justifiee",
            "eleve_id": str(eleve.id),
            "matiere": matiere_nom,
            "note": note_str,
        }

        return cls._dispatch(
            eleve,
            "note_justifiee",
            titre,
            message,
            payload=payload,
            source=source,
            push_title=titre,
            push_body=message,
            push_data=push_data,
        )

    @classmethod
    def notify_moyenne(
        cls,
        eleve: Eleve,
        moyenne_obtenue,
        matiere_nom: Optional[str] = None,
        periode_nom: Optional[str] = None,
        rang: Optional[int] = None,
        source=None,
    ) -> dict:
        classe_nom = cls._format_classe(eleve)
        moyenne_str = cls._format_score(moyenne_obtenue)
        matiere_label = f" en {matiere_nom}" if matiere_nom else ""
        periode_label = f" pour {periode_nom}" if periode_nom else ""
        rang_label = f" (rang : {rang})" if rang else ""

        titre = "Nouvelle moyenne disponible"
        message = (
            f"Votre enfant {eleve.nom_complet} en {classe_nom} a une moyenne de {moyenne_str}{matiere_label}{periode_label}{rang_label}."
        )

        payload = {
            "moyenne": moyenne_str,
            "matiere": matiere_nom,
            "periode": periode_nom,
            "rang": rang,
        }

        push_data = {
            "type": "parent_moyenne",
            "eleve_id": str(eleve.id),
            "moyenne": moyenne_str,
        }

        return cls._dispatch(
            eleve,
            "moyenne",
            titre,
            message,
            payload=payload,
            source=source,
            push_title=titre,
            push_body=message,
            push_data=push_data,
        )

    @classmethod
    def notify_bulletin(cls, eleve: Eleve, periode_nom: Optional[str] = None, url: Optional[str] = None, source=None, extra_message: Optional[str] = None) -> dict:
        classe_nom = cls._format_classe(eleve)
        periode_label = f" pour {periode_nom}" if periode_nom else ""
        titre = "Bulletin disponible"
        message = f"Le bulletin de votre enfant {eleve.nom_complet} en {classe_nom}{periode_label} est désormais disponible dans votre espace parent."
        if extra_message:
            message = f"{message} {extra_message}".strip()

        payload = {
            "periode": periode_nom,
            "url": url,
        }

        push_data = {
            "type": "parent_bulletin",
            "eleve_id": str(eleve.id),
            "url": url or "",
        }

        return cls._dispatch(
            eleve,
            "bulletin",
            titre,
            message,
            payload=payload,
            source=source,
            push_title=titre,
            push_body=message,
            push_data=push_data,
        )

    @classmethod
    def notify_sanction(cls, sanction) -> dict:
        eleve = getattr(sanction, "eleve", None)
        if not eleve:
            return {"created": 0, "push": None}

        classe_nom = cls._format_classe(eleve)
        type_label = sanction.get_type_sanction_display() if hasattr(sanction, "get_type_sanction_display") else getattr(sanction, "type_sanction", "")
        gravite = getattr(sanction, "gravite", None)
        gravite_label = ""
        if gravite:
            try:
                gravite_label = sanction.get_gravite_display()
            except Exception:
                gravite_label = str(gravite)
        raison = getattr(sanction, "raison", "")
        date_sanction = getattr(sanction, "date_sanction", None)
        date_label = f" le {date_sanction.strftime('%d/%m/%Y')}" if date_sanction else ""

        titre = "Sanction appliquée"
        message = (
            f"Votre enfant {eleve.nom_complet} en {classe_nom} a reçu une sanction '{type_label}'{date_label}."
        )
        if gravite_label:
            message += f" Gravité : {gravite_label}."
        if raison:
            message += f" Motif : {raison}."

        payload = {
            "sanction_id": getattr(sanction, "id", None),
            "type": type_label,
            "gravite": gravite_label,
            "raison": raison,
            "date": date_sanction.strftime("%d/%m/%Y") if date_sanction else None,
        }

        push_data = {
            "type": "parent_sanction",
            "eleve_id": str(eleve.id),
            "sanction_id": str(getattr(sanction, "id", "")),
        }

        return cls._dispatch(
            eleve,
            "sanction",
            titre,
            message,
            payload=payload,
            source=sanction,
            push_title=titre,
            push_body=message,
            push_data=push_data,
        )

    @classmethod
    def notify_custom(
        cls,
        eleve: Eleve,
        type_notification: str,
        titre: str,
        message: str,
        payload: Optional[dict] = None,
        source=None,
        push_title: Optional[str] = None,
        push_body: Optional[str] = None,
        push_data: Optional[dict] = None,
    ) -> dict:
        """Permet d'envoyer une notification personnalisée aux parents."""
        return cls._dispatch(
            eleve,
            type_notification,
            titre,
            message,
            payload=payload,
            source=source,
            push_title=push_title or titre,
            push_body=push_body or message,
            push_data=push_data,
        )


