# Audit financier Aria — diagnostic avant codage

Date : 2026-10-03. Aucun modèle, aucune migration et aucun écran n’ont été modifiés.
Sources lues : cahier des charges CRUD, plan `plan_finances_etablissement.md`, code de `school_admin`.

Une seule application Django métier : `school_admin`. L’établissement est le compte directeur (`Etablissement`). Le personnel passe par `PersonnelAdministratif.fonction`. L’argent de l’école et l’argent de la société Aria sont deux registres distincts.

---

## 1. Architecture financière actuelle

Trois couches coexistent. Elles ne forment pas encore un seul écran Finances.

| Couche | Rôle réel | Où c’est branché |
|---|---|---|
| Scolarité | Créances, encaissements, reçus, impayés, moratoires | `comptabilite_eleve_model.py`, `comptabilite_controller.py`, `recouvrement_controller.py` |
| Caisse école | Dépense du jour, supprimée physiquement | `DepenseEtablissement`, `caisse_controller.py` |
| Comptabilité générale | Partie double, plan, journaux, exercice, virement caisse → banque | `comptabilite_generale_model.py`, `services/comptabilite_generale.py` |
| Société Aria | Dépenses de la plateforme, avec pièce jointe | `Depense` dans `depense_model.py`, `comptable_view.py` |

La partie double existe. Ce n’est pas un projet. `creer_ecriture` refuse une pièce dont le débit n’est pas égal au crédit, refuse un exercice clôturé et refuse une période verrouillée (`services/comptabilite_generale.py`).

Les ponts réellement appelés :

| Opération | Écriture | Appel |
|---|---|---|
| Créance élève, régime engagement | Débit 411 / crédit 7051, 7052 ou 7061 | signal `comptabilite_signals.py` |
| Encaissement élève, engagement | Débit 571, 521 ou 585 / crédit 411 | `comptabilite_controller.py` |
| Encaissement élève, trésorerie | Débit 571, 521 ou 585 / crédit 70x | même pont, autre contrepartie |
| Dépense école | Débit 6xx / crédit 571 | `caisse_controller.py` |
| Paie vacataire | Débit 637 / crédit 571, sur le net seulement | service `pont_paie` |
| Virement | Débit 521 / crédit 571 | écran Trésorerie |
| Dotation | Débit 681 / crédit 2813 | écran Fournisseurs, action manuelle |

Le régime est sur `ParametresComptabilite.regime_comptable` : `engagement` par défaut, ou `tresorerie`. Le changement est bloqué dès qu’une écriture existe sur l’exercice civil ouvert.

Le plan ensemencé est le SYSCOHADA révisé : 571 caisse, 521 banque, 585 mobile money, 411 familles, 7051 / 7052 / 7061 produits. Une table `REMAP_PCE` renomme d’anciens numéros (512 → 521, 531 → 571, 701 → 7051). Le plan précédent qui parlait encore de 512 et 531 comme numéros vivants est dépassé par ce code.

Ce qui n’existe pas : prêt, remboursement de prêt, compte bancaire nommé, relevé bancaire, pièce jointe sur une opération d’école, annulation tracée, journal d’audit, catégorie configurable, remboursement d’un parent.

---

## 2. Modèles existants

### Scolarité — à lire, pas à recopier

- `ComptabiliteEleve` : dossier annuel, statut `a_jour` / `en_retard` / `impaye`.
- `FraisInscription`, `Mensualite`, `FraisAnnexe` : dû, payé, reste, échéance.
- `PaiementEleve` : montant, type, mode (`especes`, `cheque`, `virement`, `mobile_money`, `carte`), référence, `numero_recu` unique par établissement, `date_paiement`, `enregistre_par`.
- `RelanceImpaye`, `Moratoire`, `EcheanceMoratoire`.
- `ParametresComptabilite` et barème par groupe de classes.

### Comptabilité générale

