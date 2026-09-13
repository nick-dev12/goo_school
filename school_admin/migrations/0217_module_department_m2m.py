# Module mutualisé : relation N-N Module ↔ Spécialité

from django.db import migrations, models


def backfill_module_departments(apps, schema_editor):
    Module = apps.get_model('school_admin', 'Module')
    ModuleDepartment = apps.get_model('school_admin', 'ModuleDepartment')
    for module in Module.objects.filter(department_id__isnull=False).iterator():
        ModuleDepartment.objects.get_or_create(
            module_id=module.id,
            department_id=module.department_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0216_matiere_niveau_lmd_key'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModuleDepartment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('department', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='module_departments', to='school_admin.department', verbose_name='Spécialité')),
                ('module', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='module_departments', to='school_admin.module', verbose_name='Module')),
            ],
            options={
                'verbose_name': 'Module-Spécialité',
                'verbose_name_plural': 'Modules-Spécialités',
                'unique_together': {('module', 'department')},
            },
        ),
        migrations.AlterField(
            model_name='module',
            name='department',
            field=models.ForeignKey(
                blank=True,
                help_text='Renseignée si le module est propre à une seule spécialité ; vide si mutualisé.',
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='modules',
                to='school_admin.department',
                verbose_name='Spécialité principale',
            ),
        ),
        migrations.AddField(
            model_name='module',
            name='departments',
            field=models.ManyToManyField(
                blank=True,
                help_text='Une ou plusieurs spécialités auxquelles ce module est rattaché.',
                related_name='modules_lies',
                through='school_admin.ModuleDepartment',
                to='school_admin.department',
                verbose_name='Spécialités concernées',
            ),
        ),
        migrations.RunPython(backfill_module_departments, migrations.RunPython.noop),
    ]
