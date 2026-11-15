from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0243_tarifs_mensualite_par_mois'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fraisannexe',
            name='statut',
            field=models.CharField(
                choices=[
                    ('en_attente', 'En attente'),
                    ('paye', 'Payé'),
                    ('en_retard', 'En retard'),
                    ('clos', 'Clos / désabonné'),
                ],
                default='en_attente',
                max_length=20,
                verbose_name='Statut',
            ),
        ),
        migrations.CreateModel(
            name='ChoixFraisAnnexeEleve',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=40, verbose_name='Code du frais')),
                ('statut', models.CharField(
                    choices=[
                        ('inscrit', 'Inscrit'),
                        ('refuse', 'Refusé'),
                        ('non_choisi', 'Non choisi'),
                    ],
                    default='non_choisi',
                    max_length=20,
                    verbose_name='Statut du choix',
                )),
                ('date_choix', models.DateTimeField(auto_now=True, verbose_name='Dernière mise à jour')),
                ('date_creation', models.DateTimeField(auto_now_add=True, verbose_name='Date de création')),
                ('annee_scolaire', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='choix_frais_annexes',
                    to='school_admin.anneescolaire',
                    verbose_name='Année scolaire',
                )),
                ('eleve', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='choix_frais_annexes',
                    to='school_admin.eleve',
                    verbose_name='Élève',
                )),
                ('etablissement', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='choix_frais_annexes',
                    to='school_admin.etablissement',
                    verbose_name='Établissement',
                )),
            ],
            options={
                'verbose_name': 'Choix frais annexe élève',
                'verbose_name_plural': 'Choix frais annexes élèves',
            },
        ),
        migrations.AddIndex(
            model_name='choixfraisannexeeleve',
            index=models.Index(fields=['eleve', 'annee_scolaire'], name='choixfax_eleve_annee_idx'),
        ),
        migrations.AddIndex(
            model_name='choixfraisannexeeleve',
            index=models.Index(fields=['etablissement', 'code'], name='choixfax_etab_code_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='choixfraisannexeeleve',
            unique_together={('eleve', 'annee_scolaire', 'code')},
        ),
    ]
