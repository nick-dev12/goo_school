# Generated manually — aligne Professeur.niveau_enseignement sur Etablissement.type_etablissement

from django.db import migrations

TYPE_TO_NIVEAU = {
    'primary': 'primaire',
    'primaire': 'primaire',
    'collège': 'college',
    'college': 'college',
    'lycée': 'lycee',
    'lycee': 'lycee',
    'collège_lycée': 'lycee',
    'college_lycee': 'lycee',
    'lycee_college': 'lycee',
    'mixte': 'primaire',
    'superieur': 'superieur',
}


def _expected_niveau(type_etablissement):
    if not type_etablissement:
        return 'college'
    return TYPE_TO_NIVEAU.get(str(type_etablissement).strip(), 'college')


def sync_prof_niveaux(apps, schema_editor):
    Professeur = apps.get_model('school_admin', 'Professeur')
    Etablissement = apps.get_model('school_admin', 'Etablissement')
    etab_types = {
        row['id']: row['type_etablissement']
        for row in Etablissement.objects.values('id', 'type_etablissement')
    }
    to_update = []
    for prof in Professeur.objects.exclude(etablissement_id__isnull=True).iterator():
        type_etab = etab_types.get(prof.etablissement_id)
        expected = _expected_niveau(type_etab)
        if prof.niveau_enseignement != expected:
            prof.niveau_enseignement = expected
            to_update.append(prof)
    if to_update:
        Professeur.objects.bulk_update(to_update, ['niveau_enseignement'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0223_pce_syscohada_revise'),
    ]

    operations = [
        migrations.RunPython(sync_prof_niveaux, migrations.RunPython.noop),
    ]
