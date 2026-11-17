from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('school_admin', '0254_carte_elan_campus_prisme')]
    operations = [migrations.AlterField(
        model_name='carteidentitepersonnalisation', name='modele',
        field=models.CharField(max_length=20, default='classique', verbose_name='Modèle de carte',
            choices=[('classique', 'Classique'), ('moderne', 'Moderne'), ('horizon', 'Horizon'),
                     ('signature', 'Signature'), ('elan', 'Élan'), ('campus', 'Campus'), ('prisme', 'Prisme'),
                     ('rivage', 'Rivage'), ('academie', 'Académie'), ('equateur', 'Équateur')]))]
