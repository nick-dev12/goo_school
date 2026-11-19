from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('school_admin', '0255_carte_rivage_academie_equateur')]
    operations = [migrations.AddField(model_name='moyenneperiode', name='empreinte_sources',
                  field=models.CharField(max_length=64, blank=True, default='', editable=False))]
