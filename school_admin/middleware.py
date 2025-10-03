from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings

class AuthenticationMiddleware:
    """
    Middleware pour vérifier l'authentification des utilisateurs et les rediriger
    vers la page de connexion si nécessaire, ou vers leur tableau de bord approprié.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Liste des URLs qui ne nécessitent pas d'authentification
        public_urls = [
            reverse('school_admin:connexion_compte_user'),
            reverse('school_admin:inscription_compte_user'),
            # Ajouter d'autres URLs publiques si nécessaire
        ]
        
        # Si l'URL actuelle est une URL publique, on laisse passer
        if request.path in public_urls or request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return self.get_response(request)
        
        # Si l'utilisateur n'est pas connecté et qu'il n'est pas sur une URL publique
        if not request.user.is_authenticated and request.path not in public_urls:
            # Sauvegarder l'URL actuelle pour rediriger l'utilisateur après connexion
            next_url = request.path
            login_url = f"{reverse('school_admin:connexion_compte_user')}?next={next_url}"
            return redirect(login_url)
        
        # Si l'utilisateur est connecté et qu'il est sur la page d'accueil
        if request.user.is_authenticated and request.path == '/school_admin/':
            # Rediriger vers le tableau de bord approprié selon la fonction
            if hasattr(request.user, 'fonction'):
                fonction = request.user.fonction
                
                if fonction == 'commercial':
                    return redirect('school_admin:dashboard_commercial')
                elif fonction == 'support':
                    return redirect('school_admin:dashboard_support')
                elif fonction == 'developpeur':
                    return redirect('school_admin:dashboard_developpeur')
                elif fonction == 'marketing':
                    return redirect('school_admin:dashboard_marketing')
                elif fonction == 'comptable':
                    return redirect('school_admin:dashboard_comptable')
                elif fonction == 'ressources humaines':
                    return redirect('school_admin:dashboard_rh')
                elif fonction == 'administrateur':
                    return redirect('school_admin:dashboard')
        
        response = self.get_response(request)
        return response
