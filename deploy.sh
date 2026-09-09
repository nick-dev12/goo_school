#!/bin/bash

# Script de déploiement pour les fichiers statiques et le code
# Usage: ./deploy.sh
# 
# Ce script automatise le processus de mise à jour de l'application Django
# après avoir poussé les modifications sur GitHub.

set -e  # Arrêter en cas d'erreur

# Obtenir le chemin absolu du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"

# Vérifier et corriger les permissions d'exécution du script
if [ ! -x "$SCRIPT_PATH" ]; then
    echo "🔧 Correction des permissions du script..."
    chmod +x "$SCRIPT_PATH"
fi

echo "🚀 Début du déploiement..."

# Aller dans le dossier du projet
cd ~/aria/goo_school

# Activer l'environnement virtuel
echo "🐍 Activation de l'environnement virtuel..."
source venv/bin/activate

# Gérer les modifications locales (fichiers de logs, etc.)
echo "🔍 Vérification des modifications locales..."
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  Modifications locales détectées (fichiers de logs, etc.)"
    echo "📦 Stash des modifications locales..."
    git stash push -m "Modifications locales avant déploiement $(date +%Y-%m-%d_%H:%M:%S)"
    STASHED=true
else
    STASHED=false
fi

# Récupérer les modifications
echo "📥 Récupération des modifications depuis GitHub..."
git pull origin main

# Supprimer le stash si on a stasher (on ne veut pas réappliquer les modifications locales)
if [ "$STASHED" = true ]; then
    echo "🗑️  Suppression du stash (modifications locales ignorées)..."
    git stash drop || true
fi

# Installer les nouvelles dépendances (si nécessaire)
echo "📦 Installation des dépendances..."
pip install -r requirements.txt --quiet

# Effectuer les migrations (si nécessaire)
echo "🗄️  Application des migrations..."
# Désactiver temporairement set -e pour permettre de continuer en cas d'erreur
set +e
python manage.py migrate --noinput
MIGRATE_EXIT_CODE=$?
set -e

if [ $MIGRATE_EXIT_CODE -ne 0 ]; then
    echo "⚠️  Erreur lors des migrations (code: $MIGRATE_EXIT_CODE)"
    echo "💡 Si une colonne existe déjà, vous devrez marquer la migration comme appliquée:"
    echo "   python manage.py migrate school_admin 0142 --fake"
    echo "   Puis relancer: python manage.py migrate --noinput"
    echo ""
    echo "⏭️  Continuation du déploiement malgré l'erreur de migration..."
fi

# Re-collecter les fichiers statiques
echo "📁 Collecte des fichiers statiques..."
python manage.py collectstatic --noinput --clear

# Corriger les permissions
echo "🔐 Correction des permissions..."
if sudo -n true 2>/dev/null; then
    sudo chgrp -R www-data ~/aria/goo_school/staticfiles/
    sudo chmod -R 755 ~/aria/goo_school/staticfiles/
    sudo find ~/aria/goo_school/staticfiles -type f -exec chmod 644 {} \;
else
    echo "⚠️  sudo indisponible — permissions locales appliquées sans chgrp www-data"
    chmod -R u+rwX,go+rX ~/aria/goo_school/staticfiles/
    find ~/aria/goo_school/staticfiles -type f -exec chmod 644 {} \;
fi

# Redémarrer les services applicatifs (ASGI + Celery)
DAPHNE_PATTERN='/home/nick/aria/goo_school/venv/bin/daphne -b 127.0.0.1 -p 8001'
CELERY_PATTERN='/home/nick/aria/goo_school/venv/bin/celery -A school worker'

echo "🔄 Redémarrage de aria-daphne..."
if sudo -n systemctl restart aria-daphne 2>/dev/null; then
    echo "✅ aria-daphne redémarré (systemctl)"
elif pgrep -f "$DAPHNE_PATTERN" >/dev/null; then
    pkill -f "$DAPHNE_PATTERN"
    sleep 3
    pgrep -f "$DAPHNE_PATTERN" >/dev/null || { echo "❌ aria-daphne n'a pas redémarré"; exit 1; }
    echo "✅ aria-daphne redémarré (systemd Restart=always)"
else
    echo "❌ aria-daphne introuvable"
    exit 1
fi

echo "🔄 Redémarrage de aria-celery..."
if sudo -n systemctl restart aria-celery 2>/dev/null; then
    echo "✅ aria-celery redémarré (systemctl)"
elif pgrep -f "$CELERY_PATTERN" >/dev/null; then
    pkill -f "$CELERY_PATTERN"
    sleep 3
    pgrep -f "$CELERY_PATTERN" >/dev/null || { echo "❌ aria-celery n'a pas redémarré"; exit 1; }
    echo "✅ aria-celery redémarré (systemd Restart=always)"
else
    echo "❌ aria-celery introuvable"
    exit 1
fi

# Recharger Nginx (optionnel si sudo indisponible)
echo "🔄 Rechargement de Nginx..."
if sudo -n systemctl reload nginx 2>/dev/null; then
    echo "✅ nginx rechargé"
else
    echo "⚠️  nginx non rechargé (sudo indisponible) — généralement non bloquant"
fi

echo ""
echo "✅ Déploiement terminé avec succès!"
echo "🌐 Vérifiez votre site: https://aria-edu.com"
echo ""
echo "💡 Pour forcer le rechargement dans le navigateur:"
echo "   - Windows/Linux: Ctrl + F5"
echo "   - Mac: Cmd + Shift + R"
echo ""

