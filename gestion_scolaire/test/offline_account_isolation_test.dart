import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:gestion_scolaire/services/local_database.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'Données et actions séparées par compte ; déconnexion verrouillée',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'aria_isolation_',
      );
      final db = LocalDatabase.instance;
      try {
        await db.init(directory: directory.path);
        expect(db.isReady, false);
        await db.activateAccount('professeur:1:etablissement:10', () => true);
        await db.enqueue({
          'id': 'same-id',
          'resource': 'presence_liste',
          'payload': {'owner': 'A'},
        });
        await db.cachePut('eleves', [
          {'id': 1, 'nom': 'Compte A'},
        ]);

        db.lockAccount();
        expect(db.isReady, false);
        await expectLater(db.pendingActions(), throwsStateError);

        await db.activateAccount('professeur:2:etablissement:20', () => true);
        expect(await db.pendingCount(), 0);
        expect(await db.cacheGet('eleves'), isEmpty);
        await db.enqueue({
          'id': 'same-id',
          'resource': 'presence_liste',
          'payload': {'owner': 'B'},
        });
        await db.cachePut('eleves', [
          {'id': 1, 'nom': 'Compte B'},
        ]);

        await db.activateAccount('professeur:1:etablissement:10', () => true);
        expect(await db.pendingCount(), 1);
        expect((await db.cacheGet('eleves')).single['nom'], 'Compte A');
        expect((await db.pendingActions()).single['payload'], contains('"A"'));

        await db.activateAccount('professeur:3:etablissement:30', () => false);
        expect(db.isReady, false);
      } finally {
        await db.close();
        await directory.delete(recursive: true);
      }
    },
  );
}
