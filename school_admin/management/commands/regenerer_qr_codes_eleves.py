"""
Commande Django pour régénérer tous les QR codes des élèves
avec les nouveaux paramètres optimisés pour le scan
"""

import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from school_admin.model.eleve_model import Eleve


class Command(BaseCommand):
    help = 'Régénère tous les QR codes des élèves avec les nouveaux paramètres optimisés pour le scan'

    def add_arguments(self, parser):
        parser.add_argument(
            '--etablissement',
            type=int,
            help='ID de l\'établissement pour lequel régénérer les QR codes (optionnel)',
        )
        parser.add_argument(
            '--actifs-seulement',
            action='store_true',
            help='Régénérer uniquement les QR codes des élèves actifs',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Régénérer même si le QR code existe déjà',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Nombre d\'élèves à traiter par batch (défaut: 100)',
        )

    def handle(self, *args, **options):
        # Afficher l'en-tête
        self.stdout.write(
            self.style.SUCCESS(
                '\n' + '='*70 + '\n'
                'RÉGÉNÉRATION DES QR CODES DES ÉLÈVES\n'
                '='*70 + '\n'
            )
        )
        
        # Construire le queryset
        queryset = Eleve.objects.all()
        
        # Filtrer par établissement si spécifié
        if options['etablissement']:
            queryset = queryset.filter(etablissement_id=options['etablissement'])
            self.stdout.write(
                self.style.WARNING(f'Filtrage par établissement ID: {options["etablissement"]}')
            )
        
        # Filtrer uniquement les actifs si demandé
        if options['actifs_seulement']:
            queryset = queryset.filter(actif=True)
            self.stdout.write(self.style.WARNING('Filtrage: élèves actifs uniquement'))
        
        # Compter les élèves à traiter
        total_eleves = queryset.count()
        
        if total_eleves == 0:
            self.stdout.write(
                self.style.ERROR('Aucun élève trouvé avec les critères spécifiés.')
            )
            return
        
        # Afficher les statistiques
        self.stdout.write(
            f'\nNombre total d\'élèves à traiter: {self.style.SUCCESS(str(total_eleves))}'
        )
        
        # Demander confirmation si pas de --force
        if not options['force']:
            confirm = input(
                '\nVoulez-vous continuer ? Cette opération peut prendre du temps. (oui/non): '
            )
            if confirm.lower() not in ['oui', 'o', 'yes', 'y']:
                self.stdout.write(self.style.WARNING('Opération annulée.'))
                return
        
        # Traitement par batch
        batch_size = options['batch_size']
        total_success = 0
        total_errors = 0
        errors_list = []
        
        self.stdout.write(f'\nTraitement par batch de {batch_size} élèves...\n')
        
        # Traiter les élèves par batch
        for offset in range(0, total_eleves, batch_size):
            batch = queryset[offset:offset + batch_size]
            batch_num = (offset // batch_size) + 1
            total_batches = (total_eleves + batch_size - 1) // batch_size
            
            self.stdout.write(
                f'\n[{batch_num}/{total_batches}] Traitement du batch {batch_num} '
                f'(élèves {offset + 1} à {min(offset + batch_size, total_eleves)})...'
            )
            
            for eleve in batch:
                try:
                    # Vérifier si le QR code existe déjà (sauf si --force)
                    if not options['force'] and eleve.qr_code_image and eleve.qr_code_identifier:
                        # Vérifier si l'image existe vraiment
                        from django.core.files.storage import default_storage
                        if default_storage.exists(eleve.qr_code_image.name):
                            self.stdout.write(
                                f'  [SKIP] {eleve.nom_complet} (ID: {eleve.pk}) - QR code existe deja, ignore'
                            )
                            continue
                    
                    # Sauvegarder l'ancien chemin pour suppression ultérieure
                    ancien_chemin = None
                    if eleve.qr_code_image:
                        ancien_chemin = eleve.qr_code_image.name
                    
                    # Générer un nouvel identifiant QR si nécessaire ou si --force
                    if not eleve.qr_code_identifier or options['force']:
                        import uuid
                        eleve.qr_code_identifier = str(uuid.uuid4())
                    
                    # Supprimer l'ancienne image si --force
                    if options['force'] and ancien_chemin:
                        from django.core.files.storage import default_storage
                        try:
                            if default_storage.exists(ancien_chemin):
                                default_storage.delete(ancien_chemin)
                        except Exception as del_error:
                            # Logger l'erreur mais continuer
                            self.stdout.write(
                                self.style.WARNING(
                                    f'  [WARN] Impossible de supprimer l\'ancienne image: {str(del_error)}'
                                )
                            )
                    
                    # Réinitialiser l'image pour forcer la régénération
                    if options['force']:
                        eleve.qr_code_image = None
                    
                    # Sauvegarder pour déclencher la régénération du QR code
                    # La méthode save() du modèle va automatiquement régénérer le QR code
                    eleve.save()
                    
                    total_success += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  [OK] {eleve.nom_complet} (ID: {eleve.pk}) - QR code regenere'
                        )
                    )
                    
                except Exception as e:
                    total_errors += 1
                    error_msg = f'  [ERROR] {eleve.nom_complet} (ID: {eleve.pk}) - Erreur: {str(e)}'
                    errors_list.append(error_msg)
                    self.stdout.write(
                        self.style.ERROR(error_msg)
                    )
            
            # Afficher la progression
            progress = ((offset + len(batch)) / total_eleves) * 100
            self.stdout.write(
                f'\n  Progression: {progress:.1f}% ({offset + len(batch)}/{total_eleves})'
            )
        
        # Afficher le résumé final
        self.stdout.write(
            self.style.SUCCESS(
                '\n' + '='*70 + '\n'
                'RÉSUMÉ DE LA RÉGÉNÉRATION\n'
                '='*70 + '\n'
            )
        )
        
        self.stdout.write(
            f'Total d\'élèves traités: {self.style.SUCCESS(str(total_eleves))}'
        )
        self.stdout.write(
            f'QR codes régénérés avec succès: {self.style.SUCCESS(str(total_success))}'
        )
        
        if total_errors > 0:
            self.stdout.write(
                f'Erreurs rencontrées: {self.style.ERROR(str(total_errors))}'
            )
            self.stdout.write(
                self.style.WARNING('\nDétails des erreurs:')
            )
            for error in errors_list:
                self.stdout.write(self.style.ERROR(f'  {error}'))
        else:
            self.stdout.write(
                self.style.SUCCESS('\n[SUCCESS] Tous les QR codes ont ete regeneres avec succes!')
            )
        
        self.stdout.write('\n' + '='*70 + '\n')
        
        # Afficher des informations sur les nouveaux paramètres
        self.stdout.write(
            self.style.SUCCESS(
                '\nNouveaux paramètres du QR code:\n'
                '  - Taille des points (box_size): 15 (augmenté de 10)\n'
                '  - Bordure (border): 3 (optimisée)\n'
                '  - Correction d\'erreur: ERROR_CORRECT_H (haute robustesse)\n'
                '  - Format: URL vers la page de scan\n'
            )
        )

