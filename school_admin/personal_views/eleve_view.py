"""
Vues pour l'espace élève
"""
from django.shortcuts import render, redirect, get_object_or_404
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
from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
from school_admin.model.presence_model import Presence
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
from school_admin.model.parent_model import Parent
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.sanction_model import Sanction
from school_admin.model.notification_eleve_model import NotificationEleve
from ..model.exercice_maison_model import ExerciceMaison
from ..utils.session_utils import get_session_active
from ..model.inscription_eleve_model import InscriptionEleve
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


def get_classe_eleve_active(eleve, annee_scolaire_active, etablissement=None):
    """
    Récupère la classe de l'élève pour l'année scolaire active depuis InscriptionEleve.
    Retourne None si l'élève n'est pas inscrit pour cette année.
    
    Args:
        eleve: L'objet Eleve
        annee_scolaire_active: L'objet AnneeScolaire active
        etablissement: L'établissement (optionnel, utilise eleve.etablissement si non fourni)
    
    Returns:
        Classe ou None
    """
    if not annee_scolaire_active:
        # Fallback sur eleve.classe si pas d'année scolaire active
        return eleve.classe
    
    if not etablissement:
        etablissement = eleve.etablissement
    
    if not etablissement:
        return eleve.classe
    
    try:
        inscription = InscriptionEleve.objects.filter(
            eleve=eleve,
            annee_scolaire=annee_scolaire_active,
            etablissement=etablissement
        ).select_related('classe').first()
        
        if inscription and inscription.classe:
            return inscription.classe
    except Exception:
        pass
    
    # Fallback sur eleve.classe si aucune inscription trouvée
    return eleve.classe


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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if eleve.etablissement:
        annee_scolaire_active = get_session_active(request, eleve.etablissement)
    
    try:
        # Date d'aujourd'hui
        date_aujourdhui = timezone.now().date()
        
        # Calculer la moyenne générale (désactivé temporairement pour debug)
        moyenne_generale = None
        periode_active = None
        if eleve.etablissement:
            from ..model.periode_model import PeriodeScolaire
            from ..model.moyenne_periode_model import MoyennePeriode

            # Utiliser la méthode get_periode_active qui vérifie les dates et est_active
            periode_query = PeriodeScolaire.objects.filter(etablissement=eleve.etablissement, est_active=True)
            if annee_scolaire_active:
                periode_query = periode_query.filter(annee_scolaire_fk=annee_scolaire_active)
            periode_active = periode_query.filter(
                date_debut__lte=date_aujourdhui,
                date_fin__gte=date_aujourdhui
            ).first()
            
            # Si aucune période active trouvée, prendre la dernière période de l'établissement
            if not periode_active:
                periodes_qs = PeriodeScolaire.objects.filter(etablissement=eleve.etablissement)
                if annee_scolaire_active:
                    periodes_qs = periodes_qs.filter(annee_scolaire_fk=annee_scolaire_active)
                periode_active = periodes_qs.order_by('-date_debut').first()

            moyenne_obj = None
            if periode_active:
                moyenne_obj_qs = MoyennePeriode.objects.filter(
                    eleve=eleve,
                    etablissement=eleve.etablissement,
                    periode=periode_active,
                    est_moyenne_generale=True,
                    afficher_bulletin=True
                )
                if annee_scolaire_active:
                    moyenne_obj_qs = moyenne_obj_qs.filter(annee_scolaire=annee_scolaire_active)
                moyenne_obj = moyenne_obj_qs.order_by('-updated_at').first()

            if not moyenne_obj:
                moyenne_obj_qs = MoyennePeriode.objects.filter(
                    eleve=eleve,
                    etablissement=eleve.etablissement,
                    est_moyenne_generale=True,
                    afficher_bulletin=True
                )
                if annee_scolaire_active:
                    moyenne_obj_qs = moyenne_obj_qs.filter(annee_scolaire=annee_scolaire_active)
                moyenne_obj = moyenne_obj_qs.order_by('-updated_at').first()

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
                notes_queryset = NotePrimaire.objects.filter(eleve=eleve, absent=False)
                if annee_scolaire_active:
                    notes_queryset = notes_queryset.filter(annee_scolaire=annee_scolaire_active)
                notes_queryset = notes_queryset.select_related('evaluation_primaire', 'evaluation_primaire__matiere').order_by('-evaluation_primaire__date_evaluation')[:3]
                
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
                notes_queryset = Note.objects.filter(eleve=eleve)
                if annee_scolaire_active:
                    notes_queryset = notes_queryset.filter(annee_scolaire=annee_scolaire_active)
                notes_queryset = notes_queryset.select_related('evaluation', 'evaluation__matiere').order_by('-evaluation__date_evaluation')[:3]
                
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
        presences = Presence.objects.filter(eleve=eleve)
        if annee_scolaire_active:
            presences = presences.filter(annee_scolaire=annee_scolaire_active)
        else:
            # Fallback: utiliser la date de début d'année si pas d'année scolaire active
            debut_annee = timezone.now().replace(month=9, day=1, hour=0, minute=0, second=0, microsecond=0)
            if timezone.now().month < 9:
                debut_annee = debut_annee.replace(year=debut_annee.year - 1)
            presences = presences.filter(date__gte=debut_annee)
        
        total_presences = presences.count()
        presences_absentes = presences.filter(statut='absent').count()
        presences_retards = presences.filter(statut='retard').count()
        jours_present = total_presences - presences_absentes
        
        if total_presences > 0:
            taux_presence = round((jours_present / total_presences) * 100, 1)
        else:
            taux_presence = 100
        
        # Récupérer la classe de l'élève pour l'année scolaire active
        classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, eleve.etablissement)
        
        # Récupérer les prochains cours d'aujourd'hui
        prochains_cours = []
        emploi_non_publie = False
        if classe_active:
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
                classe=classe_active,
                est_actif=True,
            )
            if annee_scolaire_active:
                emplois_actifs = emplois_actifs.filter(annee_scolaire_fk=annee_scolaire_active)
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

        if classe_active:
            exercices_qs = ExerciceMaison.objects.filter(
                classe=classe_active,
                actif=True
            )
            if eleve.etablissement:
                exercices_qs = exercices_qs.filter(etablissement=eleve.etablissement)
            if annee_scolaire_active:
                exercices_qs = exercices_qs.filter(annee_scolaire=annee_scolaire_active)
            exercices_qs = exercices_qs.select_related('matiere')

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
        
        annonces_query = Annonce.objects.filter(
            Q(etablissement=eleve.etablissement) &
            Q(statut='publiee') &
            Q(actif=True) &
            (Q(destinataires__contains=['tous']) | 
             Q(destinataires__contains=['eleves']))
        )
        if annee_scolaire_active:
            annonces_query = annonces_query.filter(annee_scolaire=annee_scolaire_active)
        nombre_annonces = annonces_query.count()
        
        context = {
            'page_title': 'Tableau de bord',
            'eleve': eleve,
            'est_parent': est_parent,
            'moyenne_generale': moyenne_generale,
            'periode_active': periode_active,
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
            'annee_scolaire_active': annee_scolaire_active,
            'classe': classe_active,
        }
        
        return render(request, 'school_admin/eleve/dashboard_eleve.html', context)
        
    except Exception as e:
        messages.error(request, f"Erreur lors du chargement du tableau de bord : {str(e)}")
        return redirect('school_admin:connexion_compte_user')


