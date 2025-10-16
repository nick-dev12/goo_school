from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def commercial_required(view_func):
    """
    Décorateur pour vérifier si l'utilisateur est connecté et est un commercial.
    Redirige vers la page de connexion si l'utilisateur n'est pas connecté.
    Redirige vers le tableau de bord approprié si l'utilisateur n'est pas un commercial.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Vérifier si l'utilisateur est connecté
        if not request.user.is_authenticated:
            next_url = request.path
            return redirect(f"school_admin:connexion_compte_user?next={next_url}")
        
        # Vérifier si l'utilisateur est un commercial
        from .model.compte_user import CompteUser
        if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction') or request.user.fonction != 'commercial':
            messages.error(request, "Vous n'avez pas accès à cette page. Vous avez été redirigé vers votre tableau de bord.")
            return redirect('school_admin:dashboard')
        
        # Si tout est OK, exécuter la vue
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view

def admin_required(view_func):
    """
    Décorateur pour vérifier si l'utilisateur est connecté et est un administrateur.
    Redirige vers la page de connexion si l'utilisateur n'est pas connecté.
    Redirige vers le tableau de bord approprié si l'utilisateur n'est pas un administrateur.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Vérifier si l'utilisateur est connecté
        if not request.user.is_authenticated:
            next_url = request.path
            return redirect(f"school_admin:connexion_compte_user?next={next_url}")
        
        # Vérifier si l'utilisateur est un administrateur
        from .model.compte_user import CompteUser
        if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction') or request.user.fonction != 'administrateur':
            messages.error(request, "Vous n'avez pas accès à cette page. Vous avez été redirigé vers votre tableau de bord.")
            return redirect('school_admin:dashboard')
        
        # Si tout est OK, exécuter la vue
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view

def login_required_with_redirect(view_func):
    """
    Décorateur pour vérifier si l'utilisateur est connecté.
    Redirige vers la page de connexion si l'utilisateur n'est pas connecté.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Vérifier si l'utilisateur est connecté
        if not request.user.is_authenticated:
            next_url = request.path
            return redirect(f"school_admin:connexion_compte_user?next={next_url}")
        
        # Si tout est OK, exécuter la vue
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view
