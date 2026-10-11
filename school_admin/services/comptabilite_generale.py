"""Plan SYSCOHADA révisé (éducation), journaux, exercices et ponts d'écritures."""
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    Immobilisation,
    JournalComptable,
    LigneEcriture,
    PeriodeComptable,
)

# PCE §3.2 — SYSCOHADA révisé, subdivision éducation.
PLAN_SYSCOHADA_EDUCATION = [
    ('101', 'Capital / fonds de dotation', '1', 'passif'),
    ('111', 'Réserves', '1', 'passif'),
    ('121', 'Report à nouveau créditeur', '1', 'passif'),
    ('129', 'Report à nouveau débiteur', '1', 'passif'),
    ('1301', 'Résultat net — bénéfice', '1', 'passif'),
    ('1309', 'Résultat net — perte', '1', 'passif'),
    ('1621', 'Emprunts auprès des établissements de crédit', '1', 'passif'),
    ('211', 'Terrains', '2', 'actif'),
    ('213', 'Bâtiments scolaires', '2', 'actif'),
    ('2182', 'Matériel de transport (bus)', '2', 'actif'),
    ('2183', 'Matériel informatique', '2', 'actif'),
    ('2184', 'Mobilier de classe', '2', 'actif'),
    ('2188', 'Autres immobilisations corporelles', '2', 'actif'),
    ('2813', 'Amortissements bâtiments', '2', 'actif'),
    ('2818', 'Amortissements autres immobilisations', '2', 'actif'),
    ('401', 'Fournisseurs', '4', 'passif'),
    ('411', 'Clients — familles / élèves', '4', 'actif'),
    ('419', 'Clients créditeurs — avances familles', '4', 'passif'),
    ('421', 'Personnel — avances et acomptes', '4', 'actif'),
    ('422', 'Personnel — rémunérations dues', '4', 'passif'),
    ('4311', 'CSS (prestations familiales / AT)', '4', 'passif'),
    ('4312', 'IPRES (retraite)', '4', 'passif'),
    ('447', 'État — IR / retenues à la source', '4', 'passif'),
    ('4011', 'Fournisseurs d’immobilisations', '4', 'passif'),
    ('409', 'Fournisseurs débiteurs — avances versées', '4', 'actif'),
    ('471', 'Débiteurs / créditeurs divers', '4', 'passif'),
    ('476', 'Charges constatées d’avance', '4', 'actif'),
    ('477', 'Produits constatés d’avance', '4', 'passif'),
    ('521', 'Banques locales', '5', 'actif'),
    ('571', 'Caisse établissement', '5', 'actif'),
    ('585', 'Monnaie électronique / Mobile Money', '5', 'actif'),
    ('588', 'Virements de fonds internes', '5', 'actif'),
    ('604', 'Fournitures scolaires et de bureau', '6', 'charge'),
    ('605', 'Eau, électricité, fluides', '6', 'charge'),
    ('615', 'Entretien, réparations et maintenance', '6', 'charge'),
    ('616', 'Primes d’assurance', '6', 'charge'),
    ('622', 'Locations et charges locatives', '6', 'charge'),
    ('624', 'Transports / carburant', '6', 'charge'),
    ('628', 'Frais de télécommunications et internet', '6', 'charge'),
    ('631', 'Frais bancaires', '6', 'charge'),
    ('637', 'Personnel extérieur / vacations', '6', 'charge'),
    ('6611', 'Appointements et salaires — personnel national', '6', 'charge'),
    ('6641', 'Charges sociales patronales — CSS', '6', 'charge'),
    ('6642', 'Charges sociales patronales — IPRES', '6', 'charge'),
    ('667', 'Rémunérations de personnel extérieur (clôture)', '6', 'charge'),
    ('6711', 'Intérêts des emprunts', '6', 'charge'),
    ('6712', 'Frais sur emprunts', '6', 'charge'),
    ('646', 'Droits d’enregistrement et taxes', '6', 'charge'),
    ('658', 'Charges diverses', '6', 'charge'),
    ('681', 'Dotations aux amortissements', '6', 'charge'),
    ('7051', 'Prestations — droits d’inscription / réinscription', '7', 'produit'),
    ('7052', 'Prestations — scolarité (mensualités / forfait)', '7', 'produit'),
    ('7061', 'Produits accessoires — cantine, transport, tenues…', '7', 'produit'),
    ('7068', 'Autres produits scolaires', '7', 'produit'),
    ('711', 'Subventions d’exploitation / bourses', '7', 'produit'),
    ('758', 'Produits divers', '7', 'produit'),
    ('771', 'Intérêts et produits financiers', '7', 'produit'),
]

# Ancien numéro PCG / ancien SYSCOHADA → PCE révisé. Ordre : sources collisionnées d’abord.
REMAP_PCE = (
    ('622', '637'),  # vacations avant que 613 ne prenne 622
    ('613', '622'),
    ('421', '422'),
    ('431', '4311'),
    ('442', '447'),
    ('512', '521'),
    ('531', '571'),
    ('601', '604'),
    ('641', '6611'),
    ('645', '6641'),
    ('701', '7051'),
    ('702', '7052'),
    ('706', '7061'),
    ('708', '7068'),
)

COMPTE_FOURNISSEURS = '401'
COMPTE_CAISSE = '571'
COMPTE_BANQUE = '521'
COMPTE_MOBILE = '585'
COMPTE_CLIENTS = '411'
COMPTE_CHARGES_VACATAIRES = '637'
COMPTE_REMUNERATIONS_DUES = '422'
COMPTE_AMORT = '2813'
COMPTE_DOTATION = '681'
COMPTE_EMPRUNTS = '1621'
COMPTE_INTERETS_EMPRUNTS = '6711'
COMPTE_FRAIS_EMPRUNTS = '6712'

JOURNAUX_DEFAUT = [
    ('CAI', 'Caisse', COMPTE_CAISSE),
    ('BAN', 'Banque', COMPTE_BANQUE),
    ('ACH', 'Achats', '401'),
    ('SCO', 'Ventes / Scolarité', COMPTE_CLIENTS),
    ('OD', 'Opérations diverses', None),
    ('PAI', 'Paie', COMPTE_REMUNERATIONS_DUES),
    ('AN', 'À-nouveaux (ouverture)', None),
]

COMPTE_RESULTAT_BENEFICE = '1301'
COMPTE_RESULTAT_PERTE = '1309'
COMPTE_FOURNISSEURS_IMMO = '4011'

# Catégorie d'immobilisation → (compte d'immobilisation, compte d'amortissement).
COMPTES_IMMOBILISATION = {
    'batiment': ('213', '2813'),
    'bus': ('2182', '2818'),
    'informatique': ('2183', '2818'),
    'mobilier': ('2184', '2818'),
    'autre': ('2188', '2818'),
}

MOIS_FR = (
    '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
)

PLAN_PAR_NUMERO = {row[0]: row for row in PLAN_SYSCOHADA_EDUCATION}

# Préfixes classe 4 → passif (fournisseurs, dettes) vs actif (clients, créances).
_CLASSE4_PASSIF_PREFIXES = ('40', '42', '44', '45', '46', '47', '48', '49')


