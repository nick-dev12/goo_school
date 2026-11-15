# Rappels automatiques et refonte des popups — audit et feuille de route

Date : 14 novembre 2026. Statut : **audit terminé, feuille de route à valider — aucun code modifié à ce stade.**

Ce document sert de référence aux prochains agents. Il complète (sans les remplacer) :
`audit_notifications_push_2026-11-12.md`, `configuration_push_2026-11-12.md`,
`couverture_actions_push_2026-11-12.md`, `audit_plan_popups_contextuels_2026-11-12.md`.

> Règle de sécurité à respecter pendant tout le chantier : les tests passent uniquement par
> `python manage.py test` (base de test dédiée). Jamais de runner maison sur la base de développement.

---

## 1. Objectif

Chaque acteur doit être prévenu **automatiquement** de ce qu'il a à faire, au bon moment, sans qu'un humain déclenche l'envoi :

1. **Notification persistante** dans son centre de notifications (cloche) ;
2. **Push** sur ses appareils (file `PushDelivery`, déjà fiable) ;
3. **Popup d'orientation** à l'arrivée dans son espace, redessiné, qui dit quoi faire et y conduit en un clic.

Un rappel disparaît de lui-même dès que l'action est faite. Aucun rappel n'est inventé : chaque règle s'appuie sur une donnée métier vérifiable.

---

## 2. Audit de l'existant

### 2.1 Ce qui fonctionne déjà (à réutiliser, ne pas réécrire)

| Brique | Fichiers | État |
|---|---|---|
| File push persistante, dédupliquée, avec reprises | `services/push_delivery.py`, `model/push_delivery_model.py`, `tasks/celery_tasks.py` (`deliver_push_task`, `retry_pending_push`) | Opérationnelle. Clé `event_key` → un seul envoi par événement et destinataire |
| Planificateur | `school/settings.py` → `CELERY_BEAT_SCHEDULE` ; unités `deploy/systemd/aria-celery*.service` | 3 tâches : reprise push (60 s), relances impayés (8 h), moratoires (7 h 30) |
| Notifications persistantes | `NotificationDirecteur`, `NotificationEnseignant`, `NotificationParent`, `NotificationEleve` + 4 services `*_notification_service.py` | 4 rôles couverts |
| Notifications événementielles | `services/notification_tasks.py` (annonce, emploi du temps, bulletin, évaluation, devoir, présence, justification) | Déclenchées par une action humaine |
| Moteur de popups | `services/context_popups.py`, `api_views/context_popup_views.py`, `model/context_popup_model.py`, `context_popup_middleware.py`, `static/.../js/shared/context_popups.js`, `css/shared/context_popups.css` | Opérationnel : visite, version, report, action revalidée côté serveur |
| Relances scolarité | `services/recouvrement.py::envoyer_relances_automatiques` | Seul vrai rappel automatique existant (parents, WhatsApp/SMS + push) |

### 2.2 Ce qui manque (constats)

| # | Constat | Conséquence |
|---|---|---|
| C1 | **Aucun moteur de rappels planifiés.** Hors scolarité, tout push part d'une action humaine. Rien ne prévient « demain », « aujourd'hui », « en retard ». | Devoirs, évaluations, convocations, relevés, appels : aucun rappel automatique |
| C2 | Les popups ne calculent les situations **qu'à l'ouverture d'une page**. Un utilisateur qui ne se connecte pas n'est jamais prévenu. | Popup et push ne sont pas reliés |
| C3 | **Personnel administratif** (secrétaire, comptable, caissier, surveillant, censeur…) : aucun modèle de notification, aucune cloche, aucun service. Seules 2 cartes popup existent. | Espace presque muet |
| C4 | **Professeur** : une seule règle popup (évaluation à J-2). Rien sur l'appel, le cahier de texte, les notes à saisir, le relevé à soumettre — alors que ces données existent déjà dans `services/dashboard/teacher.py` et `services/cahier_texte.py`. | Les tâches quotidiennes du professeur ne sont pas rappelées |
| C5 | **Direction** : 3 règles popup (préinscriptions, liaisons, impayés). Les alertes déjà calculées par `services/dashboard/alerts.py` (justifications, relevés non soumis, bulletins non publiés, appels manquants) ne sont ni poussées ni présentées en popup. | Double calcul, information dispersée |
| C6 | **Élève / parent** : popup pour devoirs (J-3), évaluations (J-3), convocations (J-7), échéance. Aucun push de rappel à l'approche de ces dates ; rien sur les examens, les absences à justifier, la réinscription. | Rappels visibles seulement si l'on se connecte |
| C7 | **Équipe plateforme** (`CompteUser` : commercial, support, comptable, RH…) exclue du middleware popup ; aucune notification. Sources disponibles : `RendezVous`, `MessageCommercial.ticket_statut`, `Facturation`. | Espace interne non couvert |
| C8 | Pas d'heures calmes, pas de plafond quotidien, pas de réglage par établissement (sauf scolarité). | Risque de sur-sollicitation dès qu'on automatise |
| C9 | Design popup : pictogrammes en caractères (`✎ ◷ ! i`), 3 cartes maximum sans regroupement, pas de compte à rebours, pas de moyen de rouvrir la synthèse une fois fermée, titre identique pour tous les rôles. | Orientation faible ; à refondre |
| C10 | `school_admin/tasks/__init__.py` n'importe pas toutes les tâches ; en local, worker et Beat ne sont pas des services (à relancer après redémarrage). | À fiabiliser pour que « automatique » soit vrai |

