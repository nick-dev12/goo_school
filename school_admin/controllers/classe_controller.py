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
        # Vérifier que l'utilisateur est du personnel administratif
        if not isinstance(request.user, PersonnelAdministratif):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        personnel = request.user
        etablissement = personnel.etablissement
        
        # Récupérer les classes de l'établissement
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
        
        context = {
            'classes': classes,
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
        # Vérifier que l'utilisateur est du personnel administratif
        if not isinstance(request.user, PersonnelAdministratif):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        personnel = request.user
        etablissement = personnel.etablissement
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
        # Vérifier que l'utilisateur est du personnel administratif
        if not isinstance(request.user, PersonnelAdministratif):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            classe = Classe.objects.get(
                id=classe_id,
                etablissement=request.user.etablissement
            )
        except Classe.DoesNotExist:
            messages.error(request, "Classe non trouvée.")
            return redirect('administrateur_etablissement:liste_classes')
        
        context = {
            'classe': classe,
            'etablissement': request.user.etablissement,
            'personnel': request.user,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/classes/detail_classe.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, classe_id):
        """
        Active/désactive une classe
        """
        # Vérifier que l'utilisateur est du personnel administratif
        if not isinstance(request.user, PersonnelAdministratif):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            classe = Classe.objects.get(
                id=classe_id,
                etablissement=request.user.etablissement
            )
            
            classe.actif = not classe.actif
            classe.save()
            
            status = "activée" if classe.actif else "désactivée"
            messages.success(request, f"La classe {classe.nom_complet} a été {status}.")
            
        except Classe.DoesNotExist:
            messages.error(request, "Classe non trouvée.")
        
        return redirect('administrateur_etablissement:liste_classes')
