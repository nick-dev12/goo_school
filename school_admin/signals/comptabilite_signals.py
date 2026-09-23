"""
Signals pour la gestion automatique de la comptabilité
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from ..model.parametres_comptabilite_model import ParametresComptabilite


def _emettre_creance_nouvelle(instance, kind, source):
    from school_admin.services.comptabilite_generale import pont_emission_creance

    try:
        _emettre_creance_nouvelle_inner(instance, kind, source, pont_emission_creance)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Pont émission créance ignoré (%s #%s)", source, instance.pk)


def _emettre_creance_nouvelle_inner(instance, kind, source, pont_emission_creance):
    reste = instance.get_reste_a_payer() if hasattr(instance, 'get_reste_a_payer') else None
    if reste is None:
        reste = (instance.montant or 0) - (instance.montant_paye or 0)
    if reste <= 0:
        return
    eleve_nom = getattr(instance.eleve, 'nom_complet', str(instance.eleve_id))
    from django.utils import timezone
    date_ecr = getattr(instance, 'date_echeance', None) or timezone.now().date()
    type_paiement = {
        'inscription': 'frais_inscription',
        'mensualite': 'mensualite',
        'annexe': 'frais_annexe',
    }.get(kind, 'autre')
    pont_emission_creance(
        instance.etablissement,
        reste,
        date_ecr,
        type_paiement,
        source,
        instance.id,
        f"Créance {kind} — {eleve_nom}",
        auxiliaire=eleve_nom,
        annee_scolaire=getattr(instance, 'annee_scolaire', None),
    )


@receiver(post_save, sender=ParametresComptabilite)
def mettre_a_jour_systeme_apres_sauvegarde_parametres(sender, instance, created, **kwargs):
    """
    Met à jour automatiquement tout le système de comptabilité après la sauvegarde des paramètres.
    Cette fonction est appelée automatiquement après chaque sauvegarde (création ou mise à jour).
    
    Actions effectuées :
    - Initialise automatiquement tous les élèves inscrits dans l'année scolaire active
    - Met à jour les frais d'inscription et mensualités existants avec les nouveaux montants
    - Recalcule les statuts de paiement
    """
    try:
        instance.mettre_a_jour_systeme_comptabilite()
    except Exception as e:
        # En cas d'erreur, on log mais on ne bloque pas la sauvegarde
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la mise à jour automatique du système de comptabilité : {str(e)}")


@receiver(post_save, sender='school_admin.FraisInscription')
def emettre_creance_inscription(sender, instance, created, **kwargs):
    if created:
        _emettre_creance_nouvelle(instance, 'inscription', 'creance_inscription')


@receiver(post_save, sender='school_admin.Mensualite')
def emettre_creance_mensualite(sender, instance, created, **kwargs):
    if created:
        _emettre_creance_nouvelle(instance, 'mensualite', 'creance_mensualite')


@receiver(post_save, sender='school_admin.FraisAnnexe')
def emettre_creance_annexe(sender, instance, created, **kwargs):
    if created:
        _emettre_creance_nouvelle(instance, 'annexe', 'creance_annexe')

