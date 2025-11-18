# Generated manually to add photo_profil column to eleve table

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0140_alter_professeurotpcode_professeur'),
    ]

    operations = [
        migrations.AddField(
            model_name='eleve',
            name='photo_profil',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='eleves/photos/',
                verbose_name='Photo de profil',
                help_text="Photographie récente de l'élève pour son dossier",
            ),
        ),
    ]

