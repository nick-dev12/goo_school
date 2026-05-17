import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

/// Service pour gérer Firebase Cloud Messaging
class FCMService {
  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();
  static String? _fcmToken;
  static String? _serverUrl;
  static Function(String)? _onNotificationTap;

  /// Initialiser les notifications locales
  static Future<void> initializeLocalNotifications() async {
    const androidSettings = AndroidInitializationSettings(
      '@mipmap/ic_launcher',
    );
    const initializationSettings = InitializationSettings(
      android: androidSettings,
    );

    await _localNotifications.initialize(
      initializationSettings,
      onDidReceiveNotificationResponse: (NotificationResponse response) {
        // Gérer le clic sur la notification
        if (response.payload != null) {
          final url = response.payload;
          if (url != null && _onNotificationTap != null) {
            _onNotificationTap!(url);
          }
        }
      },
    );

    // Créer le canal de notification Android
    const androidChannel = AndroidNotificationChannel(
      'aria_channel',
      'Aria Notifications',
      description: 'Notifications de la plateforme Aria',
      importance: Importance.high,
      playSound: true,
      enableVibration: true,
    );

    await _localNotifications
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.createNotificationChannel(androidChannel);
  }

  /// Définir le callback pour la navigation depuis les notifications
  static void setNotificationTapCallback(Function(String url) callback) {
    _onNotificationTap = callback;
  }

