import logging
import secrets
from datetime import timedelta
from typing import Optional

from django.contrib import messages
from django.contrib.auth import login
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .controllers import (
    AdministrateurCompteController,
    CommercialCompteController,
    CompteUserController,
    EtablissementController,
)
from .forms.professeur_otp_forms import (
    ProfesseurOtpRequestForm,
    ProfesseurOtpVerifyForm,
)
from .model.professeur_model import Professeur
from .model.professeur_otp_model import ProfesseurOtpCode
from .services.wasender_api import WasenderApiClient

# Configurer le logger
logger = logging.getLogger(__name__)

# Create your views here.
def inscription_compte_user(request):
    """
    Gère l'inscription d'un nouvel utilisateur (public)
    """
    if request.method == 'POST':
        # Utiliser le contrôleur pour traiter l'inscription
        result = CompteUserController.compte_user_register_view(request)
        if isinstance(result, tuple) and len(result) == 2:
            context, response = result
            if response:
                return response
        else:
            # Si c'est juste le contexte
            context = result
    else:
        # Initialiser le contexte pour le formulaire vide
        context = {
            'field_errors': {},
            'form_data': {}
        }
    
    return render(request, 'school_admin/inscription.html', context)


def conditions_utilisation(request):
    """Affiche les conditions générales d'utilisation."""
    return render(request, 'school_admin/conditions_utilisation.html')


def politique_confidentialite(request):
    """Affiche la politique de confidentialité."""
    return render(request, 'school_admin/politique_confidentialite.html')


def politiques_utilisation(request):
    """Redirection permanente vers les conditions d'utilisation (ancienne URL)."""
    return redirect('school_admin:conditions_utilisation', permanent=True)


def suppression_compte(request):
    """
    Affiche la page de demande de suppression de compte et de données
    Page publique accessible sans authentification
    """
    return render(request, 'school_admin/suppression_compte.html')


