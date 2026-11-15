# Brief — architecture technique du module Finances

L'audit est maintenant considéré comme la base de travail.

IMPORTANT : ne pas commencer encore l'implémentation complète.

L'objectif de cette étape est de transformer l'audit en architecture technique définitive, vérifiable et sans ambiguïté, avant de créer massivement des modèles et des migrations.

---

## 1. Objectif

Construire un module **Finances** : une interface de gestion financière simple pour le personnel de l'établissement, qui utilise la comptabilité générale déjà existante.

```
INTERFACE FINANCES
        ↓
SERVICES MÉTIER FINANCES
        ↓
MOTEUR COMPTABILITÉ GÉNÉRALE EXISTANT
        ↓
ECRITURES COMPTABLES
```

Le module Finances ne doit jamais créer directement des `EcritureComptable` / `LigneEcriture` avec des `.objects.create()`.

Une seule porte d'entrée doit exister pour générer les écritures comptables.

---

## 2. Ce qui est confirmé par l'audit

L'application possède déjà :

- comptabilité en partie double
- `EcritureComptable`
- `LigneEcriture`
- `CompteComptable`
- `JournalComptable`
- `ExerciceComptable`
- `PeriodeComptable`
- régime engagement / trésorerie
- `PaiementEleve`
- créances
- reçus
- impayés
- moratoires
- `DepenseEtablissement`
- `FactureFournisseur`
- `MouvementTresorerie`

Ne pas créer de deuxième système comptable.

Ne pas recréer le paiement scolaire.

Ne pas recréer les créances.

Ne pas fusionner les dépenses de la société Aria avec les dépenses de l'établissement.

---

## 3. Architecture à proposer

Proposer une architecture claire autour de `services/finances/`, avec au minimum, si réellement nécessaire :

- `dashboard.py`
- `metrics.py`
- `tresorerie.py`
- `recettes.py`
- `depenses.py`
- `charges.py`
- `transferts.py`
- `remboursements.py`
- `financements.py`
- `rapprochement.py`
- `rapports.py`

Ne pas créer des fichiers uniquement pour respecter cette liste.

Justifier chaque service.

---

## 4. Moteur des indicateurs

Créer une couche centralisée de métriques financières.

Elle doit être la source officielle pour :

- dashboard
- rapports
- exports
- éventuellement assistant IA futur

Indicateurs minimum :

1. Disponible
2. Encaissé
3. Payé
4. Résultat selon le régime comptable
5. Créances
6. Dettes
7. Engagements

Pour chaque indicateur, documenter :

- définition
- source
- formule
- période
- établissement
- année / exercice
- régime comptable
- opérations incluses
- opérations exclues

Ne jamais additionner naïvement créances émises + encaissements. Cela créerait un double comptage en régime engagement.

---

## 5. Modèles à valider

Avant création, vérifier une dernière fois que ces concepts n'existent pas déjà.

### CompteTresorerie

Permettre :

- caisse principale
- plusieurs banques
- Mobile Money
- autres comptes si nécessaire

Relations : `Etablissement` → `CompteTresorerie` → `CompteComptable`.

Le solde est calculé à partir des écritures / opérations.

### CategorieFinanciere

Catégories configurables.

Prévoir :

- type
- libellé
- actif
- établissement
- éventuellement parent

Ne pas coder toutes les catégories en dur.

### PaiementCharge

Une facture peut avoir 1, 2, 3 paiements, etc.

Exemple :

- facture 450 000
- paiement 300 000
- paiement 100 000
- paiement 50 000
- reste = 0

Le champ historique `FactureFournisseur.montant_paye` ne doit pas devenir un deuxième endroit de saisie.

Déterminer comment le rendre calculé ou non modifiable.

### RecetteEtablissement

Uniquement pour les recettes qui ne sont pas déjà dans `PaiementEleve`.

Exemples : activité, subvention, divers.

Une recette doit posséder une catégorie et une destination si nécessaire.

### PretEtablissement

Prévoir :

- établissement
- banque
- référence
- date
- montant
- taux
- durée
- objet
- compte crédité
- statut
- échéancier

### RemboursementPret

Séparer capital, intérêts et frais.

Le capital diminue la dette. Les intérêts et les frais sont des charges.

### RemboursementOperation

Permettre :

- paiement initial 300 000
- remboursement 50 000
- net 250 000

Ne jamais supprimer le paiement original.

### LigneReleve

Prévoir un vrai rapprochement :

```
Relevé → Ligne → Opération Aria → Pointage → Écart
```

### PieceFinanciere

Permettre les justificatifs associés à :

- dépenses
- factures
- recettes
- remboursements
- prêts
- autres opérations si nécessaire

Respecter le stockage existant du projet.

### JournalAuditFinancier

Prévoir une traçabilité des actions sensibles :

- création
- modification
- validation
- annulation
- remboursement
- rapprochement
- clôture
- correction

Conserver au minimum :

- utilisateur
- date
- objet
- action
- ancienne valeur si pertinente
- nouvelle valeur si pertinente
- motif si nécessaire

---

## 6. Annulation et suppression

Une opération validée ne peut plus être supprimée.

```
BROUILLON → VALIDÉE → ANNULÉE
```

Une annulation :

- conserve l'opération
- conserve son auteur
- conserve sa date
- exige un motif
- génère la correction comptable appropriée
- exclut l'opération des totaux actifs

Aucune suppression physique après validation.

---

## 7. Périodes verrouillées

Le verrou actuel doit protéger toutes les opérations financières, pas uniquement `creer_ecriture()`.

Tester notamment :

- dépense
- facture
- paiement
- recette
- transfert
- remboursement
- prêt
- rapprochement

