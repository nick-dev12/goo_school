from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from school_admin.authentication_backends import _user_type_context

class UserTypeMiddleware:
    """
    Middleware qui stocke le type d'utilisateur dans le thread-local
    pour que get_user() puisse l'utiliser.
    Ce middleware doit s'exécuter AVANT AuthenticationMiddleware.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Récupérer le type d'utilisateur depuis la session si disponible
        user_type = request.session.get('_auth_user_type', None)
        if user_type:
            _user_type_context.user_type = user_type
        else:
            # Nettoyer le thread-local si pas de type
            if hasattr(_user_type_context, 'user_type'):
                delattr(_user_type_context, 'user_type')
        
        response = self.get_response(request)
        
        # Nettoyer le thread-local après la requête
        if hasattr(_user_type_context, 'user_type'):
            delattr(_user_type_context, 'user_type')
        
        return response

class AuthenticationMiddleware:
    """
    Middleware pour vérifier l'authentification des utilisateurs et les rediriger
    vers la page de connexion si nécessaire, ou vers leur tableau de bord approprié.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        # Liste des URLs qui ne nécessitent pas d'authentification
        public_urls = [
            reverse('school_admin:connexion_compte_user'),
            reverse('school_admin:inscription_compte_user'),
            reverse('school_admin:firebase_messaging_sw'),
            reverse('school_admin:prof_connexion_otp'),
            reverse('school_admin:password_reset_request'),
            reverse('school_admin:politiques_utilisation'),
            reverse('school_admin:verifier_bulletin_qr'),
            # Ajouter d'autres URLs publiques si nécessaire
        ]

        technical_urls = {
            '/service-worker.js',
            '/firebase-messaging-sw.js',
            '/manifest.json',
            '/favicon.ico',
        }
        
        print(f"\n[MIDDLEWARE] Path: {request.path}, User: {request.user}, Type: {type(request.user).__name__}, Authenticated: {request.user.is_authenticated}")
        logger.info(f"[MIDDLEWARE] Path: {request.path}, User: {request.user}, Authenticated: {request.user.is_authenticated}")
        
        # Si l'URL actuelle est une URL publique, on laisse passer
        if (
            request.path in public_urls
            or request.path in technical_urls
            or request.path.startswith('/admin/')
            or request.path.startswith('/static/')
            or request.path.startswith('/connexion/professeurs/otp/verification/')
            or request.path.startswith('/password-reset/')  # Pages de réinitialisation de mot de passe
            or request.path.startswith('/politiques-utilisation/')  # Page des politiques d'utilisation
            or request.path.startswith('/bulletins/verifier/')  # Page de vérification de bulletin (accessible via QR code)
        ):
            return self.get_response(request)
        
        # Si l'utilisateur n'est pas connecté et qu'il n'est pas sur une URL publique
        is_public_path = (
            request.path in public_urls
            or request.path in technical_urls
            or request.path.startswith('/password-reset/')
            or request.path.startswith('/connexion/professeurs/otp/verification/')
            or request.path.startswith('/politiques-utilisation/')  # Page des politiques d'utilisation
            or request.path.startswith('/bulletins/verifier/')  # Page de vérification de bulletin (accessible via QR code)
        )
        
        if not request.user.is_authenticated and not is_public_path:
            print(f"[MIDDLEWARE] User not authenticated, redirecting to login from {request.path}")
            logger.warning(f"[MIDDLEWARE] User not authenticated, redirecting to login from {request.path}")
            # Sauvegarder l'URL actuelle pour rediriger l'utilisateur après connexion
            next_url = request.path
            login_url = f"{reverse('school_admin:connexion_compte_user')}?next={next_url}"
            return redirect(login_url)
        
        # Si l'utilisateur est connecté et qu'il est sur la page d'accueil
        if request.user.is_authenticated and request.path == '/school_admin/':
            # Rediriger vers le tableau de bord approprié selon le type d'utilisateur
            from .model.compte_user import CompteUser
            from .model.etablissement_model import Etablissement
            from .model.personnel_administratif_model import PersonnelAdministratif
            from .model.eleve_model import Eleve
            from .model.professeur_model import Professeur
            
            # Si c'est un CompteUser, vérifier sa fonction
            if isinstance(request.user, CompteUser) and hasattr(request.user, 'fonction'):
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
            
            # Si c'est un Etablissement, vérifier qu'une année scolaire active existe
            elif isinstance(request.user, Etablissement):
                from .model.annee_scolaire_model import AnneeScolaire
                from .utils.session_utils import get_session_active
                
                etablissement = request.user
                annee_active = get_session_active(request, etablissement)
                
                # Si aucune année active n'existe, rediriger vers la création obligatoire
                if not annee_active:
                    return redirect('directeur:creer_annee_scolaire_obligatoire')
                
                # Définir la session active dans la session utilisateur seulement si pas déjà définie
                # (pour ne pas écraser une session consultée explicitement sélectionnée)
                if not request.session.get('annee_scolaire_consultee_id'):
                    request.session['annee_scolaire_consultee_id'] = annee_active.id
                    request.session['school_year_id'] = annee_active.id
                
                return redirect('directeur:dashboard_directeur')
            
            # Si c'est un Professeur, récupérer l'année scolaire active et rediriger vers le dashboard enseignant
            elif isinstance(request.user, Professeur):
                professeur = request.user
                if hasattr(professeur, 'etablissement') and professeur.etablissement:
                    from .model.annee_scolaire_model import AnneeScolaire
                    from .utils.session_utils import get_session_active
                    
                    etablissement = professeur.etablissement
                    annee_active = get_session_active(request, etablissement)
                    
                    # Si une année active existe, définir automatiquement la session
                    if annee_active:
                        request.session['annee_scolaire_consultee_id'] = annee_active.id
                        request.session['school_year_id'] = annee_active.id
                
                return redirect('enseignant:dashboard_enseignant')
            
            # Si c'est un PersonnelAdministratif, rediriger vers le dashboard personnel
            elif isinstance(request.user, PersonnelAdministratif):
                return redirect('personnel_administratif:dashboard_personnel_administratif')
            
            # Si c'est un Eleve, rediriger vers le dashboard élève
            elif isinstance(request.user, Eleve):
                return redirect('eleve:dashboard_eleve')
        
        response = self.get_response(request)
        return response


