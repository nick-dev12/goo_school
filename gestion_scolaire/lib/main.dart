import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:image_picker/image_picker.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'dart:convert';
import 'services/fcm_service.dart';
import 'dart:async';

// Handler pour les notifications en arrière-plan
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  print(
    '📬 Notification reçue en arrière-plan: ${message.notification?.title}',
  );
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  print('🔥 Démarrage de l\'application...');

  try {
    // Initialiser Firebase
    print('🔥 Initialisation de Firebase...');
    await Firebase.initializeApp();
    print('✅ Firebase initialisé avec succès');
  } catch (e) {
    print('❌ ERREUR lors de l\'initialisation Firebase: $e');
  }

  try {
    // Configurer le handler pour les notifications en arrière-plan
    print('🔥 Configuration du handler en arrière-plan...');
    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
    print('✅ Handler en arrière-plan configuré');
  } catch (e) {
    print('❌ ERREUR lors de la configuration du handler: $e');
  }

  runApp(const AriaApp());
}

class AriaApp extends StatelessWidget {
  const AriaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Aria-edu',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        primarySwatch: Colors.blue,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF3b82f6),
          primary: const Color(0xFF3b82f6),
          secondary: const Color(0xFF7c3aed),
        ),
        useMaterial3: true,
      ),
      home: const WebViewScreen(),
    );
  }
}

class WebViewScreen extends StatefulWidget {
  const WebViewScreen({super.key});

  @override
  State<WebViewScreen> createState() => _WebViewScreenState();
}