- `CompteComptable` : plan par établissement, numéro unique.
- `JournalComptable` : CAI, BAN, ACH, SCO, OD, PAI.
- `ExerciceComptable` : ouvert / clôturé, lien optionnel vers `AnneeScolaire`, alignement civil par défaut.
- `PeriodeComptable` : mois, trimestre, semestre, booléen `verrouillee`.
- `EcritureComptable` + `LigneEcriture` : débit, crédit, `source` + `source_id`, `validee` (vrai par défaut).
- `FournisseurEtablissement`.
- `FactureFournisseur` : montant, `montant_paye`, échéance, statut `a_payer` / `partiel` / `payee`. Aucun paiement fils. Aucun code ne met `montant_paye` à jour. Aucune écriture 401 à la création.
- `Immobilisation` : valeur, durée, dotation linéaire.
- `MouvementTresorerie` : `virement_interne` ou `rapprochement`, montant, `pointe`, date de pointage. Pas de compte source ni de compte destination. Le pont force toujours caisse → banque.

### Caisse école

`DepenseEtablissement` : date, motif figé (salaire, loyer, électricité, fournitures, carburant, autre), libellé, montant, année scolaire. Pas de statut, pas de pièce, pas de fournisseur, pas de compte de trésorerie. `supprimer_depense_directeur` fait un `delete()` réel. L’écriture déjà passée reste dans le grand livre.

### Hors périmètre école

`Depense` (`depense_model.py`) sert la gestion comptable de la plateforme. Pièce jointe, statuts d’approbation, établissement facultatif. Ce n’est pas la caisse de l’école.

### Audit réel des écritures

`EcritureComptable` a `date_creation` et `creee_par`. `creee_par` n’est rempli que si l’utilisateur est un `CompteUser`. Le directeur est un `Etablissement` : `_user()` renvoie alors `None`. Pas de `updated_by`, pas de motif d’annulation, pas d’ancienne valeur, pas de table d’audit.

---

## 3. Modèles à créer

Pas tous d’un coup. Seulement ce qui n’a aucun équivalent.

| Modèle | Pourquoi il n’existe pas déjà |
|---|---|
| `CompteTresorerie` | 571 / 521 / 585 sont des comptes du plan, pas des caisses nommées avec solde de départ et date d’ouverture. Une école avec deux banques ne peut pas les distinguer. |
| `PaiementCharge` | La facture fournisseur n’a qu’un total payé, sans lignes de paiement. |
| `RecetteEtablissement` | Activité, subvention, divers : aucune table. |
| `PretEtablissement` et `RemboursementPret` | Aucune table. Le capital, les intérêts et les frais n’ont pas de comptes dédiés dans le plan ensemencé (pas de 16, pas de 671). |
| `RemboursementOperation` | Aucun flux « on rend 50 000 sur un encaissement de 300 000 » sans effacer le paiement. Le compte 419 existe dans le plan et n’est jamais mouvementé. |
| `LigneReleve` | Le pointage actuel est un booléen sur le virement, pas un relevé. |
| `PieceFinanciere` | Aucun fichier sur `DepenseEtablissement`, `PaiementEleve` ou `FactureFournisseur`. |
| `CategorieFinanciere` | Les motifs de dépense sont un choix figé dans le modèle. |
| `JournalAuditFinancier` | Aucune trace des anciennes valeurs. |

---

## 4. Modèles à modifier

| Modèle | Modification |
|---|---|
| `DepenseEtablissement` | Statut, motif d’annulation, auteur, date. Lien optionnel vers une facture. Interdire le `delete()` d’une ligne déjà écrite. |
| `FactureFournisseur` | Catégorie, destination, lien vers les paiements. Ne plus se contenter d’un `montant_paye` saisi à la main. |
| `MouvementTresorerie` | Sens et deux `CompteTresorerie`. Aujourd’hui un seul sens est possible. |
| `EcritureComptable` | Lien vers l’écriture d’origine pour la contre-écriture. Ne pas ajouter un deuxième grand livre. |
| `PeriodeComptable` | Le verrou existe. Il ne protège que `creer_ecriture`. La suppression de dépense et la saisie de facture passent à côté. |
| `ParametresComptabilite` | Déjà le régime et l’alignement d’exercice. Y ajouter plus tard la règle de rapport des subventions, pas un booléen universel « équipement = hors résultat ». |

