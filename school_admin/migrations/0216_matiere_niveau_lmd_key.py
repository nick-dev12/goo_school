# Generated manually for niveau-scoped matiere uniqueness in modules

from django.db import migrations, models


def _niveau_key_from_classe(classe):
    if getattr(classe, 'niveau_lmd', None) and classe.niveau_lmd != 'AUTRE':
        return classe.niveau_lmd
    if getattr(classe, 'academic_level_id', None) and classe.academic_level:
        return (classe.academic_level.code or '').strip() or 'AUTRE'
    return 'AUTRE'


def backfill_matiere_niveau_lmd_key(apps, schema_editor):
    Matiere = apps.get_model('school_admin', 'Matiere')
    Classe = apps.get_model('school_admin', 'Classe')
    for matiere in Matiere.objects.filter(module__isnull=False).iterator():
        class_ids = list(
            matiere.classes.through.objects.filter(matiere_id=matiere.id).values_list('classe_id', flat=True)
        )
        if not class_ids:
            matiere.niveau_lmd_key = ''
        else:
            keys = set()
            for classe in Classe.objects.filter(id__in=class_ids):
                keys.add(_niveau_key_from_classe(classe))
            matiere.niveau_lmd_key = keys.pop() if len(keys) == 1 else ''
        matiere.save(update_fields=['niveau_lmd_key'])


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0215_department_sigle'),
    ]

    operations = [
        migrations.AddField(
            model_name='matiere',
            name='niveau_lmd_key',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Clé de niveau LMD (L1, L2, …) lorsque la matière est rattachée à un module supérieur',
                max_length=20,
                verbose_name='Niveau LMD (module)',
            ),
        ),
        migrations.RunPython(backfill_matiere_niveau_lmd_key, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='matiere',
            name='matiere_unique_par_module',
        ),
        migrations.AddConstraint(
            model_name='matiere',
            constraint=models.UniqueConstraint(
                condition=models.Q(('department__isnull', False), ('module__isnull', False)),
                fields=('nom', 'etablissement', 'department', 'module', 'niveau_lmd_key'),
                name='matiere_unique_par_module_niveau',
            ),
        ),
    ]
