# Feuille de route UX professeur — plan intégral (tous types d’établissement)

**Statut : plan d’implémentation — **P0–P3** livrés** (branches `cursor/prof-ux-p0-a40c` … `cursor/prof-ux-p3-a40c`). **Hotfix nav** livré (`cursor/prof-ux-hotfix-nav-8a75`). **P4 en cours** (nav XHR réactivée + `emit_live` notes primaire + refresh hub panel élargi).

**Remplace / complète** : [feuille-route-prof-ux-temps-reel.md](feuille-route-prof-ux-temps-reel.md) (vagues R0–R5 partielles, inventaire obsolète sur plusieurs lignes).

**Objectif produit** : expérience **cohérente, fluide et temps réel** pour **100 % des écrans professeur** (primaire, collège, lycée, mixte, supérieur LMD) — navigation hub sans reload, fil d’Ariane sémantique, live WS sur les actions métier, sans refonte SPA React.

**Références** : [design-system-aria.md](design-system-aria.md), [feuille-route-ui-professeur.md](feuille-route-ui-professeur.md), [project-context.md](project-context.md).

---

## 0. Synthèse exécutive

| Domaine | État actuel (code) | Cible intégrale |
|---------|-------------------|-----------------|
| **Contrat `hub_partial`** | 6 vues branchées (primaire notes/élèves/présence/exercices ; secondaire notes/présence) | Toutes les pages à barres hub `matiere-tabs-bar` |
| **`prof_hub_nav_live.js`** | 8 templates avec `data-prof-hub-nav-live="1"` | Tous hubs + onglets query canoniques |
| **Reload au clic onglet** | Encore **GET-full** sur ~15 hubs / pages à filtres | **XHR + swap** partout où un `<a href="?…">` sert de filtre |
| **Temps réel** | `enseignant_live.js` + `live_partial` / `hub_partial=panel` partiel ; `emit_live` inégal | Matrice complète POST → `emit_live` + refresh ciblé |
| **Breadcrumbs** | ~~`prof_nav_trail` ~6 règles ; CTA « Retour … » restants~~ **P3 livré** | Table `url_name → parent` + `prof_breadcrumb.html` ; CTA génériques retirés |
| **Bug P0** | ~~Crash exercices primaire~~ **Corrigé** (template + alias vue + tests) | — |

---

## P0 — Correctif crash Exercices primaire ✅ **LIVRÉ** (2026-09-26)

**Branche** : `cursor/prof-ux-p0-a40c`  
**Fichiers** : `prof_primaire_periode_tabs.html` (branches `{% if periodes %}` / `{% elif periodes_scolaires %}`), alias `periodes_scolaires` dans `exercices_maison_primaire`, tests `test_exercices_full_page_periode_classe` + `test_exercices_hub_partial_swap_periode_classe`.

---

## P0 — Correctif crash Exercices primaire (référence audit)

### Symptôme

- **URL** : `http://127.0.0.1:8001/enseignant/primaire/exercices/?periode=2&classe=15`
- **Erreur** : `VariableDoesNotExist` — *Failed lookup for key `[name]'periodes_scolaires'`*

### Cause racine (audit template)

1. La vue `exercices_maison_primaire` passe **`periodes`** et **`periode_selectionnee`** au contexte, **pas** `periodes_scolaires`.
2. Le partial partagé `prof_primaire_periode_tabs.html` contient :
   - `{% if periodes or periodes_scolaires %}`
   - `{% with periodes_list=periodes|default:periodes_scolaires … %}`
3. Avec `string_if_invalid` / résolution stricte Django, le filtre **`default:periodes_scolaires`** force la résolution de `periodes_scolaires` même lorsque `periodes` est présent → **500** si la clé absente.
4. Le crash apparaît en **navigation hub live** (`?hub_partial=hub` XHR) et au **premier rendu** si la branche `{% if periodes or periodes_scolaires %}` évalue la seconde variable.

### Correctif P0 (spec)

| Option | Action | Recommandation |
|--------|--------|----------------|
| A | Alias contexte vue : `'periodes_scolaires': periodes` (+ tests) | Rapide, compatible secondaire |
| B | Template : `{% if periodes %}` uniquement + `periodes_list=periodes` | Plus propre long terme |
| C | Context processor prof : normaliser `periodes` / `periodes_scolaires` sur toutes les vues hub | **Recommandé** avec A en hotfix |