def devoirs_eleve(request):
    """
    Liste exhaustive des évaluations et exercices programmés pour l'élève.
    Deux onglets principaux : Évaluations et Exercices.
    Filtrage par période avec sous-onglets.
    """
    eleve, est_parent = get_eleve_from_request(request)

    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if eleve.etablissement:
        annee_scolaire_active = get_session_active(request, eleve.etablissement)
    
    # Récupérer l'inscription de l'élève pour l'année scolaire active
    # C'est depuis l'inscription qu'on récupère la classe et l'établissement de cette année scolaire
    inscription_active = None
    if annee_scolaire_active and eleve.etablissement:
        inscription_active = InscriptionEleve.objects.filter(
            eleve=eleve,
            annee_scolaire=annee_scolaire_active,
            etablissement=eleve.etablissement
        ).select_related('classe', 'etablissement').first()
    
    # Récupérer la classe de l'élève pour l'année scolaire active depuis l'inscription
    classe_active = None
    etablissement_inscription = None
    if inscription_active:
        classe_active = inscription_active.classe
        etablissement_inscription = inscription_active.etablissement
    else:
        # Fallback : utiliser la fonction helper si pas d'inscription trouvée
        classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, eleve.etablissement)
        etablissement_inscription = eleve.etablissement
    
    if not classe_active:
        messages.info(request, "Aucune classe n'est associée à votre profil pour l'année scolaire active.")
        return redirect('eleve:dashboard_eleve')

    # Déterminer si l'établissement de l'inscription est de type primaire
    # C'est le type d'établissement de l'année scolaire active qui détermine quel modèle d'évaluation utiliser
    est_primaire = False
    if etablissement_inscription:
        type_etablissement = getattr(etablissement_inscription, 'type_etablissement', None)
        est_primaire = type_etablissement == 'primary'

    date_aujourdhui = timezone.now().date()
    debut_semaine = date_aujourdhui - timedelta(days=date_aujourdhui.weekday())
    fin_semaine = debut_semaine + timedelta(days=6)

    # Récupérer les paramètres de l'onglet et de la période
    onglet_actif = request.GET.get('onglet', 'evaluations')  # 'evaluations' ou 'exercices'
    periode_selectionnee = request.GET.get('periode', 'all')

    # ========== GESTION DES ÉVALUATIONS ==========
    # Utiliser EvaluationPrimaire pour les établissements primaires
    # Utiliser Evaluation pour les établissements secondaires (collège, lycée, collège_lycée, mixte)
    if est_primaire:
        evaluations_base = EvaluationPrimaire.objects.filter(
            classe=classe_active,
            actif=True
        )
        if annee_scolaire_active:
            evaluations_base = evaluations_base.filter(annee_scolaire=annee_scolaire_active)
        evaluations_base = evaluations_base.select_related('matiere', 'professeur', 'periode_scolaire').order_by('date_evaluation')
    else:
        evaluations_base = Evaluation.objects.filter(
            classe=classe_active,
            actif=True
        )
        if annee_scolaire_active:
            evaluations_base = evaluations_base.filter(annee_scolaire=annee_scolaire_active)
        evaluations_base = evaluations_base.select_related('matiere', 'professeur', 'periode_scolaire').order_by('date_evaluation')

    total_evaluations = evaluations_base.count()

    # Récupérer toutes les périodes pour les évaluations
    periodes_evaluations = [{
        'id': 'all',
        'nom': 'Toutes les périodes',
        'total': total_evaluations,
    }]
    total_sans_periode_eval = evaluations_base.filter(periode_scolaire__isnull=True).count()
    if total_sans_periode_eval:
        periodes_evaluations.append({
            'id': 'none',
            'nom': 'Sans période',
            'total': total_sans_periode_eval,
        })
    
    periodes_stats_eval = evaluations_base.filter(periode_scolaire__isnull=False).values(
        'periode_scolaire_id',
        'periode_scolaire__nom_periode'
    ).annotate(total=Count('id')).order_by('periode_scolaire__date_debut', 'periode_scolaire__nom_periode')

    for stat in periodes_stats_eval:
        periodes_evaluations.append({
            'id': str(stat['periode_scolaire_id']),
            'nom': stat['periode_scolaire__nom_periode'],
            'total': stat['total'],
        })

    # Filtrer les évaluations par période
    evaluations_filtres = evaluations_base
    if periode_selectionnee != 'all' and onglet_actif == 'evaluations':
        if periode_selectionnee == 'none':
            evaluations_filtres = evaluations_filtres.filter(periode_scolaire__isnull=True)
        else:
            try:
                periode_id = int(periode_selectionnee)
                evaluations_filtres = evaluations_filtres.filter(periode_scolaire_id=periode_id)
            except (TypeError, ValueError):
                pass

    evaluations_list = []
    for evaluation in evaluations_filtres:
        delta = (evaluation.date_evaluation - date_aujourdhui).days
        if delta < 0:
            statut = 'passe'
            statut_label = "Passée"
        elif delta == 0:
            statut = 'aujourdhui'
            statut_label = "Aujourd'hui"
        elif delta == 1:
            statut = 'demain'
            statut_label = "Demain"
        elif delta <= 7:
            statut = 'proche'
            statut_label = f"Dans {delta} jours"
        else:
            statut = 'planifie'
            statut_label = f"Dans {delta} jours"

        evaluations_list.append({
            'id': evaluation.id,
            'titre': evaluation.titre,
            'matiere': evaluation.matiere.nom if evaluation.matiere else "Matière non définie",
            'description': evaluation.description.strip() if evaluation.description else "",
            'date_evaluation': evaluation.date_evaluation,
            'professeur': getattr(evaluation.professeur, 'nom_complet', str(evaluation.professeur)),
            'periode': evaluation.periode_scolaire.nom_periode if evaluation.periode_scolaire else "Sans période",
            'bareme': evaluation.bareme,
            'statut': statut,
            'statut_label': statut_label,
            'jours_restant': delta,
            'jours_restant_abs': abs(delta),
        })

    # ========== GESTION DES EXERCICES ==========
    # Filtrer les exercices par classe, établissement et année scolaire de l'inscription active
    exercices_base = ExerciceMaison.objects.filter(
        classe=classe_active,
        actif=True
    )
    if etablissement_inscription:
        exercices_base = exercices_base.filter(etablissement=etablissement_inscription)
    if annee_scolaire_active:
        exercices_base = exercices_base.filter(annee_scolaire=annee_scolaire_active)
    exercices_base = exercices_base.select_related('matiere', 'professeur', 'periode_scolaire').order_by('date_rendu')

    total_exercices = exercices_base.count()
    total_semaine = exercices_base.filter(date_rendu__range=(debut_semaine, fin_semaine)).count()
    total_a_venir = exercices_base.filter(date_rendu__gte=date_aujourdhui).count()

    # Récupérer toutes les périodes pour les exercices
    periodes_exercices = [{
        'id': 'all',
        'nom': 'Toutes les périodes',
        'total': total_exercices,
    }]
    total_sans_periode_ex = exercices_base.filter(periode_scolaire__isnull=True).count()
    if total_sans_periode_ex:
        periodes_exercices.append({
            'id': 'none',
            'nom': 'Sans période',
            'total': total_sans_periode_ex,
        })

    periodes_stats_ex = exercices_base.filter(periode_scolaire__isnull=False).values(
        'periode_scolaire_id',
        'periode_scolaire__nom_periode'
    ).annotate(total=Count('id')).order_by('periode_scolaire__date_debut', 'periode_scolaire__nom_periode')

    for stat in periodes_stats_ex:
        periodes_exercices.append({
            'id': str(stat['periode_scolaire_id']),
            'nom': stat['periode_scolaire__nom_periode'],
            'total': stat['total'],
        })

    # Filtrer les exercices par période
    exercices_filtres = exercices_base
    if periode_selectionnee != 'all' and onglet_actif == 'exercices':
        if periode_selectionnee == 'none':
            exercices_filtres = exercices_filtres.filter(periode_scolaire__isnull=True)
        else:
            try:
                periode_id = int(periode_selectionnee)
                exercices_filtres = exercices_filtres.filter(periode_scolaire_id=periode_id)
            except (TypeError, ValueError):
                pass

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
        'page_title': 'Devoirs et évaluations',
        'eleve': eleve,
        'est_parent': est_parent,
        'onglet_actif': onglet_actif,
        'periode_selectionnee': periode_selectionnee,
        'periodes_evaluations': periodes_evaluations,
        'periodes_exercices': periodes_exercices,
        'evaluations': evaluations_list,
        'exercices': exercices_list,
        'total_evaluations': total_evaluations,
        'total_exercices': total_exercices,
        'total_semaine': total_semaine,
        'total_a_venir': total_a_venir,
        'date_aujourdhui': date_aujourdhui,
        'classe': classe_active,
        'annee_scolaire_active': annee_scolaire_active,
        'est_primaire': est_primaire,
    }

    return render(request, 'school_admin/eleve/devoirs_eleve.html', context)


