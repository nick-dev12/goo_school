# Audit notifications et push — 12 novembre 2026

## Verdict

Le système possède les composants nécessaires pour les quatre rôles principaux, mais la chaîne push ne peut pas être considérée comme opérationnelle de bout en bout. Les API de jetons fonctionnent ; plusieurs défauts de cycle de vie, de déclenchement, d'affichage et de suivi restent à corriger avant configuration définitive.

Audit du code des notifications et de leurs déclencheurs, des API, des templates, du JavaScript, des service workers et de l'état local de la base. Aucun push réel, WhatsApp ou message à un utilisateur n'a été envoyé. Les essais de jetons fictifs ont été annulés par transaction. Les clés privées n'ont pas été affichées.

## État local vérifié

| Contrôle | Résultat |
|---|---|
| Firebase Admin installé | 7.1.0 |
| Fichier de compte de service attendu | Présent |
| Initialisation locale Firebase Admin | Réussie ; ne prouve pas l'autorisation d'envoi distante |
| USE_CELERY | True |
| Adresse de broker configurée | Oui ; disponibilité du broker et des workers non prouvée |
| Jetons FCM en base avant essais | 0 |
| Notifications parent | 50 ; 0 marquée push envoyée |
| Notifications élève | 50 ; 0 marquée push envoyée |
| Notifications direction / professeur | 0 / 0 |
| POST jeton anonyme | 401 |
| Enregistrer/supprimer jeton direction | 200 / 200 |
| Enregistrer/supprimer jeton professeur | 200 / 200 |
| Enregistrer/supprimer jeton parent | 200 / 200 |
| Enregistrer/supprimer jeton élève | 200 / 200 |
| Même jeton après changement de compte | 403 |
| /service-worker.js | 200, JavaScript |
| /firebase-messaging-sw.js | 200, JavaScript |

Les compteurs ne permettent pas de déduire la cause historique de chaque absence d'envoi. Ils confirment simplement l'absence actuelle d'appareil utilisable dans cette base.

## Cartographie des acteurs

| Acteur | Enregistrement appareil | Notifications persistantes | Branchement navigateur | Observation |
|---|---|---|---|---|
| Direction | GenericForeignKey vers Etablissement ; testé | NotificationDirecteur | Dashboard directeur | Relevés, justifications et sanctions disposent de services ; chargement push pas commun à toutes les pages |
| Professeur primaire | GenericForeignKey vers Professeur ; testé | NotificationEnseignant | Dashboard primaire et variantes enseignant | Annonces ; couverture des autres interactions à définir selon besoin métier |
| Professeur secondaire | Même modèle ; testé | NotificationEnseignant | Dashboard et dashboard_v3 | Module pas systématiquement chargé dans toutes les pages |
| Parent | GenericForeignKey vers Parent ; testé | NotificationParent | Pied de page partagé parent | Liens familiaux actifs/validés et parent inscripteur actif sélectionnés par le service |
| Élève | GenericForeignKey vers Eleve ; testé | NotificationEleve | Pied de page partagé élève | Notes, bulletins, annonces, sanctions, présences, convocations |
| Secrétaire/comptable/personnel administratif | Modèle générique techniquement capable de stocker un jeton | Aucun service dédié trouvé dans les services de notifications examinés | Aucun parcours d'activation dédié trouvé | Ne pas considérer ces rôles comme couverts par le seul service direction |

## Cartographie des interactions examinées

