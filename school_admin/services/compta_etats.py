"""
États et outils de la comptabilité générale (SYSCOHADA révisé, système normal simplifié).

Tout est calculé à partir des lignes d'écritures validées : grand livre, balance,
bilan, compte de résultat, séries mensuelles pour les graphiques, contrôles de
cohérence, saisie manuelle et clôture d'exercice avec à-nouveaux.
"""
from __future__ import annotations

from calendar import monthrange
from collections import OrderedDict, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, F, Q, Sum

from school_admin.model.comptabilite_generale_model import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    JournalComptable,
    LigneEcriture,
)
from school_admin.services import comptabilite_generale as cg

ZERO = Decimal('0')
MOIS_COURTS = ('', 'janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.')

# Rubriques du compte de résultat (préfixe de compte → libellé).
RUBRIQUES_PRODUITS = OrderedDict([
    ('70', 'Prestations de services (scolarité, inscriptions, annexes)'),
    ('71', "Subventions d'exploitation"),
    ('72', 'Production immobilisée'),
    ('75', 'Autres produits'),
    ('77', 'Revenus financiers'),
    ('78', 'Transferts de charges'),
    ('79', 'Reprises de provisions'),
])
RUBRIQUES_CHARGES = OrderedDict([
    ('60', 'Achats et fournitures'),
    ('61', 'Transports'),
    ('62', 'Services extérieurs A'),
    ('63', 'Services extérieurs B'),
    ('64', 'Impôts et taxes'),
    ('65', 'Autres charges'),
    ('66', 'Charges de personnel'),
    ('67', 'Frais financiers'),
    ('68', 'Dotations aux amortissements'),
    ('69', 'Dotations aux provisions / impôts sur le résultat'),
])
CLASSES = OrderedDict(CompteComptable.CLASSE_CHOICES)


def _d(valeur):
    return valeur if isinstance(valeur, Decimal) else Decimal(str(valeur or 0))


def parse_montant(valeur):
    texte = str(valeur or '').replace(' ', '').replace(' ', '').replace(',', '.').strip()
    if not texte:
        return ZERO
    try:
        montant = Decimal(texte).quantize(Decimal('0.01'))
    except InvalidOperation as exc:
        raise ValueError(f"Montant invalide : {valeur}") from exc
    if montant < 0:
        raise ValueError("Les montants négatifs ne sont pas acceptés : utilisez l'autre colonne.")
    return montant


# --------------------------------------------------------------------------- exercices
def exercices(etablissement):
    return ExerciceComptable.objects.filter(etablissement=etablissement).order_by('-date_debut')


def exercice_selectionne(request, etablissement, annee_scolaire=None):
    """Exercice choisi (?exercice=ID, mémorisé en session), sinon l'exercice civil en cours."""
    courant = cg.ensure_exercice(etablissement, annee_scolaire)
    choix = request.GET.get('exercice') or request.session.get('cg_exercice_id')
    if choix:
        exo = ExerciceComptable.objects.filter(etablissement=etablissement, pk=choix).first()
        if exo:
            request.session['cg_exercice_id'] = exo.pk
            return exo
    return courant


def _lignes(etablissement, exercice, du=None, au=None):
    qs = LigneEcriture.objects.filter(
        ecriture__etablissement=etablissement, ecriture__exercice=exercice, ecriture__validee=True,
    )
    if du:
        qs = qs.filter(ecriture__date_ecriture__gte=du)
    if au:
        qs = qs.filter(ecriture__date_ecriture__lte=au)
    return qs


def soldes_comptes(etablissement, exercice, du=None, au=None, a_nouveaux=None):
    """{compte_id: {'compte', 'debit', 'credit', 'solde'}} sur la période.

    a_nouveaux : None = toutes les lignes, True = seulement les à-nouveaux, False = sans les à-nouveaux.
    """
    qs = _lignes(etablissement, exercice, du, au)
    if a_nouveaux is True:
        qs = qs.filter(ecriture__source='a_nouveaux')
    elif a_nouveaux is False:
        qs = qs.exclude(ecriture__source='a_nouveaux')
    agg = qs.values('compte_id').annotate(d=Sum('debit'), c=Sum('credit'))
    comptes = {c.id: c for c in CompteComptable.objects.filter(etablissement=etablissement)}
    out = {}
    for row in agg:
        cpt = comptes.get(row['compte_id'])
        if cpt is None:
            continue
        d, c = row['d'] or ZERO, row['c'] or ZERO
        out[cpt.id] = {'compte': cpt, 'debit': d, 'credit': c, 'solde': d - c}
    return out


