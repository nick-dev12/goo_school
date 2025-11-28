# Configuration des icônes et de l'écran de lancement

## ✅ Configuration effectuée

Les fichiers de configuration ont été mis en place dans `pubspec.yaml` :
- Package `flutter_launcher_icons` pour générer les icônes
- Package `flutter_native_splash` pour générer l'écran de lancement
- Icône source copiée dans `assets/images/app_icon.png`
- Logo splash copié dans `assets/images/splash_logo.png`

## 🚀 Commandes à exécuter

Exécutez ces commandes dans le terminal depuis le dossier `gestion_scolaire` :

### 1. Installer les dépendances
```bash
flutter pub get
```

### 2. Générer les icônes d'application
```bash
flutter pub run flutter_launcher_icons
```

Cette commande va :
- Générer toutes les tailles d'icônes nécessaires pour Android
- Générer toutes les tailles d'icônes nécessaires pour iOS
- Créer l'icône adaptative pour Android (Android 8.0+)
- Configurer automatiquement les fichiers AndroidManifest.xml et Info.plist

### 3. Générer l'écran de lancement (splash screen)
```bash
flutter pub run flutter_native_splash:create
```

Cette commande va :
- Créer le splash screen pour Android
- Créer le splash screen pour iOS
- Créer le splash screen pour Android 12+ (avec support des icônes adaptatives)
- Configurer automatiquement les fichiers nécessaires

## 📱 Résultat attendu

Après l'exécution de ces commandes :

### Android
- ✅ Icône visible dans la liste des applications
- ✅ Icône adaptative (Android 8.0+)
- ✅ Écran de lancement au démarrage de l'application
- ✅ Support Android 12+ avec splash screen moderne

### iOS
- ✅ Icône visible sur l'écran d'accueil
- ✅ Écran de lancement au démarrage de l'application
- ✅ Support de toutes les résolutions (iPhone, iPad)

## 🔄 Mise à jour des icônes

Si vous souhaitez changer l'icône plus tard :

1. Remplacez le fichier `assets/images/app_icon.png` (recommandé : 1024x1024px)
2. Remplacez le fichier `assets/images/splash_logo.png` si nécessaire
3. Relancez les commandes de génération :
   ```bash
   flutter pub run flutter_launcher_icons
   flutter pub run flutter_native_splash:create
   ```

## 📝 Notes

- L'icône source doit être au minimum 1024x1024px pour une meilleure qualité
- Le format PNG avec transparence est recommandé
- Les packages génèrent automatiquement toutes les tailles nécessaires
- Les fichiers générés sont automatiquement ajoutés aux projets Android et iOS

## ⚠️ Dépannage

### Les icônes ne s'affichent pas
1. Vérifiez que les commandes ont bien été exécutées
2. Faites un `flutter clean` puis relancez `flutter pub get`
3. Recompilez l'application : `flutter run`

### L'écran de lancement ne s'affiche pas
1. Vérifiez que `flutter_native_splash:create` a bien été exécuté
2. Sur Android, vérifiez que le fichier `android/app/src/main/res/drawable/launch_background.xml` existe
3. Sur iOS, vérifiez que le fichier `ios/Runner/Assets.xcassets/LaunchImage.imageset/` existe

