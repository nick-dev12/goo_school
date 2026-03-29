from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("school_admin", "0210_periodescolaire_niveau_lmd"),
    ]

    operations = [
        migrations.AddField(
            model_name="moduleclasse",
            name="periode",
            field=models.ForeignKey(
                blank=True,
                help_text="Semestre auquel ce module est rattaché pour cette classe.",
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="module_classes",
                to="school_admin.periodescolaire",
                verbose_name="Période rattachée",
            ),
        ),
    ]
