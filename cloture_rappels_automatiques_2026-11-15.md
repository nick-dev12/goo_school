# Rappels automatiques — audit de branchement et clôture

Date : 15 novembre 2026.
Référence : `feuille_route_rappels_automatiques_2026-11-14.md` (audit initial, règles par espace, détail des phases 0 à 4).

## Verdict

**Le code est correctement branché de bout en bout** : modèles, moteur, règles des cinq espaces, popup, centre « À faire », cloche, page de réglages, tâche planifiée. 23 contrôles sur 24 sont bons, le 24ᵉ est un faux positif expliqué plus bas, et 97 tests passent.

**Une condition d'exploitation n'est pas remplie sur ce poste** : aucun worker Celery ni Celery Beat ne tourne. Tant qu'ils ne sont pas démarrés, **aucun rappel planifié ne part** — le planificateur n'a d'ailleurs jamais effectué de passage (`dernier_passage` vide pour les trois établissements, 0 rappel émis). Les popups et le centre « À faire », eux, fonctionnent sans Celery.

La partie développement (phases 0 à 4) est donc close ; la mise en service reste à faire (section 5).

---

## 1. Contrôles effectués

| # | Contrôle | Résultat |
|---|---|---|
| 1 | `manage.py check` | Aucun problème |
| 2 | `makemigrations --check --dry-run` | Aucune migration manquante |
| 3 | Migrations `0249`, `0250`, `0251` | Appliquées en local |
| 4 | Tables `RappelEnvoye`, `ParametresRappels`, `NotificationPersonnel`, `PushDelivery`, `ContextPopupState` | Présentes |
| 5 | Colonnes `rappelenvoye.etablissement_id`, `parametresrappels.rappel_cours_demain` | Présentes |
| 6 | Entrée Beat `rappels-automatiques` → `generer_rappels_task` (à :05 et :35) | Présente dans `CELERY_BEAT_SCHEDULE` |
| 7 | Tâches Celery `generer_rappels_task`, `deliver_push_task`, `retry_pending_push` | Enregistrées dans l'application Celery |
| 8 | `ContextPopupMiddleware` | Actif dans `MIDDLEWARE` |
| 9 | Fichiers statiques (JS et CSS du popup, CSS de la page de réglages) | Trouvés ; versions JS et CSS alignées (`v=8`) |
| 10 | Page de démonstration temporaire | Supprimée |
| 11 | 35 noms d'URL utilisés par les cartes | Tous résolus, sauf un faux positif (voir ci-dessous) |
| 12 | URL `directeur:rappels_automatiques`, `directeur:notifications_directeur`, `school_admin:context_popup` | Résolues |
| 13 | Chaque fournisseur de règles exécuté **directement** sur les données locales, sans le filet `try/except` | Aucune erreur — 3 établissements, 4 personnels, 2 professeurs, 42 élèves, 38 parents |
| 14 | Passage complet en simulation (`generer(dry_run=True)`) | 19 rappels dus, 89 personnes, 0 erreur, rien envoyé |
| 15 | Serveur en marche : API anonyme | 401 (attendu) |
| 16 | Serveur en marche : JS et CSS du popup servis dans leur dernière version | Oui |
| 17 | Serveur en marche : page de réglages sans connexion | Redirection vers la connexion (attendu) |
| 18 | Redis (broker) | Répond |
| 19 | Worker Celery | **Aucun worker ne répond** |
| 20 | Celery Beat | **Aucun processus** |

**Faux positif du contrôle 11** : `enseignant_primaire:noter_examen` n'existe pas, mais la règle PROF-08 qui l'utilise est placée sous `if not primaire` (`services/rappels/professeur.py`). Elle ne s'exécute donc jamais pour un professeur du primaire. Aucune correction nécessaire.

### Règles réellement déclenchées par les données locales

| Code | Rappel | Occurrences |
|---|---|---|
| PAR-01 | Échéance de scolarité | 11 |
| PAR-05 | Absence à justifier | 6 |
| PROF-02 | Cahier de texte à compléter | 1 |
| NOTIF | Nouveautés (notifications non lues, jamais re-poussées) | 16 |

Le passage complet y ajoute les règles déjà présentes avant ce chantier (impayés de la direction et du personnel, convocation). Les autres règles n'ont simplement pas de données correspondantes en local ; elles sont couvertes par les tests.

### Tests

```
python manage.py test school_admin.tests_rappels school_admin.tests_cahier_texte school_admin.tests_hubs_directeur school_admin.tests_recouvrement school_admin.tests_smoke_primaire_secondaire school_admin.tests_pointage --settings=school.test_settings --noinput
```

97 tests, tous réussis (base de test en mémoire, jamais la base de développement). `tests_rappels.py` en contient 40 : seuils, journal anti-doublon, heures calmes, plafond, synthèse, permissions du personnel, page de réglages, cloche du personnel, règles professeur, élève et parent.

