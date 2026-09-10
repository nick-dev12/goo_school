import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'local_database.dart';

/// Synchronise la file SQLite locale vers Django dès que le réseau revient.
class SyncService {
  SyncService._();

  static final SyncService instance = SyncService._();

  final LocalDatabase _db = LocalDatabase.instance;
  final Connectivity _connectivity = Connectivity();

  StreamSubscription<List<ConnectivityResult>>? _subscription;
  bool _flushing = false;
  bool _online = true;
  String _baseUrl = 'https://aria-edu.com';
  String? _cookieHeader;
  String? _csrfToken;

  void Function(bool online, int pending)? onStatusChanged;

  bool get isOnline => _online;

  void configure({required String baseUrl, String? cookieHeader}) {
    _baseUrl = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    if (cookieHeader != null) {
      setCookieHeader(cookieHeader);
    }
  }

  void setCookieHeader(String? cookieHeader) {
    _cookieHeader = cookieHeader;
    _csrfToken = _extractCookieValue(cookieHeader, 'csrftoken');
  }

  Future<void> start() async {
    await _refreshConnectivity();
    _subscription ??= _connectivity.onConnectivityChanged.listen((results) {
      final nextOnline = _hasNetwork(results);
      final changed = nextOnline != _online;
      _online = nextOnline;
      if (changed) {
        debugPrint(
          nextOnline
              ? '🌐 Connexion rétablie — tentative de sync'
              : '📴 Mode hors ligne',
        );
        _notify();
      }
      if (nextOnline) {
        unawaited(flushQueue());
        unawaited(pull());
      }
    });
  }

  Future<void> stop() async {
    await _subscription?.cancel();
    _subscription = null;
  }

  Future<bool> refreshOnlineStatus() async {
    await _refreshConnectivity();
    return _online;
  }

  Map<String, String> _headers({bool jsonBody = false}) {
    return {
      'Accept': 'application/json',
      if (jsonBody) 'Content-Type': 'application/json; charset=utf-8',
      if (_cookieHeader != null && _cookieHeader!.isNotEmpty)
        'Cookie': _cookieHeader!,
      if (_csrfToken != null && _csrfToken!.isNotEmpty)
        'X-CSRFToken': _csrfToken!,
      'Referer': '$_baseUrl/',
    };
  }

  Future<Map<String, dynamic>> flushQueue() async {
    if (_flushing) {
      return {'success': true, 'skipped': true, 'reason': 'already_running'};
    }
    if (!_online) {
      return {'success': false, 'error': 'offline'};
    }
    if (!_db.isReady) {
      return {'success': false, 'error': 'database_not_ready'};
    }

    _flushing = true;
    var synced = 0;
    var failed = 0;

    try {
      final items = await _db.pendingActions();
      if (items.isEmpty) {
        await _db.setMeta(
          'last_sync_at',
          DateTime.now().toUtc().toIso8601String(),
        );
        await _notify();
        return {'success': true, 'synced': 0, 'failed': 0};
      }

      final uri = Uri.parse('$_baseUrl/api/sync/push/');
      final response = await http
          .post(
            uri,
            headers: _headers(jsonBody: true),
            body: jsonEncode({
              'items': items
                  .map(
                    (row) => {
                      'id': row['id'],
                      'action': row['action'],
                      'resource': row['resource'],
                      'payload': _decodePayload(row['payload']),
                      'created_at': row['created_at'],
                    },
                  )
                  .toList(),
            }),
          )
          .timeout(const Duration(seconds: 30));

      if (response.statusCode == 401 || response.statusCode == 403) {
        debugPrint('⚠️ Sync refusée (${response.statusCode}) — session à renouveler');
        return {
          'success': false,
          'error': 'unauthorized',
          'pending': items.length,
        };
      }

      if (response.statusCode == 404 ||
          response.statusCode == 405 ||
          response.statusCode == 501) {
        debugPrint(
          'ℹ️ Endpoint /api/sync/push/ pas encore disponible (${response.statusCode})',
        );
        return {
          'success': false,
          'error': 'api_not_ready',
          'pending': items.length,
        };
      }

      if (response.statusCode >= 200 && response.statusCode < 300) {
        final body = _tryDecode(response.body);
        final results = body['results'];
        if (results is List) {
          for (final raw in results) {
            if (raw is! Map) {
              continue;
            }
            final id = raw['id']?.toString();
            if (id == null || id.isEmpty) {
              continue;
            }
            if (raw['ok'] == true || raw['status'] == 'synced') {
              await _db.markSynced(id);
              synced += 1;
            } else {
              await _db.markFailed(id, raw['error']?.toString() ?? 'rejected');
              failed += 1;
            }
          }
        } else {
          for (final row in items) {
            await _db.markSynced(row['id'].toString());
            synced += 1;
          }
        }
        await _db.setMeta(
          'last_sync_at',
          DateTime.now().toUtc().toIso8601String(),
        );
      } else {
        final error = 'HTTP ${response.statusCode}: ${response.body}';
        for (final row in items) {
          await _db.markFailed(row['id'].toString(), error);
          failed += 1;
        }
      }
    } catch (e) {
      debugPrint('⚠️ Sync flush interrompu : $e');
      return {'success': false, 'error': e.toString(), 'pending': true};
    } finally {
      _flushing = false;
      await _notify();
    }

    return {
      'success': failed == 0,
      'synced': synced,
      'failed': failed,
    };
  }