On ne modifie pas le calcul des reçus, des impayés ni des moratoires.

---

## 5. Relations

```
Etablissement
  ├── AnneeScolaire
  ├── ParametresComptabilite (régime)
  ├── ComptabiliteEleve → FraisInscription / Mensualite / FraisAnnexe
  │       └── PaiementEleve ──source──► EcritureComptable
  ├── DepenseEtablissement ──source──► EcritureComptable
  ├── FactureFournisseur → (paiements à créer) ──source──► EcritureComptable
  ├── CompteTresorerie → CompteComptable (571, 521 ou 585)
  ├── MouvementTresorerie (de compte, vers compte) ──source──► EcritureComptable
  ├── RecetteEtablissement ──source──► EcritureComptable
  ├── PretEtablissement → RemboursementPret ──source──► EcritureComptable
  └── ExerciceComptable → PeriodeComptable
            └── EcritureComptable → LigneEcriture → CompteComptable
```

Règle de lien : une opération métier a au plus une écriture active (`source` + `source_id`, déjà utilisé). Une annulation ajoute une contre-écriture. Elle ne supprime pas la première.

`Depense` (plateforme) ne pointe pas vers `EcritureComptable`. On ne la raccorde pas.

---

## 6. Règles métier retenues après confrontation

1. Un versement caisse → banque est un transfert. Le pont actuel le fait déjà (débit 521 / crédit 571, aucun compte de classe 6 ou 7). L’écran Finances doit le classer en Trésorerie, pas en Entrées.
2. La scolarité se lit dans `PaiementEleve` et dans les créances. On ne crée pas une `RecetteEtablissement` pour un paiement déjà enregistré.
3. En régime engagement, le produit naît à la créance (crédit 70x), l’encaissement ne fait que solder le 411. Additionner « créances émises » et « encaissements » comme deux recettes double le chiffre.
4. En régime trésorerie, le produit naît à l’encaissement. Il n’y a pas d’émission 411.
5. Une facture a un prévu et plusieurs paiements. Le paiement ne crée pas une seconde `DepenseEtablissement`.
6. Un prêt augmente le compte de trésorerie et une dette. Il ne crédite pas un compte de produit. Le capital remboursé diminue la dette. Intérêts et frais sont des charges, sur des comptes à ajouter au plan (à valider : 162 / 671, ou subdivision choisie par l’établissement).
7. Une subvention garde une destination : fonctionnement, équipement, projet, autre. Aucune destination n’est codée « toujours hors résultat ». Le rapport applique la règle choisie dans les paramètres, et il indique laquelle.
8. Une opération validée s’annule : statut, motif, utilisateur, date. Elle sort des totaux actifs et reste dans la liste.
9. Une période verrouillée refuse la saisie et la modification. La correction est une contre-écriture datée du jour, avec lien vers la pièce d’origine.
10. Le solde d’un compte de trésorerie se calcule. Le solde initial se corrige par un ajustement, pas par une réécriture silencieuse.
11. Le rouge signale un retard, un découvert ou une anomalie. Une dépense validée n’est pas rouge.
12. Les indicateurs restent séparés : disponible (caisse + banques), encaissé, payé, résultat selon le régime, créances familles, dettes (fournisseurs + capital restant), engagements (prévu non payé).

---

## 7. Flux financiers

### Déjà en production

```
Barème / inscription
  → créance (inscription, mensualité, annexe)
  → si engagement : écriture SCO  D 411 / C 70x
  → encaissement caissier : reçu REC-…
  → écriture CAI ou BAN  D 571|521|585 / C 411 ou C 70x
  → statut élève, relance, moratoire
```

```
Dépense du jour
  → DepenseEtablissement
  → écriture CAI  D 6xx / C 571
  → une exception du pont est avalée : la dépense reste, l’écriture peut manquer
```

```
Virement
  → MouvementTresorerie
  → écriture OD  D 521 / C 571
```

