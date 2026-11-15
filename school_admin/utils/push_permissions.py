from functools import wraps
from django.conf import settings
from django.http import JsonResponse


def push_diagnostic_admin(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not getattr(settings, 'PUSH_DIAGNOSTICS_ENABLED', False):
            return JsonResponse({'error': 'Diagnostic désactivé.'}, status=404)
        if not request.user.is_authenticated or not request.user.is_superuser:
            return JsonResponse({'error': 'Accès administrateur requis.'}, status=403)
        return view(request, *args, **kwargs)
    return guarded
