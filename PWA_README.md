# 📱 Configuration PWA - Aria Plateforme Éducative

## ✅ Configuration terminée

Votre application Django est maintenant configurée comme une **Progressive Web App (PWA)** complète avec support hors ligne.

## 🎯 Fonctionnalités implémentées

- ✅ **Manifest.json** : Configuration complète pour l'installation
- ✅ **Service Worker** : Cache intelligent et mode hors ligne
- ✅ **Meta tags PWA** : Support multi-plateforme (Android, iOS, Desktop)
- ✅ **Scripts d'enregistrement** : Gestion automatique du service worker
- ✅ **Vues Django** : Routes pour servir les fichiers PWA
- ✅ **Page hors ligne** : Interface dédiée pour le mode offline

## 🚀 Installation rapide

### 1. Générer les icônes PWA

**Option A : Script Python automatique (Recommandé)**

```bash
# Installer Pillow si nécessaire
pip install Pillow

# Générer les icônes
python school_admin/generate_icons.py
```

**Option B : Outil en ligne**

1. Allez sur https://realfavicongenerator.net/
2. Uploadez `school_admin/static/school_admin/img/logo.png`
3. Téléchargez et placez les icônes dans `school_admin/static/school_admin/img/icons/`

### 2. Vérifier les fichiers

Assurez-vous que ces fichiers existent :
- ✅ `school_admin/static/school_admin/manifest.json`
- ✅ `school_admin/static/school_admin/service-worker.js`
- ✅ `school_admin/static/school_admin/js/pwa.js`
- ✅ `school_admin/pwa_views.py`
- ✅ `school_admin/templates/school_admin/partials/pwa_meta.html`
- ✅ `school_admin/static/school_admin/img/icons/` (dossier avec toutes les icônes)

### 3. Ajouter les meta tags dans vos templates

Pour chaque template HTML principal, ajoutez dans le `<head>` :

```django
{% load static %}
{% include 'school_admin/partials/pwa_meta.html' %}
```

**Exemple :**
```html
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ma Page</title>
    {% load static %}
    <!-- PWA Meta Tags -->
    {% include 'school_admin/partials/pwa_meta.html' %}
</head>
<body>
    <!-- Votre contenu -->
</body>
</html>
```

### 4. Tester l'application

1. **Démarrer le serveur Django :**
   ```bash
   python manage.py runserver
   ```

2. **Ouvrir dans Chrome/Edge :**
   - Allez sur `http://localhost:8000`
   - Ouvrez les DevTools (F12)
   - Onglet "Application" > "Service Workers"
   - Vérifiez que le service worker est actif

3. **Tester l'installation :**
   - Chrome/Edge : Cliquez sur l'icône d'installation dans la barre d'adresse
   - Android : Menu > "Ajouter à l'écran d'accueil"
   - iOS Safari : Partager > "Sur l'écran d'accueil"

4. **Tester le mode hors ligne :**
   - DevTools > Network > Cocher "Offline"
   - Rechargez la page
   - L'application devrait fonctionner hors ligne

## 📋 Fichiers créés/modifiés

### Nouveaux fichiers

1. `school_admin/static/school_admin/manifest.json` - Configuration PWA
2. `school_admin/static/school_admin/service-worker.js` - Service Worker
3. `school_admin/static/school_admin/js/pwa.js` - Script d'enregistrement PWA
4. `school_admin/pwa_views.py` - Vues Django pour PWA
5. `school_admin/templates/school_admin/partials/pwa_meta.html` - Meta tags PWA
6. `school_admin/generate_icons.py` - Script de génération d'icônes
7. `school_admin/static/school_admin/PWA_SETUP.md` - Guide détaillé

### Fichiers modifiés

1. `school_admin/urls.py` - Ajout des routes PWA
2. `school_admin/templates/school_admin/connexion.html` - Ajout des meta tags PWA

## 🔧 Configuration HTTPS (Production)

⚠️ **Important** : Les Service Workers nécessitent HTTPS en production.

### Développement local
- ✅ Fonctionne sur `localhost` et `127.0.0.1` sans HTTPS

### Production
Configurez HTTPS avec :
- **Nginx** + Let's Encrypt
- **Apache** + Let's Encrypt
- **Cloudflare** (proxy HTTPS)
- **Heroku/Railway** (HTTPS automatique)

## 📱 Support multi-plateforme

### ✅ Android (Chrome, Edge, Samsung Internet)
- Installation complète
- Mode hors ligne
- Notifications push (si configuré)

### ✅ iOS (Safari)
- Installation sur l'écran d'accueil
- Mode hors ligne (limité)
- Meta tags Apple configurés

### ✅ Desktop (Chrome, Edge, Firefox)
- Installation comme application
- Mode hors ligne
- Fenêtre standalone

## 🎨 Personnalisation

### Modifier le thème de couleur

Éditez `school_admin/static/school_admin/manifest.json` :
```json
{
  "theme_color": "#3b82f6",  // Couleur de la barre d'état
  "background_color": "#ffffff"  // Couleur de fond au démarrage
}
```

### Modifier le nom de l'application

Éditez `school_admin/static/school_admin/manifest.json` :
```json
{
  "name": "Aria - Plateforme Éducative",
  "short_name": "Aria"
}
```

## 🐛 Dépannage

### Le service worker ne s'enregistre pas

1. Vérifiez la console du navigateur (F12)
2. Vérifiez que `service-worker.js` est accessible
3. Vérifiez que vous êtes sur HTTPS (ou localhost)

### Les icônes ne s'affichent pas

1. Vérifiez que toutes les icônes existent dans `school_admin/static/school_admin/img/icons/`
2. Vérifiez les chemins dans `manifest.json`
3. Videz le cache du navigateur

### L'application ne fonctionne pas hors ligne

1. Vérifiez que le service worker est actif
2. Vérifiez la console pour les erreurs
3. Vérifiez que les ressources sont bien mises en cache

## 📚 Ressources

- [MDN - Progressive Web Apps](https://developer.mozilla.org/fr/docs/Web/Progressive_web_apps)
- [Web.dev - PWA](https://web.dev/progressive-web-apps/)
- [Service Worker API](https://developer.mozilla.org/fr/docs/Web/API/Service_Worker_API)

## ✅ Checklist finale

- [ ] Icônes générées et placées dans le bon dossier
- [ ] Meta tags PWA ajoutés dans tous les templates principaux
- [ ] Service worker testé et fonctionnel
- [ ] Mode hors ligne testé
- [ ] Installation testée sur Android
- [ ] Installation testée sur iOS
- [ ] HTTPS configuré pour la production

---

**🎉 Votre application est maintenant une PWA complète !**

