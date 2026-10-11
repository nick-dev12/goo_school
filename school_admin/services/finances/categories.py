"""Catégories par établissement. Les valeurs de départ restent modifiables."""
from school_admin.model.finances_model import CategorieFinanciere
from school_admin.services.comptabilite_generale import compte, ensure_plan_comptable

CATEGORIES_SORTIE = (
    ('Salaire / vacataire', '6611', 10),
    ('Loyer', '622', 20),
    ('Électricité / eau', '605', 30),
    ('Fournitures', '604', 40),
    ('Carburant / transport', '624', 50),
    ('Autre sortie', '604', 60),
)

CATEGORIES_RECETTE = (
    ('Activité', '7068', 10),
    ('Subvention', '711', 20),
    ('Recette diverse', '758', 30),
)

MOTIF_VERS_LIBELLE = {
    'salaire': 'Salaire / vacataire',
    'loyer': 'Loyer',
    'electricite': 'Électricité / eau',
    'fournitures': 'Fournitures',
    'carburant': 'Carburant / transport',
    'autre': 'Autre sortie',
}


def _poser_categories(etablissement, type_categorie, lignes):
    for libelle, numero, ordre in lignes:
        compte_lie = compte(etablissement, numero)
        if compte_lie is None:
            continue
        CategorieFinanciere.objects.get_or_create(
            etablissement=etablissement,
            type_categorie=type_categorie,
            libelle=libelle,
            defaults={
                'compte_comptable': compte_lie,
                'ordre': ordre,
                'actif': True,
            },
        )


def assurer_categories(etablissement):
    ensure_plan_comptable(etablissement)
    _poser_categories(etablissement, 'sortie', CATEGORIES_SORTIE)
    _poser_categories(etablissement, 'recette', CATEGORIES_RECETTE)


def categorie_pour_motif(etablissement, motif):
    assurer_categories(etablissement)
    libelle = MOTIF_VERS_LIBELLE.get(motif, 'Autre sortie')
    return CategorieFinanciere.objects.filter(
        etablissement=etablissement,
        type_categorie='sortie',
        libelle=libelle,
        actif=True,
    ).first()
