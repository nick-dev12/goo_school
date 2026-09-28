# Plan d’architecture — Comptabilité établissements (Aria)

Document de conception uniquement. Aucune implémentation dans ce livrable.
À valider par le coordinateur / l’utilisateur avant tout code, migration ou PR.

- Date : 2026-09-23
- Workspace : `C:\wamp64\www\goo_school` (repo `nick-dev12/goo_school`)
- App Django unique aujourd’hui : `school_admin`

---

## 1. Objectif et hypothèses

### 1.1 Objectif

Donner à chaque établissement une **comptabilité d’entité** exploitable au quotidien (caisse, scolarité, fournisseurs, paie) et **rapprochable** d’un plan SYSCOHADA révisé, sans remplacer le module déjà vivant de facturation élèves / recouvrement.

### 1.2 Hypothèses (à confirmer)

| # | Hypothèse | Impact si fausse |
|---|-----------|------------------|
| H1 | Cible principale = **écoles privées francophones UEMOA**, surtout **Sénégal** (titres de postes, FCFA, CSS / IPRES, convention enseignement privé). | Adapter cotisations et libellés (Côte d’Ivoire CNPS, Cameroun CNPS, etc.). |
| H2 | L’établissement est une **entité commerciale / associative** soumise à l’**Acte uniforme OHADA relatif au droit comptable** (SYSCOHADA révisé, 2017) s’il dépasse les seuils du système minimal de trésorerie. Les petites écoles peuvent rester en **caisse** ; le logiciel doit pouvoir les deux. | Ne pas forcer le bilan SYSCOHADA aux toutes petites structures. |
| H3 | Devise de travail = **FCFA** (`Etablissement.devise_monnaie`, défaut déjà `FCFA`). Pas de multi-devises. | Hors scope. |
| H4 | Année **scolaire** (sept.–juin typique) ≠ exercice **civil** (1er janv.–31 déc. SYSCOHADA / DGI). | Deux calendriers à relier, jamais à fusionner. |
| H5 | Enseignement **privé** : inscription + mensualités + frais annexes. **Public** : forfait annuel. Déjà porté par `type_etablissement_comptabilite`. | Conserver ce basculeur. |
| H6 | Les vacataires sont **payés à l’heure** (EDT publié − absences). Les permanents (CDI/CDD) ont un **salaire de base** au dossier employé, pas encore une paie mensuelle. | Deux circuits de paie distincts. |
| H7 | Pas de « plan comptable scolaire » officiel OHADA : on construit un **PCE** (plan comptable d’entité) par subdivision du SYSCOHADA. | Les numéros 701/702 actuels sont pédagogiques, pas normatifs. |
| H8 | La comptabilité **société Aria** (`Facturation`, `Depense`, `Budget`, `CompteUser.salaire`) est un autre monde. | Strictement hors scope de ce plan. |

---

## 2. État actuel du projet

### 2.1 Architecture globale

- Un seul projet Django (`school`), une seule app métier (`school_admin`).
- Multi-tenant par `Etablissement` (le directeur **est** l’établissement : `Etablissement` hérite de `AbstractUser`).
- Autres comptes : `PersonnelAdministratif`, `Professeur`, `Eleve`, `Parent`, `CompteUser` (équipe Aria).
- PostgreSQL, Celery, Channels / Daphne.

### 2.2 Ce qui existe déjà — scolarité / recouvrement

| Modèle | Rôle |
|--------|------|
| `ParametresComptabilite` | Barèmes établissement : inscription, réinscription, mensualité, forfait public, période sept.–juin, jour de versement, retards, partiels, remise fratrie, catalogue JSON des frais annexes. |
| `ParametresComptabiliteGroupeClasse` | Barèmes par groupe de classes (prioritaires sur le général). |
| `ComptabiliteEleve` | Dossier annuel : totaux dus / payés, statut `a_jour` / `en_retard` / `impaye`. |
| `FraisInscription` | Inscription ou réinscription, paiements partiels, remise fratrie. |
| `Mensualite` | Une ligne par mois de l’année scolaire. |
| `FraisAnnexe` | Tenue, carte, assurance, transport, cantine, etc. |
| `PaiementEleve` | Encaissement unitaire + reçu séquentiel (`REC-AAAA-xxxxx`), modes espèces / chèque / virement / mobile money / carte. |
| `CompteurRecuPaiement` | Compteur par établissement × année scolaire. |
| `RelanceImpaye` | Trace SMS / WhatsApp / in-app. |
| `Moratoire` + `EcheanceMoratoire` | Rééchelonnement ; rupture si une échéance reste impayée. |

