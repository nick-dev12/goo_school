#!/usr/bin/env bash
# Fichiers déposés (media/) : seuls les logos restent servis directement par Nginx ; tout le reste passe
# par l'application, qui vérifie les droits puis rend la main à Nginx (X-Accel-Redirect, emplacement interne).
# À lancer APRÈS avoir déployé la version qui contient la vue servir_media :
#     sudo bash deploy/configurer_nginx_media.sh
# Sans risque à relancer. En cas d'erreur de syntaxe Nginx, l'ancienne configuration est restaurée.
set -euo pipefail

CONF="${ARIA_NGINX_CONF:-/etc/nginx/sites-available/aria-edu}"
MEDIA_ROOT="${ARIA_MEDIA_ROOT:-/home/nick/aria/goo_school/media}"

if [ "$(id -u)" -ne 0 ]; then
    echo "À lancer avec sudo." >&2
    exit 2
fi
[ -f "$CONF" ] || { echo "Configuration introuvable : $CONF" >&2; exit 1; }

if grep -q 'location /protected-media/' "$CONF"; then
    echo "Déjà configuré."
    exit 0
fi

BACKUP="$CONF.bak-$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$CONF" "$BACKUP"

python3 - "$CONF" "$MEDIA_ROOT" <<'PYEOF'
import re
import sys

conf_path, media_root = sys.argv[1], sys.argv[2].rstrip('/')
conf = open(conf_path, encoding='utf-8').read()

# Bloc « location /media/ { ... } » actuel (sans bloc imbriqué).
match = re.search(r'\n([ \t]*)location /media/ \{[^{}]*\}', conf)
if not match:
    sys.exit("Bloc « location /media/ » introuvable : configuration laissée telle quelle.")
indent = match.group(1)
nouveau = f'''
{indent}# Logos d'établissement : seuls fichiers déposés servis sans contrôle.
{indent}location /media/etablissements/logos/ {{
{indent}    alias {media_root}/etablissements/logos/;
{indent}    expires 7d;
{indent}    add_header Cache-Control "public";
{indent}    add_header X-Content-Type-Options nosniff;
{indent}}}

{indent}# Autres fichiers déposés : /media/ part vers l'application (location /), qui contrôle les droits
{indent}# puis répond par X-Accel-Redirect vers cet emplacement, inaccessible directement depuis Internet.
{indent}location /protected-media/ {{
{indent}    internal;
{indent}    alias {media_root}/;
{indent}    add_header X-Content-Type-Options nosniff;
{indent}}}'''
conf = conf[:match.start()] + nouveau + conf[match.end():]
open(conf_path, 'w', encoding='utf-8').write(conf)
PYEOF

if ! nginx -t; then
    cp -p "$BACKUP" "$CONF"
    echo "Configuration précédente restaurée ; Nginx n'a pas été rechargé." >&2
    exit 1
fi
systemctl reload nginx
echo "Fichiers déposés protégés. Sauvegarde de l'ancienne configuration : $BACKUP"
