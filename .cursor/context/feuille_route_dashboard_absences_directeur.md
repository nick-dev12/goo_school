# Feuille de route — Onglet Absences du tableau de bord directeur

**Statut : implémenté en local (P1–P4) — 2026-10-02**  
**URL cible :** `http://127.0.0.1:8001/dashboard/directeur/?activite=absences`  
**Production :** `https://aria-edu.com/dashboard/directeur/?activite=absences`

**Références :** [feuille_route_ui_directeur.md](feuille_route_ui_directeur.md), [design-system-aria.md](../rules/code-couleur-de-app.mdc), Chart.js (pattern existant : `bilan_comptabilite.js`).

---

## 0. Synthèse exécutive

| Domaine | État actuel (code) | Cible |
|--------|-------------------|--------|
| **Contenu onglet** | 4 dernières `SoumissionListePresence` (liste texte) | **Centre de pilotage** KPI + graphiques + actions |
| **Données** | Enrichissement inline dans `dashboard_directeur` | Service dédié `dashboard_absences_stats` (requêtes agrégées) |
| **Graphiques** | Aucun | Chart.js 4.4 (lazy init à l’onglet) |
| **Temps réel** | `presence.mise_a_jour` → page `dashboard` (reload partiel non ciblé) | Refresh **KPI + graphiques** ou reload léger documenté |
| **Responsive** | Cartes activité génériques | Grille KPI + canvas + tableaux scrollables |
| **i18n** | Textes FR en dur dans le template | `{% trans %}` sur libellés utilisateur |

**Objectif produit :** permettre au directeur de **comprendre la situation absences en &lt; 10 s**, d’**identifier les classes et élèves à risque**, et d’**accéder en 1 clic** au suivi détaillé — sans quitter le dashboard.

---

## 1. Périmètre et hors périmètre

### 1.1 In scope

- Refonte **uniquement** du panneau `#tab-absences` dans `dashboard_directeur.html`.
- Calcul des statistiques côté **Django** (pas de validation métier en JS).
- Animations **décoratives** (compteurs, fade-in, Chart.js) — pas d’envoi de formulaires en JS.
- Respect **année scolaire consultée** (`_get_session_directeur`) et **établissement** courant.
- **Directeur** + **personnel administratif** avec les mêmes restrictions que le dashboard actuel.

### 1.2 Out of scope (vagues ultérieures)

- Refonte des onglets Notes / Sanctions / Justifications (harmonisation visuelle optionnelle V2).
- Export PDF / Excel depuis le dashboard.
- Filtres avancés multi-mois avec URL canonique complexe (phase P4 optionnelle).
- Nouvelle page dédiée « Analytics absences » (le dashboard reste le hub).

---

## 2. Règles métier (contrat de calcul)

À **documenter dans le service** et **tester** — une seule source de vérité.

| Règle | Détail |
|-------|--------|
| **Période par défaut** | Année scolaire consultée (`annee_scolaire_active`). Si absente : toutes les présences de l’établissement (bandeau warning déjà présent sur le dashboard). |
| **Élèves pris en compte** | Même périmètre que le dashboard : inscrits actifs sur l’année (`InscriptionEleve` + `Eleve.actif=True`). |
| **Absence « comptée » (paliers)** | `statut='absent'` — aligné sur `Presence.get_nombre_absences` et badges liste élèves. |
| **Absence justifiée** | `statut='absent_justifie'` — indicateur séparé, **exclue** des paliers 10–12 / &gt;12. |
| **Présent / retard** | `present`, `retard` — pour taux de présence et graphique statuts. |
| **Granularité enregistrement** | Une ligne `Presence` = un **appel** (date × `numero_appel` × matière éventuelle). Les KPI « par élève » = **nombre d’appels absents**, pas jours calendaires distincts (sauf indicateur dédié « jours distincts » — voir §3.7). |
| **Top 5 classes** | **Meilleur taux de présence** = `presents / total_enregistrements` sur la période, minimum **seuil effectif** (ex. ≥ 10 enregistrements classe) pour éviter biais petites classes. |
| **Bottom 5 classes** | Même métrique, ordre inverse (classes les plus fragiles). |
| **Sexe** | Champ `Eleve.sexe` (`F` / `M`) — regrouper « non renseigné » dans **Autre / N/R** si présent. |

**Décisions utilisateur (défaut retenus si silence) :**

- Top 5 = **taux de présence** (pas volume brut d’absences).
- Paliers 10–12 et &gt;12 = **sur l’année scolaire consultée**.
- Paliers = **absences non justifiées** uniquement.

---

