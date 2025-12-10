import hashlib
import json
import logging
from io import BytesIO
from urllib.parse import urlencode

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.core.files.base import ContentFile
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.urls import reverse
from ..model.etablissement_model import Etablissement
from ..model.facturation_model import Facturation
from ..model.eleve_model import Eleve
from ..model.demande_liaison_model import DemandeLiaisonParent
from ..model.lien_familial_model import LienFamilial
from ..model.ponderation_model import Ponderation
from ..model.moyenne_periode_model import MoyennePeriode
from collections import defaultdict
from ..services.parent_notification_service import ParentNotificationService
from ..services.eleve_notification_service import EleveNotificationService
from ..services.notification_tasks import schedule_bulletin_publication
from ..model.notification_directeur_model import NotificationDirecteur
from ..model.justification_note_model import JustificationNote
from ..model.note_primaire_model import MoyenneMatierePrimaire
from ..utils.calcul_moyennes_primaire import calculer_moyenne_avec_mode, get_appreciation_moyenne
from ..model.standards_reussite_model import StandardsReussite, AppreciationMatiereStandard, AppreciationConseilStandard
from ..model.annee_scolaire_model import AnneeScolaire
from ..model.inscription_eleve_model import InscriptionEleve
from ..model.inscription_parent_model import InscriptionParent
from ..model.classe_model import Classe
from ..model.parent_model import Parent
from django.db.models.functions import Lower
from ..utils.session_utils import get_session_active, get_session_consultee
from ..utils.decorators_permissions import check_permission, require_permission
from ..model.personnel_administratif_model import PersonnelAdministratif
from django.db.models import Q
from django.db import transaction
from datetime import datetime, date


def _get_user_etablissement(request, required_permission=None):
    """
    Helper pour récupérer l'établissement de l'utilisateur et vérifier les permissions
    Retourne (etablissement, is_directeur, personnel) ou None si accès refusé
    """
    user = request.user
    
    if isinstance(user, Etablissement):
        return user, True, None
    elif isinstance(user, PersonnelAdministratif):
        # Vérifier la permission si nécessaire
        if required_permission and not check_permission(user, required_permission):
            return None, False, None
        return user.etablissement, False, user
    
    return None, False, None


def _get_session_directeur(request, etablissement):
    """
    Récupère la session consultée par le directeur.
    Si aucune session n'est sélectionnée, retourne la session active.
    Cette fonction permet au directeur de consulter des sessions différentes
    sans affecter la session active utilisée par les autres utilisateurs.
    
    Args:
        request: La requête HTTP
        etablissement: L'établissement
        
    Returns:
        AnneeScolaire|None: La session consultée ou la session active
    """
    return get_session_consultee(request, etablissement)


def _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active=None):
    """
    Récupère les élèves d'une classe depuis InscriptionEleve pour l'année scolaire active.
    Retourne un queryset d'élèves actifs inscrits dans cette classe pour l'année active.
    
    Args:
        classe: L'objet Classe
        etablissement: L'établissement
        annee_scolaire_active: L'année scolaire active (optionnel)
    
    Returns:
        QuerySet d'élèves
    """
    if annee_scolaire_active:
        # Récupérer directement les inscriptions pour cette classe et cette année scolaire
        inscriptions = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire_active,
            classe=classe,
            etablissement=etablissement
        ).select_related('eleve').order_by(Lower('eleve__nom'), Lower('eleve__prenom'))
        
        # Récupérer les élèves depuis les inscriptions (filtrer uniquement les actifs)
        eleves_ids = [inscription.eleve_id for inscription in inscriptions if inscription.eleve and inscription.eleve.actif]
        
        # Créer un queryset à partir de la liste pour maintenir la compatibilité
        return Eleve.objects.filter(id__in=eleves_ids, actif=True).order_by(Lower('nom'), Lower('prenom'))
    else:
        # Comportement par défaut : tous les élèves actifs de la classe
        return Eleve.objects.filter(classe=classe, actif=True).order_by(Lower('nom'), Lower('prenom'))

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
except ImportError:  # pragma: no cover
    qrcode = None
    ERROR_CORRECT_M = None


logger = logging.getLogger(__name__)

# Constante pour les types d'établissements secondaires (lycée, collège, etc.)
TYPES_ETABLISSEMENT_SECONDAIRE = [
    'lycée', 'collège', 'collège_lycée', 'lycee_college', 
    'mixte', 'lycee', 'college'
]


def _safe_decimal(value):
    """Convertit une valeur en Decimal sans lever d'erreur."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format_decimal_value(value):
    """Formate une valeur décimale avec deux chiffres après la virgule."""
    decimal_value = _safe_decimal(value)
    if decimal_value is None:
        return None
    return f"{decimal_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"


def _fallback_appreciation_matiere(note_decimal):
    """Appréciation générique utilisée si aucun palier n'est défini."""
    if note_decimal is None:
        return None
    note_float = float(note_decimal)
    if note_float < 7:
        return "Très insuffisant"
    if note_float < 10:
        return "Insuffisant"
    if note_float < 12:
        return "Passable"
    if note_float < 14:
        return "Assez bien"
    if note_float < 16:
        return "Bien"
    if note_float <= 18:
        return "Très bien"
    return "Excellent"


def _fallback_appreciation_generale(note_decimal):
    """Appréciation générale par défaut."""
    if note_decimal is None:
        return None
    note_float = float(note_decimal)
    if note_float < 7:
        return "Très insuffisant"
    if note_float < 10:
        return "Insuffisant"
    if note_float < 12:
        return "Passable"
    if note_float < 14:
        return "Assez bien"
    if note_float < 16:
        return "Bien"
    if note_float <= 18:
        return "Très bien"
    return "Excellent"


def _resolve_standard_matiere_appreciation(note_decimal, ranges):
    """Retourne l'appréciation standard correspondant au palier."""
    if note_decimal is None or not ranges:
        return None
    for range_obj in ranges:
        min_val = _safe_decimal(range_obj.note_min)
        max_val = _safe_decimal(range_obj.note_max)
        if min_val is None or max_val is None:
            continue
        if min_val <= note_decimal <= max_val:
            return range_obj.appreciation
    return None


def _compute_statut_from_thresholds(note_decimal, standards):
    """Retourne le statut (passage, accompagnement) en fonction des seuils."""
    if note_decimal is None or standards is None:
        return None, None

    passage = _safe_decimal(standards.moyenne_passage)
    statut_code = None

    if passage is not None and note_decimal >= passage:
        statut_code = 'passage'
    elif passage is not None:
        statut_code = 'accompagnement'

    if not statut_code:
        return None, None

    passage_str = _format_decimal_value(passage)

    if statut_code == 'passage':
        label = (
            f"Passage recommandé (moyenne ≥ {passage_str}/20)"
            if passage_str else "Passage recommandé"
        )
    else:
        if passage_str:
            label = (
                f"Accompagnement conseillé (moyenne < {passage_str}/20)"
            )
        else:
            label = "Accompagnement conseillé"

    return statut_code, label


def _compute_matiere_appreciation(note_value, standards_bundle, initial_appreciation=None):
    """
    Détermine l'appréciation d'une matière à partir des standards configurés.
    Retourne (appréciation_appliquée, source, appreciation_standard).
    """
    note_decimal = _safe_decimal(note_value)
    if note_decimal is None:
        return None, 'none', None

    standard_label = None
    if standards_bundle:
        standard_label = _resolve_standard_matiere_appreciation(
            note_decimal,
            standards_bundle['matiere_ranges']
        )

    if standard_label:
        return standard_label, 'standard', standard_label
    fallback_value = _fallback_appreciation_matiere(note_decimal)
    return fallback_value, 'fallback', None


def _compute_appreciation_generale(note_value, standards_bundle, initial_appreciation=None):
    """
    Calcule l'appréciation générale selon les seuils généraux.
    Retourne (appréciation, source, statut_code, statut_label, appreciation_standard).
    """
    note_decimal = _safe_decimal(note_value)
    if note_decimal is None:
        return None, 'none', None, None, None

    standards = standards_bundle['instance'] if standards_bundle else None
    statut_code, statut_label = _compute_statut_from_thresholds(note_decimal, standards)
    appreciation_standard = None

    if statut_code == 'accompagnement':
        appreciation_standard = "Accompagnement conseillé"

    if appreciation_standard:
        return appreciation_standard, 'standard', statut_code, statut_label, appreciation_standard

    fallback_value = _fallback_appreciation_generale(note_decimal)
    return fallback_value, 'fallback', statut_code, statut_label, None


def _compute_decision_conseil(note_value, standards_bundle, initial_decision=None):
    """
    Détermine la décision du conseil à partir des paliers.
    Retourne (decision, source, decision_standard, statut_code, statut_label).
    """
    note_decimal = _safe_decimal(note_value)
    if note_decimal is None:
        if initial_decision:
            return initial_decision, 'initiale', None, None, None
        return None, 'none', None, None, None

    standards = standards_bundle['instance'] if standards_bundle else None
    conseil_ranges = standards_bundle['conseil_ranges'] if standards_bundle else []
    statut_code, statut_label = _compute_statut_from_thresholds(note_decimal, standards)
    decision_standard = None

    if conseil_ranges:
        for range_obj in conseil_ranges:
            min_val = _safe_decimal(range_obj.note_min)
            if min_val is None:
                continue
            if note_decimal >= min_val:
                decision_standard = range_obj.appreciation
            else:
                break
        if decision_standard:
            return decision_standard, 'standard', decision_standard, statut_code, statut_label

    if initial_decision:
        return initial_decision, 'initiale', None, statut_code, statut_label

    return None, 'none', None, statut_code, statut_label


def _get_standards_bundle(etablissement):
    """Charge les standards de réussite liés à l'établissement."""
    try:
        standards = etablissement.standards_reussite
    except StandardsReussite.DoesNotExist:
        return None

    return {
        'instance': standards,
        'matiere_ranges': list(standards.appreciations_matieres.all().order_by('note_min')),
        'conseil_ranges': list(standards.appreciations_conseil.all().order_by('note_min')),
    }


def _build_standards_metadata(standards_bundle, appreciation_source, decision_source, statut_code, statut_label):
    """Assemble des informations sur les standards utilisés."""
    if not standards_bundle:
        return None

    standards = standards_bundle['instance']
    return {
        'moyenne_passage': float(standards.moyenne_passage) if standards.moyenne_passage is not None else None,
        'moyenne_passage_display': _format_decimal_value(standards.moyenne_passage),
        'has_matiere_ranges': bool(standards_bundle['matiere_ranges']),
        'has_conseil_ranges': bool(standards_bundle['conseil_ranges']),
        'appreciation_source': appreciation_source,
        'decision_source': decision_source,
        'statut_code': statut_code,
        'statut_label': statut_label,
    }


def _generate_bulletin_serial(eleve, periode):
    """Crée un numéro de série unique et court pour un bulletin."""
    timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
    random_segment = get_random_string(5).upper()
    base_serial = f"BUL-{periode.id}-{eleve.id}-{timestamp}-{random_segment}"
    return base_serial[:64]


def _ensure_bulletin_security_assets(moyenne_obj, *, eleve, classe, periode, etablissement, verification_url_base=None):
    """
    Génère (ou régénère) les éléments de traçabilité d'un bulletin :
    numéro de série, signature numérique et QR code.
    """
    if not moyenne_obj or moyenne_obj.moyenne_generale is None:
        return None, None

    numero_serie = moyenne_obj.numero_serie or _generate_bulletin_serial(eleve, periode)
    payload = {
        'numero_serie': numero_serie,
        'eleve_id': eleve.id,
        'eleve': eleve.nom_complet,
        'classe_id': classe.id,
        'classe': classe.nom,
        'periode_id': periode.id,
        'periode': periode.nom_periode,
        'etablissement_id': etablissement.id,
        'etablissement': etablissement.nom,
        'moyenne_generale': float(moyenne_obj.moyenne_generale),
        'date_generation': timezone.now().isoformat(),
    }

    payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    signature = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

    moyenne_obj.numero_serie = numero_serie
    moyenne_obj.signature_numerique = signature
    verification_url = None
    if verification_url_base:
        query = urlencode({
            'numero_serie': numero_serie,
            'signature': signature or '',
        })
        verification_url = f"{verification_url_base}?{query}"

    qr_payload = verification_url or payload_str

    moyenne_obj.qr_code_data = qr_payload
    moyenne_obj.qr_code_generated_at = timezone.now()

    updated_fields = ['numero_serie', 'signature_numerique', 'qr_code_data', 'qr_code_generated_at', 'updated_at']

    # Générer le QR code pour tous les types d'établissements
    if qrcode:
        try:
            qr = qrcode.QRCode(
                version=2,
                error_correction=ERROR_CORRECT_M or qrcode.constants.ERROR_CORRECT_M,
                box_size=7,
                border=2,
            )
            qr.add_data(qr_payload)
            qr.make(fit=True)
            qr_image = qr.make_image(fill_color="#111827", back_color="#ffffff")
            buffer = BytesIO()
            qr_image.save(buffer, format='PNG')
            filename = f"bulletin_qr_{numero_serie}.png"
            if moyenne_obj.qr_code_image:
                moyenne_obj.qr_code_image.delete(save=False)
            moyenne_obj.qr_code_image.save(filename, ContentFile(buffer.getvalue()), save=False)
            updated_fields.append('qr_code_image')
        except Exception as e:
            logger.error(f"Erreur lors de la génération du QR code pour le bulletin {numero_serie}: {str(e)}", exc_info=True)
            # Continuer même si la génération du QR code échoue

    try:
        moyenne_obj.save(update_fields=updated_fields)
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde des éléments de sécurité du bulletin {numero_serie}: {str(e)}", exc_info=True)
        raise
    
    return numero_serie, signature


def _apply_standards_to_bulletin(matieres_table, moyenne_generale, appreciation_generale, decision_conseil, standards_bundle):
    """
    Applique les standards au bulletin et retourne les valeurs recalculées et métadonnées.
    """
    extra = {
        'appreciation_generale_standard': None,
        'appreciation_generale_source': None,
        'decision_conseil_standard': None,
        'decision_conseil_source': None,
        'statut_conseil_code': None,
        'statut_conseil_label': None,
        'standards_summary': None,
    }

    for item in matieres_table:
        initial_appreciation = item.get('appreciation')
        appreciation_value, source, standard_label = _compute_matiere_appreciation(
            item.get('moyenne_eleve'),
            standards_bundle,
            initial_appreciation
        )
        item['appreciation_initiale'] = initial_appreciation
        item['appreciation_standard'] = standard_label
        item['appreciation_source'] = source
        item['appreciation'] = appreciation_value

    appreciation_generale_value, appreciation_source, statut_code, statut_label, appreciation_standard = _compute_appreciation_generale(
        moyenne_generale,
        standards_bundle,
        appreciation_generale
    )
    extra['appreciation_generale_standard'] = appreciation_standard
    extra['appreciation_generale_source'] = appreciation_source

    decision_value, decision_source, decision_standard, statut_code_decision, statut_label_decision = _compute_decision_conseil(
        moyenne_generale,
        standards_bundle,
        decision_conseil
    )
    extra['decision_conseil_standard'] = decision_standard
    extra['decision_conseil_source'] = decision_source
    extra['statut_conseil_code'] = statut_code_decision or statut_code
    extra['statut_conseil_label'] = statut_label_decision or statut_label

    extra['standards_summary'] = _build_standards_metadata(
        standards_bundle,
        appreciation_source,
        decision_source,
        extra['statut_conseil_code'],
        extra['statut_conseil_label'],
    )

    return appreciation_generale_value, decision_value, extra


@login_required
def dashboard_directeur(request):
    """
    Vue du tableau de bord pour les directeurs d'établissement et le personnel administratif
    Le personnel administratif accède à la même interface mais avec des restrictions selon ses permissions
    """
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..utils.permissions_personnel import get_permissions_personnel, has_permission
    
    # Vérifier que l'utilisateur est soit un établissement soit un personnel administratif
    if isinstance(request.user, Etablissement):
        etablissement = request.user
        is_directeur = True
        personnel = None
        user_permissions = None  # Le directeur a toutes les permissions
    elif isinstance(request.user, PersonnelAdministratif):
        personnel = request.user
        etablissement = personnel.etablissement
        is_directeur = False
        user_permissions = get_permissions_personnel(personnel)
    else:
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        return redirect('school_admin:connexion_compte_user')
    from ..model.classe_model import Classe
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..model.professeur_model import Professeur
    from ..model.moyenne_model import Moyenne
    from ..model.inscription_eleve_model import InscriptionEleve
    from datetime import datetime, timedelta
    
    # Récupérer la session consultée par le directeur (peut être différente de la session active)
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    # Récupérer aussi la session réellement active pour l'afficher
    annee_scolaire_reellement_active = get_session_active(request, etablissement)
    
    # === STATISTIQUES DES ÉLÈVES ===
    # Filtrer les élèves par année scolaire active si disponible
    if annee_scolaire_active:
        eleves_ids_inscrits = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire_active,
            etablissement=etablissement
        ).values_list('eleve_id', flat=True)
        eleves = Eleve.objects.filter(
            id__in=eleves_ids_inscrits,
            etablissement=etablissement,
            actif=True
        )
    else:
        eleves = Eleve.objects.filter(etablissement=etablissement, actif=True)
    nombre_eleves_total = eleves.count()
    
    # Calculer le pourcentage de croissance (approximation basée sur les dates d'inscription récentes)
    date_annee_derniere = datetime.now() - timedelta(days=365)
    eleves_annee_derniere = Eleve.objects.filter(
        etablissement=etablissement, 
        date_inscription__lte=date_annee_derniere,
        actif=True
    ).count()
    if eleves_annee_derniere > 0:
        croissance_eleves = round(((nombre_eleves_total - eleves_annee_derniere) / eleves_annee_derniere) * 100, 1)
    else:
        croissance_eleves = 0
    
    # === STATISTIQUES DES ENSEIGNANTS ===
    nombre_enseignants = Professeur.objects.filter(etablissement=etablissement, actif=True).count()
    
    # === STATISTIQUES DU PERSONNEL ADMINISTRATIF ===
    nombre_personnel_admin = PersonnelAdministratif.objects.filter(
        etablissement=etablissement,
        actif=True
    ).count()
    
    # Calculer le changement de personnel cette année
    personnel_annee_derniere = PersonnelAdministratif.objects.filter(
        etablissement=etablissement,
        date_creation__lte=date_annee_derniere,
        actif=True
    ).count()
    changement_personnel = nombre_personnel_admin - personnel_annee_derniere
    
    # === STATISTIQUES DES CLASSES ===
    nombre_classes = Classe.objects.filter(etablissement=etablissement, actif=True).count()
    
    # === ÉVALUATIONS EN COURS ===
    # Récupérer les évaluations/devoirs de la semaine en cours
    date_debut_semaine = datetime.now() - timedelta(days=datetime.now().weekday())
    
    # Pour établissements primaires
    if etablissement.type_etablissement == 'primary':
        from ..model.evaluation_primaire_model import EvaluationPrimaire
        evaluations_queryset = EvaluationPrimaire.objects.filter(
            professeur__etablissement=etablissement,
            date_evaluation__gte=date_debut_semaine,
            actif=True
        )
        if annee_scolaire_active:
            evaluations_queryset = evaluations_queryset.filter(annee_scolaire=annee_scolaire_active)
        evaluations_semaine = evaluations_queryset.count()
    else:
        # Pour collège/lycée (0 si pas de modèle Evaluation)
        evaluations_semaine = 0
    
    # === BULLETINS PUBLIÉS ===
    # Compter les bulletins publiés (MoyennePeriode avec est_publie=True)
    from ..model.periode_model import PeriodeScolaire
    
    # Récupérer la période active
    periode_active = PeriodeScolaire.get_periode_active(etablissement)
    
    # Compter les bulletins publiés pour la période active ou toutes les périodes
    if periode_active:
        bulletins_queryset = MoyennePeriode.objects.filter(
            etablissement=etablissement,
            periode=periode_active,
            est_publie=True,
            est_moyenne_generale=True  # Seulement les moyennes générales (bulletins)
        )
        if annee_scolaire_active:
            bulletins_queryset = bulletins_queryset.filter(annee_scolaire=annee_scolaire_active)
        bulletins_publies = bulletins_queryset.count()
    else:
        # Si pas de période active, compter tous les bulletins publiés de l'établissement
        bulletins_queryset = MoyennePeriode.objects.filter(
            etablissement=etablissement,
            est_publie=True,
            est_moyenne_generale=True
        )
        if annee_scolaire_active:
            bulletins_queryset = bulletins_queryset.filter(annee_scolaire=annee_scolaire_active)
        bulletins_publies = bulletins_queryset.count()
    
    # === ALERTES ===
    # Compter les élèves avec un taux de présence < 80% ou moyenne < 10
    from ..model.presence_model import Presence
    from django.db.models import Q
    
    alertes_count = 0
    
    # Alertes de présence (élèves avec beaucoup d'absences ce mois)
    date_debut_mois = datetime.now().replace(day=1)
    eleves_avec_absences = 0
    for eleve in eleves[:100]:  # Limiter pour la performance
        absences_queryset = Presence.objects.filter(
            eleve=eleve,
            date__gte=date_debut_mois,
            statut__in=['absent', 'absent_justifie']
        )
        if annee_scolaire_active:
            absences_queryset = absences_queryset.filter(annee_scolaire=annee_scolaire_active)
        absences = absences_queryset.count()
        if absences >= 5:
            eleves_avec_absences += 1
    
    alertes_count = eleves_avec_absences
    
    # === TAUX DE RÉUSSITE ===
    # Calculer le taux basé sur les moyennes générales de MoyennePeriode >= 10/20
    # Seulement les moyennes générales (bulletins) pour la période active
    if periode_active:
        moyennes_generales = MoyennePeriode.objects.filter(
            etablissement=etablissement,
            periode=periode_active,
            est_moyenne_generale=True,
            moyenne_generale__isnull=False
        )
        if annee_scolaire_active:
            moyennes_generales = moyennes_generales.filter(annee_scolaire=annee_scolaire_active)
    else:
        # Si pas de période active, utiliser toutes les moyennes générales
        moyennes_generales = MoyennePeriode.objects.filter(
            etablissement=etablissement,
            est_moyenne_generale=True,
            moyenne_generale__isnull=False
        )
        if annee_scolaire_active:
            moyennes_generales = moyennes_generales.filter(annee_scolaire=annee_scolaire_active)
    
    if moyennes_generales.exists():
        # Compter les moyennes >= 10/20 comme réussies
        moyennes_reussies = moyennes_generales.filter(moyenne_generale__gte=Decimal('10.00')).count()
        total_moyennes = moyennes_generales.count()
        taux_reussite = round((moyennes_reussies / total_moyennes) * 100) if total_moyennes > 0 else 0
    else:
        taux_reussite = 0
    
    # === RESSOURCES PÉDAGOGIQUES ===
    # 0 si pas encore de table dédiée
    ressources_pedagogiques = 0
    
    # === DISTINCTIONS ===
    # 0 si pas encore de table dédiée
    distinctions = 0
    
    # === DERNIERS ÉLÈVES INSCRITS ===
    derniers_eleves = eleves.order_by('-date_inscription')[:2]
    
    # === DERNIERS PERSONNELS AJOUTÉS ===
    derniers_personnels = PersonnelAdministratif.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('-date_creation')[:2]
    
    # === DERNIÈRES MOYENNES PUBLIÉES ===
    dernieres_moyennes_qs = Moyenne.objects.filter(
        eleve__etablissement=etablissement,
        soumis=True,
        actif=True
    )
    if annee_scolaire_active:
        dernieres_moyennes_qs = dernieres_moyennes_qs.filter(annee_scolaire=annee_scolaire_active)
    dernieres_moyennes = dernieres_moyennes_qs.select_related('eleve', 'classe', 'matiere').order_by('-date_calcul')[:2]
    
    # === DERNIÈRES ÉVALUATIONS ===
    if etablissement.type_etablissement == 'primary':
        from ..model.evaluation_primaire_model import EvaluationPrimaire
        dernieres_evaluations_qs = EvaluationPrimaire.objects.filter(
            professeur__etablissement=etablissement,
            actif=True
        )
        if annee_scolaire_active:
            dernieres_evaluations_qs = dernieres_evaluations_qs.filter(annee_scolaire=annee_scolaire_active)
        dernieres_evaluations = dernieres_evaluations_qs.select_related('classe', 'matiere').order_by('-date_evaluation')[:2]
    else:
        from ..model.evaluation_model import Evaluation
        dernieres_evaluations_qs = Evaluation.objects.filter(
            professeur__etablissement=etablissement,
            actif=True
        )
        # Pour les établissements secondaires, on ne peut pas filtrer par année scolaire directement
        # car le modèle Evaluation n'a pas ce champ, donc on filtre par période si disponible
        if periode_active and annee_scolaire_active:
            # Filtrer indirectement via les périodes de l'année scolaire active
            periodes_ids = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                annee_scolaire_fk=annee_scolaire_active
            ).values_list('id', flat=True)
            dernieres_evaluations_qs = dernieres_evaluations_qs.filter(
                periode_scolaire_id__in=periodes_ids
            )
        dernieres_evaluations = dernieres_evaluations_qs.select_related('classe', 'matiere').order_by('-date_evaluation')[:2]
    
    notifications_non_lues = NotificationDirecteur.objects.filter(
        etablissement=etablissement,
        lu=False,
    ).count()
    
    # === HISTORIQUE DES DERNIÈRES ACTIVITÉS ===
    from ..model.presence_model import SoumissionListePresence, Presence
    from ..model.releve_notes_model import ReleveNotes
    from ..model.sanction_model import Sanction
    
    # 1. Dernières soumissions de listes de présence (max 4)
    dernieres_soumissions_presence_qs = SoumissionListePresence.objects.filter(
        etablissement=etablissement
    ).select_related('professeur', 'classe', 'matiere')
    
    if annee_scolaire_active:
        dernieres_soumissions_presence_qs = dernieres_soumissions_presence_qs.filter(
            annee_scolaire=annee_scolaire_active
        )
    
    dernieres_soumissions_presence = dernieres_soumissions_presence_qs.order_by('-date_soumission')[:4]
    
    # Enrichir avec les statistiques de présence/absence pour chaque soumission
    dernieres_soumissions_presence_enrichies = []
    for soumission in dernieres_soumissions_presence:
        # Récupérer les présences pour cette classe, date et matière
        presences_qs = Presence.objects.filter(
            classe=soumission.classe,
            date=soumission.date,
            etablissement=etablissement
        )
        if soumission.matiere:
            presences_qs = presences_qs.filter(matiere=soumission.matiere)
        if annee_scolaire_active:
            presences_qs = presences_qs.filter(annee_scolaire=annee_scolaire_active)
        
        nombre_presents = presences_qs.filter(statut='present').count()
        nombre_absents = presences_qs.filter(statut__in=['absent', 'absent_justifie']).count()
        
        dernieres_soumissions_presence_enrichies.append({
            'soumission': soumission,
            'nombre_presents': nombre_presents,
            'nombre_absents': nombre_absents,
        })
    
    # 2. Derniers relevés de notes soumis (max 4)
    derniers_releves_notes_qs = ReleveNotes.objects.filter(
        etablissement=etablissement,
        soumis=True
    ).select_related('professeur', 'classe', 'matiere', 'periode_scolaire')
    
    if annee_scolaire_active:
        derniers_releves_notes_qs = derniers_releves_notes_qs.filter(
            annee_scolaire=annee_scolaire_active
        )
    
    derniers_releves_notes = derniers_releves_notes_qs.order_by('-date_soumission')[:4]
    
    # 3. Dernières sanctions données (max 4)
    dernieres_sanctions_qs = Sanction.objects.filter(
        etablissement=etablissement
    ).select_related('eleve', 'classe', 'professeur')
    
    if annee_scolaire_active:
        dernieres_sanctions_qs = dernieres_sanctions_qs.filter(
            annee_scolaire=annee_scolaire_active
        )
    
    dernieres_sanctions = dernieres_sanctions_qs.order_by('-date_sanction', '-date_creation')[:4]
    
    # 4. Dernières justifications de notes en attente (max 4)
    dernieres_justifications_qs = JustificationNote.objects.filter(
        etablissement=etablissement,
        statut=JustificationNote.STATUT_EN_ATTENTE
    ).select_related(
        'classe',
        'eleve',
        'matiere',
        'professeur',
        'evaluation',
        'evaluation_primaire',
        'note_examen',
        'note_examen__session_examen'
    )
    
    if annee_scolaire_active:
        dernieres_justifications_qs = dernieres_justifications_qs.filter(annee_scolaire=annee_scolaire_active)
    
    dernieres_justifications = dernieres_justifications_qs.order_by('-date_creation')[:4]
    
    # Compter le total des justifications en attente
    total_justifications_en_attente = dernieres_justifications_qs.count()
    
    # Récupérer toutes les années scolaires de l'établissement pour le sélecteur
    toutes_annees_scolaires = AnneeScolaire.objects.filter(
        etablissement=etablissement
    ).order_by('-date_debut')

    # Préparer le contexte avec les données de l'établissement
    context = {
        'etablissement': etablissement,
        'periode_active': periode_active,  # Ajouter la période active au contexte
        'annee_scolaire_active': annee_scolaire_active,  # Session consultée par le directeur
        'annee_scolaire_reellement_active': annee_scolaire_reellement_active,  # Session réellement active
        'toutes_annees_scolaires': toutes_annees_scolaires,  # Toutes les sessions pour le sélecteur
        
        # Informations sur l'utilisateur et ses permissions
        'is_directeur': is_directeur,
        'is_personnel_administratif': not is_directeur,
        'personnel': personnel if not is_directeur else None,
        'user_permissions': user_permissions if not is_directeur else None,  # Liste des permissions (None = toutes)
        
        # Statistiques principales
        'stats': {
            'nombre_eleves': nombre_eleves_total,
            'croissance_eleves': croissance_eleves,
            'nombre_enseignants': nombre_enseignants,
            'nombre_personnel_admin': nombre_personnel_admin,
            'changement_personnel': changement_personnel,
            'nombre_classes': nombre_classes,
            'evaluations_semaine': evaluations_semaine,
            'bulletins_publies': bulletins_publies,
            'alertes': alertes_count,
            'taux_reussite': taux_reussite,
            'ressources_pedagogiques': ressources_pedagogiques,
            'distinctions': distinctions,
        },
        
        # Dernières activités
        'derniers_eleves': derniers_eleves,
        'derniers_personnels': derniers_personnels,
        'dernieres_moyennes': dernieres_moyennes,
        'dernieres_evaluations': dernieres_evaluations,
        'notifications_directeur_non_lues': notifications_non_lues,
        
        # Historique des dernières activités
        'dernieres_soumissions_presence': dernieres_soumissions_presence_enrichies,
        'derniers_releves_notes': derniers_releves_notes,
        'dernieres_sanctions': dernieres_sanctions,
        'dernieres_justifications': dernieres_justifications,
        'total_justifications_en_attente': total_justifications_en_attente,
    }
    
    return render(request, 'school_admin/directeur/dashboard_directeur.html', context)


