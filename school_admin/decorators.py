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


def parent_required(view_func):
    """
    Décorateur pour vérifier si l'utilisateur est connecté et est un parent.
    Redirige vers la page de connexion si l'utilisateur n'est pas connecté.
    Redirige vers le tableau de bord approprié si l'utilisateur n'est pas un parent.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Vérifier si l'utilisateur est connecté
        if not request.user.is_authenticated:
            next_url = request.path
            return redirect(f"school_admin:connexion_compte_user?next={next_url}")
        
        # Vérifier si l'utilisateur est un parent
        from .model.parent_model import Parent
        if not isinstance(request.user, Parent):
            messages.error(request, "Vous n'avez pas accès à cette page. Vous avez été redirigé vers votre tableau de bord.")
            # Rediriger vers le tableau de bord approprié selon le type d'utilisateur
            if hasattr(request.user, 'fonction'):
                if request.user.fonction == 'directeur':
                    return redirect('school_admin:dashboard_directeur')
                elif request.user.fonction == 'commercial':
                    return redirect('school_admin:dashboard_commercial')
            return redirect('school_admin:connexion')
        
        # Si tout est OK, exécuter la vue
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def comptable_required(view_func):
    """
    Décorateur pour vérifier si l'utilisateur est connecté et est un comptable.
    Redirige vers la page de connexion si l'utilisateur n'est pas connecté.
    Redirige vers le tableau de bord approprié si l'utilisateur n'est pas un comptable.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Vérifier si l'utilisateur est connecté
        if not request.user.is_authenticated:
            next_url = request.path
            return redirect(f"school_admin:connexion_compte_user?next={next_url}")
        
        # Vérifier si l'utilisateur est un comptable
        from .model.compte_user import CompteUser
        if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction') or request.user.fonction != 'comptable':
            messages.error(request, "Accès refusé. Seuls les comptables peuvent accéder à cette page.")
            # Rediriger vers le tableau de bord approprié
            if isinstance(request.user, CompteUser) and hasattr(request.user, 'fonction'):
                if request.user.fonction == 'administrateur':
                    return redirect('school_admin:dashboard')
                else:
                    return redirect('school_admin:dashboard')
            return redirect('school_admin:connexion_compte_user')
        
        # Si tout est OK, exécuter la vue
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def comptable_or_admin_required(view_func):
    """
    Décorateur pour vérifier si l'utilisateur est connecté et est soit un comptable soit un administrateur.
    Redirige vers la page de connexion si l'utilisateur n'est pas connecté.
    Redirige vers le tableau de bord approprié si l'utilisateur n'est ni comptable ni administrateur.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Vérifier si l'utilisateur est connecté
        if not request.user.is_authenticated:
            next_url = request.path
            return redirect(f"school_admin:connexion_compte_user?next={next_url}")
        
        # Vérifier si l'utilisateur est un comptable ou un administrateur
        from .model.compte_user import CompteUser
        if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction'):
            messages.error(request, "Accès refusé. Seuls les comptables et administrateurs peuvent accéder à cette page.")
            return redirect('school_admin:connexion_compte_user')
        
        fonction = request.user.fonction
        if fonction not in ['comptable', 'administrateur']:
            messages.error(request, "Accès refusé. Seuls les comptables et administrateurs peuvent accéder à cette page.")
            # Rediriger vers le tableau de bord approprié
            return redirect('school_admin:dashboard')
        
        # Si tout est OK, exécuter la vue
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view