Après clôture : aucune modification normale.

Correction : contre-écriture + date actuelle + motif + référence de l'opération originale + permission appropriée.

---

## 8. Permissions

Ne pas créer un rôle Auditeur. Utiliser les rôles existants.

Matrice pour : Caissier, Comptable, Gestionnaire, Intendant, Direction.

Créer des permissions spécifiques si nécessaire :

- `finances_voir`
- `finances_saisir`
- `finances_valider`
- `finances_annuler`
- `finances_rapprocher`
- `finances_cloturer`
- `finances_exporter`

Réutiliser les permissions existantes lorsque possible.

Le contrôle doit être côté serveur.

---

## 9. Scolarité

`PaiementEleve` reste la source.

Finances → Entrées → Scolarité : lecture seule, statistiques, lien vers le dossier élève / reçu.

Aucune `RecetteEtablissement` créée pour un `PaiementEleve`.

---

## 10. Dépenses et factures

Flux :

```
FACTURE → PaiementCharge → EcritureComptable
```

Empêcher qu'un même paiement soit également enregistré comme `DepenseEtablissement`.

Si une `DepenseEtablissement` représente une dépense immédiate sans facture, elle reste possible.

Le système doit empêcher les doublons lorsque la même opération est liée à une facture.

Proposer une règle d'unicité ou une stratégie de liaison.

---

## 11. Trésorerie

Permettre :

- caisse → banque
- banque → caisse
- banque A → banque B
- compte → Mobile Money

Chaque transfert a : compte source, compte destination, montant, date, référence, motif, statut.

Écriture : débit compte destination, crédit compte source. Aucun produit. Aucune charge.

---

## 12. Prêts

Réception : débit trésorerie, crédit dette.

Remboursement : débit dette = capital, débit charge financière = intérêts + frais, crédit trésorerie = total payé.

Le système doit vérifier : capital restant ≥ 0.

---

## 13. Subventions

Ne pas coder « équipement = toujours hors résultat ».

Stocker : destination = fonctionnement / équipement / projet / autre.

Documenter comment le rapport utilise cette information.

---

## 14. Rapports

Prévoir :

- situation financière
- recettes
- dépenses
- trésorerie
- caisse
- banques
- rapprochement
- créances
- dettes
- engagements
- prêts
- remboursements

Chaque rapport doit clairement préciser ce qu'il mesure.

---

## 15. UI / UX

Entrée principale : **Finances**.

Onglets : Situation, Entrées, Sorties, Trésorerie, Financements.

Interface : premium, moderne, élégante, très claire, professionnelle, responsive, sans dégradé, sans surcharge.

Couleurs :

- vert = validé / payé / positif
- bleu = information / transfert
- ambre = attente / partiel
- rouge = anomalie / retard / découvert
- violet = dette / financement
- gris = annulé / historique

Une dépense normale ne doit jamais être rouge uniquement parce qu'elle est une sortie d'argent.

---

## 16. Design Situation

Interface inspirée du dashboard Aria existant.

Filtres en haut : année, période, établissement, compte, catégorie.

Puis KPI : Disponible, Encaissé, Payé, Résultat, Créances, Dettes, Engagements.

Puis : évolution financière, répartition recettes, répartition dépenses, trésorerie, impayés, échéances, alertes.

Chaque carte doit permettre un drill-down.

---

## 17. Responsive

Largeurs : 1920, 1440, 1366, 1024, 768, 430, 390, 375.

Sur mobile :

- cartes empilées
- filtres adaptatifs
- tableaux scrollables
- boutons accessibles
- onglets scrollables horizontalement
- graphiques redimensionnés
- aucun overflow involontaire

---

## 18. Performance

Utiliser `select_related`, `prefetch_related`, `annotate`, `aggregate`.

Éviter : N+1, boucles ORM inutiles, calculs dans les templates, duplication des agrégats.

Ne pas ajouter Redis avant mesure réelle.

---

## 19. Migration des données

Aucune suppression. Aucun recalcul silencieux.

Avant migration, produire : données concernées, nombre d'enregistrements, risque, stratégie, rollback.

Pour les anciennes dépenses supprimées dont l'écriture existe encore : créer uniquement un rapport d'anomalies. Ne pas passer automatiquement une contre-écriture.

---

## 20. Tests avant codage

Définir les tests unitaires et d'intégration pour :

1. paiement scolaire
2. dépense
3. facture partiellement payée
4. facture entièrement payée
5. transfert
6. prêt
7. remboursement prêt
8. remboursement opération
9. annulation
10. période verrouillée
11. permissions
12. rapprochement
13. multi-banques
14. régime engagement
15. régime trésorerie
16. double comptabilisation
17. isolation établissement

---

## 21. Livrable de cette étape

Ne pas coder encore.

Fournir uniquement :

- A. Architecture finale
- B. Diagramme des relations
- C. Liste des modèles à créer
- D. Liste des modèles à modifier
- E. Champs de chaque modèle
- F. Relations
- G. Contraintes d'intégrité
- H. Services
- I. Flux financiers
- J. Permissions
- K. Règles métier
- L. Stratégie migration
- M. Stratégie tests
- N. Architecture UI
- O. Risques restants
- P. Ordre exact d'implémentation

Pour chaque décision importante, expliquer pourquoi.

Si une contradiction ou un risque supplémentaire apparaît dans le code réel, le signaler avant de proposer l'implémentation.

Ne créer aucun fichier de code. Ne créer aucune migration. Ne modifier aucune donnée. Ne modifier aucun modèle pour l'instant.

Cette étape doit aboutir à une architecture définitive validable avant développement.