## 3. Inventaire des éléments UI (indispensables + enrichissements)

### 3.1 En-tête du panneau

- Titre **Absences** + sous-texte période (`{{ annee_scolaire_active.libelle }}` ou « Toutes sessions »).
- CTA principal : **Voir le suivi complet** → `directeur:suivi_presence`.
- CTA secondaire : **Liste des élèves** (filtre absences pré-appliqué côté lien si possible) → hub élèves / liste.
- Badge **alerte** si &gt; 0 élèves &gt;12 absences (lien ancre vers tableau risque).

### 3.2 Bandeau KPI (6–8 cartes)

| # | Carte | Valeur | Trend optionnel |
|---|--------|--------|-----------------|
| K1 | **Taux de présence global** | % arrondi 1 décimale | vs mois précédent (Δ points) |
| K2 | **Total absences non justifiées** | Nombre d’appels | vs mois précédent |
| K3 | **Absences justifiées** | Nombre | — |
| K4 | **Retards** | Nombre + % du total | — |
| K5 | **Filles** (absences NJ cumulées) | Nombre | % du total NJ |
| K6 | **Garçons** (absences NJ cumulées) | Nombre | % du total NJ |
| K7 | **Élèves 10–12 absences NJ** | Effectif élèves | — |
| K8 | **Élèves &gt; 12 absences NJ** | Effectif élèves | — |

Cartes supplémentaires **recommandées** :

| # | Carte | Valeur |
|---|--------|--------|
| K9 | **Élèves sans absence NJ** | Effectif (motivation / contraste) |
| K10 | **Couverture des appels** | % classes ayant ≥1 soumission sur les N derniers jours ouvrés |

### 3.3 Graphiques (Chart.js)

| # | Graphique | Type | Données |
|---|-----------|------|---------|
| G1 | Répartition **F / M** (volume NJ) | Doughnut | 2–3 tranches |
| G2 | **Statuts** (présent, NJ, justifié, retard) | Doughnut ou barres empilées | 4 valeurs |
| G3 | **Tranches par élève** (0, 1–3, 4–9, 10–12, 13+) | Barres horizontales | Effectifs |
| G4 | **Top 5 classes** (taux présence) | Barres horizontales | Labels = nom classe |
| G5 | **Bottom 5 classes** | Barres horizontales | Couleur `--accent` |
| G6 | **Évolution mensuelle** | Ligne ou aires | Absences NJ + option justifiées |
| G7 | **Comparatif F/M par tranche** (option P3) | Barres groupées | 13+ absences par sexe |

Chaque graphique : **titre**, **légende**, **valeurs accessibles** (table `sr-only` ou chiffres sous le canvas).

### 3.4 Tableaux actionnables

| # | Tableau | Contenu | Action |
|---|---------|---------|--------|
| T1 | **Élèves à risque** (top 10) | Nom, classe, NJ, justifiées, taux | Lien fiche élève `#presences-tab` |
| T2 | **Classes sous seuil** | Classe, taux, NJ, effectif | Lien suivi présence filtré classe |
| T3 | **Dernières soumissions** (existant enrichi) | Prof, classe, présents/absents, date | Timeline visuelle |

Contraintes tableaux : conteneur `.table-responsive`, `min-width` colonnes, typo responsive (règle projet).

### 3.5 Indicateurs « qualité des données »

- **Dernière soumission** : date/heure la plus récente (`SoumissionListePresence`).
- **Classes sans appel** depuis X jours : liste compacte (max 5 + « voir suivi »).
- Message si **aucune présence** en base sur la période (empty state pédagogique).

### 3.6 Indicateur **jours d’absence distincts** (différenciation appels)

- KPI ou sous-ligne : pour les élèves &gt;12, afficher en tooltip / colonne secondaire le nombre de **dates distinctes** absentes (NJ).
- Évite la confusion prof / directeur sur primaire (plusieurs appels/jour).

### 3.7 Légende / aide contextuelle

- Icône **(?** ) ouvrant un panneau : définitions NJ, taux, tranches, lien vers doc interne.
- Pas de modale bloquante ; `details/summary` HTML ou panneau CSS.

### 3.8 États vides et erreurs

- Aucune donnée : illustration + texte + bouton suivi présence.
- Année scolaire inactive : reprendre le bandeau dashboard existant.
- Graphiques : placeholder « Données insuffisantes » si &lt; 2 points mensuels.

### 3.9 Accessibilité et motion

- `prefers-reduced-motion` : désactiver compteurs et réduire animations Chart.js.
- Contraste cartes (charte `--directeur-primary`, `--accent`, etc.).
- Onglet : `role="tabpanel"` + `aria-labelledby` conservés.

