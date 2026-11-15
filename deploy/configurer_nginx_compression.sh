#!/usr/bin/env bash
# Active la compression des CSS / JavaScript, les copies .gz pré-calculées et HTTP/2 pour aria-edu.com.
# À lancer une fois sur le serveur :  sudo bash deploy/configurer_nginx_compression.sh
# Sans risque à relancer : chaque réglage n'est ajouté que s'il manque. En cas d'erreur de syntaxe Nginx,
# la configuration précédente est restaurée et rien n'est rechargé.
set -euo pipefail

CONF="${ARIA_NGINX_CONF:-/etc/nginx/sites-available/aria-edu}"
SNIPPET_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/nginx/aria-static-compression.conf"
SNIPPET_DST="/etc/nginx/snippets/aria-static-compression.conf"

if [ "$(id -u)" -ne 0 ]; then
    echo "À lancer avec sudo." >&2
    exit 2
fi
[ -f "$CONF" ] || { echo "Configuration introuvable : $CONF" >&2; exit 1; }
[ -f "$SNIPPET_SRC" ] || { echo "Fragment introuvable : $SNIPPET_SRC" >&2; exit 1; }

BACKUP="$CONF.bak-$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$CONF" "$BACKUP"
HAD_SNIPPET=0
[ -f "$SNIPPET_DST" ] && HAD_SNIPPET=1 && cp -p "$SNIPPET_DST" "$SNIPPET_DST.bak"

restore() {
    cp -p "$BACKUP" "$CONF"
    if [ "$HAD_SNIPPET" -eq 1 ]; then cp -p "$SNIPPET_DST.bak" "$SNIPPET_DST"; else rm -f "$SNIPPET_DST"; fi
    echo "Configuration précédente restaurée ; Nginx n'a pas été rechargé." >&2
}

install -m 644 "$SNIPPET_SRC" "$SNIPPET_DST"

# 1) Compression de tout ce qui est du texte, dans le bloc HTTPS (le premier « server_name » du fichier).
if ! grep -q 'snippets/aria-static-compression.conf' "$CONF"; then
    sed -i '0,/^\s*server_name .*;/s//&\n    include snippets\/aria-static-compression.conf;/' "$CONF"
fi

# 2) Copies .gz produites par collectstatic, servies telles quelles.
if ! grep -q 'gzip_static on;' "$CONF"; then
    sed -i '0,/^\s*alias .*staticfiles\/;/s//&\n        gzip_static on;/' "$CONF"
fi

# 3) HTTP/2 sur le port 443 (syntaxe de Nginx 1.24 : sur la directive listen).
sed -i -E '/listen .*443 ssl/{/http2/!s/443 ssl/443 ssl http2/}' "$CONF"

if ! nginx -t; then
    restore
    exit 1
fi
systemctl reload nginx
rm -f "$SNIPPET_DST.bak"
echo "Compression et HTTP/2 activés. Sauvegarde de l'ancienne configuration : $BACKUP"