La suite complète du projet n'a pas été relancée.

---

## 2. Ce qui est livré

| Phase | Contenu | État |
|---|---|---|
| 0 | Moteur, journal, réglages par établissement, tâche Beat, commande `generer_rappels` | Livré |
| 1 | Nouveau popup, centre « À faire », pastille flottante, feuille basse sur mobile | Livré |
| 2 | 17 règles direction / personnel, cloche du personnel, page « Rappels automatiques » | Livré |
| 3 | 10 règles professeur, jauge d'avancement du jour | Livré |
| 4 | Règles élève et parent (examens, bulletin, absences, moratoire, liaison, cours du lendemain) | Livré |
| 5 | Équipe plateforme (commercial, support, comptable) | **Non fait** (optionnel) |
| 6 | Recette sur appareils réels | **Non faite** |

Chaîne d'un rappel : une règle produit une carte (`services/context_popups.py::card`) → le popup et le centre « À faire » l'affichent à l'ouverture d'une page → le passage planifié (`services/rappels/moteur.py::generer`) crée la notification dans la cloche du rôle et met le push en file (`PushDelivery`) → `RappelEnvoye` empêche tout doublon pour le même seuil.

---

## 3. Écarts connus par rapport à la feuille de route

| Prévu | Situation |
|---|---|
| ADM-03 et PAR-07 — réinscriptions à faire | Non livrés : la liste est calculée dans la vue, pas dans un service réutilisable |
| ADM-06 — paie des professeurs à préparer | Non livré : aucune donnée fiable de « reste à payer du mois » ; le code ADM-06 désigne maintenant dépenses en brouillon et échéances de prêt |
| DIR-07 — synthèse hebdomadaire des impayés | Reste un rappel avec relances |
| PAR-04 — synthèse du dimanche soir | Remplacée par les rappels J-3, J-1, jour J |
| PAR-01 — fusion avec la relance WhatsApp/SMS | Les deux coexistent, avec un garde-fou anti-doublon de 3 jours |
| PROF-11 — cours à démarrer | Seul « cours resté ouvert » est rappelé |
| PROF-04, PROF-08, PROF-11 | Pas de cas de test positif (requêtes vérifiées sans erreur) |

---

## 4. Ce qui n'a pas été vérifié

- **Réception réelle d'un push** sur un téléphone ou un navigateur (un seul appareil actif en base locale).
- **Rendu des pages avec un compte connecté** : popup dans chaque espace, page « Rappels automatiques », page Notifications du personnel. Le popup et la jauge ont été vus uniquement sur une page de démonstration avec des données simulées.
- **Position de la pastille « À faire »** par rapport aux barres de navigation basses de chaque espace (variable CSS `--arp-pill-offset`).
- **Charge** : le passage parcourt chaque personne active ; non mesuré sur un gros établissement.
- **Production** : rien n'est déployé ni commité.

---

## 5. Mise en service (à faire)

1. **Démarrer le worker et Beat.** En local, dans deux terminaux :

   ```bash
   env/Scripts/celery.exe -A school worker -l info --pool=solo
   ```

   ```bash
   env/Scripts/celery.exe -A school beat -l info
   ```

   En production : `sudo systemctl restart aria-celery aria-celery-beat` (une seule instance de Beat).

   Attention : dès le premier passage (à :05 ou :35, hors heures calmes 21 h – 6 h 30), les rappels dus partent réellement — une vingtaine avec les données locales actuelles.

2. **Vérifier avant d'envoyer** :

   ```bash
   python manage.py generer_rappels --dry-run
   ```

   ou, dans l'espace direction, « Rappels automatiques » → « Voir ce qui partirait ».

3. **Contrôler le premier passage** : la page « Rappels automatiques » doit afficher une heure de dernier passage et le journal doit se remplir.

4. **Recette** : un compte par espace, sur ordinateur et sur téléphone — popup, « Plus tard », bouton d'action, cloche, push reçu puis clic.

5. **Déploiement** : appliquer les migrations `0246` à `0251`, redémarrer Daphne, le worker et Beat.

---

## 6. Fichiers de ce chantier

**Nouveaux**
- `school_admin/model/rappel_model.py`
- `school_admin/migrations/0249_rappels_automatiques.py`, `0250_rappel_etablissement.py`, `0251_rappel_cours_demain.py`
- `school_admin/services/rappels/` : `__init__.py`, `moteur.py`, `etablissement.py`, `professeur.py`, `famille.py`
- `school_admin/controllers/rappels_controller.py`
- `school_admin/management/commands/generer_rappels.py`
- `school_admin/templates/school_admin/directeur/rappels_automatiques.html`
- `school_admin/static/school_admin/css/directeur/rappels.css`
- `school_admin/tests_rappels.py`