---

## 3. Architecture cible

```
            ┌──────────────────────────────────────────────┐
            │  Registre de règles  services/rappels/        │
            │  une règle = code, acteur, source métier,     │
            │  seuils, texte, lien d'action, permission     │
            └───────────────┬──────────────────────────────┘
                            │ produit des « rappels dus »
        ┌───────────────────┴────────────────────┐
        │                                        │
 Celery Beat (planifié)                  À l'ouverture d'une page
 tasks.generer_rappels_task              api/context-popup/ (existant)
        │                                        │
        ▼                                        ▼
 Journal RappelEnvoye (anti-doublon)     Popup redessiné + centre « À faire »
        │
        ├─► Notification persistante (cloche du rôle)
        └─► PushDelivery (event_key = règle:objet:seuil)
```

**Principe central : une seule définition par rappel.** La même règle alimente le push planifié, la cloche et le popup. Le popup et le push ne peuvent donc plus se contredire, et une action faite retire le rappel partout.

### 3.1 Nouveaux éléments

| Élément | Rôle |
|---|---|
| `services/rappels/` (`registre.py`, `moteur.py`, un fichier par espace) | Règles déclaratives + calcul des rappels dus. `context_popups.py` devient un consommateur de ce registre |
| Modèle `RappelEnvoye` | Journal : destinataire (générique), code règle, objet, seuil, date. Contrainte d'unicité → un rappel par seuil, jamais deux fois |
| Modèle `NotificationPersonnel` + service + page « Notifications » + cloche | Donne enfin un centre de notifications au personnel administratif (C3) |
| Modèle `ParametresRappels` (par établissement) | Activer/désactiver chaque famille de rappels, heures calmes, plafond par jour |
| Tâches Beat `generer_rappels_task` (toutes les 15 min) et `synthese_matinale_task` (7 h) | Rendent le système réellement automatique |
| Commande `python manage.py generer_rappels [--dry-run] [--etablissement ID]` | Exécution manuelle, diagnostic, secours sans Celery |
| Page direction « Rappels automatiques » | Réglages + journal des envois (qui a été prévenu de quoi, quand) |

### 3.2 Règles de diffusion (valeurs par défaut proposées)

- **Seuils** : `J-3`, `J-1`, `Jour J`, `Retard` (puis au plus un rappel tous les 3 jours, 3 fois maximum).
- **Heures calmes** : aucun push entre 21 h et 6 h 30 (heure de l'établissement) ; le rappel attend le matin.
- **Plafond** : 4 pushs de rappel par personne et par jour ; au-delà, regroupement en une synthèse (« 6 actions vous attendent »).
- **Regroupement** : plusieurs objets de même nature = un seul message (ex. « 3 devoirs à rendre cette semaine »).
- **Arrêt automatique** : situation résolue (note saisie, paiement reçu, appel soumis) → plus aucun rappel, carte retirée.
- **Jours non ouvrés** : pas de rappel d'appel ou de cahier de texte le dimanche ni hors période scolaire active.
- **WhatsApp/SMS** : inchangé, réservé à la scolarité comme aujourd'hui.

---

## 4. Rappels par espace

Légende source : ✅ donnée vérifiée dans le code pendant l'audit · 🔎 modèle présent, champ exact à confirmer au moment du branchement (la règle n'est livrée que si la source est fiable).

### 4.1 Direction (compte `Etablissement`)