### À ajouter sans second système

```
Facture fournisseur
  → paiement 1, paiement 2 sur la même facture
  → chaque paiement : D 401 ou D 6xx / C compte de trésorerie
  → pas une DepenseEtablissement en plus

Activité, subvention, divers
  → RecetteEtablissement
  → D compte de trésorerie / C 711 ou 758 selon la catégorie
  → la destination est conservée pour le rapport

Transfert
  → MouvementTresorerie entre deux CompteTresorerie
  → D compte arrivée / C compte départ
  → résultat inchangé

Prêt reçu
  → D compte de trésorerie / C dette
Remboursement
  → D dette (capital) + D charges (intérêts, frais) / C compte de trésorerie

Remboursement à une famille
  → le PaiementEleve d’origine reste
  → RemboursementOperation lié
  → net = paiement − remboursement
```

---

## 8. Permissions

Il n’y a pas de rôle Auditeur. On n’en crée pas. Les fonctions déjà là : `comptable`, `caissier`, `gestionnaire`, `intendant`, direction. Le directeur (`Etablissement`) passe `_require_compta` sans contrôle de permission.

Permissions actuelles :

| Clé | Caissier | Comptable | Gestionnaire | Intendant |
|---|---|---|---|---|
| `comptabilite_voir` | oui | oui | oui | non |
| `comptabilite_paiements` | oui | oui | oui | non |
| `comptabilite_bilans` | non | oui | oui | non |

Écart constaté : tous les écrans de comptabilité générale appellent `_require_compta` avec la clé par défaut `comptabilite_voir`. Le caissier a cette clé. Le middleware `CaissierAccessMiddleware` autorise tout `/dashboard/directeur/`. Le caissier peut donc ouvrir le plan, les fournisseurs, le virement et le pointage. Ce n’est pas le comportement demandé.

Clés à ajouter sur le dictionnaire existant, sans nouveau rôle :

| Clé | Caissier | Comptable | Gestionnaire | Directeur |
|---|---|---|---|---|
| Saisir une dépense ou un transfert autorisé | oui | oui | oui | oui |
| Annuler une pièce validée | non | oui | oui | oui |
| Pointer un relevé | non | oui | oui | oui |
| Clôturer une période | non | non | non | oui |
| Exporter | non | oui | oui | oui |

Le contrôle reste dans le contrôleur, pas seulement dans le menu.

---

## 9. Risques de double comptabilisation

| Risque | État dans le code |
|---|---|
| Compter l’encaissement élève une deuxième fois dans « autres recettes » | Pas encore d’écran autres recettes. À interdire dès la phase 4. |
| Additionner le produit d’engagement (crédit 70x à l’émission) et l’encaissement (débit 5) | Les deux écritures existent. Un tableau de bord naïf les additionnerait. |
| Virement compté comme recette | Le pont ne touche pas la classe 7. Le risque est dans un futur total « toutes les opérations ». |
| Facture fournisseur + dépense du jour pour la même facture | La facture n’écrit rien aujourd’hui. Le jour où elle écrira, le double apparaîtra si la dépense libre reste possible. |
| Paie vacataire + dépense motif salaire | Les deux peuvent créditer 571 pour le même versement. |
| Suppression de dépense | La caisse oublie le montant. L’écriture, elle, reste. Les deux totaux divergent. |
| `montant_paye` de facture saisi en plus d’un paiement | Le champ existe et n’est alimenté par personne. Ne pas le rendre saisissable. |

---

## 10. Stratégie de migration des données existantes

Aucune suppression. Aucun recalcul silencieux des écritures déjà validées.

