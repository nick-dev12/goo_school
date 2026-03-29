# Generated manually for ModuleClasse.numero_ue

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0208_desactiver_options_examens_formulaire_classe'),
    ]

    operations = [
        migrations.AddField(
            model_name='moduleclasse',
            name='numero_ue',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ex. UE3.1.1 — affiché sur le bulletin pour cette association module / classe.',
                max_length=80,
                verbose_name="Numéro d'unité d'enseignement (UE)",
            ),
        ),
    ]
