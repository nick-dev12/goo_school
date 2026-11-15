"""Catalogue et synchronisation des frais annexes de scolarité."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.db import transaction


PERIODICITE_INSCRIPTION = 'inscription'
PERIODICITE_ANNUEL = 'annuel'
PERIODICITE_PONCTUEL = 'ponctuel'

PERIODICITE_CHOICES = (
    (PERIODICITE_INSCRIPTION, "À l'inscription"),
    (PERIODICITE_ANNUEL, 'Annuel'),
    (PERIODICITE_PONCTUEL, 'Ponctuel'),
)

PERIODICITE_VALIDES = {code for code, _ in PERIODICITE_CHOICES}

MODE_TOUS = 'tous'
MODE_AU_CHOIX = 'au_choix'
MODE_APPLICATION_VALIDES = {MODE_TOUS, MODE_AU_CHOIX}

CHOIX_INSCRIT = 'inscrit'
CHOIX_REFUSE = 'refuse'
CHOIX_NON_CHOISI = 'non_choisi'

# Frais typiques d'un établissement (Sénégal et ailleurs).
# Transport et cantine sont optionnels : activés seulement si l'école les facture.
FRAIS_ANNEXES_CATALOGUE = (
    {
        'code': 'tenue',
        'libelle': 'Tenue / uniforme scolaire',
        'periodicite': PERIODICITE_ANNUEL,
        'obligatoire': True,
        'optionnel': False,
        'libelle_editable': False,
        'icon': 'fa-shirt',
    },
    {
        'code': 'carte_scolaire',
        'libelle': 'Carte scolaire',
        'periodicite': PERIODICITE_ANNUEL,
        'obligatoire': True,
        'optionnel': False,
        'libelle_editable': False,
        'icon': 'fa-id-card',
    },
    {
        'code': 'dossier',
        'libelle': 'Dossier / frais administratifs',
        'periodicite': PERIODICITE_INSCRIPTION,
        'obligatoire': True,
        'optionnel': False,
        'libelle_editable': False,
        'icon': 'fa-folder-open',
    },
    {
        'code': 'assurance',
        'libelle': 'Assurance scolaire',
        'periodicite': PERIODICITE_ANNUEL,
        'obligatoire': True,
        'optionnel': False,
        'libelle_editable': False,
        'icon': 'fa-shield-heart',
    },
    {
        'code': 'examen',
        'libelle': "Frais d'examen / composition",
        'periodicite': PERIODICITE_PONCTUEL,
        'obligatoire': True,
        'optionnel': False,
        'libelle_editable': False,
        'icon': 'fa-file-pen',
    },
    {
        'code': 'transport',
        'libelle': 'Transport scolaire',
        'periodicite': PERIODICITE_ANNUEL,
        'obligatoire': False,
        'optionnel': True,
        'libelle_editable': False,
        'icon': 'fa-bus',
    },
    {
        'code': 'cantine',
        'libelle': 'Cantine / restauration',
        'periodicite': PERIODICITE_ANNUEL,
        'obligatoire': False,
        'optionnel': True,
        'libelle_editable': False,
        'icon': 'fa-utensils',
    },
    {
        'code': 'apport',
        'libelle': 'Apport / activités',
        'periodicite': PERIODICITE_PONCTUEL,
        'obligatoire': True,
        'optionnel': False,
        'libelle_editable': False,
        'icon': 'fa-hands-holding-circle',
    },
    {
        'code': 'autre',
        'libelle': 'Autres frais',
        'periodicite': PERIODICITE_PONCTUEL,
        'obligatoire': False,
        'optionnel': False,
        'libelle_editable': True,
        'icon': 'fa-ellipsis',
    },
    {
        'code': 'autre_2',
        'libelle': 'Autres frais (2)',
        'periodicite': PERIODICITE_PONCTUEL,
        'obligatoire': False,
        'optionnel': False,
        'libelle_editable': True,
        'icon': 'fa-ellipsis',
    },
    {
        'code': 'autre_3',
        'libelle': 'Autres frais (3)',
        'periodicite': PERIODICITE_PONCTUEL,
        'obligatoire': False,
        'optionnel': False,
        'libelle_editable': True,
        'icon': 'fa-ellipsis',
    },
)

CATALOGUE_PAR_CODE = {item['code']: item for item in FRAIS_ANNEXES_CATALOGUE}


def _to_decimal(value, default='0.00'):
    if value is None or value == '':
        return Decimal(default)
    try:
        return Decimal(str(value).replace(',', '.').replace(' ', ''))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'on', 'oui', 'yes'}


def periodicite_label(code):
    return dict(PERIODICITE_CHOICES).get(code, code or '')


def default_frais_annexes():
    """Liste vide normalisée (tous inactifs, montant 0)."""
    return [normaliser_frais_item({}) for _item in FRAIS_ANNEXES_CATALOGUE]


def _resoudre_mode_application(raw, fallback, catalog, obligatoire):
    """tous = tous les élèves ; au_choix = uniquement les élèves inscrits au frais."""
    for source in (raw, fallback):
        if not isinstance(source, dict):
            continue
        mode = str(source.get('mode_application') or '').strip()
        if mode in MODE_APPLICATION_VALIDES:
            return mode
    # Rétrocompat : config déjà enregistrée sans mode → comportement historique (tous).
    if isinstance(raw, dict) and ('actif' in raw or 'montant' in raw):
        return MODE_TOUS if obligatoire else MODE_AU_CHOIX
    if catalog.get('optionnel'):
        return MODE_AU_CHOIX
    return MODE_TOUS if obligatoire else MODE_AU_CHOIX


def normaliser_frais_item(raw, fallback=None):
    """Normalise un dict de configuration (JSON, POST ou assistant)."""
    raw = raw if isinstance(raw, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    code = str(raw.get('code') or fallback.get('code') or '').strip()
    catalog = CATALOGUE_PAR_CODE.get(code, {})
    libelle_defaut = catalog.get('libelle') or fallback.get('libelle') or 'Autres frais'
    periodicite_defaut = (
        catalog.get('periodicite')
        or fallback.get('periodicite')
        or PERIODICITE_PONCTUEL
    )
    periodicite = str(raw.get('periodicite') or periodicite_defaut).strip()
    if periodicite not in PERIODICITE_VALIDES:
        periodicite = periodicite_defaut
    libelle = str(raw.get('libelle') or libelle_defaut).strip() or libelle_defaut
    montant = _to_decimal(raw.get('montant', fallback.get('montant')))
    if montant < Decimal('0.00'):
        montant = Decimal('0.00')
    obligatoire = catalog.get('obligatoire', False)
    if 'obligatoire' in raw:
        obligatoire = _to_bool(raw.get('obligatoire'))
    elif 'obligatoire' in fallback:
        obligatoire = _to_bool(fallback.get('obligatoire'))
    mode_application = _resoudre_mode_application(raw, fallback, catalog, obligatoire)
    # Alignement : au choix ⇒ non obligatoire pour la charge créée.
    if mode_application == MODE_AU_CHOIX:
        obligatoire = False
    else:
        obligatoire = True
    return {
        'code': code or 'autre',
        'libelle': libelle[:120],
        'montant': str(montant.quantize(Decimal('0.01'))),
        'montant_decimal': montant,
        'actif': _to_bool(raw.get('actif', fallback.get('actif', False))),
        'periodicite': periodicite,
        'periodicite_display': periodicite_label(periodicite),
        'obligatoire': bool(obligatoire),
        'mode_application': mode_application,
        'au_choix': mode_application == MODE_AU_CHOIX,
        'optionnel': bool(catalog.get('optionnel', False)) or mode_application == MODE_AU_CHOIX,
        'libelle_editable': bool(catalog.get('libelle_editable', not bool(catalog))),
        'icon': catalog.get('icon', 'fa-coins'),
    }


def normaliser_frais_annexes(stored):
    """Fusionne le catalogue avec les valeurs enregistrées."""
    stored = stored if isinstance(stored, list) else []
    by_code = {}
    extras = []
    for item in stored:
        if not isinstance(item, dict):
            continue
        code = str(item.get('code') or '').strip()
        if not code:
            continue
        if code in CATALOGUE_PAR_CODE:
            by_code[code] = item
        else:
            extras.append(item)

    result = []
    for catalog_item in FRAIS_ANNEXES_CATALOGUE:
        result.append(normaliser_frais_item(by_code.get(catalog_item['code'], {}), catalog_item))
    for extra in extras:
        result.append(normaliser_frais_item(extra, extra))
    return result


def frais_annexes_actifs(stored):
    """Frais activés avec un montant > 0."""
    return [
        item
        for item in normaliser_frais_annexes(stored)
        if item['actif'] and item['montant_decimal'] > Decimal('0.00')
    ]


def total_frais_annexes_actifs(stored):
    total = Decimal('0.00')
    for item in frais_annexes_actifs(stored):
        total += item['montant_decimal']
    return total


def serialiser_frais_annexes_pour_stockage(items):
    """JSON compact à persister (sans champs dérivés)."""
    payload = []
    for item in items or []:
        norm = normaliser_frais_item(item, item)
        payload.append({
            'code': norm['code'],
            'libelle': norm['libelle'],
            'montant': norm['montant'],
            'actif': norm['actif'],
            'periodicite': norm['periodicite'],
            'obligatoire': norm['obligatoire'],
            'mode_application': norm['mode_application'],
        })
    return payload


def extraire_frais_annexes_depuis_post(post):
    """Lit les champs `frais_annexe_<code>_*` d'un formulaire Django."""
    items = []
    seen = set()
    codes = [item['code'] for item in FRAIS_ANNEXES_CATALOGUE]
    for key in post.keys():
        if key.startswith('frais_annexe_') and key.endswith('_montant'):
            code = key[len('frais_annexe_'):-len('_montant')]
            if code and code not in codes:
                codes.append(code)
    for code in codes:
        prefix = f'frais_annexe_{code}'
        if f'{prefix}_montant' not in post and f'{prefix}_actif' not in post:
            if code in CATALOGUE_PAR_CODE:
                items.append(normaliser_frais_item({'code': code, 'actif': False}, CATALOGUE_PAR_CODE[code]))
                seen.add(code)
            continue
        catalog = CATALOGUE_PAR_CODE.get(code, {'code': code, 'libelle': 'Autres frais'})
        mode = post.get(f'{prefix}_mode') or post.get(f'{prefix}_mode_application')
        items.append(normaliser_frais_item({
            'code': code,
            'actif': post.get(f'{prefix}_actif'),
            'montant': post.get(f'{prefix}_montant', '0'),
            'periodicite': post.get(f'{prefix}_periodicite') or catalog.get('periodicite'),
            'libelle': post.get(f'{prefix}_libelle') or catalog.get('libelle'),
            'obligatoire': catalog.get('obligatoire', False),
            'mode_application': mode,
        }, catalog))
        seen.add(code)
    return serialiser_frais_annexes_pour_stockage(items)


