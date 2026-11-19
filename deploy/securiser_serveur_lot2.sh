#!/usr/bin/env bash
# Sécurité, lot 2 : limites de débit dans Nginx et bannissement automatique (fail2ban).
# À lancer sur le serveur, après le déploiement du code du lot 2 :
#     sudo bash deploy/securiser_serveur_lot2.sh
# Sans risque à relancer. En cas d'erreur de syntaxe Nginx, l'ancienne configuration est restaurée.
#
# Seuils volontairement larges : chez les opérateurs mobiles, des milliers d'abonnés peuvent sortir sur
# Internet par la même adresse IP. Le but est d'arrêter les robots et les rafales, pas les écoles.
set -euo pipefail

CONF="${ARIA_NGINX_CONF:-/etc/nginx/sites-available/aria-edu}"
ZONES="/etc/nginx/conf.d/aria-limites.conf"

if [ "$(id -u)" -ne 0 ]; then
    echo "À lancer avec sudo." >&2
    exit 2
fi
[ -f "$CONF" ] || { echo "Configuration introuvable : $CONF" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$CONF" "$CONF.bak-$STAMP"
HAD_ZONES=0
[ -f "$ZONES" ] && HAD_ZONES=1 && cp -p "$ZONES" "$ZONES.bak-$STAMP"

restore() {
    cp -p "$CONF.bak-$STAMP" "$CONF"
    if [ "$HAD_ZONES" -eq 1 ]; then cp -p "$ZONES.bak-$STAMP" "$ZONES"; else rm -f "$ZONES"; fi
    echo "Configuration précédente restaurée ; Nginx n'a pas été rechargé." >&2
}

# ---------------------------------------------------------------- 1. Zones de limitation (contexte http)
cat > "$ZONES" <<'NGINX'
# Sécurité Aria, lot 2 — zones de limitation de débit, par adresse IP du visiteur.
# Pages et API : anti-rafales (un robot qui aspire ou qui sature le site).
limit_req_zone $binary_remote_addr zone=aria_general:20m rate=50r/s;
# Formulaires sensibles : seuls les envois (POST) sont comptés, l'affichage reste libre.
map $request_method $aria_cle_envoi {
    POST    $binary_remote_addr;
    default "";
}
limit_req_zone $aria_cle_envoi zone=aria_formulaires:10m rate=30r/m;
limit_req_status 429;
limit_req_log_level warn;
NGINX

# ---------------------------------------------------------------- 2. Application dans le site
if ! grep -q 'zone=aria_general' "$CONF"; then
    python3 - "$CONF" <<'PYEOF'
import re
import sys

path = sys.argv[1]
conf = open(path, encoding='utf-8').read()

# Bloc « location / { ... } » (sans bloc imbriqué) : on y ajoute la limite générale, et on en recopie
# le contenu pour un emplacement dédié aux formulaires sensibles.
match = re.search(r'\n([ \t]*)location / \{([^{}]*)\}', conf)
if not match:
    sys.exit("Bloc « location / » introuvable : configuration laissée telle quelle.")
indent, body = match.group(1), match.group(2)
general = f'\n{indent}    limit_req zone=aria_general burst=200 nodelay;'
formulaires = (
    f'\n{indent}# Connexion, mots de passe, préinscription, candidature, liaison parent : envois limités.'
    f'\n{indent}location ~ ^/(connexion|password-reset|preinscription/formulaire|candidature|parent/demande-liaison)(/|$) {{'
    f'\n{indent}    limit_req zone=aria_formulaires burst=30 nodelay;'
    f'{general}{body}}}\n'
)
nouveau = f'{formulaires}\n{indent}location / {{{general}{body}}}'
conf = conf[:match.start()] + nouveau + conf[match.end():]
open(path, 'w', encoding='utf-8').write(conf)
PYEOF
fi

if ! nginx -t; then
    restore
    exit 1
fi
systemctl reload nginx
echo "Limites Nginx actives."

# ---------------------------------------------------------------- 3. fail2ban
if ! command -v fail2ban-client >/dev/null 2>&1; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq fail2ban
fi
cat > /etc/fail2ban/jail.d/aria.local <<'JAIL'
# Sécurité Aria, lot 2.
[DEFAULT]
bantime  = 1h
findtime = 10m
# Ne jamais bannir le serveur lui-même.
ignoreip = 127.0.0.1/8 ::1

[sshd]
enabled  = true
maxretry = 5

# Adresses qui dépassent sans cesse les limites de débit de Nginx (robots, aspirateurs).
[nginx-limit-req]
enabled  = true
port     = http,https
logpath  = /var/log/nginx/error.log
maxretry = 60

# Robots qui cherchent des fichiers d'autres logiciels (wp-login.php, phpmyadmin…).
[nginx-botsearch]
enabled  = true
port     = http,https
logpath  = /var/log/nginx/access.log
maxretry = 10
JAIL
systemctl enable --now fail2ban >/dev/null
systemctl restart fail2ban
sleep 2
fail2ban-client status
echo "Sécurité lot 2 appliquée. Sauvegardes : $CONF.bak-$STAMP"