# --------------------------------------------------------------------------- balance
def balance_generale(etablissement, exercice, du=None, au=None, avec_vides=False):
    """Balance à 6 colonnes regroupée par classe : ouverture, mouvements, soldes."""
    # Ouverture = à-nouveaux de l'exercice + mouvements antérieurs à la période demandée.
    ouverture = soldes_comptes(etablissement, exercice, a_nouveaux=True)
    if du and du > exercice.date_debut:
        avant = soldes_comptes(etablissement, exercice, au=du - timedelta(days=1), a_nouveaux=False)
        for cid, row in avant.items():
            cur = ouverture.setdefault(cid, {'compte': row['compte'], 'debit': ZERO, 'credit': ZERO, 'solde': ZERO})
            cur['solde'] += row['solde']
    mouvements = soldes_comptes(etablissement, exercice, du, au, a_nouveaux=False)
    comptes = CompteComptable.objects.filter(etablissement=etablissement).order_by('numero')
    classes = OrderedDict()
    totaux = defaultdict(lambda: ZERO)
    for cpt in comptes:
        o = ouverture.get(cpt.id, {}).get('solde', ZERO)
        m = mouvements.get(cpt.id, {'debit': ZERO, 'credit': ZERO})
        if not avec_vides and not o and not m['debit'] and not m['credit']:
            continue
        fin = o + m['debit'] - m['credit']
        row = {
            'compte': cpt,
            'ouv_debit': o if o > 0 else ZERO, 'ouv_credit': -o if o < 0 else ZERO,
            'mvt_debit': m['debit'], 'mvt_credit': m['credit'],
            'solde_debit': fin if fin > 0 else ZERO, 'solde_credit': -fin if fin < 0 else ZERO,
        }
        bloc = classes.setdefault(cpt.classe, {'classe': cpt.classe, 'libelle': CLASSES.get(cpt.classe, ''),
                                               'rows': [], 'totaux': defaultdict(lambda: ZERO)})
        bloc['rows'].append(row)
        for k in ('ouv_debit', 'ouv_credit', 'mvt_debit', 'mvt_credit', 'solde_debit', 'solde_credit'):
            bloc['totaux'][k] += row[k]
            totaux[k] += row[k]
    for bloc in classes.values():
        bloc['totaux'] = dict(bloc['totaux'])
    totaux = dict(totaux)
    equilibree = (totaux.get('mvt_debit', ZERO) == totaux.get('mvt_credit', ZERO)
                  and totaux.get('solde_debit', ZERO) == totaux.get('solde_credit', ZERO))
    nb = sum(len(b['rows']) for b in classes.values())
    return {'classes': list(classes.values()), 'totaux': totaux, 'equilibree': equilibree, 'nb_comptes': nb}


# --------------------------------------------------------------------------- grand livre
def grand_livre(etablissement, exercice, compte=None, du=None, au=None, limite_comptes=None):
    """Mouvements par compte avec solde progressif (un compte ou tous les comptes mouvementés)."""
    comptes = CompteComptable.objects.filter(etablissement=etablissement)
    if compte is not None:
        comptes = comptes.filter(pk=compte.pk)
    else:
        ids = _lignes(etablissement, exercice).values_list('compte_id', flat=True).distinct()
        comptes = comptes.filter(pk__in=ids)
    comptes = list(comptes.order_by('numero'))
    if limite_comptes:
        comptes = comptes[:limite_comptes]
    blocs = []
    for cpt in comptes:
        report = ZERO
        if du and du > exercice.date_debut:
            agg = _lignes(etablissement, exercice, au=du - timedelta(days=1)).filter(compte=cpt).aggregate(
                d=Sum('debit'), c=Sum('credit'))
            report = (agg['d'] or ZERO) - (agg['c'] or ZERO)
        solde = report
        rows = []
        total_d = total_c = ZERO
        qs = (_lignes(etablissement, exercice, du, au).filter(compte=cpt)
              .select_related('ecriture__journal').order_by('ecriture__date_ecriture', 'ecriture_id', 'id'))
        for ligne in qs:
            solde += ligne.debit - ligne.credit
            total_d += ligne.debit
            total_c += ligne.credit
            e = ligne.ecriture
            rows.append({'date': e.date_ecriture, 'journal': e.journal.code, 'piece': e.numero,
                         'ecriture_id': e.id, 'libelle': ligne.libelle or e.libelle,
                         'auxiliaire': ligne.auxiliaire, 'reference': e.reference,
                         'debit': ligne.debit, 'credit': ligne.credit, 'solde': solde})
        blocs.append({'compte': cpt, 'report': report, 'rows': rows, 'total_debit': total_d,
                      'total_credit': total_c, 'solde': solde, 'solde_abs': abs(solde)})
    return blocs


