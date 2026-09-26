# Feuille de route UI — espace professeur (copie repo)

**Store** : `...\bc-451181e0-...\files\docs\feuille-route-ui-professeur.md`

**Statut** : **Vagues 0–3 livrées** — branche `cursor/prof-ui-vague3-a40c` — **STOP avant Vague 4 (LMD supérieur)**.

## V3 — collège / lycée / mixte

- Hub : `prof_hub_ui_assets.html` / `prof_hub_ui_scripts.html`, partials primaire (classe, période, recherche).
- Backend : `enseignant_est_hub_v3_collège_lycée`, `_enseignant_classe_hub_bundle`, context processor `professeur_hub_v3`.
- URLs clés : `/enseignant/classes/`, `eleves/`, `presence/`, `notes/`, `justifications-notes/`, `exercices/`, `eleves-difficulte/` avec `?classe=` / `?periode=`.
- Hors scope : `est_superieur` (Vague 4), primaire (V0–2), directeur, assistant, CG, shell.

Voir le store pour le détail recette et manuel restant.
