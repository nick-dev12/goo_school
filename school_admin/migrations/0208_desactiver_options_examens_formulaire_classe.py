# Retire du formulaire d'ajout de classe les options listées (catalogue.actif = False).

from django.db import migrations


CODES_A_DESACTIVER = [
    'BT',
    'LP',
    'BP',
    'CONCOURS_BTS',
    'CONCOURS_BT',
    'CONCOURS_ADMIN',
    'EXAMEN_BLANC',
    'CERTIF_PRO',
    'VAE',
    'AUTRE_INSTIT',
]


def desactiver_options(apps, schema_editor):
    Catalogue = apps.get_model('school_admin', 'CatalogueExamenConcours')
    Catalogue.objects.filter(code__in=CODES_A_DESACTIVER).update(actif=False)


def reactiver_options(apps, schema_editor):
    Catalogue = apps.get_model('school_admin', 'CatalogueExamenConcours')
    Catalogue.objects.filter(code__in=CODES_A_DESACTIVER).update(actif=True)


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0207_add_classe_parcours_examen'),
    ]

    operations = [
        migrations.RunPython(desactiver_options, reactiver_options),
    ]
