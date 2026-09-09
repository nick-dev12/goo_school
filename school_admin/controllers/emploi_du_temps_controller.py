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
from ..utils.session_utils import get_session_active

logger = logging.getLogger(__name__)


def _emploi_live_response(request, etablissement, classe_id, emploi_id=None, message=None, field_errors=None, form_data=None):
    from django.urls import reverse
    from ..services.realtime_helpers import wants_json_response, json_ok, json_fail, emit_live
    from ..services.live_serializers import serialize_emploi_refresh_item

    item = serialize_emploi_refresh_item(classe_id, emploi_id)

    if field_errors:
        if wants_json_response(request):
            return json_fail(field_errors=field_errors, message=message)
        if form_data is not None:
            request.session['creneau_form_data'] = form_data
            request.session['creneau_field_errors'] = field_errors
        return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe_id)

    emit_live(
        etablissement.id,
        'emploi.mise_a_jour',
        {'event': 'emploi.mise_a_jour', 'item': item},
    )
    if wants_json_response(request):
        return json_ok(message=message or 'Emploi du temps mis à jour.', item=item)
    if message:
        messages.success(request, message)
    return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe_id)


class EmploiDuTempsController:
    """
    Contrôleur pour gérer les emplois du temps des classes
    """

    @staticmethod
    def _matieres_pour_emploi_du_temps_classe(etablissement, classe):
        """
        Matières proposées pour ajouter/modifier un créneau d'emploi du temps.

        - Hors supérieur : toutes les matières actives de l'établissement.
        - Supérieur : uniquement les matières liées à la classe (M2M ``matiere.classes``
          ou classes du module via ``module.classes``), comme pour les affectations.
        """
        from django.db.models import Q
        from ..model.matiere_model import Matiere

        base = Matiere.objects.filter(etablissement=etablissement, actif=True)
        if getattr(etablissement, 'type_etablissement', None) != 'superieur':
            return base.order_by('nom')

        return (
            base.filter(Q(classes=classe) | Q(module__classes=classe))
            .distinct()
            .order_by('nom')
        )

    @staticmethod
    def _matiere_est_autorisee_emploi_superieur(etablissement, classe, matiere):
        """Vérifie qu'une matière POST est bien dans le périmètre classe (supérieur)."""
        if matiere is None:
            return True
        if getattr(etablissement, 'type_etablissement', None) != 'superieur':
            return True
        return EmploiDuTempsController._matieres_pour_emploi_du_temps_classe(
            etablissement, classe
        ).filter(pk=matiere.pk).exists()

    @staticmethod
    @login_required
    def liste_emplois_du_temps(request):
        """
        Affiche la liste des classes avec leurs emplois du temps regroupés par catégorie
        Affiche uniquement les emplois du temps de l'année scolaire active
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
        
        # Récupérer toutes les classes de l'établissement (academic_level pour libellé niveau complet)
        classes = Classe.objects.filter(
            etablissement=etablissement,
            actif=True
        ).select_related('academic_level', 'department').prefetch_related('emplois_du_temps').order_by('niveau', 'nom')
        
        # Ajouter les informations d'emploi du temps pour chaque classe
        classes_with_edt = []
        for classe in classes:
            # Récupérer l'emploi du temps actif pour l'année scolaire active uniquement
            if annee_scolaire_active:
                emploi_actif = classe.emplois_du_temps.filter(
                    est_actif=True,
                    annee_scolaire_fk=annee_scolaire_active
                ).first()
            else:
                # Si pas d'année active, aucun emploi du temps
                emploi_actif = None
            
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
        
        context = {
            'is_directeur': isinstance(request.user, Etablissement),
            'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
            'personnel': personnel,
            'classes': classes,
            'classes_with_edt': classes_with_edt,
            'classes_grouped': classes_grouped,
            'etablissement': etablissement,
            'stats': stats,
            'annee_scolaire_active': annee_scolaire_active,
            'annee_scolaire': annee_scolaire_active.libelle if annee_scolaire_active else '',
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
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = get_session_active(request, etablissement)
        
        if not annee_scolaire_active:
            messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de consulter un emploi du temps.")
            return redirect('administrateur_etablissement:liste_emplois_du_temps')
        
        # Récupérer la classe (relations pour libellé niveau LMD / académique)
        classe = get_object_or_404(
            Classe.objects.select_related('academic_level', 'department'),
            id=classe_id,
            etablissement=etablissement,
        )
        
        # Récupérer l'emploi du temps actif pour l'année scolaire active uniquement
        emploi_du_temps = classe.emplois_du_temps.filter(
            est_actif=True,
            annee_scolaire_fk=annee_scolaire_active
        ).first()
        
        # Si pas d'emploi du temps, rediriger vers la création
        if not emploi_du_temps:
            messages.info(request, f"Aucun emploi du temps actif pour la classe {classe.nom} pour l'année scolaire {annee_scolaire_active.libelle}. Créez-en un.")
            return redirect('administrateur_etablissement:creer_emploi_du_temps', classe_id=classe.id)
        
        # Récupérer les créneaux organisés par jour (comme pour les examens)
        jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
        
        # Récupérer tous les créneaux triés par jour et heure de début
        tous_creneaux = emploi_du_temps.creneaux.all().order_by('jour', 'heure_debut')
        
        # Organiser les créneaux en grille comme pour les examens
        # Créer une plage horaire pour chaque heure de début unique des créneaux
        heures_debut_uniques = sorted(list(set(creneau.heure_debut for creneau in tous_creneaux)))
        
        plages_horaires = []
        for heure_debut in heures_debut_uniques:
            # Pour chaque heure de début, créer une plage de 1h
            dt_debut = datetime.combine(datetime.today(), heure_debut)
            dt_fin = dt_debut + timedelta(hours=1)
            heure_fin = dt_fin.time()
            
            plages_horaires.append({
                'debut': heure_debut,
                'fin': heure_fin,
                'label': f"{heure_debut.strftime('%H:%M')} - {heure_fin.strftime('%H:%M')}"
            })
        
        # Trier les plages horaires par heure de début (plus tôt en haut)
        plages_horaires.sort(key=lambda p: p['debut'])
        
        # Créer la grille d'emploi du temps (structure similaire aux examens)
        grille_emploi = {}
        for jour in jours_semaine:
            grille_emploi[jour] = {
                'jour': jour,
                'plages': {}
            }
            for plage in plages_horaires:
                grille_emploi[jour]['plages'][plage['label']] = []
        
        # Remplir la grille avec les créneaux
        cellules_masquees = {}
        for creneau in tous_creneaux:
            jour = creneau.jour
            
            # Trouver la plage horaire correspondante (celle qui commence exactement à l'heure de début du créneau)
            plage_index = -1
            for idx, plage in enumerate(plages_horaires):
                # Le créneau commence exactement à cette plage horaire
                if plage['debut'] == creneau.heure_debut:
                    plage_index = idx
                    
                    # Calculer le rowspan (nombre de plages horaires que le créneau occupe)
                    # On compte combien de plages horaires sont couvertes par le créneau
                    rowspan = 1
                    creneau_fin = creneau.heure_fin
                    
                    # Parcourir les plages suivantes pour voir combien sont couvertes
                    for i in range(1, len(plages_horaires) - plage_index):
                        if plage_index + i < len(plages_horaires):
                            plage_suivante = plages_horaires[plage_index + i]
                            # Si le créneau se termine après le début de la plage suivante, il couvre cette plage
                            if creneau_fin > plage_suivante['debut']:
                                rowspan += 1
                            else:
                                break
                    
                    if jour in grille_emploi:
                        # Ajouter icône et couleur au créneau
                        matiere_nom = creneau.matiere.nom if creneau.matiere else "Sans matière"
                        icone, couleur = get_matiere_config(matiere_nom)
                        creneau.matiere_icone = icone
                        creneau.matiere_couleur = couleur
                        
                        grille_emploi[jour]['plages'][plage['label']].append({
                            'creneau': creneau,
                            'rowspan': rowspan
                        })
                    
                    # Marquer les cellules suivantes comme masquées
                    if jour not in cellules_masquees:
                        cellules_masquees[jour] = {}
                    
                    for i in range(1, rowspan):
                        if plage_index + i < len(plages_horaires):
                            plage_suivante = plages_horaires[plage_index + i]
                            cellules_masquees[jour][plage_suivante['label']] = True
                    break
        
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
        
        # Récupérer les données nécessaires pour le formulaire d'ajout de créneau
        from ..model.professeur_model import Professeur
        from ..model.salle_model import Salle
        
        matieres = EmploiDuTempsController._matieres_pour_emploi_du_temps_classe(etablissement, classe)
        salles = Salle.objects.filter(etablissement=etablissement, actif=True).order_by('numero')
        professeurs_options, afficher_matiere_prof = EmploiDuTempsController._get_professeurs_options(classe, annee_scolaire_active)

        creneaux_par_jour = {j: [] for j in jours_semaine}
        for cr in tous_creneaux:
            if cr.jour in creneaux_par_jour:
                creneaux_par_jour[cr.jour].append(cr)
        
        # Récupérer les erreurs et données du formulaire depuis la session (si présentes)
        creneau_form_data = request.session.pop('creneau_form_data', {})
        creneau_field_errors = request.session.pop('creneau_field_errors', {})
        show_modal_creneau = bool(creneau_form_data or creneau_field_errors)

        modifier_creneau_form_data = request.session.pop('modifier_creneau_form_data', {})
        modifier_creneau_field_errors = request.session.pop('modifier_creneau_field_errors', {})
        modifier_creneau_id = request.session.pop('modifier_creneau_id', None)
        if modifier_creneau_id:
            from ..model.matiere_model import Matiere
            try:
                cr_mod = CreneauEmploiDuTemps.objects.select_related('matiere').get(
                    pk=modifier_creneau_id,
                    emploi_du_temps=emploi_du_temps,
                )
                if (
                    getattr(etablissement, 'type_etablissement', None) == 'superieur'
                    and cr_mod.matiere_id
                    and not matieres.filter(pk=cr_mod.matiere_id).exists()
                ):
                    matieres = (
                        matieres | Matiere.objects.filter(pk=cr_mod.matiere_id, etablissement=etablissement)
                    ).distinct().order_by('nom')
            except CreneauEmploiDuTemps.DoesNotExist:
                modifier_creneau_id = None
                modifier_creneau_form_data = {}
                modifier_creneau_field_errors = {}

        show_modal_modifier_creneau = bool(
            modifier_creneau_id and (modifier_creneau_form_data or modifier_creneau_field_errors)
        )
        
        context = {
            'classe': classe,
            'emploi_du_temps': emploi_du_temps,
            'tous_creneaux': tous_creneaux,
            'etablissement': etablissement,
            'personnel': personnel,
            'is_directeur': isinstance(request.user, Etablissement),
            'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
            'jours_semaine': jours_semaine,
            'statut_publication': emploi_du_temps.get_statut_publication_display(),
            'date_publication': emploi_du_temps.date_publication,
            'peut_publier': not emploi_du_temps.est_publie,
            'doit_republier': emploi_du_temps.doit_republier,
            # Données pour l'emploi du temps des classes (structure comme les examens)
            'grille_emploi': grille_emploi,
            'plages_horaires': plages_horaires,
            'cellules_masquees': cellules_masquees,
            # Données pour l'emploi du temps des examens
            'sessions_examens': sessions_examens,
            'creneaux_examens': creneaux_examens,
            'grille_emploi_examens': grille_emploi_examens,
            'plages_horaires_examens': plages_horaires_examens,
            'dates_examens_triees': dates_examens_triees,
            'cellules_masquees_examens': cellules_masquees_examens,
            # Données pour le formulaire d'ajout de créneau
            'matieres': matieres,
            'professeurs_options': professeurs_options,
            'afficher_matiere_prof': afficher_matiere_prof,
            'salles': salles,
            'jours_choices': CreneauEmploiDuTemps.JOUR_CHOICES,
            'annee_scolaire_active': annee_scolaire_active,
            # Données pour le formulaire d'ajout de créneau (en cas d'erreur)
            'creneau_form_data': creneau_form_data,
            'creneau_field_errors': creneau_field_errors,
            'show_modal_creneau': show_modal_creneau,
            'creneaux_par_jour': creneaux_par_jour,
            'modifier_creneau_form_data': modifier_creneau_form_data,
            'modifier_creneau_field_errors': modifier_creneau_field_errors,
            'modifier_creneau_id': modifier_creneau_id,
            'show_modal_modifier_creneau': show_modal_modifier_creneau,
            'type_cours_choices': CreneauEmploiDuTemps.TYPE_COURS_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/emploi_du_temps/detail_emploi_du_temps.html', context)
    
    @staticmethod
    @login_required
    def imprimer_emploi_du_temps(request, classe_id):
        """
        Affiche la page d'impression de l'emploi du temps pour une classe
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
            messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de consulter un emploi du temps.")
            return redirect('administrateur_etablissement:liste_emplois_du_temps')
        
        # Récupérer la classe (relations pour libellé niveau complet à l'impression)
        classe = get_object_or_404(
            Classe.objects.select_related('academic_level', 'department'),
            id=classe_id,
            etablissement=etablissement,
        )
        
        # Récupérer l'emploi du temps actif pour l'année scolaire active uniquement
        emploi_du_temps = classe.emplois_du_temps.filter(
            est_actif=True,
            annee_scolaire_fk=annee_scolaire_active
        ).first()
        
        # Si pas d'emploi du temps, rediriger vers la création
        if not emploi_du_temps:
            messages.info(request, f"Aucun emploi du temps actif pour la classe {classe.nom} pour l'année scolaire {annee_scolaire_active.libelle}.")
            return redirect('administrateur_etablissement:liste_emplois_du_temps')
        
        # Récupérer les créneaux organisés par jour (comme pour les examens)
        jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
        
        # Récupérer tous les créneaux triés par jour et heure de début
        tous_creneaux = emploi_du_temps.creneaux.all().order_by('jour', 'heure_debut')
        
        # Organiser les créneaux en grille comme pour les examens
        # Créer une plage horaire pour chaque heure de début unique des créneaux
        heures_debut_uniques = sorted(list(set(creneau.heure_debut for creneau in tous_creneaux)))
        
        plages_horaires = []
        for heure_debut in heures_debut_uniques:
            # Pour chaque heure de début, créer une plage de 1h
            dt_debut = datetime.combine(datetime.today(), heure_debut)
            dt_fin = dt_debut + timedelta(hours=1)
            heure_fin = dt_fin.time()
            
            plages_horaires.append({
                'debut': heure_debut,
                'fin': heure_fin,
                'label': f"{heure_debut.strftime('%H:%M')} - {heure_fin.strftime('%H:%M')}"
            })
        
        # Trier les plages horaires par heure de début (plus tôt en haut)
        plages_horaires.sort(key=lambda p: p['debut'])
        
        # Créer la grille d'emploi du temps (structure similaire aux examens)
        grille_emploi = {}
        for jour in jours_semaine:
            grille_emploi[jour] = {
                'jour': jour,
                'plages': {}
            }
            for plage in plages_horaires:
                grille_emploi[jour]['plages'][plage['label']] = []
        
        # Remplir la grille avec les créneaux
        cellules_masquees = {}
        for creneau in tous_creneaux:
            jour = creneau.jour
            
            # Trouver la plage horaire correspondante (celle qui commence exactement à l'heure de début du créneau)
            plage_index = -1
            for idx, plage in enumerate(plages_horaires):
                # Le créneau commence exactement à cette plage horaire
                if plage['debut'] == creneau.heure_debut:
                    plage_index = idx
                    
                    # Calculer le rowspan (nombre de plages horaires que le créneau occupe)
                    # On compte combien de plages horaires sont couvertes par le créneau
                    rowspan = 1
                    creneau_fin = creneau.heure_fin
                    
                    # Parcourir les plages suivantes pour voir combien sont couvertes
                    for i in range(1, len(plages_horaires) - plage_index):
                        if plage_index + i < len(plages_horaires):
                            plage_suivante = plages_horaires[plage_index + i]
                            # Si le créneau se termine après le début de la plage suivante, il couvre cette plage
                            if creneau_fin > plage_suivante['debut']:
                                rowspan += 1
                            else:
                                break
                    
                    if jour in grille_emploi:
                        # Ajouter icône et couleur au créneau
                        matiere_nom = creneau.matiere.nom if creneau.matiere else "Sans matière"
                        icone, couleur = get_matiere_config(matiere_nom)
                        creneau.matiere_icone = icone
                        creneau.matiere_couleur = couleur
                        
                        grille_emploi[jour]['plages'][plage['label']].append({
                            'creneau': creneau,
                            'rowspan': rowspan
                        })
                    
                    # Marquer les cellules suivantes comme masquées
                    if jour not in cellules_masquees:
                        cellules_masquees[jour] = {}
                    
                    for i in range(1, rowspan):
                        if plage_index + i < len(plages_horaires):
                            plage_suivante = plages_horaires[plage_index + i]
                            cellules_masquees[jour][plage_suivante['label']] = True
                    break
        
        context = {
            'classe': classe,
            'emploi_du_temps': emploi_du_temps,
            'tous_creneaux': tous_creneaux,
            'etablissement': etablissement,
            'jours_semaine': jours_semaine,
            'grille_emploi': grille_emploi,
            'plages_horaires': plages_horaires,
            'cellules_masquees': cellules_masquees,
            'annee_scolaire_active': annee_scolaire_active,
        }
        
        return render(request, 'school_admin/directeur/administrateur_etablissement/emploi_du_temps/imprimer_emploi_du_temps.html', context)
    
    @staticmethod
    @login_required
    def publier_emploi_du_temps(request, emploi_id):
        """
        Publie un emploi du temps et déclenche les notifications.
        """
        if request.method != 'POST':
            messages.error(request, "Méthode non autorisée.")
            return redirect('administrateur_etablissement:liste_emplois_du_temps')

        # Vérifier les droits
        if isinstance(request.user, PersonnelAdministratif):
            etablissement = request.user.etablissement
        elif isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')

        emploi = get_object_or_404(
            EmploiDuTemps.objects.select_related('classe'),
            id=emploi_id,
            classe__etablissement=etablissement,
        )

        deja_publie_precedemment = emploi.date_publication is not None

        if emploi.est_publie:
            messages.info(request, "Cet emploi du temps est déjà publié.")
        else:
            emploi.publier()
            if deja_publie_precedemment:
                messages.success(
                    request,
                    f"L'emploi du temps de la classe {emploi.classe.nom} a été republié. Les notifications sont en cours d'envoi pour informer les élèves, les parents et les enseignants.",
                )
            else:
                messages.success(
                request,
                f"L'emploi du temps de la classe {emploi.classe.nom} a été publié et les notifications sont en cours d'envoi.",
            )

        from ..services.realtime_helpers import wants_json_response, json_ok, emit_live
        from ..services.live_serializers import serialize_emploi_refresh_item
        item = serialize_emploi_refresh_item(emploi.classe.id, emploi.id)
        emit_live(
            etablissement.id,
            'emploi.mise_a_jour',
            {'event': 'emploi.mise_a_jour', 'item': item},
        )
        if wants_json_response(request):
            return json_ok(message="Emploi du temps publié.", item=item)

        return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=emploi.classe.id)
    
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
        
        # Récupérer la classe (relations pour libellé niveau complet)
        classe = get_object_or_404(
            Classe.objects.select_related('academic_level', 'department'),
            id=classe_id,
            etablissement=etablissement,
        )
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = get_session_active(request, etablissement)
        
        if not annee_scolaire_active:
            messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de créer un emploi du temps.")
            return redirect('administrateur_etablissement:liste_emplois_du_temps')
        
        # Vérifier si la classe a déjà un emploi du temps actif pour l'année scolaire active
        emploi_existant = classe.emplois_du_temps.filter(
            est_actif=True,
            annee_scolaire_fk=annee_scolaire_active
        ).first()
        if emploi_existant:
            messages.warning(request, f"La classe {classe.nom} a déjà un emploi du temps actif pour l'année scolaire {annee_scolaire_active.libelle}.")
            return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe.id)
        
        if request.method == 'POST':
            notes = request.POST.get('notes', '').strip()
            
            try:
                with transaction.atomic():
                    # Créer l'emploi du temps avec l'année scolaire active
                    emploi_du_temps = EmploiDuTemps.objects.create(
                        classe=classe,
                        annee_scolaire=annee_scolaire_active.libelle,  # Utiliser le libellé
                        annee_scolaire_fk=annee_scolaire_active,  # Lier à l'année scolaire active
                        est_actif=True,
                        notes=notes if notes else None
                    )
                    
                    messages.success(request, f"Emploi du temps créé avec succès pour la classe {classe.nom} pour l'année scolaire {annee_scolaire_active.libelle}.")
                    return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe.id)
                    
            except Exception as e:
                logger.error(f"Erreur lors de la création de l'emploi du temps: {str(e)}")
                messages.error(request, "Une erreur est survenue lors de la création de l'emploi du temps.")
        
        context = {
            'classe': classe,
            'etablissement': etablissement,
            'personnel': personnel,
            'is_directeur': isinstance(request.user, Etablissement),
            'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
            'annee_scolaire_active': annee_scolaire_active,
            'annee_scolaire_defaut': annee_scolaire_active.libelle if annee_scolaire_active else '',
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
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = get_session_active(request, etablissement)
        
        if not annee_scolaire_active:
            messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'ajouter un créneau.")
            return redirect('administrateur_etablissement:liste_emplois_du_temps')
        
        # Récupérer l'emploi du temps et vérifier qu'il appartient à l'année scolaire active
        emploi_du_temps = get_object_or_404(
            EmploiDuTemps.objects.select_related('classe'),
            id=emploi_id,
            classe__etablissement=etablissement,
            annee_scolaire_fk=annee_scolaire_active  # Vérifier que l'emploi du temps appartient à l'année active
        )
        
        # Récupérer les matières et professeurs
        from ..model.matiere_model import Matiere
        from ..model.professeur_model import Professeur
        from ..model.salle_model import Salle
        
        classe_edt = emploi_du_temps.classe
        matieres = EmploiDuTempsController._matieres_pour_emploi_du_temps_classe(etablissement, classe_edt)
        salles = Salle.objects.filter(etablissement=etablissement, actif=True).order_by('numero')
        
        professeurs_options, afficher_matiere_prof = EmploiDuTempsController._get_professeurs_options(emploi_du_temps.classe, annee_scolaire_active)
        
        form_data = {}
        field_errors = {}
        
        if request.method == 'POST':
            # Récupération des données (utilise directement heure_debut et heure_fin)
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
            
            # Validation des heures
            heure_debut_obj = None
            heure_fin_obj = None
            if is_valid and form_data['heure_debut'] and form_data['heure_fin']:
                try:
                    heure_debut_obj = datetime.strptime(form_data['heure_debut'], '%H:%M').time()
                    heure_fin_obj = datetime.strptime(form_data['heure_fin'], '%H:%M').time()
                    
                    # Vérifier que l'heure de fin est après l'heure de début
                    if heure_fin_obj <= heure_debut_obj:
                        field_errors['heure_fin'] = "L'heure de fin doit être après l'heure de début."
                        is_valid = False
                except (ValueError, TypeError):
                    field_errors['heure_debut'] = "Format d'heure invalide."
                    is_valid = False
            
            # Vérification des chevauchements
            if is_valid and form_data['jour'] and heure_debut_obj and heure_fin_obj:
                # 1. Vérifier si un créneau existe déjà pour cette classe, ce jour avec chevauchement d'heures
                creneaux_classe = CreneauEmploiDuTemps.objects.filter(
                    emploi_du_temps=emploi_du_temps,
                    jour=form_data['jour']
                )
                
                for creneau_existant in creneaux_classe:
                    heure_debut_existant = creneau_existant.heure_debut
                    heure_fin_existant = creneau_existant.heure_fin
                    
                    if heure_debut_existant and heure_fin_existant:
                        # Vérifier si les heures se chevauchent
                        chevauche = (
                            (heure_debut_obj <= heure_debut_existant < heure_fin_obj) or
                            (heure_debut_obj < heure_fin_existant <= heure_fin_obj) or
                            (heure_debut_existant <= heure_debut_obj and heure_fin_existant >= heure_fin_obj) or
                            (heure_debut_obj <= heure_debut_existant and heure_fin_obj >= heure_fin_existant)
                        )
                        
                        if chevauche:
                            matiere_existante = creneau_existant.matiere.nom if creneau_existant.matiere else "Sans matière"
                            heure_debut_str = heure_debut_obj.strftime('%H:%M')
                            heure_fin_str = heure_fin_obj.strftime('%H:%M')
                            jour_display = dict(CreneauEmploiDuTemps.JOUR_CHOICES).get(form_data['jour'], form_data['jour']).capitalize()
                            field_errors['non_field_errors'] = f"Un créneau existe déjà pour cet horaire ({heure_debut_str} à {heure_fin_str}) le {jour_display} dans cette classe avec la matière {matiere_existante}. Veuillez choisir un autre horaire."
                            is_valid = False
                            break
                
                # 2. Vérifier si le professeur sélectionné a déjà un créneau qui se chevauche
                if is_valid and form_data['professeur_id']:
                    try:
                        professeur = Professeur.objects.get(id=form_data['professeur_id'], etablissement=etablissement)
                        
                        # Récupérer tous les créneaux du professeur pour ce jour et cette année scolaire
                        creneaux_professeur = CreneauEmploiDuTemps.objects.filter(
                            professeur=professeur,
                            jour=form_data['jour'],
                            emploi_du_temps__est_actif=True,
                            emploi_du_temps__annee_scolaire_fk=annee_scolaire_active
                        ).exclude(emploi_du_temps=emploi_du_temps).select_related('emploi_du_temps__classe', 'matiere')
                        
                        # Vérifier les chevauchements d'heures
                        for creneau_existant in creneaux_professeur:
                            heure_debut_existant = creneau_existant.heure_debut
                            heure_fin_existant = creneau_existant.heure_fin
                            
                            if heure_debut_existant and heure_fin_existant:
                                # Vérifier si les heures se chevauchent
                                chevauche = (
                                    (heure_debut_obj <= heure_debut_existant < heure_fin_obj) or
                                    (heure_debut_obj < heure_fin_existant <= heure_fin_obj) or
                                    (heure_debut_existant <= heure_debut_obj and heure_fin_existant >= heure_fin_obj) or
                                    (heure_debut_obj <= heure_debut_existant and heure_fin_obj >= heure_fin_existant)
                                )
                                
                                if chevauche:
                                    matiere_conflict = creneau_existant.matiere.nom if creneau_existant.matiere else "Sans matière"
                                    heure_debut_str = heure_debut_obj.strftime('%H:%M')
                                    heure_fin_str = heure_fin_obj.strftime('%H:%M')
                                    jour_display = dict(CreneauEmploiDuTemps.JOUR_CHOICES).get(form_data['jour'], form_data['jour']).capitalize()
                                    field_errors['non_field_errors'] = f"Le professeur est déjà programmé pour cet horaire ({heure_debut_str} à {heure_fin_str}) le {jour_display} avec la matière {matiere_conflict}. Veuillez choisir un autre horaire."
                                    is_valid = False
                                    break
                                
                    except Professeur.DoesNotExist:
                        pass
            
            # Supérieur : la matière doit être liée à la classe (anti-falsification)
            if is_valid and form_data.get('matiere_id'):
                try:
                    matiere_tmp = Matiere.objects.get(
                        id=form_data['matiere_id'],
                        etablissement=etablissement,
                    )
                    if not EmploiDuTempsController._matiere_est_autorisee_emploi_superieur(
                        etablissement, classe_edt, matiere_tmp
                    ):
                        field_errors['matiere'] = (
                            "Cette matière n'est pas associée à cette classe. "
                            "Liez la matière à la classe (ou au module) dans la gestion pédagogique."
                        )
                        is_valid = False
                except (Matiere.DoesNotExist, ValueError, TypeError):
                    field_errors['matiere'] = "Matière invalide."
                    is_valid = False
            
            # Si tout est valide, créer le créneau
            if is_valid:
                try:
                    with transaction.atomic():
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
                        
                        # Créer le créneau avec les heures directement
                        creneau = CreneauEmploiDuTemps(
                            emploi_du_temps=emploi_du_temps,
                            jour=form_data['jour'],
                            heure_debut=heure_debut_obj,
                            heure_fin=heure_fin_obj,
                            type_cours=form_data['type_cours'],
                            notes=form_data['notes'] if form_data['notes'] else None,
                            matiere=matiere,
                            professeur=professeur,
                            salle=salle
                        )
                        creneau.save()
                        
                        emploi_du_temps.marquer_comme_modifie()
                        
                        EmploiDuTempsController._alerter_republication(request, emploi_du_temps)
                        return _emploi_live_response(
                            request,
                            etablissement,
                            emploi_du_temps.classe.id,
                            emploi_id=emploi_du_temps.id,
                            message="Le créneau a été ajouté avec succès !",
                        )
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout du créneau: {str(e)}")
                    field_errors['non_field_errors'] = "Une erreur est survenue lors de l'ajout du créneau."
            
            # En cas d'erreur, stocker les données en session et rediriger vers detail_emploi_du_temps
            if not is_valid:
                return _emploi_live_response(
                    request,
                    etablissement,
                    emploi_du_temps.classe.id,
                    emploi_id=emploi_du_temps.id,
                    field_errors=field_errors,
                    form_data=form_data,
                )
        
        # Si c'est une requête GET, rediriger vers detail_emploi_du_temps
        return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=emploi_du_temps.classe.id)
    
    @staticmethod
    @login_required
    def modifier_creneau(request, creneau_id):
        """
        Enregistre la modification d'un créneau (POST uniquement).
        Le formulaire est affiché sur la page détail de l'emploi du temps (modal).
        """
        if isinstance(request.user, PersonnelAdministratif):
            etablissement = request.user.etablissement
        elif isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')

        creneau = get_object_or_404(
            CreneauEmploiDuTemps.objects.select_related('emploi_du_temps__classe'),
            id=creneau_id,
            emploi_du_temps__classe__etablissement=etablissement,
        )
        emploi_du_temps = creneau.emploi_du_temps
        classe_edt = emploi_du_temps.classe
        classe_id = classe_edt.id

        if request.method != 'POST':
            return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe_id)

        from ..model.matiere_model import Matiere
        from ..model.professeur_model import Professeur
        from ..model.salle_model import Salle

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
        field_errors = {}
        is_valid = True

        if not form_data['jour']:
            field_errors['jour'] = "Le jour est obligatoire."
            is_valid = False
        if not form_data['heure_debut']:
            field_errors['heure_debut'] = "L'heure de début est obligatoire."
            is_valid = False
        if not form_data['heure_fin']:
            field_errors['heure_fin'] = "L'heure de fin est obligatoire."
            is_valid = False

        if form_data['heure_debut'] and form_data['heure_fin']:
            try:
                t_deb = datetime.strptime(form_data['heure_debut'], '%H:%M').time()
                t_fin = datetime.strptime(form_data['heure_fin'], '%H:%M').time()
                if t_fin <= t_deb:
                    field_errors['heure_fin'] = "L'heure de fin doit être après l'heure de début."
                    is_valid = False
            except ValueError:
                field_errors['heure_debut'] = "Format d'heure invalide."
                is_valid = False

        debut = None
        fin = None
        if is_valid and form_data['jour'] and form_data['heure_debut'] and form_data['heure_fin']:
            try:
                debut = datetime.strptime(form_data['heure_debut'], '%H:%M').time()
                fin = datetime.strptime(form_data['heure_fin'], '%H:%M').time()
            except (ValueError, TypeError):
                debut = None
                fin = None
                is_valid = False

            if is_valid and debut and fin:
                creneaux_classe = CreneauEmploiDuTemps.objects.filter(
                    emploi_du_temps=emploi_du_temps,
                    jour=form_data['jour'],
                ).exclude(id=creneau.id)

                for creneau_existant in creneaux_classe:
                    heure_debut_existant = creneau_existant.heure_debut
                    heure_fin_existant = creneau_existant.heure_fin
                    if heure_debut_existant and heure_fin_existant:
                        chevauche = (
                            (debut <= heure_debut_existant < fin)
                            or (debut < heure_fin_existant <= fin)
                            or (heure_debut_existant <= debut and heure_fin_existant >= fin)
                            or (debut <= heure_debut_existant and fin >= heure_fin_existant)
                        )
                        if chevauche:
                            matiere_existante = creneau_existant.matiere.nom if creneau_existant.matiere else "Sans matière"
                            jour_display = dict(CreneauEmploiDuTemps.JOUR_CHOICES).get(
                                form_data['jour'], form_data['jour']
                            ).capitalize()
                            field_errors['non_field_errors'] = (
                                f"Un créneau existe déjà pour ces heures le {jour_display} dans cette classe "
                                f"avec la matière {matiere_existante}. Veuillez choisir un autre horaire."
                            )
                            is_valid = False
                            break

                if is_valid and form_data['professeur_id']:
                    try:
                        professeur = Professeur.objects.get(
                            id=form_data['professeur_id'],
                            etablissement=etablissement,
                        )
                        annee_scolaire_active = get_session_active(request, etablissement)
                        creneaux_professeur = CreneauEmploiDuTemps.objects.filter(
                            professeur=professeur,
                            jour=form_data['jour'],
                            emploi_du_temps__est_actif=True,
                        )
                        if annee_scolaire_active:
                            creneaux_professeur = creneaux_professeur.filter(
                                emploi_du_temps__annee_scolaire_fk=annee_scolaire_active
                            )
                        creneaux_professeur = creneaux_professeur.exclude(id=creneau.id).select_related(
                            'emploi_du_temps__classe', 'matiere'
                        )
                        for creneau_existant in creneaux_professeur:
                            heure_debut_existant = creneau_existant.heure_debut
                            heure_fin_existant = creneau_existant.heure_fin
                            if heure_debut_existant and heure_fin_existant:
                                chevauche = (
                                    (debut <= heure_debut_existant < fin)
                                    or (debut < heure_fin_existant <= fin)
                                    or (heure_debut_existant <= debut and heure_fin_existant >= fin)
                                    or (debut <= heure_debut_existant and fin >= heure_fin_existant)
                                )
                                if chevauche:
                                    matiere_conflict = creneau_existant.matiere.nom if creneau_existant.matiere else "Sans matière"
                                    jour_display = dict(CreneauEmploiDuTemps.JOUR_CHOICES).get(
                                        form_data['jour'], form_data['jour']
                                    ).capitalize()
                                    field_errors['non_field_errors'] = (
                                        f"Le professeur est déjà programmé pour cet horaire "
                                        f"({form_data['heure_debut']} à {form_data['heure_fin']}) le {jour_display} "
                                        f"avec la matière {matiere_conflict}. Veuillez choisir un autre horaire."
                                    )
                                    is_valid = False
                                    break
                    except Professeur.DoesNotExist:
                        pass

        if is_valid and form_data.get('matiere_id'):
            try:
                matiere_tmp = Matiere.objects.get(
                    id=form_data['matiere_id'],
                    etablissement=etablissement,
                )
                if not EmploiDuTempsController._matiere_est_autorisee_emploi_superieur(
                    etablissement, classe_edt, matiere_tmp
                ):
                    field_errors['matiere'] = (
                        "Cette matière n'est pas associée à cette classe. "
                        "Liez la matière à la classe (ou au module) dans la gestion pédagogique."
                    )
                    is_valid = False
            except (Matiere.DoesNotExist, ValueError, TypeError):
                field_errors['matiere'] = "Matière invalide."
                is_valid = False

        if is_valid:
            try:
                with transaction.atomic():
                    creneau.jour = form_data['jour']
                    creneau.heure_debut = form_data['heure_debut']
                    creneau.heure_fin = form_data['heure_fin']
                    creneau.type_cours = form_data['type_cours']
                    creneau.notes = form_data['notes'] if form_data['notes'] else None

                    if form_data['matiere_id']:
                        try:
                            matiere = Matiere.objects.get(id=form_data['matiere_id'], etablissement=etablissement)
                            creneau.matiere = matiere
                        except Matiere.DoesNotExist:
                            creneau.matiere = None
                    else:
                        creneau.matiere = None

                    if form_data['professeur_id']:
                        try:
                            professeur = Professeur.objects.get(
                                id=form_data['professeur_id'],
                                etablissement=etablissement,
                            )
                            creneau.professeur = professeur
                        except Professeur.DoesNotExist:
                            creneau.professeur = None
                    else:
                        creneau.professeur = None

                    if form_data['salle_id']:
                        try:
                            salle = Salle.objects.get(id=form_data['salle_id'], etablissement=etablissement)
                            creneau.salle = salle
                        except Salle.DoesNotExist:
                            creneau.salle = None
                    else:
                        creneau.salle = None

                    creneau.save()
                    emploi_du_temps.marquer_comme_modifie()

                EmploiDuTempsController._alerter_republication(request, emploi_du_temps)
                return _emploi_live_response(
                    request,
                    etablissement,
                    classe_id,
                    emploi_id=emploi_du_temps.id,
                    message="Le créneau a été modifié avec succès !",
                )
            except Exception as e:
                logger.error("Erreur lors de la modification du créneau: %s", str(e))
                field_errors['non_field_errors'] = "Une erreur est survenue lors de la modification du créneau."

        request.session['modifier_creneau_form_data'] = form_data
        request.session['modifier_creneau_field_errors'] = field_errors
        request.session['modifier_creneau_id'] = creneau.id
        return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe_id)
    
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
        
        emploi_du_temps = creneau.emploi_du_temps
        classe_id = emploi_du_temps.classe.id
        
        if request.method == 'POST':
            try:
                creneau.delete()
                emploi_du_temps.marquer_comme_modifie()
                EmploiDuTempsController._alerter_republication(request, emploi_du_temps)
                return _emploi_live_response(
                    request,
                    etablissement,
                    classe_id,
                    emploi_id=emploi_du_temps.id,
                    message="Le créneau a été supprimé avec succès.",
                )
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du créneau: {str(e)}")
                from ..services.realtime_helpers import wants_json_response, json_fail
                if wants_json_response(request):
                    return json_fail(message="Une erreur est survenue lors de la suppression du créneau.")
                messages.error(request, "Une erreur est survenue lors de la suppression du créneau.")
        
        return redirect('administrateur_etablissement:detail_emploi_du_temps', classe_id=classe_id)
    
    @staticmethod
    def _alerter_republication(request, emploi_du_temps):
        """
        Ajoute un message d'information lorsque l'emploi du temps doit être republié.
        """
        if emploi_du_temps.doit_republier:
            messages.info(
                request,
                "Des modifications ont été enregistrées. Republiez l'emploi du temps pour notifier les élèves, les parents d'élèves et les enseignants concernés.",
            )
    
    @staticmethod
    def _get_professeurs_options(classe, annee_scolaire_active=None):
        """
        Retourne la liste des professeurs affectés à une classe avec un libellé adapté.
        Filtre uniquement les professeurs affectés à la classe pour l'année scolaire active.
        
        Args:
            classe: L'objet Classe
            annee_scolaire_active: L'année scolaire active (optionnel mais recommandé)
        """
        from collections import OrderedDict
        from ..model.professeur_model import Professeur
        from ..model.affectation_model import AffectationProfesseur
        from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

        etablissement = classe.etablissement
        type_etablissement = getattr(etablissement, "type_etablissement", "").lower()
        niveau_classe = getattr(classe, "niveau", "").lower()
        afficher_matiere = (
            type_etablissement in ('collège', 'lycée', 'college', 'lycee') or
            niveau_classe in ('college', 'lycee', 'superieur') or
            'lycee' in niveau_classe or
            'college' in niveau_classe
        )

        options = []

        if type_etablissement in ('primary', 'primaire'):
            affectations_primaire = (
                AffectationProfesseurPrimaire.objects.filter(
                    classe=classe,
                    actif=True,
                    professeur__actif=True,
                )
            )
            # Filtrer par année scolaire active si fournie
            if annee_scolaire_active:
                affectations_primaire = affectations_primaire.filter(
                    annee_scolaire=annee_scolaire_active
                )
            affectations_primaire = (
                affectations_primaire
                .select_related('professeur')
                .prefetch_related('matieres')
                .order_by('professeur__nom', 'professeur__prenom')
            )

            for affectation in affectations_primaire:
                professeur = affectation.professeur
                label = professeur.nom_complet
                options.append({
                    'id': professeur.id,
                    'label': label,
                    'prenom': professeur.prenom,
                    'nom': professeur.nom,
                    'matiere': None,
                })

        else:
            affectations = (
                AffectationProfesseur.objects.filter(
                    classe=classe,
                    actif=True,
                    professeur__actif=True,
                )
            )
            # Filtrer par année scolaire active si fournie
            if annee_scolaire_active:
                affectations = affectations.filter(
                    annee_scolaire=annee_scolaire_active
                )
            affectations = (
                affectations
                .select_related('professeur', 'matiere')
                .order_by('professeur__nom', 'professeur__prenom', 'matiere__nom')
            )

            prof_map = OrderedDict()
            for affectation in affectations:
                professeur = affectation.professeur
                entry = prof_map.setdefault(
                    professeur.id,
                    {
                        'professeur': professeur,
                        'matieres_codes': [],
                    },
                )
                if affectation.matiere:
                    code_matiere = affectation.matiere.code or affectation.matiere.nom[:4].upper()
                    if code_matiere not in entry['matieres_codes']:
                        entry['matieres_codes'].append(code_matiere)

            for professeur_id, data in prof_map.items():
                professeur = data['professeur']
                matieres_codes = data['matieres_codes']
                label = professeur.nom_complet
                matiere_nom = None
                if afficher_matiere and matieres_codes:
                    matiere_nom = " / ".join(matieres_codes)
                    label = f"{label} - {matiere_nom}"
                elif afficher_matiere and professeur.matiere_principale:
                    matiere_nom = professeur.matiere_principale.code or professeur.matiere_principale.nom[:4].upper()
                    label = f"{label} - {matiere_nom}"

                options.append({
                    'id': professeur.id,
                    'label': label,
                    'prenom': professeur.prenom,
                    'nom': professeur.nom,
                    'matiere': matiere_nom,
                })

        if not options:
            professeurs_associes = classe.professeurs.filter(actif=True).order_by('nom', 'prenom')
            for professeur in professeurs_associes:
                label = professeur.nom_complet
                matiere_nom = None
                if afficher_matiere and professeur.matiere_principale:
                    matiere_nom = professeur.matiere_principale.code or professeur.matiere_principale.nom[:4].upper()
                    label = f"{label} - {matiere_nom}"
                options.append({
                    'id': professeur.id,
                    'label': label,
                    'prenom': professeur.prenom,
                    'nom': professeur.nom,
                    'matiere': matiere_nom,
                })

        if not options:
            professeurs_etab = Professeur.objects.filter(
                etablissement=classe.etablissement,
                actif=True,
                classes=classe,
            ).order_by('nom', 'prenom')
            for professeur in professeurs_etab:
                label = professeur.nom_complet
                matiere_nom = None
                if afficher_matiere and professeur.matiere_principale:
                    matiere_nom = professeur.matiere_principale.code or professeur.matiere_principale.nom[:4].upper()
                    label = f"{label} - {matiere_nom}"
                options.append({
                    'id': professeur.id,
                    'label': label,
                    'prenom': professeur.prenom,
                    'nom': professeur.nom,
                    'matiere': matiere_nom,
                })

        return options, afficher_matiere
    
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

