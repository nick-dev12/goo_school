# Audit de préparation à la production — ARIA / Goo School

Date : 8 novembre 2026. Audit du code local, comprenant les modifications présentes au démarrage. Aucun code métier modifié, aucun envoi de message, aucune migration ou opération destructive exécutée.

## Verdict

La mise en production de cette version est déconseillée avant correction des points P0. Le projet possède déjà une base importante : services métier, migrations, tests spécialisés, protection CSRF, contrôles d'établissement dans plusieurs vues, Redis, Channels et Celery. Mais ces éléments coexistent avec des failles d'authentification, des fonctions inachevées et un déploiement insuffisamment fiable.

Ce document recense les anomalies identifiées pendant cette revue ; il ne certifie pas l'exhaustivité du projet ni l'état du serveur distant. P0 : bloquant avant exposition ; P1 : correction prioritaire avant ouverture générale ; P2 : consolidation.

## Anomalies confirmées

### 1. P0 — Réinitialisation de mots de passe sans preuve d'autorisation

Sources : `school_admin/views.py:543`, `:733`, `:913` ; routes `school_admin/urls.py:99-104` ; exemption d'authentification dans `school_admin/middleware.py` pour `/password-reset/`.

Les vues finales professeur, élève et parent recherchent le compte par matricule puis acceptent un nouveau mot de passe. Elles ne vérifient ni jeton signé, ni OTP, ni marqueur de session prouvant l'étape précédente. La vérification d'informations personnelles n'accorde d'ailleurs aucune autorisation persistante. Un visiteur connaissant un matricule peut donc soumettre directement le formulaire final. La protection CSRF ne prouve pas l'identité du titulaire.

Correction : imposer une preuve de possession via un canal vérifié, un jeton expirant à usage unique lié au compte et à l'opération ; invalider la preuve après usage. Ajouter des tests d'accès direct, d'expiration et de réutilisation sur les trois parcours.

### 2. P0 — Secrets et identifiants dans le code

Source : `school/settings.py`, notamment lignes 57, 173, section Wasender et ligne 502 ; exemples également présents dans `README_DEPLOIEMENT.md`.

Mot de passe SMTP en clair, jeton Wasender de repli en clair, mot de passe PostgreSQL de repli et clé Django de repli sont présents. Leur validité actuelle n'a pas été testée. Les variables d'environnement ne suffisent pas à supprimer l'exposition passée.

Correction : révoquer/remplacer les valeurs encore utilisables, les sortir du code et de la documentation, examiner l'historique Git, rendre les secrets indispensables au démarrage en production. Ne pas confondre ces secrets serveur avec la configuration publique Firebase du navigateur.

### 3. P0 — Connexion sans mot de passe si DEBUG est activé

Sources : `school/settings.py:60`, `school_admin/views.py:138`, `school_admin/urls.py:88`, `school_admin/middleware.py:108`.

DEBUG vaut True par défaut. La route `dev-login` authentifie sans mot de passe quand DEBUG est vrai ; aucune restriction d'adresse locale n'est visible dans cette vue. Une erreur de configuration transforme donc une aide de développement en accès aux comptes. Le contrôle DEBUG existe bien, mais ne suffit pas avec ce défaut permissif.

Correction : DEBUG=False par défaut, refus de démarrage en configuration dangereuse et suppression de cette route des déploiements de production.

### 4. P1 — Vérification TLS SMTP désactivée

Source : `school_admin/email_backends.py`, classe `CustomSMTPEmailBackend`, utilisée par les settings.

`check_hostname=False` et `CERT_NONE` désactivent l'authentification du serveur SMTP, y compris pendant STARTTLS. Cela expose identifiants et courriels à une interception réseau.

Correction : rétablir la vérification standard et corriger la chaîne de certificats du serveur.

### 5. P1 — Cache de pages privées sans cloisonnement par compte

Source : `school_admin/static/school_admin/service-worker.js:231` et suivantes.

Le service worker place les réponses HTML 200 dans un cache commun par URL, sans vérifier `Cache-Control: no-store` ni identifier le compte. En cas de panne réseau, il cherche aussi des pages sans leurs paramètres, puis par chemin. Il peut ainsi restituer des informations d'un ancien compte sur un appareil partagé, ou une variante incorrecte de page. Le fichier examiné ne prévoit pas de purge liée à la déconnexion.

