# Rapport D2 — Présences, alertes, insights

**Date :** 2026-10-02  
**Décision produit :** un **retard n’est pas une présence**.

---

## Architecture

- `attendance_rate` / `attendance_trend` : numérateur = `statut='present'` uniquement.
- Assistant `PRESENCE_PRESENT` aligné (plus de retard).
- Alertes : `dashboard/alerts.py` (URGENT / IMPORTANT / SURVEILLER / INFO).
- Insights : déterministes + « Pourquoi ? ».
- Chart factory : `dashboard_chart_factory.js` (bar + line).

## Tests

22 tests OK (D0–D2 + absences + `get_taux_presence` assistant).

Preuve retard : 1 présent + 1 retard = **50 %**, pas 100 %.

## Recette

Dashboard HTTP 200 : blocs À traiter, À retenir, évolution 7/30 j.

## Suite

D3 (pédagogie) non commencé.
