# school_admin/controllers/classe_controller.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
import logging
import random
import string

from ..model.classe_model import Classe
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.etablissement_model import Etablissement

logger = logging.getLogger(__name__)


class ClasseController:
    """
    Contrôleur pour gérer les classes d'un établissement
    """
    
    @staticmethod
    def generate_code_classe(nom, niveau, etablissement):
        """
        Génère un code de classe unique basé sur le nom, niveau et établissement
        """
        # Préfixes selon le niveau
        prefixes = {
            'maternelle': 'MAT',
            'primaire': 'PRI',
            'college': 'COL',
            'lycee': 'LYC',
            'superieur': 'SUP',
        }
        
        prefix = prefixes.get(niveau, 'CLS')
        code_etab = etablissement.code_etablissement[:3]  # 3 premiers caractères du code établissement
        
        # Nettoyer le nom de la classe
        nom_clean = ''.join(c for c in nom if c.isalnum())[:3].upper()
        
        # Générer un numéro séquentiel
        count = Classe.objects.filter(
            etablissement=etablissement,
            niveau=niveau
        ).count() + 1
        
        code = f"{prefix}-{code_etab}-{nom_clean}-{count:02d}"
        
        # Vérifier l'unicité
        while Classe.objects.filter(code_classe=code).exists():
            count += 1
            code = f"{prefix}-{code_etab}-{nom_clean}-{count:02d}"
        
        return code
    
    @staticmethod
    @login_required
    def liste_classes(request):
        """
        Affiche la liste des classes de l'établissement
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, PersonnelAdministratif):
            personnel = request.user
            etablissement = personnel.etablissement
        elif isinstance(request.user, Etablissement):
            personnel = None
            etablissement = request.user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        # Récupérer les classes de l'établissement avec les affectations
        classes = Classe.objects.filter(
            etablissement=etablissement
        ).prefetch_related('affectations__professeur').order_by('niveau', 'nom')
        
        # Ajouter le nombre d'enseignants affectés à chaque classe
        classes_with_teachers = []
        for classe in classes:
            classe_data = {
                'classe': classe,
                'nombre_enseignants': classe.affectations.filter(actif=True).count(),
                'enseignants': classe.affectations.filter(actif=True).select_related('professeur')
            }
            classes_with_teachers.append(classe_data)
        
        # Regrouper les classes par catégorie (niveau + préfixe)
        import re
        classes_grouped = {}
        
        for classe_data in classes_with_teachers:
            classe = classe_data['classe']
            
            # Extraire la catégorie (ex: "6ème" de "6ème A", "6ème B", etc.)
            nom = classe.nom
            # Pattern pour extraire le niveau et la lettre/section
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
            
            if match:
                categorie = match.group(1)  # "6ème", "5ème", "Terminale", etc.
                section = match.group(2)    # "A", "B", "C", "1", "2", etc.
            else:
                # Si pas de pattern trouvé, utiliser le nom complet comme catégorie
                categorie = nom
                section = ""
            
            if categorie not in classes_grouped:
                classes_grouped[categorie] = {
                    'niveau': classe.niveau,
                    'classes': [],
                    'total_eleves': 0,
                    'total_enseignants': 0,
                    'total_capacite': 0
                }
            
            classes_grouped[categorie]['classes'].append(classe_data)
            classes_grouped[categorie]['total_eleves'] += classe.nombre_eleves
            classes_grouped[categorie]['total_enseignants'] += classe_data['nombre_enseignants']
            classes_grouped[categorie]['total_capacite'] += classe.capacite_max
        
        # Statistiques
        stats = {
            'total': classes.count(),
            'actives': classes.filter(actif=True).count(),
            'inactives': classes.filter(actif=False).count(),
            'par_niveau': {},
            'total_enseignants_affectes': sum(classe_data['nombre_enseignants'] for classe_data in classes_with_teachers)
        }
        
        # Compter par niveau
        for niveau, label in Classe.NIVEAU_CHOICES:
            count = classes.filter(niveau=niveau).count()
            if count > 0:
                stats['par_niveau'][label] = count
        
        context = {
            'classes': classes,
            'classes_with_teachers': classes_with_teachers,
            'classes_grouped': classes_grouped,
            'etablissement': etablissement,
            'personnel': personnel,
            'stats': stats,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/classes/liste_classes.html', context)
    
    @staticmethod
    @login_required
    def ajouter_classe(request):
        """
        Affiche le formulaire d'ajout de classe et traite la soumission
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, PersonnelAdministratif):
            personnel = request.user
            etablissement = personnel.etablissement
        elif isinstance(request.user, Etablissement):
            personnel = None
            etablissement = request.user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        form_data = {}
        field_errors = {}
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'niveau': request.POST.get('niveau', ''),
                'capacite_max': request.POST.get('capacite_max', ''),
                'description': request.POST.get('description', '').strip(),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            required_fields = ['nom', 'niveau', 'capacite_max']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation de la capacité
            try:
                capacite = int(form_data['capacite_max'])
                if capacite <= 0:
                    field_errors['capacite_max'] = "La capacité doit être supérieure à 0."
                    is_valid = False
                elif capacite > 100:
                    field_errors['capacite_max'] = "La capacité ne peut pas dépasser 100."
                    is_valid = False
            except ValueError:
                field_errors['capacite_max'] = "La capacité doit être un nombre valide."
                is_valid = False
            
            # Validation du niveau
            valid_niveaux = [choice[0] for choice in Classe.NIVEAU_CHOICES]
            if form_data['niveau'] not in valid_niveaux:
                field_errors['niveau'] = "Le niveau sélectionné n'est pas valide."
                is_valid = False
            
            # Vérification de l'unicité du nom dans l'établissement
            if form_data['nom'] and Classe.objects.filter(
                nom=form_data['nom'],
                etablissement=etablissement
            ).exists():
                field_errors['nom'] = "Une classe avec ce nom existe déjà dans cet établissement."
                is_valid = False
            
            # Si tout est valide, créer la classe
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer le code de classe
                        code_classe = ClasseController.generate_code_classe(
                            form_data['nom'],
                            form_data['niveau'],
                            etablissement
                        )
                        
                        # Créer la classe
                        classe = Classe(
                            nom=form_data['nom'],
                            niveau=form_data['niveau'],
                            code_classe=code_classe,
                            capacite_max=int(form_data['capacite_max']),
                            description=form_data['description'] if form_data['description'] else None,
                            etablissement=etablissement,
                        )
                        
                        classe.save()
                        
                        messages.success(request, f"La classe {classe.nom_complet} a été ajoutée avec succès !")
                        return redirect('administrateur_etablissement:liste_classes')
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout de la classe: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de l'ajout de la classe."
                    is_valid = False
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'etablissement': etablissement,
            'personnel': personnel,
            'niveau_choices': Classe.NIVEAU_CHOICES,
        }
        
        # Si c'est une requête POST avec des erreurs, afficher la liste avec le modal ouvert
        if request.method == 'POST' and field_errors:
            # Récupérer les classes pour la liste
            classes = Classe.objects.filter(
                etablissement=etablissement
            ).order_by('niveau', 'nom')
            
            # Statistiques
            stats = {
                'total': classes.count(),
                'actives': classes.filter(actif=True).count(),
                'inactives': classes.filter(actif=False).count(),
                'par_niveau': {}
            }
            
            # Compter par niveau
            for niveau, label in Classe.NIVEAU_CHOICES:
                count = classes.filter(niveau=niveau).count()
                if count > 0:
                    stats['par_niveau'][label] = count
            
            context.update({
                'classes': classes,
                'stats': stats,
                'show_modal': True,  # Flag pour ouvrir le modal
            })
            
            return render(request, 'school_admin/directeur/administrateur_etablissement/classes/liste_classes.html', context)
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/classes/ajouter_classe.html', context)
    
    @staticmethod
    @login_required
    def detail_classe(request, classe_id):
        """
        Affiche les détails d'une classe
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, PersonnelAdministratif):
            personnel = request.user
            etablissement = personnel.etablissement
        elif isinstance(request.user, Etablissement):
            personnel = None
            etablissement = request.user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            classe = Classe.objects.get(
                id=classe_id,
                etablissement=etablissement
            )
        except Classe.DoesNotExist:
            messages.error(request, "Classe non trouvée.")
            return redirect('administrateur_etablissement:liste_classes')
        
        # Récupérer les affectations des enseignants
        affectations = classe.affectations.filter(actif=True).select_related('professeur', 'professeur__matiere_principale')
        
        # Organiser les enseignants par statut
        enseignants_principaux = affectations.filter(statut='principal')
        enseignants_classiques = affectations.filter(statut='classique')
        
        # Récupérer les élèves de la classe
        from ..model.eleve_model import Eleve
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('prenom', 'nom')
        
        # Statistiques des élèves
        stats_eleves = {
            'total': eleves.count(),
            'masculin': eleves.filter(sexe='M').count(),
            'feminin': eleves.filter(sexe='F').count(),
            'nouveaux': eleves.filter(statut='nouvelle').count(),
            'transferts': eleves.filter(statut='transfert').count(),
            'reinscriptions': eleves.filter(statut='reinscription').count(),
        }
        
        context = {
            'classe': classe,
            'etablissement': etablissement,
            'personnel': personnel,
            'affectations': affectations,
            'enseignants_principaux': enseignants_principaux,
            'enseignants_classiques': enseignants_classiques,
            'nombre_enseignants': affectations.count(),
            'eleves': eleves,
            'stats_eleves': stats_eleves,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/classes/detail_classe.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, classe_id):
        """
        Active/désactive une classe
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, PersonnelAdministratif):
            etablissement = request.user.etablissement
        elif isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            classe = Classe.objects.get(
                id=classe_id,
                etablissement=etablissement
            )
            
            classe.actif = not classe.actif
            classe.save()
            
            status = "activée" if classe.actif else "désactivée"
            messages.success(request, f"La classe {classe.nom_complet} a été {status}.")
            
        except Classe.DoesNotExist:
            messages.error(request, "Classe non trouvée.")
        
        return redirect('administrateur_etablissement:liste_classes')
