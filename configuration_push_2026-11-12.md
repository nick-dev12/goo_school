# Configuration push — 12 novembre 2026

## Changements appliqués

- Appareil associé à la session ; retrait du jeton à la déconnexion et lors du changement de compte. Les anciennes associations sans session peuvent être renouvelées côté navigateur.
- Activation confirmée uniquement après sauvegarde serveur réussie. Vérification des capacités navigateur et enregistrement du worker avant l'attente de disponibilité.
- Configuration publique commune via `/api/push/config/` et `/push-config.js`. Réglages surchargeables : FIREBASE_WEB_CONFIG, FIREBASE_VAPID_PUBLIC_KEY, FIREBASE_CREDENTIALS_PATH (ce dernier accepte aussi une variable d'environnement).
- Un worker PWA pour les deux URLs historiques ; messages de données, affichage unique et URL interne au clic ; texte affiché sans injection HTML. Nouveau cache aria-static-v3 pour remplacer les anciens fichiers.
- Module chargé par les en-têtes direction et enseignant, en plus des pieds de page partagés parent/élève.
- Relances de scolarité raccordées au push parent.
- Envoi utilisateur via PushDelivery, une ligne persistante par destinataire, dans la transaction métier ; lancement après commit. Aucune notification utilisateur n'est envoyée pour une transaction annulée via ce circuit.
- Résultats reliés à la notification du destinataire ; le drapeau push représente une acceptation FCM sur au moins un de ses appareils, pas une preuve de lecture.
- Lots limités à 500 ; jetons non enregistrés désactivés ; reprises jusqu'à cinq tentatives avec délai progressif. Les appareils déjà servis ne sont pas sollicités à nouveau pendant les reprises du même envoi.
- Diagnostics désactivés par défaut ; activation explicite PUSH_DIAGNOSTICS_ENABLED et compte superutilisateur nécessaires.
- Migration 0246 appliquée.

## Exécution locale

Worker Celery et Celery Beat démarrés en arrière-plan. Réponse du worker : aria-local@DESKTOP-FMNRJBR, pong. Beat démarre et la reprise des push en attente est planifiée chaque minute.

La commande `python manage.py traiter_push` permet aussi une reprise manuelle. Le suivi se trouve dans PushDelivery : pending, sent, skipped (aucun appareil actif), failed (cinq tentatives). Aucune reprise ne peut transformer une acceptation FCM en preuve de livraison physique.

Ces processus locaux ne constituent pas des services Windows installés au démarrage. En production, superviser le worker et un seul Beat et conserver la base/broker. Après un redémarrage de l'ordinateur, relancer ces processus ou les installer dans le gestionnaire de services retenu pour le déploiement.

## Validation

Tests transactionnels annulés : configuration accessible sans session, sauvegarde d'appareil, retrait à la déconnexion, association au nouveau compte, diagnostics interdits, création persistante et planification après commit, traitement simulé réussi, reprise après échec, découpage 500+1, payload sans notification automatique redondante.

Contrôles Django, absence de migration manquante, syntaxe du module JavaScript et du worker : réussis. Firebase Admin s'initialise avec le compte de service existant. Aucun push réel envoyé pendant la validation.

## Limites de réception

Aucun jeton réel dans la base locale avant configuration : il faut activer les notifications sur un navigateur compatible pour recevoir un message. La validation réelle exige avant-plan/arrière-plan, clic, session expirée et changement de compte sur ce navigateur. Vérifier également le domaine HTTPS de production et les permissions Firebase/VAPID distantes.

Les modèles de notification métier couvrent direction, professeur, parent et élève. Le chargement du module dans l'en-tête ne crée pas automatiquement de nouveaux événements destinés aux secrétaires/comptables ; ces événements et leurs permissions doivent être définis avant d'ajouter ces destinataires. Les circuits historiques de génération d'événements en threads restent présents : la file persistante garantit la reprise une fois l'envoi utilisateur créé, pas avant l'exécution de chacun de ces producteurs historiques.