class _WebViewScreenState extends State<WebViewScreen>
    with WidgetsBindingObserver {
  InAppWebViewController? webViewController;
  final String url = 'https://aria-edu.com/';
  bool isLoading = true;
  bool isInitialLoad = true; // Pour distinguer le premier chargement
  double progress = 0;
  String? _currentUrl; // Sauvegarder l'URL actuelle

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _requestPermissions();
    _initializeFCM();
    _loadSavedUrl();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  // Observer le cycle de vie de l'application
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    if (state == AppLifecycleState.paused) {
      // Application en arrière-plan - sauvegarder l'URL
      _saveCurrentUrl();
    } else if (state == AppLifecycleState.resumed) {
      // Application revenue au premier plan - restaurer l'URL si nécessaire
      _restoreUrlIfNeeded();
    }
  }

  // Sauvegarder l'URL actuelle
  Future<void> _saveCurrentUrl() async {
    if (webViewController != null) {
      try {
        final currentUrl = await webViewController!.getUrl();
        if (currentUrl != null) {
          _currentUrl = currentUrl.toString();
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('last_webview_url', _currentUrl!);
        }
      } catch (e) {
        print('Erreur lors de la sauvegarde de l\'URL: $e');
      }
    }
  }

  // Charger l'URL sauvegardée
  Future<void> _loadSavedUrl() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedUrl = prefs.getString('last_webview_url');
      if (savedUrl != null && savedUrl.isNotEmpty) {
        _currentUrl = savedUrl;
      }
    } catch (e) {
      print('Erreur lors du chargement de l\'URL sauvegardée: $e');
    }
  }

  // Restaurer l'URL si nécessaire (seulement si différente de l'URL actuelle)
  Future<void> _restoreUrlIfNeeded() async {
    if (webViewController != null && _currentUrl != null) {
      try {
        final currentUrl = await webViewController!.getUrl();
        // Si la WebView est toujours sur la bonne page, ne rien faire
        if (currentUrl != null && currentUrl.toString() == _currentUrl) {
          // La page est déjà chargée, pas besoin de recharger
          return;
        }
        // Sinon, recharger l'URL sauvegardée (utilise le cache si disponible)
        await webViewController!.loadUrl(
          urlRequest: URLRequest(url: WebUri(_currentUrl!)),
        );
      } catch (e) {
        print('Erreur lors de la restauration de l\'URL: $e');
      }
    }
  }

  // Initialiser Firebase Cloud Messaging
  Future<void> _initializeFCM() async {
    print('🔥 Début de l\'initialisation FCM...');
    try {
      // Définir le callback pour la navigation depuis les notifications
      print('🔥 Configuration du callback de navigation...');
      FCMService.setNotificationTapCallback((url) {
        // Naviguer dans la WebView vers l'URL de la notification
        if (webViewController != null && url.isNotEmpty) {
          final fullUrl = url.startsWith('http') ? url : '$url$url';
          webViewController?.loadUrl(
            urlRequest: URLRequest(url: WebUri(fullUrl)),
          );
        }
      });
      print('✅ Callback de navigation configuré');

      // Initialiser FCM avec l'URL du serveur
      print('🔥 Initialisation de FCMService avec URL: $url');
      final token = await FCMService.initialize(url);

      if (token != null) {
        print(
          '✅ FCM initialisé avec succès, token: ${token.substring(0, 20)}...',
        );
      } else {
        print('⚠️ FCM initialisé mais token non obtenu');
      }

      // Configurer le rafraîchissement automatique du token
      print('🔥 Configuration du rafraîchissement automatique du token...');
      FCMService.setupTokenRefresh();
      print('✅ Rafraîchissement automatique configuré');

      print('✅ FCM complètement initialisé avec succès');
    } catch (e, stackTrace) {
      print('❌ ERREUR lors de l\'initialisation FCM: $e');
      print('❌ Stack trace: $stackTrace');
    }
  }

  // Demander les permissions nécessaires
  Future<void> _requestPermissions() async {
    await [
      Permission.camera,
      Permission.storage,
      Permission.location,
      Permission.notification,
    ].request();
  }

  // Gérer les messages JavaScript depuis la WebView
  void _setupJavaScriptHandlers() {
    webViewController?.addJavaScriptHandler(
      handlerName: 'requestCamera',
      callback: (args) async {
        return await _handleCameraRequest();
      },
    );

    webViewController?.addJavaScriptHandler(
      handlerName: 'requestLocation',
      callback: (args) async {
        return await _handleLocationRequest();
      },
    );

    webViewController?.addJavaScriptHandler(
      handlerName: 'saveData',
      callback: (args) async {
        if (args.isNotEmpty) {
          final data = args[0];
          return await _handleSaveData(data);
        }
        return {'success': false, 'error': 'No data provided'};
      },
    );

    webViewController?.addJavaScriptHandler(
      handlerName: 'getData',
      callback: (args) async {
        if (args.isNotEmpty) {
          final key = args[0] as String;
          return await _handleGetData(key);
        }
        return {'success': false, 'error': 'No key provided'};
      },
    );

    webViewController?.addJavaScriptHandler(
      handlerName: 'showNotification',
      callback: (args) async {
        if (args.length >= 2) {
          final title = args[0] as String;
          final body = args[1] as String;
          return await _handleShowNotification(title, body);
        }
        return {'success': false, 'error': 'Invalid parameters'};
      },
    );
  }

  // Gérer la demande de caméra
  Future<Map<String, dynamic>> _handleCameraRequest() async {
    try {
      // Vérifier d'abord le statut de la permission de caméra
      PermissionStatus cameraStatus = await Permission.camera.status;

      // Si la permission n'est pas accordée, la demander
      if (!cameraStatus.isGranted) {
        cameraStatus = await Permission.camera.request();

        // Si la permission est refusée de manière permanente
        if (cameraStatus.isPermanentlyDenied) {
          return {
            'success': false,
            'error':
                'L\'accès à la caméra est refusé de manière permanente. Veuillez l\'activer dans les paramètres de l\'application.',
          };
        }

        // Si la permission est refusée
        if (!cameraStatus.isGranted) {
          return {
            'success': false,
            'error': 'L\'accès à la caméra a été refusé.',
          };
        }
      }

      // Maintenant que la permission est accordée, accéder à la caméra
      final ImagePicker picker = ImagePicker();
      final XFile? image = await picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 85,
      );

      if (image != null) {
        final bytes = await image.readAsBytes();
        final base64Image = base64Encode(bytes);
        return {
          'success': true,
          'image': 'data:image/jpeg;base64,$base64Image',
          'path': image.path,
        };
      }
      return {'success': false, 'error': 'Aucune image sélectionnée'};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  // Gérer la demande de localisation
  Future<Map<String, dynamic>> _handleLocationRequest() async {
    try {
      bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        return {'success': false, 'error': 'Location services are disabled'};
      }

      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          return {'success': false, 'error': 'Location permissions are denied'};
        }
      }

      if (permission == LocationPermission.deniedForever) {
        return {
          'success': false,
          'error': 'Location permissions are permanently denied',
        };
      }

      Position position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );

      return {
        'success': true,
        'latitude': position.latitude,
        'longitude': position.longitude,
        'accuracy': position.accuracy,
        'altitude': position.altitude,
        'speed': position.speed,
        'timestamp': position.timestamp.toIso8601String(),
      };
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  // Sauvegarder des données localement
  Future<Map<String, dynamic>> _handleSaveData(dynamic data) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (data is Map) {
        for (var entry in data.entries) {
          final key = entry.key.toString();
          final value = entry.value;
          if (value is String) {
            await prefs.setString(key, value);
          } else if (value is int) {
            await prefs.setInt(key, value);
          } else if (value is double) {
            await prefs.setDouble(key, value);
          } else if (value is bool) {
            await prefs.setBool(key, value);
          } else {
            await prefs.setString(key, jsonEncode(value));
          }
        }
        return {'success': true};
      }
      return {'success': false, 'error': 'Invalid data format'};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  // Récupérer des données localement
  Future<Map<String, dynamic>> _handleGetData(String key) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final value = prefs.get(key);
      if (value != null) {
        return {'success': true, 'data': value};
      }
      return {'success': false, 'error': 'Key not found'};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  // Afficher une notification
  Future<Map<String, dynamic>> _handleShowNotification(
    String title,
    String body,
  ) async {
    try {
      // Ici vous pouvez intégrer flutter_local_notifications
      // Pour l'instant, on retourne un succès
      // Vous pouvez aussi afficher un snackbar ou dialog
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('$title: $body'),
            duration: const Duration(seconds: 3),
          ),
        );
      }
      return {'success': true};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  // Injecter le code JavaScript pour la communication
  Future<void> _injectJavaScript() async {
    const jsCode = '''
      (function() {
        // Créer l'objet AriaNative pour la communication
        window.AriaNative = {
          // Demander l'accès à la caméra
          requestCamera: function() {
            return new Promise((resolve, reject) => {
              window.flutter_inappwebview.callHandler('requestCamera')
                .then(result => {
                  if (result.success) {
                    resolve(result);
                  } else {
                    reject(new Error(result.error || 'Camera request failed'));
                  }
                })
                .catch(error => reject(error));
            });
          },
          
          // Demander la localisation
          requestLocation: function() {
            return new Promise((resolve, reject) => {
              window.flutter_inappwebview.callHandler('requestLocation')
                .then(result => {
                  if (result.success) {
                    resolve(result);
                  } else {
                    reject(new Error(result.error || 'Location request failed'));
                  }
                })
                .catch(error => reject(error));
            });
          },
          
          // Sauvegarder des données
          saveData: function(data) {
            return new Promise((resolve, reject) => {
              window.flutter_inappwebview.callHandler('saveData', data)
                .then(result => {
                  if (result.success) {
                    resolve(result);
                  } else {
                    reject(new Error(result.error || 'Save failed'));
                  }
                })
                .catch(error => reject(error));
            });
          },
          
          // Récupérer des données
          getData: function(key) {
            return new Promise((resolve, reject) => {
              window.flutter_inappwebview.callHandler('getData', key)
                .then(result => {
                  if (result.success) {
                    resolve(result.data);
                  } else {
                    reject(new Error(result.error || 'Get failed'));
                  }
                })
                .catch(error => reject(error));
            });
          },
          
          // Afficher une notification
          showNotification: function(title, body) {
            return new Promise((resolve, reject) => {
              window.flutter_inappwebview.callHandler('showNotification', title, body)
                .then(result => {
                  if (result.success) {
                    resolve(result);
                  } else {
                    reject(new Error(result.error || 'Notification failed'));
                  }
                })
                .catch(error => reject(error));
            });
          }
        };
        
        console.log('AriaNative API initialized');
      })();
    ''';

    await webViewController?.evaluateJavascript(source: jsCode);
  }

  // Enregistrer le token FCM dans la WebView (utilise la session authentifiée)
  Future<void> _registerFCMTokenInWebView() async {
    try {
      final fcmToken = FCMService.getToken();
      if (fcmToken != null) {
        // Injecter le script pour enregistrer le token via la WebView
        final script = FCMService.getTokenRegistrationScript(fcmToken);
        await webViewController?.evaluateJavascript(source: script);
        print('📤 Token FCM envoyé via WebView');
      }
    } catch (e) {
      print('❌ Erreur lors de l\'enregistrement du token FCM: $e');
    }
  }

  // Gérer le bouton retour Android
  Future<bool> _handleBackButton() async {
    if (webViewController != null) {
      // Vérifier si la WebView peut revenir en arrière
      final canGoBack = await webViewController!.canGoBack();
      if (canGoBack) {
        // Revenir à la page précédente dans l'historique
        await webViewController!.goBack();
        return false; // Empêcher la fermeture de l'app
      }
    }
    // Si on ne peut pas revenir en arrière, fermer l'application
    return true; // Permettre la fermeture de l'app
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false, // Empêcher la fermeture automatique
      onPopInvoked: (didPop) async {
        if (!didPop) {
          final shouldPop = await _handleBackButton();
          if (shouldPop && context.mounted) {
            SystemNavigator.pop(); // Fermer l'application
          }
        }
      },
      child: Scaffold(
        // Désactiver la résize automatique pour améliorer les performances du clavier
        resizeToAvoidBottomInset: false,
        body: Stack(
          children: [
            SafeArea(
              child: InAppWebView(
                initialUrlRequest: URLRequest(url: WebUri(_currentUrl ?? url)),
                initialSettings: InAppWebViewSettings(
                  javaScriptEnabled: true,
                  domStorageEnabled: true,
                  databaseEnabled: true,
                  useShouldOverrideUrlLoading: true,
                  mediaPlaybackRequiresUserGesture: false,
                  allowsInlineMediaPlayback: true,
                  iframeAllow: "camera; microphone",
                  iframeAllowFullscreen: true,
                  // Désactivé pour améliorer les performances
                  useOnLoadResource: false,
                  useOnDownloadStart: false,
                  useShouldInterceptRequest: false,
                  thirdPartyCookiesEnabled: true,
                  cacheEnabled: true,
                  clearCache: false,
                  transparentBackground: false,
                  supportZoom: true,
                  builtInZoomControls: false,
                  displayZoomControls: false,
                  // Optimisations pour le clavier
                  verticalScrollBarEnabled: true,
                  horizontalScrollBarEnabled: true,
                  // Désactiver les animations inutiles
                  disableVerticalScroll: false,
                  disableHorizontalScroll: false,
                ),
                onWebViewCreated: (controller) {
                  webViewController = controller;
                  _setupJavaScriptHandlers();
                },
                onLoadStart: (controller, url) {
                  setState(() {
                    isLoading = true;
                  });
                },
                onLoadStop: (controller, url) async {
                  setState(() {
                    isLoading = false;
                    isInitialLoad =
                        false; // Après le premier chargement, ce n'est plus le chargement initial
                  });
                  // Sauvegarder l'URL actuelle
                  if (url != null) {
                    _currentUrl = url.toString();
                    await _saveCurrentUrl();
                  }
                  await _injectJavaScript();
                  // Envoyer le token FCM après le chargement de la page
                  await _registerFCMTokenInWebView();
                },
                onProgressChanged: (controller, progress) {
                  // Ne mettre à jour que si la différence est significative pour éviter trop de rebuilds
                  final newProgress = progress / 100;
                  if ((newProgress - this.progress).abs() > 0.01) {
                    setState(() {
                      this.progress = newProgress;
                    });
                  }
                },
                onPermissionRequest: (controller, request) async {
                  // Autoriser caméra/micro par défaut pour la WebView
                  return PermissionResponse(
                    resources: request.resources,
                    action: PermissionResponseAction.GRANT,
                  );
                },
                onReceivedError: (controller, request, error) {
                  print('WebView Error: ${error.description}');
                },
                shouldOverrideUrlLoading: (controller, navigationAction) async {
                  final uri = navigationAction.request.url;
                  if (uri != null &&
                      uri.toString().startsWith('https://aria-edu.com')) {
                    return NavigationActionPolicy.ALLOW;
                  }
                  return NavigationActionPolicy.ALLOW;
                },
              ),
            ),
            // Loader plein écran uniquement au lancement
            if (isLoading && isInitialLoad) _AriaLoader(progress: progress),
            // Barre de progression discrète en haut pour les navigations
            if (isLoading && !isInitialLoad)
              _TopProgressBar(progress: progress),
          ],
        ),
      ),
    );
  }
}

