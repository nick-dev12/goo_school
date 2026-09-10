"""API de synchronisation hors ligne (file SQLite Flutter -> Django)."""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import (
    AffectationProfesseurPrimaire,
)
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.presence_model import Presence
from school_admin.model.professeur_model import Professeur
from school_admin.model.sync_action_model import SyncAction
from school_admin.services.presence_sync_service import (
    PresenceSyncError,
    enregistrer_liste_presence,
    get_eleves_classe,
)

logger = logging.getLogger(__name__)


def _json_error(message, status=400, **extra):
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _require_professeur(request):
    if not request.user.is_authenticated:
        return None, _json_error("Non authentifié", status=401)
    if not isinstance(request.user, Professeur):
        return None, _json_error("Accès réservé aux enseignants", status=403)
    return request.user, None


@require_http_methods(["POST"])
def sync_push(request):
    professeur, error = _require_professeur(request)
    if error:
        return error

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json_error("JSON invalide")

    items = body.get("items")
    if not isinstance(items, list):
        return _json_error("items doit être une liste")

    results = []
    for raw in items:
        if not isinstance(raw, dict):
            results.append({"id": None, "ok": False, "error": "item invalide"})
            continue
        results.append(_process_item(professeur, raw))

    return JsonResponse({"ok": True, "results": results})


def _process_item(professeur, raw: dict) -> dict:
    item_id = str(raw.get("id") or "").strip()
    resource = str(raw.get("resource") or "").strip()
    action = str(raw.get("action") or "CREATE").upper()
    payload = raw.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}

    if not item_id:
        return {"id": item_id, "ok": False, "error": "id manquant"}

    existing = SyncAction.objects.filter(client_uuid=item_id).first()
    if existing:
        stored = existing.resultat if isinstance(existing.resultat, dict) else {}
        return {"id": item_id, **stored, "replayed": True}

    if resource != "presence_liste":
        result = {"ok": False, "error": f"resource inconnue: {resource}"}
        _store_action(item_id, resource, action, professeur, result)
        return {"id": item_id, **result}

    try:
        saved = enregistrer_liste_presence(professeur, payload)
        result = {
            "ok": True,
            "status": "synced",
            "message": saved.get("message"),
            "classe_id": saved.get("classe_id"),
        }
    except PresenceSyncError as exc:
        result = {"ok": False, "error": exc.message, "code": exc.code}
    except Exception as exc:
        logger.exception("Erreur sync présence %s", item_id)
        result = {"ok": False, "error": str(exc)}

    _store_action(item_id, resource, action, professeur, result)
    return {"id": item_id, **result}


def _store_action(client_uuid, resource, action, professeur, result):
    SyncAction.objects.update_or_create(
        client_uuid=client_uuid,
        defaults={
            "resource": resource or "unknown",
            "action": action or "CREATE",
            "utilisateur_id": professeur.id,
            "utilisateur_type": "professeur",
            "resultat": result,
        },
    )


@require_http_methods(["GET"])
def sync_pull(request):
    professeur, error = _require_professeur(request)
    if error:
        return error

    requested = {
        part.strip()
        for part in (request.GET.get("resources") or "classes,eleves,presences").split(",")
        if part.strip()
    }
    etablissement = professeur.etablissement
    annee = AnneeScolaire.get_session_active(etablissement) if etablissement else None
    classes = _classes_affectees(professeur, annee)

    data = {}
    if "classes" in requested:
        data["classes"] = [
            {
                "id": classe.id,
                "server_id": classe.id,
                "nom": classe.nom,
                "etablissement_id": classe.etablissement_id,
            }
            for classe in classes
        ]

    if "eleves" in requested:
        eleves = []
        for classe in classes:
            for eleve in get_eleves_classe(classe, etablissement, annee):
                eleves.append({
                    "id": eleve.id,
                    "server_id": eleve.id,
                    "nom": eleve.nom,
                    "prenom": getattr(eleve, "prenom", ""),
                    "nom_complet": getattr(eleve, "nom_complet", eleve.nom),
                    "matricule": getattr(eleve, "matricule", ""),
                    "classe_id": classe.id,
                })
        data["eleves"] = eleves

    if "presences" in requested:
        since = timezone.localdate() - timedelta(days=7)
        classe_ids = [classe.id for classe in classes]
        qs = Presence.objects.filter(
            classe_id__in=classe_ids,
            date__gte=since,
        )
        if annee:
            qs = qs.filter(annee_scolaire=annee)
        data["presences"] = [
            {
                "id": presence.id,
                "server_id": presence.id,
                "eleve_id": presence.eleve_id,
                "classe_id": presence.classe_id,
                "matiere_id": presence.matiere_id,
                "date": presence.date.isoformat(),
                "numero_appel": presence.numero_appel,
                "statut": presence.statut,
                "updated_at": presence.date_modification.isoformat()
                if presence.date_modification
                else None,
            }
            for presence in qs
        ]

    return JsonResponse({"ok": True, "data": data})


def _classes_affectees(professeur, annee):
    secondaire = AffectationProfesseur.objects.filter(
        professeur=professeur, actif=True
    ).select_related("classe")
    primaire = AffectationProfesseurPrimaire.objects.filter(
        professeur=professeur, actif=True
    ).select_related("classe")
    if annee:
        secondaire = secondaire.filter(annee_scolaire=annee)
        primaire = primaire.filter(annee_scolaire=annee)

    classes = {}
    for aff in list(secondaire) + list(primaire):
        if aff.classe_id and aff.classe_id not in classes:
            classes[aff.classe_id] = aff.classe
    return list(classes.values())
