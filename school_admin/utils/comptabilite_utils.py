# school_admin/utils/comptabilite_utils.py

from django.utils import timezone
from datetime import datetime, timedelta
from calendar import monthrange
from decimal import Decimal
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.eleve_model import Eleve
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.comptabilite_eleve_model import (
    ComptabiliteEleve, FraisInscription, Mensualite, PaiementEleve
)


def creer_frais_inscription(eleve, annee_scolaire, type_frais='inscription'):
    """
    Crée les frais d'inscription pour un élève
    
    Args:
        eleve: Instance de Eleve
        annee_scolaire: Instance de AnneeScolaire
        type_frais: 'inscription' ou 'reinscription'
    
    Returns:
        Instance de FraisInscription créée
    """
    etablissement = eleve.etablissement
    
    # Vérifier que l'établissement a le module comptabilité activé
    if not etablissement.module_comptabilite:
        return None
    
    # Déterminer le montant selon le type d'établissement
    montant = None
    if etablissement.type_etablissement_comptabilite == 'prive':
        montant = etablissement.montant_frais_inscription
    else:  # public
        montant = etablissement.montant_facturation_annuelle
    
    if not montant:
        return None
    
    # Récupérer ou créer la comptabilité de l'élève
    comptabilite_eleve, created = ComptabiliteEleve.objects.get_or_create(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        defaults={
            'statut_paiement': 'a_jour'
        }
    )
    
    # Date d'échéance : 30 jours après l'inscription
    date_echeance = timezone.now().date() + timedelta(days=30)
    
    # Créer les frais d'inscription avec statut 'en_attente' et montant_paye=0
    # La caissière/comptable enregistrera le paiement manuellement
    frais_inscription = FraisInscription.objects.create(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        comptabilite_eleve=comptabilite_eleve,
        montant=montant,
        date_echeance=date_echeance,
        type_frais=type_frais,
        statut='en_attente',
        montant_paye=Decimal('0.00'),
        reste_a_payer=montant  # Initialiser le reste à payer au montant total
    )
    
    return frais_inscription


def generer_mensualites_mois(etablissement, mois, annee):
    """
    Génère les mensualités pour un établissement privé pour un mois donné
    
    Args:
        etablissement: Instance de Etablissement
        mois: Numéro du mois (1-12)
        annee: Année
    
    Returns:
        Nombre de mensualités créées
    """
    if etablissement.type_etablissement_comptabilite != 'prive':
        return 0
    
    if not etablissement.montant_mensualite:
        return 0
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = AnneeScolaire.get_session_active(etablissement)
    if not annee_scolaire_active:
        return 0
    
    # Vérifier que le mois est dans la période de l'année scolaire
    date_debut_mois = datetime(annee, mois, 1).date()
    if not (annee_scolaire_active.date_debut <= date_debut_mois <= annee_scolaire_active.date_fin):
        return 0
    
    # Noms des mois en français
    noms_mois = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]
    periode = f"{noms_mois[mois]} {annee}"
    
    # Calculer la date d'échéance (fin du mois)
    dernier_jour_mois = monthrange(annee, mois)[1]
    date_echeance = datetime(annee, mois, dernier_jour_mois).date()
    
    # Récupérer tous les élèves actifs
    eleves = Eleve.objects.filter(
        etablissement=etablissement,
        actif=True
    ).all()
    
    mensualites_creees = 0
    
    for eleve in eleves:
        # Vérifier si une mensualité existe déjà
        mensualite_existante = Mensualite.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            mois=mois,
            annee=annee
        ).first()
        
        if mensualite_existante:
            continue
        
        # Récupérer ou créer la comptabilité de l'élève
        comptabilite_eleve, created = ComptabiliteEleve.objects.get_or_create(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            defaults={
                'statut_paiement': 'a_jour'
            }
        )
        
        # Créer la mensualité avec montant_paye=0 (sera payé par la caissière/comptable)
        Mensualite.objects.create(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            comptabilite_eleve=comptabilite_eleve,
            mois=mois,
            annee=annee,
            montant=etablissement.montant_mensualite,
            date_echeance=date_echeance,
            periode=periode,
            statut='en_attente',
            montant_paye=Decimal('0.00')
        )
        
        mensualites_creees += 1
    
    return mensualites_creees


def verifier_eleve_a_jour(eleve, annee_scolaire=None):
    """
    Vérifie si un élève est à jour dans ses paiements
    
    Args:
        eleve: Instance de Eleve
        annee_scolaire: Instance de AnneeScolaire (optionnel, utilise l'année active si non fourni)
    
    Returns:
        bool: True si l'élève est à jour, False sinon
    """
    if not annee_scolaire:
        annee_scolaire = AnneeScolaire.get_session_active(eleve.etablissement)
        if not annee_scolaire:
            return True  # Pas d'année scolaire active, considérer comme à jour
    
    comptabilite = ComptabiliteEleve.objects.filter(
        eleve=eleve,
        annee_scolaire=annee_scolaire
    ).first()
    
    if not comptabilite:
        return True  # Pas de comptabilité, considérer comme à jour
    
    # Vérifier le statut
    comptabilite.verifier_statut_paiement()
    
    return comptabilite.statut_paiement == 'a_jour'


def calculer_retard_mensualites(eleve, annee_scolaire=None):
    """
    Calcule le nombre de mensualités en retard pour un élève
    
    Args:
        eleve: Instance de Eleve
        annee_scolaire: Instance de AnneeScolaire (optionnel)
    
    Returns:
        int: Nombre de mensualités en retard
    """
    if not annee_scolaire:
        annee_scolaire = AnneeScolaire.get_session_active(eleve.etablissement)
        if not annee_scolaire:
            return 0
    
    maintenant = timezone.now().date()
    
    mensualites_en_retard = Mensualite.objects.filter(
        eleve=eleve,
        annee_scolaire=annee_scolaire,
        statut__in=['en_attente', 'en_retard', 'impaye'],
        date_echeance__lt=maintenant
    ).count()
    
    return mensualites_en_retard


def calculer_total_du_eleve(eleve, annee_scolaire=None):
    """
    Calcule le total dû par un élève
    
    Args:
        eleve: Instance de Eleve
        annee_scolaire: Instance de AnneeScolaire (optionnel)
    
    Returns:
        Decimal: Total dû
    """
    if not annee_scolaire:
        annee_scolaire = AnneeScolaire.get_session_active(eleve.etablissement)
        if not annee_scolaire:
            return Decimal('0.00')
    
    comptabilite = ComptabiliteEleve.objects.filter(
        eleve=eleve,
        annee_scolaire=annee_scolaire
    ).first()
    
    if not comptabilite:
        return Decimal('0.00')
    
    return comptabilite.calculer_total_du()


def calculer_total_paye_eleve(eleve, annee_scolaire=None):
    """
    Calcule le total payé par un élève
    
    Args:
        eleve: Instance de Eleve
        annee_scolaire: Instance de AnneeScolaire (optionnel)
    
    Returns:
        Decimal: Total payé
    """
    if not annee_scolaire:
        annee_scolaire = AnneeScolaire.get_session_active(eleve.etablissement)
        if not annee_scolaire:
            return Decimal('0.00')
    
    comptabilite = ComptabiliteEleve.objects.filter(
        eleve=eleve,
        annee_scolaire=annee_scolaire
    ).first()
    
    if not comptabilite:
        return Decimal('0.00')
    
    return comptabilite.calculer_total_paye()

