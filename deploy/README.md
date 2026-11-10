# Exploitation ARIA

Ce document est la référence actuelle. Le guide historique à la racine décrit des versions antérieures de l'infrastructure.

## Configuration

- Python 3.11, PostgreSQL, Redis, Nginx, environnement virtuel et dépendances `requirements.txt`.
- Copier `env.production.example` vers `/etc/aria/env`, accessible seulement au compte de service. Renseigner une clé Django aléatoire d'au moins 50 caractères, le mot de passe PostgreSQL et les accès SMTP/Wasender renouvelés. Ne pas réutiliser les anciens secrets du dépôt.
- `DEBUG=False`, HTTPS obligatoire ; proxy local de confiance seul autorisé à joindre Daphne. Le fuseau par défaut est `Africa/Dakar`, configurable selon l'exploitation.
- Le SMTP vérifie les certificats. Corriger le certificat serveur plutôt que désactiver sa validation. Les comptes sans adresse de récupération passent par leur administration ; les anciennes pages fondées sur les informations personnelles ne réinitialisent plus les mots de passe.
- Les chemins et l'utilisateur `nick` des unités systemd doivent correspondre à l'installation. Le dossier `logs/` doit exister et être accessible. Les fichiers médias privés doivent être servis via une autorisation applicative, pas par un alias public général.

## Services et Nginx

Installer les trois unités `aria-daphne`, `aria-celery` et `aria-celery-beat`. Une seule instance Beat doit tourner pour le même calendrier.

Inclure `nginx/aria-upstream.conf` dans `http {}`, puis `nginx/aria-websocket.conf` dans le `server {}` HTTPS. Le bloc HTTP doit rediriger vers HTTPS. Garder les locations de statiques indépendantes. Exécuter `nginx -t` avant rechargement.

`GET /health/ready/` renvoie 200 si PostgreSQL et le cache Redis activé répondent, 503 sinon. Il ne remplace pas la supervision des workers, du scheduler, des sauvegardes, des prestataires, de l'espace disque et des erreurs applicatives.

## Livraison

Depuis un répertoire propre : `bash deploy.sh <commit-ou-tag>`. `ARIA_VENV`, `ARIA_BACKUP_DIR` et `ARIA_HEALTH_URL` permettent d'adapter les chemins et la sonde.

Le script sauvegarde avant de changer de version, installe les dépendances, vérifie Django et les migrations, applique les migrations, collecte les statiques et contrôle les services. Une erreur interrompt immédiatement la livraison. Aucun stash n'est effacé, aucune migration n'est marquée artificiellement comme appliquée. La migration exige une sauvegarde et une validation préalable en préproduction ; le déploiement n'est pas atomique et peut nécessiter une fenêtre de maintenance.

Le code précédent est consigné dans `previous-commit.txt`. Après une migration, ne pas revenir aveuglément à l'ancien code : vérifier sa compatibilité avec le schéma ou restaurer ensemble base, médias et code.

## Sauvegarde et restauration

`python manage.py backup_production --output /chemin/prive/horodatage` produit `database.dump` et `media.tar.gz`. Le dossier doit être hors des emplacements servis par le Web, protégé et sauvegardé hors du serveur. Le script ne chiffre pas les archives : le stockage de sauvegarde doit assurer chiffrement et contrôle d'accès.

Tester la restauration dans une base vide isolée : `pg_restore --no-owner --no-acl --dbname=<base_de_recette> database.dump`. Restaurer les médias dans un répertoire isolé, démarrer le commit correspondant, vérifier effectifs, notes, reçus et pièces jointes. Ne pas appliquer cette commande à une base active. Définir et surveiller la rétention et une sauvegarde quotidienne ; la sauvegarde avant livraison ne remplace pas cette planification.

## Contrôles

`python manage.py check --deploy --fail-level WARNING` avec l'environnement de production ; `python manage.py makemigrations --check --dry-run` ; tests isolés via `--settings=school.test_settings`.

Les tests SQLite actuels construisent le schéma depuis les modèles. Le parcours PostgreSQL réel est couvert séparément par `python manage.py test school_admin.tests.test_preproduction_security --settings=school.postgres_test_settings --noinput --buffer`. Une base jetable unique est créée et nettoyée, y compris en cas d'échec de migration. La migration `0001_squashed_0114_initial` remplace les 114 premières migrations pour les installations neuves, dont l'historique contenait plusieurs créations en double. Les fichiers historiques sont conservés pour les installations déjà migrées. Vérifier le plan d'une installation partiellement migrée avant intervention. Le parcours à froid jusqu'à 0242 a été validé localement sur PostgreSQL ; la restauration reste à valider sur l'infrastructure cible.

Le cache PWA est désormais réservé à `/static/`. Les anciennes pages privées sont supprimées à l'activation du nouveau worker. La base Flutter historique sans propriétaire reste sur l'appareil mais n'est plus consultée ; les nouvelles données et actions sont séparées dans des fichiers par identité confirmée par le serveur. Un redémarrage hors ligne exige une vérification en ligne avant de réouvrir ces données. Définir une politique de rétention et de protection du stockage appareil avant diffusion mobile générale.