---

## 4. Architecture technique

### 4.1 Fichiers à créer

| Fichier | Rôle |
|---------|------|
| `school_admin/services/dashboard_absences_stats.py` | Agrégations ORM, retour dict + structure chart JSON |
| `school_admin/templates/school_admin/directeur/partials/dashboard_tab_absences.html` | Markup panneau complet |
| `school_admin/static/school_admin/css/directeur/dashboard_absences.css` | Styles `.dbd-abs-*` |
| `school_admin/static/school_admin/js/directeur/dashboard_absences_charts.js` | Lazy Chart.js + compteurs |
| `school_admin/tests/test_dashboard_absences_stats.py` | Tests service (factory Présence / Élève) |

### 4.2 Fichiers à modifier

| Fichier | Modification |
|---------|--------------|
| `school_admin/personal_views/directeur_view.py` | Appeler le service dans `dashboard_directeur`, injecter contexte |
| `school_admin/templates/school_admin/directeur/dashboard_directeur.html` | Remplacer contenu `#tab-absences` par `{% include partial %}`, CDN Chart.js conditionnel ou global footer |
| `school_admin/static/school_admin/js/directeur/dashboard_directeur.js` | Hook `switchActivityTab` → `window.DBD_initAbsencesCharts()` si onglet absences |
| `school_admin/static/school_admin/js/directeur/directeur_live.js` | Sur `presence.mise_a_jour`, rafraîchir stats (reload page ou endpoint futur — voir §6) |
| `.cursor/context/feuille_route_ui_directeur.md` | Ligne **Vague 6 — Dashboard absences analytics** |

### 4.3 Contrat contexte Django

```python
context['absences_dashboard'] = {
    'kpis': {...},
    'charts': {...},          # sérialisable JSON
    'top_classes': [...],
    'bottom_classes': [...],
    'eleves_risque': [...],
    'dernieres_soumissions': [...],  # format existant enrichi
    'meta': {
        'period_label': str,
        'last_submission_at': datetime|None,
        'classes_sans_appel': [...],
    },
}
```

JSON embarqué :

```html
<script type="application/json" id="dbd-absences-chart-data">…</script>
```

Pattern identique à `scb-chart-data` / `bilan_comptabilite.js`.

### 4.4 Performance

- **Interdit** : boucle Python sur tous les élèves (anti-pattern actuel alertes `:100`).
- **Cible** : `values('eleve_id').annotate(Count(...))`, `values('classe_id')`, filtres indexés (`date`, `annee_scolaire`, `etablissement`).
- Budget : &lt; 300 ms SQL sur établissement moyen (mesure en recette).
- Option : cache Redis 60 s clé `dbd_abs:{etablissement_id}:{annee_id}` si charge VPS (P4).

### 4.5 Sécurité

- Données strictement filtrées par `etablissement` de l’utilisateur connecté.
- Pas d’exposition d’IDs élèves d’autres établissements dans le JSON.
- Personnel admin : même garde que `dashboard_directeur`.

---

## 5. Design system

- Variables `:root` du dashboard (`dashboard_directeur.css`) — pas de nouvelle palette.
- Cartes KPI : `--shadow-card`, hover `--shadow-card-hover`, icônes fond `--primary-light` / `--accent-light`.
- Graphiques : palette fixe alignée charte (bleu `#3b82f6`, violet `#7c3aed`, rouge `#ef4444`, vert `#10b981`, ambre `#fbbf24`).
- Typo responsive : `rem`, breakpoints 768 / 1024 comme règles projet.
- **Pas de template base Django** : structure HTML dans le partial / page existante.

---

## 6. Temps réel (directeur_live)

| Option | Description | Phase |
|--------|-------------|-------|
| A (simple) | `presence.mise_a_jour` déclenche **reload** location si `data-live-page=dashboard` et onglet absences actif | P2 |
| B (cible) | Endpoint GET `?partial=absences_stats` + swap KPI/JSON + re-init charts | P4 |

Commencer par **A** pour livrer vite ; documenter **B** si le reload est jugé trop brutal en recette.

---

## 7. Plan de livraison par phases

### P0 — Préparation (0,5 j)

- [x] Valider contrat métier §2 avec le commanditaire.
- [x] Créer fixtures minimal test (2 classes, F/M, présences variées).
- [x] Maquette ASCII validée (§8).

### P1 — Backend + KPI (1 j)

- [x] Implémenter `dashboard_absences_stats.py` (KPI K1–K8, K9).
- [x] Brancher `dashboard_directeur`.
- [x] Tests unitaires service (paliers 10–12, &gt;12, sexe, top classes).