  Future<Map<String, dynamic>> pull({
    List<String> resources = const ['classes', 'eleves', 'presences'],
  }) async {
    if (!_online || !_db.isReady) {
      return {'success': false, 'error': 'offline_or_db'};
    }
    if (_cookieHeader == null || _cookieHeader!.isEmpty) {
      return {'success': false, 'error': 'no_session'};
    }

    try {
      final uri = Uri.parse('$_baseUrl/api/sync/pull/').replace(
        queryParameters: {'resources': resources.join(',')},
      );
      final response = await http
          .get(uri, headers: _headers())
          .timeout(const Duration(seconds: 30));

      if (response.statusCode < 200 || response.statusCode >= 300) {
        return {
          'success': false,
          'error': 'HTTP ${response.statusCode}',
        };
      }

      final body = _tryDecode(response.body);
      final data = body['data'];
      if (data is! Map) {
        return {'success': false, 'error': 'invalid_payload'};
      }

      for (final resource in resources) {
        final records = data[resource];
        if (records is List) {
          await _db.cachePut(resource, records);
        }
      }
      await _db.setMeta(
        'last_pull_at',
        DateTime.now().toUtc().toIso8601String(),
      );
      return {'success': true};
    } catch (e) {
      debugPrint('⚠️ Sync pull interrompu : $e');
      return {'success': false, 'error': e.toString()};
    }
  }

  Future<void> _refreshConnectivity() async {
    try {
      final results = await _connectivity.checkConnectivity();
      _online = _hasNetwork(results);
    } catch (e) {
      debugPrint('⚠️ Impossible de lire l\'état réseau : $e');
      _online = true;
    }
    await _notify();
  }

  bool _hasNetwork(List<ConnectivityResult> results) {
    if (results.isEmpty) {
      return false;
    }
    return results.any((result) => result != ConnectivityResult.none);
  }

  Future<void> _notify() async {
    final pending = _db.isReady ? await _db.pendingCount() : 0;
    onStatusChanged?.call(_online, pending);
  }

  Object? _decodePayload(Object? payload) {
    if (payload is String) {
      try {
        return jsonDecode(payload);
      } catch (_) {
        return payload;
      }
    }
    return payload;
  }

  Map<String, dynamic> _tryDecode(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      if (decoded is Map) {
        return Map<String, dynamic>.from(decoded);
      }
    } catch (_) {}
    return {};
  }

  String? _extractCookieValue(String? header, String name) {
    if (header == null || header.isEmpty) {
      return null;
    }
    for (final part in header.split(';')) {
      final cookie = part.trim();
      final separator = cookie.indexOf('=');
      if (separator <= 0) {
        continue;
      }
      if (cookie.substring(0, separator) == name) {
        return cookie.substring(separator + 1);
      }
    }
    return null;
  }
}
