# Configuration PWA - Guide d'installation

## 📱 Génération des icônes PWA

Pour que la PWA fonctionne correctement, vous devez générer les icônes dans différentes tailles.

### Option 1 : Utiliser un outil en ligne (Recommandé)

1. Allez sur https://realfavicongenerator.net/ ou https://www.pwabuilder.com/imageGenerator
2. Uploadez votre logo (`school_admin/static/school_admin/img/logo.png`)
3. Configurez les paramètres :
   - Android Chrome: 192x192 et 512x512
   - iOS: 152x152, 180x180
   - Windows: 144x144
4. Téléchargez les icônes générées
5. Placez-les dans `school_admin/static/school_admin/img/icons/`

### Option 2 : Utiliser Python avec Pillow

Si vous avez Pillow installé, vous pouvez utiliser le script suivant :

```python
from PIL import Image
import os

# Chemin du logo source
logo_path = 'school_admin/static/school_admin/img/logo.png'
output_dir = 'school_admin/static/school_admin/img/icons/'

# Créer le dossier si nécessaire
os.makedirs(output_dir, exist_ok=True)

# Tailles requises
sizes = [16, 32, 72, 96, 128, 144, 152, 192, 384, 512]

# Ouvrir l'image source
img = Image.open(logo_path)

# Générer les icônes
for size in sizes:
    # Redimensionner en gardant les proportions
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    # Sauvegarder
    resized.save(f'{output_dir}icon-{size}x{size}.png', 'PNG')
    print(f'✓ Icône {size}x{size} générée')

print('\n✅ Toutes les icônes ont été générées avec succès!')
```

### Option 3 : Utiliser ImageMagick (ligne de commande)

```bash
# Installer ImageMagick (si nécessaire)
# Windows: choco install imagemagick
# macOS: brew install imagemagick
# Linux: sudo apt-get install imagemagick

# Créer le dossier
mkdir -p school_admin/static/school_admin/img/icons

# Générer les icônes
for size in 16 32 72 96 128 144 152 192 384 512; do
  convert school_admin/static/school_admin/img/logo.png -resize ${size}x${size} school_admin/static/school_admin/img/icons/icon-${size}x${size}.png
done
```

## 📁 Structure des fichiers requis

```
school_admin/static/school_admin/img/icons/
├── icon-16x16.png
├── icon-32x32.png
├── icon-72x72.png
├── icon-96x96.png
├── icon-128x128.png
├── icon-144x144.png
├── icon-152x152.png
├── icon-192x192.png
├── icon-384x384.png
└── icon-512x512.png
```

## ✅ Vérification

1. Vérifiez que tous les fichiers d'icônes existent
2. Testez l'application sur différents appareils :
   - Android (Chrome)
   - iOS (Safari)
   - Desktop (Chrome, Edge, Firefox)
3. Vérifiez que le manifest.json est accessible : `http://votre-domaine/manifest.json`
4. Vérifiez que le service-worker.js est accessible : `http://votre-domaine/service-worker.js`

## 🔧 Configuration HTTPS

⚠️ **Important** : Les Service Workers nécessitent HTTPS en production (sauf en localhost).

Pour le développement local, utilisez :
```bash
python manage.py runserver 0.0.0.0:8000
```

Pour la production, configurez HTTPS avec un reverse proxy (Nginx, Apache) ou utilisez un service comme Heroku, Railway, etc.

## 📱 Test de l'installation

1. Ouvrez l'application dans Chrome/Edge
2. Ouvrez les DevTools (F12)
3. Allez dans l'onglet "Application" > "Service Workers"
4. Vérifiez que le service worker est actif
5. Testez le mode hors ligne :
   - DevTools > Network > Cocher "Offline"
   - Rechargez la page
   - L'application devrait fonctionner hors ligne

## 🚀 Fonctionnalités PWA

- ✅ Installation sur appareil
- ✅ Mode hors ligne
- ✅ Cache des ressources statiques
- ✅ Mise à jour automatique
- ✅ Support multi-plateforme (Android, iOS, Desktop)

