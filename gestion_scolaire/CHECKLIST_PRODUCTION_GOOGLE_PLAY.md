# ✅ Checklist de Production - Google Play Store

## 📋 Vérification de l'Environnement

### 1. ✅ Configuration de Signature
- [x] **Keystore créé** : `android/app/aria-release-key.jks`
- [x] **key.properties configuré** : `android/key.properties`
- [x] **key.properties dans .gitignore** : ✅ Protégé
- [x] **build.gradle.kts configuré** : Signature release activée
- [x] **Chemin keystore** : `app/aria-release-key.jks` ✅

### 2. ✅ Configuration Firebase
- [x] **google-services.json présent** : `android/app/google-services.json`
- [x] **Package name correspond** : `com.ariaedu.app` ✅
- [x] **google-services.json dans .gitignore** : ✅ Protégé
- [x] **Plugin Google Services activé** : `build.gradle.kts` ✅

### 3. ✅ Configuration de l'Application
- [x] **Application ID** : `com.ariaedu.app` ✅
- [x] **Version** : `1.0.0+1` (versionName: 1.0.0, versionCode: 1)
- [x] **Nom de l'app** : "Aria" ✅
- [x] **Debug banner désactivé** : `debugShowCheckedModeBanner: false` ✅

### 4. ✅ Icônes et Splash Screen
- [x] **Icône app** : `assets/images/app_icon.png` ✅
- [x] **Splash logo** : `assets/images/splash_logo.png` ✅
- [x] **flutter_launcher_icons configuré** : ✅
- [x] **flutter_native_splash configuré** : ✅

### 5. ✅ Sécurité et Optimisation
- [x] **ProGuard activé** : `isMinifyEnabled = true` ✅
- [x] **Shrink Resources** : `isShrinkResources = true` ✅
- [x] **ProGuard rules configuré** : `proguard-rules.pro` ✅
- [x] **usesCleartextTraffic retiré** : ✅ Corrigé (sécurité)
- [x] **Core Library Desugaring** : Activé ✅

### 6. ✅ Permissions Android
Les permissions suivantes sont déclarées :
- ✅ `INTERNET` - Requis pour WebView
- ✅ `ACCESS_NETWORK_STATE` - Requis pour vérifier la connexion
- ✅ `CAMERA` - Pour l'accès à la caméra
- ✅ `READ_EXTERNAL_STORAGE` - Pour lire les fichiers
- ✅ `WRITE_EXTERNAL_STORAGE` - Pour sauvegarder les fichiers
- ✅ `ACCESS_FINE_LOCATION` - Pour la localisation GPS
- ✅ `ACCESS_COARSE_LOCATION` - Pour la localisation approximative
- ✅ `POST_NOTIFICATIONS` - Pour les notifications push (Android 13+)
- ✅ `VIBRATE` - Pour les notifications
- ✅ `RECEIVE_BOOT_COMPLETED` - Pour les notifications programmées

**⚠️ IMPORTANT** : Vous devrez justifier ces permissions dans la console Google Play :
- **CAMERA** : "L'application permet aux utilisateurs de prendre des photos pour leurs profils et devoirs"
- **LOCATION** : "L'application utilise la localisation pour les fonctionnalités de présence et de géolocalisation"
- **STORAGE** : "L'application permet de sauvegarder et partager des documents éducatifs"

### 7. ✅ Services et Receivers
- [x] **FirebaseMessagingService** : Configuré ✅
- [x] **ScheduledNotificationReceiver** : Configuré ✅
- [x] **ScheduledNotificationBootReceiver** : Configuré ✅
- [x] **android:exported** : Correctement configuré ✅

### 8. ✅ Dépendances
- [x] **Firebase Core** : `firebase_core: ^3.6.0` ✅
- [x] **Firebase Messaging** : `firebase_messaging: ^15.1.3` ✅
- [x] **WebView** : `flutter_inappwebview: ^6.0.0` ✅
- [x] **Permissions** : `permission_handler: ^11.3.1` ✅
- [x] **Notifications** : `flutter_local_notifications: ^17.0.0` ✅
- [x] **Core Library Desugaring** : `desugar_jdk_libs:2.0.4` ✅

### 9. ✅ Fichiers Protégés (.gitignore)
- [x] `android/key.properties` ✅
- [x] `android/app/*.jks` ✅
- [x] `android/app/google-services.json` ✅
- [x] `android/app/*.keystore` ✅

---

## 🚀 Étapes pour Publier sur Google Play Store