Correction : exclure les pages et API sensibles ; si le hors ligne métier est nécessaire, concevoir explicitement le cloisonnement, l'expiration et la purge. Vérifier l'enregistrement et la portée du worker effectivement distribué, puis tester changement de compte et déconnexion hors ligne.

### 6. P1 — Déploiement poursuivi après échec des migrations

Source : `deploy.sh`, traitement de `MIGRATE_EXIT_CODE`.

Le script continue la collecte des statiques et le redémarrage malgré une migration échouée, puis peut annoncer un succès. Il suggère également une migration précise avec `--fake`. Le code déployé peut alors être incompatible avec la base.

Correction : arrêter immédiatement, sauvegarder avant migration, valider le schéma et définir une procédure de retour arrière adaptée aux migrations.

### 7. P1 — Suppression automatique des modifications locales au déploiement

Source : `deploy.sh`, `git stash push` puis `git stash drop`.

Le script supprime le stash qu'il vient de créer au lieu de préserver les modifications. Il déploie également directement par `git pull` dans le répertoire actif.

Correction : refuser un répertoire modifié et déployer une version identifiée dans un répertoire de release ; préserver les données locales et garder la release précédente.

### 8. P1 — Option dry-run trompeuse et dangereuse

Source : `school_admin/management/commands/envoyer_relances_impayes.py:13-25`.

`--dry-run` est accepté mais jamais utilisé : la commande appelle réellement la vérification des moratoires et l'envoi des relances. Le texte d'aide reconnaît le problème. Une simulation peut donc modifier des états et envoyer des messages.

Correction : propager le mode simulation jusqu'aux services et garantir zéro écriture et zéro envoi ; sinon retirer immédiatement cette option.

### 9. P1 — WebSockets sans validation d'origine à l'entrée ASGI

Source : `school/asgi.py`.

La pile contient les sessions et l'authentification mais aucun `OriginValidator` ou `AllowedHostsOriginValidator`. Une session authentifiée ne remplace pas le contrôle d'origine. L'exploitabilité dépend notamment des cookies et du filtrage réel du proxy.

Correction : ajouter une liste d'origines autorisées et tester les connexions provenant d'un site tiers ainsi que l'isolation entre établissements dans les consumers.

### 10. P1 — Suppression FCM sans contrôle du propriétaire

Source : `school_admin/api_views/fcm_views.py:66-83`.

Un utilisateur authentifié peut supprimer un token par sa seule valeur, sans filtrer `content_type` et `object_id` sur le compte courant. L'enregistrement peut aussi réaffecter un token existant via `update_or_create`. L'abus suppose de connaître le token concerné.

Correction : vérifier l'appartenance et formaliser les règles de transfert d'un appareil entre comptes.

### 11. P1 — Sessions de dix ans

Source : `school/settings.py:40-46`, et `dev_login`.

Les sessions durent dix ans et sont renouvelées à chaque requête. Une session dérobée ou laissée ouverte sur un appareil partagé bénéficie d'une durée excessive. `SESSION_SAVE_EVERY_REQUEST` ajoute aussi des écritures de session.

Correction : délais adaptés aux rôles, expiration d'inactivité, révocation et réauthentification pour les actions sensibles.

### 12. P1 — Fragment Nginx incohérent avec sa notice

Source : `deploy/nginx/aria-websocket.conf:1-8`.

La notice demande d'inclure le fichier dans un bloc `server`, alors que le fichier contient un bloc `upstream`, qui appartient au contexte `http`. Une inclusion littérale à l'emplacement indiqué échoue.

Correction : séparer la définition upstream et les locations, livrer une configuration complète vérifiable par `nginx -t`.

### 13. P1 — Planification Celery non couverte par les unités fournies

Sources : `school/settings.py`, `CELERY_BEAT_SCHEDULE` ; `deploy/systemd/aria-celery.service` ; `deploy.sh`.

Des relances et contrôles quotidiens sont programmés, mais l'unité fournie lance seulement un worker, sans Beat ; aucune unité Beat n'a été trouvée dans `deploy/`. Définir un calendrier ne lance pas le planificateur.

Correction : fournir et superviser une instance unique du scheduler, ou documenter l'ordonnanceur externe réellement utilisé. L'absence sur le serveur n'est pas démontrée par cette revue.

### 14. P1 — Actions de gestion des dépenses affichées mais non réalisées

Sources : `school_admin/templates/school_admin/gestion_comptable/gestion_depenses.html:849-913` ; rendu depuis `school_admin/personal_views/comptable_view.py:2811`.

