import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import ValidationError

from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.salle_model import Salle

logger = logging.getLogger(__name__)

class SalleController:
    @staticmethod
    @login_required
    def liste_salles(request):
        """Affiche la liste des salles de l'établissement"""
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
        
        # Récupérer les salles de l'établissement
        salles = Salle.objects.filter(
            etablissement=etablissement
        ).order_by('numero', 'nom')
        
        # Regrouper les salles par type
        salles_grouped = {}
        for salle in salles:
            type_salle = salle.get_type_salle_display()
            if type_salle not in salles_grouped:
                salles_grouped[type_salle] = {
                    'type': salle.type_salle,
                    'salles': [],
                    'total_capacite': 0,
                    'salles_disponibles': 0,
                    'salles_occupees': 0,
                    'salles_maintenance': 0
                }
            
            salles_grouped[type_salle]['salles'].append(salle)
            salles_grouped[type_salle]['total_capacite'] += salle.capacite_max
            
            if salle.etat == 'disponible':
                salles_grouped[type_salle]['salles_disponibles'] += 1
            elif salle.etat == 'occupee':
                salles_grouped[type_salle]['salles_occupees'] += 1
            elif salle.etat == 'maintenance':
                salles_grouped[type_salle]['salles_maintenance'] += 1
        
        # Statistiques
        stats = {
            'total': salles.count(),
            'actives': salles.filter(actif=True).count(),
            'inactives': salles.filter(actif=False).count(),
            'disponibles': salles.filter(etat='disponible', actif=True).count(),
            'occupees': salles.filter(etat='occupee').count(),
            'maintenance': salles.filter(etat='maintenance').count(),
            'total_capacite': sum(salle.capacite_max for salle in salles),
            'par_type': {}
        }
        
        for type_salle, label in Salle.TYPE_SALLE_CHOICES:
            count = salles.filter(type_salle=type_salle).count()
            if count > 0:
                stats['par_type'][label] = count
        
        context = {
            'salles': salles,
            'salles_grouped': salles_grouped,
            'etablissement': etablissement,
            'personnel': personnel,
            'stats': stats,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/salles/liste_salles.html', context)
    
    @staticmethod
    @login_required
    def ajouter_salle(request):
        """Ajoute une nouvelle salle"""
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
                    nom = request.POST.get('nom')
                    numero = request.POST.get('numero')
                    type_salle = request.POST.get('type_salle')
                    capacite_max = request.POST.get('capacite_max')
                    etat = request.POST.get('etat', 'disponible')
                    
                    # Validation des champs obligatoires
                    if not nom or not numero or not type_salle or not capacite_max:
                        messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                        return redirect('salle:liste_salles')
                    
                    # Vérifier si le numéro de salle existe déjà
                    if Salle.objects.filter(numero=numero, etablissement=etablissement).exists():
                        messages.error(request, f"Une salle avec le numéro '{numero}' existe déjà dans cet établissement.")
                        return redirect('salle:liste_salles')
                    
                    # Créer la salle
                    salle = Salle.objects.create(
                        nom=nom,
                        numero=numero,
                        type_salle=type_salle,
                        capacite_max=int(capacite_max),
                        etat=etat,
                        etablissement=etablissement
                    )
                    
                    messages.success(request, f"Salle '{salle.nom_complet}' ajoutée avec succès.")
                    return redirect('salle:liste_salles')
                    
            except ValidationError as e:
                messages.error(request, f"Erreur de validation: {e}")
            except Exception as e:
                logger.error(f"Erreur lors de l'ajout de la salle: {e}")
                messages.error(request, f"Une erreur est survenue lors de l'ajout de la salle: {e}")
        
        return redirect('salle:liste_salles')
    
    @staticmethod
    @login_required
    def detail_salle(request, salle_id):
        """Affiche les détails d'une salle"""
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
            salle = Salle.objects.get(
                id=salle_id,
                etablissement=etablissement
            )
        except Salle.DoesNotExist:
            messages.error(request, "Salle non trouvée.")
            return redirect('salle:liste_salles')
        
        # Statistiques de la salle
        stats_salle = {
            'capacite_actuelle': salle.capacite_actuelle,
            'taux_occupation': 0,  # TODO: Calculer le taux d'occupation réel
            'jours_utilisee': 0,   # TODO: Calculer les jours d'utilisation
            'derniere_utilisation': None,  # TODO: Récupérer la dernière utilisation
        }
        
        context = {
            'salle': salle,
            'etablissement': etablissement,
            'personnel': personnel,
            'stats_salle': stats_salle,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/salles/detail_salle.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, salle_id):
        """Active/désactive une salle"""
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
            salle = Salle.objects.get(
                id=salle_id,
                etablissement=etablissement
            )
            
            salle.actif = not salle.actif
            salle.save()
            
            action = "activée" if salle.actif else "désactivée"
            messages.success(request, f"Salle '{salle.nom_complet}' {action} avec succès.")
            
        except Salle.DoesNotExist:
            messages.error(request, "Salle non trouvée.")
        
        return redirect('salle:liste_salles')
    
    @staticmethod
    @login_required
    def modifier_salle(request, salle_id):
        """Modifie une salle"""
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
                salle = Salle.objects.get(
                    id=salle_id,
                    etablissement=etablissement
                )
                
                with transaction.atomic():
                    # Récupérer les données du formulaire
                    nom = request.POST.get('nom')
                    numero = request.POST.get('numero')
                    type_salle = request.POST.get('type_salle')
                    capacite_max = request.POST.get('capacite_max')
                    etat = request.POST.get('etat')
                    
                    # Validation des champs obligatoires
                    if not nom or not numero or not type_salle or not capacite_max:
                        messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                        return redirect('salle:detail_salle', salle_id=salle_id)
                    
                    # Vérifier si le numéro de salle existe déjà (sauf pour cette salle)
                    if Salle.objects.filter(numero=numero, etablissement=etablissement).exclude(id=salle_id).exists():
                        messages.error(request, f"Une salle avec le numéro '{numero}' existe déjà dans cet établissement.")
                        return redirect('salle:detail_salle', salle_id=salle_id)
                    
                    # Mettre à jour la salle
                    salle.nom = nom
                    salle.numero = numero
                    salle.type_salle = type_salle
                    salle.capacite_max = int(capacite_max)
                    salle.etat = etat
                    salle.save()
                    
                    messages.success(request, f"Salle '{salle.nom_complet}' modifiée avec succès.")
                    return redirect('salle:detail_salle', salle_id=salle_id)
                    
            except Salle.DoesNotExist:
                messages.error(request, "Salle non trouvée.")
                return redirect('salle:liste_salles')
            except ValidationError as e:
                messages.error(request, f"Erreur de validation: {e}")
            except Exception as e:
                logger.error(f"Erreur lors de la modification de la salle: {e}")
                messages.error(request, f"Une erreur est survenue lors de la modification de la salle: {e}")
        
        return redirect('salle:detail_salle', salle_id=salle_id)