@login_required
def changer_session_directeur(request):
    """
    Vue pour changer la session consultée par le directeur.
    Cette vue permet au directeur de consulter une session différente
    sans affecter la session active utilisée par les autres utilisateurs.
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    if request.method == 'POST':
        session_id = request.POST.get('session_id', '').strip()
        
        if session_id:
            try:
                session = AnneeScolaire.objects.get(
                    id=int(session_id),
                    etablissement=etablissement
                )
                from ..utils.session_utils import set_session_consultee
                set_session_consultee(request, session)
                messages.success(request, f"Session consultée changée : {session.libelle}")
            except (AnneeScolaire.DoesNotExist, ValueError):
                messages.error(request, "Session invalide.")
        else:
            # Réinitialiser à la session active
            from ..utils.session_utils import set_session_consultee
            set_session_consultee(request, None)
            messages.success(request, "Retour à la session active.")
    
    # Rediriger vers la page d'origine ou le dashboard
    redirect_url = request.GET.get('next', 'directeur:dashboard_directeur')
    return redirect(redirect_url)


@login_required
def facturation_directeur(request):
    """
    Vue de la page de facturation pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer toutes les factures de l'établissement
    facturations = Facturation.objects.filter(etablissement=etablissement).order_by('-date_creation')
    
    # Filtres
    statut_filter = request.GET.get('statut', '')
    type_filter = request.GET.get('type', '')
    
    if statut_filter:
        facturations = facturations.filter(statut=statut_filter)
    if type_filter:
        facturations = facturations.filter(type_facture=type_filter)
    
    # Statistiques détaillées
    stats = {
        'total_factures': facturations.count(),
        'montant_total': facturations.aggregate(total=Sum('montant_total'))['total'] or 0,
        'en_attente': facturations.filter(statut='en_attente').count(),
        'payees': facturations.filter(statut='paye').count(),
        'en_retard': facturations.filter(statut='en_retard').count(),
        'annulees': facturations.filter(statut='annule').count(),
    }
    
    # Montants par statut
    montants_par_statut = {}
    for statut, _ in Facturation.STATUT_CHOICES:
        montant = facturations.filter(statut=statut).aggregate(total=Sum('montant_total'))['total'] or 0
        montants_par_statut[statut] = montant
    
    # Factures urgentes (en retard ou échéance proche)
    factures_urgentes = []
    for facture in facturations.filter(statut__in=['en_attente', 'en_retard']):
        if facture.est_urgente or facture.est_en_retard():
            factures_urgentes.append(facture)
    
    # Modules activés et inactifs
    modules_info = {
        'gestion_eleves': {'nom': 'Gestion des élèves', 'actif': etablissement.module_gestion_eleves, 'prix': 0},
        'notes_evaluations': {'nom': 'Notes et évaluations', 'actif': etablissement.module_notes_evaluations, 'prix': 0},
        'emploi_temps': {'nom': 'Emploi du temps', 'actif': etablissement.module_emploi_temps, 'prix': 0},
        'gestion_personnel': {'nom': 'Gestion du personnel', 'actif': etablissement.module_gestion_personnel, 'prix': 0},
        'surveillance': {'nom': 'Surveillance et sécurité', 'actif': etablissement.module_surveillance, 'prix': 0},
        'communication': {'nom': 'Communication parents', 'actif': etablissement.module_communication, 'prix': 0},
        'orientation': {'nom': 'Orientation scolaire', 'actif': etablissement.module_orientation, 'prix': 0},
        'formation': {'nom': 'Formation continue', 'actif': etablissement.module_formation, 'prix': 0},
        'transport_scolaire': {'nom': 'Transport scolaire', 'actif': etablissement.module_transport_scolaire, 'prix': 0},
        'cantine': {'nom': 'Gestion de la cantine', 'actif': etablissement.module_cantine, 'prix': 0},
        'bibliotheque': {'nom': 'Gestion de la bibliothèque', 'actif': etablissement.module_bibliotheque, 'prix': 0},
        'sante': {'nom': 'Suivi médical', 'actif': etablissement.module_sante, 'prix': 0},
        'activites': {'nom': 'Activités extra-scolaires', 'actif': etablissement.module_activites, 'prix': 0},
        'comptabilite': {'nom': 'Comptabilité', 'actif': etablissement.module_comptabilite, 'prix': 0},
        'censeurs': {'nom': 'Censeurs', 'actif': etablissement.module_censeurs, 'prix': 0},
    }
    
    # Calculer le montant total théorique
    # Récupérer l'année scolaire active pour filtrer les élèves
    from ..utils.session_utils import get_session_active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    # Filtrer les élèves par année scolaire active si disponible
    if annee_scolaire_active:
        eleves_ids_inscrits = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire_active,
            etablissement=etablissement
        ).values_list('eleve_id', flat=True)
        nombre_eleves_total = Eleve.objects.filter(
            id__in=eleves_ids_inscrits,
            etablissement=etablissement,
            actif=True
        ).count()
    else:
        nombre_eleves_total = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
    
    montant_par_eleve = etablissement.montant_par_eleve
    montant_total_theorique = nombre_eleves_total * montant_par_eleve
    
    # Statistiques du personnel
    from ..model.personnel_administratif_model import PersonnelAdministratif
    nombre_personnel_admin = PersonnelAdministratif.objects.filter(etablissement=etablissement).count()
    nombre_enseignants = 0  # À implémenter quand le modèle enseignant sera créé
    nombre_classes = 0  # À implémenter quand le modèle classe sera créé
    
    context = {
        'etablissement': etablissement,
        'facturations': facturations,
        'stats': stats,
        'montants_par_statut': montants_par_statut,
        'factures_urgentes': factures_urgentes,
        'modules_info': modules_info,
        'statut_choices': Facturation.STATUT_CHOICES,
        'type_choices': Facturation.TYPE_FACTURE_CHOICES,
        'statut_filter': statut_filter,
        'type_filter': type_filter,
        'montant_par_eleve': montant_par_eleve,
        'nombre_eleves_total': nombre_eleves_total,
        'montant_total_theorique': montant_total_theorique,
        'nombre_personnel_admin': nombre_personnel_admin,
        'nombre_enseignants': nombre_enseignants,
        'nombre_classes': nombre_classes,
    }
    
    return render(request, 'school_admin/directeur/facturation_directeur.html', context)


@login_required
def gestion_pedagogique(request):
    """
    Vue de la page de gestion pédagogique pour les directeurs d'établissement et le personnel administratif
    """
    # Vérifier que l'utilisateur a accès (au moins une permission pédagogique)
    user = request.user
    if isinstance(user, Etablissement):
        etablissement = user
        is_directeur = True
        personnel = None
    elif isinstance(user, PersonnelAdministratif):
        # Vérifier au moins une permission pédagogique
        has_notes = check_permission(user, 'notes_liste')
        has_presences = check_permission(user, 'presences_liste')
        if not (has_notes or has_presences):
            messages.error(request, "Vous n'avez pas la permission d'accéder à cette page.")
            return redirect('directeur:dashboard_directeur')
        etablissement = user.etablissement
        is_directeur = False
        personnel = user
    else:
        return redirect('school_admin:connexion_compte_user')
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    context = {
        'etablissement': etablissement,
        'annee_scolaire_active': annee_scolaire_active,
    }
   
    return render(request, 'school_admin/directeur/gestion_pedagogique.html', context)


@login_required
def gestion_eleves(request):
    """
    Vue de la page de gestion des élèves pour les directeurs d'établissement et le personnel administratif
    """
    # Vérifier que l'utilisateur a accès
    result = _get_user_etablissement(request, 'eleves_liste')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement, is_directeur, personnel = result
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    context = {
        'etablissement': etablissement,
        'annee_scolaire_active': annee_scolaire_active,
    }
  
    return render(request, 'school_admin/directeur/gestion_eleves.html', context)


@login_required
@login_required
@require_permission('eleves_reinscrire')
def liste_reinscription_eleves(request):
    """
    Liste des élèves éligibles à la réinscription
    Affiche les élèves ayant une inscription dans une année précédente mais pas dans l'année active
    """
    result = _get_user_etablissement(request, 'eleves_reinscrire')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(
            request,
            "Aucune année scolaire active n'a été trouvée. Créez ou activez d'abord une session pour continuer."
        )
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Récupérer les IDs des élèves déjà inscrits pour l'année active
    eleves_inscrits_ids = InscriptionEleve.objects.filter(
        annee_scolaire=annee_scolaire_active,
        etablissement=etablissement
    ).values_list('eleve_id', flat=True)
    
    # Récupérer les élèves ayant une inscription dans une année précédente (désactivée)
    # mais pas dans l'année active
    eleves_eligibles = Eleve.objects.filter(
        etablissement=etablissement,
        inscriptions__annee_scolaire__est_active=False
    ).exclude(
        id__in=eleves_inscrits_ids
    ).distinct().select_related('classe').prefetch_related('inscriptions__annee_scolaire', 'inscriptions__classe')
    
    # Recherche par nom/prénom (insensible à la casse)
    search_query = request.GET.get('search', '').strip()
    classe_id = request.GET.get('classe', '').strip()
    
    eleves_data = []
    has_search = False
    
    # Si une recherche a été effectuée
    if search_query or classe_id:
        has_search = True
        
        # Filtre par nom/prénom (insensible à la casse)
        if search_query:
            eleves_eligibles = eleves_eligibles.filter(
                Q(nom__icontains=search_query) | 
                Q(prenom__icontains=search_query) | 
                Q(matricule_eleve__icontains=search_query)
            )
        
        # Filtre par classe (via la dernière inscription)
        if classe_id:
            try:
                classe_obj = Classe.objects.get(id=classe_id, etablissement=etablissement)
                # Filtrer les élèves qui ont eu une inscription dans cette classe
                eleves_ids_avec_classe = InscriptionEleve.objects.filter(
                    annee_scolaire__est_active=False,
                    classe=classe_obj,
                    etablissement=etablissement
                ).values_list('eleve_id', flat=True)
                eleves_eligibles = eleves_eligibles.filter(id__in=eleves_ids_avec_classe)
            except Classe.DoesNotExist:
                pass
        
        # Préparer les données pour l'affichage
        for eleve in eleves_eligibles.order_by('nom', 'prenom'):
            # Récupérer la dernière inscription (année la plus récente)
            derniere_inscription = eleve.inscriptions.filter(
                annee_scolaire__est_active=False
            ).select_related('annee_scolaire', 'classe').order_by('-annee_scolaire__date_debut').first()
            
            if derniere_inscription:
                eleves_data.append({
                    'eleve': eleve,
                    'derniere_inscription': derniere_inscription,
                    'derniere_annee': derniere_inscription.annee_scolaire,
                    'derniere_classe': derniere_inscription.classe,
                })
    
    context = {
        'etablissement': etablissement,
        'annee_scolaire_active': annee_scolaire_active,
        'eleves_data': eleves_data,
        'search_query': search_query,
        'classe_id': classe_id,
        'classes': classes,
        'has_search': has_search,
    }
    
    return render(request, 'school_admin/directeur/reinscription/liste_reinscription_eleves.html', context)


@login_required
@require_permission('eleves_reinscrire')
def reinscription_eleve(request, eleve_id):
    """
    Formulaire de réinscription pour un élève spécifique
    """
    result = _get_user_etablissement(request, 'eleves_reinscrire')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(
            request,
            "Aucune année scolaire active n'a été trouvée. Créez ou activez d'abord une session pour continuer."
        )
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    # Récupérer l'élève
    try:
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:liste_reinscription')
    
    # Vérifier que l'élève n'est pas déjà inscrit pour l'année active
    inscription_existante = InscriptionEleve.objects.filter(
        eleve=eleve,
        annee_scolaire=annee_scolaire_active,
        etablissement=etablissement
    ).first()
    
    if inscription_existante:
        messages.warning(request, f"L'élève {eleve.nom_complet} est déjà inscrit pour l'année scolaire active.")
        return redirect('directeur:liste_reinscription')
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Récupérer le parent associé (s'il existe)
    parent = None
    lien_familial = None
    if eleve.parent_telephone:
        from ..model.lien_familial_model import LienFamilial
        lien_familial = LienFamilial.objects.filter(
            eleve=eleve,
            actif=True
        ).select_related('parent').first()
        if lien_familial:
            parent = lien_familial.parent
    
    # Initialiser les données du formulaire avec les données de l'élève
    form_data = {
        'nom': eleve.nom,
        'prenom': eleve.prenom,
        'date_naissance': eleve.date_naissance.strftime('%Y-%m-%d') if eleve.date_naissance else '',
        'lieu_naissance': eleve.lieu_naissance or '',
        'sexe': eleve.sexe,
        'nationalite': eleve.nationalite or '',
        'adresse': eleve.adresse or '',
        'telephone': eleve.telephone or '',
        'email': eleve.email or '',
        'classe': eleve.classe.id if eleve.classe else '',
        'date_inscription': date.today().strftime('%Y-%m-%d'),
        'statut': 'reinscription',
        # Informations parent
        'parent_nom': eleve.parent_nom or (parent.nom if parent else ''),
        'parent_prenom': eleve.parent_prenom or (parent.prenom if parent else ''),
        'parent_telephone': eleve.parent_telephone or (parent.telephone if parent else ''),
        'parent_email': eleve.parent_email or (parent.email if parent else ''),
        'parent_adresse': eleve.parent_adresse or (parent.adresse if parent else ''),
        'parent_profession': eleve.parent_profession or (parent.profession if parent else ''),
        'parent_lien': eleve.parent_lien or (lien_familial.type_lien if lien_familial else ''),
        # Documents
        'document_acte_naissance': eleve.document_acte_naissance,
        'document_cni': eleve.document_cni,
        'document_passeport': eleve.document_passeport,
        'document_bulletin_precedent': eleve.document_bulletin_precedent,
        'document_certificat_scolarite': eleve.document_certificat_scolarite,
        'document_livret_scolaire': eleve.document_livret_scolaire,
        'document_certificat_medical': eleve.document_certificat_medical,
        'document_carnet_vaccination': eleve.document_carnet_vaccination,
        'document_assurance_maladie': eleve.document_assurance_maladie,
        'document_justificatif_domicile': eleve.document_justificatif_domicile,
        'document_photo_identite': eleve.document_photo_identite,
        'document_autorisation_parentale': eleve.document_autorisation_parentale,
    }
    
    field_errors = {}
    
    if request.method == 'POST':
        # Récupération des données du formulaire
        form_data = {
            'nom': request.POST.get('nom', '').strip(),
            'prenom': request.POST.get('prenom', '').strip(),
            'date_naissance': request.POST.get('date_naissance', ''),
            'lieu_naissance': request.POST.get('lieu_naissance', '').strip(),
            'sexe': request.POST.get('sexe', ''),
            'nationalite': request.POST.get('nationalite', '').strip(),
            'adresse': request.POST.get('adresse', '').strip(),
            'telephone': request.POST.get('telephone', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'classe': request.POST.get('classe', ''),
            'date_inscription': request.POST.get('date_inscription', ''),
            'statut': 'reinscription',
            # Informations parent
            'parent_nom': request.POST.get('parent_nom', '').strip(),
            'parent_prenom': request.POST.get('parent_prenom', '').strip(),
            'parent_telephone': request.POST.get('parent_telephone_full', '').strip() or request.POST.get('parent_telephone', '').strip(),
            'parent_email': request.POST.get('parent_email', '').strip(),
            'parent_adresse': request.POST.get('parent_adresse', '').strip(),
            'parent_profession': request.POST.get('parent_profession', '').strip(),
            'parent_lien': request.POST.get('parent_lien', ''),
            # Documents
            'document_acte_naissance': request.POST.get('document_acte_naissance') == 'true',
            'document_cni': request.POST.get('document_cni') == 'true',
            'document_passeport': request.POST.get('document_passeport') == 'true',
            'document_bulletin_precedent': request.POST.get('document_bulletin_precedent') == 'true',
            'document_certificat_scolarite': request.POST.get('document_certificat_scolarite') == 'true',
            'document_livret_scolaire': request.POST.get('document_livret_scolaire') == 'true',
            'document_certificat_medical': request.POST.get('document_certificat_medical') == 'true',
            'document_carnet_vaccination': request.POST.get('document_carnet_vaccination') == 'true',
            'document_assurance_maladie': request.POST.get('document_assurance_maladie') == 'true',
            'document_justificatif_domicile': request.POST.get('document_justificatif_domicile') == 'true',
            'document_photo_identite': request.POST.get('document_photo_identite') == 'true',
            'document_autorisation_parentale': request.POST.get('document_autorisation_parentale') == 'true',
        }
        
        # Validation
        is_valid = True
        inscription_date_obj = None
        
        # Champs obligatoires
        required_fields = ['nom', 'prenom', 'date_naissance', 'lieu_naissance', 'sexe', 'nationalite', 'classe', 'date_inscription']
        for field in required_fields:
            if not form_data[field]:
                field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                is_valid = False
        
        # Validation des champs parent
        parent_required = ['parent_nom', 'parent_prenom', 'parent_telephone', 'parent_lien']
        for field in parent_required:
            if not form_data[field]:
                field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                is_valid = False
        
        # Validation de la date de naissance
        if form_data['date_naissance']:
            try:
                birth_date = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
                if birth_date > date.today():
                    field_errors['date_naissance'] = "La date de naissance ne peut pas être dans le futur."
                    is_valid = False
            except ValueError:
                field_errors['date_naissance'] = "Format de date invalide."
                is_valid = False
        
        # Validation de la date d'inscription
        if form_data['date_inscription']:
            try:
                inscription_date = datetime.strptime(form_data['date_inscription'], '%Y-%m-%d').date()
                inscription_date_obj = inscription_date
                if inscription_date > date.today():
                    field_errors['date_inscription'] = "La date d'inscription ne peut pas être dans le futur."
                    is_valid = False
            except ValueError:
                field_errors['date_inscription'] = "Format de date invalide."
                is_valid = False
        
        # Validation de la classe
        classe = None
        if form_data['classe']:
            try:
                classe = Classe.objects.get(id=form_data['classe'], etablissement=etablissement)
                if classe.places_disponibles <= 0:
                    field_errors['classe'] = f"La classe {classe.nom} est pleine. Aucune place disponible."
                    is_valid = False
            except Classe.DoesNotExist:
                field_errors['classe'] = "La classe sélectionnée n'existe pas."
                is_valid = False
        
        # Validation du sexe
        if form_data['sexe'] not in ['M', 'F']:
            field_errors['sexe'] = "Le sexe doit être Masculin ou Féminin."
            is_valid = False
        
        # Validation du lien parent
        if form_data['parent_lien'] not in ['pere', 'mere', 'grand_parent', 'oncle_tante', 'frere_soeur', 'autre_famille', 'tuteur_legal', 'autre']:
            field_errors['parent_lien'] = "Le lien avec l'élève sélectionné n'est pas valide."
            is_valid = False
        
        # Si tout est valide, procéder à la réinscription
        if is_valid:
            try:
                with transaction.atomic():
                    # Mettre à jour les informations de l'élève si nécessaire
                    eleve.nom = form_data['nom']
                    eleve.prenom = form_data['prenom']
                    if form_data['date_naissance']:
                        eleve.date_naissance = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
                    eleve.lieu_naissance = form_data['lieu_naissance']
                    eleve.sexe = form_data['sexe']
                    eleve.nationalite = form_data['nationalite']
                    eleve.adresse = form_data['adresse'] if form_data['adresse'] else None
                    eleve.telephone = form_data['telephone'] if form_data['telephone'] else None
                    eleve.email = form_data['email'] if form_data['email'] else None
                    eleve.classe = classe
                    eleve.date_inscription = inscription_date_obj
                    eleve.statut = 'reinscription'
                    # Informations parent
                    eleve.parent_nom = form_data['parent_nom']
                    eleve.parent_prenom = form_data['parent_prenom']
                    eleve.parent_telephone = form_data['parent_telephone']
                    eleve.parent_email = form_data['parent_email'] if form_data['parent_email'] else None
                    eleve.parent_adresse = form_data['parent_adresse'] if form_data['parent_adresse'] else None
                    eleve.parent_profession = form_data['parent_profession'] if form_data['parent_profession'] else None
                    eleve.parent_lien = form_data['parent_lien']
                    # Documents
                    eleve.document_acte_naissance = form_data['document_acte_naissance']
                    eleve.document_cni = form_data['document_cni']
                    eleve.document_passeport = form_data['document_passeport']
                    eleve.document_bulletin_precedent = form_data['document_bulletin_precedent']
                    eleve.document_certificat_scolarite = form_data['document_certificat_scolarite']
                    eleve.document_livret_scolaire = form_data['document_livret_scolaire']
                    eleve.document_certificat_medical = form_data['document_certificat_medical']
                    eleve.document_carnet_vaccination = form_data['document_carnet_vaccination']
                    eleve.document_assurance_maladie = form_data['document_assurance_maladie']
                    eleve.document_justificatif_domicile = form_data['document_justificatif_domicile']
                    eleve.document_photo_identite = form_data['document_photo_identite']
                    eleve.document_autorisation_parentale = form_data['document_autorisation_parentale']
                    
                    eleve.save()
                    
                    # Gérer le parent
                    from ..model.lien_familial_model import LienFamilial
                    
                    # Vérifier si un parent avec ce téléphone existe déjà
                    parent_existant = None
                    if form_data['parent_telephone']:
                        parent_existant = Parent.objects.filter(
                            telephone=form_data['parent_telephone'],
                            etablissement=etablissement
                        ).first()
                    
                    if parent_existant:
                        parent = parent_existant
                        # Mettre à jour les informations du parent si nécessaire
                        parent.nom = form_data['parent_nom']
                        parent.prenom = form_data['parent_prenom']
                        if form_data['parent_email']:
                            parent.email = form_data['parent_email']
                        if form_data['parent_adresse']:
                            parent.adresse = form_data['parent_adresse']
                        if form_data['parent_profession']:
                            parent.profession = form_data['parent_profession']
                        parent.save()
                    else:
                        # Créer un nouveau compte parent si nécessaire
                        # Note: Parent est déjà importé en haut du fichier
                        matricule_parent = Parent.generer_matricule_parent(etablissement)
                        mot_de_passe_parent = Parent.generer_mot_de_passe()
                        
                        parent = Parent(
                            matricule_parental=matricule_parent,
                            type_parent=form_data['parent_lien'] if form_data['parent_lien'] in ['mere', 'pere', 'tuteur'] else 'tuteur',
                            nom=form_data['parent_nom'],
                            prenom=form_data['parent_prenom'],
                            telephone=form_data['parent_telephone'],
                            email=form_data['parent_email'] if form_data['parent_email'] else '',
                            adresse=form_data['parent_adresse'] if form_data['parent_adresse'] else '',
                            profession=form_data['parent_profession'] if form_data['parent_profession'] else '',
                            etablissement=etablissement,
                            mot_de_passe_provisoire=mot_de_passe_parent,
                            mot_de_passe_modifie=False,
                            username=matricule_parent,
                            is_active=True,
                            is_staff=False,
                            is_superuser=False,
                        )
                        parent.set_password(mot_de_passe_parent)
                        parent.save()
                    
                    # Créer ou mettre à jour le lien familial
                    lien_familial, created = LienFamilial.objects.update_or_create(
                        parent=parent,
                        eleve=eleve,
                        defaults={
                            'type_lien': form_data['parent_lien'] if form_data['parent_lien'] in ['mere', 'pere', 'tuteur'] else 'tuteur',
                            'statut': 'valide',
                            'est_inscripteur': True,
                            'actif': True,
                        }
                    )
                    
                    # Archiver l'inscription dans InscriptionEleve
                    from ..personal_views.secretaire_view import _archiver_inscription_eleve_parent
                    _archiver_inscription_eleve_parent(
                        eleve=eleve,
                        parent=parent,
                        etablissement=etablissement,
                        annee_scolaire=annee_scolaire_active,
                        date_inscription=inscription_date_obj or eleve.date_inscription
                    )
                    
                    # Mettre à jour la date de dernière facturation
                    etablissement.date_derniere_facturation = timezone.now()
                    etablissement.save(update_fields=['date_derniere_facturation'])
                    
                    messages.success(request, f"L'élève {form_data['nom']} {form_data['prenom']} a été réinscrit avec succès pour l'année scolaire {annee_scolaire_active.libelle} !")
                    return redirect('directeur:liste_reinscription')
                    
            except Exception as e:
                logger.error(f"Erreur lors de la réinscription: {str(e)}", exc_info=True)
                field_errors['__all__'] = f"Une erreur est survenue lors de la réinscription: {str(e)}. Veuillez réessayer."
                is_valid = False
    
    # Récupérer la liste des pays pour le select
    try:
        from django_countries import countries
        pays_list = [(code, str(nom)) for code, nom in countries]
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des pays: {str(e)}")
        pays_list = []
    
    context = {
        'etablissement': etablissement,
        'annee_scolaire_active': annee_scolaire_active,
        'eleve': eleve,
        'classes': classes,
        'form_data': form_data,
        'field_errors': field_errors,
        'pays_list': pays_list,
        'parent': parent,
    }
    
    return render(request, 'school_admin/directeur/reinscription/reinscription_eleve.html', context)


@login_required
@login_required
@require_permission('notes_liste')
def notes_et_resultats(request):
    """
    Page de visualisation des notes et résultats par classe et par matière
    Adaptée pour le primaire et le collège/lycée
    """
    result = _get_user_etablissement(request, 'notes_liste')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Note, Evaluation
    from ..model.affectation_model import AffectationProfesseur
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from ..model.note_primaire_model import MoyenneMatierePrimaire
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    from collections import defaultdict
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Les données affichées ne sont pas filtrées par session.")
    
    # Détecter le type d'établissement
    est_primaire = etablissement.type_etablissement in ['primaire', 'primary']
    
    # Récupérer la liste des périodes filtrées par année scolaire active
    if annee_scolaire_active:
        periodes = list(
            PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                annee_scolaire_fk=annee_scolaire_active
            ).order_by('date_debut')
        )
    else:
        periodes = list(
            PeriodeScolaire.objects.filter(etablissement=etablissement).order_by('date_debut')
        )
    periode_id_param = request.GET.get('periode')
    periode_selectionnee = periodes[0] if periodes else None
    if periode_id_param and periodes:
        periode_selectionnee = next((p for p in periodes if str(p.id) == str(periode_id_param)), periode_selectionnee)
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau numérique
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "6eme", "5eme", "CM1", etc.
        else:
            categorie = nom
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'nombre_classes': 0,
            }
        
        if est_primaire:
            # LOGIQUE PRIMAIRE
            # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
            eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
            
            # Utiliser la période sélectionnée
            periode_active = periode_selectionnee
            
            # Récupérer toutes les matières du primaire de l'établissement
            # (peu importe si un professeur est affecté ou non)
            matieres = Matiere.objects.filter(
                etablissement=etablissement,
                niveau__in=['primaire', 'tous']
            ).order_by('nom')
            
            # Préparer les données pour chaque élève avec toutes les matières
            eleves_data = []
            for eleve in eleves:
                eleve_info = {
                    'eleve': eleve,
                    'matieres': {},
                    'nombre_matieres_avec_moyenne': 0,
                }
                
                # Pour chaque matière, récupérer la moyenne si elle existe
                for matiere in matieres:
                    moyenne_obj = None
                    if periode_active:
                        moyenne_qs = MoyenneMatierePrimaire.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            periode_scolaire=periode_active
                        )
                        # Filtrer par année scolaire active si disponible
                        if annee_scolaire_active:
                            moyenne_qs = moyenne_qs.filter(annee_scolaire=annee_scolaire_active)
                        moyenne_obj = moyenne_qs.first()
                    
                    # CONDITION PRIMAIRE : Le champ soumis est directement sur MoyenneMatierePrimaire
                    moyenne_soumise = moyenne_obj and moyenne_obj.soumis
                    
                    # CONDITION : Afficher la moyenne SEULEMENT si elle est soumise
                    eleve_info['matieres'][matiere.nom] = {
                        'moyenne': moyenne_obj.moyenne if moyenne_soumise else None,
                        'nombre_notes': moyenne_obj.nombre_notes if moyenne_obj else 0,
                        'releve_soumis': moyenne_soumise,
                    }
                    
                    if moyenne_obj and moyenne_obj.moyenne and moyenne_soumise:
                        eleve_info['nombre_matieres_avec_moyenne'] += 1
                
                eleves_data.append(eleve_info)
            
            # Trier par nom (ordre alphabétique) pour le primaire
            eleves_data.sort(key=lambda x: (
                x['eleve'].nom.lower() if x['eleve'].nom else '',
                x['eleve'].prenom.lower() if x['eleve'].prenom else ''
            ))
            
            classe_info = {
                'classe': classe,
                'eleves_data': eleves_data,
                'matieres': [m.nom for m in matieres],
                'nombre_eleves': eleves.count(),
                'est_primaire': True,
                'periode_id': periode_active.id if periode_active else None,
            }
        else:
            # LOGIQUE COLLÈGE/LYCÉE - Utilisation du modèle Moyenne
            from ..model.moyenne_model import Moyenne
            
            # Utiliser la période sélectionnée
            periode_active = periode_selectionnee
            
            # Récupérer TOUTES les matières de l'établissement pour collège/lycée
            toutes_matieres = Matiere.objects.filter(
                etablissement=etablissement,
                niveau__in=['college', 'lycee', 'tous'],
                actif=True
            ).order_by('nom')
            
            # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
            eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
            
            # Préparer les données pour chaque élève
            eleves_data = []
            for eleve in eleves:
                eleve_info = {
                    'eleve': eleve,
                    'matieres_moyennes': {},
                }
                
                # Pour chaque matière, récupérer la moyenne si elle existe
                for matiere in toutes_matieres:
                    moyenne_obj = None
                    if periode_active:
                        moyenne_qs = Moyenne.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            periode=str(periode_active.id),
                            actif=True
                        )
                        # Filtrer par année scolaire active si disponible
                        if annee_scolaire_active:
                            moyenne_qs = moyenne_qs.filter(annee_scolaire=annee_scolaire_active)
                        moyenne_obj = moyenne_qs.first()
                    
                    # Afficher la moyenne SEULEMENT si elle est soumise
                    moyenne_soumise = moyenne_obj and moyenne_obj.soumis
                    moyenne_value = moyenne_obj.moyenne if moyenne_soumise and moyenne_obj.moyenne else None
                    
                    eleve_info['matieres_moyennes'][matiere.nom] = {
                        'moyenne': moyenne_value,
                        'soumis': moyenne_soumise,
                    }
                
                eleves_data.append(eleve_info)
            
            # Calculer une moyenne temporaire pour le tri (basée sur les moyennes disponibles)
            for eleve_info in eleves_data:
                moyennes_valides = [
                    data['moyenne'] for data in eleve_info['matieres_moyennes'].values()
                    if data['moyenne'] is not None
                ]
                eleve_info['moyenne_tri'] = (
                    round(sum(moyennes_valides) / len(moyennes_valides), 2)
                    if moyennes_valides else None
                )
            
            # Trier d'abord par nom (ordre alphabétique), puis par moyenne décroissante (None en dernier)
            eleves_data.sort(key=lambda x: (
                x['eleve'].nom.lower() if x['eleve'].nom else '',
                x['eleve'].prenom.lower() if x['eleve'].prenom else '',
                x['moyenne_tri'] is None,
                -x['moyenne_tri'] if x['moyenne_tri'] is not None else 0
            ))
            
            classe_info = {
                'classe': classe,
                'eleves_data': eleves_data,
                'matieres': list(toutes_matieres),
                'nombre_eleves': eleves.count(),
                'est_primaire': False,
                'periode_id': periode_active.id if periode_active else None,
            }
        
        classes_grouped[categorie]['classes'].append(classe_info)
        classes_grouped[categorie]['total_eleves'] += classe_info['nombre_eleves']
        classes_grouped[categorie]['nombre_classes'] += 1
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': classes_grouped,
        'est_primaire': est_primaire,
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/notes_et_resultats.html', context)


