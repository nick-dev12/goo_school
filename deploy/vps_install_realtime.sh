#!/usr/bin/env bash
# Installation des services temps réel sur Ubuntu 22.04/24.04 (VPS)
# Usage : sudo bash deploy/vps_install_realtime.sh

set -euo pipefail

echo "==> Mise à jour des paquets"
apt-get update
apt-get install -y redis-server python3-venv python3-dev build-essential libpq-dev nginx

echo "==> Configuration Redis"
sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
sed -i 's/^# maxmemory .*/maxmemory 256mb/' /etc/redis/redis.conf
sed -i 's/^# maxmemory-policy .*/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
systemctl enable redis-server
systemctl restart redis-server

echo "==> Redis actif :"
redis-cli ping

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo ""
echo "==> Installation des services systemd (Daphne + Celery)"
cp "$PROJECT_DIR/deploy/systemd/aria-daphne.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/systemd/aria-celery.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable aria-daphne aria-celery

echo ""
echo "==> Étapes manuelles restantes :"
echo "1. Créer /etc/aria/env depuis deploy/env.production.example"
echo "2. systemctl start aria-daphne aria-celery"
echo "3. Intégrer deploy/nginx/aria-websocket.conf dans votre site Nginx"
echo "4. nginx -t && systemctl reload nginx"
echo ""
echo "Variables d'environnement : voir deploy/env.production.example"
