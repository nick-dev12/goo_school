# Feuille de route UI — espace professeur (copie repo)

**Référence complète (store)** :  
`C:\Users\jomas\AppData\Local\Cursor\AgentStores\cursor_agent_stores\bc-451181e0-6549-474d-99e2-eb6302769440\files\docs\feuille-route-ui-professeur.md`

**Statut** : **Vague 0 + Vague 1 livrées** — branche `cursor/prof-ui-vague0-a40c` — STOP avant Vague 2+.

## Synthèse livrée

| Sujet | Livré |
|-------|--------|
| Stack prof | `professeur_tab_storage.js`, `professeur_ui_tabs.py`, overflow includes bottom nav + pages pilotes |
| Présence | Binaire Présent/Absent ; legacy lecture seule ; prof ne justifie plus ; POST retard/justifié rejeté |
| Hub notes primaire | `/enseignant/primaire/notes/?periode=&classe=&matiere=&vue=` — 3 barres overflow, relevé inline, redirect `evaluations-classe` |

## Recette (8047)

- `/enseignant/presence/<classe>/`
- `/enseignant/primaire/presence/<classe>/`
- `/enseignant/primaire/notes/?…`
- `/enseignant/primaire/evaluations-classe/<id>/` → redirect hub
