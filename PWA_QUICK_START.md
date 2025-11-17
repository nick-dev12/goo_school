# 🚀 Démarrage rapide PWA

## ⚡ Installation en 3 étapes

### 1️⃣ Générer les icônes (2 minutes)

```bash
# Installer Pillow
pip install Pillow

# Générer toutes les icônes
python school_admin/generate_icons.py
```

### 2️⃣ Ajouter les meta tags dans vos templates

Dans chaque template HTML principal, ajoutez dans le `<head>` :

```django
{% load static %}
{% include 'school_admin/partials/pwa_meta.html' %}
```

**Templates à modifier :**
- ✅ `connexion.html` (déjà fait)
- ⚠️ `dashboard.html`
- ⚠️ `inscription.html`
- ⚠️ Tous les autres templates principaux

### 3️⃣ Tester

```bash
# Démarrer le serveur
python manage.py runserver

# Ouvrir http://localhost:8000
# DevTools (F12) > Application > Service Workers
# Vérifier que le service worker est actif
```

## ✅ Vérification rapide

- [ ] Icônes générées dans `school_admin/static/school_admin/img/icons/`
- [ ] Meta tags PWA ajoutés dans les templates
- [ ] Service worker accessible : `http://localhost:8000/service-worker.js`
- [ ] Manifest accessible : `http://localhost:8000/manifest.json`

## 📱 Tester l'installation

1. **Chrome/Edge Desktop :** Icône d'installation dans la barre d'adresse
2. **Android :** Menu > "Ajouter à l'écran d'accueil"
3. **iOS :** Safari > Partager > "Sur l'écran d'accueil"

## 🎯 C'est tout !

Votre application est maintenant une PWA complète avec support hors ligne.

Pour plus de détails, consultez `PWA_README.md`

