#!/bin/bash

# Script de déploiement pour les fichiers statiques et le code
# Usage: ./deploy.sh
# 
# Ce script automatise le processus de mise à jour de l'application Django
# après avoir poussé les modifications sur GitHub.

set -e  # Arrêter en cas d'erreur

echo "🚀 Début du déploiement..."

# Aller dans le dossier du projet
cd ~/aria/goo_school

# Activer l'environnement virtuel
echo "🐍 Activation de l'environnement virtuel..."
source venv/bin/activate

# Récupérer les modifications
echo "📥 Récupération des modifications depuis GitHub..."
git pull origin main

# Installer les nouvelles dépendances (si nécessaire)
echo "📦 Installation des dépendances..."
pip install -r requirements.txt --quiet

# Effectuer les migrations (si nécessaire)
echo "🗄️  Application des migrations..."
python manage.py migrate --noinput

# Re-collecter les fichiers statiques
echo "📁 Collecte des fichiers statiques..."
python manage.py collectstatic --noinput --clear

# Corriger les permissions
echo "🔐 Correction des permissions..."
sudo chgrp -R www-data ~/aria/goo_school/staticfiles/
sudo chmod -R 755 ~/aria/goo_school/staticfiles/
sudo find ~/aria/goo_school/staticfiles -type f -exec chmod 644 {} \;

# Redémarrer Gunicorn
echo "🔄 Redémarrage de Gunicorn..."
sudo systemctl restart gunicorn

# Recharger Nginx
echo "🔄 Rechargement de Nginx..."
sudo systemctl reload nginx

echo ""
echo "✅ Déploiement terminé avec succès!"
echo "🌐 Vérifiez votre site: https://aria-edu.com"
echo ""
echo "💡 Pour forcer le rechargement dans le navigateur:"
echo "   - Windows/Linux: Ctrl + F5"
echo "   - Mac: Cmd + Shift + R"
echo ""

