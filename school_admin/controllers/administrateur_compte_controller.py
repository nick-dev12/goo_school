from django.shortcuts import render, redirect
from django.contrib import messages
from ..model.compte_user import CompteUser
from django.contrib.auth import logout
from ..controllers.compte_user_controller import CompteUserController
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth import update_session_auth_hash
from ..model.etablissement_model import Etablissement
from ..model.eleve_model import Eleve





class AdministrateurCompteController:
    @staticmethod
    def get_user_compte_administrateur(request):
        """
        Vue pour la création d'un compte administrateur
        """
        user = request.user
        if user.is_authenticated and user.fonction == 'administrateur':
            return user
        else:
            return None
        return render(request, 'school_admin/administrateur/register.html')
    
    @staticmethod
    def get_admin_statistics():
        """
        Récupère les statistiques pour le profil administrateur
        """
        nombre_etablissements = Etablissement.objects.filter(actif=True).count()
        nombre_eleves = Eleve.objects.filter(is_active=True).count()
        return {
            'nombre_etablissements': nombre_etablissements,
            'nombre_eleves': nombre_eleves,
        }
    
    
    @staticmethod
    def logout_user_administrateur(request):
        """
        Déconnexion d'un compte administrateur
        """
        logout(request)
        return redirect('school_admin:connexion_compte_user')
    
    
    # ===== INFORMATIONS PROFIL ADMINISTRATEUR =====
    def profil_admin(request):
        """
        Profil de l'administrateur (protégé)
        """
       
        user = request.user
        user_administrateur = AdministrateurCompteController.get_user_compte_administrateur(request)
        statistics = AdministrateurCompteController.get_admin_statistics()
        
        # Vérifier si l'utilisateur est administrateur
        is_administrateur = user.is_authenticated and hasattr(user, 'fonction') and user.fonction == 'administrateur'
        
        context = {
            'user': user,
            'user_administrateur': user_administrateur,
            'is_administrateur': is_administrateur,
            **statistics
        }
        return render(request, 'school_admin/profil_admin.html', context)
   
   # ===== METTRE A JOUR LES INFORMATIONS PROFIL ADMINISTRATEUR =====
    @staticmethod
    def update_profil_admin(request):
        """
        Mettre à jour les informations profil administrateur
        Vérifie si tout est bien configuré et applique les bonnes pratiques de sécurité.
        """
        form_data = {}
        field_errors = {}
        is_valid = True  # Initialisation correcte du flag de validation

        # Vérification que l'utilisateur est bien authentifié et administrateur
        if not request.user.is_authenticated or getattr(request.user, 'fonction', None) != 'administrateur':
            messages.error(request, "Accès non autorisé. Seuls les administrateurs peuvent modifier leurs informations.")
            return redirect('school_admin:profil_admin')

        if request.method == 'POST':
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
            }
            photo = request.FILES.get('photo')

            # === Validation du nom ===
            if not form_data['nom']:
                field_errors['nom'] = "Le nom est obligatoire"
                is_valid = False

            # === Validation du prénom ===
            if not form_data['prenom']:
                field_errors['prenom'] = "Le prénom est obligatoire"
                is_valid = False

            # === Validation de l'email ===
            if not form_data['email']:
                field_errors['email'] = "L'email est obligatoire."
                is_valid = False
            else:
                try:
                    validate_email(form_data['email'])
                    # Vérifier l'unicité de l'email, sauf si c'est l'email actuel de l'utilisateur
                    if form_data['email'] != request.user.email and CompteUser.objects.filter(email=form_data['email']).exists():
                        field_errors['email'] = "Cet email est déjà utilisé."
                        is_valid = False
                except ValidationError:
                    field_errors['email'] = "Adresse email invalide."
                    is_valid = False

            # === Validation du téléphone ===
            if not form_data['telephone']:
                field_errors['telephone'] = "Le téléphone est obligatoire"
                is_valid = False

            # === Si tout est valide, on met à jour le compte ===
            if is_valid:
                try:
                    user = CompteUser.objects.get(email=request.user.email)
                    user.nom = form_data['nom']
                    user.prenom = form_data['prenom']
                    user.email = form_data['email']
                    user.telephone = form_data['telephone']

                    if photo:
                        # Optionnel : vérifier le type et la taille du fichier photo pour la sécurité
                        user.photo = photo
                    user.save()
                    messages.success(request, "Compte utilisateur mis à jour avec succès !")
                    return redirect('school_admin:profil_admin')
                except CompteUser.DoesNotExist:
                    field_errors['__all__'] = "Utilisateur introuvable."
                except Exception as e:
                    field_errors['__all__'] = "Une erreur interne est survenue. Veuillez réessayer."
                # Afficher les erreurs si une exception est levée
                user_administrateur = AdministrateurCompteController.get_user_compte_administrateur(request)
                statistics = AdministrateurCompteController.get_admin_statistics()
                is_administrateur = request.user.is_authenticated and hasattr(request.user, 'fonction') and request.user.fonction == 'administrateur'
                return render(request, 'school_admin/profil_admin.html', {
                    'field_errors': field_errors,
                    'form_data': form_data,
                    'user': request.user,
                    'user_administrateur': user_administrateur,
                    'is_administrateur': is_administrateur,
                    'active_tab': 'security',  # Activer l'onglet de sécurité pour afficher les erreurs
                    **statistics
                })
            else:
                # Afficher les erreurs de validation
                user_administrateur = AdministrateurCompteController.get_user_compte_administrateur(request)
                statistics = AdministrateurCompteController.get_admin_statistics()
                is_administrateur = request.user.is_authenticated and hasattr(request.user, 'fonction') and request.user.fonction == 'administrateur'
                return render(request, 'school_admin/profil_admin.html', {
                    'field_errors': field_errors,
                    'form_data': form_data,
                    'user': request.user,
                    'user_administrateur': user_administrateur,
                    'is_administrateur': is_administrateur,
                    'active_tab': 'security',  # Activer l'onglet de sécurité pour afficher les erreurs
                    **statistics
                })

        # GET ou autre méthode : afficher le formulaire pré-rempli
        user = request.user
        form_data = {
            'nom': user.nom,
            'prenom': user.prenom,
            'email': user.email,
            'telephone': user.telephone,
        }
        statistics = AdministrateurCompteController.get_admin_statistics()
        is_administrateur = user.is_authenticated and hasattr(user, 'fonction') and user.fonction == 'administrateur'
        return render(request, 'school_admin/profil_admin.html', {
            'form_data': form_data,
            'user': user,
            'is_administrateur': is_administrateur,
            **statistics
        })
        
    @staticmethod
    def update_password_admin(request):
        """
        Mettre à jour le mot de passe de l'utilisateur
        Accessible à tous les utilisateurs authentifiés
        """
        
        # Vérification que l'utilisateur est bien authentifié
        if not request.user.is_authenticated:
            messages.error(request, "Vous devez être connecté pour modifier votre mot de passe.")
            return redirect('school_admin:connexion_compte_user')
        
        # Initialisation des variables
        field_errors = {}
        form_data = {}
        
        if request.method == 'POST':
            # Récupération des données du formulaire
            form_data = {
                'password': request.POST.get('password', '').strip(),
                'new_password': request.POST.get('new_password', '').strip(),
                'confirm_password': request.POST.get('confirm_new_password', '').strip(),
            }
            
            # Validation des champs
            if not form_data['password']:
                field_errors['password'] = "Le mot de passe est obligatoire"
            elif not request.user.check_password(form_data['password']):
                field_errors['password'] = "Le mot de passe actuel est incorrect"
            
            if not form_data['new_password']:
                field_errors['new_password'] = "Le nouveau mot de passe est obligatoire"
            elif len(form_data['new_password']) < 8:
                field_errors['new_password'] = "Le nouveau mot de passe doit contenir au moins 8 caractères"
            
            if not form_data['confirm_password']:
                field_errors['confirm_password'] = "La confirmation du mot de passe est obligatoire"
            elif form_data['new_password'] != form_data['confirm_password']:
                field_errors['confirm_password'] = "Les mots de passe ne correspondent pas"
            
            # Si validation réussie, mettre à jour le mot de passe
            if not field_errors:
                    request.user.set_password(form_data['new_password'])
                    request.user.save()
                    # Maintenir la session active après changement de mot de passe
                    update_session_auth_hash(request, request.user)
                    messages.success(request, "Mot de passe mis à jour avec succès !")
                    return redirect('school_admin:profil_admin')
            # Si validation échouée ou exception, réafficher le formulaire avec les erreurs
            user_administrateur = AdministrateurCompteController.get_user_compte_administrateur(request)
            statistics = AdministrateurCompteController.get_admin_statistics()
            is_administrateur = request.user.is_authenticated and hasattr(request.user, 'fonction') and request.user.fonction == 'administrateur'
            return render(request, 'school_admin/profil_admin.html', {
                'field_errors': field_errors,
                'form_data': form_data,
                'user': request.user,
                'user_administrateur': user_administrateur,
                'is_administrateur': is_administrateur,
                'active_tab': 'security',
                **statistics
            })
        
        # GET ou autre méthode : afficher le formulaire vide
        user_administrateur = AdministrateurCompteController.get_user_compte_administrateur(request)
        statistics = AdministrateurCompteController.get_admin_statistics()
        is_administrateur = request.user.is_authenticated and hasattr(request.user, 'fonction') and request.user.fonction == 'administrateur'
        return render(request, 'school_admin/profil_admin.html', {
            'form_data': form_data,
            'field_errors': {},
            'user': request.user,
            'user_administrateur': user_administrateur,
            'is_administrateur': is_administrateur,
            'active_tab': 'security',
            **statistics
        })
        