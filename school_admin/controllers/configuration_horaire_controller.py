# school_admin/controllers/configuration_horaire_controller.py

from datetime import datetime
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render

from ..model.configuration_horaire_model import ConfigurationHoraire, PeriodeEtablissement
from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..utils.session_utils import get_session_active

logger = logging.getLogger(__name__)


class ConfigurationHoraireController:
    """
    Contrôleur pour gérer la configuration des horaires de l'établissement
    """

    @staticmethod
    def _parse_time_value(time_str: str):
        """Convertit une chaîne HH:MM en objet time."""
        if not time_str:
            return None
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            return None
    
    @staticmethod
    @login_required
    def gerer_configuration(request):
        """
        Affiche et gère la configuration des horaires de l'établissement
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
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = get_session_active(request, etablissement)
        
        if not annee_scolaire_active:
            messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de configurer les horaires.")
            return redirect('directeur:creer_annee_scolaire_obligatoire')
        
        # Récupérer ou créer la configuration horaire (OneToOneField avec etablissement)
        # Il ne peut y avoir qu'une seule configuration par établissement
        try:
            configuration = ConfigurationHoraire.objects.get(etablissement=etablissement)
            created = False
            # Mettre à jour l'année scolaire active si nécessaire
            if configuration.annee_scolaire != annee_scolaire_active:
                configuration.annee_scolaire = annee_scolaire_active
                configuration.save(update_fields=['annee_scolaire'])
        except ConfigurationHoraire.DoesNotExist:
            # Créer une nouvelle configuration avec l'année scolaire active
            configuration = ConfigurationHoraire.objects.create(
                etablissement=etablissement,
                heure_debut_cours='08:00',
                heure_fin_cours='16:00',
                actif=True,
                annee_scolaire=annee_scolaire_active
            )
            created = True
        
        if created:
            messages.success(request, "Configuration horaire créée avec les valeurs par défaut.")
        
        form_data = {}
        field_errors = {}
        
        if request.method == 'POST':
            action = request.POST.get('action', 'update')
            
            # ACTION : SUPPRIMER
            if action == 'supprimer':
                try:
                    # Réinitialiser aux valeurs par défaut au lieu de supprimer
                    configuration.heure_debut_cours = '08:00'
                    configuration.heure_fin_cours = '16:00'
                    configuration.save()
                    messages.success(request, "Configuration horaire réinitialisée aux valeurs par défaut.")
                    logger.info(f"Configuration horaire réinitialisée - Établissement: {etablissement.nom}")
                    # Rediriger en mode édition pour que l'utilisateur puisse reconfigurer
                    return redirect('administrateur_etablissement:configuration_horaires' + '?mode=edit')
                except Exception as e:
                    logger.error(f"Erreur lors de la réinitialisation: {str(e)}")
                    messages.error(request, "Une erreur est survenue lors de la réinitialisation.")
            
            # ACTION : METTRE À JOUR (par défaut)
            else:
                # Récupération des données
                form_data = {
                    'heure_debut_cours': request.POST.get('heure_debut_cours', '').strip(),
                    'heure_fin_cours': request.POST.get('heure_fin_cours', '').strip(),
                    'heure_pause1': request.POST.get('heure_pause1', '').strip(),
                    'heure_pause2': request.POST.get('heure_pause2', '').strip(),
                    'heure_pause3': request.POST.get('heure_pause3', '').strip(),
                }
                
                # Validation
                is_valid = True
                
                if not form_data['heure_debut_cours']:
                    field_errors['heure_debut_cours'] = "L'heure de début est obligatoire."
                    is_valid = False
                
                if not form_data['heure_fin_cours']:
                    field_errors['heure_fin_cours'] = "L'heure de fin est obligatoire."
                    is_valid = False
                
                # Validation de l'heure de fin > heure de début
                if form_data['heure_debut_cours'] and form_data['heure_fin_cours']:
                    if form_data['heure_fin_cours'] <= form_data['heure_debut_cours']:
                        field_errors['heure_fin_cours'] = "L'heure de fin doit être après l'heure de début."
                        is_valid = False
                
                if is_valid:
                    try:
                        with transaction.atomic():
                            # Mettre à jour la configuration
                            configuration.heure_debut_cours = form_data['heure_debut_cours']
                            configuration.heure_fin_cours = form_data['heure_fin_cours']
                            configuration.save()
                            
                            messages.success(request, "Configuration horaire mise à jour avec succès !")
                            
                            # Si des horaires de pause sont fournis, suggérer de configurer les périodes
                            if form_data['heure_pause1'] or form_data['heure_pause2'] or form_data['heure_pause3']:
                                messages.info(request, "Configurez maintenant les périodes détaillées pour votre établissement.")
                                return redirect('administrateur_etablissement:gerer_periodes')
                            
                            return redirect('administrateur_etablissement:configuration_horaires')
                            
                    except Exception as e:
                        logger.error(f"Erreur lors de la mise à jour: {str(e)}")
                        messages.error(request, "Une erreur est survenue lors de la mise à jour.")
        else:
            # Pré-remplir le formulaire avec les données actuelles
            # Gérer le cas où les heures sont des objets time ou des strings
            heure_debut = configuration.heure_debut_cours
            heure_fin = configuration.heure_fin_cours
            
            if heure_debut:
                if isinstance(heure_debut, str):
                    heure_debut_str = heure_debut
                else:
                    heure_debut_str = heure_debut.strftime('%H:%M')
            else:
                heure_debut_str = ''
            
            if heure_fin:
                if isinstance(heure_fin, str):
                    heure_fin_str = heure_fin
                else:
                    heure_fin_str = heure_fin.strftime('%H:%M')
            else:
                heure_fin_str = ''
            
            form_data = {
                'heure_debut_cours': heure_debut_str,
                'heure_fin_cours': heure_fin_str,
                'heure_pause1': '',
                'heure_pause2': '',
                'heure_pause3': '',
            }
        
        # Récupérer les périodes existantes
        periodes = PeriodeEtablissement.objects.filter(
            configuration_horaire=configuration,
            actif=True
        ).order_by('ordre')
        
        context = {
            'etablissement': etablissement,
            'personnel': personnel,
            'is_directeur': isinstance(request.user, Etablissement),
            'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
            'configuration': configuration,
            'form_data': form_data,
            'field_errors': field_errors,
            'periodes': periodes,
            'annee_scolaire_active': annee_scolaire_active,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/configuration_horaires.html', context)
    
    @staticmethod
    @login_required
    def gerer_periodes(request):
        """
        Gère les périodes détaillées de l'établissement
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
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = get_session_active(request, etablissement)
        
        if not annee_scolaire_active:
            messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de gérer les périodes.")
            return redirect('directeur:creer_annee_scolaire_obligatoire')
        
        # Récupérer la configuration horaire pour l'année scolaire active
        configuration = ConfigurationHoraire.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        ).first()
        
        if not configuration:
            messages.error(request, "Veuillez d'abord configurer les horaires de base pour l'année scolaire active.")
            return redirect('administrateur_etablissement:configuration_horaires')
        
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'ajouter_periode':
                # Ajouter une nouvelle période
                try:
                    with transaction.atomic():
                        nom = request.POST.get('nom', '').strip()
                        type_periode = request.POST.get('type_periode', '')
                        heure_debut = request.POST.get('heure_debut', '').strip()
                        heure_fin = request.POST.get('heure_fin', '').strip()
                        
                        if not all([nom, type_periode, heure_debut, heure_fin]):
                            messages.error(request, "Tous les champs sont obligatoires.")
                            return redirect('administrateur_etablissement:gerer_periodes')

                        if type_periode not in dict(PeriodeEtablissement.TYPE_PERIODE_CHOICES):
                            messages.error(request, "Type de période invalide.")
                            return redirect('administrateur_etablissement:gerer_periodes')

                        heure_debut_obj = ConfigurationHoraireController._parse_time_value(heure_debut)
                        heure_fin_obj = ConfigurationHoraireController._parse_time_value(heure_fin)

                        if not heure_debut_obj or not heure_fin_obj:
                            messages.error(request, "Les heures fournies sont invalides.")
                            return redirect('administrateur_etablissement:gerer_periodes')

                        if heure_fin_obj <= heure_debut_obj:
                            messages.error(request, "L'heure de fin doit être postérieure à l'heure de début.")
                            return redirect('administrateur_etablissement:gerer_periodes')
                        
                        # Récupérer l'ordre max actuel
                        dernier_ordre = PeriodeEtablissement.objects.filter(
                            configuration_horaire=configuration
                        ).count()
                        
                        periode = PeriodeEtablissement.objects.create(
                            configuration_horaire=configuration,
                            nom=nom,
                            type_periode=type_periode,
                            heure_debut=heure_debut_obj,
                            heure_fin=heure_fin_obj,
                            ordre=dernier_ordre + 1,
                            actif=True,
                            annee_scolaire=annee_scolaire_active
                        )
                        
                        messages.success(request, f"Période '{periode.nom}' ajoutée avec succès !")
                        return redirect('administrateur_etablissement:gerer_periodes')
                        
                except ValidationError as exc:
                    messages.error(request, "; ".join(exc.messages))
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout de la période: {str(e)}")
                    messages.error(request, f"Erreur: {str(e)}")
            
            elif action == 'modifier_periode':
                periode_id = request.POST.get('periode_id')
                nom = request.POST.get('nom', '').strip()
                type_periode = request.POST.get('type_periode', '').strip()
                heure_debut = request.POST.get('heure_debut', '').strip()
                heure_fin = request.POST.get('heure_fin', '').strip()

                if not all([periode_id, nom, type_periode, heure_debut, heure_fin]):
                    messages.error(request, "Tous les champs sont obligatoires pour modifier la période.")
                    return redirect('administrateur_etablissement:gerer_periodes')

                if type_periode not in dict(PeriodeEtablissement.TYPE_PERIODE_CHOICES):
                    messages.error(request, "Type de période invalide.")
                    return redirect('administrateur_etablissement:gerer_periodes')

                heure_debut_obj = ConfigurationHoraireController._parse_time_value(heure_debut)
                heure_fin_obj = ConfigurationHoraireController._parse_time_value(heure_fin)

                if not heure_debut_obj or not heure_fin_obj:
                    messages.error(request, "Les heures fournies sont invalides.")
                    return redirect('administrateur_etablissement:gerer_periodes')

                if heure_fin_obj <= heure_debut_obj:
                    messages.error(request, "L'heure de fin doit être postérieure à l'heure de début.")
                    return redirect('administrateur_etablissement:gerer_periodes')

                try:
                    periode = PeriodeEtablissement.objects.get(
                        id=periode_id,
                        configuration_horaire=configuration
                    )
                    periode.nom = nom
                    periode.type_periode = type_periode
                    periode.heure_debut = heure_debut_obj
                    periode.heure_fin = heure_fin_obj
                    # Conserver l'année scolaire active
                    if periode.annee_scolaire != annee_scolaire_active:
                        periode.annee_scolaire = annee_scolaire_active
                    periode.save()
                    messages.success(request, f"Période « {periode.nom} » mise à jour avec succès.")
                except PeriodeEtablissement.DoesNotExist:
                    messages.error(request, "Période introuvable.")
                except ValidationError as exc:
                    messages.error(request, "; ".join(exc.messages))
                except Exception as e:
                    logger.error(f"Erreur lors de la modification de la période: {str(e)}")
                    messages.error(request, f"Erreur: {str(e)}")

                return redirect('administrateur_etablissement:gerer_periodes')

            elif action == 'supprimer_periode':
                # Supprimer une période
                periode_id = request.POST.get('periode_id')
                try:
                    periode = PeriodeEtablissement.objects.get(id=periode_id, configuration_horaire=configuration)
                    nom_periode = periode.nom
                    periode.delete()
                    messages.success(request, f"Période '{nom_periode}' supprimée avec succès !")
                except PeriodeEtablissement.DoesNotExist:
                    messages.error(request, "Période non trouvée.")
                except Exception as e:
                    logger.error(f"Erreur lors de la suppression: {str(e)}")
                    messages.error(request, f"Erreur: {str(e)}")
                
                return redirect('administrateur_etablissement:gerer_periodes')
        
        # Récupérer les périodes existantes pour l'année scolaire active
        periodes = PeriodeEtablissement.objects.filter(
            configuration_horaire=configuration,
            annee_scolaire=annee_scolaire_active,
            actif=True
        ).order_by('ordre')
        
        context = {
            'etablissement': etablissement,
            'personnel': personnel,
            'is_directeur': isinstance(request.user, Etablissement),
            'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
            'configuration': configuration,
            'periodes': periodes,
            'annee_scolaire_active': annee_scolaire_active,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/gerer_periodes.html', context)

