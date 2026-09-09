"""
Contrôleur pour la gestion des affectations des professeurs
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.db.models import Prefetch
from django.http import JsonResponse
from django.core.exceptions import ValidationError
import logging

from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.professeur_model import Professeur
from ..model.classe_model import Classe
from ..model.matiere_model import Matiere
from ..model.affectation_model import AffectationProfesseur
from ..model.module_model import Module
from ..model.academic_structure_model import Department
from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from ..utils.session_utils import get_session_active

logger = logging.getLogger(__name__)


def _affectation_fail(request, message, level='error'):
    from ..services.realtime_helpers import wants_json_response, json_fail
    if wants_json_response(request):
        return json_fail(message=message)
    if level == 'warning':
        messages.warning(request, message)
    else:
        messages.error(request, message)
    return redirect('affectation:affectation_professeurs')


def _affectation_done(request, etablissement, professeur_id, action):
    from ..services.realtime_helpers import wants_json_response, json_ok, emit_live
    from ..services.live_serializers import serialize_affectation_refresh_item

    item = serialize_affectation_refresh_item(professeur_id, action)
    emit_live(
        etablissement.id,
        'affectation.mise_a_jour',
        {'event': 'affectation.mise_a_jour', 'item': item},
    )
    if wants_json_response(request):
        return json_ok(message='Affectation mise à jour.', item=item)
    return redirect('affectation:affectation_professeurs')

class AffectationController:
    
    @staticmethod
    @login_required
    def affectation_professeurs(request):
        """
        Page principale d'affectation des professeurs aux classes
        Affiche uniquement les affectations de l'année scolaire active
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
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = get_session_active(request, etablissement)
        
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire pour voir les affectations.")
            # Continuer quand même pour afficher la page vide avec un message
        
        est_superieur = etablissement.type_etablissement == 'superieur'

        # Récupérer tous les professeurs avec leurs matières et affectations
        professeurs = Professeur.objects.filter(
            etablissement=etablissement
        ).select_related(
            'matiere_principale',
            'matiere_principale__module',
            'matiere_principale__department',
        ).prefetch_related(
            'matiere_principale__classes',
            'matiere_principale__module__classes',
            Prefetch(
                'matieres_secondaires',
                queryset=Matiere.objects.select_related('module', 'department').prefetch_related(
                    'classes', 'module__classes'
                ),
            ),
            'affectations__classe',
        )

        # Classes : supérieur = uniquement classes niveau supérieur + filière
        if est_superieur:
            classes = (
                Classe.objects.filter(
                    etablissement=etablissement,
                    niveau='superieur',
                    actif=True,
                )
                .select_related('department', 'academic_level')
                .order_by('department__nom', 'nom')
            )
        else:
            classes = Classe.objects.filter(etablissement=etablissement).order_by('nom')

        # Matières (liaisons classes / module pour le filtrage JS supérieur)
        matieres = (
            Matiere.objects.filter(etablissement=etablissement)
            .select_related('module', 'department')
            .prefetch_related('classes', 'module__classes')
            .order_by('nom')
        )

        matieres_pour_onglets = (
            matieres.filter(actif=True, department__isnull=False)
            if est_superieur
            else matieres
        )

        # Organiser les professeurs par matière (onglets)
        professeurs_par_matiere = {}
        for matiere in matieres_pour_onglets:
            professeurs_principaux = professeurs.filter(matiere_principale=matiere)
            professeurs_secondaires = professeurs.filter(matieres_secondaires=matiere)
            professeurs_par_matiere[matiere] = {
                'principaux': professeurs_principaux,
                'secondaires': professeurs_secondaires,
                'total': professeurs_principaux.count() + professeurs_secondaires.count(),
            }
        
        # Créer les statistiques
        stats = {
            'total_professeurs': professeurs.count(),
            'total_classes': classes.count(),
            'total_matieres': matieres_pour_onglets.count(),
            'professeurs_affectes': 0,  # À calculer
        }
        
        # Calculer les affectations existantes pour l'année scolaire active uniquement
        if annee_scolaire_active:
            for professeur in professeurs:
                if etablissement.type_etablissement == 'primary':
                    # Pour le primaire, vérifier AffectationProfesseurPrimaire
                    if AffectationProfesseurPrimaire.objects.filter(
                        professeur=professeur, 
                        actif=True,
                        annee_scolaire=annee_scolaire_active
                    ).exists():
                        stats['professeurs_affectes'] += 1
                else:
                    # Pour les autres, vérifier AffectationProfesseur
                    if professeur.affectations.filter(
                        actif=True,
                        annee_scolaire=annee_scolaire_active
                    ).exists():
                        stats['professeurs_affectes'] += 1
        
        # Préparer les classes disponibles pour chaque professeur
        professeurs_with_classes = []
        for professeur in professeurs:
            # Pour le primaire, utiliser AffectationProfesseurPrimaire
            if etablissement.type_etablissement == 'primary':
                if annee_scolaire_active:
                    affectations_primaires = AffectationProfesseurPrimaire.objects.filter(
                        professeur=professeur,
                        actif=True,
                        annee_scolaire=annee_scolaire_active
                    ).select_related('classe').prefetch_related('matieres')
                else:
                    # Si pas d'année active, aucune affectation
                    affectations_primaires = AffectationProfesseurPrimaire.objects.none()
                
                affectations_a_afficher = list(affectations_primaires)
                affectations_actives = affectations_primaires.values_list('classe_id', flat=True).distinct()
            else:
                # Pour les autres établissements, utiliser AffectationProfesseur standard
                if annee_scolaire_active:
                    affectations_actives_query = professeur.affectations.filter(
                        actif=True,
                        annee_scolaire=annee_scolaire_active
                    ).select_related(
                        'classe',
                        'classe__department',
                        'classe__academic_level',
                        'matiere',
                        'matiere__module',
                        'matiere__department',
                    )
                else:
                    # Si pas d'année active, aucune affectation
                    affectations_actives_query = professeur.affectations.none()
                
                affectations_a_afficher = list(affectations_actives_query)
                affectations_actives = affectations_actives_query.values_list('classe_id', flat=True).distinct()
            
            # Pour les collèges/lycées, ne pas exclure les classes déjà affectées
            # car un professeur peut être affecté à la même classe avec plusieurs matières
            if etablissement.type_etablissement == 'primary':
                classes_disponibles = classes.exclude(id__in=affectations_actives)
            else:
                classes_disponibles = classes  # Toutes les classes sont disponibles
            
            # Récupérer toutes les matières que le professeur peut enseigner
            matieres_enseignables = []
            if professeur.matiere_principale:
                matieres_enseignables.append(professeur.matiere_principale)
            if professeur.matieres_secondaires.exists():
                matieres_enseignables.extend(list(professeur.matieres_secondaires.all()))
            
            professeurs_with_classes.append({
                'professeur': professeur,
                'classes_disponibles': classes_disponibles,
                'affectations': affectations_a_afficher,
                'matieres_enseignables': matieres_enseignables,
            })
        
        # Supérieur : structure Filière > Module > Matière (pour filtres / cohérence UI)
        matieres_par_module = None
        matieres_structure_superieur = []
        departments_affectation = []
        if est_superieur:
            departments_affectation = list(
                Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
            )
            for dep in departments_affectation:
                modules_dep = (
                    Module.objects.filter(
                        etablissement=etablissement,
                        department=dep,
                        actif=True,
                    )
                    .order_by('ordre', 'nom')
                    .prefetch_related(
                        Prefetch(
                            'matieres',
                            queryset=Matiere.objects.filter(
                                actif=True, department=dep
                            ).order_by('nom'),
                        )
                    )
                )
                for mod in modules_dep:
                    for m in mod.matieres.all():
                        matieres_structure_superieur.append(
                            {'department': dep, 'module': mod, 'matiere': m}
                        )
                for m in (
                    Matiere.objects.filter(
                        etablissement=etablissement,
                        department=dep,
                        module__isnull=True,
                        actif=True,
                    )
                    .order_by('nom')
                ):
                    matieres_structure_superieur.append(
                        {'department': dep, 'module': None, 'matiere': m}
                    )
            # Compat : liste (module, matiere) pour anciens fragments éventuels
            matieres_par_module = [
                (row['module'], row['matiere']) for row in matieres_structure_superieur
            ]

        context = {
            'etablissement': etablissement,
            'professeurs_with_classes': professeurs_with_classes,
            'classes': classes,
            'matieres': matieres,
            'matieres_par_module': matieres_par_module,
            'matieres_structure_superieur': matieres_structure_superieur,
            'departments_affectation': departments_affectation,
            'professeurs_par_matiere': professeurs_par_matiere,
            'stats': stats,
            'type_etablissement': etablissement.type_etablissement,
            'est_superieur': est_superieur,
            'annee_scolaire_active': annee_scolaire_active,
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
                return _affectation_fail(request, 'Professeur ou classe non trouvé.')
            
            # Récupérer la matière si spécifiée
            matiere = None
            if matiere_id:
                try:
                    matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
                except Matiere.DoesNotExist:
                    messages.error(request, 'Matière non trouvée.')
                    return redirect('affectation:affectation_professeurs')
            
            # Récupérer l'année scolaire active
            annee_scolaire_active = get_session_active(request, etablissement)
            
            if not annee_scolaire_active:
                return _affectation_fail(
                    request,
                    "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'effectuer une affectation.",
                )
            
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
                        
                        # Récupérer toutes les affectations primaires existantes pour cette classe et cette année scolaire
                        affectations_existantes = AffectationProfesseurPrimaire.objects.filter(
                            classe=classe,
                            actif=True,
                            annee_scolaire=annee_scolaire_active
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
                            return _affectation_fail(request, message_final)
                    
                    # Pour les écoles primaires, utiliser AffectationProfesseurPrimaire
                    if etablissement.type_etablissement == 'primary':
                        # Vérifier si une affectation primaire existe déjà pour cette année scolaire
                        existing_affectation = AffectationProfesseurPrimaire.objects.filter(
                            professeur=professeur,
                            classe=classe,
                            actif=True,
                            annee_scolaire=annee_scolaire_active
                        ).first()
                        
                        if existing_affectation:
                            messages.warning(request, f"Le professeur {professeur.nom} est déjà affecté à la classe {classe.nom} pour l'année scolaire {annee_scolaire_active.libelle}.")
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
                                    annee_scolaire=annee_scolaire_active,
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
                        # Vérifier que le professeur peut enseigner cette matière
                        matieres_enseignables_ids = []
                        if professeur.matiere_principale:
                            matieres_enseignables_ids.append(professeur.matiere_principale.id)
                        matieres_enseignables_ids.extend(
                            list(professeur.matieres_secondaires.values_list('id', flat=True))
                        )
                        
                        if matiere.id not in matieres_enseignables_ids:
                            messages.error(
                                request,
                                f"Le professeur {professeur.nom} ne peut pas enseigner {matiere.nom}. "
                                f"Cette matière n'est ni sa matière principale ni une de ses matières secondaires."
                            )
                            return redirect('affectation:affectation_professeurs')
                        
                        # Supérieur : même filière + classes cibles (matière ou module / ModuleClasse)
                        if etablissement.type_etablissement == 'superieur':
                            if (
                                matiere.department_id
                                and classe.department_id
                                and matiere.department_id != classe.department_id
                            ):
                                messages.error(
                                    request,
                                    f"La classe {classe.nom} n'appartient pas à la filière de la matière {matiere.nom}. "
                                    f"Veuillez sélectionner une classe de la filière {matiere.department.nom}.",
                                )
                                return redirect('affectation:affectation_professeurs')
                            if not matiere.classe_est_compatible_affectation_superieur(classe):
                                messages.error(
                                    request,
                                    f"La classe {classe.nom} n'est pas rattachée à la matière « {matiere.nom} » "
                                    f"(ni au module associé). Configurez les classes sur la matière ou le module.",
                                )
                                return redirect('affectation:affectation_professeurs')
                        
                        # Vérifier si une affectation existe déjà pour cette année scolaire (actif ou non)
                        existing_affectation = AffectationProfesseur.objects.filter(
                            professeur=professeur,
                            classe=classe,
                            matiere=matiere,
                            annee_scolaire=annee_scolaire_active
                        ).first()
                        
                        if existing_affectation:
                            if existing_affectation.actif:
                                messages.warning(request, f"Le professeur {professeur.nom} est déjà affecté à la classe {classe.nom} pour {matiere.nom} pour l'année scolaire {annee_scolaire_active.libelle}.")
                            else:
                                # Réactiver l'affectation existante
                                existing_affectation.actif = True
                                existing_affectation.statut = statut
                                existing_affectation.annee_scolaire = annee_scolaire_active
                                existing_affectation.save()
                                statut_display = "Professeur Principal" if statut == 'principal' else "Professeur Classique"
                                messages.success(request, f"Affectation réactivée : Professeur {professeur.nom} affecté à la classe {classe.nom} en tant que {statut_display} pour la matière {matiere.nom}")
                        else:
                            try:
                                AffectationProfesseur.objects.create(
                                    professeur=professeur,
                                    classe=classe,
                                    matiere=matiere,
                                    statut=statut,
                                    annee_scolaire=annee_scolaire_active,
                                    actif=True
                                )
                                statut_display = "Professeur Principal" if statut == 'principal' else "Professeur Classique"
                                messages.success(request, f"Professeur {professeur.nom} affecté à la classe {classe.nom} en tant que {statut_display} pour la matière {matiere.nom}")
                            except IntegrityError:
                                # Si une erreur d'intégrité se produit (contrainte unique violée)
                                messages.error(request, f"Le professeur {professeur.nom} est déjà affecté à la classe {classe.nom} pour {matiere.nom} pour l'année scolaire {annee_scolaire_active.libelle}. Veuillez vérifier les affectations existantes.")
                            except ValidationError as e:
                                messages.error(request, str(e))
                                return redirect('affectation:affectation_professeurs')
                        
                elif action == 'remove':
                    # Pour le primaire, supprimer l'affectation primaire
                    if etablissement.type_etablissement == 'primary':
                        affectation = AffectationProfesseurPrimaire.objects.filter(
                            professeur=professeur,
                            classe=classe,
                            actif=True,
                            annee_scolaire=annee_scolaire_active
                        ).first()
                        
                        if not affectation:
                            messages.warning(request, f"Cette affectation n'existe pas pour l'année scolaire active.")
                        else:
                            affectation.actif = False
                            affectation.save()
                            messages.success(request, f"Affectation du professeur {professeur.nom} à la classe {classe.nom} supprimée")
                    else:
                        # Pour les autres, supprimer l'affectation standard
                        # Récupérer la matière si elle est fournie dans le POST pour une suppression plus précise
                        matiere_id_remove = request.POST.get('matiere_id')
                        if matiere_id_remove:
                            affectation = AffectationProfesseur.objects.filter(
                                professeur=professeur,
                                classe=classe,
                                matiere_id=matiere_id_remove,
                                actif=True,
                                annee_scolaire=annee_scolaire_active
                            ).first()
                        else:
                            # Si aucune matière n'est spécifiée, prendre la première affectation trouvée pour cette année scolaire
                            affectation = AffectationProfesseur.objects.filter(
                                professeur=professeur,
                                classe=classe,
                                actif=True,
                                annee_scolaire=annee_scolaire_active
                            ).first()
                        
                        if not affectation:
                            messages.warning(request, f"Cette affectation n'existe pas pour l'année scolaire active.")
                        else:
                            matiere_nom = affectation.matiere.nom if affectation.matiere else "toutes les matières"
                            affectation.actif = False
                            affectation.save()
                            messages.success(request, f"Affectation du professeur {professeur.nom} à la classe {classe.nom} pour {matiere_nom} supprimée")
                else:
                    return _affectation_fail(request, 'Action invalide.')
            
            return _affectation_done(
                request,
                etablissement,
                professeur.id,
                action,
            )
        
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
