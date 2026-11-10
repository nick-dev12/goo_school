from django.utils.cache import add_never_cache_headers, patch_vary_headers
from django.conf import settings


class PrivateResponseMiddleware:
    """Les réponses liées à une session ne doivent pas être partagées ou stockées."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        authenticated = getattr(request.user, 'is_authenticated', False)
        if authenticated and request.session.get_expiry_age() > settings.SESSION_COOKIE_AGE:
            request.session.set_expiry(None)
        response = self.get_response(request)
        if authenticated or getattr(request.user, 'is_authenticated', False):
            add_never_cache_headers(response)
            patch_vary_headers(response, ['Cookie'])
        return response