  /// Initialiser FCM et obtenir le token
  static Future<String?> initialize(String serverUrl) async {
    print('🔥 FCMService.initialize() appelé avec URL: $serverUrl');
    _serverUrl = serverUrl;

    try {
      // Initialiser les notifications locales
      print('🔥 Initialisation des notifications locales...');
      await initializeLocalNotifications();
      print('✅ Notifications locales initialisées');

      // Demander la permission pour les notifications
      NotificationSettings settings = await _messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
        provisional: false,
      );

      if (settings.authorizationStatus == AuthorizationStatus.authorized) {
        print('✅ Permission de notification accordée');
      } else if (settings.authorizationStatus ==
          AuthorizationStatus.provisional) {
        print('⚠️ Permission de notification provisoire');
      } else {
        print('❌ Permission de notification refusée');
        return null;
      }

      // Obtenir le token FCM
      _fcmToken = await _messaging.getToken();

      if (_fcmToken != null) {
        print('📱 Token FCM obtenu: ${_fcmToken!.substring(0, 20)}...');
        print('📱 TOKEN FCM COMPLET: $_fcmToken'); // Pour debug

        // Sauvegarder le token localement
        await _saveTokenLocally(_fcmToken!);

        // Envoyer le token au serveur
        await _sendTokenToServer(_fcmToken!);

        // Configurer les handlers pour les notifications
        _setupMessageHandlers();

        return _fcmToken;
      } else {
        print('❌ Impossible d\'obtenir le token FCM');
        return null;
      }
    } catch (e) {
      print('❌ Erreur lors de l\'initialisation FCM: $e');
      return null;
    }
  }

  /// Sauvegarder le token localement
  static Future<void> _saveTokenLocally(String token) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('fcm_token', token);
    } catch (e) {
      print('Erreur lors de la sauvegarde locale du token: $e');
    }
  }

  /// Envoyer le token au serveur Django via JavaScript dans la WebView
  /// Note: L'envoi réel se fait via getTokenRegistrationScript() injecté dans la WebView
  static Future<bool> _sendTokenToServer(String token) async {
    if (_serverUrl == null) {
      print('❌ URL du serveur non configurée');
      return false;
    }

    // Le token sera envoyé via JavaScript dans la WebView
    // Cela permet d'utiliser la session authentifiée de l'utilisateur
    print('📤 Token FCM prêt à être envoyé via WebView');
    return true;
  }

  /// Code JavaScript à injecter dans la WebView pour enregistrer le token
  static String getTokenRegistrationScript(String token) {
    final serverUrl = _serverUrl ?? 'https://aria-edu.com';
    return '''
      (function() {
        const token = '$token';
        const deviceType = 'android';
        const deviceName = 'Aria Mobile App';
        const serverUrl = '$serverUrl';
        
        function getCookie(name) {
          let cookieValue = null;
          if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
              const cookie = cookies[i].trim();
              if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
              }
            }
          }
          return cookieValue;
        }
        
        console.log('📤 Envoi du token FCM au serveur...');
        console.log('📤 Token:', token);
        
        // Nettoyer l'URL pour éviter les doubles slashes
        let baseUrl = serverUrl;
        if (baseUrl.endsWith('/')) {
          baseUrl = baseUrl.slice(0, -1);
        }
        const apiUrl = baseUrl + '/api/fcm/save-token/';
        console.log('📤 URL:', apiUrl);
        
        fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || ''
          },
          credentials: 'include',
          body: JSON.stringify({
            token: token,
            device_type: deviceType,
            device_name: deviceName
          })
        })
        .then(response => {
          console.log('📤 Réponse du serveur:', response.status, response.statusText);
          console.log('📤 Content-Type:', response.headers.get('content-type'));
          
          // Vérifier que la réponse est bien du JSON
          const contentType = response.headers.get('content-type');
          if (!contentType || !contentType.includes('application/json')) {
            // Si ce n'est pas du JSON, lire le texte pour voir ce qui est renvoyé
            return response.text().then(text => {
              console.error('❌ Le serveur a renvoyé du HTML au lieu de JSON:');
              console.error('❌ Premiers caractères:', text.substring(0, 200));
              throw new Error('Le serveur a renvoyé du HTML au lieu de JSON. Vérifiez l\\'endpoint Django.');
            });
          }
          
          return response.json();
        })
        .then(data => {
          console.log('✅ Token FCM enregistré avec succès:', data);
        })
        .catch(error => {
          console.error('❌ Erreur enregistrement token FCM:', error);
        });
      })();
    ''';
  }

  /// Afficher une notification locale
  static Future<void> _showLocalNotification(RemoteMessage message) async {
    print('🔔 Affichage de la notification locale...');
    final title = message.notification?.title ?? 'Aria';
    final body = message.notification?.body ?? '';
    final url =
        message.data['redirect_url'] ?? message.data['url'] ?? _serverUrl ?? '';

    print('🔔 Titre: $title');
    print('🔔 Corps: $body');
    print('🔔 URL: $url');

    const androidDetails = AndroidNotificationDetails(
      'aria_channel',
      'Aria Notifications',
      channelDescription: 'Notifications de la plateforme Aria',
      importance: Importance.high,
      priority: Priority.high,
      playSound: true,
      enableVibration: true,
      icon: '@mipmap/ic_launcher',
    );

    const notificationDetails = NotificationDetails(android: androidDetails);

    await _localNotifications.show(
      DateTime.now().millisecondsSinceEpoch.remainder(100000),
      title,
      body,
      notificationDetails,
      payload: url,
    );
  }

  /// Configurer les handlers pour les notifications
  static void _setupMessageHandlers() {
    print('🔔 Configuration des handlers de notification...');

    // Notification reçue quand l'app est au premier plan
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      print('📬 ===== NOTIFICATION REÇUE (APP OUVERTE) =====');
      print('   Titre: ${message.notification?.title}');
      print('   Corps: ${message.notification?.body}');
      print('   Données: ${message.data}');
      print('   Message ID: ${message.messageId}');

      // Afficher la notification localement
      _showLocalNotification(message);
      print('📬 Notification locale affichée');
    });

    // Notification reçue quand l'app est en arrière-plan et l'utilisateur clique dessus
    FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
      print('📬 Notification ouverte depuis l\'arrière-plan:');
      print('   Titre: ${message.notification?.title}');
      print('   Données: ${message.data}');

      // Naviguer vers la page appropriée si nécessaire
      _handleNotificationNavigation(message.data);
    });

    // Vérifier si l'app a été ouverte depuis une notification
    _checkInitialMessage();
  }

  /// Vérifier si l'app a été ouverte depuis une notification
  static Future<void> _checkInitialMessage() async {
    RemoteMessage? initialMessage = await _messaging.getInitialMessage();

    if (initialMessage != null) {
      print('📬 App ouverte depuis une notification:');
      print('   Titre: ${initialMessage.notification?.title}');
      print('   Données: ${initialMessage.data}');

      _handleNotificationNavigation(initialMessage.data);
    }
  }

  /// Gérer la navigation depuis une notification
  static void _handleNotificationNavigation(Map<String, dynamic> data) {
    // Si vous avez une URL de redirection dans les données
    if (data.containsKey('redirect_url') || data.containsKey('url')) {
      final url = data['redirect_url'] ?? data['url'];
      if (url != null && url is String) {
        print('🔗 Navigation vers: $url');
        // Ici, vous pouvez utiliser un callback pour naviguer dans la WebView
      }
    }
  }

  /// Obtenir le token FCM actuel
  static String? getToken() {
    return _fcmToken;
  }

  /// Rafraîchir le token (appelé automatiquement par FCM)
  static void setupTokenRefresh() {
    _messaging.onTokenRefresh.listen((newToken) {
      print('🔄 Token FCM rafraîchi: ${newToken.substring(0, 20)}...');
      _fcmToken = newToken;
      _saveTokenLocally(newToken);
      _sendTokenToServer(newToken);
    });
  }
}

/// Handler pour les notifications en arrière-plan (doit être une fonction top-level)
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();

  print('📬 Notification reçue en arrière-plan:');
  print('   Titre: ${message.notification?.title}');
  print('   Corps: ${message.notification?.body}');
  print('   Données: ${message.data}');

  // Initialiser les notifications locales pour afficher la notification
  final FlutterLocalNotificationsPlugin localNotifications =
      FlutterLocalNotificationsPlugin();

  const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
  const initializationSettings = InitializationSettings(
    android: androidSettings,
  );
  await localNotifications.initialize(initializationSettings);

  // Afficher la notification
  final title = message.notification?.title ?? 'Aria';
  final body = message.notification?.body ?? '';
  final url = message.data['redirect_url'] ?? message.data['url'] ?? '';

  const androidDetails = AndroidNotificationDetails(
    'aria_channel',
    'Aria Notifications',
    channelDescription: 'Notifications de la plateforme Aria',
    importance: Importance.high,
    priority: Priority.high,
    playSound: true,
    enableVibration: true,
    icon: '@mipmap/ic_launcher',
  );

  const notificationDetails = NotificationDetails(android: androidDetails);

  await localNotifications.show(
    DateTime.now().millisecondsSinceEpoch.remainder(100000),
    title,
    body,
    notificationDetails,
    payload: url,
  );
}