@login_required
@login_required
@require_permission('notes_justifications_voir')
def justifications_notes_directeur(request):
    """
    Liste et traitement des demandes de justification de notes transmises par les enseignants.
    """
    result = _get_user_etablissement(request, 'notes_justifications_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.classe_model import Classe
    from ..utils.session_utils import get_session_active
    from django.db import transaction
    from django.shortcuts import get_object_or_404
    from django.utils import timezone

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de consulter les justifications de notes.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')

    classe_id = request.GET.get('classe')
    statut_filtre = request.GET.get('statut')
    periode_id = request.GET.get('periode')

    # Récupérer les périodes scolaires
    from ..model.periode_model import PeriodeScolaire
    periodes_queryset = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_queryset.order_by('date_debut')
    
    # Sélectionner la période (GET paramètre ou période active par défaut)
    periode_active = None
    if periodes.exists():
        if periode_id:
            try:
                periode_active = periodes.get(id=periode_id)
            except PeriodeScolaire.DoesNotExist:
                pass
        if not periode_active:
            periode_active = periodes.filter(est_active=True).first() or periodes.first()

    classes = Classe.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('niveau', 'nom')

    # Filtrer les justifications par année scolaire active
    justifications_queryset = JustificationNote.objects.filter(
        etablissement=etablissement
    )
    if annee_scolaire_active:
        justifications_queryset = justifications_queryset.filter(annee_scolaire=annee_scolaire_active)
    
    justifications_queryset = justifications_queryset.select_related(
        'classe',
        'eleve',
        'matiere',
        'professeur',
        'evaluation',
        'evaluation_primaire',
        'note_examen',
        'note_examen__session_examen'
    ).order_by('-date_creation')

    if classe_id:
        justifications_queryset = justifications_queryset.filter(classe_id=classe_id)

    # Filtrer par période
    if periode_active:
        from ..model.session_examen_model import SessionExamen
        from django.db.models import Q
        # Filtrer les justifications liées à une évaluation de la période
        # ou à une note d'examen d'une session de cette période
        session_ids_periode = list(SessionExamen.objects.filter(
            periode=periode_active,
            actif=True
        ).values_list('id', flat=True))
        
        # Combiner les trois types de justifications : évaluations secondaires, primaires et examens
        q_objects = Q()
        # Justifications avec évaluation secondaire
        q_objects |= Q(evaluation__periode_scolaire=periode_active)
        # Justifications avec évaluation primaire
        q_objects |= Q(evaluation_primaire__periode_scolaire=periode_active)
        # Justifications avec note d'examen liée à une session de cette période
        if session_ids_periode:
            q_objects |= Q(note_examen__session_examen_id__in=session_ids_periode)
        
        justifications_queryset = justifications_queryset.filter(q_objects)

    # Filtrer uniquement les justifications en attente pour la page principale
    justifications_queryset = justifications_queryset.filter(statut=JustificationNote.STATUT_EN_ATTENTE)

    if request.method == 'POST':
        action = request.POST.get('action')
        justification_id = request.POST.get('justification_id')
        commentaire = (request.POST.get('commentaire') or '').strip()

        if not justification_id:
            messages.error(request, "La justification à traiter est introuvable.")
            return redirect(request.get_full_path())

        with transaction.atomic():
            justification = get_object_or_404(
                JustificationNote,
                id=justification_id,
                etablissement=etablissement,
            )

            if justification.statut != JustificationNote.STATUT_EN_ATTENTE:
                messages.warning(request, "Cette justification a déjà été traitée.")
                return redirect(request.get_full_path())

            if action == 'valider':
                note_obj = justification.note or justification.note_primaire or justification.note_examen

                if not note_obj:
                    messages.error(request, "Impossible de mettre à jour la note ciblée.")
                    return redirect(request.get_full_path())

                bareme = None
                if justification.note and justification.evaluation:
                    bareme = justification.evaluation.bareme
                elif justification.note_primaire and justification.evaluation_primaire:
                    bareme = justification.evaluation_primaire.bareme
                elif justification.note_examen:
                    bareme = justification.note_examen.bareme

                if bareme is not None and justification.nouvelle_note > bareme:
                    messages.error(request, f"La note proposée dépasse le barème ({bareme}).")
                    return redirect(request.get_full_path())

                note_obj.note = justification.nouvelle_note
                if hasattr(note_obj, 'absent'):
                    note_obj.absent = False
                note_obj.save()

                justification.statut = JustificationNote.STATUT_VALIDEE
                justification.commentaire_direction = commentaire
                justification.valide_par = etablissement
                justification.date_validation = timezone.now()
                justification.save()

                # Recalcul automatique des moyennes (Primaire)
                if justification.note_primaire and justification.evaluation_primaire:
                    try:
                        matiere = justification.evaluation_primaire.matiere
                        periode = justification.evaluation_primaire.periode_scolaire

                        if matiere and periode:
                            moyenne_obj, _ = MoyenneMatierePrimaire.objects.get_or_create(
                                eleve=justification.eleve,
                                matiere=matiere,
                                periode_scolaire=periode,
                                defaults={
                                    'classe': justification.classe,
                                    'mode_calcul': 'toutes',
                                    'ponderation': '50_50',
                                    'evaluations_utilisees': [],
                                    'nombre_notes': 0,
                                }
                            )

                            mode_calcul = moyenne_obj.mode_calcul or 'toutes'
                            ponderation = moyenne_obj.ponderation or '50_50'
                            evaluations_selectionnees = moyenne_obj.evaluations_utilisees or []

                            moyenne_recalc, evaluations_effectives = calculer_moyenne_avec_mode(
                                justification.eleve,
                                matiere,
                                periode,
                                mode_calcul,
                                ponderation,
                                evaluations_selectionnees,
                            )

                            evaluations_finales = evaluations_effectives or evaluations_selectionnees
                            if moyenne_recalc is not None:
                                moyenne_obj.moyenne = moyenne_recalc
                                moyenne_obj.appreciation = get_appreciation_moyenne(moyenne_recalc)
                            moyenne_obj.mode_calcul = mode_calcul
                            moyenne_obj.ponderation = ponderation
                            moyenne_obj.evaluations_utilisees = evaluations_finales
                            moyenne_obj.nombre_notes = len(evaluations_finales)
                            if justification.classe:
                                moyenne_obj.classe = justification.classe
                            moyenne_obj.save()
                    except Exception as exc:
                        logger.exception("Recalcul moyenne primaire après justification impossible: %s", exc)
                        messages.warning(
                            request,
                            "La note est mise à jour mais la moyenne n'a pas pu être recalculée automatiquement.",
                        )

                try:
                    matiere_nom = getattr(justification.matiere, "nom", "Matière")
                    evaluation_nom = None
                    if justification.evaluation:
                        evaluation_nom = getattr(justification.evaluation, "titre", None)
                    elif justification.evaluation_primaire:
                        evaluation_nom = getattr(justification.evaluation_primaire, "titre", None)
                    elif justification.note_examen and justification.note_examen.session_examen:
                        evaluation_nom = f"Examen: {justification.note_examen.session_examen.nom_examen}"

                    EleveNotificationService.notify_note_justifiee(
                        justification.eleve,
                        matiere_nom=matiere_nom,
                        nouvelle_note=justification.nouvelle_note,
                        bareme=bareme,
                        evaluation_nom=evaluation_nom,
                        source=justification,
                    )
                    ParentNotificationService.notify_note_justifiee(
                        justification.eleve,
                        matiere_nom=matiere_nom,
                        nouvelle_note=justification.nouvelle_note,
                        bareme=bareme,
                        evaluation_nom=evaluation_nom,
                        source=justification,
                    )
                except Exception as notification_error:
                    logger.error(
                        "Erreur lors de l'envoi des notifications suite à la justification de note: %s",
                        notification_error,
                        exc_info=True,
                    )

                messages.success(
                    request,
                    f"La note de {justification.eleve.nom_complet} a été mise à jour."
                )
            elif action == 'rejeter':
                justification.statut = JustificationNote.STATUT_REFUSEE
                justification.commentaire_direction = commentaire
                justification.valide_par = etablissement
                justification.date_validation = timezone.now()
                justification.save()

                messages.info(
                    request,
                    "La demande de justification a été refusée."
                )
            else:
                messages.error(request, "Action inconnue.")

        # Rediriger vers la page principale après traitement
        redirect_url = reverse('directeur:justifications_notes')
        params = []
        if periode_active:
            params.append(f"periode={periode_active.id}")
        if params:
            redirect_url = f"{redirect_url}?{'&'.join(params)}"
        return redirect(redirect_url)

    # Grouper les justifications par classe
    justifications_par_classe = {}
    for justification in justifications_queryset:
        classe_id = justification.classe.id
        if classe_id not in justifications_par_classe:
            justifications_par_classe[classe_id] = {
                'classe': justification.classe,
                'justifications': [],
                'count': 0
            }
        justifications_par_classe[classe_id]['justifications'].append(justification)
        justifications_par_classe[classe_id]['count'] += 1

    # Trier les classes par nom
    classes_avec_justifications = sorted(
        justifications_par_classe.values(),
        key=lambda x: (x['classe'].niveau, x['classe'].nom)
    )

    # Sélectionner la première classe par défaut si aucune n'est sélectionnée
    classe_selectionnee_obj = None
    justifications_classe_selectionnee = []
    if classe_id:
        try:
            classe_selectionnee_obj = Classe.objects.get(id=classe_id, etablissement=etablissement)
            if classe_id in justifications_par_classe:
                justifications_classe_selectionnee = justifications_par_classe[classe_id]['justifications']
        except Classe.DoesNotExist:
            pass
    elif classes_avec_justifications:
        classe_selectionnee_obj = classes_avec_justifications[0]['classe']
        justifications_classe_selectionnee = classes_avec_justifications[0]['justifications']

    total_en_attente = justifications_queryset.count()

    context = {
        'etablissement': etablissement,
        'classes_avec_justifications': classes_avec_justifications,
        'classe_selectionnee': classe_selectionnee_obj,
        'justifications_classe_selectionnee': justifications_classe_selectionnee,
        'total_en_attente': total_en_attente,
        'annee_scolaire_active': annee_scolaire_active,
        'periodes': periodes,
        'periode_active': periode_active,
        'is_directeur': is_directeur,
        'is_personnel_administratif': not is_directeur,
        'personnel': personnel,
    }

    return render(request, 'school_admin/directeur/justifications_notes.html', context)


@login_required
@require_permission('notes_justifications_voir')
def justifications_notes_classe_directeur(request, classe_id):
    """
    Vue pour consulter toutes les justifications d'une classe (en attente, validées, refusées).
    Permet de réaccepter des demandes refusées.
    """
    result = _get_user_etablissement(request, 'notes_justifications_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.classe_model import Classe
    from django.db import transaction
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from django.urls import reverse

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')

    periode_id = request.GET.get('periode')
    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)

    # Récupérer les périodes scolaires
    from ..model.periode_model import PeriodeScolaire
    periodes_queryset = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    )
    if annee_scolaire_active:
        periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = periodes_queryset.order_by('date_debut')
    
    # Sélectionner la période
    periode_active = None
    if periodes.exists():
        if periode_id:
            try:
                periode_active = periodes.get(id=periode_id)
            except PeriodeScolaire.DoesNotExist:
                pass
        if not periode_active:
            periode_active = periodes.filter(est_active=True).first() or periodes.first()

    # Récupérer toutes les justifications de cette classe
    justifications_queryset = JustificationNote.objects.filter(
        etablissement=etablissement,
        classe=classe
    )
    if annee_scolaire_active:
        justifications_queryset = justifications_queryset.filter(annee_scolaire=annee_scolaire_active)
    
    justifications_queryset = justifications_queryset.select_related(
        'classe',
        'eleve',
        'matiere',
        'professeur',
        'evaluation',
        'evaluation_primaire',
        'note_examen',
        'note_examen__session_examen'
    ).order_by('-date_creation')

    # Filtrer par période
    if periode_active:
        from ..model.session_examen_model import SessionExamen
        from django.db.models import Q
        session_ids_periode = list(SessionExamen.objects.filter(
            periode=periode_active,
            actif=True
        ).values_list('id', flat=True))
        
        q_objects = Q()
        q_objects |= Q(evaluation__periode_scolaire=periode_active)
        q_objects |= Q(evaluation_primaire__periode_scolaire=periode_active)
        if session_ids_periode:
            q_objects |= Q(note_examen__session_examen_id__in=session_ids_periode)
        
        justifications_queryset = justifications_queryset.filter(q_objects)

    if request.method == 'POST':
        action = request.POST.get('action')
        justification_id = request.POST.get('justification_id')
        commentaire = (request.POST.get('commentaire') or '').strip()

        if not justification_id:
            messages.error(request, "La justification à traiter est introuvable.")
            return redirect(request.get_full_path())

        with transaction.atomic():
            justification = get_object_or_404(
                JustificationNote,
                id=justification_id,
                etablissement=etablissement,
                classe=classe,
            )

            if action == 'valider':
                # Permettre de valider même si déjà refusée (réaccepter)
                if justification.statut == JustificationNote.STATUT_VALIDEE:
                    messages.warning(request, "Cette justification a déjà été validée.")
                    return redirect(request.get_full_path())

                note_obj = justification.note or justification.note_primaire or justification.note_examen

                if not note_obj:
                    messages.error(request, "Impossible de mettre à jour la note ciblée.")
                    return redirect(request.get_full_path())

                bareme = None
                if justification.note and justification.evaluation:
                    bareme = justification.evaluation.bareme
                elif justification.note_primaire and justification.evaluation_primaire:
                    bareme = justification.evaluation_primaire.bareme
                elif justification.note_examen:
                    bareme = justification.note_examen.bareme

                if bareme is not None and justification.nouvelle_note > bareme:
                    messages.error(request, f"La note proposée dépasse le barème ({bareme}).")
                    return redirect(request.get_full_path())

                note_obj.note = justification.nouvelle_note
                if hasattr(note_obj, 'absent'):
                    note_obj.absent = False
                note_obj.save()

                justification.statut = JustificationNote.STATUT_VALIDEE
                justification.commentaire_direction = commentaire
                justification.valide_par = etablissement
                justification.date_validation = timezone.now()
                justification.save()

                # Recalcul automatique des moyennes (Primaire)
                if justification.note_primaire and justification.evaluation_primaire:
                    try:
                        matiere = justification.evaluation_primaire.matiere
                        periode = justification.evaluation_primaire.periode_scolaire

                        if matiere and periode:
                            moyenne_obj, _ = MoyenneMatierePrimaire.objects.get_or_create(
                                eleve=justification.eleve,
                                matiere=matiere,
                                periode_scolaire=periode,
                                defaults={
                                    'classe': justification.classe,
                                    'mode_calcul': 'toutes',
                                    'ponderation': '50_50',
                                    'evaluations_utilisees': [],
                                    'nombre_notes': 0,
                                }
                            )

                            mode_calcul = moyenne_obj.mode_calcul or 'toutes'
                            ponderation = moyenne_obj.ponderation or '50_50'
                            evaluations_selectionnees = moyenne_obj.evaluations_utilisees or []

                            moyenne_recalc, evaluations_effectives = calculer_moyenne_avec_mode(
                                justification.eleve,
                                matiere,
                                periode,
                                mode_calcul,
                                ponderation,
                                evaluations_selectionnees,
                            )

                            evaluations_finales = evaluations_effectives or evaluations_selectionnees
                            if moyenne_recalc is not None:
                                moyenne_obj.moyenne = moyenne_recalc
                                moyenne_obj.appreciation = get_appreciation_moyenne(moyenne_recalc)
                            moyenne_obj.mode_calcul = mode_calcul
                            moyenne_obj.ponderation = ponderation
                            moyenne_obj.evaluations_utilisees = evaluations_finales
                            moyenne_obj.nombre_notes = len(evaluations_finales)
                            if justification.classe:
                                moyenne_obj.classe = justification.classe
                            moyenne_obj.save()
                    except Exception as exc:
                        logger.exception("Recalcul moyenne primaire après justification impossible: %s", exc)
                        messages.warning(
                            request,
                            "La note est mise à jour mais la moyenne n'a pas pu être recalculée automatiquement.",
                        )

                try:
                    matiere_nom = getattr(justification.matiere, "nom", "Matière")
                    evaluation_nom = None
                    if justification.evaluation:
                        evaluation_nom = getattr(justification.evaluation, "titre", None)
                    elif justification.evaluation_primaire:
                        evaluation_nom = getattr(justification.evaluation_primaire, "titre", None)
                    elif justification.note_examen and justification.note_examen.session_examen:
                        evaluation_nom = f"Examen: {justification.note_examen.session_examen.nom_examen}"

                    EleveNotificationService.notify_note_justifiee(
                        justification.eleve,
                        matiere_nom=matiere_nom,
                        nouvelle_note=justification.nouvelle_note,
                        bareme=bareme,
                        evaluation_nom=evaluation_nom,
                        source=justification,
                    )
                    ParentNotificationService.notify_note_justifiee(
                        justification.eleve,
                        matiere_nom=matiere_nom,
                        nouvelle_note=justification.nouvelle_note,
                        bareme=bareme,
                        evaluation_nom=evaluation_nom,
                        source=justification,
                    )
                except Exception as notification_error:
                    logger.error(
                        "Erreur lors de l'envoi des notifications suite à la justification de note: %s",
                        notification_error,
                        exc_info=True,
                    )

                messages.success(
                    request,
                    f"La note de {justification.eleve.nom_complet} a été mise à jour."
                )
            elif action == 'rejeter':
                if justification.statut == JustificationNote.STATUT_REFUSEE:
                    messages.warning(request, "Cette justification a déjà été refusée.")
                    return redirect(request.get_full_path())
                
                justification.statut = JustificationNote.STATUT_REFUSEE
                justification.commentaire_direction = commentaire
                justification.valide_par = etablissement
                justification.date_validation = timezone.now()
                justification.save()

                messages.info(
                    request,
                    "La demande de justification a été refusée."
                )
            else:
                messages.error(request, "Action inconnue.")

        return redirect(request.get_full_path())

    # Grouper par statut
    demandes_grouped = {
        JustificationNote.STATUT_EN_ATTENTE: [],
        JustificationNote.STATUT_VALIDEE: [],
        JustificationNote.STATUT_REFUSEE: [],
    }

    for justification in justifications_queryset:
        demandes_grouped[justification.statut].append(justification)

    stats = {
        'en_attente': len(demandes_grouped[JustificationNote.STATUT_EN_ATTENTE]),
        'validees': len(demandes_grouped[JustificationNote.STATUT_VALIDEE]),
        'refusees': len(demandes_grouped[JustificationNote.STATUT_REFUSEE]),
    }

    context = {
        'etablissement': etablissement,
        'classe': classe,
        'demandes_grouped': demandes_grouped,
        'stats': stats,
        'annee_scolaire_active': annee_scolaire_active,
        'periodes': periodes,
        'periode_active': periode_active,
        'is_directeur': is_directeur,
        'is_personnel_administratif': not is_directeur,
        'personnel': personnel,
    }

    return render(request, 'school_admin/directeur/justifications_notes_classe.html', context)


@login_required
@login_required
@require_permission('bulletins_voir')
def bulletins_notes(request):
    """Synthèse des bulletins par classe avec regroupement par niveau."""
    result = _get_user_etablissement(request, 'bulletins_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from collections import OrderedDict
    import re
    from django.db.models import Max
    from ..utils.session_utils import get_session_active

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de consulter les bulletins.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')

    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.moyenne_model import Moyenne
    from ..model.note_primaire_model import MoyenneMatierePrimaire

    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    periodes_queryset = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True)
    if annee_scolaire_active:
        periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = list(periodes_queryset.order_by('date_debut'))

    periode_param = request.GET.get('periode')
    periode_active = None
    if periodes:
        for periode in periodes:
            if str(periode.id) == periode_param:
                periode_active = periode
                break
        if not periode_active:
            periode_active = periodes[0]

    periodes_nav = [
        {
            'id': str(periode.id),
            'nom': periode.nom_periode,
            'type': periode.type_periode,
            'annee': periode.annee_scolaire,
            'est_active': periode_active and periode.id == periode_active.id,
            'statut': periode.statut_periode,
        }
        for periode in periodes
    ]

    classes_grouped = OrderedDict()
    total_eleves_global = 0
    total_eleves_cibles = 0
    total_eleves_avec_bulletins = 0
    total_eleves_publies = 0
    classes_terminees = 0

    periode_choices_map = dict(Moyenne.PERIODE_CHOICES)

    for classe in classes:
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
        categorie = match.group(1) if match else classe.nom

        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'nombre_classes': 0,
            }

        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        eleves_classe_qs = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        nombre_eleves_classe = eleves_classe_qs.count()

        bulletins_info = {
            'eleves_total': nombre_eleves_classe,
            'eleves_avec_bulletin': 0,
            'eleves_publies': 0,
            'progression': 0,
            'periodes': [],
            'derniere_soumission': None,
            'nb_matieres': 0,
            'nb_moyennes_enregistrees': 0,
            'eleves': [],
            'publication_complete': False,
        }

        eleves_soumis_ids = set()

        if classe.niveau in ['primaire', 'maternelle'] or etablissement.type_etablissement in ['primaire', 'primary']:
            if periode_active:
                moyennes_qs = MoyenneMatierePrimaire.objects.filter(
                    classe=classe, 
                    periode_scolaire=periode_active,
                    annee_scolaire=annee_scolaire_active
                )
            else:
                moyennes_qs = MoyenneMatierePrimaire.objects.none()
            bulletins_info['nb_moyennes_enregistrees'] = moyennes_qs.count()
            bulletins_info['nb_matieres'] = moyennes_qs.values('matiere_id').distinct().count()

            eleves_soumis = moyennes_qs.filter(soumis=True).values('eleve_id').distinct().count()
            eleves_soumis_ids = set(moyennes_qs.filter(soumis=True).values_list('eleve_id', flat=True))
            bulletins_info['eleves_avec_bulletin'] = eleves_soumis
            bulletins_info['progression'] = round((eleves_soumis / nombre_eleves_classe) * 100, 1) if nombre_eleves_classe else 0
            bulletins_info['derniere_soumission'] = moyennes_qs.filter(soumis=True).aggregate(Max('date_soumission'))['date_soumission__max']

            if periode_active:
                soumis_periode = eleves_soumis
                bulletins_info['periodes'].append({
                    'id': periode_active.id,
                    'nom': periode_active.nom_periode,
                    'type': periode_active.type_periode,
                    'statut': periode_active.statut_periode,
                    'total_eleves': nombre_eleves_classe,
                    'eleves_avec_bulletin': soumis_periode,
                    'progression': bulletins_info['progression'],
                    'derniere_soumission': bulletins_info['derniere_soumission'],
                })
        else:
            if periode_active:
                periode_filters = {str(periode_active.id), periode_active.nom_periode}
                periode_slug = ''.join(ch for ch in periode_active.nom_periode.lower() if ch.isalnum())
                periode_filters.add(periode_slug)
                moyennes_qs = Moyenne.objects.filter(
                    classe=classe, 
                    actif=True, 
                    periode__in=list(periode_filters),
                    annee_scolaire=annee_scolaire_active
                )
            else:
                moyennes_qs = Moyenne.objects.none()
            bulletins_info['nb_moyennes_enregistrees'] = moyennes_qs.count()
            bulletins_info['nb_matieres'] = moyennes_qs.values('matiere_id').distinct().count()

            eleves_soumis = moyennes_qs.filter(soumis=True).values('eleve_id').distinct().count()
            eleves_soumis_ids = set(moyennes_qs.filter(soumis=True).values_list('eleve_id', flat=True))
            bulletins_info['eleves_avec_bulletin'] = eleves_soumis
            bulletins_info['progression'] = round((eleves_soumis / nombre_eleves_classe) * 100, 1) if nombre_eleves_classe else 0
            bulletins_info['derniere_soumission'] = moyennes_qs.filter(soumis=True).aggregate(Max('date_calcul'))['date_calcul__max']

            if periode_active:
                bulletins_info['periodes'].append({
                    'id': str(periode_active.id),
                    'nom': periode_active.nom_periode,
                    'type': periode_active.type_periode,
                    'statut': periode_active.statut_periode,
                    'total_eleves': nombre_eleves_classe,
                    'eleves_avec_bulletin': eleves_soumis,
                    'progression': bulletins_info['progression'],
                    'derniere_soumission': bulletins_info['derniere_soumission'],
                })

        # Vérifier si les moyennes ont été calculées pour cette classe
        from ..model.moyenne_periode_model import MoyennePeriode
        moyennes_calculees = False
        moyennes_generales_map = {}
        
        if periode_active:
            moyennes_generales_qs = MoyennePeriode.objects.filter(
                etablissement=etablissement,
                periode=periode_active,
                est_moyenne_generale=True,
                eleve__classe=classe,
                annee_scolaire=annee_scolaire_active
            ).select_related('eleve')
            
            if moyennes_generales_qs.exists():
                moyennes_calculees = True
                for mp in moyennes_generales_qs:
                    moyennes_generales_map[mp.eleve_id] = {
                        'moyenne': float(mp.moyenne_generale) if mp.moyenne_generale is not None else None,
                        'rang': mp.rang,
                        'publie': mp.est_publie,
                        'date_publication': mp.date_publication,
                    'afficher_bulletin': mp.afficher_bulletin,
                    }
        
        bulletins_info['moyennes_calculees'] = moyennes_calculees
        
        eleves_liste = []
        for eleve in eleves_classe_qs.order_by('nom', 'prenom'):
            moyenne_info = moyennes_generales_map.get(eleve.id, {})
            # Construire l'URL du bulletin avec le paramètre période si disponible
            bulletin_url = reverse('directeur:voir_bulletin_eleve', args=[classe.id, eleve.id])
            if periode_active:
                bulletin_url = f"{bulletin_url}?periode={periode_active.id}"
            eleves_liste.append({
                'id': eleve.id,
                'nom': eleve.nom_complet,
                'matricule': eleve.matricule_eleve or eleve.numero_eleve,
                'bulletin_valide': eleve.id in eleves_soumis_ids if nombre_eleves_classe else False,
                'bulletin_url': bulletin_url,
                'moyenne_generale': moyenne_info.get('moyenne'),
                'rang': moyenne_info.get('rang'),
                'publie': moyenne_info.get('publie', False),
                'date_publication': moyenne_info.get('date_publication'),
                'afficher_bulletin': moyenne_info.get('afficher_bulletin', True),
            })
        
        # Trier les élèves par moyenne décroissante si les moyennes ont été calculées
        if moyennes_calculees:
            eleves_liste.sort(key=lambda x: (
                x['moyenne_generale'] is None,  # None en dernier
                -(x['moyenne_generale'] or 0)  # Tri décroissant
            ), reverse=False)

        # Mettre à jour les statistiques d'affichage et de publication selon la visibilité choisie
        visibles_total = sum(1 for item in eleves_liste if item['afficher_bulletin'])
        bulletins_visibles_valides = sum(
            1 for item in eleves_liste if item['bulletin_valide'] and item['afficher_bulletin']
        )
        bulletins_info['eleves_avec_bulletin'] = bulletins_visibles_valides
        bulletins_info['progression'] = round(
            (bulletins_visibles_valides / visibles_total) * 100, 1
        ) if visibles_total else 0
        total_eleves_cibles += visibles_total

        for periode_item in bulletins_info['periodes']:
            periode_item['eleves_avec_bulletin'] = bulletins_visibles_valides
            periode_item['progression'] = bulletins_info['progression']

        publies_count = sum(1 for item in eleves_liste if item['publie'] and item['afficher_bulletin'])
        bulletins_info['eleves_publies'] = publies_count
        if visibles_total > 0 and publies_count >= visibles_total:
            bulletins_info['publication_complete'] = True

        bulletins_info['eleves'] = eleves_liste

        classes_grouped[categorie]['classes'].append({
            'classe': classe,
            'bulletins': bulletins_info,
        })
        classes_grouped[categorie]['total_eleves'] += nombre_eleves_classe
        classes_grouped[categorie]['nombre_classes'] += 1

        total_eleves_global += nombre_eleves_classe
        total_eleves_avec_bulletins += bulletins_info['eleves_avec_bulletin']
        total_eleves_publies += publies_count
        if visibles_total > 0 and bulletins_info['eleves_avec_bulletin'] >= visibles_total:
            classes_terminees += 1

    progression_globale = round((total_eleves_avec_bulletins / total_eleves_cibles) * 100, 1) if total_eleves_cibles else 0

    stats_generales = {
        'total_eleves': total_eleves_global,
        'total_classes': classes.count(),
        'bulletins_publies': total_eleves_publies,
        'progression_globale': progression_globale,
        'classes_terminees': classes_terminees,
    }

    context = {
        'etablissement': etablissement,
        'classes_grouped': classes_grouped,
        'stats_generales': stats_generales,
        'periodes': periodes,
        'periodes_nav': periodes_nav,
        'periode_active': periode_active,
        'annee_scolaire_active': annee_scolaire_active,
    }

    return render(request, 'school_admin/directeur/bulletins_notes.html', context)


