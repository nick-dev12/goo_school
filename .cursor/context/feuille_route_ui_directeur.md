# Feuille de route UI — espace directeur (Design System ARIA)

Référence visuelle : design system ARIA (palette `#2563EB`, fond `#F8FAFC`, cartes blanches).  
Pilote livré : **liste élèves** — `http://127.0.0.1:8001/liste/eleves/`.

Copie synchronisée avec le livrable agent : `docs/feuille-route-ui-directeur.md` (store projet).

## Principes communs

- Onglets : `matiere-tabs-bar` + overflow (`tabs_nav_overflow.js`, bouton « Autres … »).
- Persistance : query string (`?niveau=`, `?classe=`, …) + `localStorage` en secours ; `replaceState`.
- Structure : hero KPI → panneau → navigation → filtres → liste/table.
- Responsive + rôles ARIA tablist/tab/tabpanel.

## Vagues

| Vague | Périmètre |
|-------|-----------|
| **0** | Liste élèves (done) |
| **1** | Certificats, attestations, fiches, convocations, réinscription, hub gestion élèves |
| **2** | Matières, classes, examens, périodes, EDT, notes/bulletins |
| **3** | Annonces, liaison parents, présences |
| **4** | Personnel, établissement, dashboard |
| **5** | Compta élèves / impayés (pas CG complète) |

## Hors scope

Assistant vocal, comptabilité générale lourde, shell/VPS, refonte enseignant/élève/parent.

## Recette

Overflow desktop/mobile, refresh = même onglet, actions métier OK. Voir checklist détaillée dans la copie store `docs/feuille-route-ui-directeur.md`.
