# RAPPORT ÉTAPE 6

## 1. Objectif

Enregistrer un prêt et ses remboursements. La réception débite la trésorerie et crédite la dette. Elle n'entre pas dans le résultat. Le remboursement débite la dette pour le capital, les charges pour les intérêts et les frais, et crédite la trésorerie pour le total. Le capital restant ne peut pas devenir négatif.

Les comptes 1621, 6711 et 6712 sont ajoutés au plan, comme prévu pour cette étape.

## 2. Fichiers modifiés

- `school_admin/services/comptabilite_generale.py`
- `school_admin/model/finances_model.py`
- `school_admin/model/__init__.py`
- `school_admin/services/finances/operations.py`
- `school_admin/controllers/comptabilite_generale_controller.py`
- `school_admin/personal_views/directeur_view.py`
- `school_admin/personal_url/directeur_url.py`
- `school_admin/templates/school_admin/directeur/comptabilite_generale/hub.html`
- `school_admin/templates/school_admin/directeur/comptabilite_generale/partials/cg_subnav.html`
- `school_admin/static/school_admin/css/directeur/comptabilite_generale.css`

## 3. Fichiers créés

- `school_admin/services/finances/prets.py`
- `school_admin/templates/school_admin/directeur/comptabilite_generale/prets.html`
- `school_admin/migrations/0229_prets_remboursements.py`
- `school_admin/tests_finances_prets.py`
- `.cursor/context/rapport_etape_6_finances.md`

## 4. Modèles modifiés

- `PretEtablissement` : compte crédité, référence, date, montant, taux, durée, objet, statut en cours / soldé / annulé.
- `EcheancePret` : prévision de capital, d'intérêts et de frais. Aucune écriture.
- `RemboursementPret` : capital, intérêts et frais séparés. Le prêt d'origine reste.

## 5. Migrations

`0229_prets_remboursements`. Création des trois tables. Aucun prêt inventé pour l'historique. L'opération automatique sur les fonctions du personnel a été retirée.

Les comptes 1621, 6711 et 6712 ne sont pas dans la migration : `ensure_plan_comptable` les crée à la première ouverture, sans réécrire les écritures déjà là.

## 6. Services

- `enregistrer_pret` : débit du compte crédité, crédit 1621. Pas de classe 6, pas de classe 7.
- `ajouter_echeance` : ligne de prévision seulement.
- `enregistrer_remboursement` : débit 1621 pour le capital, 6711 pour les intérêts, 6712 pour les frais, crédit trésorerie pour le total. Le contrôle du capital restant est dans la transaction.
- Quand le capital restant tombe à 0, le prêt passe à Soldé.
- `annuler_pret` refuse tant qu'un remboursement validé existe. La ligne reste. Contre-écriture du jour.

## 7. URLs / Views

`comptabilite-generale/prets/`, nom `cg_prets`, réservée à `comptabilite_bilans`. POST : prêt, échéance, remboursement, annulations.

## 8. Templates / CSS / JS

- Bandeau du résultat des classes 6 et 7, avec la phrase qui dit que le capital ne le change pas.
- Fiche : compte, date, montant, référence, objet, taux, durée, justificatif facultatif.
- Capital restant en violet. Soldé en vert. Annulé en gris. Remboursement validé en bleu.
- Échéance et remboursement en POST Django. Pas de JavaScript pour l'envoi.
- Aplats, pas de dégradé. CSS `?v=1.0.7`.

## 9. Tests exécutés

```
.\env\Scripts\python.exe manage.py test school_admin.tests_finances_prets school_admin.tests_finances_recettes school_admin.tests_comptabilite_generale --keepdb
```

```
.\env\Scripts\python.exe manage.py test school_admin.tests_finances_transferts school_admin.tests_finances_charges school_admin.tests_finances_fondations school_admin.tests_caisse --keepdb
```

## 10. Résultat des tests

PASS. 33 tests, puis 28 tests. 0 échec.

Couvert : réception 20 000 000 en 521 / 1621 sans produit ni charge, remboursement 500 000 + 100 000 + 10 000 (reste 19 500 000, charges +110 000, banque 19 390 000), échéance sans écriture, capital trop élevé refusé, annulation qui ramène la banque à 0, période verrouillée, autre école.

## 11. Tests manuels

Sur fleur de lune : prêt VERIF-PRET de 1 XOF en caisse, objet « Vérification ». Le résultat reste à 0. Capital restant 1, statut En cours. Remboursement du capital 1 : capital restant 0, statut Soldé, résultat toujours 0. Annulation du remboursement, puis du prêt. Les deux lignes restent, statut Annulé. Le résultat est toujours 0.

## 12. Vérification UI

La page Prêts montre le résultat, le formulaire et la fiche annulée. Le menu complémentaire était déjà ouvert.

## 13. Responsive

À 375 px, la page ne déborde pas (`scrollWidth` = 375). Le tableau défile dans son cadre (840 px de contenu dans 296 px visibles).

## 14. Problèmes rencontrés

- La migration automatique voulait réécrire les fonctions du personnel. Cette opération a été retirée.

## 15. Risques restants

- Le prêt VERIF-PRET de 1 XOF et son remboursement restent dans l'historique de fleur de lune, tous deux annulés. Les écritures se compensent.
- Le taux et la durée sont enregistrés. Ils ne calculent pas l'échéancier tout seuls. Les échéances se saisissent.
- `kpi_cg` n'est toujours pas le moteur des sept indicateurs.

## 16. État final

TERMINÉ.

## 17. Étape suivante

Étape 7 — rapprochement bancaire : `ReleveBancaire` et `LigneReleve`. Afficher le solde Aria, le solde du relevé, l'écart et les lignes non pointées. Une ligne pointée ne se modifie plus en silence. Le booléen `MouvementTresorerie.pointe` est audité avant de décider s'il est conservé ou seulement lu.

Elle n'est pas commencée.