class SessionActiveMiddleware:
    """
    Middleware pour gérer la redirection automatique vers une nouvelle session ouverte
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # URLs à exclure de la vérification de session
        creation_obligatoire_path = reverse('directeur:creer_annee_scolaire_obligatoire')
        excluded_paths = [
            '/admin/',
            '/static/',
            '/media/',
            '/connexion/',
            '/inscription/',
            '/password-reset/',
            '/session/info/',
            '/session/changer/',
            creation_obligatoire_path,
        ]
        
        # Vérifier si le chemin est exclu
        is_excluded = any(request.path.startswith(path) for path in excluded_paths)
        if request.path.endswith('/activer/'):
            is_excluded = True
        
        # Ne vérifier que pour les utilisateurs authentifiés et non exclus
        if request.user.is_authenticated and not is_excluded:
            try:
                from .utils.session_utils import get_session_active, set_session_consultee
                from .model.etablissement_model import Etablissement
                
                # Récupérer l'établissement selon le type d'utilisateur
                etablissement = None
                if isinstance(request.user, Etablissement):
                    etablissement = request.user
                elif hasattr(request.user, 'etablissement'):
                    etablissement = request.user.etablissement
                
                if etablissement:
                    # Vérifier si une année scolaire active existe
                    annee_active = get_session_active(request, etablissement)
                    
                    # Si c'est un directeur et qu'aucune année active n'existe
                    # ET qu'il n'est pas déjà sur la page de création obligatoire
                    if isinstance(request.user, Etablissement) and not annee_active:
                        if request.path != creation_obligatoire_path:
                            from django.shortcuts import redirect
                            return redirect('directeur:creer_annee_scolaire_obligatoire')
                    
                    # Si une année active existe, définir automatiquement la session
                    # IMPORTANT: Pour les directeurs, ne PAS écraser la session consultée
                    # s'ils ont explicitement sélectionné une session différente
                    if annee_active:
                        # Pour les directeurs, respecter leur choix de session consultée
                        if isinstance(request.user, Etablissement):
                            # Si le directeur n'a pas encore de session consultée, utiliser la session active
                            if not request.session.get('annee_scolaire_consultee_id'):
                                request.session['annee_scolaire_consultee_id'] = annee_active.id
                                request.session['school_year_id'] = annee_active.id
                                set_session_consultee(request, annee_active)
                            # Sinon, laisser la session consultée telle quelle (ne pas l'écraser)
                        else:
                            # Pour les autres utilisateurs (professeurs, etc.), utiliser toujours la session active
                            if not request.session.get('annee_scolaire_consultee_id') or \
                               request.session.get('annee_scolaire_consultee_id') != annee_active.id:
                                request.session['annee_scolaire_consultee_id'] = annee_active.id
                                request.session['school_year_id'] = annee_active.id
                                set_session_consultee(request, annee_active)
            
            except Exception as e:
                # En cas d'erreur, continuer normalement
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Erreur dans SessionActiveMiddleware: {e}", exc_info=True)
        
        response = self.get_response(request)
        return response