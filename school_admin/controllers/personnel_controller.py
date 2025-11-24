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
    def categoriser_personnel(personnel_queryset):
        """
        Catégorise le personnel par type de fonction
        """
        categories = {
            'direction': {'label': 'Direction', 'icon': 'fa-user-tie', 'personnel': []},
            'censeurs': {'label': 'Censeurs', 'icon': 'fa-chalkboard-teacher', 'personnel': []},
            'surveillants': {'label': 'Surveillants', 'icon': 'fa-eye', 'personnel': []},
            'administration': {'label': 'Administration', 'icon': 'fa-briefcase', 'personnel': []},
            'autres': {'label': 'Autres', 'icon': 'fa-users-cog', 'personnel': []},
        }
        
        # Fonctions par catégorie
        fonctions_direction = [
            'directeur_adjoint_primaire', 'principal_adjoint',
            'proviseur_adjoint', 'directeur_principal',
            'directeur_section_primaire', 'principal_section_college', 'proviseur_section_lycee'
        ]
        
        fonctions_censeurs = [
            'censeur', 'censeur_etudes', 'censeur_adjoint',
            'censeur_premier_cycle', 'censeur_second_cycle',
            'censeur_pedagogie', 'censeur_vie_scolaire'
        ]
        
        fonctions_surveillants = [
            'surveillant_general'
        ]
        
        fonctions_administration = [
            'secretaire_principal', 'gestionnaire', 'secretaire_vie_scolaire'
        ]
        
        # Catégoriser chaque personnel
        for personnel in personnel_queryset:
            if personnel.fonction in fonctions_direction:
                categories['direction']['personnel'].append(personnel)
            elif personnel.fonction in fonctions_censeurs:
                categories['censeurs']['personnel'].append(personnel)
            elif personnel.fonction in fonctions_surveillants:
                categories['surveillants']['personnel'].append(personnel)
            elif personnel.fonction in fonctions_administration:
                categories['administration']['personnel'].append(personnel)
            else:
                categories['autres']['personnel'].append(personnel)
        
        return categories
    
    @staticmethod
    def get_fonctions_par_type_etablissement(type_etablissement):
        """
        Retourne les fonctions disponibles selon le type d'établissement
        """
        fonctions = {
            'primary': [
                ('directeur_adjoint_primaire', 'Directeur Adjoint (École Primaire)'),
                ('secretaire_principal', 'Secrétaire Principal'),
                ('gestionnaire', 'Gestionnaire'),
                ('surveillant_general', 'Surveillant Général'),
            ],
            'collège': [
                ('principal_adjoint', 'Principal Adjoint (Collège)'),
                ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
                ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
                ('censeur_premier_cycle', 'Censeur du Premier Cycle (6e à 3e)'),
                ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
                ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
                ('surveillant_general', 'Surveillant Général'),
                ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
            ],
            'lycée': [
                ('proviseur_adjoint', 'Proviseur Adjoint (Lycée)'),
                ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
                ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
                ('censeur_second_cycle', 'Censeur du Second Cycle (2nde à Tle)'),
                ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
                ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
                ('surveillant_general', 'Surveillant Général'),
                ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
            ],
            'collège_lycée': [
                # Direction
                ('principal_adjoint', 'Principal Adjoint (Collège)'),
                ('proviseur_adjoint', 'Proviseur Adjoint (Lycée)'),
                # Administration
                ('secretaire_principal', 'Secrétaire Principal'),
                # Pédagogie - Censeurs
                ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
                ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
                ('censeur_premier_cycle', 'Censeur du Premier Cycle (6e à 3e)'),
                ('censeur_second_cycle', 'Censeur du Second Cycle (2nde à Tle)'),
                ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
                ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
                # Vie Scolaire
                ('surveillant_general', 'Surveillant Général'),
                ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
            ],
            'mixte': [
                # Direction générale
                ('directeur_principal', 'Directeur Principal (Établissement Mixte)'),
                ('directeur_section_primaire', 'Directeur de Section Primaire'),
                ('principal_section_college', 'Principal de Section Collège'),
                ('proviseur_section_lycee', 'Proviseur de Section Lycée'),
                # Direction spécifiques
                ('directeur_adjoint_primaire', 'Directeur Adjoint (École Primaire)'),
                ('principal_adjoint', 'Principal Adjoint (Collège)'),
                ('proviseur_adjoint', 'Proviseur Adjoint (Lycée)'),
                # Administration
                ('secretaire_principal', 'Secrétaire Principal'),
                ('gestionnaire', 'Gestionnaire'),
                # Pédagogie - Censeurs
                ('censeur', 'Censeur'),
                ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
                ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
                ('censeur_premier_cycle', 'Censeur du Premier Cycle (6e à 3e)'),
                ('censeur_second_cycle', 'Censeur du Second Cycle (2nde à Tle)'),
                ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
                ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
                # Vie Scolaire
                ('surveillant_general', 'Surveillant Général'),
                ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
            ],
        }
        
        # Ajouter l'administrateur système à tous les types
        for type_etab in fonctions:
            fonctions[type_etab].append(('administrateur', 'Administrateur Système'))
        
        return fonctions.get(type_etablissement, [])
    
    @staticmethod
    def generate_mot_de_passe_provisoire():
        """
        Génère un mot de passe provisoire de 6 chiffres
        """
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    @staticmethod
    def generate_numero_employe(fonction, etablissement):
        """
        Génère un numéro d'employé unique basé sur le rôle et l'établissement
        """
        # Préfixes selon le rôle
        prefixes = {
            # Direction
            'directeur_adjoint_primaire': 'DIR-ADJ',
            'principal_adjoint': 'PRI-ADJ',
            'proviseur_adjoint': 'PROV-ADJ',
            'directeur_principal': 'DIR-P',
            'directeur_section_primaire': 'DIR-SEC',
            'principal_section_college': 'PRI-SEC',
            'proviseur_section_lycee': 'PROV-SEC',
            # Administration
            'secretaire_principal': 'SEC-P',
            'gestionnaire': 'GES',
            # Pédagogie
            'censeur': 'CEN',
            'censeur_etudes': 'CEN-ET',
            'censeur_adjoint': 'CEN-ADJ',
            'censeur_premier_cycle': 'CEN-C1',
            'censeur_second_cycle': 'CEN-C2',
            'censeur_pedagogie': 'CEN-PED',
            'censeur_vie_scolaire': 'CEN-VS',
            # Vie Scolaire
            'surveillant_general': 'SG',
            'secretaire_vie_scolaire': 'SEC-VS',
            # Autres
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
        
        # Catégoriser le personnel
        categories_personnel = PersonnelController.categoriser_personnel(personnel)
        
        # Récupérer les professeurs de l'établissement
        from ..model.professeur_model import Professeur
        from django.db.models.functions import Lower
        professeurs = Professeur.objects.filter(
            etablissement=etablissement
        ).select_related('matiere_principale').order_by(Lower('nom'), Lower('prenom'))
        
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
            'categories_personnel': categories_personnel,
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
            }
            
            # Validation
            is_valid = True
            
            # Récupérer les fonctions valides pour ce type d'établissement
            fonctions_valides = PersonnelController.get_fonctions_par_type_etablissement(
                etablissement.type_etablissement
            )
            fonctions_valides_codes = [f[0] for f in fonctions_valides]
            
            # Champs obligatoires
            required_fields = ['nom', 'prenom', 'email', 'telephone', 'fonction']
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
            
            # Validation du type de personnel selon le type d'établissement
            if form_data['fonction'] and form_data['fonction'] not in fonctions_valides_codes:
                field_errors['fonction'] = f"Cette fonction n'est pas disponible pour un établissement de type {etablissement.get_type_etablissement_display()}."
                is_valid = False
            
            # Si tout est valide, créer le personnel
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer le username, numéro d'employé et mot de passe
                        username = form_data['email']
                        numero_employe = PersonnelController.generate_numero_employe(
                            form_data['fonction'], 
                            etablissement
                        )
                        mot_de_passe = PersonnelController.generate_mot_de_passe_provisoire()
                        
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
                            mot_de_passe_provisoire=mot_de_passe,
                        )
                        
                        # Définir le mot de passe (haché)
                        personnel.set_password(mot_de_passe)
                        personnel.save()
                        
                        messages.success(
                            request, 
                            f"Le personnel {personnel.nom_complet} a été ajouté avec succès ! Mot de passe provisoire : {mot_de_passe}"
                        )
                        return redirect('personnel:liste_personnel')
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout du personnel: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de l'ajout du personnel."
                    is_valid = False
        
        # Récupérer les fonctions disponibles selon le type d'établissement
        fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(
            etablissement.type_etablissement
        )
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'etablissement': etablissement,
            'fonctions_disponibles': fonctions_disponibles,
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
