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

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
except ImportError:  # pragma: no cover
    qrcode = None
    ERROR_CORRECT_M = None


logger = logging.getLogger(__name__)


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
    """Retourne le statut (passage, redoublement, accompagnement) en fonction des seuils."""
    if note_decimal is None or standards is None:
        return None, None

    passage = _safe_decimal(standards.moyenne_passage)
    redoublement = _safe_decimal(standards.moyenne_redoublement)
    statut_code = None

    if passage is not None and note_decimal >= passage:
        statut_code = 'passage'
    elif redoublement is not None and note_decimal < redoublement:
        statut_code = 'redoublement'
    elif passage is not None or redoublement is not None:
        statut_code = 'accompagnement'

    if not statut_code:
        return None, None

    passage_str = _format_decimal_value(passage)
    redoublement_str = _format_decimal_value(redoublement)

    if statut_code == 'passage':
        label = (
            f"Passage recommandé (moyenne ≥ {passage_str}/20)"
            if passage_str else "Passage recommandé"
        )
    elif statut_code == 'redoublement':
        label = (
            f"Redoublement recommandé (moyenne < {redoublement_str}/20)"
            if redoublement_str else "Redoublement recommandé"
        )
    else:
        if passage_str and redoublement_str:
            label = (
                f"Accompagnement conseillé ({redoublement_str}/20 ≤ moyenne < {passage_str}/20)"
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

    if standards and statut_code == 'passage':
        appreciation_standard = (
            standards.appreciation_conseil.strip()
            if standards.appreciation_conseil else None
        )
    elif statut_code == 'redoublement':
        appreciation_standard = "Redoublement recommandé"
    elif statut_code == 'accompagnement':
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

    if standards and standards.appreciation_conseil:
        decision_standard = standards.appreciation_conseil.strip()
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
        'moyenne_redoublement': float(standards.moyenne_redoublement) if standards.moyenne_redoublement is not None else None,
        'moyenne_redoublement_display': _format_decimal_value(standards.moyenne_redoublement),
        'appreciation_conseil': standards.appreciation_conseil.strip() if standards.appreciation_conseil else None,
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

    if qrcode:
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

    moyenne_obj.save(update_fields=updated_fields)
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
    Vue du tableau de bord pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les informations de l'établissement
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..model.professeur_model import Professeur
    from ..model.moyenne_model import Moyenne
    from datetime import datetime, timedelta
    
    # === STATISTIQUES DES ÉLÈVES ===
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
        evaluations_semaine = EvaluationPrimaire.objects.filter(
            professeur__etablissement=etablissement,
            date_evaluation__gte=date_debut_semaine,
            actif=True
        ).count()
    else:
        # Pour collège/lycée (0 si pas de modèle Evaluation)
        evaluations_semaine = 0
    
    # === BULLETINS PUBLIÉS ===
    # Compter les moyennes soumises ce trimestre (approximation des bulletins)
    moyennes_soumises = Moyenne.objects.filter(
        eleve__etablissement=etablissement,
        soumis=True,
        actif=True
    ).count()
    
    # === ALERTES ===
    # Compter les élèves avec un taux de présence < 80% ou moyenne < 10
    from ..model.presence_model import Presence
    from django.db.models import Q
    
    alertes_count = 0
    
    # Alertes de présence (élèves avec beaucoup d'absences ce mois)
    date_debut_mois = datetime.now().replace(day=1)
    eleves_avec_absences = 0
    for eleve in eleves[:100]:  # Limiter pour la performance
        absences = Presence.objects.filter(
            eleve=eleve,
            date__gte=date_debut_mois,
            statut__in=['absent', 'absent_justifie']
        ).count()
        if absences >= 5:
            eleves_avec_absences += 1
    
    alertes_count = eleves_avec_absences
    
    # === TAUX DE RÉUSSITE ===
    # Calculer le taux basé sur les moyennes >= 10/20
    moyennes_valides = Moyenne.objects.filter(
        eleve__etablissement=etablissement,
        soumis=True,
        actif=True
    ).exclude(moyenne__isnull=True)
    
    if moyennes_valides.exists():
        moyennes_reussies = moyennes_valides.filter(moyenne__gte=10).count()
        total_moyennes = moyennes_valides.count()
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
    dernieres_moyennes = Moyenne.objects.filter(
        eleve__etablissement=etablissement,
        soumis=True,
        actif=True
    ).select_related('eleve', 'classe', 'matiere').order_by('-date_calcul')[:2]
    
    # === DERNIÈRES ÉVALUATIONS ===
    if etablissement.type_etablissement == 'primary':
        from ..model.evaluation_primaire_model import EvaluationPrimaire
        dernieres_evaluations = EvaluationPrimaire.objects.filter(
            professeur__etablissement=etablissement,
            actif=True
        ).select_related('classe', 'matiere').order_by('-date_evaluation')[:2]
    else:
        from ..model.evaluation_model import Evaluation
        dernieres_evaluations = Evaluation.objects.filter(
            professeur__etablissement=etablissement,
            actif=True
        ).select_related('classe', 'matiere').order_by('-date_evaluation')[:2]
    
    notifications_non_lues = NotificationDirecteur.objects.filter(
        etablissement=etablissement,
        statut='non_lu'
    ).count()

    # Préparer le contexte avec les données de l'établissement
    context = {
        'etablissement': etablissement,
        
        # Statistiques principales
        'stats': {
            'nombre_eleves': nombre_eleves_total,
            'croissance_eleves': croissance_eleves,
            'nombre_enseignants': nombre_enseignants,
            'nombre_personnel_admin': nombre_personnel_admin,
            'changement_personnel': changement_personnel,
            'nombre_classes': nombre_classes,
            'evaluations_semaine': evaluations_semaine,
            'bulletins_publies': moyennes_soumises,
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
    }
    
    return render(request, 'school_admin/directeur/dashboard_directeur.html', context)


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
    nombre_eleves_total = Eleve.objects.filter(etablissement=etablissement).count()
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
    Vue de la page de gestion pédagogique pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
   
    return render(request, 'school_admin/directeur/gestion_pedagogique.html')


@login_required
def gestion_eleves(request):
    """
    Vue de la page de gestion des élèves pour les directeurs d'établissement
    """
      # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
  
    return render(request, 'school_admin/directeur/gestion_eleves.html')


@login_required
def notes_et_resultats(request):
    """
    Page de visualisation des notes et résultats par classe et par matière
    Adaptée pour le primaire et le collège/lycée
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Note, Evaluation
    from ..model.affectation_model import AffectationProfesseur
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from ..model.note_primaire_model import MoyenneMatierePrimaire
    from ..model.matiere_model import Matiere
    from ..model.periode_model import PeriodeScolaire
    import re
    from collections import defaultdict
    
    # Détecter le type d'établissement
    est_primaire = etablissement.type_etablissement in ['primaire', 'primary']
    
    # Récupérer la liste des périodes et déterminer celle sélectionnée
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
            # Récupérer tous les élèves de la classe
            eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
            
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
                        moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            periode_scolaire=periode_active
                        ).first()
                    
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
            
            # Récupérer tous les élèves de la classe
            eleves = Eleve.objects.filter(classe=classe, actif=True)
            
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
                        moyenne_obj = Moyenne.objects.filter(
                            eleve=eleve,
                            classe=classe,
                            matiere=matiere,
                            periode=str(periode_active.id),
                            actif=True
                        ).first()
                    
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
            
            # Trier par moyenne décroissante (None en dernier)
            eleves_data.sort(key=lambda x: (x['moyenne_tri'] is None, -x['moyenne_tri'] if x['moyenne_tri'] is not None else 0))
            
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
    }
    
    return render(request, 'school_admin/directeur/notes_et_resultats.html', context)


@login_required
def justifications_notes_directeur(request):
    """
    Liste et traitement des demandes de justification de notes transmises par les enseignants.
    """
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    from ..model.classe_model import Classe
    from django.db import transaction
    from django.shortcuts import get_object_or_404
    from django.utils import timezone

    classe_id = request.GET.get('classe')
    statut_filtre = request.GET.get('statut')

    classes = Classe.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('niveau', 'nom')

    justifications_queryset = JustificationNote.objects.filter(
        etablissement=etablissement
    ).select_related(
        'classe',
        'eleve',
        'matiere',
        'professeur',
        'evaluation'
    ).order_by('-date_creation')

    if classe_id:
        justifications_queryset = justifications_queryset.filter(classe_id=classe_id)

    if statut_filtre in {
        JustificationNote.STATUT_EN_ATTENTE,
        JustificationNote.STATUT_VALIDEE,
        JustificationNote.STATUT_REFUSEE,
    }:
        justifications_queryset = justifications_queryset.filter(statut=statut_filtre)

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
                note_obj = justification.note or justification.note_primaire

                if not note_obj:
                    messages.error(request, "Impossible de mettre à jour la note ciblée.")
                    return redirect(request.get_full_path())

                bareme = None
                if justification.note and justification.evaluation:
                    bareme = justification.evaluation.bareme
                elif justification.note_primaire and justification.evaluation_primaire:
                    bareme = justification.evaluation_primaire.bareme

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

        return redirect(request.get_full_path())

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
        'classes': classes,
        'classe_selectionnee': classe_id,
        'statut_selectionne': statut_filtre,
        'demandes_grouped': demandes_grouped,
        'stats': stats,
    }

    return render(request, 'school_admin/directeur/justifications_notes.html', context)


@login_required
def bulletins_notes(request):
    """Synthèse des bulletins par classe avec regroupement par niveau."""
    from collections import OrderedDict
    import re
    from django.db.models import Max

    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user

    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.periode_model import PeriodeScolaire
    from ..model.moyenne_model import Moyenne
    from ..model.note_primaire_model import MoyenneMatierePrimaire

    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    periodes = list(PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True).order_by('date_debut'))

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

        eleves_classe_qs = Eleve.objects.filter(classe=classe, actif=True)
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
                moyennes_qs = MoyenneMatierePrimaire.objects.filter(classe=classe, periode_scolaire=periode_active)
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
                moyennes_qs = Moyenne.objects.filter(classe=classe, actif=True, periode__in=list(periode_filters))
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
                eleve__classe=classe
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
        for eleve in eleves_classe_qs.order_by('prenom', 'nom'):
            moyenne_info = moyennes_generales_map.get(eleve.id, {})
            eleves_liste.append({
                'id': eleve.id,
                'nom': eleve.nom_complet,
                'matricule': eleve.matricule_eleve or eleve.numero_eleve,
                'bulletin_valide': eleve.id in eleves_soumis_ids if nombre_eleves_classe else False,
                'bulletin_url': reverse('directeur:voir_bulletin_eleve', args=[classe.id, eleve.id]),
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

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    
    periode = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True).order_by('date_debut').first()
    if not periode:
        messages.error(request, "Aucune période scolaire active n'est configurée.")
        return redirect('directeur:bulletins_notes')

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
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    if not eleves.exists():
        messages.warning(request, "Cette classe ne contient aucun élève.")
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
                            soumis=True
                        ).first()
                        
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
                    est_moyenne_generale=True
                ).update(rang=index)
                
                # Mettre à jour aussi les rangs par matière (tri décroissant : la plus forte moyenne = rang 1)
                for matiere in matieres:
                    matiere_moyennes = list(MoyennePeriode.objects.filter(
                        etablissement=etablissement,
                        periode=periode,
                        matiere=matiere,
                        est_moyenne_generale=False,
                        moyenne_matiere__isnull=False
                    ).select_related('eleve'))
                    
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
    if selected_periode_id:
        redirect_url = f"{redirect_url}?periode={selected_periode_id}"
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

    notifications = list(
        NotificationDirecteur.objects.filter(etablissement=etablissement)
        .order_by('-date_creation')
    )
    notification_ids = [notification.id for notification in notifications]

    if notification_ids:
        NotificationDirecteur.objects.filter(id__in=notification_ids).update(
            statut='lu',
            date_lecture=timezone.now(),
            date_modification=timezone.now(),
        )

    context = {
        'etablissement': etablissement,
        'notifications': notifications,
        'notifications_directeur_non_lues': 0,
    }

    response = render(request, 'school_admin/directeur/notifications_directeur.html', context)

    if notification_ids:
        NotificationDirecteur.objects.filter(id__in=notification_ids).delete()

    return response


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

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    eleve = get_object_or_404(Eleve, id=eleve_id, classe=classe, etablissement=etablissement, actif=True)

    periode = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True).order_by('date_debut').first()
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
    moyenne_periode_generale = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        periode=periode,
        est_moyenne_generale=True
    ).first()

    bulletin_numero_serie = None
    bulletin_signature = None
    bulletin_qr_image_url = None
    bulletin_qr_data = None
    bulletin_qr_generated_at = None

    # Si les moyennes ont été calculées, utiliser les données de MoyennePeriode
    if moyenne_periode_generale:
        moyennes_periode = MoyennePeriode.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            periode=periode,
            est_moyenne_generale=False
        ).select_related('matiere').order_by('matiere__nom')

        matieres_table = []
        for mp in moyennes_periode:
            if mp.matiere:
                matieres_table.append({
                    'nom': mp.matiere.nom,
                    'moyenne_classe': float(mp.moyenne_classe) if mp.moyenne_classe is not None else None,
                    'note_examen': float(mp.note_examen) if mp.note_examen is not None else None,
                    'coefficient': float(mp.coefficient) if mp.coefficient else 1,
                    'moyenne_eleve': float(mp.moyenne_matiere) if mp.moyenne_matiere is not None else None,
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
                    moyennes_classe_matiere = MoyenneMatierePrimaire.objects.filter(
                        classe=classe,
                        periode_scolaire=periode,
                        matiere__nom=item['nom'],
                        soumis=True,
                        moyenne__isnull=False
                    )
                else:
                    from ..model.moyenne_model import Moyenne
                    matiere_obj = Matiere.objects.filter(nom=item['nom'], etablissement=etablissement).first()
                    if matiere_obj:
                        moyennes_classe_matiere = Moyenne.objects.filter(
                            classe=classe,
                            periode=str(periode.id),
                            matiere=matiere_obj,
                            soumis=True,
                            actif=True,
                            moyenne__isnull=False
                        )
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

            eleve_moyennes = {
                item.matiere_id: item
                for item in MoyenneMatierePrimaire.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    periode_scolaire=periode
                )
            }

            moyennes_classe = MoyenneMatierePrimaire.objects.filter(
                classe=classe,
                periode_scolaire=periode,
                soumis=True,
                moyenne__isnull=False
            )

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

                matieres_table.append({
                    'nom': matiere.nom,
                    'moyenne_classe': float(moyenne_classe) if moyenne_classe is not None else None,
                    'note_examen': note_examen_value,
                    'coefficient': float(matiere.coefficient) if matiere.coefficient is not None else 1,
                    'moyenne_eleve': float(moyenne_value) if moyenne_value is not None else None,
                    'rang': rang,
                    'appreciation': appreciation,
                })

            if poids_generaux > 0:
                moyenne_generale = float((somme_generale / poids_generaux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

            bulletin_valide = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                classe=classe,
                periode_scolaire=periode,
                soumis=True
            ).exists()

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

            for item in moyennes_classe.iterator():
                valeur = Decimal(item.moyenne)
                coeff_decimal = Decimal(str(item.matiere.coefficient or 1))
                matiere_scores_map[item.matiere_id].append((item.eleve_id, valeur))
                overall_totaux[item.eleve_id]['sum'] += valeur * coeff_decimal
                overall_totaux[item.eleve_id]['coeff'] += coeff_decimal

            examens_map = {}
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

            for matiere in matieres:
                moyenne_obj = eleve_moyennes.get(matiere.id)
                soumis = bool(moyenne_obj and moyenne_obj.soumis)
                moyenne_value = None
                appreciation = None
                if soumis and moyenne_obj and moyenne_obj.moyenne is not None:
                    moyenne_value = Decimal(moyenne_obj.moyenne)
                    appreciation = moyenne_obj.appreciation if hasattr(moyenne_obj, 'appreciation') else None
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

                matieres_table.append({
                    'nom': matiere.nom,
                    'moyenne_classe': float(moyenne_classe) if moyenne_classe is not None else None,
                    'note_examen': examens_map.get(matiere.id),
                    'coefficient': float(matiere.coefficient) if matiere.coefficient is not None else 1,
                    'moyenne_eleve': float(moyenne_value) if moyenne_value is not None else None,
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

    complement_info = {
        'moyenne_periode': moyenne_generale,
        'moyenne_annuelle': None,
        'rang_general': rang_general,
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
            'statut_conseil_code': standards_extra['statut_conseil_code'],
            'statut_conseil_label': standards_extra['statut_conseil_label'],
        })
        if decision_conseil:
            complement_info.update({
                'decision_conseil_standard': standards_extra['decision_conseil_standard'],
                'decision_conseil_source': standards_extra['decision_conseil_source'],
            })

    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleve': eleve,
        'periode': periode,
        'est_primaire': est_primaire,
        'matieres_table': matieres_table,
        'moyenne_generale': moyenne_generale,
        'bulletin_valide': bulletin_valide,
        'bulletin_disponible': bulletin_disponible,
        'soumissions': soumissions,
        'total_matieres': total_matieres,
        'pourcentage_soumission': pourcentage_soumission,
        'retour_url': reverse('directeur:bulletins_notes'),
        'releve_classe_url': reverse('directeur:imprimer_releve_notes', args=[classe.id]),
        'date_generation': timezone.now(),
        'classe_effectif': classe_effectif,
        'rang_general': rang_general,
        'complement_info': complement_info,
        'impression_url': reverse('directeur:imprimer_bulletin_eleve', args=[classe.id, eleve.id]),
        'standards_summary': standards_extra['standards_summary'] if standards_extra else None,
        'standards_applied': bool(standards_bundle),
        'bulletin_qr_image_url': bulletin_qr_image_url,
        'bulletin_qr_data': bulletin_qr_data,
        'bulletin_qr_generated_at': bulletin_qr_generated_at,
        'bulletin_signature': bulletin_signature,
        'bulletin_numero_serie': bulletin_numero_serie,
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

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    eleve = get_object_or_404(Eleve, id=eleve_id, classe=classe, etablissement=etablissement, actif=True)

    periode = PeriodeScolaire.objects.filter(etablissement=etablissement, est_active=True).order_by('date_debut').first()
    if not periode:
        messages.warning(request, "Aucune période scolaire active n'est configurée.")
        return redirect('directeur:voir_bulletin_eleve', classe_id=classe_id, eleve_id=eleve_id)

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
                    moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                        eleve=eleve,
                        classe=classe,
                        periode_scolaire=periode,
                        matiere=matiere,
                        soumis=True
                    ).first()

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
            eleves_classe = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
            eleves_moyennes_generales = []

            for eleve_classe in eleves_classe:
                moyenne_gen = MoyennePeriode.objects.filter(
                    eleve=eleve_classe,
                    etablissement=etablissement,
                    periode=periode,
                    est_moyenne_generale=True
                ).first()

                if moyenne_gen and moyenne_gen.moyenne_generale is not None:
                    eleves_moyennes_generales.append({
                        'eleve_id': eleve_classe.id,
                        'moyenne': Decimal(str(moyenne_gen.moyenne_generale)),
                    })

            # Calculer les rangs (tri décroissant : la plus forte moyenne = rang 1)
            eleves_moyennes_generales.sort(key=lambda x: (x['moyenne'] is not None, -(x['moyenne'] or 0)), reverse=False)

            for index, item in enumerate(eleves_moyennes_generales, start=1):
                eleve_id_rang = item['eleve_id']
                MoyennePeriode.objects.filter(
                    eleve_id=eleve_id_rang,
                    etablissement=etablissement,
                    periode=periode,
                    est_moyenne_generale=True
                ).update(rang=index)

                # Mettre à jour aussi les rangs par matière (tri décroissant : la plus forte moyenne = rang 1)
                for matiere in matieres:
                    matiere_moyennes = list(MoyennePeriode.objects.filter(
                        etablissement=etablissement,
                        periode=periode,
                        matiere=matiere,
                        est_moyenne_generale=False,
                        moyenne_matiere__isnull=False
                    ).select_related('eleve'))

                    # Trier par moyenne décroissante (plus forte moyenne = rang 1)
                    matiere_moyennes.sort(key=lambda x: (x.moyenne_matiere is None, -(x.moyenne_matiere or 0)), reverse=False)

                    for rang_matiere, moyenne_periode in enumerate(matiere_moyennes, start=1):
                        moyenne_periode.rang = rang_matiere
                        moyenne_periode.save(update_fields=['rang'])

        messages.success(request, f"✅ La moyenne générale de {eleve.nom_complet} a été calculée et mise à jour avec succès. Les rangs de la classe ont également été recalculés.")
    except Exception as e:
        logger.error(f"Erreur lors du calcul de la moyenne de l'élève: {str(e)}", exc_info=True)
        messages.error(request, f"❌ Erreur lors du calcul de la moyenne: {str(e)}")

    return redirect('directeur:voir_bulletin_eleve', classe_id=classe_id, eleve_id=eleve_id)


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
    ).select_related('eleve')

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

    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, actif=True)
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('prenom', 'nom')
    
    if not eleves.exists():
        messages.warning(request, "Cette classe ne contient aucun élève.")
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

    periodes = PeriodeScolaire.objects.filter(etablissement=etablissement).order_by('date_debut')

    annee_scolaire = Ponderation.default_school_year()
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
        if not est_primaire:
            messages.warning(request, "La configuration des pondérations n'est disponible que pour les établissements primaires.")
            return redirect('directeur:configuration_moyennes_generales')

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

    standards, _ = StandardsReussite.objects.get_or_create(etablissement=etablissement)

    def _format_decimal(value):
        if value is None:
            return ''
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"

    general_settings = {
        'moyenne_passage': _format_decimal(standards.moyenne_passage),
        'moyenne_redoublement': _format_decimal(standards.moyenne_redoublement),
        'appreciation_conseil': standards.appreciation_conseil or '',
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
                moyenne_redoublement = Decimal(request.POST.get('moyenne_redoublement', '').strip()).quantize(Decimal('0.01'))
                zero = Decimal('0')
                vingt = Decimal('20')
                if not (zero <= moyenne_passage <= vingt and zero <= moyenne_redoublement <= vingt):
                    raise ValueError
            except Exception:
                messages.error(request, "Les moyennes doivent être des nombres entre 0 et 20.")
            else:
                standards.moyenne_passage = moyenne_passage
                standards.moyenne_redoublement = moyenne_redoublement
                standards.appreciation_conseil = request.POST.get('appreciation_conseil', '').strip() or None
                standards.save(update_fields=['moyenne_passage', 'moyenne_redoublement', 'appreciation_conseil', 'date_modification'])
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
    import re
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    # Récupérer les périodes scolaires disponibles
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
        
        # Récupérer tous les élèves de la classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        # Construire le queryset de présence filtré par période le cas échéant
        presences_queryset = Presence.objects.filter(classe=classe)
        if periode_selectionnee:
            presences_queryset = presences_queryset.filter(
                date__gte=periode_selectionnee.date_debut,
                date__lte=periode_selectionnee.date_fin
            )
        
        # Récupérer les mois distincts où il y a des données de présence pour cette classe
        presences_classe = presences_queryset.values('date__month', 'date__year').distinct().order_by('date__year', 'date__month')
        
        # Créer une liste des mois disponibles
        mois_disponibles = []
        for p in presences_classe:
            date_mois = datetime(p['date__year'], p['date__month'], 1)
            mois_disponibles.append({
                'numero': p['date__month'],
                'annee': p['date__year'],
                'nom': date_mois.strftime('%B'),
                'nom_court': date_mois.strftime('%b'),
            })
        
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
def gestion_etablissement(request):
    """
    Vue de la page de gestion de l'établissement pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
   
    return render(request, 'school_admin/directeur/gestion_etablissement.html')


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
        
        try:
            with transaction.atomic():
                nom_periode = request.POST.get('nom_periode', '').strip()
                type_periode = request.POST.get('type_periode', 'trimestre')
                date_debut_str = request.POST.get('date_debut', '')
                date_fin_str = request.POST.get('date_fin', '')
                annee_scolaire = request.POST.get('annee_scolaire', annee_scolaire_actuelle)
                est_active = request.POST.get('est_active') == 'on'
                
                # Validations
                if not all([nom_periode, date_debut_str, date_fin_str, annee_scolaire]):
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('directeur:gestion_periodes_scolaires')
                
                # Convertir les dates string en objets date
                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                
                # Créer la période
                periode = PeriodeScolaire.objects.create(
                    etablissement=etablissement,
                    nom_periode=nom_periode,
                    type_periode=type_periode,
                    date_debut=date_debut,
                    date_fin=date_fin,
                    annee_scolaire=annee_scolaire,
                    est_active=est_active
                )
                
                messages.success(request, f"La période '{periode.nom_periode}' a été créée avec succès.")
                return redirect('directeur:gestion_periodes_scolaires')
                
        except ValidationError as e:
            messages.error(request, f"Erreur de validation : {e}")
            return redirect('directeur:gestion_periodes_scolaires')
        except Exception as e:
            messages.error(request, f"Erreur lors de la création de la période : {str(e)}")
            return redirect('directeur:gestion_periodes_scolaires')
    
    # Récupérer toutes les périodes de l'établissement
    from ..model.periode_model import PeriodeScolaire
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement
    ).order_by('-annee_scolaire', 'date_debut')
    
    # Grouper les périodes par année scolaire
    periodes_par_annee = {}
    for periode in periodes:
        if periode.annee_scolaire not in periodes_par_annee:
            periodes_par_annee[periode.annee_scolaire] = []
        periodes_par_annee[periode.annee_scolaire].append(periode)
    
    context = {
        'user': etablissement,
        'etablissement': etablissement,
        'periodes': periodes,
        'periodes_par_annee': periodes_par_annee,
        'annee_scolaire_actuelle': annee_scolaire_actuelle,
    }
    
    return render(request, 'school_admin/directeur/gestion_periodes_scolaires.html', context)


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
    
    # Vérifier que c'est une requête AJAX
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Requête invalide'}, status=400)
    
    # Récupérer les paramètres
    classe_id = request.GET.get('classe_id')
    matiere_nom = request.GET.get('matiere_nom')
    periode_id = request.GET.get('periode_id')
    
    if not all([classe_id, matiere_nom, periode_id]):
        return JsonResponse({'success': False, 'message': 'Paramètres manquants'}, status=400)
    
    try:
        # Récupérer les objets
        classe = Classe.objects.get(id=classe_id)
        matiere = Matiere.objects.get(nom=matiere_nom, etablissement=classe.etablissement)
        periode = PeriodeScolaire.objects.get(id=periode_id)
        
        # Récupérer tous les élèves de la classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
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
    
    # Vérifier que c'est une requête AJAX
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Requête invalide'}, status=400)
    
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        return JsonResponse({'success': False, 'message': 'Accès non autorisé'}, status=403)
    
    etablissement = request.user
    
    # Vérifier que c'est un établissement secondaire
    if etablissement.type_etablissement not in ['lycée', 'collège', 'collège_lycée']:
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
        
        # Récupérer tous les élèves de la classe avec leurs moyennes
        eleves = Eleve.objects.filter(classe=classe, actif=True)
        
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
                'initiales': f"{eleve.prenom[0]}{eleve.nom[0]}" if eleve.prenom and eleve.nom else eleve.nom[:2].upper(),
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
    from collections import defaultdict
    
    try:
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement)
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:notes_et_resultats')
    
    # Détecter le type d'établissement
    est_primaire = etablissement.type_etablissement == 'primary'
    
    # Récupérer la période scolaire active
    periode = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    ).first()
    
    if not periode:
        messages.warning(request, "Aucune période scolaire active trouvée.")
        return redirect('directeur:notes_et_resultats')
    
    eleves = Eleve.objects.filter(classe=classe).order_by('nom', 'prenom')
    
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
                # Récupérer la moyenne de l'élève pour cette matière
                moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                    eleve=eleve,
                    matiere=matiere,
                    periode_scolaire=periode
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
                # Récupérer la moyenne de l'élève pour cette matière
                moyenne_obj = Moyenne.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    matiere=matiere,
                    periode=str(periode.id),
                    actif=True
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
        }
    
    return render(request, 'school_admin/directeur/imprimer_releve_notes.html', context)