La génération des lignes (inscription, mensualités, annexes) se fait à la sauvegarde des paramètres (`mettre_a_jour_systeme_comptabilite`) et à l’inscription.

### 2.3 Ce qui existe déjà — comptabilité générale

Fichiers clés :

- `school_admin/model/comptabilite_generale_model.py`
- `school_admin/services/comptabilite_generale.py`
- `school_admin/controllers/comptabilite_generale_controller.py`
- URLs `directeur:cg_*` (hub, plan, journaux, exercices, clients, fournisseurs, trésorerie, paie, états)
- Migration `0222_comptabilite_generale`

| Modèle | Rôle |
|--------|------|
| `CompteComptable` | Plan par établissement (`numero` unique). Classes 1–8, natures actif/passif/charge/produit. Flag `est_auxiliaire` peu exploité. |
| `JournalComptable` | CAI, BAN, ACH, SCO, OD, PAI. |
| `ExerciceComptable` | Lié **optionnellement** à `AnneeScolaire`. Ouvert / clôturé. |
| `PeriodeComptable` | Mois (et T1 / S1 créés de façon incomplète). Verrouillable. |
| `EcritureComptable` + `LigneEcriture` | Pièce équilibrée, source + `source_id` pour idempotence. |
| `FournisseurEtablissement` + `FactureFournisseur` | Achats ; **pas encore de pont d’écriture** à la création / au règlement. |
| `Immobilisation` | Dotation linéaire annuelle (`pont_amortissement`). |
| `MouvementTresorerie` | Virement interne caisse → banque. |

Plan **ensemencé aujourd’hui** (`PLAN_SYSCOHADA_EDUCATION`) :

`211, 213, 2182, 2183, 2184, 2813, 401, 411, 421, 431, 442, 512, 531, 601, 605, 613, 622, 641, 645, 681, 701, 702, 706, 708, 758`

Ponts déjà branchés dans les contrôleurs :

| Source opérationnelle | Pont | Écriture actuelle |
|----------------------|------|-------------------|
| `PaiementEleve` | `pont_paiement_eleve` | **D 531/512 / C 70x** (caisse) |
| `DepenseEtablissement` | `pont_depense` | **D 6xx / C 531** |
| `PaieProfesseurPeriode` | `pont_paie` | **D 622 / C 531** (net seulement) |
| `MouvementTresorerie` | `pont_virement_interne` | D 512 / C 531 |
| `Immobilisation` | `pont_amortissement` | D 681 / C 2813 |

### 2.4 Ce qui existe déjà — caisse et paie

| Modèle | Rôle |
|--------|------|
| `DepenseEtablissement` | Sortie de caisse école (salaire, loyer, électricité, fournitures, carburant, autre). Distinct de `Depense` (société Aria). |
| `PaieProfesseurPeriode` | Marque une période (semaine / mois / année) comme payée : heures, brut, `%` charges, net. Contrainte unique professeur × dates. |
| `AbsenceEnseignant` | Jour d’absence + remplaçant optionnel, déduit du volume horaire. |
| `DossierEmployeComplementaire` | Type de contrat (`cdi`, `cdd`, `vacataire`, `stage`, `convention`, `prestation`), `salaire_base`, n° CNSS, RIB. |
| `Professeur.prix_volume_horaire` | Tarif horaire vacataire. |
| `utils/volume_horaire.py` | Calcul pur : EDT publié × période − absences → montant. |

**Il n’existe pas** de bulletin de paie permanent (salaire mensuel, retenues CSS/IPRES/IR, acomptes, 13ᵉ mois).

### 2.5 Rôles et permissions déjà en place

Fonctions établissement (`PersonnelAdministratif.TYPE_FONCTION_CHOICES`) : directeur adjoint / principal / proviseur, secrétaire, **gestionnaire**, **comptable**, **caissier**, intendant, censeurs, etc.

Permissions compta :

| Permission | Qui (défaut) |
|------------|----------------|
| `comptabilite_voir` | directeur, gestionnaire, comptable, caissier |
| `comptabilite_paiements` | idem |
| `comptabilite_bilans` | directeur, gestionnaire, comptable — **pas le caissier** |
| `comptabilite_scan_qr` | définie, peu utilisée |

