# Generated manually for Module.classes M2M

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0202_matiere_unique_par_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='module',
            name='classes',
            field=models.ManyToManyField(
                blank=True,
                help_text="Classes qui suivent ce module (sélectionnées par niveau LMD lors de la création)",
                related_name='modules',
                to='school_admin.classe',
                verbose_name='Classes concernées'
            ),
        ),
    ]