| Code | Rappel | Source | Seuils | Action |
|---|---|---|---|---|
| DIR-01 | Préinscriptions en attente | ✅ `PreinscriptionEleve.statut='en_attente'` | À l'arrivée, puis si > 48 h | Examiner les demandes |
| DIR-02 | Demandes de liaison parent | ✅ `DemandeLiaisonParent.statut='en_attente'` | idem | Vérifier les demandes |
| DIR-03 | Justifications de note à traiter | ✅ `JustificationNote.STATUT_EN_ATTENTE` | À la demande, puis > 48 h | Traiter les justifications |
| DIR-04 | Relevés de notes non soumis avant la fin de période | ✅ `ReleveNotes.soumis=False` + `PeriodeScolaire.date_fin` | J-7, J-3, J, retard | Voir les relevés |
| DIR-05 | Bulletins prêts mais non publiés | ✅ `completeness` → `bulletins_non_publies` | Fin de période + 3 j | Publier les bulletins |
| DIR-06 | Classes sans appel | ✅ `completeness` → `appels_manquants` | Synthèse du matin | Suivi des présences |
| DIR-07 | Échéances de scolarité dépassées | ✅ `FraisInscription/FraisAnnexe/Mensualite` | Synthèse hebdo (lundi) + nouveaux dossiers | Voir les impayés |
| DIR-08 | Moratoire rompu | ✅ `Moratoire.date_rupture` (`verifier_rupture_moratoires`) | À l'événement | Ouvrir le dossier |
| DIR-09 | Demandes de modification du cahier de texte | ✅ `CahierTexte.demande_statut='en_attente'` | À la demande, puis > 48 h | Traiter la demande |
| DIR-10 | Séances de pointage contestées / anomalies | 🔎 `SeanceCours.statut` | Quotidien | Décider |
| DIR-11 | Convocations du jour | ✅ `Convocation.date_convocation` | Matin du jour | Voir les convocations |
| DIR-12 | Session d'examen qui approche | ✅ `SessionExamen.date_debut` | J-7, J-1 | Vérifier le planning |
| DIR-13 | Délibération restée en brouillon (supérieur) | ✅ `Deliberation.statut` | Fin de période + 7 j | Ouvrir la délibération |
| DIR-14 | Fin de période / fin d'année scolaire | ✅ `PeriodeScolaire.date_fin` | J-7 | Préparer la clôture |
| DIR-15 | Échéance de prêt de l'établissement | 🔎 `EcheancePret` | J-3, J, retard | Voir le prêt |
| DIR-16 | Dépenses en attente de validation | 🔎 `DepenseEtablissement.statut` | Quotidien | Valider |
| DIR-17 | Facture d'abonnement Aria à régler | ✅ `Facturation.date_echeance` | J-7, J-1, retard | Voir la facture |

### 4.2 Personnel administratif (filtré par permission — jamais par simple nom de fonction)

| Code | Rappel | Permission exigée | Source |
|---|---|---|---|
| ADM-01 | Préinscriptions / liaisons à traiter | `eleves_inscrire` | ✅ idem DIR-01/02 |
| ADM-02 | Dossiers élèves incomplets | `eleves_modifier` | ✅ `suivi_eleves.controle_liste` |
| ADM-03 | Réinscriptions à faire (campagne ouverte) | `eleves_reinscrire` | ✅ `suivi_eleves.controle_reinscriptions` |
| ADM-04 | Échéances du jour et dossiers en retard | `comptabilite_voir` | ✅ recouvrement |
| ADM-05 | Moratoires rompus et échéances de moratoire sous 3 jours | `comptabilite_voir` | ✅ `Moratoire`, `EcheanceMoratoire` |
| ADM-06 | Dépenses en brouillon, échéances de prêt | `comptabilite_bilans` | ✅ `DepenseEtablissement`, `EcheancePret` |
| ADM-07 | Classes sans appel / absences non justifiées | `presences_liste` | ✅ completeness, `Presence` |
| ADM-08 | Convocations et sanctions du jour | `sanctions_liste` | ✅ `Convocation`, `Sanction` |
| ADM-09 | Relevés non soumis, cahiers de texte en retard | `notes_liste` | ✅ `ReleveNotes`, `_taux_cahier` |
| ADM-10 | Pointage : séances à contrôler | `pointage_controle` | 🔎 `SeanceCours` |

### 4.3 Professeur (primaire et secondaire/supérieur)

| Code | Rappel | Source | Seuils | Action |
|---|---|---|---|---|
| PROF-01 | Appel non fait pour un cours terminé | ✅ créneaux publiés + `SoumissionListePresence` | 30 min après le cours, puis fin de journée | Faire l'appel |
| PROF-02 | Cahier de texte non renseigné | ✅ `cahier_texte.cours_du_professeur` (cours sans entrée) | Fin de journée, puis J+2 | Remplir le cahier |
| PROF-03 | Brouillons du cahier de texte à valider | ✅ `CahierTexte.statut='brouillon'` | Hebdo | Valider |
| PROF-04 | Notes à saisir (évaluation passée, saisie incomplète) | ✅ `teacher.py` → `a_corriger` | J+3, J+7 | Saisir les notes |
| PROF-05 | Relevé à soumettre avant la fin de période | ✅ `ReleveNotes` + période | J-7, J-3, J | Soumettre le relevé |
| PROF-06 | Évaluation à préparer | ✅ existant | J-2, J-1 | Ouvrir l'évaluation |
| PROF-07 | Devoir donné arrivant à échéance | ✅ `ExerciceMaison.date_rendu` | Jour J | Voir le devoir |
| PROF-08 | Notes d'examen à saisir | 🔎 `SessionExamen` + saisie | Fin de session + 2 j | Saisir |
| PROF-09 | Réponse de la direction (justification, cahier de texte) | ✅ notifications existantes | À l'événement | Consulter |
| PROF-10 | Mes cours de demain (synthèse du soir, désactivable) | ✅ emploi du temps publié | Veille 18 h | Voir mon planning |
| PROF-11 | Séance à démarrer / terminer (si pointage actif) | 🔎 `SeanceCours` | Début de créneau | Pointer |

