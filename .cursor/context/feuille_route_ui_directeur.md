# Feuille de route UI — espace directeur (copie repo)

Référence store : `docs/feuille-route-ui-directeur.md` (agent store).

| Vague | Statut |
|-------|--------|
| 0 — Liste élèves | Livrée |
| 1 — Hub élèves, certificats, attestations, fiches, convocations, cartes, réinscription | Livrée |
| 2 — Matières, classes, examens, périodes, EDT, notes/bulletins | Livrée |
| 3 — Annonces, liaison parents, présences | Livrée |
| 4 — Personnel, établissement, dashboard | Livrée (2026-09-26) |
| **5 — Compta élèves / impayés / scolarité (pas CG)** | **Livrée (2026-09-26)** |
| **6 — Dashboard onglet Absences (KPI + graphiques)** | **Livrée en local (2026-10-02) — [feuille_route_dashboard_absences_directeur.md](feuille_route_dashboard_absences_directeur.md)** |

**Feuille vagues 0–5 : terminée.**  
**Vague 6 : livrée en local ; déploiement VPS (P5) sur demande.**

## Recette Vague 6 (prévue)

- `/dashboard/directeur/?activite=absences`
- Cohérence avec `/suivi-presence/` (même année scolaire consultée)
- Desktop + mobile, Chart.js lazy, F5 + persistance onglet `activite`

## Recette Vague 5 (`http://127.0.0.1:8047`)

- `/comptabilite/eleves/`
- `/comptabilite/impayes/`
- `/comptabilite/bilan/`
- `/comptabilite/classe/<id>/bilan/`
- `/comptabilite/eleve/<id>/details/`
- `/comptabilite/parametres/`
- `/comptabilite/caisse/`

Ctrl+F5 desktop + mobile, overflow, F5 persistance, smoke métier.

## Recette Vague 4 (`http://127.0.0.1:8047`)

- `/dashboard/directeur/`
- `/gestion-etablissement/`
- `/profil/etablissement/`
- `/personnel/`

## Recette Vague 3 (`http://127.0.0.1:8047`)

- `/directeur/annonces/`
- `/demandes-liaison/`
- `/suivi-presence/`

## Recette Vague 2 (`http://127.0.0.1:8047`)

Voir store / commit Vague 2.
