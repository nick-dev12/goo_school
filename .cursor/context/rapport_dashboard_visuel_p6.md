# Rapport Phase 6 — QA finale

**Date :** 2026-10-02  
**URL :** `/dashboard/directeur/?vue=executive`  
**Compte :** fleur de lune (`webgeniuses12@gmail.com`)

## Tests automatisés

| Contrôle | Résultat |
|----------|----------|
| Anonyme → redirection `/connexion/` | OK |
| Directeur connecté → HTTP 200, `dashboard-premium`, `#dbd-a-retenir` | OK |
| Filtre `cycle=college` conservé dans le HTML | OK |
| Pas de chiffres de démo (1 248 / 94,2 % / 12,4 M) | OK |
| Bottom nav présente dans le HTML | OK |
| Personnel sans `comptabilite_voir` → finance / recettes empty | OK |

**45 tests** dashboard OK (`d0`–`d4`, visuel, absences, `--keepdb`).

## Recette vs image

| Cible | Constat |
|-------|---------|
| Topbar claire | Header blanc `rgb(255, 255, 255)`, bandeau bleu école `display: none` |
| Bottom nav | Inchangée (Accueil, Établissement, Pédagogie, Élèves, Menu) |
| Bannière + 5 KPI | Bonjour Diop, 5 cartes réelles |
| Colonne droite | Aujourd’hui / À traiter / Activité |
| Graphiques | Donut effectifs ; empty explicites si pas de données |
| Pas de 0 % trompeur | Tirets + motifs (présence, réussite, recettes) |
| Responsive | Phase 5 |
| Drill-down | 5 CTA vers routes existantes |

**Données live (filtre collège) :** 53 élèves, présence / réussite / recettes = —, dossiers incomplets = 2 (contrôles D1).

## Écarts acceptés (pas de démo)

- Pas de sidebar gauche sombre (image + contrainte bottom nav).
- KPI « 1 248 / 94,2 % / 12,4 M » non reproduits — ce n’est pas la donnée de l’établissement.
- FAB Aria peut recouvrir un lien en bas à droite.
- KPI historiques à 0 % encore dans le HTML, **masqués** en premium.

## Suite

Reproduction visuelle **P0–P6 terminée**. Pas de phase suivante dans la feuille de route.
