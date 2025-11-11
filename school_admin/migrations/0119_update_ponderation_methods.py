import django.core.validators
from django.db import migrations, models


def migrate_ponderations(apps, schema_editor):
    Ponderation = apps.get_model('school_admin', 'Ponderation')
    for ponderation in Ponderation.objects.all():
        ponderation.type_calcul = 'classique_50_50'
        ponderation.poids_classe = 50
        ponderation.poids_examen = 50
        ponderation.save(update_fields=['type_calcul', 'poids_classe', 'poids_examen'])


class Migration(migrations.Migration):

    dependencies = [
        ("school_admin", "0118_alter_ponderation_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ponderation",
            name="poids_classe",
            field=models.PositiveSmallIntegerField(default=50, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name="Pourcentage du contrôle continu"),
        ),
        migrations.AlterField(
            model_name="ponderation",
            name="poids_examen",
            field=models.PositiveSmallIntegerField(default=50, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name="Pourcentage des examens"),
        ),
        migrations.AlterField(
            model_name="ponderation",
            name="type_calcul",
            field=models.CharField(choices=[("classique_50_50", "Classique (50/50)"), ("exigeante_40_60", "École exigeante (40/60)"), ("continu_60_40", "Travail continu (60/40)"), ("speciale_30_70", "Évaluation spéciale (30/70)")], default="classique_50_50", max_length=20, verbose_name="Type de calcul"),
        ),
        migrations.RunPython(migrate_ponderations, migrations.RunPython.noop),
    ]

