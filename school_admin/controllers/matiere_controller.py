from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Count, Q
import logging

from ..model.matiere_model import Matiere
from ..model.etablissement_model import Etablissement
from ..model.classe_model import Classe

logger = logging.getLogger(__name__)


class MatiereController:
    """
    Contrôleur pour la gestion des matières
    """
    
    @staticmethod
    @login_required
    def liste_matieres(request):
        """
        Affiche la liste des matières avec possibilité d'ajout
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
        
        # Récupérer les matières
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        # Récupérer les classes pour le formulaire
        classes = Classe.objects.filter(etablissement=etablissement).order_by('nom')
        
        # Statistiques
        stats = {
            'total': matieres.count(),
            'actives': matieres.filter(actif=True).count(),
            'inactives': matieres.filter(actif=False).count(),
            'par_type': {},
            'par_niveau': {},
        }
        
        # Compter par type
        for type_matiere, label in Matiere.TYPE_MATIERE_CHOICES:
            count = matieres.filter(type_matiere=type_matiere).count()
            if count > 0:
                stats['par_type'][label] = count
        
        # Compter par niveau
        for niveau, label in Matiere.NIVEAU_CHOICES:
            count = matieres.filter(niveau=niveau).count()
            if count > 0:
                stats['par_niveau'][label] = count
        
        context = {
            'matieres': matieres,
            'classes': classes,
            'etablissement': etablissement,
            'stats': stats,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'niveau_choices': Matiere.NIVEAU_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/liste_matieres.html', context)
    
    @staticmethod
    @login_required
    def ajouter_matiere(request):
        """
        Affiche le formulaire d'ajout de matière et traite la soumission
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
        is_valid = True
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'type_matiere': request.POST.get('type_matiere', ''),
                'niveau': request.POST.get('niveau', ''),
                'coefficient': request.POST.get('coefficient', '1.0'),
                'classes': request.POST.getlist('classes', []),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            required_fields = ['nom', 'type_matiere', 'niveau']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation du nom
            if form_data['nom'] and len(form_data['nom']) < 2:
                field_errors['nom'] = "Le nom de la matière doit contenir au moins 2 caractères."
                is_valid = False
            
            # Vérification de l'unicité du nom
            if form_data['nom'] and Matiere.objects.filter(
                nom__iexact=form_data['nom'], 
                etablissement=etablissement
            ).exists():
                field_errors['nom'] = "Cette matière existe déjà dans cet établissement."
                is_valid = False
            
            
            # Validation du coefficient
            try:
                coefficient = float(form_data['coefficient'])
                if coefficient < 0 or coefficient > 10:
                    field_errors['coefficient'] = "Le coefficient doit être entre 0 et 10."
                    is_valid = False
            except ValueError:
                field_errors['coefficient'] = "Le coefficient doit être un nombre valide."
                is_valid = False
            
            
            # Si tout est valide, créer la matière
            if is_valid:
                try:
                    with transaction.atomic():
                        # Créer la matière
                        matiere = Matiere(
                            nom=form_data['nom'],
                            code=form_data['nom'][:3].upper(),
                            type_matiere=form_data['type_matiere'],
                            niveau=form_data['niveau'],
                            coefficient=float(form_data['coefficient']),
                            etablissement=etablissement,
                        )
                        matiere.save()
                        
                        # Assigner les classes
                        if form_data['classes']:
                            classes_ids = [int(id) for id in form_data['classes'] if id.isdigit()]
                            classes = Classe.objects.filter(id__in=classes_ids, etablissement=etablissement)
                            matiere.classes.set(classes)
                        
                        messages.success(request, f"La matière '{matiere.nom_complet}' a été ajoutée avec succès !")
                        return redirect('matiere:liste_matieres')
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout de la matière: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de l'ajout de la matière."
                    is_valid = False
        
        # Récupérer les classes pour le formulaire
        classes = Classe.objects.filter(etablissement=etablissement).order_by('nom')
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'classes': classes,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'niveau_choices': Matiere.NIVEAU_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/liste_matieres.html', context)
    
    @staticmethod
    @login_required
    def detail_matiere(request, matiere_id):
        """
        Affiche les détails d'une matière avec possibilité de modification
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
            matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
            return redirect('matiere:liste_matieres')
        
        # Récupérer les professeurs associés à cette matière
        from ..model.professeur_model import Professeur
        professeurs_principaux = Professeur.objects.filter(
            matiere_principale=matiere,
            etablissement=etablissement
        ).select_related('matiere_principale')
        
        professeurs_secondaires = Professeur.objects.filter(
            matieres_secondaires=matiere,
            etablissement=etablissement
        ).select_related('matiere_principale')
        
        # Récupérer les classes associées
        classes_associees = matiere.classes.all().order_by('nom')
        
        # Récupérer toutes les classes pour le formulaire de modification
        toutes_classes = Classe.objects.filter(etablissement=etablissement).order_by('nom')
        
        # Données du formulaire de modification
        form_data = {}
        field_errors = {}
        is_valid = True
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'type_matiere': request.POST.get('type_matiere', ''),
                'niveau': request.POST.get('niveau', ''),
                'coefficient': request.POST.get('coefficient', '1.0'),
                'classes': request.POST.getlist('classes', []),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            required_fields = ['nom', 'type_matiere', 'niveau']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation du nom
            if form_data['nom'] and len(form_data['nom']) < 2:
                field_errors['nom'] = "Le nom de la matière doit contenir au moins 2 caractères."
                is_valid = False
            
            # Vérification de l'unicité du nom (sauf pour la matière actuelle)
            if form_data['nom'] and Matiere.objects.filter(
                nom__iexact=form_data['nom'], 
                etablissement=etablissement
            ).exclude(id=matiere.id).exists():
                field_errors['nom'] = "Cette matière existe déjà dans cet établissement."
                is_valid = False
            
            # Validation du coefficient
            try:
                coefficient = float(form_data['coefficient'])
                if coefficient < 0 or coefficient > 10:
                    field_errors['coefficient'] = "Le coefficient doit être entre 0 et 10."
                    is_valid = False
            except ValueError:
                field_errors['coefficient'] = "Le coefficient doit être un nombre valide."
                is_valid = False
            
            # Si tout est valide, modifier la matière
            if is_valid:
                try:
                    with transaction.atomic():
                        # Modifier la matière
                        matiere.nom = form_data['nom']
                        matiere.code = form_data['nom'][:3].upper()
                        matiere.type_matiere = form_data['type_matiere']
                        matiere.niveau = form_data['niveau']
                        matiere.coefficient = float(form_data['coefficient'])
                        matiere.save()
                        
                        # Assigner les classes
                        if form_data['classes']:
                            classes_ids = [int(id) for id in form_data['classes'] if id.isdigit()]
                            classes = Classe.objects.filter(id__in=classes_ids, etablissement=etablissement)
                            matiere.classes.set(classes)
                        else:
                            matiere.classes.clear()
                        
                        messages.success(request, f"La matière '{matiere.nom_complet}' a été modifiée avec succès !")
                        return redirect('matiere:detail_matiere', matiere_id=matiere.id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de la modification de la matière: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de la modification de la matière."
                    is_valid = False
        else:
            # Pré-remplir le formulaire avec les données actuelles
            form_data = {
                'nom': matiere.nom,
                'type_matiere': matiere.type_matiere,
                'niveau': matiere.niveau,
                'coefficient': str(matiere.coefficient),
                'classes': [str(classe.id) for classe in classes_associees],
            }
        
        context = {
            'matiere': matiere,
            'professeurs_principaux': professeurs_principaux,
            'professeurs_secondaires': professeurs_secondaires,
            'classes_associees': classes_associees,
            'toutes_classes': toutes_classes,
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'niveau_choices': Matiere.NIVEAU_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/detail_matiere.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, matiere_id):
        """
        Active/désactive une matière
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
            matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
            matiere.actif = not matiere.actif
            matiere.save()
            
            status = "activée" if matiere.actif else "désactivée"
            messages.success(request, f"La matière '{matiere.nom_complet}' a été {status}.")
            
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
        
        return redirect('matiere:liste_matieres')
    
    @staticmethod
    @login_required
    def supprimer_matiere(request, matiere_id):
        """
        Supprime une matière
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
            matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
            nom_matiere = matiere.nom_complet
            
            # Vérifier s'il y a des professeurs associés
            from ..model.professeur_model import Professeur
            professeurs_principaux = Professeur.objects.filter(matiere_principale=matiere).count()
            professeurs_secondaires = Professeur.objects.filter(matieres_secondaires=matiere).count()
            
            if professeurs_principaux > 0 or professeurs_secondaires > 0:
                messages.error(request, f"Impossible de supprimer la matière '{nom_matiere}' car elle est associée à {professeurs_principaux + professeurs_secondaires} professeur(s).")
                return redirect('matiere:detail_matiere', matiere_id=matiere_id)
            
            # Supprimer la matière
            matiere.delete()
            messages.success(request, f"La matière '{nom_matiere}' a été supprimée avec succès !")
            
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
        
        return redirect('matiere:liste_matieres')
