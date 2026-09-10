from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("school_admin", "0213_employe_dossier_documents_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="SyncAction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "client_uuid",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        unique=True,
                        verbose_name="UUID client",
                    ),
                ),
                ("resource", models.CharField(max_length=64, verbose_name="Ressource")),
                (
                    "action",
                    models.CharField(
                        default="CREATE", max_length=16, verbose_name="Action"
                    ),
                ),
                ("utilisateur_id", models.PositiveIntegerField(verbose_name="ID utilisateur")),
                (
                    "utilisateur_type",
                    models.CharField(
                        default="professeur",
                        max_length=32,
                        verbose_name="Type utilisateur",
                    ),
                ),
                (
                    "resultat",
                    models.JSONField(blank=True, default=dict, verbose_name="Résultat"),
                ),
                (
                    "date_creation",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
            ],
            options={
                "verbose_name": "Action de synchronisation",
                "verbose_name_plural": "Actions de synchronisation",
                "ordering": ["-date_creation"],
            },
        ),
        migrations.AddIndex(
            model_name="syncaction",
            index=models.Index(
                fields=["utilisateur_type", "utilisateur_id"],
                name="school_admi_utilisa_sync_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="syncaction",
            index=models.Index(
                fields=["resource", "date_creation"],
                name="school_admi_resourc_sync_idx",
            ),
        ),
    ]