### 4.4 Élève

| Code | Rappel | Source | Seuils |
|---|---|---|---|
| ELV-01 | Devoir à rendre | ✅ `ExerciceMaison.date_rendu` | J-3, J-1, J |
| ELV-02 | Évaluation à réviser | ✅ `Evaluation` / `EvaluationPrimaire` | J-3, J-1 |
| ELV-03 | Épreuve d'examen | ✅ `SessionExamen`, 🔎 créneaux | J-7, J-1 |
| ELV-04 | Convocation | ✅ `Convocation` | J-1, J |
| ELV-05 | Bulletin publié non consulté | ✅ notification non lue | J+2 |
| ELV-06 | Mes cours de demain (désactivable) | ✅ emploi du temps | Veille 18 h |

### 4.5 Parent (toujours par enfant, liens familiaux actifs et validés)

| Code | Rappel | Source | Seuils |
|---|---|---|---|
| PAR-01 | Échéance de scolarité | ✅ `resume_dette_eleve` (existant, à relier au registre) | J-3, J, retard |
| PAR-02 | Échéance de moratoire | ✅ `EcheanceMoratoire` | J-2, J |
| PAR-03 | Convocation de l'enfant | ✅ | J-1, J |
| PAR-04 | Devoirs et évaluations de la semaine | ✅ | Synthèse dimanche soir + J-1 |
| PAR-05 | Absence non justifiée | ✅ `Presence.statut='absent'` | J+1 |
| PAR-06 | Bulletin disponible non consulté | ✅ | J+2 |
| PAR-07 | Réinscription à effectuer | ✅ `controle_reinscriptions` | Ouverture, puis hebdo |
| PAR-08 | Demande de liaison traitée ou en attente | ✅ `DemandeLiaisonParent` | À l'événement |
| PAR-09 | Épreuves d'examen de l'enfant | ✅ / 🔎 | J-7, J-1 |

### 4.6 Équipe plateforme Aria (`CompteUser`) — phase optionnelle

| Code | Acteur | Rappel | Source |
|---|---|---|---|
| INT-01 | Commercial | Rendez-vous du jour et du lendemain | ✅ `RendezVous.date_rdv/heure_rdv` |
| INT-02 | Commercial | Compte rendu à rédiger après une visite | ✅ `RendezVous` sans `CompteRendu` |
| INT-03 | Support | Tickets ouverts non pris en charge | ✅ `MessageCommercial.ticket_statut='ouvert'` |
| INT-04 | Comptable plateforme | Factures en retard / à échéance | ✅ `Facturation` |
| INT-05 | Administrateur | Synthèse quotidienne (tickets, retards, nouveaux établissements) | ✅ agrégat |

RH, marketing, développeur : aucune source d'« action à faire » fiable trouvée → **pas de rappel inventé**.

---

## 5. Refonte des popups

Contrainte héritée des préférences déjà exprimées : **fonds unis, pas de dégradé, pas de bordure colorée**, variables `--ax-*` des shells existants.

| Avant | Après |
|---|---|
| Titre unique « À voir aujourd'hui » | Salutation personnalisée par rôle et moment (« Bonjour M. Diop — 3 actions vous attendent ») |
| 3 cartes à plat | 3 groupes hiérarchisés : **À faire maintenant** · **À venir** · **Nouveautés** |
| Pictogrammes en caractères | Icônes SVG par nature (appel, notes, devoir, scolarité, convocation, dossier…) |
| Date brute | Compte à rebours lisible : « Aujourd'hui », « Demain », « Dans 3 jours », « En retard de 2 jours » |
| Une carte = un objet | Regroupement avec compteur (« 3 devoirs ») et détail dépliable |
| Fermé = perdu jusqu'à la prochaine visite | Pastille flottante « À faire (n) » qui rouvre le centre de rappels à tout moment |
| Boutons « Consulter » génériques | Verbe d'action précis par règle (« Faire l'appel », « Saisir les notes », « Régler ») |
| Aucune progression | Jauge discrète « 2 sur 5 traitées aujourd'hui » pour les rôles à tâches (professeur, secrétariat) |
| — | Feuille basse plein-largeur sur mobile, fenêtre centrée sur ordinateur ; clavier, lecteur d'écran, `prefers-reduced-motion` conservés |
| — | État vide positif (« Tout est à jour ») dans le centre de rappels, jamais en popup intrusif |