def connexion_compte_user(request):
    """
    Gère la connexion d'un utilisateur (public)
    Si l'utilisateur est déjà connecté, il est redirigé vers son tableau de bord.
    """
    # Importer les modèles pour la vérification
    from .model.parent_model import Parent
    from .model.compte_user import CompteUser
    from .model.etablissement_model import Etablissement
    from .model.personnel_administratif_model import PersonnelAdministratif
    from .model.eleve_model import Eleve
    from .model.professeur_model import Professeur
    from django.contrib.auth.models import AnonymousUser
    
    # Vérifier si l'utilisateur est déjà authentifié
    # Vérifier aussi directement le type pour éviter les problèmes avec is_authenticated
    is_authenticated_user = (
        request.user.is_authenticated or
        isinstance(request.user, (Parent, CompteUser, Etablissement, PersonnelAdministratif, Eleve, Professeur))
    ) and not isinstance(request.user, AnonymousUser)
    
    if is_authenticated_user:
        logger.info(f"Utilisateur déjà connecté - Type: {type(request.user).__name__}, User: {request.user}, is_authenticated: {request.user.is_authenticated}")
        # Obtenir l'URL du tableau de bord approprié pour cet utilisateur
        dashboard_url = CompteUserController.get_user_dashboard_url(request.user)
        logger.info(f"Redirection vers: {dashboard_url}")
        return redirect(dashboard_url)
    
    if request.method == 'POST':
        # Utiliser le contrôleur pour traiter la connexion
        result = CompteUserController.compte_user_login_view(request)
        if isinstance(result, tuple) and len(result) == 2:
            context, response = result
            if response:
                return response
            # Si pas de redirection, utiliser le contexte
        else:
            # Si c'est juste le contexte
            context = result
    else:
        # Initialiser le contexte pour le formulaire vide
        context = {
            'field_errors': {},
            'form_data': {}
        }
    
    response = render(request, 'school_admin/connexion.html', context)
    # Empêcher la mise en cache pour éviter qu'un utilisateur connecté puisse revoir cette page
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def password_reset_request(request):
    """
    Vue pour demander la réinitialisation du mot de passe
    Pour les membres de l'équipe (CompteUser), les établissements (Etablissement), 
    les professeurs (Professeur), les élèves (Eleve) et les parents (Parent)
    Accepte soit un username (CompteUser), un email (Etablissement), un matricule (Professeur, Eleve ou Parent)
    """
    from .model.compte_user import CompteUser
    from .model.etablissement_model import Etablissement
    from .model.professeur_model import Professeur
    from .model.eleve_model import Eleve
    from django.contrib import messages
    from django.utils import timezone
    from datetime import timedelta
    import random
    
    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip()  # Peut être username, email ou matricule
        
        if not identifier:
            messages.error(request, "Veuillez entrer votre nom d'utilisateur, votre email ou votre matricule.")
            return render(request, 'school_admin/password_reset_request.html', {
                'form_data': {'identifier': identifier},
                'field_errors': {'identifier': 'Ce champ est obligatoire'}
            })
        
        # PRIORITÉ 1 : Vérifier d'abord les professeurs, élèves et parents (pas d'email requis)
        # Essayer d'abord de trouver un Professeur par numero_employe (matricule)
        try:
            professeur = Professeur.objects.get(numero_employe__iexact=identifier, actif=True)
            # Si c'est un professeur, rediriger directement vers la page de vérification des informations
            # AUCUN EMAIL N'EST ENVOYÉ pour les professeurs
            return redirect('school_admin:password_reset_professeur_verify', matricule=identifier)
        except Professeur.DoesNotExist:
            pass
        
        # Essayer de trouver un Eleve par username (le matricule est dans username)
        eleve = None
        try:
            # Chercher d'abord par username (car le matricule est dans username)
            eleve = Eleve.objects.get(username__iexact=identifier, actif=True)
            logger.info(f"Élève trouvé par username: {identifier}")
        except Eleve.DoesNotExist:
            # Si pas trouvé par username, essayer aussi par matricule_eleve (au cas où)
            try:
                eleve = Eleve.objects.filter(
                    matricule_eleve__isnull=False
                ).exclude(
                    matricule_eleve=''
                ).get(matricule_eleve__iexact=identifier, actif=True)
                logger.info(f"Élève trouvé par matricule_eleve: {identifier}")
            except Eleve.DoesNotExist:
                pass
        
        if eleve:
            # Si c'est un élève, rediriger directement vers la page de vérification des informations
            # AUCUN EMAIL N'EST ENVOYÉ pour les élèves
            # Utiliser le username comme matricule pour la redirection
            matricule_to_use = eleve.username
            logger.info(f"Redirection vers password_reset_eleve_verify avec matricule: {matricule_to_use}")
            return redirect('school_admin:password_reset_eleve_verify', matricule=matricule_to_use)
        
        # Essayer de trouver un Parent par username (le matricule est dans username)
        from .model.parent_model import Parent
        try:
            parent = Parent.objects.get(username__iexact=identifier, actif=True)
            # Si c'est un parent, rediriger directement vers la page de vérification des informations
            # AUCUN EMAIL N'EST ENVOYÉ pour les parents
            logger.info(f"Parent trouvé par username: {identifier}")
            matricule_to_use = parent.username
            return redirect('school_admin:password_reset_parent_verify', matricule=matricule_to_use)
        except Parent.DoesNotExist:
            pass
        
        # PRIORITÉ 2 : Vérifier les CompteUser et Etablissement (email requis)
        # Ces utilisateurs nécessitent un email pour recevoir le code de réinitialisation
        user = None
        user_type = None
        
        # Essayer de trouver un CompteUser par username
        try:
            user = CompteUser.objects.get(username=identifier)
            user_type = 'compte_user'
        except CompteUser.DoesNotExist:
            # Si pas trouvé, essayer de trouver un Etablissement par email
            try:
                user = Etablissement.objects.get(email=identifier)
                user_type = 'etablissement'
            except Etablissement.DoesNotExist:
                # Ne pas révéler si l'utilisateur existe ou non pour la sécurité
                # Message générique qui ne mentionne pas l'email (car peut être un matricule invalide)
                messages.success(request, "Si cet identifiant existe, vous recevrez les instructions de réinitialisation.")
                return render(request, 'school_admin/password_reset_request.html', {
                    'form_data': {},
                })
        
        # Si on arrive ici, c'est un CompteUser ou Etablissement (nécessite un email)
        if user and user_type:
            # Vérifier que l'utilisateur a bien un email avant d'envoyer le code
            user_email = None
            if user_type == 'etablissement':
                user_email = user.email
            else:
                user_email = user.email
            
            # Vérifier que l'email existe
            if not user_email:
                messages.error(request, "Aucune adresse email associée à ce compte. Veuillez contacter l'administration.")
                return render(request, 'school_admin/password_reset_request.html', {
                    'form_data': {'identifier': identifier},
                })
            
            # Générer un code de 6 chiffres
            reset_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            
            # Stocker le code et définir l'expiration (15 minutes)
            user.password_reset_code = reset_code
            user.password_reset_expires = timezone.now() + timedelta(minutes=15)
            user.save()
            
            # Envoyer l'email avec le code
            from django.core.mail import send_mail
            from django.template.loader import render_to_string
            from django.conf import settings
            
            email_subject = "Réinitialisation de votre mot de passe - Aria"
            
            # Préparer le contexte selon le type d'utilisateur
            if user_type == 'etablissement':
                user_name = f"{user.directeur_prenom} {user.directeur_nom}"
            else:
                user_name = f"{user.prenom} {user.nom}"
            
            email_context = {
                'user': user,
                'user_name': user_name,
                'reset_code': reset_code,
                'expires_in': 15,
                'user_type': user_type,
            }
            
            email_html = render_to_string('school_admin/emails/password_reset_code.html', email_context)
            
            try:
                send_mail(
                    subject=email_subject,
                    message=f"Votre code de réinitialisation est : {reset_code}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user_email],
                    html_message=email_html,
                    fail_silently=False,
                )
                messages.success(request, f"Un code de réinitialisation a été envoyé à votre adresse email ({user_email}).")
                # Utiliser l'identifiant approprié selon le type
                if user_type == 'etablissement':
                    identifier_param = user.email
                else:
                    identifier_param = user.username
                return redirect('school_admin:password_reset_verify', identifier=identifier_param, user_type=user_type)
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi de l'email de réinitialisation: {str(e)}")
                messages.error(request, "Une erreur est survenue lors de l'envoi de l'email. Veuillez réessayer plus tard.")
                return render(request, 'school_admin/password_reset_request.html', {
                    'form_data': {'identifier': identifier},
                })
        else:
            # Ne pas révéler si l'utilisateur existe ou non pour la sécurité
            messages.success(request, "Si cet identifiant existe, un code de réinitialisation a été envoyé à l'adresse email associée.")
            return render(request, 'school_admin/password_reset_request.html', {
                'form_data': {},
            })
    
    return render(request, 'school_admin/password_reset_request.html', {
        'form_data': {},
        'field_errors': {}
    })