def deconnexion_eleve(request):
    """
    Déconnexion de l'élève
    Nettoie complètement la session et affiche un message de confirmation
    """
    from django.contrib.auth import logout
    from school_admin.authentication_backends import _user_type_context
    
    # Nettoyer le thread-local
    if hasattr(_user_type_context, 'user_type'):
        delattr(_user_type_context, 'user_type')
    
    # Déconnecter l'utilisateur (nettoie la session avec flush())
    logout(request)
    
    # Ajouter un message de succès APRÈS logout()
    messages.success(request, "Déconnexion réussie. Vous avez été déconnecté avec succès.")
    
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
    
    etablissement = eleve.etablissement
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    # Vérifier que l'élève a une classe pour l'année scolaire active
    if not classe:
        messages.warning(request, "Vous n'êtes pas encore affecté à une classe pour l'année scolaire active.")
        return redirect('eleve:dashboard')
    
    # Récupérer l'emploi du temps actif de la classe
    from ..model.emploi_du_temps_model import EmploiDuTemps
    emplois_actifs = EmploiDuTemps.objects.filter(
        classe=classe,
        est_actif=True,
    )
    if annee_scolaire_active:
        emplois_actifs = emplois_actifs.filter(annee_scolaire_fk=annee_scolaire_active)
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
    
    sessions_examens_query = SessionExamen.objects.filter(
        etablissement=etablissement,
        classes=classe,
        actif=True
    )
    if annee_scolaire_active:
        sessions_examens_query = sessions_examens_query.filter(annee_scolaire=annee_scolaire_active)
    sessions_examens = sessions_examens_query.select_related('periode').prefetch_related('matieres', 'classes')
    
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
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
    periodes_query = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_query = periodes_query.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_query.order_by('date_debut')
    
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
            moyennes_query = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                periode_scolaire=periode
            )
            if annee_scolaire_active:
                moyennes_query = moyennes_query.filter(annee_scolaire=annee_scolaire_active)
            moyennes = moyennes_query.select_related('matiere').exclude(moyenne__isnull=True)
        else:
            moyennes_query = Moyenne.objects.filter(
                eleve=eleve,
                periode=str(periode.id),
                actif=True
            )
            if annee_scolaire_active:
                moyennes_query = moyennes_query.filter(annee_scolaire=annee_scolaire_active)
            moyennes = moyennes_query.select_related('matiere').exclude(moyenne__isnull=True)
        
        # Calculer ou récupérer la moyenne générale de la période
        moyenne_generale_value = None
        moyenne_generale_display = None
        total_pondere = Decimal('0')
        total_coefficients = Decimal('0')
        
        # Vérifier si c'est un établissement lycée pour utiliser les coefficients par groupe
        est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
        
        for moy in moyennes:
            if moy.moyenne and moy.matiere:
                if est_lycee:
                    from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                    coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(moy.matiere, classe_active)
                    # Convertir en Decimal pour éviter les erreurs de type
                    coef = Decimal(str(coefficient_decimal)) if coefficient_decimal else Decimal('1')
                else:
                    # Convertir le coefficient en Decimal si ce n'est pas déjà le cas
                    if hasattr(moy.matiere, 'coefficient') and moy.matiere.coefficient:
                        coef = Decimal(str(moy.matiere.coefficient))
                    else:
                        coef = Decimal('1')
                
                # Convertir moy.moyenne en Decimal si ce n'est pas déjà le cas
                moyenne_decimal = Decimal(str(moy.moyenne)) if not isinstance(moy.moyenne, Decimal) else moy.moyenne
                
                total_pondere += moyenne_decimal * coef
                total_coefficients += coef

        moyenne_generale_record_qs = MoyennePeriode.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            periode=periode,
            est_moyenne_generale=True,
            afficher_bulletin=True
        )
        if annee_scolaire_active:
            moyenne_generale_record_qs = moyenne_generale_record_qs.filter(annee_scolaire=annee_scolaire_active)
        moyenne_generale_record = moyenne_generale_record_qs.order_by('-updated_at').first()

        if moyenne_generale_record and moyenne_generale_record.moyenne_generale is not None:
            moyenne_generale_value = float(moyenne_generale_record.moyenne_generale)
        
        if moyenne_generale_value is None and total_coefficients > Decimal('0'):
            moyenne_generale_value = float(total_pondere / total_coefficients)
        
        if moyenne_generale_value is not None:
            moyenne_generale_display = f"{Decimal(str(moyenne_generale_value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
        
        # Récupérer les matières avec leurs moyennes
        matieres_moyennes = []
        for moy in moyennes:
            if moy.matiere:
                # Pour le primaire, utiliser MoyenneMatierePrimaire pour la moyenne de classe
                if etablissement.type_etablissement == 'primary':
                    moyenne_classe_query = MoyenneMatierePrimaire.objects.filter(
                        classe=classe_active,
                        matiere=moy.matiere,
                        periode_scolaire=periode
                    )
                    if annee_scolaire_active:
                        moyenne_classe_query = moyenne_classe_query.filter(annee_scolaire=annee_scolaire_active)
                    moyenne_classe_obj = moyenne_classe_query.exclude(moyenne__isnull=True).aggregate(Avg('moyenne'))['moyenne__avg']
                    moyenne_classe = round(moyenne_classe_obj, 2) if moyenne_classe_obj else None
                    
                    # Calculer la position de l'élève
                    moyennes_classe_query = MoyenneMatierePrimaire.objects.filter(
                        classe=classe_active,
                        matiere=moy.matiere,
                        periode_scolaire=periode
                    )
                    if annee_scolaire_active:
                        moyennes_classe_query = moyennes_classe_query.filter(annee_scolaire=annee_scolaire_active)
                    moyennes_classe = moyennes_classe_query.exclude(moyenne__isnull=True).order_by('-moyenne')
                else:
                    # Pour le collège/lycée, utiliser le modèle Moyenne existant
                    moyenne_classe_query = Moyenne.objects.filter(
                        classe=classe_active,
                        matiere=moy.matiere,
                        periode=str(periode.id),
                        actif=True
                    )
                    if annee_scolaire_active:
                        moyenne_classe_query = moyenne_classe_query.filter(annee_scolaire=annee_scolaire_active)
                    moyenne_classe = moyenne_classe_query.exclude(moyenne__isnull=True).aggregate(Avg('moyenne'))['moyenne__avg']
                    
                    # Calculer la position de l'élève
                    moyennes_classe_query = Moyenne.objects.filter(
                        classe=classe_active,
                        matiere=moy.matiere,
                        periode=str(periode.id),
                        actif=True
                    )
                    if annee_scolaire_active:
                        moyennes_classe_query = moyennes_classe_query.filter(annee_scolaire=annee_scolaire_active)
                    moyennes_classe = moyennes_classe_query.exclude(moyenne__isnull=True).order_by('-moyenne')
                
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
                    affectations_query = AffectationProfesseurPrimaire.objects.filter(
                        classe=classe_active,
                        matieres=moy.matiere
                    )
                    if annee_scolaire_active:
                        affectations_query = affectations_query.filter(annee_scolaire=annee_scolaire_active)
                    affectations = affectations_query
                    if affectations.exists():
                        affectation = affectations.first()
                        if affectation.professeur:
                            enseignant_nom = f"{affectation.professeur.prenom} {affectation.professeur.nom}"
                else:
                    affectation_query = AffectationProfesseur.objects.filter(
                        classe=classe_active,
                        matiere=moy.matiere
                    )
                    if annee_scolaire_active:
                        affectation_query = affectation_query.filter(annee_scolaire=annee_scolaire_active)
                    affectation = affectation_query.first()
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
                notes_matiere_query = NotePrimaire.objects.filter(
                    eleve=eleve,
                    evaluation_primaire__matiere=matiere,
                    evaluation_primaire__periode_scolaire=periode,
                    retenue=True,
                    absent=False
                )
                if annee_scolaire_active:
                    notes_matiere_query = notes_matiere_query.filter(annee_scolaire=annee_scolaire_active)
                notes_matiere = notes_matiere_query.select_related('evaluation_primaire').exclude(note__isnull=True).order_by('evaluation_primaire__date_evaluation')

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
                notes_matiere_query = Note.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    evaluation__periode_scolaire=periode,
                    retenue=True,
                    absent=False
                )
                if annee_scolaire_active:
                    notes_matiere_query = notes_matiere_query.filter(annee_scolaire=annee_scolaire_active)
                notes_matiere = notes_matiere_query.select_related('evaluation').exclude(note__isnull=True).order_by('evaluation__date_evaluation')

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
                )
                if annee_scolaire_active:
                    note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                note_examen_qs = note_examen_qs.select_related('session_examen').order_by('-date_saisie')
            else:
                note_examen_qs = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    session_examen__periode=periode,
                    absent=False,
                    retenue=True
                )
                if annee_scolaire_active:
                    note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                note_examen_qs = note_examen_qs.select_related('session_examen').exclude(note_sur_20__isnull=True).order_by('-date_saisie')
                
                if not note_examen_qs.exists():
                    note_examen_qs = NoteExamen.objects.filter(
                        eleve=eleve,
                        matiere=matiere,
                        session_examen__periode=periode,
                        absent=False
                    )
                    if annee_scolaire_active:
                        note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                    note_examen_qs = note_examen_qs.select_related('session_examen').order_by('-date_saisie')
            
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
        notes_primaires_query = NotePrimaire.objects.filter(
            eleve=eleve,
            retenue=True,
            absent=False
        )
        if annee_scolaire_active:
            notes_primaires_query = notes_primaires_query.filter(annee_scolaire=annee_scolaire_active)
        notes_primaires = notes_primaires_query.select_related('evaluation_primaire__matiere', 'evaluation_primaire').exclude(note__isnull=True).order_by('-date_saisie')[:20]
        
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
                # 'type': note.evaluation_primaire.type_evaluation,  # Champ supprimé
                'coefficient': 1,  # Coefficient par défaut pour le primaire
                'commentaire': note.appreciation if note.appreciation else '',
            })
    else:
        # Pour collège/lycée - Récupérer les notes récentes de la table Note
        notes_secondaires_query = Note.objects.filter(
            eleve=eleve,
            retenue=True,
            absent=False
        )
        if annee_scolaire_active:
            notes_secondaires_query = notes_secondaires_query.filter(annee_scolaire=annee_scolaire_active)
        notes_secondaires = notes_secondaires_query.select_related('evaluation__matiere', 'evaluation', 'matiere').exclude(note__isnull=True).order_by('-date_saisie')[:20]
        
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
                # 'type': note.evaluation.type_evaluation,  # Champ supprimé
                'coefficient': matiere.coefficient if matiere.coefficient else 1,
                'commentaire': note.appreciation if note.appreciation else '',
            })
    
    # Récupérer les évaluations à venir
    evaluations_a_venir = []
    if etablissement.type_etablissement == 'primary' and classe_active:
        evals_query = EvaluationPrimaire.objects.filter(
            classe=classe_active,
            date_evaluation__gte=timezone.now().date()
        )
        if annee_scolaire_active:
            evals_query = evals_query.filter(annee_scolaire=annee_scolaire_active)
        evals = evals_query.select_related('matiere', 'professeur').order_by('date_evaluation')[:10]
        
        for ev in evals:
            evaluations_a_venir.append({
                'id': ev.id,
                'titre': ev.titre,
                'matiere': ev.matiere,
                'date': ev.date_evaluation,
                # 'type': ev.type_evaluation,  # Champ supprimé
                'professeur': ev.professeur,
            })
    elif classe_active:
        # Pour collège/lycée - Récupérer les évaluations à venir de la table Evaluation
        evals_query = Evaluation.objects.filter(
            classe=classe_active,
            date_evaluation__gte=timezone.now().date()
        )
        if annee_scolaire_active:
            evals_query = evals_query.filter(annee_scolaire=annee_scolaire_active)
        evals = evals_query.select_related('matiere', 'professeur').order_by('date_evaluation')[:10]
        
        for ev in evals:
            evaluations_a_venir.append({
                'id': ev.id,
                'titre': ev.titre,
                'matiere': ev.matiere,
                'date': ev.date_evaluation,
                # 'type': ev.type_evaluation,  # Champ supprimé
                'professeur': ev.professeur,
            })
    
    # Récupérer toutes les matières de l'élève avec leurs notes détaillées
    matieres_avec_notes = {}
    
    if classe_active:
        # Récupérer toutes les matières de la classe
        from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
        
        if etablissement.type_etablissement == 'primary':
            affectations_query = AffectationProfesseurPrimaire.objects.filter(
                classe=classe_active,
                actif=True
            )
            if annee_scolaire_active:
                affectations_query = affectations_query.filter(annee_scolaire=annee_scolaire_active)
            affectations = affectations_query.prefetch_related('matieres')
            
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
                notes_matiere_query = NotePrimaire.objects.filter(
                    eleve=eleve,
                    evaluation_primaire__matiere=matiere,
                    retenue=True,
                    absent=False
                )
                if annee_scolaire_active:
                    notes_matiere_query = notes_matiere_query.filter(annee_scolaire=annee_scolaire_active)
                notes_matiere = notes_matiere_query.select_related('evaluation_primaire__periode_scolaire').exclude(note__isnull=True).order_by('-date_saisie')
                
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
                        # 'type': note.evaluation_primaire.type_evaluation,  # Champ supprimé
                        'note': note.note,
                        'bareme': note.evaluation_primaire.bareme,
                        'note_sur_20': round(note_sur_20, 2) if note_sur_20 else 0,
                        'appreciation': note.appreciation if note.appreciation else '',
                        'est_examen': False,
                    })
                
                # Ajouter les notes d'examen pour chaque période
                from ..model.note_examen_model import NoteExamen
                notes_examen_query = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere_id=matiere.id
                )
                if annee_scolaire_active:
                    notes_examen_query = notes_examen_query.filter(annee_scolaire=annee_scolaire_active)
                notes_examen = notes_examen_query.select_related('session_examen__periode').order_by('-date_saisie')
                
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
            
            affectations_query = AffectationProfesseur.objects.filter(
                classe=classe_active,
                actif=True
            )
            if annee_scolaire_active:
                affectations_query = affectations_query.filter(annee_scolaire=annee_scolaire_active)
            affectations = affectations_query.select_related('matiere')
            
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
                notes_matiere_query = Note.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    retenue=True,
                    absent=False
                )
                if annee_scolaire_active:
                    notes_matiere_query = notes_matiere_query.filter(annee_scolaire=annee_scolaire_active)
                notes_matiere = notes_matiere_query.select_related('evaluation__periode_scolaire').exclude(note__isnull=True).order_by('-date_saisie')
                
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
                        # 'type': note.evaluation.type_evaluation,  # Champ supprimé
                        'note': note.note,
                        'bareme': 20,
                        'note_sur_20': round(float(note.note), 2),
                        'appreciation': note.appreciation if note.appreciation else '',
                        'est_examen': False,
                    })
                
                # Ajouter les notes d'examen pour chaque période (secondaire)
                from ..model.note_examen_model import NoteExamen
                notes_examen_query = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    absent=False,
                    retenue=True
                )
                if annee_scolaire_active:
                    notes_examen_query = notes_examen_query.filter(annee_scolaire=annee_scolaire_active)
                notes_examen = notes_examen_query.select_related('session_examen__periode').exclude(note_sur_20__isnull=True).order_by('-date_saisie')
                
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
    
    bulletin_record_qs = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        est_moyenne_generale=True,
        afficher_bulletin=True,
        moyenne_generale__isnull=False
    )
    if annee_scolaire_active:
        bulletin_record_qs = bulletin_record_qs.filter(annee_scolaire=annee_scolaire_active)
    bulletin_record = bulletin_record_qs.select_related('periode').order_by('-updated_at').first()

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
        'annee_scolaire_active': annee_scolaire_active,
        'classe': classe_active,
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

    etablissement = eleve.etablissement
    if not etablissement:
        messages.warning(request, "Aucun établissement n'est associé à votre profil.")
        return redirect('eleve:notes_evaluations')
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    if not classe_active:
        messages.info(request, "Aucune classe n'est associée à votre profil pour l'année scolaire active.")
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
    )
    if annee_scolaire_active:
        bulletins_qs = bulletins_qs.filter(annee_scolaire=annee_scolaire_active)
    bulletins_qs = bulletins_qs.select_related('periode').order_by('-updated_at')

    if periode_param:
        bulletins_qs = bulletins_qs.filter(periode_id=periode_param)

    moyenne_generale_record = bulletins_qs.first()
    if not moyenne_generale_record:
        messages.warning(request, "Votre bulletin n'est pas encore disponible.")
        return redirect('eleve:notes_evaluations')

    periode = moyenne_generale_record.periode
    if not periode:
        periode_query = PeriodeScolaire.objects.filter(
            etablissement=etablissement,
            est_active=True
        )
        if annee_scolaire_active:
            periode_query = periode_query.filter(annee_scolaire_fk=annee_scolaire_active)
        periode = periode_query.order_by('date_debut').first()
        if not periode:
            messages.warning(request, "Aucune période scolaire active n'est configurée.")
            return redirect('eleve:notes_evaluations')

    matieres_qs = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        periode=periode,
        est_moyenne_generale=False
    )
    if annee_scolaire_active:
        matieres_qs = matieres_qs.filter(annee_scolaire=annee_scolaire_active)
    matieres_qs = matieres_qs.select_related('matiere').order_by('matiere__nom')

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
    classe_effectif = classe_active.eleves.filter(actif=True).count()

    absences_justifiees_query = Presence.objects.filter(
        eleve=eleve,
        classe=classe_active,
        date__gte=periode.date_debut,
        date__lte=periode.date_fin,
        statut='absent_justifie'
    )
    if annee_scolaire_active:
        absences_justifiees_query = absences_justifiees_query.filter(annee_scolaire=annee_scolaire_active)
    absences_justifiees = absences_justifiees_query.count()

    absences_non_justifiees_query = Presence.objects.filter(
        eleve=eleve,
        classe=classe_active,
        date__gte=periode.date_debut,
        date__lte=periode.date_fin,
        statut='absent'
    )
    if annee_scolaire_active:
        absences_non_justifiees_query = absences_non_justifiees_query.filter(annee_scolaire=annee_scolaire_active)
    absences_non_justifiees = absences_non_justifiees_query.count()

    # Récupérer la moyenne minimale de passage depuis les standards
    moyenne_passage_standards = None
    if standards_bundle:
        standards = standards_bundle.get('instance')
        if standards and standards.moyenne_passage is not None:
            moyenne_passage_standards = float(standards.moyenne_passage)
    
    # Calculer l'appréciation générale basée sur la moyenne >= 10.00
    appreciation_generale_periode = None
    if moyenne_generale is not None:
        if moyenne_generale >= 10.00:
            appreciation_generale_periode = f"{periode.nom_periode} validée"
        else:
            appreciation_generale_periode = f"{periode.nom_periode} non validée"
    
    # Récupérer la moyenne annuelle si elle existe
    from ..model.moyenne_periode_model import MoyenneAnnuelle
    moyenne_annuelle = None
    moyenne_annuelle_obj = MoyenneAnnuelle.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire_active,
        periode_calcul=periode
    ).first()
    
    if moyenne_annuelle_obj and moyenne_annuelle_obj.moyenne_annuelle is not None:
        moyenne_annuelle = float(moyenne_annuelle_obj.moyenne_annuelle)
    
    # Calculer la décision du conseil basée sur la moyenne annuelle
    decision_conseil_finale = decision_conseil
    if moyenne_annuelle is not None and moyenne_passage_standards is not None:
        if moyenne_annuelle >= moyenne_passage_standards:
            decision_conseil_finale = "Admis en classe supérieure"
        else:
            decision_conseil_finale = f"Redouble la {classe_active.nom}"
    
    complement_info = {
        'moyenne_periode': moyenne_generale,
        'moyenne_annuelle': moyenne_annuelle,
        'rang_general': moyenne_generale_record.rang,
        'effectif': classe_effectif,
        'absences_justifiees': absences_justifiees,
        'absences_non_justifiees': absences_non_justifiees,
        'appreciation_generale': appreciation_generale_periode,  # Utiliser la nouvelle logique
        'appreciation_generale_originale': appreciation_generale,  # Garder l'originale si besoin
        'moyenne_generale_validee': moyenne_generale >= 10.00 if moyenne_generale is not None else None,
        'decision_conseil': decision_conseil_finale,  # Utiliser la nouvelle logique
        'decision_conseil_originale': decision_conseil,  # Garder l'originale si besoin
        'moyenne_passage': moyenne_passage_standards,  # Pour la comparaison avec la moyenne annuelle
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
        'classe': classe_active,
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
        'annee_scolaire_active': annee_scolaire_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    from ..model.periode_model import PeriodeScolaire
    from django.db.models import Count, Q
    from datetime import timedelta
    
    # Récupérer la période active
    periode_query = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periode_query = periode_query.filter(annee_scolaire_fk=annee_scolaire_active)
    periode_active = periode_query.order_by('-date_debut').first()
    
    # Calculer les statistiques globales
    presences_totales = Presence.objects.filter(eleve=eleve)
    if annee_scolaire_active:
        presences_totales = presences_totales.filter(annee_scolaire=annee_scolaire_active)
    
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
    periodes_query = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_query = periodes_query.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_query.order_by('date_debut')
    
    from collections import defaultdict
    import calendar
    
    periodes_data = []
    for periode in periodes:
        presences_periode_query = Presence.objects.filter(
            eleve=eleve,
            date__gte=periode.date_debut,
            date__lte=periode.date_fin
        )
        if annee_scolaire_active:
            presences_periode_query = presences_periode_query.filter(annee_scolaire=annee_scolaire_active)
        presences_periode = presences_periode_query
        
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
    
    absences_recentes_query = Presence.objects.filter(
        Q(statut='absent') | Q(statut='absent_justifie'),
        eleve=eleve,
        date__gte=date_limite
    )
    if annee_scolaire_active:
        absences_recentes_query = absences_recentes_query.filter(annee_scolaire=annee_scolaire_active)
    absences_recentes = absences_recentes_query.order_by('-date')[:10]
    
    retards_recents_query = Presence.objects.filter(
        eleve=eleve,
        statut='retard',
        date__gte=date_limite
    )
    if annee_scolaire_active:
        retards_recents_query = retards_recents_query.filter(annee_scolaire=annee_scolaire_active)
    retards_recents = retards_recents_query.order_by('-date')[:10]
    
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
        'annee_scolaire_active': annee_scolaire_active,
        'classe': classe_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    from ..model.periode_model import PeriodeScolaire
    from django.db.models import Avg, Count, Q
    
    # Récupérer la période active
    periode_query = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periode_query = periode_query.filter(annee_scolaire_fk=annee_scolaire_active)
    periode_active = periode_query.order_by('-date_debut').first()
    
    # Statistiques de présence
    presences = Presence.objects.filter(eleve=eleve)
    if annee_scolaire_active:
        presences = presences.filter(annee_scolaire=annee_scolaire_active)
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
    # Ouvrir le modal de mot de passe si demandé via paramètre GET ou si des erreurs existent
    password_modal_open = request.GET.get('password_modal') == 'open' or False
    password_errors = []

    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "upload-photo":
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
        
        elif action == "change_password":
            password_modal_open = True
            
            if est_parent:
                messages.error(
                    request,
                    "Seul l'élève connecté peut modifier son mot de passe.",
                )
                return redirect("eleve:profil_eleve")
            
            # Changement de mot de passe
            from django.contrib.auth.hashers import check_password, make_password
            from django.contrib.auth import update_session_auth_hash
            
            old_password = request.POST.get('old_password', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()
            
            # Validation des champs obligatoires
            validation_errors = []
            
            if not old_password:
                validation_errors.append("L'ancien mot de passe est obligatoire.")
            
            if not new_password:
                validation_errors.append("Le nouveau mot de passe est obligatoire.")
            elif len(new_password) < 8:
                validation_errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
            
            if not confirm_password:
                validation_errors.append("La confirmation du mot de passe est obligatoire.")
            elif new_password and confirm_password and new_password != confirm_password:
                validation_errors.append("Les nouveaux mots de passe ne correspondent pas.")
            
            # Si des erreurs de validation existent, les afficher et arrêter
            if validation_errors:
                password_errors = validation_errors
                for error in validation_errors:
                    messages.error(request, error)
                # Rediriger avec un paramètre pour ouvrir le modal
                return redirect(reverse('eleve:profil_eleve') + '?password_modal=open')
            # Vérifier le mot de passe actuel seulement si toutes les validations précédentes sont passées
            elif not check_password(old_password, eleve.password):
                password_errors.append("L'ancien mot de passe est incorrect.")
                messages.error(request, "L'ancien mot de passe est incorrect.")
                # Rediriger avec un paramètre pour ouvrir le modal
                return redirect(reverse('eleve:profil_eleve') + '?password_modal=open')
            else:
                # Toutes les validations sont passées, changer le mot de passe
                eleve.password = make_password(new_password)
                eleve.save()
                # Maintenir la session active après changement de mot de passe
                update_session_auth_hash(request, eleve)
                messages.success(request, "Mot de passe modifié avec succès.")
                logger.info(f"Mot de passe changé - Élève: {eleve.nom_complet}")
                return redirect("eleve:profil_eleve")
    
    # Statistiques de notes
    if etablissement.type_etablissement == 'primary':
        from ..model.note_primaire_model import MoyenneMatierePrimaire
        
        # Moyenne générale
        if periode_active:
            moyennes_query = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                periode_scolaire=periode_active
            )
            if annee_scolaire_active:
                moyennes_query = moyennes_query.filter(annee_scolaire=annee_scolaire_active)
            moyennes = moyennes_query.exclude(moyenne__isnull=True)
            
            total_pondere = Decimal('0')
            total_coefficients = Decimal('0')
            nb_matieres = 0
            
            for moy in moyennes:
                if moy.moyenne and moy.matiere:
                    # Convertir le coefficient en Decimal
                    if hasattr(moy.matiere, 'coefficient') and moy.matiere.coefficient:
                        coef = Decimal(str(moy.matiere.coefficient))
                    else:
                        coef = Decimal('1')
                    
                    # Convertir moy.moyenne en Decimal si ce n'est pas déjà le cas
                    moyenne_decimal = Decimal(str(moy.moyenne)) if not isinstance(moy.moyenne, Decimal) else moy.moyenne
                    
                    total_pondere += moyenne_decimal * coef
                    total_coefficients += coef
                    nb_matieres += 1
            
            moyenne_generale = float(total_pondere / total_coefficients) if total_coefficients > Decimal('0') else None
            if moyenne_generale is not None:
                moyenne_generale = round(moyenne_generale, 2)
        else:
            moyenne_generale = None
            nb_matieres = 0
    else:
        from ..model.moyenne_model import Moyenne
        
        if periode_active:
            moyennes_query = Moyenne.objects.filter(
                eleve=eleve,
                periode=str(periode_active.id),
                actif=True
            )
            if annee_scolaire_active:
                moyennes_query = moyennes_query.filter(annee_scolaire=annee_scolaire_active)
            moyennes = moyennes_query.exclude(moyenne__isnull=True)
            
            total_pondere = Decimal('0')
            total_coefficients = Decimal('0')
            nb_matieres = 0
            
            # Vérifier si c'est un établissement lycée pour utiliser les coefficients par groupe
            est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
            
            for moy in moyennes:
                if moy.moyenne and moy.matiere:
                    if est_lycee:
                        from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                        coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(moy.matiere, classe_active)
                        # Convertir en Decimal pour éviter les erreurs de type
                        coef = Decimal(str(coefficient_decimal)) if coefficient_decimal else Decimal('1')
                    else:
                        # Convertir le coefficient en Decimal si ce n'est pas déjà le cas
                        if hasattr(moy.matiere, 'coefficient') and moy.matiere.coefficient:
                            coef = Decimal(str(moy.matiere.coefficient))
                        else:
                            coef = Decimal('1')
                    
                    # Convertir moy.moyenne en Decimal si ce n'est pas déjà le cas
                    moyenne_decimal = Decimal(str(moy.moyenne)) if not isinstance(moy.moyenne, Decimal) else moy.moyenne
                    
                    total_pondere += moyenne_decimal * coef
                    total_coefficients += coef
                    nb_matieres += 1
            
            moyenne_generale = float(total_pondere / total_coefficients) if total_coefficients > Decimal('0') else None
            if moyenne_generale is not None:
                moyenne_generale = round(moyenne_generale, 2)
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
        'password_errors': password_errors,
        'password_modal_open': password_modal_open,
        'carte_annee_scolaire': carte_annee_scolaire,
        'annee_scolaire_active': annee_scolaire_active,
        'classe': classe_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    # Récupérer toutes les sanctions de l'élève
    sanctions_query = Sanction.objects.filter(eleve=eleve)
    if annee_scolaire_active:
        sanctions_query = sanctions_query.filter(annee_scolaire=annee_scolaire_active)
    sanctions = sanctions_query.select_related('classe', 'professeur', 'etablissement').order_by('-date_sanction', '-date_creation')
    
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
    
    periodes_query = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_query = periodes_query.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_query.order_by('-date_debut')
    
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
        'annee_scolaire_active': annee_scolaire_active,
        'classe': classe_active,
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
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if eleve.etablissement:
        annee_scolaire_active = get_session_active(request, eleve.etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, eleve.etablissement)
    
    # Récupérer les annonces publiées destinées aux élèves ou à tous
    annonces_query = Annonce.objects.filter(
        Q(etablissement=eleve.etablissement) &
        Q(statut='publiee') &
        Q(actif=True) &
        (Q(destinataires__contains=['tous']) | 
         Q(destinataires__contains=['eleves']))
    )
    if annee_scolaire_active:
        annonces_query = annonces_query.filter(annee_scolaire=annee_scolaire_active)
    annonces = annonces_query.order_by('-date_publication', '-date_creation')
    
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
        'annee_scolaire_active': annee_scolaire_active,
        'classe': classe_active,
    }
    
    return render(request, 'school_admin/eleve/annonces_eleve.html', context)