Le comportement validé le 12/11 est conservé : une synthèse par visite, report « Plus tard », action revalidée côté serveur, aucune interruption pendant une saisie ou sur une page d'impression.

---

## 6. Déroulement

| Phase | Contenu | Livrable vérifiable |
|---|---|---|
| **0. Fondations** | Registre de règles, moteur, `RappelEnvoye`, `ParametresRappels`, `NotificationPersonnel`, tâches Beat, commande `generer_rappels`, correction `tasks/__init__.py` | `generer_rappels --dry-run` liste les rappels dus sans rien envoyer ; tests unitaires |
| **1. Refonte popup** | Nouveau composant (JS/CSS), centre « À faire », API enrichie (groupe, icône, compte à rebours, compteur) | Captures ordinateur + mobile dans chaque espace |
| **2. Direction + personnel** | DIR-01→17, ADM-01→10, cloche et page notifications du personnel, page de réglages | Tests par permission ; popup et push cohérents |
| **3. Professeur** | PROF-01→11, primaire et secondaire | Rappel d'appel et de notes vérifiés puis disparition après action |
| **4. Élève + parent** | ELV-01→06, PAR-01→09 ; rattachement de la relance scolarité au registre | Parent multi-enfants, multi-établissements |
| **5. Équipe plateforme** *(optionnel)* | INT-01→05, middleware étendu à `CompteUser` | — |
| **6. Recette et exploitation** | Suite `manage.py test`, heures calmes, plafond, dédoublonnage, documentation d'exploitation (worker + Beat en local Windows et en production) | Rapport de recette ajouté à ce fichier |

Chaque phase se termine par : tests, vérification dans le navigateur, mise à jour de la section 8.

---

## 7. Risques et garde-fous

- **Sur-sollicitation** → heures calmes, plafond, regroupement, réglage par établissement.
- **Rappel faux** (dette déjà réglée, devoir annulé) → recalcul au moment de l'envoi *et* au moment du clic ; les règles 🔎 ne sont livrées qu'après confirmation de la source.
- **Fuite d'information** → mêmes filtres que les pages (établissement, année, liens familiaux, permissions) ; aucun montant pour un personnel sans droit comptable.
- **Charge serveur** → calcul par établissement, requêtes agrégées, pas de recalcul des tableaux de bord complets ; tâche bornée dans le temps.
- **Beat arrêté** → la commande manuelle et la synthèse à l'ouverture de page restent fonctionnelles ; la page de réglages affiche l'heure du dernier passage du planificateur.
- **Migrations** → 3 nouveaux modèles, aucune modification destructive des tables existantes.

---

## 8. Journal d'avancement

| Date | Phase | État |
|---|---|---|
| 2026-11-14 | Audit et feuille de route | Terminé, validé |
| 2026-11-14 | Phase 0 — Fondations | Livrée (voir 8.1) |
| 2026-11-14 | Phase 1 — Refonte popup | Livrée (voir 8.2) ; à revoir dans chaque espace avec un compte connecté |
| 2026-11-14 | Phase 2 — Direction et personnel | Livrée (voir 8.3) ; pages non vues avec un compte connecté |
| 2026-11-14 | Phase 3 — Professeur | Livrée (voir 8.4) |
| 2026-11-14 | Phase 4 — Élève et parent | Livrée (voir 8.5) |
| 2026-11-15 | Audit de branchement | Code branché et vérifié ; Celery worker et Beat non démarrés en local — voir `cloture_rappels_automatiques_2026-11-15.md` |
| — | Phases 5 et 6 | À faire |

### 8.1 Phase 0 — ce qui est en place

| Élément | Fichier |
|---|---|
| Modèles `RappelEnvoye`, `ParametresRappels`, `NotificationPersonnel` | `model/rappel_model.py`, migration `0249_rappels_automatiques` (appliquée en local, uniquement des créations de tables) |
| Moteur | `services/rappels/moteur.py` : `rappels_dus`, `emettre`, `traiter`, `generer`, `heures_calmes`, `parametres` |
| Définition unique des situations | `services/context_popups.py::card()` porte maintenant `code`, `icon`, `family`, `group`, `stage`, `due`, `late`, `count`, `push`, `eleve_id`, `etab` |
| Tâche planifiée | `tasks/celery_tasks.py::generer_rappels_task`, Beat `rappels-automatiques` à :05 et :35 de chaque heure |
| Commande | `python manage.py generer_rappels [--dry-run] [--etablissement ID]` |
| Push du personnel | `services/push_delivery.py` relie `PushDelivery` à `NotificationPersonnel` |
| Import des tâches | `tasks/__init__.py` importe désormais toutes les tâches |

