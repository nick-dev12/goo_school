"""Renumérote le plan PCG / ancien SYSCOHADA vers le PCE §3.2 (dry-run par défaut)."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from school_admin.model.etablissement_model import Etablissement
from school_admin.services.comptabilite_generale import (
    backfill_creances_ouvertes,
    migrer_plan_syscohada,
    snapshot_soldes,
)


class Command(BaseCommand):
    help = (
        "Aligne le plan de comptes SYSCOHADA révisé (531→571, 512→521, 701→705x…). "
        "Dry-run par défaut. --apply pour écrire. --backup pour un JSON des soldes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help="Exécute la renumérotation (sinon dry-run).",
        )
        parser.add_argument(
            '--backup',
            action='store_true',
            help="Écrit un JSON des soldes avant migration dans tmp/.",
        )
        parser.add_argument(
            '--backfill-411',
            action='store_true',
            help="Après le remap, émet D 411 / C 70x pour les créances ouvertes (reste seulement).",
        )
        parser.add_argument(
            '--etablissement-id',
            type=int,
            default=None,
            help="Limiter à un établissement.",
        )

    def handle(self, *args, **options):
        dry_run = not options['apply']
        qs = Etablissement.objects.all().order_by('id')
        if options['etablissement_id']:
            qs = qs.filter(pk=options['etablissement_id'])
            if not qs.exists():
                raise CommandError("Établissement introuvable.")

        rapport = []
        for etab in qs:
            avant = snapshot_soldes(etab)
            if options['backup']:
                dossier = Path('tmp')
                dossier.mkdir(exist_ok=True)
                chemin = dossier / f"pce-backup-{etab.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}.json"
                chemin.write_text(
                    json.dumps({k: str(v) for k, v in avant.items()}, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
                self.stdout.write(f"Backup soldes {etab.nom}: {chemin}")

            resultat = migrer_plan_syscohada(etab, dry_run=dry_run)
            backfill = None
            if options['backfill_411'] and not dry_run:
                backfill = backfill_creances_ouvertes(etab, dry_run=False)
            elif options['backfill_411'] and dry_run:
                backfill = backfill_creances_ouvertes(etab, dry_run=True)

            ligne = {
                'etablissement': etab.nom,
                'id': etab.id,
                'dry_run': dry_run,
                'soldes_identiques': resultat['soldes_identiques'],
                'actions': resultat['actions'],
                'comptes_crees': resultat['comptes_crees'],
                'backfill': backfill,
            }
            rapport.append(ligne)
            etat = 'OK' if resultat['soldes_identiques'] else 'ECART SOLDES'
            self.stdout.write(
                f"{etat} {etab.nom} (#{etab.id}) — {len(resultat['actions'])} remap, "
                f"{resultat['comptes_crees']} comptes créés"
            )
            if backfill:
                self.stdout.write(
                    f"  411 backfill: {backfill['emises']} émises, {backfill['ignorees']} ignorées"
                )

        mode = 'DRY-RUN' if dry_run else 'APPLIQUÉ'
        self.stdout.write(self.style.SUCCESS(f"{mode} — {len(rapport)} établissement(s)."))
        if dry_run:
            self.stdout.write("Relancer avec --apply pour écrire, --backup pour un JSON de soldes.")
