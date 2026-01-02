"""
Commande Django pour supprimer toutes les données de comptabilité
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from school_admin.model.comptabilite_eleve_model import (
    ComptabiliteEleve, FraisInscription, Mensualite, PaiementEleve
)
from school_admin.model.parametres_comptabilite_model import ParametresComptabilite
from school_admin.model.parametres_comptabilite_groupe_classe_model import ParametresComptabiliteGroupeClasse


class Command(BaseCommand):
    help = 'Supprime toutes les données de comptabilité (paiements, mensualités, frais d\'inscription, comptabilités élèves, paramètres)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Exécuter sans confirmation',
        )
        parser.add_argument(
            '--garder-parametres',
            action='store_true',
            help='Garder les paramètres de comptabilité (ne supprime que les données)',
        )

    def handle(self, *args, **options):
        # Compter les données existantes
        nb_paiements = PaiementEleve.objects.count()
        nb_mensualites = Mensualite.objects.count()
        nb_frais_inscription = FraisInscription.objects.count()
        nb_comptabilites = ComptabiliteEleve.objects.count()
        nb_parametres = ParametresComptabilite.objects.count()
        nb_parametres_groupes = ParametresComptabiliteGroupeClasse.objects.count()
        
        total = nb_paiements + nb_mensualites + nb_frais_inscription + nb_comptabilites
        if not options['garder_parametres']:
            total += nb_parametres + nb_parametres_groupes
        
        # Afficher les statistiques
        self.stdout.write(
            self.style.WARNING(
                '\n' + '='*70 + '\n'
                'SUPPRESSION DES DONNÉES DE COMPTABILITÉ\n'
                '='*70 + '\n'
            )
        )
        
        self.stdout.write(f'Nombre de paiements à supprimer: {nb_paiements}')
        self.stdout.write(f'Nombre de mensualités à supprimer: {nb_mensualites}')
        self.stdout.write(f'Nombre de frais d\'inscription à supprimer: {nb_frais_inscription}')
        self.stdout.write(f'Nombre de comptabilités élèves à supprimer: {nb_comptabilites}')
        
        if options['garder_parametres']:
            self.stdout.write(self.style.SUCCESS(f'Paramètres de comptabilité généraux: {nb_parametres} (seront conservés)'))
            self.stdout.write(self.style.SUCCESS(f'Paramètres de comptabilité par groupe: {nb_parametres_groupes} (seront conservés)'))
        else:
            self.stdout.write(f'Nombre de paramètres généraux à supprimer: {nb_parametres}')
            self.stdout.write(f'Nombre de paramètres par groupe à supprimer: {nb_parametres_groupes}')
        
        self.stdout.write(f'\nTOTAL: {total} enregistrements seront supprimés\n')
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Aucune donnée de comptabilité à supprimer.'))
            return
        
        # Demander confirmation si pas de --force
        if not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    '\n' + '='*70 + '\n'
                    'ATTENTION: Cette opération est IRRÉVERSIBLE!\n'
                    'Toutes les données de comptabilité seront définitivement supprimées.\n'
                    '='*70 + '\n'
                )
            )
            confirm = input('Êtes-vous sûr de vouloir continuer? (oui/non): ')
            if confirm.lower() not in ['oui', 'o', 'yes', 'y']:
                self.stdout.write(self.style.ERROR('Opération annulée.'))
                return
        
        # Supprimer les données dans l'ordre correct (en respectant les dépendances)
        try:
            with transaction.atomic():
                # 1. Supprimer les paiements (dépendent de FraisInscription et Mensualite)
                if nb_paiements > 0:
                    self.stdout.write(f'\nSuppression de {nb_paiements} paiement(s)...')
                    deleted = PaiementEleve.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK] {deleted[0]} paiement(s) supprime(s)'
                        )
                    )
                
                # 2. Supprimer les mensualités (dépendent de ComptabiliteEleve)
                if nb_mensualites > 0:
                    self.stdout.write(f'\nSuppression de {nb_mensualites} mensualite(s)...')
                    deleted = Mensualite.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK] {deleted[0]} mensualite(s) supprimee(s)'
                        )
                    )
                
                # 3. Supprimer les frais d'inscription (dépendent de ComptabiliteEleve)
                if nb_frais_inscription > 0:
                    self.stdout.write(f'\nSuppression de {nb_frais_inscription} frais d\'inscription...')
                    deleted = FraisInscription.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK] {deleted[0]} frais d\'inscription supprime(s)'
                        )
                    )
                
                # 4. Supprimer les comptabilités élèves
                if nb_comptabilites > 0:
                    self.stdout.write(f'\nSuppression de {nb_comptabilites} comptabilite(s) eleve(s)...')
                    deleted = ComptabiliteEleve.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK] {deleted[0]} comptabilite(s) eleve(s) supprimee(s)'
                        )
                    )
                
                # 5. Supprimer les paramètres par groupe de classes (optionnel)
                if not options['garder_parametres'] and nb_parametres_groupes > 0:
                    self.stdout.write(f'\nSuppression de {nb_parametres_groupes} parametre(s) de comptabilite par groupe...')
                    deleted = ParametresComptabiliteGroupeClasse.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK] {deleted[0]} parametre(s) par groupe supprime(s)'
                        )
                    )
                elif options['garder_parametres'] and nb_parametres_groupes > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\n[OK] {nb_parametres_groupes} parametre(s) par groupe conserve(s)'
                        )
                    )
                
                # 6. Supprimer les paramètres généraux (optionnel)
                if not options['garder_parametres'] and nb_parametres > 0:
                    self.stdout.write(f'\nSuppression de {nb_parametres} parametre(s) de comptabilite general(aux)...')
                    deleted = ParametresComptabilite.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK] {deleted[0]} parametre(s) general(aux) supprime(s)'
                        )
                    )
                elif options['garder_parametres'] and nb_parametres > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\n[OK] {nb_parametres} parametre(s) general(aux) conserve(s)'
                        )
                    )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        '\n' + '='*70 + '\n'
                        '[OK] Suppression terminee avec succes!\n'
                        '='*70 + '\n'
                    )
                )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'\nErreur lors de la suppression: {str(e)}\n'
                    'La transaction a été annulée. Aucune donnée n\'a été supprimée.'
                )
            )
            raise