**Comment ajouter un rappel (phases suivantes)** : écrire un fournisseur dans `context_popups.py` qui renvoie des `card(...)` avec un `code`, une `family`, une `icon` et, s'il y a une date, un `deadline`. Rien d'autre : le popup, le centre « À faire », la cloche et le push planifié le prennent automatiquement.

**Règles appliquées par le moteur**
- Situation datée : un rappel par seuil (`j-3`, `j-1`, `j`, `retard-0/1/2`).
- Situation sans date : rappel `initial`, puis `relance-1..3` espacées de 3 jours ; un nouveau dossier dans la liste relance, une liste qui diminue ne relance pas.
- Les cartes `group='news'` (issues d'une notification existante) ne sont jamais re-poussées.
- Heures calmes et plafond quotidien lus dans `ParametresRappels` (21 h–6 h 30, 4 par jour par défaut) ; au-delà du plafond, une synthèse unique par jour.
- Scolarité parent : pas de rappel si une `RelanceImpaye` a été envoyée dans les 3 derniers jours.
- Les notifications créées portent `donnees.rappel = <code>` ; `recent_notifications` les ignore pour ne pas doubler la carte métier.

**Vérifications** : `python manage.py test school_admin.tests_rappels --settings=school.test_settings` → 18 tests réussis. Simulation locale (`--dry-run`) : 17 rappels dus pour 89 personnes sur 3 établissements, aucune erreur, **rien envoyé**.

**À faire côté exploitation** : redémarrer le worker Celery et Beat pour charger la nouvelle tâche et le nouveau calendrier (en production : `sudo systemctl restart aria-celery aria-celery-beat`). Sans redémarrage, aucun rappel planifié ne part.

**Limites connues**
- Aucun rappel réel n'a encore été émis ni reçu sur un appareil.
- Le passage parcourt chaque personne active (quelques requêtes par personne) : à surveiller sur de gros établissements, optimisation par lots prévue si nécessaire.
- Pas encore de page de réglages ni de cloche pour le personnel administratif (phase 2) : `ParametresRappels` se modifie pour l'instant en base ou via le shell.

### 8.2 Phase 1 — ce qui est en place

- `static/school_admin/js/shared/context_popups.js` et `css/shared/context_popups.css` réécrits (classes `arp-*`, version `?v=7`).
- Synthèse d'arrivée : salutation avec prénom, date du jour, groupes « À faire maintenant / À venir / Nouveautés », icônes SVG, compte à rebours coloré (retard, proche), pastille de quantité, bouton d'action par règle, « Plus tard ».
- Centre « À faire » : pastille flottante avec compteur sur toutes les pages privées ; liste complète, section « Reportées », état vide « Tout est à jour ».
- API `api/context-popup/` : `GET ?centre=1`, actions `go` et `later` (revalidées côté serveur), `total` et `greeting` renvoyés par `claim`.
- Mobile : feuille basse pleine largeur ; `prefers-reduced-motion`, clavier et Échap conservés.
- Vérifié visuellement sur une page de démonstration avec données simulées (ordinateur et 375 px). **Non vérifié avec un compte connecté dans chaque espace** : position de la pastille par rapport aux barres de navigation basses à contrôler (variable CSS `--arp-pill-offset`).
- Non livré : jauge de progression « n sur m traitées » (prévue avec les tâches du professeur, phase 3).

### 8.3 Phase 2 — ce qui est en place

**Règles** — `services/rappels/etablissement.py::situations()`, appelée par `context_popups.staff_situations`. Le code affiché est `DIR-xx` pour la direction et `ADM-xx` pour le personnel (même règle, même source).

| Règle | Direction | Personnel (permission) | Seuil |
|---|---|---|---|
| Préinscriptions, demandes de liaison | DIR-01, DIR-02 | ADM-01 (`eleves_inscrire`) | sans date |
| Justifications de note en attente | DIR-03 | ADM-09 (`notes_justifications_voir`) | sans date |
| Relevés non soumis (période finissant entre J-14 et J+7) | DIR-04 | ADM-09 (`notes_liste`) | fin de période |
| Bulletins calculés non publiés (3 à 45 jours après la fin) | DIR-05 | ADM-09 (`bulletins_voir`) | sans date |
| Classes sans appel sur 5 jours ouvrés | DIR-06 | ADM-07 (`presences_liste`) | sans date |
| Échéances de scolarité dépassées | DIR-07 | ADM-04 (`comptabilite_voir`) | sans date |
| Moratoires rompus (7 jours), échéances de moratoire sous 3 jours | DIR-08 | ADM-05 (`comptabilite_voir`) | sans date / échéance |
| Demandes de modification du cahier de texte | DIR-09 | ADM-09 (`professeurs_detail` ou `pointage_controle`) | sans date |
| Séances « à vérifier » ou « contestées » | DIR-10 | ADM-10 (`pointage_controle`) | sans date |
| Convocations du jour | DIR-11 | ADM-08 (`sanctions_liste`) | jour J |
| Session d'examen sous 7 jours | DIR-12 | `examens_voir` | date de début |
| Délibérations en brouillon 7 jours après la période | DIR-13 | `examens_voir` | sans date |
| Fin de période sous 7 jours | DIR-14 | — | date de fin |
| Échéance de prêt non réglée | DIR-15 | ADM-06 (`comptabilite_bilans`) | échéance |
| Dépenses en brouillon | DIR-16 | ADM-06 (`comptabilite_bilans`) | sans date |
| Facture d'abonnement Aria sous 7 jours ou dépassée | DIR-17 | — | échéance |
| Élèves sans classe | — | ADM-02 (`eleves_modifier`) | sans date |

Précisions :
- DIR-06 / ADM-07 ne se déclenche que pendant une période scolaire en cours **et** si l'établissement utilise déjà l'appel numérique (au moins une classe couverte), pour ne pas relancer chaque jour une école qui ne s'en sert pas.
- Une erreur dans ces règles est journalisée et n'empêche pas les autres cartes de s'afficher.

**Non livré dans cette phase**
- ADM-03 (réinscriptions à faire) : la liste des élèves à réinscrire est calculée dans la vue, pas dans un service réutilisable.
- Paie des professeurs à préparer : aucune source fiable d'« à payer ce mois-ci » identifiée.
- DIR-07 reste un rappel « dossiers à suivre » (initial + relances), pas encore une synthèse hebdomadaire du lundi.

**Cloche et notifications du personnel administratif**
- Le personnel partage l'interface de la direction : `context_processors.notifications_directeur` compte ses `NotificationPersonnel`, et la page `directeur:notifications_directeur` les affiche (et seulement les siennes).
- Les notifications de rappel affichent un bouton « Ouvrir » vers la page d'action (direction et personnel).

**Page « Rappels automatiques »** — `directeur:rappels_automatiques` (`/rappels-automatiques/`), réservée au directeur ; lien dans le hub Administration.
- `controllers/rappels_controller.py`, `templates/.../directeur/rappels_automatiques.html`, `css/directeur/rappels.css`.
- Réglages : activation, heures calmes, plafond quotidien (1 à 10), sujets rappelés.
- État : dernier passage du planificateur (alerte s'il date de plus de 2 h), rappels et personnes sur 7 jours.
- « Voir ce qui partirait » (simulation, n'envoie rien) et « Envoyer maintenant » (passage immédiat pour l'établissement).
- Journal des 60 derniers rappels ; `RappelEnvoye.etablissement` ajouté pour cela (migration `0250_rappel_etablissement`).

**Vérifications** : `python manage.py test school_admin.tests_rappels school_admin.tests_hubs_directeur --settings=school.test_settings` → 31 tests réussis (règles, permissions, page de réglages, cloche du personnel). Simulation locale : 18 rappels dus, aucune erreur, rien envoyé.

**Non vérifié** : rendu de la page de réglages et de la page de notifications dans le navigateur (connexion requise) ; réception réelle d'un push.

### 8.4 Phase 3 — ce qui est en place

**Règles** — `services/rappels/professeur.py::situations()`, appelée par `context_popups.teacher_situations` (primaire et secondaire/supérieur ; l'espace est choisi par `niveau_enseignement`).

| Code | Rappel | Source | Seuil |
|---|---|---|---|
| PROF-01 | Appel non fait pour un cours terminé depuis 30 min | emploi du temps publié + `SoumissionListePresence` du jour | jour J |
| PROF-02 | Cours des 7 derniers jours sans séance au cahier de texte | `cahier_texte.cours_du_professeur` | sans date ; un nouveau jour manquant relance |
| PROF-03 | Séances du cahier de texte en brouillon | `CahierTexte.statut='brouillon'` | sans date |
| PROF-04 | Évaluation passée (3 à 45 jours) sans toutes ses notes | notes saisies < effectif inscrit | sans date |
| PROF-05 | Relevé non soumis (période finissant entre J-14 et J+7) | `ReleveNotes.soumis=False` | fin de période |
| PROF-06 | Évaluation à préparer | existant | J-2 |
| PROF-07 | Devoirs à ramasser aujourd'hui | `ExerciceMaison.date_rendu` | jour J |
| PROF-08 | Notes d'examen saisies mais non soumises (secondaire) | `NoteExamen.soumis=False`, session terminée depuis 2 jours | sans date |
| PROF-10 | Cours du lendemain, à partir de 17 h | emploi du temps publié | veille — **option désactivée par défaut** |
| PROF-11 | Cours resté ouvert après son heure de fin (pointage actif) | `SeanceCours.statut='en_cours'` | jour J |

Précisions :
- PROF-01 ne concerne qu'un professeur qui a déjà soumis au moins un appel dans l'année ; PROF-02 et PROF-03 ne concernent qu'un établissement qui utilise déjà le cahier de texte. Une école qui n'utilise pas ces outils n'est pas relancée.
- PROF-08 ne détecte que des notes saisies et non soumises ; une matière sans aucune note saisie n'est pas détectable de façon fiable.
- PROF-09 (réponse de la direction) reste porté par les notifications existantes, affichées dans « Nouveautés ».
- PROF-11 ne rappelle pas un cours à démarrer : le rappel partirait trop tard avec un passage toutes les 30 minutes.

**Option « cours du lendemain »** : champ `ParametresRappels.rappel_cours_demain` (migration `0251_rappel_cours_demain`), interrupteur dans la page « Rappels automatiques ». Servira aussi à l'élève (ELV-06) en phase 4.

**Jauge du jour** : `professeur.progression()` → `context_popups.progress()` → renvoyée par l'API (`claim`, `?centre=1`) et affichée sous le titre du popup (« Aujourd'hui : 1/3 appel(s) · 2/2 cahier(s) de texte »). Affichée seulement pour le professeur, quand il a des cours terminés dans la journée.

**Vérifications** : `python manage.py test school_admin.tests_rappels school_admin.tests_cahier_texte school_admin.tests_hubs_directeur --settings=school.test_settings` → 45 tests réussis. Simulation locale : 19 rappels dus dont un PROF-02 réel, aucune erreur, rien envoyé. Jauge vue sur une page de démonstration (données simulées).

**Non vérifié** : PROF-04, PROF-08 et PROF-11 n'ont pas de test avec données (leurs requêtes s'exécutent sans erreur dans les tests et la simulation, mais aucun cas positif n'a été construit).

### 8.5 Phase 4 — ce qui est en place

**Règles** — `services/rappels/famille.py` (`situations()` appelée par `context_popups.student_situations`, `parent_situations()` appelée par `candidates`), en complément des règles déjà présentes dans `context_popups.py`.

| Code | Rappel | Source | Seuil |
|---|---|---|---|
| ELV-01 / PAR-04 | Devoir à rendre | existant | J-3, J-1, J |
| ELV-02 / PAR-04 | Évaluation | existant | J-3, J-1, J |
| ELV-03 / PAR-09 | Épreuves d'examen sous 7 jours (planning publié uniquement) | `CreneauExamen` + `classes_concernees` | date de la première épreuve |
| ELV-04 / PAR-03 | Convocation | existant | J-7, J-1, J |
| ELV-05 / PAR-06 | Bulletin publié non consulté depuis 2 jours | notification `bulletin` non lue | une seule fois |
| ELV-06 | Cours du lendemain à partir de 17 h | emploi du temps publié de la classe | veille — option `rappel_cours_demain`, éteinte par défaut |
| PAR-01 | Échéance de scolarité | existant ; pas de doublon si une `RelanceImpaye` date de moins de 3 jours | J-3, J, retard |
| PAR-02 | Échéance d'un moratoire actif sous 3 jours | `EcheanceMoratoire` non payée | échéance |
| PAR-05 | Absence non justifiée des 7 derniers jours | `Presence.statut='absent'` | sans date ; un nouveau jour d'absence relance |
| PAR-08 | Demande de liaison validée ou refusée (7 jours) | `DemandeLiaisonParent` | une seule fois (le refus n'est pas poussé, seulement affiché) |

**Nouveau dans le moteur** : `card(..., once=True)` — information ponctuelle, jamais relancée.

**Non livré**
- PAR-07 (réinscription à effectuer) : même raison qu'ADM-03, pas de service réutilisable.
- PAR-04 en synthèse du dimanche soir : les rappels J-3 / J-1 / J par devoir et par évaluation la remplacent.
- PAR-01 n'est pas fusionné avec la relance WhatsApp/SMS : les deux coexistent, avec un garde-fou anti-doublon.

**Vérifications** : `python manage.py test school_admin.tests_rappels school_admin.tests_cahier_texte school_admin.tests_hubs_directeur school_admin.tests_recouvrement --settings=school.test_settings` → 65 tests réussis, dont un cas positif pour chaque nouvelle règle de cette phase. Simulation locale : 22 rappels dus (dont 3 PAR-05 réels), aucune erreur, rien envoyé.

### 8.6 Reste à faire

- Phase 5 (équipe plateforme, optionnelle) : INT-01 à INT-05, middleware popup étendu à `CompteUser`.
- Phase 6 : recette sur appareils réels (push reçu, clic, heures calmes), vue des pages avec un compte connecté dans chaque espace, redémarrage et supervision de Celery worker + Beat, cas de test positifs manquants (PROF-04, PROF-08, PROF-11), optimisation éventuelle du passage sur gros établissements.
