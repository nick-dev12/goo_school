# school_admin/controllers/personnel_controller.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
import logging
import random
import string

from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.etablissement_model import Etablissement

logger = logging.getLogger(__name__)


class PersonnelController:
    """
    Contrôleur pour gérer le personnel administratif
    """
    
    @staticmethod
    def generate_numero_employe(fonction, etablissement):
        """
        Génère un numéro d'employé unique basé sur le rôle et l'établissement
        """
        # Préfixes selon le rôle
        prefixes = {
            'secretaire': 'SEC',
            'surveillant_general': 'SG',
            'censeur': 'CEN',
            'administrateur': 'ADM',
        }
        
        prefix = prefixes.get(fonction, 'EMP')
        code_etab = etablissement.code_etablissement[:3]  # 3 premiers caractères du code établissement
        
        # Générer un numéro séquentiel
        count = PersonnelAdministratif.objects.filter(
            etablissement=etablissement,
            fonction=fonction
        ).count() + 1
        
        numero = f"{prefix}-{code_etab}-{count:03d}"
        
        # Vérifier l'unicité
        while PersonnelAdministratif.objects.filter(numero_employe=numero).exists():
            count += 1
            numero = f"{prefix}-{code_etab}-{count:03d}"
        
        return numero
    
    @staticmethod
    def generate_username(nom, prenom, etablissement):
        """
        Génère un nom d'utilisateur unique
        """
        # Créer un username basé sur le prénom et nom
        base_username = f"{prenom.lower()}.{nom.lower()}"
        username = base_username
        
        # Vérifier l'unicité et ajouter un suffixe si nécessaire
        counter = 1
        while PersonnelAdministratif.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        return username
    
    @staticmethod
    @login_required
    def liste_personnel(request):
        """
        Affiche la liste du personnel administratif et des professeurs de l'établissement
        """
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = request.user
        
        # Récupérer le personnel administratif de l'établissement
        personnel = PersonnelAdministratif.objects.filter(
            etablissement=etablissement
        ).order_by('-date_creation')
        
        # Récupérer les professeurs de l'établissement
        from ..model.professeur_model import Professeur
        professeurs = Professeur.objects.filter(
            etablissement=etablissement
        ).select_related('matiere_principale').order_by('-date_creation')
        
        # Récupérer les matières avec le nombre de professeurs
        from ..model.matiere_model import Matiere
        matieres_avec_compteurs = []
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        for matiere in matieres:
            count = professeurs.filter(matiere_principale=matiere).count()
            matieres_avec_compteurs.append({
                'matiere': matiere,
                'count': count,
                'professeurs': professeurs.filter(matiere_principale=matiere)
            })
        
        # Statistiques générales
        stats = {
            'total_personnel': personnel.count(),
            'total_professeurs': professeurs.count(),
            'total_actifs': personnel.filter(actif=True).count() + professeurs.filter(actif=True).count(),
            'total_inactifs': personnel.filter(actif=False).count() + professeurs.filter(actif=False).count(),
            'par_role': {}
        }
        
        # Compter par rôle pour le personnel administratif
        for fonction, label in PersonnelAdministratif.TYPE_FONCTION_CHOICES:
            count = personnel.filter(fonction=fonction).count()
            if count > 0:
                stats['par_role'][label] = count
        
        # Ajouter les professeurs aux statistiques
        if professeurs.count() > 0:
            stats['par_role']['Professeurs'] = professeurs.count()
        
        context = {
            'personnel': personnel,
            'professeurs': professeurs,
            'matieres_avec_compteurs': matieres_avec_compteurs,
            'etablissement': etablissement,
            'stats': stats,
        }
        
        return render(request, 'school_admin/directeur/personnel/liste_personnel.html', context)
    
    @staticmethod
    @login_required
    def ajouter_personnel(request):
        """
        Affiche le formulaire d'ajout de personnel et traite la soumission
        """
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = request.user
        form_data = {}
        field_errors = {}
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'fonction': request.POST.get('fonction', ''),
                'password': request.POST.get('password', ''),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            required_fields = ['nom', 'prenom', 'email', 'telephone', 'fonction', 'password']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation de l'email
            if form_data['email'] and '@' not in form_data['email']:
                field_errors['email'] = "L'adresse email n'est pas valide."
                is_valid = False
            
            # Vérification de l'unicité de l'email
            if form_data['email'] and PersonnelAdministratif.objects.filter(email=form_data['email']).exists():
                field_errors['email'] = "Cette adresse email est déjà utilisée."
                is_valid = False
            
            # Validation des mots de passe
            if form_data['password'] and len(form_data['password']) < 8:
                field_errors['password'] = "Le mot de passe doit contenir au moins 8 caractères."
                is_valid = False
            
            # Validation du type de personnel
            valid_types = [choice[0] for choice in PersonnelAdministratif.TYPE_FONCTION_CHOICES]
            if form_data['fonction'] not in valid_types:
                field_errors['fonction'] = "Le type de fonction sélectionné n'est pas valide."
                is_valid = False
            
            # Si tout est valide, créer le personnel
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer le username et numéro d'employé
                        username = form_data['email']
                        numero_employe = PersonnelController.generate_numero_employe(
                            form_data['fonction'], 
                            etablissement
                        )
                        
                        # Créer le personnel
                        personnel = PersonnelAdministratif(
                            nom=form_data['nom'],
                            prenom=form_data['prenom'],
                            email=form_data['email'],
                            telephone=form_data['telephone'],
                            fonction=form_data['fonction'],
                            username=username,
                            numero_employe=numero_employe,
                            etablissement=etablissement,
                        )
                        
                        # Définir le mot de passe
                        personnel.set_password(form_data['password'])
                        personnel.save()
                        
                        messages.success(request, f"Le personnel {personnel.nom_complet} a été ajouté avec succès !")
                        return redirect('personnel:liste_personnel')
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout du personnel: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de l'ajout du personnel."
                    is_valid = False
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'etablissement': etablissement,
            'type_choices': PersonnelAdministratif.TYPE_FONCTION_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/personnel/ajouter_personnel.html', context)
    
    @staticmethod
    @login_required
    def detail_personnel(request, personnel_id):
        """
        Affiche les détails d'un membre du personnel
        """
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            personnel = PersonnelAdministratif.objects.get(
                id=personnel_id,
                etablissement=request.user
            )
        except PersonnelAdministratif.DoesNotExist:
            messages.error(request, "Personnel non trouvé.")
            return redirect('personnel:liste_personnel')
        
        context = {
            'personnel': personnel,
            'etablissement': request.user,
        }
        
        return render(request, 'school_admin/directeur/personnel/detail_personnel.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, personnel_id):
        """
        Active/désactive un membre du personnel
        """
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            personnel = PersonnelAdministratif.objects.get(
                id=personnel_id,
                etablissement=request.user
            )
            
            personnel.actif = not personnel.actif
            personnel.save()
            
            status = "activé" if personnel.actif else "désactivé"
            messages.success(request, f"{personnel.nom_complet} a été {status}.")
            
        except PersonnelAdministratif.DoesNotExist:
            messages.error(request, "Personnel non trouvé.")
        
        return redirect('personnel:liste_personnel')
