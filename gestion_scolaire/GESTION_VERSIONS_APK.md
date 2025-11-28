# 📦 Gestion des versions APK

## 🔄 Comportement lors du build

Quand vous exécutez `flutter build apk --release`, Flutter va :

1. **Créer un nouveau fichier APK** dans `build/app/outputs/flutter-apk/`
2. **Écraser l'ancien fichier** s'il existe déjà
3. **Le nom du fichier** : `ARIA_APP.apk` (configuré dans `build.gradle.kts`)

### ⚠️ Important

- **L'ancien APK sera perdu** (écrasé)
- Ce n'est **pas une mise à jour**, c'est un **remplacement complet**
- Si vous voulez garder une version, **sauvegardez-la ailleurs** avant de rebuild

## 📁 Emplacement du fichier APK

```
gestion_scolaire/
└── build/
    └── app/
        └── outputs/
            └── flutter-apk/
                └── ARIA_APP.apk  ← Ici (écrasé à chaque build)
```

## 💾 Sauvegarder les versions importantes

### Option 1 : Renommer avant le build

```bash
# Avant de rebuild
cd gestion_scolaire/build/app/outputs/flutter-apk
ren ARIA_APP.apk ARIA_APP_v1.0.0.apk

# Puis rebuild
cd ../../../../..
flutter build apk --release
```

### Option 2 : Créer un dossier de sauvegarde

```bash
# Créer un dossier pour les versions
mkdir gestion_scolaire/releases

# Copier l'APK avant rebuild
copy gestion_scolaire\build\app\outputs\flutter-apk\ARIA_APP.apk gestion_scolaire\releases\ARIA_APP_v1.0.0.apk
```

### Option 3 : Script PowerShell automatique

Créez un fichier `save-version.ps1` :

```powershell
# Sauvegarder la version actuelle avant rebuild
$version = "1.0.0"
$source = "build\app\outputs\flutter-apk\ARIA_APP.apk"
$destination = "releases\ARIA_APP_v$version.apk"

if (Test-Path $source) {
    if (-not (Test-Path "releases")) {
        New-Item -ItemType Directory -Path "releases"
    }
    Copy-Item $source $destination
    Write-Host "✅ Version sauvegardée : $destination"
} else {
    Write-Host "⚠️ Aucun APK trouvé à sauvegarder"
}
```

## 🔢 Gestion des versions

### Version dans `pubspec.yaml`

Le numéro de version est défini dans `pubspec.yaml` :

```yaml
version: 1.0.0+1
```

- `1.0.0` = Version name (visible par l'utilisateur)
- `1` = Version code (incrémenté à chaque build pour Google Play)

### Incrémenter la version

Avant chaque nouveau build important :

```yaml
version: 1.0.1+2  # Version name + Version code
```

Puis rebuild :
```bash
flutter build apk --release --build-name=1.0.1 --build-number=2
```

## 📋 Workflow recommandé

### Pour un nouveau build

1. **Sauvegarder l'ancienne version** (si importante)
   ```bash
   copy build\app\outputs\flutter-apk\ARIA_APP.apk releases\ARIA_APP_v1.0.0.apk
   ```

2. **Incrémenter la version** dans `pubspec.yaml` (si nécessaire)

3. **Build**
   ```bash
   flutter clean
   flutter pub get
   flutter build apk --release
   ```

4. **Le nouveau APK** remplace l'ancien dans `build/app/outputs/flutter-apk/ARIA_APP.apk`

## 🎯 Résumé

- ✅ **Chaque build crée un nouveau APK**
- ✅ **L'ancien APK est écrasé** (pas de mise à jour)
- ✅ **Sauvegardez les versions importantes** avant de rebuild
- ✅ **Le nom reste `ARIA_APP.apk`** (configuré dans build.gradle.kts)

## 💡 Astuce

Pour garder un historique, créez un dossier `releases/` et copiez-y chaque version importante avec un numéro de version :

```
releases/
├── ARIA_APP_v1.0.0.apk
├── ARIA_APP_v1.0.1.apk
└── ARIA_APP_v1.1.0.apk
```

