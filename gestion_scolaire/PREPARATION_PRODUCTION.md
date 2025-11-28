# Guide de préparation pour la production - Aria

## ✅ Checklist avant génération APK/AAB

### 1. Configuration de base ✅
- [x] Icônes d'application configurées
- [x] Splash screen configuré
- [x] Permissions configurées
- [ ] Nom de l'application personnalisé
- [ ] Application ID unique
- [ ] Version de l'application
- [ ] Signature de l'application (release)

### 2. Configuration Android

#### Application ID
L'Application ID doit être unique. Format recommandé : `com.votredomaine.aria` ou `com.ariaedu.app`

#### Nom de l'application
Le nom affiché dans la liste des applications doit être "Aria" ou "Aria - Gestion Scolaire"

#### Version
- Version name : 1.0.0 (visible par l'utilisateur)
- Version code : 1 (incrémenté à chaque build)

### 3. Signature de l'application (OBLIGATOIRE pour Google Play)

Pour publier sur Google Play Store, vous devez signer votre application avec une clé de signature.

#### Créer une clé de signature

```bash
# Naviguer vers le dossier android/app
cd android/app

# Créer la clé (remplacez les valeurs)
keytool -genkey -v -keystore aria-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias aria

# Vous devrez entrer :
# - Mot de passe du keystore
# - Informations sur votre organisation
```

#### Configurer la signature dans build.gradle.kts

Créer un fichier `key.properties` dans `android/` :

```properties
storePassword=votre_mot_de_passe_keystore
keyPassword=votre_mot_de_passe_key
keyAlias=aria
storeFile=../app/aria-release-key.jks
```

### 4. Optimisations pour la production

- [ ] Minification activée
- [ ] Obfuscation du code (ProGuard/R8)
- [ ] Compression des ressources
- [ ] Désactiver le debug

### 5. Tests avant publication

- [ ] Tester sur différents appareils Android
- [ ] Vérifier toutes les fonctionnalités natives (caméra, GPS, etc.)
- [ ] Tester la connexion Internet
- [ ] Vérifier les permissions
- [ ] Tester le chargement de la WebView

## 📦 Commandes de build

### Build APK (pour test direct)
```bash
flutter build apk --release
```
Fichier généré : `build/app/outputs/flutter-apk/app-release.apk`

### Build AAB (pour Google Play Store)
```bash
flutter build appbundle --release
```
Fichier généré : `build/app/outputs/bundle/release/app-release.aab`

### Build avec version personnalisée
```bash
flutter build appbundle --release --build-name=1.0.0 --build-number=1
```

## 🔐 Sécurité

⚠️ **IMPORTANT** : Ne commitez JAMAIS le fichier `key.properties` ou les fichiers `.jks` dans Git !

Ajoutez-les au `.gitignore` :
```
android/key.properties
android/app/*.jks
android/app/*.keystore
```

## 📱 Publication sur Google Play Store

1. Créer un compte développeur Google Play (25$ unique)
2. Créer une nouvelle application
3. Remplir les informations de l'application
4. Uploader le fichier AAB
5. Configurer les captures d'écran et descriptions
6. Soumettre pour révision

## 🍎 Publication sur App Store (iOS)

Pour iOS, vous aurez besoin :
- Compte développeur Apple (99$/an)
- Certificats de développement
- Profils de provisioning
- Configuration Xcode

