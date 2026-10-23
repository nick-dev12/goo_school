"""Ramène les types d'établissement saisis par l'ancien formulaire admin (lycee, college…) aux valeurs du modèle."""
from django.db import migrations

CORRESPONDANCE = {
    'lycee': 'lycée',
    'college': 'collège',
    'lycee_college': 'collège_lycée',
    'ecole_primaire': 'primary',
    'primaire': 'primary',
    'universite': 'superieur',
}


def normaliser(apps, schema_editor):
    Etablissement = apps.get_model('school_admin', 'Etablissement')
    for ancien, nouveau in CORRESPONDANCE.items():
        Etablissement.objects.filter(type_etablissement=ancien).update(type_etablissement=nouveau)


class Migration(migrations.Migration):
    dependencies = [
        ('school_admin', '0240_admissions_diplomes_niveaux'),
    ]

    operations = [
        migrations.RunPython(normaliser, migrations.RunPython.noop),
    ]