| Événement | Déclencheur et circuit trouvés | Destinataires / réserve |
|---|---|---|
| Publication annonce | annonce_model → schedule_annonce_notification → notification_tasks | Élèves, parents, enseignants selon sélection ; tâches après commit |
| Publication emploi du temps | emploi_du_temps_model → schedule_emploi_publication | Circuit de publication présent ; destinataires traités dans notification_tasks |
| Publication bulletin | directeur_view → schedule_bulletin_publication | Services élève/parent ; tâche par thread après commit |
| Nouvelle évaluation secondaire | enseignant_view → schedule_evaluation_notification | Élèves et parents ; circuit présent |
| Nouvelle évaluation primaire | enseignant_primaire_view → schedule_evaluation_primaire_notification | Circuit distinct présent |
| Exercice maison | vues enseignant primaire/secondaire → schedule_exercice_maison_notification | Circuit présent |
| Présences/absences | presence_sync_service → schedule_presence_notifications | Circuit élève/parent ; après commit |
| Notes/moyennes | services ParentNotificationService et EleveNotificationService et appels directs Firebase dans les vues enseignant | Plusieurs chemins à harmoniser ; aucune preuve d'absence de doublon sur un événement complet |
| Convocation / sanction | méthodes dédiées parent et élève ; sanction direction | Services présents ; réception réelle non testée |
| Relevé soumis / justification | DirecteurNotificationService | Direction ; push direct depuis le service |
| Relance scolarité | recouvrement._notifier_parents_scolarite → ParentNotificationService._dispatch | Notification persistante seulement : push_title/push_body absents |
| Paiement/reçu scolarité | Reçus et comptabilité distincts du système de notification | Aucun circuit push systématique de confirmation démontré dans ce périmètre |

Cette cartographie établit les branchements du code ; elle ne représente pas une recette complète de chaque formulaire et chaque statut métier.

## Écarts prioritaires

### P0 — Sécurité des routes de test

`api_views/fcm_test_views.py::test_notification_eleve` accepte un eleve_id et recherche l'élève sans restriction d'établissement ou de propriété ; la protection visible est login_required. `api_views/test_notes_notifications.py` expose également des opérations de test sur un élève choisi. Les routes sont publiées dans urls.py. Restreindre ces fonctions aux administrateurs autorisés, filtrer l'établissement et désactiver les routes de diagnostic en production. Aucune exploitation ni notification réelle n'a été déclenchée durant l'audit.

### P0 — Appareil partagé et déconnexion

`api_views/fcm_views.py` refuse l'association d'un jeton à un second compte (403 reproduit). Le client appelle save-token, mais aucun appel de suppression à la déconnexion n'a été trouvé dans le module FCM ni dans les parcours de déconnexion examinés. Le jeton peut rester associé à l'ancien compte alors que le navigateur est utilisé par un autre. Risque de notifications de l'ancien utilisateur affichées sur un appareil partagé. Il faut une association explicite de l'installation au compte courant et un retrait fiable à la déconnexion.

### P1 — Activation annoncée même si la sauvegarde échoue

`fcm_notifications.js::registerServiceWorkerAndGetToken` attend saveTokenToServer, puis retourne le jeton même si cette sauvegarde a répondu false. Le bouton peut donc disparaître et afficher un succès après une erreur 403/500. Le succès utilisateur doit dépendre de l'enregistrement serveur.

### P1 — Démarrage et compatibilité navigateur

Le module appelle getMessaging au chargement sans détection préalable de compatibilité. initializeFCM accède directement à Notification.permission. Le contrôle `Notification in window` n'existe que dans le chemin manuel. De plus, registerServiceWorkerAndGetToken attend navigator.serviceWorker.ready avant de tenter l'enregistrement : si aucun worker n'est installé et que le module PWA n'est pas chargé, l'attente peut rester bloquée. Le PWA est enregistré séparément à l'événement load ; cette dépendance doit être rendue explicite.

### P1 — Notifications d'arrière-plan et clic

Le serveur envoie un payload notification + data ; les workers appellent aussi showNotification dans onBackgroundMessage. Firebase documente l'affichage automatique des messages notification en arrière-plan : risque de double affichage à vérifier et à supprimer par une stratégie unique.

Le chemin avant-plan utilise `new Notification` sans gestionnaire onclick : l'URL métier n'est pas ouverte par ce code. Le worker PWA vérifie l'origine de l'URL, mais la version générée dans views.py ne présente pas la même protection et compare une URL absolue de fenêtre à une URL souvent relative. Plusieurs implémentations divergent.

Référence officielle : https://firebase.google.com/docs/cloud-messaging/web/receive-messages

### P1 — Relances de scolarité sans push

`services/recouvrement.py::_notifier_parents_scolarite` fournit titre, texte et payload, mais pas push_title/push_body. `_dispatch` envoie un push seulement si les deux arguments existent. La notification parent est donc créée sans passage à Firebase pour cette interaction.

