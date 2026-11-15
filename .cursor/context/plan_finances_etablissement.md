# Finances de l’établissement — plan d’action

Plan pour le cahier des charges CRUD du module financier, recalé sur Aria.
Le personnel voit cinq questions simples. Le comptable retrouve, derrière, la partie double déjà commencée dans l’application.

Source : cahier des charges, 5 pages, exemples de septembre 2026.
Les chiffres sont repris tels quels, puis reclassés. Ce ne sont pas les comptes réels de l’école.

---

## 1. Lecture du cahier

Le cahier demande dix carnets séparés : dépenses du jour, charges du mois, activités, subventions, recettes exceptionnelles, versements, retraits, situation de banque, prêts, remboursements, plus un tableau de bord.

On garde : champs obligatoires, filtres, FCFA, pièce jointe, export PDF et Excel, annulation plutôt que l’effacement.

Le total de banque annoncé ne se vérifie pas. La règle du cahier est « solde initial + versements − retraits = 7 100 000 FCFA ». Avec les exemples du même document : 5 000 000 + 1 500 000 − 500 000 = 6 000 000. Le prêt de 20 000 000 et le remboursement de 610 000 n’entrent dans aucune formule. On ne reprend pas ce 7 100 000.

| Demande du cahier | Dans Aria aujourd’hui | Décision |
|---|---|---|
| Scolarité des familles | Déjà en place : créances, reçus, impayés, moratoires | On l’affiche. On ne la ressaisit pas. |
| Dépense du jour | Dépense d’établissement, écrite en comptabilité | On l’enrichit : pièce, statut, annulation |
| Charge du mois, prévu / payé / reste | Facture fournisseur, sans lien avec le paiement | Une charge, un ou plusieurs paiements |
| Activités, subventions, recettes diverses | Absent | À créer, trois natures bien séparées |
| Versement et retrait | Virement caisse vers banque seulement | À élargir, sans les compter comme recettes |
| Prêt et échéances | Absent | À créer : capital, intérêts et frais séparés |
| Tableau de bord | Indicateurs éparpillés | Un seul écran Situation |

La comptabilité société Aria (factures de la plateforme) reste en dehors de ce module. Ici, on parle uniquement de l’argent de l’établissement.

---

## 2. Ce qu’on corrige

Six règles pour que les totaux restent vrais.

1. **Un même billet ne se compte qu’une fois.** Verser la caisse à la banque déplace l’argent. Ce n’est pas une nouvelle entrée. Le versement apparaît dans Caisse et banque, pas dans Entrées.
2. **Payer l’électricité une seule fois.** Si la charge du mois et la dépense du jour décrivent le même paiement, la sortie est doublée. On paie la charge du mois. Ce paiement ne crée pas une deuxième dépense.
3. **La scolarité est déjà saisie à la caisse élèves.** La rajouter dans « autres recettes » doublerait les encaissements. Onglet Entrées : ligne Scolarité en lecture seule, avec un lien vers le dossier élève.
4. **L’argent emprunté n’est pas un gain.** Le prêt augmente la banque et la dette. Seuls les intérêts et les frais sont une sortie. Le capital remboursé baisse la dette. Il ne baisse pas le résultat du mois.
5. **Une subvention matériel n’est pas le bénéfice du mois.** L’exemple « appui équipement, 2 000 000 » financerait des tables ou un bus. À la saisie : choix Fonctionnement ou Équipement. Seul le fonctionnement entre dans le résultat.
6. **On annule, on n’efface pas.** Statut Annulée, motif obligatoire, nom de la personne. Le montant sort des totaux. La ligne reste visible.

### Septembre 2026, exemples du cahier reclassés

La scolarité de 1 500 000 est l’origine indiquée du versement bancaire : déjà encaissée, pas une recette nouvelle.

| Indicateur | Montant (FCFA) |
|---|---:|
| Entrées d’exploitation | 2 100 000 |
| Sorties d’exploitation | 615 000 |
| Résultat du mois | 1 485 000 |
| Hors résultat — équipement | 2 000 000 |

Entrées = scolarité 1 500 000 + activité 600 000.
Sorties = fournitures 75 000 + électricité payée 430 000 + intérêts et frais 110 000.

| Opération du cahier | Montant | Classement |
|---|---:|---|
| Scolarité déjà encaissée | 1 500 000 | Entrée, module élèves, pas de nouvelle saisie |
| Sortie pédagogique, 120 × 5 000 | 600 000 | Entrée — activité |
| Fournitures de bureau | 75 000 | Sortie du jour |
| Électricité payée (prévu 450 000) | 430 000 | Sortie du mois, une seule fois. Reste 20 000 |
| Intérêts 100 000 + frais 10 000 | 110 000 | Sortie — coût de l’emprunt |
| Capital remboursé | 500 000 | Dette, pas une sortie d’exploitation |
| Subvention appui équipement | 2 000 000 | Hors résultat du mois |
| Vente de matériel réformé | 350 000 | À qualifier : tout le prix seulement si le bien n’est pas à l’inventaire |
| Versement à la banque | 1 500 000 | Déplacement caisse vers banque |
| Prêt reçu, 36 mois, 7 % | 20 000 000 | Dette. Augmente la banque, pas les entrées |

### Mots de l’écran

Le plan de comptes ne s’affiche pas au caissier. Il sert au moment où l’opération est validée.

| Le comptable pense | L’écran dit |
|---|---|
| Produit d’exploitation | Entrée |
| Charge | Sortie |
| Virement interne caisse / banque | Versement à la banque |
| Emprunt | Argent emprunté |
| Intérêts | Coût de l’emprunt |
| Extourne | Annulation |
| Rapprochement bancaire | Pointage du relevé |
| Créance famille | Ce que la famille doit encore |

