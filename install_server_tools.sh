#!/bin/bash

# Script d'installation de Python, Git et Nginx sur Ubuntu 24.04
# À exécuter sur le serveur VPS

echo "================================================"
echo "Installation des outils serveur"
echo "================================================"
echo ""

# Mise à jour du système
echo "📦 Mise à jour des paquets..."
sudo apt update
sudo apt upgrade -y

# Installation de Python 3 et pip
echo ""
echo "🐍 Installation de Python 3 et pip..."
sudo apt install -y python3 python3-pip python3-venv python3-dev

# Installation de Git
echo ""
echo "📚 Installation de Git..."
sudo apt install -y git

# Installation de Nginx
echo ""
echo "🌐 Installation de Nginx..."
sudo apt install -y nginx

# Vérification des versions installées
echo ""
echo "================================================"
echo "✅ Installation terminée!"
echo "================================================"
echo ""
echo "Versions installées:"
echo "Python: $(python3 --version)"
echo "Pip: $(pip3 --version)"
echo "Git: $(git --version)"
echo "Nginx: $(nginx -v 2>&1)"
echo ""
echo "Statut des services:"
sudo systemctl status nginx --no-pager -l | head -n 5
echo ""
echo "================================================"