@login_required
def gestion_administrative(request):
    """
    Page de gestion administrative pour les directeurs
    Génération de documents administratifs (certificats, attestations, etc.)
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    context = {
        'etablissement': etablissement,
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
    import re
    from collections import defaultdict
    
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
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
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
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:certificat_scolarite_liste')
    
    # Informations pour le certificat
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
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
    import re
    
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
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
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
    from datetime import datetime
    
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
            }
            return render(request, 'school_admin/directeur/formulaire_convocation.html', context)
        
        try:
            # Convertir les chaînes en objets date et time
            from datetime import datetime as dt
            date_convocation = dt.strptime(date_convocation_str, '%Y-%m-%d').date()
            heure_convocation = dt.strptime(heure_convocation_str, '%H:%M').time()
            
            # Créer et sauvegarder la convocation
            from ..model.convocation_model import Convocation
            convocation = Convocation.objects.create(
                eleve=eleve,
                etablissement=etablissement,
                objet=objet,
                motif=motif,
                date_convocation=date_convocation,
                heure_convocation=heure_convocation,
                lieu=lieu,
                statut='en_attente'
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
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer toutes les convocations de l'élève
    convocations = Convocation.objects.filter(
        eleve=eleve,
        actif=True
    ).order_by('-date_convocation', '-heure_convocation')
    
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'convocations': convocations,
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
    
    # Informations pour la convocation
    context = {
        'etablissement': etablissement,
        'eleve': convocation.eleve,
        'convocation': convocation,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
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
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(
        classe=classe,
        etablissement=etablissement,
        actif=True
    ).order_by('nom', 'prenom')
    
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
            }
            return render(request, 'school_admin/directeur/formulaire_convocation_classe.html', context)
        
        try:
            # Convertir les chaînes en objets date et time
            from datetime import datetime as dt
            date_convocation = dt.strptime(date_convocation_str, '%Y-%m-%d').date()
            heure_convocation = dt.strptime(heure_convocation_str, '%H:%M').time()
            
            # Créer les convocations pour tous les élèves de la classe
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
                    convocation_classe=True  # Marquer comme convocation de classe
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
            }
            return render(request, 'school_admin/directeur/formulaire_convocation_classe.html', context)
    
    # Afficher le formulaire
    context = {
        'etablissement': etablissement,
        'classe': classe,
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
    from collections import defaultdict
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:convocation_liste')
    
    # Récupérer toutes les convocations de classe pour cette classe
    # On regroupe par (objet, motif, date, heure, lieu) pour éviter les doublons
    convocations_classe = Convocation.objects.filter(
        eleve__classe=classe,
        etablissement=etablissement,
        actif=True,
        convocation_classe=True
    ).select_related('eleve').order_by('-date_convocation', '-heure_convocation')
    
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
    from datetime import datetime
    
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
        # Récupérer la convocation de référence
        convocation_ref = Convocation.objects.get(id=convocation_id, actif=True, convocation_classe=True)
        
        # Récupérer toutes les convocations identiques (même objet, date, heure, lieu)
        convocations = Convocation.objects.filter(
            eleve__classe=classe,
            etablissement=etablissement,
            actif=True,
            convocation_classe=True,
            objet=convocation_ref.objet,
            date_convocation=convocation_ref.date_convocation,
            heure_convocation=convocation_ref.heure_convocation,
            lieu=convocation_ref.lieu
        ).select_related('eleve', 'eleve__classe').order_by('eleve__nom', 'eleve__prenom')
        
    except Convocation.DoesNotExist:
        messages.error(request, "Convocation non trouvée.")
        return redirect('directeur:convocations_classe_liste', classe_id=classe_id)
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'convocations': convocations,
        'convocation_ref': convocation_ref,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',
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
    import re
    
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
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
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
    }
    
    return render(request, 'school_admin/directeur/attestation_reussite_liste.html', context)


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
    from datetime import datetime
    
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
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
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
    import re
    
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
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
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
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:attestation_conduite_liste')
    
    # Informations pour l'attestation
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
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
    import re
    
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
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
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
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:fiche_inscription_liste')
    
    # Informations pour la fiche
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
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
    from datetime import datetime
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:fiche_inscription_liste')
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(
        classe=classe,
        actif=True
    ).order_by('nom', 'prenom')
    
    if not eleves.exists():
        messages.warning(request, "Aucun élève dans cette classe.")
        return redirect('directeur:fiche_inscription_liste')
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleves': eleves,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',
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
    import re
    
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
        
        # Récupérer les élèves de cette classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
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
    from datetime import datetime
    
    try:
        eleve = Eleve.objects.select_related('classe').get(
            id=eleve_id,
            etablissement=etablissement
        )
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('directeur:certificat_radiation_liste')
    
    # Informations pour le certificat
    context = {
        'etablissement': etablissement,
        'eleve': eleve,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',  # À adapter selon la période active
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
    from datetime import datetime
    
    try:
        classe = Classe.objects.get(
            id=classe_id,
            etablissement=etablissement,
            actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('directeur:liste_eleves')
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(
        classe=classe,
        actif=True
    ).order_by('nom', 'prenom')
    
    context = {
        'etablissement': etablissement,
        'classe': classe,
        'eleves': eleves,
        'date_generation': datetime.now(),
        'annee_scolaire': '2024-2025',
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
    from datetime import datetime
    from django.db.models import Q
    
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
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Calculer les statistiques de présence pour chaque élève
    eleves_presences = []
    
    for eleve in eleves:
        presences = Presence.objects.filter(
            eleve=eleve,
            classe=classe,
            date__month=mois_numero,
            date__year=mois_annee
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
    }
    
    return render(request, 'school_admin/directeur/imprimer_liste_presence.html', context)


def demandes_liaison_liste(request):
    """
    Liste des demandes de liaison parent-enfant pour le directeur
    """
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer toutes les demandes pour les élèves de cet établissement
    demandes = DemandeLiaisonParent.objects.filter(
        eleve_valide__etablissement=etablissement
    ).select_related(
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
def annonces_directeur(request):
    """
    Vue pour la gestion des annonces par le directeur
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.annonce_model import Annonce
    
    # Récupérer toutes les annonces de l'établissement
    annonces = Annonce.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('-date_publication', '-date_creation')
    
    # Filtrer par statut si demandé
    statut_filtre = request.GET.get('statut', '')
    if statut_filtre:
        annonces = annonces.filter(statut=statut_filtre)
    
    # Statistiques
    total_annonces = annonces.count()
    annonces_publiees = annonces.filter(statut='publiee').count()
    annonces_brouillon = annonces.filter(statut='brouillon').count()
    annonces_archivees = annonces.filter(statut='archivee').count()
    
    context = {
        'annonces': annonces,
        'total_annonces': total_annonces,
        'annonces_publiees': annonces_publiees,
        'annonces_brouillon': annonces_brouillon,
        'annonces_archivees': annonces_archivees,
        'statut_filtre': statut_filtre,
    }
    
    return render(request, 'school_admin/directeur/annonces/liste_annonces.html', context)