1. Ajouter les champs nouveaux en nullable, avec défaut compatible : les dépenses actuelles deviennent « validées ».
2. Ne pas réécrire les `PaiementEleve` ni leurs écritures.
3. Créer un compte de trésorerie « Caisse principale » lié au 571 et un compte « Banque » lié au 521 pour chaque établissement qui a déjà un plan. Le solde initial reste 0 si l’historique des écritures porte déjà les mouvements. On ne saisit un solde initial que pour un compte ouvert sans historique.
4. Laisser `FactureFournisseur.montant_paye` tel quel. Les prochaines factures passent par `PaiementCharge`. Un rapport signale les factures dont `montant_paye` est déjà non nul.
5. Produire la liste des `EcritureComptable` de source `depense` dont la `DepenseEtablissement` n’existe plus. On ne les efface pas. Une contre-écriture ne sera passée qu’après validation, pièce par pièce.
6. Ne pas fusionner `Depense` (plateforme) avec la caisse école.

Pas de migration lourde tant que ce diagnostic n’est pas validé.

---

## 11. Architecture UI

Une entrée de menu Finances, à côté de la scolarité déjà dans la barre. Cinq onglets en liens (`?onglet=`), pour que le filtre survive à un rechargement :

1. Situation
2. Entrées — Scolarité (lecture + lien dossier), Activités, Subventions, Divers
3. Sorties — Dépenses, Charges, À payer, En retard
4. Trésorerie — Vue, Caisse, Banques, Transferts, Rapprochement
5. Financements — Prêts, Échéances, Remboursements

Le hub actuel `comptabilite-generale` (plan, journaux, exercices) reste l’écran du comptable. Il n’est pas recopié dans Finances. Un lien « Comptabilité » y mène.

Formulaires Django en POST. Le JavaScript ouvre, ferme et trie. Pas de dégradé. Couleurs déjà dans l’application : vert `#10b981`, bleu `#3b82f6`, ambre `#fbbf24`, rouge `#ef4444`, violet `#7c3aed`, gris `#6b7280`. Le rouge n’est pas la couleur d’une dépense normale. Variables CSS existantes, plus `--debt` pour le violet. Pas un second design system.

Listes : recherche, filtres, tri, total du filtre, Voir, Modifier si brouillon, Annuler si le droit le permet. Export après la phase 10. Mobile : scroll horizontal du tableau avec largeur minimale, comme les autres tableaux Aria.

---

## 12. Architecture services

Tout reste dans `school_admin`.

| Service | Droit | Interdit |
|---|---|---|
| `comptabilite_controller` | Créances et `PaiementEleve` | Écrire une ligne comptable à la main |
| `comptabilite_generale` | Seul à appeler `creer_ecriture` et la contre-écriture | Recalculer un reste élève |
| `recouvrement` | Impayés, relances, moratoires, reçus | Créer une recette parallèle |
| `caisse` | Dépense du jour | `delete()` d’une dépense écrite |
| Nouveau `finances` | Agrégats Situation, catégories, prêts, rapprochement | Dupliquer un `PaiementEleve` |

Les totaux de Situation viennent d’agrégats (`Sum`, `annotate`), pas de boucles dans le template. `select_related` sur établissement, compte, facture, élève.

Le `except Exception: pass` autour de `pont_depense` est un défaut : une dépense peut exister sans écriture. La correction affichera l’erreur au lieu de l’avaler. Elle ne fait pas partie de cet audit.

---

## 13. Stratégie de tests

`tests_comptabilite_generale.py` couvre déjà des ponts d’encaissement et le régime. On ne les réécrit pas. Les tests nouveaux visent le service `finances`, une fois les modèles ajoutés.

| Test | Attendu |
|---|---|
| 1. Paiement scolaire 500 000 | Visible dans Entrées / Scolarité. Aucune `RecetteEtablissement` créée. |
| 2. Virement 500 000 | Caisse −500 000, banque +500 000. Produits et charges inchangés. |
| 3. Dépense 100 000 | Charge +100 000, caisse −100 000, une seule fois. |
| 4 à 6. Facture 450 000, paiements 300 000 puis 100 000 puis 50 000 | Reste 150 000, puis 50 000, puis 0. Une seule facture. |
| 7. Prêt 5 000 000 | Banque +5 000 000, dette +5 000 000. Produits inchangés. |
| 8. Remboursement capital 200 000 + intérêts 30 000 | Dette −200 000. Charge financière +30 000. |
| 9. Annulation | Ligne conservée, motif, utilisateur, hors totaux. |
| 10. Paiement 300 000, remboursement 50 000 | Les deux lignes restent. Net 250 000. |
| 11. Période verrouillée | Saisie refusée. Contre-écriture acceptée seulement avec le droit et un motif. |
| 12. Droits | Caissier : pas d’annulation validée, pas de pointage. Comptable : annulation et pointage. Directeur : clôture. Intendant : pas d’accès. |

