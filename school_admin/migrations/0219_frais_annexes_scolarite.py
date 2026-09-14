from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0218_matiere_unique_module_partage'),
    ]

    operations = [
        migrations.AddField(
            model_name='parametrescomptabilite',
            name='frais_annexes',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Tenue, carte scolaire, dossier, assurance, examen, transport, cantine, apport, autres.',
                verbose_name='Frais annexes',
            ),
        ),
        migrations.AddField(
            model_name='parametrescomptabilitegroupeclasse',
            name='frais_annexes',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Tenue, carte scolaire, dossier, assurance, examen, transport, cantine, apport, autres.',
                verbose_name='Frais annexes',
            ),
        ),
        migrations.CreateModel(
            name='FraisAnnexe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='Identifiant stable (tenue, carte_scolaire, autre, ...)', max_length=40, verbose_name='Code du frais')),
                ('libelle', models.CharField(max_length=120, verbose_name='Libellé')),
                ('periodicite', models.CharField(choices=[('inscription', "À l'inscription"), ('annuel', 'Annuel'), ('ponctuel', 'Ponctuel')], default='annuel', max_length=20, verbose_name='Périodicité')),
                ('obligatoire', models.BooleanField(default=True, verbose_name='Obligatoire')),
                ('montant', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Montant')),
                ('montant_paye', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10, verbose_name='Montant payé')),
                ('reste_a_payer', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10, verbose_name='Reste à payer')),
                ('date_echeance', models.DateField(verbose_name="Date d'échéance")),
                ('statut', models.CharField(choices=[('en_attente', 'En attente'), ('paye', 'Payé'), ('en_retard', 'En retard')], default='en_attente', max_length=20, verbose_name='Statut')),
                ('date_paiement', models.DateTimeField(blank=True, null=True, verbose_name='Date de paiement')),
                ('date_creation', models.DateTimeField(auto_now_add=True, verbose_name='Date de création')),
                ('annee_scolaire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='frais_annexes', to='school_admin.anneescolaire', verbose_name='Année scolaire')),
                ('comptabilite_eleve', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='frais_annexes', to='school_admin.comptabiliteeleve', verbose_name='Comptabilité élève')),
                ('eleve', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='frais_annexes', to='school_admin.eleve', verbose_name='Élève')),
                ('etablissement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='frais_annexes', to='school_admin.etablissement', verbose_name='Établissement')),
            ],
            options={
                'verbose_name': 'Frais annexe',
                'verbose_name_plural': 'Frais annexes',
                'ordering': ['libelle'],
            },
        ),
        migrations.AddField(
            model_name='paiementeleve',
            name='frais_annexe',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='paiements', to='school_admin.fraisannexe', verbose_name='Frais annexe'),
        ),
        migrations.AlterField(
            model_name='paiementeleve',
            name='type_paiement',
            field=models.CharField(choices=[('frais_inscription', "Frais d'inscription"), ('mensualite', 'Mensualité'), ('frais_annexe', 'Frais annexes'), ('autre', 'Autre')], max_length=30, verbose_name='Type de paiement'),
        ),
        migrations.AddIndex(
            model_name='fraisannexe',
            index=models.Index(fields=['eleve', 'annee_scolaire'], name='fraisann_eleve_annee_idx'),
        ),
        migrations.AddIndex(
            model_name='fraisannexe',
            index=models.Index(fields=['etablissement', 'statut'], name='fraisann_etab_statut_idx'),
        ),
        migrations.AddIndex(
            model_name='fraisannexe',
            index=models.Index(fields=['code'], name='fraisann_code_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='fraisannexe',
            unique_together={('eleve', 'annee_scolaire', 'code')},
        ),
    ]
