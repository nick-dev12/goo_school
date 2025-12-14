# Generated migration for making heure_debut and heure_fin required

from django.db import migrations, models
from datetime import time


def remplir_heures_vides(apps, schema_editor):
    """
    Remplit les heures vides avec les heures depuis periode_etablissement si elle existe,
    sinon utilise des valeurs par défaut.
    """
    CreneauEmploiDuTemps = apps.get_model('school_admin', 'CreneauEmploiDuTemps')
    
    for creneau in CreneauEmploiDuTemps.objects.filter(heure_debut__isnull=True):
        if creneau.periode_etablissement:
            creneau.heure_debut = creneau.periode_etablissement.heure_debut
            creneau.heure_fin = creneau.periode_etablissement.heure_fin
        else:
            # Valeur par défaut : 08:00 - 09:00
            creneau.heure_debut = time(8, 0)
            creneau.heure_fin = time(9, 0)
        creneau.save()
    
    for creneau in CreneauEmploiDuTemps.objects.filter(heure_fin__isnull=True):
        if creneau.periode_etablissement and not creneau.heure_fin:
            creneau.heure_fin = creneau.periode_etablissement.heure_fin
        elif not creneau.heure_fin:
            # Valeur par défaut : 09:00
            creneau.heure_fin = time(9, 0)
        creneau.save()


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0180_add_note_examen_to_justification'),
    ]

    operations = [
        migrations.RunPython(remplir_heures_vides, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='creneauemploidutemps',
            name='heure_debut',
            field=models.TimeField(help_text='Heure de début du créneau', verbose_name='Heure de début'),
        ),
        migrations.AlterField(
            model_name='creneauemploidutemps',
            name='heure_fin',
            field=models.TimeField(help_text='Heure de fin du créneau', verbose_name='Heure de fin'),
        ),
    ]
