# school_admin/controllers/etablissement_controller.py

from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import get_user_model
from django.db import transaction
from django.contrib import messages
from django.db.models import Q
import logging
import uuid
import random
import string
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
            'lycée': 'LYC-'
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
            'lycée': 'Lycées'
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
                'establishment_email': 'Email de l\'établissement',
                'establishment_type': 'Type d\'établissement',
                'establishment_password': 'Mot de passe provisoire',
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
            
            # Vérification si l'email du directeur existe déjà
            if Etablissement.objects.filter(email=data['teacher_email']).exists():
                errors['teacher_email'] = "Cette adresse email de directeur est déjà utilisée."
                return False, "Cette adresse email de directeur est déjà utilisée.", None, errors
            
            # Vérification si l'email de l'établissement existe déjà
            if Etablissement.objects.filter(email=data['establishment_email']).exists():
                errors['establishment_email'] = "Cette adresse email d'établissement est déjà utilisée."
                return False, "Cette adresse email d'établissement est déjà utilisée.", None, errors
            
            # Validation du mot de passe
            try:
                validate_password(data['establishment_password'])
            except ValidationError as e:
                errors['establishment_password'] = "; ".join(e.messages)
                return False, "Le mot de passe ne respecte pas les critères de sécurité.", None, errors
            
            # Vérification du type d'établissement
            valid_types = ['primary', 'collège', 'lycée']
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
                    pays=data['establishment_country'],
                    ville=data['establishment_city'],
                    email=data['establishment_email'],
                    telephone=data.get('establishment_phone', ''),
                    type_etablissement=data['establishment_type'],
                    directeur_prenom=data['teacher_firstname'],
                    directeur_nom=data['teacher_lastname'],
                    directeur_email=data['teacher_email'],
                    directeur_telephone=data.get('teacher_phone', ''),
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
                
                # Définir le mot de passe pour l'établissement
                etablissement.set_password(data['establishment_password'])
                
                etablissement.save()
                
              
                
                logger.info(f"Établissement créé: {etablissement.nom}")
            
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
        context = {
            'field_errors': {},
            'form_data': {}
        }
        
        if request.method == 'POST':
            # Sauvegarder les données du formulaire pour les réafficher en cas d'erreur
            form_data = {
                'teacher_firstname': request.POST.get('teacher_firstname', ''),
                'teacher_lastname': request.POST.get('teacher_lastname', ''),
                'teacher_email': request.POST.get('teacher_email', ''),
                'teacher_phone': request.POST.get('teacher_phone', ''),
                'establishment_name': request.POST.get('establishment_name', ''),
                'establishment_address': request.POST.get('establishment_address', ''),
                'establishment_email': request.POST.get('establishment_email', ''),
                'establishment_phone': request.POST.get('establishment_phone', ''),
                'establishment_type': request.POST.get('establishment_type', ''),
                'establishment_password': request.POST.get('establishment_password', ''),
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