def infer_classe_nature_compte(numero):
    """
    Déduit classe et nature SYSCOHADA à partir du numéro de compte.
    Retourne (classe, nature, message_erreur).
    """
    raw = (numero or '').strip()
    if not raw:
        return None, None, 'Numéro de compte requis.'
    if not raw[0].isdigit():
        return None, None, 'Le numéro doit commencer par un chiffre (classe SYSCOHADA 1 à 8).'

    plan_row = PLAN_PAR_NUMERO.get(raw)
    if plan_row:
        _num, _lib, classe, nature = plan_row
        return classe, nature, None

    lead = raw[0]
    if lead not in '12345678':
        return None, None, 'Classe SYSCOHADA inconnue pour ce numéro.'

    classe = lead
    if lead == '1':
        nature = 'passif'
    elif lead in ('2', '3', '5'):
        nature = 'actif'
    elif lead == '4':
        nature = 'passif' if raw.startswith(_CLASSE4_PASSIF_PREFIXES) else 'actif'
    elif lead == '6':
        nature = 'charge'
    elif lead == '7':
        nature = 'produit'
    else:
        nature = 'hors'
    return classe, nature, None


REGIME_ENGAGEMENT = 'engagement'
REGIME_TRESORERIE = 'tresorerie'


def _meta_compte(numero):
    return PLAN_PAR_NUMERO.get(numero)


def ensure_plan_comptable(etablissement, _skip_remap=False):
    created = 0
    for numero, libelle, classe, nature in PLAN_SYSCOHADA_EDUCATION:
        obj, was_created = CompteComptable.objects.get_or_create(
            etablissement=etablissement,
            numero=numero,
            defaults={
                'libelle': libelle,
                'classe': classe,
                'nature': nature,
                'est_auxiliaire': numero in ('411', '401', '419', '422'),
                'actif': True,
            },
        )
        if was_created:
            created += 1
        else:
            updates = []
            if obj.libelle != libelle:
                obj.libelle = libelle
                updates.append('libelle')
            if obj.classe != classe:
                obj.classe = classe
                updates.append('classe')
            if obj.nature != nature:
                obj.nature = nature
                updates.append('nature')
            if not obj.actif:
                obj.actif = True
                updates.append('actif')
            if updates:
                obj.save(update_fields=updates)
    return created


def ensure_journaux(etablissement):
    ensure_plan_comptable(etablissement)
    created = 0
    for code, libelle, numero_compte in JOURNAUX_DEFAUT:
        compte_obj = None
        if numero_compte:
            compte_obj = CompteComptable.objects.filter(
                etablissement=etablissement, numero=numero_compte
            ).first()
        journal_obj, was_created = JournalComptable.objects.get_or_create(
            etablissement=etablissement,
            code=code,
            defaults={'libelle': libelle, 'compte_contrepartie': compte_obj},
        )
        if was_created:
            created += 1
        elif compte_obj and journal_obj.compte_contrepartie_id != compte_obj.id:
            journal_obj.compte_contrepartie = compte_obj
            journal_obj.save(update_fields=['compte_contrepartie'])
    return created


def _periodes_mois(exercice):
    current = date(exercice.date_debut.year, exercice.date_debut.month, 1)
    fin = exercice.date_fin
    while current <= fin:
        last_day = monthrange(current.year, current.month)[1]
        debut = max(current, exercice.date_debut)
        fin_mois = min(date(current.year, current.month, last_day), fin)
        yield {
            'type_periode': 'mois',
            'libelle': f"{MOIS_FR[current.month]} {current.year}",
            'date_debut': debut,
            'date_fin': fin_mois,
        }
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _periodes_civiles_agregats(exercice):
    year = exercice.date_debut.year
    return (
        {
            'type_periode': 'trimestre',
            'libelle': 'T1',
            'date_debut': date(year, 1, 1),
            'date_fin': date(year, 3, 31),
        },
        {
            'type_periode': 'trimestre',
            'libelle': 'T2',
            'date_debut': date(year, 4, 1),
            'date_fin': date(year, 6, 30),
        },
        {
            'type_periode': 'trimestre',
            'libelle': 'T3',
            'date_debut': date(year, 7, 1),
            'date_fin': date(year, 9, 30),
        },
        {
            'type_periode': 'trimestre',
            'libelle': 'T4',
            'date_debut': date(year, 10, 1),
            'date_fin': date(year, 12, 31),
        },
        {
            'type_periode': 'semestre',
            'libelle': 'S1',
            'date_debut': date(year, 1, 1),
            'date_fin': date(year, 6, 30),
        },
        {
            'type_periode': 'semestre',
            'libelle': 'S2',
            'date_debut': date(year, 7, 1),
            'date_fin': date(year, 12, 31),
        },
    )


def dates_exercice_civil(annee=None):
    year = annee or timezone.now().date().year
    return date(year, 1, 1), date(year, 12, 31), str(year)


def ensure_exercice(etablissement, annee_scolaire=None):
    """Exercice = année civile (1 janv.–31 déc.). L’année scolaire reste pédagogique."""
    ensure_journaux(etablissement)
    return _exercice_annee(etablissement, timezone.now().date().year, annee_scolaire)


def exercice_pour_date(etablissement, jour, annee_scolaire=None):
    """Exercice qui contient la date (créé au besoin : une année civile)."""
    existant = ExerciceComptable.objects.filter(
        etablissement=etablissement, date_debut__lte=jour, date_fin__gte=jour,
    ).first()
    if existant:
        return existant
    ensure_journaux(etablissement)
    return _exercice_annee(etablissement, jour.year, annee_scolaire)


def _exercice_annee(etablissement, year, annee_scolaire=None):
    debut, fin, libelle = dates_exercice_civil(year)

    exercice, created = ExerciceComptable.objects.get_or_create(
        etablissement=etablissement,
        libelle=libelle,
        defaults={
            'date_debut': debut,
            'date_fin': fin,
            'annee_scolaire': annee_scolaire,
            'statut': 'ouvert',
        },
    )
    updates = []
    if exercice.date_debut != debut or exercice.date_fin != fin:
        exercice.date_debut = debut
        exercice.date_fin = fin
        updates.extend(['date_debut', 'date_fin'])
    if annee_scolaire and exercice.annee_scolaire_id is None:
        exercice.annee_scolaire = annee_scolaire
        updates.append('annee_scolaire')
    if updates:
        exercice.save(update_fields=updates)

    if created or not exercice.periodes.filter(type_periode='mois').exists():
        for payload in _periodes_mois(exercice):
            PeriodeComptable.objects.get_or_create(
                exercice=exercice,
                type_periode=payload['type_periode'],
                libelle=payload['libelle'],
                defaults={
                    'date_debut': payload['date_debut'],
                    'date_fin': payload['date_fin'],
                },
            )
        for payload in _periodes_civiles_agregats(exercice):
            PeriodeComptable.objects.get_or_create(
                exercice=exercice,
                type_periode=payload['type_periode'],
                libelle=payload['libelle'],
                defaults={
                    'date_debut': payload['date_debut'],
                    'date_fin': payload['date_fin'],
                },
            )
    return exercice