`_require_compta` : directeur = accès total ; sinon `check_permission`.
Middleware `CaissierAccessMiddleware` : le caissier est confiné à l’accueil / scolarité / encaissements.

**Manque** : permissions dédiées écritures, clôture, paramétrage du plan, paie, extourne.

### 2.6 Écarts critiques (pourquoi un plan, pas seulement « finir l’UI »)

1. **Numérotation hybride PCG français / ancien SYSCOHADA**, pas le SYSCOHADA **révisé 2017** (caisse `531` au lieu de `57`, banque `512` au lieu de `52`, salaires `641` au lieu de `66`).
2. **Produits 701 / 702** : en SYSCOHADA révisé, `701` = ventes de **marchandises**. Les frais de scolarité sont des **prestations de services** (`705`) et produits accessoires (`706`).
3. **Comptabilité de caisse** sur les encaissements : le compte `411` Clients est créé mais **jamais mouvementé**. Les créances élèves (impayés) n’apparaissent pas au bilan.
4. **Paie** : un seul schéma vacataire « net en caisse » ; pas de `422` rémunérations dues, pas de charges sociales, pas de circuit CDI/CDD.
5. **Facture fournisseur** : stockée sans écriture `401` / `60`.
6. **Auxiliaires** : champ texte `LigneEcriture.auxiliaire`, pas de grand-livre famille / fournisseur / salarié.
7. **Exercice** calé sur l’année scolaire ; T1/S1 générés sur le calendrier civil (janvier), donc **incohérents** si l’exercice commence en septembre.
8. **Pas d’extourne / contre-passation** : un paiement annulé ou une dépense supprimée laisse (ou devrait laisser) une écriture orpheline.
9. **Mobile money** traité comme de la caisse, alors que le révisé prévoit `55` / `585`.
10. UI CG déjà présente : le risque n’est pas « partir de zéro », c’est **corriger le fond sans casser les encaissements**.

---

## 3. Normes retenues

### 3.1 Référentiel principal : SYSCOHADA révisé (2017)

Sources utilisées (consultation 2026-09-23) :

- Acte uniforme OHADA relatif au droit comptable et à l’information financière + Guide d’application SYSCOHADA révisé (ohada.com).
- Plan de comptes normalisé (classes 1–8 ; classe 9 hors bilan / analytique).
- Principe : le SYSCOHADA donne des comptes à 2–4 chiffres ; **chaque entité construit son PCE** en subdivisant.

Règles à appliquer dans Aria :

1. **Partie double** obligatoire : une écriture n’est valide que si Σ débit = Σ crédit.
2. **Exercice de 12 mois**, en principe **année civile**. L’année scolaire reste le **périmètre pédagogique / tarifaire**.
3. **Permanence des méthodes** et **non-compensation**.
4. **Créances et dettes** au bilan (comptabilité d’engagement) pour les établissements qui sortent du système de trésorerie.
5. **Clôture** : verrouillage des périodes, puis de l’exercice ; à-nouveaux en classe 1–5 uniquement.
6. **Pièce justificative** : chaque écriture pointe une source métier (`paiement_eleve`, `facture_eleve`, `depense`, `paie`, `facture_fournisseur`, `od`, `extourne`).

### 3.2 PCE éducation (proposition)

Subdivision stable, suffisante pour une école, extensible par le comptable (écran déjà existant « ajouter un compte »).

#### Classe 2 — Immobilisations

| N° | Libellé |
|----|---------|
| 213 | Bâtiments scolaires |
| 2182 | Matériel de transport (bus) |
| 2183 | Matériel informatique |
| 2184 | Mobilier de classe |
| 2188 | Autres immobilisations corporelles |
| 2813 / 2818 | Amortissements correspondants |

#### Classe 4 — Tiers

| N° | Libellé | Usage Aria |
|----|---------|------------|
| 401 | Fournisseurs | `FactureFournisseur` |
| 411 | Clients — familles / élèves | créance scolarité |
| 419 | Clients créditeurs — avances familles | trop-perçu, paiement d’avance |
| 422 | Personnel — rémunérations dues | net à verser |
| 421 | Personnel — avances et acomptes | acomptes enseignants |
| 4311 | CSS (prestations familiales / AT) | paramétrable |
| 4312 | IPRES (retraite) | paramétrable |
| 447 | État — IR / retenues à la source | si activé |
| 471 | Débiteurs / créditeurs divers | filet |

