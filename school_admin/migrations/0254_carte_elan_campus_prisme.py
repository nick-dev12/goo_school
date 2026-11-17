from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('school_admin', '0253_carte_horizon_signature')]
    operations = [migrations.AlterField(
        model_name='carteidentitepersonnalisation', name='modele',
        field=models.CharField(max_length=20, default='classique', verbose_name='Modèle de carte',
            choices=[('classique', 'Classique'), ('moderne', 'Moderne'), ('horizon', 'Horizon'),
                     ('signature', 'Signature'), ('elan', 'Élan'), ('campus', 'Campus'), ('prisme', 'Prisme')]))]
