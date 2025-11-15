"""
Vues pour l'espace élève
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count
from django.urls import reverse
from django.core.files.base import ContentFile
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from io import BytesIO
import logging
import uuid

from school_admin.model.eleve_model import Eleve
from school_admin.model.evaluation_model import Note, Evaluation
from school_admin.model.presence_model import Presence
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
from school_admin.model.parent_model import Parent
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.sanction_model import Sanction
from school_admin.model.notification_eleve_model import NotificationEleve
from ..model.exercice_maison_model import ExerciceMaison
from school_admin.personal_views.directeur_view import (
    _apply_standards_to_bulletin,
    _get_standards_bundle,
)
try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - Pillow doit être installé
    Image = None
    ImageOps = None

logger = logging.getLogger(__name__)

ALLOWED_PHOTO_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/pjpeg",
}
MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024  # 5 Mo


def _build_portrait_photo(uploaded_file):
    """
    Génère une version recadrée (format identité) de la photo envoyée.
    """
    if Image is None:
        raise ValueError(
            "Le traitement d'image est indisponible. Contactez l'administration."
        )

    try:
        image = Image.open(uploaded_file)
    except Exception as exc:  # pragma: no cover - dépend des entrées utilisateur
        raise ValueError("Impossible de lire cette image.") from exc

    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")

    target_ratio = 3 / 4  # format identité (portrait)
    width, height = image.size
    current_ratio = width / height

    if current_ratio > target_ratio:
        new_width = int(target_ratio * height)
        left = max(0, (width - new_width) // 2)
        right = left + new_width
        top = 0
        bottom = height
    else:
        new_height = int(width / target_ratio)
        top = max(0, ((height - new_height) // 2) - int(new_height * 0.15))
        bottom = top + new_height
        if bottom > height:
            bottom = height
            top = max(0, bottom - new_height)
        left = 0
        right = width

    image = image.crop((left, top, right, bottom))

    final_size = (600, 800)
    resample_attr = getattr(Image, "Resampling", None)
    resample_filter = resample_attr.LANCZOS if resample_attr else Image.LANCZOS
    image = image.resize(final_size, resample=resample_filter)

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)

    filename = f"eleve_photo_{uuid.uuid4().hex[:10]}.jpg"
    return filename, buffer.getvalue()


def get_eleve_from_request(request):
    """
    Fonction helper pour récupérer l'élève à partir de la requête
    Supporte à la fois les élèves connectés et les parents consultant leur enfant
    
    Returns:
        tuple: (eleve, est_parent) ou (None, False) si accès refusé
    """
    # Si c'est un parent qui consulte
    if isinstance(request.user, Parent):
        eleve_id = request.session.get('eleve_consulte_id')
        if not eleve_id:
            return None, False
        
        # Vérifier que le parent a bien accès à cet élève
        lien = LienFamilial.objects.filter(
            parent=request.user,
            eleve_id=eleve_id,
            actif=True,
            statut='valide'
        ).select_related('eleve').first()
        
        if not lien:
            return None, False
        
        return lien.eleve, True
    
    # Si c'est un élève connecté
    elif isinstance(request.user, Eleve):
        return request.user, False
    
    # Autre type d'utilisateur : accès refusé
    return None, False


def dashboard_eleve(request):
    """
    Tableau de bord principal de l'élève
    Accessible par l'élève lui-même ou par son parent
    """
    print(f"\n[DASHBOARD ELEVE] User: {request.user}, Type: {type(request.user).__name__}, Authenticated: {request.user.is_authenticated}")
    logger.info(f"Dashboard eleve - User: {request.user}, Type: {type(request.user).__name__}, Authenticated: {request.user.is_authenticated}")
    
    # Utiliser la fonction helper pour récupérer l'élève
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Date d'aujourd'hui
        date_aujourdhui = timezone.now().date()
        
        # Calculer la moyenne générale (désactivé temporairement pour debug)
        moyenne_generale = None
        periode_active = None
        if eleve.etablissement:
            from ..model.periode_model import PeriodeScolaire
            from ..model.moyenne_periode_model import MoyennePeriode

            periodes_qs = PeriodeScolaire.objects.filter(etablissement=eleve.etablissement).order_by('date_debut')
            periode_active = periodes_qs.filter(est_active=True).first()
            if not periode_active:
                periode_active = periodes_qs.last()

            moyenne_obj = None
            if periode_active:
                moyenne_obj = MoyennePeriode.objects.filter(
                    eleve=eleve,
                    etablissement=eleve.etablissement,
                    periode=periode_active,
                    est_moyenne_generale=True,
                    afficher_bulletin=True
                ).order_by('-updated_at').first()

            if not moyenne_obj:
                moyenne_obj = MoyennePeriode.objects.filter(
                    eleve=eleve,
                    etablissement=eleve.etablissement,
                    est_moyenne_generale=True,
                    afficher_bulletin=True
                ).order_by('-updated_at').first()

            if moyenne_obj and moyenne_obj.moyenne_generale is not None:
                moyenne_generale = format(moyenne_obj.moyenne_generale, '.2f')
        
        # Récupérer les 3 dernières notes de l'élève
        dernieres_notes = []
        
        # Vérifier le type d'établissement pour récupérer les notes appropriées
        if eleve.etablissement:
            type_etablissement = eleve.etablissement.type_etablissement
            
            if type_etablissement in ('primaire', 'primary', 'ecole_primaire'):
                # Pour le primaire, utiliser NotePrimaire
                from ..model.note_primaire_model import NotePrimaire
                notes_queryset = (
                    NotePrimaire.objects.filter(eleve=eleve, absent=False)
                    .select_related('evaluation_primaire', 'evaluation_primaire__matiere')
                    .order_by('-evaluation_primaire__date_evaluation')[:3]
                )
                
                for note_obj in notes_queryset:
                    note_sur_20 = note_obj.note_sur_20
                    if note_sur_20 is None:
                        continue
                    
                    if note_sur_20 >= 16:
                        classe_css = 'excellent'
                    elif note_sur_20 >= 14:
                        classe_css = 'tres-bien'
                    elif note_sur_20 >= 12:
                        classe_css = 'bien'
                    elif note_sur_20 >= 10:
                        classe_css = 'assez-bien'
                    else:
                        classe_css = 'insuffisant'
                    
                    dernieres_notes.append({
                        'matiere': note_obj.evaluation_primaire.matiere.nom,
                        'titre': note_obj.evaluation_primaire.titre,
                        'note': note_sur_20,
                        'classe_css': classe_css,
                        'date': note_obj.evaluation_primaire.date_evaluation
                    })
            else:
                # Pour collège/lycée, utiliser Note
                notes_queryset = Note.objects.filter(
                    eleve=eleve
                ).select_related('evaluation', 'evaluation__matiere').order_by('-evaluation__date_evaluation')[:3]
                
                for note_obj in notes_queryset:
                    # Calculer la classe CSS selon la note
                    note_sur_20 = note_obj.note if note_obj.evaluation.bareme == 20 else (note_obj.note * 20 / note_obj.evaluation.bareme)
                    
                    if note_sur_20 >= 16:
                        classe_css = 'excellent'
                    elif note_sur_20 >= 14:
                        classe_css = 'tres-bien'
                    elif note_sur_20 >= 12:
                        classe_css = 'bien'
                    elif note_sur_20 >= 10:
                        classe_css = 'assez-bien'
                    else:
                        classe_css = 'insuffisant'
                    
                    dernieres_notes.append({
                        'matiere': note_obj.evaluation.matiere.nom,
                        'titre': note_obj.evaluation.titre,
                        'note': round(note_sur_20, 2),
                        'classe_css': classe_css,
                        'date': note_obj.evaluation.date_evaluation
                    })
        
        # Calculer les statistiques de présence
        debut_annee = timezone.now().replace(month=9, day=1, hour=0, minute=0, second=0, microsecond=0)
        if timezone.now().month < 9:
            debut_annee = debut_annee.replace(year=debut_annee.year - 1)
        
        presences = Presence.objects.filter(
            eleve=eleve,
            date__gte=debut_annee
        )
        
        total_presences = presences.count()
        presences_absentes = presences.filter(statut='absent').count()
        presences_retards = presences.filter(statut='retard').count()
        jours_present = total_presences - presences_absentes
        
        if total_presences > 0:
            taux_presence = round((jours_present / total_presences) * 100, 1)
        else:
            taux_presence = 100
        
        # Récupérer les prochains cours d'aujourd'hui
        prochains_cours = []
        emploi_non_publie = False
        if eleve.classe:
            # Convertir le numéro du jour en nom de jour
            jours_mapping = {
                0: 'lundi',
                1: 'mardi',
                2: 'mercredi',
                3: 'jeudi',
                4: 'vendredi',
                5: 'samedi',
                6: 'dimanche',
            }
            jour_actuel = jours_mapping.get(date_aujourdhui.weekday(), 'lundi')
            
            # Récupérer l'emploi du temps actif de la classe
            from ..model.emploi_du_temps_model import EmploiDuTemps
            emplois_actifs = EmploiDuTemps.objects.filter(
                classe=eleve.classe,
                est_actif=True,
            )
            emploi_du_temps = emplois_actifs.filter(statut_publication='publie').first()
            
            if not emploi_du_temps and emplois_actifs.exists():
                emploi_non_publie = True
            
            if emploi_du_temps:
                creneaux = CreneauEmploiDuTemps.objects.filter(
                    emploi_du_temps=emploi_du_temps,
                    jour=jour_actuel
                ).select_related('matiere', 'professeur', 'periode_etablissement', 'salle').order_by('periode_etablissement__ordre')
            else:
                creneaux = []
            
            for creneau in creneaux:
                # Ne pas afficher les pauses dans les prochains cours
                if creneau.periode_etablissement and creneau.periode_etablissement.est_pause:
                    continue
                
                # Définir icône et couleur selon la matière
                icon = 'fas fa-book'
                icon_color = 'neo-blue'
                
                if creneau.matiere:
                    matiere_nom = creneau.matiere.nom.lower()
                    if 'math' in matiere_nom:
                        icon = 'fas fa-calculator'
                        icon_color = 'neo-blue'
                    elif 'français' in matiere_nom or 'francais' in matiere_nom or 'langue française' in matiere_nom:
                        icon = 'fas fa-book'
                        icon_color = 'neo-red'
                    elif 'anglais' in matiere_nom or 'langue anglaise' in matiere_nom:
                        icon = 'fas fa-language'
                        icon_color = 'neo-purple'
                    elif 'histoire' in matiere_nom or 'géographie' in matiere_nom or 'geographie' in matiere_nom:
                        icon = 'fas fa-globe-europe'
                        icon_color = 'neo-green'
                    elif 'svt' in matiere_nom or 'biologie' in matiere_nom or 'éveil' in matiere_nom or 'eveil' in matiere_nom or 'étude du milieu' in matiere_nom:
                        icon = 'fas fa-leaf'
                        icon_color = 'neo-teal'
                    elif 'physique' in matiere_nom or 'chimie' in matiere_nom:
                        icon = 'fas fa-flask'
                        icon_color = 'neo-cyan'
                    elif 'sport' in matiere_nom or 'eps' in matiere_nom or 'éducation physique' in matiere_nom or 'education physique' in matiere_nom:
                        icon = 'fas fa-running'
                        icon_color = 'neo-orange'
                    elif 'art' in matiere_nom or 'plastique' in matiere_nom:
                        icon = 'fas fa-palette'
                        icon_color = 'neo-pink'
                    elif 'morale' in matiere_nom or 'civique' in matiere_nom or 'emc' in matiere_nom:
                        icon = 'fas fa-balance-scale'
                        icon_color = 'neo-purple'
                
                prochains_cours.append({
                    'matiere': creneau.matiere.nom if creneau.matiere else 'Non défini',
                    'icon': icon,
                    'icon_color': icon_color,
                    'heure_debut': creneau.periode_etablissement.heure_debut.strftime('%H:%M') if creneau.periode_etablissement else 'N/A',
                    'heure_fin': creneau.periode_etablissement.heure_fin.strftime('%H:%M') if creneau.periode_etablissement else 'N/A',
                    'salle': creneau.salle.numero if creneau.salle else None,
                    'enseignant': creneau.professeur.nom_complet if creneau.professeur else None
                })
        
        # Devoirs à faire (exercices programmés)
        devoirs = []
        total_devoirs = 0

        if eleve.classe:
            exercices_qs = ExerciceMaison.objects.filter(
                classe=eleve.classe,
                actif=True
            ).select_related('matiere')

            if eleve.etablissement:
                exercices_qs = exercices_qs.filter(etablissement=eleve.etablissement)

            debut_semaine = date_aujourdhui - timedelta(days=date_aujourdhui.weekday())
            fin_semaine = debut_semaine + timedelta(days=6)
            total_devoirs = exercices_qs.filter(
                date_rendu__range=(debut_semaine, fin_semaine)
            ).count()

            prochains_exercices = exercices_qs.filter(
                date_rendu__gte=date_aujourdhui
            ).order_by('date_rendu')[:5]

            for exercice in prochains_exercices:
                delta = (exercice.date_rendu - date_aujourdhui).days
                if delta <= 1:
                    priorite = 'high'
                    priorite_label = 'Haute'
                elif delta <= 3:
                    priorite = 'medium'
                    priorite_label = 'Moyenne'
                else:
                    priorite = 'low'
                    priorite_label = 'Basse'

                devoirs.append({
                    'id': exercice.id,
                    'titre': exercice.titre,
                    'matiere': exercice.matiere.nom if exercice.matiere else "Matière non définie",
                    'description': exercice.description.strip() if exercice.description else "Consignes disponibles auprès de votre enseignant.",
                    'date_limite': exercice.date_rendu,
                    'priorite': priorite,
                    'priorite_label': priorite_label,
                })
        
        # Compter les annonces destinées aux élèves
        from ..model.annonce_model import Annonce
        from django.db.models import Q
        
        nombre_annonces = Annonce.objects.filter(
            Q(etablissement=eleve.etablissement) &
            Q(statut='publiee') &
            Q(actif=True) &
            (Q(destinataires__contains=['tous']) | 
             Q(destinataires__contains=['eleves']))
        ).count()
        
        context = {
            'page_title': 'Tableau de bord',
            'eleve': eleve,
            'est_parent': est_parent,
            'moyenne_generale': moyenne_generale,
            'dernieres_notes': dernieres_notes,
            'taux_presence': taux_presence,
            'jours_present': jours_present,
            'total_absences': presences_absentes,
            'total_retards': presences_retards,
            'prochains_cours': prochains_cours,
            'devoirs': devoirs,
            'total_devoirs': total_devoirs,
            'date_aujourdhui': date_aujourdhui,
            'nombre_annonces': nombre_annonces,
            'emploi_non_publie': emploi_non_publie,
        }
        
        return render(request, 'school_admin/eleve/dashboard_eleve.html', context)
        
    except Exception as e:
        messages.error(request, f"Erreur lors du chargement du tableau de bord : {str(e)}")
        return redirect('school_admin:connexion_compte_user')


def devoirs_eleve(request):
    """
    Liste exhaustive des exercices programmés pour l'élève.
    Filtrage par matière et par période.
    """
    eleve, est_parent = get_eleve_from_request(request)

    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    if not eleve.classe:
        messages.info(request, "Aucune classe n'est associée à votre profil.")
        return redirect('eleve:dashboard_eleve')

    date_aujourdhui = timezone.now().date()
    debut_semaine = date_aujourdhui - timedelta(days=date_aujourdhui.weekday())
    fin_semaine = debut_semaine + timedelta(days=6)

    exercices_base = ExerciceMaison.objects.filter(
        classe=eleve.classe,
        actif=True
    ).select_related('matiere', 'professeur', 'periode_scolaire').order_by('date_rendu')

    if eleve.etablissement:
        exercices_base = exercices_base.filter(etablissement=eleve.etablissement)

    total_exercices = exercices_base.count()
    total_semaine = exercices_base.filter(date_rendu__range=(debut_semaine, fin_semaine)).count()
    total_a_venir = exercices_base.filter(date_rendu__gte=date_aujourdhui).count()

    matieres_stats = exercices_base.values('matiere_id', 'matiere__nom').annotate(total=Count('id')).order_by('matiere__nom')
    matieres_tabs = [{
        'id': 'all',
        'nom': 'Toutes les matières',
        'total': total_exercices,
    }]
    for stat in matieres_stats:
        matieres_tabs.append({
            'id': str(stat['matiere_id']),
            'nom': stat['matiere__nom'],
            'total': stat['total'],
        })

    periodes_tabs = [{
        'id': 'all',
        'nom': 'Toutes les périodes',
        'total': total_exercices,
    }]
    total_sans_periode = exercices_base.filter(periode_scolaire__isnull=True).count()
    if total_sans_periode:
        periodes_tabs.append({
            'id': 'none',
            'nom': 'Sans période',
            'total': total_sans_periode,
        })

    periodes_stats = exercices_base.filter(periode_scolaire__isnull=False).values(
        'periode_scolaire_id',
        'periode_scolaire__nom_periode'
    ).annotate(total=Count('id')).order_by('periode_scolaire__date_debut', 'periode_scolaire__nom_periode')

    for stat in periodes_stats:
        periodes_tabs.append({
            'id': str(stat['periode_scolaire_id']),
            'nom': stat['periode_scolaire__nom_periode'],
            'total': stat['total'],
        })

    matiere_selectionnee = request.GET.get('matiere', 'all')
    periode_selectionnee = request.GET.get('periode', 'all')

    exercices_filtres = exercices_base

    if matiere_selectionnee != 'all':
        try:
            matiere_id = int(matiere_selectionnee)
            exercices_filtres = exercices_filtres.filter(matiere_id=matiere_id)
            matiere_selectionnee = str(matiere_id)
        except (TypeError, ValueError):
            matiere_selectionnee = 'all'

    if periode_selectionnee != 'all':
        if periode_selectionnee == 'none':
            exercices_filtres = exercices_filtres.filter(periode_scolaire__isnull=True)
        else:
            try:
                periode_id = int(periode_selectionnee)
                exercices_filtres = exercices_filtres.filter(periode_scolaire_id=periode_id)
                periode_selectionnee = str(periode_id)
            except (TypeError, ValueError):
                periode_selectionnee = 'all'

    exercices_list = []
    for exercice in exercices_filtres:
        delta = (exercice.date_rendu - date_aujourdhui).days
        if delta < 0:
            statut = 'retard'
            statut_label = "En retard"
        elif delta == 0:
            statut = 'jour'
            statut_label = "Pour aujourd'hui"
        elif delta == 1:
            statut = 'bientot'
            statut_label = "Pour demain"
        elif delta <= 3:
            statut = 'proche'
            statut_label = f"Dans {delta} jours"
        else:
            statut = 'planifie'
            statut_label = f"Dans {delta} jours"

        exercices_list.append({
            'id': exercice.id,
            'titre': exercice.titre,
            'matiere': exercice.matiere.nom if exercice.matiere else "Matière non définie",
            'description': exercice.description.strip() if exercice.description else "",
            'date_rendu': exercice.date_rendu,
            'professeur': getattr(exercice.professeur, 'nom_complet', str(exercice.professeur)),
            'periode': exercice.periode_scolaire.nom_periode if exercice.periode_scolaire else "Sans période",
            'statut': statut,
            'statut_label': statut_label,
            'jours_restant': delta,
            'jours_restant_abs': abs(delta),
        })

    context = {
        'page_title': 'Devoirs à rendre',
        'eleve': eleve,
        'est_parent': est_parent,
        'matieres_tabs': matieres_tabs,
        'periodes_tabs': periodes_tabs,
        'matiere_selectionnee': matiere_selectionnee,
        'periode_selectionnee': periode_selectionnee,
        'exercices': exercices_list,
        'total_exercices': total_exercices,
        'total_semaine': total_semaine,
        'total_a_venir': total_a_venir,
        'date_aujourdhui': date_aujourdhui,
        'classe': eleve.classe,
    }

    return render(request, 'school_admin/eleve/devoirs_eleve.html', context)


def deconnexion_eleve(request):
    """
    Déconnexion de l'élève
    """
    from django.contrib.auth import logout
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès.")
    return redirect('school_admin:connexion_compte_user')


def emploi_du_temps_eleve(request):
    """
    Affiche l'emploi du temps de la classe de l'élève
    Accessible par l'élève ou son parent
    """
    logger.info(f"Emploi du temps élève - User: {request.user}, Type: {type(request.user).__name__}")
    
    # Utiliser la fonction helper pour récupérer l'élève
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    # Vérifier que l'élève a une classe
    if not eleve.classe:
        messages.warning(request, "Vous n'êtes pas encore affecté à une classe.")
        return redirect('eleve:dashboard')
    
    classe = eleve.classe
    etablissement = eleve.etablissement
    
    # Récupérer l'emploi du temps actif de la classe
    from ..model.emploi_du_temps_model import EmploiDuTemps
    emplois_actifs = EmploiDuTemps.objects.filter(
        classe=classe,
        est_actif=True,
    )
    emploi_du_temps = emplois_actifs.filter(statut_publication='publie').first()
    
    # Si pas d'emploi du temps, afficher un message
    if not emploi_du_temps:
        context = {
            'eleve': eleve,
            'classe': classe,
            'emploi_du_temps': None,
            'periodes_affichage': [],
            'jours_semaine': [],
            'emploi_non_publie': emplois_actifs.exists(),
        }
        return render(request, 'school_admin/eleve/emploi_du_temps_eleve.html', context)
    
    # Récupérer les créneaux organisés par jour
    jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
    
    # Récupérer tous les créneaux
    tous_creneaux = emploi_du_temps.creneaux.all().order_by('jour', 'heure_debut')
    
    # Organiser les créneaux par période et par jour
    from ..model.configuration_horaire_model import ConfigurationHoraire, PeriodeEtablissement
    from ..controllers.emploi_du_temps_controller import get_matiere_config
    
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
                'skip_render': {},
                'rowspans': {}
            }
            
            # Pour chaque jour, trouver le créneau correspondant à cette période
            for jour in jours_semaine:
                periode_info['skip_render'][jour] = False
                periode_info['rowspans'][jour] = 1
                
                if periode.est_pause:
                    # C'est une pause: créer un créneau virtuel
                    periode_info['creneaux_par_jour'][jour] = {
                        'est_pause': True,
                        'est_virtual': True,
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
                        # Pour les créneaux groupés, afficher le premier créneau dans toutes les périodes du groupe
                        if creneau.groupe_creneau:
                            groupe_creneaux = creneaux_groupes.get(creneau.groupe_creneau, [])
                            groupe_creneaux_jour = [c for c in groupe_creneaux if c.jour == jour]
                            groupe_creneaux_jour.sort(key=lambda c: c.periode_etablissement.ordre)
                            
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
        horaires_uniques = set()
        for creneau in tous_creneaux:
            horaires_uniques.add((creneau.get_heure_debut(), creneau.get_heure_fin()))
        
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
                
                if creneau and creneau.matiere:
                    matiere_nom = creneau.matiere.nom
                    icone, couleur = get_matiere_config(matiere_nom)
                    creneau.matiere_icone = icone
                    creneau.matiere_couleur = couleur
                
                periode_info['creneaux_par_jour'][jour] = creneau
            
            periodes_affichage.append(periode_info)
    
    # Récupérer les créneaux d'examens pour cette classe
    from ..model.session_examen_model import SessionExamen
    from ..model.creneau_examen_model import CreneauExamen
    
    sessions_examens = SessionExamen.objects.filter(
        etablissement=etablissement,
        classes=classe,
        actif=True
    ).select_related('periode').prefetch_related('matieres', 'classes')
    
    creneaux_examens = CreneauExamen.objects.filter(
        session_examen__in=sessions_examens,
        actif=True
    ).select_related('session_examen', 'matiere', 'surveillant', 'salle').order_by('date_examen', 'heure_debut')
    
    # Organiser les créneaux d'examens
    dates_examens_uniques = set()
    
    for session in sessions_examens:
        if session.date_debut and session.date_fin:
            date_courante = session.date_debut
            while date_courante <= session.date_fin:
                dates_examens_uniques.add(date_courante)
                date_courante += timedelta(days=1)
    
    for creneau in creneaux_examens:
        dates_examens_uniques.add(creneau.date_examen)
    
    dates_examens_triees = sorted(list(dates_examens_uniques))
    
    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'classe': classe,
        'emploi_du_temps': emploi_du_temps,
        'emploi_non_publie': False,
        'periodes_affichage': periodes_affichage,
        'tous_creneaux': tous_creneaux,
        'etablissement': etablissement,
        'jours_semaine': jours_semaine,
        'config_horaire': config_horaire,
        'sessions_examens': sessions_examens,
        'creneaux_examens': creneaux_examens,
        'dates_examens_triees': dates_examens_triees,
    }
    
    return render(request, 'school_admin/eleve/emploi_du_temps_eleve.html', context)


def notes_evaluations_eleve(request):
    """
    Page des notes et évaluations pour les élèves
    Accessible par l'élève ou son parent
    """
    logger.info(f"Notes et évaluations - User: {request.user}, Type: {type(request.user).__name__}")
    
    # Utiliser la fonction helper pour récupérer l'élève
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = eleve.etablissement
    
    from ..model.periode_model import PeriodeScolaire
    from ..model.moyenne_model import Moyenne
    from ..model.moyenne_periode_model import MoyennePeriode
    from ..model.matiere_model import Matiere
    from ..model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire
    from ..model.evaluation_primaire_model import EvaluationPrimaire
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from ..model.affectation_model import AffectationProfesseur
    from django.db.models import Avg, Count
    
    # Récupérer toutes les périodes actives
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Déterminer la période active (en cours)
    periode_active = None
    for periode in periodes:
        if periode.est_en_cours:
            periode_active = periode
            break
    
    if not periode_active and periodes.exists():
        periode_active = periodes.first()
    
    # Récupérer les moyennes par période et par matière
    periodes_data = []
    
    for periode in periodes:
        # Récupérer les moyennes de l'élève pour cette période
        # Utiliser MoyenneMatierePrimaire pour le primaire, Moyenne pour le collège/lycée
        if etablissement.type_etablissement == 'primary':
            moyennes = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                periode_scolaire=periode
            ).select_related('matiere').exclude(moyenne__isnull=True)
        else:
            moyennes = Moyenne.objects.filter(
                eleve=eleve,
                periode=str(periode.id),
                actif=True
            ).select_related('matiere').exclude(moyenne__isnull=True)
        
        # Calculer ou récupérer la moyenne générale de la période
        moyenne_generale_value = None
        moyenne_generale_display = None
        total_pondere = 0
        total_coefficients = 0
        
        for moy in moyennes:
            if moy.moyenne and moy.matiere:
                coef = moy.matiere.coefficient if moy.matiere.coefficient else 1
                total_pondere += moy.moyenne * coef
                total_coefficients += coef

        moyenne_generale_record = MoyennePeriode.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            periode=periode,
            est_moyenne_generale=True,
            afficher_bulletin=True
        ).order_by('-updated_at').first()

        if moyenne_generale_record and moyenne_generale_record.moyenne_generale is not None:
            moyenne_generale_value = float(moyenne_generale_record.moyenne_generale)
        
        if moyenne_generale_value is None and total_coefficients > 0:
            moyenne_generale_value = float(total_pondere / total_coefficients)
        
        if moyenne_generale_value is not None:
            moyenne_generale_display = f"{Decimal(str(moyenne_generale_value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
        
        # Récupérer les matières avec leurs moyennes
        matieres_moyennes = []
        for moy in moyennes:
            if moy.matiere:
                # Pour le primaire, utiliser MoyenneMatierePrimaire pour la moyenne de classe
                if etablissement.type_etablissement == 'primary':
                    moyenne_classe_obj = MoyenneMatierePrimaire.objects.filter(
                        classe=eleve.classe,
                        matiere=moy.matiere,
                        periode_scolaire=periode
                    ).exclude(moyenne__isnull=True).aggregate(Avg('moyenne'))['moyenne__avg']
                    moyenne_classe = round(moyenne_classe_obj, 2) if moyenne_classe_obj else None
                    
                    # Calculer la position de l'élève
                    moyennes_classe = MoyenneMatierePrimaire.objects.filter(
                        classe=eleve.classe,
                        matiere=moy.matiere,
                        periode_scolaire=periode
                    ).exclude(moyenne__isnull=True).order_by('-moyenne')
                else:
                    # Pour le collège/lycée, utiliser le modèle Moyenne existant
                    moyenne_classe = Moyenne.objects.filter(
                        classe=eleve.classe,
                        matiere=moy.matiere,
                        periode=str(periode.id),
                        actif=True
                    ).exclude(moyenne__isnull=True).aggregate(Avg('moyenne'))['moyenne__avg']
                    
                    # Calculer la position de l'élève
                    moyennes_classe = Moyenne.objects.filter(
                        classe=eleve.classe,
                        matiere=moy.matiere,
                        periode=str(periode.id),
                        actif=True
                    ).exclude(moyenne__isnull=True).order_by('-moyenne')
                
                position = None
                total_eleves = moyennes_classe.count()
                for idx, m in enumerate(moyennes_classe):
                    if etablissement.type_etablissement == 'primary':
                        if m.eleve_id == eleve.id:
                            position = idx + 1
                            break
                    else:
                        if m.eleve_id == eleve.id:
                            position = idx + 1
                            break
                
                # Récupérer le professeur qui enseigne cette matière dans cette classe
                enseignant_nom = "N/A"
                if etablissement.type_etablissement == 'primary':
                    # Pour le primaire, un professeur peut enseigner plusieurs matières (relation ManyToMany)
                    affectations = AffectationProfesseurPrimaire.objects.filter(
                        classe=eleve.classe,
                        matieres=moy.matiere
                    )
                    if affectations.exists():
                        affectation = affectations.first()
                        if affectation.professeur:
                            enseignant_nom = f"{affectation.professeur.prenom} {affectation.professeur.nom}"
                else:
                    affectation = AffectationProfesseur.objects.filter(
                        classe=eleve.classe,
                        matiere=moy.matiere
                    ).first()
                    if affectation and affectation.professeur:
                        enseignant_nom = f"{affectation.professeur.prenom} {affectation.professeur.nom}"
                
                # Déterminer l'icône et la couleur selon la matière
                matiere_nom = moy.matiere.nom.lower()
                icon = 'fas fa-book'
                color = 'neo-blue'
                
                if 'math' in matiere_nom:
                    icon = 'fas fa-calculator'
                    color = 'neo-blue'
                elif 'français' in matiere_nom or 'francais' in matiere_nom:
                    icon = 'fas fa-book'
                    color = 'neo-red'
                elif 'anglais' in matiere_nom:
                    icon = 'fas fa-language'
                    color = 'neo-purple'
                elif 'histoire' in matiere_nom or 'géographie' in matiere_nom:
                    icon = 'fas fa-globe-europe'
                    color = 'neo-green'
                elif 'svt' in matiere_nom or 'biologie' in matiere_nom or 'éveil' in matiere_nom:
                    icon = 'fas fa-leaf'
                    color = 'neo-teal'
                elif 'physique' in matiere_nom or 'chimie' in matiere_nom:
                    icon = 'fas fa-flask'
                    color = 'neo-cyan'
                elif 'sport' in matiere_nom or 'eps' in matiere_nom or 'éducation physique' in matiere_nom:
                    icon = 'fas fa-running'
                    color = 'neo-orange'
                elif 'art' in matiere_nom or 'plastique' in matiere_nom:
                    icon = 'fas fa-palette'
                    color = 'neo-pink'
                elif 'morale' in matiere_nom or 'civique' in matiere_nom:
                    icon = 'fas fa-balance-scale'
                    color = 'neo-purple'
                elif 'technologie' in matiere_nom:
                    icon = 'fas fa-microchip'
                    color = 'neo-cyan'
                elif 'musique' in matiere_nom:
                    icon = 'fas fa-music'
                    color = 'neo-light-blue'
                
                matieres_moyennes.append({
                    'matiere': moy.matiere,
                    'moyenne_eleve': moy.moyenne,
                    'moyenne_classe': moyenne_classe if moyenne_classe else None,
                    'coefficient': moy.matiere.coefficient if moy.matiere.coefficient else 1,
                    'appreciation': moy.appreciation if moy.appreciation else '',
                    'position': position,
                    'total_eleves': total_eleves,
                    'enseignant': enseignant_nom,
                    'icon': icon,
                    'color': color,
                })
        
        # Déterminer les points forts et points à améliorer
        points_forts = []
        points_ameliorer = []
        
        matieres_triees = sorted(matieres_moyennes, key=lambda x: x['moyenne_eleve'] if x['moyenne_eleve'] else 0, reverse=True)
        
        for matiere_data in matieres_triees[:3]:
            if matiere_data['moyenne_eleve'] and matiere_data['moyenne_eleve'] >= 14:
                points_forts.append(f"Excellents résultats en {matiere_data['matiere'].nom}")
        
        for matiere_data in reversed(matieres_triees[-3:]):
            if matiere_data['moyenne_eleve'] and matiere_data['moyenne_eleve'] < 12:
                points_ameliorer.append(f"Renforcer les acquis en {matiere_data['matiere'].nom}")
        
        if not points_forts:
            points_forts = ["Bon travail général"]
        if not points_ameliorer:
            points_ameliorer = ["Continuer sur cette lancée"]
        
        # Construire le tableau de notes pour cette période
        tableau_notes = []
        for matiere_data in matieres_moyennes:
            matiere = matiere_data['matiere']
            
            # Récupérer toutes les notes pour cette matière et cette période
            notes_list = []
            if etablissement.type_etablissement == 'primary':
                notes_matiere = NotePrimaire.objects.filter(
                    eleve=eleve,
                    evaluation_primaire__matiere=matiere,
                    evaluation_primaire__periode_scolaire=periode,
                    retenue=True,
                    absent=False
                ).select_related('evaluation_primaire').exclude(note__isnull=True).order_by('evaluation_primaire__date_evaluation')

                for note in notes_matiere:
                    note_sur_20 = note.note_sur_20
                    if note_sur_20 is None:
                        continue
                    notes_list.append({
                        'titre': note.evaluation_primaire.titre,
                        'note': note.note,
                        'bareme': note.evaluation_primaire.bareme,
                        'note_sur_20': round(float(note_sur_20), 2),
                    })
            else:
                # Pour collège/lycée - Récupérer les notes de la table Note
                notes_matiere = Note.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    evaluation__periode_scolaire=periode,
                    retenue=True,
                    absent=False
                ).select_related('evaluation').exclude(note__isnull=True).order_by('evaluation__date_evaluation')

                for note in notes_matiere:
                    note_sur_20 = note.note_sur_20
                    if note_sur_20 is None:
                        continue
                    notes_list.append({
                        'titre': note.evaluation.titre,
                        'note': note.note,
                        'bareme': note.evaluation.bareme or 20,
                        'note_sur_20': round(float(note_sur_20), 2),
                    })
            
            # Récupérer la note d'examen pour cette matière et cette période
            from ..model.note_examen_model import NoteExamen
            
            if etablissement.type_etablissement == 'primary':
                note_examen_qs = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere_id=matiere.id,
                    session_examen__periode=periode
                ).select_related('session_examen').order_by('-date_saisie')
            else:
                note_examen_qs = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    session_examen__periode=periode,
                    absent=False,
                    retenue=True
                ).select_related('session_examen').exclude(note_sur_20__isnull=True).order_by('-date_saisie')
                
                if not note_examen_qs.exists():
                    note_examen_qs = NoteExamen.objects.filter(
                        eleve=eleve,
                        matiere=matiere,
                        session_examen__periode=periode,
                        absent=False
                    ).select_related('session_examen').order_by('-date_saisie')
            
            note_examen_sur_20 = None
            note_examen = note_examen_qs.first()
            if note_examen:
                if note_examen.note_sur_20 is not None:
                    note_examen_sur_20 = round(float(note_examen.note_sur_20), 2)
                elif note_examen.note is not None and note_examen.bareme and note_examen.bareme > 0:
                    note_examen_sur_20 = round(float((note_examen.note / note_examen.bareme) * 20), 2)
            
            # Ajouter au tableau si on a des notes de devoirs OU une note d'examen OU une moyenne
            if notes_list or note_examen_sur_20 is not None or matiere_data['moyenne_eleve'] is not None:
                tableau_notes.append({
                    'matiere': matiere,
                    'icon': matiere_data['icon'],
                    'color': matiere_data['color'],
                    'notes': notes_list,
                    'note_examen': note_examen_sur_20,
                    'moyenne': matiere_data['moyenne_eleve'],
                })

        max_notes_count = max((len(item['notes']) for item in tableau_notes), default=0)
        notes_indices = list(range(max_notes_count))

        periodes_data.append({
            'periode': periode,
            'moyenne_generale': moyenne_generale_display,
            'matieres_moyennes': matieres_moyennes,
            'tableau_notes': tableau_notes,
            'notes_indices': notes_indices,
            'est_active': periode.est_en_cours,
            'points_forts': points_forts,
            'points_ameliorer': points_ameliorer,
        })
    
    # Récupérer les notes récentes (toutes périodes confondues)
    notes_recentes = []
    if etablissement.type_etablissement == 'primary':
        notes_primaires = NotePrimaire.objects.filter(
            eleve=eleve,
            retenue=True,
            absent=False
        ).select_related('evaluation_primaire__matiere', 'evaluation_primaire').exclude(note__isnull=True).order_by('-date_saisie')[:20]
        
        for note in notes_primaires:
            if not note.evaluation_primaire:
                continue
            
            # Récupérer la matière via l'évaluation
            matiere = note.evaluation_primaire.matiere
            if not matiere:
                continue
            
            # Déterminer l'icône et la couleur
            matiere_nom = matiere.nom.lower()
            icon = 'fas fa-book'
            color = 'neo-blue'
            
            if 'math' in matiere_nom:
                icon = 'fas fa-calculator'
                color = 'neo-blue'
            elif 'français' in matiere_nom or 'francais' in matiere_nom:
                icon = 'fas fa-book'
                color = 'neo-red'
            elif 'anglais' in matiere_nom:
                icon = 'fas fa-language'
                color = 'neo-purple'
            elif 'histoire' in matiere_nom or 'géographie' in matiere_nom:
                icon = 'fas fa-globe-europe'
                color = 'neo-green'
            elif 'svt' in matiere_nom or 'éveil' in matiere_nom:
                icon = 'fas fa-leaf'
                color = 'neo-teal'
            elif 'sport' in matiere_nom or 'eps' in matiere_nom:
                icon = 'fas fa-running'
                color = 'neo-orange'
            elif 'art' in matiere_nom or 'plastique' in matiere_nom:
                icon = 'fas fa-palette'
                color = 'neo-pink'
            
            # Vérifier que la note existe
            if note.note is None:
                continue
            
            # Calculer la note sur 20
            note_sur_20 = note.note
            if note.evaluation_primaire.bareme and note.evaluation_primaire.bareme != 20:
                note_sur_20 = (note.note / note.evaluation_primaire.bareme) * 20
            
            notes_recentes.append({
                'id': note.id,
                'titre': note.evaluation_primaire.titre,
                'matiere': matiere,
                'matiere_icon': icon,
                'matiere_color': color,
                'date': note.date_saisie,
                'note': note.note,
                'note_sur_20': round(note_sur_20, 2) if note_sur_20 else 0,
                'bareme': note.evaluation_primaire.bareme,
                'type': note.evaluation_primaire.type_evaluation,
                'coefficient': 1,  # Coefficient par défaut pour le primaire
                'commentaire': note.appreciation if note.appreciation else '',
            })
    else:
        # Pour collège/lycée - Récupérer les notes récentes de la table Note
        notes_secondaires = Note.objects.filter(
            eleve=eleve,
            retenue=True,
            absent=False
        ).select_related('evaluation__matiere', 'evaluation', 'matiere').exclude(note__isnull=True).order_by('-date_saisie')[:20]
        
        for note in notes_secondaires:
            if not note.evaluation:
                continue
            
            # Récupérer la matière
            matiere = note.matiere if note.matiere else note.evaluation.matiere
            if not matiere:
                continue
            
            # Déterminer l'icône et la couleur
            matiere_nom = matiere.nom.lower()
            icon = 'fas fa-book'
            color = 'neo-blue'
            
            if 'math' in matiere_nom:
                icon = 'fas fa-calculator'
                color = 'neo-blue'
            elif 'français' in matiere_nom or 'francais' in matiere_nom:
                icon = 'fas fa-book'
                color = 'neo-red'
            elif 'anglais' in matiere_nom:
                icon = 'fas fa-language'
                color = 'neo-purple'
            elif 'histoire' in matiere_nom or 'géographie' in matiere_nom:
                icon = 'fas fa-globe-europe'
                color = 'neo-green'
            elif 'svt' in matiere_nom or 'physique' in matiere_nom or 'chimie' in matiere_nom:
                icon = 'fas fa-flask'
                color = 'neo-teal'
            elif 'sport' in matiere_nom or 'eps' in matiere_nom:
                icon = 'fas fa-running'
                color = 'neo-orange'
            elif 'art' in matiere_nom or 'plastique' in matiere_nom:
                icon = 'fas fa-palette'
                color = 'neo-pink'
            
            # Vérifier que la note existe
            if note.note is None:
                continue
            
            notes_recentes.append({
                'id': note.id,
                'titre': note.evaluation.titre,
                'matiere': matiere,
                'matiere_icon': icon,
                'matiere_color': color,
                'date': note.date_saisie,
                'note': note.note,
                'note_sur_20': round(float(note.note), 2),
                'bareme': 20,
                'type': note.evaluation.type_evaluation,
                'coefficient': matiere.coefficient if matiere.coefficient else 1,
                'commentaire': note.appreciation if note.appreciation else '',
            })
    
    # Récupérer les évaluations à venir
    evaluations_a_venir = []
    if etablissement.type_etablissement == 'primary' and eleve.classe:
        evals = EvaluationPrimaire.objects.filter(
            classe=eleve.classe,
            date_evaluation__gte=timezone.now().date()
        ).select_related('matiere', 'professeur').order_by('date_evaluation')[:10]
        
        for ev in evals:
            evaluations_a_venir.append({
                'id': ev.id,
                'titre': ev.titre,
                'matiere': ev.matiere,
                'date': ev.date_evaluation,
                'type': ev.type_evaluation,
                'professeur': ev.professeur,
            })
    elif eleve.classe:
        # Pour collège/lycée - Récupérer les évaluations à venir de la table Evaluation
        evals = Evaluation.objects.filter(
            classe=eleve.classe,
            date_evaluation__gte=timezone.now().date()
        ).select_related('matiere', 'professeur').order_by('date_evaluation')[:10]
        
        for ev in evals:
            evaluations_a_venir.append({
                'id': ev.id,
                'titre': ev.titre,
                'matiere': ev.matiere,
                'date': ev.date_evaluation,
                'type': ev.type_evaluation,
                'professeur': ev.professeur,
            })
    
    # Récupérer toutes les matières de l'élève avec leurs notes détaillées
    matieres_avec_notes = {}
    
    if eleve.classe:
        # Récupérer toutes les matières de la classe
        from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
        
        if etablissement.type_etablissement == 'primary':
            affectations = AffectationProfesseurPrimaire.objects.filter(
                classe=eleve.classe
            ).prefetch_related('matieres')
            
            matieres = set()
            for affectation in affectations:
                matieres.update(affectation.matieres.all())
            
            # Pour chaque matière, récupérer les notes par période
            for matiere in matieres:
                # Déterminer l'icône et la couleur
                matiere_nom = matiere.nom.lower()
                icon = 'fas fa-book'
                color = 'neo-blue'
                
                if 'math' in matiere_nom:
                    icon = 'fas fa-calculator'
                    color = 'neo-blue'
                elif 'français' in matiere_nom or 'francais' in matiere_nom:
                    icon = 'fas fa-book'
                    color = 'neo-red'
                elif 'anglais' in matiere_nom:
                    icon = 'fas fa-language'
                    color = 'neo-purple'
                elif 'histoire' in matiere_nom or 'géographie' in matiere_nom:
                    icon = 'fas fa-globe-europe'
                    color = 'neo-green'
                elif 'svt' in matiere_nom or 'éveil' in matiere_nom:
                    icon = 'fas fa-leaf'
                    color = 'neo-teal'
                elif 'sport' in matiere_nom or 'eps' in matiere_nom or 'éducation physique' in matiere_nom:
                    icon = 'fas fa-running'
                    color = 'neo-orange'
                elif 'art' in matiere_nom or 'plastique' in matiere_nom:
                    icon = 'fas fa-palette'
                    color = 'neo-pink'
                elif 'morale' in matiere_nom or 'civique' in matiere_nom:
                    icon = 'fas fa-balance-scale'
                    color = 'neo-purple'
                
                # Récupérer toutes les notes de cette matière
                notes_matiere = NotePrimaire.objects.filter(
                    eleve=eleve,
                    evaluation_primaire__matiere=matiere,
                    retenue=True,
                    absent=False
                ).select_related('evaluation_primaire__periode_scolaire').exclude(note__isnull=True).order_by('-date_saisie')
                
                notes_par_periode = {}
                
                for note in notes_matiere:
                    if note.note is None or not note.evaluation_primaire:
                        continue
                    
                    periode_nom = note.evaluation_primaire.periode_scolaire.nom_periode if note.evaluation_primaire.periode_scolaire else 'Non définie'
                    
                    if periode_nom not in notes_par_periode:
                        notes_par_periode[periode_nom] = []
                    
                    # Calculer la note sur 20
                    note_sur_20 = note.note
                    if note.evaluation_primaire.bareme and note.evaluation_primaire.bareme != 20:
                        note_sur_20 = (note.note / note.evaluation_primaire.bareme) * 20
                    
                    notes_par_periode[periode_nom].append({
                        'date': note.date_saisie,
                        'titre': note.evaluation_primaire.titre,
                        'type': note.evaluation_primaire.type_evaluation,
                        'note': note.note,
                        'bareme': note.evaluation_primaire.bareme,
                        'note_sur_20': round(note_sur_20, 2) if note_sur_20 else 0,
                        'appreciation': note.appreciation if note.appreciation else '',
                        'est_examen': False,
                    })
                
                # Ajouter les notes d'examen pour chaque période
                from ..model.note_examen_model import NoteExamen
                notes_examen = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere_id=matiere.id
                ).select_related('session_examen__periode').order_by('-date_saisie')
                
                for note_ex in notes_examen:
                    if not note_ex.session_examen or not note_ex.session_examen.periode:
                        continue
                    
                    periode_nom = note_ex.session_examen.periode.nom_periode
                    
                    if periode_nom not in notes_par_periode:
                        notes_par_periode[periode_nom] = []
                    
                    note_ex_value = note_ex.note_sur_20
                    if note_ex_value is None and note_ex.note is not None and note_ex.bareme and note_ex.bareme > 0:
                        note_ex_value = (note_ex.note / note_ex.bareme) * 20
                    if note_ex_value is None:
                        continue
                    
                    notes_par_periode[periode_nom].append({
                        'date': note_ex.date_saisie,
                        'titre': note_ex.session_examen.nom_examen if note_ex.session_examen else 'Examen',
                        'type': 'Examen',
                        'note': round(float(note_ex_value), 2),
                        'bareme': 20,
                        'note_sur_20': round(float(note_ex_value), 2),
                        'appreciation': note_ex.commentaire if note_ex.commentaire else '',
                        'est_examen': True,
                    })
                
                if notes_par_periode:
                    matieres_avec_notes[matiere.id] = {
                        'matiere': matiere,
                        'icon': icon,
                        'color': color,
                        'notes_par_periode': notes_par_periode,
                        'total_notes': sum(len(notes) for notes in notes_par_periode.values()),
                    }
        else:
            # Pour collège/lycée - Récupérer les matières via AffectationProfesseur
            from ..model.affectation_model import AffectationProfesseur
            
            affectations = AffectationProfesseur.objects.filter(
                classe=eleve.classe
            ).select_related('matiere')
            
            matieres = set()
            for affectation in affectations:
                if affectation.matiere:
                    matieres.add(affectation.matiere)
            
            # Pour chaque matière, récupérer les notes par période
            for matiere in matieres:
                # Déterminer l'icône et la couleur
                matiere_nom = matiere.nom.lower()
                icon = 'fas fa-book'
                color = 'neo-blue'
                
                if 'math' in matiere_nom:
                    icon = 'fas fa-calculator'
                    color = 'neo-blue'
                elif 'français' in matiere_nom or 'francais' in matiere_nom:
                    icon = 'fas fa-book'
                    color = 'neo-red'
                elif 'anglais' in matiere_nom:
                    icon = 'fas fa-language'
                    color = 'neo-purple'
                elif 'espagnol' in matiere_nom or 'allemand' in matiere_nom:
                    icon = 'fas fa-language'
                    color = 'neo-purple'
                elif 'histoire' in matiere_nom or 'géographie' in matiere_nom:
                    icon = 'fas fa-globe-europe'
                    color = 'neo-green'
                elif 'svt' in matiere_nom or 'physique' in matiere_nom or 'chimie' in matiere_nom or 'science' in matiere_nom:
                    icon = 'fas fa-flask'
                    color = 'neo-teal'
                elif 'sport' in matiere_nom or 'eps' in matiere_nom or 'éducation physique' in matiere_nom:
                    icon = 'fas fa-running'
                    color = 'neo-orange'
                elif 'art' in matiere_nom or 'plastique' in matiere_nom:
                    icon = 'fas fa-palette'
                    color = 'neo-pink'
                elif 'philo' in matiere_nom:
                    icon = 'fas fa-brain'
                    color = 'neo-purple'
                elif 'économie' in matiere_nom or 'economie' in matiere_nom:
                    icon = 'fas fa-chart-line'
                    color = 'neo-green'
                elif 'informatique' in matiere_nom:
                    icon = 'fas fa-laptop-code'
                    color = 'neo-blue'
                
                # Récupérer toutes les notes de cette matière
                notes_matiere = Note.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    retenue=True,
                    absent=False
                ).select_related('evaluation__periode_scolaire').exclude(note__isnull=True).order_by('-date_saisie')
                
                notes_par_periode = {}
                
                for note in notes_matiere:
                    if note.note is None or not note.evaluation:
                        continue
                    
                    periode_nom = note.evaluation.periode_scolaire.nom_periode if note.evaluation.periode_scolaire else 'Non définie'
                    
                    if periode_nom not in notes_par_periode:
                        notes_par_periode[periode_nom] = []
                    
                    # Les notes secondaires sont déjà sur 20
                    notes_par_periode[periode_nom].append({
                        'date': note.date_saisie,
                        'titre': note.evaluation.titre,
                        'type': note.evaluation.type_evaluation,
                        'note': note.note,
                        'bareme': 20,
                        'note_sur_20': round(float(note.note), 2),
                        'appreciation': note.appreciation if note.appreciation else '',
                        'est_examen': False,
                    })
                
                # Ajouter les notes d'examen pour chaque période (secondaire)
                from ..model.note_examen_model import NoteExamen
                notes_examen = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    absent=False,
                    retenue=True
                ).select_related('session_examen__periode').exclude(note_sur_20__isnull=True).order_by('-date_saisie')
                
                for note_ex in notes_examen:
                    if note_ex.note_sur_20 is None or not note_ex.session_examen or not note_ex.session_examen.periode:
                        continue
                    
                    periode_nom = note_ex.session_examen.periode.nom_periode
                    
                    if periode_nom not in notes_par_periode:
                        notes_par_periode[periode_nom] = []
                    
                    notes_par_periode[periode_nom].append({
                        'date': note_ex.date_saisie,
                        'titre': note_ex.session_examen.nom_examen if note_ex.session_examen else 'Examen',
                        'type': 'Examen',
                        'note': note_ex.note_sur_20,
                        'bareme': 20,
                        'note_sur_20': round(float(note_ex.note_sur_20), 2),
                        'appreciation': note_ex.commentaire if note_ex.commentaire else '',
                        'est_examen': True,
                    })
                
                if notes_par_periode:
                    matieres_avec_notes[matiere.id] = {
                        'matiere': matiere,
                        'icon': icon,
                        'color': color,
                        'notes_par_periode': notes_par_periode,
                        'total_notes': sum(len(notes) for notes in notes_par_periode.values()),
                    }
    
    bulletin_record = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        est_moyenne_generale=True,
        afficher_bulletin=True,
        moyenne_generale__isnull=False
    ).select_related('periode').order_by('-updated_at').first()

    bulletin_disponible = bool(bulletin_record)
    bulletin_periode_label = (
        bulletin_record.periode.nom_periode
        if bulletin_record and bulletin_record.periode
        else None
    )

    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'etablissement': etablissement,
        'periodes': periodes,
        'periode_active': periode_active,
        'periodes_data': periodes_data,
        'notes_recentes': notes_recentes,
        'evaluations_a_venir': evaluations_a_venir,
        'matieres_avec_notes': matieres_avec_notes,
        'bulletin_disponible': bulletin_disponible,
        'bulletin_periode_label': bulletin_periode_label,
        'bulletin_url': reverse('eleve:bulletin_eleve'),
        'today': timezone.now().date(),
    }
    
    return render(request, 'school_admin/eleve/notes_evaluations_eleve.html', context)


def bulletin_eleve(request):
    """
    Affiche le bulletin de l'élève dans son espace personnel.
    """
    eleve, est_parent = get_eleve_from_request(request)

    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    if not eleve.classe:
        messages.info(request, "Aucune classe n'est associée à votre profil.")
        return redirect('eleve:notes_evaluations')

    etablissement = eleve.etablissement
    if not etablissement:
        messages.warning(request, "Aucun établissement n'est associé à votre profil.")
        return redirect('eleve:notes_evaluations')

    from ..model.moyenne_periode_model import MoyennePeriode
    from ..model.periode_model import PeriodeScolaire
    from ..model.presence_model import Presence

    periode_param = request.GET.get('periode')
    bulletins_qs = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        est_moyenne_generale=True,
        afficher_bulletin=True,
        moyenne_generale__isnull=False
    ).select_related('periode').order_by('-updated_at')

    if periode_param:
        bulletins_qs = bulletins_qs.filter(periode_id=periode_param)

    moyenne_generale_record = bulletins_qs.first()
    if not moyenne_generale_record:
        messages.warning(request, "Votre bulletin n'est pas encore disponible.")
        return redirect('eleve:notes_evaluations')

    periode = moyenne_generale_record.periode
    if not periode:
        periode = PeriodeScolaire.objects.filter(
            etablissement=etablissement,
            est_active=True
        ).order_by('date_debut').first()
        if not periode:
            messages.warning(request, "Aucune période scolaire active n'est configurée.")
            return redirect('eleve:notes_evaluations')

    matieres_qs = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        periode=periode,
        est_moyenne_generale=False
    ).select_related('matiere').order_by('matiere__nom')

    matieres_table = []
    for moyenne in matieres_qs:
        if not moyenne.matiere:
            continue
        matieres_table.append({
            'nom': moyenne.matiere.nom,
            'moyenne_classe': float(moyenne.moyenne_classe) if moyenne.moyenne_classe is not None else None,
            'note_examen': float(moyenne.note_examen) if moyenne.note_examen is not None else None,
            'coefficient': float(moyenne.coefficient) if moyenne.coefficient is not None else 1,
            'moyenne_eleve': float(moyenne.moyenne_matiere) if moyenne.moyenne_matiere is not None else None,
            'rang': moyenne.rang,
            'appreciation': moyenne.appreciation_matiere or '',
        })

    if not matieres_table:
        messages.warning(request, "Le bulletin de cette période n'est pas encore complet.")
        return redirect('eleve:notes_evaluations')

    moyenne_generale = (
        float(moyenne_generale_record.moyenne_generale)
        if moyenne_generale_record.moyenne_generale is not None
        else None
    )
    appreciation_generale = moyenne_generale_record.appreciation_generale
    decision_conseil = moyenne_generale_record.decision_conseil

    standards_bundle = _get_standards_bundle(etablissement)
    appreciation_generale, decision_conseil, standards_extra = _apply_standards_to_bulletin(
        matieres_table,
        moyenne_generale,
        appreciation_generale,
        decision_conseil,
        standards_bundle
    )

    soumissions = sum(1 for item in matieres_table if item['moyenne_eleve'] is not None)
    total_matieres = len(matieres_table)
    pourcentage_soumission = round((soumissions / total_matieres) * 100, 1) if total_matieres else 0
    bulletin_disponible = soumissions > 0
    classe_effectif = eleve.classe.eleves.filter(actif=True).count()

    absences_justifiees = Presence.objects.filter(
        eleve=eleve,
        classe=eleve.classe,
        date__gte=periode.date_debut,
        date__lte=periode.date_fin,
        statut='absent_justifie'
    ).count()

    absences_non_justifiees = Presence.objects.filter(
        eleve=eleve,
        classe=eleve.classe,
        date__gte=periode.date_debut,
        date__lte=periode.date_fin,
        statut='absent'
    ).count()

    complement_info = {
        'moyenne_periode': moyenne_generale,
        'moyenne_annuelle': None,
        'rang_general': moyenne_generale_record.rang,
        'effectif': classe_effectif,
        'absences_justifiees': absences_justifiees,
        'absences_non_justifiees': absences_non_justifiees,
        'appreciation_generale': appreciation_generale,
        'decision_conseil': decision_conseil,
    }

    if standards_extra:
        complement_info.update({
            'appreciation_generale_standard': standards_extra['appreciation_generale_standard'],
            'appreciation_generale_source': standards_extra['appreciation_generale_source'],
            'decision_conseil_standard': standards_extra['decision_conseil_standard'],
            'decision_conseil_source': standards_extra['decision_conseil_source'],
            'statut_conseil_code': standards_extra['statut_conseil_code'],
            'statut_conseil_label': standards_extra['statut_conseil_label'],
        })

    context = {
        'page_title': "Bulletin de notes",
        'eleve': eleve,
        'est_parent': est_parent,
        'etablissement': etablissement,
        'classe': eleve.classe,
        'periode': moyenne_generale_record.periode or periode,
        'est_primaire': etablissement.type_etablissement == 'primary',
        'matieres_table': matieres_table,
        'moyenne_generale': moyenne_generale,
        'bulletin_valide': bool(moyenne_generale_record.est_publie or bulletin_disponible),
        'bulletin_disponible': bulletin_disponible,
        'soumissions': soumissions,
        'total_matieres': total_matieres,
        'pourcentage_soumission': pourcentage_soumission,
        'retour_url': reverse('eleve:notes_evaluations'),
        'releve_classe_url': None,
        'date_generation': timezone.now(),
        'classe_effectif': classe_effectif,
        'rang_general': moyenne_generale_record.rang,
        'complement_info': complement_info,
        'impression_url': request.build_absolute_uri(request.get_full_path()),
        'standards_summary': standards_extra['standards_summary'] if standards_extra else None,
        'standards_applied': bool(standards_bundle),
        'bulletin_qr_image_url': moyenne_generale_record.qr_code_image.url if moyenne_generale_record.qr_code_image else None,
        'bulletin_qr_data': moyenne_generale_record.qr_code_data,
        'bulletin_qr_generated_at': moyenne_generale_record.qr_code_generated_at,
        'bulletin_signature': moyenne_generale_record.signature_numerique,
        'bulletin_numero_serie': moyenne_generale_record.numero_serie,
    }

    return render(request, 'school_admin/eleve/bulletin_eleve.html', context)


def absences_retards_eleve(request):
    """
    Page des absences et retards pour les élèves
    Accessible par l'élève ou son parent
    """
    logger.info(f"Absences et retards - User: {request.user}, Type: {type(request.user).__name__}")
    
    # Utiliser la fonction helper pour récupérer l'élève
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = eleve.etablissement
    
    from ..model.periode_model import PeriodeScolaire
    from django.db.models import Count, Q
    from datetime import timedelta
    
    # Récupérer la période active
    periode_active = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    ).order_by('-date_debut').first()
    
    # Calculer les statistiques globales
    presences_totales = Presence.objects.filter(eleve=eleve)
    
    total_jours = presences_totales.count()
    total_presences = presences_totales.filter(statut='present').count()
    total_absences = presences_totales.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
    total_retards = presences_totales.filter(statut='retard').count()
    absences_justifiees = presences_totales.filter(statut='absent_justifie').count()
    absences_non_justifiees = presences_totales.filter(statut='absent').count()
    
    # Calculer le taux de présence
    taux_presence = 0
    if total_jours > 0:
        taux_presence = round((total_presences / total_jours) * 100, 1)
    
    # Récupérer les absences et retards par période et par mois
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    ).order_by('date_debut')
    
    from collections import defaultdict
    import calendar
    
    periodes_data = []
    for periode in periodes:
        presences_periode = Presence.objects.filter(
            eleve=eleve,
            date__gte=periode.date_debut,
            date__lte=periode.date_fin
        )
        
        absences_periode = presences_periode.filter(Q(statut='absent') | Q(statut='absent_justifie')).order_by('-date')
        retards_periode = presences_periode.filter(statut='retard').order_by('-date')
        
        # Regrouper par mois
        mois_data = defaultdict(lambda: {'absences': [], 'retards': []})
        
        for absence in absences_periode:
            mois_key = absence.date.strftime('%Y-%m')
            mois_nom = f"{calendar.month_name[absence.date.month]} {absence.date.year}"
            mois_data[mois_key]['mois_nom'] = mois_nom
            mois_data[mois_key]['mois_numero'] = absence.date.month
            mois_data[mois_key]['annee'] = absence.date.year
            mois_data[mois_key]['absences'].append(absence)
        
        for retard in retards_periode:
            mois_key = retard.date.strftime('%Y-%m')
            mois_nom = f"{calendar.month_name[retard.date.month]} {retard.date.year}"
            mois_data[mois_key]['mois_nom'] = mois_nom
            mois_data[mois_key]['mois_numero'] = retard.date.month
            mois_data[mois_key]['annee'] = retard.date.year
            mois_data[mois_key]['retards'].append(retard)
        
        # Convertir en liste triée par date (plus récent d'abord)
        mois_liste = []
        for mois_key in sorted(mois_data.keys(), reverse=True):
            data = mois_data[mois_key]
            mois_liste.append({
                'mois_key': mois_key,
                'mois_nom': data['mois_nom'],
                'mois_numero': data['mois_numero'],
                'annee': data['annee'],
                'absences': data['absences'],
                'retards': data['retards'],
                'nb_absences': len(data['absences']),
                'nb_retards': len(data['retards']),
            })
        
        periodes_data.append({
            'periode': periode,
            'est_active': periode.est_en_cours,
            'absences': absences_periode,
            'retards': retards_periode,
            'nb_absences': absences_periode.count(),
            'nb_retards': retards_periode.count(),
            'mois_liste': mois_liste,
        })
    
    # Récupérer les absences et retards récents (30 derniers jours)
    date_limite = timezone.now().date() - timedelta(days=30)
    
    absences_recentes = Presence.objects.filter(
        Q(statut='absent') | Q(statut='absent_justifie'),
        eleve=eleve,
        date__gte=date_limite
    ).order_by('-date')[:10]
    
    retards_recents = Presence.objects.filter(
        eleve=eleve,
        statut='retard',
        date__gte=date_limite
    ).order_by('-date')[:10]
    
    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'etablissement': etablissement,
        'periode_active': periode_active,
        'periodes_data': periodes_data,
        'total_jours': total_jours,
        'total_presences': total_presences,
        'total_absences': total_absences,
        'total_retards': total_retards,
        'absences_justifiees': absences_justifiees,
        'absences_non_justifiees': absences_non_justifiees,
        'taux_presence': taux_presence,
        'absences_recentes': absences_recentes,
        'retards_recents': retards_recents,
        'today': timezone.now().date(),
    }
    
    return render(request, 'school_admin/eleve/absences_retards_eleve.html', context)


def profil_eleve(request):
    """
    Page de profil de l'élève (lecture seule)
    Accessible par l'élève ou son parent
    """
    logger.info(f"Profil élève - User: {request.user}, Type: {type(request.user).__name__}")
    
    # Utiliser la fonction helper pour récupérer l'élève
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = eleve.etablissement
    
    from ..model.periode_model import PeriodeScolaire
    from django.db.models import Avg, Count, Q
    
    # Récupérer la période active
    periode_active = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    ).order_by('-date_debut').first()
    
    # Statistiques de présence
    presences = Presence.objects.filter(eleve=eleve)
    total_jours = presences.count()
    total_presences = presences.filter(statut='present').count()
    total_absences = presences.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
    total_retards = presences.filter(statut='retard').count()
    
    taux_presence = 0
    if total_jours > 0:
        taux_presence = round((total_presences / total_jours) * 100, 1)
    
    # Récupérer les parents liés à l'élève
    from ..model.lien_familial_model import LienFamilial
    from ..model.parent_model import Parent
    
    liens_familiaux = LienFamilial.objects.filter(
        eleve=eleve,
        actif=True,
        statut='valide'
    ).select_related('parent').order_by('type_lien')
    
    # Organiser les parents par type
    parents_data = {
        'pere': None,
        'mere': None,
        'tuteurs': []
    }
    
    parent_inscripteur = None
    
    for lien in liens_familiaux:
        parent_info = {
            'nom_complet': lien.parent.nom_complet,
            'matricule': lien.parent.matricule_parental,
            'telephone': lien.parent.telephone,
            'email': lien.parent.email,
            'adresse': lien.parent.adresse if lien.parent.adresse else "Non renseignée",
            'profession': lien.parent.profession if lien.parent.profession else "Non renseignée",
            'type_lien': lien.get_type_lien_display()
        }
        
        if lien.type_lien == 'pere':
            parents_data['pere'] = parent_info
        elif lien.type_lien == 'mere':
            parents_data['mere'] = parent_info
        elif lien.type_lien == 'tuteur':
            parents_data['tuteurs'].append(parent_info)
        
        if lien.est_inscripteur:
            parent_inscripteur = parent_info
    
    # Calcul de l'année scolaire pour la carte d'identité
    if periode_active and getattr(periode_active, "annee_scolaire", None):
        carte_annee_scolaire = periode_active.annee_scolaire
    else:
        today = timezone.now().date()
        if today.month >= 9:
            carte_annee_scolaire = f"{today.year}-{today.year + 1}"
        else:
            carte_annee_scolaire = f"{today.year - 1}-{today.year}"

    # Gestion du formulaire de photo de profil sans Django forms
    photo_errors = []
    photo_modal_open = False

    if request.method == "POST" and request.POST.get("action") == "upload-photo":
        photo_modal_open = True

        if est_parent:
            messages.error(
                request,
                "Seul l'élève connecté peut modifier sa photo de profil.",
            )
            return redirect("eleve:profil_eleve")

        uploaded_file = request.FILES.get("photo_profil")

        if not uploaded_file:
            photo_errors.append("Veuillez sélectionner une image.")
        else:
            if uploaded_file.size > MAX_PHOTO_SIZE_BYTES:
                photo_errors.append("L'image est trop volumineuse (maximal 5 Mo).")

            content_type = getattr(uploaded_file, "content_type", "")
            if content_type not in ALLOWED_PHOTO_CONTENT_TYPES:
                photo_errors.append("Formats autorisés : JPG, PNG ou WebP.")

        if not photo_errors:
            try:
                filename, content = _build_portrait_photo(uploaded_file)
            except ValueError as exc:
                photo_errors.append(str(exc))
            else:
                if eleve.photo_profil:
                    eleve.photo_profil.delete(save=False)
                eleve.photo_profil.save(
                    filename,
                    ContentFile(content),
                    save=True,
                )
                messages.success(
                    request,
                    "Votre photo de profil a été mise à jour avec succès.",
                )
                return redirect("eleve:profil_eleve")
    
    # Statistiques de notes
    if etablissement.type_etablissement == 'primary':
        from ..model.note_primaire_model import MoyenneMatierePrimaire
        
        # Moyenne générale
        if periode_active:
            moyennes = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                periode_scolaire=periode_active
            ).exclude(moyenne__isnull=True)
            
            total_pondere = 0
            total_coefficients = 0
            nb_matieres = 0
            
            for moy in moyennes:
                if moy.moyenne and moy.matiere:
                    coef = moy.matiere.coefficient if moy.matiere.coefficient else 1
                    total_pondere += moy.moyenne * coef
                    total_coefficients += coef
                    nb_matieres += 1
            
            moyenne_generale = round(total_pondere / total_coefficients, 2) if total_coefficients > 0 else None
        else:
            moyenne_generale = None
            nb_matieres = 0
    else:
        from ..model.moyenne_model import Moyenne
        
        if periode_active:
            moyennes = Moyenne.objects.filter(
                eleve=eleve,
                periode=str(periode_active.id),
                actif=True
            ).exclude(moyenne__isnull=True)
            
            total_pondere = 0
            total_coefficients = 0
            nb_matieres = 0
            
            for moy in moyennes:
                if moy.moyenne and moy.matiere:
                    coef = moy.matiere.coefficient if moy.matiere.coefficient else 1
                    total_pondere += moy.moyenne * coef
                    total_coefficients += coef
                    nb_matieres += 1
            
            moyenne_generale = round(total_pondere / total_coefficients, 2) if total_coefficients > 0 else None
        else:
            moyenne_generale = None
            nb_matieres = 0
    
    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'etablissement': etablissement,
        'periode_active': periode_active,
        'taux_presence': taux_presence,
        'total_absences': total_absences,
        'total_retards': total_retards,
        'moyenne_generale': moyenne_generale,
        'nb_matieres': nb_matieres,
        'parents_data': parents_data,
        'parent_inscripteur': parent_inscripteur,
        'today': timezone.now().date(),
        'photo_errors': photo_errors,
        'photo_modal_open': photo_modal_open,
        'carte_annee_scolaire': carte_annee_scolaire,
    }
    
    return render(request, 'school_admin/eleve/profil_eleve.html', context)


def sanctions_eleve(request):
    """
    Page des sanctions disciplinaires.
    Accessible à l'élève connecté ou à son parent.
    """
    logger.info(f"Sanctions élève - User: {request.user}, Type: {type(request.user).__name__}")

    eleve, est_parent = get_eleve_from_request(request)

    if not eleve:
        if isinstance(request.user, Parent):
            messages.error(request, "Aucun élève sélectionné ou accès non autorisé.")
            return redirect('school_admin:dashboard_parent')
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')

    etablissement = eleve.etablissement
    
    # Récupérer toutes les sanctions de l'élève
    sanctions = Sanction.objects.filter(
        eleve=eleve
    ).select_related('classe', 'professeur', 'etablissement').order_by('-date_sanction', '-date_creation')
    
    # Calculer les statistiques globales
    total_sanctions = sanctions.count()
    sanctions_legeres = sanctions.filter(gravite='legere').count()
    sanctions_moyennes = sanctions.filter(gravite='moyenne').count()
    sanctions_graves = sanctions.filter(gravite='grave').count()
    sanctions_tres_graves = sanctions.filter(gravite='tres_grave').count()
    
    # Organiser par type de sanction
    sanctions_par_type = {}
    for sanction in sanctions:
        type_sanction = sanction.get_type_sanction_display()
        if type_sanction not in sanctions_par_type:
            sanctions_par_type[type_sanction] = []
        sanctions_par_type[type_sanction].append(sanction)
    
    # Organiser par période scolaire si disponible
    from school_admin.model.periode_model import PeriodeScolaire
    from collections import defaultdict
    
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    ).order_by('-date_debut')
    
    sanctions_par_periode = []
    for periode in periodes:
        sanctions_periode = sanctions.filter(
            date_sanction__gte=periode.date_debut,
            date_sanction__lte=periode.date_fin
        ).order_by('-date_sanction')
        
        if sanctions_periode.exists():
            sanctions_par_periode.append({
                'periode': periode,
                'sanctions': sanctions_periode,
                'nb_sanctions': sanctions_periode.count(),
                'nb_graves': sanctions_periode.filter(gravite__in=['grave', 'tres_grave']).count(),
            })
    
    # Sanctions récentes (30 derniers jours)
    date_limite = timezone.now().date() - timedelta(days=30)
    sanctions_recentes = sanctions.filter(date_sanction__gte=date_limite).order_by('-date_sanction')[:10]
    
    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'etablissement': etablissement,
        'sanctions': sanctions,
        'sanctions_recentes': sanctions_recentes,
        'total_sanctions': total_sanctions,
        'sanctions_legeres': sanctions_legeres,
        'sanctions_moyennes': sanctions_moyennes,
        'sanctions_graves': sanctions_graves,
        'sanctions_tres_graves': sanctions_tres_graves,
        'sanctions_par_type': sanctions_par_type,
        'sanctions_par_periode': sanctions_par_periode,
        'periodes': periodes,
        'today': timezone.now().date(),
    }
    
    return render(request, 'school_admin/eleve/sanctions_eleve.html', context)


def annonces_eleve(request):
    """
    Affiche les annonces destinées aux élèves.
    """
    # Utiliser la fonction helper pour récupérer l'élève
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    from ..model.annonce_model import Annonce
    from django.db.models import Q
    from datetime import timedelta
    
    # Récupérer les annonces publiées destinées aux élèves ou à tous
    annonces = Annonce.objects.filter(
        Q(etablissement=eleve.etablissement) &
        Q(statut='publiee') &
        Q(actif=True) &
        (Q(destinataires__contains=['tous']) | 
         Q(destinataires__contains=['eleves']))
    ).order_by('-date_publication', '-date_creation')
    
    # Filtrer par date si demandé
    filtre_periode = request.GET.get('periode', '')
    today = timezone.now().date()
    
    if filtre_periode:
        if filtre_periode == 'semaine':
            date_debut = today - timedelta(days=7)
            annonces = annonces.filter(date_publication__gte=date_debut)
        elif filtre_periode == 'mois':
            date_debut = today - timedelta(days=30)
            annonces = annonces.filter(date_publication__gte=date_debut)
        elif filtre_periode == 'trimestre':
            date_debut = today - timedelta(days=90)
            annonces = annonces.filter(date_publication__gte=date_debut)
    
    # Statistiques
    total_annonces = annonces.count()
    date_semaine = today - timedelta(days=7)
    annonces_cette_semaine = annonces.filter(
        date_publication__gte=date_semaine
    ).count() if annonces.exists() else 0
    
    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'annonces': annonces,
        'total_annonces': total_annonces,
        'annonces_cette_semaine': annonces_cette_semaine,
        'filtre_periode': filtre_periode,
    }
    
    return render(request, 'school_admin/eleve/annonces_eleve.html', context)


def notifications_eleve(request):
    """Affiche les notifications reçues par l'élève."""
    eleve, est_parent = get_eleve_from_request(request)

    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    notifications = list(
        NotificationEleve.objects.filter(eleve=eleve)
        .order_by('-date_creation')
    )
    notification_ids = [notif.id for notif in notifications]

    if notification_ids:
        NotificationEleve.objects.filter(id__in=notification_ids).update(
            statut='lu',
            date_lecture=timezone.now(),
            date_modification=timezone.now(),
        )

    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'notifications': notifications,
        'notifications_eleve_non_lues': 0,
    }

    response = render(
        request,
        'school_admin/eleve/notifications_eleve.html',
        context,
    )

    if notification_ids:
        NotificationEleve.objects.filter(id__in=notification_ids).delete()

    return response