#### Classe 5 — Trésorerie

| N° | Libellé | Mapping modes de paiement |
|----|---------|---------------------------|
| 521 | Banques locales | virement, chèque, carte |
| 571 | Caisse établissement | espèces |
| 585 | Monnaie électronique / Mobile Money | Wave, Orange Money, MTN |
| 588 | Virements de fonds internes | pont caisse ↔ banque |

*(Les numéros actuels `512` / `531` deviennent des alias de migration, pas des comptes cibles.)*

#### Classe 6 — Charges

| N° | Libellé |
|----|---------|
| 604 | Fournitures scolaires et de bureau |
| 605 | Eau, électricité, fluides *(intitulé PCE ; à ajuster si le cabinet de l’école impose un autre 60x)* |
| 622 | Locations et charges locatives |
| 624 | Transports / carburant |
| 637 | Personnel extérieur / vacations **pendant l’exercice** |
| 6611 | Appointements et salaires — personnel national (permanents) |
| 6641 | Charges sociales patronales — CSS |
| 6642 | Charges sociales patronales — IPRES |
| 667 | Rémunérations de personnel extérieur **à la clôture** (reclassement 637 → 667, SYSCOHADA) |
| 681 | Dotations aux amortissements |

#### Classe 7 — Produits

| N° | Libellé | Source métier |
|----|---------|---------------|
| 7051 | Prestations — droits d’inscription / réinscription | `FraisInscription` |
| 7052 | Prestations — scolarité (mensualités / forfait annuel) | `Mensualite` ou forfait public |
| 7061 | Produits accessoires — cantine, transport, tenues, carte, assurance… | `FraisAnnexe` |
| 7068 | Autres produits scolaires | `type_paiement=autre` |
| 711 | Subventions d’exploitation / bourses | saisie OD ou module futur |
| 758 | Produits divers | filet |

### 3.3 Mode d’enregistrement : engagement + encaissement

**Recommandation (à valider)** : passer en **comptabilité d’engagement** pour la scolarité, tout en gardant la caisse comme journal de trésorerie.

1. **À l’émission de la créance** (création / activation d’un `FraisInscription`, `Mensualite`, `FraisAnnexe` exigible)  
   `D 411  /  C 705x ou 706x`  
   Journal **SCO**.
2. **À l’encaissement** (`PaiementEleve`)  
   `D 571 ou 521 ou 585  /  C 411`  
   Journal **CAI / BAN / (MM via BAN ou journal dédié)**.
3. **Remise fratrie** : diminuer le produit (`D 705x / C 411`) ou n’émettre que le net. Préférer **n’émettre que le net** (déjà stocké dans `montant` après remise) pour éviter les écritures d’avoir systématiques.
4. **Trop-perçu** : `C 419` puis imputation ultérieure.
5. **Annulation / extourne** : écriture inverse datée du jour, `source=extourne`, lien vers l’écriture d’origine. Jamais de suppression physique d’une pièce validée.

Le pont actuel `D trésorerie / C 70x` reste acceptable **uniquement** pour le **système de trésorerie** (petites écoles). Prévoir un flag établissement :

```
ParametresComptabilite.regime_comptable ∈ { tresorerie, engagement }
```

Défaut proposé : `engagement` pour les privés déjà outillés ; `tresorerie` en option.

### 3.4 Frais de scolarité — règles métier (pas une norme OHADA)

Il n’existe pas de plan comptable « scolaire » officiel. Les règles métier Aria, à conserver :

- Privé : inscription (ou réinscription) + N mensualités sur `mois_debut` → `mois_fin` + annexes du catalogue.
- Public : une créance annuelle.
- Paiements partiels, délai de tolérance, « non en règle », reçus inaltérables, moratoires.
- Barème par groupe de classes > barème établissement.
- Recouvrement (relances, balance âgée) déjà amorcé dans `cg_clients` — à **alimenter par 411**, pas seulement par le reste à payer applicatif.

### 3.5 Paie — permanents vs vacataires

Références Sénégal (hypothèse H1) :

- Code du travail (loi 97-17) + **convention collective nationale de l’enseignement privé**.
- **CSS** : affiliation employeur ; AT enseignement souvent cité autour de **1 %** (catégorie 3) — taux **paramétrable**, jamais figé en dur.
- **IPRES** régime général (ordres de grandeur documentés, plafonds changeants) : ~**8,4 % employeur / 5,6 % salarié** ; complémentaire cadres ~**3,6 / 2,4 %**. Plafonds à saisir par l’établissement, pas à coder en magique.
- Vacataire / vacation : souvent traité en **personnel extérieur** (637 puis 667) s’il n’est pas assimilé salarié. Si le dossier a un n° CNSS et un contrat de travail, le traiter comme **661**.

