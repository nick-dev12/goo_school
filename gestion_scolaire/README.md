# Aria - Application Mobile de Gestion Scolaire

Application mobile Flutter qui embarque l'application web Django Aria (https://aria-edu.com/) dans une WebView avec accès aux fonctionnalités natives du téléphone.

## 🚀 Fonctionnalités

- **WebView complète** : Intègre votre application web Django
- **Accès à la caméra** : Prendre des photos directement depuis l'application
- **Localisation GPS** : Récupérer la position de l'utilisateur
- **Stockage local** : Sauvegarder des données sur le téléphone
- **Notifications** : Afficher des notifications natives
- **Communication JavaScript** : API bidirectionnelle entre la WebView et Flutter

## 📋 Prérequis

- Flutter SDK (version 3.10.1 ou supérieure)
- Android Studio (pour Android)
- Xcode (pour iOS, macOS uniquement)
- Un compte développeur Apple (pour iOS)

## 🔧 Installation

1. **Installer les dépendances Flutter** :
```bash
cd gestion_scolaire
flutter pub get
```

2. **Vérifier la configuration** :
```bash
flutter doctor
```

3. **Lancer l'application** :
```bash
# Sur Android
flutter run

# Sur iOS (macOS uniquement)
flutter run -d ios
```

## 📱 Configuration

### Android

Les permissions sont déjà configurées dans `android/app/src/main/AndroidManifest.xml` :
- Internet
- Caméra
- Stockage
- Localisation
- Notifications

### iOS

Les permissions sont configurées dans `ios/Runner/Info.plist` avec les descriptions appropriées.

## 🔌 API JavaScript

L'application expose une API JavaScript `AriaNative` dans la WebView. Voir le fichier [ARIA_NATIVE_API.md](ARIA_NATIVE_API.md) pour la documentation complète.

### Exemple rapide

```javascript
// Vérifier si l'API est disponible
if (window.AriaNative) {
  // Prendre une photo
  const result = await window.AriaNative.requestCamera();
  
  // Récupérer la localisation
  const location = await window.AriaNative.requestLocation();
  
  // Sauvegarder des données
  await window.AriaNative.saveData({key: 'value'});
  
  // Récupérer des données
  const data = await window.AriaNative.getData('key');
  
  // Afficher une notification
  await window.AriaNative.showNotification('Titre', 'Message');
}
```

## 🏗️ Structure du projet

```
gestion_scolaire/
├── lib/
│   └── main.dart          # Point d'entrée de l'application
├── android/               # Configuration Android
│   └── app/src/main/
│       └── AndroidManifest.xml
├── ios/                   # Configuration iOS
│   └── Runner/
│       └── Info.plist
├── pubspec.yaml           # Dépendances Flutter
└── ARIA_NATIVE_API.md     # Documentation de l'API JavaScript
```

## 🔐 Sécurité

- L'application charge uniquement les URLs du domaine `aria-edu.com`
- Les permissions sont demandées de manière explicite
- Le trafic HTTPS est privilégié (HTTP autorisé pour le développement)

## 🐛 Dépannage

### L'application ne se charge pas

1. Vérifiez votre connexion Internet
2. Vérifiez que le domaine https://aria-edu.com/ est accessible
3. Vérifiez les logs : `flutter logs`

### Les permissions ne fonctionnent pas

1. Vérifiez que les permissions sont bien déclarées dans les fichiers de configuration
2. Sur Android, allez dans Paramètres > Applications > Aria > Permissions
3. Sur iOS, allez dans Réglages > Aria

### L'API JavaScript n'est pas disponible

1. Vérifiez que JavaScript est activé dans la WebView (déjà configuré)
2. Attendez que la page soit complètement chargée avant d'utiliser l'API
3. Vérifiez la console du navigateur pour les erreurs

## 📦 Build pour la production

### Android (APK)

```bash
flutter build apk --release
```

Le fichier APK sera généré dans `build/app/outputs/flutter-apk/app-release.apk`

### Android (App Bundle pour Google Play)

```bash
flutter build appbundle --release
```

### iOS

```bash
flutter build ios --release
```

Puis ouvrez le projet dans Xcode pour finaliser la signature et l'upload sur l'App Store.

## 🔄 Mise à jour de l'URL

Pour changer l'URL de l'application web, modifiez la variable `url` dans `lib/main.dart` :

```dart
final String url = 'https://votre-nouvelle-url.com/';
```

## 📝 Notes

- L'application utilise `flutter_inappwebview` pour une meilleure intégration que `webview_flutter`
- Les fonctionnalités natives sont accessibles via des handlers JavaScript
- Le stockage local utilise `SharedPreferences` de Flutter
- Les notifications peuvent être étendues avec `flutter_local_notifications` pour des notifications push

## 🤝 Support

Pour toute question ou problème, consultez :
- La documentation Flutter : https://docs.flutter.dev/
- La documentation de flutter_inappwebview : https://inappwebview.com/docs/

## 📄 Licence

Ce projet est privé et destiné à l'usage interne de l'établissement scolaire.
