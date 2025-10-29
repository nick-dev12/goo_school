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
from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

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
            if etablissement.type_etablissement == 'primary':
                # Pour le primaire, vérifier AffectationProfesseurPrimaire
                if AffectationProfesseurPrimaire.objects.filter(professeur=professeur, actif=True).exists():
                    stats['professeurs_affectes'] += 1
            else:
                # Pour les autres, vérifier AffectationProfesseur
                if professeur.affectations.filter(actif=True).exists():
                    stats['professeurs_affectes'] += 1
        
        # Préparer les classes disponibles pour chaque professeur
        professeurs_with_classes = []
        for professeur in professeurs:
            # Pour le primaire, utiliser AffectationProfesseurPrimaire
            if etablissement.type_etablissement == 'primary':
                affectations_primaires = AffectationProfesseurPrimaire.objects.filter(
                    professeur=professeur,
                    actif=True
                ).select_related('classe').prefetch_related('matieres')
                
                affectations_a_afficher = list(affectations_primaires)
                affectations_actives = affectations_primaires.values_list('classe_id', flat=True).distinct()
            else:
                # Pour les autres établissements, utiliser AffectationProfesseur standard
                affectations_actives_query = professeur.affectations.filter(actif=True).select_related('classe', 'matiere')
                affectations_a_afficher = list(affectations_actives_query)
                affectations_actives = professeur.affectations.filter(actif=True).values_list('classe_id', flat=True).distinct()
            
            classes_disponibles = classes.exclude(id__in=affectations_actives)
            
            # Récupérer toutes les matières que le professeur peut enseigner
            matieres_enseignables = [professeur.matiere_principale]
            if professeur.matieres_secondaires.exists():
                matieres_enseignables.extend(list(professeur.matieres_secondaires.all()))
            
            professeurs_with_classes.append({
                'professeur': professeur,
                'classes_disponibles': classes_disponibles,
                'affectations': affectations_a_afficher,
                'matieres_enseignables': matieres_enseignables,
            })
        
        context = {
            'etablissement': etablissement,
            'professeurs_with_classes': professeurs_with_classes,
            'classes': classes,
            'matieres': matieres,
            'professeurs_par_matiere': professeurs_par_matiere,
            'stats': stats,
            'type_etablissement': etablissement.type_etablissement,
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
            matiere_id = request.POST.get('matiere_id')  # Matière à enseigner
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
            
            # Récupérer la matière si spécifiée
            matiere = None
            if matiere_id:
                try:
                    matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
                except Matiere.DoesNotExist:
                    messages.error(request, 'Matière non trouvée.')
                    return redirect('affectation:affectation_professeurs')
            
            with transaction.atomic():
                if action == 'add':
                    # Si aucune matière n'est spécifiée, utiliser la matière principale
                    if not matiere:
                        matiere = professeur.matiere_principale
                    
                    # VÉRIFICATION SPÉCIFIQUE POUR LES ÉCOLES PRIMAIRES
                    if etablissement.type_etablissement == 'primary':
                        # Récupérer toutes les matières du professeur à affecter
                        matieres_professeur = set()
                        if professeur.matiere_principale:
                            matieres_professeur.add(professeur.matiere_principale.id)
                        matieres_professeur.update(professeur.matieres_secondaires.values_list('id', flat=True))
                        
                        # Récupérer toutes les affectations primaires existantes pour cette classe
                        affectations_existantes = AffectationProfesseurPrimaire.objects.filter(
                            classe=classe,
                            actif=True
                        ).exclude(professeur=professeur).select_related('professeur').prefetch_related('matieres')
                        
                        # Vérifier les conflits de matières par professeur
                        conflits = {}
                        for affectation_existante in affectations_existantes:
                            prof_existant = affectation_existante.professeur
                            
                            # Récupérer toutes les matières de l'affectation existante
                            matieres_existantes = set(affectation_existante.matieres.values_list('id', flat=True))
                            
                            # Vérifier s'il y a des matières en commun
                            matieres_communes = matieres_professeur.intersection(matieres_existantes)
                            if matieres_communes:
                                # Récupérer les noms des matières en conflit
                                matieres_noms = Matiere.objects.filter(id__in=matieres_communes).values_list('nom', flat=True)
                                conflits[prof_existant.nom_complet] = list(matieres_noms)
                        
                        # Si des conflits existent, refuser l'affectation
                        if conflits:
                            messages_conflit = []
                            for prof_nom, matieres in conflits.items():
                                matieres_str = ", ".join(matieres)
                                messages_conflit.append(f"{prof_nom} enseigne déjà: {matieres_str}")
                            
                            message_final = f"Impossible d'affecter {professeur.nom_complet} à la classe {classe.nom}. " + " | ".join(messages_conflit)
                            messages.error(request, message_final)
                            return redirect('affectation:affectation_professeurs')
                    
                    # Pour les écoles primaires, utiliser AffectationProfesseurPrimaire
                    if etablissement.type_etablissement == 'primary':
                        # Vérifier si une affectation primaire existe déjà
                        existing_affectation = AffectationProfesseurPrimaire.objects.filter(
                            professeur=professeur,
                            classe=classe,
                            actif=True
                        ).first()
                        
                        if existing_affectation:
                            messages.warning(request, f"Le professeur {professeur.nom} est déjà affecté à la classe {classe.nom}.")
                        else:
                            try:
                                # Récupérer toutes les matières du professeur
                                toutes_matieres = []
                                if professeur.matiere_principale:
                                    toutes_matieres.append(professeur.matiere_principale)
                                toutes_matieres.extend(list(professeur.matieres_secondaires.all()))
                                
                                # Créer l'affectation primaire
                                statut_primaire = 'principal' if statut == 'principal' else 'polyvalent'
                                affectation_primaire = AffectationProfesseurPrimaire.objects.create(
                                    professeur=professeur,
                                    classe=classe,
                                    statut=statut_primaire,
                                    actif=True
                                )
                                
                                # Ajouter toutes les matières
                                affectation_primaire.matieres.set(toutes_matieres)
                                
                                statut_display = "Professeur Principal" if statut == 'principal' else "Professeur Polyvalent"
                                messages.success(request, f"Professeur {professeur.nom} affecté à la classe {classe.nom} en tant que {statut_display} pour toutes ses matières ({len(toutes_matieres)} matière(s))")
                            except ValidationError as e:
                                messages.error(request, str(e))
                                return redirect('affectation:affectation_professeurs')
                    else:
                        # Pour les autres établissements, utiliser AffectationProfesseur standard
                        existing_affectation = AffectationProfesseur.objects.filter(
                            professeur=professeur,
                            classe=classe,
                            matiere=matiere,
                            actif=True
                        ).first()
                        
                        if existing_affectation:
                            messages.warning(request, f"Le professeur {professeur.nom} est déjà affecté à la classe {classe.nom} pour {matiere.nom}.")
                        else:
                            try:
                                AffectationProfesseur.objects.create(
                                    professeur=professeur,
                                    classe=classe,
                                    matiere=matiere,
                                    statut=statut
                                )
                                statut_display = "Professeur Principal" if statut == 'principal' else "Professeur Classique"
                                messages.success(request, f"Professeur {professeur.nom} affecté à la classe {classe.nom} en tant que {statut_display} pour la matière {matiere.nom}")
                            except ValidationError as e:
                                messages.error(request, str(e))
                                return redirect('affectation:affectation_professeurs')
                        
                elif action == 'remove':
                    # Pour le primaire, supprimer l'affectation primaire
                    if etablissement.type_etablissement == 'primary':
                        affectation = AffectationProfesseurPrimaire.objects.filter(
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
                        # Pour les autres, supprimer l'affectation standard
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
