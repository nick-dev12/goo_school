# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0173_add_moyenne_annuelle_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='moyenneperiode',
            name='moyenne_avec_coefficient',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Moyenne de l'élève multipliée par le coefficient de la matière",
                max_digits=8,
                null=True,
                verbose_name='Moyenne avec coefficient (moyenne_matiere × coefficient)'
            ),
        ),
    ]