@login_required
def calculer_moyennes_periode(request, classe_id):
    """
    Calcule et enregistre les moyennes de période selon la pondération configurée.
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    selected_periode_id = request.GET.get('periode')
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.matiere_model import Matiere
    from ..model.moyenne_periode_model import MoyennePeriode
    from ..services.notification_tasks import schedule_bulletin_publication
    from ..model.note_examen_model import NoteExamen
    from django.db import transaction
    from ..utils.session_utils import get_session_active

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de calculer les moyennes.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    
    # Récupérer la période depuis le paramètre GET ou utiliser la première période active
    periode_queryset = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True)
    if annee_scolaire_active:
        periode_queryset = periode_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    
    periode = None
    if selected_periode_id:
        try:
            periode = periode_queryset.filter(id=int(selected_periode_id)).first()
        except (ValueError, TypeError):
            pass
    
    # Si aucune période trouvée via le paramètre, prendre la première période active
    if not periode:
        periode = periode_queryset.order_by('date_debut').first()
    
    if not periode:
        messages.error(request, "Aucune période scolaire active n'est configurée.")
        # Rediriger vers les bulletins avec le paramètre période si disponible
        redirect_url = reverse('directeur:bulletins_notes')
        if selected_periode_id:
            redirect_url = f"{redirect_url}?periode={selected_periode_id}"
        return redirect(redirect_url)

    # Récupérer la pondération configurée
    annee_scolaire = getattr(periode, 'annee_scolaire', None) or Ponderation.default_school_year()
    ponderation = Ponderation.objects.filter(
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        actif=True
    ).first()

    if not ponderation:
        messages.error(request, "Aucune pondération n'est configurée pour cette année scolaire.")
        return redirect('directeur:bulletins_notes')

    poids_classe = Decimal(str(ponderation.poids_classe)) / Decimal('100')
    poids_examen = Decimal(str(ponderation.poids_examen)) / Decimal('100')

    est_primaire = etablissement.type_etablissement == 'primary'
    standards_bundle = _get_standards_bundle(etablissement)
    verification_base_url = request.build_absolute_uri(
        reverse('school_admin:verifier_bulletin_qr')
    )
    verification_base_url = request.build_absolute_uri(
        reverse('school_admin:verifier_bulletin_qr')
    )
    
    # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
    eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    
    if not eleves.exists():
        messages.warning(request, "Cette classe ne contient aucun élève pour l'année scolaire active.")
        return redirect('directeur:bulletins_notes')

    # Récupérer les matières
    matieres = classe.matieres.filter(actif=True).order_by('nom')
    if not matieres.exists():
        matieres = Matiere.objects.filter(
            niveau__in=[classe.niveau, 'tous'],
            etablissement=etablissement,
            actif=True
        ).order_by('nom')

    if not matieres.exists():
        messages.warning(request, "Aucune matière n'est configurée pour cette classe.")
        return redirect('directeur:bulletins_notes')

    try:
        with transaction.atomic():
            eleves_moyennes_generales = []
            
            for eleve in eleves:
                matieres_moyennes = []
                total_pondere = Decimal('0')
                somme_coefficients = Decimal('0')
                
                for matiere in matieres:
                    # Récupérer la moyenne de classe
                    moyenne_classe = None
                    note_examen = None
                    
                    if est_primaire:
                        from ..model.note_primaire_model import MoyenneMatierePrimaire
                        moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            periode_scolaire=periode,
                            matiere=matiere,
                            soumis=True,
                            annee_scolaire=annee_scolaire_active
                        ).first()
                        
                        if moyenne_obj and moyenne_obj.moyenne is not None:
                            moyenne_classe = Decimal(str(moyenne_obj.moyenne))
                        
                        # Récupérer la note d'examen
                        examens = NoteExamen.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            session_examen__periode=periode,
                            actif=True,
                            annee_scolaire=annee_scolaire_active
                        )
                        
                        if examens.exists():
                            notes_exam = []
                            for exam in examens:
                                if exam.note_sur_20 is not None:
                                    notes_exam.append(Decimal(str(exam.note_sur_20)))
                                elif exam.note is not None and exam.bareme:
                                    bareme_decimal = Decimal(str(exam.bareme)) if exam.bareme else Decimal('20')
                                    if bareme_decimal > 0:
                                        note_sur_20 = (Decimal(str(exam.note)) / bareme_decimal) * Decimal('20')
                                        notes_exam.append(note_sur_20)
                            
                            if notes_exam:
                                note_examen = sum(notes_exam) / Decimal(len(notes_exam))
                    else:
                        from ..model.moyenne_model import Moyenne
                        moyenne_obj = Moyenne.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            periode=str(periode.id),
                            soumis=True,
                            actif=True,
                            annee_scolaire=annee_scolaire_active
                        ).first()
                        
                        if moyenne_obj and moyenne_obj.moyenne is not None:
                            moyenne_classe = Decimal(str(moyenne_obj.moyenne))
                        
                        # Récupérer la note d'examen
                        exam = NoteExamen.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            session_examen__periode=periode,
                            actif=True,
                            annee_scolaire=annee_scolaire_active
                        ).first()
                        
                        if exam:
                            if exam.note_sur_20 is not None:
                                note_examen = Decimal(str(exam.note_sur_20))
                            elif exam.note is not None and exam.bareme:
                                bareme_decimal = Decimal(str(exam.bareme)) if exam.bareme else Decimal('20')
                                if bareme_decimal > 0:
                                    note_examen = (Decimal(str(exam.note)) / bareme_decimal) * Decimal('20')
                    
                    # Calculer la moyenne de la matière selon la pondération
                    moyenne_matiere = None
                    if moyenne_classe is not None or note_examen is not None:
                        total = Decimal('0')
                        poids_total = Decimal('0')
                        
                        if moyenne_classe is not None:
                            total += moyenne_classe * poids_classe
                            poids_total += poids_classe
                        
                        if note_examen is not None:
                            total += note_examen * poids_examen
                            poids_total += poids_examen
                        
                        if poids_total > 0:
                            moyenne_matiere = (total / poids_total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    
                    # Récupérer le coefficient selon le type d'établissement
                    # Pour les établissements lycée, utiliser le coefficient par groupe
                    est_lycee = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
                    if est_lycee:
                        from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                        coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(matiere, classe)
                        coefficient = Decimal(str(coefficient_decimal)) if coefficient_decimal else Decimal('1')
                    else:
                        # Pour les établissements primaires, utiliser le coefficient global de la matière
                        coefficient = Decimal(str(matiere.coefficient)) if matiere.coefficient else Decimal('1')
                    
                    # Calculer l'appréciation de la matière
                    appreciation_matiere = None
                    if moyenne_matiere is not None:
                        appreciation_matiere, _, _ = _compute_matiere_appreciation(
                            moyenne_matiere,
                            standards_bundle,
                            getattr(moyenne_obj, 'appreciation', None)
                        )
                    
                    # Enregistrer ou mettre à jour la moyenne de la matière
                    if moyenne_matiere is not None:
                        moyenne_avec_coeff = moyenne_matiere * coefficient
                        MoyennePeriode.objects.update_or_create(
                            eleve=eleve,
                            etablissement=etablissement,
                            periode=periode,
                            matiere=matiere,
                            est_moyenne_generale=False,
                            defaults={
                                'moyenne_classe': float(moyenne_classe) if moyenne_classe is not None else None,
                                'note_examen': float(note_examen) if note_examen is not None else None,
                                'moyenne_matiere': float(moyenne_matiere),
                                'coefficient': float(coefficient),
                                'total_matiere': float(moyenne_matiere * coefficient),
                                'moyenne_avec_coefficient': float(moyenne_avec_coeff),
                                'appreciation_matiere': appreciation_matiere,
                                'poids_classe': ponderation.poids_classe,
                                'poids_examen': ponderation.poids_examen,
                                'annee_scolaire': annee_scolaire_active,
                            }
                        )
                        
                        matieres_moyennes.append({
                            'matiere': matiere,
                            'moyenne': moyenne_matiere,
                            'coefficient': coefficient,
                        })
                        
                        total_pondere += moyenne_matiere * coefficient
                        somme_coefficients += coefficient
                
                # Calculer la moyenne générale
                moyenne_generale = None
                if somme_coefficients > 0:
                    moyenne_generale = (total_pondere / somme_coefficients).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                
                # Calculer l'appréciation générale et la décision du conseil
                appreciation_generale, _, _, _, _ = _compute_appreciation_generale(
                    moyenne_generale,
                    standards_bundle,
                    None
                )
                decision_conseil, _, _, _, _ = _compute_decision_conseil(
                    moyenne_generale,
                    standards_bundle,
                    None
                )
                
                # Enregistrer la moyenne générale
                if moyenne_generale is not None:
                    moyenne_generale_obj, created = MoyennePeriode.objects.update_or_create(
                        eleve=eleve,
                        etablissement=etablissement,
                        periode=periode,
                        matiere=None,
                        est_moyenne_generale=True,
                        defaults={
                            'moyenne_generale': float(moyenne_generale),
                            'appreciation_generale': appreciation_generale,
                            'decision_conseil': decision_conseil,
                            'poids_classe': ponderation.poids_classe,
                            'poids_examen': ponderation.poids_examen,
                            'annee_scolaire': annee_scolaire_active,
                        }
                    )

                    # Générer les éléments de sécurité (QR code, numéro de série, signature) pour tous les types d'établissements
                    try:
                        numero_serie, signature = _ensure_bulletin_security_assets(
                            moyenne_generale_obj,
                            eleve=eleve,
                            classe=classe,
                            periode=periode,
                            etablissement=etablissement,
                            verification_url_base=verification_base_url,
                        )
                        if numero_serie and signature:
                            logger.info(f"Éléments de sécurité générés pour {eleve.nom_complet} (classe {classe.nom}, période {periode.nom_periode}): numéro série={numero_serie}")
                        else:
                            logger.warning(f"Échec de génération des éléments de sécurité pour {eleve.nom_complet} (classe {classe.nom}, période {periode.nom_periode})")
                    except Exception as e:
                        logger.error(f"Erreur lors de la génération des éléments de sécurité pour {eleve.nom_complet} (classe {classe.nom}, période {periode.nom_periode}): {str(e)}", exc_info=True)
                        # Continuer même si la génération échoue pour ne pas bloquer le calcul des moyennes
                    
                    eleves_moyennes_generales.append({
                        'eleve_id': eleve.id,
                        'moyenne': moyenne_generale,
                    })
            
            # Calculer les rangs (tri décroissant : la plus forte moyenne = rang 1)
            # None doit venir en dernier, donc on utilise is_not_None comme première clé
            # Avec -(moyenne), les plus grandes moyennes deviennent les plus petites valeurs négatives
            # reverse=False pour que les plus petites valeurs négatives (donc plus grandes moyennes) viennent en premier
            eleves_moyennes_generales.sort(key=lambda x: (x['moyenne'] is not None, -(x['moyenne'] or 0)), reverse=False)
            
            for index, item in enumerate(eleves_moyennes_generales, start=1):
                eleve_id = item['eleve_id']
                MoyennePeriode.objects.filter(
                    eleve_id=eleve_id,
                    etablissement=etablissement,
                    periode=periode,
                    est_moyenne_generale=True,
                    annee_scolaire=annee_scolaire_active
                ).update(rang=index)
                
                # Mettre à jour aussi les rangs par matière (tri décroissant : la plus forte moyenne = rang 1)
                # IMPORTANT : Comparer uniquement les élèves de la même classe
                for matiere in matieres:
                    matiere_moyennes = list(MoyennePeriode.objects.filter(
                        etablissement=etablissement,
                        periode=periode,
                        matiere=matiere,
                        est_moyenne_generale=False,
                        moyenne_matiere__isnull=False,
                        eleve__classe=classe,  # Filtrer uniquement les élèves de la même classe
                        annee_scolaire=annee_scolaire_active
                    ).select_related('eleve', 'eleve__classe'))
                    
                    # Trier par moyenne décroissante (plus forte moyenne = rang 1)
                    # reverse=False pour que les plus petites valeurs négatives (donc plus grandes moyennes) viennent en premier
                    matiere_moyennes.sort(key=lambda x: (x.moyenne_matiere is None, -(x.moyenne_matiere or 0)), reverse=False)
                    
                    for rang_matiere, moyenne_periode in enumerate(matiere_moyennes, start=1):
                        moyenne_periode.rang = rang_matiere
                        moyenne_periode.save(update_fields=['rang'])

        messages.success(request, f"✅ Les moyennes de la période ont été calculées et mises à jour avec succès pour la classe {classe.nom}. Vous pouvez recalculer autant de fois que nécessaire.")
    except Exception as e:
        logger.error(f"Erreur lors du calcul des moyennes: {str(e)}", exc_info=True)
        messages.error(request, f"❌ Erreur lors du calcul des moyennes: {str(e)}")

    redirect_url = reverse('directeur:bulletins_notes')
    params = []
    if selected_periode_id:
        params.append(f"periode={selected_periode_id}")
    # Préserver l'ID de la classe pour restaurer l'onglet actif
    classe_id_param = request.GET.get('classe_id')
    if classe_id_param:
        params.append(f"classe_id={classe_id_param}")
    if params:
        redirect_url = f"{redirect_url}?{'&'.join(params)}"
    return redirect(redirect_url)


@login_required
def calculer_moyenne_annuelle(request, classe_id):
    """
    Calcule et enregistre la moyenne annuelle pour tous les élèves d'une classe.
    La moyenne annuelle est calculée en additionnant toutes les moyennes des périodes
    et en divisant par le nombre de périodes.
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.periode_model import PeriodeScolaire
    from ..model.moyenne_periode_model import MoyennePeriode, MoyenneAnnuelle
    from django.db import transaction
    from ..utils.session_utils import get_session_active
    from decimal import Decimal, ROUND_HALF_UP

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de calculer les moyennes annuelles.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    
    # Récupérer la période depuis le paramètre GET ou utiliser la première période active
    periode_param = request.GET.get('periode')
    periode_queryset = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True)
    if annee_scolaire_active:
        periode_queryset = periode_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    
    periode_calcul = None
    if periode_param:
        try:
            periode_calcul = periode_queryset.filter(id=int(periode_param)).first()
        except (ValueError, TypeError):
            pass
    
    # Si aucune période trouvée via le paramètre, prendre la première période active
    if not periode_calcul:
        periode_calcul = periode_queryset.order_by('date_debut').first()
    
    if not periode_calcul:
        messages.error(request, "Aucune période scolaire active n'est configurée.")
        redirect_url = reverse('directeur:bulletins_notes')
        if periode_param:
            redirect_url = f"{redirect_url}?periode={periode_param}&classe_id={classe_id}"
        return redirect(redirect_url)
    
    # Récupérer tous les élèves de la classe pour l'année scolaire active
    eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    
    if not eleves.exists():
        messages.warning(request, "Cette classe ne contient aucun élève pour l'année scolaire active.")
        redirect_url = reverse('directeur:bulletins_notes')
        if periode_param:
            redirect_url = f"{redirect_url}?periode={periode_param}&classe_id={classe_id}"
        return redirect(redirect_url)
    
    # Récupérer toutes les périodes jusqu'à la période de calcul (inclusive)
    periodes_queryset = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        date_debut__lte=periode_calcul.date_debut
    )
    if annee_scolaire_active:
        periodes_queryset = periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    periodes = list(periodes_queryset.order_by('date_debut'))
    
    if not periodes:
        messages.error(request, "Aucune période trouvée pour le calcul de la moyenne annuelle.")
        redirect_url = reverse('directeur:bulletins_notes')
        if periode_param:
            redirect_url = f"{redirect_url}?periode={periode_param}&classe_id={classe_id}"
        return redirect(redirect_url)
    
    try:
        with transaction.atomic():
            moyennes_calculees = 0
            
            for eleve in eleves:
                # Récupérer toutes les moyennes générales des périodes pour cet élève
                moyennes_periodes_list = []
                for periode_item in periodes:
                    moyenne_periode_qs = MoyennePeriode.objects.filter(
                        eleve=eleve,
                        etablissement=etablissement,
                        periode=periode_item,
                        est_moyenne_generale=True
                    )
                    if annee_scolaire_active:
                        moyenne_periode_qs = moyenne_periode_qs.filter(annee_scolaire=annee_scolaire_active)
                    moyenne_periode_obj = moyenne_periode_qs.first()
                    
                    if moyenne_periode_obj and moyenne_periode_obj.moyenne_generale is not None:
                        moyennes_periodes_list.append(float(moyenne_periode_obj.moyenne_generale))
                
                # Calculer la moyenne annuelle si on a au moins une moyenne de période
                if moyennes_periodes_list:
                    somme_moyennes = sum(moyennes_periodes_list)
                    nombre_periodes = len(moyennes_periodes_list)
                    moyenne_annuelle = Decimal(str(somme_moyennes / nombre_periodes)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    
                    # Enregistrer ou mettre à jour la moyenne annuelle
                    MoyenneAnnuelle.objects.update_or_create(
                        eleve=eleve,
                        etablissement=etablissement,
                        annee_scolaire=annee_scolaire_active,
                        periode_calcul=periode_calcul,
                        defaults={
                            'moyenne_annuelle': float(moyenne_annuelle),
                            'nombre_periodes': nombre_periodes
                        }
                    )
                    moyennes_calculees += 1
            
        messages.success(
            request, 
            f"✅ Les moyennes annuelles ont été calculées et enregistrées avec succès pour {moyennes_calculees} élève(s) de la classe {classe.nom}. "
            f"Calcul effectué à partir de la période {periode_calcul.nom_periode}."
        )
    except Exception as e:
        logger.error(f"Erreur lors du calcul des moyennes annuelles: {str(e)}", exc_info=True)
        messages.error(request, f"❌ Erreur lors du calcul des moyennes annuelles: {str(e)}")

    redirect_url = reverse('directeur:bulletins_notes')
    params = []
    if periode_param:
        params.append(f"periode={periode_param}")
    classe_id_param = request.GET.get('classe_id')
    if classe_id_param:
        params.append(f"classe_id={classe_id_param}")
    if params:
        redirect_url = f"{redirect_url}?{'&'.join(params)}"
    return redirect(redirect_url)


@login_required
def notifications_directeur(request):
    """
    Affiche les notifications reçues par le directeur puis les supprime après consultation.
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user

    notifications_query = NotificationDirecteur.objects.filter(etablissement=etablissement)

    notifications_non_lues = notifications_query.filter(lu=False)
    notification_ids_non_lues = list(notifications_non_lues.values_list('id', flat=True))

    if notification_ids_non_lues:
        NotificationDirecteur.objects.filter(id__in=notification_ids_non_lues).update(
            lu=True,
            statut='lu',
            date_lecture=timezone.now(),
            date_modification=timezone.now(),
        )

    notifications = list(
        notifications_query
        .order_by('-date_creation')
    )

    notifications_non_lues_count = notifications_query.filter(lu=False).count()

    context = {
        'etablissement': etablissement,
        'notifications': notifications,
        'notifications_directeur_non_lues': notifications_non_lues_count,
    }

    return render(request, 'school_admin/directeur/notifications_directeur.html', context)


def _build_bulletin_context(request, classe_id, eleve_id):
    """Prépare le contexte commun pour l'affichage ou l'impression d'un bulletin."""
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return None, redirect('school_admin:connexion_compte_user')

    etablissement = request.user

    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.matiere_model import Matiere
    from ..model.presence_model import Presence
    from ..utils.session_utils import get_session_active

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    eleve = get_object_or_404(Eleve, id=eleve_id, classe=classe, etablissement=etablissement, actif=True)

    # Récupérer la période depuis le paramètre GET ou utiliser la première période active
    periode_param = request.GET.get('periode')
    periode_queryset = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True)
    if annee_scolaire_active:
        periode_queryset = periode_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    
    periode = None
    if periode_param:
        try:
            periode = periode_queryset.filter(id=int(periode_param)).first()
        except (ValueError, TypeError):
            pass
    
    # Si aucune période trouvée via le paramètre, prendre la première période active
    if not periode:
        periode = periode_queryset.order_by('date_debut').first()
    
    if not periode:
        messages.warning(request, "Aucune période scolaire active n'est configurée.")
        return None, redirect('directeur:bulletins_notes')

    est_primaire = etablissement.type_etablissement == 'primary'
    standards_bundle = _get_standards_bundle(etablissement)
    matieres = classe.matieres.filter(actif=True).order_by('nom')

    if not matieres.exists():
        matieres = Matiere.objects.filter(
            niveau__in=[classe.niveau, 'tous'],
            etablissement=etablissement,
            actif=True
        ).order_by('nom')

    matieres_table = []
    somme_generale = Decimal('0')
    poids_generaux = Decimal('0')
    moyenne_generale = None
    bulletin_valide = False
    general_scores = []
    appreciation_generale = None
    decision_conseil = None
    rang_general = None

    classe_effectif = classe.eleves.filter(actif=True).count()

    # Vérifier si les moyennes ont été calculées et enregistrées dans MoyennePeriode
    from ..model.moyenne_periode_model import MoyennePeriode
    moyenne_periode_generale_qs = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        periode=periode,
        est_moyenne_generale=True
    )
    if annee_scolaire_active:
        moyenne_periode_generale_qs = moyenne_periode_generale_qs.filter(annee_scolaire=annee_scolaire_active)
    moyenne_periode_generale = moyenne_periode_generale_qs.first()

    bulletin_numero_serie = None
    bulletin_signature = None
    bulletin_qr_image_url = None
    bulletin_qr_data = None
    bulletin_qr_generated_at = None

    # Si les moyennes ont été calculées, utiliser les données de MoyennePeriode
    if moyenne_periode_generale:
        moyennes_periode_qs = MoyennePeriode.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            periode=periode,
            est_moyenne_generale=False
        )
        if annee_scolaire_active:
            moyennes_periode_qs = moyennes_periode_qs.filter(annee_scolaire=annee_scolaire_active)
        # Utiliser defer() pour exclure moyenne_avec_coefficient de la requête SQL
        # Cela évite l'erreur si la colonne n'existe pas encore dans la base de données
        try:
            moyennes_periode = moyennes_periode_qs.select_related('matiere').defer('moyenne_avec_coefficient').order_by('matiere__nom')
        except Exception:
            # Si defer échoue (champ non reconnu), charger normalement
            # Cela signifie que le champ n'existe pas dans le modèle ou la colonne n'existe pas
            moyennes_periode = moyennes_periode_qs.select_related('matiere').order_by('matiere__nom')

        # Vérifier si c'est un établissement lycée pour utiliser les coefficients par groupe
        est_lycee = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
        est_college_lycee = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
        
        # Récupérer les affectations des professeurs pour cette classe et cette année scolaire
        professeurs_par_matiere = {}
        if est_college_lycee:
            from ..model.affectation_model import AffectationProfesseur
            affectations = AffectationProfesseur.objects.filter(
                classe=classe,
                actif=True,
                matiere__isnull=False
            )
            if annee_scolaire_active:
                affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
            affectations = affectations.select_related('professeur', 'matiere')
            
            for affectation in affectations:
                if affectation.matiere:
                    # Extraire le premier nom et le premier prénom
                    nom_parts = affectation.professeur.nom.split() if affectation.professeur.nom else []
                    prenom_parts = affectation.professeur.prenom.split() if affectation.professeur.prenom else []
                    premier_nom = nom_parts[0] if nom_parts else affectation.professeur.nom
                    premier_prenom = prenom_parts[0] if prenom_parts else affectation.professeur.prenom
                    professeurs_par_matiere[affectation.matiere.id] = f"{premier_prenom} {premier_nom}"
        
        matieres_table = []
        has_note_examen = False
        for mp in moyennes_periode:
            if mp.matiere:
                # Pour les établissements lycée, utiliser le coefficient par groupe (actuel de la configuration)
                # Sinon, utiliser le coefficient enregistré dans MoyennePeriode
                if est_lycee:
                    from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                    coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(mp.matiere, classe)
                    coefficient_value = float(coefficient_decimal) if coefficient_decimal else (float(mp.coefficient) if mp.coefficient else 1)
                else:
                    coefficient_value = float(mp.coefficient) if mp.coefficient else 1
                
                note_examen_value = float(mp.note_examen) if mp.note_examen is not None else None
                if note_examen_value is not None:
                    has_note_examen = True
                
                moyenne_avec_coeff_value = None
                # Utiliser getattr pour éviter l'erreur si le champ n'existe pas encore dans la base
                moyenne_avec_coeff_db = getattr(mp, 'moyenne_avec_coefficient', None)
                if moyenne_avec_coeff_db is not None:
                    moyenne_avec_coeff_value = float(moyenne_avec_coeff_db)
                elif mp.moyenne_matiere is not None:
                    # Calculer si non enregistré
                    moyenne_avec_coeff_value = float(mp.moyenne_matiere) * coefficient_value
                
                professeur_nom = professeurs_par_matiere.get(mp.matiere.id) if est_college_lycee else None
                
                matieres_table.append({
                    'nom': mp.matiere.nom,
                    'moyenne_classe': float(mp.moyenne_classe) if mp.moyenne_classe is not None else None,
                    'note_examen': note_examen_value,
                    'coefficient': coefficient_value,
                    'moyenne_eleve': float(mp.moyenne_matiere) if mp.moyenne_matiere is not None else None,
                    'moyenne_avec_coefficient': moyenne_avec_coeff_value,
                    'professeur': professeur_nom,
                    'rang': mp.rang,
                    'appreciation': mp.appreciation_matiere,
                })

        moyenne_generale = float(moyenne_periode_generale.moyenne_generale) if moyenne_periode_generale.moyenne_generale is not None else None
        rang_general = moyenne_periode_generale.rang
        appreciation_generale = moyenne_periode_generale.appreciation_generale
        decision_conseil = moyenne_periode_generale.decision_conseil
        bulletin_numero_serie = moyenne_periode_generale.numero_serie
        bulletin_signature = moyenne_periode_generale.signature_numerique
        bulletin_qr_data = moyenne_periode_generale.qr_code_data
        bulletin_qr_generated_at = moyenne_periode_generale.qr_code_generated_at
        if moyenne_periode_generale.qr_code_image:
            bulletin_qr_image_url = moyenne_periode_generale.qr_code_image.url
        
        # Initialiser general_scores pour le calcul du rang si nécessaire
        general_scores = []
        if moyenne_generale is not None:
            general_scores.append((eleve.id, Decimal(str(moyenne_generale))))

        # Calculer la moyenne de classe pour chaque matière (pour affichage)
        for item in matieres_table:
            if item['moyenne_eleve'] is not None:
                # Récupérer toutes les moyennes de la classe pour cette matière
                if est_primaire:
                    from ..model.note_primaire_model import MoyenneMatierePrimaire
                    moyennes_classe_matiere_qs = MoyenneMatierePrimaire.objects.filter(
                        classe=classe,
                        periode_scolaire=periode,
                        matiere__nom=item['nom'],
                        soumis=True,
                        moyenne__isnull=False
                    )
                    if annee_scolaire_active:
                        moyennes_classe_matiere_qs = moyennes_classe_matiere_qs.filter(annee_scolaire=annee_scolaire_active)
                    moyennes_classe_matiere = moyennes_classe_matiere_qs
                else:
                    from ..model.moyenne_model import Moyenne
                    matiere_obj = Matiere.objects.filter(nom=item['nom'], etablissement=etablissement).first()
                    if matiere_obj:
                        moyennes_classe_matiere_qs = Moyenne.objects.filter(
                            classe=classe,
                            periode=str(periode.id),
                            matiere=matiere_obj,
                            soumis=True,
                            actif=True,
                            moyenne__isnull=False
                        )
                        if annee_scolaire_active:
                            moyennes_classe_matiere_qs = moyennes_classe_matiere_qs.filter(annee_scolaire=annee_scolaire_active)
                        moyennes_classe_matiere = moyennes_classe_matiere_qs
                    else:
                        moyennes_classe_matiere = []

                if moyennes_classe_matiere.exists():
                    if est_primaire:
                        moyenne_classe_calc = sum(Decimal(str(m.moyenne)) for m in moyennes_classe_matiere) / Decimal(moyennes_classe_matiere.count())
                    else:
                        moyenne_classe_calc = sum(Decimal(str(m.moyenne)) for m in moyennes_classe_matiere) / Decimal(moyennes_classe_matiere.count())
                    
                    if item['moyenne_classe'] is None:
                        item['moyenne_classe'] = float(moyenne_classe_calc.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

        bulletin_valide = True
    else:
        # Calculer à la volée comme avant
        if est_primaire:
            from ..model.note_primaire_model import MoyenneMatierePrimaire
            from ..model.note_examen_model import NoteExamen

            eleve_moyennes_qs = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                classe=classe,
                periode_scolaire=periode
            )
            if annee_scolaire_active:
                eleve_moyennes_qs = eleve_moyennes_qs.filter(annee_scolaire=annee_scolaire_active)
            eleve_moyennes = {
                item.matiere_id: item
                for item in eleve_moyennes_qs
            }

            moyennes_classe_qs = MoyenneMatierePrimaire.objects.filter(
                classe=classe,
                periode_scolaire=periode,
                soumis=True,
                moyenne__isnull=False
            )
            if annee_scolaire_active:
                moyennes_classe_qs = moyennes_classe_qs.filter(annee_scolaire=annee_scolaire_active)
            moyennes_classe = moyennes_classe_qs

            matiere_scores_map = defaultdict(list)
            overall_scores_map = defaultdict(list)
            examens_map = defaultdict(list)

            for item in moyennes_classe.iterator():
                valeur = Decimal(item.moyenne)
                matiere_scores_map[item.matiere_id].append((item.eleve_id, valeur))
                overall_scores_map[item.eleve_id].append(valeur)

            examens_qs = NoteExamen.objects.filter(
                eleve=eleve,
                classe=classe,
                session_examen__periode=periode,
                actif=True,
                matiere__in=matieres
            ).select_related('matiere')

            for exam in examens_qs:
                note_valeur = None
                if exam.note_sur_20 is not None:
                    note_valeur = Decimal(str(exam.note_sur_20))
                elif exam.note is not None and exam.bareme:
                    bareme_decimal = Decimal(str(exam.bareme)) if exam.bareme else Decimal('20')
                    if bareme_decimal > 0:
                        note_valeur = (Decimal(str(exam.note)) / bareme_decimal) * Decimal('20')

                if note_valeur is not None:
                    examens_map[exam.matiere_id].append(
                        note_valeur.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    )

            if examens_map:
                logger.debug(
                    "[Bulletin] Notes d'examen récupérées pour %s (classe %s, période %s): %s",
                    eleve.nom_complet,
                    classe.nom,
                    periode.nom_periode,
                    dict(examens_map)
                )

            has_note_examen = False
            for matiere in matieres:
                moyenne_obj = eleve_moyennes.get(matiere.id)
                soumis = bool(moyenne_obj and moyenne_obj.soumis)
                moyenne_value = None
                appreciation = None
                note_examen_value = None
                if soumis and moyenne_obj and moyenne_obj.moyenne is not None:
                    moyenne_value = Decimal(moyenne_obj.moyenne)
                    appreciation = moyenne_obj.appreciation or None
                    somme_generale += moyenne_value
                    poids_generaux += Decimal('1')

                examens_matiere = examens_map.get(matiere.id)
                if examens_matiere:
                    note_examen_value = float(
                        (sum(examens_matiere) / Decimal(len(examens_matiere))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    )
                    has_note_examen = True

                scores_classe = matiere_scores_map.get(matiere.id, [])
                moyenne_classe = None
                rang = None
                if scores_classe:
                    moyenne_classe = (sum(val for _, val in scores_classe) / Decimal(len(scores_classe))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if moyenne_value is not None:
                        sorted_scores = sorted(scores_classe, key=lambda x: (x[1], -x[0]), reverse=True)
                        for index, (eleve_score_id, _) in enumerate(sorted_scores, start=1):
                            if eleve_score_id == eleve.id:
                                rang = index
                                break

                # Récupérer le coefficient selon le type d'établissement
                est_lycee = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
                if est_lycee:
                    from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                    coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(matiere, classe)
                    coefficient_value = float(coefficient_decimal) if coefficient_decimal else 1
                else:
                    coefficient_value = float(matiere.coefficient) if matiere.coefficient is not None else 1
                
                moyenne_avec_coeff_value = None
                if moyenne_value is not None:
                    moyenne_avec_coeff_value = float(moyenne_value * Decimal(str(coefficient_value)))
                
                matieres_table.append({
                    'nom': matiere.nom,
                    'moyenne_classe': float(moyenne_classe) if moyenne_classe is not None else None,
                    'note_examen': note_examen_value,
                    'coefficient': coefficient_value,
                    'moyenne_eleve': float(moyenne_value) if moyenne_value is not None else None,
                    'moyenne_avec_coefficient': moyenne_avec_coeff_value,
                    'professeur': None,  # Pas de professeur pour primaire
                    'rang': rang,
                    'appreciation': appreciation,
                })

            if poids_generaux > 0:
                moyenne_generale = float((somme_generale / poids_generaux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

            bulletin_valide_qs = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                classe=classe,
                periode_scolaire=periode,
                soumis=True
            )
            if annee_scolaire_active:
                bulletin_valide_qs = bulletin_valide_qs.filter(annee_scolaire=annee_scolaire_active)
            bulletin_valide = bulletin_valide_qs.exists()

            general_scores = []
            for eleve_id_map, valeurs in overall_scores_map.items():
                if valeurs:
                    general_scores.append((eleve_id_map, (sum(valeurs) / Decimal(len(valeurs))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)))
        else:
            from ..model.moyenne_model import Moyenne
            from ..model.note_examen_model import NoteExamen

            eleve_moyennes = {
                item.matiere_id: item
                for item in Moyenne.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    periode=str(periode.id),
                    actif=True
                )
            }

            moyennes_classe = Moyenne.objects.filter(
                classe=classe,
                periode=str(periode.id),
                actif=True,
                soumis=True,
                moyenne__isnull=False
            ).select_related('matiere')

            matiere_scores_map = defaultdict(list)
            overall_totaux = defaultdict(lambda: {'sum': Decimal('0'), 'coeff': Decimal('0')})

            # Récupérer le coefficient selon le type d'établissement
            est_lycee = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
            
            for item in moyennes_classe.iterator():
                valeur = Decimal(item.moyenne)
                if est_lycee:
                    from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                    coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(item.matiere, classe)
                    coeff_decimal = Decimal(str(coefficient_decimal)) if coefficient_decimal else Decimal('1')
                else:
                    coeff_decimal = Decimal(str(item.matiere.coefficient or 1))
                matiere_scores_map[item.matiere_id].append((item.eleve_id, valeur))
                overall_totaux[item.eleve_id]['sum'] += valeur * coeff_decimal
                overall_totaux[item.eleve_id]['coeff'] += coeff_decimal

            examens_map = {}
            has_note_examen = False
            examens_qs = NoteExamen.objects.filter(
                eleve=eleve,
                classe=classe,
                session_examen__periode=periode,
                actif=True,
                matiere__in=matieres
            ).select_related('session_examen', 'matiere').order_by('date_saisie')
            for exam in examens_qs:
                note_val = exam.note_sur_20 if exam.note_sur_20 is not None else exam.note
                if note_val is not None:
                    examens_map[exam.matiere_id] = float(Decimal(note_val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                    has_note_examen = True

            # Récupérer les affectations des professeurs pour cette classe et cette année scolaire
            est_college_lycee = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
            professeurs_par_matiere = {}
            if est_college_lycee:
                from ..model.affectation_model import AffectationProfesseur
                affectations = AffectationProfesseur.objects.filter(
                    classe=classe,
                    actif=True,
                    matiere__in=matieres
                )
                if annee_scolaire_active:
                    affectations = affectations.filter(annee_scolaire=annee_scolaire_active)
                affectations = affectations.select_related('professeur', 'matiere')
                
                for affectation in affectations:
                    if affectation.matiere:
                        # Extraire le premier nom et le premier prénom
                        nom_parts = affectation.professeur.nom.split() if affectation.professeur.nom else []
                        prenom_parts = affectation.professeur.prenom.split() if affectation.professeur.prenom else []
                        premier_nom = nom_parts[0] if nom_parts else affectation.professeur.nom
                        premier_prenom = prenom_parts[0] if prenom_parts else affectation.professeur.prenom
                        professeurs_par_matiere[affectation.matiere.id] = f"{premier_prenom} {premier_nom}"

            for matiere in matieres:
                moyenne_obj = eleve_moyennes.get(matiere.id)
                soumis = bool(moyenne_obj and moyenne_obj.soumis)
                moyenne_value = None
                appreciation = None
                if soumis and moyenne_obj and moyenne_obj.moyenne is not None:
                    moyenne_value = Decimal(moyenne_obj.moyenne)
                    appreciation = moyenne_obj.appreciation if hasattr(moyenne_obj, 'appreciation') else None
                    if est_lycee:
                        from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                        coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(matiere, classe)
                        coeff_decimal = Decimal(str(coefficient_decimal)) if coefficient_decimal else Decimal('1')
                    else:
                        coeff_decimal = Decimal(str(matiere.coefficient or 1))
                    somme_generale += moyenne_value * coeff_decimal
                    poids_generaux += coeff_decimal

                scores_classe = matiere_scores_map.get(matiere.id, [])
                moyenne_classe = None
                rang = None
                if scores_classe:
                    moyenne_classe = (sum(val for _, val in scores_classe) / Decimal(len(scores_classe))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if moyenne_value is not None:
                        sorted_scores = sorted(scores_classe, key=lambda x: (x[1], -x[0]), reverse=True)
                        for index, (eleve_score_id, _) in enumerate(sorted_scores, start=1):
                            if eleve_score_id == eleve.id:
                                rang = index
                                break

                # Récupérer le coefficient selon le type d'établissement pour l'affichage
                if est_lycee:
                    from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                    coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(matiere, classe)
                    coefficient_display = float(coefficient_decimal) if coefficient_decimal else (float(matiere.coefficient) if matiere.coefficient is not None else 1)
                else:
                    coefficient_display = float(matiere.coefficient) if matiere.coefficient is not None else 1
                
                note_examen_value = examens_map.get(matiere.id)
                moyenne_avec_coeff_value = None
                if moyenne_value is not None:
                    moyenne_avec_coeff_value = float(moyenne_value * Decimal(str(coefficient_display)))
                
                professeur_nom = professeurs_par_matiere.get(matiere.id) if est_college_lycee else None
                
                matieres_table.append({
                    'nom': matiere.nom,
                    'moyenne_classe': float(moyenne_classe) if moyenne_classe is not None else None,
                    'note_examen': note_examen_value,
                    'coefficient': coefficient_display,
                    'moyenne_eleve': float(moyenne_value) if moyenne_value is not None else None,
                    'moyenne_avec_coefficient': moyenne_avec_coeff_value,
                    'professeur': professeur_nom,
                    'rang': rang,
                    'appreciation': appreciation,
                })

            if poids_generaux > 0:
                moyenne_generale = float((somme_generale / poids_generaux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

            bulletin_valide = Moyenne.objects.filter(
                eleve=eleve,
                classe=classe,
                periode=str(periode.id),
                soumis=True,
                actif=True
            ).exists()

            general_scores = []
            for eleve_id_map, data in overall_totaux.items():
                if data['coeff'] > 0:
                    general_scores.append((
                        eleve_id_map,
                        (data['sum'] / data['coeff']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    ))

    appreciation_generale, decision_conseil, standards_extra = _apply_standards_to_bulletin(
        matieres_table,
        moyenne_generale,
        appreciation_generale,
        decision_conseil,
        standards_bundle
    )

    soumissions = sum(1 for item in matieres_table if item['moyenne_eleve'] is not None)
    total_matieres = len(matieres_table)
    bulletin_disponible = soumissions > 0
    pourcentage_soumission = round((soumissions / total_matieres) * 100, 1) if total_matieres else 0

    # Calculer rang_general, appreciation_generale et decision_conseil seulement si pas déjà définis
    if 'rang_general' not in locals() or rang_general is None:
        rang_general = None
        if bulletin_disponible:
            general_scores_sorted = sorted(general_scores, key=lambda x: (x[1], -x[0]), reverse=True)
            for index, (eleve_ident, _) in enumerate(general_scores_sorted, start=1):
                if eleve_ident == eleve.id:
                    rang_general = index
                    break

    absences_justifiees = Presence.objects.filter(
        eleve=eleve,
        classe=classe,
        date__gte=periode.date_debut,
        date__lte=periode.date_fin,
        statut='absent_justifie'
    ).count()

    absences_non_justifiees = Presence.objects.filter(
        eleve=eleve,
        classe=classe,
        date__gte=periode.date_debut,
        date__lte=periode.date_fin,
        statut='absent'
    ).count()

    # Récupérer toutes les moyennes des périodes précédentes et de la période actuelle
    # Trier par date_debut croissante pour afficher dans l'ordre chronologique
    from ..model.moyenne_periode_model import MoyennePeriode
    
    # Récupérer toutes les périodes de l'année scolaire active (y compris la période actuelle)
    toutes_periodes_queryset = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        date_debut__lte=periode.date_debut  # Inclure la période actuelle et toutes les précédentes
    )
    if annee_scolaire_active:
        toutes_periodes_queryset = toutes_periodes_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    toutes_periodes = list(toutes_periodes_queryset.order_by('date_debut'))
    
    # Créer un dictionnaire pour stocker les dates de début pour le tri
    periode_dates = {p.id: p.date_debut for p in toutes_periodes}
    
    # Récupérer tous les élèves de la classe pour calculer les moyennes de classe et les rangs
    eleves_classe = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    
    # Récupérer les moyennes pour toutes ces périodes avec moyenne de classe et rang
    moyennes_periodes = []
    for periode_item in toutes_periodes:
        # Récupérer la moyenne de l'élève pour cette période
        moyenne_periode_qs = MoyennePeriode.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            periode=periode_item,
            est_moyenne_generale=True
        )
        if annee_scolaire_active:
            moyenne_periode_qs = moyenne_periode_qs.filter(annee_scolaire=annee_scolaire_active)
        moyenne_periode_obj = moyenne_periode_qs.first()
        
        moyenne_eleve = None
        if moyenne_periode_obj and moyenne_periode_obj.moyenne_generale is not None:
            moyenne_eleve = float(moyenne_periode_obj.moyenne_generale)
        elif periode_item.id == periode.id and moyenne_generale is not None:
            # Si c'est la période actuelle et qu'on a une moyenne calculée mais pas encore enregistrée
            moyenne_eleve = float(moyenne_generale) if moyenne_generale is not None else None
        
        # Calculer la moyenne de classe et le rang pour cette période
        moyenne_classe = None
        rang_periode = None
        
        if moyenne_eleve is not None:
            # Récupérer toutes les moyennes générales de tous les élèves de la classe pour cette période
            moyennes_classe_qs = MoyennePeriode.objects.filter(
                eleve__in=eleves_classe,
                etablissement=etablissement,
                periode=periode_item,
                est_moyenne_generale=True
            )
            if annee_scolaire_active:
                moyennes_classe_qs = moyennes_classe_qs.filter(annee_scolaire=annee_scolaire_active)
            
            # Récupérer toutes les moyennes avec les IDs des élèves
            moyennes_list = []
            for moy_obj in moyennes_classe_qs:
                if moy_obj.moyenne_generale is not None:
                    moyennes_list.append({
                        'eleve_id': moy_obj.eleve.id,
                        'moyenne': float(moy_obj.moyenne_generale)
                    })
            
            if moyennes_list:
                # Calculer la moyenne de classe
                somme_moyennes = sum(m['moyenne'] for m in moyennes_list)
                moyenne_classe = round(somme_moyennes / len(moyennes_list), 2)
                
                # Calculer le rang de l'élève (tri décroissant)
                moyennes_list.sort(key=lambda x: x['moyenne'], reverse=True)
                for index, moy_data in enumerate(moyennes_list, start=1):
                    if moy_data['eleve_id'] == eleve.id:
                        rang_periode = index
                        break
        
        # Ajouter les informations de la période
        if moyenne_eleve is not None:
            moyennes_periodes.append({
                'periode_id': periode_item.id,
                'periode_nom': periode_item.nom_periode,
                'moyenne': moyenne_eleve,
                'moyenne_classe': moyenne_classe,
                'rang': rang_periode,
                'effectif': len(eleves_classe) if eleves_classe.exists() else 0,
                'est_periode_actuelle': periode_item.id == periode.id,
                'date_debut': periode_item.date_debut
            })
    
    # Trier par date_debut pour s'assurer de l'ordre chronologique (période 1, puis 2, puis 3, etc.)
    moyennes_periodes.sort(key=lambda x: x['date_debut'])
    
    # Pour la compatibilité avec l'ancien code, garder aussi moyenne_periode_precedente
    # (la dernière période avant la période actuelle)
    moyenne_periode_precedente = None
    periode_precedente_nom = None
    if len(moyennes_periodes) > 1:
        # Prendre l'avant-dernière (la dernière avant la période actuelle)
        periode_precedente_data = moyennes_periodes[-2] if not moyennes_periodes[-1]['est_periode_actuelle'] else moyennes_periodes[-1]
        moyenne_periode_precedente = periode_precedente_data['moyenne']
        periode_precedente_nom = periode_precedente_data['periode_nom']
    elif len(moyennes_periodes) == 1 and not moyennes_periodes[0]['est_periode_actuelle']:
        moyenne_periode_precedente = moyennes_periodes[0]['moyenne']
        periode_precedente_nom = moyennes_periodes[0]['periode_nom']

    # Calculer les statistiques de la classe pour la période actuelle
    # (forte moyenne, faible moyenne, moyenne de classe)
    forte_moyenne_classe = None
    faible_moyenne_classe = None
    moyenne_classe_periode_actuelle = None
    
    # Récupérer toutes les moyennes générales de tous les élèves de la classe pour la période actuelle
    moyennes_classe_actuelle_qs = MoyennePeriode.objects.filter(
        eleve__in=eleves_classe,
        etablissement=etablissement,
        periode=periode,
        est_moyenne_generale=True
    )
    if annee_scolaire_active:
        moyennes_classe_actuelle_qs = moyennes_classe_actuelle_qs.filter(annee_scolaire=annee_scolaire_active)
    
    moyennes_classe_actuelle_list = []
    for moy_obj in moyennes_classe_actuelle_qs:
        if moy_obj.moyenne_generale is not None:
            moyennes_classe_actuelle_list.append(float(moy_obj.moyenne_generale))
    
    if moyennes_classe_actuelle_list:
        forte_moyenne_classe = max(moyennes_classe_actuelle_list)
        faible_moyenne_classe = min(moyennes_classe_actuelle_list)
        moyenne_classe_periode_actuelle = round(sum(moyennes_classe_actuelle_list) / len(moyennes_classe_actuelle_list), 2)
    
    # Récupérer le professeur principal de la classe
    professeur_principal = None
    from ..model.affectation_model import AffectationProfesseur
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    
    if est_primaire:
        affectation_principal = AffectationProfesseurPrimaire.objects.filter(
            classe=classe,
            actif=True,
            statut='principal'
        )
        if annee_scolaire_active:
            affectation_principal = affectation_principal.filter(annee_scolaire=annee_scolaire_active)
        affectation_principal = affectation_principal.first()
        if affectation_principal:
            professeur_principal = affectation_principal.professeur
    else:
        affectation_principal = AffectationProfesseur.objects.filter(
            classe=classe,
            actif=True,
            statut='principal'
        )
        if annee_scolaire_active:
            affectation_principal = affectation_principal.filter(annee_scolaire=annee_scolaire_active)
        affectation_principal = affectation_principal.first()
        if affectation_principal:
            professeur_principal = affectation_principal.professeur
    
    # Récupérer la moyenne annuelle si elle existe pour cette période
    moyenne_annuelle = None
    moyenne_annuelle_classe = None
    rang_annuel = None
    from ..model.moyenne_periode_model import MoyenneAnnuelle
    moyenne_annuelle_obj = MoyenneAnnuelle.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire_active,
        periode_calcul=periode
    ).first()
    
    if moyenne_annuelle_obj and moyenne_annuelle_obj.moyenne_annuelle is not None:
        moyenne_annuelle = float(moyenne_annuelle_obj.moyenne_annuelle)
        
        # Calculer la moyenne de classe et le rang pour la moyenne annuelle
        moyennes_annuelles_classe_qs = MoyenneAnnuelle.objects.filter(
            eleve__in=eleves_classe,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            periode_calcul=periode
        )
        
        moyennes_annuelles_list = []
        for moy_ann_obj in moyennes_annuelles_classe_qs:
            if moy_ann_obj.moyenne_annuelle is not None:
                moyennes_annuelles_list.append({
                    'eleve_id': moy_ann_obj.eleve.id,
                    'moyenne': float(moy_ann_obj.moyenne_annuelle)
                })
        
        if moyennes_annuelles_list:
            # Calculer la moyenne de classe annuelle
            somme_moyennes_annuelles = sum(m['moyenne'] for m in moyennes_annuelles_list)
            moyenne_annuelle_classe = round(somme_moyennes_annuelles / len(moyennes_annuelles_list), 2)
            
            # Calculer le rang annuel de l'élève (tri décroissant)
            moyennes_annuelles_list.sort(key=lambda x: x['moyenne'], reverse=True)
            for index, moy_data in enumerate(moyennes_annuelles_list, start=1):
                if moy_data['eleve_id'] == eleve.id:
                    rang_annuel = index
                    break

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
    
    # Calculer la décision du conseil basée sur la moyenne annuelle
    decision_conseil_finale = decision_conseil
    if moyenne_annuelle is not None and moyenne_passage_standards is not None:
        if moyenne_annuelle >= moyenne_passage_standards:
            decision_conseil_finale = "Admis en classe supérieure"
        else:
            decision_conseil_finale = f"Redouble la {classe.nom}"
    
    complement_info = {
        'moyenne_periode': moyenne_generale,
        'moyenne_periode_precedente': moyenne_periode_precedente,
        'periode_precedente_nom': periode_precedente_nom,
        'moyennes_toutes_periodes': moyennes_periodes,  # Liste de toutes les moyennes par période avec moyenne_classe et rang
        'moyenne_annuelle': moyenne_annuelle,
        'moyenne_annuelle_classe': moyenne_annuelle_classe,
        'rang_annuel': rang_annuel,
        'rang_general': rang_general,
        'effectif': classe_effectif,
        'absences_justifiees': absences_justifiees,
        'absences_non_justifiees': absences_non_justifiees,
        'appreciation_generale': appreciation_generale_periode,  # Utiliser la nouvelle logique
        'appreciation_generale_originale': appreciation_generale,  # Garder l'originale si besoin
        'moyenne_generale_validee': moyenne_generale >= 10.00 if moyenne_generale is not None else None,
        'decision_conseil': decision_conseil_finale,  # Utiliser la nouvelle logique
        'decision_conseil_originale': decision_conseil,  # Garder l'originale si besoin
        # Statistiques de la classe pour la période actuelle
        'forte_moyenne_classe': forte_moyenne_classe,
        'faible_moyenne_classe': faible_moyenne_classe,
        'moyenne_classe_periode_actuelle': moyenne_classe_periode_actuelle,
        'professeur_principal': professeur_principal,
        'moyenne_passage': moyenne_passage_standards,  # Pour la comparaison avec la moyenne annuelle
    }

    if standards_extra:
        complement_info.update({
            'appreciation_generale_standard': standards_extra['appreciation_generale_standard'],
            'appreciation_generale_source': standards_extra['appreciation_generale_source'],
            'statut_conseil_code': standards_extra['statut_conseil_code'],
            'statut_conseil_label': standards_extra['statut_conseil_label'],
        })
        if decision_conseil:
            complement_info.update({
                'decision_conseil_standard': standards_extra['decision_conseil_standard'],
                'decision_conseil_source': standards_extra['decision_conseil_source'],
            })

    # Construire les URLs avec le paramètre période si disponible
    retour_url = reverse('directeur:bulletins_notes')
    if periode:
        retour_url = f"{retour_url}?periode={periode.id}"
    
    impression_url = reverse('directeur:imprimer_bulletin_eleve', args=[classe.id, eleve.id])
    if periode:
        impression_url = f"{impression_url}?periode={periode.id}"

    # Déterminer s'il y a des notes d'examen dans matieres_table
    has_note_examen_final = any(item.get('note_examen') is not None for item in matieres_table)
    est_college_lycee_final = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleve': eleve,
        'periode': periode,
        'est_primaire': est_primaire,
        'est_college_lycee': est_college_lycee_final,
        'matieres_table': matieres_table,
        'has_note_examen': has_note_examen_final,
        'moyenne_generale': moyenne_generale,
        'bulletin_valide': bulletin_valide,
        'bulletin_disponible': bulletin_disponible,
        'soumissions': soumissions,
        'total_matieres': total_matieres,
        'pourcentage_soumission': pourcentage_soumission,
        'retour_url': retour_url,
        'releve_classe_url': reverse('directeur:imprimer_releve_notes', args=[classe.id]),
        'date_generation': timezone.now(),
        'classe_effectif': classe_effectif,
        'rang_general': rang_general,
        'complement_info': complement_info,
        'impression_url': impression_url,
        'standards_summary': standards_extra['standards_summary'] if standards_extra else None,
        'standards_applied': bool(standards_bundle),
        'bulletin_qr_image_url': bulletin_qr_image_url,
        'bulletin_qr_data': bulletin_qr_data,
        'bulletin_qr_generated_at': bulletin_qr_generated_at,
        'bulletin_signature': bulletin_signature,
        'bulletin_numero_serie': bulletin_numero_serie,
        'annee_scolaire_active': annee_scolaire_active,
    }

    logger.debug(
        "[Bulletin] Contexte matieres pour %s (classe %s): %s",
        eleve.nom_complet,
        classe.nom,
        matieres_table
    )

    return context, None


@login_required
def calculer_moyenne_eleve(request, classe_id, eleve_id):
    """Calcule et met à jour la moyenne générale d'un élève spécifique pour la période active."""
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.matiere_model import Matiere
    from ..model.moyenne_periode_model import MoyennePeriode
    from ..model.note_examen_model import NoteExamen
    from django.db import transaction
    from ..utils.session_utils import get_session_active

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    eleve = get_object_or_404(Eleve, id=eleve_id, classe=classe, etablissement=etablissement, actif=True)

    # Récupérer la période depuis le paramètre GET ou utiliser la première période active
    periode_param = request.GET.get('periode')
    periode_queryset = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True)
    if annee_scolaire_active:
        periode_queryset = periode_queryset.filter(annee_scolaire_fk=annee_scolaire_active)
    
    periode = None
    if periode_param:
        try:
            periode = periode_queryset.filter(id=int(periode_param)).first()
        except (ValueError, TypeError):
            pass
    
    # Si aucune période trouvée via le paramètre, prendre la première période active
    if not periode:
        periode = periode_queryset.order_by('date_debut').first()
    
    if not periode:
        messages.warning(request, "Aucune période scolaire active n'est configurée.")
        # Rediriger vers le bulletin avec le paramètre période si disponible
        redirect_url = reverse('directeur:voir_bulletin_eleve', args=[classe_id, eleve_id])
        if periode_param:
            redirect_url = f"{redirect_url}?periode={periode_param}"
        return redirect(redirect_url)

    # Récupérer la pondération
    ponderation = Ponderation.objects.filter(etablissement=etablissement).first()
    if not ponderation:
        messages.error(request, "La configuration de pondération n'est pas définie. Veuillez la configurer d'abord.")
        return redirect('directeur:voir_bulletin_eleve', classe_id=classe_id, eleve_id=eleve_id)

    poids_classe = Decimal(str(ponderation.poids_classe)) / Decimal('100')
    poids_examen = Decimal(str(ponderation.poids_examen)) / Decimal('100')

    est_primaire = etablissement.type_etablissement == 'primary'
    standards_bundle = _get_standards_bundle(etablissement)
    verification_base_url = request.build_absolute_uri(
        reverse('school_admin:verifier_bulletin_qr')
    )

    # Récupérer les matières
    matieres = classe.matieres.filter(actif=True).order_by('nom')
    if not matieres.exists():
        matieres = Matiere.objects.filter(
            niveau__in=[classe.niveau, 'tous'],
            etablissement=etablissement,
            actif=True
        ).order_by('nom')

    if not matieres.exists():
        messages.warning(request, "Aucune matière n'est configurée pour cette classe.")
        return redirect('directeur:voir_bulletin_eleve', classe_id=classe_id, eleve_id=eleve_id)

    try:
        with transaction.atomic():
            matieres_moyennes = []
            total_pondere = Decimal('0')
            somme_coefficients = Decimal('0')

            for matiere in matieres:
                # Récupérer la moyenne de classe
                moyenne_classe = None
                note_examen = None

                if est_primaire:
                    from ..model.note_primaire_model import MoyenneMatierePrimaire
                    moyenne_obj_qs = MoyenneMatierePrimaire.objects.filter(
                        eleve=eleve,
                        classe=classe,
                        periode_scolaire=periode,
                        matiere=matiere,
                        soumis=True
                    )
                    if annee_scolaire_active:
                        moyenne_obj_qs = moyenne_obj_qs.filter(annee_scolaire=annee_scolaire_active)
                    moyenne_obj = moyenne_obj_qs.first()

                    if moyenne_obj and moyenne_obj.moyenne is not None:
                        moyenne_classe = Decimal(str(moyenne_obj.moyenne))

                    # Récupérer la note d'examen
                    examens = NoteExamen.objects.filter(
                        eleve=eleve,
                        classe=classe,
                        matiere=matiere,
                        session_examen__periode=periode,
                        actif=True
                    )

                    if examens.exists():
                        notes_exam = []
                        for exam in examens:
                            if exam.note_sur_20 is not None:
                                notes_exam.append(Decimal(str(exam.note_sur_20)))
                            elif exam.note is not None and exam.bareme:
                                bareme_decimal = Decimal(str(exam.bareme)) if exam.bareme else Decimal('20')
                                if bareme_decimal > 0:
                                    note_sur_20 = (Decimal(str(exam.note)) / bareme_decimal) * Decimal('20')
                                    notes_exam.append(note_sur_20)

                        if notes_exam:
                            note_examen = sum(notes_exam) / Decimal(len(notes_exam))
                else:
                    from ..model.moyenne_model import Moyenne
                    moyenne_obj = Moyenne.objects.filter(
                        eleve=eleve,
                        classe=classe,
                        matiere=matiere,
                        periode=str(periode.id),
                        soumis=True,
                        actif=True
                    ).first()

                    if moyenne_obj and moyenne_obj.moyenne is not None:
                        moyenne_classe = Decimal(str(moyenne_obj.moyenne))

                    # Récupérer la note d'examen
                    exam = NoteExamen.objects.filter(
                        eleve=eleve,
                        classe=classe,
                        matiere=matiere,
                        session_examen__periode=periode,
                        actif=True
                    ).first()

                    if exam:
                        if exam.note_sur_20 is not None:
                            note_examen = Decimal(str(exam.note_sur_20))
                        elif exam.note is not None and exam.bareme:
                            bareme_decimal = Decimal(str(exam.bareme)) if exam.bareme else Decimal('20')
                            if bareme_decimal > 0:
                                note_examen = (Decimal(str(exam.note)) / bareme_decimal) * Decimal('20')

                # Calculer la moyenne de la matière selon la pondération
                moyenne_matiere = None
                if moyenne_classe is not None or note_examen is not None:
                    total = Decimal('0')
                    poids_total = Decimal('0')

                    if moyenne_classe is not None:
                        total += moyenne_classe * poids_classe
                        poids_total += poids_classe

                    if note_examen is not None:
                        total += note_examen * poids_examen
                        poids_total += poids_examen

                    if poids_total > 0:
                        moyenne_matiere = (total / poids_total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                # Récupérer le coefficient selon le type d'établissement
                # Pour les établissements lycée, utiliser le coefficient par groupe
                est_lycee = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
                if est_lycee:
                    from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
                    coefficient_decimal = CoefficientMatiereGroupe.get_coefficient_for_classe(matiere, classe)
                    coefficient = Decimal(str(coefficient_decimal)) if coefficient_decimal else Decimal('1')
                else:
                    # Pour les établissements primaires, utiliser le coefficient global de la matière
                    coefficient = Decimal(str(matiere.coefficient)) if matiere.coefficient else Decimal('1')

                # Calculer l'appréciation de la matière
                appreciation_matiere = None
                if moyenne_matiere is not None:
                    appreciation_matiere, _, _ = _compute_matiere_appreciation(
                        moyenne_matiere,
                        standards_bundle,
                        getattr(moyenne_obj, 'appreciation', None)
                    )

                # Enregistrer ou mettre à jour la moyenne de la matière
                if moyenne_matiere is not None:
                    MoyennePeriode.objects.update_or_create(
                        eleve=eleve,
                        etablissement=etablissement,
                        periode=periode,
                        matiere=matiere,
                        est_moyenne_generale=False,
                        defaults={
                            'moyenne_classe': float(moyenne_classe) if moyenne_classe is not None else None,
                            'note_examen': float(note_examen) if note_examen is not None else None,
                            'moyenne_matiere': float(moyenne_matiere),
                            'coefficient': float(coefficient),
                            'total_matiere': float(moyenne_matiere * coefficient),
                            'appreciation_matiere': appreciation_matiere,
                            'poids_classe': ponderation.poids_classe,
                            'poids_examen': ponderation.poids_examen,
                            'annee_scolaire': annee_scolaire_active,
                        }
                    )

                    matieres_moyennes.append({
                        'matiere': matiere,
                        'moyenne': moyenne_matiere,
                        'coefficient': coefficient,
                    })

                    total_pondere += moyenne_matiere * coefficient
                    somme_coefficients += coefficient

            # Calculer la moyenne générale
            moyenne_generale = None
            if somme_coefficients > 0:
                moyenne_generale = (total_pondere / somme_coefficients).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            # Calculer l'appréciation générale et la décision du conseil
            appreciation_generale, _, _, _, _ = _compute_appreciation_generale(
                moyenne_generale,
                standards_bundle,
                None
            )
            decision_conseil, _, _, _, _ = _compute_decision_conseil(
                moyenne_generale,
                standards_bundle,
                None
            )

            # Enregistrer ou mettre à jour la moyenne générale
            if moyenne_generale is not None:
                moyenne_generale_obj, _ = MoyennePeriode.objects.update_or_create(
                    eleve=eleve,
                    etablissement=etablissement,
                    periode=periode,
                    matiere=None,
                    est_moyenne_generale=True,
                    defaults={
                        'moyenne_generale': float(moyenne_generale),
                        'appreciation_generale': appreciation_generale,
                        'decision_conseil': decision_conseil,
                        'poids_classe': ponderation.poids_classe,
                        'poids_examen': ponderation.poids_examen,
                        'annee_scolaire': annee_scolaire_active,
                    }
                )

                _ensure_bulletin_security_assets(
                    moyenne_generale_obj,
                    eleve=eleve,
                    classe=classe,
                    periode=periode,
                    etablissement=etablissement,
                    verification_url_base=verification_base_url,
                )

            # Recalculer les rangs de toute la classe (car le rang dépend des autres élèves)
            # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
            eleves_classe = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
            eleves_moyennes_generales = []

            for eleve_classe in eleves_classe:
                moyenne_gen_qs = MoyennePeriode.objects.filter(
                    eleve=eleve_classe,
                    etablissement=etablissement,
                    periode=periode,
                    est_moyenne_generale=True
                )
                if annee_scolaire_active:
                    moyenne_gen_qs = moyenne_gen_qs.filter(annee_scolaire=annee_scolaire_active)
                moyenne_gen = moyenne_gen_qs.first()

                if moyenne_gen and moyenne_gen.moyenne_generale is not None:
                    eleves_moyennes_generales.append({
                        'eleve_id': eleve_classe.id,
                        'moyenne': Decimal(str(moyenne_gen.moyenne_generale)),
                    })

            # Calculer les rangs (tri décroissant : la plus forte moyenne = rang 1)
            eleves_moyennes_generales.sort(key=lambda x: (x['moyenne'] is not None, -(x['moyenne'] or 0)), reverse=False)

            for index, item in enumerate(eleves_moyennes_generales, start=1):
                eleve_id_rang = item['eleve_id']
                rang_update_qs = MoyennePeriode.objects.filter(
                    eleve_id=eleve_id_rang,
                    etablissement=etablissement,
                    periode=periode,
                    est_moyenne_generale=True
                )
                if annee_scolaire_active:
                    rang_update_qs = rang_update_qs.filter(annee_scolaire=annee_scolaire_active)
                rang_update_qs.update(rang=index)

                # Mettre à jour aussi les rangs par matière (tri décroissant : la plus forte moyenne = rang 1)
                # IMPORTANT : Comparer uniquement les élèves de la même classe
                for matiere in matieres:
                    matiere_moyennes_qs = MoyennePeriode.objects.filter(
                        etablissement=etablissement,
                        periode=periode,
                        matiere=matiere,
                        est_moyenne_generale=False,
                        moyenne_matiere__isnull=False,
                        eleve__classe=classe  # Filtrer uniquement les élèves de la même classe
                    )
                    if annee_scolaire_active:
                        matiere_moyennes_qs = matiere_moyennes_qs.filter(annee_scolaire=annee_scolaire_active)
                    matiere_moyennes = list(matiere_moyennes_qs.select_related('eleve', 'eleve__classe'))

                    # Trier par moyenne décroissante (plus forte moyenne = rang 1)
                    matiere_moyennes.sort(key=lambda x: (x.moyenne_matiere is None, -(x.moyenne_matiere or 0)), reverse=False)

                    for rang_matiere, moyenne_periode in enumerate(matiere_moyennes, start=1):
                        moyenne_periode.rang = rang_matiere
                        moyenne_periode.save(update_fields=['rang'])

        messages.success(request, f"✅ La moyenne générale de {eleve.nom_complet} a été calculée et mise à jour avec succès. Les rangs de la classe ont également été recalculés.")
    except Exception as e:
        logger.error(f"Erreur lors du calcul de la moyenne de l'élève: {str(e)}", exc_info=True)
        messages.error(request, f"❌ Erreur lors du calcul de la moyenne: {str(e)}")

    # Rediriger vers le bulletin en conservant le paramètre période
    redirect_url = reverse('directeur:voir_bulletin_eleve', args=[classe_id, eleve_id])
    periode_param = request.GET.get('periode')
    if periode_param:
        redirect_url = f"{redirect_url}?periode={periode_param}"
    return redirect(redirect_url)


@login_required
def mettre_a_jour_visibilite_bulletins(request, classe_id):
    """Met à jour la visibilité des bulletins pour une classe et une période donnée."""
    if request.method != 'POST':
        redirect_url = reverse('directeur:bulletins_notes')
        if request.GET.get('periode'):
            redirect_url = f"{redirect_url}?periode={request.GET.get('periode')}"
        return redirect(redirect_url)

    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    selected_periode_id = request.POST.get('periode') or request.GET.get('periode')

    from ..model.classe_model import Classe
    from ..model.periode_model import PeriodeScolaire
    from ..model.moyenne_periode_model import MoyennePeriode
    from ..utils.session_utils import get_session_active

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)

    periode_qs = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True).order_by('date_debut')
    if selected_periode_id:
        periode = periode_qs.filter(id=selected_periode_id).first()
    else:
        periode = periode_qs.first()

    if not periode:
        messages.error(request, "Aucune période scolaire active n'est configurée.")
        redirect_url = reverse('directeur:bulletins_notes')
        if selected_periode_id:
            redirect_url = f"{redirect_url}?periode={selected_periode_id}"
        return redirect(redirect_url)

    moyennes_generales_qs = MoyennePeriode.objects.filter(
        etablissement=etablissement,
        periode=periode,
        est_moyenne_generale=True,
        eleve__classe=classe
    )
    if annee_scolaire_active:
        moyennes_generales_qs = moyennes_generales_qs.filter(annee_scolaire=annee_scolaire_active)

    if not moyennes_generales_qs.exists():
        messages.warning(
            request,
            "Aucune moyenne générale n'a été calculée pour cette classe. Calculez d'abord les moyennes avant d'ajuster la visibilité."
        )
        redirect_url = reverse('directeur:bulletins_notes')
        if selected_periode_id:
            redirect_url = f"{redirect_url}?periode={selected_periode_id}"
        return redirect(redirect_url)

    eleves_selectionnes_raw = request.POST.getlist('eleves')
    eleves_selectionnes = set()
    for eleve_id in eleves_selectionnes_raw:
        try:
            eleves_selectionnes.add(int(eleve_id))
        except (TypeError, ValueError):
            continue

    mises_a_jour = 0
    for moyenne in moyennes_generales_qs:
        doit_afficher = moyenne.eleve_id in eleves_selectionnes
        if moyenne.afficher_bulletin != doit_afficher:
            moyenne.afficher_bulletin = doit_afficher
            moyenne.save(update_fields=['afficher_bulletin', 'updated_at'])
            mises_a_jour += 1

    if mises_a_jour:
        messages.success(
            request,
            f"La visibilité des bulletins de la classe {classe.nom} a été mise à jour pour {mises_a_jour} élève(s)."
        )
    else:
        messages.info(request, "Aucune modification de visibilité n'a été nécessaire.")

    redirect_url = reverse('directeur:bulletins_notes')
    if selected_periode_id:
        redirect_url = f"{redirect_url}?periode={selected_periode_id}"
    return redirect(redirect_url)


@login_required
def publier_bulletins_classe(request, classe_id):
    """Publie les bulletins d'une classe et notifie les élèves."""
    if request.method != 'POST':
        redirect_url = reverse('directeur:bulletins_notes')
        if request.GET.get('periode'):
            redirect_url = f"{redirect_url}?periode={request.GET.get('periode')}"
        return redirect(redirect_url)

    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    selected_periode_id = request.POST.get('periode') or request.GET.get('periode')
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.moyenne_periode_model import MoyennePeriode
    from ..utils.session_utils import get_session_active

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)

    periode_qs = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True)
    if annee_scolaire_active:
        periode_qs = periode_qs.filter(annee_scolaire_fk=annee_scolaire_active)
    periode_qs = periode_qs.order_by('date_debut')
    if selected_periode_id:
        periode = periode_qs.filter(id=selected_periode_id).first()
    else:
        periode = periode_qs.first()
    if not periode:
        messages.error(request, "Aucune période scolaire active n'est configurée.")
        redirect_url = reverse('directeur:bulletins_notes')
        if selected_periode_id:
            redirect_url = f"{redirect_url}?periode={selected_periode_id}"
        return redirect(redirect_url)

    moyennes_generales_qs = MoyennePeriode.objects.filter(
        etablissement=etablissement,
        periode=periode,
        est_moyenne_generale=True,
        eleve__classe=classe
    )
    if annee_scolaire_active:
        moyennes_generales_qs = moyennes_generales_qs.filter(annee_scolaire=annee_scolaire_active)
    moyennes_generales_qs = moyennes_generales_qs.select_related('eleve')

    if not moyennes_generales_qs.exists():
        messages.warning(request, "Aucune moyenne générale n'a été calculée pour cette classe. Veuillez d'abord calculer les moyennes avant de publier.")
        redirect_url = reverse('directeur:bulletins_notes')
        if selected_periode_id:
            redirect_url = f"{redirect_url}?periode={selected_periode_id}"
        return redirect(redirect_url)

    moyennes_generales_list = list(moyennes_generales_qs)

    if request.POST.get('visibility_form_submitted'):
        eleves_visibles_ids = set()
        for eleve_id in request.POST.getlist('eleves'):
            try:
                eleves_visibles_ids.add(int(eleve_id))
            except (TypeError, ValueError):
                continue

        for moyenne in moyennes_generales_list:
            doit_afficher = moyenne.eleve_id in eleves_visibles_ids
            if moyenne.afficher_bulletin != doit_afficher:
                moyenne.afficher_bulletin = doit_afficher
                moyenne.save(update_fields=['afficher_bulletin', 'updated_at'])

    now = timezone.now()
    moyennes_ids = [moyenne.id for moyenne in moyennes_generales_list]
    publies = MoyennePeriode.objects.filter(id__in=moyennes_ids).update(est_publie=True, date_publication=now)

    if publies > 0:
        try:
            schedule_bulletin_publication(
                classe_id=classe.id,
                periode_id=periode.id,
                etablissement_id=etablissement.id,
            )
        except Exception as scheduling_error:
            logger.error(
                "Erreur lors de la planification des notifications de publication des bulletins: %s",
                scheduling_error,
                exc_info=True,
            )
            messages.warning(
                request,
                "Les bulletins ont été publiés, mais la planification des notifications a échoué. Consultez les journaux.",
            )

    if publies > 0:
        messages.success(
            request,
            f"✅ {publies} bulletin{'s' if publies > 1 else ''} ont été publiés pour la classe {classe.nom}."
        )
        messages.info(
            request,
            "📣 Les notifications sont en cours d'envoi en arrière-plan.",
        )
    else:
        messages.info(request, "Aucun bulletin supplémentaire à publier : tous les bulletins étaient déjà marqués comme publiés.")

    redirect_url = reverse('directeur:bulletins_notes')
    if selected_periode_id:
        redirect_url = f"{redirect_url}?periode={selected_periode_id}"
    return redirect(redirect_url)


