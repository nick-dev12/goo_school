# Plan d’implémentation — module Finances

Base de travail : `audit_finances_aria.md`, `brief_architecture_finances.md`, et le code réel de `school_admin`.

Ce plan ne code pas le module. Chaque étape est indépendante. L’étape suivante ne démarre qu’après un message « GO ÉTAPE X ».

Priorité : correctitude, sécurité, cohérence des données, tests, UX, performance, rapidité.

---

## Protocole de chaque étape

1. Auditer le code réel.
2. Planifier uniquement cette étape.
3. Implémenter uniquement cette étape.
4. Tester.
5. Vérifier le fonctionnement.
6. Vérifier l’interface si l’étape en a une.
7. Vérifier le responsive si l’étape concerne l’UI.
8. Corriger les problèmes trouvés.
9. Relancer les tests.
10. Produire le rapport au format imposé.
11. S’arrêter.

Interdit pendant une étape : inventer un modèle, une URL, une permission, un champ ou une fonction ; supposer qu’une fonctionnalité existe ou n’existe pas ; créer un second système ; appeler `EcritureComptable.objects.create()` ou `LigneEcriture.objects.create()` depuis Finances.

Porte unique des écritures : `school_admin/services/comptabilite_generale.py`, fonction `creer_ecriture`.

Aucune suppression de données, aucune migration destructive, aucun recalcul silencieux des écritures déjà passées. Si une étape exige une décision métier ou une modification de données, elle s’arrête et le signale.

Une régression sur l’existant arrête l’étape. On corrige avant tout rapport « terminé ».

---

## Architecture imposée

```
INTERFACE FINANCES
        ↓
services/finances/
        ↓
services/comptabilite_generale.py  (creer_ecriture et ponts)
        ↓
EcritureComptable + LigneEcriture
```

Hors périmètre de toutes les étapes : recréer `PaiementEleve`, les créances, les reçus, les impayés, les moratoires ; fusionner `Depense` (plateforme Aria, `depense_model.py`) avec `DepenseEtablissement`.

Constat déjà vérifié dans le code, à ne pas réouvrir sans nouvel audit :

- La partie double existe (`creer_ecriture` refuse une pièce déséquilibrée, un exercice clôturé et une période verrouillée).
- `AUTH_USER_MODEL` est `CompteUser` (équipe Aria). Le directeur est un `Etablissement`, le caissier un `PersonnelAdministratif`. `EcritureComptable.creee_par` ne peut pas les stocker.
- `kpi_cg` et `solde_mois` (`services/caisse.py`) ne sont pas les sept indicateurs. On ne les additionne pas aux futures métriques.
- `FactureFournisseur.montant_paye` n’est alimenté par aucun écran.
- `supprimer_depense_directeur` efface la dépense et laisse l’écriture.
- Les vues `cg_*` exigent seulement `comptabilite_voir`. Le caissier possède cette clé.
- Les comptes `1621`, `6711` et `6712` ne sont pas dans `PLAN_SYSCOHADA_EDUCATION`.

---

## Étape 0 — Préparation et sécurisation du développement

Objectif : figer ce plan et mesurer l’état des tests financiers déjà présents. Aucun modèle, aucune migration, aucun écran.

Fichiers autorisés : ce plan et le rapport d’étape.

Tests de référence, sans les modifier :

- `school_admin.tests_comptabilite_generale`
- `school_admin.tests_caisse`
- `school_admin.tests_frais_annexes`
- `school_admin.tests_recouvrement`

Critère de sortie : le plan est écrit, les quatre suites ont été lancées, le rapport indique PASS ou FAIL. Pas de correctif fonctionnel dans cette étape. Un FAIL est documenté et bloque l’étape 1 tant qu’il n’est pas compris.

## Étape 1 — Sécurisation de l’existant financier

Objectif : fermer les trous déjà constatés, sans nouveau module Finances.

Périmètre prévu, à reconfirmer par audit au moment du GO :

- Les vues `cg_*` ne s’ouvrent plus avec la seule clé `comptabilite_voir` du caissier. Contrôle serveur.
- `supprimer_depense_directeur` n’efface plus une dépense qui a déjà une écriture `source=depense`.
- `pont_depense` ne masque plus une erreur comptable par `except Exception: pass`.
- Rapport d’anomalies en lecture seule : écritures `source=depense` dont la `DepenseEtablissement` n’existe plus. Aucune contre-écriture automatique.

Hors périmètre : nouveaux modèles, écran Finances, modification de `PaiementEleve`.

## Étape 2 — Fondations financières

Objectif : le socle réutilisé par les étapes suivantes.

Périmètre prévu, après nouvel audit :

- `CompteTresorerie` relié à un `CompteComptable` (caisse, banque, mobile money, autre). Solde calculé sur les écritures.
- `CategorieFinanciere` par établissement, avec parent optionnel et compte du plan. Pas un catalogue figé dans le code.
- `JournalAuditFinancier` avec acteur générique (le directeur n’est pas un `CompteUser`).
- Cycle brouillon / validée / annulée sur `DepenseEtablissement`.
- `services/finances/operations.py` : verrou de période avant toute écriture métier, annulation avec motif, appel des ponts existants.
- Pièces `PieceFinanciere` seulement si le stockage `FileField` du projet est réutilisé tel quel.

