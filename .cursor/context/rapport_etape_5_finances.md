# RAPPORT ÉTAPE 5

## 1. Objectif

Enregistrer les recettes qui ne sont pas la scolarité : activité, subvention, divers. La scolarité reste dans `PaiementEleve`, en lecture seule. Une subvention garde sa destination (fonctionnement, équipement, projet, autre). Ce mot ne retire rien du résultat. Le montant entre dans le résultat des classes 6 et 7 seulement si le compte de la catégorie est en classe 7.

Un remboursement conserve la recette d'origine. Le net est le montant d'origine moins les remboursements encore validés.

## 2. Fichiers modifiés

- `school_admin/model/finances_model.py`
- `school_admin/model/__init__.py`
- `school_admin/services/finances/categories.py`
- `school_admin/services/finances/operations.py`
- `school_admin/services/comptabilite_generale.py`
- `school_admin/controllers/comptabilite_generale_controller.py`
- `school_admin/personal_views/directeur_view.py`
- `school_admin/personal_url/directeur_url.py`
- `school_admin/templates/school_admin/directeur/comptabilite_generale/hub.html`
- `school_admin/templates/school_admin/directeur/comptabilite_generale/partials/cg_subnav.html`
- `school_admin/static/school_admin/css/directeur/comptabilite_generale.css`

## 3. Fichiers créés

- `school_admin/services/finances/recettes.py`
- `school_admin/templates/school_admin/directeur/comptabilite_generale/recettes.html`
- `school_admin/migrations/0228_recettes_complementaires.py`
- `school_admin/tests_finances_recettes.py`
- `.cursor/context/rapport_etape_5_finances.md`

## 4. Modèles modifiés

- `RecetteEtablissement` : nature, destination, catégorie, compte de trésorerie, libellé, origine, référence, montant, statut. Le net ignore une recette annulée.
- `RemboursementOperation` : lié à la recette, sans la supprimer.
- Catégories de départ : Activité (7068), Subvention (711), Recette diverse (758). Elles restent modifiables.

## 5. Migrations

`0228_recettes_complementaires`. Création des deux tables. Aucune recette fabriquée pour les paiements élèves déjà en base. L'opération automatique sur les fonctions du personnel a été retirée.

## 6. Services

- `enregistrer_recette` : débit du compte encaissé, crédit du compte de la catégorie. Journal caisse ou banque. Période ouverte exigée.
- La destination n'est exigée que pour une subvention. Elle n'est pas lue pour choisir le compte.
- `enregistrer_remboursement` refuse un paiement élève et un montant supérieur au net.
- `annuler_recette` refuse tant qu'un remboursement validé existe. La ligne reste. Contre-écriture du jour.
- `paiements_scolarite` lit les paiements élèves et n'écrit rien.

## 7. URLs / Views

`comptabilite-generale/recettes/`, nom `cg_recettes`, réservée à `comptabilite_bilans`. POST : enregistrer, annuler, rembourser, annuler le remboursement.

## 8. Templates / CSS / JS

- Bandeau du résultat des classes 6 et 7, avec les destinations de subvention à côté, sans les soustraire.
- Formulaire de recette. La destination n'apparaît que si la nature est Subvention. L'envoi reste un POST Django.
- Tableau des recettes, remboursements et annulations avec motif.
- Scolarité en lecture seule, lien dossier et lien reçu.
- Aplats, pas de dégradé. Pastille verte en classe 7, ambre hors classe 7, grise si annulé, bleue si validé.
- CSS `?v=1.0.6`.

## 9. Tests exécutés

```
.\env\Scripts\python.exe manage.py test school_admin.tests_finances_recettes school_admin.tests_finances_transferts school_admin.tests_finances_charges school_admin.tests_finances_fondations school_admin.tests_comptabilite_generale school_admin.tests_caisse --keepdb
```

Puis, après le correctif du paiement élève de test :

```
.\env\Scripts\python.exe manage.py test school_admin.tests_finances_recettes --keepdb
```

## 10. Résultat des tests

PASS. 8 tests de recettes. Sur le passage d'ensemble, 54 tests étaient déjà verts ; le 55e échouait parce que le paiement de test était une mensualité sans échéance. Il est maintenant de type « autre ». Les 8 tests de recettes sont verts.

Couvert : activité en 7068 sans classe 6, subvention équipement qui reste en 711, compte 2184 hors résultat malgré la destination équipement, subvention sans destination refusée, remboursement 50 sur 300 (net 250, origine conservée), annulation qui ramène la caisse à 0, paiement élève sans recette créée, période verrouillée, autre école, justificatif PDF.

## 11. Tests manuels

Sur fleur de lune : recette Activité de 1 XOF encaissée en caisse. Le résultat des classes 6 et 7 passe de 0 à 1 (produits 1). La ligne est Validée, pastille Classe 7. Annulation avec le motif « Vérification technique, sans effet ». Le résultat revient à 0. La ligne reste, statut Annulée, net 0.

La destination s'affiche pour Subvention et se cache pour Activité.

La scolarité de l'année 2026-2027 n'a aucun paiement élève sur cette école : le tableau le dit, sans formulaire de saisie.

## 12. Vérification UI

La page Recettes montre le résultat, les trois catégories (7068, 711, 758), les trois comptes, le tableau et le bloc Scolarité. Le menu complémentaire était déjà ouvert.

## 13. Responsive

À 375 px, la page ne déborde pas (`scrollWidth` = 375). Les tableaux défilent dans leur cadre (1 200 px et 720 px de contenu dans 296 px visibles).

## 14. Problèmes rencontrés

- La migration automatique voulait réécrire les fonctions du personnel. Cette opération a été retirée.
- Le premier test de scolarité créait une mensualité sans échéance. Le type a été changé en « autre ».

## 15. Risques restants

- La recette de 1 XOF reste dans l'historique de fleur de lune, annulée. Les écritures se compensent.
- Une catégorie de subvention pointe encore sur 711. Changer ce compte est le seul moyen de sortir une subvention du résultat.
- Le remboursement d'un paiement élève n'est pas ouvert ici. La scolarité reste en lecture seule.
- `kpi_cg` n'est toujours pas le moteur des sept indicateurs.

## 16. État final

TERMINÉ.

## 17. Étape suivante

Étape 6 — prêts et remboursements : `PretEtablissement`, `EcheancePret`, `RemboursementPret`. Réception : débit trésorerie, crédit dette. Remboursement : capital en dette, intérêts et frais en charges, total en trésorerie. Les comptes 1621, 6711 et 6712 seront ajoutés au plan dans cette étape seulement.

Elle n'est pas commencée.
