"""
Contrôleur pour la gestion des affectations des professeurs
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.core.exceptions import ValidationError
import logging

from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.professeur_model import Professeur
from ..model.classe_model import Classe
from ..model.matiere_model import Matiere
from ..model.affectation_model import AffectationProfesseur

logger = logging.getLogger(__name__)

class AffectationController:
    
    @staticmethod
    @login_required
    def affectation_professeurs(request):
        """
        Page principale d'affectation des professeurs aux classes
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        # Récupérer tous les professeurs avec leurs matières et affectations
        professeurs = Professeur.objects.filter(
            etablissement=etablissement
        ).select_related('matiere_principale').prefetch_related('matieres_secondaires', 'affectations__classe')
        
        # Récupérer toutes les classes
        classes = Classe.objects.filter(etablissement=etablissement).order_by('nom')
        
        # Récupérer toutes les matières
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        # Organiser les professeurs par matière
        professeurs_par_matiere = {}
        for matiere in matieres:
            professeurs_principaux = professeurs.filter(matiere_principale=matiere)
            professeurs_secondaires = professeurs.filter(matieres_secondaires=matiere)
            professeurs_par_matiere[matiere] = {
                'principaux': professeurs_principaux,
                'secondaires': professeurs_secondaires,
                'total': professeurs_principaux.count() + professeurs_secondaires.count()
            }
        
        # Créer les statistiques
        stats = {
            'total_professeurs': professeurs.count(),
            'total_classes': classes.count(),
            'total_matieres': matieres.count(),
            'professeurs_affectes': 0,  # À calculer
        }
        
        # Calculer les affectations existantes
        for professeur in professeurs:
            if professeur.affectations.filter(actif=True).exists():
                stats['professeurs_affectes'] += 1
        
        # Préparer les classes disponibles pour chaque professeur
        professeurs_with_classes = []
        for professeur in professeurs:
            affectations_actives = professeur.affectations.filter(actif=True).values_list('classe_id', flat=True)
            classes_disponibles = classes.exclude(id__in=affectations_actives)
            professeurs_with_classes.append({
                'professeur': professeur,
                'classes_disponibles': classes_disponibles,
                'affectations': professeur.affectations.filter(actif=True)
            })
        
        context = {
            'etablissement': etablissement,
            'professeurs_with_classes': professeurs_with_classes,
            'classes': classes,
            'matieres': matieres,
            'professeurs_par_matiere': professeurs_par_matiere,
            'stats': stats,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/affectation_professeurs.html', context)
    
    @staticmethod
    @login_required
    def affecter_professeur(request):
        """
        Affecter un professeur à une classe
        """
        if request.method == 'POST':
            professeur_id = request.POST.get('professeur_id')
            classe_id = request.POST.get('classe_id')
            action = request.POST.get('action')  # 'add' ou 'remove'
            statut = request.POST.get('statut', 'classique')  # 'principal' ou 'classique'
            
            # Vérifier que l'utilisateur est autorisé
            if isinstance(request.user, Etablissement):
                etablissement = request.user
            else:
                if isinstance(request.user, PersonnelAdministratif):
                    etablissement = request.user.etablissement
                else:
                    messages.error(request, 'Accès non autorisé.')
                    return redirect('affectation:affectation_professeurs')
            
            # Récupérer le professeur et la classe
            try:
                professeur = Professeur.objects.get(id=professeur_id, etablissement=etablissement)
                classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
            except (Professeur.DoesNotExist, Classe.DoesNotExist):
                messages.error(request, 'Professeur ou classe non trouvé.')
                return redirect('affectation:affectation_professeurs')
            
            with transaction.atomic():
                if action == 'add':
                    # Vérifier si l'affectation existe déjà
                    existing_affectation = AffectationProfesseur.objects.filter(
                        professeur=professeur,
                        classe=classe,
                        actif=True
                    ).first()
                    
                    if existing_affectation:
                        messages.warning(request, f"Le professeur {professeur.nom} est déjà affecté à la classe {classe.nom}.")
                    else:
                        try:
                            # Créer la nouvelle affectation
                            AffectationProfesseur.objects.create(
                                professeur=professeur,
                                classe=classe,
                                statut=statut
                            )
                            statut_display = "Professeur Principal" if statut == 'principal' else "Professeur Classique"
                            messages.success(request, f"Professeur {professeur.nom} affecté à la classe {classe.nom} en tant que {statut_display}")
                        except ValidationError as e:
                            # Capturer l'erreur de validation du modèle
                            messages.error(request, str(e))
                            return redirect('affectation:affectation_professeurs')
                        
                elif action == 'remove':
                    # Trouver l'affectation à supprimer
                    affectation = AffectationProfesseur.objects.filter(
                        professeur=professeur,
                        classe=classe,
                        actif=True
                    ).first()
                    
                    if not affectation:
                        messages.warning(request, f"Cette affectation n'existe pas.")
                    else:
                        affectation.actif = False
                        affectation.save()
                        messages.success(request, f"Affectation du professeur {professeur.nom} à la classe {classe.nom} supprimée")
                else:
                    messages.error(request, 'Action invalide.')
                    return redirect('affectation:affectation_professeurs')
            
            return redirect('affectation:affectation_professeurs')
        
        return redirect('affectation:affectation_professeurs')
    
    @staticmethod
    @login_required
    def get_affectations_professeur(request, professeur_id):
        """
        Récupérer les affectations d'un professeur
        """
        try:
            # Vérifier que l'utilisateur est autorisé
            if isinstance(request.user, Etablissement):
                etablissement = request.user
            else:
                if isinstance(request.user, PersonnelAdministratif):
                    etablissement = request.user.etablissement
                else:
                    return JsonResponse({'success': False, 'message': 'Accès non autorisé.'})
            
            professeur = Professeur.objects.get(id=professeur_id, etablissement=etablissement)
            classes = professeur.classes.all().values('id', 'nom')
            
            return JsonResponse({
                'success': True,
                'classes': list(classes)
            })
            
        except Professeur.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Professeur non trouvé.'})
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des affectations: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Une erreur est survenue.'})
