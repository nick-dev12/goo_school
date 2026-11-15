# Rapport D4 — Finances

**Date :** 2026-10-02  
**Décision produit :** recouvrement = **payé / dû** ; sans charge → **tiret**, jamais 0 % inventé.

---

## Architecture

- `metrics/finance.py` : `collection_rate`, `outstanding_amount`, `finance_status`
- `querysets.comptabilite_qs` : dossiers filtrés par élèves inscrits + filtres GET
- Formule alignée assistant `tool_statistiques_pilotage`
- Devise : `recouvrement.devise_etablissement`

## UI executive

- KPI : Taux de recouvrement, Reste à recouvrer
- Bloc **Comment se porte la scolarité ?**
  - statuts de paiement (barres)
  - encaissements 30 j (courbe)
  - tableau restes par classe
- Insight : recouvrement < 70 % (seuil fixe documenté)
- Alerte impayés (D2) conservée

## Tests

31 tests OK (D0–D4).

Preuve : 20 000 / 50 000 → **40 %**, reste **30 000**.

## Recette

HTTP 200, blocs finance présents. Données réelles selon dossiers comptables de l’établissement.

## Suite

D5 (enseignants) non commencé.