**Recette P0** : GET full page + clic onglet période/classe sans JS + clic onglet avec `prof_hub_nav_live` ; `test_prof_hub_partial` exercices primaire.

---

## Hotfix nav / session / onglets (2026-09-26) — **base P4**

**Branche** : `cursor/prof-ux-hotfix-nav-8a75` (base P3 `99d393c9`).

Trois bloqueurs recette (primaire + secondaire + LMD) :

1. **302 `/connexion/?next=/enseignant/…`** — `get_user()` sans `_auth_user_type` renvoyait le premier modèle au même PK (établissement / CompteUser). Hash de session invalide → Django **flush** → middleware anonyme. Correctif : `persist_auth_user_type` (signal + OTP), contexte async-safe, refus de collision, `LOGIN_URL=/connexion/`.
2. **Onglets inertes** — `preventDefault` + XHR qui avalait la page login. Fetch refuse redirect `/connexion/` et HTML sans `#prof-hub-chrome`.
3. **Double barre** — pills hub (classe / période / matière) **conservées** ; rangée CP/CE1/… (`.tabs-nav` + `.classes-tabs`) masquée via `prof_primaire_hub.css`.

**P4** : reprise après correctifs session — `prof_hub_nav_live.js` (clic + fallback GET), alias `periodes` dans `render_prof_hub_partial`, `notes.mise_a_jour` sur saisie/calcul/publication primaire.

---

## P3 — Breadcrumbs v2 ✅ **LIVRÉ** (2026-09-26)

**Branche** : `cursor/prof-ux-p3-a40c`  
**Contrat** : `prof_nav_trail` + `prof_breadcrumb.html` — 1 niveau `[Parent] › courant` ; hubs et dashboards sans fil ; query `classe`/`periode`/`matiere`/`vue` conservée (`classe_id` du path → `?classe=`).  
**Enfants mappés** (primaire + secondaire/LMD) : `noter_eleves`, `voir_releve`, `creer_evaluation`, `liste_evaluations`, `modifier_evaluation`, `evaluations_classe` (primaire), `noter_examen` / `noter_examen_session`, `liste_presence`, `detail_eleve`, `detail_classe`, `historique_presence`, `historique_sanctions`, `liste_sanctions_classe`, `historique_annees`, `historique_annee_detail`.  
**CTA** : retrait des « Retour » / `history.back` / « Retour aux notes / dashboard » redondants sur les pages prof (hubs P0–P2 inchangés). Alias namespace `school_admin` → `enseignant` (URLs secondaire aussi enregistrées sous `school_admin`).

---

## P2 — Hubs secondaire/LMD restants ✅ **LIVRÉ** (2026-09-26)

**Branche** : `cursor/prof-ux-p2-a40c`  
**Pages** (`hub_prof_ui` V3/V4) : `gestion_classes`, `gestion_eleves`, `justifications_notes`, `exercices_maison`, `eleves_en_difficulte` — partials `*_enseignant_hub_swap.html` / `*_hub_panel.html`, `data-prof-hub-nav-live="1"`. Notes/présence inchangés.

---

## P1 — Hubs primaire restants ✅ **LIVRÉ** (2026-09-26)

**Branche** : `cursor/prof-ux-p1-a40c`  
**Pages** : `gestion_classes`, `justifications_notes`, `eleves_en_difficulte` — partials `*_hub_swap.html` / `*_hub_panel.html`, `render_prof_hub_partial`, `data-prof-hub-nav-live="1"`. Justifications : cartes classe/matière en `prof-hub-nav-link` ; `notes-data` dans le panel + re-init JS sur `prof-hub-panel-loaded`.

---

## 1. Inventaire COMPLET — URLs professeur

**Légende**

- **Nav hub** : barres période / classe / matière / vue (overflow).
- **Reload onglet** : comportement **aujourd’hui** au clic filtre hub (sans tenir compte du JS si non activé).
- **hub_partial** : vue Django répond à `?hub_partial=hub|panel` + XHR.
- **nav-live** : `data-prof-hub-nav-live="1"` + `prof_hub_nav_live.js`.

### 1.1 Primaire — namespace `enseignant_primaire` (`/enseignant/primaire/`)