### Étape 1 : Créer un Compte Développeur Google Play
1. Allez sur [Google Play Console](https://play.google.com/console)
2. Créez un compte développeur (frais unique de **25$ USD**)
3. Complétez votre profil développeur

### Étape 2 : Créer une Nouvelle Application
1. Cliquez sur "Créer une application"
2. Remplissez les informations :
   - **Nom de l'application** : Aria
   - **Langue par défaut** : Français
   - **Type d'application** : Application
   - **Gratuit ou payant** : Gratuit

### Étape 3 : Préparer les Ressources
Vous aurez besoin de :
- **Icône haute résolution** : 512x512 px (PNG, 32 bits)
- **Capture d'écran** : Au moins 2 (minimum 320px, maximum 3840px)
- **Graphique de fonctionnalité** : 1024x500 px (optionnel mais recommandé)
- **Description courte** : 80 caractères max
- **Description complète** : 4000 caractères max
- **Politique de confidentialité** : URL requise

### Étape 4 : Configurer le Contenu de l'Application
1. **Catégorie** : Éducation
2. **Classification du contenu** : Complétez le questionnaire
3. **Politique de confidentialité** : Créez une page sur votre site web
4. **Prix et distribution** : Gratuit, tous les pays

### Étape 5 : Générer l'AAB (Android App Bundle)
```bash
cd gestion_scolaire
flutter clean
flutter pub get
flutter build appbundle --release
```

Le fichier AAB sera généré dans :
```
build/app/outputs/bundle/release/app-release.aab
```

**⚠️ IMPORTANT** : Google Play Store nécessite un **AAB** (Android App Bundle), pas un APK pour la production.

### Étape 6 : Téléverser l'AAB
1. Dans Google Play Console, allez dans "Production" > "Créer une version"
2. Téléversez votre fichier `app-release.aab`
3. Remplissez les notes de version (ex: "Première version de l'application Aria")

### Étape 7 : Justifier les Permissions
Google Play vous demandera de justifier certaines permissions sensibles :
- **CAMERA** : "Permet aux utilisateurs de prendre des photos pour leurs profils et devoirs"
- **LOCATION** : "Utilisé pour les fonctionnalités de présence et de géolocalisation"
- **STORAGE** : "Permet de sauvegarder et partager des documents éducatifs"

### Étape 8 : Soumettre pour Révision
1. Vérifiez que toutes les sections sont complètes (✅ vert)
2. Cliquez sur "Soumettre pour révision"
3. Le processus de révision prend généralement **1-3 jours**

---

## ⚠️ Points d'Attention

### 1. Politique de Confidentialité
**OBLIGATOIRE** : Vous devez créer une page de politique de confidentialité accessible publiquement sur votre site web (`https://aria-edu.com/privacy-policy` ou similaire).

Cette page doit expliquer :
- Quelles données sont collectées
- Comment elles sont utilisées
- Avec qui elles sont partagées
- Comment les utilisateurs peuvent supprimer leurs données

### 2. Version et Build Number
- **Version actuelle** : `1.0.0+1`
- Pour chaque mise à jour, incrémentez :
  - `versionName` : `1.0.1`, `1.1.0`, `2.0.0`, etc.
  - `versionCode` : `2`, `3`, `4`, etc. (toujours incrémenter)

### 3. Test de l'AAB
Avant de publier, testez votre AAB avec :
```bash
# Installer bundletool (outil Google)
# Télécharger depuis : https://github.com/google/bundletool/releases

# Générer un APK de test depuis l'AAB
bundletool build-apks --bundle=app-release.aab --output=app.apks --mode=universal

# Installer sur un appareil
bundletool install-apks --apks=app.apks
```

### 4. Taille de l'Application
- Vérifiez la taille de votre AAB (doit être < 150 MB pour téléchargement direct)
- Si > 150 MB, utilisez les "App Bundle Expansion Files"

### 5. Target SDK Version
- Assurez-vous que `targetSdkVersion` est à jour (minimum Android 12+ pour 2024)
- Google Play exige des versions récentes du SDK

---

## 📝 Checklist Finale Avant Publication

- [ ] Compte développeur Google Play créé et payé (25$)
- [ ] Application créée dans la console
- [ ] Toutes les ressources préparées (icônes, captures d'écran)
- [ ] Politique de confidentialité créée et accessible
- [ ] AAB généré et testé
- [ ] Description de l'application rédigée
- [ ] Catégorie et classification complétées
- [ ] Permissions justifiées
- [ ] Version et build number corrects
- [ ] Application testée sur plusieurs appareils
- [ ] Toutes les fonctionnalités testées (notifications, caméra, GPS, etc.)

---

## 🔗 Liens Utiles

- [Google Play Console](https://play.google.com/console)
- [Documentation Google Play](https://developer.android.com/distribute/googleplay)
- [Politique de confidentialité - Modèle](https://support.google.com/googleplay/android-developer/answer/10787469)
- [Bundletool](https://github.com/google/bundletool/releases)

---

## ✅ Statut Actuel

**Votre environnement est prêt pour la production !** 🎉

Tous les fichiers de configuration sont en place. Il ne vous reste plus qu'à :
1. Créer votre compte développeur Google Play
2. Générer l'AAB avec `flutter build appbundle --release`
3. Téléverser et soumettre votre application

**Bonne chance avec votre publication !** 🚀