**Modifiés**
- `school_admin/services/context_popups.py`, `school_admin/api_views/context_popup_views.py`, `school_admin/context_popup_middleware.py`
- `school_admin/static/school_admin/js/shared/context_popups.js`, `css/shared/context_popups.css` (réécrits)
- `school_admin/services/push_delivery.py`, `school_admin/tasks/__init__.py`, `school_admin/tasks/celery_tasks.py`, `school/settings.py`
- `school_admin/context_processors.py`, `school_admin/personal_views/directeur_view.py` (vue des notifications), `templates/.../directeur/notifications_directeur.html`
- `school_admin/personal_url/directeur_url.py`, `school_admin/services/hubs_directeur.py`, `school_admin/model/__init__.py`

**Pour ajouter un rappel plus tard** : écrire une carte `card(...)` dans le fournisseur de l'espace concerné, avec un `code`, une `family`, une `icon` et, s'il y a une date, un `deadline`. Le popup, le centre « À faire », la cloche et le push planifié la prennent en charge sans autre modification. Ajouter un test dans `tests_rappels.py` qui appelle le fournisseur directement, car les erreurs d'une règle sont volontairement absorbées à l'exécution.

---

## 7. Mise en service locale — 15 novembre 2026, 10 h 35

Worker Celery et Celery Beat démarrés en arrière-plan sur ce poste (journaux : `logs/celery_worker.log`, `logs/celery_beat.log`). Le worker répond et la tâche `generer_rappels_task` y est chargée.

**Premier passage planifié (10 h 35), exécuté par Beat sans intervention** : 3 établissements, 89 personnes, 19 rappels, 0 erreur, en 2,4 secondes.

| Règle | Rappels émis |
|---|---|
| PAR-01 — échéance de scolarité | 11 |
| PAR-05 — absence à justifier | 3 |
| DIR-07 — dossiers de scolarité (direction) | 2 |
| ADM-04 — dossiers de scolarité (personnel) | 2 |
| PROF-02 — cahier de texte à compléter | 1 |

- Les 19 notifications sont dans la cloche de leurs destinataires, dont 2 dans celle du personnel administratif.
- Push : 1 accepté par Firebase, 18 ignorés faute d'appareil enregistré pour ces comptes (comportement attendu : seul un compte a activé les notifications sur ce poste). Une acceptation par Firebase n'est pas une preuve d'affichage sur l'appareil.
- La date de dernier passage est renseignée pour les trois établissements.

Ces deux processus ne sont pas des services Windows : ils s'arrêtent à la fermeture de la session ou au redémarrage du poste et doivent alors être relancés (section 5).

---

## 8. Mise en production — nuit du 15 au 16 novembre 2026

**Livraison** : commit `55112c1d` poussé sur `main`, puis déployé sur le VPS par `deploy.sh` (sauvegarde, migrations `0243` à `0251`, collecte des fichiers statiques, redémarrage de Daphne, du worker Celery et de Beat). Correctif du script de déploiement : commit `358adff5`.

**Vérifié après livraison**
- Site : `/health/ready/` répond 200 ; page de connexion 200 ; API des popups 401 sans connexion (attendu).
- Les trois services `aria-daphne`, `aria-celery`, `aria-celery-beat` sont actifs sur la nouvelle version.
- Le worker a chargé `generer_rappels_task`, `deliver_push_task` et `retry_pending_push`.
- **Premier passage automatique en production, lundi 16 novembre à 6 h 35 (fin des heures calmes)** : 28 établissements, 570 personnes, 9 rappels, 0 erreur, en 38 secondes. Détail : 4 DIR-07, 3 PAR-01, 1 ADM-04, 1 DIR-01. Le passage suivant (7 h 05) n'a rien renvoyé : aucun doublon.
- Push : 3 acceptés par Firebase, 6 ignorés faute d'appareil enregistré. 20 jetons d'appareils périmés ont été désactivés automatiquement (93 → 73 actifs).

**Deux incidents pendant la livraison, corrigés**
1. Le contrôle de santé du script a répondu 502 : il partait une seconde avant que Daphne n'écoute. Le site était en réalité remonté. Le script s'est arrêté là, donc le réglage Nginx n'a pas été appliqué à ce moment.
2. Les nouveaux dossiers statiques (`vendor/` : icônes, graphiques, scanner QR) et les copies `.gz` avaient été créés sans droit de lecture pour Nginx à cause du `umask 077` du script : ces fichiers ont répondu 403 pendant quelques minutes après le redémarrage. Droits rétablis à la main (`chmod`), tous les fichiers contrôlés répondent 200.

Le script `deploy/deploy_safe.sh` rétablit désormais les droits après la collecte et réessaie le contrôle de santé pendant une minute.

**Reste à faire sur le serveur** : `sudo bash deploy/configurer_nginx_compression.sh` (compression des CSS / JavaScript, copies `.gz`, HTTP/2). Tant que ce n'est pas fait, les CSS et JavaScript partent non compressés.

**Non vérifié en production** : affichage du popup et de la page « Rappels automatiques » avec un compte connecté ; réception d'un push sur un téléphone.
