#!/usr/bin/env bash
# Sécurité, lot 4 : durcissement du serveur et sauvegarde quotidienne chiffrée.
#     sudo bash deploy/durcir_serveur_lot4.sh
# Sans risque à relancer. Chaque modification est vérifiée avant d'être appliquée (sshd -t, nginx -t).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPTE="${ARIA_COMPTE:-nick}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [ "$(id -u)" -ne 0 ]; then
    echo "À lancer avec sudo." >&2
    exit 2
fi

# ---------------------------------------------------------------- 1. SSH : plus de connexion « root »
# Le compte $COMPTE se connecte par clé et dispose de sudo : root n'a plus besoin d'être joignable.
# Fichier « 00- » : lu en premier, il l'emporte sur PermitRootLogin yes de sshd_config.
if ! id "$COMPTE" >/dev/null 2>&1 || [ ! -s "/home/$COMPTE/.ssh/authorized_keys" ]; then
    echo "Le compte $COMPTE n'a pas de clé SSH : SSH laissé tel quel pour ne pas bloquer l'accès." >&2
else
    cat > /etc/ssh/sshd_config.d/00-aria.conf <<'SSH'
# Sécurité Aria, lot 4.
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
MaxAuthTries 4
SSH
    if sshd -t; then
        systemctl reload ssh 2>/dev/null || systemctl reload sshd
        echo "SSH : connexion root désactivée, mots de passe refusés."
    else
        rm -f /etc/ssh/sshd_config.d/00-aria.conf
        echo "SSH : configuration refusée par sshd -t, rien n'a changé." >&2
    fi
fi

# ---------------------------------------------------------------- 2. Webmin : fermé à Internet
if systemctl list-unit-files webmin.service >/dev/null 2>&1 && systemctl is-enabled webmin >/dev/null 2>&1; then
    systemctl disable --now webmin
    echo "Webmin arrêté et désactivé."
fi
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw deny 10000/tcp >/dev/null
    echo "Pare-feu : port 10000 fermé."
fi

# ---------------------------------------------------------------- 3. Nginx : moins d'informations, moins de surface
cp -a /etc/nginx/sites-enabled "/etc/nginx/sites-enabled.bak-$STAMP"
echo 'server_tokens off;  # Sécurité Aria, lot 4 : ne pas annoncer la version de Nginx' > /etc/nginx/conf.d/aria-durcissement.conf
# Ancienne configuration pgAdmin (service arrêté) qui répondait en HTTP sur l'adresse IP.
rm -f /etc/nginx/sites-enabled/pgadmin /etc/nginx/sites-enabled/default
if nginx -t; then
    systemctl reload nginx
    echo "Nginx : version masquée, configurations inutiles retirées."
else
    rm -f /etc/nginx/conf.d/aria-durcissement.conf
    rm -rf /etc/nginx/sites-enabled && cp -a "/etc/nginx/sites-enabled.bak-$STAMP" /etc/nginx/sites-enabled
    echo "Nginx : configuration refusée, état précédent restauré." >&2
fi

# ---------------------------------------------------------------- 4. Fichiers et services résiduels
[ -f "$PROJECT_DIR/.env.bak-avant-sync" ] && chmod 600 "$PROJECT_DIR/.env.bak-avant-sync"
systemctl disable --now gunicorn.service >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 5. Sauvegarde quotidienne chiffrée
if [ ! -s /etc/aria/sauvegarde.cle ]; then
    openssl rand -base64 48 > /etc/aria/sauvegarde.cle
    NOUVELLE_CLE=1
fi
chown root:"$COMPTE" /etc/aria/sauvegarde.cle
chmod 640 /etc/aria/sauvegarde.cle

cat > /etc/systemd/system/aria-sauvegarde.service <<UNIT
[Unit]
Description=Aria — sauvegarde quotidienne chiffrée (base et fichiers déposés)
After=postgresql.service

[Service]
Type=oneshot
User=$COMPTE
EnvironmentFile=/etc/aria/env
ExecStart=/bin/bash $PROJECT_DIR/deploy/sauvegarde_quotidienne.sh
UNIT
cat > /etc/systemd/system/aria-sauvegarde.timer <<'UNIT'
[Unit]
Description=Aria — sauvegarde chaque nuit à 2 h 30

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
RandomizedDelaySec=10min

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now aria-sauvegarde.timer >/dev/null
echo "Sauvegarde : premier passage maintenant pour vérification…"
systemctl start aria-sauvegarde.service
journalctl -u aria-sauvegarde.service -n 5 --no-pager | tail -n 3

echo
echo "Durcissement terminé."
if [ "${NOUVELLE_CLE:-0}" = 1 ]; then
    echo "IMPORTANT : une clé de chiffrement des sauvegardes a été créée dans /etc/aria/sauvegarde.cle."
    echo "            Copiez-la dans votre gestionnaire de mots de passe : sans elle, les sauvegardes sont illisibles."
    echo "            Pour l'afficher : sudo cat /etc/aria/sauvegarde.cle"
fi
[ -f /var/run/reboot-required ] && echo "Un redémarrage du serveur est en attente (correctifs du noyau) : à faire à une heure creuse."
exit 0