### P1 — Envoi avant validation et durabilité des tâches

Les fonctions `_dispatch` créent la notification puis envoient directement à Firebase. Elles peuvent donc être appelées dans une transaction non encore validée. En cas de rollback, un utilisateur peut recevoir un push pour une donnée annulée. Plusieurs tâches passent bien par on_commit, mais le comportement n'est pas uniforme.

Le dispatcher utilise un thread daemon, y compris pour soumettre une tâche Celery. D'autres notifications utilisent directement des threads daemon sans Celery. Un arrêt de processus peut perdre le travail. Aucune file persistante de tentatives push par appareil ni politique de reprise n'a été trouvée dans le service Firebase examiné. USE_CELERY=True ne prouve pas que tous ces chemins passent par un worker.

### P1 — Suivi d'envoi inexact pour les parents

`parent_notification_service.py` marque toutes les notifications parent créées comme envoyées si le résultat agrégé contient au moins un succès. Avec deux parents, un succès pour le premier peut marquer à tort le second comme servi. Il faut suivre les résultats par destinataire/appareil. Le drapeau « envoyé » désigne au mieux une acceptation par FCM ; il ne prouve ni livraison au téléphone ni lecture.

### P1 — Contenu injecté dans un toast

`fcm_notifications.js::showToastNotification` insère title et message dans innerHTML sans échappement. Ces contenus peuvent provenir d'annonces ou d'autres textes métier. Construire les nœuds avec textContent. Risque constaté dans le code, pas de payload malveillant injecté.

### P2 — Lots, jetons invalides et erreurs

send_multicast construit un lot unique pour tous les appareils sans découpage ; les envois importants doivent respecter la limite du SDK. Le nettoyage des jetons dépend de sous-chaînes de texte d'exception et l'envoi unitaire ne passe pas par ce nettoyage. Une erreur transient est journalisée sans tentative différée. Un compte sans jeton renvoie 0 succès/0 échec, ce qui ne distingue pas clairement « non inscrit aux notifications » d'un envoi vide.

### P2 — Configuration et maintenance

Projet Firebase et clé VAPID sont codés dans le JavaScript ; chemin du compte de service fixé dans firebase_service.py. Des configurations sont répétées dans plusieurs workers et dans views.py. Ces valeurs publiques ne sont pas des clés privées, mais les duplications favorisent les divergences entre environnements. Prévoir une source de configuration commune et un stockage protégé du compte de service.

FCMToken.updated_at n'est pas inclus dans update_fields lors de la réactivation du jeton : le timestamp peut ne pas refléter sa dernière utilisation. Aucune préférence fine par catégorie ou mode silencieux n'a été trouvée dans ce circuit.

## Plan de configuration proposé après audit

1. Sécuriser les diagnostics et gérer l'association appareil/compte et la déconnexion.
2. Unifier le worker actif et le module navigateur ; vérifier la sauvegarde serveur avant de confirmer l'activation ; gérer refus et navigateurs non compatibles.
3. Unifier le contrat d'envoi (identifiant de notification, événement, acteur, URL interne, tag) et les clics avant/arrière-plan.
4. Déclencher les pushes après commit via une file durable ; résultats et reprises par appareil ; lots bornés et invalidation fiable des jetons.
5. Brancher les événements métier manquants, particulièrement la scolarité, puis compléter les rôles personnel selon leurs permissions.
6. Recette sur appareils réels : quatre rôles, primaire/secondaire, appareil partagé, permission refusée, session expirée, avant-plan, arrière-plan, fermeture, erreurs réseau et clic sur chaque catégorie.

## Limites et points à prouver en environnement réel

Pas de permission navigateur sollicitée, pas de vrai jeton généré, pas d'envoi FCM distant. Les clés Firebase présentes et l'initialisation réussie ne prouvent pas que VAPID, projet client et droits distants correspondent. L'état du broker, des workers Celery, de HTTPS en production et des appareils mobiles n'a pas été vérifié. Les pages n'ont pas toutes été testées visuellement ni chaque interaction métier soumise. L'audit couvre les notifications, pas un nouvel audit de tous les modules de gestion scolaire.

Aucun code de configuration ou code métier n'a été modifié à ce stade.
