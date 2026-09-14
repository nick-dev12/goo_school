from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0219_frais_annexes_scolarite'),
        ('school_admin', '0219_pg_trgm_unaccent'),
    ]

    operations = [
        migrations.AddField(
            model_name='fraisinscription',
            name='montant_brut',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Montant barème avant application de la remise fratrie',
                max_digits=10,
                null=True,
                verbose_name='Montant avant remise',
            ),
        ),
        migrations.AddField(
            model_name='fraisinscription',
            name='remise_fratrie',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=10,
                verbose_name='Remise fratrie',
            ),
        ),
        migrations.AddField(
            model_name='mensualite',
            name='montant_brut',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Montant barème avant application de la remise fratrie',
                max_digits=10,
                null=True,
                verbose_name='Montant avant remise',
            ),
        ),
        migrations.AddField(
            model_name='mensualite',
            name='remise_fratrie',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=10,
                verbose_name='Remise fratrie',
            ),
        ),
        migrations.AddField(
            model_name='paiementeleve',
            name='numero_recu',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Numéro séquentiel officiel du reçu (ex: REC-2025-00001)',
                max_length=40,
                verbose_name='Numéro de reçu',
            ),
        ),
        migrations.AlterField(
            model_name='paiementeleve',
            name='type_paiement',
            field=models.CharField(
                choices=[
                    ('frais_inscription', "Frais d'inscription"),
                    ('mensualite', 'Mensualité'),
                    ('frais_annexe', 'Frais annexes'),
                    ('moratoire', 'Moratoire'),
                    ('autre', 'Autre'),
                ],
                max_length=30,
                verbose_name='Type de paiement',
            ),
        ),
        migrations.AddIndex(
            model_name='paiementeleve',
            index=models.Index(fields=['etablissement', 'numero_recu'], name='paiemeleve_etab_recu_idx'),
        ),
        migrations.AddConstraint(
            model_name='paiementeleve',
            constraint=models.UniqueConstraint(
                condition=~models.Q(numero_recu=''),
                fields=('etablissement', 'numero_recu'),
                name='uniq_recu_paiement_etablissement_numero',
            ),
        ),
        migrations.AlterField(
            model_name='notificationparent',
            name='type_notification',
            field=models.CharField(
                choices=[
                    ('presence', 'Présence / Absence'),
                    ('note', 'Note individuelle'),
                    ('moyenne', 'Moyenne de période'),
                    ('bulletin', 'Bulletin disponible'),
                    ('sanction', 'Sanction appliquée'),
                    ('evaluation', 'Évaluation programmée'),
                    ('information', 'Information générale'),
                    ('scolarite', 'Scolarité / impayé'),
                ],
                max_length=30,
                verbose_name='Type de notification',
            ),
        ),
        migrations.CreateModel(
            name='CompteurRecuPaiement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dernier_numero', models.PositiveIntegerField(default=0, verbose_name='Dernier numéro attribué')),
                ('annee_scolaire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compteurs_recus_paiement', to='school_admin.anneescolaire', verbose_name='Année scolaire')),
                ('etablissement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compteurs_recus_paiement', to='school_admin.etablissement', verbose_name='Établissement')),
            ],
            options={
                'verbose_name': 'Compteur de reçus de paiement',
                'verbose_name_plural': 'Compteurs de reçus de paiement',
                'unique_together': {('etablissement', 'annee_scolaire')},
            },
        ),
        migrations.CreateModel(
            name='RelanceImpaye',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telephone', models.CharField(blank=True, max_length=30, verbose_name='Téléphone destinataire')),
                ('canal', models.CharField(choices=[('whatsapp', 'WhatsApp'), ('sms', 'SMS'), ('in_app', 'Notification in-app')], default='whatsapp', max_length=20)),
                ('statut', models.CharField(choices=[('envoye', 'Envoyé'), ('partiel', 'Partiellement envoyé'), ('echec', 'Échec'), ('ignore', 'Ignoré')], default='envoye', max_length=20)),
                ('declenche_par', models.CharField(choices=[('automatique', 'Automatique'), ('manuel', 'Manuel (1 clic)')], default='manuel', max_length=20)),
                ('message', models.TextField(verbose_name='Message envoyé')),
                ('montant_du', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('date_echeance', models.DateField(blank=True, null=True)),
                ('erreur', models.TextField(blank=True)),
                ('date_envoi', models.DateTimeField(default=django.utils.timezone.now)),
                ('annee_scolaire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relances_impayes', to='school_admin.anneescolaire', verbose_name='Année scolaire')),
                ('eleve', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relances_impayes', to='school_admin.eleve', verbose_name='Élève')),
                ('enregistre_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='relances_impayes_envoyees', to='school_admin.compteuser')),
                ('etablissement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relances_impayes', to='school_admin.etablissement', verbose_name='Établissement')),
            ],
            options={
                'verbose_name': 'Relance impayé',
                'verbose_name_plural': 'Relances impayés',
                'ordering': ['-date_envoi'],
            },
        ),
        migrations.CreateModel(
            name='Moratoire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('motif', models.TextField(verbose_name='Motif')),
                ('montant_total', models.DecimalField(decimal_places=2, max_digits=12)),
                ('statut', models.CharField(choices=[('actif', 'Actif'), ('solde', 'Soldé'), ('rompu', 'Rompu'), ('annule', 'Annulé')], default='actif', max_length=20)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('date_rupture', models.DateTimeField(blank=True, null=True)),
                ('motif_rupture', models.CharField(blank=True, max_length=255)),
                ('annee_scolaire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moratoires', to='school_admin.anneescolaire', verbose_name='Année scolaire')),
                ('comptabilite_eleve', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moratoires', to='school_admin.comptabiliteeleve', verbose_name='Comptabilité élève')),
                ('cree_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moratoires_crees', to='school_admin.compteuser')),
                ('eleve', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moratoires', to='school_admin.eleve', verbose_name='Élève')),
                ('etablissement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moratoires', to='school_admin.etablissement', verbose_name='Établissement')),
            ],
            options={
                'verbose_name': 'Moratoire',
                'verbose_name_plural': 'Moratoires',
                'ordering': ['-date_creation'],
            },
        ),
        migrations.CreateModel(
            name='EcheanceMoratoire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.PositiveIntegerField(verbose_name="N° d'échéance")),
                ('date_echeance', models.DateField(verbose_name="Date d'échéance")),
                ('montant', models.DecimalField(decimal_places=2, max_digits=12)),
                ('montant_paye', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('statut', models.CharField(choices=[('en_attente', 'En attente'), ('paye', 'Payé'), ('en_retard', 'En retard'), ('impaye', 'Impayé')], default='en_attente', max_length=20)),
                ('date_paiement', models.DateTimeField(blank=True, null=True)),
                ('moratoire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='echeances', to='school_admin.moratoire', verbose_name='Moratoire')),
            ],
            options={
                'verbose_name': 'Échéance de moratoire',
                'verbose_name_plural': 'Échéances de moratoire',
                'ordering': ['numero'],
                'unique_together': {('moratoire', 'numero')},
            },
        ),
        migrations.AddIndex(
            model_name='relanceimpaye',
            index=models.Index(fields=['etablissement', 'date_envoi'], name='relance_etab_date_idx'),
        ),
        migrations.AddIndex(
            model_name='relanceimpaye',
            index=models.Index(fields=['eleve', 'annee_scolaire', 'date_envoi'], name='relance_eleve_annee_idx'),
        ),
        migrations.AddIndex(
            model_name='moratoire',
            index=models.Index(fields=['etablissement', 'statut'], name='moratoire_etab_statut_idx'),
        ),
        migrations.AddIndex(
            model_name='moratoire',
            index=models.Index(fields=['eleve', 'annee_scolaire', 'statut'], name='moratoire_eleve_annee_idx'),
        ),
    ]