Plusieurs fonctions JavaScript se limitent à des alertes « à implémenter » : rapports, budget, export, approbation en lot, édition, détails, téléchargement, catégories et suppression de budget. Ce constat concerne ces actions précises, pas l'intégralité du module finances.

Correction : terminer chaque action retenue dans le périmètre commercial ou la retirer de l'interface jusqu'à disponibilité.

### 15. P2 — Indicateurs de salles et de tableaux de bord artificiels

Sources : `school_admin/controllers/salle_controller.py:229-231` ; `school_admin/model/salle_model.py:96-101` ; `school_admin/personal_views/secretaire_view.py:404` ; `school_admin/personal_views/enseignant_view.py:474`.

Taux d'occupation et jours d'utilisation à zéro, dernière utilisation absente, capacité actuelle égale à la capacité maximale, évaluations en cours et messages non lus laissés à zéro. Ces valeurs peuvent être interprétées comme de vrais résultats.

Correction : calculer les métriques ou afficher explicitement « indisponible », avec définition métier et période de référence.

### 16. P2 — Architecture concentrée dans des fichiers volumineux

Sources : `school_admin/personal_views/directeur_view.py` (~489 Ko), `enseignant_view.py` (~378 Ko), `enseignant_primaire_view.py` (~263 Ko), `comptable_view.py` (~162 Ko) ; contrôleur comptable ~132 Ko.

Le projet dispose déjà de services, mais les responsabilités restent réparties entre `views`, `personal_views`, `controllers`, services et modèles. La taille des vues rend l'examen des permissions, des transactions et des régressions coûteux. Le routage est lui aussi réparti entre de nombreux fichiers inclus à la racine.

Correction : découper progressivement par domaine métier, centraliser les règles d'accès et transactions dans des services explicites, garder des vues courtes. Éviter une réécriture globale avant d'avoir sécurisé les parcours existants.

### 17. P2 — Authentification multi-modèles complexe

Source : `school_admin/authentication_backends.py` et middlewares associés.

Six types de comptes sont résolus via plusieurs tables, des formats d'identifiants parfois identiques et un contexte de type d'utilisateur. Des commentaires documentent déjà un ancien problème de collision de clés et de contexte asynchrone. Cette complexité n'est pas une faille supplémentaire démontrée, mais impose une couverture systématique des sessions HTTP/WebSocket, changements de rôle et clés identiques.

Correction : définir une identité d'authentification unifiée à terme et tester dès maintenant les frontières entre rôles et établissements.

### 18. P2 — Journalisation excessive et conservation non définie

Sources : `school_admin/middleware.py:121-122` ; `school/settings.py:341`.

Chaque requête produit un print et un log INFO avec utilisateur et chemin. Le fichier utilise un FileHandler sans rotation configurée dans Django. La rotation système éventuelle n'a pas été vérifiée.

Correction : réduire les logs routiniers, filtrer les données personnelles, définir rotation, rétention, corrélation des erreurs et alertes.

### 19. P2 — Fuseau horaire fixé à Paris

Source : `school/settings.py:207`, également utilisé par Celery.

Le projet ciblant notamment le Sénégal, les tâches quotidiennes à 7h30 et 8h suivent Paris, avec variation saisonnière. L'intention métier doit être clarifiée avant de changer cette valeur.

Correction : rendre le fuseau configurable, définir celui de chaque établissement si plusieurs pays et tester les échéances autour de minuit.

### 20. P2 — Validation des nouveaux mots de passe incomplète

Source : vues finales de réinitialisation dans `school_admin/views.py`.

Ces vues vérifient surtout une longueur minimale et la confirmation ; elles n'appellent pas les validateurs Django configurés. Configurer `AUTH_PASSWORD_VALIDATORS` ne les applique pas automatiquement à ces formulaires manuels.

Correction : utiliser les formulaires/validateurs partagés sur tous les parcours, avec limitation des tentatives et réponses évitant l'énumération des comptes.

### 21. P2 — Documentation et outillage d'exploitation dispersés

Sources : `README_DEPLOIEMENT.md`, `deploy.sh`, `deploy/`, scripts `add_column*`, `fix_column.py`, `fix_migrations.py`, scripts de suppression à la racine.

Le guide décrit principalement Gunicorn alors que les scripts actuels démarrent Daphne. Les chemins et noms d'utilisateur serveur sont figés. Des scripts modifient directement le schéma ou la table de suivi des migrations. La racine contient aussi des archives, supports marketing, captures et scripts ponctuels. Les modifications locales présentes au début rendent nécessaire l'identification d'une version précise à auditer et livrer.

