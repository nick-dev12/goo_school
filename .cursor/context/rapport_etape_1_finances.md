# RAPPORT ÉTAPE 1

## 1. Objectif

Sécuriser l'existant financier : le caissier n'ouvre plus la comptabilité générale, une dépense déjà écrite ne s'efface plus, une erreur de période n'est plus masquée, et les écritures de dépenses orphelines sont listées sans correction automatique.

## 2. Fichiers modifiés

- `school_admin/controllers/comptabilite_generale_controller.py`
- `school_admin/controllers/caisse_controller.py`
- `school_admin/services/comptabilite_generale.py`
- `school_admin/templates/school_admin/directeur/gestion_etablissement.html`
- `school_admin/templates/school_admin/directeur/caisse/caisse_mois.html`
- `school_admin/templates/school_admin/directeur/comptabilite_generale/hub.html`
- `school_admin/static/school_admin/css/directeur/comptabilite_generale.css`
- `school_admin/static/school_admin/css/directeur/caisse.css`
- `school_admin/tests_comptabilite_generale.py`

## 3. Fichiers créés

- `.cursor/context/rapport_etape_1_finances.md`

## 4. Modèles modifiés

Aucun.

## 5. Migrations

Aucune.

## 6. Services

- `ecritures_depenses_orphelines` dans `services/comptabilite_generale.py` : lecture seule.
- `pont_depense` inchangé. L'appel depuis la caisse ne masque plus `ValueError`.

## 7. URLs / Views

Aucune URL nouvelle. Les neuf vues `cg_*` exigent `comptabilite_bilans`. La caisse refuse la suppression si une écriture `source=depense` existe, et annule l'enregistrement si la période est verrouillée.

## 8. Templates / CSS / JS

- Carte « Comptabilité générale » visible seulement avec `comptabilite_bilans`.
- Sortie déjà écrite : libellé « Écrite », sans bouton Retirer.
- Hub : liste des écritures orphelines, affichée seulement s'il y en a.
- CSS aplats, pas de dégradé. Pas de JavaScript nouveau.

## 9. Tests exécutés

```
.\env\Scripts\python.exe manage.py test school_admin.tests_comptabilite_generale school_admin.tests_caisse school_admin.tests_frais_annexes school_admin.tests_recouvrement --verbosity 1 --keepdb
```

## 10. Résultat des tests

PASS. 50 tests, 0 échec.

Les deux tests rouges de l'étape 0 ont été alignés sur le signal qui émet la créance à la création du frais. Six tests nouveaux couvrent le refus caissier, l'accès comptable, l'orpheline sans extourne, la suppression bloquée, la suppression d'une sortie sans écriture, et la période verrouillée.

## 11. Tests manuels

- Hub comptable ouvert avec le directeur de fleur de lune : cartes Plan, Journaux, Exercices, Fournisseurs, Trésorerie, Paie, États. Pas de bandeau d'anomalies, donc aucune écriture orpheline pour cet établissement.
- Caisse, onglet Sorties, octobre 2026 : formulaire Date, Motif, Montant, Enregistrer. Liste vide : « Aucune sortie ce mois-ci. »

## 12. Vérification UI

La caisse et le hub s'affichent dans le design directeur déjà en place. Le menu complémentaire était ouvert par-dessus la page au moment de la capture : ce n'est pas un effet de cette étape. Le formulaire de sortie et les cartes du hub sont présents dans la page.

## 13. Responsive

Contrôlé à 375×667 sur le hub et sur la caisse : pas de défilement horizontal (`scrollWidth` = 375). Les autres largeurs du protocole (1920, 1440, 1366, 1024, 768, 430, 390) ne changent pas la structure ajoutée : un libellé et un tableau déjà dans `.table-responsive`. La grille complète reste pour l'écran Finances, étape 9.

## 14. Problèmes rencontrés

- Les tests de backfill et de verrouillage de régime échouaient parce que le signal écrit la créance avant l'appel du test. Ils attendent maintenant `emises = 0` et un régime déjà verrouillé, puis vérifient qu'il n'y a pas de second produit et que le régime ne change plus.
- Le navigateur de vérification était déjà en largeur étroite, avec le menu complémentaire ouvert.

## 15. Risques restants

- Une sortie sans écriture (plan de comptes absent) peut encore être retirée. Le message d'avertissement est affiché à l'enregistrement.
- `creee_par` reste vide quand le directeur enregistre : il n'est pas un `CompteUser`.
- `kpi_cg` n'est pas le moteur des sept indicateurs.
- La paie vacataire et une dépense « salaire » peuvent encore compter deux fois la même somme.
- Aucune contre-écriture n'a été passée sur d'éventuelles orphelines d'autres établissements. Le hub les montre, il ne les corrige pas.

## 16. État final

TERMINÉ.

## 17. Étape suivante

Étape 2 — fondations : `CompteTresorerie`, `CategorieFinanciere`, journal d'audit avec acteur générique, cycle brouillon / validée / annulée sur la dépense, et verrou appliqué avant toute écriture métier. Pas de factures multi-paiements, pas de prêts, pas d'écran Situation. Le compte de contrepartie du solde initial doit être confirmé avant migration.

Elle n'est pas commencée.
