# school_admin/controllers/compte_user_controller.py
from datetime import datetime, date

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
from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.eleve_model import Eleve


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

            # Vérification des mots de passe
            if form_data['password'] != form_data['confirm_password']:
                field_errors['confirm_password'] = "Les mots de passe ne correspondent pas."
                is_valid = False

            if len(form_data['password']) < 8:
                field_errors['password'] = "Le mot de passe doit contenir au moins 8 caractères."
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
                # Convertir les clés avec tiret en underscore pour correspondre à ton template
                # (ex: 'date-naissance' → 'date_naissance')
                template_errors = {}
                return {
                    'form_data': form_data,
                    'field_errors': template_errors,
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
        
        # Récupérer l'URL de redirection après connexion (si présente)
        next_url = request.GET.get('next', '')
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'username': request.POST.get('email', '').strip(),
                'password': request.POST.get('password', '').strip(),
            }
            
            # Récupérer l'URL next du formulaire (peut être différente de celle dans l'URL)
            next_url = request.POST.get('next', next_url)
            
            # Vérification des champs
            if not form_data['username']:
                field_errors['email'] = "L'email est obligatoire."
                
            if not form_data['password']:
                field_errors['password'] = "Le mot de passe est obligatoire."
                
            # Si pas d'erreurs de validation, on tente l'authentification
            if not field_errors:
                user = authenticate(request, username=form_data['username'], password=form_data['password'])
                if user is not None:
                    login(request, user)
                    
                    # Redirection vers l'URL next si présente, sinon vers le tableau de bord approprié
                    if next_url:
                        return None, redirect(next_url)
                    else:
                        # Vérifier le type d'utilisateur et rediriger selon sa fonction
                        if isinstance(user, Etablissement):
                            return None, redirect('directeur:dashboard_directeur')
                        elif isinstance(user, PersonnelAdministratif):
                            return None, CompteUserController._redirect_personnel_administratif(user.fonction)
                        elif isinstance(user, Eleve):
                            return None, redirect('eleve:dashboard_eleve')
                        else:
                            # Redirection basée sur la fonction de l'utilisateur (CompteUser)
                            return None, CompteUserController._redirect_based_on_function(user.fonction)
                else:
                    field_errors['__all__'] = "Email ou mot de passe incorrect."
                    
        return {
            'form_data': form_data,
            'field_errors': field_errors,
            'next_url': next_url,  # Passer l'URL next au template
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
            'surveillant_general': 'administrateur_etablissement:dashboard_administrateur_etablissement',
            'censeur': 'administrateur_etablissement:dashboard_administrateur_etablissement',
            'administrateur': 'administrateur_etablissement:dashboard_administrateur_etablissement',
            }
        return redirect(redirect_mapping.get(fonction, 'administrateur_etablissement:dashboard_administrateur_etablissement'))
