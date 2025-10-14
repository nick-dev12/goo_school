import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Q, Count
from django.http import JsonResponse
from datetime import datetime, date

from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.classe_model import Classe
from ..model.salle_model import Salle
from ..model.affectation_salle_model import AffectationSalle

logger = logging.getLogger(__name__)

class AffectationSalleController:
    @staticmethod
    @login_required
    def liste_affectations(request):
        """Affiche la liste des affectations salles-classes"""
        user = request.user
        
        # Vérifier le type d'utilisateur
        if isinstance(user, PersonnelAdministratif):
            etablissement = user.etablissement
            personnel = user
        elif isinstance(user, Etablissement):
            etablissement = user
            personnel = None
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        # Récupérer les affectations de l'établissement
        affectations = AffectationSalle.objects.filter(
            classe__etablissement=etablissement,
            salle__etablissement=etablissement
        ).select_related('classe', 'salle').order_by('classe__nom', 'jour_semaine', 'periode')
        
        # Regrouper par classe
        affectations_par_classe = {}
        for affectation in affectations:
            classe_nom = affectation.classe.nom
            if classe_nom not in affectations_par_classe:
                affectations_par_classe[classe_nom] = {
                    'classe': affectation.classe,
                    'affectations': [],
                    'total_salles': 0
                }
            affectations_par_classe[classe_nom]['affectations'].append(affectation)
            affectations_par_classe[classe_nom]['total_salles'] += 1
        
        # Regrouper les classes par catégorie (niveau + préfixe)
        import re
        classes_grouped = {}
        
        for classe_nom, data in affectations_par_classe.items():
            classe = data['classe']
            
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
                    'total_affectations': 0,
                    'total_salles': 0
                }
            
            classes_grouped[categorie]['classes'].append((classe_nom, data))
            classes_grouped[categorie]['total_affectations'] += len(data['affectations'])
            classes_grouped[categorie]['total_salles'] += data['total_salles']
        
        # Convertir en liste triée pour le template
        classes_par_niveau = []
        for categorie, data in classes_grouped.items():
            classes_par_niveau.append({
                'niveau': data['niveau'],
                'categorie': categorie,
                'classes': data['classes'],
                'total_affectations': data['total_affectations'],
                'total_salles': data['total_salles']
            })
        
        # Trier par niveau
        classes_par_niveau.sort(key=lambda x: x['niveau'])
        
        # Regrouper par salle
        affectations_par_salle = {}
        for affectation in affectations:
            salle_nom = affectation.salle.nom
            if salle_nom not in affectations_par_salle:
                affectations_par_salle[salle_nom] = {
                    'salle': affectation.salle,
                    'affectations': [],
                    'total_classes': 0
                }
            affectations_par_salle[salle_nom]['affectations'].append(affectation)
            affectations_par_salle[salle_nom]['total_classes'] += 1
        
        # Regrouper les salles par type
        salles_grouped = {}
        
        for salle_nom, data in affectations_par_salle.items():
            salle = data['salle']
            type_salle = salle.get_type_salle_display()
            
            if type_salle not in salles_grouped:
                salles_grouped[type_salle] = {
                    'salles': [],
                    'total_affectations': 0,
                    'total_classes': 0
                }
            
            salles_grouped[type_salle]['salles'].append((salle_nom, data))
            salles_grouped[type_salle]['total_affectations'] += len(data['affectations'])
            salles_grouped[type_salle]['total_classes'] += data['total_classes']
        
        # Convertir en liste triée pour le template
        salles_par_type = []
        for type_salle, data in salles_grouped.items():
            salles_par_type.append({
                'type': type_salle,
                'salles': data['salles'],
                'total_affectations': data['total_affectations'],
                'total_classes': data['total_classes']
            })
        
        # Trier par type
        salles_par_type.sort(key=lambda x: x['type'])
        
        # Statistiques
        stats = {
            'total_affectations': affectations.count(),
            'affectations_actives': affectations.filter(actif=True, statut='active').count(),
            'classes_affectees': len(affectations_par_classe),
            'salles_utilisees': len(affectations_par_salle),
            'par_jour': {},
            'par_periode': {}
        }
        
        # Statistiques par jour
        for jour, _ in AffectationSalle.JOUR_SEMAINE_CHOICES:
            count = affectations.filter(jour_semaine=jour, actif=True).count()
            if count > 0:
                stats['par_jour'][jour] = count
        
        # Statistiques par période
        for periode, _ in AffectationSalle.PERIODE_CHOICES:
            count = affectations.filter(periode=periode, actif=True).count()
            if count > 0:
                stats['par_periode'][periode] = count
        
        context = {
            'affectations': affectations,
            'affectations_par_classe': affectations_par_classe,
            'affectations_par_salle': affectations_par_salle,
            'classes_par_niveau': classes_par_niveau,
            'salles_par_type': salles_par_type,
            'etablissement': etablissement,
            'personnel': personnel,
            'stats': stats,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/affectations_salles/liste_affectations.html', context)
    
    @staticmethod
    @login_required
    def ajouter_affectation(request):
        """Ajoute une nouvelle affectation salle-classe"""
        if request.method == 'POST':
            user = request.user
            
            # Vérifier le type d'utilisateur
            if isinstance(user, PersonnelAdministratif):
                etablissement = user.etablissement
            elif isinstance(user, Etablissement):
                etablissement = user
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
            
            try:
                with transaction.atomic():
                    # Récupérer les données du formulaire
                    classe_id = request.POST.get('classe')
                    salle_id = request.POST.get('salle')
                    jour_semaine = request.POST.get('jour_semaine')
                    periode = request.POST.get('periode')
                    heure_debut = request.POST.get('heure_debut')
                    heure_fin = request.POST.get('heure_fin')
                    commentaire = request.POST.get('commentaire', '')
                    
                    # Validation des champs obligatoires
                    if not all([classe_id, salle_id, jour_semaine, periode]):
                        messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                        return redirect('affectation_salle:liste_affectations')
                    
                    # Récupérer les objets
                    classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
                    salle = Salle.objects.get(id=salle_id, etablissement=etablissement)
                    
                    # Vérifier la disponibilité de la salle
                    if not AffectationSalle.get_disponibilites_salle(salle, jour_semaine, periode):
                        messages.error(request, f"La salle {salle.nom} n'est pas disponible le {dict(AffectationSalle.JOUR_SEMAINE_CHOICES)[jour_semaine]} en {dict(AffectationSalle.PERIODE_CHOICES)[periode]}.")
                        return redirect('affectation_salle:liste_affectations')
                    
                    
                    # Créer l'affectation
                    affectation = AffectationSalle.objects.create(
                        classe=classe,
                        salle=salle,
                        jour_semaine=jour_semaine,
                        periode=periode,
                        heure_debut=heure_debut if heure_debut else None,
                        heure_fin=heure_fin if heure_fin else None,
                        commentaire=commentaire
                    )
                    
                    messages.success(request, f"Affectation créée : {affectation.nom_complet}")
                    return redirect('affectation_salle:liste_affectations')
                    
            except Classe.DoesNotExist:
                messages.error(request, "Classe non trouvée.")
            except Salle.DoesNotExist:
                messages.error(request, "Salle non trouvée.")
            except ValidationError as e:
                messages.error(request, f"Erreur de validation: {e}")
            except Exception as e:
                logger.error(f"Erreur lors de l'ajout de l'affectation: {e}")
                messages.error(request, f"Une erreur est survenue: {e}")
        
        return redirect('affectation_salle:liste_affectations')
    
    @staticmethod
    @login_required
    def modifier_affectation(request, affectation_id):
        """Modifie une affectation existante"""
        if request.method == 'POST':
            user = request.user
            
            # Vérifier le type d'utilisateur
            if isinstance(user, PersonnelAdministratif):
                etablissement = user.etablissement
            elif isinstance(user, Etablissement):
                etablissement = user
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
            
            try:
                affectation = AffectationSalle.objects.get(
                    id=affectation_id,
                    classe__etablissement=etablissement,
                    salle__etablissement=etablissement
                )
                
                with transaction.atomic():
                    # Récupérer les données du formulaire
                    classe_id = request.POST.get('classe')
                    salle_id = request.POST.get('salle')
                    jour_semaine = request.POST.get('jour_semaine')
                    periode = request.POST.get('periode')
                    heure_debut = request.POST.get('heure_debut')
                    heure_fin = request.POST.get('heure_fin')
                    statut = request.POST.get('statut')
                    commentaire = request.POST.get('commentaire', '')
                    
                    # Validation des champs obligatoires
                    if not all([classe_id, salle_id, jour_semaine, periode]):
                        messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                        return redirect('affectation_salle:liste_affectations')
                    
                    # Récupérer les objets
                    classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
                    salle = Salle.objects.get(id=salle_id, etablissement=etablissement)
                    
                    # Vérifier la disponibilité de la salle (sauf pour cette affectation)
                    if not AffectationSalle.get_disponibilites_salle(salle, jour_semaine, periode):
                        # Vérifier s'il y a un conflit avec une autre affectation
                        conflits = AffectationSalle.objects.filter(
                            salle=salle,
                            jour_semaine=jour_semaine,
                            periode=periode,
                            actif=True,
                            statut='active'
                        ).exclude(pk=affectation.id)
                        
                        if conflits.exists():
                            messages.error(request, f"La salle {salle.nom} n'est pas disponible le {dict(AffectationSalle.JOUR_SEMAINE_CHOICES)[jour_semaine]} en {dict(AffectationSalle.PERIODE_CHOICES)[periode]}.")
                            return redirect('affectation_salle:liste_affectations')
                    
                    # Gérer les dates selon le type d'affectation
                    if type_affectation == 'temporaire':
                        if not date_debut:
                            messages.error(request, "La date de début est obligatoire pour une affectation temporaire.")
                            return redirect('affectation_salle:liste_affectations')
                        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
                        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date() if date_fin else None
                    else:  # permanente
                        date_debut_obj = affectation.date_debut  # Garder la date de création
                        date_fin_obj = None
                    
                    # Mettre à jour l'affectation
                    affectation.classe = classe
                    affectation.salle = salle
                    affectation.jour_semaine = jour_semaine
                    affectation.periode = periode
                    affectation.heure_debut = heure_debut if heure_debut else None
                    affectation.heure_fin = heure_fin if heure_fin else None
                    affectation.statut = statut
                    affectation.commentaire = commentaire
                    affectation.save()
                    
                    messages.success(request, f"Affectation modifiée : {affectation.nom_complet}")
                    return redirect('affectation_salle:liste_affectations')
                    
            except AffectationSalle.DoesNotExist:
                messages.error(request, "Affectation non trouvée.")
            except Classe.DoesNotExist:
                messages.error(request, "Classe non trouvée.")
            except Salle.DoesNotExist:
                messages.error(request, "Salle non trouvée.")
            except ValidationError as e:
                messages.error(request, f"Erreur de validation: {e}")
            except Exception as e:
                logger.error(f"Erreur lors de la modification de l'affectation: {e}")
                messages.error(request, f"Une erreur est survenue: {e}")
        
        return redirect('affectation_salle:liste_affectations')
    
    @staticmethod
    @login_required
    def supprimer_affectation(request, affectation_id):
        """Supprime une affectation (désactivation)"""
        user = request.user
        
        # Vérifier le type d'utilisateur
        if isinstance(user, PersonnelAdministratif):
            etablissement = user.etablissement
        elif isinstance(user, Etablissement):
            etablissement = user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            affectation = AffectationSalle.objects.get(
                id=affectation_id,
                classe__etablissement=etablissement,
                salle__etablissement=etablissement
            )
            
            affectation.actif = False
            affectation.save()
            
            messages.success(request, f"Affectation supprimée : {affectation.nom_complet}")
            
        except AffectationSalle.DoesNotExist:
            messages.error(request, "Affectation non trouvée.")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression de l'affectation: {e}")
            messages.error(request, f"Une erreur est survenue: {e}")
        
        return redirect('affectation_salle:liste_affectations')
    
    @staticmethod
    @login_required
    def toggle_actif(request, affectation_id):
        """Active/désactive une affectation"""
        user = request.user
        
        # Vérifier le type d'utilisateur
        if isinstance(user, PersonnelAdministratif):
            etablissement = user.etablissement
        elif isinstance(user, Etablissement):
            etablissement = user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            affectation = AffectationSalle.objects.get(
                id=affectation_id,
                classe__etablissement=etablissement,
                salle__etablissement=etablissement
            )
            
            affectation.actif = not affectation.actif
            affectation.save()
            
            action = "activée" if affectation.actif else "désactivée"
            messages.success(request, f"Affectation {action} : {affectation.nom_complet}")
            
        except AffectationSalle.DoesNotExist:
            messages.error(request, "Affectation non trouvée.")
        except Exception as e:
            logger.error(f"Erreur lors du toggle de l'affectation: {e}")
            messages.error(request, f"Une erreur est survenue: {e}")
        
        return redirect('affectation_salle:liste_affectations')
    
    @staticmethod
    @login_required
    def detail_affectation(request, affectation_id):
        """Affiche les détails d'une affectation"""
        user = request.user
        
        # Vérifier le type d'utilisateur
        if isinstance(user, PersonnelAdministratif):
            etablissement = user.etablissement
            personnel = user
        elif isinstance(user, Etablissement):
            etablissement = user
            personnel = None
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            affectation = AffectationSalle.objects.select_related('classe', 'salle').get(
                id=affectation_id,
                classe__etablissement=etablissement,
                salle__etablissement=etablissement
            )
            
            context = {
                'affectation': affectation,
                'etablissement': etablissement,
                'personnel': personnel,
            }
            
            return render(request, 'school_admin/directeur/administrateur_etablissement/affectations_salles/detail_affectation.html', context)
            
        except AffectationSalle.DoesNotExist:
            messages.error(request, "Affectation non trouvée.")
            return redirect('affectation_salle:liste_affectations')
    
    @staticmethod
    @login_required
    def get_disponibilites_salle(request):
        """API pour récupérer les disponibilités d'une salle"""
        if request.method == 'GET':
            salle_id = request.GET.get('salle_id')
            jour = request.GET.get('jour')
            periode = request.GET.get('periode')
            
            if not all([salle_id, jour, periode]):
                return JsonResponse({'error': 'Paramètres manquants'}, status=400)
            
            try:
                salle = Salle.objects.get(id=salle_id)
                disponible = AffectationSalle.get_disponibilites_salle(salle, jour, periode)
                
                return JsonResponse({
                    'disponible': disponible,
                    'salle': salle.nom,
                    'jour': dict(AffectationSalle.JOUR_SEMAINE_CHOICES)[jour],
                    'periode': dict(AffectationSalle.PERIODE_CHOICES)[periode]
                })
                
            except Salle.DoesNotExist:
                return JsonResponse({'error': 'Salle non trouvée'}, status=404)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)
        
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
