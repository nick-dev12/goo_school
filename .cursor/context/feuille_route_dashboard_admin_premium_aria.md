# Feuille de route — Tableau de bord administratif premium Aria (v2)

**Statut :** D0 ☑ · D1 ☑ · D2 ☑ · D3 ☑ · **D4 livré** (2026-10-02) · D5+ sur validation  
**Règle présence :** un retard **n’est pas** une présence.  
**Règle réussite :** moyenne générale ≥ seuil (`StandardsReussite`, sinon 10/20). Aucune moyenne → tiret, jamais 0 %.  
**URL :** `/dashboard/directeur/` (évolution progressive, **sans casser l’existant**)  
**Références :** [feuille_route_dashboard_absences_directeur.md](feuille_route_dashboard_absences_directeur.md), [feuille_route_ui_directeur.md](feuille_route_ui_directeur.md), [comptabilite_plan.md](comptabilite_plan.md)

**Règle de travail :** l’**intention** est dans ce document ; la **vérité technique** est dans le **code**. Ne rien supposer non vérifié.

---

## 0. Audit initial (code réel — 2026-10-02)

### 0.1 Points conformes à la vision

| Élément | Fichier / zone | Constat |
|---------|----------------|---------|
| Dashboard directeur | `directeur_view.dashboard_directeur` | KPI + onglets activité, session année via `_get_session_directeur` |
| Tenant | `Etablissement` user | Filtrage établissement sur vues directeur |
| Permissions personnel | `permissions_personnel.py` | Granulaire (pas rôles « censeur » figés) |
| Onglet absences pilotage | `dashboard_absences_stats.py`, partial, Chart.js | Pilote UX § présence (KPI, charts, tableaux) |
| Bilan scolarité | `bilan_comptabilite.*` | Chart.js 4.4, pattern `json_script` |
| Assistant pilotage | `assistant_pilotage.py` | Effectifs, taux présence, réussite, recouvrement |
| Recouvrement | `recouvrement.py` | Impayés, agrégats finance |
| Temps réel | `directeur_live.js` | `presence.mise_a_jour` → reload dashboard |
| Persistance onglets | `directeur_ui_tabs.py`, `dashboard_directeur.js` | `?activite=` + localStorage |
| Caissier restreint | `is_caissier` templates | Masque blocs pédagogiques |

### 0.2 Incohérences / dettes identifiées (à corriger via Metrics Engine)

| Sujet | Code A | Code B | Risque |
|-------|--------|--------|--------|
| **Taux de présence** | `dashboard_absences_stats` : `present / total` | `assistant_pilotage` : `(present + retard) / total` | Chiffres différents dashboard vs assistant |
| **Absences NJ** | `Presence.get_nombre_absences` + dashboard : `statut='absent'` | Alertes dashboard (boucle `:100` élèves) | Perf + incohérence avec onglet absences |
| **Taux de réussite** | `dashboard_directeur` : moyennes ≥ 10/20 | `assistant_pilotage._seuil_passage` | Peut diverger si seuil configuré |
| **Année scolaire** | Filtre strict `annee_scolaire` sur présences | Assistant parfois `Q(annee_scolaire=…) \| Q(annee_scolaire__isnull=True)` | Mélange silencieux possible côté assistant |
| **Fraîcheur** | Non affichée | Reload WS ≠ temps réel calcul | UX « faux live » si non libellé |
| **Vue executive** | Non | 15 widgets possibles si on empile sections | Surcharge UX |

### 0.3 Améliorations intégrées (mission audit v2)

1. **Metrics Engine** — source unique par `metric_id` (dashboard, assistant, alertes, exports futurs).  
2. **Executive par défaut** — `?vue=executive` ; analytique `?vue=analytique`.  
3. **Blocs « Aujourd’hui »** et **« Fiabilité / complétude »** — D1/D2 selon données réelles.  
4. **Comparaisons temporelles** explicites (valeur, référence, delta, libellé période).  
5. **Fraîcheur** — `computed_at` par bloc (horodatage serveur, pas « temps réel » abusif).  
6. **Alertes** — catégories URGENT / IMPORTANT / SURVEILLER / INFO + schéma structuré.  
7. **Insights v1** — 100 % déterministe, format `why` traçable.  
8. **Perf** — ORM d’abord ; **pas de Redis** avant mesures.  
9. **Chart factory** — un module JS ; Chart.js 4.4 seul ; heatmap **phase ultérieure**.  
10. **Stop gate** — fin D1 → **rapport obligatoire** avant D2.

### 0.4 Décisions structurantes (validées dans ce document)

