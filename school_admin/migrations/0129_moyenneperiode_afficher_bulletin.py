from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0128_notificationeleve'),
    ]

    operations = [
        migrations.AddField(
            model_name='moyenneperiode',
            name='afficher_bulletin',
            field=models.BooleanField(
                default=True,
                help_text="Détermine si la moyenne générale et le bulletin sont visibles dans l'espace élève.",
                verbose_name="Bulletin visible par l'élève",
            ),
        ),
    ]

