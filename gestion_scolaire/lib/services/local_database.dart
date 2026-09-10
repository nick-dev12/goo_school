import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:uuid/uuid.dart';

/// Base SQLite native de l'application (mobile et desktop).
///
/// Fichier : aria_local.db
/// - Android / iOS : dossier databases de l'app
/// - Windows / macOS / Linux : Application Support
class LocalDatabase {
  LocalDatabase._();

  static final LocalDatabase instance = LocalDatabase._();
  static const int _schemaVersion = 1;
  static const String _fileName = 'aria_local.db';
  static const _uuid = Uuid();

  Database? _db;

  Database get db {
    final database = _db;
    if (database == null) {
      throw StateError(
        'LocalDatabase n\'est pas initialisée. Appelez init() d\'abord.',
      );
    }
    return database;
  }

  bool get isReady => _db != null;

  /// À appeler une fois au démarrage, avant runApp.
  Future<void> init() async {
    if (_db != null) {
      return;
    }

    _configureFactory();
    final dbPath = await _resolveDbPath();
    _db = await openDatabase(
      dbPath,
      version: _schemaVersion,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );
    debugPrint('✅ SQLite local prêt : $dbPath');
  }

  Future<void> close() async {
    await _db?.close();
    _db = null;
  }

  void _configureFactory() {
    if (kIsWeb) {
      return;
    }
    if (Platform.isWindows || Platform.isLinux || Platform.isMacOS) {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
    }
  }

  Future<String> _resolveDbPath() async {
    if (!kIsWeb &&
        (Platform.isWindows || Platform.isLinux || Platform.isMacOS)) {
      final dir = await getApplicationSupportDirectory();
      if (!await dir.exists()) {
        await dir.create(recursive: true);
      }
      return p.join(dir.path, _fileName);
    }
    final databasesPath = await getDatabasesPath();
    return p.join(databasesPath, _fileName);
  }

  Future<void> _onCreate(Database db, int version) async {
    await db.execute('''
      CREATE TABLE sync_queue (
        id TEXT PRIMARY KEY,
        action TEXT NOT NULL,
        resource TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        retries INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        last_error TEXT
      )
    ''');
    await db.execute('''
      CREATE TABLE cache_records (
        id TEXT PRIMARY KEY,
        resource TEXT NOT NULL,
        server_id INTEGER,
        payload TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        synced_at TEXT
      )
    ''');
    await db.execute('''
      CREATE TABLE sync_metadata (
        key TEXT PRIMARY KEY,
        value TEXT
      )
    ''');
    await db.execute(
      'CREATE INDEX idx_sync_queue_status ON sync_queue(status)',
    );
    await db.execute(
      'CREATE INDEX idx_cache_resource ON cache_records(resource)',
    );
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    // Migrations futures : version 2, 3, ...
  }

  Future<Map<String, dynamic>> enqueue(Map<String, dynamic> data) async {
    final id = (data['id'] ?? data['client_uuid'] ?? _uuid.v4()).toString();
    final now = DateTime.now().toUtc().toIso8601String();
    final action = (data['action'] ?? 'CREATE').toString().toUpperCase();
    final resource = (data['resource'] ?? '').toString();
    if (resource.isEmpty) {
      throw ArgumentError('resource est obligatoire');
    }

    final payload = data['payload'];
    final payloadJson = payload is String
        ? payload
        : jsonEncode(payload ?? data);

    await db.insert('sync_queue', {
      'id': id,
      'action': action,
      'resource': resource,
      'payload': payloadJson,
      'created_at': data['created_at']?.toString() ?? now,
      'updated_at': data['updated_at']?.toString() ?? now,
      'retries': 0,
      'status': 'pending',
    }, conflictAlgorithm: ConflictAlgorithm.replace);

    return {
      'id': id,
      'action': action,
      'resource': resource,
      'status': 'pending',
    };
  }

  Future<List<Map<String, dynamic>>> pendingActions({int limit = 100}) async {
    return db.query(
      'sync_queue',
      where: 'status = ?',
      whereArgs: ['pending'],
      orderBy: 'created_at ASC',
      limit: limit,
    );
  }

  Future<int> pendingCount() async {
    final rows = await db.rawQuery(
      "SELECT COUNT(*) AS c FROM sync_queue WHERE status = 'pending'",
    );
    return (rows.first['c'] as int?) ?? 0;
  }

  Future<void> markSynced(String id) async {
    await db.update(
      'sync_queue',
      {
        'status': 'synced',
        'updated_at': DateTime.now().toUtc().toIso8601String(),
        'last_error': null,
      },
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<void> markFailed(String id, String error) async {
    await db.rawUpdate(
      '''
      UPDATE sync_queue
      SET retries = retries + 1,
          last_error = ?,
          updated_at = ?,
          status = CASE WHEN retries + 1 >= 8 THEN 'failed' ELSE 'pending' END
      WHERE id = ?
      ''',
      [error, DateTime.now().toUtc().toIso8601String(), id],
    );
  }

  Future<void> cachePut(String resource, List<dynamic> records) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final batch = db.batch();
    for (final raw in records) {
      if (raw is! Map) {
        continue;
      }
      final record = Map<String, dynamic>.from(raw);
      final id =
          (record['id'] ??
                  record['client_uuid'] ??
                  record['server_id'] ??
                  _uuid.v4())
              .toString();
      batch.insert('cache_records', {
        'id': id,
        'resource': resource,
        'server_id': record['server_id'] ?? record['id'],
        'payload': jsonEncode(record),
        'updated_at': record['updated_at']?.toString() ?? now,
        'synced_at': now,
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await batch.commit(noResult: true);
  }

  Future<List<Map<String, dynamic>>> cacheGet(
    String resource, {
    Object? serverId,
  }) async {
    final rows = serverId == null
        ? await db.query(
            'cache_records',
            where: 'resource = ?',
            whereArgs: [resource],
            orderBy: 'updated_at DESC',
          )
        : await db.query(
            'cache_records',
            where: 'resource = ? AND server_id = ?',
            whereArgs: [resource, serverId],
          );

    return rows.map((row) {
      final payload = row['payload'];
      if (payload is String) {
        try {
          return Map<String, dynamic>.from(jsonDecode(payload) as Map);
        } catch (_) {
          return Map<String, dynamic>.from(row);
        }
      }
      return Map<String, dynamic>.from(row);
    }).toList();
  }

  Future<void> setMeta(String key, String? value) async {
    await db.insert('sync_metadata', {
      'key': key,
      'value': value,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<String?> getMeta(String key) async {
    final rows = await db.query(
      'sync_metadata',
      where: 'key = ?',
      whereArgs: [key],
      limit: 1,
    );
    if (rows.isEmpty) {
      return null;
    }
    return rows.first['value'] as String?;
  }
}