**Règle Aria proposée** (dérivée de `DossierEmployeComplementaire.type_contrat`) :

| Contrat | Base de calcul | Compte de charge | Charges sociales |
|---------|----------------|------------------|------------------|
| `vacataire`, `prestation` | Volume horaire (existant) | 637 (→ 667 à la clôture) | Optionnelles (flag) |
| `cdi`, `cdd`, `convention` | `salaire_base` mensuel | 6611 | CSS + IPRES si flag |
| `stage` | Indemnité forfaitaire | 6611 ou 637 | Selon paramétrage |

Schéma d’écriture **permanent** (engagement) :

```
D 6611          brut
D 6641 / 6642   charges patronales
    C 422           net à payer
    C 4311 / 4312   parts salariales + patronales (détail en sous-lignes)
    C 447           IR si activé
```

Puis règlement :

```
D 422
    C 571 / 521 / 585
```

Schéma **vacataire** (proche de l’existant, corrigé) :

```
D 637           brut (heures × tarif)
    C 422           net
    C 431x          si charges activées
D 422
    C 571 / 521     règlement
```

Aujourd’hui `pont_paie` n’écrit que le **net** en charge : le brut et les charges disparaissent. À corriger.

### 3.6 Ce que SYSCOHADA n’impose pas (et qu’on n’invente pas)

- Pas de TVA scolaire par défaut (exonération fréquente ; pas de module TVA v1).
- Pas de liasse fiscale automatique (bilan SYSCOHADA officiel, TFT, notes annexes).
- Pas de déclaration CSS / IPRES EDI.
- Pas de classe 9 analytique (coût par classe / filière) en v1.

---

## 4. Modèle de données cible

Principe : **réutiliser** les tables actuelles, **ajouter** peu, **ne pas dupliquer** la scolarité dans la CG.

### 4.1 Conservé tel quel (domaine scolarité)

`ComptabiliteEleve`, `FraisInscription`, `Mensualite`, `FraisAnnexe`, `PaiementEleve`, paramètres, recouvrement, reçus.

Ajouts minimaux envisagés plus tard (pas dans une première migration si on peut s’en passer) :

- `ParametresComptabilite.regime_comptable`
- `ParametresComptabilite.exercice_aligne_sur` ∈ `{ annee_civile, annee_scolaire }` — défaut `annee_civile` + lien de rattachement.
- Sur chaque créance : `ecriture_emission_id` (FK optionnelle) pour le pont 411.

### 4.2 Conservé et à faire évoluer (domaine CG)

`CompteComptable` : ajouter éventuellement `numero_syscohada` (cible) vs `numero` affiché, ou **migrer les numéros** via table de correspondance.

`EcritureComptable` : ajouter

- `sens` / `type_piece` ∈ `{ normale, extourne, a_nouveau }`
- `ecriture_origine` (FK, pour extourne)
- `periode` (FK `PeriodeComptable`, dérivée de la date)

`LigneEcriture` : remplacer le texte libre `auxiliaire` par (progressivement) :

- `tiers_eleve` / `tiers_fournisseur` / `tiers_employe` (FKs nullables, une seule renseignée)
- garder `auxiliaire` en libellé d’affichage

`FactureFournisseur` : pont à la création (`D 60x / C 401`) et au paiement (`D 401 / C 5xx`).

### 4.3 Paie — nouveau cœur (sans casser `PaieProfesseurPeriode`)

Ne pas inventer un ERP paie. Une couche mince :

```
BulletinPaie
  etablissement, employe (professeur OU personnel),
  type ∈ { vacataire_periode, mensuel_permanent },
  periode_debut, periode_fin,
  brut, retenues_salariales, charges_patronales, net,
  statut ∈ { brouillon, valide, paye, annule },
  paie_periode_id (nullable, pont vers l’existant vacataire)

LigneBulletinPaie
  code ∈ { brut, css_sal, ipres_sal, ir, css_pat, ipres_pat, acompte, net },
  montant, compte_comptable
```

`PaieProfesseurPeriode` devient le **socle vacataire déjà en production** ; le bulletin l’enveloppe quand on active les charges.