def convocations_eleve(request):
    """Affiche les convocations de l'élève."""
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = eleve.etablissement
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    # Récupérer les convocations de l'élève
    from ..model.convocation_model import Convocation
    convocations_query = Convocation.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        actif=True
    )
    if annee_scolaire_active:
        convocations_query = convocations_query.filter(annee_scolaire=annee_scolaire_active)
    convocations = convocations_query.order_by('-date_convocation', '-heure_convocation')
    
    # Séparer les convocations par statut
    convocations_en_attente = convocations.filter(statut='en_attente')
    convocations_vues = convocations.filter(statut='vue')
    convocations_honorees = convocations.filter(statut='honoree')
    convocations_non_honorees = convocations.filter(statut='non_honoree')
    
    # Statistiques
    total_convocations = convocations.count()
    convocations_a_venir = convocations.filter(
        date_convocation__gte=timezone.now().date()
    ).count()
    convocations_passees = convocations.filter(
        date_convocation__lt=timezone.now().date()
    ).count()
    
    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'etablissement': etablissement,
        'convocations': convocations,
        'convocations_en_attente': convocations_en_attente,
        'convocations_vues': convocations_vues,
        'convocations_honorees': convocations_honorees,
        'convocations_non_honorees': convocations_non_honorees,
        'total_convocations': total_convocations,
        'convocations_a_venir': convocations_a_venir,
        'convocations_passees': convocations_passees,
        'annee_scolaire_active': annee_scolaire_active,
        'classe': classe_active,
    }
    
    return render(request, 'school_admin/eleve/convocations_eleve.html', context)


