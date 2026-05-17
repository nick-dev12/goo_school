# school_admin/controllers/compte_user_controller.py
from datetime import datetime, date
import logging

from urllib.parse import urlparse

from django.shortcuts import render, redirect
from django.contrib import messages
from ..model.compte_user import CompteUser
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.contrib.auth import authenticate, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.urls import reverse
from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.eleve_model import Eleve
from ..model.professeur_model import Professeur
from ..model.parent_model import Parent
from ..utils.login_throttle import clear_on_success, get_seconds_remaining, register_auth_failure

logger = logging.getLogger(__name__)


class CompteUserController:

    @staticmethod
    def compte_user_register_view(request):
        # Initialisation des données pour pré-remplir en cas d'erreur
        form_data = {}
        field_errors = {}

        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'date_naissance': request.POST.get('date_naissance', ''),  # Template utilise date-naissance
                'type_compte': request.POST.get('type_compte', ''),  # Template utilise type-compte
                'departement': request.POST.get('departement', ''),
                'fonction': request.POST.get('fonction', ''),
                'password': request.POST.get('password', ''),
                'confirm_password': request.POST.get('confirm_password', ''),  # Template utilise confirm-password
            }

            photo = request.FILES.get('photo')
            
            username = request.POST.get('email', '').strip()
            # === Validation manuelle ===
            is_valid = True

            # Champs obligatoires
            required_fields = ['nom', 'prenom', 'email', 'telephone', 'date_naissance',
                             'type_compte', 'departement', 'fonction', 'password', 'confirm_password']
            
            # Validation des champs obligatoires
            for field in required_fields:
                if not form_data.get(field):
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False

            # Vérification de l'email (format + unicité)
            if form_data['email']:
                try:
                    validate_email(form_data['email'])
                    # Email valide, vérifier l'unicité
                    if CompteUser.objects.filter(email=form_data['email']).exists():
                        field_errors['email'] = "Cet email est déjà utilisé."
                        is_valid = False
                except ValidationError:
                    field_errors['email'] = "Adresse email invalide."
                    is_valid = False
            elif not field_errors.get('email'):  # Si l'email est vide et n'a pas déjà d'erreur
                field_errors['email'] = "L'email est obligatoire."
                is_valid = False

            # Vérification des mots de passe
            if form_data['password'] and form_data['confirm_password']:
                if form_data['password'] != form_data['confirm_password']:
                    field_errors['confirm_password'] = "Les mots de passe ne correspondent pas."
                    is_valid = False

                if len(form_data['password']) < 8:
                    field_errors['password'] = "Le mot de passe doit contenir au moins 8 caractères."
                    is_valid = False
            elif form_data['password'] and not form_data['confirm_password']:
                field_errors['confirm_password'] = "Veuillez confirmer votre mot de passe."
                is_valid = False
            elif not form_data['password'] and form_data['confirm_password']:
                field_errors['password'] = "Veuillez saisir un mot de passe."
                is_valid = False

            # Vérification de la date de naissance
            birth_date = None
            if form_data['date_naissance']:
                try:
                    birth_date = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
                    if birth_date > datetime.today().date():
                        field_errors['date_naissance'] = "La date de naissance ne peut pas être dans le futur."
                        is_valid = False
                except ValueError:
                    field_errors['date_naissance'] = "Format de date invalide."
                    is_valid = False

            # Vérification des choix (type_compte, departement, fonction)
            valid_types = dict(CompteUser.TYPE_COMPTE_CHOICES).keys()
            valid_departements = dict(CompteUser.DEPARTEMENT_CHOICES).keys()
            valid_fonctions = dict(CompteUser.FONCTION_CHOICES).keys()

            if form_data['type_compte'] not in valid_types:
                field_errors['type_compte'] = "Type de compte invalide."
                is_valid = False

            if form_data['departement'] not in valid_departements:
                field_errors['departement'] = "Département invalide."
                is_valid = False

            if form_data['fonction'] not in valid_fonctions:
                field_errors['fonction'] = "Fonction invalide."
                is_valid = False
                
                 
            # === Si tout est valide, on crée l'utilisateur ===
            if is_valid:
                try:
                    # Utiliser la date par défaut si birth_date est None
                    user_birth_date = birth_date if birth_date else date(1990, 1, 1)
                    
                    user = CompteUser(
                        nom=form_data['nom'],
                        prenom=form_data['prenom'],
                        email=form_data['email'],
                        telephone=form_data['telephone'],
                        date_naissance=user_birth_date,
                        type_compte=form_data['type_compte'],
                        departement=form_data['departement'],
                        fonction=form_data['fonction'],
                        username=username,
                    )
                    # Sauvegarde de la photo si présente
                    if photo:
                        # Optionnel : tu peux redimensionner ou valider le type de fichier
                        user.photo = photo
                    user.set_password(form_data['password'])  # ⚠️ Hash le mot de passe
                    user.save()
                        

                    messages.success(request, "Compte utilisateur créé avec succès !")
                    
                    # Vérifier si l'administrateur est déjà connecté
                    if request.user.is_authenticated and request.user.fonction == 'administrateur':
                        return None, redirect('school_admin:management_equipes')
                    else:
                        return None, redirect('school_admin:connexion_compte_user')

                except Exception as e:
                    # En production, log l'erreur, mais ne l'affiche pas à l'utilisateur
                    field_errors['__all__'] = "Une erreur interne est survenue. Veuillez réessayer."
                    is_valid = False

            # Si invalide, on reste sur la page avec les erreurs
            if not is_valid:
                return {
                    'form_data': form_data,
                    'field_errors': field_errors,
                }, None

        # GET request : afficher le formulaire vide
        return {
            'form_data': form_data,
            'field_errors': field_errors,
        }, None
    
    @staticmethod
    def compte_user_login_view(request):
        """
        Vue pour la connexion d'un utilisateur.
        Gère la validation des champs, la connexion et la redirection basée sur la fonction.
        """
        form_data = {}
        field_errors = {}
        login_lockout_seconds = 0

        # Récupérer l'URL de redirection après connexion (si présente)
        next_url = request.GET.get('next', '')
        
        if request.method == 'POST':
            # Récupération des données
            email_input = request.POST.get('email', '').strip()
            conditions_acceptees = request.POST.get('conditions_acceptees') == 'on'
            form_data = {
                'username': email_input,
                'email': email_input,  # Pour compatibilité avec le template
                'password': request.POST.get('password', '').strip(),
                'conditions_acceptees': conditions_acceptees,
            }
            
            # Récupérer l'URL next du formulaire (peut être différente de celle dans l'URL)
            next_url = request.POST.get('next', next_url)

            # Nettoyer l'URL de redirection pour éviter les assets ou URLs externes
            if next_url:
                parsed_next = urlparse(next_url)
                next_path = parsed_next.path or ''
                forbidden_extensions = (
                    '.js', '.css', '.map', '.json', '.ico', '.png', '.jpg',
                    '.jpeg', '.gif', '.svg', '.webmanifest', '.woff', '.woff2'
                )

                if not next_path.startswith('/'):
                    next_url = ''
                elif next_path.endswith(forbidden_extensions):
                    next_url = ''
                elif next_path == reverse('school_admin:connexion_compte_user'):
                    next_url = ''
                else:
                    sanitized_next = next_path
                    if parsed_next.query:
                        sanitized_next = f"{sanitized_next}?{parsed_next.query}"
                    next_url = sanitized_next
            
            # Verrouillage après échecs (IP + identifiant) — non contournable côté client
            if form_data.get('username'):
                rem = get_seconds_remaining(request, form_data['username'])
                if rem > 0:
                    return {
                        'form_data': form_data,
                        'field_errors': {
                            '__all__': 'Trop de tentatives de connexion. Veuillez patienter avant un nouvel essai.',
                        },
                        'next_url': next_url,
                        'login_lockout_seconds': rem,
                    }, None

            # Vérification des champs
            if not form_data['username']:
                field_errors['email'] = "L'email est obligatoire."
                
            if not form_data['password']:
                field_errors['password'] = "Le mot de passe est obligatoire."
            
            # Vérification de l'acceptation des conditions
            if not conditions_acceptees:
                field_errors['conditions_acceptees'] = "Vous devez accepter les conditions d'utilisation et la politique de confidentialité pour vous connecter."
                
            # Si pas d'erreurs de validation, on vérifie d'abord si le compte existe et est actif
            if not field_errors:
                logger.info(f"Tentative d'authentification - Username: {form_data['username']}, Password: {'*' * len(form_data['password'])}")
                
                # Vérifier si le compte existe et est actif avant l'authentification
                account_inactive = False
                from ..model.etablissement_model import Etablissement
                from ..model.compte_user import CompteUser
                from ..model.professeur_model import Professeur
                from ..model.personnel_administratif_model import PersonnelAdministratif
                from ..model.eleve_model import Eleve
                from ..model.parent_model import Parent
                
                # Détecter le type d'utilisateur à partir du format de l'identifiant
                username = form_data['username']
                
                # Vérifier dans chaque type de compte
                if '@' in username or (len(username) > 0 and username[0].isalpha()):
                    # Email-based (Etablissement ou CompteUser)
                    try:
                        etablissement = Etablissement.objects.get(username=username)
                        if not etablissement.actif:
                            account_inactive = True
                    except Etablissement.DoesNotExist:
                        try:
                            user = CompteUser.objects.get(username=username)
                            if not user.is_active:
                                account_inactive = True
                        except CompteUser.DoesNotExist:
                            pass
                elif len(username) >= 2 and username[:2].isalpha():
                    # Format matricule (Parent, Eleve, Professeur)
                    if username.startswith('LP') or username.startswith('BP'):
                        # Parent
                        try:
                            parent = Parent.objects.get(matricule_parental=username)
                            if not parent.is_active:
                                account_inactive = True
                        except Parent.DoesNotExist:
                            pass
                    else:
                        # Professeur ou Eleve
                        try:
                            professeur = Professeur.objects.get(username=username)
                            if not professeur.actif:
                                account_inactive = True
                        except Professeur.DoesNotExist:
                            try:
                                eleve = Eleve.objects.get(username=username)
                                if not eleve.actif:
                                    account_inactive = True
                            except Eleve.DoesNotExist:
                                pass
                else:
                    # Personnel administratif ou autre
                    try:
                        personnel = PersonnelAdministratif.objects.get(username=username)
                        if not personnel.actif:
                            account_inactive = True
                    except PersonnelAdministratif.DoesNotExist:
                        pass
                
                if account_inactive:
                    field_errors['__all__'] = "Ce compte a été désactivé. Veuillez contacter l'administration pour plus d'informations."
                    logger.warning(f"Tentative de connexion avec un compte désactivé - Username: {form_data['username']}")
                else:
                    # Tenter l'authentification seulement si le compte est actif
                    user = authenticate(request, username=form_data['username'], password=form_data['password'])
                    logger.info(f"Résultat authentification - User: {user}, Type: {type(user).__name__ if user else 'None'}")
                    if user is not None:
                        # Vérifier si l'utilisateur a accepté les conditions
                        if hasattr(user, 'conditions_acceptees') and not user.conditions_acceptees:
                            # Si les conditions ne sont pas acceptées, les mettre à jour
                            user.conditions_acceptees = True
                            user.save(update_fields=['conditions_acceptees'])
                            logger.info(f"Conditions acceptées mises à jour pour l'utilisateur: {type(user).__name__} - {getattr(user, 'email', getattr(user, 'username', 'N/A'))}")
                        
                        login(request, user)
                        clear_on_success(request, form_data['username'])

                        # Configuration de la session persistante "à vie"
                        # Définir une expiration très longue (10 ans) pour que la session ne s'expire jamais
                        # La session sera renouvelée automatiquement à chaque requête grâce à SESSION_SAVE_EVERY_REQUEST
                        from datetime import timedelta
                        request.session.set_expiry(timedelta(days=365 * 10))  # 10 ans
                        
                        # Stocker le type d'utilisateur dans la session pour get_user()
                        user_type_map = {
                            'Etablissement': 'etablissement',
                            'CompteUser': 'compte_user',
                            'PersonnelAdministratif': 'personnel',
                            'Professeur': 'professeur',
                            'Eleve': 'eleve',
                            'Parent': 'parent',
                        }
                        user_type = user_type_map.get(type(user).__name__, 'unknown')
                        request.session['_auth_user_type'] = user_type
                        logger.info(f"Login réussi pour {getattr(user, 'email', 'N/A')}, Type: {type(user).__name__}, Session type: {user_type}, Session persistante activée")
                        
                        # Sauvegarder l'année scolaire active dans la session pour les élèves
                        if isinstance(user, Eleve) and user.etablissement:
                            from ..utils.session_utils import get_session_active
                            annee_scolaire_active = get_session_active(request, user.etablissement)
                            if annee_scolaire_active:
                                request.session['annee_scolaire_active_id'] = annee_scolaire_active.id
                                logger.info(f"Année scolaire active sauvegardée pour l'élève: {annee_scolaire_active.id}")
                        
                        # Redirection vers l'URL next si présente, sinon vers le tableau de bord approprié
                        if next_url:
                            return None, redirect(next_url)
                        else:
                            # Vérifier le type d'utilisateur et rediriger selon sa fonction
                            if isinstance(user, PersonnelAdministratif):
                                # Rediriger le personnel administratif vers le dashboard du directeur (même interface mais avec restrictions)
                                return None, redirect('directeur:dashboard_directeur')
                            elif isinstance(user, Etablissement):
                                return None, redirect('directeur:dashboard_directeur')
                            elif isinstance(user, Professeur):
                                # Vérifier le type d'établissement pour rediriger vers le bon dashboard
                                if user.etablissement.type_etablissement == 'primary':
                                    return None, redirect('enseignant_primaire:dashboard')
                                else:
                                    return None, redirect('enseignant:dashboard_enseignant')
                            elif isinstance(user, Eleve):
                                return None, redirect('eleve:dashboard_eleve')
                            elif isinstance(user, Parent):
                                # Sauvegarder l'année scolaire active dans la session pour les parents
                                if user.etablissement:
                                    from ..utils.session_utils import get_session_active
                                    annee_scolaire_active = get_session_active(request, user.etablissement)
                                    if annee_scolaire_active:
                                        request.session['annee_scolaire_active_id'] = annee_scolaire_active.id
                                        logger.info(f"Année scolaire active sauvegardée pour le parent: {annee_scolaire_active.id}")
                                # Redirection vers le dashboard parent
                                return None, redirect('school_admin:dashboard_parent')
                            else:
                                # Redirection basée sur la fonction de l'utilisateur (CompteUser)
                                return None, CompteUserController._redirect_based_on_function(user.fonction)
                    else:
                        # Mauvais mot de passe (compte actif ou inexistant : même message)
                        login_lockout_seconds = register_auth_failure(
                            request, form_data['username']
                        )
                        if login_lockout_seconds > 0:
                            field_errors['__all__'] = (
                                'Trop de tentatives de connexion. '
                                'Veuillez patienter avant un nouvel essai.'
                            )
                        else:
                            field_errors['__all__'] = 'Email ou mot de passe incorrect.'
                    
        return {
            'form_data': form_data,
            'field_errors': field_errors,
            'next_url': next_url,
            'login_lockout_seconds': login_lockout_seconds,
        }, None
    
    @staticmethod
    def _redirect_based_on_function(fonction):
        """
        Redirige l'utilisateur vers le bon tableau de bord selon sa fonction.
        """
        redirect_mapping = {
            'commercial': 'school_admin:dashboard_commercial',
            'administrateur': 'school_admin:dashboard',
            'support': 'school_admin:dashboard_support',
            'developpeur': 'school_admin:dashboard_developpeur',
            'marketing': 'school_admin:dashboard_marketing',
            'comptable': 'school_admin:dashboard_comptable',
            'ressources humaines': 'school_admin:dashboard_rh',
        }
        
        # Par défaut, rediriger vers le dashboard principal
        return redirect(redirect_mapping.get(fonction, 'school_admin:dashboard'))
    @staticmethod
    def _redirect_personnel_administratif(fonction):
        """
        Redirige le personnel administratif vers le bon tableau de bord selon sa fonction.
        """
        redirect_mapping = {
            'secretaire': 'secretaire:dashboard_secretaire',
            'surveillant_general': 'directeur:dashboard_directeur',
            'censeur': 'directeur:dashboard_directeur',
            'administrateur': 'directeur:dashboard_directeur',
            }
        return redirect(redirect_mapping.get(fonction, 'directeur:dashboard_directeur'))
    
    @staticmethod
    def get_user_dashboard_url(user):
        """
        Retourne l'URL du tableau de bord approprié pour un utilisateur connecté.
        Utilisé pour rediriger les utilisateurs déjà connectés qui tentent d'accéder à la page de connexion.
        
        Args:
            user: L'utilisateur authentifié
            
        Returns:
            str: Le nom de l'URL (reverse) du tableau de bord approprié
        """
        logger.info(f"get_user_dashboard_url - Type utilisateur: {type(user).__name__}, User: {user}")
        
        # Vérifier Parent en premier car il hérite de AbstractUser et pourrait être confondu
        if isinstance(user, Parent):
            logger.info("Utilisateur détecté comme Parent")
            return 'school_admin:dashboard_parent'
        elif isinstance(user, PersonnelAdministratif):
            fonction = user.fonction
            logger.info(f"Utilisateur détecté comme PersonnelAdministratif - Fonction: {fonction}")
            redirect_mapping = {
                'secretaire': 'secretaire:dashboard_secretaire',
                'surveillant_general': 'directeur:dashboard_directeur',
                'censeur': 'directeur:dashboard_directeur',
                'administrateur': 'directeur:dashboard_directeur',
            }
            return redirect_mapping.get(fonction, 'directeur:dashboard_directeur')
        elif isinstance(user, Etablissement):
            logger.info("Utilisateur détecté comme Etablissement")
            return 'directeur:dashboard_directeur'
        elif isinstance(user, Professeur):
            logger.info("Utilisateur détecté comme Professeur")
            # Vérifier le type d'établissement pour rediriger vers le bon dashboard
            if hasattr(user, 'etablissement') and user.etablissement:
                if user.etablissement.type_etablissement == 'primary':
                    return 'enseignant_primaire:dashboard'
                else:
                    return 'enseignant:dashboard_enseignant'
            else:
                # Par défaut si pas d'établissement, rediriger vers le dashboard enseignant standard
                return 'enseignant:dashboard_enseignant'
        elif isinstance(user, Eleve):
            logger.info("Utilisateur détecté comme Eleve")
            return 'eleve:dashboard_eleve'
        elif isinstance(user, CompteUser):
            logger.info(f"Utilisateur détecté comme CompteUser - Fonction: {user.fonction}")
            # Redirection basée sur la fonction de l'utilisateur (CompteUser)
            redirect_mapping = {
                'commercial': 'school_admin:dashboard_commercial',
                'administrateur': 'school_admin:dashboard',
                'support': 'school_admin:dashboard_support',
                'developpeur': 'school_admin:dashboard_developpeur',
                'marketing': 'school_admin:dashboard_marketing',
                'comptable': 'school_admin:dashboard_comptable',
                'ressources humaines': 'school_admin:dashboard_rh',
            }
            return redirect_mapping.get(user.fonction, 'school_admin:dashboard')
        else:
            logger.warning(f"Type d'utilisateur non reconnu: {type(user).__name__}, redirection vers dashboard par défaut")
            # Par défaut, rediriger vers le dashboard principal
            return 'school_admin:dashboard'
    
    @staticmethod
    def auth_qr_login(request, token):
        """
        Authentifie un utilisateur (Parent ou Élève) via un token QR Code
        """
        from django.shortcuts import redirect
        from django.contrib import messages
        from django.contrib.auth import login
        from django.urls import reverse
        from django.http import HttpResponseRedirect
        
        try:
            logger.info(f"Tentative d'authentification QR Code avec token: {token[:10]}...")
            
            if not token or not token.strip():
                logger.warning("Token QR Code vide ou invalide")
                messages.error(request, "Token QR Code invalide.")
                return HttpResponseRedirect(reverse('school_admin:connexion_compte_user'))
            
            token = token.strip()
            
            # Chercher l'élève avec ce token (sans filtrer par actif pour détecter les comptes désactivés)
            eleve = None
            try:
                # Rechercher avec le token exact (sans filtre actif pour pouvoir détecter les comptes désactivés)
                eleve = Eleve.objects.filter(qr_auth_token=token).first()
                if eleve:
                    logger.info(f"Élève trouvé: {eleve.nom_complet} (ID: {eleve.id}, Actif: {eleve.actif})")
                else:
                    logger.debug("Aucun élève trouvé avec ce token")
            except Exception as e:
                logger.error(f"Erreur lors de la recherche d'élève: {str(e)}", exc_info=True)
            
            # Chercher le parent avec ce token (sans filtrer par actif pour détecter les comptes désactivés)
            parent = None
            if not eleve:
                try:
                    # Rechercher avec le token exact (sans filtre actif pour pouvoir détecter les comptes désactivés)
                    parent = Parent.objects.filter(qr_auth_token=token).first()
                    if parent:
                        logger.info(f"Parent trouvé: {parent.nom_complet} (ID: {parent.id}, Actif: {parent.is_active})")
                    else:
                        logger.debug("Aucun parent trouvé avec ce token")
                except Exception as e:
                    logger.error(f"Erreur lors de la recherche de parent: {str(e)}", exc_info=True)
            
            # Vérifier qu'un utilisateur a été trouvé
            if not eleve and not parent:
                logger.warning(f"Token QR Code invalide: {token[:10]}...")
                messages.error(request, "Code QR invalide. Veuillez utiliser un code QR valide.")
                return HttpResponseRedirect(reverse('school_admin:connexion_compte_user'))
            
            # Déterminer l'utilisateur à connecter
            user_to_login = eleve if eleve else parent
            
            # Vérifier que l'utilisateur est actif
            is_active = user_to_login.actif if hasattr(user_to_login, 'actif') else user_to_login.is_active
            if not is_active:
                logger.warning(f"Compte désactivé: {type(user_to_login).__name__} (ID: {user_to_login.id})")
                messages.error(request, "Désolé, ce compte a été désactivé. Veuillez contacter l'administration.")
                return HttpResponseRedirect(reverse('school_admin:connexion_compte_user'))
            
            # Vérifier que l'utilisateur a un établissement
            if hasattr(user_to_login, 'etablissement') and not user_to_login.etablissement:
                logger.warning(f"Aucun établissement associé: {type(user_to_login).__name__} (ID: {user_to_login.id})")
                messages.error(request, "Aucun établissement associé à votre compte.")
                return HttpResponseRedirect(reverse('school_admin:connexion_compte_user'))
            
            # Connecter l'utilisateur
            logger.info(f"Tentative de connexion: {type(user_to_login).__name__} (ID: {user_to_login.id})")
            
            # Spécifier le backend d'authentification
            from school_admin.authentication_backends import MultiUserBackend
            backend_path = 'school_admin.authentication_backends.MultiUserBackend'
            
            # Marquer le type d'utilisateur pour le backend
            if isinstance(user_to_login, Eleve):
                user_to_login._auth_user_type = 'eleve'
            elif isinstance(user_to_login, Parent):
                user_to_login._auth_user_type = 'parent'
            
            # Sauvegarder le type dans la session pour le middleware
            request.session['_auth_user_type'] = user_to_login._auth_user_type
            
            login(request, user_to_login, backend=backend_path)
            logger.info(f"Utilisateur connecté via QR Code: {type(user_to_login).__name__} - {user_to_login}")
            
            # Accepter automatiquement les conditions d'utilisation lors de la connexion par QR
            if hasattr(user_to_login, 'conditions_acceptees'):
                if not user_to_login.conditions_acceptees:
                    user_to_login.conditions_acceptees = True
                    user_to_login.save(update_fields=['conditions_acceptees'])
                    logger.info(f"Conditions d'utilisation acceptées pour: {type(user_to_login).__name__} (ID: {user_to_login.id})")
            
            # Déterminer la redirection selon le type d'utilisateur
            if isinstance(user_to_login, Eleve):
                messages.success(request, f"Bienvenue {user_to_login.nom_complet} !")
                redirect_url = reverse('eleve:dashboard_eleve')
                logger.info(f"Redirection vers dashboard élève: {redirect_url}")
                return HttpResponseRedirect(redirect_url)
            elif isinstance(user_to_login, Parent):
                messages.success(request, f"Bienvenue {user_to_login.nom_complet} !")
                redirect_url = reverse('school_admin:dashboard_parent')
                logger.info(f"Redirection vers dashboard parent: {redirect_url}")
                return HttpResponseRedirect(redirect_url)
            else:
                logger.warning(f"Type d'utilisateur non reconnu: {type(user_to_login).__name__}")
                messages.success(request, "Connexion réussie !")
                redirect_url = reverse('school_admin:connexion_compte_user')
                return HttpResponseRedirect(redirect_url)
                
        except Exception as e:
            logger.error(f"Erreur lors de la connexion par QR Code: {str(e)}", exc_info=True)
            messages.error(request, f"Une erreur est survenue lors de la connexion: {str(e)}. Veuillez réessayer.")
            try:
                redirect_url = reverse('school_admin:connexion_compte_user')
                return HttpResponseRedirect(redirect_url)
            except Exception as reverse_error:
                logger.error(f"Erreur lors de la redirection: {str(reverse_error)}", exc_info=True)
                return redirect('/connexion/')