def compte(etablissement, numero):
    return CompteComptable.objects.filter(
        etablissement=etablissement, numero=numero, actif=True
    ).first()


def journal(etablissement, code):
    return JournalComptable.objects.filter(
        etablissement=etablissement, code=code, actif=True
    ).first()


def periode_verrouillee(exercice, date_ecriture):
    return exercice.periodes.filter(
        verrouillee=True,
        date_debut__lte=date_ecriture,
        date_fin__gte=date_ecriture,
    ).exists()


def _prochain_numero(journal_obj):
    last = (
        EcritureComptable.objects.filter(journal=journal_obj)
        .order_by('-id')
        .values_list('numero', flat=True)
        .first()
    )
    if last and last.isdigit():
        return f"{int(last) + 1:06d}"
    count = EcritureComptable.objects.filter(journal=journal_obj).count() + 1
    return f"{count:06d}"


def regime_comptable_etablissement(etablissement):
    from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

    params = ParametresComptabilite.objects.filter(etablissement=etablissement).first()
    if params and params.regime_comptable == REGIME_TRESORERIE:
        return REGIME_TRESORERIE
    return REGIME_ENGAGEMENT


def get_or_create_parametres_comptabilite(etablissement):
    from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

    params, _ = ParametresComptabilite.objects.get_or_create(
        etablissement=etablissement,
        defaults={'regime_comptable': REGIME_ENGAGEMENT},
    )
    return params


def exercice_a_des_ecritures(exercice):
    return EcritureComptable.objects.filter(exercice=exercice).exists()


def regime_est_verrouille(etablissement, annee_scolaire=None):
    """Interdit de changer de régime dès qu’une pièce existe sur l’exercice civil ouvert."""
    exercice = ExerciceComptable.objects.filter(
        etablissement=etablissement,
        libelle=str(timezone.now().date().year),
        statut='ouvert',
    ).first()
    if exercice is None:
        return False
    return exercice_a_des_ecritures(exercice)


def _compte_treso_pour_mode(etablissement, mode_paiement):
    if mode_paiement == 'mobile_money':
        return compte(etablissement, COMPTE_MOBILE)
    if mode_paiement in ('virement', 'cheque', 'carte'):
        return compte(etablissement, COMPTE_BANQUE)
    return compte(etablissement, COMPTE_CAISSE)


def _journal_pour_mode(etablissement, mode_paiement):
    if mode_paiement in ('virement', 'cheque', 'carte', 'mobile_money'):
        return journal(etablissement, 'BAN')
    return journal(etablissement, 'CAI')


def _compte_produit_pour_type(etablissement, type_paiement):
    mapping = {
        'frais_inscription': '7051',
        'mensualite': '7052',
        'frais_annexe': '7061',
        'moratoire': '7052',
        'autre': '7068',
    }
    return compte(etablissement, mapping.get(type_paiement, '7068'))


def creer_ecriture(etablissement, exercice, journal_obj, date_ecriture, libelle, lignes, source='', source_id=None, reference='', user=None, ecriture_origine=None):
    # Une pièce appartient toujours à l'exercice qui contient sa date (paiement antidaté, clôture…).
    if exercice is None or not (exercice.date_debut <= date_ecriture <= exercice.date_fin):
        exercice = exercice_pour_date(etablissement, date_ecriture)
    if not exercice.est_ouvert():
        raise ValueError("L'exercice est clôturé.")
    if periode_verrouillee(exercice, date_ecriture):
        raise ValueError("Cette période comptable est verrouillée.")
    debit = sum((l.get('debit') or Decimal('0') for l in lignes), Decimal('0'))
    credit = sum((l.get('credit') or Decimal('0') for l in lignes), Decimal('0'))
    if debit != credit:
        raise ValueError("Écriture non équilibrée.")
    if debit <= 0:
        raise ValueError("Écriture sans montant.")
    with transaction.atomic():
        ecriture = EcritureComptable.objects.create(
            etablissement=etablissement,
            exercice=exercice,
            journal=journal_obj,
            numero=_prochain_numero(journal_obj),
            date_ecriture=date_ecriture,
            libelle=libelle[:200],
            reference=(reference or '')[:80],
            source=source,
            source_id=source_id,
            ecriture_origine=ecriture_origine,
            creee_par=user if user and user.__class__.__name__ == 'CompteUser' else None,
        )
        for ligne in lignes:
            LigneEcriture.objects.create(
                ecriture=ecriture,
                compte=ligne['compte'],
                libelle=(ligne.get('libelle') or libelle)[:200],
                debit=ligne.get('debit') or Decimal('0'),
                credit=ligne.get('credit') or Decimal('0'),
                auxiliaire=(ligne.get('auxiliaire') or '')[:80],
            )
    return ecriture


def extourner(ecriture, date_extourne, motif, user=None):
    """Contre-écriture. L'originale reste. Une seule extourne par pièce."""
    existante = EcritureComptable.objects.filter(source='extourne', source_id=ecriture.id).first()
    if existante:
        return existante
    if ecriture.source in ('extourne', 'a_nouveaux'):
        raise ValueError("Cette pièce ne peut pas être contrepassée.")
    exercice = exercice_pour_date(ecriture.etablissement, date_extourne)
    if not exercice.est_ouvert():
        raise ValueError("La date d'annulation tombe dans un exercice clôturé.")
    lignes = []
    for ligne in ecriture.lignes.select_related('compte'):
        lignes.append({
            'compte': ligne.compte,
            'debit': ligne.credit,
            'credit': ligne.debit,
            'libelle': (motif or ligne.libelle)[:200],
            'auxiliaire': ligne.auxiliaire,
        })
    if not lignes:
        raise ValueError("Cette écriture n'a aucune ligne à contrepasser.")
    return creer_ecriture(
        ecriture.etablissement,
        exercice,
        ecriture.journal,
        date_extourne,
        f"Annulation — {ecriture.libelle}"[:200],
        lignes,
        source='extourne',
        source_id=ecriture.id,
        reference=ecriture.numero,
        user=user,
        ecriture_origine=ecriture,
    )


def ajouter_compte(etablissement, numero, libelle, classe, nature='actif'):
    """Ajoute un compte au plan de l'école sans réécrire les comptes existants."""
    ensure_plan_comptable(etablissement)
    compte_obj, _created = CompteComptable.objects.get_or_create(
        etablissement=etablissement,
        numero=str(numero),
        defaults={
            'libelle': libelle[:160],
            'classe': classe,
            'nature': nature,
            'actif': True,
        },
    )
    return compte_obj


