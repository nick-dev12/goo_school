from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0130_standards_reussite'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppreciationConseilStandard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note_min', models.DecimalField(decimal_places=2, max_digits=5, verbose_name='Note minimale')),
                ('appreciation', models.CharField(max_length=200, verbose_name='Appréciation')),
                ('standards', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='appreciations_conseil', to='school_admin.standardsreussite', verbose_name='Standards associés')),
            ],
            options={
                'verbose_name': 'Appréciation conseil',
                'verbose_name_plural': 'Appréciations conseil',
                'ordering': ['note_min'],
            },
        ),
    ]