| url_name | Chemin | Nav hub | Reload onglet (état) | hub_partial | nav-live | Live (`data-live-page`) | Breadcrumb |
|----------|--------|---------|----------------------|-------------|----------|-------------------------|------------|
| `dashboard` | `dashboard/` | — | — | Non | Non | Non | Non (règle) |
| `gestion_classes` | `classes/?classe=` | Classe | **XHR** si JS | **Oui** | **Oui** | Non | Non |
| `detail_classe` | `classe/<id>/` | Onglets internes | Mix GET / JS | Non | Non | Non | **Oui** (classes) |
| `gestion_eleves` | `eleves/?classe=` | Classe | **XHR** si JS | **Oui** | **Oui** | `eleves-gestion` | Non |
| `detail_eleve` | `eleve/<id>/` | Sous-onglets | GET / JS | Non | Non | `eleve-detail` | **Oui** (élèves) |
| `gestion_notes` | `notes/?…` | Période+classe+matière+vue | **XHR** si JS | **Oui** | **Oui** | `notes-gestion` | Non |
| `justifications_notes` | `justifications-notes/` | Période+classe+matière | **XHR** si JS (barres + cartes matière) | **Oui** | **Oui** | `justifications` | Non |
| `exercices_maison` | `exercices/?…` | Période+classe | **XHR** si JS | **Oui** | **Oui** | `exercices` | Non |
| `gestion_presence` | `presence/?classe=` | Classe + tabs catégorie | Classe **XHR** ; catégorie **JS-panel** | **Oui** | **Oui** | Non (*scripts ajoutés récemment*) | Non |
| `eleves_en_difficulte` | `eleves-difficulte/` | Période+classe | **XHR** si JS | **Oui** | **Oui** | Non | Non |
| `noter_eleves` | `noter/<classe>/` | Matières | **JS-panel** / POST | Non | Non | `notes-noter` | **Oui** (notes) |
| `voir_releve` | `releve/<classe>/` | — | GET | Non | Non | Partiel | **Oui** (notes) |
| `soumettre_releve` | POST | — | — | — | — | emit | — |
| `imprimer_releve` | GET print | — | Nouvel onglet | — | — | — | — |
| `creer_evaluation` | `evaluation/creer/<classe>/` | — | POST | Non | Non | Partiel | **Oui** (notes) |
| `modifier_evaluation` | `modifier-evaluation/<id>/` | — | POST | Non | Non | Partiel | **Oui** (évaluations) |
| `supprimer_evaluation` | POST | — | — | — | — | Partiel | — |
| `liste_evaluations` | `evaluations/` | Filtres | GET-full | Non | Non | `evaluations-liste` | **Oui** (notes) |
| `evaluations_classe` | `evaluations-classe/<id>/` | — | GET-full | Non | Non | Oui | **Oui** (évaluations) |
| `calculer_moyennes` | POST | — | — | — | — | — | — |
| `liste_presence` | `presence/<classe>/` | — | POST appel | Non | Non | `presence-liste` | **Oui** (présence) |
| `valider_presence` | POST | — | — | — | — | via service | — |
| `modifier_presence` | POST | — | — | — | — | Partiel | Non |
| `historique_presence` | `historique-presence/<eleve>/` | — | GET | Non | Non | `presence-historique` | **Oui** (élève) |
| `justifier_absence` | POST | — | — | — | — | Partiel | Non |
| `imprimer_tableau_presence` | GET print | — | Nouvel onglet | — | — | — | — |
| `soumettre_sanction` | POST | — | — | — | — | emit récent | — |
| `historique_sanctions` | GET | — | GET | Non | Non | Non | **Oui** (élève) |
| `liste_sanctions_classe` | `sanctions-classe/<id>/` | — | GET | Non | Non | Non | **Oui** (élèves) |
| `parametres_profil` | `parametres-profil/` | — | — | Non | Non | `profil` | Non |
| `historique_annees` | `historique-annees/` | — | GET | Non | Non | Non | **Oui** (profil) |
| `historique_annee_detail` | `historique-annees/<id>/` | — | GET | Non | Non | Non | **Oui** (années) |
| `emploi_du_temps` | `emploi-du-temps/` | — | GET | Non | Non | Non | Non |
| `annonces_enseignant` | `annonces/` | — | GET | Non | Non | Non | Non |

### 1.2 Secondaire / mixte / LMD — namespace `enseignant` (`/enseignant/`, `/dashboard/enseignant/`)

