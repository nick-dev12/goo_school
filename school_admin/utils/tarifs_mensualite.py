"""Paliers de mensualité : un montant pour un ou plusieurs mois."""
from decimal import Decimal, InvalidOperation

NOMS_MOIS = (
    'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
)
TRANCHE_SLOTS = 6


def nom_mois(numero):
    try:
        return NOMS_MOIS[int(numero) - 1]
    except (TypeError, ValueError, IndexError):
        return ''


def ordre_mois_facturation(debut=9, fin=6):
    debut = int(debut or 9)
    fin = int(fin or 6)
    mois = []
    courant = debut
    for _ in range(12):
        mois.append(courant)
        if courant == fin:
            break
        courant = 1 if courant == 12 else courant + 1
    return mois


def formater_plage_mois(mois_nums, debut=9, fin=6):
    nums = [int(m) for m in mois_nums]
    if not nums:
        return ''
    ordre = ordre_mois_facturation(debut, fin)
    try:
        positions = [ordre.index(m) for m in nums]
    except ValueError:
        positions = list(range(len(nums)))
    consecutifs = positions == list(range(positions[0], positions[0] + len(positions)))
    noms = [nom_mois(m) for m in nums]
    if len(noms) == 1:
        return noms[0]
    if len(noms) == 2:
        return '%s et %s' % (noms[0], noms[1])
    if consecutifs:
        return '%s à %s' % (noms[0], noms[-1])
    return ', '.join(noms)


def paliers_depuis_parametre(parametre):
    if parametre is None:
        return []
    debut = getattr(parametre, 'mois_debut_facturation', 9) or 9
    fin = getattr(parametre, 'mois_fin_facturation', 6) or 6
    paliers = []
    courant = None
    for mois in ordre_mois_facturation(debut, fin):
        montant = parametre.montant_pour_mois(mois)
        if montant is None or Decimal(str(montant)) <= 0:
            courant = None
            continue
        montant = Decimal(str(montant))
        if courant and courant['montant'] == montant:
            courant['mois'].append(mois)
        else:
            courant = {
                'mois': [mois],
                'montant': montant,
                'label': '',
            }
            paliers.append(courant)
    for palier in paliers:
        palier['label'] = formater_plage_mois(palier['mois'], debut, fin)
        palier['phrase'] = '%s : %s' % (
            palier['label'],
            _format_montant(palier['montant']),
        )
    return paliers


def phrase_paliers(parametre, devise='FCFA'):
    paliers = paliers_depuis_parametre(parametre)
    if not paliers:
        return ''
    return ' · '.join(
        '%s %s' % (palier['phrase'], devise) for palier in paliers
    )


def _format_montant(montant):
    valeur = Decimal(str(montant)).quantize(Decimal('1'))
    texte = '%s' % int(valeur)
    if len(texte) > 3:
        groupes = []
        while texte:
            groupes.append(texte[-3:])
            texte = texte[:-3]
        texte = ' '.join(reversed(groupes))
    return texte


def mois_ordre_form(debut=9, fin=6):
    ordre = ordre_mois_facturation(debut, fin)
    restants = [n for n in range(1, 13) if n not in ordre]
    return [{'numero': n, 'nom': nom_mois(n), 'dans_periode': n in ordre}
            for n in ordre + restants]


def tranches_form(parametre=None, slots=TRANCHE_SLOTS):
    paliers = paliers_depuis_parametre(parametre) if parametre else []
    visible_min = 2 if not paliers else max(len(paliers), 1)
    lignes = []
    for index in range(slots):
        if index < len(paliers):
            palier = paliers[index]
            montant = palier['montant']
            montant_txt = ('%s' % montant).rstrip('0').rstrip('.')
            lignes.append({
                'index': index,
                'montant': montant_txt,
                'mois': palier['mois'],
                'visible': True,
            })
        else:
            lignes.append({
                'index': index,
                'montant': '',
                'mois': [],
                'visible': index < visible_min,
            })
    return lignes


def extraire_tarifs_par_mois(post, slots=TRANCHE_SLOTS, debut=None, fin=None):
    """Lit les paliers du POST Django. Dernier palier gagne en cas de chevauchement interdit."""
    mapping = {}
    vus = {}
    periode = None
    if debut is not None and fin is not None:
        periode = {str(m) for m in ordre_mois_facturation(debut, fin)}
    for index in range(slots):
        brut = (post.get('tranche_%s_montant' % index) or '').strip().replace(' ', '')
        mois_list = post.getlist('tranche_%s_mois' % index)
        if not brut and not mois_list:
            continue
        if brut and not mois_list:
            raise ValueError(
                'Pour le tarif n°%s, cochez au moins un mois.' % (index + 1)
            )
        if mois_list and not brut:
            raise ValueError(
                'Pour le tarif n°%s, indiquez le montant à payer.' % (index + 1)
            )
        try:
            valeur = Decimal(brut)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError('Le montant du tarif n°%s n’est pas valide.' % (index + 1))
        if valeur <= 0:
            raise ValueError('Le montant du tarif n°%s doit être supérieur à zéro.' % (index + 1))
        for raw in mois_list:
            mois = str(int(raw))
            if periode is not None and mois not in periode:
                raise ValueError(
                    '%s est hors de la période Premier mois → Dernier mois.'
                    % nom_mois(mois)
                )
            if mois in vus:
                raise ValueError(
                    '%s est coché dans deux tarifs différents. Un mois ne peut avoir qu’un seul montant.'
                    % nom_mois(mois)
                )
            vus[mois] = index
            mapping[mois] = str(valeur)
    return mapping


def _decimal(valeur):
    try:
        montant = Decimal(str(valeur if valeur is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')
    if montant < 0:
        return Decimal('0')
    return montant


def etat_ligne_frais(montant=0, paye=0, mois_nom=''):
    """Payé / versé+reste+en attente / à payer+en attente / vide — pour une colonne de scolarité."""
    montant = _decimal(montant)
    paye = _decimal(paye)
    reste = montant - paye
    if reste < 0:
        reste = Decimal('0')
    if montant <= 0:
        etat = 'vide'
        badge = ''
    elif paye >= montant:
        etat = 'paye'
        badge = 'Payé'
        reste = Decimal('0')
    elif paye > 0:
        etat = 'partiel'
        badge = 'En attente'
    else:
        etat = 'impaye'
        badge = 'En attente'
    return {
        'etat': etat,
        'badge': badge,
        'montant': montant,
        'paye': paye,
        'reste': reste,
        'mois_nom': mois_nom or '',
    }


def etat_depuis_mensualite(mensualite):
    if not mensualite:
        return etat_ligne_frais(0, 0)
    return etat_ligne_frais(
        mensualite.montant,
        mensualite.montant_paye,
        mois_nom=nom_mois(mensualite.mois),
    )


def etat_mois_impayes(mensualites, cle_limite):
    """Premier mois échu non soldé, plus le libellé des autres mois impayés."""
    impayes = []
    for mensualite in mensualites or []:
        if (mensualite.annee, mensualite.mois) >= cle_limite:
            continue
        if mensualite.get_reste_a_payer() > 0:
            impayes.append(mensualite)
    if not impayes:
        return etat_ligne_frais(0, 0)
    etat = etat_depuis_mensualite(impayes[0])
    etat['badge'] = 'Impayé'
    extras = [nom_mois(item.mois) for item in impayes[1:]]
    if len(extras) == 1:
        etat['autres_libelle'] = extras[0]
    elif len(extras) > 1:
        etat['autres_libelle'] = '%s autres' % len(extras)
    else:
        etat['autres_libelle'] = ''
    return etat
