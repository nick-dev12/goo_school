# Rapport Phase 4 — À retenir + fiabilité

**Date :** 2026-10-02  
**URL :** `/dashboard/directeur/?vue=executive`  
**Compte recette :** fleur de lune (`webgeniuses12@gmail.com`)

## Fait

- Bandeau **À retenir** toujours visible (plus masqué si la liste est vide).
- Chaque puce a un libellé déterministe : *À surveiller* / *Information* / *Fiabilité*, le message, la période ou la note (`why`), et un lien *Voir*.
- Badge **Données partielles** dans le hero dès que `completeness.status != complete` : ancre `#dbd-a-retenir`, infobulle = détail D1.
- Même badge dans l’en-tête du bandeau + phrase de fiabilité (« Certaines données ne sont pas encore disponibles. »).
- Si aucun insight métrique mais des écarts D1 : les `gaps` deviennent des puces *Fiabilité*.
- Si tout est complet et sans insight : « Aucun écart sur les règles de pilotage actives. »
- Alertes reprises dans le bandeau : appels manquants, relevés non soumis, impayés, élèves sous seuil, bulletins non publiés. Aucune causalité inventée.

## Recette (fleur de lune, cycle collège)

- Hero : badge *Données partielles* → saute à `#dbd-a-retenir`.
- Bandeau : *À retenir* + badge + détail D1.
- Puce : *À SURVEILLER* — 5 classe(s) sans appel sur les 5 derniers jours ouvrés — « 5 jours ouvrés » — *Voir* → `/suivi-presence/`.
- Bottom nav **non modifiée**. Le FAB Aria peut recouvrir le lien *Voir* (à traiter en Phase 5).

## Tests

41 tests OK (D0–D4 + visuel + absences, `--keepdb`).  
Daphne redémarré sur `127.0.0.1:8001`.

## Suite

Phase 5 : responsive (1920 / 1440 / 1024 / 768 / 430) et collision bottom nav / FAB.