**Flags** : `hub_v3` (collège/lycée/mixte), `hub_v4` (supérieur), `hub_prof_ui = hub_v3 ∨ hub_v4`.

| url_name | Chemin | Nav hub (si hub_prof_ui) | Reload onglet (état) | hub_partial | nav-live | Live | Breadcrumb |
|----------|--------|--------------------------|----------------------|-------------|----------|------|------------|
| `dashboard_enseignant` | `/dashboard/enseignant/` | — | — | Non | Non | Non | Non |
| `gestion_classes` | `classes/?classe=` | Classe | **XHR** si JS (hub_prof_ui) | **Oui** | **Oui** | Non | Non |
| `gestion_eleves` | `eleves/?classe=` | Classe | **XHR** si JS (hub_prof_ui) | **Oui** | **Oui** | `eleves-gestion` | Non |
| `gestion_notes` | `notes/?…` | V3: période+classe ; V4: classe + périodes/classe | **XHR** si JS | **Oui** | **Oui** | `notes-gestion` | Non |
| `gestion_presence` | `presence/?classe=` | Classe | **XHR** si JS | **Oui** | **Oui** | `presence-gestion` | Non |
| `justifications_notes` | `justifications-notes/` | V3/V4 classe (+ période selon template) | **XHR** si JS | **Oui** | **Oui** | `justifications` | Non |
| `exercices_maison` | `exercices/?…` | V3: période+classe ; V4: classe | **XHR** si JS | **Oui** | **Oui** | `exercices` | Non |
| `eleves_en_difficulte` | `eleves-difficulte/` | Période+classe | **XHR** si JS | **Oui** | **Oui** | Non | Non |
| `noter_eleves` | `noter/<classe>/` | — | POST / JS | Non | Non | `notes-noter` | **Oui** (notes) |
| `noter_examen` | `noter-examen/<classe>/` | Session | POST | Non | Non | `notes-noter` | **Oui** (notes) |
| `voir_releve` | `releve/<classe>/` | — | GET | Non | Non | Partiel | **Oui** (notes) |
| `api_releve_modal` | API | — | XHR | — | — | — | — |
| `liste_evaluations` | `evaluations/` | Filtres | GET-full | Non | Non | `evaluations-liste` | **Oui** (notes) |
| `creer/modifier/supprimer_evaluation` | divers | — | POST | Non | Non | emit partiel | **Oui** (créer→notes, modifier→évaluations) |
| `liste_presence` | `presence/<classe>/` | — | POST | Non | Non | `presence-liste` | **Oui** (présence) |
| `detail_classe` | `classe/<id>/` | Onglets | Mix | Non | Non | Non | **Oui** (classes) |
| `detail_eleve` | `eleve/<id>/` | Onglets | Mix | Non | Non | `eleve-detail` | **Oui** (élèves) |
| `notifications_enseignant` | `notifications/` | — | GET | Non | Non | Non | Non |
| `annonces_enseignant` | `annonces/` | — | GET | Non | Non | Non | Non |
| *(autres)* | profil, EDT, historique, sanctions… | — | GET / POST | Non | Non | Variable | historique / sanctions : **Oui** |

### 1.3 Pages encore en **reload full page** au clic onglet hub (priorité produit)

**Primaire**

- Onglets **catégorie** internes (JS, hors query URL) : `gestion_classes`, `gestion_eleves`, `gestion_presence`, `eleves_en_difficulte`, `justifications_notes` (grille catégories)

**Secondaire / LMD (hub_prof_ui)**

- Onglets **catégorie** internes (JS) sur classes, élèves, exercices, justifications, difficulté
- Établissements **hors** hub V3/V4 : navigation legacy GET-full

**Legacy / sans hub_prof_ui**

- Tous les établissements ou profils hors V3/V4 : onglets legacy → **GET-full** (progressive enhancement obligatoire).

---

## 2. Spec — navigation sans reload (universelle)

### 2.1 Principes (inchangés, étendus)

1. **Shell stable** : header, bottom nav, `#prof-hub-chrome`, `#prof-hub-panel`.
2. **Clic** sur `a.prof-hub-nav-link` (et overflow) → `fetch` GET + `hub_partial=hub` → swap chrome+panel → `history.replaceState` → `prof-hub-panel-loaded`.
3. **Sans JS** : les `<a href>` restent valides.
4. **Un module** : `prof_hub_nav_live.js` ; pas de duplication dans `gestion_*.js` pour les clics hub.
5. **LMD** : champs dynamiques `periode_<classe_id>` dans `data-prof-hub-fields` (builder côté template).