@login_required
def creer_annonce(request):
    """
    Vue pour créer une nouvelle annonce
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.annonce_model import Annonce
    
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
            
            # Créer l'annonce
            annonce = Annonce.objects.create(
                etablissement=etablissement,
                auteur_directeur=etablissement,
                titre=titre,
                contenu=contenu,
                destinataires=destinataires,
                fichier_joint=fichier_joint,
                statut='brouillon'
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
    context = {
        'destinataires_choices': Annonce.DESTINATAIRES_CHOICES,
    }
    
    return render(request, 'school_admin/directeur/annonces/creer_annonce.html', context)


@login_required
def modifier_annonce(request, annonce_id):
    """
    Vue pour modifier une annonce existante
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
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
    context = {
        'annonce': annonce,
        'destinataires_choices': Annonce.DESTINATAIRES_CHOICES,
    }
    
    return render(request, 'school_admin/directeur/annonces/modifier_annonce.html', context)


@login_required
def apercu_annonce(request, annonce_id):
    """
    Vue pour prévisualiser une annonce avant publication
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.annonce_model import Annonce
    
    # Récupérer l'annonce
    annonce = get_object_or_404(
        Annonce,
        id=annonce_id,
        etablissement=etablissement,
        actif=True
    )
    
    context = {
        'annonce': annonce,
    }
    
    return render(request, 'school_admin/directeur/annonces/apercu_annonce.html', context)


@login_required
def publier_annonce(request, annonce_id):
    """
    Vue pour publier une annonce en brouillon
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
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
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
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
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
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
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')

    etablissement = request.user
    success_message = None

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
            if etablissement.logo:
                etablissement.logo.delete(save=False)
                etablissement.logo = None
                etablissement.save(update_fields=['logo', 'date_modification'])
                success_message = "Logo supprimé avec succès."
            else:
                messages.info(request, "Aucun logo n'est actuellement défini.")

        if success_message:
            messages.success(request, success_message)
        return redirect('directeur:profil_etablissement')

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
    }

    return render(request, 'school_admin/directeur/mon_profil_etablissement.html', context)