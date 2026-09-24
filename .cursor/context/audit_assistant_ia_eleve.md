# Audit + feuille de route — Assistant IA Élève (compte élève seul)

**Date** : 2026-09-24  
**Statut** : **Elv0 livrée** (2026-09-24). Elv1+ **non démarrées**.  
**Branche** : `cursor/assistant-eleve-elv0-a40c`  
**Workspace** : `C:\wamp64\www\goo_school`  
**Références** :
- Parent (Par0–Par8 livrées, réutilisation cible) : [audit_assistant_ia_parent.md](audit_assistant_ia_parent.md)
- Directeur : [audit_assistant_ia_directeur.md](audit_assistant_ia_directeur.md)
- Runtime Gemini (G1–G7) : [audit_assistant_ia_gemini_libre.md](audit_assistant_ia_gemini_libre.md)
- Professeur : [audit_assistant_ia_professeur.md](audit_assistant_ia_professeur.md)

**Objectif utilisateur** : connecter Aria sur **toutes** les pages de l’**espace élève** lorsque l’**élève est connecté avec son propre compte** (pas le mode parent `eleve_consulte_id`). Persona orienté **conseil, organisation, efficacité scolaire** — au service de l’apprenant, **pas** du pilotage d’établissement. **Wolof** si l’élève s’exprime en wolof (oral ou écrit), avec la même exigence de qualité que le parcours parent.

---

## 1. Verdict en une phrase

**Elv0 posé côté backend** : WebSocket **`Eleve` accepté**, persona **`eleve`**, scope self-only, prompt tutoiement, schéma tools **vide** (conseil sans chiffres). **UI élève seul** : widget toujours **absent** (`est_parent` seulement) → **Elv1**. Mode parent sur espace enfant : **persona parent** inchangé.

---

## 2. Périmètre produit (à ne pas diluer)

### 2.1 Ce que l’élève doit vivre avec Aria

| Attendu | Exemples |
|---------|----------|
| **Comprendre sa scolarité** | Notes, moyennes, bulletin, devoirs, EDT, absences, sanctions, convocations |
| **S’organiser** | « Qu’est-ce que j’ai demain ? », « Quels devoirs cette semaine ? », « Prochaine éval ? » |
| **Conseil & motivation** | Expliquer une moyenne, proposer un plan de révision, rappeler les échéances — **sans** parler à sa place aux adultes de l’établissement |
| **Efficacité dans l’app** | Ouvrir la bonne page, résumer une annonce, notifications |
| **Wolof** | Élève en wolof → réponses **dans la même langue** (français si repasse en français) |

### 2.2 Hors persona (même si le LLM « sait »)

- Tout le **directeur** : effectifs, caisse, RH, préinscriptions, validation liaisons, publication bulletins, examens **direction**, comptabilité générale.
- Tout le **professeur** : saisie notes, appel, création évaluations, sanctions **enregistrées**.
- **Scolarité / paiements** : pas d’écran `eleve:*` dédié reste dû / reçus (hub **parent** uniquement) → **pas** de tool scolarité ni paiement vocal pour l’élève.
- Données d’**autres élèves** (camardes, effectifs classe, moyennes de classe globales non exposées à l’élève).
- **Mot de passe / photo** : rester **formulaires Django** (`profil_eleve`) — pas de modification vocale.
- Shell, VPS, SQL, `manage.py` arbitraire.

### 2.3 Distinction parent vs élève (critique)

| Dimension | Parent (`persona=parent`) | Élève (`persona=eleve`) |
|-----------|----------------------------|-------------------------|
| Auth WS | `Parent` | `Eleve` |
| Scope | Enfants `LienFamilial` + session `eleve_consulte_id` | **`request.user` uniquement** |
| UI espace enfant | `est_parent=True` → widget parent | **`est_parent=False`** → widget **élève** (aujourd’hui **absent**) |
| Tools multi-enfants | `get_mes_enfants`, `select_enfant`, `get_scolarite_famille`, … | **Interdits** |
| Ton prompt | Famille, « votre enfant » | Tutoiement/vouvoiement **élève**, « toi / ton parcours » |

Les deux personas peuvent **partager** les fonctions de lecture (`read_notes`, `read_devoirs`, …) mais **pas** le même schéma Gemini ni le même cache.

---

## 3. Architecture actuelle (stack assistant)

