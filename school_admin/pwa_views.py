"""
Vues pour la Progressive Web App (PWA)
"""
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.cache import cache_control
from django.conf import settings
import json
import os


@require_GET
@cache_control(max_age=3600, public=True)
def manifest_view(request):
    """
    Vue pour servir le manifest.json de la PWA
    """
    manifest_path = os.path.join(
        settings.BASE_DIR,
        'school_admin',
        'static',
        'school_admin',
        'manifest.json'
    )
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
        
        # Ajuster les URLs selon le domaine
        if request.is_secure():
            protocol = 'https'
        else:
            protocol = 'http'
        
        host = request.get_host()
        base_url = f"{protocol}://{host}"
        
        # Mettre à jour les URLs des icônes
        if 'icons' in manifest_data:
            for icon in manifest_data['icons']:
                if icon['src'].startswith('/'):
                    icon['src'] = f"{base_url}{icon['src']}"
        
        # Mettre à jour start_url
        if 'start_url' in manifest_data:
            manifest_data['start_url'] = f"{base_url}{manifest_data['start_url']}"
        
        # Mettre à jour scope
        if 'scope' in manifest_data:
            manifest_data['scope'] = f"{base_url}{manifest_data['scope']}"
        
        response = JsonResponse(manifest_data, json_dumps_params={'ensure_ascii': False})
        response['Content-Type'] = 'application/manifest+json'
        return response
        
    except FileNotFoundError:
        return JsonResponse({'error': 'Manifest not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid manifest format'}, status=500)


@require_GET
@cache_control(max_age=3600, public=True)
def service_worker_view(request):
    """
    Vue pour servir le service-worker.js
    """
    sw_path = os.path.join(
        settings.BASE_DIR,
        'school_admin',
        'static',
        'school_admin',
        'service-worker.js'
    )
    
    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            service_worker_content = f.read()
        
        response = HttpResponse(service_worker_content, content_type='application/javascript')
        # Headers importants pour les Service Workers
        response['Service-Worker-Allowed'] = '/'
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
        
    except FileNotFoundError:
        return HttpResponse('// Service Worker not found', status=404, content_type='application/javascript')


@require_GET
def offline_view(request):
    """
    Vue pour afficher une page hors ligne
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hors ligne - Aria</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .offline-container {
                background: white;
                border-radius: 16px;
                padding: 40px;
                max-width: 500px;
                width: 100%;
                text-align: center;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            }
            .offline-icon {
                width: 120px;
                height: 120px;
                margin: 0 auto 30px;
                background: linear-gradient(135deg, #3b82f6, #1d4ed8);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 60px;
                color: white;
            }
            h1 {
                color: #1f2937;
                font-size: 28px;
                margin-bottom: 16px;
            }
            p {
                color: #6b7280;
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 24px;
            }
            .retry-btn {
                background: linear-gradient(135deg, #3b82f6, #1d4ed8);
                color: white;
                border: none;
                padding: 14px 32px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .retry-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(59, 130, 246, 0.4);
            }
            .retry-btn:active {
                transform: translateY(0);
            }
        </style>
    </head>
    <body>
        <div class="offline-container">
            <div class="offline-icon">📡</div>
            <h1>Vous êtes hors ligne</h1>
            <p>Il semble que vous n'ayez pas de connexion Internet. Veuillez vérifier votre connexion et réessayer.</p>
            <button class="retry-btn" onclick="window.location.reload()">Réessayer</button>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html_content, content_type='text/html')

