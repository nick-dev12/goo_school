# school_admin/controllers/professeur_controller.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
import logging

from ..model.professeur_model import Professeur
from ..model.etablissement_model import Etablissement

logger = logging.getLogger(__name__)


class ProfesseurController:
    """
    Contrôleur pour gérer les professeurs
    """
    
    @staticmethod
    def generate_numero_employe(etablissement):
        """
        Génère un numéro d'employé unique pour un professeur
        """
        code_etab = etablissement.code_etablissement[:3]
        
        # Générer un numéro séquentiel
        count = Professeur.objects.filter(
            etablissement=etablissement
        ).count() + 1
        
        numero = f"PROF-{code_etab}-{count:03d}"
        
        # Vérifier l'unicité
        while Professeur.objects.filter(numero_employe=numero).exists():
            count += 1
            numero = f"PROF-{code_etab}-{count:03d}"
        
        return numero
    
    @staticmethod
    @login_required
    def liste_professeurs(request):
        """
        Affiche la liste des professeurs de l'établissement
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        # Récupérer les professeurs de l'établissement
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
        
        # Statistiques
        stats = {
            'total': professeurs.count(),
            'actifs': professeurs.filter(actif=True).count(),
            'inactifs': professeurs.filter(actif=False).count(),
            'par_niveau': {}
        }
        
        # Compter par niveau
        for niveau, label in Professeur.NIVEAU_CHOICES:
            count = professeurs.filter(niveau_enseignement=niveau).count()
            if count > 0:
                stats['par_niveau'][label] = count
        
        context = {
            'professeurs': professeurs,
            'matieres_avec_compteurs': matieres_avec_compteurs,
            'etablissement': etablissement,
            'stats': stats,
        }
        
        return render(request, 'school_admin/directeur/personnel/professeurs/liste_professeurs.html', context)
    
    @staticmethod
    @login_required
    def ajouter_professeur(request):
        """
        Affiche le formulaire d'ajout de professeur et traite la soumission
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        form_data = {}
        field_errors = {}
        is_valid = True  # Initialiser is_valid
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'matiere_principale': request.POST.get('matiere_principale', ''),
                'niveau_enseignement': request.POST.get('niveau_enseignement', ''),
                'password': request.POST.get('password', ''),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            required_fields = ['nom', 'prenom', 'email', 'telephone', 'matiere_principale', 'niveau_enseignement', 'password']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation de la matière
            matiere_principale_obj = None
            if form_data['matiere_principale']:
                try:
                    from ..model.matiere_model import Matiere
                    matiere_principale_obj = Matiere.objects.get(id=form_data['matiere_principale'], etablissement=etablissement)
                except Matiere.DoesNotExist:
                    field_errors['matiere_principale'] = "La matière sélectionnée n'existe pas."
                    is_valid = False
            
            # Validation de l'email
            if form_data['email'] and '@' not in form_data['email']:
                field_errors['email'] = "L'adresse email n'est pas valide."
                is_valid = False
            
            # Vérification de l'unicité de l'email
            if form_data['email'] and Professeur.objects.filter(email=form_data['email']).exists():
                field_errors['email'] = "Cette adresse email est déjà utilisée."
                is_valid = False
            
            # Validation des mots de passe
            if form_data['password'] and len(form_data['password']) < 8:
                field_errors['password'] = "Le mot de passe doit contenir au moins 8 caractères."
                is_valid = False
            
            
            # Si tout est valide, créer le professeur
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer le numéro d'employé
                        numero_employe = ProfesseurController.generate_numero_employe(etablissement)
                        
                        # Créer le professeur
                        professeur = Professeur(
                            nom=form_data['nom'],
                            prenom=form_data['prenom'],
                            email=form_data['email'],
                            telephone=form_data['telephone'],
                            matiere_principale=matiere_principale_obj,
                            niveau_enseignement=form_data['niveau_enseignement'],
                            username=form_data['email'],
                            numero_employe=numero_employe,
                            etablissement=etablissement,
                        )
                        
                        # Définir le mot de passe
                        professeur.set_password(form_data['password'])
                        professeur.save()
                        
                        messages.success(request, f"Le professeur {professeur.nom_complet} a été ajouté avec succès !")
                        return redirect('professeur:liste_professeurs')
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout du professeur: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de l'ajout du professeur."
                    is_valid = False
        
        # Debug: afficher les erreurs
        print(f"DEBUG - field_errors: {field_errors}")
        print(f"DEBUG - is_valid: {is_valid}")
        
        # Récupérer les matières de l'établissement
        from ..model.matiere_model import Matiere
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'matieres': matieres,
            'niveau_choices': Professeur.NIVEAU_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/personnel/professeurs/ajouter_professeur.html', context)
    
    @staticmethod
    @login_required
    def detail_professeur(request, professeur_id):
        """
        Affiche les détails d'un professeur
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        try:
            professeur = Professeur.objects.get(
                id=professeur_id,
                etablissement=etablissement
            )
        except Professeur.DoesNotExist:
            messages.error(request, "Professeur non trouvé.")
            return redirect('professeur:liste_professeurs')
        
        context = {
            'professeur': professeur,
            'etablissement': etablissement,
        }
        
        return render(request, 'school_admin/directeur/personnel/professeurs/detail_professeur.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, professeur_id):
        """
        Active/désactive un professeur
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        try:
            professeur = Professeur.objects.get(
                id=professeur_id,
                etablissement=etablissement
            )
            
            professeur.actif = not professeur.actif
            professeur.save()
            
            status = "activé" if professeur.actif else "désactivé"
            messages.success(request, f"{professeur.nom_complet} a été {status}.")
            
        except Professeur.DoesNotExist:
            messages.error(request, "Professeur non trouvé.")
        
        return redirect('professeur:liste_professeurs')
