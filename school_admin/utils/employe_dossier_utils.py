# school_admin/utils/employe_dossier_utils.py

from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.utils.dateparse import parse_date

from ..model.employe_dossier_model import DocumentEmploye, DossierEmployeComplementaire


def parse_optional_decimal(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        return Decimal(str(value).replace(',', '.').strip())
    except (InvalidOperation, ValueError):
        return None


def parse_optional_date(value):
    if not value or not str(value).strip():
        return None
    if hasattr(value, 'year'):
        return value
    return parse_date(str(value).strip())


def get_sexe_display(sexe):
    if sexe == 'M':
        return 'Masculin'
    if sexe == 'F':
        return 'Féminin'
    return '—'


def get_or_create_dossier(professeur=None, personnel=None):
    if professeur:
        dossier, _ = DossierEmployeComplementaire.objects.get_or_create(professeur=professeur)
        return dossier
    if personnel:
        dossier, _ = DossierEmployeComplementaire.objects.get_or_create(
            personnel_administratif=personnel,
        )
        return dossier
    return None


def update_dossier_from_post(dossier, post_data):
    """Met à jour le dossier avec les champs fournis (tous optionnels)."""
    dossier.date_naissance = parse_optional_date(post_data.get('date_naissance'))
    dossier.lieu_naissance = (post_data.get('lieu_naissance') or '').strip()
    dossier.nationalite = (post_data.get('nationalite') or '').strip()
    dossier.adresse = (post_data.get('adresse') or '').strip()
    dossier.numero_cni = (post_data.get('numero_cni') or '').strip()
    dossier.numero_cnss = (post_data.get('numero_cnss') or '').strip()
    dossier.type_contrat = (post_data.get('type_contrat') or '').strip()
    dossier.date_fin_contrat = parse_optional_date(post_data.get('date_fin_contrat'))
    dossier.salaire_base = parse_optional_decimal(post_data.get('salaire_base'))
    dossier.banque = (post_data.get('banque') or '').strip()
    dossier.numero_compte_bancaire = (post_data.get('numero_compte_bancaire') or '').strip()
    dossier.diplome_plus_eleve = (post_data.get('diplome_plus_eleve') or '').strip()
    dossier.numero_autorisation = (post_data.get('numero_autorisation') or '').strip()
    dossier.contact_urgence_nom = (post_data.get('contact_urgence_nom') or '').strip()
    dossier.contact_urgence_telephone = (post_data.get('contact_urgence_telephone') or '').strip()
    dossier.contact_urgence_lien = (post_data.get('contact_urgence_lien') or '').strip()
    dossier.observations = (post_data.get('observations') or '').strip()
    dossier.save()
    return dossier


def update_employe_base_from_post(employe, post_data, is_professeur=True):
    """Met à jour sexe, date_embauche et prix horaire (champs de base)."""
    sexe = (post_data.get('sexe') or '').strip()
    if sexe in ('M', 'F'):
        employe.sexe = sexe
    employe.date_embauche = parse_optional_date(post_data.get('date_embauche'))
    employe.prix_volume_horaire = parse_optional_decimal(post_data.get('prix_volume_horaire'))
    employe.save(update_fields=['sexe', 'date_embauche', 'prix_volume_horaire'])


def save_documents_from_request(request, professeur=None, personnel=None):
    """Enregistre les documents uploadés (optionnels, multiples)."""
    files = request.FILES.getlist('documents_fichier')
    libelles = request.POST.getlist('documents_libelle')
    created = []
    for index, fichier in enumerate(files):
        if not fichier:
            continue
        libelle = libelles[index].strip() if index < len(libelles) else ''
        doc = DocumentEmploye(
            professeur=professeur,
            personnel_administratif=personnel,
            libelle=libelle or fichier.name,
            fichier=fichier,
        )
        doc.save()
        created.append(doc)
    return created


def get_documents_for_employe(professeur=None, personnel=None):
    if professeur:
        return DocumentEmploye.objects.filter(professeur=professeur).order_by('-date_ajout')
    if personnel:
        return DocumentEmploye.objects.filter(personnel_administratif=personnel).order_by('-date_ajout')
    return DocumentEmploye.objects.none()


DOSSIER_FORM_FIELDS = (
    'date_naissance',
    'lieu_naissance',
    'nationalite',
    'adresse',
    'numero_cni',
    'numero_cnss',
    'type_contrat',
    'date_fin_contrat',
    'salaire_base',
    'banque',
    'numero_compte_bancaire',
    'diplome_plus_eleve',
    'numero_autorisation',
    'contact_urgence_nom',
    'contact_urgence_telephone',
    'contact_urgence_lien',
    'observations',
)


def dossier_form_data_from_dossier(dossier):
    """Préremplit un dict formulaire à partir d'un dossier existant."""
    if not dossier:
        return {field: '' for field in DOSSIER_FORM_FIELDS}
    return {
        'date_naissance': dossier.date_naissance.strftime('%Y-%m-%d') if dossier.date_naissance else '',
        'lieu_naissance': dossier.lieu_naissance or '',
        'nationalite': dossier.nationalite or '',
        'adresse': dossier.adresse or '',
        'numero_cni': dossier.numero_cni or '',
        'numero_cnss': dossier.numero_cnss or '',
        'type_contrat': dossier.type_contrat or '',
        'date_fin_contrat': dossier.date_fin_contrat.strftime('%Y-%m-%d') if dossier.date_fin_contrat else '',
        'salaire_base': str(dossier.salaire_base) if dossier.salaire_base is not None else '',
        'banque': dossier.banque or '',
        'numero_compte_bancaire': dossier.numero_compte_bancaire or '',
        'diplome_plus_eleve': dossier.diplome_plus_eleve or '',
        'numero_autorisation': dossier.numero_autorisation or '',
        'contact_urgence_nom': dossier.contact_urgence_nom or '',
        'contact_urgence_telephone': dossier.contact_urgence_telephone or '',
        'contact_urgence_lien': dossier.contact_urgence_lien or '',
        'observations': dossier.observations or '',
    }


def dossier_form_data_from_post(post_data):
    """Extrait les champs dossier depuis un POST."""
    return {field: (post_data.get(field) or '').strip() for field in DOSSIER_FORM_FIELDS}


def dossier_has_post_data(post_data):
    """True si au moins un champ complémentaire du dossier est renseigné."""
    for field in DOSSIER_FORM_FIELDS:
        if (post_data.get(field) or '').strip():
            return True
    return False


def save_dossier_from_post_if_any(professeur=None, personnel=None, post_data=None):
    """Crée ou met à jour le dossier si des champs complémentaires sont fournis."""
    if post_data is None or not dossier_has_post_data(post_data):
        return None
    dossier = get_or_create_dossier(professeur=professeur, personnel=personnel)
    update_dossier_from_post(dossier, post_data)
    return dossier
