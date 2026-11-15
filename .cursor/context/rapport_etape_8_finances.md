# RAPPORT ÉTAPE 8

## 1. Objectif

`services/finances/metrics.py` est la source unique des sept indicateurs : Disponible, Encaissé, Payé, Résultat, Créances, Dettes, Engagements.

Chaque indicateur documente définition, source, formule, période, établissement, année ou exercice, régime, inclus, exclus. Les créances émises et les encaissements ne s’additionnent pas. `kpi_cg` n’est pas branché sur ce moteur. Aucune interface Finances n’est ouverte.

## 2. Fichiers modifiés

Aucun fichier existant n’a été modifié. Le moteur n’est importé nulle part hors de ses tests.

## 3. Fichiers créés

- `school_admin/services/finances/metrics.py`
- `school_admin/tests_finances_metrics.py`
- `.cursor/context/rapport_etape_8_finances.md`

## 4. Modèles modifiés

Aucun.

## 5. Migrations

Aucune. Lecture seulement.

## 6. Services

`calculer_indicateurs(etablissement, date_debut, date_fin, annee_scolaire)` relit le régime et l’exercice, n’écrit rien, n’appelle pas `kpi_cg`.

| Indicateur | Formule | Période |
|---|---|---|
| Disponible | Somme des `solde_calcule` des comptes de trésorerie actifs | Stock à `date_fin` |
| Encaissé | `PaiementEleve` + `RecetteEtablissement` validée − `RemboursementOperation` validé | Flux de la période |
| Payé | `DepenseEtablissement` validée + `PaiementCharge` validé + intérêts et frais d’emprunt | Flux de la période |
| Résultat | Produits − charges sur `LigneEcriture` validée, nature charge ou produit | Flux de la période. Le régime est déjà dans les ponts. |
| Créances | `max(dû − payé, 0)` sur inscription, mensualités, frais annexes | Stock année scolaire |
| Engagements | `max(montant facture − PaiementCharge validé, 0)` | Stock courant |
| Dettes | Engagements + capital restant des prêts en cours | Stock courant |

Exclus documentés : transferts, réception d’un prêt, capital remboursé, recettes ou opérations annulées, destination « équipement » à elle seule, créances émises dans l’Encaissé, encaissement dans le Résultat en régime d’engagement (le produit est à l’émission, le paiement crédite 411).

`valeur(...)` lit un identifiant dans le même dictionnaire.

Les dates omises reprennent `bornes_mois` du jour. Une date de début postérieure à la date de fin lève `ValueError`.

## 7. URLs / Views

Aucune. L’étape 9 n’est pas commencée.

## 8. Templates / CSS / JS

Aucun.

## 9. Tests exécutés

```
.\env\Scripts\python.exe manage.py test school_admin.tests_finances_metrics school_admin.tests_finances_rapprochement school_admin.tests_finances_prets school_admin.tests_finances_transferts school_admin.tests_finances_charges school_admin.tests_finances_fondations school_admin.tests_finances_recettes school_admin.tests_caisse school_admin.tests_comptabilite_generale school_admin.tests_frais_annexes school_admin.tests_recouvrement --keepdb
```

## 10. Résultat des tests

PASS. 99 tests. 0 échec.

Couvert par `tests_finances_metrics` :

- les sept définitions, régime engagement, exercice, zéros de départ ;
- transfert et prêt hors Encaissé, Payé, Résultat ; le prêt augmente Disponible et Dettes ;
- remboursement : capital hors Payé, intérêts et frais dans Payé et Résultat ;
- facture en engagement : charge à l’émission, Payé seulement au règlement, Engagements = reste ;
- facture en trésorerie : Résultat à 0 à l’émission, charge au paiement ;
- créance 1 000 + encaissement 400 : Encaissé = 400, Créances = 600, Résultat = 1 000 (produit d’émission), pas 1 400 ;
- recette 600 et sortie 75 : Encaissé / Payé / Résultat du moteur ; `kpi_cg.entrees_mois` reste 0 (scolarité caisse seulement) ; remboursement de recette et annulation de sortie ; isolation d’un autre établissement.

## 11. Tests manuels

Aucun écran à vérifier. Le moteur n’est pas branché sur une vue.

## 12. Vérification UI

Non applicable.

## 13. Responsive

Non applicable.

## 14. Problèmes rencontrés

- `PaiementEleve` de type `frais_inscription` exige le FK `frais_inscription`. Le test le renseigne.
- Le signal `emettre_creance_inscription` passe D 411 / C 70x à la création du frais. Le Résultat en engagement vaut donc le dû émis, pas zéro. L’encaissement ne le double pas.

## 15. Risques restants

- `kpi_cg` n’est toujours pas le moteur des sept indicateurs. Inchangé, volontaire.
- `solde_initial` reste ignoré par `solde_calcule`. Disponible suit cette règle.
- Créances, Engagements et Dettes sont un stock courant. Ils ne rejouent pas l’historique à une `date_fin` passée (`montant_paye` n’est pas daté).
- Engagements ignore l’ancien champ `FactureFournisseur.montant_paye` sans ligne `PaiementCharge`.
- Le dashboard (`services/dashboard/metrics/finance.py`) n’utilise pas ce moteur.

## 16. État final

TERMINÉ.

## 17. Étape suivante

Étape 9 — Interface Finances : une entrée Finances, onglets Situation, Entrées, Sorties, Trésorerie, Financements. Filtres GET, formulaires POST Django, JavaScript limité à l’affichage, design Aria existant.

Elle n’est pas commencée.
