# 🔔 Explication du problème des notifications push

## 📱 Pourquoi les notifications ne fonctionnent pas dans l'app mobile ?

### Le problème

Votre application Django utilise **Firebase Cloud Messaging (FCM)** pour envoyer les notifications push. Il y a une différence importante entre :

1. **Navigateur web** : Utilise l'API Web Notifications du navigateur
2. **Application mobile** : Doit utiliser Firebase Cloud Messaging (FCM) natif

### Comment ça fonctionne actuellement

#### Dans le navigateur web ✅
1. L'utilisateur se connecte sur `aria-edu.com`
2. Le JavaScript du navigateur demande la permission de notification
3. Un **token FCM web** est généré et enregistré sur le serveur
4. Quand une note est publiée, Django envoie une notification via FCM
5. Le navigateur reçoit la notification et l'affiche

#### Dans l'application mobile ❌ (avant correction)
1. L'utilisateur ouvre l'application Flutter
2. ❌ **Aucun token FCM n'est généré**
3. ❌ **Le token n'est pas enregistré sur le serveur**
4. Quand une note est publiée, Django cherche le token FCM de l'utilisateur
5. ❌ **Aucun token trouvé** → Aucune notification envoyée

## ✅ Solution implémentée

J'ai créé un service FCM complet qui :

1. **Initialise Firebase** au démarrage de l'application
2. **Demande la permission** de notification à l'utilisateur
3. **Génère un token FCM** unique pour l'appareil
4. **Enregistre le token** sur le serveur Django via l'API `/api/fcm/save-token/`
5. **Reçoit les notifications** même quand l'app est fermée
6. **Gère la navigation** quand l'utilisateur clique sur une notification

## 🔧 Configuration requise

### 1. Fichier `google-services.json` pour Android

Vous devez télécharger le fichier `google-services.json` depuis la console Firebase :

1. Allez sur https://console.firebase.google.com/
2. Sélectionnez votre projet `gestion-scolaire-6945a`
3. Allez dans **Paramètres du projet** (⚙️)
4. Dans l'onglet **Vos applications**, cliquez sur **Ajouter une application**
5. Sélectionnez **Android**
6. Entrez le **Package name** : `com.ariaedu.app`
7. Téléchargez le fichier `google-services.json`
8. Placez-le dans : `gestion_scolaire/android/app/google-services.json`

### 2. Configuration dans `build.gradle.kts`

Le plugin Google Services doit être ajouté (déjà fait si vous suivez les étapes).

### 3. Test

Après avoir ajouté `google-services.json`, rebuild l'application :

```bash
flutter clean
flutter pub get
flutter build apk --release
```

## 📋 Étapes pour que ça fonctionne

### Étape 1 : Télécharger `google-services.json`
- Depuis Firebase Console
- Placer dans `android/app/google-services.json`

### Étape 2 : Rebuild l'application
```bash
flutter clean
flutter pub get
flutter build apk --release
```

### Étape 3 : Installer et tester
1. Installez l'APK sur votre téléphone
2. Connectez-vous avec un compte élève
3. L'application va automatiquement :
   - Demander la permission de notification
   - Générer un token FCM
   - Envoyer le token au serveur

### Étape 4 : Vérifier dans Django
- Allez dans l'admin Django
- Vérifiez la table `fcm_tokens`
- Vous devriez voir un token avec `device_type='android'` pour l'utilisateur

### Étape 5 : Tester une notification
- Connectez-vous en tant que professeur
- Publiez une note
- L'élève devrait recevoir la notification sur son téléphone

## 🔍 Vérification du fonctionnement

### Dans les logs Flutter
Vous devriez voir :
```
✅ Permission de notification accordée
📱 Token FCM obtenu: [token]...
✅ Token FCM envoyé au serveur avec succès
```

### Dans les logs Django
Quand une note est publiée :
```
Envoi de notifications à X token(s)
Notifications envoyées: X succès, 0 échecs
```

## ⚠️ Points importants

1. **Le token FCM est unique par appareil** : Chaque téléphone a son propre token
2. **Le token peut changer** : FCM rafraîchit automatiquement le token si nécessaire
3. **Les notifications fonctionnent même si l'app est fermée** : Grâce au handler en arrière-plan
4. **Pas besoin de publier sur Google Play** : Les notifications FCM fonctionnent même avec un APK installé manuellement

## 🐛 Dépannage

### Les notifications ne s'affichent toujours pas

1. **Vérifiez que `google-services.json` est présent**
   ```bash
   ls android/app/google-services.json
   ```

2. **Vérifiez les logs Flutter**
   - Cherchez les messages avec "FCM" ou "Token"

3. **Vérifiez dans Django Admin**
   - Allez dans `FCM Tokens`
   - Vérifiez qu'un token existe pour l'utilisateur

4. **Vérifiez les permissions**
   - Paramètres Android > Applications > Aria > Notifications
   - Assurez-vous que les notifications sont activées

5. **Testez avec un token manuel**
   - Dans Django Admin, créez un token de test
   - Utilisez l'API de test de notification

## 📚 Documentation supplémentaire

- [Firebase Cloud Messaging](https://firebase.google.com/docs/cloud-messaging)
- [Flutter Firebase Messaging](https://firebase.flutter.dev/docs/messaging/overview)