Correction : un guide de référence maintenu, un dossier d'outils d'administration documentés, migrations reproductibles et séparation claire du code, des supports et des données de travail.

## Points nécessitant une vérification complémentaire

- **Isolation entre établissements et rôles** : plusieurs contrôles existent ; la couverture de chaque endpoint n'a pas été démontrée. Tester l'accès à un objet appartenant à un autre établissement pour les lectures, exports, écritures et WebSockets.
- **Finances** : contrôler concurrence des encaissements, idempotence, numérotation, annulations, clôture, précision décimale et traçabilité. La présence de nombreux tests finances est positive ; leur réussite n'a pas été vérifiée ici.
- **Hors ligne Flutter** : `gestion_scolaire/lib/services/local_database.dart` stocke les données dans un SQLite commun sans colonne de propriétaire dans les tables examinées. Vérifier la purge, le cloisonnement au changement de compte, la protection des données sur appareil et les conflits de synchronisation. Les endpoints push/pull existent bien côté Django ; ne pas les déclarer manquants sur la base du message de repli du client.
- **HTTPS** : cookies sécurisés et HSTS sont prévus quand DEBUG=False, mais pas de `SECURE_SSL_REDIRECT` explicite. Vérifier la redirection effective dans Nginx et la confiance accordée aux en-têtes du proxy.
- **Données média privées** : vérifier les autorisations de téléchargement et la configuration Nginx ; le routage Django ne les sert explicitement qu'en DEBUG. Une URL non devinable ne constitue pas une autorisation.
- **Sauvegardes et restauration** : aucune procédure opérationnelle de restauration testée n'a été identifiée dans les fichiers d'exploitation examinés. Vérifier PostgreSQL, médias, chiffrement, conservation et restauration sur un environnement isolé.
- **Tests et livraison** : aucun pipeline CI versionné trouvé via `git ls-files .github`. Les tests sont nombreux, mais répartis entre `school_admin/tests/`, `tests_*.py` et scripts à la racine ; `school_admin/tests.py` est un squelette et coexiste avec le package `tests/`. Vérifier explicitement la découverte et la liste des tests réellement exécutés, puis rendre les contrôles bloquants.
- **Performances** : mesurer requêtes SQL, pagination, temps des bulletins et tableaux de bord avec un volume réaliste. La taille des vues seule ne prouve pas un problème de performance.
- **Dépendances** : versions épinglées dans requirements, mais aucun audit de vulnérabilités exécuté. Vérifier les avis de sécurité actuels et la reproductibilité dans un environnement neuf avant livraison.
- **Observabilité** : vérifier healthchecks applicatifs et dépendances, alertes sur erreurs, files Celery, Redis, saturation disque et indisponibilité des prestataires.
- **Périmètre fonctionnel** : effectuer une recette navigateur par rôle sur inscription, notes, bulletins, absences, paiements, exports et notification. Aucun parcours UI complet n'a été réalisé pendant cet audit.

## Vérifications réalisées et limites

Lecture et recherches ciblées sur configuration, authentification, routage, middleware, déploiement, service worker, client Flutter, actions inachevées et organisation des tests/services. Les fichiers `.env` et les fichiers de secrets n'ont pas été reproduits dans le rapport ; les valeurs sensibles du code sont volontairement omises.

`env/Scripts/python.exe manage.py check --deploy` a été lancé, mais n'a fourni aucun bilan après l'attente ; il a été interrompu. Sa cause n'est pas déterminée. Aucun résultat positif de contrôle Django ou de tests ne peut donc être revendiqué. Aucun accès au VPS, test d'exploitation, audit de données, scan réseau ou vérification des secrets auprès des prestataires n'a été effectué.

## Ordre recommandé

1. Corriger les réinitialisations, remplacer les secrets et neutraliser le risque dev-login.
2. Sécuriser SMTP, caches privés, WebSockets, sessions et opérations FCM.
3. Rendre le déploiement bloquant sur erreur, préserver les releases et valider sauvegarde/restauration et migrations en préproduction.
4. Achever ou retirer les actions inactives et remplacer les indicateurs artificiels.
5. Exécuter la recette par rôle et établissement, les tests financiers, les contrôles de charge et un pipeline reproductible.
6. Découper progressivement les vues et consolider la documentation après sécurisation des parcours.