def password_reset_verify(request, identifier, user_type):
    """
    Vue pour vérifier le code et réinitialiser le mot de passe
    Gère à la fois les CompteUser et les Etablissement
    """
    from .model.compte_user import CompteUser
    from .model.etablissement_model import Etablissement
    from django.contrib import messages
    from django.utils import timezone
    
    user = None
    
    # Récupérer l'utilisateur selon le type
    try:
        if user_type == 'etablissement':
            user = Etablissement.objects.get(email=identifier)
        else:
            user = CompteUser.objects.get(username=identifier)
    except (CompteUser.DoesNotExist, Etablissement.DoesNotExist):
        messages.error(request, "Utilisateur introuvable.")
        return redirect('school_admin:password_reset_request')
    
    if request.method == 'POST':
        reset_code = request.POST.get('reset_code', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        validation_errors = []
        
        # Vérifier le code
        if not reset_code:
            validation_errors.append("Le code de réinitialisation est obligatoire.")
        elif not user.password_reset_code or user.password_reset_code != reset_code:
            validation_errors.append("Le code de réinitialisation est incorrect.")
        elif not user.password_reset_expires or user.password_reset_expires < timezone.now():
            validation_errors.append("Le code de réinitialisation a expiré. Veuillez en demander un nouveau.")
        
        # Vérifier le nouveau mot de passe
        if not new_password:
            validation_errors.append("Le nouveau mot de passe est obligatoire.")
        elif len(new_password) < 8:
            validation_errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
        
        if not confirm_password:
            validation_errors.append("La confirmation du mot de passe est obligatoire.")
        elif new_password and confirm_password and new_password != confirm_password:
            validation_errors.append("Les mots de passe ne correspondent pas.")
        
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return render(request, 'school_admin/password_reset_verify.html', {
                'identifier': identifier,
                'user_type': user_type,
                'form_data': {
                    'reset_code': reset_code,
                    'new_password': new_password,
                    'confirm_password': confirm_password,
                },
            })
        
        # Toutes les validations sont passées, réinitialiser le mot de passe
        user.set_password(new_password)
        user.password_reset_code = None
        user.password_reset_expires = None
        user.save()
        
        messages.success(request, "Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.")
        if user_type == 'etablissement':
            logger.info(f"Mot de passe réinitialisé - Établissement: {user.email}")
        else:
            logger.info(f"Mot de passe réinitialisé - Utilisateur: {user.username}")
        return redirect('school_admin:connexion_compte_user')
    
    return render(request, 'school_admin/password_reset_verify.html', {
        'identifier': identifier,
        'user_type': user_type,
        'form_data': {},
    })


def password_reset_professeur_verify(request, matricule):
    """
    Vue pour vérifier les informations du professeur avant la réinitialisation du mot de passe
    Vérifie : nom, prénom, nom de l'établissement, téléphone
    Tout est insensible à la casse
    """
    from .model.professeur_model import Professeur
    from django.contrib import messages
    
    try:
        professeur = Professeur.objects.get(numero_employe__iexact=matricule, actif=True)
    except Professeur.DoesNotExist:
        messages.error(request, "Matricule introuvable ou compte inactif.")
        return redirect('school_admin:password_reset_request')
    
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        etablissement_nom = request.POST.get('etablissement_nom', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        
        validation_errors = []
        
        # Vérifier le nom (insensible à la casse)
        if not nom:
            validation_errors.append("Le nom est obligatoire.")
        elif nom.lower() != professeur.nom.lower():
            validation_errors.append("Le nom ne correspond pas.")
        
        # Vérifier le prénom (insensible à la casse)
        if not prenom:
            validation_errors.append("Le prénom est obligatoire.")
        elif prenom.lower() != professeur.prenom.lower():
            validation_errors.append("Le prénom ne correspond pas.")
        
        # Vérifier le nom de l'établissement (insensible à la casse)
        if not etablissement_nom:
            validation_errors.append("Le nom de l'établissement est obligatoire.")
        elif etablissement_nom.lower() != professeur.etablissement.nom.lower():
            validation_errors.append("Le nom de l'établissement ne correspond pas.")
        
        # Vérifier le téléphone (normaliser et comparer - insensible à la casse et aux formats)
        if not telephone:
            validation_errors.append("Le numéro de téléphone est obligatoire.")
        else:
            # Normaliser les deux numéros (enlever espaces, tirets, +, etc.)
            def normalize_phone(phone_str):
                if not phone_str:
                    return ""
                # Enlever tous les caractères non numériques sauf le + au début
                normalized = phone_str.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('.', '')
                # Si commence par +, le garder, sinon enlever
                if normalized.startswith('+'):
                    return normalized
                return normalized.lstrip('+')
            
            telephone_normalized = normalize_phone(telephone)
            professeur_telephone_normalized = normalize_phone(professeur.telephone)
            
            # Comparer les versions normalisées
            if telephone_normalized != professeur_telephone_normalized:
                # Essayer aussi sans le préfixe + et sans les zéros en début
                tel_clean = telephone_normalized.lstrip('+').lstrip('0')
                prof_clean = professeur_telephone_normalized.lstrip('+').lstrip('0')
                if tel_clean != prof_clean:
                    validation_errors.append("Le numéro de téléphone ne correspond pas.")
        
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return render(request, 'school_admin/password_reset_professeur_verify.html', {
                'matricule': matricule,
                'form_data': {
                    'nom': nom,
                    'prenom': prenom,
                    'etablissement_nom': etablissement_nom,
                    'telephone': telephone,
                },
            })
        
        # Toutes les validations sont passées, rediriger vers la page de réinitialisation
        return redirect('school_admin:password_reset_professeur_reset', matricule=matricule)
    
    return render(request, 'school_admin/password_reset_professeur_verify.html', {
        'matricule': matricule,
        'form_data': {},
    })


def password_reset_professeur_reset(request, matricule):
    """
    Vue pour réinitialiser le mot de passe du professeur après vérification des informations
    """
    from .model.professeur_model import Professeur
    from django.contrib import messages
    from django.utils import timezone
    
    try:
        professeur = Professeur.objects.get(numero_employe__iexact=matricule, actif=True)
    except Professeur.DoesNotExist:
        messages.error(request, "Matricule introuvable ou compte inactif.")
        return redirect('school_admin:password_reset_request')
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        validation_errors = []
        
        # Vérifier le nouveau mot de passe
        if not new_password:
            validation_errors.append("Le nouveau mot de passe est obligatoire.")
        elif len(new_password) < 8:
            validation_errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
        
        if not confirm_password:
            validation_errors.append("La confirmation du mot de passe est obligatoire.")
        elif new_password and confirm_password and new_password != confirm_password:
            validation_errors.append("Les mots de passe ne correspondent pas.")
        
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return render(request, 'school_admin/password_reset_professeur_reset.html', {
                'matricule': matricule,
                'form_data': {
                    'new_password': new_password,
                    'confirm_password': confirm_password,
                },
            })
        
        # Toutes les validations sont passées, réinitialiser le mot de passe
        professeur.set_password(new_password)
        professeur.save()
        
        messages.success(request, "Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.")
        logger.info(f"Mot de passe réinitialisé - Professeur: {professeur.numero_employe}")
        return redirect('school_admin:connexion_compte_user')
    
    return render(request, 'school_admin/password_reset_professeur_reset.html', {
        'matricule': matricule,
        'form_data': {},
    })


def password_reset_eleve_verify(request, matricule):
    """
    Vue pour vérifier les informations de l'élève avant la réinitialisation du mot de passe
    Vérifie : nom, prénom, date de naissance, classe, nom du parent inscripteur
    Tout est insensible à la casse
    """
    from .model.eleve_model import Eleve
    from django.contrib import messages
    from datetime import datetime
    
    # Chercher l'élève par username (le matricule est dans username)
    eleve = None
    try:
        # Chercher d'abord par username (car le matricule est dans username)
        eleve = Eleve.objects.get(username__iexact=matricule, actif=True)
        logger.info(f"Élève trouvé par username dans password_reset_eleve_verify: {matricule}")
    except Eleve.DoesNotExist:
        # Si pas trouvé par username, essayer aussi par matricule_eleve (au cas où)
        try:
            eleve = Eleve.objects.filter(
                matricule_eleve__isnull=False
            ).exclude(
                matricule_eleve=''
            ).get(matricule_eleve__iexact=matricule, actif=True)
            logger.info(f"Élève trouvé par matricule_eleve dans password_reset_eleve_verify: {matricule}")
        except Eleve.DoesNotExist:
            messages.error(request, "Matricule introuvable ou compte inactif.")
            return redirect('school_admin:password_reset_request')
    
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        date_naissance = request.POST.get('date_naissance', '').strip()
        classe_nom = request.POST.get('classe_nom', '').strip()
        parent_nom = request.POST.get('parent_nom', '').strip()
        
        validation_errors = []
        
        # Vérifier le nom (insensible à la casse)
        if not nom:
            validation_errors.append("Le nom est obligatoire.")
        elif nom.lower() != eleve.nom.lower():
            validation_errors.append("Le nom ne correspond pas.")
        
        # Vérifier le prénom (insensible à la casse)
        if not prenom:
            validation_errors.append("Le prénom est obligatoire.")
        elif prenom.lower() != eleve.prenom.lower():
            validation_errors.append("Le prénom ne correspond pas.")
        
        # Vérifier la date de naissance
        if not date_naissance:
            validation_errors.append("La date de naissance est obligatoire.")
        else:
            try:
                # L'input de type "date" envoie toujours le format YYYY-MM-DD
                date_parsed = datetime.strptime(date_naissance, '%Y-%m-%d').date()
                
                if date_parsed != eleve.date_naissance:
                    validation_errors.append("La date de naissance ne correspond pas.")
            except ValueError:
                validation_errors.append("Format de date invalide.")
            except Exception as e:
                validation_errors.append("Format de date invalide.")
        
        # Vérifier la classe (insensible à la casse)
        if not classe_nom:
            validation_errors.append("Le nom de la classe est obligatoire.")
        elif not eleve.classe:
            validation_errors.append("Aucune classe n'est associée à cet élève.")
        elif classe_nom.lower() != eleve.classe.nom.lower():
            validation_errors.append("Le nom de la classe ne correspond pas.")
        
        # Vérifier le nom du parent inscripteur (insensible à la casse)
        if not parent_nom:
            validation_errors.append("Le nom du parent inscripteur est obligatoire.")
        else:
            parent_inscripteur = eleve.parent_inscripteur
            if not parent_inscripteur:
                # Si pas de parent inscripteur via LienFamilial, utiliser les champs parent_nom et parent_prenom
                parent_full_name = f"{eleve.parent_prenom} {eleve.parent_nom}".strip()
                if parent_nom.lower() not in parent_full_name.lower() and parent_full_name.lower() not in parent_nom.lower():
                    validation_errors.append("Le nom du parent inscripteur ne correspond pas.")
            else:
                # Utiliser le nom du parent depuis LienFamilial
                parent_full_name = f"{parent_inscripteur.prenom} {parent_inscripteur.nom}".strip()
                if parent_nom.lower() not in parent_full_name.lower() and parent_full_name.lower() not in parent_nom.lower():
                    validation_errors.append("Le nom du parent inscripteur ne correspond pas.")
        
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            # S'assurer que la date est au format YYYY-MM-DD pour l'input de type "date"
            date_formatted = date_naissance
            if date_naissance:
                try:
                    # Si la date est dans un autre format, la convertir
                    date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d']
                    date_parsed = None
                    for date_format in date_formats:
                        try:
                            date_parsed = datetime.strptime(date_naissance, date_format).date()
                            break
                        except ValueError:
                            continue
                    if date_parsed:
                        date_formatted = date_parsed.strftime('%Y-%m-%d')
                except:
                    pass
            
            from datetime import date
            return render(request, 'school_admin/password_reset_eleve_verify.html', {
                'matricule': matricule,
                'form_data': {
                    'nom': nom,
                    'prenom': prenom,
                    'date_naissance': date_formatted,
                    'classe_nom': classe_nom,
                    'parent_nom': parent_nom,
                },
                'today': date.today(),
            })
        
        # Toutes les validations sont passées, rediriger vers la page de réinitialisation
        return redirect('school_admin:password_reset_eleve_reset', matricule=matricule)
    
    from datetime import date
    return render(request, 'school_admin/password_reset_eleve_verify.html', {
        'matricule': matricule,
        'form_data': {},
        'today': date.today(),
    })


def password_reset_eleve_reset(request, matricule):
    """
    Vue pour réinitialiser le mot de passe de l'élève après vérification des informations
    """
    from .model.eleve_model import Eleve
    from django.contrib import messages
    
    # Chercher l'élève par username (le matricule est dans username)
    eleve = None
    try:
        # Chercher d'abord par username (car le matricule est dans username)
        eleve = Eleve.objects.get(username__iexact=matricule, actif=True)
        logger.info(f"Élève trouvé par username dans password_reset_eleve_reset: {matricule}")
    except Eleve.DoesNotExist:
        # Si pas trouvé par username, essayer aussi par matricule_eleve (au cas où)
        try:
            eleve = Eleve.objects.filter(
                matricule_eleve__isnull=False
            ).exclude(
                matricule_eleve=''
            ).get(matricule_eleve__iexact=matricule, actif=True)
            logger.info(f"Élève trouvé par matricule_eleve dans password_reset_eleve_reset: {matricule}")
        except Eleve.DoesNotExist:
            messages.error(request, "Matricule introuvable ou compte inactif.")
            return redirect('school_admin:password_reset_request')
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        validation_errors = []
        
        # Vérifier le nouveau mot de passe
        if not new_password:
            validation_errors.append("Le nouveau mot de passe est obligatoire.")
        elif len(new_password) < 8:
            validation_errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
        
        if not confirm_password:
            validation_errors.append("La confirmation du mot de passe est obligatoire.")
        elif new_password and confirm_password and new_password != confirm_password:
            validation_errors.append("Les mots de passe ne correspondent pas.")
        
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return render(request, 'school_admin/password_reset_eleve_reset.html', {
                'matricule': matricule,
                'form_data': {
                    'new_password': new_password,
                    'confirm_password': confirm_password,
                },
            })
        
        # Toutes les validations sont passées, réinitialiser le mot de passe
        eleve.set_password(new_password)
        eleve.mot_de_passe_eleve_modifie = True  # Marquer que le mot de passe a été modifié
        eleve.save()
        
        messages.success(request, "Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.")
        # Utiliser username comme identifiant pour le log (car le matricule est dans username)
        logger.info(f"Mot de passe réinitialisé - Élève: {eleve.username}")
        return redirect('school_admin:connexion_compte_user')
    
    return render(request, 'school_admin/password_reset_eleve_reset.html', {
        'matricule': matricule,
        'form_data': {},
    })


def password_reset_parent_verify(request, matricule):
    """
    Vue pour vérifier les informations du parent avant la réinitialisation du mot de passe
    Vérifie : nom, prénom, téléphone, nom et prénom d'un élève lié
    Tout est insensible à la casse
    """
    from .model.parent_model import Parent
    from django.contrib import messages
    
    # Chercher le parent par username (le matricule est dans username)
    try:
        parent = Parent.objects.get(username__iexact=matricule, actif=True)
        logger.info(f"Parent trouvé par username dans password_reset_parent_verify: {matricule}")
    except Parent.DoesNotExist:
        messages.error(request, "Matricule introuvable ou compte inactif.")
        return redirect('school_admin:password_reset_request')
    
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        eleve_nom = request.POST.get('eleve_nom', '').strip()
        eleve_prenom = request.POST.get('eleve_prenom', '').strip()
        
        validation_errors = []
        
        # Vérifier le nom (insensible à la casse)
        if not nom:
            validation_errors.append("Le nom est obligatoire.")
        elif nom.lower() != parent.nom.lower():
            validation_errors.append("Le nom ne correspond pas.")
        
        # Vérifier le prénom (insensible à la casse)
        if not prenom:
            validation_errors.append("Le prénom est obligatoire.")
        elif prenom.lower() != parent.prenom.lower():
            validation_errors.append("Le prénom ne correspond pas.")
        
        # Vérifier le téléphone (normaliser et comparer - insensible à la casse et aux formats)
        if not telephone:
            validation_errors.append("Le numéro de téléphone est obligatoire.")
        else:
            # Normaliser les deux numéros (enlever espaces, tirets, +, etc.)
            def normalize_phone(phone_str):
                if not phone_str:
                    return ""
                # Enlever tous les caractères non numériques sauf le + au début
                normalized = phone_str.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('.', '')
                # Si commence par +, le garder, sinon enlever
                if normalized.startswith('+'):
                    return normalized
                return normalized.lstrip('+')
            
            telephone_normalized = normalize_phone(telephone)
            parent_telephone_normalized = normalize_phone(parent.telephone)
            
            # Comparer les versions normalisées
            if telephone_normalized != parent_telephone_normalized:
                # Essayer aussi sans le préfixe + et sans les zéros en début
                tel_clean = telephone_normalized.lstrip('+').lstrip('0')
                parent_clean = parent_telephone_normalized.lstrip('+').lstrip('0')
                if tel_clean != parent_clean:
                    validation_errors.append("Le numéro de téléphone ne correspond pas.")
        
        # Vérifier le nom et prénom d'un élève lié (insensible à la casse)
        if not eleve_nom:
            validation_errors.append("Le nom de l'élève est obligatoire.")
        if not eleve_prenom:
            validation_errors.append("Le prénom de l'élève est obligatoire.")
        
        if eleve_nom and eleve_prenom:
            # Récupérer les élèves liés au parent
            enfants = parent.enfants
            if not enfants.exists():
                validation_errors.append("Aucun élève n'est lié à ce compte parent.")
            else:
                # Vérifier si un élève correspond
                eleve_trouve = False
                for enfant in enfants:
                    if (enfant.nom.lower() == eleve_nom.lower() and 
                        enfant.prenom.lower() == eleve_prenom.lower()):
                        eleve_trouve = True
                        break
                
                if not eleve_trouve:
                    validation_errors.append("Aucun élève avec ce nom et prénom n'est lié à ce compte parent.")
        
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return render(request, 'school_admin/password_reset_parent_verify.html', {
                'matricule': matricule,
                'form_data': {
                    'nom': nom,
                    'prenom': prenom,
                    'telephone': telephone,
                    'eleve_nom': eleve_nom,
                    'eleve_prenom': eleve_prenom,
                },
            })
        
        # Toutes les validations sont passées, rediriger vers la page de réinitialisation
        return redirect('school_admin:password_reset_parent_reset', matricule=matricule)
    
    return render(request, 'school_admin/password_reset_parent_verify.html', {
        'matricule': matricule,
        'form_data': {},
    })


def password_reset_parent_reset(request, matricule):
    """
    Vue pour réinitialiser le mot de passe du parent après vérification des informations
    """
    from .model.parent_model import Parent
    from django.contrib import messages
    
    # Chercher le parent par username (le matricule est dans username)
    try:
        parent = Parent.objects.get(username__iexact=matricule, actif=True)
        logger.info(f"Parent trouvé par username dans password_reset_parent_reset: {matricule}")
    except Parent.DoesNotExist:
        messages.error(request, "Matricule introuvable ou compte inactif.")
        return redirect('school_admin:password_reset_request')
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        validation_errors = []
        
        # Vérifier le nouveau mot de passe
        if not new_password:
            validation_errors.append("Le nouveau mot de passe est obligatoire.")
        elif len(new_password) < 8:
            validation_errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
        
        if not confirm_password:
            validation_errors.append("La confirmation du mot de passe est obligatoire.")
        elif new_password and confirm_password and new_password != confirm_password:
            validation_errors.append("Les mots de passe ne correspondent pas.")
        
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return render(request, 'school_admin/password_reset_parent_reset.html', {
                'matricule': matricule,
                'form_data': {
                    'new_password': new_password,
                    'confirm_password': confirm_password,
                },
            })
        
        # Toutes les validations sont passées, réinitialiser le mot de passe
        parent.set_password(new_password)
        parent.mot_de_passe_modifie = True  # Marquer que le mot de passe a été modifié
        parent.save()
        
        messages.success(request, "Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.")
        logger.info(f"Mot de passe réinitialisé - Parent: {parent.username}")
        return redirect('school_admin:connexion_compte_user')
    
    return render(request, 'school_admin/password_reset_parent_reset.html', {
        'matricule': matricule,
        'form_data': {},
    })


OTP_RESEND_COOLDOWN_SECONDS = 60


def _normalize_phone_digits(phone_value: Optional[str]) -> str:
    if not phone_value:
        return ""
    return "".join(ch for ch in str(phone_value) if ch.isdigit())


def _find_professeur_by_phone(phone_number: str) -> Optional[Professeur]:
    """
    Recherche un professeur actif en comparant le numéro sous plusieurs formats.
    """

    professeur = Professeur.objects.filter(
        telephone__iexact=phone_number,
        actif=True,
    ).first()
    if professeur:
        return professeur

    stripped_plus = phone_number.lstrip("+")
    if stripped_plus != phone_number:
        professeur = Professeur.objects.filter(
            telephone__iexact=stripped_plus,
            actif=True,
        ).first()
        if professeur:
            return professeur

    normalized_input = _normalize_phone_digits(phone_number)
    if not normalized_input:
        return None

    for prof in Professeur.objects.filter(actif=True).only("id", "telephone", "actif"):
        if _normalize_phone_digits(prof.telephone) == normalized_input:
            return prof

    return None


def professeur_connexion_otp_request(request):
    """
    Affiche le formulaire de demande d'OTP pour les professeurs et gère l'envoi du code.
    """

    form = ProfesseurOtpRequestForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        phone_number = form.cleaned_data["phone_number"]
        professeur = _find_professeur_by_phone(phone_number)

        recent_code = (
            ProfesseurOtpCode.objects.filter(
                phone_number=phone_number,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )

        if (
            recent_code
            and not recent_code.is_expired()
            and (timezone.now() - recent_code.created_at).total_seconds()
            < OTP_RESEND_COOLDOWN_SECONDS
        ):
            wait_seconds = OTP_RESEND_COOLDOWN_SECONDS - int(
                (timezone.now() - recent_code.created_at).total_seconds()
            )
            messages.warning(
                request,
                (
                    "Veuillez patienter encore "
                    f"{wait_seconds} seconde(s) avant de redemander un code."
                ),
            )
        else:
            otp_code = f"{secrets.randbelow(1_000_000):06d}"
            otp_entry = ProfesseurOtpCode.objects.create(
                professeur=professeur,
                phone_number=phone_number,
                code=otp_code,
                expires_at=ProfesseurOtpCode.build_expiration(),
            )

            client = WasenderApiClient()
            message = (
                "Goo-school - Code de connexion: "
                f"{otp_code}. Ce code expire dans 5 minutes."
            )

            try:
                response = client.send_text_message(
                    phone_number=phone_number,
                    message=message,
                )
                if not response.is_success:
                    raise ValueError(response.body)
            except Exception as exc:
                otp_entry.delete()
                logger.exception("Erreur lors de l'envoi du code OTP")
                messages.error(
                    request,
                    (
                        "Impossible d'envoyer le code pour le moment. "
                        "Veuillez réessayer ultérieurement."
                    ),
                )
            else:
                messages.success(
                    request,
                    (
                        "Un code de validation vous a été envoyé sur WhatsApp. "
                        "Veuillez le saisir pour poursuivre votre connexion."
                    ),
                )
                return redirect(
                    reverse(
                        "school_admin:prof_connexion_otp_verify",
                        kwargs={"token": str(otp_entry.token)},
                    )
                )

    context = {
        "form": form,
    }
    return render(
        request,
        "school_admin/professeurs/connexion_otp.html",
        context,
    )


def professeur_connexion_otp_verification(request, token):
    """
    Vérifie le code OTP saisi et connecte le professeur.
    """

    otp_entry = get_object_or_404(ProfesseurOtpCode, token=token)

    if otp_entry.is_used:
        messages.info(
            request,
            "Ce code a déjà été utilisé. Veuillez en générer un nouveau.",
        )
        return redirect("school_admin:prof_connexion_otp")

    if otp_entry.is_expired():
        messages.error(
            request,
            "Ce code a expiré. Merci de demander un nouveau code.",
        )
        return redirect("school_admin:prof_connexion_otp")

    form = ProfesseurOtpVerifyForm(
        request.POST or None,
        initial={"otp_token": otp_entry.token},
    )

    if request.method == "POST" and form.is_valid():
        posted_token = form.cleaned_data["otp_token"]
        if str(posted_token) != str(otp_entry.token):
            messages.error(
                request,
                "Le jeton de validation est invalide. Veuillez recommencer.",
            )
            return redirect("school_admin:prof_connexion_otp")

        if otp_entry.attempts >= ProfesseurOtpCode.MAX_ATTEMPTS:
            messages.error(
                request,
                "Nombre de tentatives dépassé. Veuillez redemander un code.",
            )
            otp_entry.is_used = True
            otp_entry.save(update_fields=["is_used", "updated_at"])
            return redirect("school_admin:prof_connexion_otp")

        if form.cleaned_data["otp_code"] != otp_entry.code:
            otp_entry.attempts += 1
            otp_entry.save(update_fields=["attempts", "updated_at"])
            remaining = ProfesseurOtpCode.MAX_ATTEMPTS - otp_entry.attempts
            messages.error(
                request,
                (
                    "Code incorrect. "
                    f"Il vous reste {max(remaining, 0)} tentative(s)."
                ),
            )
        else:
            professeur = otp_entry.professeur or _find_professeur_by_phone(
                otp_entry.phone_number
            )
            if not professeur:
                messages.error(
                    request,
                    (
                        "Votre numéro n'est pas associé à un compte professeur actif. "
                        "Veuillez contacter l'administration."
                    ),
                )
                return redirect("school_admin:prof_connexion_otp")

            if otp_entry.professeur is None:
                otp_entry.professeur = professeur

            otp_entry.is_used = True
            otp_entry.used_at = timezone.now()
            otp_entry.save(
                update_fields=["is_used", "used_at", "professeur", "updated_at"]
            )

            professeur._auth_user_type = "professeur"
            login(
                request,
                professeur,
                backend="school_admin.authentication_backends.MultiUserBackend",
            )

            if professeur.etablissement.type_etablissement == "primary":
                redirect_url = "enseignant_primaire:dashboard"
            else:
                redirect_url = "enseignant:dashboard_enseignant"

            messages.success(request, "Connexion réussie. Bienvenue !")
            return redirect(redirect_url)

    context = {
        "form": form,
        "expires_in": otp_entry.remaining_seconds(),
        "phone_number": otp_entry.phone_number,
        "token": otp_entry.token,
    }
    return render(
        request,
        "school_admin/professeurs/connexion_otp_verification.html",
        context,
    )





# ===== SUPPORT =====
def dashboard_support(request):
    """
    Tableau de bord pour le support client
    """
    context = {
        'user_function': 'support',
        'page_title': 'Tableau de bord Support'
    }
    return render(request, 'school_admin/dashboards/dashboard_support.html', context)


# ===== DEVELOPPEUR =====
def dashboard_developpeur(request):
    """
    Tableau de bord pour les développeurs
    """
    context = {
        'user_function': 'developpeur',
        'page_title': 'Tableau de bord Développeur'
    }
    return render(request, 'school_admin/dashboards/dashboard_developpeur.html', context)


# ===== MARKETING =====
def dashboard_marketing(request):
    """
    Tableau de bord pour le marketing
    """
    context = {
        'user_function': 'marketing',
        'page_title': 'Tableau de bord Marketing'
    }
    return render(request, 'school_admin/dashboards/dashboard_marketing.html', context)


# ===== COMPTABLE =====
def dashboard_comptable(request):
    """
    Tableau de bord pour les comptables
    """
    context = {
        'user_function': 'comptable',
        'page_title': 'Tableau de bord Comptable'
    }
    return render(request, 'school_admin/dashboards/dashboard_comptable.html', context)


# ===== RH =====
def dashboard_rh(request):
    """
    Tableau de bord pour les ressources humaines
    """
    context = {
        'user_function': 'ressources humaines',
        'page_title': 'Tableau de bord Ressources Humaines'
    }
    return render(request, 'school_admin/dashboards/dashboard_rh.html', context)

# ===== DECONNEXION PAR FONCTION =====
# ===== COMMERCIAL =====
def deconnexion_compte_commercial(request):
    """
    Déconnexion d'un compte commercial
    """
    return CommercialCompteController.logout_user_commercial(request)

# ===== ADMINISTRATEUR =====
def deconnexion_compte_administrateur(request):
    """
    Déconnexion d'un compte administrateur
    """
    return AdministrateurCompteController.logout_user_administrateur(request)

# ===== SUPPORT =====

# ===== DEVELOPPEUR =====

# ===== MARKETING =====

# ===== COMPTABLE =====

# ===== RH =====


# ===== FIREBASE SERVICE WORKER =====
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_control

@require_http_methods(["GET"])
@cache_control(max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def firebase_messaging_sw(request):
    """
    Sert le fichier Service Worker pour Firebase Cloud Messaging
    avec le bon Content-Type et depuis la racine du site
    """
    sw_content = """// Service Worker pour Firebase Cloud Messaging

// Import Firebase scripts
importScripts('https://www.gstatic.com/firebasejs/12.5.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/12.5.0/firebase-messaging-compat.js');

// Configuration Firebase
const firebaseConfig = {
  apiKey: "AIzaSyCSvm0VNdvnLqdIFPdDs4DPYDjHvDsO4_Q",
  authDomain: "gestion-scolaire-6945a.firebaseapp.com",
  projectId: "gestion-scolaire-6945a",
  storageBucket: "gestion-scolaire-6945a.firebasestorage.app",
  messagingSenderId: "983006440407",
  appId: "1:983006440407:web:8cbfc916f43b745a7e7992",
  measurementId: "G-1SHG5PC5T7"
};

// Initialiser Firebase
firebase.initializeApp(firebaseConfig);

// Initialiser Firebase Messaging
const messaging = firebase.messaging();

// Gérer les notifications en arrière-plan
messaging.onBackgroundMessage((payload) => {
  console.log('[firebase-messaging-sw.js] Message reçu en arrière-plan', payload);
  
  const notificationTitle = payload.notification?.title || 'Nouvelle notification';
  const notificationOptions = {
    body: payload.notification?.body || 'Vous avez une nouvelle notification',
    icon: '/static/school_admin/images/logo.png',
    badge: '/static/school_admin/images/badge.png',
    tag: payload.data?.tag || 'general',
    data: payload.data || {},
    requireInteraction: true,
    vibrate: [200, 100, 200],
  };

  return self.registration.showNotification(notificationTitle, notificationOptions);
});

// Gérer le clic sur la notification
self.addEventListener('notificationclick', (event) => {
  console.log('[firebase-messaging-sw.js] Clic sur la notification', event);
  
  event.notification.close();
  
  // Ouvrir l'URL spécifiée ou le dashboard
  const urlToOpen = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Vérifier si une fenêtre est déjà ouverte
        for (let i = 0; i < clientList.length; i++) {
          const client = clientList[i];
          if (client.url === urlToOpen && 'focus' in client) {
            return client.focus();
          }
        }
        // Ouvrir une nouvelle fenêtre
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});
"""
    
    return HttpResponse(sw_content, content_type='application/javascript; charset=utf-8')


# ===== PAGE DE TEST FCM =====
from django.contrib.auth.decorators import login_required

@login_required
def test_fcm_page(request):
    """
    Page de test pour les notifications FCM
    """
    return render(request, 'school_admin/test_fcm.html')
