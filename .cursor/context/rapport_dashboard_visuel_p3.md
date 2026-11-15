# Rapport Phase 3 — Graphiques principaux

**Date :** 2026-10-02  
**URL :** `/dashboard/directeur/?vue=executive`  
**Compte recette :** fleur de lune (`webgeniuses12@gmail.com`)

## Fait

- **Situation générale** : courbe présence quotidienne 30 j (retard ≠ présent). Pastilles 7 j / 30 j si calculables. Pas de série réussite mélangée (période scolaire ≠ jours).
- **Répartition** : donut + total au centre + légende avec effectif et %.
- **Présence par classe** : métrique `presence_by_class` (min. 3 appels, rouge sous 85 %). Plus le top 10 de l’onglet absences.
- **Résultats** : barres réussite par cycle si moyennes ; sinon répartition des notes ; empty si aucune moyenne.
- **Finance** : courbe 30 j si encaissements, sinon barres de statuts ; légende reste + recouvrement. Empty si aucune charge.
- **CTA « Voir le détail »** sur chaque carte :
  - présence → `/suivi-presence/`
  - effectifs → `/gestion-eleves/`
  - notes → `/notes-et-resultats/`
  - finance → `/comptabilite/impayes/`

## Recette navigateur

| Bloc | Tous cycles | Filtre collège |
|------|-------------|----------------|
| Situation | 1 point 04/09, 50,0 % sur 30 j | empty (pas d’appels collège récents) |
| Effectifs | donut 103 (53 / 50, 51,5 % / 48,5 %) | Collège 53 100 % |
| Présence classes | 1ère A 50 % (rouge) | empty (min. 3) |
| Résultats | empty — aucune moyenne T1 | idem |
| Finance | empty — aucune charge | idem |

Routes de drill-down HTTP 200. Bottom nav **non modifiée**.  
Les CTA en bas de carte peuvent être masqués par la bottom nav (Phase 5).

## Tests

39 tests OK (`test_dashboard_d0`–`d4`, `test_dashboard_visuel`, `test_dashboard_absences_stats`, `--keepdb`).  
Daphne redémarré sur `127.0.0.1:8001`.

## Suite

Phase 4 : bandeau « À retenir » + badge données partielles (déjà partiellement en place).