def extraire_frais_annexes_depuis_args(args, existants=None):
    """Fusionne une liste assistant / API avec la config actuelle."""
    existants = normaliser_frais_annexes(existants)
    by_code = {item['code']: item for item in existants}
    incoming = args.get('frais_annexes') if isinstance(args, dict) else None
    if isinstance(incoming, dict):
        incoming = [incoming]
    if not isinstance(incoming, list):
        return serialiser_frais_annexes_pour_stockage(existants)

    for raw in incoming:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get('code') or '').strip()
        if not code:
            continue
        base = by_code.get(code) or CATALOGUE_PAR_CODE.get(code, {'code': code})
        merged = dict(base)
        merged.update({k: v for k, v in raw.items() if v is not None})
        by_code[code] = normaliser_frais_item(merged, base)

    ordered = []
    for catalog_item in FRAIS_ANNEXES_CATALOGUE:
        if catalog_item['code'] in by_code:
            ordered.append(by_code.pop(catalog_item['code']))
    ordered.extend(by_code.values())
    return serialiser_frais_annexes_pour_stockage(ordered)


def date_echeance_frais_annexe(periodicite, inscription=None, annee_scolaire=None):
    today = timezone.now().date()
    if periodicite == PERIODICITE_INSCRIPTION:
        base = None
        if inscription is not None:
            base = getattr(inscription, 'date_inscription', None)
        if base:
            return max(base, today) + timedelta(days=30)
        return today + timedelta(days=30)
    if periodicite == PERIODICITE_ANNUEL and annee_scolaire is not None:
        debut = getattr(annee_scolaire, 'date_debut', None)
        if debut:
            return max(debut, today) + timedelta(days=30)
    return today + timedelta(days=30)


