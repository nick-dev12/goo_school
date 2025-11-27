# school_admin/controllers/etablissement_controller.py

from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import get_user_model
from django.db import transaction
from django.contrib import messages
from django.db.models import Q
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django_countries import countries
import logging
import uuid
import random
import string
import threading
from ..model.etablissement_model import Etablissement


# Configurer le logger
logger = logging.getLogger(__name__)

class EtablissementController:
    """
    Contrôleur pour gérer toutes les actions liées aux établissements
    """
    
    @staticmethod
    def generate_etablissement_code(type_etablissement):
        """
        Génère un code unique pour un établissement avec un préfixe basé sur le type
        
        Args:
            type_etablissement (str): Le type d'établissement ('primary', 'secondary', 'highschool')
            
        Returns:
            str: Le code unique généré
        """
        # Définir le préfixe en fonction du type d'établissement
        prefixes = {
            'primary': 'PRI-',
            'collège': 'COL-',
            'lycée': 'LYC-',
            'collège_lycée': 'CL-',
            'mixte': 'MIX-'
        }
        
        prefix = prefixes.get(type_etablissement, 'ETB-')
        
        # Générer une partie numérique aléatoire (5 chiffres)
        numeric_part = ''.join(random.choices(string.digits, k=5))
        
        # Générer une partie alphabétique aléatoire (2 lettres majuscules)
        alpha_part = ''.join(random.choices(string.ascii_uppercase, k=2))
        
        # Combiner pour former le code complet
        code = f"{prefix}{numeric_part}{alpha_part}"
        
        # Vérifier si le code existe déjà, si oui, en générer un nouveau
        while Etablissement.objects.filter(code_etablissement=code).exists():
            numeric_part = ''.join(random.choices(string.digits, k=5))
            alpha_part = ''.join(random.choices(string.ascii_uppercase, k=2))
            code = f"{prefix}{numeric_part}{alpha_part}"
        
        return code
    
    @staticmethod
    def get_all_etablissements(search_query=None, type_filter=None, status_filter=None):
        """
        Récupère tous les établissements avec possibilité de filtrage
        
        Args:
            search_query (str, optional): Terme de recherche pour filtrer les établissements
            type_filter (str, optional): Filtre par type d'établissement
            status_filter (str, optional): Filtre par statut (actif/inactif)
            
        Returns:
            QuerySet: Liste des établissements filtrés
        """
        etablissements = Etablissement.objects.all().order_by('-date_creation')
        
        # Récupérer le nombre d'établissements par pays
        # Appliquer les filtres si fournis
        if search_query:
            etablissements = etablissements.filter(
                Q(nom__icontains=search_query) | 
                Q(directeur_prenom__icontains=search_query) | 
                Q(directeur_nom__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        
        if type_filter and type_filter != "":
            etablissements = etablissements.filter(type_etablissement=type_filter)
            
        if status_filter:
            if status_filter == "active":
                etablissements = etablissements.filter(actif=True)
            elif status_filter == "inactive":
                etablissements = etablissements.filter(actif=False)
        
        return etablissements
    
    def get_etablissement_by_id(id):
        """
        Récupère un établissement par son ID
        """
        etablissement = Etablissement.objects.get(id=id)
        return etablissement
    
    def count_all_etablissements():
        """
        Compte le nombre d'établissements
        """
        total_etablissements = Etablissement.objects.count()
        return total_etablissements
    
    @staticmethod
    def get_etablissement_stats_by_country():
        """
        Récupère le nombre d'établissements par pays
        
        Returns:
            dict: Dictionnaire avec les pays comme clés et le nombre d'établissements comme valeurs
        """
        from django.db.models import Count
        stats = Etablissement.objects.values('pays').annotate(count=Count('id')).order_by('-count')
        return {item['pays']: item['count'] for item in stats}

    @staticmethod
    def get_etablissement_stats_by_type():
        """
        Récupère le nombre d'établissements par type
        
        Returns:
            dict: Dictionnaire avec les types comme clés et le nombre d'établissements comme valeurs
        """
        from django.db.models import Count
        stats = Etablissement.objects.values('type_etablissement').annotate(count=Count('id')).order_by('-count')
        type_labels = {
            'primary': 'Écoles Primaires',
            'collège': 'Collèges',
            'lycée': 'Lycées',
            'collège_lycée': 'Collège + Lycée',
            'mixte': 'Établissements Mixtes'
        }
        return {type_labels.get(item['type_etablissement'], item['type_etablissement']): item['count'] for item in stats}

    @staticmethod
    def get_recent_etablissements():
        """
        Récupère les 5 derniers établissements créés
        
        Returns:
            QuerySet: Les 5 derniers établissements créés
        """
        return Etablissement.objects.order_by('-date_creation')[:5]
    
    @staticmethod
    def count_active_etablissements():
        """
        Compte le nombre d'établissements actifs
        
        Returns:
            int: Nombre d'établissements actifs
        """
        return Etablissement.objects.filter(actif=True).count()
    
    @staticmethod
    def send_etablissement_creation_email(etablissement, data):
        """
        Envoie un email de bienvenue à l'établissement avec les informations de connexion
        
        Args:
            etablissement: L'objet Etablissement créé
            data: Les données du formulaire contenant les informations
        """
        # Préparer les données pour le template
        type_etablissement_labels = {
            'primary': 'École Primaire',
            'collège': 'Collège',
            'lycée': 'Lycée',
            'collège_lycée': 'Collège + Lycée',
            'mixte': 'Établissement Mixte (Primaire + Collège + Lycée)'
        }
        
        type_facturation_labels = {
            'mensuel': 'Facturation mensuelle',
            'annuel': 'Facturation annuelle'
        }
        
        # Liste des modules activés
        modules_actives = []
        module_labels = {
            'module_gestion_eleves': 'Gestion des élèves',
            'module_notes_evaluations': 'Notes et évaluations',
            'module_emploi_temps': 'Emploi du temps',
            'module_gestion_personnel': 'Gestion du personnel',
            'module_surveillance': 'Surveillance et sécurité',
            'module_communication': 'Communication parents',
            'module_orientation': 'Orientation scolaire',
            'module_formation': 'Formation continue',
            'module_transport_scolaire': 'Transport scolaire',
            'module_cantine': 'Gestion de la cantine',
            'module_bibliotheque': 'Gestion de la bibliothèque',
            'module_sante': 'Suivi médical',
            'module_activites': 'Activités extra-scolaires',
            'module_comptabilite': 'Comptabilité',
            'module_censeurs': 'Censeurs'
        }
        
        for module_key, module_label in module_labels.items():
            if data.get(module_key):
                modules_actives.append(module_label)
        
        # Construire l'URL de connexion
        # Utiliser le premier host autorisé ou localhost en développement
        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS[0] != '*' else 'localhost:8000'
        protocol = 'https' if not settings.DEBUG else 'http'
        login_url = f"{protocol}://{host}/school_admin/connexion/"
        
        # Contexte pour le template
        context = {
            'directeur_prenom': etablissement.directeur_prenom,
            'directeur_nom': etablissement.directeur_nom,
            'establishment_name': etablissement.nom,
            'establishment_type_display': type_etablissement_labels.get(etablissement.type_etablissement, etablissement.type_etablissement),
            'code_etablissement': etablissement.code_etablissement,
            'establishment_address': etablissement.adresse,
            'establishment_city': etablissement.ville,
            'establishment_country': etablissement.pays,
            'establishment_email': etablissement.email,
            'establishment_phone': etablissement.telephone or '',
            'establishment_password': data.get('establishment_password', ''),
            'login_url': login_url,
            'modules_actives': modules_actives,
            'type_facturation': data.get('type_facturation', ''),
            'type_facturation_display': type_facturation_labels.get(data.get('type_facturation', ''), data.get('type_facturation', '')),
            'montant_par_eleve': f"{float(data.get('montant_par_eleve', 0)):,.0f}"
        }
        
        # Rendre le template HTML
        html_message = render_to_string('school_admin/emails/etablissement_creation.html', context)
        
        # Sujet de l'email
        subject = f"Bienvenue sur Aria - Votre établissement {etablissement.nom} a été créé"
        
        # Envoyer l'email
        send_mail(
            subject=subject,
            message='',  # Message texte vide car on utilise HTML
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[etablissement.email],
            html_message=html_message,
            fail_silently=False,
        )
    
    @staticmethod
    def ajouter_etablissement(request, data):
        """
        Ajoute un nouvel établissement et crée un compte directeur associé
        
        Args:
            request: L'objet request Django
            data: Les données du formulaire
            
        Returns:
            tuple: (success, message, etablissement, errors)
        """
        errors = {}
        
        try:
            # Validation des champs obligatoires
            required_fields = {
                'teacher_firstname': 'Prénom du directeur',
                'teacher_lastname': 'Nom du directeur',
                'teacher_email': 'Email du directeur',
                'establishment_name': 'Nom de l\'établissement',
                'establishment_address': 'Adresse de l\'établissement',
                'establishment_country': 'Pays',
                'establishment_email': 'Email de l\'établissement',
                'establishment_type': 'Type d\'établissement',
                'type_facturation': 'Type de facturation',
                'montant_par_eleve': 'Montant par élève'
            }
            
            # Vérifier les champs obligatoires
            for field, label in required_fields.items():
                if not data.get(field):
                    errors[field] = f"Le champ {label} est obligatoire."
            
            # Si des champs obligatoires sont manquants, retourner l'erreur
            if errors:
                return False, "Veuillez remplir tous les champs obligatoires.", None, errors
            
            # Validation des emails
            if '@' not in data.get('teacher_email', ''):
                errors['teacher_email'] = "L'adresse email du directeur n'est pas valide."
                return False, "L'adresse email du directeur n'est pas valide.", None, errors
                
            if '@' not in data.get('establishment_email', ''):
                errors['establishment_email'] = "L'adresse email de l'établissement n'est pas valide."
                return False, "L'adresse email de l'établissement n'est pas valide.", None, errors

            # Validation du pays via django-countries
            valid_country_codes = {code for code, _ in countries}
            selected_country_code = data.get('establishment_country')
            if selected_country_code not in valid_country_codes:
                errors['establishment_country'] = "Le pays sélectionné n'est pas valide."
                return False, "Le pays sélectionné n'est pas valide.", None, errors
            country_display_name = dict(countries).get(selected_country_code, selected_country_code)
            
            teacher_phone_value = (data.get('teacher_phone_full') or data.get('teacher_phone') or '').strip()
            establishment_phone_value = (data.get('establishment_phone_full') or data.get('establishment_phone') or '').strip()
            
            # Vérification si l'email du directeur existe déjà
            if Etablissement.objects.filter(email=data['teacher_email']).exists():
                errors['teacher_email'] = "Cette adresse email de directeur est déjà utilisée."
                return False, "Cette adresse email de directeur est déjà utilisée.", None, errors
            
            # Vérification si l'email de l'établissement existe déjà
            if Etablissement.objects.filter(email=data['establishment_email']).exists():
                errors['establishment_email'] = "Cette adresse email d'établissement est déjà utilisée."
                return False, "Cette adresse email d'établissement est déjà utilisée.", None, errors
            
            # Générer un mot de passe provisoire aléatoire de 8 caractères
            # Mélange de lettres majuscules, minuscules, chiffres et symboles
            password_chars = string.ascii_letters + string.digits + "!@#$%&*"
            establishment_password = ''.join(random.choices(password_chars, k=8))
            
            logger.info(f"Mot de passe provisoire généré automatiquement (8 caractères)")
            
            # Vérification du type d'établissement
            valid_types = ['primary', 'collège', 'lycée', 'collège_lycée', 'mixte']
            if data['establishment_type'] not in valid_types:
                errors['establishment_type'] = "Le type d'établissement n'est pas valide."
                return False, "Le type d'établissement n'est pas valide.", None, errors
            
            # Validation du type de facturation
            valid_facturation_types = ['mensuel', 'annuel']
            if data['type_facturation'] not in valid_facturation_types:
                errors['type_facturation'] = "Le type de facturation n'est pas valide."
                return False, "Le type de facturation n'est pas valide.", None, errors
            
            # Validation du montant par élève
            try:
                montant_par_eleve = float(data['montant_par_eleve'])
                if montant_par_eleve < 0:
                    errors['montant_par_eleve'] = "Le montant par élève ne peut pas être négatif."
                    return False, "Le montant par élève ne peut pas être négatif.", None, errors
            except (ValueError, TypeError):
                errors['montant_par_eleve'] = "Le montant par élève doit être un nombre valide."
                return False, "Le montant par élève doit être un nombre valide.", None, errors
            
            email_directeur = data['teacher_email']
            username = email_directeur
            
            # Création de l'établissement et du compte directeur dans une transaction
            with transaction.atomic():
                # Générer un code unique pour l'établissement
                code_etablissement = EtablissementController.generate_etablissement_code(data['establishment_type'])
                
                # 1. Créer l'établissement
                etablissement = Etablissement(
                    code_etablissement=code_etablissement,
                    nom=data['establishment_name'],
                    adresse=data['establishment_address'],
                    pays=country_display_name,
                    ville=data['establishment_city'],
                    email=data['establishment_email'],
                    telephone=establishment_phone_value,
                    type_etablissement=data['establishment_type'],
                    directeur_prenom=data['teacher_firstname'],
                    directeur_nom=data['teacher_lastname'],
                    directeur_email=data['teacher_email'],
                    directeur_telephone=teacher_phone_value,
                    username=username,
                    cree_par=request.user if request.user.is_authenticated else None,
                    # Configuration de facturation
                    type_facturation=data['type_facturation'],
                    montant_par_eleve=montant_par_eleve,
                    # Modules activés
                    module_gestion_eleves=bool(data.get('module_gestion_eleves')),
                    module_notes_evaluations=bool(data.get('module_notes_evaluations')),
                    module_emploi_temps=bool(data.get('module_emploi_temps')),
                    module_gestion_personnel=bool(data.get('module_gestion_personnel')),
                    # Modules premium
                    module_surveillance=bool(data.get('module_surveillance')),
                    module_communication=bool(data.get('module_communication')),
                    module_orientation=bool(data.get('module_orientation')),
                    module_formation=bool(data.get('module_formation')),
                    # Modules optionnels
                    module_transport_scolaire=bool(data.get('module_transport_scolaire')),
                    module_cantine=bool(data.get('module_cantine')),
                    module_bibliotheque=bool(data.get('module_bibliotheque')),
                    module_sante=bool(data.get('module_sante')),
                    module_activites=bool(data.get('module_activites')),
                    module_comptabilite=bool(data.get('module_comptabilite')),
                    module_censeurs=bool(data.get('module_censeurs'))
                )
                
                # Définir le mot de passe provisoire généré pour l'établissement
                etablissement.set_password(establishment_password)
                
                # Sauvegarder l'établissement dans la base de données
                etablissement.save()
                
                logger.info(f"Établissement créé: {etablissement.nom}")
            
            # Après le commit de la transaction, envoyer l'email en arrière-plan
            # On récupère l'ID de l'établissement et les données nécessaires
            # pour s'assurer qu'il est bien en base avant d'envoyer l'email
            etablissement_id = etablissement.id
            etablissement_email = etablissement.email
            
            # Copier les données nécessaires pour l'email (éviter les problèmes de closure)
            # Utiliser le mot de passe généré automatiquement
            email_data = {
                'teacher_firstname': data.get('teacher_firstname', ''),
                'teacher_lastname': data.get('teacher_lastname', ''),
                'establishment_name': data.get('establishment_name', ''),
                'establishment_type': data.get('establishment_type', ''),
                'establishment_address': data.get('establishment_address', ''),
                'establishment_city': data.get('establishment_city', ''),
                'establishment_country': data.get('establishment_country', ''),
                'establishment_phone': data.get('establishment_phone', ''),
                'establishment_password': establishment_password,  # Utiliser le mot de passe généré
                'type_facturation': data.get('type_facturation', ''),
                'montant_par_eleve': data.get('montant_par_eleve', ''),
                # Modules
                'module_gestion_eleves': data.get('module_gestion_eleves'),
                'module_notes_evaluations': data.get('module_notes_evaluations'),
                'module_emploi_temps': data.get('module_emploi_temps'),
                'module_gestion_personnel': data.get('module_gestion_personnel'),
                'module_surveillance': data.get('module_surveillance'),
                'module_communication': data.get('module_communication'),
                'module_orientation': data.get('module_orientation'),
                'module_formation': data.get('module_formation'),
                'module_transport_scolaire': data.get('module_transport_scolaire'),
                'module_cantine': data.get('module_cantine'),
                'module_bibliotheque': data.get('module_bibliotheque'),
                'module_sante': data.get('module_sante'),
                'module_activites': data.get('module_activites'),
                'module_comptabilite': data.get('module_comptabilite'),
                'module_censeurs': data.get('module_censeurs')
            }
            
            # Fonction pour envoyer l'email en arrière-plan
            def send_email_background(etab_id, etab_email, email_data_dict):
                """
                Envoie l'email en arrière-plan après que l'établissement soit créé et commité
                
                Args:
                    etab_id: ID de l'établissement
                    etab_email: Email de l'établissement
                    email_data_dict: Dictionnaire contenant les données pour l'email
                """
                try:
                    # Attendre un court instant pour s'assurer que la transaction est bien commitée
                    import time
                    time.sleep(0.5)
                    
                    # Récupérer l'établissement depuis la base de données
                    # pour s'assurer qu'il est bien commité
                    from ..model.etablissement_model import Etablissement
                    etablissement_obj = Etablissement.objects.get(id=etab_id)
                    
                    # Envoyer l'email
                    EtablissementController.send_etablissement_creation_email(etablissement_obj, email_data_dict)
                    logger.info(f"Email de création envoyé avec succès à {etab_email}")
                except Etablissement.DoesNotExist:
                    logger.error(f"Établissement avec ID {etab_id} introuvable lors de l'envoi de l'email")
                except Exception as email_error:
                    logger.error(f"Erreur lors de l'envoi de l'email à {etab_email}: {str(email_error)}")
                    # Ne pas faire échouer la création si l'email échoue
            
            # Lancer l'envoi d'email en arrière-plan dans un thread séparé
            # Le thread est en mode daemon pour ne pas bloquer l'arrêt de l'application
            email_thread = threading.Thread(
                target=send_email_background,
                args=(etablissement_id, etablissement_email, email_data),
                daemon=True,
                name=f"EmailThread-{etablissement_id}"
            )
            email_thread.start()
            logger.info(f"Envoi d'email en arrière-plan lancé pour l'établissement {etablissement.nom} (ID: {etablissement_id})")
            
            return True, "L'établissement a été créé avec succès.", etablissement, {}
            
        except Exception as e:
            logger.error(f"[ERREUR CRÉATION ÉTABLISSEMENT] {str(e)}")
            return False, f"Une erreur est survenue lors de la création de l'établissement: {str(e)}", None, {}
    
    @staticmethod
    def process_ajout_etablissement(request):
        """
        Traite la soumission du formulaire d'ajout d'établissement
        
        Args:
            request: L'objet request Django
            
        Returns:
            tuple: (context, redirect_response)
        """
        try:
            pays_list = [(code, str(nom)) for code, nom in countries]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des pays pour le formulaire établissement: {str(e)}")
            pays_list = []

        context = {
            'field_errors': {},
            'form_data': {},
            'pays_list': pays_list,
        }
        
        if request.method == 'POST':
            # Sauvegarder les données du formulaire pour les réafficher en cas d'erreur
            form_data = {
                'teacher_firstname': request.POST.get('teacher_firstname', ''),
                'teacher_lastname': request.POST.get('teacher_lastname', ''),
                'teacher_email': request.POST.get('teacher_email', ''),
                'teacher_phone': request.POST.get('teacher_phone', ''),
                'teacher_phone_full': request.POST.get('teacher_phone_full', ''),
                'establishment_name': request.POST.get('establishment_name', ''),
                'establishment_address': request.POST.get('establishment_address', ''),
                'establishment_email': request.POST.get('establishment_email', ''),
                'establishment_phone': request.POST.get('establishment_phone', ''),
                'establishment_phone_full': request.POST.get('establishment_phone_full', ''),
                'establishment_type': request.POST.get('establishment_type', ''),
                'establishment_country': request.POST.get('establishment_country', ''),
                'establishment_city': request.POST.get('establishment_city', ''),
                # Configuration de facturation
                'type_facturation': request.POST.get('type_facturation', ''),
                'montant_par_eleve': request.POST.get('montant_par_eleve', ''),
                # Modules
                'module_gestion_eleves': request.POST.get('module_gestion_eleves'),
                'module_notes_evaluations': request.POST.get('module_notes_evaluations'),
                'module_emploi_temps': request.POST.get('module_emploi_temps'),
                'module_gestion_personnel': request.POST.get('module_gestion_personnel'),
                # Modules premium
                'module_surveillance': request.POST.get('module_surveillance'),
                'module_communication': request.POST.get('module_communication'),
                'module_orientation': request.POST.get('module_orientation'),
                'module_formation': request.POST.get('module_formation'),
                # Modules optionnels
                'module_transport_scolaire': request.POST.get('module_transport_scolaire'),
                'module_cantine': request.POST.get('module_cantine'),
                'module_bibliotheque': request.POST.get('module_bibliotheque'),
                'module_sante': request.POST.get('module_sante'),
                'module_activites': request.POST.get('module_activites'),
                'module_comptabilite': request.POST.get('module_comptabilite'),
                'module_censeurs': request.POST.get('module_censeurs')
            }
            context['form_data'] = form_data
            
            # Traiter l'ajout de l'établissement
            success, message, etablissement, errors = EtablissementController.ajouter_etablissement(request, request.POST)
            
            if success:
                messages.success(request, message)
                from django.shortcuts import redirect
                return context, redirect('school_admin:etablissements')
            else:
                messages.error(request, message)
                # S'assurer que les clés d'erreur correspondent aux noms des champs dans le template
                field_errors = {}
                for key, value in errors.items():
                    # Convertir les clés avec tirets en clés avec underscores pour le template si nécessaire
                    field_errors[key] = value
                
                context['field_errors'] = field_errors
                # Ajouter des logs pour le débogage
                logger.debug(f"Erreurs de formulaire: {field_errors}")
                logger.debug(f"Données du formulaire: {form_data}")
                return context, None
                
        # Si ce n'est pas une requête POST, simplement afficher le formulaire
        return context, None
