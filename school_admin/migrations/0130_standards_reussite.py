from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0129_moyenneperiode_afficher_bulletin'),
    ]

    operations = [
        migrations.CreateModel(
            name='StandardsReussite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('moyenne_passage', models.DecimalField(decimal_places=2, default=10, max_digits=5, verbose_name='Moyenne minimale de passage')),
                ('moyenne_redoublement', models.DecimalField(decimal_places=2, default=8, max_digits=5, verbose_name='Moyenne de redoublement')),
                ('appreciation_conseil', models.TextField(blank=True, null=True, verbose_name='Appréciation du conseil de classe')),
                ('date_creation', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Date de création')),
                ('date_modification', models.DateTimeField(auto_now=True, verbose_name='Dernière modification')),
                ('etablissement', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='standards_reussite', to='school_admin.etablissement', verbose_name='Établissement')),
            ],
            options={
                'verbose_name': 'Standards de réussite',
                'verbose_name_plural': 'Standards de réussite',
            },
        ),
        migrations.CreateModel(
            name='AppreciationMatiereStandard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note_min', models.DecimalField(decimal_places=2, max_digits=5, verbose_name='Note minimale')),
                ('note_max', models.DecimalField(decimal_places=2, max_digits=5, verbose_name='Note maximale')),
                ('appreciation', models.CharField(max_length=150, verbose_name='Appréciation')),
                ('standards', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='appreciations_matieres', to='school_admin.standardsreussite', verbose_name='Standards associés')),
            ],
            options={
                'verbose_name': "Palier d'appréciation",
                'verbose_name_plural': "Paliers d'appréciation",
                'ordering': ['note_min'],
            },
        ),
    ]

