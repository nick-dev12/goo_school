import 'package:flutter/foundation.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import 'local_database.dart';
import 'sync_service.dart';

/// Pont JavaScript <-> Flutter pour le mode hors ligne (option 1).
class OfflineBridge {
  OfflineBridge._();

  static final LocalDatabase _db = LocalDatabase.instance;
  static final SyncService _sync = SyncService.instance;

  static void register(InAppWebViewController controller) {
    controller.addJavaScriptHandler(
      handlerName: 'offlineSave',
      callback: (args) async => _wrap(() async {
        if (args.isEmpty || args[0] is! Map) {
          throw ArgumentError('payload JSON attendu');
        }
        final saved = await _db.enqueue(Map<String, dynamic>.from(args[0] as Map));
        if (_sync.isOnline) {
          await _sync.flushQueue();
        }
        return {
          ...saved,
          'pending': await _db.pendingCount(),
          'online': _sync.isOnline,
        };
      }),
    );

    controller.addJavaScriptHandler(
      handlerName: 'offlinePending',
      callback: (args) async => _wrap(() async {
        return {'items': await _db.pendingActions()};
      }),
    );

    controller.addJavaScriptHandler(
      handlerName: 'offlinePendingCount',
      callback: (args) async => _wrap(() async {
        return {'count': await _db.pendingCount()};
      }),
    );

    controller.addJavaScriptHandler(
      handlerName: 'offlineCachePut',
      callback: (args) async => _wrap(() async {
        if (args.length < 2) {
          throw ArgumentError('resource et records attendus');
        }
        final resource = args[0].toString();
        final records = args[1] is List ? args[1] as List : [args[1]];
        await _db.cachePut(resource, records);
        return {'stored': records.length};
      }),
    );

    controller.addJavaScriptHandler(
      handlerName: 'offlineCacheGet',
      callback: (args) async => _wrap(() async {
        if (args.isEmpty) {
          throw ArgumentError('resource attendue');
        }
        final resource = args[0].toString();
        final serverId = args.length > 1 ? args[1] : null;
        return {'items': await _db.cacheGet(resource, serverId: serverId)};
      }),
    );

    controller.addJavaScriptHandler(
      handlerName: 'offlineSetMeta',
      callback: (args) async => _wrap(() async {
        if (args.length < 2) {
          throw ArgumentError('key et value attendus');
        }
        await _db.setMeta(args[0].toString(), args[1]?.toString());
        return {'ok': true};
      }),
    );

    controller.addJavaScriptHandler(
      handlerName: 'offlineGetMeta',
      callback: (args) async => _wrap(() async {
        if (args.isEmpty) {
          throw ArgumentError('key attendue');
        }
        return {'value': await _db.getMeta(args[0].toString())};
      }),
    );

    controller.addJavaScriptHandler(
      handlerName: 'offlineIsOnline',
      callback: (args) async => _wrap(() async {
        final online = await _sync.refreshOnlineStatus();
        return {'online': online, 'pending': await _db.pendingCount()};
      }),
    );

    controller.addJavaScriptHandler(
      handlerName: 'offlineSyncNow',
      callback: (args) async => _wrap(() async {
        return await _sync.flushQueue();
      }),
    );
  }

  static Future<void> notifyWebView(
    InAppWebViewController? controller, {
    required bool online,
    required int pending,
  }) async {
    if (controller == null) {
      return;
    }
    final script =
        '''
      (function() {
        window.__ARIA_OFFLINE_STATUS = {
          online: ${online ? 'true' : 'false'},
          pending: $pending
        };
        window.dispatchEvent(new CustomEvent('aria-connectivity', {
          detail: window.__ARIA_OFFLINE_STATUS
        }));
      })();
    ''';
    try {
      await controller.evaluateJavascript(source: script);
    } catch (e) {
      debugPrint('⚠️ Notification WebView offline: $e');
    }
  }

  static Future<Map<String, dynamic>> _wrap(
    Future<Map<String, dynamic>> Function() action,
  ) async {
    try {
      final result = await action();
      return {'success': true, ...result};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  /// API JS injectée dans chaque page chargée par la WebView.
  static const javascriptApi = r'''
      (function() {
        function callNative(name) {
          var args = Array.prototype.slice.call(arguments, 1);
          return window.flutter_inappwebview.callHandler.apply(
            window.flutter_inappwebview,
            [name].concat(args)
          ).then(function(result) {
            if (result && result.success === false) {
              throw new Error(result.error || (name + ' failed'));
            }
            return result;
          });
        }

        window.AriaOffline = {
          ready: true,
          storage: 'sqlite',
          save: function(data) { return callNative('offlineSave', data); },
          getPending: function() { return callNative('offlinePending'); },
          pendingCount: function() {
            return callNative('offlinePendingCount').then(function(r) {
              return r.count || 0;
            });
          },
          cachePut: function(resource, records) {
            return callNative('offlineCachePut', resource, records);
          },
          cacheGet: function(resource, serverId) {
            return callNative('offlineCacheGet', resource, serverId).then(function(r) {
              return r.items || [];
            });
          },
          setMeta: function(key, value) { return callNative('offlineSetMeta', key, value); },
          getMeta: function(key) {
            return callNative('offlineGetMeta', key).then(function(r) {
              return r.value;
            });
          },
          isOnline: function() {
            return callNative('offlineIsOnline').then(function(r) {
              return !!r.online;
            });
          },
          syncNow: function() { return callNative('offlineSyncNow'); }
        };

        if (window.AriaNative) {
          window.AriaNative.offline = window.AriaOffline;
          window.AriaNative.offlineReady = true;
        }

        window.dispatchEvent(new CustomEvent('aria-offline-ready'));
        console.log('[AriaOffline] SQLite natif prêt');
      })();
  ''';
}
