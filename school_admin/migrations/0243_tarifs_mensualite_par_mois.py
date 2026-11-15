from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('school_admin', '0242_parent_facultatif')]

    operations = [
        migrations.AddField(
            model_name='parametrescomptabilitegroupeclasse',
            name='montants_mensualite_par_mois',
            field=models.JSONField(blank=True, default=dict, help_text='Mois (1 à 12) associés à un montant différent de la mensualité de base', verbose_name='Montants particuliers par mois'),
        ),
    ]