// Widget personnalisé pour le loader avec logo et barre de progression
class _AriaLoader extends StatefulWidget {
  final double progress;

  const _AriaLoader({required this.progress});

  @override
  State<_AriaLoader> createState() => _AriaLoaderState();
}

class _AriaLoaderState extends State<_AriaLoader>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat(reverse: true);

    _scaleAnimation = Tween<double>(begin: 0.95, end: 1.05).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF3b82f6), Color(0xFF1d4ed8)],
        ),
      ),
      child: SafeArea(
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Logo avec animation
              AnimatedBuilder(
                animation: _animationController,
                builder: (context, child) {
                  return Transform.scale(
                    scale: _scaleAnimation.value,
                    child: Container(
                      width: 120,
                      height: 120,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(24),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.2),
                            blurRadius: 20,
                            offset: const Offset(0, 10),
                          ),
                        ],
                      ),
                      padding: const EdgeInsets.all(20),
                      child: Image.asset(
                        'assets/images/app_icon.png',
                        fit: BoxFit.contain,
                        errorBuilder: (context, error, stackTrace) {
                          // Fallback si l'image n'est pas trouvée
                          return const Icon(
                            Icons.school,
                            size: 60,
                            color: Color(0xFF3b82f6),
                          );
                        },
                      ),
                    ),
                  );
                },
              ),
              const SizedBox(height: 40),
              // Texte de chargement
              const Text(
                'Aria',
                style: TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                  letterSpacing: 2,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Chargement de votre plateforme...',
                style: TextStyle(
                  fontSize: 16,
                  color: Colors.white.withOpacity(0.9),
                  fontWeight: FontWeight.w300,
                ),
              ),
              const SizedBox(height: 50),
              // Barre de progression stylée
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 60),
                child: Column(
                  children: [
                    // Barre de progression principale
                    Container(
                      height: 8,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(10),
                        color: Colors.white.withOpacity(0.2),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.1),
                            blurRadius: 4,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: Stack(
                        children: [
                          // Fond
                          Container(
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(10),
                              color: Colors.white.withOpacity(0.2),
                            ),
                          ),
                          // Progression
                          FractionallySizedBox(
                            widthFactor: widget.progress.clamp(0.0, 1.0),
                            child: Container(
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(10),
                                gradient: const LinearGradient(
                                  colors: [Colors.white, Color(0xFFa5d6ff)],
                                ),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.white.withOpacity(0.5),
                                    blurRadius: 8,
                                    spreadRadius: 1,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    // Pourcentage
                    Text(
                      '${(widget.progress * 100).toInt()}%',
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.white.withOpacity(0.8),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 40),
              // Indicateur de chargement animé
              SizedBox(
                width: 30,
                height: 30,
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(
                    Colors.white.withOpacity(0.8),
                  ),
                  strokeWidth: 3,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// Barre de progression discrète en haut de l'écran pour les navigations
class _TopProgressBar extends StatelessWidget {
  final double progress;

  const _TopProgressBar({required this.progress});

  @override
  Widget build(BuildContext context) {
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        height: 3,
        child: Stack(
          children: [
            // Barre de progression
            FractionallySizedBox(
              widthFactor: progress.clamp(0.0, 1.0),
              child: Container(
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF3b82f6), Color(0xFF1d4ed8)],
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF3b82f6).withOpacity(0.6),
                      blurRadius: 6,
                      spreadRadius: 1,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