Scénario du cahier, avec ses propres montants, sans reprendre le solde banque de 7 100 000 : 5 000 000 + 1 500 000 − 500 000 = 6 000 000, et ce total ignore encore le prêt et le remboursement. Le test documente le reclassement (transfert, prêt, capital, intérêts) et échoue si l’un d’eux est rangé en recette ou en charge d’exploitation.

Les largeurs 1920, 1440, 1366, 1024, 768, 430, 390 et 375 se vérifient sur l’écran Finances au moment de l’interface, pas avant qu’elle existe.

---

## 14. Points du cahier des charges à corriger

| Point du cahier | Correction |
|---|---|
| Solde banque 7 100 000 | Incohérent avec 5 000 000 + 1 500 000 − 500 000. Le prêt et le remboursement sont absents de la formule. |
| Versement listé à côté des recettes | Transfert. |
| Recettes totales sans la scolarité, puis avec un versement « recettes scolaires » | La scolarité est déjà dans Aria. Le versement ne la recrée pas. |
| Charges = dépenses du jour + charges du mois payées | Double compte si le paiement du mois est aussi une dépense du jour. |
| Subvention équipement dans les recettes de l’exemple | Destination conservée. Le rapport dira si elle entre dans le résultat, selon le paramètre, pas selon une règle universelle. |
| Solde initial modifiable | Ajustement tracé après la première opération. |
| Suppression | Annulation. Le code actuel, lui, supprime encore la dépense. |
| Une seule date | Document, opération, échéance, paiement, validation, rapprochement et annulation restent des dates distinctes quand l’opération en a plusieurs. |

---

## 15. Points de l’analyse précédente à corriger

Le fichier `plan_finances_etablissement.md` reste une base utile. Ces points y sont inexacts ou trop raides une fois le code lu.

| Analyse précédente | Constat dans le code |
|---|---|
| La partie double est surtout un objectif derrière l’écran | Elle est en place et appelée à l’encaissement, à la dépense et au virement. |
| Les numéros vivants seraient encore 512 et 531 | Le plan ensemencé est 521, 571, 585. L’ancien numéro est remappé. |
| « Équipement = toujours hors résultat » | À retirer. On stocke la destination. La règle de rapport sera un paramètre, indiqué sur le rapport. |
| La banque et le rapprochement sont à créer de zéro | Un virement caisse → banque et un pointage booléen existent. Ils ne suffisent pas : pas de relevé, pas d’écart, pas de deuxième banque. |
| L’annulation est le comportement prévu | La dépense école est effacée. L’écriture comptable, non. |
| Un rôle Auditeur | Cette fonction n’existe pas. On n’en ajoute pas. |
| Quatre indicateurs suffisent | Il en faut sept : disponible, encaissé, payé, résultat selon le régime, créances, dettes, engagements. |
| Le caissier ne voit pas la banque | Avec `comptabilite_voir`, il ouvre aujourd’hui toute la comptabilité générale. |

---

## Ordre proposé, après validation

1. Permissions et fin du `delete()` de dépense, sans nouvel écran.
2. `CompteTresorerie`, catégories, statuts d’annulation.
3. Paiements de facture, sans seconde dépense.
4. Recettes autres, scolarité en lecture seule.
5. Transferts dans les deux sens, puis relevé et écart.
6. Prêts : capital, intérêts, frais.
7. Verrou de période sur toutes les saisies, contre-écriture.
8. Écran Situation, puis exports.
9. Interface Finances, puis contrôle des largeurs.

La phase 1 ne démarre pas tant que ce diagnostic n’est pas accepté. Aucune donnée existante ne sera supprimée.