def voir_bulletin_eleve(request, classe_id, eleve_id):
    """Affiche le bulletin détaillé d'un élève pour la période active."""
    context, redirect_response = _build_bulletin_context(request, classe_id, eleve_id)
    if redirect_response:
        return redirect_response
    return render(request, 'school_admin/directeur/voir_bulletin_eleve.html', context)


@login_required
def imprimer_bulletin_eleve(request, classe_id, eleve_id):
    """Affiche la version impression du bulletin d'un élève."""
    context, redirect_response = _build_bulletin_context(request, classe_id, eleve_id)
    if redirect_response:
        return redirect_response
    return render(request, 'school_admin/directeur/imprimer_bulletin_eleve.html', context)


@login_required
def imprimer_bulletins_classe(request, classe_id):
    """Affiche tous les bulletins d'une classe pour l'impression."""
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..utils.session_utils import get_session_active

    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    
    # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
    eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
    
    if not eleves.exists():
        messages.warning(request, "Cette classe ne contient aucun élève pour l'année scolaire active.")
        return redirect('directeur:bulletins_notes')
    
    # Construire le contexte pour chaque élève
    bulletins_data = []
    for eleve in eleves:
        bulletin_context, redirect_response = _build_bulletin_context(request, classe_id, eleve.id)
        if redirect_response:
            # Si redirection nécessaire (ex: pas de période active), on continue avec les autres élèves
            continue
        if bulletin_context:  # Si le contexte est valide
            bulletins_data.append({
                'eleve': eleve,
                'bulletin': bulletin_context,
            })
    
    if not bulletins_data:
        messages.warning(request, "Aucun bulletin disponible pour cette classe.")
        return redirect('directeur:bulletins_notes')
    
    # Contexte commun pour la page
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'bulletins_data': bulletins_data,
        'retour_url': reverse('directeur:bulletins_notes'),
        'date_generation': timezone.now(),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/imprimer_bulletins_classe.html', context)


