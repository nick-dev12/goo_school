"""Verrou, annulation et pièces. Les écritures passent par les ponts existants."""
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.comptabilite_generale_model import EcritureComptable
from school_admin.model.finances_model import (
    JournalAuditFinancier,
    PieceFinanciere,
    PretEtablissement,
    RecetteEtablissement,
)
from school_admin.services.comptabilite_generale import (
    ensure_exercice,
    extourner,
    periode_verrouillee,
    pont_depense,
)
from school_admin.services.finances.categories import categorie_pour_motif
from school_admin.services.finances.tresorerie import compte_principal

CIBLES_PIECE = (DepenseEtablissement, RecetteEtablissement, PretEtablissement)
TAILLES_PIECE_MAX = 5 * 1024 * 1024
EXTENSIONS_PIECE = ('.pdf', '.jpg', '.jpeg', '.png', '.webp')


def _acteur(user):
    if user is None or not getattr(user, 'pk', None) or not getattr(user, '_meta', None):
        return None, None
    return ContentType.objects.get_for_model(user), user.pk


def journaliser(etablissement, cible, action, user=None, motif='', avant=None, apres=None):
    type_acteur, id_acteur = _acteur(user)
    return JournalAuditFinancier.objects.create(
        etablissement=etablissement,
        acteur_content_type=type_acteur,
        acteur_object_id=id_acteur,
        cible_content_type=ContentType.objects.get_for_model(cible),
        cible_object_id=cible.pk,
        action=action,
        anciennes_valeurs=avant or {},
        nouvelles_valeurs=apres or {},
        motif=motif or '',
    )


def _exiger_periode_ouverte(etablissement, jour):
    exercice = ensure_exercice(etablissement)
    if not exercice.est_ouvert():
        raise ValueError("L'exercice est clôturé.")
    if periode_verrouillee(exercice, jour):
        raise ValueError("Cette période comptable est verrouillée.")
    return exercice


def enregistrer_sortie(etablissement, date_depense, motif, montant, libelle='', annee_scolaire=None, user=None, fichier=None, fournisseur=None):
    """Sortie validée tout de suite. La période est contrôlée avant l'enregistrement."""
    from school_admin.services.finances.charges import refuser_doublon_facture

    _exiger_periode_ouverte(etablissement, date_depense)
    if fournisseur is not None and fournisseur.etablissement_id != etablissement.id:
        raise ValueError("Ce fournisseur n'appartient pas à cette école.")
    refuser_doublon_facture(etablissement, fournisseur, montant, date_depense)
    categorie = categorie_pour_motif(etablissement, motif)
    caisse = compte_principal(etablissement, 'caisse')
    with transaction.atomic():
        depense = DepenseEtablissement.objects.create(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            date_depense=date_depense,
            motif=motif or 'autre',
            libelle=(libelle or '')[:160],
            montant=montant,
            statut='validee',
            categorie=categorie,
            compte_tresorerie=caisse,
            fournisseur=fournisseur,
            enregistre_par=user if user is not None and user.__class__.__name__ == 'CompteUser' else None,
        )
        if fichier is not None:
            attacher_piece(etablissement, depense, fichier, user=user)
        ecriture = pont_depense(depense, annee_scolaire=annee_scolaire, user=user)
        journaliser(
            etablissement,
            depense,
            'validation',
            user=user,
            apres={'montant': str(montant), 'motif': depense.motif, 'statut': 'validee'},
        )
    return depense, ecriture


def annuler_sortie(depense, motif, user=None):
    """La sortie reste. Une contre-écriture est datée du jour si la période du jour est ouverte."""
    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif d'annulation est obligatoire.")
    if depense.statut == 'annulee':
        raise ValueError("Cette sortie est déjà annulée.")
    if depense.statut != 'validee':
        raise ValueError("Seule une sortie validée peut être annulée.")
    aujourd_hui = timezone.now().date()
    _exiger_periode_ouverte(depense.etablissement, aujourd_hui)
    with transaction.atomic():
        originale = EcritureComptable.objects.filter(
            etablissement=depense.etablissement,
            source='depense',
            source_id=depense.id,
        ).first()
        if originale is not None:
            extourner(originale, aujourd_hui, texte, user=user)
        type_acteur, id_acteur = _acteur(user)
        depense.statut = 'annulee'
        depense.motif_annulation = texte
        depense.date_annulation = timezone.now()
        depense.annule_content_type = type_acteur
        depense.annule_object_id = id_acteur
        depense.save(update_fields=[
            'statut',
            'motif_annulation',
            'date_annulation',
            'annule_content_type',
            'annule_object_id',
        ])
        journaliser(
            depense.etablissement,
            depense,
            'annulation',
            user=user,
            motif=texte,
            avant={'statut': 'validee'},
            apres={'statut': 'annulee'},
        )
    return depense


def attacher_piece(etablissement, cible, fichier, user=None):
    if not isinstance(cible, CIBLES_PIECE):
        raise ValueError("Ce document ne peut pas recevoir de justificatif ici.")
    nom = (getattr(fichier, 'name', '') or 'justificatif')
    if not nom.lower().endswith(EXTENSIONS_PIECE):
        raise ValueError("Format accepté : PDF ou image.")
    taille = getattr(fichier, 'size', 0) or 0
    if taille > TAILLES_PIECE_MAX:
        raise ValueError("Le justificatif dépasse 5 Mo.")
    type_acteur, id_acteur = _acteur(user)
    return PieceFinanciere.objects.create(
        etablissement=etablissement,
        content_type=ContentType.objects.get_for_model(cible),
        object_id=cible.pk,
        fichier=fichier,
        nom=nom[:180],
        deposant_content_type=type_acteur,
        deposant_object_id=id_acteur,
    )
