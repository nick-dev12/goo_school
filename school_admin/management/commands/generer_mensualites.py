# school_admin/management/commands/generer_mensualites.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from calendar import monthrange
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.eleve_model import Eleve
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve, Mensualite


class Command(BaseCommand):
    help = 'Génère automatiquement les mensualités pour les établissements privés pour le mois en cours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mois',
            type=int,
            help='Mois à générer (1-12). Par défaut, le mois en cours',
        )
        parser.add_argument(
            '--annee',
            type=int,
            help='Année à générer. Par défaut, l\'année en cours',
        )
        parser.add_argument(
            '--etablissement',
            type=int,
            help='ID de l\'établissement spécifique (optionnel)',
        )

    def handle(self, *args, **options):
        maintenant = timezone.now()
        mois = options.get('mois') or maintenant.month
        annee = options.get('annee') or maintenant.year
        etablissement_id = options.get('etablissement')

        # Validation du mois
        if mois < 1 or mois > 12:
            self.stdout.write(
                self.style.ERROR(f'Mois invalide : {mois}. Le mois doit être entre 1 et 12.')
            )
            return

        # Récupérer les établissements privés
        etablissements_query = Etablissement.objects.filter(
            type_etablissement_comptabilite='prive',
            actif=True,
            module_comptabilite=True
        )

        if etablissement_id:
            etablissements_query = etablissements_query.filter(id=etablissement_id)

        etablissements = etablissements_query.all()

        if not etablissements.exists():
            self.stdout.write(
                self.style.WARNING('Aucun établissement privé avec module comptabilité activé trouvé.')
            )
            return

        total_mensualites_creees = 0
        total_eleves_traites = 0

        # Noms des mois en français
        noms_mois = [
            '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]

        periode = f"{noms_mois[mois]} {annee}"

        # Calculer la date d'échéance (fin du mois)
        dernier_jour_mois = monthrange(annee, mois)[1]
        date_echeance = datetime(annee, mois, dernier_jour_mois).date()

        self.stdout.write(
            self.style.SUCCESS(f'Génération des mensualités pour {periode} (échéance: {date_echeance})')
        )

        for etablissement in etablissements:
            # Vérifier que l'établissement a un montant de mensualité configuré
            if not etablissement.montant_mensualite:
                self.stdout.write(
                    self.style.WARNING(
                        f'Établissement {etablissement.nom} : montant de mensualité non configuré. Ignoré.'
                    )
                )
                continue

            # Récupérer l'année scolaire active
            annee_scolaire_active = AnneeScolaire.get_session_active(etablissement)
            if not annee_scolaire_active:
                self.stdout.write(
                    self.style.WARNING(
                        f'Établissement {etablissement.nom} : aucune année scolaire active trouvée. Ignoré.'
                    )
                )
                continue

            # Vérifier que le mois est dans la période de l'année scolaire
            date_debut_mois = datetime(annee, mois, 1).date()
            if not (annee_scolaire_active.date_debut <= date_debut_mois <= annee_scolaire_active.date_fin):
                self.stdout.write(
                    self.style.WARNING(
                        f'Établissement {etablissement.nom} : le mois {mois}/{annee} n\'est pas dans la période '
                        f'de l\'année scolaire {annee_scolaire_active.libelle}. Ignoré.'
                    )
                )
                continue

            # Récupérer tous les élèves actifs de l'établissement
            eleves = Eleve.objects.filter(
                etablissement=etablissement,
                actif=True
            ).all()

            mensualites_etablissement = 0

            for eleve in eleves:
                total_eleves_traites += 1

                # Vérifier si une mensualité existe déjà pour ce mois/année
                mensualite_existante = Mensualite.objects.filter(
                    eleve=eleve,
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active,
                    mois=mois,
                    annee=annee
                ).first()

                if mensualite_existante:
                    continue  # Mensualité déjà générée

                # Récupérer ou créer la comptabilité de l'élève
                comptabilite_eleve, created = ComptabiliteEleve.objects.get_or_create(
                    eleve=eleve,
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active,
                    defaults={
                        'statut_paiement': 'a_jour'
                    }
                )

                # Créer la mensualité
                mensualite = Mensualite.objects.create(
                    eleve=eleve,
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active,
                    comptabilite_eleve=comptabilite_eleve,
                    mois=mois,
                    annee=annee,
                    montant=etablissement.montant_mensualite,
                    date_echeance=date_echeance,
                    periode=periode,
                    statut='en_attente'
                )

                mensualites_etablissement += 1
                total_mensualites_creees += 1

            if mensualites_etablissement > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Établissement {etablissement.nom} : {mensualites_etablissement} mensualité(s) créée(s)'
                    )
                )

        # Résumé
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Génération terminée : {total_mensualites_creees} mensualité(s) créée(s) '
                f'pour {total_eleves_traites} élève(s) dans {etablissements.count()} établissement(s)'
            )
        )