# --------------------------------------------------------------------------- compte de résultat
def compte_de_resultat(etablissement, exercice, du=None, au=None):
    soldes = soldes_comptes(etablissement, exercice, du, au)
    produits = OrderedDict((k, {'code': k, 'libelle': v, 'montant': ZERO, 'comptes': []})
                           for k, v in RUBRIQUES_PRODUITS.items())
    charges = OrderedDict((k, {'code': k, 'libelle': v, 'montant': ZERO, 'comptes': []})
                          for k, v in RUBRIQUES_CHARGES.items())
    for row in soldes.values():
        cpt = row['compte']
        pref = cpt.numero[:2]
        if cpt.classe == '7':
            montant = row['credit'] - row['debit']
            bloc = produits.setdefault(pref, {'code': pref, 'libelle': cpt.libelle, 'montant': ZERO, 'comptes': []})
        elif cpt.classe == '6':
            montant = row['debit'] - row['credit']
            bloc = charges.setdefault(pref, {'code': pref, 'libelle': cpt.libelle, 'montant': ZERO, 'comptes': []})
        else:
            continue
        if montant:
            bloc['montant'] += montant
            bloc['comptes'].append({'compte': cpt, 'montant': montant})
    for bloc in list(produits.values()) + list(charges.values()):
        bloc['comptes'].sort(key=lambda r: r['compte'].numero)

    def total(blocs, codes):
        return sum((blocs[c]['montant'] for c in codes if c in blocs), ZERO)

    produits_expl = total(produits, ('70', '71', '72', '75', '78', '79'))
    charges_expl = total(charges, ('60', '61', '62', '63', '64', '65', '66', '68', '69'))
    produits_fin = total(produits, ('77',))
    charges_fin = total(charges, ('67',))
    total_produits = sum((b['montant'] for b in produits.values()), ZERO)
    total_charges = sum((b['montant'] for b in charges.values()), ZERO)
    return {
        'produits': [b for b in produits.values() if b['montant']],
        'charges': [b for b in charges.values() if b['montant']],
        'total_produits': total_produits,
        'total_charges': total_charges,
        'resultat_exploitation': produits_expl - charges_expl,
        'resultat_financier': produits_fin - charges_fin,
        'resultat': total_produits - total_charges,
        'marge_pct': (round((total_produits - total_charges) / total_produits * 100, 1)
                      if total_produits else None),
    }


