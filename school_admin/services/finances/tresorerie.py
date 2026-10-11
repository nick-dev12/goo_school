"""Comptes de trésorerie nommés. Le solde vient des écritures."""
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import CompteComptable, LigneEcriture
from school_admin.model.finances_model import CompteTresorerie
from school_admin.services.comptabilite_generale import (
    ajouter_compte,
    compte,
    ensure_plan_comptable,
)

COMPTES_DEFAUT = (
    ('caisse', 'Caisse principale', '571'),
    ('banque', 'Banque', '521'),
    ('mobile_money', 'Mobile money', '585'),
)


def assurer_comptes_defaut(etablissement):
    """Nomme les comptes déjà au plan. Solde initial à zéro : l'historique est déjà dans le journal."""
    ensure_plan_comptable(etablissement)
    devise = getattr(etablissement, 'devise_monnaie', '') or ''
    aujourd_hui = timezone.now().date()
    for type_compte, libelle, numero in COMPTES_DEFAUT:
        compte_plan = compte(etablissement, numero)
        if compte_plan is None:
            continue
        CompteTresorerie.objects.get_or_create(
            etablissement=etablissement,
            compte_comptable=compte_plan,
            defaults={
                'type_compte': type_compte,
                'libelle': libelle,
                'devise': devise[:10],
                'date_ouverture': aujourd_hui,
                'solde_initial': Decimal('0'),
                'statut': 'ouvert',
                'actif': True,
            },
        )


def compte_principal(etablissement, type_compte='caisse'):
    assurer_comptes_defaut(etablissement)
    return CompteTresorerie.objects.filter(
        etablissement=etablissement,
        type_compte=type_compte,
        actif=True,
        statut='ouvert',
    ).order_by('id').first()


def solde_calcule(compte_tresorerie, a_date=None):
    """Débit moins crédit des écritures validées. Le solde initial n'est pas ajouté."""
    lignes = LigneEcriture.objects.filter(
        compte=compte_tresorerie.compte_comptable,
        ecriture__etablissement=compte_tresorerie.etablissement,
        ecriture__validee=True,
    ).exclude(ecriture__source='a_nouveaux')  # les à-nouveaux reprennent un solde déjà compté
    if a_date is not None:
        lignes = lignes.filter(ecriture__date_ecriture__lte=a_date)
    totaux = lignes.aggregate(debit=Sum('debit'), credit=Sum('credit'))
    debit = totaux['debit'] or Decimal('0')
    credit = totaux['credit'] or Decimal('0')
    return debit - credit


def definir_solde_initial(compte_tresorerie, montant):
    """Refusé dès qu'une écriture existe. Aucune pièce d'ouverture n'est passée ici."""
    if LigneEcriture.objects.filter(
        compte=compte_tresorerie.compte_comptable,
        ecriture__etablissement=compte_tresorerie.etablissement,
    ).exists():
        raise ValueError(
            "Ce compte a déjà des écritures. Le solde initial ne peut plus être modifié."
        )
    compte_tresorerie.solde_initial = Decimal(montant)
    compte_tresorerie.save(update_fields=['solde_initial'])
    return compte_tresorerie


def ouvrir_compte(etablissement, type_compte, libelle, reference=''):
    """Nouveau compte nommé. Une banque de plus reçoit un sous-compte, pas un second 521."""
    prefixes = {
        'caisse': ('571', '5', 'actif'),
        'banque': ('521', '5', 'actif'),
        'mobile_money': ('585', '5', 'actif'),
        'autre': ('588', '5', 'actif'),
    }
    if type_compte not in prefixes:
        raise ValueError("Type de compte inconnu.")
    prefixe, classe, nature = prefixes[type_compte]
    ensure_plan_comptable(etablissement)
    numero = _prochain_numero(etablissement, prefixe)
    compte_plan = ajouter_compte(etablissement, numero, libelle, classe, nature)
    if CompteTresorerie.objects.filter(
        etablissement=etablissement,
        compte_comptable=compte_plan,
    ).exists():
        raise ValueError("Ce compte du plan est déjà relié à une trésorerie.")
    return CompteTresorerie.objects.create(
        etablissement=etablissement,
        type_compte=type_compte,
        libelle=libelle[:120],
        reference=(reference or '')[:80],
        compte_comptable=compte_plan,
        devise=(getattr(etablissement, 'devise_monnaie', '') or '')[:10],
        date_ouverture=timezone.now().date(),
        solde_initial=Decimal('0'),
    )


def _prochain_numero(etablissement, prefixe):
    deja = set(
        CompteComptable.objects.filter(
            etablissement=etablissement,
            numero__startswith=prefixe,
        ).values_list('numero', flat=True)
    )
    if prefixe not in deja:
        return prefixe
    n = 1
    while True:
        candidat = f"{prefixe}{n}"
        if candidat not in deja:
            return candidat
        n += 1
