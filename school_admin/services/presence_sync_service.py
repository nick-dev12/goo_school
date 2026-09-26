"""
Enregistrement d'une liste de présence (HTML en ligne + sync hors ligne).
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from django.db import transaction
from django.db.models.functions import Lower
from django.utils import timezone

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import (
    AffectationProfesseurPrimaire,
)
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.presence_model import ListePresence, Presence, SoumissionListePresence
from school_admin.services.realtime_helpers import emit_live

logger = logging.getLogger(__name__)

TYPES_ETABLISSEMENT_SECONDAIRE = {
    "lycée",
    "collège",
    "collège_lycée",
    "lycee_college",
    "mixte",
    "lycee",
    "college",
}

STATUTS_VALIDES = {"present", "absent", "retard", "absent_justifie"}
STATUTS_SAISIE_PROF = {"present", "absent"}


class PresenceSyncError(Exception):
    def __init__(self, message, code="error"):
        super().__init__(message)
        self.message = message
        self.code = code


def presences_from_post(post) -> list[dict]:
    items = []
    for key, value in post.items():
        if not key.startswith("presence_"):
            continue
        raw_id = key.replace("presence_", "", 1)
        try:
            items.append({"eleve_id": int(raw_id), "statut": value})
        except (TypeError, ValueError):
            continue
    return items


def get_eleves_classe(classe, etablissement, annee_scolaire=None):
    if annee_scolaire:
        inscriptions = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire,
            classe=classe,
            etablissement=etablissement,
        ).select_related("eleve")
        eleves_ids = [
            inscription.eleve_id
            for inscription in inscriptions
            if inscription.eleve and inscription.eleve.actif
        ]
        return Eleve.objects.filter(id__in=eleves_ids, actif=True).order_by(
            Lower("nom"), Lower("prenom")
        )
    return Eleve.objects.filter(classe=classe, actif=True).order_by(
        Lower("nom"), Lower("prenom")
    )


def _parse_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return timezone.localdate()


def enregistrer_liste_presence(professeur, payload: dict) -> dict:
    """
    Enregistre une feuille d'appel complète.

    payload:
      classe_id, matiere_id?, numero_appel?, date?, niveau?, presences[]
    """
    if not professeur or not getattr(professeur, "id", None):
        raise PresenceSyncError("Professeur invalide.", code="invalid_user")

    try:
        classe_id = int(payload.get("classe_id"))
    except (TypeError, ValueError):
        raise PresenceSyncError("classe_id est obligatoire.", code="invalid_data")

    classe = Classe.objects.select_related("etablissement").filter(id=classe_id).first()
    if not classe:
        raise PresenceSyncError("Classe introuvable.", code="invalid_data")

    etablissement = classe.etablissement or getattr(professeur, "etablissement", None)
    if not etablissement:
        raise PresenceSyncError("Établissement introuvable.", code="invalid_data")
    if classe.etablissement_id != etablissement.id:
        raise PresenceSyncError("Données incohérentes.", code="invalid_data")

    annee_scolaire = AnneeScolaire.get_session_active(etablissement)
    niveau = (payload.get("niveau") or "").strip().lower()
    est_secondaire = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
    if niveau == "primaire":
        est_secondaire = False
    elif niveau == "secondaire":
        est_secondaire = True

    jour = _parse_date(payload.get("date"))
    try:
        numero_appel = int(payload.get("numero_appel") or 1)
    except (TypeError, ValueError):
        numero_appel = 1
    if numero_appel < 1:
        numero_appel = 1

    matiere = _resolve_matiere(payload.get("matiere_id"), etablissement, est_secondaire)
    if est_secondaire and not matiere:
        raise PresenceSyncError(
            "La matière est obligatoire pour les établissements secondaires.",
            code="missing_matiere",
        )

    _assert_affectation(professeur, classe, annee_scolaire, est_secondaire)

    statuts = _statuts_par_eleve(payload.get("presences") or [])

    if est_secondaire:
        return _enregistrer_secondaire(
            professeur=professeur,
            classe=classe,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            matiere=matiere,
            jour=jour,
            numero_appel=numero_appel,
            statuts=statuts,
        )
    return _enregistrer_primaire(
        professeur=professeur,
        classe=classe,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        jour=jour,
        numero_appel=numero_appel,
        statuts=statuts,
    )


def _resolve_matiere(matiere_id, etablissement: Etablissement, est_secondaire: bool):
    if not matiere_id:
        return None
    try:
        return Matiere.objects.get(id=int(matiere_id), etablissement=etablissement)
    except (Matiere.DoesNotExist, TypeError, ValueError):
        if est_secondaire:
            raise PresenceSyncError("Matière non trouvée ou invalide.", code="invalid_data")
        return None


def _assert_affectation(professeur, classe, annee_scolaire, est_secondaire: bool):
    if est_secondaire:
        qs = AffectationProfesseur.objects.filter(
            professeur=professeur, classe=classe, actif=True
        )
        if annee_scolaire:
            qs = qs.filter(annee_scolaire=annee_scolaire)
        if not qs.exists():
            raise PresenceSyncError(
                "Vous n'êtes pas affecté à cette classe.", code="not_assigned"
            )
        return

    qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur, classe=classe, actif=True
    )
    if annee_scolaire:
        qs = qs.filter(annee_scolaire=annee_scolaire)
    if not qs.exists():
        raise PresenceSyncError(
            "Vous n'êtes pas affecté à cette classe.", code="not_assigned"
        )


def _statuts_par_eleve(presences) -> dict[int, str]:
    mapping = {}
    for item in presences:
        if not isinstance(item, dict):
            continue
        try:
            eleve_id = int(item.get("eleve_id"))
        except (TypeError, ValueError):
            continue
        statut = str(item.get("statut") or "present").strip()
        if statut not in STATUTS_SAISIE_PROF:
            raise PresenceSyncError(
                "Seuls les statuts Présent et Absent sont autorisés à l'appel.",
                code="invalid_statut",
            )
        mapping[eleve_id] = statut
    return mapping


def _enregistrer_secondaire(
    *,
    professeur,
    classe,
    etablissement,
    annee_scolaire,
    matiere,
    jour,
    numero_appel,
    statuts,
) -> dict:
    filters_soumission = {
        "classe": classe,
        "professeur": professeur,
        "matiere": matiere,
        "date": jour,
    }
    if annee_scolaire:
        filters_soumission["annee_scolaire"] = annee_scolaire
    else:
        filters_soumission["annee_scolaire__isnull"] = True

    with transaction.atomic():
        if SoumissionListePresence.objects.filter(**filters_soumission).exists():
            matiere_msg = f" pour la matière {matiere.nom}" if matiere else ""
            raise PresenceSyncError(
                f"Les présences{matiere_msg} ont déjà été soumises pour aujourd'hui.",
                code="already_submitted",
            )

        result = _upsert_presences(
            professeur=professeur,
            classe=classe,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            matiere=matiere,
            jour=jour,
            numero_appel=numero_appel,
            statuts=statuts,
        )

        SoumissionListePresence.objects.create(
            classe=classe,
            professeur=professeur,
            etablissement=etablissement,
            matiere=matiere,
            date=jour,
            date_soumission=timezone.now(),
            annee_scolaire=annee_scolaire,
        )

    _after_save(professeur, classe, result["presence_ids"], result["count"])
    matiere_msg = f" pour la matière {matiere.nom}" if matiere else ""
    return {
        "message": (
            f"Liste de présence{matiere_msg} soumise avec succès ! "
            f"{result['presents']} présent(s), {result['absents']} absent(s)."
        ),
        "classe_id": classe.id,
        "presents": result["presents"],
        "absents": result["absents"],
        "retards": result["retards"],
        "count": result["count"],
        "niveau": "secondaire",
    }


def _enregistrer_primaire(
    *,
    professeur,
    classe,
    etablissement,
    annee_scolaire,
    jour,
    numero_appel,
    statuts,
) -> dict:
    if not annee_scolaire:
        raise PresenceSyncError(
            "Aucune année scolaire active n'est définie pour votre établissement.",
            code="invalid_data",
        )
    if numero_appel > 3:
        raise PresenceSyncError(
            "Le numéro d'appel ne peut pas dépasser 3.",
            code="invalid_data",
        )

    with transaction.atomic():
        liste_qs = ListePresence.objects.filter(
            classe=classe,
            date=jour,
            numero_appel=numero_appel,
            annee_scolaire=annee_scolaire,
        )
        liste_presence = liste_qs.first()
        if liste_presence and liste_presence.validee:
            raise PresenceSyncError(
                f"L'appel n°{numero_appel} a déjà été validé pour aujourd'hui.",
                code="already_submitted",
            )
        if not liste_presence:
            valides = ListePresence.objects.filter(
                classe=classe,
                date=jour,
                annee_scolaire=annee_scolaire,
                validee=True,
            ).count()
            if valides >= 3:
                raise PresenceSyncError(
                    "La limite de 3 appels du jour est atteinte.",
                    code="already_submitted",
                )
            liste_presence = ListePresence.objects.create(
                classe=classe,
                date=jour,
                numero_appel=numero_appel,
                professeur=professeur,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire,
            )

        result = _upsert_presences(
            professeur=professeur,
            classe=classe,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            matiere=None,
            jour=jour,
            numero_appel=numero_appel,
            statuts=statuts,
        )

        liste_presence.validee = True
        liste_presence.date_validation = timezone.now()
        liste_presence.nombre_presents = result["presents"]
        liste_presence.nombre_absents = result["absents"]
        liste_presence.save()

    _after_save(professeur, classe, result["presence_ids"], result["count"])
    return {
        "message": (
            f"Appel n°{numero_appel} validé avec succès ! "
            f"{result['presents']} présent(s), {result['absents']} absent(s), "
            f"{result['retards']} retard(s)."
        ),
        "classe_id": classe.id,
        "presents": result["presents"],
        "absents": result["absents"],
        "retards": result["retards"],
        "count": result["count"],
        "numero_appel": numero_appel,
        "niveau": "primaire",
    }


def _upsert_presences(
    *,
    professeur,
    classe,
    etablissement,
    annee_scolaire,
    matiere,
    jour,
    numero_appel,
    statuts,
) -> dict:
    eleves = get_eleves_classe(classe, etablissement, annee_scolaire)
    presents = absents = retards = 0
    presence_ids = []

    for eleve in eleves:
        statut = statuts.get(eleve.id, "present")
        presence, created = Presence.objects.update_or_create(
            eleve=eleve,
            classe=classe,
            date=jour,
            numero_appel=numero_appel,
            matiere=matiere,
            defaults={
                "professeur": professeur,
                "etablissement": etablissement,
                "statut": statut,
                "annee_scolaire": annee_scolaire,
            },
        )
        if not created:
            presence.professeur = professeur
            presence.etablissement = etablissement
            presence.statut = statut
            if matiere and not presence.matiere_id:
                presence.matiere = matiere
            if annee_scolaire:
                presence.annee_scolaire = annee_scolaire
            presence.save()

        presence_ids.append(presence.id)
        if statut == "present":
            presents += 1
        elif statut in ("absent", "absent_justifie"):
            absents += 1
        elif statut == "retard":
            retards += 1

    return {
        "presents": presents,
        "absents": absents,
        "retards": retards,
        "count": len(presence_ids),
        "presence_ids": presence_ids,
    }


def _after_save(professeur, classe, presence_ids, count):
    if presence_ids:
        from school_admin.services.notification_tasks import schedule_presence_notifications

        schedule_presence_notifications(presence_ids)
    etablissement_id = getattr(professeur, "etablissement_id", None)
    if etablissement_id:
        emit_live(
            etablissement_id,
            "presence.mise_a_jour",
            {
                "event": "presence.mise_a_jour",
                "classe_id": classe.id,
                "classe_nom": classe.nom,
                "count": count,
            },
        )
