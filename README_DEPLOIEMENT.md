# Guide de Déploiement - Application Django sur VPS Ubuntu

Ce guide détaille toutes les étapes nécessaires pour déployer l'application Django **Goo School** sur un serveur VPS Ubuntu avec PostgreSQL, Nginx, Gunicorn et HTTPS.

## Table des matières

1. [Prérequis](#prérequis)
2. [Installation des dépendances système](#installation-des-dépendances-système)
3. [Configuration de PostgreSQL](#configuration-de-postgresql)
4. [Configuration de l'environnement virtuel Python](#configuration-de-lenvironnement-virtuel-python)
5. [Clonage et configuration du projet](#clonage-et-configuration-du-projet)
6. [Configuration de Django](#configuration-de-django)
7. [Configuration de Gunicorn](#configuration-de-gunicorn)
8. [Configuration de Nginx](#configuration-de-nginx)
9. [Installation du certificat SSL (HTTPS)](#installation-du-certificat-ssl-https)
10. [Configuration des fichiers statiques](#configuration-des-fichiers-statiques)
11. [Mise à jour des fichiers statiques et invalidation du cache](#mise-à-jour-des-fichiers-statiques-et-invalidation-du-cache)
12. [Commandes utiles pour la maintenance](#commandes-utiles-pour-la-maintenance)

---

## Prérequis

- Un serveur VPS Ubuntu (testé sur Ubuntu 22.04/24.04)
- Accès SSH au serveur
- Un nom de domaine pointant vers l'IP du serveur (ex: `aria-edu.com`)
- Les droits sudo sur le serveur

---

## Installation des dépendances système

### 1. Mise à jour du système

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Installation de Python 3 et pip

```bash
sudo apt install -y python3 python3-pip python3-venv python3-dev
```

Vérification :
```bash
python3 --version
pip3 --version
```

### 3. Installation de Git

```bash
sudo apt install -y git
```

Configuration (optionnel) :
```bash
git config --global user.name "Votre Nom"
git config --global user.email "votre.email@example.com"
```

### 4. Installation de Nginx

```bash
sudo apt install -y nginx
```

Démarrer et activer Nginx :
```bash
sudo systemctl start nginx
sudo systemctl enable nginx
```

Vérification :
```bash
sudo systemctl status nginx
```

---

## Configuration de PostgreSQL

### 1. Installation de PostgreSQL

```bash
sudo apt install -y postgresql postgresql-contrib
```

### 2. Démarrage et activation de PostgreSQL

```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 3. Configuration de la base de données

Se connecter à PostgreSQL :
```bash
sudo -u postgres psql
```

Créer la base de données et l'utilisateur :
```sql
-- Créer un utilisateur (si nécessaire)
ALTER USER postgres PASSWORD 'Ludvanne';

-- Créer la base de données
CREATE DATABASE goo_school;

-- Vérifier
\l

-- Quitter
\q
```

### 4. Configuration de pg_hba.conf (si nécessaire)

Éditer le fichier de configuration :
```bash
sudo nano /etc/postgresql/*/main/pg_hba.conf
```

S'assurer que la ligne suivante est présente :
```
local   all             all                                     md5
host    all             all             127.0.0.1/32            md5
```

Redémarrer PostgreSQL :
```bash
sudo systemctl restart postgresql
```

---

## Configuration de l'environnement virtuel Python

### 1. Créer le répertoire du projet

```bash
mkdir -p ~/aria
cd ~/aria
```

### 2. Cloner le projet depuis GitHub

```bash
git clone https://github.com/nick-dev12/goo_school.git
cd goo_school
```

### 3. Créer l'environnement virtuel

```bash
python3 -m venv venv
```

### 4. Activer l'environnement virtuel

```bash
source venv/bin/activate
```

### 5. Installer les dépendances

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Vérification :
```bash
pip list
```

---

## Clonage et configuration du projet

### 1. Vérifier la branche

```bash
git branch
git checkout main  # Si nécessaire
```

### 2. Créer les dossiers nécessaires

```bash
mkdir -p logs
mkdir -p media
mkdir -p staticfiles
```

### 3. Configurer les permissions

```bash
chmod -R 755 ~/aria/goo_school
```

---

## Configuration de Django

### 1. Configuration de settings.py

Éditer le fichier `school/settings.py` :

```python
# DEBUG et ALLOWED_HOSTS
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = [
    'aria-edu.com',
    'www.aria-edu.com',
    '157.173.102.180',  # IP du serveur
    'localhost',
    '127.0.0.1',
]

# Base de données
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'goo_school'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'Ludvanne'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'client_encoding': 'UTF8',
        },
    }
}

# Fichiers statiques
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'school_admin/static'),
]

# Fichiers médias
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Sécurité HTTPS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# CORS
CORS_ALLOWED_ORIGINS = [
    "https://aria-edu.com",
    "https://www.aria-edu.com",
    "http://157.173.102.180",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
```

### 2. Effectuer les migrations

```bash
cd ~/aria/goo_school
source venv/bin/activate
python manage.py makemigrations
python manage.py migrate
```

### 3. Créer un superutilisateur (si nécessaire)

```bash
python manage.py createsuperuser
```

### 4. Collecter les fichiers statiques

```bash
python manage.py collectstatic --noinput
```

### 5. Vérifier la configuration

```bash
python manage.py check
```

---

## Configuration de Gunicorn

### 1. Installation de Gunicorn

```bash
pip install gunicorn
```

### 2. Créer le fichier de configuration Gunicorn

```bash
mkdir -p ~/aria/goo_school/config
nano ~/aria/goo_school/config/gunicorn_config.py
```

Contenu du fichier :
```python
# Gunicorn configuration file
import multiprocessing

# Nombre de workers (généralement 2-4 x nombre de CPU)
workers = multiprocessing.cpu_count() * 2 + 1

# Nombre de threads par worker
threads = 2

# Socket pour communiquer avec Nginx
bind = "127.0.0.1:8000"

# Timeout
timeout = 120

# Mode de démarrage (daemon = False pour systemd)
daemon = False

# Logs
accesslog = "/home/nick/aria/goo_school/logs/gunicorn_access.log"
errorlog = "/home/nick/aria/goo_school/logs/gunicorn_error.log"
loglevel = "info"

# Process name
proc_name = "goo_school"

# Préchargement de l'application
preload_app = True

# Worker class
worker_class = "sync"

# Max requests (recycler les workers après N requêtes)
max_requests = 1000
max_requests_jitter = 50

# Graceful timeout
graceful_timeout = 30
```

### 3. Créer le service systemd pour Gunicorn

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

Contenu du service :
```ini
[Unit]
Description=gunicorn daemon for Goo School Django application
After=network.target postgresql.service

[Service]
User=nick
Group=nick
WorkingDirectory=/home/nick/aria/goo_school
Environment="PATH=/home/nick/aria/goo_school/venv/bin"
ExecStart=/home/nick/aria/goo_school/venv/bin/gunicorn \
    --bind 127.0.0.1:8000 \
    --workers 3 \
    --threads 2 \
    --timeout 120 \
    --access-logfile /home/nick/aria/goo_school/logs/gunicorn_access.log \
    --error-logfile /home/nick/aria/goo_school/logs/gunicorn_error.log \
    --log-level info \
    school.wsgi:application
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Note :** Remplacez `nick` par votre nom d'utilisateur.

### 4. Activer et démarrer Gunicorn

```bash
sudo systemctl daemon-reload
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
sudo systemctl status gunicorn
```

---

## Configuration de Nginx

### 1. Créer la configuration Nginx

```bash
sudo nano /etc/nginx/sites-available/aria-edu
```

Configuration initiale (HTTP) :
```nginx
# Configuration HTTP (pour obtenir le certificat SSL)
server {
    listen 80;
    listen [::]:80;
    server_name aria-edu.com www.aria-edu.com;

    # Taille maximale des uploads
    client_max_body_size 100M;

    # Fichiers statiques
    location /static/ {
        alias /home/nick/aria/goo_school/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Fichiers médias
    location /media/ {
        alias /home/nick/aria/goo_school/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Proxy vers Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_redirect off;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
```

**Note :** Remplacez `nick` par votre nom d'utilisateur et `aria-edu.com` par votre domaine.

### 2. Activer le site

```bash
sudo ln -s /etc/nginx/sites-available/aria-edu /etc/nginx/sites-enabled/
```

### 3. Supprimer la configuration par défaut (si nécessaire)

```bash
sudo rm -f /etc/nginx/sites-enabled/default
```

### 4. Vérifier et recharger Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl status nginx
```

---

## Installation du certificat SSL (HTTPS)

### 1. Installation de Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 2. Obtenir le certificat SSL

```bash
sudo certbot --nginx -d aria-edu.com -d www.aria-edu.com
```

Certbot va :
- Obtenir le certificat SSL
- Modifier automatiquement la configuration Nginx pour ajouter HTTPS
- Configurer la redirection HTTP → HTTPS

### 3. Vérifier le certificat

```bash
sudo certbot certificates
```

### 4. Tester le renouvellement automatique

```bash
sudo certbot renew --dry-run
```

Le renouvellement automatique est configuré par défaut.

---

## Configuration des fichiers statiques

### 1. Collecter les fichiers statiques

```bash
cd ~/aria/goo_school
source venv/bin/activate
python manage.py collectstatic --noinput
```

### 2. Configurer les permissions

```bash
# Permissions des dossiers parents
sudo chmod 755 /home/nick
chmod 755 ~/aria
chmod 755 ~/aria/goo_school

# Permissions de staticfiles
sudo chgrp -R www-data ~/aria/goo_school/staticfiles/
sudo chmod -R 755 ~/aria/goo_school/staticfiles/
sudo find ~/aria/goo_school/staticfiles -type f -exec chmod 644 {} \;
```

### 3. Vérifier l'accès

```bash
curl -I https://aria-edu.com/static/admin/css/base.css
```

---

## Mise à jour des fichiers statiques et invalidation du cache

### Workflow de mise à jour

Lorsque vous modifiez des fichiers statiques (CSS, JS, images) en local, suivez ces étapes pour les déployer en production :

#### 1. En local (environnement de développement)

```bash
# 1. Modifier vos fichiers statiques
# - CSS : school_admin/static/school_admin/css/
# - JS : school_admin/static/school_admin/js/
# - Images : school_admin/static/school_admin/img/

# 2. Tester vos modifications localement
python manage.py runserver

# 3. Commiter et pousser sur GitHub
git add school_admin/static/
git commit -m "Mise à jour des fichiers statiques"
git push origin main
```

#### 2. Sur le serveur VPS

```bash
# 1. Se connecter au serveur
ssh nick@157.173.102.180

# 2. Aller dans le dossier du projet
cd ~/aria/goo_school

# 3. Récupérer les modifications depuis GitHub
git pull origin main

# 4. Activer l'environnement virtuel
source venv/bin/activate

# 5. Re-collecter les fichiers statiques (IMPORTANT)
python manage.py collectstatic --noinput

# 6. Vérifier que les nouveaux fichiers sont présents
ls -la staticfiles/school_admin/css/
ls -la staticfiles/school_admin/js/
ls -la staticfiles/school_admin/img/

# 7. Redémarrer Gunicorn (si nécessaire, pour les changements de code Python)
sudo systemctl restart gunicorn

# 8. Recharger Nginx (pour s'assurer que les fichiers sont servis)
sudo systemctl reload nginx
```

### Invalidation du cache navigateur (Cache Busting)

Pour forcer les navigateurs à charger les nouvelles versions des fichiers statiques, utilisez le **versioning** (cache busting).

#### Méthode 1 : Versioning manuel dans les templates

Dans vos templates Django, ajoutez un paramètre de version :

```django
{% load static %}
<link rel="stylesheet" href="{% static 'school_admin/css/style.css' %}?v=2.0">
<script src="{% static 'school_admin/js/script.js' %}?v=2.0"></script>
```

**Avantages :** Simple, contrôle total  
**Inconvénients :** Nécessite de modifier les templates à chaque mise à jour

#### Méthode 2 : Versioning automatique avec Django

Créer un template tag personnalisé pour générer automatiquement des versions :

**1. Créer le fichier `school_admin/templatetags/static_version.py` :**

```python
from django import template
from django.conf import settings
import os

register = template.Library()

@register.simple_tag
def static_version(path):
    """
    Génère une URL avec un paramètre de version basé sur la date de modification
    """
    static_path = os.path.join(settings.STATIC_ROOT, path)
    if os.path.exists(static_path):
        mtime = os.path.getmtime(static_path)
        version = int(mtime)
        return f"{settings.STATIC_URL}{path}?v={version}"
    return f"{settings.STATIC_URL}{path}"
```

**2. Utiliser dans vos templates :**

```django
{% load static_version %}
<link rel="stylesheet" href="{% static_version 'school_admin/css/style.css' %}">
<script src="{% static_version 'school_admin/js/script.js' %}"></script>
```

**Avantages :** Automatique, basé sur la date de modification  
**Inconvénients :** Nécessite de créer un template tag

#### Méthode 3 : Configuration Nginx avec versioning

Modifier la configuration Nginx pour gérer le cache de manière plus intelligente :

```nginx
# Dans /etc/nginx/sites-available/aria-edu
location /static/ {
    alias /home/nick/aria/goo_school/staticfiles/;
    
    # Cache avec ETag pour invalidation automatique
    expires 30d;
    add_header Cache-Control "public, must-revalidate";
    add_header ETag on;
    
    # Désactiver le cache pour les fichiers avec ?v= dans l'URL
    if ($args ~ "v=") {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        expires -1;
    }
}
```

Puis recharger Nginx :
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Script de déploiement automatisé

Créer un script pour automatiser le processus de mise à jour :

**Créer `~/aria/goo_school/deploy.sh` :**

```bash
#!/bin/bash

# Script de déploiement pour les fichiers statiques
# Usage: ./deploy.sh

set -e  # Arrêter en cas d'erreur

echo "🚀 Début du déploiement..."

# Aller dans le dossier du projet
cd ~/aria/goo_school

# Activer l'environnement virtuel
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

echo "✅ Déploiement terminé avec succès!"
echo "🌐 Vérifiez votre site: https://aria-edu.com"
```

**Rendre le script exécutable :**

```bash
chmod +x ~/aria/goo_school/deploy.sh
```

**Utilisation :**

```bash
cd ~/aria/goo_school
./deploy.sh
```

### Forcer le rechargement côté client

Pour forcer les utilisateurs à voir les nouvelles versions immédiatement :

#### Option 1 : Versioning dans l'URL (recommandé)

Utilisez la méthode de versioning décrite ci-dessus. Les navigateurs considéreront `style.css?v=2.0` comme un fichier différent de `style.css?v=1.0`.

#### Option 2 : Headers HTTP pour désactiver le cache (temporaire)

Pour une mise à jour urgente, modifiez temporairement Nginx :

```nginx
location /static/ {
    alias /home/nick/aria/goo_school/staticfiles/;
    # Désactiver le cache temporairement
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    expires -1;
}
```

**⚠️ Attention :** Cela désactive le cache pour tous les fichiers statiques, ce qui peut ralentir le site. Réactivez le cache après la mise à jour.

#### Option 3 : Vider le cache Nginx (si configuré)

Si vous avez configuré un cache Nginx :

```bash
# Vider le cache Nginx (si configuré)
sudo rm -rf /var/cache/nginx/*
sudo systemctl reload nginx
```

### Vérification après mise à jour

```bash
# 1. Vérifier que les fichiers sont présents
ls -la ~/aria/goo_school/staticfiles/school_admin/css/

# 2. Tester l'accès HTTP
curl -I https://aria-edu.com/static/school_admin/css/style.css

# 3. Vérifier les headers de cache
curl -I https://aria-edu.com/static/school_admin/css/style.css | grep -i cache

# 4. Vérifier les logs Nginx
sudo tail -20 /var/log/nginx/access.log | grep static
```

### Checklist de mise à jour

- [ ] Modifier les fichiers statiques en local
- [ ] Tester localement
- [ ] Commiter et pousser sur GitHub
- [ ] Se connecter au serveur VPS
- [ ] Exécuter `git pull origin main`
- [ ] Exécuter `python manage.py collectstatic --noinput`
- [ ] Vérifier que les fichiers sont collectés
- [ ] Redémarrer Gunicorn (si nécessaire)
- [ ] Recharger Nginx
- [ ] Tester le site en production
- [ ] Vider le cache du navigateur (Ctrl+F5) pour vérifier

### Problèmes courants et solutions

#### Problème : Les modifications ne s'affichent pas

**Solutions :**
1. Vérifier que `collectstatic` a été exécuté
2. Vider le cache du navigateur (Ctrl+F5 ou Cmd+Shift+R)
3. Vérifier les permissions des fichiers
4. Vérifier que Nginx sert les bons fichiers
5. Utiliser le versioning pour forcer le rechargement

#### Problème : Les anciens fichiers sont toujours servis

**Solutions :**
1. Utiliser `collectstatic --clear` pour vider le dossier
2. Vérifier que les nouveaux fichiers sont dans `staticfiles/`
3. Vérifier les logs Nginx pour les erreurs
4. Redémarrer Nginx complètement : `sudo systemctl restart nginx`

#### Problème : Le cache navigateur est trop agressif

**Solutions :**
1. Utiliser le versioning dans les URLs
2. Modifier temporairement les headers de cache Nginx
3. Informer les utilisateurs de vider leur cache

---

## Commandes utiles pour la maintenance

### Gunicorn

```bash
# Voir le statut
sudo systemctl status gunicorn

# Redémarrer
sudo systemctl restart gunicorn

# Voir les logs
sudo journalctl -u gunicorn -f
sudo tail -f ~/aria/goo_school/logs/gunicorn_error.log

# Vérifier que Gunicorn écoute
netstat -tlnp | grep 8000
```

### Nginx

```bash
# Voir le statut
sudo systemctl status nginx

# Recharger (sans interruption)
sudo systemctl reload nginx

# Redémarrer
sudo systemctl restart nginx

# Vérifier la configuration
sudo nginx -t

# Voir les logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### PostgreSQL

```bash
# Voir le statut
sudo systemctl status postgresql

# Se connecter
sudo -u postgres psql

# Se connecter à une base de données spécifique
sudo -u postgres psql -d goo_school

# Commandes PostgreSQL utiles
\l          # Lister les bases de données
\dt         # Lister les tables
\d table    # Décrire une table
\q          # Quitter
```

### Django

```bash
# Activer l'environnement virtuel
cd ~/aria/goo_school
source venv/bin/activate

# Migrations
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations

# Collecter les fichiers statiques
python manage.py collectstatic --noinput

# Créer un superutilisateur
python manage.py createsuperuser

# Vérifier la configuration
python manage.py check

# Shell Django
python manage.py shell
```

### Certbot (SSL)

```bash
# Voir les certificats
sudo certbot certificates

# Renouveler manuellement
sudo certbot renew

# Tester le renouvellement
sudo certbot renew --dry-run
```

### Fichiers statiques

```bash
# Re-collecter après modification
cd ~/aria/goo_school
source venv/bin/activate
python manage.py collectstatic --noinput

# Vérifier les permissions
ls -ld ~/aria/goo_school/staticfiles/
ls -l ~/aria/goo_school/staticfiles/school_admin/css/

# Corriger les permissions si nécessaire
sudo chgrp -R www-data ~/aria/goo_school/staticfiles/
sudo chmod -R 755 ~/aria/goo_school/staticfiles/
sudo find ~/aria/goo_school/staticfiles -type f -exec chmod 644 {} \;
```

### Tests de connexion

```bash
# Tester Gunicorn localement
curl -I http://127.0.0.1:8000

# Tester HTTPS
curl -I https://aria-edu.com

# Tester HTTP (redirection)
curl -I http://aria-edu.com

# Tester les fichiers statiques
curl -I https://aria-edu.com/static/admin/css/base.css
```

### Mise à jour du code

```bash
# Sur le serveur
cd ~/aria/goo_school

# Récupérer les modifications
git pull origin main

# Activer l'environnement virtuel
source venv/bin/activate

# Installer les nouvelles dépendances (si nécessaire)
pip install -r requirements.txt

# Effectuer les migrations (si nécessaire)
python manage.py migrate

# Recollecter les fichiers statiques
python manage.py collectstatic --noinput

# Redémarrer Gunicorn
sudo systemctl restart gunicorn

# Recharger Nginx
sudo systemctl reload nginx
```

---

## Dépannage

### Problème : Gunicorn ne démarre pas

```bash
# Vérifier les logs
sudo journalctl -u gunicorn -n 50

# Vérifier les permissions
ls -la ~/aria/goo_school/venv/bin/gunicorn

# Tester manuellement
cd ~/aria/goo_school
source venv/bin/activate
gunicorn --bind 127.0.0.1:8000 school.wsgi:application
```

### Problème : Nginx retourne 502 Bad Gateway

```bash
# Vérifier que Gunicorn fonctionne
sudo systemctl status gunicorn
netstat -tlnp | grep 8000

# Vérifier les logs Nginx
sudo tail -50 /var/log/nginx/error.log

# Vérifier la configuration Nginx
sudo nginx -t
```

### Problème : Fichiers statiques non chargés (403 Forbidden)

```bash
# Vérifier les permissions
ls -ld ~/aria/goo_school/staticfiles/
ls -l ~/aria/goo_school/staticfiles/school_admin/css/

# Corriger les permissions
sudo chmod 755 /home/nick
sudo chgrp -R www-data ~/aria/goo_school/staticfiles/
sudo chmod -R 755 ~/aria/goo_school/staticfiles/
sudo find ~/aria/goo_school/staticfiles -type f -exec chmod 644 {} \;

# Vérifier les logs Nginx
sudo tail -50 /var/log/nginx/error.log | grep static
```

### Problème : Erreurs de migration

```bash
# Voir les migrations appliquées
python manage.py showmigrations

# Marquer une migration comme appliquée (si nécessaire)
python manage.py migrate school_admin 0142 --fake

# Réinitialiser les migrations (ATTENTION : perte de données)
# python manage.py migrate school_admin zero
# python manage.py migrate
```

### Problème : Certificat SSL expiré

```bash
# Renouveler le certificat
sudo certbot renew

# Vérifier les certificats
sudo certbot certificates
```

---

## Structure des répertoires

```
/home/nick/aria/goo_school/
├── config/
│   └── gunicorn_config.py
├── logs/
│   ├── gunicorn_access.log
│   └── gunicorn_error.log
├── media/
├── staticfiles/
├── school/
│   └── settings.py
├── school_admin/
├── venv/
├── manage.py
└── requirements.txt
```

---

## Configuration des services systemd

### Gunicorn
- Fichier : `/etc/systemd/system/gunicorn.service`
- Commandes : `sudo systemctl start/stop/restart/reload gunicorn`

### Nginx
- Fichier : `/etc/nginx/sites-available/aria-edu`
- Commandes : `sudo systemctl start/stop/restart/reload nginx`

### PostgreSQL
- Fichier : `/etc/postgresql/*/main/postgresql.conf`
- Commandes : `sudo systemctl start/stop/restart postgresql`

---

## Sécurité

### Recommandations

1. **Firewall** : Configurer UFW pour limiter les ports accessibles
   ```bash
   sudo ufw allow 22/tcp    # SSH
   sudo ufw allow 80/tcp    # HTTP
   sudo ufw allow 443/tcp   # HTTPS
   sudo ufw enable
   ```

2. **Mots de passe** : Utiliser des mots de passe forts pour PostgreSQL et Django

3. **Variables d'environnement** : Utiliser un fichier `.env` pour les secrets (recommandé)

4. **Mises à jour** : Maintenir le système à jour
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

5. **Backups** : Configurer des sauvegardes régulières de la base de données

---

## Support

Pour toute question ou problème, consultez :
- [Documentation Django](https://docs.djangoproject.com/)
- [Documentation Gunicorn](https://docs.gunicorn.org/)
- [Documentation Nginx](https://nginx.org/en/docs/)
- [Documentation Certbot](https://certbot.eff.org/docs/)

---

**Dernière mise à jour :** Novembre 2025

