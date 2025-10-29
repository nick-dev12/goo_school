# school_admin/controllers/emploi_du_temps_controller.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, models
from django.utils import timezone
from datetime import datetime, timedelta
import logging
import re

# Configuration icônes et couleurs des matières
MATIERES_CONFIG = {
    'Mathématiques': ('calculator', '#3b82f6'),
    'Mathématiques Approfondies': ('calculator', '#3b82f6'),
    'Français': ('book-open', '#10b981'),
    'Anglais': ('globe', '#8b5cf6'),
    'Histoire': ('landmark', '#f59e0b'),
    'Géographie': ('map-marked-alt', '#14b8a6'),
    'Physique-Chimie': ('flask', '#ec4899'),
    'Sciences Physiques': ('flask', '#ec4899'),
    'Sciences Naturelles': ('microscope', '#22c55e'),
    'SVT': ('leaf', '#22c55e'),
    'EPS': ('running', '#ef4444'),
    'Éducation Civique': ('balance-scale', '#6366f1'),
    'Philosophie': ('brain', '#6366f1'),
    'Sciences Économiques': ('chart-line', '#f43f5e'),
    'Arabe': ('language', '#84cc16'),
    'Wolof': ('language', '#84cc16'),
    'Pulaar': ('language', '#84cc16'),
    'Informatique': ('laptop-code', '#06b6d4'),
    'Musique': ('music', '#a855f7'),
    'Arts': ('palette', '#f97316'),
}

