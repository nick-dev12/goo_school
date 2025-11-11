"""Script autonome pour réinitialiser la soumission des moyennes primaires.

Usage:
    python scripts/reset_soumission_moyennes_primaire.py [--etablissement ID] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import django
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction


def configure_django() -> None:
    """Initialise l'environnement Django."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")
    try:
        django.setup()
    except ImproperlyConfigured as exc:  # pragma: no cover - erreur de configuration
        raise SystemExit(f"Configuration Django invalide : {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments CLI."""
    parser = argparse.ArgumentParser(
        description="Réinitialise la colonne 'soumis' des moyennes primaires."
    )
    parser.add_argument(
        "--etablissement",
        type=int,
        default=None,
        help="Identifiant d'établissement pour limiter la réinitialisation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le nombre d'enregistrements impactés sans écriture en base.",
    )
    return parser.parse_args(argv)


def reset_soumissions(etablissement_id: int | None = None, dry_run: bool = False) -> int:
    """Réinitialise le champ 'soumis' sur la table `MoyenneMatierePrimaire`.

    Args:
        etablissement_id: Identifiant d'établissement pour filtrer les moyennes.
        dry_run: Lorsque vrai, ne met pas à jour la base de données.

    Returns:
        int: Nombre d'enregistrements concernés.
    """
    from school_admin.model.note_primaire_model import MoyenneMatierePrimaire

    queryset = MoyenneMatierePrimaire.objects.filter(soumis=True)
    if etablissement_id is not None:
        queryset = queryset.filter(classe__etablissement_id=etablissement_id)

    total = queryset.count()
    if total == 0 or dry_run:
        return total

    with transaction.atomic():
        queryset.update(soumis=False, date_soumission=None)
    return total


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_django()

    total = reset_soumissions(args.etablissement, args.dry_run)

    if args.dry_run:
        msg = f"[DRY-RUN] {total} moyenne(s) serait(-ent) réinitialisée(s)."
    else:
        msg = f"{total} moyenne(s) réinitialisée(s)."

    if args.etablissement is not None:
        msg += f" Filtre établissement ID={args.etablissement}."

    print(msg)


if __name__ == "__main__":
    main(sys.argv[1:])

