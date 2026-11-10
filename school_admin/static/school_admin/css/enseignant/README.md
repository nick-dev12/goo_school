# Index — design espace enseignant

Documents à suivre pour construire ou modifier l’UI professeur (tous types d’établissement).

| Sujet | README | Règle Cursor | CSS |
|---|---|---|---|
| Onglets (composant unique) | [../README-DESIGN-ONGLETS.md](../README-DESIGN-ONGLETS.md) | `.cursor/rules/design-onglets.mdc` | `shared/aria_filter_tabs.css` |
| Boutons (largeur du texte, hauteur onglets) | [README-DESIGN-BOUTONS.md](README-DESIGN-BOUTONS.md) | `.cursor/rules/design-boutons-enseignant.mdc` | `prof_notes_actions.css`, `evaluations_hub.css` |
| Listes (ex-tableaux : notes, relevés, élèves, présence, justifications) | [README-DESIGN-LISTES.md](README-DESIGN-LISTES.md) | `.cursor/rules/design-listes-enseignant.mdc` | `prof_notes_list.css` |

## Rappels globaux

- Pas de dégradé CSS — jetons dans `.cursor/rules/code-couleur-de-app.mdc`
- Templates Django autonomes, pas de `base.html`
- Formulaires via `action` Django ; JS seulement pour affichage / animation
- Hub Notes : `.cursor/rules/prof-hub-notes.mdc`
- Listes : colonnes sur tous les écrans (pas de `<table>` écran, pas de cartes mobile). Relevé Notes = bouton Moyenne + onglets par évaluation. Détail et mapping par page : [README-DESIGN-LISTES.md](README-DESIGN-LISTES.md)