Paramètres sociaux (nouvelle table courte, 1 ligne / établissement) :

```
ParametresPaie
  taux_css_patronal, taux_css_salarial,
  taux_ipres_rg_patronal, taux_ipres_rg_salarial,
  plafond_ipres, activer_ir, activer_charges_vacataires
```

Taux livrés **à titre indicatif Sénégal**, toujours éditables.

### 4.4 Ce qu’on ne crée pas

- Pas de nouvelle app Django en v1 (voir § 5).
- Pas de grand-livre stocké (il se calcule depuis `LigneEcriture`).
- Pas de copie des soldes élèves dans la CG (une seule vérité : créances + paiements ; la CG en est l’image).

---

## 5. Modules / apps Django

### 5.1 Décision

**Rester dans `school_admin`.** Le socle CG, les ponts et les écrans existent déjà. Extraire une app `comptabilite` multiplierait les imports et les migrations pour un gain nul à ce stade.

Organisation interne à respecter (déjà amorcée) :

```
school_admin/
  model/           # pas de nouveau « gros » models.py
  services/
    comptabilite_generale.py   # ponts, plan, soldes
    recouvrement.py
    caisse.py
    paie.py                    # à créer : bulletins, charges
  controllers/
    comptabilite_controller.py
    comptabilite_generale_controller.py
    recouvrement_controller.py
    caisse_controller.py
    volume_horaire_controller.py
  templates/school_admin/directeur/comptabilite*/
```

### 5.2 Frontières de services (contrat)

| Service | Responsabilité | Interdit |
|---------|----------------|----------|
| `comptabilite_eleve` (contrôleur actuel) | Créer / encaisser les créances élèves | Écrire des `LigneEcriture` à la main |
| `comptabilite_generale` | Seul autorisé à `creer_ecriture` | Recalculer un reste à payer élève |
| `recouvrement` | Impayés, relances, moratoires, n° de reçu | Modifier le plan de comptes |
| `caisse` | Solde mois, dépenses | Paie structurée |
| `paie` (futur) | Volume horaire → bulletin ; salaire mensuel → bulletin | Toucher la scolarité |

Tout pont est **idempotent** (`source` + `source_id`) et **silencieux si le plan n’est pas initialisé** (comportement actuel à conserver pour ne pas bloquer un encaissement).

### 5.3 Multi-tenant

Toutes les requêtes CG filtrent `etablissement=`. Le plan est **par établissement** (déjà `unique_together [etablissement, numero]`) : une école peut ajouter `7053 Examens officiels` sans impacter les autres.

---

## 6. Flux

### 6.1 Scolarité (existant + ponts)

```
Paramètres / inscription
        │
        ▼
Créances (inscription, mensualités, annexes)
        │  régime=engagement → écriture SCO  D411 / C705-706
        ▼
Encaissement caissier / comptable / directeur
        │  reçu séquentiel
        │  régime=engagement → D5xx / C411
        │  régime=tresorerie  → D5xx / C705-706  (comportement actuel corrigé de numéros)
        ▼
Statut ComptabiliteEleve + recouvrement + (option) relance
```

Règles UI déjà imposées par le projet : **formulaire HTML + POST Django**, JS seulement pour afficher / masquer.

### 6.2 Dépenses et fournisseurs

```
Dépense caisse ponctuelle     → journal CAI   D6xx / C571
Facture fournisseur           → journal ACH   D6xx / C401
Règlement fournisseur         → CAI ou BAN    D401 / C5xx
Virement interne              → OD ou 588     D521 / C571  (via 588 si on veut l’état de virement)
```

### 6.3 Paie

```
Vacataire
  EDT publié + absences → volume_horaire
       → bulletin (brut, charges optionnelles)
       → PaieProfesseurPeriode (marque « payé »)
       → écritures PAI (637 / 422 / 5xx)

Permanent
  Dossier.salaire_base + ParametresPaie
       → bulletin mensuel
       → écritures PAI (661 / 664 / 422 / 431 / 5xx)
```

### 6.4 Clôture

1. Verrouiller les mois (déjà UI).
2. Contrôles : écritures non équilibrées = 0 ; ponts manquants listés.
3. Reclassement 637 → 667 (vacations).
4. Dotations d’amortissement manquantes.
5. Clôturer l’exercice (déjà UI) — **retirer ou restreindre « rouvrir »** au seul directeur, avec trace.
6. Exercice N+1 : à-nouveaux classes 1–5 (OD).