def notifications_eleve(request):
    """Affiche les notifications reçues par l'élève."""
    eleve, est_parent = get_eleve_from_request(request)

    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if eleve.etablissement:
        annee_scolaire_active = get_session_active(request, eleve.etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, eleve.etablissement)

    # Base query pour toutes les notifications de l'élève (SANS FILTRE de lecture)
    # On récupère TOUTES les notifications, peu importe leur statut de lecture
    notifications_query = NotificationEleve.objects.filter(eleve=eleve)
    
    # Filtrer par année scolaire si disponible (optionnel, pour cohérence)
    # Mais on peut aussi afficher toutes les notifications sans ce filtre
    # if annee_scolaire_active:
    #     notifications_query = notifications_query.filter(annee_scolaire=annee_scolaire_active)
    
    # Récupérer TOUTES les notifications non lues pour les marquer comme lues
    notifications_non_lues = notifications_query.filter(lu=False)
    notification_ids_non_lues = list(notifications_non_lues.values_list('id', flat=True))
    
    # Marquer TOUTES les notifications non lues comme lues quand on visite la page
    # C'est ce qui se passe quand on clique sur la cloche de notification
    if notification_ids_non_lues:
        NotificationEleve.objects.filter(id__in=notification_ids_non_lues).update(
            lu=True,
            statut='lu',
            date_lecture=timezone.now(),
            date_modification=timezone.now(),
        )
    
    # Récupérer TOUTES les notifications pour l'affichage (de la plus récente à la plus ancienne)
    # AUCUN FILTRE - Afficher toutes les notifications, lues ou non lues
    notifications = list(notifications_query.order_by('-date_creation'))
    
    # Compter les notifications non lues restantes (après marquage)
    # Ce compteur sera utilisé dans le header pour afficher le badge
    notifications_non_lues_count = notifications_query.filter(lu=False).count()
    
    # Log pour débogage
    logger.info(
        f"Notifications pour élève {eleve.id} ({eleve.nom_complet}): "
        f"Total={notifications_query.count()}, "
        f"Non lues avant marquage={len(notification_ids_non_lues)}, "
        f"Non lues après marquage={notifications_non_lues_count}, "
        f"À afficher={len(notifications)}"
    )
    
    # Log détaillé des notifications
    if notifications:
        logger.info(f"Première notification: {notifications[0].titre} (lu={notifications[0].lu})")
        logger.info(f"Dernière notification: {notifications[-1].titre} (lu={notifications[-1].lu})")
    else:
        logger.warning(f"Aucune notification trouvée pour l'élève {eleve.id}")

    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'notifications': notifications,
        'notifications_eleve_non_lues': notifications_non_lues_count,
        'annee_scolaire_active': annee_scolaire_active,
        'classe': classe_active,
    }

    return render(
        request,
        'school_admin/eleve/notifications_eleve.html',
        context,
    )


