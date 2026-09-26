# Feuille de route UX professeur — navigation sans reload & temps réel

**Statut : feuille validée — R0 + R1 livrés (branche `cursor/prof-ux-r0-r1-a40c`). Pause avant R2.**

Voir section « Livraison R0 / R1 » dans la copie store `docs/feuille-route-prof-ux-temps-reel.md`.

Références : [feuille-route-ui-professeur.md](feuille-route-ui-professeur.md) (UI V0–5 livrée), [design-system-aria.md](design-system-aria.md), [project-context.md](project-context.md).

**Objectifs produit**

1. **Navigation hub** (onglets période / classe / matière / vue) **sans rechargement complet** : fetch + swap de panneaux, URL synchronisée via `history.replaceState`, F5 cohérent.
2. **Temps réel** sur les actions prof (notes, présence, évaluations, sanctions, exercices, justifications, etc.) — prolonger le socle existant (`emit_live`, WebSocket établissement, `enseignant_live.js`).
3. **Fil d’Ariane applicatif** : lien parent dynamique vers la page de retour métier ; **suppression** du bouton header « Retour » (`history.back`) et des CTA « Retour … » redondants — **sauf** dashboard d’accueil (pas de breadcrumb parent).

---

## 1. Verdict audit (état au 2026-09-26)

| Axe | Constat |
|-----|---------|
| **Routing** | **Primaire** : `/enseignant/primaire/…` (`enseignant_primaire`). **Collège / lycée / mixte / supérieur** : `/enseignant/…` (`enseignant`), avec `hub_v3` (secondaire) et `hub_v4` (LMD) via context processors. |
| **Onglets hub** | Markup **directeur-like** en place (`matiere-tabs-bar`, overflow, `prof_matiere_tabs_bar.css`). **Comportement** : liens `<a href="?…">` → **navigation GET full page** (primaire notes, partials `prof_primaire_*_tabs`, hub V3/V4). |
| **Persistance** | `professeur_tab_storage.js` + `localStorage` ; parfois `location.replace` au chargement (merge query). **Pas** d’intercepteur global « clic onglet → fetch ». |
| **Live partiel secondaire** | `gestion_notes.html` / `gestion_presence.html` : `#gestion-notes-live-root` / `#gestion-presence-live-root` + `?live_partial=notes|presence` (XHR) **uniquement** pour **rafraîchissement WS/post-action**, pas pour changement d’onglet. |
| **Primaire notes hub** | `gestion_notes_primaire.html` : **pas** de `gestion-notes-live-root` ; changement période/classe/matière/vue = **reload intégral**. Modales éval : fetch JSON/HTML ponctuel. |
| **Primaire présence hub** | `gestion_presence_primaire.html` : onglets **catégorie** legacy (`switchTab` JS) + barre classes hub en GET ; **sans** `enseignant_live_scripts`. |
| **Temps réel client** | `enseignant_live_scripts.html` → `realtime_page.js` + `enseignant_live.js` sur ~22 écrans ; écoute WS `LIVE_EVENTS` (évaluations, notes, présence, justification, exercice, sanction). |
| **Temps réel serveur** | `_emit_enseignant_live` / `emit_live` : surtout **secondaire** (notes, évaluations, présence, exercices, sanctions, soumission relevé). **Primaire** : émission partielle (ex. création éval, soumission relevé) ; **absent** sur nombreuses actions (justifications primaire, présence liste, modifs notes hub). |
| **Breadcrumb / Retour** | Breadcrumbs ad hoc par template ; **header** `backButton` → `history.back()` (`header_enseignant_new.js`, `header_primaire.html`). Nombreux boutons « Retour aux notes / classes / dashboard » en bas de page. |

---

## 2. Inventaire pages & comportement de navigation aujourd’hui

Légende **Nav onglets** : `GET-full` = rechargement page ; `JS-panel` = panneaux sans changer l’URL ; `XHR-partial` = fragment HTML ; `—` = pas d’onglets hub.

### 2.1 Primaire (`/enseignant/primaire/`)

