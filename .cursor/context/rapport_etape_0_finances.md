# RAPPORT ÉTAPE 0

## 1. Objectif

Figer le plan d’implémentation par étapes et mesurer les tests financiers déjà présents. Aucun modèle, aucune migration, aucun écran.

## 2. Fichiers modifiés

Aucun.

## 3. Fichiers créés

- `.cursor/context/plan_implementation_finances.md`
- `.cursor/context/rapport_etape_0_finances.md`

## 4. Modèles modifiés

Aucun.

## 5. Migrations

Aucune.

## 6. Services

Aucun.

## 7. URLs / Views

Aucune.

## 8. Templates / CSS / JS

Aucun.

## 9. Tests exécutés

```
.\env\Scripts\python.exe manage.py test school_admin.tests_comptabilite_generale school_admin.tests_caisse school_admin.tests_frais_annexes school_admin.tests_recouvrement --verbosity 1 --keepdb
```

Répertoire : `c:\wamp64\www\goo_school`.
`--keepdb` : la base `test_aria` existait déjà. Django demandait une confirmation interactive pour la supprimer. La base de test a été réutilisée, pas détruite.

## 10. Résultat des tests

FAIL. 44 tests, 2 échecs, 42 réussites.

Les deux échecs sont dans `school_admin.tests_comptabilite_generale.PontsEtBackfillTests` :

- `test_backfill_411_sans_doubler_le_deja_encaisse` : `backfill_creances_ouvertes` renvoie `emises = 0`, le test attend au moins 2.
- `test_regime_verrouille_apres_ecriture` : `regime_est_verrouille` est déjà vrai avant l’encaissement que le test voulait être le premier.

Cause lue dans le code, pas corrigée : `signals/comptabilite_signals.py` poste une créance (`creance_inscription`, `creance_mensualite`) dès la création du frais. Ces pièces existent donc avant l’appel explicite du test. Le backfill les ignore parce que `source` + `source_id` existent déjà. Le régime est verrouillé par ces mêmes pièces. Les tests décrivent un monde où seule la fonction appelée dans le test écrit. Le signal écrit avant.

`tests_caisse`, `tests_frais_annexes` et `tests_recouvrement` n’apparaissent pas dans les échecs.

## 11. Tests manuels

Aucun parcours écran. Cette étape ne change pas l’application.

## 12. Vérification UI

Non concernée.

## 13. Responsive

Non concerné.

## 14. Problèmes rencontrés

- `python -m django test` sans `manage.py` échoue : `DJANGO_SETTINGS_MODULE` n’est pas défini.
- La création de `test_aria` échoue si la base existe, et Django attend une saisie « yes » impossible ici. Relance avec `--keepdb`.
- Les deux tests ci-dessus échouent sur le code actuel, avant toute modification de cette étape.

## 15. Risques restants

- La suite comptable générale n’est pas verte. L’étape 1 ne doit pas empiler de changements tant que ces deux tests ne sont pas soit corrigés, soit assumés comme obsolètes par rapport au signal.
- `kpi_cg` et `solde_mois` ne mesurent pas les sept indicateurs. Inchangé.
- Le caissier ouvre encore la comptabilité générale avec `comptabilite_voir`. Inchangé.
- Une dépense validée peut encore être effacée alors que son écriture reste. Inchangé.

## 16. État final

TERMINÉ pour la préparation. Le plan est écrit. La mesure de départ est FAIL, documentée, non masquée.

## 17. Étape suivante

Étape 1 — sécurisation de l’existant : retirer au caissier l’accès au hub comptable, empêcher l’effacement d’une dépense déjà écrite, ne plus avaler l’erreur de `pont_depense`, lister les écritures `source=depense` orphelines sans les extourner.

Elle n’est pas commencée. Les deux tests rouges devront être traités au début de cette étape, ou par un GO dédié, avant d’ajouter d’autres changements.