def appliquer_nouveau_montant(charge, nouveau_montant):
    """Met à jour montant / reste / statut en conservant les paiements déjà faits."""
    nouveau_montant = _to_decimal(nouveau_montant)
    paye = _to_decimal(getattr(charge, 'montant_paye', 0))
    # Une baisse ne rembourse pas un versement et ne crée pas de crédit implicite
    # qui pourrait solder d'autres frais dans les totaux de l'élève.
    charge.montant = max(nouveau_montant, paye)
    reste = nouveau_montant - paye
    if reste <= Decimal('0.00'):
        charge.reste_a_payer = Decimal('0.00')
        charge.statut = 'paye'
        if not getattr(charge, 'date_paiement', None):
            charge.date_paiement = timezone.now()
    else:
        charge.reste_a_payer = reste
        if charge.statut == 'paye':
            charge.statut = 'en_attente'
    return charge


def get_choix_frais_annexe(eleve, annee_scolaire, code):
    from school_admin.model.comptabilite_eleve_model import ChoixFraisAnnexeEleve

    return ChoixFraisAnnexeEleve.objects.filter(
        eleve=eleve,
        annee_scolaire=annee_scolaire,
        code=code,
    ).first()


def enregistrer_choix_frais_annexe(eleve, etablissement, annee_scolaire, code, statut):
    from school_admin.model.comptabilite_eleve_model import ChoixFraisAnnexeEleve

    if statut not in {CHOIX_INSCRIT, CHOIX_REFUSE, CHOIX_NON_CHOISI}:
        raise ValueError('Statut de choix invalide.')
    choix, _created = ChoixFraisAnnexeEleve.objects.update_or_create(
        eleve=eleve,
        annee_scolaire=annee_scolaire,
        code=code,
        defaults={
            'etablissement': etablissement,
            'statut': statut,
        },
    )
    return choix


