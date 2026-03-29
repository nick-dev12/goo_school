# Generated manually for LMD bulletin (supérieur)

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0205_add_domaine_mention_department'),
    ]

    operations = [
        migrations.AddField(
            model_name='moyenneperiode',
            name='note_rattrapage',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Session dont le nom contient « rattrap » ; retenue si supérieure à la note d'examen pour le calcul LMD.",
                max_digits=5,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(20),
                ],
                verbose_name='Note de rattrapage',
            ),
        ),
    ]
