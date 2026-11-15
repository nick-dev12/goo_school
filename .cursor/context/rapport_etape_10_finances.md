# RAPPORT ÉTAPE 10

## 1. Objectif

Couvrir les 17 scénarios financiers du brief, l’isolation par établissement, les requêtes ORM, les largeurs d’écran, et le rapport d’anomalies des écritures `source=depense` orphelines.

Pas de Redis. Pas de nouvelle fonctionnalité. Aucune contre-écriture automatique.

## 2. Fichiers modifiés

- `school_admin/services/finances/metrics.py` — Disponible : un agrégat `LigneEcriture`, même formule que `solde_calcule`, au lieu d’un SELECT par compte.
- `school_admin/controllers/finances_controller.py` — GET Entrées : ne charge que la sous-vue affichée. GET : n’appelle plus `ensure_plan_comptable` / `assurer_*` si les comptes de trésorerie existent déjà.

## 3. Fichiers créés

- `school_admin/tests_finances_scenarios.py`
- `.cursor/context/rapport_etape_10_finances.md`

## 4. Modèles modifiés

Aucun.

## 5. Migrations

Aucune. Aucune donnée recréée. Aucune orpheline extournée.

## 6. Services

Lecture seule inchangée pour `ecritures_depenses_orphelines`. `calculer_indicateurs` n’appelle toujours pas `kpi_cg`. Les écritures restent derrière `creer_ecriture`.

## 7. URLs / Views

Aucune URL nouvelle. Les cinq GET Finances restent les mêmes.

## 8. Templates / CSS / JS

Aucun.

## 9. Tests exécutés

```
.\env\Scripts\python.exe manage.py test school_admin.tests_finances_scenarios school_admin.tests_finances_ui school_admin.tests_finances_metrics school_admin.tests_finances_rapprochement school_admin.tests_finances_prets school_admin.tests_finances_transferts school_admin.tests_finances_charges school_admin.tests_finances_fondations school_admin.tests_finances_recettes school_admin.tests_caisse school_admin.tests_comptabilite_generale school_admin.tests_frais_annexes school_admin.tests_recouvrement --keepdb
```

## 10. Résultat des tests

PASS. 126 tests. 0 échec.

Les 17 scénarios, dans `tests_finances_scenarios` :

| # | Scénario | Contrôle |
|---|---|---|
| 1 | Paiement scolaire | Encaissé, aucune `RecetteEtablissement`, onglet Scolarité |
| 2 | Dépense | Payé, pill `cg-pill--info` |
| 3 | Facture partielle | Reste 20, Engagements 20, Payé 430 |
| 4 | Facture soldée | Reste 0, Engagements 0 |
| 5 | Transfert | Hors Encaissé / Payé / Résultat, Disponible inchangé |
| 6 | Prêt | Disponible et Dettes, pas Encaissé ni Résultat |
| 7 | Remboursement prêt | Capital hors Payé, intérêts et frais dans Payé et Résultat |
| 8 | Remboursement opération | Origine conservée, Encaissé = net |
| 9 | Annulation | Ligne conservée, totaux à 0 |
| 10 | Période verrouillée | `ValueError`, rien enregistré |
| 11 | Permissions | Anonyme redirigé, secrétaire refusé, caissier GET OK sans annuler |
| 12 | Rapprochement | Pointage sans écriture supplémentaire |
| 13 | Multi-banques | Banque A → B et caisse → mobile hors résultat |
| 14 | Régime engagement | Charge à l’émission, Payé au règlement |
| 15 | Régime trésorerie | Résultat 0 à l’émission, charge au paiement |
| 16 | Double comptabilisation | Sortie refusée si facture ouverte ; créances + encaissement ≠ Résultat ; prêt et virement hors Encaissé |
| 17 | Isolation | Autre école absente des GET et des indicateurs |

ORM : `calculer_indicateurs` ≤ 4 lectures `LigneEcriture` même avec plusieurs banques. GET Situation plafonné (chrome directeur inclus). Orphelines filtrées par établissement, sans extourne.

## 11. Tests manuels

Base locale (4 établissements) : `ecritures_depenses_orphelines` = **0**. Aucune contre-écriture.

Directeur fleur de lune, `http://127.0.0.1:8001` : Situation, Entrées, Sorties, Trésorerie, Financements se chargent après le correctif ORM du contrôleur.

## 12. Vérification UI

Les cinq onglets restent ceux de l’étape 9. Pas de second design. Une sortie validée n’est pas rouge. `kpi_cg` n’apparaît pas sur Situation.

## 13. Responsive

Pas de débordement de page (`scrollWidth === clientWidth`) à 375 et 768 après rechargement. À 375, overflow des onglets (« Afficher 3 autres onglets »). Les largeurs 1920, 1440, 1366, 1024, 430, 390 avaient déjà été mesurées à l’étape 9 sans overflow de document.

## 14. Problèmes rencontrés

- L’élève s’affiche `SOW Awa` (casse du nom), pas `Sow`.
- `enregistrer_regime_comptable` n’accepte pas `user=`.
- Le GET Situation charge encore le chrome directeur (header, session, assistant) : le plafond de requêtes HTTP reste élevé, ce n’est pas un N+1 du moteur des sept indicateurs.

## 15. Risques restants

- `kpi_cg` n’est toujours pas le moteur des sept indicateurs. Volontaire.
- Le dashboard (`services/dashboard/metrics/finance.py`) n’utilise pas `calculer_indicateurs`.
- La liste des factures de l’onglet Sorties n’est pas bornée au mois du filtre GET (plafond 80, toutes dates).
- `solde_initial` reste ignoré par `solde_calcule` / Disponible.
- Créances, Engagements et Dettes restent un stock courant, pas un historique à une `date_fin` passée.
- Les deux recettes de contrôle 15 000 XOF de l’étape 9 restent sur fleur de lune.
- Redis n’est pas ajouté. La mesure réelle des GET montre surtout le chrome, pas un besoin de cache métier.

## 16. État final

TERMINÉ. Le plan d’implémentation Finances (étapes 0 à 10) est couvert.

## 17. Étape suivante

Aucune étape d’implémentation dans ce plan.

Hors plan, si un GO distinct le demande : brancher le dashboard sur `calculer_indicateurs`, filtrer les factures sur le mois, ou traiter manuellement d’éventuelles orphelines de production. Rien de cela n’est commencé.