# --------------------------------------------------------------------------- bilan
def bilan(etablissement, exercice, au=None):
    """Bilan SYSCOHADA simplifié. Les comptes de tiers vont à l'actif ou au passif selon leur solde."""
    soldes = soldes_comptes(etablissement, exercice, au=au)
    rub = OrderedDict([
        ('immo_brut', {'libelle': 'Immobilisations (valeur brute)', 'cote': 'actif', 'montant': ZERO, 'comptes': []}),
        ('amort', {'libelle': 'Amortissements cumulés', 'cote': 'actif', 'montant': ZERO, 'comptes': []}),
        ('stocks', {'libelle': 'Stocks', 'cote': 'actif', 'montant': ZERO, 'comptes': []}),
        ('clients', {'libelle': 'Créances familles (clients)', 'cote': 'actif', 'montant': ZERO, 'comptes': []}),
        ('autres_creances', {'libelle': 'Autres créances', 'cote': 'actif', 'montant': ZERO, 'comptes': []}),
        ('treso_actif', {'libelle': 'Trésorerie — actif (caisse, banque, mobile money)', 'cote': 'actif',
                         'montant': ZERO, 'comptes': []}),
        ('capitaux', {'libelle': 'Capitaux propres et réserves', 'cote': 'passif', 'montant': ZERO, 'comptes': []}),
        ('dettes_fin', {'libelle': 'Dettes financières (emprunts)', 'cote': 'passif', 'montant': ZERO, 'comptes': []}),
        ('fournisseurs', {'libelle': 'Fournisseurs', 'cote': 'passif', 'montant': ZERO, 'comptes': []}),
        ('fiscal_social', {'libelle': 'Dettes sociales et fiscales', 'cote': 'passif', 'montant': ZERO, 'comptes': []}),
        ('autres_dettes', {'libelle': 'Autres dettes (avances familles, divers)', 'cote': 'passif',
                           'montant': ZERO, 'comptes': []}),
        ('treso_passif', {'libelle': 'Trésorerie — passif (découverts)', 'cote': 'passif',
                          'montant': ZERO, 'comptes': []}),
    ])
    produits = charges = ZERO
    for row in soldes.values():
        cpt, solde = row['compte'], row['solde']
        n = cpt.numero
        if cpt.classe == '6':
            charges += solde
            continue
        if cpt.classe == '7':
            produits += -solde
            continue
        if not solde:
            continue
        if cpt.classe == '2':
            cle, montant = ('amort', solde) if n.startswith(('28', '29')) else ('immo_brut', solde)
        elif cpt.classe == '3':
            cle, montant = 'stocks', solde
        elif cpt.classe == '5':
            cle, montant = ('treso_actif', solde) if solde > 0 else ('treso_passif', -solde)
        elif cpt.classe == '1':
            cle, montant = ('dettes_fin', -solde) if n.startswith(('16', '17')) else ('capitaux', -solde)
        elif cpt.classe == '4':
            if solde > 0:
                cle, montant = ('clients', solde) if n.startswith('41') else ('autres_creances', solde)
            else:
                if n.startswith('40'):
                    cle = 'fournisseurs'
                elif n.startswith(('42', '43', '44')):
                    cle = 'fiscal_social'
                else:
                    cle = 'autres_dettes'
                montant = -solde
        else:
            continue
        rub[cle]['montant'] += montant
        rub[cle]['comptes'].append({'compte': cpt, 'montant': montant})
    resultat = produits - charges
    actif_immo_net = rub['immo_brut']['montant'] + rub['amort']['montant']
    actif_circulant = rub['stocks']['montant'] + rub['clients']['montant'] + rub['autres_creances']['montant']
    total_actif = actif_immo_net + actif_circulant + rub['treso_actif']['montant']
    capitaux = rub['capitaux']['montant'] + resultat
    passif_circulant = (rub['fournisseurs']['montant'] + rub['fiscal_social']['montant']
                        + rub['autres_dettes']['montant'])
    total_passif = capitaux + rub['dettes_fin']['montant'] + passif_circulant + rub['treso_passif']['montant']
    return {
        'rubriques': rub, 'resultat': resultat,
        'actif_immo_net': actif_immo_net, 'actif_circulant': actif_circulant,
        'tresorerie_actif': rub['treso_actif']['montant'], 'total_actif': total_actif,
        'capitaux_propres': capitaux, 'dettes_financieres': rub['dettes_fin']['montant'],
        'passif_circulant': passif_circulant, 'tresorerie_passif': rub['treso_passif']['montant'],
        'total_passif': total_passif, 'equilibre': total_actif == total_passif,
        'tresorerie_nette': rub['treso_actif']['montant'] - rub['treso_passif']['montant'],
        'fonds_roulement': (capitaux + rub['dettes_fin']['montant']) - actif_immo_net,
        'bfr': actif_circulant - passif_circulant,
    }


# --------------------------------------------------------------------------- séries graphiques
def _mois_exercice(exercice):
    current = date(exercice.date_debut.year, exercice.date_debut.month, 1)
    while current <= exercice.date_fin:
        fin = date(current.year, current.month, monthrange(current.year, current.month)[1])
        yield current, min(fin, exercice.date_fin)
        current = (fin + timedelta(days=1))


