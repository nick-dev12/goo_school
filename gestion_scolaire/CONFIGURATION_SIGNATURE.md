# 🔐 Configuration de la signature Android

## 📋 Étape 1 : Créer la clé de signature (keystore)

### Sur Windows (PowerShell) :

```powershell
cd gestion_scolaire\android\app
keytool -genkey -v -keystore aria-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias aria
```

### Informations à fournir :

- **Mot de passe du keystore** : Choisissez un mot de passe fort (notez-le bien !)
- **Confirmer le mot de passe** : Retapez le même mot de passe
- **Prénom et nom** : Votre nom ou nom de l'organisation
- **Unité organisationnelle** : Département (ex: "Développement")
- **Organisation** : Nom de votre organisation (ex: "Aria Education")
- **Ville** : Votre ville
- **État/Région** : Votre région
- **Code pays** : Code à 2 lettres (ex: "CM" pour Cameroun, "FR" pour France)
- **Confirmer** : Tapez "oui" (ou "yes" en anglais)
- **Mot de passe de la clé** : Utilisez le même que le keystore (ou un autre, notez-le !)

### ⚠️ IMPORTANT :

- **Sauvegardez le fichier `aria-release-key.jks`** dans un endroit sûr
- **Notez les mots de passe** dans un gestionnaire de mots de passe
- **Ne perdez JAMAIS ce fichier** : vous ne pourrez plus mettre à jour votre app sur Google Play !

## 📋 Étape 2 : Créer le fichier key.properties

Créez un fichier `key.properties` dans `gestion_scolaire/android/` :

```properties
storePassword=VOTRE_MOT_DE_PASSE_KEYSTORE
keyPassword=VOTRE_MOT_DE_PASSE_CLE
keyAlias=aria
storeFile=app/aria-release-key.jks
```

**Remplacez** :
- `VOTRE_MOT_DE_PASSE_KEYSTORE` : Le mot de passe du keystore
- `VOTRE_MOT_DE_PASSE_CLE` : Le mot de passe de la clé (peut être le même)

## 📋 Étape 3 : Configurer build.gradle.kts

Le fichier est déjà pré-configuré, il suffit de décommenter la section signingConfigs.

## 📋 Étape 4 : Vérifier que key.properties est dans .gitignore

Le fichier `.gitignore` doit contenir :
```
key.properties
*.jks
*.keystore
```

## 📋 Étape 5 : Build l'APK/AAB signé

### Pour un APK signé :
```bash
flutter build apk --release
```

### Pour un AAB (Android App Bundle - requis pour Google Play) :
```bash
flutter build appbundle --release
```

## 📋 Étape 6 : Localisation des fichiers

- **APK signé** : `build/app/outputs/flutter-apk/app-release.apk`
- **AAB signé** : `build/app/outputs/bundle/release/app-release.aab`

## ✅ Vérification

Pour vérifier que l'APK est bien signé :
```bash
cd build/app/outputs/flutter-apk
jarsigner -verify -verbose -certs app-release.apk
```

Vous devriez voir : `jar verified.`

## 🚨 Sécurité

- **Ne commitez JAMAIS** `key.properties` ou `*.jks` dans Git
- **Sauvegardez** le keystore dans plusieurs endroits sécurisés
- **Notez les mots de passe** dans un gestionnaire de mots de passe
- **Partagez** les informations avec votre équipe de manière sécurisée

