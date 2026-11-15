from django.middleware.gzip import GZipMiddleware

# Réponses textuelles : pages, JSON des API, scripts générés (push-config.js, service worker), manifeste.
TYPES_COMPRESSIBLES = ('text/', 'application/json', 'application/javascript', 'application/manifest+json',
                       'application/xml', 'image/svg+xml')


class CompressionMiddleware(GZipMiddleware):
    """Compresse les réponses textuelles (5 à 8 fois plus légères sur une connexion lente).

    Les flux (événements serveur, audio, fichiers) passent tels quels : ils doivent partir au fil de l'eau.
    """

    def process_response(self, request, response):
        content_type = response.get('Content-Type', '')
        if (response.streaming or not content_type.startswith(TYPES_COMPRESSIBLES)
                or content_type.startswith('text/event-stream')):
            return response
        return super().process_response(request, response)
