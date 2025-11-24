# school_admin/management/commands/associer_annee_scolaire_donnees.py

from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.utils import timezone
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.eleve_model import Eleve
from school_admin.model.evaluation_model import Evaluation, Note
from school_admin.model.moyenne_model import Moyenne
from school_admin.model.presence_model import Presence
from school_admin.model.annonce_model import Annonce
from school_admin.model.convocation_model import Convocation
from school_admin.model.creneau_examen_model import CreneauExamen
from school_admin.model.emploi_du_temps_model import EmploiDuTemps


class Command(BaseCommand):
    help = 'Associe une année scolaire à toutes les données existantes d\'un établissement'

    def add_arguments(self, parser):
        parser.add_argument(
            '--etablissement-id',
            type=int,
            default=34,
            help='ID de l\'établissement (défaut: 34)',
        )
        parser.add_argument(
            '--annee-scolaire-id',
            type=int,
            default=1,
            help='ID de l\'année scolaire (défaut: 1)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mode simulation : affiche ce qui sera fait sans modifier la base',
        )

    def handle(self, *args, **options):
        etablissement_id = options['etablissement_id']
        annee_scolaire_id = options['annee_scolaire_id']
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Association année scolaire aux données existantes'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n[!] MODE SIMULATION - Aucune modification ne sera effectuee\n'))
        
        # Récupérer l'établissement
        try:
            etablissement = Etablissement.objects.get(pk=etablissement_id)
            self.stdout.write(f'Établissement: {etablissement.nom} (ID: {etablissement_id})')
        except Etablissement.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'[ERREUR] Etablissement avec ID {etablissement_id} introuvable'))
            return
        
        # Récupérer l'année scolaire
        try:
            annee_scolaire = AnneeScolaire.objects.get(pk=annee_scolaire_id, etablissement=etablissement)
            self.stdout.write(f'Annee scolaire: {annee_scolaire.libelle} (ID: {annee_scolaire_id})')
            self.stdout.write(f'Periode: {annee_scolaire.date_debut} - {annee_scolaire.date_fin}\n')
        except AnneeScolaire.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'[ERREUR] Annee scolaire avec ID {annee_scolaire_id} introuvable pour cet etablissement'))
            return
        
        stats = {
            'total': 0,
            'modifies': 0,
            'erreurs': 0
        }
        
        try:
            with transaction.atomic():
                # 1. Evaluations
                self.stdout.write('\n[1] Traitement des Evaluations...')
                evaluations = Evaluation.objects.filter(
                    classe__etablissement=etablissement,
                    annee_scolaire__isnull=True
                )
                count = evaluations.count()
                stats['total'] += count
                if count > 0:
                    if not dry_run:
                        updated = evaluations.update(annee_scolaire=annee_scolaire)
                        stats['modifies'] += updated
                        self.stdout.write(self.style.SUCCESS(f'  [+] {updated} evaluation(s) associee(s)'))
                    else:
                        self.stdout.write(self.style.WARNING(f'  [SIMULATION] {count} evaluation(s) seraient associee(s)'))
                else:
                    self.stdout.write('  [i] Aucune evaluation a traiter')
                
                # 2. Notes
                self.stdout.write('\n[2] Traitement des Notes...')
                notes = Note.objects.filter(
                    eleve__etablissement=etablissement,
                    annee_scolaire__isnull=True
                )
                count = notes.count()
                stats['total'] += count
                if count > 0:
                    if not dry_run:
                        updated = notes.update(annee_scolaire=annee_scolaire)
                        stats['modifies'] += updated
                        self.stdout.write(self.style.SUCCESS(f'  [+] {updated} note(s) associee(s)'))
                    else:
                        self.stdout.write(self.style.WARNING(f'  [SIMULATION] {count} note(s) seraient associee(s)'))
                else:
                    self.stdout.write('  [i] Aucune note a traiter')
                
                # 3. Moyennes
                self.stdout.write('\n[3] Traitement des Moyennes...')
                moyennes = Moyenne.objects.filter(
                    eleve__etablissement=etablissement,
                    annee_scolaire__isnull=True
                )
                count = moyennes.count()
                stats['total'] += count
                if count > 0:
                    if not dry_run:
                        updated = moyennes.update(annee_scolaire=annee_scolaire)
                        stats['modifies'] += updated
                        self.stdout.write(self.style.SUCCESS(f'  [+] {updated} moyenne(s) associee(s)'))
                    else:
                        self.stdout.write(self.style.WARNING(f'  [SIMULATION] {count} moyenne(s) seraient associee(s)'))
                else:
                    self.stdout.write('  [i] Aucune moyenne a traiter')
                
                # 4. Presences
                self.stdout.write('\n[4] Traitement des Presences...')
                presences = Presence.objects.filter(
                    etablissement=etablissement,
                    annee_scolaire__isnull=True
                )
                count = presences.count()
                stats['total'] += count
                if count > 0:
                    if not dry_run:
                        updated = presences.update(annee_scolaire=annee_scolaire)
                        stats['modifies'] += updated
                        self.stdout.write(self.style.SUCCESS(f'  [+] {updated} presence(s) associee(s)'))
                    else:
                        self.stdout.write(self.style.WARNING(f'  [SIMULATION] {count} presence(s) seraient associee(s)'))
                else:
                    self.stdout.write('  [i] Aucune presence a traiter')
                
                # 5. Eleves (base sur date_inscription)
                self.stdout.write('\n[5] Traitement des Eleves...')
                eleves = Eleve.objects.filter(
                    etablissement=etablissement,
                    date_inscription__gte=annee_scolaire.date_debut,
                    date_inscription__lte=annee_scolaire.date_fin
                )
                count = eleves.count()
                self.stdout.write(f'  [i] {count} eleve(s) inscrit(s) pendant cette annee scolaire')
                # Note: Eleve n'a pas de ForeignKey annee_scolaire, donc on ne peut pas l'associer directement
                # Si besoin, il faudrait creer un modele InscriptionEleve ou ajouter le champ
                
                # 6. EmploiDuTemps (mise a jour du champ CharField annee_scolaire)
                self.stdout.write('\n[6] Traitement des Emplois du Temps...')
                from django.db.models import Q
                emplois = EmploiDuTemps.objects.filter(
                    classe__etablissement=etablissement
                ).exclude(annee_scolaire=annee_scolaire.libelle)
                count = emplois.count()
                stats['total'] += count
                if count > 0:
                    if not dry_run:
                        updated = emplois.update(annee_scolaire=annee_scolaire.libelle)
                        stats['modifies'] += updated
                        self.stdout.write(self.style.SUCCESS(f'  [+] {updated} emploi(s) du temps mis a jour'))
                    else:
                        self.stdout.write(self.style.WARNING(f'  [SIMULATION] {count} emploi(s) du temps seraient mis a jour'))
                else:
                    self.stdout.write('  [i] Aucun emploi du temps a traiter')
                
                # 7. Convocations (base sur date_convocation)
                self.stdout.write('\n[7] Traitement des Convocations...')
                convocations = Convocation.objects.filter(
                    etablissement=etablissement,
                    date_convocation__gte=annee_scolaire.date_debut,
                    date_convocation__lte=annee_scolaire.date_fin
                )
                count = convocations.count()
                self.stdout.write(f'  [i] {count} convocation(s) pendant cette annee scolaire')
                # Note: Convocation n'a pas de ForeignKey annee_scolaire
                
                # 8. Creneaux d'examens (base sur date_examen)
                self.stdout.write('\n[8] Traitement des Creneaux d\'Examens...')
                creneaux = CreneauExamen.objects.filter(
                    session_examen__etablissement=etablissement,
                    date_examen__gte=annee_scolaire.date_debut,
                    date_examen__lte=annee_scolaire.date_fin
                )
                count = creneaux.count()
                self.stdout.write(f'  [i] {count} creneau(x) d\'examen pendant cette annee scolaire')
                # Note: CreneauExamen n'a pas de ForeignKey annee_scolaire
                
                # 9. Annonces (base sur date_creation)
                self.stdout.write('\n[9] Traitement des Annonces...')
                annonces = Annonce.objects.filter(
                    etablissement=etablissement,
                    date_creation__date__gte=annee_scolaire.date_debut,
                    date_creation__date__lte=annee_scolaire.date_fin
                )
                count = annonces.count()
                self.stdout.write(f'  [i] {count} annonce(s) creee(s) pendant cette annee scolaire')
                # Note: Annonce n'a pas de ForeignKey annee_scolaire
                
                if dry_run:
                    # En mode dry-run, on annule la transaction
                    raise Exception("Mode simulation - transaction annulee")
                
        except Exception as e:
            if dry_run:
                self.stdout.write(self.style.WARNING(f'\n[!] Mode simulation termine (transaction annulee)'))
            else:
                self.stdout.write(self.style.ERROR(f'\n[ERREUR] {str(e)}'))
                stats['erreurs'] += 1
                raise
        
        # Resume
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('RESUME'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'Total d\'enregistrements traites: {stats["total"]}')
        self.stdout.write(f'Enregistrements modifies: {stats["modifies"]}')
        if stats['erreurs'] > 0:
            self.stdout.write(self.style.ERROR(f'Erreurs: {stats["erreurs"]}'))
        else:
            self.stdout.write(self.style.SUCCESS('[OK] Operation terminee avec succes!'))