def _eleve_doit_etre_facture(item, choix):
    if item.get('mode_application') != MODE_AU_CHOIX:
        return True
    if choix is None:
        return False
    return choix.statut == CHOIX_INSCRIT


def _retirer_charge_si_besoin(frais):
    """Désabonnement : annule si jamais payé, sinon clôture en conservant les versements."""
    if frais is None:
        return
    if frais.statut == 'clos':
        return
    frais.clore_apres_desabonnement()


def _assurer_charge(eleve, etablissement, annee_scolaire, comptabilite, item, inscription, existant):
    montant = item['montant_decimal']
    from school_admin.model.comptabilite_eleve_model import FraisAnnexe

    if existant is None:
        return FraisAnnexe.objects.create(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            comptabilite_eleve=comptabilite,
            code=item['code'],
            libelle=item['libelle'],
            periodicite=item['periodicite'],
            obligatoire=item['obligatoire'],
            montant=montant,
            montant_paye=Decimal('0.00'),
            reste_a_payer=montant,
            date_echeance=date_echeance_frais_annexe(
                item['periodicite'], inscription, annee_scolaire
            ),
            statut='en_attente',
        ), True

    if existant.statut == 'clos':
        # Réinscription au frais : rouvrir une nouvelle dette sur le montant courant.
        paye = _to_decimal(existant.montant_paye)
        if paye > Decimal('0.00') and paye < montant:
            existant.montant = montant
            existant.reste_a_payer = montant - paye
            existant.statut = 'en_attente'
            existant.libelle = item['libelle']
            existant.periodicite = item['periodicite']
            existant.obligatoire = item['obligatoire']
            existant.save(update_fields=[
                'montant', 'reste_a_payer', 'statut', 'libelle', 'periodicite', 'obligatoire',
            ])
            return existant, False
        if paye >= montant:
            existant.libelle = item['libelle']
            existant.periodicite = item['periodicite']
            existant.obligatoire = item['obligatoire']
            existant.montant = paye
            existant.reste_a_payer = Decimal('0.00')
            existant.statut = 'paye'
            existant.save(update_fields=[
                'libelle', 'periodicite', 'obligatoire', 'montant', 'reste_a_payer', 'statut',
            ])
            return existant, False
        # Clos sans paiement résiduel utile : repartir à zéro
        existant.montant = montant
        existant.montant_paye = Decimal('0.00')
        existant.reste_a_payer = montant
        existant.statut = 'en_attente'
        existant.libelle = item['libelle']
        existant.periodicite = item['periodicite']
        existant.obligatoire = item['obligatoire']
        existant.date_echeance = date_echeance_frais_annexe(
            item['periodicite'], inscription, annee_scolaire
        )
        existant.save(update_fields=[
            'montant', 'montant_paye', 'reste_a_payer', 'statut',
            'libelle', 'periodicite', 'obligatoire', 'date_echeance',
        ])
        return existant, False

    update_fields = ['libelle', 'periodicite', 'obligatoire']
    existant.libelle = item['libelle']
    existant.periodicite = item['periodicite']
    existant.obligatoire = item['obligatoire']
    if existant.montant != montant:
        appliquer_nouveau_montant(existant, montant)
        update_fields.extend(['montant', 'montant_paye', 'reste_a_payer', 'statut', 'date_paiement'])
    existant.save(update_fields=update_fields)
    return existant, False


