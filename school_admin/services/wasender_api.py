import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class WasenderApiResponse:
    """
    Représente la réponse brute renvoyée par l'API Wasender.
    """

    status_code: int
    body: Dict[str, Any]

    @property
    def is_success(self) -> bool:
        """
        Considère qu'une réponse est réussie si le statut HTTP est dans la plage 2xx
        et qu'un indicateur "success" est présent/positif dans le payload.
        """
        status_ok = 200 <= self.status_code < 300
        payload_ok = self.body.get("success", True)
        return status_ok and payload_ok


class WasenderApiClient:
    """
    Client minimal pour l'API Wasender.

    Il encapsule l'appel HTTP afin de centraliser la gestion des erreurs,
    de l'authentification et des paramètres de configuration.
    """

    DEFAULT_TIMEOUT = 10

    def __init__(
        self,
        *,
        api_token: Optional[str] = None,
        base_url: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.api_token = api_token or getattr(settings, "WASENDER_API_TOKEN", "")
        self.base_url = base_url or getattr(
            settings, "WASENDER_API_BASE_URL", "https://wasenderapi.com/api"
        )
        self.session_id = session_id or getattr(
            settings, "WASENDER_DEFAULT_SESSION_ID", ""
        )
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        if not self.session_id:
            raise ValueError(
                "WASENDER_DEFAULT_SESSION_ID est vide. "
                "Configurez le fichier .env ou settings.py avec l'identifiant de session Wasender."
            )

    def _build_headers(self) -> Dict[str, str]:
        if not self.api_token:
            raise ValueError(
                "Le jeton Wasender n'est pas configuré. "
                "Définissez WASENDER_API_TOKEN dans les paramètres."
            )
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def send_text_message(
        self,
        *,
        phone_number: str,
        message: str,
        session_id: Optional[str] = None,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> WasenderApiResponse:
        """
        Envoie un message texte via Wasender.

        :param phone_number: numéro du destinataire (format international recommandé).
        :param message: contenu texte à envoyer.
        :param session_id: identifiant de session WhatsApp (optionnel si configuré globalement).
        :param extra_payload: champs supplémentaires passés tels quels à l'API.
        """
        resolved_session = session_id or self.session_id
        if not resolved_session:
            raise ValueError(
                "Aucune session Wasender fournie. "
                "Définissez WASENDER_DEFAULT_SESSION_ID ou passez session_id."
            )

        payload: Dict[str, Any] = {
            "session": resolved_session,
            "phone": phone_number.lstrip("+"),
            "message": message,
        }

        if extra_payload:
            payload.update(extra_payload)

        endpoint = f"{self.base_url.rstrip('/')}/send-message"
        logger.debug(
            "Envoi d'un message Wasender",
            extra={"endpoint": endpoint, "phone": phone_number},
        )

        response = requests.post(
            endpoint,
            json=payload,
            headers=self._build_headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text, "success": True}

        api_response = WasenderApiResponse(status_code=response.status_code, body=data)
        if not api_response.is_success:
            logger.error(
                "Échec lors de l'envoi Wasender",
                extra={"payload": payload, "response": data},
            )
        return api_response

