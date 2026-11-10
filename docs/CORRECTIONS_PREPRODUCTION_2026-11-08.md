# Corrections de l'audit — 8 novembre 2026

## Changements livrés dans le code local

- Récupération de compte extraite de `views.py` dans `security_views.py` : code aléatoire haché, envoyé seulement à l'adresse enregistrée, valable 15 minutes, lié à la session et au mot de passe courant, limité en tentatives et inutilisable après succès. Validation Django des mots de passe. Les six anciennes URLs de vérification/réinitialisation ne peuvent plus modifier de compte.
- Suppression de la route `dev-login`, DEBUG désactivé par défaut, clé Django obligatoire et contrôlée en production. Clé locale aléatoire créée dans `.env`, non affichée et non versionnée. Secrets SMTP, Wasender et PostgreSQL retirés des valeurs de repli du code ; exemples nettoyés.
- TLS SMTP standard avec validation du certificat. La configuration doit maintenant fournir des accès SMTP valides pour permettre la récupération par courriel.
- Sessions limitées par défaut à huit heures, sans surcharge de dix ans lors de la connexion ; les longues sessions existantes sont ramenées à la politique actuelle. Refus des sessions des comptes désactivés. Nettoyage du contexte d'authentification même en cas d'exception.
- Origines WebSocket contrôlées à l'entrée ASGI ; hash de session vérifié pour refuser les sessions antérieures à un changement de mot de passe. Contexte assistant tolérant les profils optionnels absents.
- Tokens FCM supprimables uniquement par leur propriétaire ; réaffectation par un autre compte refusée ; erreurs internes non renvoyées textuellement au client.
- Service worker limité au cache des ressources `/static/`, suppression des anciens caches ARIA, suppression des chemins de repli mélangeant les paramètres de pages privées. Réponses authentifiées marquées `no-store` côté serveur. Une panne de chargement Firebase ne bloque plus l'activation sécurisée du worker.
- Flutter : bases SQLite distinctes par identité fournie par le serveur authentifié, verrouillage au changement de session, contrôle de session pendant la synchronisation et confirmation de l'identité avant envoi de la file. Le fichier historique sans propriétaire n'est plus consulté. Le serveur refuse aussi de rejouer l'action de synchronisation d'un autre compte.
- `--dry-run` propagé aux relances et contrôles des moratoires : pas d'envoi ni d'écriture dans ces branches de simulation.
- Déploiement avec version explicite, refus d'un répertoire modifié, sauvegarde préalable, arrêt sur échec, aucun effacement de stash ni `--fake` automatique. Contrôle Nginx, services et sonde après livraison. Le déploiement n'est pas atomique : prévoir une fenêtre adaptée.
- Séparation des contextes Nginx `http` et `server`, unité Celery Beat et installation correspondante, commande de sauvegarde PostgreSQL/médias, endpoint `/health/ready/` et guide courant `deploy/README.md`.
- Migration initiale consolidée remplaçant 0001–0114 pour permettre une installation neuve. Les migrations originales sont conservées. Le parcours PostgreSQL à froid jusqu'à 0242 a été exécuté avec succès sur une base jetable.
- Actions de dépenses limitées à des alertes « à implémenter » retirées de l'interface. Cela ne constitue pas une implémentation du budget ou des exports manquants.
- Indicateurs de salles inconnus représentés par `None`, sans fausse occupation à zéro ni confusion avec la capacité maximale. Compteurs secrétaire reliés aux données et au bon contexte ; évolutions fictives retirées. Compteur enseignant relié aux notifications non lues.
- Fuseau configurable, `Africa/Dakar` par défaut ; rotation des journaux Django et retrait de traces routinières de session. Protection Git des variantes `.env` ; fins de ligne Unix pour les scripts shell.
- Pipeline CI ajouté pour les contrôles, les tests et les migrations PostgreSQL. Squelette `tests.py` supprimé pour ne plus concurrencer le package `tests/`. Erreur de syntaxe préexistante d'un test de navigation réparée. Plusieurs assertions historiques adaptées aux redirections canoniques, aux templates inclus et au consumer désormais partagé avec les élèves.

## Vérifications effectuées

- Contrôle Django normal : aucun problème.
- Contrôle `check --deploy --fail-level WARNING` avec `DEBUG=False` pour le processus : aucun problème.
- Cohérence modèles/migrations après consolidation : `No changes detected`.
- Compilation Python des modules `school` et `school_admin` : réussie.
- 29 tests sécurité/recouvrement passés lors de la vérification ciblée : récupération, expiration, usage unique, limitation des essais, propriété FCM, cache privé, sessions et origines WebSocket, simulation des moratoires. Un test supplémentaire de compte désactivé a ensuite réussi dans la sélection élargie.
- Scénarios financiers (dont double comptabilisation, transferts, annulation, périodes verrouillées et isolation entre établissements) et smoke tests primaire/collège/lycée/mixte : réussis dans l'exécution ciblée avant l'arrêt sur un test assistant.
- Migrations PostgreSQL complètes sur base vierge, puis 9 tests de récupération : réussis. Base jetable supprimée. La base laissée par le tout premier essai échoué a également été nettoyée.
- Connexion navigateur réelle à `http://127.0.0.1:8000/connexion/` avec le compte de direction des Manguiers : réussie ; tableau de bord « École Primaire Les Manguiers », 10 élèves, une classe CM2 A, année 2026-2027.
- Analyse Dart : aucune erreur ni avertissement bloquant ; des informations de lint préexistantes restent dans `main.dart`. Les deux informations ajoutées sur les accolades dans `sync_service.dart` ont été corrigées.
- Un test Flutter de cloisonnement des comptes a été ajouté. Son exécution est bloquée avant les tests par un téléchargement SQLite natif dont le hash ne correspond pas à celui attendu. La vérification d'intégrité n'a pas été contournée.

La suite élargie a révélé des erreurs préexistantes et des assertions obsolètes, corrigées pendant cette intervention. La dernière relance de la suite complète n'a pas été autorisée ; aucune réussite globale de la suite finale n'est revendiquée. Pour la relancer : `python manage.py test school_admin --top-level-directory . --settings=school.test_settings --noinput --buffer`.

## À terminer avant validation de production

1. Révoquer et remplacer auprès des fournisseurs les secrets anciennement exposés, renseigner les nouveaux secrets du VPS et contrôler l'historique Git. Les enlever du code ne les révoque pas.
2. Relancer la suite complète et corriger les éventuelles dernières régressions. Valider le test Flutter avec une dépendance SQLite dont le téléchargement est conforme.
3. Déployer et valider Nginx, certificats, Redis, worker, Beat et SMTP sur le VPS ; tester la restauration chiffrée/hors site et le retour arrière avec la version du schéma. Aucun changement n'a été appliqué au VPS.
4. Achever la recette par rôle/établissement, les accès aux médias privés, la charge et les cas de concurrence réels. Les tests financiers exécutés ne remplacent pas une validation de charge.
5. Poursuivre le découpage des très grosses vues de direction/enseignement/comptabilité et l'unification progressive de l'identité. L'extraction de la récupération de compte est une première réduction, pas une refonte globale de l'architecture.
6. Décider du périmètre des fonctions retirées, des métriques d'occupation réelle et de la protection/rétention du stockage local mobile. Les fonctions indisponibles ne sont plus présentées comme opérationnelles.

Les modifications qui étaient déjà présentes sur les écrans de notation primaire et d'examens ont été préservées. Aucune migration ni suppression de données n'a été exécutée sur la base applicative des Manguiers. La connexion de test peut actualiser normalement la session et la date de dernière connexion.