| Décision | Choix |
|----------|--------|
| Refonte | **Évolution progressive** ; conserver onglets activité jusqu’à migration ancre |
| Nouveau modèle Django metrics | **Non** — registry Python + services |
| Redis cache | **Reporté** post-mesures |
| D0 scope | **Pas de 20 graphiques** — socle uniquement |
| D2 | **Bloqué** sans rapport D1 |

---

## 1. Règles absolues (rappel mission)

1. Analyser code avant d’étendre une métrique.  
2. Ne pas supprimer une fonctionnalité dashboard sans justification.  
3. Ne pas afficher `0` quand il n’y a **aucune donnée** → état `empty`.  
4. Filtres et permissions **côté serveur**.  
5. Drill-down → **routes existantes** (`directeur:*`, `secretaire:*`).  
6. Incohérence métier détectée → **signaler + alternative**, ne pas implémenter aveuglément.

---

## 2. Metrics Engine (architecture cible)

### 2.1 Objectif

Une métrique = **une définition**, **un calcul**, **plusieurs consommateurs**.

Consommateurs prévus : dashboard, assistant IA (réutilisation), notifications, rapports, export, API future.

### 2.2 Emplacement code (D0)

```
school_admin/services/dashboard/
  __init__.py
  context.py              # DashboardContext
  registry.py             # blocs UI + permissions
  metrics/
    __init__.py
    registry.py           # MetricId, métadonnées
    engine.py             # dispatch compute
    presence.py           # wrappers → unifier avec assistant
    effectifs.py
    pedagogie.py
    finance.py
  contracts.py            # formes JSON BlockPayload, Alert, Insight
  completeness.py         # D1+ : notes manquantes, appels, dossiers
  today.py                # D1+ : bloc « Aujourd’hui »
```

### 2.3 Contrat métrique (concept)

| Champ | Description |
|-------|-------------|
| `id` | ex. `attendance_rate` |
| `label` | Libellé UI |
| `unit` | `%`, `count`, `FCFA`, etc. |
| `source` | Modèles / service |
| `compute(ctx, filters)` | Fonction unique |
| `period_kind` | `day`, `rolling_7`, `rolling_30`, `period_scolaire`, `annee` |
| `comparison_kind` | `previous_period`, `same_period_prev_year`, `none` |
| `permission` | clé `permissions_personnel` ou `None` (= directeur) |
| `definition` | Texte métier court (tooltip / « Pourquoi ? ») |

### 2.4 Plan de convergence (post-D0)

| metric_id | Canonicaliser depuis |
|-----------|---------------------|
| `attendance_rate` | Décision produit : inclure **retard** ou non → **documenter** puis aligner assistant + dashboard |
| `student_count` | `InscriptionEleve` + actifs (dashboard actuel) |
| `success_rate` | `_seuil_passage` + `MoyennePeriode` |
| `collection_rate` | `recouvrement` / assistant pilotage |
| `outstanding_amount` | ComptabiliteEleve agrégats |
| `average_grade` | Moyennes générales période active |
| `unjustified_absence_count` | `dashboard_absences_stats` (NJ) |

**D0 :** registry + stubs ; **pas** refonte complète assistant (vague dédiée).

---

## 3. UX — structure Executive (défaut)

Ordre vertical **mode executive** (`?vue=executive`) :

```
HEADER (titre, année, période, date, actualiser, vue toggle*)
  ↓
FILTRES (année, période, cycle, niveau, filière, classe — cascade serveur)
  ↓
KPI PRINCIPAUX (6–8 max)
  ↓
À TRAITER (alertes catégorisées)
  ↓
AUJOURD’HUI (pilotage quotidien — données réelles uniquement)
  ↓
FIABILITÉ / COMPLÉTUDE (« Complet » | « Partiel » + explication)
  ↓
SITUATION GÉNÉRALE (repliable)
  ↓
PRÉSENCE (repliable — onglet absences existant intégré ici en analytique)
  ↓
RÉSULTATS (repliable)
  ↓
FINANCES (repliable, si permission)
  ↓
EFFECTIFS / CAPACITÉ (repliable)
  ↓
À RETENIR (insights déterministes)
  ↓
ACTIVITÉ RÉCENTE (timeline composite — phase tardive)
```

**Mode analytique** (`?vue=analytique`) : sections dépliées, graphiques additionnels, même données.

Mobile : **executive** prioritaire ; filtres en panneau ; tableaux scrollables.

\* Toggle vue : permission directeur ou profils étendus.

---

## 4. Blocs transverses (spécification)

### 4.1 Aujourd’hui (D1 partiel / D2 complet)

Afficher **uniquement si calculable** :

| Indicateur | Source probable | Permission |
|----------|-----------------|------------|
| Date du jour | serveur | tous |
| Présence du jour | `Presence` + date=today | `presences_liste` |
| Appels reçus | `SoumissionListePresence` date=today | idem |
| Cours programmés | EDT publié — **à auditer** | — |
| Cours réalisés | **si statut explicite** | — |
| Paiements du jour | `PaiementEleve` | compta |
| Alertes du jour | filtre alertes | mixte |

