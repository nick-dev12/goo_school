# Feuille de route — Reproduction visuelle du dashboard Aria

**Date d’ouverture :** 2026-10-02  
**Référence visuelle :** image fournie (SaaS clair, topbar blanche, colonne droite « Aujourd’hui »)  
**URL :** `/dashboard/directeur/`  
**Interdit :** modifier `nav.enseignant-bottom-nav.bottom-nav-directeur`  
**Règle données :** jamais recopier 1 248 / 94,2 % / 12,4 M — métriques D0–D4 uniquement.

**Statut :** Phase 0 ☑ · Phase 1 ☑ · Phase 2 ☑ · Phase 3 ☑ · Phase 4 ☑ · Phase 5 ☑ · **Phase 6 livrée** (2026-10-02) — reproduction visuelle close

---

## 0. Décisions d’architecture (audit 2026-10-02)

### 0.1 Ce que l’image montre vraiment

L’image **n’a pas** de sidebar verticale sombre à gauche.

Elle a :

1. **Topbar claire** : recherche · année · établissement · notifications · avatar / nom / rôle  
2. **Bannière** « Bonjour … » + visuel établissement  
3. **Filtres** : année, période, cycle, classe  
4. **5 KPI** + mini-sparks  
5. **Colonne droite** : Aujourd’hui · À traiter · Activité récente  
6. **Colonne gauche** : Situation générale · Répartition · Présence · Résultats · Finance  
7. **Bandeau bas** « À retenir »

### 0.2 Conflit spec écrite vs image

La spec texte demande une sidebar gauche (Tableau de bord, Présences, Finances…).  
L’image + la contrainte « ne pas toucher la bottom nav » l’interdisent.

**Décision :** pas de sidebar gauche. La navigation reste la **bottom nav existante**. Les ancres du dashboard (`#dbd-today`, `#dbd-results`…) servent de drill-down interne.

### 0.3 Architecture actuelle

| Couche | Où | État |
|--------|----|------|
| Vue | `directeur_view.dashboard_directeur` | KPI historiques + `build_executive_dashboard` |
| Métriques | `services/dashboard/metrics/*` | D0–D4 livrés |
| Alertes / insights | `alerts.py`, `insights.py` | D2–D4 |
| Template actuel | `dashboard_directeur.html` + `_executive.html` | cartes empilées, pas la maquette |
| Header | `header_directeur.html` | barre + **welcome-banner bleu** (école + session + Déconnexion) |
| CSS premium | `dashboard_premium.css` | **écrit mais non branché** ; header **bleu** (≠ image) |
| Partial sidebar | `_premium_sidebar.html` | existe, **non inclus** |
| Partial executive premium | `_premium_executive.html` | listé dans git, **fichier absent** |
| Chart.js 4.4 | CDN + `dashboard_chart_factory.js` | bar + line |
| Bottom nav | `bottom_nav_directeur.html` | **ne pas toucher** |

### 0.4 Données réelles disponibles

| Bloc maquette | Source | Statut |
|---------------|--------|--------|
| Effectifs | `student_count` | OK |
| Présence | `attendance_rate` / `attendance_trend` (retard ≠ présent) | OK |
| Réussite | `success_rate` + seuil `StandardsReussite` | OK (empty si pas de moyennes) |
| Recettes / recouvrement | `collection_rate`, `outstanding_amount` | OK (empty si pas de charges) |
| Dossiers incomplets | `completeness.gaps` | proxy (appels / bulletins) — pas un modèle « dossier » unique |
| Répartition | `cycle_distribution` | OK |
| Présence par classe | `presence_by_class` (min. 3, seuil 85 %) | OK |
| Résultats | `grade_distribution` | OK |
| Finance 30 j | `finance_status` | OK |
| Aujourd’hui | `today.py` | présence, appels, paiements — **pas** cours EDT / événements agenda |
| Alertes | `alerts.py` | déterministes |
| Activité | soumissions, relevés, sanctions, justifications (vue) | OK |

**Impossible sans inventer :** cours programmés vs réalisés (pas de statut « réalisé » fiable), recettes 12,4 M de démo.

### 0.5 Routes de drill-down (existantes)

- Présence → `directeur:suivi_presence`  
- Notes → `directeur:notes_et_resultats`  
- Impayés → `directeur:liste_impayes_directeur`  
- Élèves → `directeur:gestion_eleves` / `secretaire:detail_eleve`  
- Profil → `directeur:profil_etablissement`  
- Session → `directeur:changer_session_directeur` (POST, déjà dans le header)

### 0.6 Fichiers prévus (implémentation)

**Créés**