def pont_emission_creance(
    etablissement,
    montant,
    date_ecr,
    type_paiement,
    source,
    source_id,
    libelle,
    auxiliaire='',
    annee_scolaire=None,
    user=None,
):
    """Émission en régime engagement : D 411 / C 705x-706x. Idempotent. Skip si trésorerie."""
    if regime_comptable_etablissement(etablissement) != REGIME_ENGAGEMENT:
        return None
    if EcritureComptable.objects.filter(source=source, source_id=source_id).exists():
        return None
    montant = montant or Decimal('0')
    if montant <= 0:
        return None
    exercice = ensure_exercice(etablissement, annee_scolaire)
    jour = journal(etablissement, 'SCO')
    clients = compte(etablissement, COMPTE_CLIENTS)
    produit = _compte_produit_pour_type(etablissement, type_paiement)
    if not jour or not clients or not produit:
        return None
    return creer_ecriture(
        etablissement,
        exercice,
        jour,
        date_ecr,
        libelle,
        [
            {'compte': clients, 'debit': montant, 'credit': Decimal('0'), 'auxiliaire': auxiliaire},
            {'compte': produit, 'debit': Decimal('0'), 'credit': montant, 'auxiliaire': auxiliaire},
        ],
        source=source,
        source_id=source_id,
        user=user,
    )


def pont_paiement_eleve(paiement, annee_scolaire=None, user=None):
    """Encaissement : D 571/521/585 / C 411 (engagement) ou C 70x (trésorerie)."""
    if EcritureComptable.objects.filter(source='paiement_eleve', source_id=paiement.id).exists():
        return None
    etab = paiement.etablissement
    exercice = ensure_exercice(etab, annee_scolaire or paiement.annee_scolaire)
    jour = _journal_pour_mode(etab, paiement.mode_paiement)
    treso = _compte_treso_pour_mode(etab, paiement.mode_paiement)
    if regime_comptable_etablissement(etab) == REGIME_ENGAGEMENT:
        contrepartie = compte(etab, COMPTE_CLIENTS)
    else:
        contrepartie = _compte_produit_pour_type(etab, paiement.type_paiement)
    if not jour or not treso or not contrepartie:
        return None
    montant = paiement.montant or Decimal('0')
    if montant <= 0:
        return None
    date_ecr = paiement.date_paiement.date() if paiement.date_paiement else timezone.now().date()
    eleve_nom = getattr(paiement.eleve, 'nom_complet', str(paiement.eleve_id))
    return creer_ecriture(
        etab,
        exercice,
        jour,
        date_ecr,
        f"Encaissement scolarité — {eleve_nom}",
        [
            {'compte': treso, 'debit': montant, 'credit': Decimal('0'), 'auxiliaire': eleve_nom},
            {'compte': contrepartie, 'debit': Decimal('0'), 'credit': montant, 'auxiliaire': eleve_nom},
        ],
        source='paiement_eleve',
        source_id=paiement.id,
        reference=paiement.reference_paiement or '',
        user=user,
    )


def _comptes_sortie(depense):
    """Charge et trésorerie d'une sortie. La catégorie prime sur l'ancien motif."""
    etab = depense.etablissement
    mapping = {
        'salaire': '6611',
        'loyer': '622',
        'electricite': '605',
        'fournitures': '604',
        'carburant': '624',
        'autre': '604',
    }
    categorie = getattr(depense, 'categorie', None)
    if categorie is not None and categorie.compte_comptable_id:
        charge = categorie.compte_comptable
    else:
        charge = compte(etab, mapping.get(depense.motif, '604'))
    journal_code = 'CAI'
    tresorerie = getattr(depense, 'compte_tresorerie', None)
    if tresorerie is not None and tresorerie.compte_comptable_id:
        caisse = tresorerie.compte_comptable
        if tresorerie.type_compte in ('banque', 'mobile_money'):
            journal_code = 'BAN'
    else:
        caisse = compte(etab, COMPTE_CAISSE)
    return journal_code, charge, caisse


def pont_depense(depense, annee_scolaire=None, user=None):
    """Sortie caisse : D 6xx / C trésorerie."""
    if EcritureComptable.objects.filter(source='depense', source_id=depense.id).exists():
        return None
    etab = depense.etablissement
    exercice = ensure_exercice(etab, annee_scolaire or depense.annee_scolaire)
    journal_code, charge, caisse = _comptes_sortie(depense)
    jour = journal(etab, journal_code)
    if not jour or not caisse or not charge:
        return None
    montant = depense.montant or Decimal('0')
    if montant <= 0:
        return None
    return creer_ecriture(
        etab,
        exercice,
        jour,
        depense.date_depense,
        depense.libelle_affiche(),
        [
            {'compte': charge, 'debit': montant, 'credit': Decimal('0')},
            {'compte': caisse, 'debit': Decimal('0'), 'credit': montant},
        ],
        source='depense',
        source_id=depense.id,
        user=user,
    )


def _charge_facture(facture):
    categorie = getattr(facture, 'categorie', None)
    if categorie is not None and categorie.compte_comptable_id:
        return categorie.compte_comptable
    return compte(facture.etablissement, '604')


def _treso_paiement(paiement):
    tresorerie = getattr(paiement, 'compte_tresorerie', None)
    if tresorerie is not None and tresorerie.compte_comptable_id:
        code = 'BAN' if tresorerie.type_compte in ('banque', 'mobile_money') else 'CAI'
        return code, tresorerie.compte_comptable
    return 'CAI', compte(paiement.etablissement, COMPTE_CAISSE)


def pont_facture(facture, annee_scolaire=None, user=None):
    """Engagement : D charge / C 401. Trésorerie : aucune pièce à l'enregistrement de la facture."""
    if regime_comptable_etablissement(facture.etablissement) != REGIME_ENGAGEMENT:
        return None
    if EcritureComptable.objects.filter(source='facture', source_id=facture.id).exists():
        return None
    etab = facture.etablissement
    exercice = ensure_exercice(etab, annee_scolaire)
    jour = journal(etab, 'ACH')
    charge = _charge_facture(facture)
    fournisseur = compte(etab, COMPTE_FOURNISSEURS)
    if not jour or not charge or not fournisseur:
        return None
    montant = facture.montant or Decimal('0')
    if montant <= 0:
        return None
    return creer_ecriture(
        etab,
        exercice,
        jour,
        facture.date_facture,
        f"Facture {facture.numero} — {facture.fournisseur.nom}"[:200],
        [
            {'compte': charge, 'debit': montant, 'credit': Decimal('0')},
            {'compte': fournisseur, 'debit': Decimal('0'), 'credit': montant, 'auxiliaire': facture.fournisseur.nom},
        ],
        source='facture',
        source_id=facture.id,
        reference=facture.numero,
        user=user,
    )


def pont_paiement_charge(paiement, annee_scolaire=None, user=None):
    """Engagement : D 401 / C trésorerie. Trésorerie : D charge / C trésorerie."""
    if EcritureComptable.objects.filter(source='paiement_charge', source_id=paiement.id).exists():
        return None
    facture = paiement.facture
    etab = paiement.etablissement
    exercice = ensure_exercice(etab, annee_scolaire)
    journal_code, treso = _treso_paiement(paiement)
    jour = journal(etab, journal_code)
    if not jour or not treso:
        return None
    montant = paiement.montant or Decimal('0')
    if montant <= 0:
        return None
    if regime_comptable_etablissement(etab) == REGIME_ENGAGEMENT:
        contrepartie = compte(etab, COMPTE_FOURNISSEURS)
        libelle = f"Règlement facture {facture.numero}"
    else:
        contrepartie = _charge_facture(facture)
        libelle = f"Paiement facture {facture.numero}"
    if not contrepartie:
        return None
    return creer_ecriture(
        etab,
        exercice,
        jour,
        paiement.date_paiement,
        libelle[:200],
        [
            {'compte': contrepartie, 'debit': montant, 'credit': Decimal('0'), 'auxiliaire': facture.fournisseur.nom},
            {'compte': treso, 'debit': Decimal('0'), 'credit': montant, 'auxiliaire': facture.fournisseur.nom},
        ],
        source='paiement_charge',
        source_id=paiement.id,
        reference=facture.numero,
        user=user,
    )


