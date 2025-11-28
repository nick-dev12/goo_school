# Guide de création des fichiers APK et AAB

## 📋 Checklist avant build

### ✅ Configuration terminée
- [x] Nom de l'application : "Aria"
- [x] Application ID : com.ariaedu.app
- [x] Version : 1.0.0+1
- [x] Icônes configurées
- [x] Splash screen configuré
- [x] Permissions configurées
- [x] ProGuard configuré
- [x] Minification activée

### ⚠️ À faire avant publication sur Google Play

1. **Créer une clé de signature** (OBLIGATOIRE pour Google Play)
2. **Configurer la signature** dans `build.gradle.kts`
3. **Tester l'APK** sur plusieurs appareils

## 🔑 Étape 1 : Créer une clé de signature

### Option A : Avec keytool (recommandé)

```bash
# Naviguer vers le dossier android/app
cd android/app

# Créer la clé de signature
keytool -genkey -v -keystore aria-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias aria
```

**Informations à fournir :**
- Mot de passe du keystore (gardez-le précieusement !)
- Mot de passe de la clé (peut être le même)
- Nom et prénom : Votre nom
- Unité organisationnelle : Votre organisation
- Organisation : Nom de votre entreprise/école
- Ville : Votre ville
- État/Province : Votre région
- Code pays : CM (ou votre code pays)

### Option B : Avec Android Studio

1. Ouvrir Android Studio
2. Build > Generate Signed Bundle / APK
3. Suivre l'assistant pour créer une nouvelle clé

## 📝 Étape 2 : Configurer la signature

### 2.1 Créer le fichier key.properties

Créez le fichier `android/key.properties` :

```properties
storePassword=votre_mot_de_passe_keystore
keyPassword=votre_mot_de_passe_key
keyAlias=aria
storeFile=../app/aria-release-key.jks
```

⚠️ **IMPORTANT** : Ce fichier est dans `.gitignore` et ne doit JAMAIS être commité !

### 2.2 Décommenter la configuration dans build.gradle.kts

Ouvrez `android/app/build.gradle.kts` et décommentez la section `signingConfigs` :

```kotlin
signingConfigs {
    create("release") {
        val keystorePropertiesFile = rootProject.file("key.properties")
        val keystoreProperties = java.util.Properties()
        if (keystorePropertiesFile.exists()) {
            keystoreProperties.load(java.io.FileInputStream(keystorePropertiesFile))
            storeFile = file(keystoreProperties["storeFile"] as String)
            storePassword = keystoreProperties["storePassword"] as String
            keyAlias = keystoreProperties["keyAlias"] as String
            keyPassword = keystoreProperties["keyPassword"] as String
        }
    }
}
```

Et dans `buildTypes.release`, changez :
```kotlin
signingConfig = signingConfigs.getByName("release")
```

## 🏗️ Étape 3 : Build de l'application

### Build APK (pour test direct)

```bash
# Depuis la racine du projet
flutter clean
flutter pub get
flutter build apk --release
```

**Fichier généré :**
- `build/app/outputs/flutter-apk/app-release.apk`

**Taille approximative :** 30-50 MB

### Build AAB (pour Google Play Store)

```bash
flutter clean
flutter pub get
flutter build appbundle --release
```

**Fichier généré :**
- `build/app/outputs/bundle/release/app-release.aab`

**Taille approximative :** 20-40 MB (plus petit grâce à la compression)

### Build avec version personnalisée

```bash
flutter build appbundle --release --build-name=1.0.0 --build-number=1
```

## 🧪 Étape 4 : Tester l'APK

1. Transférez l'APK sur votre téléphone Android
2. Activez "Sources inconnues" dans les paramètres
3. Installez l'APK
4. Testez toutes les fonctionnalités :
   - Connexion à aria-edu.com
   - Caméra
   - GPS
   - Notifications
   - Stockage local

## 📤 Étape 5 : Publier sur Google Play Store

1. **Créer un compte développeur**
   - Aller sur https://play.google.com/console
   - Payer les 25$ (frais unique)

2. **Créer une nouvelle application**
   - Nom : Aria
   - Langue par défaut : Français
   - Type : Application
   - Gratuit/Payant : Gratuit

3. **Remplir les informations**
   - Description courte (80 caractères max)
   - Description complète
   - Captures d'écran (minimum 2)
   - Icône haute résolution (512x512px)
   - Bannière de fonctionnalité (1024x500px)

4. **Uploader le fichier AAB**
   - Aller dans "Production" > "Créer une version"
   - Uploader `app-release.aab`
   - Remplir les notes de version

5. **Configurer le contenu**
   - Classification du contenu
   - Cible d'âge
   - Politique de confidentialité (si nécessaire)

6. **Soumettre pour révision**
   - Google prend généralement 1-3 jours pour réviser

## 🔄 Mises à jour futures

Pour chaque nouvelle version :

1. Incrémenter le numéro de version dans `pubspec.yaml` :
   ```yaml
   version: 1.0.1+2  # 1.0.1 = version name, 2 = version code
   ```

2. Rebuild :
   ```bash
   flutter build appbundle --release --build-name=1.0.1 --build-number=2
   ```

3. Uploader le nouveau AAB sur Google Play Console

## ⚠️ Notes importantes

- **Gardez votre clé de signature en sécurité !** Si vous la perdez, vous ne pourrez plus mettre à jour l'application sur Google Play.
- Faites une sauvegarde de `aria-release-key.jks` et `key.properties` dans un endroit sûr
- Ne partagez JAMAIS ces fichiers
- Testez toujours l'APK avant de publier l'AAB

## 🐛 Dépannage

### Erreur de signature
- Vérifiez que `key.properties` existe et contient les bonnes informations
- Vérifiez que le chemin vers le fichier `.jks` est correct

### APK trop volumineux
- Utilisez `flutter build appbundle` au lieu de `flutter build apk`
- Les AAB sont automatiquement optimisés par Google Play

### Erreur ProGuard
- Vérifiez `proguard-rules.pro` pour les règles spécifiques à vos plugins