def series_mensuelles(etablissement, exercice, jusqu_a=None):
    """Produits, charges, résultat cumulé et trésorerie de fin de mois, mois par mois."""
    lignes = _lignes(etablissement, exercice).values(
        'ecriture__date_ecriture', 'compte__classe', 'debit', 'credit')
    par_mois = defaultdict(lambda: {'produits': ZERO, 'charges': ZERO, 'treso': ZERO})
    for l in lignes:
        d = l['ecriture__date_ecriture']
        clef = (d.year, d.month)
        if l['compte__classe'] == '7':
            par_mois[clef]['produits'] += l['credit'] - l['debit']
        elif l['compte__classe'] == '6':
            par_mois[clef]['charges'] += l['debit'] - l['credit']
        elif l['compte__classe'] == '5':
            par_mois[clef]['treso'] += l['debit'] - l['credit']
    labels, produits, charges, resultat_cumule, tresorerie = [], [], [], [], []
    cumul_res = cumul_treso = ZERO
    for debut, _fin in _mois_exercice(exercice):
        if jusqu_a and debut > jusqu_a:
            break
        m = par_mois.get((debut.year, debut.month), {'produits': ZERO, 'charges': ZERO, 'treso': ZERO})
        cumul_res += m['produits'] - m['charges']
        cumul_treso += m['treso']
        labels.append(MOIS_COURTS[debut.month])
        produits.append(float(m['produits']))
        charges.append(float(m['charges']))
        resultat_cumule.append(float(cumul_res))
        tresorerie.append(float(cumul_treso))
    return {'labels': labels, 'produits': produits, 'charges': charges,
            'resultat_cumule': resultat_cumule, 'tresorerie': tresorerie}


def repartition(etablissement, exercice, classe, limite=7):
    """Montants par compte de la classe 6 ou 7, les plus gros d'abord, le reste regroupé."""
    rows = []
    for row in soldes_comptes(etablissement, exercice).values():
        cpt = row['compte']
        if cpt.classe != classe:
            continue
        montant = row['debit'] - row['credit'] if classe == '6' else row['credit'] - row['debit']
        if montant > 0:
            rows.append({'label': f"{cpt.numero} {cpt.libelle}", 'court': cpt.libelle, 'montant': float(montant)})
    rows.sort(key=lambda r: -r['montant'])
    if len(rows) > limite:
        reste = sum(r['montant'] for r in rows[limite - 1:])
        rows = rows[:limite - 1] + [{'label': 'Autres comptes', 'court': 'Autres', 'montant': reste}]
    return rows


def soldes_tresorerie(etablissement, exercice):
    """Solde comptable de chaque compte de classe 5 mouvementé."""
    rows = []
    for row in soldes_comptes(etablissement, exercice).values():
        if row['compte'].classe == '5':
            rows.append({'compte': row['compte'], 'solde': row['solde']})
    return sorted(rows, key=lambda r: r['compte'].numero)


# --------------------------------------------------------------------------- journaux
def ecritures_filtrees(etablissement, exercice, journal_code='', du=None, au=None, q='', compte_id=None,
                       source=''):
    qs = (EcritureComptable.objects.filter(etablissement=etablissement, exercice=exercice)
          .select_related('journal', 'ecriture_origine').prefetch_related('lignes__compte'))
    if journal_code:
        qs = qs.filter(journal__code=journal_code)
    if du:
        qs = qs.filter(date_ecriture__gte=du)
    if au:
        qs = qs.filter(date_ecriture__lte=au)
    if compte_id:
        qs = qs.filter(lignes__compte_id=compte_id).distinct()
    if source:
        qs = qs.filter(source=source)
    if q:
        qs = qs.filter(Q(libelle__icontains=q) | Q(reference__icontains=q) | Q(numero__icontains=q)
                       | Q(lignes__auxiliaire__icontains=q)).distinct()
    return qs.order_by('-date_ecriture', '-id')


def stats_journaux(etablissement, exercice):
    rows = []
    agg = (LigneEcriture.objects.filter(ecriture__etablissement=etablissement, ecriture__exercice=exercice)
           .values('ecriture__journal_id').annotate(d=Sum('debit'), n=Count('ecriture', distinct=True)))
    par_journal = {r['ecriture__journal_id']: r for r in agg}
    for j in JournalComptable.objects.filter(etablissement=etablissement).order_by('code'):
        r = par_journal.get(j.id, {})
        rows.append({'journal': j, 'nb': r.get('n', 0), 'total': r.get('d') or ZERO})
    return rows


def ids_extournees(etablissement):
    return set(EcritureComptable.objects.filter(etablissement=etablissement, source='extourne')
               .values_list('source_id', flat=True))


