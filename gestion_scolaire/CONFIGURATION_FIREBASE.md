# 🔥 Configuration Firebase pour les notifications push

## 📋 Étapes pour configurer Firebase

### Étape 1 : Télécharger `google-services.json`

1. **Allez sur Firebase Console**
   - https://console.firebase.google.com/
   - Connectez-vous avec votre compte Google

2. **Sélectionnez votre projet**
   - Projet : `gestion-scolaire-6945a`

3. **Ajoutez une application Android**
   - Cliquez sur l'icône Android (ou ⚙️ > Paramètres du projet)
   - Cliquez sur **"Ajouter une application"** ou **"Ajouter Firebase à votre application Android"**

4. **Remplissez les informations**
   - **Package name Android** : `com.ariaedu.app`
   - **App nickname** (optionnel) : `Aria Mobile App`
   - **Debug signing certificate SHA-1** : Optionnel pour l'instant

5. **Téléchargez le fichier**
   - Cliquez sur **"Télécharger google-services.json"**
   - **IMPORTANT** : Placez ce fichier dans :
     ```
     gestion_scolaire/android/app/google-services.json
     ```

### Étape 2 : Vérifier la configuration

Le fichier `google-services.json` devrait ressembler à ceci :
```json
{
  "project_info": {
    "project_number": "...",
    "project_id": "gestion-scolaire-6945a",
    "storage_bucket": "..."
  },
  "client": [
    {
      "client_info": {
        "mobilesdk_app_id": "...",
        "android_client_info": {
          "package_name": "com.ariaedu.app"
        }
      },
      "oauth_client": [...],
      "api_key": [...],
      "services": {
        "appinvite_service": {...}
      }
    }
  ],
  "configuration_version": "1"
}
```

### Étape 3 : Rebuild l'application

```bash
cd gestion_scolaire
flutter clean
flutter pub get
flutter build apk --release
```

## ✅ Vérification

### Vérifier que le fichier est présent
```bash
ls android/app/google-services.json
```

### Vérifier dans les logs de build
Vous devriez voir :
```
> Task :app:processReleaseGoogleServices
Parsing json file: android/app/google-services.json
```

## 🔍 Test des notifications

### 1. Installer l'APK sur votre téléphone

### 2. Ouvrir l'application et se connecter
- L'application va automatiquement demander la permission de notification
- Acceptez la permission

### 3. Vérifier dans les logs
Dans les logs Flutter (via `flutter run` ou Android Studio), vous devriez voir :
```
✅ Permission de notification accordée
📱 Token FCM obtenu: [token]...
✅ Token FCM envoyé au serveur avec succès
```

### 4. Vérifier dans Django Admin
1. Allez dans l'admin Django : `/admin/`
2. Cherchez la table **FCM Tokens**
3. Vous devriez voir un token avec :
   - `device_type` = `android`
   - `device_name` = `Aria Mobile App`
   - `is_active` = `True`

### 5. Tester une notification
1. Connectez-vous en tant que **professeur**
2. Publiez une note pour un élève
3. L'élève devrait recevoir la notification sur son téléphone Android

## 🐛 Dépannage

### Erreur : "File google-services.json is missing"

**Solution** : Vérifiez que le fichier est bien dans `android/app/google-services.json`

### Erreur : "Package name mismatch"

**Solution** : Vérifiez que le package name dans `google-services.json` correspond à `com.ariaedu.app` dans `build.gradle.kts`

### Les notifications ne s'affichent toujours pas

1. **Vérifiez les permissions Android**
   - Paramètres > Applications > Aria > Notifications
   - Assurez-vous que les notifications sont activées

2. **Vérifiez les logs Flutter**
   - Cherchez les erreurs liées à FCM

3. **Vérifiez que le token est bien enregistré**
   - Dans Django Admin > FCM Tokens
   - Vérifiez qu'un token existe pour l'utilisateur

4. **Testez avec l'API de test**
   - Allez sur `/api/fcm/test-notification/` (si disponible)
   - Envoyez une notification de test

## 📝 Notes importantes

- ⚠️ **Ne commitez JAMAIS `google-services.json`** dans Git si il contient des informations sensibles
- ✅ Le fichier est déjà dans `.gitignore`
- ✅ Les notifications fonctionnent même avec un APK installé manuellement (pas besoin de Google Play)
- ✅ Chaque appareil a son propre token FCM unique

## 🔗 Liens utiles

- [Firebase Console](https://console.firebase.google.com/)
- [Documentation Firebase Messaging](https://firebase.google.com/docs/cloud-messaging)
- [Flutter Firebase Setup](https://firebase.flutter.dev/docs/overview)