| Couche | Fichier | État pour **élève seul** |
|--------|---------|---------------------------|
| WebSocket | `assistant_consumer.py` | **`Eleve` → persona `eleve`** ; `Parent` → `parent` (session enfant consulté séparé) |
| Contexte | `build_assistant_context` | `eleve=` + `persona='eleve'` |
| LLM | `gemini_assistant_service.py` | **`SYSTEM_PROMPT_ELEVE`** (tutoiement, Elv0 sans tools chiffres) |
| Schéma / tools | `assistant_eleve_tools.py` | **`get_eleve_tools_schema()` → []** ; blocage directeur/prof/parent |
| UI | `eleve/partials/bottom_nav_eleve.html` | **Elv1** : `assistant_vocal_eleve.html` ; aujourd’hui widget **parent only** |
| Vues | `eleve_view.get_eleve_from_request` | `(Eleve user, est_parent=False)` **déjà supporté** |
| STT/TTS | `assistant_parent_language.py` | Réutilisable (préférence langue) avec copy/prompt élève |
| gtranslate | `eleve/partials/header.html` | UI statique ; **ne remplace pas** wolof vocal Aria |

**Règle G7** (alignement parent Par6) : lectures + conseils → Gemini continue ; écritures → brouillon + carte **oui / modifier / annuler** ; pas de takeover wizard directeur.

---

## 4. Parcours utilisateur élève (session & sécurité)

### 4.1 Authentification

- Modèle `Eleve`, backend multi-modèles (`authentication_backends.py`) : username ou matricule + mot de passe, `actif=True`.
- Pas de `eleve_consulte_id` en session : l’élève **est** l’utilisateur.

### 4.2 Implications assistant

- Consumer : `isinstance(user, Eleve)` → établissement = `eleve.etablissement`, `persona='eleve'`, **refus** si `Parent` sans enfant ou autre profil.
- Contexte : `build_assistant_context(..., eleve=user, persona='eleve')` — **jamais** accepter un `eleve_id` argument qui ≠ user.pk (anti-IDOR).
- Pas de `select_enfant` ni navigation hub parent.

---

## 5. Inventaire — URLs, vues, templates (`eleve:`)

Source : `school_admin/personal_url/eleve_url.py` + templates `school_admin/templates/school_admin/eleve/`.

| Route | Vue | Template | Bottom nav | Widget Aria aujourd’hui |
|-------|-----|----------|------------|-------------------------|
| `eleve/dashboard/` | `dashboard_eleve` | `dashboard_eleve.html` | Oui | **Non** (élève seul) |
| `eleve/devoirs/` | `devoirs_eleve` | `devoirs_eleve.html` | Oui | **Non** |
| `eleve/bulletin/` | `bulletin_eleve` | `bulletin_eleve.html` ou `bulletin_eleve_superieur.html` | Non | **Parent only** (include conditionnel) |
| `eleve/emploi-du-temps/` | `emploi_du_temps_eleve` | `emploi_du_temps_eleve.html` | Oui | **Non** |
| `eleve/notes-evaluations/` | `notes_evaluations_eleve` | `notes_evaluations_eleve.html` | Oui | **Non** |
| `eleve/absences-retards/` | `absences_retards_eleve` | `absences_retards_eleve.html` | Oui | **Non** |
| `eleve/profil/` | `profil_eleve` | `profil_eleve.html` | Oui (menu) | **Non** |
| `eleve/sanctions/` | `sanctions_eleve` | `sanctions_eleve.html` | Oui | **Non** (vue OK élève **et** parent) |
| `eleve/convocations/` | `convocations_eleve` | `convocations_eleve.html` | Oui | **Non** |
| `eleve/annonces/` | `annonces_eleve` | `annonces_eleve.html` | Oui | **Non** |
| `eleve/notifications/` | `notifications_eleve` | `notifications_eleve.html` | Non | **Parent only** |
| `eleve/notifications/<id>/click/` | `notification_eleve_click` | redirect | — | — |
| `eleve/historique-annees/` | `historique_annees_eleve` | `historique_annees_eleve.html` | Non | **Parent only** |
| `eleve/historique-annees/<id>/` | `detail_historique_annee_eleve` | `historique_annee_detail_eleve.html` | Non | **Parent only** |
| `eleve/deconnexion/` | `deconnexion_eleve` | redirect | — | — |

**Partials** : `eleve/partials/bottom_nav_eleve.html`, `eleve/partials/header.html` (gtranslate, cloche notifications).

**Gap UI majeur (Elv1)** : inclure un partial **`assistant_vocal_eleve.html`** (ou generaliser le parent avec `persona_ui=eleve`) sur **toutes** les lignes du tableau — **sans** `{% if est_parent %}` pour l’élève connecté ; conserver le widget **parent** quand `est_parent`.

---

## 6. Fonctions métier déjà disponibles (réutilisation)