| Page | Route | Nav onglets / hub | Reload au clic onglet | Live (`data-live-page`) |
|------|-------|-------------------|------------------------|-------------------------|
| Dashboard | `dashboard/` | — | — | Non |
| Classes hub | `classes/?classe=` | Barre classes overflow | **GET-full** | Non |
| Détail classe | `classe/<id>/` | Onglets internes (présence, éval…) | Mix GET / JS | Non |
| Élèves hub | `eleves/?classe=` | Barre classes | **GET-full** | `eleves-gestion` |
| Détail élève | `eleve/<id>/` | — | — | `eleve-detail` |
| **Notes hub** | `notes/?periode&classe&matiere&vue` | 3 barres + vue Relevé/Saisie/Éval | **GET-full** | `notes-gestion` (WS refresh seulement) |
| Noter / relevé | `noter/<classe>/`, `releve/…` | Matières JS (`switchMatiereTab`) | **JS-panel** (souvent POST full) | `notes-noter` |
| Évaluations legacy | `evaluations-classe/<id>/` | Redirect / page dédiée | **GET-full** | `evaluations-liste` |
| Justifications | `justifications-notes/` | Période + classe + matière | **GET-full** | `justifications` |
| Exercices | `exercices/` | Période + classe | **GET-full** | `exercices` |
| Élèves en difficulté | `eleves-difficulte/` | Période + classe | **GET-full** | Non |
| Présence hub | `presence/?classe=` | Classes hub + **tabs catégorie** | Classes **GET-full** ; catégories **JS-panel** | Non |
| Liste appel | `presence/<classe>/` | — | POST puis parfois reload | `presence-liste` |
| Sanctions classe | `sanctions-classe/<id>/` | — | — | Non |
| Profil, EDT, historique, annonces | divers | — | — | Profil : `profil` ; reste Non |

### 2.2 Secondaire & LMD (`/enseignant/`, `hub_v3` / `hub_v4`)

| Page | Route | Nav onglets | Reload au clic | Live |
|------|-------|-------------|----------------|------|
| Dashboard | `dashboard/enseignant/` | — | — | Non |
| Classes / élèves | `classes/`, `eleves/` | Hub classes (+ périodes V3 notes) | **GET-full** | Élèves : oui |
| **Notes** | `notes/` | Périodes + classes (V3) ; LMD périodes par classe | **GET-full** ; corps via `#gestion-notes-live-root` seulement après WS | `notes-gestion` + **XHR-partial** |
| **Présence** | `presence/` | Hub classes | **GET-full** ; corps **XHR-partial** après WS | `presence-gestion` |
| Justifications / exercices / difficulté | idem urls | Hub | **GET-full** | Justif / exo : oui ; difficulté : non |
| Liste appel | `presence/<id>/` | — | POST | `presence-liste` |
| Noter / examens | `noter/…`, `noter-examen/…` | — | Formulaires POST | `notes-noter` |
| Détail classe / élève | `classe/`, `eleve/` | Sous-onglets | Mix | Élève : oui |
| Notifications, annonces, sanctions, EDT | divers | — | — | Non |

### 2.3 Synthèse douleur utilisateur

- **Tous les hubs à barres `matiere-tab-btn`** : l’utilisateur perçoit un « SPA » visuel mais subit un **flash / scroll reset** à chaque changement de filtre.
- **Secondaire** : le live ne couvre que le **bloc central** des hubs notes/présence ; les **barres d’onglets** restent server-rendered au full reload.
- **Primaire notes** (cas signalé) : 3 barres + switch vue = **4 niveaux de GET-full**.
- **Présence primaire hub** : double modèle (hub moderne + ancien `tabs-container`).

---

## 3. Spec — navigation sans rechargement (SPA-like)

### 3.1 Principes

- **Une page hub = un shell stable** : header, bottom nav, barres d’onglets, toolbar, zone `#prof-hub-panel` (unique).
- **Clic onglet** (période, classe, matière, vue, période LMD `periode_<classe_id>`) :
  1. `preventDefault` sur les liens hub (`prof-primaire-tab-link`, `notes-hub-tab-link`, overflow menu).
  2. `fetch` GET même URL avec query mise à jour + en-têtes `X-Requested-With: XMLHttpRequest` + param **`hub_partial=<id>`** (nouveau contrat serveur).
  3. Réponse : **fragment HTML** (panel + éventuellement barres si effectifs changent) ou JSON `{ html, title, kpi }`.
  4. `root.innerHTML = …` ; `layoutTabsOverflowNav()` ; ré-init scripts légers (recherche locale, modales).
  5. **`history.replaceState`** avec query canonique ; **`professeur_tab_storage.syncUrlAndStore`** inchangé.
- **popstate** : re-fetch panel pour F5/back avant-arrière cohérent.
- **Progressive enhancement** : sans JS, les `<a href>` restent valides (comportement actuel).

### 3.2 Contrat serveur proposé

| Paramètre | Usage |
|-----------|--------|
| `hub_partial=panel` | Corps principal (relevé, liste présence, cartes classes, etc.) |
| `hub_partial=chrome` | Barres onglets + KPI si la sélection change les listes disponibles |
| `hub_partial=full` | Fallback debug |

**Vues à étendre** (miroir primaire / secondaire / LMD) :

- `gestion_notes_primaire`, `gestion_notes_enseignant`
- `gestion_presence_primaire`, `gestion_presence_enseignant`
- `gestion_eleves_*`, `gestion_classes_*`, `exercices_maison_*`, `justifications_notes_*`, `eleves_en_difficulte_*`