- `.cursor/context/feuille_route_dashboard_visuel_aria.md` (ce fichier)
- `templates/.../dashboard/partials/_premium_executive.html`
- `static/.../js/directeur/dashboard_premium_charts.js`
- `tests/test_dashboard_visuel.py`
- rapports de phase dans `.cursor/context/rapport_dashboard_visuel_pN.md`

**Modifiés**

- `dashboard_directeur.html` (include + CSS + class body)
- `header_directeur.html` (topbar claire **uniquement** sur le dashboard)
- `dashboard_premium.css` (header blanc comme l’image)
- `dashboard_chart_factory.js` (doughnut)
- éventuellement `executive.py` (clés d’assemblage)

**Non touchés**

- `bottom_nav_directeur.html` et son CSS  
- modèles Django  
- Redis  
- autres dashboards (secrétaire, parent, enseignant)

---

## Phases (à suivre intégralement)

### Phase 0 — Audit

- [x] Cartographier templates / CSS / services / routes  
- [x] Trancher sidebar gauche vs image + bottom nav  
- [x] Lister données manquantes

**Stop :** document lu. Ensuite Phase 1.

### Phase 1 — Topbar + coquille + hero + filtres + 5 KPI

Objectif : la page **ressemble** à l’image (structure), données réelles, bottom nav intacte.

- [x] `body.dashboard-premium` + CSS branché  
- [x] Topbar **blanche** : search, année, établissement, notif, avatar  
- [x] Masquer `welcome-banner` bleu **sur le dashboard seulement**  
- [x] Bannière « Bonjour {prénom} » + visuel projet  
- [x] Filtres GET (année affichée, période, cycle, classe)  
- [x] 5 KPI réels + empty = tiret  
- [x] Coquille graphiques + colonne droite + À retenir  
- [x] Bottom nav **non modifiée**  
- [x] 32 tests OK + Daphne + recette

**Stop gate.** Rapport : [rapport_dashboard_visuel_p1.md](rapport_dashboard_visuel_p1.md).

### Phase 2 — Colonne droite (**livrée 2026-10-02**)

- [x] Aujourd’hui : présence %, appels, cours EDT publiés, annonces, paiements, alertes  
- [x] Empty explicite (pas de cours « réalisés » inventés)  
- [x] À traiter : URGENT / IMPORTANT / À SURVEILLER / INFORMATION + lien  
- [x] Activité récente unifiée (`activity.py`)  
- [x] Rapport : [rapport_dashboard_visuel_p2.md](rapport_dashboard_visuel_p2.md)

### Phase 3 — Graphiques principaux (**livrée 2026-10-02**)

- [x] Situation générale (présence 30 j uniquement — réussite non quotidienne)  
- [x] Donut répartition + % + total  
- [x] Présence par classe (barres, seuil 85 %)  
- [x] Résultats (cycle si moyennes, sinon buckets)  
- [x] Finance (30 j ou statuts, empty si pas de charges)  
- [x] CTA « Voir le détail » → routes existantes  
- [x] Rapport : [rapport_dashboard_visuel_p3.md](rapport_dashboard_visuel_p3.md)

### Phase 4 — À retenir + fiabilité (**livrée 2026-10-02**)

- [x] Bandeau insights déterministes (libellé, why, Voir, empty explicite)  
- [x] Badge « Données partielles » si `completeness.status != complete` (hero + bandeau)  
- [x] Rapport : [rapport_dashboard_visuel_p4.md](rapport_dashboard_visuel_p4.md)

### Phase 5 — Responsive (**livrée 2026-10-02**)

- [x] 1920 / 1440 / 1024 / 768 / 430 (media queries + recette 768 / 430 / ~780)  
- [x] Filtres empilés, KPI 2 puis 1 col, colonne droite sous le main  
- [x] Padding bas 8.5–9.5 rem — bottom nav **non modifiée**  
- [x] Rapport : [rapport_dashboard_visuel_p5.md](rapport_dashboard_visuel_p5.md)

### Phase 6 — Tests, screenshots, corrections (**livrée 2026-10-02**)

- [x] HTTP 200, auth, filtres, permissions finance  
- [x] Screenshots vs image (topbar blanche, 5 KPI réels, empty honnêtes)  
- [x] Rapport final : [rapport_dashboard_visuel_p6.md](rapport_dashboard_visuel_p6.md)

---

## Checklist visuelle (cible)

- [x] Topbar claire (pas le bandeau bleu école)  
- [x] Bottom nav inchangée  
- [x] Bannière + 5 KPI + colonne droite  
- [x] Graphiques dimensionnés  
- [x] Pas de 0 % trompeur (tiret + motif)  
- [x] Responsive  
- [x] Drill-down réel  

---

*Document de suivi — une phase à la fois, test + redémarrage avant la suivante.*