# --------------------------------------------------------------------------- contrôles
def controles(etablissement, exercice):
    """Vérifications de cohérence affichées sur le tableau de bord."""
    desequilibrees = list(
        EcritureComptable.objects.filter(etablissement=etablissement, exercice=exercice)
        .annotate(d=Sum('lignes__debit'), c=Sum('lignes__credit'))
        .exclude(d=F('c'))[:20]
    )
    hors_exercice = EcritureComptable.objects.filter(etablissement=etablissement, exercice=exercice).filter(
        Q(date_ecriture__lt=exercice.date_debut) | Q(date_ecriture__gt=exercice.date_fin)).count()
    sans_ligne = EcritureComptable.objects.filter(etablissement=etablissement, exercice=exercice,
                                                  lignes__isnull=True).count()
    bal = balance_generale(etablissement, exercice)
    decouverts = [r for r in soldes_tresorerie(etablissement, exercice) if r['solde'] < 0]
    soldes = soldes_comptes(etablissement, exercice)
    clients_crediteurs = [r for r in soldes.values() if r['compte'].numero.startswith('411') and r['solde'] < 0]
    orphelines = cg.ecritures_depenses_orphelines(etablissement).filter(exercice=exercice).count()
    items = [
        {'ok': bal['equilibree'], 'titre': 'Balance équilibrée',
         'detail': 'Total des débits égal au total des crédits.' if bal['equilibree']
         else 'Les totaux débit et crédit diffèrent.'},
        {'ok': not desequilibrees, 'titre': 'Pièces équilibrées',
         'detail': 'Chaque écriture est équilibrée.' if not desequilibrees
         else f"{len(desequilibrees)} écriture(s) déséquilibrée(s)."},
        {'ok': not hors_exercice and not sans_ligne, 'titre': 'Rattachement des pièces',
         'detail': 'Toutes les pièces sont datées dans l’exercice et ont des lignes.'
         if not hors_exercice and not sans_ligne
         else f"{hors_exercice} pièce(s) hors dates, {sans_ligne} sans ligne."},
        {'ok': not decouverts, 'titre': 'Trésorerie positive',
         'detail': 'Aucun compte de trésorerie créditeur.' if not decouverts
         else ', '.join(f"{r['compte'].numero} {r['compte'].libelle}" for r in decouverts) + ' en négatif.'},
        {'ok': not clients_crediteurs, 'titre': 'Comptes familles',
         'detail': 'Aucun compte client créditeur.' if not clients_crediteurs
         else 'Des familles ont payé plus que facturé : vérifier ou passer en 419.'},
        {'ok': not orphelines, 'titre': 'Lien avec la caisse',
         'detail': 'Chaque écriture de dépense correspond à une sortie de caisse.' if not orphelines
         else f"{orphelines} écriture(s) de dépense sans sortie de caisse."},
    ]
    return {'items': items, 'nb_alertes': sum(1 for i in items if not i['ok']), 'desequilibrees': desequilibrees}


# --------------------------------------------------------------------------- saisie manuelle
def saisir_ecriture(etablissement, journal_obj, date_ecriture, libelle, lignes_brutes, reference='', user=None):
    """Écriture saisie à la main (OD, régularisation…). Contrôles : comptes, sens unique, équilibre."""
    libelle = (libelle or '').strip()
    if not libelle:
        raise ValueError("Indiquez un libellé pour la pièce.")
    if journal_obj.code == 'AN':
        raise ValueError("Le journal des à-nouveaux est réservé à la clôture.")
    lignes = []
    for brute in lignes_brutes:
        compte_id = (str(brute.get('compte_id') or '')).strip()
        debit = parse_montant(brute.get('debit'))
        credit = parse_montant(brute.get('credit'))
        if not compte_id and not debit and not credit:
            continue
        if not compte_id:
            raise ValueError("Chaque ligne doit avoir un compte.")
        if debit and credit:
            raise ValueError("Une ligne est soit au débit, soit au crédit.")
        if not debit and not credit:
            raise ValueError("Chaque ligne doit avoir un montant.")
        cpt = CompteComptable.objects.filter(etablissement=etablissement, pk=compte_id, actif=True).first()
        if cpt is None:
            raise ValueError("Compte inconnu pour cet établissement.")
        lignes.append({'compte': cpt, 'debit': debit, 'credit': credit,
                       'libelle': (brute.get('libelle') or libelle)[:200],
                       'auxiliaire': (brute.get('auxiliaire') or '')[:80]})
    if len(lignes) < 2:
        raise ValueError("Une écriture comporte au moins deux lignes.")
    total_d = sum((l['debit'] for l in lignes), ZERO)
    total_c = sum((l['credit'] for l in lignes), ZERO)
    if total_d != total_c:
        raise ValueError(f"Écriture déséquilibrée : débit {total_d} ≠ crédit {total_c}.")
    return cg.creer_ecriture(etablissement, None, journal_obj, date_ecriture, libelle, lignes,
                             source='saisie', reference=reference, user=user)


