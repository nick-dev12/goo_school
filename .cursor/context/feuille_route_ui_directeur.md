# Feuille de route UI — espace directeur (copie repo)

Référence store : `docs/feuille-route-ui-directeur.md` (agent store).

| Vague | Statut |
|-------|--------|
| 0 — Liste élèves | Livrée |
| 1 — Hub élèves, certificats, attestations, fiches, convocations, cartes, réinscription | Livrée |
| 2 — Matières, classes, examens, périodes, EDT, notes/bulletins | Livrée |
| 3 — Annonces, liaison parents, présences | Livrée |
| **4 — Personnel, établissement, dashboard** | **Livrée (2026-09-26)** |
| 5+ | Hors scope session |

## Recette Vague 4 (`http://127.0.0.1:8047`)

- `/dashboard/directeur/`
- `/gestion-etablissement/`
- `/profil/etablissement/`
- `/personnel/`

Ctrl+F5, overflow, F5 persistance, smoke métier.

## Recette Vague 3 (`http://127.0.0.1:8047`)

- `/directeur/annonces/`
- `/demandes-liaison/`
- `/suivi-presence/`

## Recette Vague 2 (`http://127.0.0.1:8047`)

- `/matieres/` — `/classes/` — `/gestion-examens/` — `/periodes-scolaires/` — `/emplois-du-temps/` — `/notes-et-resultats/` — `/bulletins/`
