# Rapport D3 — Pédagogie

**Date :** 2026-10-02  
**Décision produit :** réussite = moyenne générale ≥ seuil configuré ; **aucune moyenne → tiret**, jamais un 0 % inventé.

---

## Architecture

- `metrics/pedagogie.py` : `success_rate`, `average_grade`, `grade_distribution`
- Seuil : `StandardsReussite.moyenne_passage`, sinon **10/20**
- Périmètre : établissement + année + période + filtres classe/cycle
- Isolation tenant : un autre établissement n’entre pas dans le calcul
- Comparaison : période précédente de la même année (si des moyennes existent)

## UI executive

- KPI : Taux de réussite, Moyenne générale (`/20`)
- Bloc **Comment se répartissent les résultats ?**
  - histogramme Chart.js (tranches)
  - tableau par classe (scroll horizontal)
  - élèves sous le seuil → fiche élève
- Alertes : sous seuil (SURVEILLER), bulletins non publiés (IMPORTANT)
- Insight : réussite en baisse vs période précédente

## Tests

26 tests OK (D0–D3).

Preuves :

- 11/20 + 13/20 avec seuil 12 → **50 %**
- sans moyenne → `empty`, valeur `None`
- autre établissement ignoré
- personnel sans `notes_liste` refusé

## Recette navigateur (fleur de lune)

HTTP 200. KPI pédagogie = **—** (« Aucune moyenne générale calculée pour cette période »).  
Le widget historique replié affiche encore 0 % : dette volontaire, non touchée en D3.

## Suite

D4 (finances) non commencé.