def notification_eleve_click(request, notification_id):
    """
    Gère le clic sur une notification : marque comme lue et redirige vers la page appropriée.
    """
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer la notification
    notification = get_object_or_404(NotificationEleve, id=notification_id, eleve=eleve)
    
    # Marquer la notification comme lue
    if not notification.lu:
        notification.marquer_comme_lue()
    
    # Récupérer l'URL de redirection depuis les données de la notification
    redirect_url = notification.donnees.get('redirect_url') if notification.donnees else None
    
    # Si pas d'URL dans les données, générer selon le type
    if not redirect_url:
        from school_admin.services.eleve_notification_service import EleveNotificationService
        redirect_url = EleveNotificationService._get_redirect_url(
            notification.type_notification,
            notification.donnees
        )
    
    # Rediriger vers l'URL appropriée
    return redirect(redirect_url)


def historique_annees_eleve(request):
    """
    Liste les années scolaires précédentes où l'élève a été inscrit.
    Accessible par l'élève ou son parent.
    """
    logger.info(f"Historique années scolaires élève - User: {request.user}")
    
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = eleve.etablissement
    if not etablissement:
        messages.error(request, "Établissement introuvable.")
        return redirect('eleve:dashboard_eleve')
    
    # Récupérer l'année scolaire active (pour le contexte)
    annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..model.presence_model import Presence
    from ..model.sanction_model import Sanction
    from django.db.models import Count, Q
    
    # Récupérer uniquement les inscriptions de l'élève pour les années scolaires désactivées
    # On affiche uniquement les sessions clôturées (est_active=False)
    inscriptions = InscriptionEleve.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire__est_active=False
    ).select_related('annee_scolaire', 'classe').order_by('-annee_scolaire__date_debut')
    
    historique_data = []
    
    for inscription in inscriptions:
        annee = inscription.annee_scolaire
        classe = inscription.classe
        
        # Compter les présences et absences
        presences_query = Presence.objects.filter(
            eleve=eleve,
            annee_scolaire=annee
        )
        nombre_presences = presences_query.filter(statut='present').count()
        nombre_absences = presences_query.filter(
            Q(statut='absent') | Q(statut='absent_justifie')
        ).count()
        
        # Compter les sanctions
        nombre_sanctions = Sanction.objects.filter(
            eleve=eleve,
            annee_scolaire=annee
        ).count()
        
        # Compter les notes (primaire ou secondaire)
        nombre_notes = 0
        type_etablissement = etablissement.type_etablissement
        if type_etablissement in ('primaire', 'primary', 'ecole_primaire'):
            from ..model.note_primaire_model import NotePrimaire
            nombre_notes = NotePrimaire.objects.filter(
                eleve=eleve,
                annee_scolaire=annee,
                absent=False
            ).exclude(note__isnull=True).count()
        else:
            nombre_notes = Note.objects.filter(
                eleve=eleve,
                annee_scolaire=annee,
                absent=False
            ).exclude(note__isnull=True).count()
        
        historique_data.append({
            'annee': annee,
            'classe': classe,
            'nombre_presences': nombre_presences,
            'nombre_absences': nombre_absences,
            'nombre_sanctions': nombre_sanctions,
            'nombre_notes': nombre_notes,
        })
    
    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'etablissement': etablissement,
        'historique_data': historique_data,
        'annee_scolaire_active': annee_scolaire_active,
        'classe': classe_active,
    }
    
    return render(request, 'school_admin/eleve/historique_annees_eleve.html', context)