def verifier_bulletin_qr(request):
    """
    Page publique d'authentification d'un bulletin via numéro de série + signature numérique.
    """
    numero_query_raw = request.GET.get('numero_serie') or request.GET.get('numero') or request.GET.get('serial') or ''
    signature_query_raw = request.GET.get('signature') or request.GET.get('hash') or ''

    numero_query = numero_query_raw.strip()
    numero_lookup = numero_query.upper()
    signature_query = signature_query_raw.strip()
    signature_lookup = signature_query.lower()

    verification_checked = bool(numero_lookup)
    verification_status = 'idle'
    bulletin_data = None
    show_details = False

    status_messages = {
        'valid': {
            'title': "Bulletin authentique",
            'message': "Le numéro de série et la signature correspondent à un bulletin officiel généré par l'établissement.",
            'tone': 'success',
            'icon': 'fas fa-check-circle',
        },
        'invalid_signature': {
            'title': "Signature numérique invalide",
            'message': "La signature transmise ne correspond pas à celle enregistrée pour ce bulletin. Vérifiez que le QR code provient bien de l'établissement.",
            'tone': 'danger',
            'icon': 'fas fa-times-circle',
        },
        'missing_signature': {
            'title': "Signature requise",
            'message': "Ce bulletin est signé numériquement. Scannez le QR code complet ou renseignez la signature pour confirmer l'authenticité.",
            'tone': 'warning',
            'icon': 'fas fa-exclamation-triangle',
        },
        'unsigned': {
            'title': "Bulletin non signé",
            'message': "Ce bulletin ne dispose pas encore d'une signature numérique. Contactez l'établissement pour régénérer le document.",
            'tone': 'warning',
            'icon': 'fas fa-info-circle',
        },
        'not_found': {
            'title': "Numéro introuvable",
            'message': "Aucun bulletin ne correspond à ce numéro de série. Vérifiez la saisie ou contactez l'établissement.",
            'tone': 'danger',
            'icon': 'fas fa-question-circle',
        },
    }

    if verification_checked:
        moyenne = (
            MoyennePeriode.objects.filter(
                numero_serie=numero_lookup,
                est_moyenne_generale=True,
            )
            .select_related('eleve__classe', 'etablissement', 'periode')
            .first()
        )

        if not moyenne:
            verification_status = 'not_found'
        else:
            stored_signature = (moyenne.signature_numerique or '').lower()
            if stored_signature:
                if signature_lookup:
                    if signature_lookup == stored_signature:
                        verification_status = 'valid'
                        show_details = True
                    else:
                        verification_status = 'invalid_signature'
                else:
                    verification_status = 'missing_signature'
            else:
                verification_status = 'unsigned'

            if show_details:
                eleve = moyenne.eleve
                classe = eleve.classe if eleve else None
                etablissement = moyenne.etablissement
                periode = moyenne.periode

                adresse_parts = [
                    etablissement.adresse or '',
                    etablissement.ville or '',
                    etablissement.pays or '',
                ]
                adresse = ', '.join(part for part in adresse_parts if part).strip(', ')

                effectif = None
                if classe:
                    effectif = classe.eleves.filter(actif=True).count()

                bulletin_data = {
                    'eleve_nom': eleve.nom_complet if eleve else None,
                    'classe_nom': classe.nom if classe else None,
                    'classe_niveau': classe.get_niveau_display() if classe else None,
                    'classe_effectif': effectif,
                    'periode_nom': periode.nom_periode if periode else None,
                    'annee_scolaire': periode.annee_scolaire if periode else None,
                    'moyenne_generale': float(moyenne.moyenne_generale) if moyenne.moyenne_generale is not None else None,
                    'rang': moyenne.rang,
                    'appreciation': moyenne.appreciation_generale,
                    'decision': moyenne.decision_conseil,
                    'numero_serie': moyenne.numero_serie,
                    'signature': moyenne.signature_numerique,
                    'date_generation': moyenne.qr_code_generated_at,
                    'date_publication': moyenne.date_publication,
                    'etablissement_nom': etablissement.nom if etablissement else None,
                    'etablissement_adresse': adresse,
                    'etablissement_email': etablissement.email if etablissement else None,
                    'etablissement_telephone': etablissement.telephone if etablissement else None,
                }

    status_info = status_messages.get(verification_status) if verification_status != 'idle' else None

    context = {
        'numero_serie_query': numero_query,
        'signature_query': signature_query,
        'verification_checked': verification_checked,
        'verification_status': verification_status,
        'status_info': status_info,
        'bulletin_data': bulletin_data,
        'show_bulletin_details': show_details,
        'verification_timestamp': timezone.now(),
    }

    return render(request, 'school_admin/directeur/verification_bulletin.html', context)


@login_required
def configuration_moyennes_generales(request):
    """Configuration des paramètres de calcul des moyennes générales."""
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    est_primaire = etablissement.type_etablissement == 'primary'

    from ..model.periode_model import PeriodeScolaire
    from ..utils.session_utils import get_session_active

    annee_scolaire_active = _get_session_directeur(request, etablissement)

    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de configurer les moyennes.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')

    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        annee_scolaire_fk=annee_scolaire_active
    ).order_by('date_debut')

    annee_scolaire = annee_scolaire_active.libelle
    ponderation = Ponderation.get_or_create_for_year(etablissement, annee_scolaire)
    methodes = []
    for key, label in Ponderation.TYPE_CALCUL_CHOICES:
        config = Ponderation.METHOD_CONFIG[key]
        methodes.append({
            'key': key,
            'label': label,
            'classe': config['classe'],
            'examen': config['examen'],
            'formule': f"(Classe × {config['classe'] / 100:.2f}) + (Examen × {config['examen'] / 100:.2f})",
        })

    methode_active = next((m for m in methodes if m['key'] == ponderation.type_calcul), None)

    errors = []

    if request.method == 'POST':
        methode_input = request.POST.get('methode', '').strip()
        if methode_input not in Ponderation.METHOD_CONFIG:
            errors.append("Méthode de calcul invalide.")
        else:
            ponderation.appliquer_methode(methode_input)
            ponderation.annee_scolaire = annee_scolaire
            ponderation.etablissement = etablissement
            ponderation.save()
            messages.success(request, "Pondération enregistrée avec succès.")
            return redirect('directeur:configuration_moyennes_generales')
        messages.error(request, "Veuillez corriger les erreurs indiquées.")

    context = {
        'etablissement': etablissement,
        'periodes': periodes,
        'est_primaire': est_primaire,
        'annee_scolaire': annee_scolaire,
        'annee_scolaire_active': annee_scolaire_active,
        'ponderation': {
            'type_calcul': ponderation.type_calcul,
            'poids_classe': ponderation.poids_classe,
            'poids_examen': ponderation.poids_examen,
        },
        'errors': errors,
        'methodes': methodes,
        'methode_active': methode_active,
    }

    return render(request, 'school_admin/directeur/configuration_moyennes_generales.html', context)


@login_required
def configuration_standards_reussite(request):
    """Configuration des standards de réussite pour l'établissement."""
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    from ..utils.session_utils import get_session_active

    annee_scolaire_active = _get_session_directeur(request, etablissement)

    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de configurer les standards.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')

    standards, _ = StandardsReussite.objects.get_or_create(
        etablissement=etablissement,
        defaults={'annee_scolaire': annee_scolaire_active}
    )

    if standards.annee_scolaire_id != (annee_scolaire_active.id if annee_scolaire_active else None):
        standards.annee_scolaire = annee_scolaire_active
        standards.save(update_fields=['annee_scolaire', 'date_modification'])

    def _format_decimal(value):
        if value is None:
            return ''
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"

    general_settings = {
        'moyenne_passage': _format_decimal(standards.moyenne_passage),
    }

    matiere_ranges = [
        {
            'min': _format_decimal(appreciation.note_min),
            'max': _format_decimal(appreciation.note_max),
            'label': appreciation.appreciation,
        }
        for appreciation in standards.appreciations_matieres.all().order_by('note_min')
    ]

    conseil_ranges = [
        {
            'min': _format_decimal(appreciation.note_min),
            'label': appreciation.appreciation,
        }
        for appreciation in standards.appreciations_conseil.all().order_by('note_min')
    ]

    periode_active_id = request.GET.get('periode') or request.POST.get('periode')

    if request.method == 'POST':
        section = request.POST.get('section', 'all').strip()
        if section == 'general':
            try:
                moyenne_passage = Decimal(request.POST.get('moyenne_passage', '').strip()).quantize(Decimal('0.01'))
                zero = Decimal('0')
                vingt = Decimal('20')
                if not (zero <= moyenne_passage <= vingt):
                    raise ValueError
            except Exception:
                messages.error(request, "La moyenne doit être un nombre entre 0 et 20.")
            else:
                standards.moyenne_passage = moyenne_passage
                standards.annee_scolaire = annee_scolaire_active
                standards.save(update_fields=['moyenne_passage', 'annee_scolaire', 'date_modification'])
                messages.success(request, "Seuils généraux enregistrés avec succès.")
                redirect_url = reverse('directeur:configuration_standards_reussite')
                if periode_active_id:
                    redirect_url = f"{redirect_url}?periode={periode_active_id}"
                return redirect(redirect_url)

        elif section == 'conseil':
            conseil_ranges = []
            index = 0
            while True:
                min_key = f"conseil-{index}-min"
                label_key = f"conseil-{index}-label"
                if min_key not in request.POST or label_key not in request.POST:
                    break
                try:
                    note_min = Decimal(request.POST[min_key].strip()).quantize(Decimal('0.01'))
                    label = request.POST[label_key].strip()
                    if note_min < 0 or note_min > 20:
                        raise ValueError
                    if not label:
                        raise ValueError
                    conseil_ranges.append((note_min, label))
                except Exception:
                    messages.error(request, f"Valeurs invalides pour l'appréciation conseil n°{index + 1}.")
                index += 1

            if conseil_ranges:
                standards.appreciations_conseil.all().delete()
                AppreciationConseilStandard.objects.bulk_create([
                    AppreciationConseilStandard(
                        standards=standards,
                        note_min=note_min,
                        appreciation=label,
                    )
                    for note_min, label in conseil_ranges
                ])
                standards.annee_scolaire = annee_scolaire_active
                standards.save(update_fields=['annee_scolaire', 'date_modification'])
                messages.success(request, "Appréciations du conseil enregistrées avec succès.")
                redirect_url = reverse('directeur:configuration_standards_reussite')
                if periode_active_id:
                    redirect_url = f"{redirect_url}?periode={periode_active_id}"
                return redirect(redirect_url)
            else:
                messages.error(request, "Ajoutez au moins une appréciation du conseil.")

        elif section == 'matieres':
            ranges = []
            index = 0
            while True:
                min_key = f"ranges-{index}-min"
                max_key = f"ranges-{index}-max"
                label_key = f"ranges-{index}-label"
                if min_key not in request.POST or max_key not in request.POST or label_key not in request.POST:
                    break
                try:
                    note_min = Decimal(request.POST[min_key].strip()).quantize(Decimal('0.01'))
                    note_max = Decimal(request.POST[max_key].strip()).quantize(Decimal('0.01'))
                    label = request.POST[label_key].strip()
                    if note_min < 0 or note_max > 20 or note_min >= note_max or not label:
                        raise ValueError
                    ranges.append((note_min, note_max, label))
                except Exception:
                    messages.error(request, f"Valeurs invalides pour le palier n°{index + 1}.")
                index += 1

            if ranges:
                standards.appreciations_matieres.all().delete()
                AppreciationMatiereStandard.objects.bulk_create([
                    AppreciationMatiereStandard(
                        standards=standards,
                        note_min=note_min,
                        note_max=note_max,
                        appreciation=label,
                    )
                    for note_min, note_max, label in ranges
                ])
                standards.annee_scolaire = annee_scolaire_active
                standards.save(update_fields=['annee_scolaire', 'date_modification'])
                messages.success(request, "Paliers d'appréciation enregistrés avec succès.")
                redirect_url = reverse('directeur:configuration_standards_reussite')
                if periode_active_id:
                    redirect_url = f"{redirect_url}?periode={periode_active_id}"
                return redirect(redirect_url)
            else:
                messages.error(request, "Ajoutez au moins un palier d'appréciation.")

        else:
            messages.error(request, "Section de formulaire inconnue.")

    context = {
        'etablissement': etablissement,
        'standards': standards,
        'general_settings': general_settings,
        'matiere_ranges': matiere_ranges,
        'conseil_ranges': conseil_ranges,
        'moyennes_standards': matiere_ranges,
        'conseil_standards': conseil_ranges,
        'periode_active_id': periode_active_id,
        'annee_scolaire_active': annee_scolaire_active,
    }
    return render(request, 'school_admin/directeur/configuration_standards_reussite.html', context)


@login_required
def suivi_presence(request):
    """
    Page de suivi des présences par classe et par mois
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.presence_model import Presence
    from ..model.periode_model import PeriodeScolaire
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Les données affichées ne sont pas filtrées par session.")
    
    # Récupérer les périodes scolaires filtrées par année scolaire active
    if annee_scolaire_active:
        periodes = list(
            PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                annee_scolaire_fk=annee_scolaire_active
            ).order_by('date_debut')
        )
    else:
        periodes = list(
            PeriodeScolaire.objects.filter(etablissement=etablissement).order_by('date_debut')
        )
    periode_id_param = request.GET.get('periode')
    periode_selectionnee = periodes[0] if periodes else None
    if periode_id_param and periodes:
        periode_selectionnee = next((p for p in periodes if str(p.id) == str(periode_id_param)), periode_selectionnee)
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau numérique
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "6eme", "5eme", etc.
        else:
            categorie = nom
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'nombre_classes': 0,
            }
        
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        # Construire le queryset de présence filtré par période et année scolaire active
        # PRIORITÉ AU FILTRAGE PAR DATE DE PÉRIODE (pas par année scolaire liée)
        presences_queryset = Presence.objects.filter(classe=classe)
        
        # LOGIQUE DE FILTRAGE BASÉE SUR LES DATES (Prioritaire sur l'objet année scolaire)
        # On compare la date d'enregistrement de la présence à la date de la période ou de l'année active.
        if periode_selectionnee:
            # Si une période est sélectionnée, on filtre strictement sur ses dates
            # Peu importe l'année scolaire liée à la présence, on affiche toutes les présences
            # dont la date est dans la plage de la période
            presences_queryset = presences_queryset.filter(
                date__gte=periode_selectionnee.date_debut,
                date__lte=periode_selectionnee.date_fin
            )
        elif annee_scolaire_active:
            # Sinon, on filtre sur les dates de l'année scolaire active
            presences_queryset = presences_queryset.filter(
                date__gte=annee_scolaire_active.date_debut,
                date__lte=annee_scolaire_active.date_fin
            )
        
        # Récupérer les mois distincts où il y a des données de présence pour cette classe
        presences_classe = presences_queryset.values('date__month', 'date__year').distinct().order_by('date__year', 'date__month')
        
        # Créer une liste des mois disponibles
        mois_disponibles = []
        
        # Si une période est sélectionnée, inclure tous les mois de la période même sans présences
        if periode_selectionnee:
            date_courante = periode_selectionnee.date_debut
            while date_courante <= periode_selectionnee.date_fin:
                mois_existant = next(
                    (m for m in mois_disponibles if m['numero'] == date_courante.month and m['annee'] == date_courante.year),
                    None
                )
                if not mois_existant:
                    date_mois = datetime(date_courante.year, date_courante.month, 1)
                    mois_disponibles.append({
                        'numero': date_courante.month,
                        'annee': date_courante.year,
                        'nom': date_mois.strftime('%B'),
                        'nom_court': date_mois.strftime('%b'),
                    })
                # Passer au mois suivant
                if date_courante.month == 12:
                    date_courante = date_courante.replace(year=date_courante.year + 1, month=1, day=1)
                else:
                    date_courante = date_courante.replace(month=date_courante.month + 1, day=1)
        
        # Ajouter aussi les mois où il y a effectivement des présences (pour éviter les doublons)
        for p in presences_classe:
            mois_existant = next(
                (m for m in mois_disponibles if m['numero'] == p['date__month'] and m['annee'] == p['date__year']),
                None
            )
            if not mois_existant:
                date_mois = datetime(p['date__year'], p['date__month'], 1)
                mois_disponibles.append({
                    'numero': p['date__month'],
                    'annee': p['date__year'],
                    'nom': date_mois.strftime('%B'),
                    'nom_court': date_mois.strftime('%b'),
                })
        
        # Trier les mois par année et mois
        mois_disponibles.sort(key=lambda x: (x['annee'], x['numero']))
        
        # Pour chaque mois, calculer les statistiques de présence pour chaque élève
        mois_presences = {}
        
        for mois in mois_disponibles:
            eleves_presences = []
            
            for eleve in eleves:
                # Récupérer les présences de l'élève pour ce mois
                presences = presences_queryset.filter(
                    eleve=eleve,
                    date__month=mois['numero'],
                    date__year=mois['annee']
                )
                
                total_jours = presences.count()
                presents = presences.filter(statut='present').count()
                absents = presences.filter(statut='absent').count()
                absents_justifies = presences.filter(statut='absent_justifie').count()
                retards = presences.filter(statut='retard').count()

                absences_details = []
                if absents:
                    absences_query = presences.filter(statut='absent').order_by('-date', '-numero_appel')
                    for absence in absences_query:
                        label_parts = [
                            absence.date.strftime('%d/%m/%Y'),
                            f"Appel {absence.numero_appel}"
                        ]
                        if absence.matiere:
                            label_parts.append(absence.matiere.nom)
                        absences_details.append({
                            'id': absence.id,
                            'label': " - ".join(label_parts)
                        })
                
                # Calculer le taux de présence
                if total_jours > 0:
                    taux_presence = round((presents / total_jours) * 100, 2)
                else:
                    taux_presence = None
                
                eleves_presences.append({
                    'eleve': eleve,
                    'total_jours': total_jours,
                    'presents': presents,
                    'absents': absents,
                    'absents_justifies': absents_justifies,
                    'retards': retards,
                    'taux_presence': taux_presence,
                    'absences_details': absences_details,
                })
            
            # Trier par taux de présence décroissant (None en dernier)
            eleves_presences.sort(key=lambda x: (x['taux_presence'] is None, -x['taux_presence'] if x['taux_presence'] is not None else 0))
            
            mois_presences[f"{mois['numero']}_{mois['annee']}"] = {
                'mois': mois,
                'eleves_presences': eleves_presences,
            }
        
        classe_info = {
            'classe': classe,
            'mois_presences': mois_presences,
            'mois_disponibles': mois_disponibles,
            'nombre_eleves': eleves.count(),
            'periode_id': periode_selectionnee.id if periode_selectionnee else None,
        }
        
        classes_grouped[categorie]['classes'].append(classe_info)
        classes_grouped[categorie]['total_eleves'] += classe_info['nombre_eleves']
        classes_grouped[categorie]['nombre_classes'] += 1
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': classes_grouped,
        'periodes': periodes,
        'periode_selectionnee': periode_selectionnee,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/suivi_presence.html', context)


@login_required
def justifier_absence_directeur(request):
    """
    Permet au directeur de justifier une absence sélectionnée en la marquant comme présence.
    """
    if request.method != 'POST':
        messages.error(request, "Méthode non autorisée.")
        return redirect('directeur:suivi_presence')

    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    presence_id = request.POST.get('presence_id')

    if not presence_id:
        messages.error(request, "Veuillez sélectionner une absence à justifier.")
        return redirect('directeur:suivi_presence')

    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from ..model.presence_model import Presence

    presence = get_object_or_404(Presence.objects.select_related('eleve', 'classe', 'etablissement'), id=presence_id)

    if presence.etablissement != request.user:
        messages.error(request, "Vous ne pouvez pas modifier une présence qui n'appartient pas à votre établissement.")
        return redirect('directeur:suivi_presence')

    if presence.statut != 'absent':
        messages.warning(request, "Seules les absences non justifiées peuvent être converties.")
        return redirect('directeur:suivi_presence')

    try:
        presence.statut = 'present'
        presence.type_justificatif = None
        presence.justificatif_valide = True
        presence.date_justification = timezone.now()
        presence.save(update_fields=['statut', 'type_justificatif', 'justificatif_valide', 'date_justification', 'date_modification'])

        eleve = getattr(presence, "eleve", None)
        classe = getattr(presence, "classe", None)
        classe_nom = getattr(classe, "nom", "sa classe")
        date_str = presence.date.strftime("%d/%m/%Y") if getattr(presence, "date", None) else timezone.now().strftime("%d/%m/%Y")
        appel = getattr(presence, "numero_appel", 1)

        notification_payload = {
            "presence_id": getattr(presence, "id", None),
            "statut": presence.statut,
            "classe": classe_nom,
            "date": date_str,
            "numero_appel": appel,
            "justifie_par": "direction",
        }

        if eleve:
            titre_eleve = "Absence justifiée"
            message_eleve = (
                f"Votre absence du {date_str} (appel n°{appel}) en {classe_nom} a été justifiée par la direction. "
                "Votre statut est désormais enregistré comme présent."
            )
            EleveNotificationService._dispatch(
                eleve,
                type_notification="presence",
                titre=titre_eleve,
                message=message_eleve,
                payload=notification_payload,
                source=presence,
                push_title=titre_eleve,
                push_body=message_eleve,
                push_data={
                    "type": "presence_justifiee",
                    "presence_id": str(getattr(presence, "id", "")),
                    "eleve_id": str(getattr(eleve, "id", "")),
                    "classe": classe_nom,
                },
            )

            titre_parent = f"Absence justifiée - {classe_nom}"
            message_parent = (
                f"{eleve.nom_complet} a été marqué présent pour l'appel du {date_str} (appel n°{appel}) "
                "après justification validée par la direction."
            )
            ParentNotificationService._dispatch(
                eleve,
                type_notification="presence",
                titre=titre_parent,
                message=message_parent,
                payload=notification_payload,
                source=presence,
                push_title=titre_parent,
                push_body=message_parent,
                push_data={
                    "type": "parent_presence_justifiee",
                    "presence_id": str(getattr(presence, "id", "")),
                    "eleve_id": str(getattr(eleve, "id", "")),
                    "classe": classe_nom,
                },
            )

        messages.success(
            request,
            f"L'absence du {presence.date.strftime('%d/%m/%Y')} pour {presence.eleve.nom_complet} a été justifiée avec succès."
        )
    except Exception as error:
        messages.error(request, f"Erreur lors de la justification de l'absence : {error}")

    return redirect('directeur:suivi_presence')


@login_required
@login_required
def gestion_etablissement(request):
    """
    Vue de la page de gestion de l'établissement pour les directeurs d'établissement et le personnel administratif
    """
    # Vérifier que l'utilisateur a accès
    result = _get_user_etablissement(request, 'etablissement_profil')
    if result[0] is None:
        messages.error(request, "Vous n'avez pas l'autorisation d'accéder à cette fonctionnalité.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    context = {
        'etablissement': etablissement,
        'annee_scolaire_active': annee_scolaire_active,
        'is_directeur': is_directeur,
        'personnel': personnel,
    }
   
    return render(request, 'school_admin/directeur/gestion_etablissement.html', context)


@login_required
def gestion_periodes_scolaires(request):
    """
    Vue pour la gestion des périodes scolaires (trimestres, semestres)
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer l'année scolaire en cours (septembre N à août N+1)
    from datetime import date
    aujourdhui = date.today()
    if aujourdhui.month >= 9:
        annee_debut = aujourdhui.year
    else:
        annee_debut = aujourdhui.year - 1
    annee_scolaire_actuelle = f"{annee_debut}-{annee_debut + 1}"
    
    # Gestion de l'ajout d'une nouvelle période
    if request.method == 'POST':
        from ..model.periode_model import PeriodeScolaire
        from django.db import transaction
        from datetime import datetime

        action = request.POST.get('action', 'ajouter').strip()

        def _parse_date(date_str: str):
            if not date_str:
                return None
            return datetime.strptime(date_str, '%Y-%m-%d').date()

        try:
            if action == 'creer_annee_scolaire':
                from ..controllers.annee_scolaire_controller import AnneeScolaireController
                
                date_debut_str = request.POST.get('date_debut', '')
                date_fin_str = request.POST.get('date_fin', '')
                est_ouverte = request.POST.get('est_ouverte') == 'on'
                
                if not all([date_debut_str, date_fin_str]):
                    messages.error(request, "Veuillez remplir les dates de début et de fin.")
                    return redirect('directeur:gestion_periodes_scolaires')
                
                date_debut = _parse_date(date_debut_str)
                date_fin = _parse_date(date_fin_str)
                
                # Calculer automatiquement les années et le libellé à partir des dates
                annee_debut = date_debut.year
                annee_fin = date_fin.year
                
                # Vérifier que l'année de fin est bien l'année de début + 1
                if annee_fin != annee_debut + 1:
                    messages.error(request, f"L'année scolaire doit couvrir une période d'un an. Année de début: {annee_debut}, Année de fin: {annee_fin}")
                    return redirect('directeur:gestion_periodes_scolaires')
                
                libelle = AnneeScolaireController.generer_libelle_annee(annee_debut)
                
                annee_scolaire = AnneeScolaireController.creer_annee_scolaire(
                    etablissement=etablissement,
                    libelle=libelle,
                    annee_debut=annee_debut,
                    annee_fin=annee_fin,
                    date_debut=date_debut,
                    date_fin=date_fin,
                    est_ouverte=est_ouverte
                )
                
                messages.success(request, f"Année scolaire {libelle} créée avec succès.")
                return redirect('directeur:gestion_periodes_scolaires')
            
            elif action == 'ajouter':
                from ..utils.session_utils import get_session_active
                from ..model.annee_scolaire_model import AnneeScolaire
                
                # Récupérer l'année scolaire active
                annee_scolaire_active = _get_session_directeur(request, etablissement)
                
                if not annee_scolaire_active:
                    messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'ajouter une période.")
                    return redirect('directeur:creer_annee_scolaire_obligatoire')
                
                with transaction.atomic():
                    nom_periode = request.POST.get('nom_periode', '').strip()
                    type_periode = request.POST.get('type_periode', 'trimestre').strip()
                    date_debut_str = request.POST.get('date_debut', '')
                    date_fin_str = request.POST.get('date_fin', '')
                    est_active = request.POST.get('est_active') == 'on'

                    if not all([nom_periode, date_debut_str, date_fin_str]):
                        messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                        return redirect('directeur:gestion_periodes_scolaires')

                    date_debut = _parse_date(date_debut_str)
                    date_fin = _parse_date(date_fin_str)

                    periode = PeriodeScolaire.objects.create(
                        etablissement=etablissement,
                        nom_periode=nom_periode,
                        type_periode=type_periode,
                        date_debut=date_debut,
                        date_fin=date_fin,
                        annee_scolaire=annee_scolaire_active.libelle,  # Utiliser le libellé de l'année active
                        annee_scolaire_fk=annee_scolaire_active,  # Lier à l'année scolaire active
                        est_active=est_active
                    )

                    messages.success(request, f"La période '{periode.nom_periode}' a été créée avec succès pour l'année scolaire {annee_scolaire_active.libelle}.")
                    return redirect('directeur:gestion_periodes_scolaires')

            elif action == 'modifier':
                periode_id = request.POST.get('periode_id')
                if not periode_id:
                    messages.error(request, "Période introuvable.")
                    return redirect('directeur:gestion_periodes_scolaires')

                with transaction.atomic():
                    periode = PeriodeScolaire.objects.get(id=periode_id, etablissement=etablissement)
                    periode.nom_periode = request.POST.get('nom_periode', periode.nom_periode).strip()
                    periode.type_periode = request.POST.get('type_periode', periode.type_periode).strip()
                    periode.date_debut = _parse_date(request.POST.get('date_debut')) or periode.date_debut
                    periode.date_fin = _parse_date(request.POST.get('date_fin')) or periode.date_fin
                    # Conserver l'année scolaire existante (ne pas la modifier)
                    # periode.annee_scolaire et periode.annee_scolaire_fk restent inchangés
                    periode.est_active = request.POST.get('est_active') == 'on'
                    periode.save()

                    messages.success(request, f"La période '{periode.nom_periode}' a été mise à jour.")
                    return redirect('directeur:gestion_periodes_scolaires')

            elif action == 'supprimer':
                periode_id = request.POST.get('periode_id')
                if not periode_id:
                    messages.error(request, "Période introuvable.")
                    return redirect('directeur:gestion_periodes_scolaires')

                with transaction.atomic():
                    periode = PeriodeScolaire.objects.get(id=periode_id, etablissement=etablissement)
                    nom_periode = periode.nom_periode
                    periode.delete()
                    messages.success(request, f"La période '{nom_periode}' a été supprimée.")
                    return redirect('directeur:gestion_periodes_scolaires')

            else:
                messages.error(request, "Action invalide.")
                return redirect('directeur:gestion_periodes_scolaires')

        except PeriodeScolaire.DoesNotExist:
            messages.error(request, "Période introuvable.")
            return redirect('directeur:gestion_periodes_scolaires')
        except ValidationError as e:
            # Extraire le message d'erreur de manière lisible (sans les détails techniques)
            error_message = "Une erreur s'est produite lors de la validation."
            
            # Django ValidationError avec message_dict (erreurs par champ)
            if hasattr(e, 'message_dict') and e.message_dict:
                # Récupérer tous les messages d'erreur de tous les champs
                error_messages = []
                for field_errors in e.message_dict.values():
                    for error in field_errors:
                        error_messages.append(str(error))
                if error_messages:
                    # Prendre le premier message (le plus important)
                    error_message = error_messages[0]
            # Django ValidationError avec message (message simple)
            elif hasattr(e, 'message') and e.message:
                error_message = str(e.message)
            # Django ValidationError avec messages (liste de messages)
            elif hasattr(e, 'messages') and e.messages:
                error_message = str(e.messages[0])
            # Fallback : essayer d'extraire le message depuis la représentation string
            else:
                error_str = str(e)
                # Nettoyer le message en enlevant les caractères techniques
                # Si le message contient des guillemets, extraire le contenu
                if "'" in error_str or '"' in error_str:
                    # Chercher le contenu entre guillemets (prendre le dernier segment entre guillemets)
                    parts = error_str.split("'")
                    if len(parts) >= 2:
                        # Prendre l'avant-dernier segment (le message)
                        error_message = parts[-2] if len(parts) > 2 else parts[-1]
                    else:
                        parts = error_str.split('"')
                        if len(parts) >= 2:
                            error_message = parts[-2] if len(parts) > 2 else parts[-1]
                else:
                    error_message = error_str.strip("'\"[]")
            
            messages.error(request, error_message)
            return redirect('directeur:gestion_periodes_scolaires')
        except Exception as e:
            messages.error(request, f"Erreur lors du traitement de la période : {str(e)}")
            return redirect('directeur:gestion_periodes_scolaires')
    
    # Récupérer l'année scolaire active AVANT de récupérer les périodes
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..utils.session_utils import get_session_active
    from ..model.periode_model import PeriodeScolaire
    
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    # Récupérer toutes les années scolaires de l'établissement
    annees_scolaires = AnneeScolaire.objects.filter(
        etablissement=etablissement
    ).order_by('-annee_debut', '-date_debut')
    
    # Récupérer uniquement les périodes de l'année scolaire active (si disponible)
    if annee_scolaire_active:
        periodes = PeriodeScolaire.objects.filter(
            etablissement=etablissement,
            annee_scolaire_fk=annee_scolaire_active
        ).order_by('date_debut')
    else:
        # Si pas d'année scolaire active, ne rien afficher
        periodes = PeriodeScolaire.objects.none()
    
    # Grouper les périodes par année scolaire (seulement l'année active sera affichée)
    periodes_par_annee = {}
    if annee_scolaire_active and periodes.exists():
        annee_libelle = annee_scolaire_active.libelle
        periodes_par_annee[annee_libelle] = list(periodes)
    
    context = {
        'user': etablissement,
        'etablissement': etablissement,
        'periodes': periodes,
        'periodes_par_annee': periodes_par_annee,
        'annee_scolaire_actuelle': annee_scolaire_actuelle,
        'annees_scolaires': annees_scolaires,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/gestion_periodes_scolaires.html', context)


@login_required
@login_required
def api_details_notes_matiere(request):
    """
    API pour récupérer les détails des notes d'une matière pour une classe
    Retourne les notes retenues, la note d'examen et la moyenne pour chaque élève
    """
    from django.http import JsonResponse
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    from ..model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire
    from ..model.evaluation_primaire_model import EvaluationPrimaire
    from ..model.note_examen_model import NoteExamen
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..utils.decorators_permissions import check_permission
    
    # Vérifier que c'est une requête AJAX
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Requête invalide'}, status=400)
    
    # Vérifier les permissions
    user = request.user
    if isinstance(user, Etablissement):
        etablissement = user
    elif isinstance(user, PersonnelAdministratif):
        if not check_permission(user, 'notes_detail'):
            return JsonResponse({'success': False, 'message': 'Accès non autorisé'}, status=403)
        etablissement = user.etablissement
    else:
        return JsonResponse({'success': False, 'message': 'Accès non autorisé'}, status=403)
    
    # Récupérer les paramètres
    classe_id = request.GET.get('classe_id')
    matiere_nom = request.GET.get('matiere_nom')
    periode_id = request.GET.get('periode_id')
    
    if not all([classe_id, matiere_nom, periode_id]):
        return JsonResponse({'success': False, 'message': 'Paramètres manquants'}, status=400)
    
    try:
        # Récupérer les objets
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
        matiere = Matiere.objects.get(nom=matiere_nom, etablissement=etablissement)
        periode = PeriodeScolaire.objects.get(id=periode_id, etablissement=etablissement)
        
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        annee_scolaire_active = get_session_active(request, etablissement)
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        eleves_data = []
        for eleve in eleves:
            # Récupérer la moyenne
            moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=matiere,
                periode_scolaire=periode
            ).first()
            
            # Si pas de moyenne, passer cet élève
            if not moyenne_obj or moyenne_obj.moyenne is None:
                continue
            
            # Récupérer TOUTES les notes de l'élève pour cette matière
            # On affiche toutes les notes (retenues ou non) pour la transparence
            notes_evaluations = NotePrimaire.objects.filter(
                eleve=eleve,
                evaluation_primaire__classe=classe,
                evaluation_primaire__matiere=matiere,
                evaluation_primaire__periode_scolaire=periode,
                absent=False
            ).select_related('evaluation_primaire').order_by('-note')
            
            notes_retenues_list = []
            for note in notes_evaluations:
                # Utiliser la propriété note_sur_20 qui calcule la note sur 20
                try:
                    note_valeur = note.note_sur_20
                    if note_valeur is not None:
                        note_float = float(note_valeur)
                        notes_retenues_list.append({
                            'titre': note.evaluation_primaire.titre,
                            'note': note_float,
                            'bareme': 20,
                            'date': note.evaluation_primaire.date_evaluation.strftime('%d/%m/%Y') if note.evaluation_primaire.date_evaluation else '',
                            'retenue': note.retenue
                        })
                except Exception:
                    pass
            
            # Récupérer la note d'examen si elle existe
            note_examen = None
            note_examen_obj = NoteExamen.objects.filter(
                eleve=eleve,
                matiere=matiere,
                classe=classe,
                session_examen__periode=periode,
                note__isnull=False
            ).order_by('-date_saisie').first()

            note_examen_absent = False
            if note_examen_obj and note_examen_obj.note is not None:
                note_examen_absent = note_examen_obj.absent
                if note_examen_obj.note_sur_20 is not None:
                    note_examen = float(note_examen_obj.note_sur_20)
                else:
                    try:
                        note_examen = float(note_examen_obj.note)
                        if note_examen_obj.bareme and note_examen_obj.bareme != 20:
                            note_examen = round((note_examen / float(note_examen_obj.bareme)) * 20, 2)
                    except (TypeError, ValueError):
                        note_examen = None
            
            # Initiales de l'élève
            initiales = ''
            if eleve.prenom:
                initiales = eleve.prenom[0].upper()
            if eleve.nom:
                initiales += eleve.nom[0].upper()
            
            eleves_data.append({
                'nom': eleve.nom_complet,
                'initiales': initiales,
                'notes_retenues': notes_retenues_list,
                'note_examen': note_examen,
                'note_examen_absent': note_examen_absent,
                'moyenne': float(moyenne_obj.moyenne)
            })
        
        # Trier par moyenne décroissante
        eleves_data.sort(key=lambda x: x['moyenne'], reverse=True)
        
        return JsonResponse({
            'success': True,
            'eleves': eleves_data,
            'matiere': matiere_nom,
            'classe': classe.nom,
            'periode': periode.nom_periode
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
@login_required
def api_details_notes_matiere_secondaire(request):
    """
    API pour récupérer les détails des notes d'une matière pour une classe (SECONDAIRE)
    Retourne les notes retenues, la note d'examen et la moyenne pour chaque élève
    Spécifique aux établissements de type lycée, collège, collège+lycée
    """
    from django.http import JsonResponse
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    from ..model.evaluation_model import Note
    from ..model.note_examen_model import NoteExamen
    from ..model.moyenne_model import Moyenne
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..utils.decorators_permissions import check_permission
    
    # Vérifier que c'est une requête AJAX
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Requête invalide'}, status=400)
    
    # Vérifier les permissions
    user = request.user
    if isinstance(user, Etablissement):
        etablissement = user
    elif isinstance(user, PersonnelAdministratif):
        if not check_permission(user, 'notes_detail'):
            return JsonResponse({'success': False, 'message': 'Accès non autorisé'}, status=403)
        etablissement = user.etablissement
    else:
        return JsonResponse({'success': False, 'message': 'Accès non autorisé'}, status=403)
    
    # Vérifier que c'est un établissement secondaire (inclure toutes les variantes)
    est_secondaire = etablissement.type_etablissement in TYPES_ETABLISSEMENT_SECONDAIRE
    if not est_secondaire:
        return JsonResponse({'success': False, 'message': 'Cette fonctionnalité est réservée aux établissements secondaires'}, status=403)
    
    # Récupérer les paramètres
    classe_id = request.GET.get('classe_id')
    matiere_nom = request.GET.get('matiere_nom')
    
    if not all([classe_id, matiere_nom]):
        return JsonResponse({'success': False, 'message': 'Paramètres manquants'}, status=400)
    
    try:
        # Récupérer les objets
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
        matiere = Matiere.objects.get(nom=matiere_nom, etablissement=etablissement)
        
        periode_id = request.GET.get('periode_id')
        periode = None
        if periode_id:
            periode = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                id=periode_id
            ).first()
        if not periode:
            periode = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True
            ).first()
        
        if not periode:
            return JsonResponse({'success': False, 'message': 'Aucune période active trouvée'}, status=404)
        
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        annee_scolaire_active = get_session_active(request, classe.etablissement)
        eleves = _get_eleves_classe_par_inscription(classe, classe.etablissement, annee_scolaire_active)
        
        eleves_data = []
        for eleve in eleves:
            # Récupérer la moyenne pour cette matière
            moyenne_obj = Moyenne.objects.filter(
                eleve=eleve,
                classe=classe,
                matiere=matiere,
                periode=str(periode.id),
                actif=True,
                soumis=True  # Seulement les moyennes soumises
            ).first()
            
            # Si pas de moyenne soumise, passer cet élève
            if not moyenne_obj or moyenne_obj.moyenne is None:
                continue
            
            # Récupérer toutes les notes retenues pour cette matière
            notes_evaluations = Note.objects.filter(
                eleve=eleve,
                evaluation__matiere=matiere,
                evaluation__periode_scolaire=periode,
                retenue=True,
                absent=False
            ).select_related('evaluation').order_by('evaluation__date_evaluation')
            
            notes_retenues_list = []
            for note in notes_evaluations:
                note_sur_20 = note.note_sur_20
                if note_sur_20 is None:
                    continue
                notes_retenues_list.append({
                    'titre': note.evaluation.titre,
                    'note': float(note_sur_20),
                    'bareme': 20,
                    'date': note.evaluation.date_evaluation.strftime('%d/%m/%Y') if note.evaluation.date_evaluation else ''
                })
            
            # Récupérer la note d'examen pour cette matière
            note_examen_obj = NoteExamen.objects.filter(
                eleve=eleve,
                matiere=matiere,
                classe=classe,
                session_examen__periode=periode,
                note__isnull=False
            ).order_by('-date_saisie').first()
            
            note_examen = None
            note_examen_absent = False
            if note_examen_obj and note_examen_obj.note is not None:
                note_examen_absent = note_examen_obj.absent
                if note_examen_obj.note_sur_20 is not None:
                    note_examen = float(note_examen_obj.note_sur_20)
                else:
                    try:
                        note_examen = float(note_examen_obj.note)
                        if note_examen_obj.bareme and note_examen_obj.bareme != 20:
                            note_examen = round((note_examen / float(note_examen_obj.bareme)) * 20, 2)
                    except (TypeError, ValueError):
                        note_examen = None
            
            # Ajouter les données de l'élève
            eleves_data.append({
                'id': eleve.id,
                'nom': eleve.nom_complet,
                'initiales': f"{eleve.nom[0]}{eleve.prenom[0]}" if eleve.nom and eleve.prenom else (eleve.nom[:2].upper() if eleve.nom else ''),
                'notes_retenues': notes_retenues_list,
                'note_examen': note_examen,
                'note_examen_absent': note_examen_absent,
                'moyenne': float(moyenne_obj.moyenne)
            })
        
        # Trier les élèves par moyenne décroissante
        eleves_data.sort(key=lambda x: x['moyenne'], reverse=True)
        
        return JsonResponse({
            'success': True,
            'eleves': eleves_data,
            'matiere': matiere_nom,
            'classe': classe.nom,
            'periode': periode.nom_periode
        })
        
    except Classe.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Classe non trouvée'}, status=404)
    except Matiere.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Matière non trouvée'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def imprimer_releve_notes(request, classe_id):
    """
    Vue pour l'impression du relevé de notes d'une classe
    Affiche un tableau professionnel avec en-tête de l'établissement et toutes les notes par matière
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Note, Evaluation
    from ..model.releve_notes_model import ReleveNotes
    from ..model.affectation_model import AffectationProfesseur
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from ..model.note_primaire_model import MoyenneMatierePrimaire
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from collections import defaultdict
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'imprimer le relevé de notes.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    try:
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:notes_et_resultats')
    
    # Détecter le type d'établissement
    est_primaire = etablissement.type_etablissement == 'primary'
    
    # Récupérer la période scolaire active filtrée par année scolaire active
    periode = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True,
        annee_scolaire_fk=annee_scolaire_active
    ).first()
    
    if not periode:
        messages.warning(request, "Aucune période scolaire active trouvée pour l'année scolaire active.")
        return redirect('directeur:notes_et_resultats')
    
    # Filtrer les élèves par année scolaire active via InscriptionEleve
    eleves_ids_inscrits = InscriptionEleve.objects.filter(
        annee_scolaire=annee_scolaire_active,
        classe=classe,
        etablissement=etablissement
    ).values_list('eleve_id', flat=True)
    
    eleves = Eleve.objects.filter(
        id__in=eleves_ids_inscrits,
        classe=classe
    ).order_by('nom', 'prenom')
    
    if est_primaire:
        # LOGIQUE PRIMAIRE
        # Récupérer TOUTES les matières de la classe
        matieres = classe.matieres.filter(actif=True).order_by('nom')
        
        # Si aucune matière n'est associée, récupérer les matières du niveau
        if not matieres.exists():
            matieres = Matiere.objects.filter(
                niveau__in=[classe.niveau, 'tous'],
                etablissement=etablissement,
                actif=True
            ).order_by('nom')
        
        # Préparer les données des élèves avec leurs moyennes par matière
        eleves_data = []
        for eleve in eleves:
            eleve_info = {
                'eleve': eleve,
                'matieres': {},
                'nombre_matieres_avec_moyenne': 0,
                'moyenne_generale': 0,
            }
            
            somme_moyennes = 0
            nombre_moyennes = 0
            
            for matiere in matieres:
                # Récupérer la moyenne de l'élève pour cette matière filtrée par année scolaire active
                moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    periode_scolaire=periode,
                    annee_scolaire=annee_scolaire_active
                ).first()
                
                moyenne_soumise = getattr(moyenne_obj, "soumis", False) if moyenne_obj else False
                moyenne_value = float(moyenne_obj.moyenne) if moyenne_obj and moyenne_obj.moyenne is not None else None
                
                eleve_info['matieres'][matiere.nom] = {
                    'moyenne': moyenne_value,
                    'nombre_notes': moyenne_obj.nombre_notes if moyenne_obj else 0,
                    'releve_soumis': moyenne_soumise,
                }
                
                if moyenne_value is not None:
                    eleve_info['nombre_matieres_avec_moyenne'] += 1
                    somme_moyennes += float(moyenne_value)
                    nombre_moyennes += 1
            
            # Calculer la moyenne générale
            if nombre_moyennes > 0:
                eleve_info['moyenne_generale'] = round(somme_moyennes / nombre_moyennes, 2)
            
            eleves_data.append(eleve_info)
        
        # Trier les élèves par moyenne générale décroissante (pour le classement)
        eleves_data.sort(key=lambda x: x['moyenne_generale'] if x['moyenne_generale'] else 0, reverse=True)
        
        context = {
            'etablissement': etablissement,
            'classe': classe,
            'periode': periode,
            'eleves_data': eleves_data,
            'matieres': matieres,
            'nombre_eleves': eleves.count(),
            'nombre_matieres': matieres.count(),
            'est_primaire': True,
            'annee_scolaire_active': annee_scolaire_active,
        }
    else:
        # LOGIQUE COLLÈGE/LYCÉE
        from ..model.moyenne_model import Moyenne
        from ..model.note_examen_model import NoteExamen
        
        # Récupérer TOUTES les matières de la classe
        matieres = classe.matieres.filter(actif=True).order_by('nom')
        
        # Si aucune matière n'est associée, récupérer les matières du niveau
        if not matieres.exists():
            matieres = Matiere.objects.filter(
                niveau__in=[classe.niveau, 'tous'],
                etablissement=etablissement,
                actif=True
            ).order_by('nom')
        
        # Préparer les données des élèves avec leurs moyennes par matière
        eleves_data = []
        for eleve in eleves:
            eleve_info = {
                'eleve': eleve,
                'matieres_moyennes': {},
                'moyenne_generale': 0,
                'total_coefficients': 0,
            }
            
            somme_ponderee = 0
            total_coefficients = 0
            
            for matiere in matieres:
                # Récupérer la moyenne de l'élève pour cette matière filtrée par année scolaire active
                moyenne_obj = Moyenne.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    matiere=matiere,
                    periode=str(periode.id),
                    actif=True,
                    annee_scolaire=annee_scolaire_active
                ).first()
                
                # Afficher la moyenne SEULEMENT si elle est soumise
                moyenne_soumise = moyenne_obj and moyenne_obj.soumis
                moyenne_value = moyenne_obj.moyenne if moyenne_soumise and moyenne_obj.moyenne else None
                
                eleve_info['matieres_moyennes'][matiere.nom] = {
                    'moyenne': moyenne_value,
                    'coefficient': matiere.coefficient,
                    'soumis': moyenne_soumise,
                }
                
                if moyenne_value is not None:
                    somme_ponderee += moyenne_value * matiere.coefficient
                    total_coefficients += matiere.coefficient
            
            # Calculer la moyenne générale
            if total_coefficients > 0:
                eleve_info['moyenne_generale'] = round(somme_ponderee / total_coefficients, 2)
                eleve_info['total_coefficients'] = total_coefficients
            
            eleves_data.append(eleve_info)
        
        # Trier les élèves par moyenne générale décroissante
        eleves_data.sort(key=lambda x: x['moyenne_generale'] if x['moyenne_generale'] else 0, reverse=True)
        
        context = {
            'etablissement': etablissement,
            'classe': classe,
            'periode': periode,
            'eleves_data': eleves_data,
            'matieres': matieres,
            'nombre_eleves': eleves.count(),
            'nombre_matieres': matieres.count(),
            'est_primaire': False,
            'annee_scolaire_active': annee_scolaire_active,
        }
    
    return render(request, 'school_admin/directeur/imprimer_releve_notes.html', context)


@login_required
@login_required
@login_required
@require_permission('administrative_voir')
def gestion_administrative(request):
    """
    Page de gestion administrative pour les directeurs et le personnel administratif
    Génération de documents administratifs (certificats, attestations, etc.)
    """
    result = _get_user_etablissement(request, 'administrative_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    context = {
        'etablissement': etablissement,
        'annee_scolaire_active': annee_scolaire_active,
        'is_directeur': is_directeur,
        'is_personnel_administratif': not is_directeur,
        'personnel': personnel,
    }
    
    return render(request, 'school_admin/directeur/gestion_administrative.html', context)


@login_required
def certificat_scolarite_liste(request):
    """
    Page listant tous les élèves pour générer des certificats de scolarité
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    from collections import defaultdict
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Les élèves affichés ne sont pas filtrés par session.")
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/certificat_scolarite_liste.html', context)