### 6.5 États à produire (lecture)

| État | Source | Public |
|------|--------|--------|
| Journal | `EcritureComptable` | comptable, directeur |
| Grand livre | agrégat lignes | comptable, directeur |
| Balance | `soldes_par_compte` (existe) | + `comptabilite_bilans` |
| Compte de résultat PCE | classes 6–7 | directeur / comptable |
| Bilan simplifié | classes 1–5 + résultat | idem |
| Balance âgée 411 | déjà ébauchée dans `cg_clients` | + recouvrement |
| Fiche famille | créances + paiements + 411 | caissier (sans bilan) |
| Fiche paie | bulletin | directeur, gestionnaire |

Les « KPI » du hub (`taux_recouvrement`, solde du mois) restent des **indicateurs de gestion**, pas des états SYSCOHADA.

---

## 7. Rôles cibles

| Acteur | Peut | Ne peut pas |
|--------|------|-------------|
| **Directeur** (`Etablissement`) | Tout : paramètres, encaisser, dépenses, paie, clôturer, plan | — |
| **Gestionnaire** | Comme le comptable + souvent RH / classes | Clôturer l’exercice (sauf permission explicite) |
| **Comptable** | Plan, journaux, OD, fournisseurs, états, valider bulletins | Modifier un reçu déjà émis ; pédagogie |
| **Caissier** | Encaisser, imprimer reçu, voir fiche élève / caisse du jour | Bilans, plan, clôture, paie, OD, supprimer dépense ancienne |
| **Intendant** | (futur) fournitures / stocks — pas v1 | Comptabilité |
| **Secrétaire** | Pas de compta par défaut (sauf permission manuelle) | — |
| **Enseignant** | Consulter sa fiche de paie / volume horaire | Saisir une paie |
| **Parent / élève** | Reçu + reste à payer (déjà parent URL) | Journaux |
| **CompteUser Aria** | Facturation **licence Aria** uniquement | Livres de l’école |

Permissions à **ajouter** (noms proposés, pas encore dans le code) :

- `comptabilite_ecritures` — OD manuelles
- `comptabilite_cloture`
- `comptabilite_parametrage_plan`
- `paie_saisir` / `paie_valider`

Le caissier **ne reçoit aucune** de ces quatre.

---

## 8. Étapes de mise en œuvre

Ordre volontaire : d’abord **ne pas casser** l’encaissement, ensuite **corriger le fond**, enfin **étendre la paie**.

### Étape 0 — Validation (cette itération)

- Valider hypothèses H1–H8, régime `engagement` vs `tresorerie`, exercice civil vs scolaire, PCE ci-dessus.
- Figé : pas de nouvelle app, pas de liasse fiscale, pas de paie convention collective complète.

### Étape 1 — Alignement du plan de comptes

- Table de correspondance `ancien → SYSCOHADA révisé` (`531→571`, `512→521`, `641→6611`, `622→637`, `701→7051`, `702→7052`, `706→7061`, `645→6641`, `613→622`, `442→447`…).
- Script de migration de données (numéros) **après** validation, sur établissements déjà ensemencés.
- Mettre à jour `PLAN_SYSCOHADA_EDUCATION` et les ponts (numéros uniquement).
- Tests : soldes globaux identiques avant / après renumérotation.

### Étape 2 — Ponts scolarité corrects

- Flag `regime_comptable`.
- Régime trésorerie : garder D 5xx / C 705-706 mais **bons comptes** + mobile money → `585`.
- Régime engagement : pont **émission** (créance) + pont **encaissement** (411).
- Extourne à l’annulation d’un paiement (quand ce flux existera).
- Ne plus appeler `creer_ecriture` depuis les vues : uniquement les ponts.

### Étape 3 — Fournisseurs et trésorerie

- Pont facture `D 60x / C 401` + règlement.
- Journal de virement via `588` (option).
- Rapprochement : rester au pointage booléen v1 ; pas d’import de relevé bancaire.

### Étape 4 — Paie structurée

- `ParametresPaie` + bulletins.
- Vacataire : envelopper `PaieProfesseurPeriode` (écriture brut / net / charges).
- Permanent : 1 bulletin / mois à partir de `salaire_base`.
- Permissions `paie_*`.
- Impression fiche (template existant `fiche-paie` à enrichir).

### Étape 5 — Qualité d’exercice

