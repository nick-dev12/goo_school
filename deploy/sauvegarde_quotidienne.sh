#!/usr/bin/env bash
# Sauvegarde quotidienne chiffrée de la base et des fichiers déposés.
# Lancée chaque nuit par le minuteur systemd aria-sauvegarde.timer (installé par durcir_serveur_lot4.sh).
#
# - base PostgreSQL + media/ (commande backup_production), réunis puis chiffrés (GPG, AES-256) ;
# - la clé de chiffrement est dans /etc/aria/sauvegarde.cle : EN GARDER UNE COPIE HORS DU SERVEUR,
#   sans elle les sauvegardes sont illisibles ;
# - 14 sauvegardes quotidiennes conservées sur le serveur ;
# - copie hors du serveur si ARIA_SAUVEGARDE_DISTANTE est défini dans /etc/aria/env :
#   « distant:chemin » pour rclone (si installé), sinon une cible rsync « utilisateur@hote:/chemin ».
set -euo pipefail
umask 077

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RACINE="${ARIA_SAUVEGARDE_DIR:-$PROJECT_DIR/../backups/quotidien}"
CLE="${ARIA_SAUVEGARDE_CLE:-/etc/aria/sauvegarde.cle}"
GARDER="${ARIA_SAUVEGARDE_JOURS:-14}"

cd "$PROJECT_DIR"
source "${ARIA_VENV:-$PROJECT_DIR/venv}/bin/activate"
if [ -f /etc/aria/env ]; then
    set -a
    source /etc/aria/env
    set +a
fi
[ -r "$CLE" ] || { echo "Clé de chiffrement illisible : $CLE" >&2; exit 1; }

mkdir -p "$RACINE"
HORODATAGE="$(date -u +%Y%m%dT%H%M%SZ)"
TRAVAIL="$(mktemp -d "$RACINE/.en-cours-XXXXXX")"
trap 'rm -rf "$TRAVAIL"' EXIT

python manage.py backup_production --output "$TRAVAIL/aria-$HORODATAGE" >/dev/null
git rev-parse HEAD > "$TRAVAIL/aria-$HORODATAGE/version.txt"

ARCHIVE="$RACINE/aria-$HORODATAGE.tar.gpg"
tar -C "$TRAVAIL" -cf - "aria-$HORODATAGE" \
    | gpg --batch --yes --quiet --symmetric --cipher-algo AES256 --passphrase-file "$CLE" -o "$ARCHIVE"
# Contrôle : l'archive se déchiffre et se relit.
gpg --batch --quiet --decrypt --passphrase-file "$CLE" "$ARCHIVE" | tar -tf - >/dev/null

# Rotation : on garde les GARDER plus récentes.
ls -1t "$RACINE"/aria-*.tar.gpg 2>/dev/null | tail -n +"$((GARDER + 1))" | xargs -r rm -f

if [ -n "${ARIA_SAUVEGARDE_DISTANTE:-}" ]; then
    if command -v rclone >/dev/null 2>&1 && [[ "$ARIA_SAUVEGARDE_DISTANTE" != *@* ]]; then
        rclone copy "$ARCHIVE" "$ARIA_SAUVEGARDE_DISTANTE"
    else
        rsync -a "$ARCHIVE" "$ARIA_SAUVEGARDE_DISTANTE/"
    fi
    echo "Sauvegarde copiée hors du serveur."
else
    echo "ATTENTION : aucune copie hors du serveur (ARIA_SAUVEGARDE_DISTANTE non défini)." >&2
fi
echo "Sauvegarde chiffrée : $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