| Domaine | Vue / modèle | Réutilisable pour tools `eleve` |
|---------|--------------|----------------------------------|
| Notes / moyennes | `notes_evaluations_eleve`, primaire/secondaire/supérieur | Oui → `assistant_parent_scolaire.read_*` |
| Bulletin | `bulletin_eleve` (+ variante supérieur) | Oui → `get_bulletin_enfant` → renommer / alias `get_mon_bulletin` |
| Devoirs | `devoirs_eleve` | Oui |
| Absences | `absences_retards_eleve` | Oui |
| Sanctions | `sanctions_eleve` | Oui (déjà accessible élève) |
| Convocations | `convocations_eleve` | Oui |
| Annonces | `annonces_eleve` | Oui (filtre destinataires élèves) |
| Notifications | `NotificationEleve` ; page marque **toutes** non lues à la visite | Lecture oui ; action vocale **optionnelle** (voir §8.4) |
| Profil | Photo + MDP (POST, élève seul) | Lecture infos OK ; **pas** d’apply vocal |
| Historique | `historique_annees_*` | Oui (Par5 élève) |
| Scolarité / reçus | **Absent** espace élève | **Hors scope** assistant élève v1 |

**Catalogue pages** : sous-ensemble de `assistant_pages_parent.PAGE_CATALOG` (`espace=enfant`) **sans** `requires_enfant_session` (toujours « moi ») → nouveau `assistant_pages_eleve.py` ou filtre `persona=eleve`.

---

## 7. Catalogue tools proposés (persona `eleve`)

### 7.1 Lecture & navigation (~14)

| Tool | Rôle | Alignement vue |
|------|------|----------------|
| `get_mon_resume` | Synthèse dashboard (classe, moyenne, notifs) | `dashboard_eleve` |
| `lister_pages` | Clés navigation espace élève | Catalogue Elv |
| `ouvrir_page` | Nav vers `eleve:*` | Même moteur que parent, scope élève |
| `get_annonces` | Annonces élève | `annonces_eleve` |
| `get_notifications` | Liste / non lues | `notifications_eleve` |
| `get_mes_notes` | Notes publiées | `notes_evaluations_eleve` |
| `get_mon_bulletin` | État publication + moyenne | `bulletin_eleve` |
| `get_mes_devoirs` | Devoirs / échéances | `devoirs_eleve` |
| `get_mes_absences` | Totaux + récents | `absences_retards_eleve` |
| `get_mes_sanctions` | Sanctions | `sanctions_eleve` |
| `get_mes_convocations` | Convocations | `convocations_eleve` |
| `get_mon_emploi` | EDT | `emploi_du_temps_eleve` |
| `get_mon_profil` | Infos compte (sans secrets) | `profil_eleve` |
| `get_mon_historique` | Années archivées (option Par5) | `historique_annees` |

**Nommage** : préfixe `get_mes_*` / `get_mon_*` pour différencier du parent `get_*_enfant` et éviter confusion LLM.

### 7.2 Schéma filtré par type d’établissement

- Reprendre la logique `assistant_parent_schema._flags_for_parent_ctx` → **`_flags_for_eleve_ctx(ctx)`** avec **un seul** établissement (celui de l’élève).
- Descriptions Gemini : primaire / collège-lycée / supérieur **LMD étudiant** — **pas** « pilotage direction », **pas** modules/examens direction.
- Cache Gemini dédié : **`aria-eleve-tools-v1`** (+ suffixe `primaire` / `lycee` / `superieur`).

### 7.3 Écriture confirmée (priorité basse)

| Action | Justification | Alignement |
|--------|---------------|------------|
| `marquer_notification_lue` (option) | Clic cloche = tout marquer ; vocal pourrait cibler une notif | `NotificationEleve` ; confirm si implémenté |
| *(exclu)* | Photo profil, mot de passe | `profil_eleve` POST only |

**Interdit** : paiement, liaison familiale, justification absence (pas de vue élève), contact prof/directeur messagerie.

---

## 8. Wolof (Elv3)

- **Réutiliser** : `assistant_parent_language.py` (STT multi `fr-FR`/`wo-SN`, TTS `language='wo'`, chips Auto/FR/Wolof).
- **Adapter** : copy accueil (`ELEVE_WELCOME_BILINGUAL`), `SYSTEM_PROMPT_ELEVE` (tutoiement, examples wolof jeune/public).
- **Tests** : reprendre pattern `test_assistant_parent_language.py` → `test_assistant_eleve_language.py`.
- gtranslate header : complément UI seulement.

---

## 9. Feuille de vagues proposées (Elv0–Elv8)