Hors périmètre : factures multi-paiements, transferts multi-comptes, recettes, prêts, écran Situation.

Le solde initial n’est pas une colonne modifiable après la première écriture. S’il faut une pièce d’ouverture, la décision du compte de contrepartie (`471` ou un autre compte déjà au plan) est signalée avant migration.

## Étape 3 — Factures, charges, paiements

Objectif : une facture, plusieurs `PaiementCharge`, un reste calculé.

`FactureFournisseur.montant_paye` n’est plus un champ de saisie. Les factures historiques dont ce montant est déjà positif sont signalées, pas converties automatiquement.

Une dépense immédiate sans facture reste une `DepenseEtablissement`. Un paiement de facture n’en crée pas une seconde. Le service refuse le doublon fournisseur + montant + jour lorsqu’une facture ouverte correspond.

Écritures uniquement via les ponts de `comptabilite_generale.py`. Régime engagement et régime trésorerie produisent des pièces différentes. Le choix est relu dans `ParametresComptabilite.regime_comptable` au moment du GO, pas supposé.

## Étape 4 — Trésorerie, comptes, transferts

Objectif : caisse → banque, banque → caisse, banque A → banque B, compte → mobile money.

`MouvementTresorerie` est étendu (source, destination, référence, motif, statut). Les virements déjà en base sont rattachés aux comptes nommés créés à l’étape 2. Les écritures historiques ne sont pas rejouées.

Pièce : débit du compte d’arrivée, crédit du compte de départ. Aucun produit, aucune charge.

## Étape 5 — Recettes complémentaires

Objectif : activité, subvention, divers dans `RecetteEtablissement`.

La scolarité reste `PaiementEleve`, en lecture seule, avec lien vers le dossier et le reçu. Aucune recette n’est créée pour un paiement élève.

Destination de subvention : fonctionnement, équipement, projet, autre. Le mot équipement ne retire rien du résultat à lui seul. Le rapport montre la destination à côté du résultat des classes 6 et 7.

`RemboursementOperation` : le paiement d’origine reste. Net = origine − remboursements validés.

## Étape 6 — Prêts et remboursements

Objectif : `PretEtablissement`, `EcheancePret`, `RemboursementPret`.

Réception : débit trésorerie, crédit dette. Remboursement : débit dette pour le capital, débit charges pour intérêts et frais, crédit trésorerie pour le total. Capital restant ≥ 0, contrôlé dans la transaction.

Les comptes `1621`, `6711` et `6712` n’existent pas aujourd’hui. Ils sont ajoutés au plan par `ensure_plan_comptable` dans cette étape seulement, après accord explicite dans le GO. Pas de numéros inventés au milieu d’une autre étape.

## Étape 7 — Rapprochement bancaire

Objectif : `ReleveBancaire` et `LigneReleve`.

Affichage : solde Aria, solde du relevé, écart, lignes non pointées. Une ligne pointée ne se modifie plus en silence. Le booléen `MouvementTresorerie.pointe` actuel est audité avant de décider s’il est conservé ou seulement lu.

## Étape 8 — Moteur des métriques

Objectif : `services/finances/metrics.py`, source unique de Disponible, Encaissé, Payé, Résultat, Créances, Dettes, Engagements.

Chaque indicateur documente définition, source, formule, période, établissement, année ou exercice, régime, inclus, exclus. Créances émises et encaissements ne s’additionnent pas. `kpi_cg` n’est pas branché sur ce moteur.

## Étape 9 — Interface Finances

Objectif : une entrée Finances, onglets Situation, Entrées, Sorties, Trésorerie, Financements.

Filtres en formulaire GET. Formulaires POST Django. JavaScript limité à l’affichage. Design Aria existant, aplats, pas de second design system. Vert, bleu, ambre, rouge, violet, gris avec le sens déjà fixé. Une dépense validée n’est pas rouge.

Responsive à contrôler : 1920, 1440, 1366, 1024, 768, 430, 390, 375.

## Étape 10 — Tests finaux, responsive, performance, audit

Objectif : les 17 scénarios financiers, l’isolation par établissement, les requêtes ORM, les largeurs d’écran, et le rapport d’anomalies des écritures orphelines.

Pas de Redis. Pas de nouvelle fonctionnalité.

---

## Tests de non-régression à relancer dès qu’une étape touche la scolarité ou la caisse

- `school_admin.tests_comptabilite_generale`
- `school_admin.tests_caisse`
- `school_admin.tests_frais_annexes`
- `school_admin.tests_recouvrement`

Commande : `env\Scripts\python.exe -m django test` avec ces modules, depuis la racine du projet.

---

## Format du rapport de fin d’étape

```
# RAPPORT ÉTAPE X

## 1. Objectif
## 2. Fichiers modifiés
## 3. Fichiers créés
## 4. Modèles modifiés
## 5. Migrations
## 6. Services
## 7. URLs / Views
## 8. Templates / CSS / JS
## 9. Tests exécutés
## 10. Résultat des tests
## 11. Tests manuels
## 12. Vérification UI
## 13. Responsive
## 14. Problèmes rencontrés
## 15. Risques restants
## 16. État final
## 17. Étape suivante
```

L’étape suivante est décrite, jamais implémentée dans le même rapport.
