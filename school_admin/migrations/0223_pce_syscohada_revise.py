from django.db import migrations, models


def migrer_plans_existants(apps, schema_editor):
    from school_admin.model.comptabilite_generale_model import CompteComptable
    from school_admin.model.etablissement_model import Etablissement
    from school_admin.services.comptabilite_generale import migrer_plan_syscohada

    ids = list(CompteComptable.objects.values_list('etablissement_id', flat=True).distinct())
    if not ids:
        return
    for etab in Etablissement.objects.filter(pk__in=ids):
        migrer_plan_syscohada(etab)


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0222_comptabilite_generale'),
    ]

    operations = [
        migrations.AddField(
            model_name='parametrescomptabilite',
            name='regime_comptable',
            field=models.CharField(
                choices=[
                    ('engagement', "Comptabilité d'engagement (411)"),
                    ('tresorerie', 'Système de trésorerie (encaissements)'),
                ],
                default='engagement',
                help_text="Engagement : créances en 411. Trésorerie : encaissements directs en 70x. "
                          "Ne pas changer en cours d'exercice.",
                max_length=16,
                verbose_name='Régime comptable',
            ),
        ),
        migrations.AddField(
            model_name='parametrescomptabilite',
            name='exercice_aligne_sur',
            field=models.CharField(
                choices=[
                    ('annee_civile', 'Année civile (1er janvier – 31 décembre)'),
                    ('annee_scolaire', 'Année scolaire (pédagogie uniquement)'),
                ],
                default='annee_civile',
                help_text="L'exercice SYSCOHADA / DGI est l'année civile. L'année scolaire reste pédagogique.",
                max_length=16,
                verbose_name="Alignement de l'exercice",
            ),
        ),
        migrations.RunPython(migrer_plans_existants, noop_reverse),
    ]