### 4.2 Fiabilité / complétude (D1/D2)

Score ou bandeau par domaine :

- notes manquantes (`ReleveNotes`, évaluations) ;
- présences non soumises (classes sans soumission N jours) ;
- dossiers incomplets (préinscription / inscription — champs métier) ;
- bulletins non finalisés (`MoyennePeriode.est_publie`) ;

États : `complete` | `partial` | `unknown` + liste `gaps[]` (max 5 + lien).

### 4.3 Comparaisons temporelles

Structure KPI :

```json
{
  "value": 94.2,
  "unit": "%",
  "comparison": {
    "reference_value": 92.1,
    "delta": 2.1,
    "delta_label": "+2,1 points",
    "period_label": "vs période précédente",
    "compatible": true
  }
}
```

Si périodes incompatibles : `comparison.compatible: false` + pas de delta affiché.

### 4.4 Fraîcheur des données

Chaque bloc :

```json
"meta": {
  "computed_at": "2026-10-02T06:20:00+00:00",
  "freshness_label": "Mis à jour à 06:20",
  "is_live": false
}
```

Reload WebSocket = **rafraîchissement page**, pas streaming métriques.

### 4.5 Drill-down (routes réelles)

| Depuis | Vers (exemples vérifiés) |
|--------|---------------------------|
| Présence classe | `directeur:suivi_presence` + query |
| Élève | `secretaire:detail_eleve#presences-tab` |
| Finance | `directeur:liste_impayes_directeur`, `details_comptabilite_eleve_directeur` |
| Notes | `directeur:notes_et_resultats` |
| Classe | pages classes / détail selon existant |

### 4.6 Alertes

```json
{
  "id": "payments_overdue_30d",
  "category": "URGENT|IMPORTANT|SURVEILLER|INFO",
  "priority": 1,
  "message": "12 dossiers de paiement en retard",
  "detail": "…",
  "value": 12,
  "period": "…",
  "source": "recouvrement.collecter_impayes",
  "url": "/comptabilite/impayes/",
  "permission": "…"
}
```

Règles explicites dans `dashboard/alerts.py` (D2).

### 4.7 Smart insights (v1)

```json
{
  "id": "presence_below_30d_avg",
  "severity": "warning",
  "message": "…",
  "why": {
    "metric": "attendance_rate",
    "value": 88.2,
    "threshold": 91.0,
    "period": "rolling_7",
    "baseline": "rolling_30_avg"
  },
  "url": "…"
}
```

Pas de LLM v1. Préparer export metrics JSON pour assistant plus tard.

---

## 5. Technique transverse

### 5.1 DashboardContext (D0)

Champs cibles :

- `etablissement`, `annee_scolaire`, `annee_reellement_active`
- `periode_scolaire` (active ou GET)
- `filters` : cycle, niveau, filiere, classe_id
- `vue` : `executive` | `analytique`
- `user_kind` : directeur | personnel
- `permissions` : set ou None
- `today`, `computed_at`

### 5.2 Registry blocs (D0)

Enregistrement : `block_id`, `permission`, `compute(ctx) -> BlockPayload`, `executive_visible: bool`.

### 5.3 JSON / templates

- Pas d’ORM dans templates.
- `json_script` pour charts.
- Partials : `directeur/dashboard/components/_stat_card.html`, `_empty`, `_skeleton`, `_error`.

### 5.4 Graphiques

- **Chart.js 4.4** uniquement.
- `static/.../dashboard/dashboard_chart_factory.js` (D1) — fusionner `dashboard_absences_charts.js` progressivement.
- Heatmap : **D3+**, CSS grid si possible.

### 5.5 Performance

1. `assertNumQueries` tests par bloc.  
2. annotate / aggregate.  
3. Mesurer P95 dashboard executive.  
4. Redis **seulement si** P95 > budget après optim SQL.

Objectif indicatif : **< 500 ms** executive (hors cache).

---

## 6. Phasage strict

### D0 — Fondations (**en cours**)

**Autorisé :**

- [x] Audit documenté (§0)
- [x] `DashboardContext` + factory depuis `dashboard_directeur`
- [x] `metrics/registry.py` + `engine.py` (`student_count`, `attendance_rate`)
- [x] `block_registry.py` (stub blocs)
- [x] `contracts.py`
- [x] Composants template empty / skeleton / error
- [x] Header enrichi (date, fraîcheur, actualiser, vue executive/analytique, badge session ≠ active)
- [x] Tests : `test_dashboard_d0.py`

