"""Commande de gestion pour réinitialiser les soumissions de notes."""

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from school_admin.model.releve_notes_model import ReleveNotes
from school_admin.model.note_primaire_model import MoyenneMatierePrimaire
from school_admin.model.moyenne_model import Moyenne
from school_admin.model.note_examen_model import NoteExamen


class Command(BaseCommand):
    help = (
        "Réinitialise les indicateurs de soumission des notes :\n"
        "  - Relevés de notes (ReleveNotes.soumis/date_soumission)\n"
        "  - Moyennes primaires (MoyenneMatierePrimaire.soumis/date_soumission)\n"
        "  - Moyennes secondaires (Moyenne.soumis)\n"
        "  - Notes d'examen (NoteExamen.soumis/date_soumission)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Affiche le nombre d'enregistrements impactés sans effectuer de modification",
        )
        parser.add_argument(
            '--etablissement',
            type=int,
            default=None,
            help="Identifiant d'établissement pour limiter l'action",
        )

    def _filter_queryset(self, queryset, etablissement_id):
        if etablissement_id is None:
            return queryset
        if hasattr(queryset.model, 'etablissement_id'):
            return queryset.filter(etablissement_id=etablissement_id)
        if queryset.model is Moyenne:
            return queryset.filter(classe__etablissement_id=etablissement_id)
        if queryset.model is NoteExamen:
            return queryset.filter(etablissement_id=etablissement_id)
        raise CommandError(
            f"Impossible de filtrer {queryset.model.__name__} par 'etablissement'."
        )

    def _reset_queryset(self, queryset, fields_to_update, dry_run):
        total = queryset.count()
        if dry_run or total == 0:
            return total
        queryset.update(**fields_to_update)
        return total

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        etablissement_id = options['etablissement']

        if dry_run:
            self.stdout.write(self.style.WARNING('Mode simulation activé (dry-run). Aucune écriture.'))

        if etablissement_id is not None:
            self.stdout.write(f"Filtre sur l'établissement ID = {etablissement_id}")

        try:
            with transaction.atomic():
                total_releves = self._reset_queryset(
                    self._filter_queryset(ReleveNotes.objects.filter(soumis=True), etablissement_id),
                    {'soumis': False, 'date_soumission': None},
                    dry_run,
                )

                total_primaires = self._reset_queryset(
                    self._filter_queryset(MoyenneMatierePrimaire.objects.filter(soumis=True), etablissement_id),
                    {'soumis': False, 'date_soumission': None},
                    dry_run,
                )

                total_secondaire = self._reset_queryset(
                    self._filter_queryset(Moyenne.objects.filter(soumis=True), etablissement_id),
                    {'soumis': False},
                    dry_run,
                )

                total_examens = self._reset_queryset(
                    self._filter_queryset(NoteExamen.objects.filter(soumis=True), etablissement_id),
                    {'soumis': False, 'date_soumission': None},
                    dry_run,
                )

                self.stdout.write(self.style.SUCCESS('Résumé de la réinitialisation :'))
                self.stdout.write(f"  - Relevés de notes remis en brouillon : {total_releves}")
                self.stdout.write(f"  - Moyennes primaires réinitialisées : {total_primaires}")
                self.stdout.write(f"  - Moyennes collège/lycée réinitialisées : {total_secondaire}")
                self.stdout.write(f"  - Notes d'examen réinitialisées : {total_examens}")

                total = total_releves + total_primaires + total_secondaire + total_examens

                if dry_run:
                    self.stdout.write(self.style.WARNING('\nSimulation terminée. Aucune donnée modifiée.'))
                else:
                    self.stdout.write(self.style.SUCCESS(f"\nRéinitialisation effectuée avec succès ({total} enregistrements)."))

                if dry_run:
                    transaction.set_rollback(True)

        except Exception as exc:
            raise CommandError(f"Erreur pendant la réinitialisation : {exc}") from exc