def pont_paie(paie, annee_scolaire=None, user=None):
    """Paie enseignant : D 637 (vacataire) ou 6611 (permanent) pour le brut,
    C trésorerie pour le net versé, C 447 pour la retenue à la source."""
    if EcritureComptable.objects.filter(source='paie', source_id=paie.id).exists():
        return None
    etab = paie.etablissement
    exercice = ensure_exercice(etab, annee_scolaire or paie.annee_scolaire)
    jour = journal(etab, 'PAI')
    permanent = getattr(paie, 'type_contrat', '') == 'permanent'
    charge = compte(etab, '6611' if permanent else COMPTE_CHARGES_VACATAIRES)
    tresorerie = getattr(paie, 'compte_tresorerie', None)
    if tresorerie is not None and tresorerie.compte_comptable_id:
        treso = tresorerie.compte_comptable
    else:
        treso = compte(etab, COMPTE_CAISSE)
    if not jour or not charge or not treso:
        return None
    brut = paie.montant_brut or Decimal('0')
    net = paie.montant_net or Decimal('0')
    if brut <= 0:
        return None
    nom = getattr(paie.professeur, 'nom_complet', str(paie.professeur_id))
    date_ecr = paie.date_paiement.date() if paie.date_paiement else timezone.now().date()
    lignes = [
        {'compte': charge, 'debit': brut, 'credit': Decimal('0'), 'auxiliaire': nom},
        {'compte': treso, 'debit': Decimal('0'), 'credit': net, 'auxiliaire': nom},
    ]
    retenue = brut - net
    if retenue > 0:
        lignes.append({'compte': compte(etab, '447'), 'debit': Decimal('0'), 'credit': retenue, 'auxiliaire': nom})
    return creer_ecriture(
        etab,
        exercice,
        jour,
        date_ecr,
        f"Paie {'enseignant' if permanent else 'vacataire'} — {nom} "
        f"({paie.date_debut:%d/%m} au {paie.date_fin:%d/%m/%Y})"[:200],
        lignes,
        source='paie',
        source_id=paie.id,
        user=user,
    )


def pont_virement_interne(mouvement, annee_scolaire=None, user=None):
    etab = mouvement.etablissement
    exercice = ensure_exercice(etab, annee_scolaire)
    jour = journal(etab, 'OD')
    banque = compte(etab, COMPTE_BANQUE)
    caisse = compte(etab, COMPTE_CAISSE)
    if not jour or not banque or not caisse:
        return None
    montant = mouvement.montant or Decimal('0')
    ecriture = creer_ecriture(
        etab,
        exercice,
        jour,
        mouvement.date_mouvement,
        mouvement.libelle or 'Virement caisse vers banque',
        [
            {'compte': banque, 'debit': montant, 'credit': Decimal('0')},
            {'compte': caisse, 'debit': Decimal('0'), 'credit': montant},
        ],
        source='virement_interne',
        source_id=mouvement.id,
        user=user,
    )
    mouvement.ecriture = ecriture
    mouvement.save(update_fields=['ecriture'])
    return ecriture


def pont_transfert(mouvement, annee_scolaire=None, user=None):
    """Débit du compte d'arrivée, crédit du compte de départ. Aucune charge, aucun produit."""
    if mouvement.ecriture_id:
        return mouvement.ecriture
    if EcritureComptable.objects.filter(source='transfert', source_id=mouvement.id).exists():
        return EcritureComptable.objects.filter(source='transfert', source_id=mouvement.id).first()
    source = mouvement.compte_source
    destination = mouvement.compte_destination
    if source is None or destination is None:
        return None
    if source.compte_comptable.classe != '5' or destination.compte_comptable.classe != '5':
        raise ValueError("Un transfert ne passe que par des comptes de trésorerie.")
    etab = mouvement.etablissement
    exercice = ensure_exercice(etab, annee_scolaire)
    jour = journal(etab, 'OD')
    if not jour:
        return None
    montant = mouvement.montant or Decimal('0')
    if montant <= 0:
        return None
    libelle = mouvement.libelle or f"Transfert {source.libelle} vers {destination.libelle}"
    ecriture = creer_ecriture(
        etab,
        exercice,
        jour,
        mouvement.date_mouvement,
        libelle[:200],
        [
            {'compte': destination.compte_comptable, 'debit': montant, 'credit': Decimal('0')},
            {'compte': source.compte_comptable, 'debit': Decimal('0'), 'credit': montant},
        ],
        source='transfert',
        source_id=mouvement.id,
        reference=mouvement.reference or '',
        user=user,
    )
    mouvement.ecriture = ecriture
    mouvement.save(update_fields=['ecriture'])
    return ecriture


def pont_recette(recette, annee_scolaire=None, user=None):
    """Encaissement complémentaire : débit trésorerie, crédit du compte de la catégorie."""
    existante = EcritureComptable.objects.filter(source='recette', source_id=recette.id).first()
    if existante:
        return existante
    categorie = getattr(recette, 'categorie', None)
    if categorie is None or not categorie.compte_comptable_id:
        return None
    journal_code, treso = _treso_paiement(recette)
    jour = journal(recette.etablissement, journal_code)
    produit = categorie.compte_comptable
    if not jour or not treso or not produit:
        return None
    montant = recette.montant or Decimal('0')
    if montant <= 0:
        return None
    libelle = recette.libelle or f"Recette {recette.get_nature_display()}"
    return creer_ecriture(
        recette.etablissement,
        ensure_exercice(recette.etablissement, annee_scolaire or recette.annee_scolaire),
        jour,
        recette.date_recette,
        libelle[:200],
        [
            {'compte': treso, 'debit': montant, 'credit': Decimal('0')},
            {'compte': produit, 'debit': Decimal('0'), 'credit': montant},
        ],
        source='recette',
        source_id=recette.id,
        reference=recette.reference or '',
        user=user,
    )


