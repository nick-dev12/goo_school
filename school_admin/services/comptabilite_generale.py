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
    ('471', 'Débiteurs / créditeurs divers', '4', 'passif'),
    ('521', 'Banques locales', '5', 'actif'),
    ('571', 'Caisse établissement', '5', 'actif'),
    ('585', 'Monnaie électronique / Mobile Money', '5', 'actif'),
    ('588', 'Virements de fonds internes', '5', 'actif'),
    ('604', 'Fournitures scolaires et de bureau', '6', 'charge'),
    ('605', 'Eau, électricité, fluides', '6', 'charge'),
    ('622', 'Locations et charges locatives', '6', 'charge'),
    ('624', 'Transports / carburant', '6', 'charge'),
    ('637', 'Personnel extérieur / vacations', '6', 'charge'),
    ('6611', 'Appointements et salaires — personnel national', '6', 'charge'),
    ('6641', 'Charges sociales patronales — CSS', '6', 'charge'),
    ('6642', 'Charges sociales patronales — IPRES', '6', 'charge'),
    ('667', 'Rémunérations de personnel extérieur (clôture)', '6', 'charge'),
    ('681', 'Dotations aux amortissements', '6', 'charge'),
    ('7051', 'Prestations — droits d’inscription / réinscription', '7', 'produit'),
    ('7052', 'Prestations — scolarité (mensualités / forfait)', '7', 'produit'),
    ('7061', 'Produits accessoires — cantine, transport, tenues…', '7', 'produit'),
    ('7068', 'Autres produits scolaires', '7', 'produit'),
    ('711', 'Subventions d’exploitation / bourses', '7', 'produit'),
    ('758', 'Produits divers', '7', 'produit'),
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

COMPTE_CAISSE = '571'
COMPTE_BANQUE = '521'
COMPTE_MOBILE = '585'
COMPTE_CLIENTS = '411'
COMPTE_CHARGES_VACATAIRES = '637'
COMPTE_REMUNERATIONS_DUES = '422'
COMPTE_AMORT = '2813'
COMPTE_DOTATION = '681'

JOURNAUX_DEFAUT = [
    ('CAI', 'Caisse', COMPTE_CAISSE),
    ('BAN', 'Banque', COMPTE_BANQUE),
    ('ACH', 'Achats', '401'),
    ('SCO', 'Ventes / Scolarité', COMPTE_CLIENTS),
    ('OD', 'Opérations diverses', None),
    ('PAI', 'Paie', COMPTE_REMUNERATIONS_DUES),
]

MOIS_FR = (
    '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
)

PLAN_PAR_NUMERO = {row[0]: row for row in PLAN_SYSCOHADA_EDUCATION}

REGIME_ENGAGEMENT = 'engagement'
REGIME_TRESORERIE = 'tresorerie'


def _meta_compte(numero):
    return PLAN_PAR_NUMERO.get(numero)


def ensure_plan_comptable(etablissement, _skip_remap=False):
    created = 0
    for numero, libelle, classe, nature in PLAN_SYSCOHADA_EDUCATION:
        _, was_created = CompteComptable.objects.get_or_create(
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
    today = timezone.now().date()
    debut, fin, libelle = dates_exercice_civil(today.year)

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


def creer_ecriture(etablissement, exercice, journal_obj, date_ecriture, libelle, lignes, source='', source_id=None, reference='', user=None):
    if not exercice.est_ouvert():
        raise ValueError("L'exercice est clôturé.")
    if periode_verrouillee(exercice, date_ecriture):
        raise ValueError("Cette période comptable est verrouillée.")
    debit = sum((l['debit'] for l in lignes), Decimal('0'))
    credit = sum((l['credit'] for l in lignes), Decimal('0'))
    if debit != credit:
        raise ValueError("Écriture non équilibrée.")
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


def pont_depense(depense, annee_scolaire=None, user=None):
    """Sortie caisse : D 6xx / C 571."""
    if EcritureComptable.objects.filter(source='depense', source_id=depense.id).exists():
        return None
    etab = depense.etablissement
    exercice = ensure_exercice(etab, annee_scolaire or depense.annee_scolaire)
    jour = journal(etab, 'CAI')
    caisse = compte(etab, COMPTE_CAISSE)
    mapping = {
        'salaire': '6611',
        'loyer': '622',
        'electricite': '605',
        'fournitures': '604',
        'carburant': '624',
        'autre': '604',
    }
    charge = compte(etab, mapping.get(depense.motif, '604'))
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


def pont_paie(paie, annee_scolaire=None, user=None):
    """Paie vacataire : D 637 / C 571 (net versé). Permanents hors étape 1."""
    if EcritureComptable.objects.filter(source='paie', source_id=paie.id).exists():
        return None
    etab = paie.etablissement
    exercice = ensure_exercice(etab, annee_scolaire or paie.annee_scolaire)
    jour = journal(etab, 'PAI')
    charge = compte(etab, COMPTE_CHARGES_VACATAIRES)
    caisse = compte(etab, COMPTE_CAISSE)
    if not jour or not charge or not caisse:
        return None
    montant = paie.montant_net or Decimal('0')
    if montant <= 0:
        return None
    nom = getattr(paie.professeur, 'nom_complet', str(paie.professeur_id))
    date_ecr = paie.date_paiement.date() if paie.date_paiement else timezone.now().date()
    return creer_ecriture(
        etab,
        exercice,
        jour,
        date_ecr,
        f"Paie vacataire — {nom}",
        [
            {'compte': charge, 'debit': montant, 'credit': Decimal('0'), 'auxiliaire': nom},
            {'compte': caisse, 'debit': Decimal('0'), 'credit': montant},
        ],
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


def pont_amortissement(immo, annee_scolaire=None, user=None):
    etab = immo.etablissement
    exercice = ensure_exercice(etab, annee_scolaire)
    jour = journal(etab, 'OD')
    charge = compte(etab, COMPTE_DOTATION)
    amort = compte(etab, COMPTE_AMORT)
    if not jour or not charge or not amort:
        return None
    montant = immo.dotation_annuelle()
    if montant <= 0:
        return None
    source_key = f"amort-{immo.id}-{exercice.libelle}"
    if EcritureComptable.objects.filter(source=source_key).exists():
        return None
    return creer_ecriture(
        etab,
        exercice,
        jour,
        timezone.now().date(),
        f"Dotation amortissement — {immo.libelle}",
        [
            {'compte': charge, 'debit': montant, 'credit': Decimal('0')},
            {'compte': amort, 'debit': Decimal('0'), 'credit': montant},
        ],
        source=source_key[:40],
        source_id=immo.id,
        user=user,
    )


def snapshot_soldes(etablissement, exercice=None):
    """Soldes par numéro de compte (toutes écritures validées, exercice optionnel)."""
    lignes = LigneEcriture.objects.filter(
        compte__etablissement=etablissement,
        ecriture__validee=True,
    )
    if exercice is not None:
        lignes = lignes.filter(ecriture__exercice=exercice)
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