- Génération des 12 mois **sur les dates réelles de l’exercice**.
- Interdire (ou journaliser) la réouverture.
- Contrôle d’équilibre à la saisie OD.
- Liste « ponts manquants » (paiements sans écriture).

### Étape 6 — États et recouvrement

- Balance / grand livre / CR / bilan simplifié exportables (CSV d’abord, PDF ensuite).
- Balance âgée 411 alignée sur le grand livre (écart applicatif vs comptable = alerte).
- Provisions `491` : **hors v1** (noté ici pour ne pas les improviser).

### Étape 7 — Durcissement

- Tests unitaires ponts (déjà un socle `tests_frais_annexes.py` côté scolarité).
- Jeu de démo sur établissement de test (directeur primaire / collège déjà documentés).
- Documentation utilisateur courte dans l’UI (aide contexte), pas un second wiki.

---

## 9. Risques

| Risque | Gravité | Mitigation |
|--------|---------|------------|
| Renuméroter des comptes déjà mouvementés | Haute | Table de correspondance + tests de soldes ; jamais supprimer un compte historisé. |
| Double comptage scolarité (émission 411 **et** ancien pont 70x à l’encaissement) | Haute | Un seul régime par établissement ; bascule atomique ; script de rejeu des ponts. |
| `mettre_a_jour_systeme_comptabilite` régénère des créances et donc des écritures 411 en boucle | Haute | Pont émission idempotent par `source=facture_eleve` + id de la ligne de frais. |
| Exercice scolaire vs civil : T1 « janvier » déjà faux | Moyenne | Recalculer les périodes ; ne plus créer T1/S1 civils sur un exercice sept.–juin. |
| Charges sociales figées fausses (plafonds IPRES changent) | Moyenne | 100 % paramétrable ; libellé « indicatif Sénégal ». |
| Vacataire assimilé à tort à 637 alors qu’il est salarié CSS | Moyenne | Décision = `type_contrat` + flag « affilié sécurité sociale ». |
| Caissier qui accède aux journaux via une URL `cg_*` | Moyenne | `_require_compta(..., 'comptabilite_bilans')` sur tout écran CG sauf caisse / encaissement. |
| Suppression d’une `DepenseEtablissement` sans extourne | Moyenne | Interdire delete si écriture validée ; proposer extourne. |
| Périmètre « trop ERP » (stocks, TVA, liasse) | Haute (dérive) | Voir hors scope. |
| Monolithe `school_admin` déjà très gros | Basse v1 | Services stricts ; extraction d’app seulement si un 2ᵉ produit réutilise la CG. |

---

## 10. Hors scope (v1 et volontairement ensuite)

- Toute **écriture de code** tant que ce plan n’est pas validé.
- Comptabilité **Aria** (licences, `Facturation`, `Depense`, `Budget`, salaires `CompteUser`).
- **Liasse SYSCOHADA** officielle, notes annexes, commissariat aux comptes.
- **TVA**, taxes sur CA, exonérations complexes.
- **Déclarations** CSS / IPRES / IR automatiques.
- **Paie complète** : 13ᵉ mois, congés, barème convention collective, heures sup, saisie des jours, multi-établissements pour un même salarié.
- **Stocks** classe 3 (cantine) et classe 9 analytique.
- **Multi-devises**, consolidation de groupe scolaire, budgets prévisionnels école.
- **Import relevé bancaire** / lettrage avancé.
- **Provisions** pour créances douteuses (`491`) et dépréciations.
- Nouvelle app Django, microservices, API publique comptable.
- Changement du modèle d’auth (directeur = établissement).

---

## 11. Décisions demandées à la validation

Réponses attendues (oui / non / amendement) :

1. **Régime par défaut** : engagement (411) ou rester en trésorerie (D 5xx / C 70x) ?
2. **Exercice** : année civile SYSCOHADA, ou continuer à coller à l’année scolaire ?
3. **PCE** : accepter la table § 3.2 (7051/7052/7061, 571/521/585, 661/637) ?
4. **Paie permanents** : v1 = bulletin simple (salaire_base + taux paramétrables), ou **reporter** après les ponts scolarité ?
5. **Périmètre pays** : Sénégal d’abord, ou PCE « UEMOA générique » dès le départ ?
6. Confirmer le **hors scope** § 10, surtout liasse fiscale et déclarations sociales.

Tant que ces six points ne sont pas tranchés, **aucun code applicatif**.