@login_required
def generer_certificat_scolarite(request, eleve_id):
    """
    Génère un certificat de scolarité pour un élève spécifique
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Le certificat sera généré sans référence à une session spécifique.")
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:certificat_scolarite_liste')
    
    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    # Informations pour le certificat
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/generer_certificat_scolarite.html', context)


@login_required
def convocation_liste(request):
    """
    Page listant tous les élèves pour générer des convocations
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Les élèves affichés ne sont pas filtrés par session.")
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/convocation_liste.html', context)


@login_required
def generer_convocation(request, eleve_id):
    """
    Affiche le formulaire de convocation pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de générer une convocation.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:convocation_liste')
    
    if request.method == 'POST':
        # Traiter le formulaire et sauvegarder dans la base de données
        objet = request.POST.get('objet', '')
        motif = request.POST.get('motif', '')
        date_convocation_str = request.POST.get('date_convocation', '')
        heure_convocation_str = request.POST.get('heure_convocation', '')
        lieu = request.POST.get('lieu', 'Bureau du Directeur')
        
        # Validation simple
        if not all([objet, motif, date_convocation_str, heure_convocation_str]):
            messages.error(request, "Veuillez remplir tous les champs obligatoires.")
            context = {
                'etablissement': etablissement,
                'eleve': eleve,
                'form_data': request.POST,
                'annee_scolaire_active': annee_scolaire_active,
            }
            return render(request, 'school_admin/directeur/formulaire_convocation.html', context)
        
        try:
            # Convertir les chaînes en objets date et time
            from datetime import datetime as dt
            date_convocation = dt.strptime(date_convocation_str, '%Y-%m-%d').date()
            heure_convocation = dt.strptime(heure_convocation_str, '%H:%M').time()
            
            # Créer et sauvegarder la convocation avec l'année scolaire active
            from ..model.convocation_model import Convocation
            convocation = Convocation.objects.create(
                eleve=eleve,
                etablissement=etablissement,
                objet=objet,
                motif=motif,
                date_convocation=date_convocation,
                heure_convocation=heure_convocation,
                lieu=lieu,
                statut='en_attente',
                annee_scolaire=annee_scolaire_active
            )

            EleveNotificationService.notify_convocation(convocation)
            ParentNotificationService.notify_convocation(convocation)
            
            messages.success(request, "Convocation créée avec succès.")
            return redirect('directeur:voir_convocations_eleve', eleve_id=eleve_id)
            
        except ValueError as e:
            messages.error(request, f"Erreur dans le format de la date ou de l'heure: {e}")
            context = {
                'etablissement': etablissement,
                'eleve': eleve,
                'form_data': request.POST,
            }
            return render(request, 'school_admin/directeur/formulaire_convocation.html', context)
    
    # Afficher le formulaire
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/formulaire_convocation.html', context)


@login_required
def voir_convocations_eleve(request, eleve_id):
    """
    Affiche toutes les convocations d'un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from ..model.convocation_model import Convocation
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Toutes les convocations sont affichées.")
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer toutes les convocations de l'élève filtrées par année scolaire active
    convocations = Convocation.objects.filter(
        eleve=eleve,
        actif=True
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        convocations = convocations.filter(annee_scolaire=annee_scolaire_active)
    
    convocations = convocations.order_by('-date_convocation', '-heure_convocation')
    
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'convocations': convocations,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/voir_convocations_eleve.html', context)


@login_required
def apercu_convocation(request, convocation_id):
    """
    Génère l'aperçu de la convocation pour impression
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.convocation_model import Convocation
    from datetime import datetime
    
    try:
        convocation = Convocation.objects.select_related('eleve', 'eleve__classe').get(
            id=convocation_id,
            etablissement=etablissement
        )
    except Convocation.DoesNotExist:
        messages.error(request, "Convocation non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer l'année scolaire active ou utiliser celle de la convocation
    from ..utils.session_utils import get_session_active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    # Utiliser l'année scolaire de la convocation si disponible, sinon celle active
    annee_scolaire_display = convocation.annee_scolaire.libelle if convocation.annee_scolaire else (
        annee_scolaire_active.libelle if annee_scolaire_active else 'N/A'
    )
    
    # Informations pour la convocation
    context = {
        'etablissement': etablissement,
        'eleve': convocation.eleve,
        'convocation': convocation,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_display,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/apercu_convocation.html', context)


@login_required
def convocation_classe(request, classe_id):
    """
    Formulaire pour convoquer toute une classe
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.convocation_model import Convocation
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de générer des convocations.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer tous les élèves de la classe filtrés par année scolaire active
    eleves = Eleve.objects.filter(
        classe=classe,
        etablissement=etablissement,
        actif=True
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        eleves_ids = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire_active
        ).values_list('eleve_id', flat=True)
        eleves = eleves.filter(id__in=eleves_ids)
    
    eleves = eleves.order_by('nom', 'prenom')
    
    if request.method == 'POST':
        # Traiter le formulaire et créer les convocations pour tous les élèves
        objet = request.POST.get('objet', '')
        motif = request.POST.get('motif', '')
        date_convocation_str = request.POST.get('date_convocation', '')
        heure_convocation_str = request.POST.get('heure_convocation', '')
        lieu = request.POST.get('lieu', 'Bureau du Directeur')
        
        # Validation simple
        if not all([objet, motif, date_convocation_str, heure_convocation_str]):
            messages.error(request, "Veuillez remplir tous les champs obligatoires.")
            context = {
                'etablissement': etablissement,
                'classe': classe,
                'eleves': eleves,
                'nombre_eleves': eleves.count(),
                'form_data': request.POST,
                'annee_scolaire_active': annee_scolaire_active,
            }
            return render(request, 'school_admin/directeur/formulaire_convocation_classe.html', context)
        
        try:
            # Convertir les chaînes en objets date et time
            from datetime import datetime as dt
            date_convocation = dt.strptime(date_convocation_str, '%Y-%m-%d').date()
            heure_convocation = dt.strptime(heure_convocation_str, '%H:%M').time()
            
            # Créer les convocations pour tous les élèves de la classe avec l'année scolaire active
            convocations_creees = []
            for eleve in eleves:
                convocation = Convocation.objects.create(
                    eleve=eleve,
                    etablissement=etablissement,
                    objet=objet,
                    motif=motif,
                    date_convocation=date_convocation,
                    heure_convocation=heure_convocation,
                    lieu=lieu,
                    statut='en_attente',
                    convocation_classe=True,  # Marquer comme convocation de classe
                    annee_scolaire=annee_scolaire_active
                )
                convocations_creees.append(convocation)
                EleveNotificationService.notify_convocation(convocation)
                ParentNotificationService.notify_convocation(convocation)
            
            messages.success(request, f"{len(convocations_creees)} convocation(s) créée(s) avec succès pour la classe {classe.nom}.")
            return redirect('directeur:convocations_classe_liste', classe_id=classe_id)
            
        except ValueError as e:
            messages.error(request, f"Erreur dans le format de la date ou de l'heure: {e}")
            context = {
                'etablissement': etablissement,
                'classe': classe,
                'eleves': eleves,
                'nombre_eleves': eleves.count(),
                'form_data': request.POST,
                'annee_scolaire_active': annee_scolaire_active,
            }
            return render(request, 'school_admin/directeur/formulaire_convocation_classe.html', context)
    
    # Afficher le formulaire
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'annee_scolaire_active': annee_scolaire_active,
        'eleves': eleves,
        'nombre_eleves': eleves.count(),
    }
    
    return render(request, 'school_admin/directeur/formulaire_convocation_classe.html', context)


@login_required
def convocations_classe_liste(request, classe_id):
    """
    Affiche toutes les convocations de classe (regroupées par convocation, pas par élève)
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.convocation_model import Convocation
    from ..utils.session_utils import get_session_active
    from collections import defaultdict
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Toutes les convocations sont affichées.")
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer toutes les convocations de classe pour cette classe filtrées par année scolaire active
    # On regroupe par (objet, motif, date, heure, lieu) pour éviter les doublons
    convocations_classe = Convocation.objects.filter(
        eleve__classe=classe,
        etablissement=etablissement,
        actif=True,
        convocation_classe=True
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        convocations_classe = convocations_classe.filter(annee_scolaire=annee_scolaire_active)
    
    convocations_classe = convocations_classe.select_related('eleve').order_by('-date_convocation', '-heure_convocation')
    
    # Regrouper les convocations identiques (même objet, date, heure, lieu)
    convocations_groupees = {}
    for conv in convocations_classe:
        cle = f"{conv.objet}_{conv.date_convocation}_{conv.heure_convocation}_{conv.lieu}"
        if cle not in convocations_groupees:
            convocations_groupees[cle] = {
                'convocation': conv,
                'eleves': [],
                'nombre_eleves': 0
            }
        convocations_groupees[cle]['eleves'].append(conv.eleve)
        convocations_groupees[cle]['nombre_eleves'] += 1
    
    # Convertir en liste pour le template
    convocations_list = list(convocations_groupees.values())
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'convocations': convocations_list,
        'nombre_convocations': len(convocations_list),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/convocations_classe_liste.html', context)


@login_required
def imprimer_convocations_classe(request, classe_id):
    """
    Imprime toutes les convocations de classe d'une seule session (toutes les convocations d'une même date/heure)
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.convocation_model import Convocation
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'imprimer les convocations.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer l'ID de la convocation depuis les paramètres GET
    convocation_id = request.GET.get('convocation_id')
    
    if not convocation_id:
        messages.error(request, "ID de convocation manquant.")
        return redirect('directeur:convocations_classe_liste', classe_id=classe_id)
    
    try:
        # Récupérer la convocation de référence filtrée par année scolaire active
        convocation_ref = Convocation.objects.get(
            id=convocation_id,
            actif=True,
            convocation_classe=True,
            annee_scolaire=annee_scolaire_active
        )
        
        # Récupérer toutes les convocations identiques (même objet, date, heure, lieu) filtrées par année scolaire active
        convocations = Convocation.objects.filter(
            eleve__classe=classe,
            etablissement=etablissement,
            actif=True,
            convocation_classe=True,
            objet=convocation_ref.objet,
            date_convocation=convocation_ref.date_convocation,
            heure_convocation=convocation_ref.heure_convocation,
            lieu=convocation_ref.lieu,
            annee_scolaire=annee_scolaire_active
        ).select_related('eleve', 'eleve__classe').order_by('eleve__nom', 'eleve__prenom')
        
    except Convocation.DoesNotExist:
        messages.error(request, "Convocation non trouvée.")
        return redirect('directeur:convocations_classe_liste', classe_id=classe_id)
    
    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'convocations': convocations,
        'convocation_ref': convocation_ref,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/imprimer_convocations_classe.html', context)


@login_required
def attestation_reussite_liste(request):
    """
    Page listant tous les élèves pour générer des attestations de réussite
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Les élèves affichés ne sont pas filtrés par session.")
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/attestation_conduite_liste.html', context)


@login_required
def generer_attestation_reussite(request, eleve_id):
    """
    Génère une attestation de réussite pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. L'attestation sera générée sans référence à une session spécifique.")
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:attestation_reussite_liste')
    
    # Informations pour l'attestation
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_active.libelle if annee_scolaire_active else 'N/A',
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/generer_attestation_reussite.html', context)


@login_required
def attestation_conduite_liste(request):
    """
    Page listant tous les élèves pour générer des attestations de conduite
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Filtrer les élèves par année scolaire active si disponible
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/attestation_conduite_liste.html', context)


@login_required
def generer_attestation_conduite(request, eleve_id):
    """
    Génère une attestation de conduite pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. L'attestation sera générée sans référence à une session spécifique.")
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:attestation_conduite_liste')
    
    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    # Informations pour l'attestation
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/generer_attestation_conduite.html', context)


@login_required
def fiche_inscription_liste(request):
    """
    Page listant tous les élèves pour générer des fiches d'inscription/réinscription
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    import re
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Les élèves affichés ne sont pas filtrés par session.")
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/fiche_inscription_liste.html', context)


@login_required
def generer_fiche_inscription(request, eleve_id):
    """
    Génère une fiche d'inscription/réinscription pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. La fiche sera générée sans référence à une session spécifique.")
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:fiche_inscription_liste')
    
    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    # Informations pour la fiche
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/generer_fiche_inscription.html', context)


@login_required
def imprimer_fiches_classe(request, classe_id):
    """
    Génère toutes les fiches d'inscription pour une classe entière
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'imprimer les fiches d'inscription.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:fiche_inscription_liste')
    
    # Filtrer les élèves par année scolaire active via InscriptionEleve
    eleves_ids_inscrits = InscriptionEleve.objects.filter(
        annee_scolaire=annee_scolaire_active,
        classe=classe,
        etablissement=etablissement
    ).values_list('eleve_id', flat=True)
    
    # Récupérer tous les élèves de la classe filtrés par année scolaire active
    eleves = Eleve.objects.filter(
        id__in=eleves_ids_inscrits,
        classe=classe,
        actif=True
    ).order_by('nom', 'prenom')
    
    if not eleves.exists():
        messages.warning(request, "Aucun élève inscrit dans cette classe pour l'année scolaire active.")
        return redirect('directeur:fiche_inscription_liste')
    
    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleves': eleves,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/imprimer_fiches_classe.html', context)


@login_required
def certificat_radiation_liste(request):
    """
    Page listant tous les élèves pour générer des certificats de radiation/transfert
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..utils.session_utils import get_session_active
    import re
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "CE1", "CE2", etc.
        else:
            categorie = nom
        
        # Initialiser la catégorie si elle n'existe pas
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'classes': [],
                'total_eleves': 0
            }
        
        # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
        eleves = _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire_active)
        
        classe_data = {
            'classe': classe,
            'eleves': eleves,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_data)
        classes_grouped[categorie]['total_eleves'] += eleves.count()
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': dict(classes_grouped),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/certificat_radiation_liste.html', context)


@login_required
def generer_certificat_radiation(request, eleve_id):
    """
    Génère un certificat de radiation/transfert pour un élève
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.eleve_model import Eleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Le certificat sera généré sans référence à une session spécifique.")
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:certificat_radiation_liste')
    
    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    # Informations pour le certificat
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/generer_certificat_radiation.html', context)


@login_required
def imprimer_liste_nominative(request, classe_id):
    """
    Génère une liste nominative imprimable des élèves d'une classe
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'imprimer la liste nominative.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:liste_eleves')
    
    # Filtrer les élèves par année scolaire active via InscriptionEleve
    eleves_ids_inscrits = InscriptionEleve.objects.filter(
        annee_scolaire=annee_scolaire_active,
        classe=classe,
        etablissement=etablissement
    ).values_list('eleve_id', flat=True)
    
    # Récupérer tous les élèves de la classe filtrés par année scolaire active
    eleves = Eleve.objects.filter(
        id__in=eleves_ids_inscrits,
        classe=classe,
        actif=True
    ).order_by('nom', 'prenom')
    
    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleves': eleves,
        'date_generation': datetime.now(),
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
        'nombre_eleves': eleves.count(),
    }
    
    return render(request, 'school_admin/directeur/imprimer_liste_nominative.html', context)