def synchroniser_frais_annexes_eleve(
    eleve,
    etablissement,
    annee_scolaire,
    comptabilite,
    parametres,
    inscription=None,
):
    """Crée / aligne les échéances annexes d'un élève selon les paramètres et les choix."""
    from school_admin.model.comptabilite_eleve_model import ChoixFraisAnnexeEleve, FraisAnnexe

    stored = getattr(parametres, 'frais_annexes', None) if parametres is not None else None
    actifs = frais_annexes_actifs(stored)
    actifs_codes = {item['code'] for item in actifs}

    existants = {
        frais.code: frais
        for frais in FraisAnnexe.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
        )
    }
    choix_par_code = {
        c.code: c
        for c in ChoixFraisAnnexeEleve.objects.filter(
            eleve=eleve,
            annee_scolaire=annee_scolaire,
            code__in=actifs_codes,
        )
    }

    crees = 0
    for item in actifs:
        code = item['code']
        choix = choix_par_code.get(code)
        # Conserver l'ancienne charge jusqu'à une décision explicite.
        if (
            item.get('mode_application') == MODE_AU_CHOIX
            and (choix is None or choix.statut == CHOIX_NON_CHOISI)
            and code in existants
            and existants[code].statut != 'clos'
        ):
            continue

        if item.get('mode_application') != MODE_AU_CHOIX and choix is None:
            choix = enregistrer_choix_frais_annexe(
                eleve, etablissement, annee_scolaire, code, CHOIX_INSCRIT
            )
            choix_par_code[code] = choix

        doit_facturer = _eleve_doit_etre_facture(item, choix)
        existant = existants.get(code)

        if not doit_facturer:
            _retirer_charge_si_besoin(existant)
            existants.pop(code, None)
            continue

        _frais, created = _assurer_charge(
            eleve, etablissement, annee_scolaire, comptabilite, item, inscription, existant
        )
        if created:
            crees += 1
        existants[code] = _frais

    for code, frais in list(existants.items()):
        if code in actifs_codes:
            continue
        if frais.statut == 'clos':
            continue
        if _to_decimal(frais.montant_paye) == Decimal('0.00'):
            frais.delete()
        else:
            frais.clore_apres_desabonnement()

    return crees


@transaction.atomic
def appliquer_choix_frais_au_choix(
    eleve,
    etablissement,
    annee_scolaire,
    comptabilite,
    parametres,
    codes_inscrits,
    inscription=None,
):
    """
    Enregistre les choix pour les frais « au choix » puis resynchronise les charges.
    codes_inscrits : iterable de codes cochés ; les autres frais au choix actifs → refusés.
    None signifie qu'aucun choix n'a été demandé dans ce parcours : les choix existants restent intacts.
    """
    stored = getattr(parametres, 'frais_annexes', None) if parametres is not None else None
    actifs = frais_annexes_actifs(stored)
    inscrire_choix = codes_inscrits is not None
    inscrits = {str(c) for c in (codes_inscrits or [])}
    for item in actifs:
        if item.get('mode_application') != MODE_AU_CHOIX:
            enregistrer_choix_frais_annexe(
                eleve, etablissement, annee_scolaire, item['code'], CHOIX_INSCRIT
            )
            continue
        if not inscrire_choix:
            continue
        statut = CHOIX_INSCRIT if item['code'] in inscrits else CHOIX_REFUSE
        enregistrer_choix_frais_annexe(
            eleve, etablissement, annee_scolaire, item['code'], statut
        )
    return synchroniser_frais_annexes_eleve(
        eleve, etablissement, annee_scolaire, comptabilite, parametres, inscription
    )


def frais_au_choix_pour_parametres(parametres):
    return [
        item for item in frais_annexes_actifs(
            getattr(parametres, 'frais_annexes', None) if parametres else None
        )
        if item.get('mode_application') == MODE_AU_CHOIX
    ]


def frais_au_choix_etablissement(etablissement):
    """Tous les frais « au choix » actifs proposés dans l'établissement (dédupliqués)."""
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )
    from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

    by_code = {}
    for parametre in ParametresComptabiliteGroupeClasse.objects.filter(etablissement=etablissement):
        for item in frais_au_choix_pour_parametres(parametre):
            by_code[item['code']] = item
    try:
        generaux = ParametresComptabilite.objects.get(etablissement=etablissement)
    except ParametresComptabilite.DoesNotExist:
        generaux = None
    for item in frais_au_choix_pour_parametres(generaux):
        by_code.setdefault(item['code'], item)
    return list(by_code.values())


def get_frais_annexes_from_parametres(parametres):
    stored = getattr(parametres, 'frais_annexes', None) if parametres is not None else None
    return normaliser_frais_annexes(stored)