### P2 — UI cartes + partial (1 j)

- [x] `dashboard_tab_absences.html` + CSS.
- [x] Bandeau KPI + tableaux T1/T3.
- [x] Include dans dashboard, versionner CSS `?v=`.

### P3 — Graphiques + animations (1 j)

- [x] Chart.js CDN (même version que comptabilité).
- [x] `dashboard_absences_charts.js` lazy init depuis `dashboard_directeur.js`.
- [x] Compteurs + `prefers-reduced-motion`.
- [x] Graphiques G1–G6.

### P4 — Finitions (0,5–1 j)

- [ ] G7 (canvas dédié — données `sexe_tranche_13_plus` déjà calculées).
- [x] K10 couverture appels, T2 classes sous seuil.
- [x] i18n `{% trans %}` sur libellés.
- [x] Intégration `directeur_live` (option A — reload dashboard déjà mappé).
- [x] Recette desktop (`127.0.0.1:8001`, compte établissement connecté).

### P5 — Déploiement

- [ ] Commit + push `main` si demandé.
- [ ] `deploy.sh` VPS + vérif services + smoke `https://aria-edu.com/dashboard/directeur/?activite=absences`.

---

## 8. Maquette structurelle (référence)

```
┌─ En-tête + CTA suivi / liste élèves ─────────────────────────┐
├─ KPI row (4×2 desktop, 2×N mobile) ──────────────────────────┤
├─ Graphiques row 1 : [G1 Donut F/M] [G4 Top 5 classes] ───────┤
├─ Graphiques row 2 : [G3 Tranches] [G6 Évolution mensuelle] ──┤
├─ Graphiques row 3 : [G2 Statuts] [G5 Bottom 5] ────────────────┤
├─ Tableau élèves à risque (T1) ─────────────────────────────────┤
├─ Timeline dernières soumissions (T3) ──────────────────────────┤
└─ Encart qualité données + légende ─────────────────────────────┘
```

---

## 9. Recette (checklist)

**URL locale :** `http://127.0.0.1:8001/dashboard/directeur/?activite=absences`  
**Comptes :** voir `.cursor/rules/info-connexion-utilisateur.mdc` (directeur primaire / collège).

| # | Scénario | Attendu |
|---|----------|---------|
| R1 | Onglet Absences au chargement | KPI cohérents avec suivi présence sur même année |
| R2 | Changement onglet Notes puis retour Absences | Graphiques initialisés une seule fois ou re-render sans fuite mémoire |
| R3 | F5 + `?activite=absences` | Persistance `directeur:dashboard` storage |
| R4 | Ctrl+F5 | Cache bust CSS/JS |
| R5 | Viewport 375px | KPI 2 col., tableaux scroll horizontal + gradient hint |
| R6 | Établissement sans présences | Empty state, pas d’erreur JS |
| R7 | Soumission présence (prof) | Live reload ou refresh stats (selon phase) |
| R8 | Comparer 2 élèves palier 11 et 13 NJ | K7/K8 corrects |
| R9 | Classe petite (&lt;10 appels) | Exclue ou badge « données faibles » top 5 |

---

## 10. Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| Double comptage multi-matières secondaire | Documenter « par appel » ; KPI jours distincts §3.6 |
| Requêtes lourdes gros établissements | Annotate SQL, cache P4, pas de N+1 |
| Chart.js onglet caché canvas 0×0 | Init uniquement quand `#tab-absences` visible |
| Divergence liste élèves vs dashboard | Même helper `get_nombre_absences` / même filtre année |

---

## 11. Évolutions post-MVP (backlog)

- Filtre **mois** : `?activite=absences&mois=2026-03` (recalc service).
- Harmonisation onglets Notes/Sanctions (même grille KPI).
- Endpoint JSON pour assistant IA directeur (`get_tableau_absences_etablissement`).
- Export CSV élèves à risque.
- Widget « comparaison inter-années ».

---

## 12. Suivi d’avancement

| Phase | Statut | Date | Notes |
|-------|--------|------|-------|
| P0 | ☑ | 2026-10-02 | |
| P1 | ☑ | 2026-10-02 | 3 tests OK |
| P2 | ☑ | 2026-10-02 | partial + CSS |
| P3 | ☑ | 2026-10-02 | Chart.js lazy |
| P4 | ☑ (G7 restant) | 2026-10-02 | reload WS existant |
| P5 | ☐ | | déploiement VPS sur demande |

**Prochaine action :** validation du commanditaire sur §2 (défauts retenus) → démarrer **P1**.
