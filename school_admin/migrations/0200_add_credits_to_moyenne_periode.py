# Generated migration for adding credits field to MoyennePeriode

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0199_add_module_and_credits'),
    ]

    operations = [
        migrations.AddField(
            model_name='moyenneperiode',
            name='credits',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name='Crédits utilisés au calcul (supérieur)',
                help_text='Crédits de la matière au moment du calcul (enseignement supérieur)'
            ),
        ),
    ]