# --------------------------------------------------------------------------- clôture
def cloturer_exercice(exercice, user=None, avant_terme=False):
    """Clôture : contrôles, verrouillage des périodes et à-nouveaux dans l'exercice suivant."""
    from django.utils import timezone as tz

    if not exercice.est_ouvert():
        raise ValueError("Cet exercice est déjà clôturé.")
    if not avant_terme and exercice.date_fin >= tz.localdate():
        raise ValueError(f"L'exercice {exercice.libelle} se termine le {exercice.date_fin:%d/%m/%Y} : "
                         "la clôture se fait après cette date.")
    etab = exercice.etablissement
    ctrl = controles(etab, exercice)
    if ctrl['desequilibrees']:
        raise ValueError("Clôture impossible : des écritures sont déséquilibrées.")
    suivant = cg.exercice_pour_date(etab, exercice.date_fin + timedelta(days=1))
    if not suivant.est_ouvert():
        raise ValueError("L'exercice suivant est clôturé : rouvrez-le d'abord.")
    cg.ensure_journaux(etab)
    jour_an = cg.journal(etab, 'AN')

    # Soldes des comptes de bilan (classes 1 à 5), par compte et par tiers.
    agg = (_lignes(etab, exercice).filter(compte__classe__in=['1', '2', '3', '4', '5'])
           .values('compte_id', 'auxiliaire').annotate(d=Sum('debit'), c=Sum('credit')))
    comptes = {c.id: c for c in CompteComptable.objects.filter(etablissement=etab)}
    lignes = []
    for row in agg:
        solde = (row['d'] or ZERO) - (row['c'] or ZERO)
        if not solde:
            continue
        cpt = comptes[row['compte_id']]
        aux = row['auxiliaire'] if cpt.est_auxiliaire else ''
        lignes.append({'compte': cpt, 'debit': solde if solde > 0 else ZERO, 'credit': -solde if solde < 0 else ZERO,
                       'libelle': f"À-nouveau {exercice.libelle}", 'auxiliaire': aux})
    resultat = compte_de_resultat(etab, exercice)['resultat']
    if resultat:
        if resultat > 0:
            cpt_res = cg.compte(etab, cg.COMPTE_RESULTAT_BENEFICE)
            lignes.append({'compte': cpt_res, 'debit': ZERO, 'credit': resultat,
                           'libelle': f"Résultat {exercice.libelle} (bénéfice)"})
        else:
            cpt_res = cg.compte(etab, cg.COMPTE_RESULTAT_PERTE)
            lignes.append({'compte': cpt_res, 'debit': -resultat, 'credit': ZERO,
                           'libelle': f"Résultat {exercice.libelle} (perte)"})
    from django.utils import timezone

    with transaction.atomic():
        ecriture = None
        if lignes:
            ecriture = cg.creer_ecriture(
                etab, suivant, jour_an, suivant.date_debut, f"À-nouveaux de l'exercice {exercice.libelle}",
                lignes, source='a_nouveaux', source_id=exercice.id, user=user,
            )
        exercice.periodes.update(verrouillee=True, date_verrouillage=timezone.now())
        exercice.statut = 'cloture'
        exercice.date_cloture = timezone.now()
        exercice.save(update_fields=['statut', 'date_cloture'])
    return {'ecriture': ecriture, 'resultat': resultat, 'suivant': suivant}


def rouvrir_exercice(exercice):
    """Réouverture : supprime les à-nouveaux générés et rouvre les périodes."""
    if exercice.est_ouvert():
        raise ValueError("Cet exercice est déjà ouvert.")
    with transaction.atomic():
        an = EcritureComptable.objects.filter(etablissement=exercice.etablissement, source='a_nouveaux',
                                              source_id=exercice.id)
        for e in an:
            e.lignes.all().delete()
            e.delete()
        exercice.periodes.update(verrouillee=False, date_verrouillage=None)
        exercice.statut = 'ouvert'
        exercice.date_cloture = None
        exercice.save(update_fields=['statut', 'date_cloture'])
