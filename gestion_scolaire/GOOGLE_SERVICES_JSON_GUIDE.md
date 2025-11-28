# 📱 Guide : Obtenir le fichier `google-services.json`

## ⚠️ Important : Deux fichiers différents

Vous avez actuellement :
- ✅ `gestion-scolaire-6945a-e1fb73fd49c4.json` → **Service Account** (pour Django serveur)

Vous avez besoin de :
- ❌ `google-services.json` → **Configuration Android** (pour l'app Flutter)

## 🔥 Comment obtenir `google-services.json`

### Étape 1 : Aller sur Firebase Console

1. Ouvrez https://console.firebase.google.com/
2. Connectez-vous avec votre compte Google
3. Sélectionnez le projet : **`gestion-scolaire-6945a`**

### Étape 2 : Ajouter une application Android

1. Cliquez sur l'icône **⚙️** (Paramètres du projet) en haut à gauche
2. Allez dans l'onglet **"Vos applications"** ou **"General"**
3. Faites défiler jusqu'à la section **"Vos applications"**
4. Cliquez sur **"Ajouter une application"** ou l'icône Android 📱

### Étape 3 : Remplir les informations

1. **Package name Android** : `com.ariaedu.app`
   - ⚠️ **IMPORTANT** : Doit correspondre exactement au `applicationId` dans `build.gradle.kts`
   
2. **App nickname** (optionnel) : `Aria Mobile App`

3. **Debug signing certificate SHA-1** : 
   - Optionnel pour l'instant
   - Vous pouvez l'ajouter plus tard si nécessaire

### Étape 4 : Télécharger le fichier

1. Cliquez sur **"Télécharger google-services.json"**
2. **Placez le fichier** dans :
   ```
   gestion_scolaire/android/app/google-services.json
   ```

### Étape 5 : Vérifier le fichier

Le fichier `google-services.json` devrait ressembler à ceci :

```json
{
  "project_info": {
    "project_number": "123456789012",
    "project_id": "gestion-scolaire-6945a",
    "storage_bucket": "gestion-scolaire-6945a.appspot.com"
  },
  "client": [
    {
      "client_info": {
        "mobilesdk_app_id": "1:123456789012:android:abcdef123456",
        "android_client_info": {
          "package_name": "com.ariaedu.app"
        }
      },
      "oauth_client": [...],
      "api_key": [
        {
          "current_key": "AIzaSy..."
        }
      ],
      "services": {
        "appinvite_service": {
          "other_platform_oauth_client": [...]
        }
      }
    }
  ],
  "configuration_version": "1"
}
```

## ✅ Vérification

### Vérifier que le fichier est présent
```bash
ls gestion_scolaire/android/app/google-services.json
```

### Vérifier le package name
Ouvrez `google-services.json` et vérifiez que :
```json
"package_name": "com.ariaedu.app"
```

Correspond à `build.gradle.kts` :
```kotlin
applicationId = "com.ariaedu.app"
```

## 🔄 Après avoir ajouté le fichier

Rebuild l'application :

```bash
cd gestion_scolaire
flutter clean
flutter pub get
flutter build apk --release
```

## 🐛 Si vous ne trouvez pas "Ajouter une application"

1. Allez dans **Paramètres du projet** (⚙️)
2. Onglet **"General"**
3. Section **"Vos applications"**
4. Si aucune application Android n'existe, cliquez sur **"Ajouter Firebase à votre application"** puis **Android**

## 📝 Notes importantes

- ⚠️ Le fichier `google-services.json` est différent du service account JSON
- ✅ Le fichier est déjà dans `.gitignore` (ne sera pas commité)
- ✅ Une fois ajouté, Firebase sera automatiquement configuré lors du build
- ✅ Les notifications fonctionneront même sans publier sur Google Play

## 🔍 Vérification dans les logs de build

Après avoir ajouté `google-services.json`, lors du build vous devriez voir :

```
> Task :app:processReleaseGoogleServices
Parsing json file: android/app/google-services.json
```

---

**Une fois le fichier ajouté, les notifications push fonctionneront !** 🎉