def pont_remboursement_operation(remboursement, annee_scolaire=None, user=None):
    """Contrepartie du remboursement : débit du compte de la recette, crédit trésorerie."""
    existante = EcritureComptable.objects.filter(
        source='remboursement_operation', source_id=remboursement.id
    ).first()
    if existante:
        return existante
    from school_admin.model.finances_model import RecetteEtablissement

    operation = remboursement.operation
    if not isinstance(operation, RecetteEtablissement):
        raise ValueError("Ce remboursement ne porte que sur une recette de l'établissement.")
    categorie = operation.categorie
    if categorie is None or not categorie.compte_comptable_id:
        return None
    journal_code, treso = _treso_paiement(remboursement)
    jour = journal(remboursement.etablissement, journal_code)
    if not jour or not treso:
        return None
    montant = remboursement.montant or Decimal('0')
    if montant <= 0:
        return None
    return creer_ecriture(
        remboursement.etablissement,
        ensure_exercice(remboursement.etablissement, annee_scolaire or operation.annee_scolaire),
        jour,
        remboursement.date_remboursement,
        f"Remboursement — {operation.libelle or operation.get_nature_display()}"[:200],
        [
            {'compte': categorie.compte_comptable, 'debit': montant, 'credit': Decimal('0')},
            {'compte': treso, 'debit': Decimal('0'), 'credit': montant},
        ],
        source='remboursement_operation',
        source_id=remboursement.id,
        reference=operation.reference or '',
        user=user,
    )


def pont_pret(pret, annee_scolaire=None, user=None):
    """Réception : débit trésorerie, crédit 1621. Aucun produit, aucune charge."""
    existante = EcritureComptable.objects.filter(source='pret', source_id=pret.id).first()
    if existante:
        return existante
    ensure_plan_comptable(pret.etablissement)
    journal_code, treso = _treso_paiement(pret)
    jour = journal(pret.etablissement, journal_code)
    dette = compte(pret.etablissement, COMPTE_EMPRUNTS)
    if not jour or not treso or not dette:
        return None
    if treso.classe != '5':
        raise ValueError("La réception d'un prêt passe par un compte de trésorerie.")
    montant = pret.montant or Decimal('0')
    if montant <= 0:
        return None
    return creer_ecriture(
        pret.etablissement,
        ensure_exercice(pret.etablissement, annee_scolaire or pret.annee_scolaire),
        jour,
        pret.date_reception,
        f"Réception prêt {pret.reference}"[:200],
        [
            {'compte': treso, 'debit': montant, 'credit': Decimal('0')},
            {'compte': dette, 'debit': Decimal('0'), 'credit': montant},
        ],
        source='pret',
        source_id=pret.id,
        reference=pret.reference,
        user=user,
    )


def pont_remboursement_pret(remboursement, annee_scolaire=None, user=None):
    """Capital au débit de la dette, intérêts et frais en charges, total au crédit de la trésorerie."""
    existante = EcritureComptable.objects.filter(
        source='remboursement_pret', source_id=remboursement.id
    ).first()
    if existante:
        return existante
    etab = remboursement.etablissement
    ensure_plan_comptable(etab)
    journal_code, treso = _treso_paiement(remboursement)
    jour = journal(etab, journal_code)
    if not jour or not treso:
        return None
    if treso.classe != '5':
        raise ValueError("Le remboursement d'un prêt passe par un compte de trésorerie.")
    capital = remboursement.capital or Decimal('0')
    interets = remboursement.interets or Decimal('0')
    frais = remboursement.frais or Decimal('0')
    total = capital + interets + frais
    if total <= 0:
        return None
    lignes = []
    if capital > 0:
        dette = compte(etab, COMPTE_EMPRUNTS)
        if not dette:
            return None
        lignes.append({'compte': dette, 'debit': capital, 'credit': Decimal('0')})
    if interets > 0:
        charge = compte(etab, COMPTE_INTERETS_EMPRUNTS)
        if not charge:
            return None
        lignes.append({'compte': charge, 'debit': interets, 'credit': Decimal('0')})
    if frais > 0:
        charge = compte(etab, COMPTE_FRAIS_EMPRUNTS)
        if not charge:
            return None
        lignes.append({'compte': charge, 'debit': frais, 'credit': Decimal('0')})
    lignes.append({'compte': treso, 'debit': Decimal('0'), 'credit': total})
    return creer_ecriture(
        etab,
        ensure_exercice(etab, annee_scolaire or remboursement.pret.annee_scolaire),
        jour,
        remboursement.date_remboursement,
        f"Remboursement prêt {remboursement.pret.reference}"[:200],
        lignes,
        source='remboursement_pret',
        source_id=remboursement.id,
        reference=remboursement.pret.reference,
        user=user,
    )


def comptes_immobilisation(immo):
    """(compte d'immobilisation, compte d'amortissement) de la catégorie du bien."""
    etab = immo.etablissement
    num_immo, num_amort = COMPTES_IMMOBILISATION.get(immo.categorie, COMPTES_IMMOBILISATION['autre'])
    cpt_immo = immo.compte_immobilisation or compte(etab, num_immo)
    return cpt_immo, compte(etab, num_amort)


def pont_acquisition_immobilisation(immo, compte_tresorerie=None, fournisseur=None, user=None):
    """Achat d'un bien : débit 2xx, crédit trésorerie (comptant) ou 4011 (à crédit)."""
    existante = EcritureComptable.objects.filter(source='acquisition_immo', source_id=immo.id).first()
    if existante:
        return existante
    etab = immo.etablissement
    ensure_journaux(etab)
    cpt_immo, _amort = comptes_immobilisation(immo)
    if compte_tresorerie is not None:
        code = 'BAN' if compte_tresorerie.type_compte in ('banque', 'mobile_money') else 'CAI'
        contrepartie = compte_tresorerie.compte_comptable
        auxiliaire = ''
    else:
        code = 'ACH'
        contrepartie = compte(etab, COMPTE_FOURNISSEURS_IMMO)
        auxiliaire = getattr(fournisseur, 'nom', '') or ''
    jour = journal(etab, code)
    if not jour or not cpt_immo or not contrepartie:
        return None
    montant = immo.valeur_origine or Decimal('0')
    return creer_ecriture(
        etab, None, jour, immo.date_acquisition, f"Acquisition — {immo.libelle}"[:200],
        [
            {'compte': cpt_immo, 'debit': montant, 'credit': Decimal('0')},
            {'compte': contrepartie, 'debit': Decimal('0'), 'credit': montant, 'auxiliaire': auxiliaire},
        ],
        source='acquisition_immo', source_id=immo.id, user=user,
    )


def plan_amortissement(immo):
    """Plan linéaire par année civile, au prorata des mois la première année."""
    base = immo.valeur_origine or Decimal('0')
    duree = max(int(immo.duree_annees or 1), 1)
    annuite = base / Decimal(duree)
    rows = []
    cumul = Decimal('0')
    annee = immo.date_acquisition.year
    mois_premiere = Decimal(13 - immo.date_acquisition.month)
    while cumul < base and len(rows) < duree + 2:
        dotation = annuite * (mois_premiere / Decimal(12)) if not rows else annuite
        dotation = min(dotation.quantize(Decimal('0.01')), base - cumul)
        cumul += dotation
        rows.append({'annee': annee, 'dotation': dotation, 'cumul': cumul, 'vnc': base - cumul})
        annee += 1
    return rows


def dotation_pour_annee(immo, annee):
    for row in plan_amortissement(immo):
        if row['annee'] == annee:
            return row['dotation']
    return Decimal('0')


