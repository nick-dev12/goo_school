# Rapport D1 — Dashboard administratif premium Aria

**Date :** 2026-10-02  
**Portée :** D0 + D1 uniquement. **D2 non commencé** (stop gate).

---

## 1. Architecture finale

```
Vue GET /dashboard/directeur/
  → dashboard_directeur
      → DashboardContext (année, période, filtres, vue, permissions)
      → build_executive_dashboard
          → compute_metric(student_count | class_capacity | attendance_rate | cycle_distribution)
          → build_today_block
          → build_completeness_block
          → build_filter_options
      → absences_dashboard (élève filtrés par le même contexte)
```

Pas de nouveau modèle Django. Pas de Redis. Chart.js 4.4 uniquement.

---

## 2. Fichiers créés

| Fichier | Rôle |
|---------|------|
| `school_admin/services/dashboard/querysets.py` | Querysets filtrés (établissement + année + cycle/classe) |
| `school_admin/services/dashboard/filter_options.py` | Options cascade du formulaire GET |
| `school_admin/services/dashboard/today.py` | Bloc Aujourd’hui |
| `school_admin/services/dashboard/completeness.py` | Fiabilité / complétude |
| `school_admin/services/dashboard/executive.py` | Assemblage D1 |
| `school_admin/templates/.../dashboard/partials/_filter_bar.html` | Filtres GET |
| `school_admin/templates/.../dashboard/partials/_executive.html` | Bandeau executive |
| `school_admin/templates/.../dashboard/components/_stat_card.html` | Carte KPI |
| `school_admin/static/.../css/directeur/dashboard_executive.css` | Styles D1 |
| `school_admin/static/.../js/directeur/dashboard_executive_charts.js` | Barres horizontales cycles |
| `school_admin/tests/test_dashboard_d1.py` | Tests D1 |
| `.cursor/context/rapport_dashboard_d1.md` | Ce rapport |

## 3. Fichiers modifiés

| Fichier | Modification |
|---------|--------------|
| `services/dashboard/context.py` | `CYCLE_VALUES`, période GET sécurisée |
| `services/dashboard/metrics/effectifs.py` | Filtres + `class_capacity` + `cycle_distribution` |
| `services/dashboard/metrics/presence.py` | Queryset partagé |
| `personal_views/directeur_view.py` | Contexte + executive + absences filtrées |
| `dashboard_directeur.html` | Include executive, KPIs historiques repliés |
| `dashboard_directeur.js` | Persistance filtres (`vue`, `cycle`, `classe`, `periode`, `filiere`) |
| `_header_meta.html` | Toggle vue conserve les filtres |
| `feuille_route_dashboard_admin_premium_aria.md` | Statut D1 |

---

## 4. Services / métriques disponibles

| id | Unité | Source | Comparaison |
|----|-------|--------|-------------|
| `student_count` | count | InscriptionEleve + Eleve.actif | année précédente si elle existe |
| `class_capacity` | % | capacite_max configurée / inscrits | — |
| `cycle_distribution` | count | classe.niveau | — |
| `attendance_rate` | % | `dashboard_absences_stats` | vs mois précédent si données |

---

## 5. Métriques impossibles (D1) et raisons

| Besoin | Raison |
|--------|--------|
| Cours programmés / réalisés aujourd’hui | Pas d’agrégat EDT fiable branché ici — à auditer en D7 |
| Notes manquantes par évaluation | Hors D1 ; `ReleveNotes` en D2/D3 |
| Funnel inscriptions | Statuts préinscription non mappés |
| Recouvrement / impayés KPI | D4 (service recouvrement existe déjà) |
| Heatmap absences | Phase ultérieure, CSS/HTML |
| Unification `attendance_rate` vs assistant (retards) | Décision produit ouverte — **D2** |

---

## 6. Requêtes importantes

- Inscriptions : `Count` / `values('classe__niveau')` — pas de boucle élèves.
- Capacité : `annotate(Count('inscriptions_eleves', filter=…))`.
- Présence jour : `aggregate` sur `Presence` date=today.
- Complétude appels : 1 query classes + 1 query soumissions 5 jours ouvrés.
- Classe d’un autre établissement : **ignorée** (pas de fuite tenant).
- Période d’une autre année : **ignorée**, fallback période active.

---

## 7. Tests

```
manage.py test school_admin.tests.test_dashboard_d0 \
  school_admin.tests.test_dashboard_d1 \
  school_admin.tests.test_dashboard_absences_stats --keepdb
```

**17 tests OK.**

Couverture D1 : filtre cycle, cycle invalide, classe autre établissement, capacité, répartition, période autre année, permission personnel, empty attendance ≠ 0.

Recette HTTP : 200, blocs présents.  
Recette navigateur : `?cycle=college` → classes limitées au collège, chips « Filtres actifs », complétude 5 classes (au lieu de 11).

---

## 8. Performance

Pas de Redis. Pas de N+1 élèves. Mesure P95 non instrumentée (à faire en D2 si besoin). Cache reporté.

---

## 9. Problèmes rencontrés

- Collision `code_etablissement` dans un test (suffixe trop court) — corrigé via UUID.
- Clic « Appliquer » masqué par le FAB assistant dans le navigateur automatisé — le GET `?cycle=college` valide le même contrat formulaire.
- « Appels reçus aujourd’hui : 0 » est un **compte réel du jour**, pas une donnée manquante (la présence du jour affiche bien un empty state).

---

## 10. Décisions techniques

1. Filtres 100 % GET Django (`action` + `Appliquer`).  
2. Vue executive par défaut ; KPIs historiques repliés, pas supprimés.  
3. Dépassement de capacité = `effectif > capacite_max` (seuil configuré, pas inventé).  
4. Onglet absences **conservé** et filtré par le même contexte.  
5. Fraîcheur = horodatage serveur, `is_live=false`.

---

## 11. Recommandations pour D2 (à valider)

1. Trancher **retards = présents ou non** pour `attendance_rate`.  
2. Alertes structurées (URGENT / IMPORTANT / SURVEILLER / INFO).  
3. Insights déterministes + « Pourquoi ? ».  
4. Factory Chart.js unique (fusionner absences + executive).  
5. Ne pas ouvrir D3/D4 tant que D2 n’est pas recetté.

**D2 n’est pas implémenté.**