### 2.2 Contrat serveur (canonical)

| Paramètre | Fragment |
|-----------|----------|
| `hub_partial=hub` | `#prof-hub-chrome` + `#prof-hub-panel` |
| `hub_partial=chrome` | Barres seules (lists effectifs changent) |
| `hub_partial=panel` | Corps (+ live roots internes) |
| `live_partial=notes\|presence` | **Alias déprécié** — maintenu jusqu’à fin migration ; client WS → `hub_partial=panel` |

**En-têtes** : `X-Requested-With: XMLHttpRequest`.

### 2.3 Checklist par page hub (Definition of Done navigation)

- [ ] `#prof-hub-chrome` / `#prof-hub-panel` + `*_hub_swap.html`
- [ ] `render_prof_hub_partial` + skip redirect canonique si XHR
- [ ] `data-prof-hub-nav-live="1"` + `data-prof-hub-key` + `data-prof-hub-fields`
- [ ] Liens onglets : classe `prof-hub-nav-link`
- [ ] `prof_hub_nav_live.js` + overflow layout post-swap
- [ ] Ré-init : recherche locale, modales, onglets internes (registry `ProfHub.onPanelLoaded`)
- [ ] Test smoke `hub_partial=hub` + `panel`

### 2.4 Cas particuliers

| Cas | Comportement |
|-----|--------------|
| POST formulaire (exercice, justification) | Full navigation ou JSON + refresh panel |
| Impression / PDF | Nouvel onglet, hors hub live |
| Détail classe onglets évaluations | Phase 2 : hub_partial ou fetch léger |
| `location.replace` boot (storage) | Exécuter **avant** attach nav-live |
| Primaire présence tabs catégorie | Conserver JS-panel ; ne pas mélanger avec URL |

---

## 3. Spec — breadcrumbs (design & couverture)

### 3.1 Règles UX (design system ARIA)

