"""Contacts imprimes sur les cartes, sans requete par eleve en classe."""
from django.db.models import Prefetch, prefetch_related_objects
from school_admin.model.lien_familial_model import LienFamilial


def precharger_contacts_cartes(eleves):
    prefetch_related_objects(eleves, Prefetch(
        'liens_parents', queryset=LienFamilial.objects.filter(
            actif=True, statut='valide', parent__actif=True, parent__is_active=True
        ).select_related('parent').order_by('-est_inscripteur', 'pk'),
        to_attr='contacts_carte_lies'))


def telephone_parent_carte(eleve):
    # L'aperçu utilise uniquement un contact fictif, sans interrogation SQL.
    if not hasattr(eleve, 'liens_parents'):
        return getattr(eleve, 'parent_telephone', '') or 'Non renseigné'
    if not hasattr(eleve, 'contacts_carte_lies'):
        precharger_contacts_cartes([eleve])
    for lien in eleve.contacts_carte_lies:
        telephone = (lien.parent.telephone or '').strip()
        if telephone:
            return telephone
    return (eleve.parent_telephone or '').strip() or 'Non renseigné'


# Codes ISO et noms normalises acceptes pour les pays utilises par les etablissements.
_CODES_TELEPHONE = {
    'sn': ('221', 'senegal'), 'ml': ('223', 'mali'),
    'bf': ('226', 'burkina faso'), 'ne': ('227', 'niger'),
    'bj': ('229', 'benin'), 'tg': ('228', 'togo'),
    'ci': ('225', "cote d'ivoire"), 'gw': ('245', 'guinee bissau'),
    'cm': ('237', 'cameroun'), 'td': ('235', 'tchad'),
    'cf': ('236', 'republique centrafricaine'), 'cg': ('242', 'congo'),
    'cd': ('243', 'republique democratique du congo'),
    'ga': ('241', 'gabon'), 'gq': ('240', 'guinee equatoriale'),
    'ma': ('212', 'maroc'), 'tn': ('216', 'tunisie'), 'dz': ('213', 'algerie'),
    'mr': ('222', 'mauritanie'), 'gn': ('224', 'guinee'),
    'gm': ('220', 'gambie'), 'cv': ('238', 'cap vert'),
    'gh': ('233', 'ghana'), 'ng': ('234', 'nigeria'),
    'fr': ('33', 'france'), 'be': ('32', 'belgique'), 'ch': ('41', 'suisse'),
    'ca': ('1', 'canada'), 'us': ('1', 'etats unis'),
    'mg': ('261', 'madagascar'), 'dj': ('253', 'djibouti'),
    'km': ('269', 'comores'), 'ht': ('509', 'haiti'),
}


def telephone_international_carte(numero, pays):
    """Ajoute l'indicatif a l'affichage uniquement, sans inventer un pays inconnu."""
    import re
    import unicodedata
    numero = (numero or '').strip()
    if not numero or numero == 'Non renseigné':
        return 'Non renseigné'
    if numero.startswith('+'):
        return numero
    if numero.startswith('00'):
        return '+' + numero[2:]
    pays = ''.join(c for c in unicodedata.normalize('NFKD', str(pays or '').lower())
                   if not unicodedata.combining(c)).replace('’', "'").replace('-', ' ')
    pays = ' '.join(pays.split())
    if pays.startswith('republique du '):
        pays = pays[len('republique du '):]
    code = next((indicatif for iso, (indicatif, nom) in _CODES_TELEPHONE.items()
                 if pays in (iso, nom)), None)
    if not code:
        return numero
    chiffres = re.sub(r'[\s().-]', '', numero)
    if not chiffres.isdigit():
        return numero
    # Indicatif deja saisi sans + (ex. 221770001122).
    if chiffres.startswith(code) and len(chiffres) > 10:
        return '+' + chiffres
    if pays in ('fr', 'france', 'be', 'belgique', 'ch', 'suisse', 'ma', 'maroc', 'dz', 'algerie'):
        chiffres = chiffres.removeprefix('0')
    return '+' + code + ' ' + chiffres