**Interdit D0 :**

- 20 graphiques, filtres cascade complets, Redis, heatmap, refonte onglets, suppression absences tab

**Livrable D0 :** code socle + tests verts ; dashboard **inchangé fonctionnellement** ou enrichissement header minimal seulement.

### D1 — Executive + filtres (**livré 2026-10-02**)

- [x] Filtres globaux + URL canonique + persistance
- [x] KPI principaux via Metrics Engine (effectifs, capacité, présence)
- [x] Vue globale effectifs / répartition cycles
- [x] Blocs « Aujourd’hui » et « Complétude » **minimum viable**
- [x] Mode `vue=executive|analytique`
- [x] Tests §18 + recette navigateur
- [x] Rapport : [rapport_dashboard_d1.md](rapport_dashboard_d1.md)

**Stop gate :** D2 **bloqué** jusqu’à validation humaine du rapport.

### D2 — Présences + alertes + insights (**livré 2026-10-02**)

- [x] `attendance_rate` : retards exclus du numérateur (dashboard + assistant)
- [x] `attendance_trend` 7 / 30 jours
- [x] Alertes multi-modules
- [x] Insights déterministes + « Pourquoi ? »
- [x] Chart factory JS
- [x] Rapport : [rapport_dashboard_d2.md](rapport_dashboard_d2.md)

### D3 — Pédagogie (**livré 2026-10-02**)

- [x] `success_rate` via `_seuil_passage` / `StandardsReussite` (pas 10/20 figé)
- [x] `average_grade` + comparaison période précédente
- [x] `grade_distribution` (tranches, classes, élèves sous seuil)
- [x] Alertes : sous seuil + bulletins non publiés
- [x] Insight : réussite inférieure à la période précédente
- [x] Rapport : [rapport_dashboard_d3.md](rapport_dashboard_d3.md)

### D4 — Finances (**livré 2026-10-02**)

- [x] `collection_rate` + comparaison année précédente
- [x] `outstanding_amount` (reste à recouvrer)
- [x] `finance_status` (statuts, encaissements 30 j, classes)
- [x] Insight recouvrement < 70 %
- [x] Rapport : [rapport_dashboard_d4.md](rapport_dashboard_d4.md)

### D5 — Enseignants · D6 — Inscriptions · D7 — EDT · D8 — Discipline & activité · D9 — Export & polish

(Inchangé dans l’esprit v1 — détail dans historique git du doc.)

---

## 7. Intégration existant (absences Vague 6)

| Asset | Stratégie |
|-------|-----------|
| `dashboard_absences_stats.py` | Wrapper metric `presence.*` ; pas de suppression |
| Onglet `?activite=absences` | Conservé jusqu’à ancre `#presence` validée |
| `dashboard_absences_charts.js` | Migré vers chart factory en D2 |

---

## 8. Tests D0 / D1 (checklist)

- [ ] Permission : personnel sans droit ne voit pas bloc finance
- [ ] Établissement : impossible d’injecter autre etab_id
- [ ] Année consultée ≠ active : métriques filtrées correctement
- [ ] Filtres invalides : ignorés ou 400 propre
- [ ] Empty : pas de KPI à 0 trompeur
- [ ] Gros volume : pas de boucle O(n) élèves (supprimer pattern `:100`)
- [ ] JSON : schéma stable `BlockPayload`
- [ ] Responsive : executive mobile (manuel + checklist)

---

## 9. Rapport obligatoire fin D1 (template)

1. Architecture finale  
2. Fichiers créés / modifiés  
3. Services / metrics disponibles  
4. Metrics impossibles + raisons  
5. Requêtes clés + `assertNumQueries`  
6. Tests exécutés  
7. Performance mesurée  
8. Problèmes rencontrés  
9. Décisions techniques  
10. Recommandations D2  

Fichier suggéré : `.cursor/context/rapport_dashboard_d1.md`

---

## 10. Parcours UX cible (qualité finale)

```
INDICATEUR → COMPRÉHENSION → PROBLÈME → DÉTAIL → ACTION
```

Chaque `ChartCard` : **question** (titre), période, unité, tooltip humain, CTA.

---

## 11. Suivi d’avancement

| Phase | Statut | Date |
|-------|--------|------|
| Audit v2 doc | ☑ | 2026-10-02 |
| D0 socle | ☑ | 2026-10-02 |
| D1 executive | ☑ | 2026-10-02 |
| Rapport D1 | ☑ | 2026-10-02 |
| D2 | ☑ | 2026-10-02 |
| D3 | ☑ | 2026-10-02 |
| D4 | ☑ | 2026-10-02 |
| D5+ | ☐ | sur validation |

---

*Document v2 — aligné mission « Audit & améliorer feuille de route avant implémentation ».*
