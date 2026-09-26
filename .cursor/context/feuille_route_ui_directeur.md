# Feuille de route UI — espace directeur (copie repo)

Référence store : `docs/feuille-route-ui-directeur.md` (agent store).

| Vague | Statut |
|-------|--------|
| 0 — Liste élèves | Livrée |
| 1 — Hub élèves, certificats, attestations, fiches, convocations, cartes, réinscription | Livrée |
| **2 — Matières, classes, examens, périodes, EDT, notes/bulletins** | **Livrée (2026-09-26)** |
| 3+ | Hors scope session |

## Recette Vague 2 (`http://127.0.0.1:8047`)

- `/matieres/` — liste matières / modules (supérieur)
- `/classes/` — gestion classes (+ spécialités supérieur)
- `/classes/specialite/<id>/` — classes par spécialité
- `/gestion-examens/` — sessions par période / groupe
- `/emploi-du-temps-examens/` — planning par session
- `/periodes-scolaires/` — années / périodes (+ niveaux LMD)
- `/emplois-du-temps/` — liste EDT par niveau
- `/emplois-du-temps/classe/<id>/` — détail EDT (cours / examens)
- `/notes-et-resultats/` — relevés
- `/notes-et-resultats/justifications/` — justifications
- `/bulletins/` — bulletins par classe

Ctrl+F5, fenêtre étroite → « Autres … », F5 = même onglet, smoke métier.
