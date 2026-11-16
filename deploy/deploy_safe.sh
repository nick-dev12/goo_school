#!/usr/bin/env bash
# Déploiement reproductible : ./deploy.sh <commit-ou-tag>
set -euo pipefail
umask 077
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
if [ "$#" -ne 1 ]; then
    echo 'Usage: ./deploy.sh <commit-ou-tag>' >&2
    exit 2
fi
if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
    echo 'Déploiement refusé : répertoire modifié. Préserver et versionner les changements.' >&2
    exit 1
fi
source "${ARIA_VENV:-$PROJECT_DIR/venv}/bin/activate"
if [ -f /etc/aria/env ]; then
    set -a
    source /etc/aria/env
    set +a
fi
git fetch origin --tags
TARGET_COMMIT="$(git rev-parse --verify "${1}^{commit}")"
PREVIOUS_COMMIT="$(git rev-parse HEAD)"
BACKUP_DIR="${ARIA_BACKUP_DIR:-$PROJECT_DIR/../backups}/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
printf '%s\n' "$PREVIOUS_COMMIT" > "$BACKUP_DIR/previous-commit.txt"
python manage.py backup_production --output "$BACKUP_DIR"
# Aucune destruction des changements locaux, aucun --fake automatique.
git checkout --detach "$TARGET_COMMIT"
pip install -r requirements.txt
python manage.py check --deploy --fail-level WARNING
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py collectstatic --noinput
# « umask 077 » protège les sauvegardes, mais Nginx (www-data) doit pouvoir lire les fichiers statiques :
# sans cette ligne, les nouveaux dossiers et les copies .gz répondent 403.
chmod -R u=rwX,go=rX "${ARIA_STATIC_ROOT:-$PROJECT_DIR/staticfiles}"
sudo nginx -t
sudo systemctl restart aria-daphne aria-celery aria-celery-beat
sudo systemctl reload nginx
for service in aria-daphne aria-celery aria-celery-beat; do
    sudo systemctl is-active --quiet "$service"
done
# Daphne met quelques secondes à écouter après son redémarrage : on réessaie avant de conclure à un échec.
HEALTH_URL="${ARIA_HEALTH_URL:-https://aria-edu.com/health/ready/}"
for attempt in $(seq 1 12); do
    if curl --fail --silent --max-time 20 "$HEALTH_URL" >/dev/null; then
        break
    fi
    if [ "$attempt" -eq 12 ]; then
        echo "Le site ne répond pas correctement après redémarrage : $HEALTH_URL" >&2
        exit 1
    fi
    sleep 5
done
echo "Version $TARGET_COMMIT déployée. Sauvegarde : $BACKUP_DIR"
# En cas d'erreur, set -e arrête la livraison. Une base migrée doit être évaluée
# avant retour au code précédent ; ne jamais prétendre annuler une migration par git.