---

## 3. Écrans

Une seule entrée de menu : **Finances**. Cinq onglets.

Le filtre (mois, compte, statut, recherche) est un formulaire. Il reste dans l’adresse. Actualiser ne l’efface pas. L’enregistrement passe par le formulaire Django.

### Situation

Quatre chiffres du mois filtré. Aucune saisie ici : pour corriger un montant, on ouvre l’opération d’origine.

- **Entrées** — scolarité + activités + subventions de fonctionnement + divers
- **Sorties** — jour + mois payé + intérêts et frais d’emprunt
- **Résultat** — entrées moins sorties
- **Disponible** — caisse + banques

En dessous : reste à payer des charges du mois, capital d’emprunt restant, trois dernières opérations.

### Entrées

| Sous-onglet | Saisie | Contenu |
|---|---|---|
| Scolarité | Lecture seule | Total encaissé du mois, impayés, lien vers le dossier de l’élève |
| Activités | Formulaire | Date, nom, responsable, nombre, prix, total réellement encaissé, mode, compte |
| Subventions | Formulaire | Date, organisme, référence, objet, montant, compte, choix Fonctionnement ou Équipement |
| Divers | Formulaire | Date, libellé, origine, motif, montant, compte. La vente d’un bien de l’inventaire n’est pas une recette pleine |

Le total du bas n’additionne que les entrées d’exploitation. La subvention Équipement a sa propre somme, libellée « hors résultat ».

### Sorties

**Du jour.** Date, numéro de pièce, libellé, catégorie, bénéficiaire, mode, montant, justificatif, observation. Catégories : fournitures, fluides, loyer, transport, entretien, autre.

**Du mois.** Mois, libellé, fournisseur, échéance, montant prévu. Les paiements s’ajoutent sur la même fiche. L’écran montre Prévu, Payé, Reste. Reste en ambre tant qu’il reste quelque chose, vert à zéro.

Le caissier paie la fiche du mois. Il ne recrée pas une dépense du jour pour la même facture.

### Caisse et banque

Le solde de départ se saisit une seule fois. Ensuite il se calcule. Une erreur de départ se corrige par une ligne d’ajustement, datée et signée.

| Mouvement | Caisse | Banque | Dans le résultat |
|---|---|---|---|
| Encaissement espèces | Augmente | — | Oui, déjà à l’entrée |
| Versement à la banque | Diminue | Augmente | Non |
| Retrait | Augmente si le cash revient en caisse | Diminue | Non. La sortie est la facture |
| Paiement fournisseur par la banque | — | Diminue | Oui, via la sortie |
| Réception du prêt | — | Augmente | Non |
| Remboursement du capital | — | Diminue | Non |
| Intérêts et frais | — | Diminue | Oui |

Une ligne pointée sur le relevé n’est plus modifiable. On l’annule par une contre-écriture du jour, avec le motif.

### Emprunts

Une fiche par prêt : banque, référence, date, montant, taux, durée, objet, compte crédité. Chaque remboursement réel a trois cases : capital, intérêts, frais. Le total et le capital restant se calculent.

Exemple du cahier, échéance 1 : capital 500 000, intérêts 100 000, frais 10 000, total 610 000, reste dû 19 500 000. Le montant réellement payé prime sur la prévision.

### Couleurs

Aplats seulement. Pas de dégradé. Une couleur a le même sens partout.

| Couleur | Sens | Exemples |
|---|---|---|
| Vert | Encaissé, payé, pointé, résultat positif | Validée et encaissée, rapprochée |
| Rouge | Argent sorti, pièce annulée, découvert | Dépense, annulation |
| Ambre | Pas encore certain | Brouillon, à valider, payé en partie, reste à payer |
| Bleu | L’argent change de place | Versement, retrait, virement |
| Violet | Dette, pas un gain | Prêt en cours, capital restant |
| Gris | Hors total | Annulée, encore visible dans l’historique |

Liste commune : bouton Ajouter, colonnes triables, total de la sélection, actions Voir / Modifier / Annuler, imprimer, Excel, PDF.

---

## 4. Ordre de réalisation

| Étape | Livrable visible | On s’appuie sur |
|---|---|---|
| 1. Le socle | Statuts Brouillon, À valider, Validée, Annulée, Pointée. Motif d’annulation. Pièce jointe. Liste filtrable et export | Dépenses et écritures déjà en place |
| 2. Les sorties | Dépense du jour + charge du mois (Prévu, Payé, Reste), sans double compte | Factures fournisseurs |
| 3. Les autres entrées | Activités, subventions, divers. Scolarité en lecture seule | Encaissements élèves, inchangés |
| 4. Caisse, banque, emprunts | Comptes, versement, retrait, solde calculé, pointage, fiche de prêt | Virement caisse vers banque |
| 5. La situation | Les quatre chiffres, le hors-résultat, les droits, le mois clos | Uniquement les opérations validées |

### Qui fait quoi

| Profil | Peut | Ne peut pas |
|---|---|---|
| Caissier | Encaisser, payer en espèces, voir ses opérations du jour | Annuler une pièce validée, pointer la banque |
| Comptable | Saisir, valider, pointer, annuler avec motif, exporter | Effacer une ligne validée, rouvrir un mois clos sans le directeur |
| Direction | Lire la situation, valider, exporter, clôturer le mois | Corriger un montant sans laisser l’ancienne valeur |
| Auditeur | Lire et exporter | Créer, modifier, annuler |

L’étape 1 fixe les statuts et l’annulation. Les écrans suivants réutilisent la même liste et les mêmes couleurs. Les brouillons n’entrent pas dans la situation.