| Règle | Implémentation |
|-------|----------------|
| Dashboard | **Aucun** fil (`dashboard`, `dashboard_enseignant`) |
| Enfant | **1 niveau** : `[ Lien parent ] › Titre courant` |
| Parent | URL **métier** + query conservée (`classe`, `periode`, `matiere`, `vue`) |
| Visibilité | Sous le welcome banner, **au-dessus** du contenu ; `prof_breadcrumb.css` (#64748B / lien #2563EB) |
| Accessibilité | `<nav aria-label="Fil d'Ariane">`, `aria-current="page"` sur courant |
| Suppression | Pas de `#backButton` ; retirer CTA « Retour aux notes / dashboard » **redondants** |

### 3.2 Table cible `prof_nav_trail` (à compléter)

Couvrir **au minimum** :

- Hubs → détail : notes → noter / relevé / créer éval ; présence → liste appel ; élèves → détail ; classes → détail classe
- Évaluations : liste → créer / modifier
- Exercices / justifications : hub → (si page enfant dédiée)
- Secondaire **et** primaire (namespaces distincts)

**Spec technique** : partial `prof_breadcrumb.html` ; labels i18n-ready ; `current_label` depuis vue ou `prof_breadcrumb_current_label` request.

---

## 4. Spec — temps réel optimal

### 4.1 Architecture cible

```
POST (ou action JSON) → emit_live(établissement, event_type, payload normalisé)
                              ↓
                    WebSocket canal établissement
                              ↓
              enseignant_live.js (filtre classe/eleve/page)
                              ↓
         fetch hub_partial=panel (ou live root legacy) + reconcile UI
```

### 4.2 Matrice cible (100 % prof — tous types)

| Domaine | event_type | Émission serveur (cible) | Refresh client |
|---------|------------|--------------------------|----------------|
| Notes / relevé | `notes.mise_a_jour` | Chaque POST note, soumission relevé, calcul moyennes (primaire + secondaire + LMD) | `#prof-hub-panel` ou `notes-noter` |
| Présence | `presence.mise_a_jour` | Liste appel, modif ligne, sync offline | hub panel / `presence-liste` |
| Évaluations | `evaluation.creee/modifiee/supprimee` | CRUD toutes vues | notes hub, listes, détail classe |
| Justifications | `justification.soumise` | POST prof (primaire + secondaire) | `justifications` |
| Exercices | `exercice.publie/modifie` | POST hub (primaire + secondaire) | `exercices` |
| Sanctions | `sanction.ajoutee` | POST prof | `eleve-detail`, listes |
| Profil | `profil.mise_a_jour` | Optionnel | profil |

**Payload** : uniformiser via `live_serializers` (`classe_id`, `eleve_id`, `periode_id`, `item`).

### 4.3 Client

- `PAGE_REFRESH` : tous les `data-live-page` hubs → `#prof-hub-panel` si `nav-live`.
- `bindLiveForm` : réponses JSON `{ ok, message, item }` sur POST live.
- **Optimistic UI** (présence liste, 2 statuts) : phase tardive ; reconcile WS ; pas de double POST.
- Scripts live : **toutes** pages POST métier (minimum : hubs restants, détail classe, sanctions).

### 4.4 État vs cible (gap)

- **OK partiel** : notes/presence hub refresh panel ; presence_sync_service ; exercice/justif/sanction primaire récents.
- **Gap** : saisie note cellule primaire ; hubs sans live scripts ; secondaire exercices/justif sans nav-live ; évaluations primaire densité emit.

---

## 5. Vagues d’implémentation réalistes

| Vague | Intitulé | Périmètre | DoD |
|-------|----------|-----------|-----|
| **P0** | Hotfix exercices | Bug `periodes_scolaires` + test XHR exercices primaire | ✅ **Fait** — URL recette OK ; 0 TemplateError |
| **P1** | Hubs primaire restants | classes, justifications, difficulté → hub_partial + nav-live | ✅ **Fait** — 3 pages ; tests smoke |
| **P2** | Hubs secondaire/LMD restants | eleves, classes, exercices, justifications, difficulté (V3/V4) | ✅ **Fait** — hub_partial + nav-live |
| **P3** | Breadcrumbs v2 | Table `prof_nav_trail` complète + retrait CTA retour + labels design | ✅ **Fait** — 17 tests trail + hubs P0–P2 OK |
| **P4** | Live dense notes/présence | emit manquants + refresh panel partout ; optional optimistic présence | **En cours** — primaire noter + hub panel WS ; secondaire/LMD à densifier |
| **P5** | Live évals/justif/exo/sanctions | Matrice §4.2 complète ; JSON POST | Tests intégration ciblés |
| **P6** | Finitions | Cache fragment, perfs, a11y onglets, doc recette 3 profils automatisée partielle | Lighthouse / charge hub |

**Branches suggérées** : `cursor/prof-ux-p<N>-a40c` (nouvelle numérotation pour éviter confusion avec R0–R5 déjà mergées partiellement).

**Ordre** : **P0 immédiat** → P1 → P2 (navigation) → P3 (breadcrumb) en parallèle partiel de P4 → P5 → P6.

---

## 6. Recette manuelle — 3 profils (référence)

Base : `http://127.0.0.1:8001` ou `8047`.

| Profil | Comptes / établissement | URLs critiques |
|--------|-------------------------|----------------|
| **Primaire** | `type_etablissement=primary` | `/enseignant/primaire/notes/`, `/exercices/?periode=&classe=`, `/presence/`, `/eleves/` |
| **Collège/lycée** | `hub_v3` | `/enseignant/notes/?periode=&classe=`, `/enseignant/presence/?classe=` |
| **LMD** | `hub_v4` | `/enseignant/notes/?classe=`, `/enseignant/presence/?classe=` |

Checklist : onglets sans flash ; F5 ; exercices **sans 500** ; breadcrumb liste appel ; WS 2 onglets.

---

## 7. Hors scope

- Directeur, assistant vocal / IA, comptabilité générale, shell / infra VPS
- Élève / parent (hors canal WS établissement partagé)
- SPA React / Turbo global
- Refonte métier présence (binaire présent/absent déjà actée)

---

## 8. Relation avec le travail déjà livré (R0–R5)

Le code actuel couvre **~25 %** des URLs hub listées (navigation live) et **100 %** des règles breadcrumb enfant (P3). Ce plan intégral **ne annule pas** R0–R5 : il fixe la **destination** et la **numérotation P0–P6** pour la suite. **P0–P3** livrés ; **hotfix nav** livré ; **P4** actif (notes live primaire + hub panel).

---

*Rédigé le 2026-09-26 — audit code + plan uniquement.*
