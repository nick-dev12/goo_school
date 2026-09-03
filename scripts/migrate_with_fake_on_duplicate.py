"""Applique les migrations en contournant les doublons (colonnes/tables déjà existantes)."""
import re
import subprocess
import sys

MAX_ATTEMPTS = 250


def run_migrate():
    result = subprocess.run(
        [sys.executable, "manage.py", "migrate"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout + result.stderr


def extract_failed_migration(output: str) -> str | None:
    match = re.search(r"Applying school_admin\.(\S+)\.\.\.", output)
    if match:
        return match.group(1)
    return None


def fake_migration(name: str):
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "school_admin", name, "--fake"],
        check=True,
    )


def main():
    for attempt in range(1, MAX_ATTEMPTS + 1):
        code, output = run_migrate()
        safe_output = output.encode("utf-8", errors="replace").decode("utf-8")
        print(safe_output)
        if code == 0:
            print("\nToutes les migrations ont ete appliquees avec succes.")
            return 0

        if "DuplicateColumn" in output or "DuplicateTable" in output or "existe d" in output.lower():
            migration = extract_failed_migration(output)
            if not migration:
                print("Impossible d'identifier la migration en conflit.", file=sys.stderr)
                return 1
            print(f"\n>>> Conflit detecte : fake de school_admin.{migration} (tentative {attempt})\n")
            fake_migration(migration)
            continue

        print("Erreur de migration non geree.", file=sys.stderr)
        return code

    print(f"Nombre maximum de tentatives ({MAX_ATTEMPTS}) atteint.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