Partials Django cibles : extraire `#prof-hub-panel` depuis templates existants (comme `gestion_notes_live_fragment.html`).

### 3.3 Module JS unique

**`prof_hub_nav_live.js`** (nom proposé) :

- S’appuie sur `data-prof-hub-key`, `data-prof-hub-fields`, `data-hub-nav-root`.
- Remplace la logique dispersée (`prof_primaire_hub.js` clic = storage only, `gestion_notes_primaire.js` idem).
- Partage overflow avec `tabs_nav_overflow.js`.
- **Ne remplace pas** les navigations **inter-pages** (bottom nav, lien vers détail élève) : full navigation OK.

### 3.4 Cas particuliers

| Cas | Comportement cible |
|-----|-------------------|
| Hub notes `vue=releve\|saisie\|evaluations` | Swap panel ; saisie lourde peut rester lien vers `noter/` avec query retour |
| LMD `periode_<classe_id>` | Inclure dans `data-prof-hub-fields` dynamiques |
| Détail classe onglets évaluations | Phase 2 : barres matière en hub_partial ou fetch léger |
| Impression / PDF | Hors hub live (nouvel onglet) |
| `location.replace` au boot (storage merge) | Conserver ; exécuter **avant** attach hub live |

### 3.5 Acceptation navigation

- Changement période/classe/matière/vue : **aucun** reload document ; URL et storage à jour ; **&lt; 300 ms** ressenti avec cache serveur raisonnable.
- Overflow « Autres » : fonctionnel après swap.
- F5 : état identique au dernier onglet.
- Mobile &lt; 400px : pas de régression scroll / focus accessibilité (`aria-selected` mis à jour).

---

## 4. Spec — temps réel (socle cohérent)

### 4.1 Architecture existante (à conserver)

```
POST/XHR action → vue Django → emit_live(etablissement_id, event_type, payload)
                                      ↓
                         Channels / realtime_service
                                      ↓
                         realtime_client.js (WS) → enseignant_live.js
                                      ↓
                         fetch refresh (fragment ou main-content)
```

- **Périmètre WS** : canal **établissement** (déjà partagé directeur / prof). Filtrage client : `classe_id`, `eleve_id`, `payloadMatchesPage`.

### 4.2 Matrice événements × actions

| Domaine | `event_type` (existant ou à ajouter) | Émission serveur aujourd’hui | Pages prof à rafraîchir | Cible |
|---------|--------------------------------------|------------------------------|-------------------------|--------|
| Évaluation CRUD | `evaluation.creee`, `.modifiee`, `.supprimee` | Secondaire + création primaire | notes hub, listes éval, détail classe | **100 %** primaire + secondaire + LMD ; payload `item` uniforme (`live_serializers`) |
| Notes / relevé | `notes.mise_a_jour` | Soumission relevé ; certaines saisies secondaire | notes hub, noter, relevé | Émettre sur **chaque** POST note (primaire + secondaire), soumission, calcul moyennes |
| Présence | `presence.mise_a_jour` | Liste / validation secondaire | presence hub, liste appel | Primaire liste + hub ; sync **offline** (`presence_offline.js`) → emit après sync |
| Justification | `justification.soumise` | Partiel (notifications) | justifications, détail élève | `_emit_enseignant_live` systématique au POST prof |
| Exercices | `exercice.publie`, `.modifie` | Secondaire POST | exercices hub | Miroir **primaire** |
| Sanctions | `sanction.ajoutee` | Secondaire | détail élève, liste sanctions | Primaire + refresh ciblé |
| Profil | *(nouveau)* `profil.mise_a_jour` | Non | profil | Optionnel faible priorité |

### 4.3 Client `enseignant_live.js` — évolutions

1. **`PAGE_REFRESH`** : ajouter hubs primaire (`notes-gestion` sans live-root → cibler `#prof-hub-panel` + `#prof-hub-chrome`).
2. **`getLiveRootConfig`** : généraliser au contrat `hub_partial` (§3).
3. **Inclusion scripts** : étendre à **toutes** pages avec POST métier (dashboard non) ; minimum : `gestion_presence_primaire`, `gestion_classes_*`, `eleves_en_difficulte_*`, `detail_classe_*`, `liste_sanctions_*`.
4. **Optimistic UI** (vague 3) : pour présence liste (2 statuts), mise à jour ligne immédiate + reconcile WS (pattern directeur `notes_presence_live.js`).
5. **Assistant vocal** : hors refonte ; les actions assistant qui modifient notes/présence doivent **réutiliser** les mêmes `emit_live` (déjà partiel via `assistant_enseignant_complements_actions.py`).

### 4.4 Acceptation temps réel