def amortissements_comptabilises(immo):
    agg = LigneEcriture.objects.filter(
        ecriture__source__startswith=f"amort-{immo.id}-", credit__gt=0,
    ).aggregate(s=Sum('credit'))
    return agg['s'] or Decimal('0')


def pont_amortissement(immo, annee_scolaire=None, user=None, exercice=None):
    """Dotation de l'exercice : débit 681, crédit 28xx. Une seule par bien et par exercice."""
    etab = immo.etablissement
    exercice = exercice or ensure_exercice(etab, annee_scolaire)
    jour = journal(etab, 'OD')
    charge = compte(etab, COMPTE_DOTATION)
    _immo, amort = comptes_immobilisation(immo)
    if not jour or not charge or not amort:
        return None
    source_key = f"amort-{immo.id}-{exercice.libelle}"
    if EcritureComptable.objects.filter(source=source_key[:40]).exists():
        raise ValueError(f"La dotation {exercice.libelle} de « {immo.libelle} » est déjà passée.")
    montant = dotation_pour_annee(immo, exercice.date_debut.year)
    if montant <= 0:
        raise ValueError(f"« {immo.libelle} » n'a pas de dotation pour {exercice.libelle}.")
    return creer_ecriture(
        etab,
        exercice,
        jour,
        exercice.date_fin,
        f"Dotation amortissement {exercice.libelle} — {immo.libelle}"[:200],
        [
            {'compte': charge, 'debit': montant, 'credit': Decimal('0')},
            {'compte': amort, 'debit': Decimal('0'), 'credit': montant},
        ],
        source=source_key[:40],
        source_id=immo.id,
        user=user,
    )


def ecritures_depenses_orphelines(etablissement):
    """Écritures source=depense dont la dépense école n'existe plus. Lecture seule."""
    from school_admin.model.caisse_etablissement_model import DepenseEtablissement

    depense_ids = DepenseEtablissement.objects.filter(etablissement=etablissement).values('id')
    return (
        EcritureComptable.objects.filter(etablissement=etablissement, source='depense')
        .exclude(source_id__in=depense_ids)
        .order_by('-date_ecriture', '-id')
    )


def snapshot_soldes(etablissement, exercice=None):
    """Soldes par numéro de compte (toutes écritures validées, exercice optionnel)."""
    lignes = LigneEcriture.objects.filter(
        compte__etablissement=etablissement,
        ecriture__validee=True,
    )
    if exercice is not None:
        lignes = lignes.filter(ecriture__exercice=exercice)
    else:
        # Tous exercices confondus : les à-nouveaux dupliqueraient les soldes reportés.
        lignes = lignes.exclude(ecriture__source='a_nouveaux')
    agg = lignes.values('compte__numero').annotate(d=Sum('debit'), c=Sum('credit'))
    return {
        row['compte__numero']: (row['d'] or Decimal('0')) - (row['c'] or Decimal('0'))
        for row in agg
    }


def _appliquer_remap_compte(etablissement, ancien, nouveau, dry_run=False):
    """Renomme ou fusionne un compte. Idempotent (622 peut être source puis cible)."""
    old_cpt = CompteComptable.objects.filter(etablissement=etablissement, numero=ancien).first()
    if old_cpt is None:
        return {'ancien': ancien, 'nouveau': nouveau, 'action': 'absent'}
    new_cpt = CompteComptable.objects.filter(etablissement=etablissement, numero=nouveau).first()
    sources_de_ancien = [src for src, dest in REMAP_PCE if dest == ancien]
    if new_cpt and sources_de_ancien:
        # 622 est aussi la cible de 613 : s’il reste 622 et déjà 637, 622 est le nouveau compte locations.
        encore_source = CompteComptable.objects.filter(
            etablissement=etablissement, numero__in=sources_de_ancien
        ).exists()
        if not encore_source:
            return {'ancien': ancien, 'nouveau': nouveau, 'action': 'conserve_cible'}

    meta = _meta_compte(nouveau)
    if new_cpt is None:
        if dry_run:
            return {'ancien': ancien, 'nouveau': nouveau, 'action': 'renommer', 'compte_id': old_cpt.id}
        old_cpt.numero = nouveau
        if meta:
            old_cpt.libelle = meta[1]
            old_cpt.classe = meta[2]
            old_cpt.nature = meta[3]
        old_cpt.actif = True
        old_cpt.save(update_fields=['numero', 'libelle', 'classe', 'nature', 'actif'])
        return {'ancien': ancien, 'nouveau': nouveau, 'action': 'renomme', 'compte_id': old_cpt.id}

    if old_cpt.id == new_cpt.id:
        return {'ancien': ancien, 'nouveau': nouveau, 'action': 'deja'}

    nb_lignes = LigneEcriture.objects.filter(compte=old_cpt).count()
    if dry_run:
        return {
            'ancien': ancien,
            'nouveau': nouveau,
            'action': 'fusionner',
            'lignes': nb_lignes,
            'depuis': old_cpt.id,
            'vers': new_cpt.id,
        }
    LigneEcriture.objects.filter(compte=old_cpt).update(compte=new_cpt)
    JournalComptable.objects.filter(compte_contrepartie=old_cpt).update(compte_contrepartie=new_cpt)
    Immobilisation.objects.filter(compte_immobilisation=old_cpt).update(compte_immobilisation=new_cpt)
    if meta:
        new_cpt.libelle = meta[1]
        new_cpt.classe = meta[2]
        new_cpt.nature = meta[3]
        new_cpt.actif = True
        new_cpt.save(update_fields=['libelle', 'classe', 'nature', 'actif'])
    archive = f"{ancien}-old-{old_cpt.id}"
    if len(archive) > 12:
        archive = f"x{old_cpt.id}"[:12]
    old_cpt.actif = False
    old_cpt.numero = archive
    old_cpt.save(update_fields=['actif', 'numero'])
    return {
        'ancien': ancien,
        'nouveau': nouveau,
        'action': 'fusionne',
        'lignes': nb_lignes,
        'depuis': old_cpt.id,
        'vers': new_cpt.id,
    }


def migrer_plan_syscohada(etablissement, dry_run=False):
    """Renumérote le plan ensemencé. Idempotent. Soldes globaux inchangés (mêmes lignes)."""
    avant = snapshot_soldes(etablissement)
    actions = []
    for ancien, nouveau in REMAP_PCE:
        actions.append(_appliquer_remap_compte(etablissement, ancien, nouveau, dry_run=dry_run))
    created = 0
    if not dry_run:
        created = ensure_plan_comptable(etablissement, _skip_remap=True)
        ensure_journaux(etablissement)
    apres = snapshot_soldes(etablissement) if not dry_run else avant
    soldes_ok = _soldes_equivalents(avant, apres, actions)
    return {
        'etablissement_id': etablissement.id,
        'actions': actions,
        'comptes_crees': created,
        'soldes_avant': avant,
        'soldes_apres': apres,
        'soldes_identiques': soldes_ok,
    }


