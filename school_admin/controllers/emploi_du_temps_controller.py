# school_admin/controllers/emploi_du_temps_controller.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from datetime import datetime
import logging
import re

from ..model.classe_model import Classe
from ..model.emploi_du_temps_model import EmploiDuTemps, CreneauEmploiDuTemps
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.etablissement_model import Etablissement

logger = logging.getLogger(__name__)


class EmploiDuTempsController:
    """
    Contrôleur pour gérer les emplois du temps des classes
    """
    
    @staticmethod
    @login_required
    def liste_emplois_du_temps(request):
        """
        Affiche la liste des classes avec leurs emplois du temps regroupés par catégorie
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
        
        # Récupérer toutes les classes de l'établissement
        classes = Classe.objects.filter(
            etablissement=etablissement,
            actif=True
        ).prefetch_related('emplois_du_temps').order_by('niveau', 'nom')
        
        # Ajouter les informations d'emploi du temps pour chaque classe
        classes_with_edt = []
        for classe in classes:
            # Récupérer l'emploi du temps actif
            emploi_actif = classe.emplois_du_temps.filter(est_actif=True).first()
            
            classe_data = {
                'classe': classe,
                'emploi_du_temps': emploi_actif,
                'a_emploi_du_temps': emploi_actif is not None,
                'nombre_creneaux': emploi_actif.nombre_creneaux if emploi_actif else 0
            }
            classes_with_edt.append(classe_data)
        
        # Regrouper les classes par catégorie (niveau + préfixe)
        classes_grouped = {}
        
        for classe_data in classes_with_edt:
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
                    'total_classes': 0,
                    'classes_avec_edt': 0,
                    'classes_sans_edt': 0
                }
            
            classes_grouped[categorie]['classes'].append(classe_data)
            classes_grouped[categorie]['total_classes'] += 1
            
            if classe_data['a_emploi_du_temps']:
                classes_grouped[categorie]['classes_avec_edt'] += 1
            else:
                classes_grouped[categorie]['classes_sans_edt'] += 1
        
        # Statistiques globales
        stats = {
            'total_classes': classes.count(),
            'classes_avec_edt': sum(1 for c in classes_with_edt if c['a_emploi_du_temps']),
            'classes_sans_edt': sum(1 for c in classes_with_edt if not c['a_emploi_du_temps']),
            'total_categories': len(classes_grouped),
        }
        
        # Année scolaire actuelle
        annee_actuelle = EmploiDuTempsController._get_annee_scolaire_actuelle()
        
        context = {
            'classes': classes,
            'classes_with_edt': classes_with_edt,
            'classes_grouped': classes_grouped,
            'etablissement': etablissement,
            'personnel': personnel,
            'stats': stats,
            'annee_scolaire': annee_actuelle,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/emploi_du_temps/liste_emplois_du_temps.html', context)
    
    @staticmethod
    @login_required
    def detail_emploi_du_temps(request, classe_id):
        """
        Affiche le détail d'un emploi du temps pour une classe
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
        
        # Récupérer la classe
        classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement)
        
        # Récupérer l'emploi du temps actif
        emploi_du_temps = classe.emplois_du_temps.filter(est_actif=True).first()
        
        # Si pas d'emploi du temps, rediriger vers la création
        if not emploi_du_temps:
            messages.info(request, f"Aucun emploi du temps actif pour la classe {classe.nom}. Créez-en un.")
            return redirect('administrateur_etablissement:creer_emploi_du_temps', classe_id=classe.id)
        
        # Récupérer les créneaux organisés par jour
        jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
        creneaux_par_jour = {}
        
        for jour in jours_semaine:
            creneaux_par_jour[jour] = emploi_du_temps.creneaux.filter(
                jour=jour
            ).order_by('heure_debut')
        
        # Récupérer tous les créneaux
        tous_creneaux = emploi_du_temps.creneaux.all().order_by('jour', 'heure_debut')
        
        context = {
            'classe': classe,
            'emploi_du_temps': emploi_du_temps,
            'creneaux_par_jour': creneaux_par_jour,
            'tous_creneaux': tous_creneaux,
            'etablissement': etablissement,
            'personnel': personnel,
            'jours_semaine': jours_semaine,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/emploi_du_temps/detail_emploi_du_temps.html', context)
    
    @staticmethod
    @login_required
    def creer_emploi_du_temps(request, classe_id):
        """
        Crée un nouvel emploi du temps pour une classe
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
        
        # Récupérer la classe
        classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement)
        
        # Vérifier si la classe a déjà un emploi du temps actif
        emploi_existant = classe.emplois_du_temps.filter(est_actif=True).first()
        if emploi_existant:
            messages.warning(request, f"La classe {classe.nom} a déjà un emploi du temps actif.")
            return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe.id)
        
        if request.method == 'POST':
            annee_scolaire = request.POST.get('annee_scolaire', '').strip()
            notes = request.POST.get('notes', '').strip()
            
            # Validation
            if not annee_scolaire:
                annee_scolaire = EmploiDuTempsController._get_annee_scolaire_actuelle()
            
            try:
                with transaction.atomic():
                    # Créer l'emploi du temps
                    emploi_du_temps = EmploiDuTemps.objects.create(
                        classe=classe,
                        annee_scolaire=annee_scolaire,
                        est_actif=True,
                        notes=notes if notes else None
                    )
                    
                    messages.success(request, f"Emploi du temps créé avec succès pour la classe {classe.nom}.")
                    return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe.id)
                    
            except Exception as e:
                logger.error(f"Erreur lors de la création de l'emploi du temps: {str(e)}")
                messages.error(request, "Une erreur est survenue lors de la création de l'emploi du temps.")
        
        # Année scolaire actuelle par défaut
        annee_actuelle = EmploiDuTempsController._get_annee_scolaire_actuelle()
        
        context = {
            'classe': classe,
            'etablissement': etablissement,
            'personnel': personnel,
            'annee_scolaire_defaut': annee_actuelle,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/emploi_du_temps/creer_emploi_du_temps.html', context)
    
    @staticmethod
    @login_required
    def ajouter_creneau(request, emploi_id):
        """
        Ajoute un créneau à un emploi du temps
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
        
        # Récupérer l'emploi du temps
        emploi_du_temps = get_object_or_404(
            EmploiDuTemps.objects.select_related('classe'),
            id=emploi_id,
            classe__etablissement=etablissement
        )
        
        # Récupérer les matières et professeurs
        from ..model.matiere_model import Matiere
        from ..model.professeur_model import Professeur
        from ..model.salle_model import Salle
        
        matieres = Matiere.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
        professeurs = Professeur.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
        salles = Salle.objects.filter(etablissement=etablissement, actif=True).order_by('numero')
        
        form_data = {}
        field_errors = {}
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'jour': request.POST.get('jour', ''),
                'heure_debut': request.POST.get('heure_debut', ''),
                'heure_fin': request.POST.get('heure_fin', ''),
                'matiere_id': request.POST.get('matiere', ''),
                'professeur_id': request.POST.get('professeur', ''),
                'salle_id': request.POST.get('salle', ''),
                'type_cours': request.POST.get('type_cours', 'cours'),
                'notes': request.POST.get('notes', '').strip(),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            if not form_data['jour']:
                field_errors['jour'] = "Le jour est obligatoire."
                is_valid = False
            
            if not form_data['heure_debut']:
                field_errors['heure_debut'] = "L'heure de début est obligatoire."
                is_valid = False
            
            if not form_data['heure_fin']:
                field_errors['heure_fin'] = "L'heure de fin est obligatoire."
                is_valid = False
            
            # Vérification que l'heure de fin est après l'heure de début
            if form_data['heure_debut'] and form_data['heure_fin']:
                from datetime import datetime as dt
                try:
                    debut = dt.strptime(form_data['heure_debut'], '%H:%M').time()
                    fin = dt.strptime(form_data['heure_fin'], '%H:%M').time()
                    
                    if fin <= debut:
                        field_errors['heure_fin'] = "L'heure de fin doit être après l'heure de début."
                        is_valid = False
                except ValueError:
                    field_errors['heure_debut'] = "Format d'heure invalide."
                    is_valid = False
            
            # Vérification des chevauchements
            if is_valid and form_data['jour'] and form_data['heure_debut'] and form_data['heure_fin']:
                chevauchements = CreneauEmploiDuTemps.objects.filter(
                    emploi_du_temps=emploi_du_temps,
                    jour=form_data['jour'],
                    heure_debut__lt=fin,
                    heure_fin__gt=debut
                )
                
                if chevauchements.exists():
                    field_errors['non_field_errors'] = "Ce créneau chevauche un autre créneau existant."
                    is_valid = False
            
            # Si tout est valide, créer le créneau
            if is_valid:
                try:
                    with transaction.atomic():
                        creneau = CreneauEmploiDuTemps(
                            emploi_du_temps=emploi_du_temps,
                            jour=form_data['jour'],
                            heure_debut=form_data['heure_debut'],
                            heure_fin=form_data['heure_fin'],
                            type_cours=form_data['type_cours'],
                            notes=form_data['notes'] if form_data['notes'] else None
                        )
                        
                        # Ajouter la matière si fournie
                        if form_data['matiere_id']:
                            try:
                                matiere = Matiere.objects.get(id=form_data['matiere_id'], etablissement=etablissement)
                                creneau.matiere = matiere
                            except Matiere.DoesNotExist:
                                pass
                        
                        # Ajouter le professeur si fourni
                        if form_data['professeur_id']:
                            try:
                                professeur = Professeur.objects.get(id=form_data['professeur_id'], etablissement=etablissement)
                                creneau.professeur = professeur
                            except Professeur.DoesNotExist:
                                pass
                        
                        # Ajouter la salle si fournie
                        if form_data['salle_id']:
                            try:
                                salle = Salle.objects.get(id=form_data['salle_id'], etablissement=etablissement)
                                creneau.salle = salle
                            except Salle.DoesNotExist:
                                pass
                        
                        creneau.save()
                        
                        messages.success(request, "Le créneau a été ajouté avec succès !")
                        return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=emploi_du_temps.classe.id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout du créneau: {str(e)}")
                    field_errors['non_field_errors'] = "Une erreur est survenue lors de l'ajout du créneau."
        
        context = {
            'emploi_du_temps': emploi_du_temps,
            'classe': emploi_du_temps.classe,
            'etablissement': etablissement,
            'personnel': personnel,
            'matieres': matieres,
            'professeurs': professeurs,
            'salles': salles,
            'form_data': form_data,
            'field_errors': field_errors,
            'jours_choices': CreneauEmploiDuTemps.JOUR_CHOICES,
            'type_cours_choices': CreneauEmploiDuTemps.TYPE_COURS_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/emploi_du_temps/ajouter_creneau.html', context)
    
    @staticmethod
    @login_required
    def modifier_creneau(request, creneau_id):
        """
        Modifie un créneau existant
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
        
        # Récupérer le créneau
        creneau = get_object_or_404(
            CreneauEmploiDuTemps.objects.select_related('emploi_du_temps__classe'),
            id=creneau_id,
            emploi_du_temps__classe__etablissement=etablissement
        )
        
        emploi_du_temps = creneau.emploi_du_temps
        
        # Récupérer les matières et professeurs
        from ..model.matiere_model import Matiere
        from ..model.professeur_model import Professeur
        from ..model.salle_model import Salle
        
        matieres = Matiere.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
        professeurs = Professeur.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
        salles = Salle.objects.filter(etablissement=etablissement, actif=True).order_by('numero')
        
        form_data = {}
        field_errors = {}
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'jour': request.POST.get('jour', ''),
                'heure_debut': request.POST.get('heure_debut', ''),
                'heure_fin': request.POST.get('heure_fin', ''),
                'matiere_id': request.POST.get('matiere', ''),
                'professeur_id': request.POST.get('professeur', ''),
                'salle_id': request.POST.get('salle', ''),
                'type_cours': request.POST.get('type_cours', 'cours'),
                'notes': request.POST.get('notes', '').strip(),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            if not form_data['jour']:
                field_errors['jour'] = "Le jour est obligatoire."
                is_valid = False
            
            if not form_data['heure_debut']:
                field_errors['heure_debut'] = "L'heure de début est obligatoire."
                is_valid = False
            
            if not form_data['heure_fin']:
                field_errors['heure_fin'] = "L'heure de fin est obligatoire."
                is_valid = False
            
            # Vérification que l'heure de fin est après l'heure de début
            if form_data['heure_debut'] and form_data['heure_fin']:
                from datetime import datetime as dt
                try:
                    debut = dt.strptime(form_data['heure_debut'], '%H:%M').time()
                    fin = dt.strptime(form_data['heure_fin'], '%H:%M').time()
                    
                    if fin <= debut:
                        field_errors['heure_fin'] = "L'heure de fin doit être après l'heure de début."
                        is_valid = False
                except ValueError:
                    field_errors['heure_debut'] = "Format d'heure invalide."
                    is_valid = False
            
            # Vérification des chevauchements (en excluant le créneau actuel)
            if is_valid and form_data['jour'] and form_data['heure_debut'] and form_data['heure_fin']:
                chevauchements = CreneauEmploiDuTemps.objects.filter(
                    emploi_du_temps=emploi_du_temps,
                    jour=form_data['jour'],
                    heure_debut__lt=fin,
                    heure_fin__gt=debut
                ).exclude(id=creneau.id)
                
                if chevauchements.exists():
                    field_errors['non_field_errors'] = "Ce créneau chevauche un autre créneau existant."
                    is_valid = False
            
            # Si tout est valide, modifier le créneau
            if is_valid:
                try:
                    with transaction.atomic():
                        creneau.jour = form_data['jour']
                        creneau.heure_debut = form_data['heure_debut']
                        creneau.heure_fin = form_data['heure_fin']
                        creneau.type_cours = form_data['type_cours']
                        creneau.notes = form_data['notes'] if form_data['notes'] else None
                        
                        # Mettre à jour la matière
                        if form_data['matiere_id']:
                            try:
                                matiere = Matiere.objects.get(id=form_data['matiere_id'], etablissement=etablissement)
                                creneau.matiere = matiere
                            except Matiere.DoesNotExist:
                                creneau.matiere = None
                        else:
                            creneau.matiere = None
                        
                        # Mettre à jour le professeur
                        if form_data['professeur_id']:
                            try:
                                professeur = Professeur.objects.get(id=form_data['professeur_id'], etablissement=etablissement)
                                creneau.professeur = professeur
                            except Professeur.DoesNotExist:
                                creneau.professeur = None
                        else:
                            creneau.professeur = None
                        
                        # Mettre à jour la salle
                        if form_data['salle_id']:
                            try:
                                salle = Salle.objects.get(id=form_data['salle_id'], etablissement=etablissement)
                                creneau.salle = salle
                            except Salle.DoesNotExist:
                                creneau.salle = None
                        else:
                            creneau.salle = None
                        
                        creneau.save()
                        
                        messages.success(request, "Le créneau a été modifié avec succès !")
                        return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=emploi_du_temps.classe.id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de la modification du créneau: {str(e)}")
                    field_errors['non_field_errors'] = "Une erreur est survenue lors de la modification du créneau."
        else:
            # Pré-remplir le formulaire avec les données existantes
            form_data = {
                'jour': creneau.jour,
                'heure_debut': creneau.heure_debut.strftime('%H:%M') if creneau.heure_debut else '',
                'heure_fin': creneau.heure_fin.strftime('%H:%M') if creneau.heure_fin else '',
                'matiere_id': creneau.matiere.id if creneau.matiere else '',
                'professeur_id': creneau.professeur.id if creneau.professeur else '',
                'salle_id': creneau.salle.id if creneau.salle else '',
                'type_cours': creneau.type_cours,
                'notes': creneau.notes or '',
            }
        
        context = {
            'creneau': creneau,
            'emploi_du_temps': emploi_du_temps,
            'classe': emploi_du_temps.classe,
            'etablissement': etablissement,
            'personnel': personnel,
            'matieres': matieres,
            'professeurs': professeurs,
            'salles': salles,
            'form_data': form_data,
            'field_errors': field_errors,
            'jours_choices': CreneauEmploiDuTemps.JOUR_CHOICES,
            'type_cours_choices': CreneauEmploiDuTemps.TYPE_COURS_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/emploi_du_temps/modifier_creneau.html', context)
    
    @staticmethod
    @login_required
    def supprimer_creneau(request, creneau_id):
        """
        Supprime un créneau
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, PersonnelAdministratif):
            etablissement = request.user.etablissement
        elif isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        # Récupérer le créneau
        creneau = get_object_or_404(
            CreneauEmploiDuTemps.objects.select_related('emploi_du_temps__classe'),
            id=creneau_id,
            emploi_du_temps__classe__etablissement=etablissement
        )
        
        classe_id = creneau.emploi_du_temps.classe.id
        
        if request.method == 'POST':
            try:
                creneau.delete()
                messages.success(request, "Le créneau a été supprimé avec succès.")
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du créneau: {str(e)}")
                messages.error(request, "Une erreur est survenue lors de la suppression du créneau.")
        
        return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe_id)
    
    @staticmethod
    def _get_annee_scolaire_actuelle():
        """
        Détermine l'année scolaire actuelle
        """
        maintenant = datetime.now()
        annee_actuelle = maintenant.year
        mois_actuel = maintenant.month
        
        # Si on est entre septembre et décembre, année scolaire = année actuelle - année suivante
        # Sinon, année scolaire = année précédente - année actuelle
        if mois_actuel >= 9:
            return f"{annee_actuelle}-{annee_actuelle + 1}"
        else:
            return f"{annee_actuelle - 1}-{annee_actuelle}"