- Deux onglets prof (même établissement, classes différentes) : modification visible **sans F5** si même filtre ou ignorée proprement si filtre différent.
- POST formulaire bound `AriaLive.bindLiveForm` : réponse JSON `{ ok, message, item }` partout où live attendu.
- Pas de boucle refresh (conserver `shouldSkipWs`, `localItemIds`).

---

## 5. Spec — breadcrumbs « app-like »

### 5.1 Règles

| Règle | Détail |
|-------|--------|
| **Dashboard** | **Aucun** breadcrumb parent (titre page seul). |
| **Page enfant** | Fil **1 niveau** : `[ Lien parent dynamique ] › Titre page courante`. |
| **Lien parent** | **Sémantique métier**, pas `history.back` : ex. liste appel → « Présence » (`gestion_presence`) ; noter → « Notes » avec query conservée ; détail élève → « Élèves » (`?classe=`). |
| **Suppression** | Retirer `#backButton` des headers ; retirer CTA bas de page « Retour au dashboard / aux notes / … » lorsqu’ remplacés par breadcrumb. |
| **Accessibilité** | `<nav aria-label="Fil d'Ariane">`, lien parent focusable, page courante en `aria-current="page"`. |

### 5.2 Implémentation proposée (future)

- Partial **`prof_breadcrumb.html`** alimenté par context processor **`prof_nav_trail`** :
  - `parent_url`, `parent_label`, `current_label`
  - Dérivé de `request.resolver_match.url_name` + query (`classe`, `periode`…).
- Table de correspondance **url_name → parent** (primaire vs secondaire namespaces).
- Design : texte `#64748B`, lien parent `#2563EB` (Design System ARIA).

### 5.3 Acceptation breadcrumb

- Zéro bouton « Retour » générique visible sur parcours prof (header + footers dupliqués).
- Parcours mobile : breadcrumb wrap propre ; bottom nav inchangée.

---

## 6. Vagues d’implémentation proposées

| Vague | Intitulé | Contenu | Recette |
|-------|----------|---------|---------|
| **R0** | Socle hub live | `hub_partial` côté vues ; `#prof-hub-panel` ; **`prof_hub_nav_live.js`** ; feature flag `PROF_HUB_NAV_LIVE` | Primaire **notes** : 3 barres sans reload |
| **R1** | Hubs primaire complets | Présence, élèves, classes, exercices, justifications, difficulté | Bottom nav primaire ; F5 ; mobile |
| **R2** | Hubs secondaire + LMD | Notes / présence V3/V4 ; périodes LMD | 3 profils type établissement |
| **R3** | Temps réel dense | Matrice §4.2 ; extensions `enseignant_live.js` ; JSON POST manquants | 2 sessions simultanées |
| **R4** | Breadcrumbs | `prof_breadcrumb` + suppression back buttons | Parcours détail → hub |
| **R5** | Finitions & perfs | Cache fragment, optimistic présence, tests auto `test_prof_hub_nav_live.py`, doc recette | Charge + a11y |

Branches suggérées : `cursor/prof-ux-r<N>-a40c`.

**Ordre recommandé** : R0 → R1 → R2 (navigation) puis R3 (temps réel en parallèle partiel dès R0 sur notes) → R4 → R5.

**Dépendance** : la feuille UI V0–5 reste valide ; ce plan **ne refond pas** le design visuel des onglets (déjà livré).

---

## 7. Hors scope

- **Directeur**, **assistant vocal / IA**, **comptabilité générale**, **shell / infra VPS**.
- **Élève / parent** (sauf réutilisation involontaire du canal WS établissement).
- Migration **SPA totale** (React/Vue) ou **Turbo Drive** global.
- Refonte métier présence (binaire présent/absent déjà actée dans feuille UI prof).
- Notifications push mobile natives.

---

## 8. Risques & mitigations

| Risque | Mitigation |
|--------|------------|
| Dette double (live_partial vs hub_partial) | Fusionner paramètres en **`hub_partial`** ; alias temporaire `live_partial` |
| Scripts inline cassés après swap | Registry `ProfHub.onPanelLoaded()` ; pas de `onclick` globaux fragiles |
| Charge serveur (fetch à chaque onglet) | Fragment cache par `(prof_id, query)` ; barres séparées si rare |
| SEO / partage URL | Query canonical suffisante (pas de hash) |

---

## 9. Validation attendue

1. Accord sur **contrat `hub_partial`** et périmètre **R0** (hub notes primaire pilote).
2. Priorisation temps réel : **notes + présence** avant sanctions / annonces.
3. Règle breadcrumb : **1 niveau parent** + suppression **backButton** confirmée.
4. Signal **GO** → branche `cursor/prof-ux-r0-a40c` uniquement après validation.

*Rédigé le 2026-09-26 — audit & plan uniquement.*