def detail_historique_annee_eleve(request, annee_id):
    """
    Affiche le détail complet d'une année scolaire précédente pour un élève.
    Organisé par matière avec notes, moyennes, présences, absences et sanctions.
    """
    logger.info(f"Détail historique année scolaire élève - User: {request.user}")
    
    eleve, est_parent = get_eleve_from_request(request)
    
    if not eleve:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = eleve.etablissement
    if not etablissement:
        messages.error(request, "Établissement introuvable.")
        return redirect('eleve:dashboard_eleve')
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer la classe de l'élève pour l'année scolaire active (pour le header)
    classe_active = get_classe_eleve_active(eleve, annee_scolaire_active, etablissement)
    
    from django.shortcuts import get_object_or_404
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..model.presence_model import Presence
    from ..model.sanction_model import Sanction
    from ..model.periode_model import PeriodeScolaire
    from django.db.models import Count, Q, Avg, Case, When, Value, FloatField, F
    from django.db.models import ExpressionWrapper
    from decimal import Decimal
    
    annee = get_object_or_404(
        AnneeScolaire,
        pk=annee_id,
        etablissement=etablissement
    )
    
    # Vérifier que l'élève était bien inscrit cette année
    inscription = InscriptionEleve.objects.filter(
        eleve=eleve,
        annee_scolaire=annee,
        etablissement=etablissement
    ).select_related('classe').first()
    
    if not inscription:
        messages.error(request, "Vous n'étiez pas inscrit cette année scolaire.")
        return redirect('eleve:historique_annees')
    
    classe = inscription.classe
    
    # Statistiques globales
    presences_query = Presence.objects.filter(
        eleve=eleve,
        annee_scolaire=annee
    )
    nombre_presences = presences_query.filter(statut='present').count()
    nombre_absences = presences_query.filter(
        Q(statut='absent') | Q(statut='absent_justifie')
    ).count()
    nombre_retards = presences_query.filter(statut='retard').count()
    
    nombre_sanctions = Sanction.objects.filter(
        eleve=eleve,
        annee_scolaire=annee
    ).count()
    
    # Récupérer les périodes de cette année
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        annee_scolaire_fk=annee,
        est_active=True
    ).order_by('date_debut')
    
    # Organiser les données par matière
    matieres_data = []
    type_etablissement = etablissement.type_etablissement
    
    if type_etablissement in ('primaire', 'primary', 'ecole_primaire'):
        # Primaire : utiliser NotePrimaire et MoyenneMatierePrimaire
        from ..model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire
        from ..model.evaluation_primaire_model import EvaluationPrimaire
        from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
        
        # Récupérer les matières enseignées dans la classe cette année
        affectations = AffectationProfesseurPrimaire.objects.filter(
            classe=classe,
            annee_scolaire=annee,
            actif=True
        ).prefetch_related('matieres')
        
        matieres_set = set()
        for affectation in affectations:
            matieres_set.update(affectation.matieres.all())
        
        for matiere in sorted(matieres_set, key=lambda m: m.nom):
            # Récupérer les notes par période
            notes_par_periode = {}
            moyennes_par_periode = {}
            
            for periode in periodes:
                # Notes de devoirs
                notes_query = NotePrimaire.objects.filter(
                    eleve=eleve,
                    evaluation_primaire__matiere=matiere,
                    evaluation_primaire__periode_scolaire=periode,
                    annee_scolaire=annee,
                    absent=False,
                    retenue=True
                ).exclude(note__isnull=True).select_related('evaluation_primaire').order_by('evaluation_primaire__date_evaluation')
                
                notes_list = []
                for note in notes_query:
                    note_sur_20 = note.note_sur_20
                    notes_list.append({
                        'titre': note.evaluation_primaire.titre,
                        'date': note.evaluation_primaire.date_evaluation,
                        'note': note.note,
                        'bareme': note.evaluation_primaire.bareme,
                        'note_sur_20': round(float(note_sur_20), 2) if note_sur_20 else None,
                        'appreciation': note.appreciation or '',
                        'est_examen': False,
                    })
                
                # Notes d'examen pour cette matière et cette période
                from ..model.note_examen_model import NoteExamen
                notes_examen_query = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere_id=matiere.id,
                    session_examen__periode=periode,
                    annee_scolaire=annee
                ).select_related('session_examen').order_by('-date_saisie')
                
                for note_ex in notes_examen_query:
                    if not note_ex.session_examen:
                        continue
                    note_ex_value = note_ex.note_sur_20
                    if note_ex_value is None and note_ex.note is not None and note_ex.bareme and note_ex.bareme > 0:
                        note_ex_value = (note_ex.note / note_ex.bareme) * 20
                    if note_ex_value is None:
                        continue
                    notes_list.append({
                        'titre': note_ex.session_examen.nom_examen if note_ex.session_examen else 'Examen',
                        'date': note_ex.date_saisie.date() if note_ex.date_saisie else None,
                        'note': round(float(note_ex_value), 2),
                        'bareme': 20,
                        'note_sur_20': round(float(note_ex_value), 2),
                        'appreciation': note_ex.commentaire or '',
                        'est_examen': True,
                    })
                
                notes_par_periode[periode.id] = {
                    'periode': periode,
                    'notes': notes_list,
                }
                
                # Moyennes
                moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    periode_scolaire=periode,
                    annee_scolaire=annee
                ).first()
                
                if moyenne_obj and moyenne_obj.moyenne is not None:
                    moyennes_par_periode[periode.id] = {
                        'periode': periode,
                        'moyenne': round(float(moyenne_obj.moyenne), 2),
                        'appreciation': moyenne_obj.appreciation or '',
                    }
            
            # Calculer la moyenne générale de la matière (toutes périodes)
            toutes_notes = NotePrimaire.objects.filter(
                eleve=eleve,
                evaluation_primaire__matiere=matiere,
                annee_scolaire=annee,
                absent=False,
                retenue=True
            ).exclude(note__isnull=True)
            
            moyenne_generale_matiere = None
            if toutes_notes.exists():
                note_expression = Case(
                    When(
                        evaluation_primaire__bareme__gt=0,
                        then=ExpressionWrapper(
                            (F('note') / F('evaluation_primaire__bareme')) * Value(20),
                            output_field=FloatField()
                        )
                    ),
                    default=Value(0),
                    output_field=FloatField()
                )
                moyenne_agregee = toutes_notes.aggregate(
                    moyenne=Avg(note_expression)
                )['moyenne']
                if moyenne_agregee:
                    moyenne_generale_matiere = round(float(moyenne_agregee), 2)
            
            # Convertir les dictionnaires en listes pour faciliter l'affichage dans le template
            periodes_notes = []
            for periode in periodes:
                periode_note_data = {
                    'periode': periode,
                    'notes': notes_par_periode.get(periode.id, {}).get('notes', []),
                    'moyenne': moyennes_par_periode.get(periode.id, {}).get('moyenne'),
                }
                if periode_note_data['notes'] or periode_note_data['moyenne']:
                    periodes_notes.append(periode_note_data)
            
            matieres_data.append({
                'matiere': matiere,
                'periodes_notes': periodes_notes,
                'moyenne_generale': moyenne_generale_matiere,
                'total_notes': toutes_notes.count(),
            })
    else:
        # Collège/Lycée : utiliser Note et Moyenne
        from ..model.affectation_model import AffectationProfesseur
        from ..model.moyenne_model import Moyenne
        
        # Récupérer les matières enseignées dans la classe cette année
        affectations = AffectationProfesseur.objects.filter(
            classe=classe,
            annee_scolaire=annee,
            actif=True
        ).select_related('matiere')
        
        matieres_set = set()
        for affectation in affectations:
            if affectation.matiere:
                matieres_set.add(affectation.matiere)
        
        for matiere in sorted(matieres_set, key=lambda m: m.nom):
            # Récupérer les notes par période
            notes_par_periode = {}
            moyennes_par_periode = {}
            
            for periode in periodes:
                # Notes de devoirs
                notes_query = Note.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    evaluation__periode_scolaire=periode,
                    annee_scolaire=annee,
                    absent=False,
                    retenue=True
                ).exclude(note__isnull=True).select_related('evaluation').order_by('evaluation__date_evaluation')
                
                notes_list = []
                for note in notes_query:
                    note_sur_20 = note.note_sur_20
                    notes_list.append({
                        'titre': note.evaluation.titre,
                        'date': note.evaluation.date_evaluation,
                        'note': note.note,
                        'bareme': note.evaluation.bareme or 20,
                        'note_sur_20': round(float(note_sur_20), 2) if note_sur_20 else None,
                        'appreciation': note.appreciation or '',
                        'est_examen': False,
                    })
                
                # Notes d'examen pour cette matière et cette période
                from ..model.note_examen_model import NoteExamen
                notes_examen_query = NoteExamen.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    session_examen__periode=periode,
                    annee_scolaire=annee,
                    absent=False,
                    retenue=True
                ).select_related('session_examen').exclude(note_sur_20__isnull=True).order_by('-date_saisie')
                
                if not notes_examen_query.exists():
                    notes_examen_query = NoteExamen.objects.filter(
                        eleve=eleve,
                        matiere=matiere,
                        session_examen__periode=periode,
                        annee_scolaire=annee,
                        absent=False
                    ).select_related('session_examen').order_by('-date_saisie')
                
                for note_ex in notes_examen_query:
                    if not note_ex.session_examen:
                        continue
                    note_ex_value = note_ex.note_sur_20
                    if note_ex_value is None and note_ex.note is not None and note_ex.bareme and note_ex.bareme > 0:
                        note_ex_value = (note_ex.note / note_ex.bareme) * 20
                    if note_ex_value is None:
                        continue
                    notes_list.append({
                        'titre': note_ex.session_examen.nom_examen if note_ex.session_examen else 'Examen',
                        'date': note_ex.date_saisie.date() if note_ex.date_saisie else None,
                        'note': round(float(note_ex_value), 2),
                        'bareme': 20,
                        'note_sur_20': round(float(note_ex_value), 2),
                        'appreciation': note_ex.commentaire or '',
                        'est_examen': True,
                    })
                
                notes_par_periode[periode.id] = {
                    'periode': periode,
                    'notes': notes_list,
                }
                
                # Moyennes
                moyenne_obj = Moyenne.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    periode=str(periode.id),
                    annee_scolaire=annee,
                    actif=True
                ).first()
                
                if moyenne_obj and moyenne_obj.moyenne is not None:
                    moyennes_par_periode[periode.id] = {
                        'periode': periode,
                        'moyenne': round(float(moyenne_obj.moyenne), 2),
                        'appreciation': moyenne_obj.appreciation or '',
                    }
            
            # Calculer la moyenne générale de la matière
            toutes_notes = Note.objects.filter(
                eleve=eleve,
                matiere=matiere,
                annee_scolaire=annee,
                absent=False,
                retenue=True
            ).exclude(note__isnull=True)
            
            moyenne_generale_matiere = None
            if toutes_notes.exists():
                moyenne_agregee = toutes_notes.aggregate(
                    moyenne=Avg('note')
                )['moyenne']
                if moyenne_agregee:
                    moyenne_generale_matiere = round(float(moyenne_agregee), 2)
            
            # Convertir les dictionnaires en listes pour faciliter l'affichage dans le template
            periodes_notes = []
            for periode in periodes:
                periode_note_data = {
                    'periode': periode,
                    'notes': notes_par_periode.get(periode.id, {}).get('notes', []),
                    'moyenne': moyennes_par_periode.get(periode.id, {}).get('moyenne'),
                }
                if periode_note_data['notes'] or periode_note_data['moyenne']:
                    periodes_notes.append(periode_note_data)
            
            matieres_data.append({
                'matiere': matiere,
                'periodes_notes': periodes_notes,
                'moyenne_generale': moyenne_generale_matiere,
                'total_notes': toutes_notes.count(),
            })
    
    # Récupérer les moyennes générales de toutes les périodes depuis MoyennePeriode
    from ..model.moyenne_periode_model import MoyennePeriode
    moyennes_periodes_dict = {}
    moyennes_periodes_queryset = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        periode__in=periodes,
        est_moyenne_generale=True,
        afficher_bulletin=True,
        moyenne_generale__isnull=False
    )
    # Filtrer par l'année scolaire historique consultée (pas l'année active)
    if annee:
        moyennes_periodes_queryset = moyennes_periodes_queryset.filter(annee_scolaire=annee)
    moyennes_periodes_queryset = moyennes_periodes_queryset.select_related('periode').order_by('periode__date_debut')
    
    for moy_periode in moyennes_periodes_queryset:
        if moy_periode.periode:
            moyennes_periodes_dict[moy_periode.periode.id] = {
                'moyenne_generale': round(float(moy_periode.moyenne_generale), 2),
                'rang': moy_periode.rang,
                'appreciation': moy_periode.appreciation_generale or '',
            }
    
    # Récupérer les présences détaillées par période
    presences_par_periode = []
    for periode in periodes:
        presences_periode = presences_query.filter(
            date__gte=periode.date_debut,
            date__lte=periode.date_fin
        ).order_by('-date')
        
        # Récupérer la moyenne générale de cette période
        moyenne_generale_periode = moyennes_periodes_dict.get(periode.id, {}).get('moyenne_generale')
        
        presences_par_periode.append({
            'periode': periode,
            'presences': presences_periode.filter(statut='present'),
            'absences': presences_periode.filter(Q(statut='absent') | Q(statut='absent_justifie')),
            'retards': presences_periode.filter(statut='retard'),
            'total_jours': presences_periode.count(),
            'moyenne_generale': moyenne_generale_periode,
        })
    
    # Récupérer les sanctions détaillées
    sanctions_list = Sanction.objects.filter(
        eleve=eleve,
        annee_scolaire=annee
    ).select_related('classe', 'professeur').order_by('-date_sanction', '-date_creation')
    
    # Calculer la moyenne générale de l'année à partir des moyennes générales des périodes
    moyenne_generale_annee = None
    if moyennes_periodes_dict:
        total_moyennes = Decimal('0')
        nombre_periodes = 0
        for periode_id, moy_data in moyennes_periodes_dict.items():
            if moy_data.get('moyenne_generale') is not None:
                total_moyennes += Decimal(str(moy_data['moyenne_generale']))
                nombre_periodes += 1
        if nombre_periodes > 0:
            moyenne_generale_annee = round(float(total_moyennes / Decimal(str(nombre_periodes))), 2)
    
    context = {
        'eleve': eleve,
        'est_parent': est_parent,
        'etablissement': etablissement,
        'annee': annee,
        'classe': classe,  # Classe de l'année historique consultée
        'classe_active': classe_active,  # Classe de l'année scolaire active (pour le header)
        'inscription': inscription,
        'nombre_presences': nombre_presences,
        'nombre_absences': nombre_absences,
        'nombre_retards': nombre_retards,
        'nombre_sanctions': nombre_sanctions,
        'periodes': periodes,
        'matieres_data': matieres_data,
        'presences_par_periode': presences_par_periode,
        'sanctions_list': sanctions_list,
        'moyenne_generale_annee': moyenne_generale_annee,
        'moyennes_periodes_dict': moyennes_periodes_dict,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/eleve/historique_annee_detail_eleve.html', context)