def get_matiere_config(matiere_nom):
    """Retourne (icône, couleur) pour une matière"""
    if not matiere_nom:
        return ('book', '#64748b')
    
    # Recherche exacte
    if matiere_nom in MATIERES_CONFIG:
        return MATIERES_CONFIG[matiere_nom]
    
    # Recherche partielle
    for key, config in MATIERES_CONFIG.items():
        if key.lower() in matiere_nom.lower():
            return config
    
    return ('book', '#64748b')

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
        
        # Récupérer tous les créneaux
        tous_creneaux = emploi_du_temps.creneaux.all().order_by('jour', 'heure_debut')
        
        # Organiser les créneaux par période et par jour
        from ..model.configuration_horaire_model import ConfigurationHoraire, PeriodeEtablissement
        
        # Récupérer la configuration horaire de l'établissement
        config_horaire = ConfigurationHoraire.objects.filter(etablissement=etablissement, actif=True).first()
        
        periodes_affichage = []
        
        if config_horaire:
            # Utiliser les périodes de l'établissement
            periodes = config_horaire.periodes.filter(actif=True).order_by('ordre')
            
            # Créer un dictionnaire pour regrouper les créneaux par groupe_creneau
            creneaux_groupes = {}
            for creneau in tous_creneaux:
                if creneau.groupe_creneau:
                    if creneau.groupe_creneau not in creneaux_groupes:
                        creneaux_groupes[creneau.groupe_creneau] = []
                    creneaux_groupes[creneau.groupe_creneau].append(creneau)
            
            for periode in periodes:
                periode_info = {
                    'nom': periode.nom,
                    'heure_debut': periode.heure_debut,
                    'heure_fin': periode.heure_fin,
                    'duree': periode.duree_minutes,
                    'est_pause': periode.est_pause,
                    'type_periode': periode.type_periode,
                    'creneaux_par_jour': {},
                    'skip_render': {},  # Pour savoir si on doit skip le rendu (cellule fusionnée)
                    'rowspans': {}  # Pour stocker les rowspans par jour
                }
                
                # Pour chaque jour, trouver le créneau correspondant à cette période
                for jour in jours_semaine:
                    periode_info['skip_render'][jour] = False
                    periode_info['rowspans'][jour] = 1  # Par défaut, pas de fusion
                    
                    if periode.est_pause:
                        # C'est une pause: créer un créneau virtuel
                        periode_info['creneaux_par_jour'][jour] = {
                            'est_pause': True,
                            'est_virtual': True,  # Flag pour identifier un dict
                            'nom_pause': periode.nom,
                            'type_periode': periode.type_periode
                        }
                    else:
                        # Chercher un créneau qui utilise cette période
                        creneau = tous_creneaux.filter(
                            jour=jour,
                            periode_etablissement=periode
                        ).first()
                        
                        if creneau:
                            # Pour les créneaux groupés, on affiche le premier créneau dans toutes les périodes du groupe
                            if creneau.groupe_creneau:
                                groupe_creneaux = creneaux_groupes.get(creneau.groupe_creneau, [])
                                # Filtrer pour le même jour
                                groupe_creneaux_jour = [c for c in groupe_creneaux if c.jour == jour]
                                groupe_creneaux_jour.sort(key=lambda c: c.periode_etablissement.ordre)
                                
                                # Toujours afficher le premier créneau du groupe (pas de skip)
                                if groupe_creneaux_jour:
                                    creneau = groupe_creneaux_jour[0]
                            
                            # Ajouter icône et couleur au créneau
                            matiere_nom = creneau.matiere.nom if creneau.matiere else "Sans matière"
                            icone, couleur = get_matiere_config(matiere_nom)
                            creneau.matiere_icone = icone
                            creneau.matiere_couleur = couleur
                            
                            periode_info['creneaux_par_jour'][jour] = creneau
                        else:
                            periode_info['creneaux_par_jour'][jour] = None
                
                periodes_affichage.append(periode_info)
        else:
            # Mode compatibilité: regrouper les créneaux par horaires
            # Extraire toutes les plages horaires uniques
            horaires_uniques = set()
            for creneau in tous_creneaux:
                horaires_uniques.add((creneau.get_heure_debut(), creneau.get_heure_fin()))
            
            # Trier les horaires
            horaires_tries = sorted(list(horaires_uniques))
            
            for heure_debut, heure_fin in horaires_tries:
                from datetime import datetime
                debut = datetime.combine(datetime.today(), heure_debut)
                fin = datetime.combine(datetime.today(), heure_fin)
                duree = int((fin - debut).total_seconds() / 60)
                
                periode_info = {
                    'nom': f"{heure_debut.strftime('%H:%M')}-{heure_fin.strftime('%H:%M')}",
                    'heure_debut': heure_debut,
                    'heure_fin': heure_fin,
                    'duree': duree,
                    'est_pause': False,
                    'creneaux_par_jour': {}
                }
                
                for jour in jours_semaine:
                    creneau = tous_creneaux.filter(
                        jour=jour,
                        heure_debut=heure_debut,
                        heure_fin=heure_fin
                    ).first()
                    
                    periode_info['creneaux_par_jour'][jour] = creneau
                
                periodes_affichage.append(periode_info)
        
        # Récupérer les créneaux d'examens pour cette classe
        from ..model.session_examen_model import SessionExamen
        from ..model.creneau_examen_model import CreneauExamen
        
        # Trouver les sessions d'examens qui incluent cette classe
        sessions_examens = SessionExamen.objects.filter(
            etablissement=etablissement,
            classes=classe,
            actif=True
        ).select_related('periode').prefetch_related('matieres', 'classes')
        
        # Récupérer tous les créneaux d'examens liés à ces sessions
        creneaux_examens = CreneauExamen.objects.filter(
            session_examen__in=sessions_examens,
            actif=True
        ).select_related('session_examen', 'matiere', 'surveillant', 'salle').order_by('date_examen', 'heure_debut')
        
        # Organiser les créneaux d'examens en grille comme dans emploi_du_temps_examens
        heures_examens_uniques = set()
        dates_examens_uniques = set()
        
        # Ajouter toutes les dates de la période d'examen
        for session in sessions_examens:
            if session.date_debut and session.date_fin:
                date_courante = session.date_debut
                while date_courante <= session.date_fin:
                    dates_examens_uniques.add(date_courante)
                    date_courante += timedelta(days=1)
        
        # Ajouter les heures des créneaux existants
        for creneau in creneaux_examens:
            dates_examens_uniques.add(creneau.date_examen)
            heures_examens_uniques.add((creneau.heure_debut, creneau.heure_fin))
        
        dates_examens_triees = sorted(list(dates_examens_uniques))
        heures_examens_triees = sorted(list(heures_examens_uniques), key=lambda x: x[0])
        
        plages_horaires_examens = []
        if heures_examens_triees:
            heure_min = min([h[0] for h in heures_examens_triees])
            heure_max = max([h[1] for h in heures_examens_triees])
            
            from datetime import datetime, time
            heure_actuelle = heure_min
            while heure_actuelle < heure_max:
                dt = datetime.combine(datetime.today(), heure_actuelle)
                dt_suivant = dt + timedelta(hours=1)
                heure_suivante = dt_suivant.time()
                
                plages_horaires_examens.append({
                    'debut': heure_actuelle,
                    'fin': heure_suivante,
                    'label': f"{heure_actuelle.strftime('%H:%M')} - {heure_suivante.strftime('%H:%M')}"
                })
                heure_actuelle = heure_suivante
        
        grille_emploi_examens = {}
        jours_semaine_fr = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
        
        for date in dates_examens_triees:
            jour_semaine = jours_semaine_fr[date.weekday()]
            grille_emploi_examens[date] = {
                'date_obj': date,
                'jour_semaine': jour_semaine,
                'plages': {}
            }
            
            for plage in plages_horaires_examens:
                grille_emploi_examens[date]['plages'][plage['label']] = []
        
        cellules_masquees_examens = {}
        
        for creneau in creneaux_examens:
            date = creneau.date_examen
            
            debut_dt = datetime.combine(datetime.today(), creneau.heure_debut)
            fin_dt = datetime.combine(datetime.today(), creneau.heure_fin)
            duree_heures = (fin_dt - debut_dt).total_seconds() / 3600
            rowspan = int(duree_heures)
            
            plage_index = -1
            for idx, plage in enumerate(plages_horaires_examens):
                if plage['debut'] == creneau.heure_debut:
                    plage_index = idx
                    if date in grille_emploi_examens:
                        grille_emploi_examens[date]['plages'][plage['label']].append({
                            'creneau': creneau,
                            'rowspan': rowspan
                        })
                    
                    if date not in cellules_masquees_examens:
                        cellules_masquees_examens[date] = {}
                    
                    for i in range(1, rowspan):
                        if plage_index + i < len(plages_horaires_examens):
                            plage_suivante = plages_horaires_examens[plage_index + i]
                            cellules_masquees_examens[date][plage_suivante['label']] = True
                    break
        
        context = {
            'classe': classe,
            'emploi_du_temps': emploi_du_temps,
            'periodes_affichage': periodes_affichage,
            'tous_creneaux': tous_creneaux,
            'etablissement': etablissement,
            'personnel': personnel,
            'jours_semaine': jours_semaine,
            'config_horaire': config_horaire,
            # Données pour l'emploi du temps des examens
            'sessions_examens': sessions_examens,
            'creneaux_examens': creneaux_examens,
            'grille_emploi_examens': grille_emploi_examens,
            'plages_horaires_examens': plages_horaires_examens,
            'dates_examens_triees': dates_examens_triees,
            'cellules_masquees_examens': cellules_masquees_examens,
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
        
        # Récupérer les périodes de l'établissement
        from ..model.configuration_horaire_model import ConfigurationHoraire, PeriodeEtablissement
        config_horaire = ConfigurationHoraire.objects.filter(etablissement=etablissement, actif=True).first()
        periodes_etablissement = []
        if config_horaire:
            periodes_etablissement = PeriodeEtablissement.objects.filter(
                configuration_horaire=config_horaire,
                actif=True,
                type_periode='cours'  # Seulement les périodes de cours
            ).order_by('ordre')
        
        form_data = {}
        field_errors = {}
        
        if request.method == 'POST':
            # Récupération des données (periodes_etablissement est maintenant une liste)
            form_data = {
                'jour': request.POST.get('jour', ''),
                'periodes_etablissement_ids': request.POST.getlist('periodes_etablissement'),
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
            
            if not form_data['periodes_etablissement_ids']:
                field_errors['periodes_etablissement'] = "Vous devez sélectionner au moins une période."
                is_valid = False
            
            # Récupérer les périodes sélectionnées
            periodes_selectionnees = []
            if form_data['periodes_etablissement_ids']:
                try:
                    periodes_selectionnees = list(PeriodeEtablissement.objects.filter(
                        id__in=form_data['periodes_etablissement_ids'],
                        configuration_horaire__etablissement=etablissement,
                        actif=True
                    ).order_by('ordre'))
                    
                    if len(periodes_selectionnees) != len(form_data['periodes_etablissement_ids']):
                        field_errors['periodes_etablissement'] = "Certaines périodes sélectionnées sont invalides."
                        is_valid = False
                except Exception:
                    field_errors['periodes_etablissement'] = "Erreur lors de la récupération des périodes."
                    is_valid = False
            
            # Vérification des chevauchements pour chaque période
            if is_valid and form_data['jour'] and periodes_selectionnees:
                for periode in periodes_selectionnees:
                    chevauchements = CreneauEmploiDuTemps.objects.filter(
                        emploi_du_temps=emploi_du_temps,
                        jour=form_data['jour'],
                        periode_etablissement=periode
                    )
                    
                    if chevauchements.exists():
                        field_errors['non_field_errors'] = f"Un créneau existe déjà pour la période {periode.nom} le {form_data['jour']}."
                        is_valid = False
                        break
            
            # Si tout est valide, créer les créneaux
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer un identifiant unique pour le groupe de créneaux si plusieurs périodes
                        import uuid
                        groupe_creneau = None
                        if len(periodes_selectionnees) > 1:
                            groupe_creneau = str(uuid.uuid4())[:8]
                        
                        # Récupérer les objets communs une seule fois
                        matiere = None
                        if form_data['matiere_id']:
                            try:
                                matiere = Matiere.objects.get(id=form_data['matiere_id'], etablissement=etablissement)
                            except Matiere.DoesNotExist:
                                pass
                        
                        professeur = None
                        if form_data['professeur_id']:
                            try:
                                professeur = Professeur.objects.get(id=form_data['professeur_id'], etablissement=etablissement)
                            except Professeur.DoesNotExist:
                                pass
                        
                        salle = None
                        if form_data['salle_id']:
                            try:
                                salle = Salle.objects.get(id=form_data['salle_id'], etablissement=etablissement)
                            except Salle.DoesNotExist:
                                pass
                        
                        # Créer un créneau pour chaque période sélectionnée
                        for periode in periodes_selectionnees:
                            creneau = CreneauEmploiDuTemps(
                                emploi_du_temps=emploi_du_temps,
                                jour=form_data['jour'],
                                periode_etablissement=periode,
                                groupe_creneau=groupe_creneau,
                                type_cours=form_data['type_cours'],
                                notes=form_data['notes'] if form_data['notes'] else None,
                                matiere=matiere,
                                professeur=professeur,
                                salle=salle
                            )
                            creneau.save()
                        
                        nb_creneaux = len(periodes_selectionnees)
                        if nb_creneaux == 1:
                            messages.success(request, "Le créneau a été ajouté avec succès !")
                        else:
                            messages.success(request, f"{nb_creneaux} créneaux consécutifs ont été ajoutés avec succès !")
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
            'periodes_etablissement': periodes_etablissement,
            'config_horaire': config_horaire,
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

