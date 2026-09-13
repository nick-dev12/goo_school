# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0214_syncaction'),
    ]

    operations = [
        migrations.AddField(
            model_name='department',
            name='sigle',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ex: GL (Génie Logiciel), TL (Transport & Logistique) — utilisé sur bulletins et relevés.',
                max_length=12,
                verbose_name='Code / Sigle de la spécialité',
            ),
        ),
        migrations.AddConstraint(
            model_name='department',
            constraint=models.UniqueConstraint(
                condition=models.Q(('sigle__gt', '')),
                fields=('etablissement', 'sigle'),
                name='unique_department_sigle_par_etablissement',
            ),
        ),
    ]