@login_required
def imprimer_liste_presence(request, classe_id, mois_numero, mois_annee):
    """
    Génère une liste de présence imprimable pour une classe et un mois donné
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.presence_model import Presence
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..utils.session_utils import get_session_active
    from datetime import datetime
    from django.db.models import Q
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'imprimer la liste de présence.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:suivi_presence')
    
    # Créer un objet mois avec les informations
    date_mois = datetime(mois_annee, mois_numero, 1)
    mois = {
        'numero': mois_numero,
        'annee': mois_annee,
        'nom': date_mois.strftime('%B').capitalize(),
    }
    
    # Filtrer les élèves par année scolaire active via InscriptionEleve
    eleves_ids_inscrits = InscriptionEleve.objects.filter(
        annee_scolaire=annee_scolaire_active,
        classe=classe,
        etablissement=etablissement
    ).values_list('eleve_id', flat=True)
    
    # Récupérer tous les élèves de la classe filtrés par année scolaire active
    eleves = Eleve.objects.filter(
        id__in=eleves_ids_inscrits,
        classe=classe,
        actif=True
    ).order_by('nom', 'prenom')
    
    # Calculer les statistiques de présence pour chaque élève filtrées par année scolaire active
    eleves_presences = []
    
    for eleve in eleves:
        presences = Presence.objects.filter(
            eleve=eleve,
            classe=classe,
            date__month=mois_numero,
            date__year=mois_annee,
            annee_scolaire=annee_scolaire_active
        )
        
        total_jours = presences.count()
        presents = presences.filter(statut='present').count()
        absents = presences.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
        absents_justifies = presences.filter(statut='absent_justifie').count()
        retards = presences.filter(statut='retard').count()
        
        # Calculer le taux de présence
        if total_jours > 0:
            taux_presence = (presents / total_jours) * 100
        else:
            taux_presence = 0
        
        eleves_presences.append({
            'eleve': eleve,
            'total_jours': total_jours,
            'presents': presents,
            'absents': absents,
            'absents_justifies': absents_justifies,
            'retards': retards,
            'taux_presence': round(taux_presence, 2)
        })
    
    # Trier par taux de présence décroissant
    eleves_presences.sort(key=lambda x: x['taux_presence'], reverse=True)
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'mois': mois,
        'eleves_presences': eleves_presences,
        'date_generation': datetime.now(),
        'nombre_eleves': len(eleves_presences),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/imprimer_liste_presence.html', context)


def demandes_liaison_liste(request):
    """
    Liste des demandes de liaison parent-enfant pour le directeur
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Toutes les demandes sont affichées.")
    
    # Récupérer toutes les demandes pour les élèves de cet établissement filtrées par année scolaire active
    demandes = DemandeLiaisonParent.objects.filter(
        eleve_valide__etablissement=etablissement
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        demandes = demandes.filter(annee_scolaire=annee_scolaire_active)
    
    demandes = demandes.select_related(
        'parent_demandeur',
        'eleve_valide',
        'eleve_valide__classe',
        'traite_par'
    ).order_by('-date_demande')
    
    # Compter les demandes par statut
    stats = {
        'total': demandes.count(),
        'en_attente': demandes.filter(statut='en_attente').count(),
        'bloquee': demandes.filter(statut='bloquee').count(),
        'reussie': demandes.filter(statut='reussie').count(),
        'echec': demandes.filter(statut='echec').count(),
        'approuvee': demandes.filter(statut='approuvee').count(),
        'refusee': demandes.filter(statut='refusee').count(),
    }
    
    context = {
        'etablissement': etablissement,
        'demandes': demandes,
        'stats': stats,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/demandes_liaison_liste.html', context)


def approuver_demande_liaison(request, demande_id):
    """
    Approuver une demande de liaison parent-enfant
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer la demande
    demande = get_object_or_404(
        DemandeLiaisonParent,
        id=demande_id,
        eleve_valide__etablissement=etablissement
    )
    
    try:
        # Vérifier si un lien existe déjà
        # Vérifier si un LienFamilial existe déjà (actif ou non)
        lien_existant = LienFamilial.objects.filter(
            parent=demande.parent_demandeur,
            eleve=demande.eleve_valide
        ).first()
        
        if lien_existant:
            # Le lien existe déjà, on le réactive s'il était désactivé
            if not lien_existant.actif:
                lien_existant.actif = True
                lien_existant.statut = 'valide'
                lien_existant.save()
                print(f"[APPROBATION] Lien réactivé - Parent: {demande.parent_demandeur.nom_complet}, Élève: {demande.eleve_valide.nom_complet}")
            
            # Mettre à jour le statut de la demande
            demande.statut = 'approuvee'
            demande.date_traitement = timezone.now()
            demande.save()
            
            messages.success(
                request,
                f"✅ Demande approuvée avec succès ! Le lien entre {demande.parent_demandeur.nom_complet} et {demande.eleve_valide.nom_complet} a été créé."
            )
        else:
            # Si la demande est bloquée, la remettre en attente temporairement
            if demande.statut == 'bloquee':
                demande.statut = 'en_attente'
                demande.save()
            
            # Approuver la demande et créer le lien
            lien = demande.approuver(traite_par=None)
            demande.statut = 'approuvee'
            demande.save()
            
            messages.success(
                request,
                f"✅ Demande approuvée avec succès ! Le lien entre {demande.parent_demandeur.nom_complet} et {demande.eleve_valide.nom_complet} a été créé."
            )
    except Exception as e:
        messages.error(request, f"❌ Erreur lors de l'approbation : {str(e)}")
    
    return redirect('directeur:demandes_liaison_liste')


def rejeter_demande_liaison(request, demande_id):
    """
    Rejeter une demande de liaison parent-enfant
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer la demande
    demande = get_object_or_404(
        DemandeLiaisonParent,
        id=demande_id,
        eleve_valide__etablissement=etablissement
    )
    
    try:
        # Rejeter la demande
        motif = request.POST.get('motif_refus', 'Demande refusée par l\'établissement')
        demande.refuser(traite_par=None, motif=motif)
        demande.statut = 'refusee'
        demande.motif_refus = motif
        demande.save()
        
        messages.success(
            request,
            f"✅ Demande rejetée. Le parent {demande.parent_demandeur.nom_complet} sera notifié."
        )
    except Exception as e:
        messages.error(request, f"❌ Erreur lors du rejet : {str(e)}")
    
    return redirect('directeur:demandes_liaison_liste')


def desapprouver_demande_liaison(request, demande_id):
    """
    Désapprouver une demande de liaison parent-enfant
    Supprime le lien familial et remet la demande en attente
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer la demande
    demande = get_object_or_404(
        DemandeLiaisonParent,
        id=demande_id,
        eleve_valide__etablissement=etablissement
    )
    
    try:
        # Vérifier que la demande a été approuvée ou réussie
        if demande.statut not in ['reussie', 'approuvee']:
            messages.warning(request, "Cette demande n'a pas été approuvée.")
            return redirect('directeur:demandes_liaison_liste')
        
        # Supprimer le lien familial correspondant
        lien = LienFamilial.objects.filter(
            parent=demande.parent_demandeur,
            eleve=demande.eleve_valide,
            actif=True
        ).first()
        
        if lien:
            lien.actif = False
            lien.save()
            print(f"[DÉSAPPROBATION] Lien désactivé - Parent: {demande.parent_demandeur.nom_complet}, Élève: {demande.eleve_valide.nom_complet}")
        
        # Remettre la demande en attente
        demande.statut = 'en_attente'
        demande.date_traitement = None
        demande.save()
        
        messages.success(
            request,
            f"✅ La liaison entre {demande.parent_demandeur.nom_complet} et {demande.eleve_valide.nom_complet} a été désapprouvée."
        )
    except Exception as e:
        messages.error(request, f"❌ Erreur lors de la désapprobation : {str(e)}")
    
    return redirect('directeur:demandes_liaison_liste')


@login_required
@login_required
@require_permission('annonces_voir')
def annonces_directeur(request):
    """
    Vue pour la gestion des annonces par le directeur
    """
    result = _get_user_etablissement(request, 'annonces_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.annonce_model import Annonce
    from ..utils.session_utils import get_session_active
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Toutes les annonces sont affichées.")
    
    # Récupérer toutes les annonces de l'établissement filtrées par année scolaire active
    annonces = Annonce.objects.filter(
        etablissement=etablissement,
        actif=True
    )
    
    # Filtrer par année scolaire active si disponible
    if annee_scolaire_active:
        annonces = annonces.filter(annee_scolaire=annee_scolaire_active)
    
    annonces = annonces.order_by('-date_publication', '-date_creation')
    
    # Filtrer par statut si demandé
    statut_filtre = request.GET.get('statut', '')
    if statut_filtre:
        annonces = annonces.filter(statut=statut_filtre)
    
    # Statistiques
    total_annonces = annonces.count()
    annonces_publiees = annonces.filter(statut='publiee').count()
    annonces_brouillon = annonces.filter(statut='brouillon').count()
    annonces_archivees = annonces.filter(statut='archivee').count()
    
    from ..model.personnel_administratif_model import PersonnelAdministratif
    context = {
        'annonces': annonces,
        'total_annonces': total_annonces,
        'annonces_publiees': annonces_publiees,
        'annonces_brouillon': annonces_brouillon,
        'annonces_archivees': annonces_archivees,
        'statut_filtre': statut_filtre,
        'annee_scolaire_active': annee_scolaire_active,
        'etablissement': etablissement,
        'is_directeur': is_directeur,
        'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
        'personnel': personnel,
    }
    
    return render(request, 'school_admin/directeur/annonces/liste_annonces.html', context)


@login_required
def creer_annonce(request):
    """
    Vue pour créer une nouvelle annonce
    """
    result = _get_user_etablissement(request, 'annonces_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.annonce_model import Annonce
    from ..utils.session_utils import get_session_active
    
    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire
            titre = request.POST.get('titre', '').strip()
            contenu = request.POST.get('contenu', '').strip()
            # Récupérer tous les destinataires sélectionnés (liste)
            destinataires = request.POST.getlist('destinataires')
            if not destinataires:
                destinataires = ['tous']  # Par défaut si aucun n'est sélectionné
            action = request.POST.get('action', 'brouillon')  # brouillon ou publier
            fichier_joint = request.FILES.get('fichier_joint', None)
            
            # Validation
            if not titre:
                messages.error(request, "Le titre est obligatoire.")
                return redirect('directeur:creer_annonce')
            
            if not contenu:
                messages.error(request, "Le contenu est obligatoire.")
                return redirect('directeur:creer_annonce')
            
            # Récupérer l'année scolaire active pour l'établissement
            annee_scolaire_active = _get_session_directeur(request, etablissement)
            
            # Créer l'annonce
            annonce = Annonce.objects.create(
                etablissement=etablissement,
                auteur_directeur=etablissement,
                titre=titre,
                contenu=contenu,
                destinataires=destinataires,
                fichier_joint=fichier_joint,
                statut='brouillon',
                annee_scolaire=annee_scolaire_active  # Associer automatiquement l'année scolaire active
            )
            
            # Publier si demandé
            if action == 'publier':
                annonce.publier()
                messages.success(request, f"✅ L'annonce '{titre}' a été créée et publiée avec succès.")
            else:
                messages.success(request, f"✅ L'annonce '{titre}' a été enregistrée en brouillon.")
            
            return redirect('directeur:annonces_directeur')
            
        except Exception as e:
            messages.error(request, f"❌ Erreur lors de la création de l'annonce : {str(e)}")
            return redirect('directeur:creer_annonce')
    
    # GET : Afficher le formulaire
    # Récupérer l'année scolaire active pour l'affichage
    annee_scolaire_active = _get_session_directeur(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. L'annonce sera créée sans référence à une session spécifique.")
    
    from ..model.personnel_administratif_model import PersonnelAdministratif
    context = {
        'destinataires_choices': Annonce.DESTINATAIRES_CHOICES,
        'annee_scolaire_active': annee_scolaire_active,
        'etablissement': etablissement,
        'is_directeur': is_directeur,
        'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
        'personnel': personnel,
    }
    
    return render(request, 'school_admin/directeur/annonces/creer_annonce.html', context)


@login_required
def modifier_annonce(request, annonce_id):
    """
    Vue pour modifier une annonce existante
    """
    result = _get_user_etablissement(request, 'annonces_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.annonce_model import Annonce
    
    # Récupérer l'annonce
    annonce = get_object_or_404(
        Annonce,
        id=annonce_id,
        etablissement=etablissement,
        actif=True
    )
    
    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire
            titre = request.POST.get('titre', '').strip()
            contenu = request.POST.get('contenu', '').strip()
            # Récupérer tous les destinataires sélectionnés (liste)
            destinataires = request.POST.getlist('destinataires')
            if not destinataires:
                destinataires = ['tous']  # Par défaut si aucun n'est sélectionné
            action = request.POST.get('action', 'enregistrer')
            
            # Validation
            if not titre:
                messages.error(request, "Le titre est obligatoire.")
                return redirect('directeur:modifier_annonce', annonce_id=annonce_id)
            
            if not contenu:
                messages.error(request, "Le contenu est obligatoire.")
                return redirect('directeur:modifier_annonce', annonce_id=annonce_id)
            
            # Mettre à jour l'annonce
            annonce.titre = titre
            annonce.contenu = contenu
            annonce.destinataires = destinataires
            
            # Gérer le fichier joint
            if request.FILES.get('fichier_joint'):
                annonce.fichier_joint = request.FILES.get('fichier_joint')
            
            # Supprimer le fichier si demandé
            if request.POST.get('supprimer_fichier') == 'true':
                annonce.fichier_joint.delete(save=False)
                annonce.fichier_joint = None
            
            annonce.save()
            
            # Publier si demandé
            if action == 'publier' and annonce.statut == 'brouillon':
                annonce.publier()
                messages.success(request, f"✅ L'annonce '{titre}' a été modifiée et publiée.")
            else:
                messages.success(request, f"✅ L'annonce '{titre}' a été modifiée avec succès.")
            
            return redirect('directeur:annonces_directeur')
            
        except Exception as e:
            messages.error(request, f"❌ Erreur lors de la modification : {str(e)}")
            return redirect('directeur:modifier_annonce', annonce_id=annonce_id)
    
    # GET : Afficher le formulaire
    from ..model.personnel_administratif_model import PersonnelAdministratif
    context = {
        'annonce': annonce,
        'destinataires_choices': Annonce.DESTINATAIRES_CHOICES,
        'etablissement': etablissement,
        'is_directeur': is_directeur,
        'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
        'personnel': personnel,
    }
    
    return render(request, 'school_admin/directeur/annonces/modifier_annonce.html', context)


@login_required
def apercu_annonce(request, annonce_id):
    """
    Vue pour prévisualiser une annonce avant publication
    """
    result = _get_user_etablissement(request, 'annonces_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.annonce_model import Annonce
    
    # Récupérer l'annonce
    annonce = get_object_or_404(
        Annonce,
        id=annonce_id,
        etablissement=etablissement,
        actif=True
    )
    
    from ..model.personnel_administratif_model import PersonnelAdministratif
    context = {
        'annonce': annonce,
        'etablissement': etablissement,
        'is_directeur': is_directeur,
        'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
        'personnel': personnel,
    }
    
    return render(request, 'school_admin/directeur/annonces/apercu_annonce.html', context)


@login_required
def imprimer_annonce(request, annonce_id):
    """
    Vue pour imprimer une annonce avec un design professionnel
    """
    result = _get_user_etablissement(request, 'annonces_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.annonce_model import Annonce
    from datetime import date
    
    # Récupérer l'annonce
    annonce = get_object_or_404(
        Annonce,
        id=annonce_id,
        etablissement=etablissement,
        actif=True
    )
    
    # Date actuelle pour l'en-tête
    aujourdhui = date.today()
    # Format français : "15 janvier 2025"
    mois_fr = {
        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
        5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
        9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
    }
    date_formatee = f"{aujourdhui.day} {mois_fr[aujourdhui.month]} {aujourdhui.year}"
    
    from ..model.personnel_administratif_model import PersonnelAdministratif
    context = {
        'annonce': annonce,
        'etablissement': etablissement,
        'date_formatee': date_formatee,
        'aujourdhui': aujourdhui,
        'is_directeur': is_directeur,
        'is_personnel_administratif': isinstance(request.user, PersonnelAdministratif),
        'personnel': personnel,
    }
    
    return render(request, 'school_admin/directeur/annonces/imprimer_annonce.html', context)


@login_required
def publier_annonce(request, annonce_id):
    """
    Vue pour publier une annonce en brouillon
    """
    result = _get_user_etablissement(request, 'annonces_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.annonce_model import Annonce
    
    if request.method == 'POST':
        try:
            # Récupérer l'annonce
            annonce = get_object_or_404(
                Annonce,
                id=annonce_id,
                etablissement=etablissement,
                actif=True
            )
            
            # Publier l'annonce
            annonce.publier()
            messages.success(request, f"✅ L'annonce '{annonce.titre}' a été publiée avec succès.")
            
        except Exception as e:
            messages.error(request, f"❌ Erreur lors de la publication : {str(e)}")
    
    return redirect('directeur:annonces_directeur')


@login_required
def archiver_annonce(request, annonce_id):
    """
    Vue pour archiver une annonce publiée
    """
    result = _get_user_etablissement(request, 'annonces_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.annonce_model import Annonce
    
    if request.method == 'POST':
        try:
            # Récupérer l'annonce
            annonce = get_object_or_404(
                Annonce,
                id=annonce_id,
                etablissement=etablissement,
                actif=True
            )
            
            # Archiver l'annonce
            annonce.archiver()
            messages.success(request, f"✅ L'annonce '{annonce.titre}' a été archivée.")
            
        except Exception as e:
            messages.error(request, f"❌ Erreur lors de l'archivage : {str(e)}")
    
    return redirect('directeur:annonces_directeur')


@login_required
def supprimer_annonce(request, annonce_id):
    """
    Vue pour supprimer définitivement une annonce
    """
    result = _get_user_etablissement(request, 'annonces_voir')
    if result[0] is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    
    etablissement, is_directeur, personnel = result
    from ..model.annonce_model import Annonce
    
    if request.method == 'POST':
        try:
            # Récupérer l'annonce
            annonce = get_object_or_404(
                Annonce,
                id=annonce_id,
                etablissement=etablissement,
                actif=True
            )
            
            titre = annonce.titre
            
            # Supprimer le fichier joint s'il existe
            if annonce.fichier_joint:
                annonce.fichier_joint.delete(save=False)
            
            # Supprimer l'annonce (soft delete)
            annonce.actif = False
            annonce.save()
            
            messages.success(request, f"✅ L'annonce '{titre}' a été supprimée.")
            
        except Exception as e:
            messages.error(request, f"❌ Erreur lors de la suppression : {str(e)}")
    
    return redirect('directeur:annonces_directeur')


@login_required
def profil_etablissement(request):
    """Page de profil et de configuration de l'établissement."""
    from ..model.personnel_administratif_model import PersonnelAdministratif
    
    user = request.user
    is_personnel = isinstance(user, PersonnelAdministratif)
    is_directeur = isinstance(user, Etablissement)
    
    # Si c'est un membre du personnel, on affiche ses informations personnelles
    if is_personnel:
        personnel = user
        etablissement = personnel.etablissement
    elif is_directeur:
        etablissement = user
        personnel = None
    else:
        return redirect('school_admin:connexion_compte_user')
    success_message = None
    
    # Récupérer l'onglet actif depuis POST ou GET
    active_tab = request.POST.get('active_tab') or request.GET.get('tab', 'informations')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'update_information':
            fields = {
                'nom': request.POST.get('nom', etablissement.nom).strip(),
                'type_etablissement': request.POST.get('type_etablissement', etablissement.type_etablissement),
                'adresse': request.POST.get('adresse', etablissement.adresse).strip(),
                'pays': request.POST.get('pays', etablissement.pays).strip(),
                'ville': request.POST.get('ville', etablissement.ville).strip(),
                'email': request.POST.get('email', etablissement.email).strip(),
                'telephone': request.POST.get('telephone') or None,
                'directeur_prenom': request.POST.get('directeur_prenom', etablissement.directeur_prenom).strip(),
                'directeur_nom': request.POST.get('directeur_nom', etablissement.directeur_nom).strip(),
                'directeur_email': request.POST.get('directeur_email', etablissement.directeur_email).strip(),
                'directeur_telephone': request.POST.get('directeur_telephone') or None,
            }

            for attr, value in fields.items():
                setattr(etablissement, attr, value)

            try:
                etablissement.full_clean()
            except ValidationError as exc:
                for field_errors in exc.message_dict.values():
                    for error in field_errors:
                        messages.error(request, error)
            else:
                etablissement.save(update_fields=list(fields.keys()) + ['date_modification'])
                success_message = "Informations mises à jour avec succès."

        elif form_type == 'update_logo':
            # Seul le directeur peut modifier le logo
            if not is_directeur:
                messages.error(request, "Vous n'avez pas l'autorisation de modifier le logo.")
            else:
                logo_file = request.FILES.get('logo')
                if logo_file:
                    max_size_bytes = 20 * 1024 * 1024  # 20 MB
                    if logo_file.size > max_size_bytes:
                        messages.error(request, "Le fichier sélectionné dépasse la taille maximale autorisée de 20 Mo.")
                    else:
                        if etablissement.logo:
                            etablissement.logo.delete(save=False)
                        etablissement.logo = logo_file
                        etablissement.save(update_fields=['logo', 'date_modification'])
                        success_message = "Logo mis à jour avec succès."
                else:
                    messages.error(request, "Veuillez sélectionner un fichier image valide pour le logo.")

        elif form_type == 'delete_logo':
            # Seul le directeur peut supprimer le logo
            if not is_directeur:
                messages.error(request, "Vous n'avez pas l'autorisation de supprimer le logo.")
            else:
                if etablissement.logo:
                    etablissement.logo.delete(save=False)
                    etablissement.logo = None
                    etablissement.save(update_fields=['logo', 'date_modification'])
                    success_message = "Logo supprimé avec succès."
                else:
                    messages.info(request, "Aucun logo n'est actuellement défini.")

        elif form_type == 'update_password':
            current_password = request.POST.get('current_password', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()
            
            # Validation des champs obligatoires
            validation_errors = []
            
            if not current_password:
                validation_errors.append("Le mot de passe actuel est obligatoire.")
            
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
                for error in validation_errors:
                    messages.error(request, error)
            else:
                # Gérer le changement de mot de passe pour directeur ou personnel
                if is_personnel:
                    # Vérifier le mot de passe actuel
                    if not personnel.check_password(current_password):
                        messages.error(request, "Le mot de passe actuel est incorrect.")
                    else:
                        # Changer le mot de passe
                        personnel.set_password(new_password)
                        personnel.save()
                        # Maintenir la session active après changement de mot de passe
                        from django.contrib.auth import update_session_auth_hash
                        update_session_auth_hash(request, personnel)
                        success_message = "Mot de passe mis à jour avec succès."
                elif is_directeur:
                    # Vérifier le mot de passe actuel
                    if not etablissement.check_password(current_password):
                        messages.error(request, "Le mot de passe actuel est incorrect.")
                    else:
                        # Changer le mot de passe
                        etablissement.set_password(new_password)
                        etablissement.save()
                        # Maintenir la session active après changement de mot de passe
                        from django.contrib.auth import update_session_auth_hash
                        update_session_auth_hash(request, etablissement)
                        success_message = "Mot de passe mis à jour avec succès."

        if success_message:
            messages.success(request, success_message)
        # Rediriger vers l'onglet actif
        return redirect(f"{reverse('directeur:profil_etablissement')}?tab={active_tab}")

    # Les modules et la facturation ne sont visibles que pour le directeur
    modules_config = []
    facturation = {}
    
    if is_directeur:
        modules_config = [
            ("Gestion des élèves", etablissement.module_gestion_eleves),
            ("Notes et évaluations", etablissement.module_notes_evaluations),
            ("Emploi du temps", etablissement.module_emploi_temps),
            ("Transport scolaire", etablissement.module_transport_scolaire),
            ("Comptabilité", etablissement.module_comptabilite),
            ("Gestion du personnel", etablissement.module_gestion_personnel),
            ("Censeurs", etablissement.module_censeurs),
            ("Surveillance et sécurité", etablissement.module_surveillance),
            ("Gestion de la cantine", etablissement.module_cantine),
            ("Gestion de la bibliothèque", etablissement.module_bibliotheque),
            ("Communication parents", etablissement.module_communication),
            ("Orientation scolaire", etablissement.module_orientation),
            ("Suivi médical", etablissement.module_sante),
            ("Activités extra-scolaires", etablissement.module_activites),
            ("Formation continue", etablissement.module_formation),
        ]

        facturation = {
            'type': etablissement.type_facturation,
            'montant_par_eleve': etablissement.montant_par_eleve,
            'montant_total_facturation': etablissement.montant_total_facturation,
            'statut': etablissement.statut_paiement,
            'date_derniere_facturation': etablissement.date_derniere_facturation,
            'nombre_eleves_factures': etablissement.nombre_eleves_factures,
        }

    context = {
        'etablissement': etablissement,
        'modules_config': modules_config,
        'facturation': facturation,
        'devise_etablissement': getattr(etablissement, 'devise', None),
        'active_tab': active_tab,
        'is_directeur': is_directeur,
        'is_personnel_administratif': is_personnel,
        'personnel': personnel,
    }

    return render(request, 'school_admin/directeur/mon_profil_etablissement.html', context)


@login_required
def liste_annees_scolaires(request):
    """
    Liste toutes les années scolaires de l'établissement
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..utils.session_utils import get_session_active
    
    annees_scolaires = AnneeScolaire.get_annees_etablissement(etablissement)
    session_active = get_session_active(request, etablissement)
    
    context = {
        'etablissement': etablissement,
        'annees_scolaires': annees_scolaires,
        'session_active': session_active,
    }
    
    return render(request, 'school_admin/directeur/annees_scolaires/liste_annees_scolaires.html', context)


@login_required
def creer_annee_scolaire(request):
    """
    Crée une nouvelle année scolaire
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..controllers.annee_scolaire_controller import AnneeScolaireController
    
    if request.method == 'POST':
        try:
            libelle = request.POST.get('libelle', '').strip()
            annee_debut = int(request.POST.get('annee_debut', 0))
            annee_fin = int(request.POST.get('annee_fin', 0))
            date_debut_str = request.POST.get('date_debut', '')
            date_fin_str = request.POST.get('date_fin', '')
            est_ouverte = request.POST.get('est_ouverte') == 'on'
            
            if not all([libelle, annee_debut, annee_fin, date_debut_str, date_fin_str]):
                messages.error(request, "Veuillez remplir tous les champs obligatoires.")
                return redirect('directeur:creer_annee_scolaire')
            
            from datetime import datetime
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
            
            annee_scolaire = AnneeScolaireController.creer_annee_scolaire(
                etablissement=etablissement,
                libelle=libelle,
                annee_debut=annee_debut,
                annee_fin=annee_fin,
                date_debut=date_debut,
                date_fin=date_fin,
                est_ouverte=est_ouverte
            )
            
            messages.success(request, f"Année scolaire {libelle} créée avec succès.")
            return redirect('directeur:detail_annee_scolaire', annee_id=annee_scolaire.pk)
            
        except ValidationError as e:
            messages.error(request, f"Erreur de validation : {str(e)}")
        except ValueError as e:
            messages.error(request, f"Erreur de format : {str(e)}")
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'année scolaire: {e}", exc_info=True)
            messages.error(request, f"Erreur lors de la création : {str(e)}")
    
    # Suggérer les valeurs par défaut
    suggestions = AnneeScolaireController.get_annee_scolaire_suivante(etablissement)
    
    context = {
        'etablissement': etablissement,
        'suggestions': suggestions,
    }
    
    return render(request, 'school_admin/directeur/annees_scolaires/creer_annee_scolaire.html', context)


@login_required
def activer_annee_scolaire(request, annee_id):
    """
    Active une année scolaire et initialise automatiquement les structures
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..controllers.annee_scolaire_controller import AnneeScolaireController
    from ..utils.session_utils import set_session_consultee
    
    annee_scolaire = get_object_or_404(AnneeScolaire, pk=annee_id, etablissement=etablissement)
    
    try:
        annee_scolaire, stats = AnneeScolaireController.activer_annee_scolaire(
            etablissement, annee_scolaire, initialiser=True
        )
        
        # Définir la session active dans la session utilisateur
        request.session['annee_scolaire_consultee_id'] = annee_scolaire.id
        request.session['school_year_id'] = annee_scolaire.id
        set_session_consultee(request, annee_scolaire)
        
        # Message de succès avec statistiques
        message = f"✅ Année scolaire {annee_scolaire.libelle} activée avec succès."
        if stats:
            message += f" Initialisation : {stats.get('classes_copiees', 0)} classes, {stats.get('matieres_copiees', 0)} matières, {stats.get('salles_copiees', 0)} salles."
        messages.success(request, message)
        
        # Rediriger vers le dashboard
        return redirect('directeur:dashboard_directeur')
        
    except ValidationError as e:
        messages.error(request, f"Erreur : {str(e)}")
    except Exception as e:
        logger.error(f"Erreur lors de l'activation de l'année scolaire: {e}", exc_info=True)
        messages.error(request, f"Erreur lors de l'activation : {str(e)}")
    
    return redirect('directeur:gestion_periodes_scolaires')


@login_required
def detail_annee_scolaire(request, annee_id):
    """
    Affiche les détails d'une année scolaire
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..controllers.annee_scolaire_controller import AnneeScolaireController
    
    annee_scolaire = get_object_or_404(AnneeScolaire, pk=annee_id, etablissement=etablissement)
    statistiques = AnneeScolaireController.get_statistiques_annee(annee_scolaire)
    
    context = {
        'etablissement': etablissement,
        'annee_scolaire': annee_scolaire,
        'statistiques': statistiques,
    }
    
    return render(request, 'school_admin/directeur/annees_scolaires/detail_annee_scolaire.html', context)


@login_required
def modifier_annee_scolaire(request, annee_id):
    """
    Modifie une année scolaire
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..controllers.annee_scolaire_controller import AnneeScolaireController
    from datetime import datetime
    
    annee_scolaire = get_object_or_404(AnneeScolaire, pk=annee_id, etablissement=etablissement)
    
    if request.method == 'POST':
        date_debut_str = request.POST.get('date_debut', '')
        date_fin_str = request.POST.get('date_fin', '')
        est_ouverte = request.POST.get('est_ouverte') == 'on'
        
        if not all([date_debut_str, date_fin_str]):
            messages.error(request, "Veuillez remplir les dates de début et de fin.")
        else:
            try:
                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                
                annee_debut = date_debut.year
                annee_fin = date_fin.year
                
                if annee_fin != annee_debut + 1:
                    messages.error(request, f"L'année scolaire doit couvrir une période d'un an. Année de début: {annee_debut}, Année de fin: {annee_fin}")
                else:
                    libelle = AnneeScolaireController.generer_libelle_annee(annee_debut)
                    
                    # Mettre à jour l'année scolaire
                    annee_scolaire.libelle = libelle
                    annee_scolaire.annee_debut = annee_debut
                    annee_scolaire.annee_fin = annee_fin
                    annee_scolaire.date_debut = date_debut
                    annee_scolaire.date_fin = date_fin
                    annee_scolaire.est_ouverte = est_ouverte
                    annee_scolaire.save()
                    
                    messages.success(request, f"Année scolaire {libelle} modifiée avec succès.")
                    return redirect('directeur:detail_annee_scolaire', annee_id=annee_scolaire.id)
                    
            except Exception as e:
                logger.error(f"Erreur lors de la modification de l'année scolaire: {e}", exc_info=True)
                messages.error(request, f"Erreur lors de la modification : {str(e)}")
    
    context = {
        'etablissement': etablissement,
        'annee_scolaire': annee_scolaire,
    }
    
    return render(request, 'school_admin/directeur/annees_scolaires/modifier_annee_scolaire.html', context)


@login_required
def desactiver_annee_scolaire(request, annee_id):
    """
    Désactive une année scolaire
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    from ..model.annee_scolaire_model import AnneeScolaire
    
    annee_scolaire = get_object_or_404(AnneeScolaire, pk=annee_id, etablissement=etablissement)
    
    if annee_scolaire.est_active:
        annee_scolaire.est_active = False
        annee_scolaire.save()
        
        # Nettoyer la session si c'était la session active
        if request.session.get('school_year_id') == annee_scolaire.id:
            del request.session['school_year_id']
            del request.session['annee_scolaire_consultee_id']
        
        messages.success(request, f"Année scolaire {annee_scolaire.libelle} désactivée avec succès.")
    else:
        messages.info(request, f"L'année scolaire {annee_scolaire.libelle} n'est pas active.")
    
    return redirect('directeur:detail_annee_scolaire', annee_id=annee_scolaire.id)


@login_required
def creer_annee_scolaire_obligatoire(request):
    """
    Vue obligatoire pour créer une année scolaire si aucune n'est active
    Redirige automatiquement vers cette page si aucune année active n'existe
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    from ..model.annee_scolaire_model import AnneeScolaire
    from ..controllers.annee_scolaire_controller import AnneeScolaireController
    from ..utils.session_utils import get_session_active
    
    # Vérifier s'il existe déjà une année active
    annee_active = get_session_active(request, etablissement)
    if annee_active:
        # Si une année active existe, rediriger vers le dashboard
        request.session['annee_scolaire_consultee_id'] = annee_active.id
        request.session['school_year_id'] = annee_active.id
        return redirect('directeur:dashboard_directeur')
    
    # Récupérer toutes les années scolaires existantes
    annees_scolaires = AnneeScolaire.objects.filter(
        etablissement=etablissement
    ).order_by('-annee_debut', '-date_debut')
    
    # Gestion de la création
    if request.method == 'POST':
        from datetime import datetime
        
        date_debut_str = request.POST.get('date_debut', '')
        date_fin_str = request.POST.get('date_fin', '')
        est_ouverte = request.POST.get('est_ouverte') == 'on'
        
        if not all([date_debut_str, date_fin_str]):
            messages.error(request, "Veuillez remplir les dates de début et de fin.")
        else:
            try:
                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                
                annee_debut = date_debut.year
                annee_fin = date_fin.year
                
                if annee_fin != annee_debut + 1:
                    messages.error(request, f"L'année scolaire doit couvrir une période d'un an. Année de début: {annee_debut}, Année de fin: {annee_fin}")
                else:
                    libelle = AnneeScolaireController.generer_libelle_annee(annee_debut)
                    
                    annee_scolaire = AnneeScolaireController.creer_annee_scolaire(
                        etablissement=etablissement,
                        libelle=libelle,
                        annee_debut=annee_debut,
                        annee_fin=annee_fin,
                        date_debut=date_debut,
                        date_fin=date_fin,
                        est_ouverte=est_ouverte
                    )
                    
                    messages.success(request, f"Année scolaire {libelle} créée avec succès. Veuillez l'activer pour continuer.")
                    return redirect('directeur:creer_annee_scolaire_obligatoire')
                    
            except Exception as e:
                messages.error(request, f"Erreur lors de la création : {str(e)}")
    
    # Suggérer la prochaine année scolaire
    suggestion = AnneeScolaireController.get_annee_scolaire_suivante(etablissement)
    
    context = {
        'etablissement': etablissement,
        'annees_scolaires': annees_scolaires,
        'suggestion': suggestion,
        'obligatoire': True,  # Indique que c'est une création obligatoire
    }
    
    return render(request, 'school_admin/directeur/annees_scolaires/creer_annee_scolaire_obligatoire.html', context)