| Vague | Contenu | STOP / livrable |
|-------|---------|-----------------|
| **Elv0** | WS accepte `Eleve` ; `assistant_eleve_scope.py` (self-only) ; `execute_eleve_tool` bloque directeur/prof/parent-tools ; prompt + schéma vide | Tests scope + refus WS parent/eleve croisé |
| **Elv1** | UI : `assistant_vocal_eleve.html` + CSS ; include sur **14 écrans** ; JS (`assistant_vocal.js` flag `persona=eleve`) ; welcome WS | Recette présence widget |
| **Elv2** | Navigation : `get_mon_resume`, `lister_pages`, `ouvrir_page` ; catalogue `assistant_pages_eleve` | Tests tools + ouvrir devoirs |
| **Elv3** | Wolof v1 (STT/TTS/chips) | Tests language + recette manuelle |
| **Elv4** | Lecture scolaire : notes, bulletin, devoirs, absences, sanctions, convocations, EDT (wrappers scolaire) | Tests par type établissement |
| **Elv5** | Historique années + notifications enrichies (`notification_id`) | Tests lecture |
| **Elv6** | Parité G1–G7 : pas takeover lectures ; multi-tools ; suggestions ; cache `aria-eleve-tools-v1` | Tests WS + G7 |
| **Elv7** | Actions confirmées (si `marquer_notification_lue` retenu) | Tests apply / refus |
| **Elv8** | Recette multi-types (primaire + collège + supérieur) + checklist métier + doc audit final | `test_assistant_eleve_recette_elv8.py` |

**Ordre** : une vague = une branche `cursor/assistant-eleve-elv<N>-a40c`, commit, push, validation utilisateur avant la suivante (même discipline que parent).

---

## 10. Critères de validation métier (checklist cible Elv8)

| # | Critère | Auto (cible) | Manuel |
|---|---------|--------------|--------|
| 1 | Bulle Aria sur **chaque** page §5 (élève seul) | Scan templates | Parcours navigateur |
| 2 | Notes / devoirs / absences → **tools**, pas d’invention | Tests tools | Dialogue Gemini |
| 3 | Impossible d’accéder à un autre `eleve_id` | Tests scope | — |
| 4 | Wolof | `wolof_marker_score` + STT mock | TTS réel |
| 5 | « Ouvre mes devoirs » → `eleve:devoirs_eleve` | Test `ouvrir_page` | UI |
| 6 | Aucun tool directeur/prof/CG dans schéma | Scan schema | — |
| 7 | Écriture seulement après confirm | Tests actions | Carte UI |

---

## 11. Hors scope (explicitement)

- Persona **parent** (déjà Par0–Par8) — ne pas fusionner les schémas.
- Assistant pour **élève non connecté** (public).
- Paiement vocal, scolarité vocal, CG, tools directeur/enseignant.
- Publication bulletin, examens session, effectifs classe.
- Shell / déploiement / SQL.

---

## 12. Arbitrages validés (2026-09-24)

1. Partial **`assistant_vocal_eleve.html`** + `data-persona="eleve"` → **Elv1** (pas Elv0).
2. **Pas** de tool `marquer_notification_lue` (Elv7 sauté ou très léger plus tard).
3. **Tutoiement** dans `SYSTEM_PROMPT_ELEVE`.
4. Mode parent sur espace enfant : **persona parent** (ne pas activer `eleve`).
5. Supérieur : libellés « étudiant » à affiner en Elv4/Elv8.

---

## 13. Compteurs (état au audit)

| Élément | Nombre |
|---------|--------|
| Routes `eleve:` (dont redirect/logout) | 15 |
| Écrans élève rendus | 14 |
| Templates élève | 14 + partials |
| Widget Aria élève seul | **0** (Elv1) |
| Tools assistant élève (exposés) | **0** (Elv0) ; ~14 lecture prévus Elv2–Elv5 |
| Tests assistant élève | **11** (scope + WS Elv0) |
| Personas WS acceptés | directeur, enseignant*, parent, **`eleve`** |

---

## 14. Livraison Elv0 (2026-09-24)

- Fichiers : `assistant_eleve_scope.py`, `assistant_eleve_tools.py`.
- Consumer : résolution `Eleve`, welcome `assistant.welcome` persona `eleve`.
- `execute_tool` → `execute_eleve_tool` ; blocage `PARENT_TOOL_NAMES_ALL` + préfixes directeur/prof.
- `assert_self_only` : refus tout `eleve_id` ≠ compte connecté.
- Tests : `test_assistant_eleve_scope.py`, `test_assistant_eleve_ws.py`.

### Prochaine étape

**Elv1** — widget `assistant_vocal_eleve.html` sur les 14 écrans (élève seul).

---

*Stop après Elv0 — pas de Elv1 dans cette livraison.*
