import django.db.models.deletion
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("school_admin", "0116_fcmtoken"),
    ]

    operations = [
        migrations.CreateModel(
            name="Ponderation",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("annee_scolaire", models.CharField(help_text="Format attendu : 2024-2025", max_length=20, verbose_name="Année scolaire")),
                ("type_calcul", models.CharField(choices=[("classique", "Calcul classique (continu + examen)"), ("personnalise", "Pondération personnalisée")], default="classique", max_length=20, verbose_name="Type de calcul")),
                ("poids_classe", models.DecimalField(decimal_places=2, default=1, max_digits=5, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Poids du contrôle continu")),
                ("poids_examen", models.DecimalField(decimal_places=2, default=1, max_digits=5, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Poids des examens")),
                ("actif", models.BooleanField(default=True, verbose_name="Actif")),
                ("date_creation", models.DateTimeField(auto_now_add=True, verbose_name="Date de création")),
                ("date_modification", models.DateTimeField(auto_now=True, verbose_name="Dernière modification")),
                ("etablissement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ponderations", to="school_admin.etablissement", verbose_name="Établissement")),
            ],
            options={
                "verbose_name": "Pondération",
                "verbose_name_plural": "Pondérations",
                "ordering": ["-date_creation"],
                "unique_together": {("etablissement", "annee_scolaire", "type_calcul")},
            },
        ),
    ]

