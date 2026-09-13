from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0217_module_department_m2m'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='matiere',
            constraint=models.UniqueConstraint(
                condition=models.Q(('department__isnull', True), ('module__isnull', False)),
                fields=('nom', 'etablissement', 'module', 'niveau_lmd_key'),
                name='matiere_unique_module_partage_niveau',
            ),
        ),
    ]