def _soldes_equivalents(avant, apres, actions):
    """Compare les soldes en tenant compte du remap ancien → nouveau."""
    remap = {a: n for a, n in REMAP_PCE}
    attendu = {}
    for numero, solde in avant.items():
        cible = remap.get(numero, numero)
        if cible.endswith('-old'):
            continue
        attendu[cible] = attendu.get(cible, Decimal('0')) + solde
    for numero, solde in apres.items():
        if numero.endswith('-old'):
            continue
        if attendu.get(numero, Decimal('0')) != solde:
            return False
    for numero, solde in attendu.items():
        if apres.get(numero, Decimal('0')) != solde:
            return False
    return True


def _reste_creance(obj):
    if hasattr(obj, 'get_reste_a_payer'):
        return obj.get_reste_a_payer() or Decimal('0')
    montant = obj.montant or Decimal('0')
    paye = obj.montant_paye or Decimal('0')
    return montant - paye


def _type_paiement_creance(kind, obj=None):
    if kind == 'inscription':
        return 'frais_inscription'
    if kind == 'mensualite':
        return 'mensualite'
    if kind == 'annexe':
        return 'frais_annexe'
    return 'autre'


def backfill_creances_ouvertes(etablissement, annee_scolaire=None, dry_run=False, user=None):
    """
    Émet D 411 / C 70x pour le *reste à payer* uniquement.
    Les encaissements déjà pontés en 70x ne sont pas rejoués (pas de double produit).
    """
    from school_admin.model.comptabilite_eleve_model import FraisAnnexe, FraisInscription, Mensualite

    if regime_comptable_etablissement(etablissement) != REGIME_ENGAGEMENT:
        return {'emises': 0, 'ignorees': 0, 'raison': 'tresorerie'}

    ensure_journaux(etablissement)
    today = timezone.now().date()
    emises = 0
    ignorees = 0
    details = []

    def _traiter(qs, kind, source):
        nonlocal emises, ignorees
        for obj in qs:
            reste = _reste_creance(obj)
            if reste <= 0:
                ignorees += 1
                continue
            if EcritureComptable.objects.filter(source=source, source_id=obj.id).exists():
                ignorees += 1
                continue
            eleve_nom = getattr(obj.eleve, 'nom_complet', str(obj.eleve_id))
            date_ecr = getattr(obj, 'date_echeance', None) or today
            libelle = f"Créance {kind} — {eleve_nom}"
            details.append({
                'source': source,
                'source_id': obj.id,
                'montant': reste,
                'libelle': libelle,
            })
            if dry_run:
                emises += 1
                continue
            pont_emission_creance(
                etablissement,
                reste,
                date_ecr,
                _type_paiement_creance(kind, obj),
                source,
                obj.id,
                libelle,
                auxiliaire=eleve_nom,
                annee_scolaire=annee_scolaire or getattr(obj, 'annee_scolaire', None),
                user=user,
            )
            emises += 1

    filtres = {'etablissement': etablissement}
    if annee_scolaire:
        filtres['annee_scolaire'] = annee_scolaire

    _traiter(
        FraisInscription.objects.filter(**filtres).exclude(statut='paye').select_related('eleve'),
        'inscription',
        'creance_inscription',
    )
    _traiter(
        Mensualite.objects.filter(**filtres).exclude(statut='paye').select_related('eleve'),
        'mensualite',
        'creance_mensualite',
    )
    _traiter(
        FraisAnnexe.objects.filter(**filtres).exclude(statut='paye').select_related('eleve'),
        'annexe',
        'creance_annexe',
    )
    return {'emises': emises, 'ignorees': ignorees, 'details': details, 'dry_run': dry_run}


def enregistrer_regime_comptable(etablissement, nouveau_regime, annee_scolaire=None):
    """Change le régime seulement s’il n’y a pas d’écriture sur l’exercice civil ouvert."""
    if nouveau_regime not in (REGIME_ENGAGEMENT, REGIME_TRESORERIE):
        raise ValueError("Régime inconnu.")
    params = get_or_create_parametres_comptabilite(etablissement)
    if params.regime_comptable == nouveau_regime:
        return params, False
    if regime_est_verrouille(etablissement, annee_scolaire):
        raise ValueError(
            "Impossible de changer de régime en cours d’exercice : des écritures existent déjà."
        )
    from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

    ParametresComptabilite.objects.filter(pk=params.pk).update(regime_comptable=nouveau_regime)
    params.regime_comptable = nouveau_regime
    if nouveau_regime == REGIME_ENGAGEMENT:
        backfill_creances_ouvertes(etablissement, annee_scolaire=annee_scolaire)
    return params, True


def soldes_par_compte(etablissement, exercice):
    rows = []
    for cpt in CompteComptable.objects.filter(etablissement=etablissement, actif=True):
        agg = LigneEcriture.objects.filter(
            compte=cpt,
            ecriture__exercice=exercice,
            ecriture__validee=True,
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        debit = agg['d'] or Decimal('0')
        credit = agg['c'] or Decimal('0')
        rows.append({
            'compte': cpt,
            'debit': debit,
            'credit': credit,
            'solde': debit - credit,
        })
    return rows


def synthese_bilan(etablissement, exercice):
    rows = soldes_par_compte(etablissement, exercice)
    actif = sum((r['solde'] for r in rows if r['compte'].nature == 'actif'), Decimal('0'))
    passif = sum((-r['solde'] for r in rows if r['compte'].nature == 'passif'), Decimal('0'))
    charges = sum((r['debit'] - r['credit'] for r in rows if r['compte'].nature == 'charge'), Decimal('0'))
    produits = sum((r['credit'] - r['debit'] for r in rows if r['compte'].nature == 'produit'), Decimal('0'))
    return {
        'actif': actif,
        'passif': passif,
        'charges': charges,
        'produits': produits,
        'resultat': produits - charges,
        'rows': rows,
    }


def kpi_cg(etablissement, annee_scolaire=None):
    from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve, PaiementEleve
    from school_admin.services.caisse import bornes_mois, solde_mois, total_depenses, total_recettes

    today = timezone.now().date()
    bornes = bornes_mois(today)
    entrees = total_recettes(etablissement, bornes.debut, bornes.fin)
    sorties = total_depenses(etablissement, bornes.debut, bornes.fin)
    solde = solde_mois(etablissement, bornes.debut, bornes.fin)

    total_du = Decimal('0')
    total_paye = Decimal('0')
    qs = ComptabiliteEleve.objects.filter(etablissement=etablissement)
    if annee_scolaire:
        qs = qs.filter(annee_scolaire=annee_scolaire)
    for cpta in qs.select_related('eleve')[:800]:
        total_du += cpta.calculer_total_du()
        total_paye += cpta.calculer_total_paye()
    taux = Decimal('0')
    if total_du > 0:
        taux = ((total_paye / total_du) * Decimal('100')).quantize(Decimal('0.1'))

    return {
        'entrees_mois': entrees,
        'sorties_mois': sorties,
        'solde_mois': solde,
        'taux_recouvrement': taux,
        'total_du': total_du,
        'total_paye': total_paye,
        'nb_ecritures': EcritureComptable.objects.filter(etablissement=etablissement).count(),
        'nb_paiements': PaiementEleve.objects.filter(etablissement=etablissement).count(),
    }
