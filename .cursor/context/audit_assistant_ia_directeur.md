# Audit + spec — Assistant IA Directeur

Audit validé le 2026-09-23. **Vague 1 et Vague 2 implémentées** (schéma filtré + pilotage/scolarité). Vagues 3–6 et tools CG : pas commencées.

- Date : 2026-09-23
- Workspace : `C:\wamp64\www\goo_school`
- Cible : rôle **Directeur** (`Etablissement`), selon `type_etablissement`
- Contexte : module **Comptabilité générale** masqué (`AFFICHER_MODULE_COMPTABILITE_GENERALE = False`) ; nav **Scolarité** encore visible
- Plan CG : [comptabilite_plan.md](comptabilite_plan.md)

Objectif : que le Directeur puisse **piloter l’établissement à la voix** (lecture + actions confirmées) sur la scolarité, la pédagogie, les inscriptions, les statistiques et la RH/paie — en tenant compte des écarts Primaire / Collège / Lycée / Collège+Lycée / Supérieur.

---

## 1. Architecture actuelle (rappel)

| Couche | Fichier | Rôle |
|--------|---------|------|
| WebSocket | `school_admin/consumers/assistant_consumer.py` | Canal vocal directeur / personnel admin / enseignant primaire |
| LLM | `school_admin/services/gemini_assistant_service.py` | Gemini 2.5 Flash + `TOOLS_SCHEMA` unique |
| Prompt | `SYSTEM_PROMPT` (même fichier) | Aria direction ; **un seul prompt** pour tous les types d’établissement |
| Lecture | `school_admin/services/assistant_tools.py` | Tools ORM + `TOOL_HANDLERS` |
| Écriture | `assistant_actions.py`, `assistant_staff.py`, `assistant_dossiers.py` | Brouillon → confirmation → `apply` |
| EDT | `assistant_emploi.py` | Créer emploi / ajouter créneau (guidé) |
| Nav | `assistant_pages.py` | Catalogue de pages (`ouvrir_page`) |
| Intentions locales | `assistant_intents.py` | Ouverture page/classe, annonce, EDT sans aller-retour LLM |

Contexte injecté (`build_assistant_context`) — **Vague 1** :

- `est_primaire` / `est_college` / `est_lycee` / `est_college_lycee` (`collège_lycée` **et** `mixte`) / `est_superieur`
- `cycle_requis` si collège+lycée ou mixte
- `libelle_eleve` = « étudiant » (supérieur) ou « élève »

Types Django (`Etablissement.TYPE_CHOICES`) :

`primary` · `collège` · `lycée` · `collège_lycée` · `mixte` · `superieur`

Le schéma et le prompt sont **filtrés par type** (`directeur_tools_schema` / `prompt_addendum_for`). Le personnel administratif garde le persona `directeur` ; l’exécution passe par `check_permission`. Tools LMD hors supérieur. Tools CG hors schéma tant que le flag est False.

Règle d’écriture déjà en place (à conserver) : **rien n’est écrit sans confirmation explicite**.

---

## 2. Inventaire — tools déjà branchés

### 2.1 Lecture / recherche (commun)

| Tool | Ce qu’il fait | Limite actuelle |
|------|----------------|-----------------|
| `chercher_en_base` | Routeur lexical vers un autre tool | Fallback = effectifs ; pas de stats/CG/ECTS |
| `get_effectifs` | Élèves, F/M, classes, profs, personnel | Pas de croissance, pas de taux |
| `rechercher_eleves` | Nom / prénom / matricule / classe | Fiche courte (pas le dossier) |
| `rechercher_classes` | Classes / promotions | Extras LMD seulement si supérieur |
| `ouvrir_classe` | URL fiche classe | — |
| `rechercher_professeurs` | Nom, matière, téléphone | Pas de contrat / tarif / dossier |
| `rechercher_personnel` | Nom + fonction | Pas de dossier complémentaire |
| `get_affectations` | Prof ↔ classe ↔ matière (année active) | Primaire : `AffectationProfesseurPrimaire` (multi-matières). Autres : `AffectationProfesseur` |
| `get_notes_eleve` | Notes publiées + moyennes de période | Primaire → `NotePrimaire`. Autres → `Note`. **Pas d’ECTS, pas de notes de classe, pas d’examens** |
| `get_emploi_du_temps` | EDT actif d’une classe | Pas l’EDT d’un prof |
| `get_presences` | Totaux N jours ou détail élève | Pas de taux, pas de classe, pas de liste à imprimer |
| `get_sanctions` | Totaux, par élève, dernières | Pas de radiation / certificat lié |
| `get_annonces` | 8 dernières publiées | — |
| `get_periodes` | Trimestres / semestres + active | **Pas de `niveau_lmd`** (trou supérieur) |
| `get_comptabilite` | Fiche élève **ou** résumé impayés | Pas de détail mensualités / annexes / reçu / bilan classe |
| `get_parametres_comptabilite` | Barèmes par groupe + annexes | Lecture seule des groupes |
| `get_caisse` | Recettes / sorties / solde du mois + 12 dépenses | Pas d’historique multi-mois, pas de CG |
| `get_volume_horaire` | Heures × tarif vacataire, mois en cours, payé ? | **Permanents absents** |
| `get_notifications` | Non lues + récentes | Pas de marquer-lu |
| `get_preinscriptions` | Liste (défaut : en attente) | Pas le détail candidat |
| `get_liaisons` | Demandes parent–élève | — |
| `get_examens` | Sessions (nom, période, dates) | Pas les créneaux / surveillants / notes d’examen |
| `get_annees` | Années de l’établissement | — |
| `get_salles` | Salles actives | Pas d’occupation / conflits |
| `get_matieres` | Nom + code | Pas de coefficient / crédits |
| `lister_pages` / `ouvrir_page` | Navigation espace directeur | Page `comptabilite_generale` **retirée** tant que le flag est False |

### 2.2 Lecture — particularité supérieur uniquement

| Tool | Ce qu’il fait | Limite |
|------|----------------|--------|
| `get_structure_superieur` | Départements (spécialités) + modules (nom, code) | **Aucun crédit ECTS, aucune UE, aucun rattachement classe / semestre** |

Hors supérieur : le tool renvoie une erreur (mais il reste dans le schéma, donc le LLM peut l’appeler).

### 2.3 Navigation / documents (commun)

| Tool | Remarque |
|------|----------|
| `ouvrir_page` | ~50 clés (dashboard, classes, notes, scolarité, caisse, bulletins, documents, etc.) |
| `generer_document` | Ouvre l’URL : certificat scolarité, attestations réussite / conduite, fiche inscription, radiation, convocation. **N’imprime pas**, n’envoie pas |

Pages catalogue **sans tool métier dédié** : justifications de notes, cartes d’identité, listes nominatives, listes de présence, config horaires, facturation licence Aria, bilan comptable (page), CG (masquée).

### 2.4 Écriture guidée (confirmation obligatoire) — commun

**Annonces** : `creer_publier_annonce`, `publier_annonce`, `modifier_annonce`, `archiver_annonce`, `supprimer_annonce`

**Années / périodes** : `creer_annee_scolaire`, `activer_annee_scolaire`, `desactiver_annee_scolaire`, `changer_session`, `creer_periode`, `activer_periode`, `supprimer_periode`

**Présences / discipline** : `justifier_absence`, `donner_sanction`

**Liaisons / préinscriptions** : `approuver_liaison`, `rejeter_liaison`, `desapprouver_liaison`, `valider_preinscription`, `rejeter_preinscription`, `toggle_lien_preinscription`

**Élèves** : `inscrire_eleve`, `modifier_eleve`, `reinscrire_eleve`, `activer_eleve`, `desactiver_eleve`

**Classes / salles / matières** : `creer_classe`, `modifier_classe`, `desactiver_classe`, `supprimer_classe`, `creer_salle`, `modifier_salle`, `desactiver_salle`, `creer_matiere`, `desactiver_matiere`

**EDT** : `creer_emploi_du_temps`, `ajouter_creneau_emploi`, `publier_emploi_du_temps`, `supprimer_creneau_emploi`

**Examens** : `creer_session_examen`, `supprimer_session_examen`

**Pédagogie (barèmes)** : `publier_bulletins`, `calculer_moyennes_classe`, `configurer_visibilite_bulletins`, `configurer_moyennes` (4 recettes 50/50 etc.), `configurer_standards` (seuil /20)

**Scolarité / caisse** : `enregistrer_paiement`, `creer_parametres_comptabilite`, `modifier_parametres_comptabilite`, `supprimer_parametres_comptabilite`, `creer_moratoire`, `payer_echeance_moratoire`, `relancer_impaye`, `ajouter_depense`, `supprimer_depense`

**RH** : `creer_professeur`, `modifier_professeur`, `desactiver_professeur`, `creer_personnel`, `modifier_personnel`, `desactiver_personnel`, `affecter_professeur`, `enregistrer_absence_professeur`, `marquer_paie`

### 2.5 Écriture — particularité supérieur

| Tool | Ce qu’il fait | Limite |
|------|----------------|--------|
| `creer_filiere` / `modifier_filiere` / `supprimer_filiere` | Spécialité (`Department`) | Pas de domaine LMD complet |
| `creer_module` / `supprimer_module` | Module LMD + spécialité | **Pas de crédits, pas d’UE, pas de rattachement classe/semestre** |

Refus explicite si `type_etablissement != 'superieur'`.

### 2.6 Compteurs

- **~31** tools de lecture / nav / brouillon annonce-EDT
- **~66** actions d’écriture enregistrées (`ACTION_SPECS`)
- **0** tool Comptabilité générale (plan, journaux, OD, fournisseurs, clôture, états SYSCOHADA)
- **0** tool ECTS / relevé de crédits / UE
- **0** tool statistiques de pilotage (taux de réussite, présence, recouvrement, comparatif)
- **0** tool dossier employé (contrat, `salaire_base`, CNSS, RIB) ni bulletin permanent

Tests existants : `school_admin/tests/test_assistant_directeur_tools.py` (socle lecture + intents). Persona enseignant primaire **hors périmètre** de cet audit.

---

## 3. Commun vs particularités par type d’établissement

Le moteur pédagogique n’est **pas** le même. L’assistant aujourd’hui ne porte que deux bascules (`primary` / `superieur`). Collège, lycée, collège+lycée et mixte sont traités comme un **secondaire générique**.

### 3.1 Socle commun (tous types)

À garder et à enrichir sans variant :

- Effectifs, élèves, classes, salles, années, annonces, notifications
- Inscription / réinscription / préinscription / liaisons parents
- Scolarité élève (créances, paiements, reçus, impayés, moratoires, relances) — le **régime public/privé** (`type_etablissement_comptabilite`) est orthogonal au type pédagogique
- Caisse du mois (recettes scolarité − dépenses)
- Personnel administratif, professeurs, absences prof, volume horaire **vacataire**
- Documents admin (certificat, convocation, radiation…)
- Navigation pages

### 3.2 Primaire (`primary`)

| Domaine | Réalité métier | Assistant aujourd’hui |
|---------|----------------|------------------------|
| Notes | `NotePrimaire` / `EvaluationPrimaire` ; instituteur polyvalent | `get_notes_eleve` OK (branche primaire) |
| Affectations | `AffectationProfesseurPrimaire` + **plusieurs matières** | `get_affectations` / `affecter_professeur` OK |
| Périodes | Trimestres (parfois année) | `get_periodes` / `creer_periode` (défaut `trimestre`) OK |
| Coefficients | Coefficient matière, pas ECTS | Pas de lecture/écriture des coefs |
| Structure | Pas de filières / modules | Tools LMD encore visibles au LLM |
| Pilotage | Notes de classe, élèves en difficulté, exercices (côté enseignant déjà) | Directeur : **aucun** `get_notes_classe` / `get_eleves_difficulte` |

### 3.3 Collège (`collège`)

| Domaine | Réalité métier | Assistant aujourd’hui |
|---------|----------------|------------------------|
| Notes | `Note` / `Evaluation` ; une matière par affectation | `get_notes_eleve` OK |
| Périodes | Trimestres | OK |
| Examens | Sessions + EDT examens (BEPC, etc.) | Créer/supprimer session ; **pas** les créneaux ni les notes d’examen |
| Classes | 6e–3e | `creer_classe` force `niveau=college` si non précisé |
| Justifications | Relevés soumis, déblocage directeur | **Aucun tool** |

### 3.4 Lycée (`lycée`)

Comme le collège, plus :

- Coefficients parfois **par groupe** (`CoefficientMatiereGroupe`) — non exposés
- Examens officiels (BAC) — mêmes trous que collège
- `creer_classe` défaut `niveau=lycee`

### 3.5 Collège + Lycée (`collège_lycée`) et Mixte (`mixte`)

**Vague 1** : flags `est_college_lycee` + `cycle_requis`. Même espace vocal.

- `creer_classe` / `creer_professeur` **exigent** `cycle` ∈ {college, lycee} ; plus de défaut `lycee` / `primaire`
- `_niveau_enseignement` ne retombe plus sur `primaire`
- Pédagogie = secondaire (notes `Note`), affectations 1 matière
- Le directeur gère **deux cycles** dans le même établissement : l’IA le sait et demande le cycle

Reste hors Vague 1 : coefficients et examens par cycle.

### 3.6 Enseignement supérieur (`superieur`)

| Domaine | Réalité métier | Assistant aujourd’hui |
|---------|----------------|------------------------|
| Apprenant | Étudiant | Libellé OK |
| Structure | `Department`, `Module`, `ModuleClasse` (crédits, `numero_ue`, semestre) | Liste noms seulement ; **zéro ECTS** |
| Périodes | Semestres LMD **par niveau** (S1–S16, L1…D3, BTS, DUT) | `get_periodes` ignore `niveau_lmd` ; `creer_periode` **n’écrit pas** `niveau_lmd` |
| Notes | Même modèle `Note`, mais le bulletin = **crédits validés / UE** | `get_notes_eleve` renvoie note/20 + moyenne, **pas les crédits** |
| Classes | `niveau_lmd`, département, promotion | `rechercher_classes` enrichit le libellé |
| EDT | TD / TP / cours (enum déjà dans `ajouter_creneau_emploi`) | OK partiel |
| Filières / modules | Création nom + spécialité | Pas d’affectation module→classe, pas de crédits |
| Parents | Liaisons existent encore | Tools liaisons utilisables |

---

## 4. Trous (ce que le Directeur pilote à l’écran mais pas à la voix)

### 4.1 Scolarité / recouvrement (nav visible)

- Détail d’une fiche : mensualités, annexes, historique des reçus
- Bilan scolarité établissement / classe (la page `bilan_comptable` existe)
- Impayés filtrés par classe, balance âgée
- Recu : ouvrir / relire un `REC-AAAA-xxxxx`
- Vérifier / recalculer les statuts (`verifier_statuts_paiement`)
- Remise fratrie : lecture / resynchro
- Annulation / extourne d’un paiement (flux métier encore incomplet côté CG)

### 4.2 Comptabilité générale (module **masqué**)

Tout le hub CG : plan, journaux, exercices, clients 411, fournisseurs 401, trésorerie, paie CG, états (balance, grand livre, CR, bilan). **Ne pas brancher tant que le flag reste False.** Spec ci-dessous pour ne pas les improviser plus tard.

### 4.3 Pédagogie

- Notes / moyennes **d’une classe** (la page `notes_et_resultats` le fait)
- Élèves en difficulté, taux de réussite, rangs
- Bulletin / relevé : lire, imprimer (seul `publier_bulletins` existe)
- Moyenne annuelle
- Justifications de notes + déblocage de relevé
- Coefficients (et crédits matière)
- Notes d’examen (`NoteExamen`) + créneaux / surveillants
- Config horaires
- Modifier un créneau EDT (aujourd’hui : ajouter / supprimer seulement)

### 4.4 Supérieur (LMD / ECTS)

- Crédits d’un étudiant, d’une classe, d’un module
- Associer un module à une classe + semestre + UE + crédits
- Relevés ECTS / validation d’UE
- Périodes par niveau LMD (création et filtrage)

### 4.5 Inscriptions / vie scolaire

- Dossier élève complet (santé, adresse, parents)
- Liste des non-réinscrits
- Cartes d’identité, listes nominatives, listes de présence (impression)
- Présences par classe, absences non justifiées, taux de présence
- Modifier une session d’examen, configurer les créneaux

### 4.6 RH / paie

- Dossier employé complémentaire (`type_contrat`, `salaire_base`, n° CNSS, RIB)
- Fiche de paie (URL existe : `fiche_paie_directeur`) — pas d’ouverture vocale
- Supprimer une absence professeur
- Paie **permanents** (n’existe pas encore côté métier — plan CG étape 4)
- Charges CSS / IPRES (idem)

### 4.7 Statistiques de direction

Le dashboard calcule déjà effectifs, croissance, enseignants, personnel. L’IA n’a **que** `get_effectifs`. Manquent : taux de présence, taux de recouvrement, taux de réussite, comparatif de périodes, effectifs par cycle (collège+lycée).

### 4.8 Qualité / robustesse

- Schéma unique : le LLM d’un primaire voit `get_structure_superieur`, `creer_module`
- Personnel administratif = **mêmes tools directeur** (pas de filtre permission)
- `collège_lycée` / `mixte` mal typés à la création
- `chercher_en_base` ne route pas vers caisse/paie/ECTS/stats de façon exhaustive (caisse et volume horaire sont déjà routés ; CG / ECTS / stats non)

---

## 5. Tools à développer / connecter

Convention de nommage : `get_*` lecture, verbe métier pour l’écriture (toujours **brouillon + confirmation**).  
Statut : **existant** (déjà branché) · **à étendre** · **à créer** · **après CG** (flag off) · **après métier** (la fonction n’existe pas encore dans l’app).

### 5.1 Pilotage / statistiques — commun

| Tool | Statut | Rôle |
|------|--------|------|
| `get_effectifs` | existant / **fait (Vague 2)** | Capacité totale + places libres (pas de croissance annuelle) |
| `get_statistiques_pilotage` | **fait (Vague 2)** | Tableau de bord vocal : effectifs, F/M, profs, personnel, taux présence N jours, taux recouvrement session, nb impayés, nb sanctions |
| `get_taux_reussite` | **fait (Vague 2)** | % au-dessus du seuil, par classe / période ; supérieur = % crédits validés **s’ils sont déjà calculés** |
| `get_taux_presence` | **fait (Vague 2)** | Établissement / classe / élève |
| `get_comparatif_periodes` | **fait (Vague 2)** | Moyennes (et crédits si supérieur), période N vs N-1 |
| `get_repartition_cycles` | **fait (Vague 2)** | Collège+lycée / mixte uniquement (`DUAL_ONLY_TOOLS`) |

### 5.2 Scolarité (nav visible) — commun

| Tool | Statut | Rôle |
|------|--------|------|
| `get_comptabilite` | existant / **fait (Vague 2)** | Query → fiche enrichie (délègue à `get_fiche_scolarite`) |
| `get_parametres_comptabilite` + CRUD | existant | Conserver |
| `enregistrer_paiement` | existant | Conserver |
| `get_fiche_scolarite` | **fait (Vague 2)** | Fiche élève : charges, mensualités, annexes, reçu, moratoire, parent à relancer |
| `get_bilan_scolarite` | **fait (Vague 2)** | Totaux dus / payés / reste, établissement ou classe |
| `get_impayes` | **fait (Vague 2)** | Filtres classe / statut / ancienneté (balance âgée 0-30 / 31-60 / 61+) |
| `ouvrir_recu` | **fait (Vague 2)** | Ouvre `recu_paiement` par n° ou dernier paiement (nav, pas d’écriture) |
| `get_moratoires` | **fait (Vague 2)** | Liste + échéances ; écriture déjà là (`creer_moratoire`, `payer_echeance_moratoire`) |
| `verifier_statuts_paiement` | **fait (Vague 2)** | Recalcul confirmé (`ComptabiliteEleve.verifier_statut_paiement`) |
| `synchroniser_remises_fratrie` | **fait (Vague 2)** | Service recouvrement, confirmation ; un élève ou toute la session |

### 5.3 Caisse — commun

| Tool | Statut | Rôle |
|------|--------|------|
| `get_caisse` | existant / **à étendre** | Mois passé, motif, comparaison N-1 |
| `ajouter_depense` / `supprimer_depense` | existant | Conserver ; **ne pas supprimer** si écriture CG validée (quand CG réactivée) |

### 5.4 Comptabilité générale — après réactivation du module

Ne pas exposer tant que `AFFICHER_MODULE_COMPTABILITE_GENERALE` est False. Spec pour plus tard, alignée sur [comptabilite_plan.md](comptabilite_plan.md).

| Tool | Statut | Rôle |
|------|--------|------|
| `get_plan_comptable` | après CG | Comptes PCE, soldes |
| `get_journaux` / `get_ecritures` | après CG | Pièces d’un journal / d’une période |
| `get_grand_livre` | après CG | Un compte, bornes |
| `get_balance` | après CG | Soldes par compte |
| `get_compte_resultat` / `get_bilan_syscohada` | après CG | Classes 6–7 / 1–5 |
| `get_exercice` | après CG | Exercice civil, périodes verrouillées |
| `creer_ecriture_od` | après CG | OD manuelle équilibrée, confirmation renforcée |
| `extourner_ecriture` | après CG | Inverse datée, jamais de delete |
| `cloturer_periode` / `cloturer_exercice` | après CG | Directeur only |
| `get_fournisseurs` / `creer_fournisseur` | après CG | Tiers 401 |
| `saisir_facture_fournisseur` / `regler_fournisseur` | après CG | Ponts 60x/401 puis 401/5xx |
| `get_tresorerie_cg` | après CG | Soldes 571/521/585 |
| `enregistrer_virement_interne` | après CG | 588 |
| `get_clients_411` | après CG | Balance âgée grand-livre (écart vs applicatif = alerte) |

### 5.5 Pédagogie — commun + variants

| Tool | Statut | Variant |
|------|--------|---------|
| `get_notes_eleve` | existant / **à étendre** | Primaire : `NotePrimaire`. Secondaire : `Note` + barème. Supérieur : + crédits module / UE / semestre |
| `get_notes_classe` | **à créer** | Même branchement de modèles. Synthèse matière × élèves |
| `get_moyennes_classe` | **à créer** | `MoyennePeriode` ; supérieur : crédits + moyenne |
| `get_bulletin_eleve` | **à créer** | Lire / ouvrir URL bulletin (pas générer un PDF magique) |
| `imprimer_bulletins_classe` | **à créer** | Ouvre l’URL d’impression déjà existante |
| `calculer_moyennes_classe` / `publier_bulletins` / configs | existant | Conserver |
| `calculer_moyenne_annuelle` | **à créer** | Route directeur déjà là |
| `get_eleves_difficulte` | **à créer** | Sous le seuil ; supérieur = crédits insuffisants |
| `get_justifications_notes` | **à créer** | Liste en attente |
| `traiter_justification` | **à créer** | Accepter / refuser (même logique que la vue) |
| `debloquer_releve` | **à créer** | API directeur déjà existante |
| `get_coefficients` | **à créer** | Primaire/collège/lycée. Lycée+groupes : `CoefficientMatiereGroupe` |
| `configurer_coefficient` | **à créer** | Confirmation |
| `get_evaluations` | **à créer** | Liste évaluations d’une classe / matière / période |

### 5.6 Supérieur — ECTS / LMD

| Tool | Statut | Rôle |
|------|--------|------|
| `get_structure_superieur` | existant / **à étendre** | Ajouter crédits totaux, UE, classes liées, semestre |
| `get_ects_etudiant` | **à créer** | Crédits acquis / inscrits / restants, par semestre |
| `get_ects_classe` | **à créer** | Maquette + validation |
| `get_modules_classe` | **à créer** | Module, crédits, `numero_ue`, période |
| `affecter_module_classe` | **à créer** | Crédits + UE + semestre |
| `fixer_credits_module` | **à créer** | MAJ `ModuleClasse.credits` |
| `creer_module` | existant / **à étendre** | Accepter crédits, UE, niveau LMD |
| `creer_periode` / `get_periodes` | **à étendre** | Champ `niveau_lmd` obligatoire en supérieur |
| `get_releve_ects` | **à créer** | Ouvre / résume le relevé (équivalent bulletin) |

Hors supérieur : ces tools **ne doivent pas** apparaître dans le schéma (filtrer `TOOLS_SCHEMA` par type — aujourd’hui non fait).

### 5.7 Examens — collège / lycée / collège+lycée / (option) supérieur

| Tool | Statut | Rôle |
|------|--------|------|
| `get_examens` | existant / **à étendre** | + nb créneaux, classes concernées |
| `creer_session_examen` / `supprimer_session_examen` | existant | Conserver |
| `modifier_session_examen` | **à créer** | Dates, période, nom |
| `get_emploi_examens` | **à créer** | Créneaux d’une session |
| `ajouter_creneau_examen` / `supprimer_creneau_examen` | **à créer** | Salle + surveillant + conflit |
| `get_notes_examen` | **à créer** | `NoteExamen` par élève / session |

### 5.8 Emploi du temps — commun

| Tool | Statut | Rôle |
|------|--------|------|
| `get_emploi_du_temps` | existant | Conserver |
| `get_emploi_professeur` | **à créer** | Semaine d’un enseignant |
| `creer_emploi_du_temps` / créneaux / publier | existant | Conserver |
| `modifier_creneau_emploi` | **à créer** | Déplacer un cours |
| `get_configuration_horaires` / `configurer_horaires` | **à créer** | Grille établissement |
| `get_occupation_salle` | **à créer** | Conflits |

### 5.9 Inscriptions / élèves — commun

| Tool | Statut | Rôle |
|------|--------|------|
| CRUD élève + préinscriptions + liaisons | existant | Conserver |
| `get_dossier_eleve` | **à créer** | Fiche complète (identité, parents, classe, scolarité, sanctions) |
| `get_non_reinscrits` | **à créer** | Liste réinscription |
| `get_parents_eleve` | **à créer** | Liens familiaux |
| `generer_cartes_identite` | **à créer** | Ouvre le flux existant (classe ou élève) |
| `imprimer_liste_nominative` | **à créer** | URL déjà existante |
| `imprimer_liste_presence` | **à créer** | URL déjà existante (classe + mois) |

### 5.10 Présences / discipline — commun

| Tool | Statut | Rôle |
|------|--------|------|
| `get_presences` | existant / **à étendre** | Filtre classe |
| `get_presences_classe` | **à créer** | Jour ou période |
| `get_absences_non_justifiees` | **à créer** | File d’attente directeur |
| `justifier_absence` / `donner_sanction` / `get_sanctions` | existant | Conserver |

### 5.11 RH / paie

| Tool | Statut | Rôle |
|------|--------|------|
| CRUD prof / personnel / affectations / absence / `marquer_paie` | existant | Vacataires |
| `get_volume_horaire` | existant / **à étendre** | Période choisie (semaine / mois), pas seulement le mois en cours |
| `get_dossier_employe` | **à créer** | Contrat, salaire de base, CNSS, RIB, tarif horaire |
| `modifier_dossier_employe` | **à créer** | Confirmation ; pas les charges sociales en dur |
| `get_absences_professeur` | **à créer** | Historique + impact heures |
| `supprimer_absence_professeur` | **à créer** | URL déjà existante |
| `ouvrir_fiche_paie` | **à créer** | Ouvre `fiche_paie_directeur` |
| `get_paie_permanents` | **après métier** | Bulletins mensuels (plan CG étape 4) |
| `creer_bulletin_paie` / `valider_bulletin_paie` | **après métier** | CSS/IPRES paramétrables, jamais figés |

### 5.12 Structure établissement

| Tool | Statut | Variant |
|------|--------|---------|
| `creer_classe` | **à étendre** | Exiger le **cycle** si `collège_lycée` ou `mixte` ; ne plus défauter à `lycee` / `primaire` |
| `get_profil_etablissement` / `modifier_profil` | **à créer** | Coordonnées, logo hors scope vocal |
| `modifier_annee_scolaire` / `modifier_periode` | **à créer** | Dates, libellé |
| `marquer_notification_lue` | **à créer** | Optionnel, faible priorité |

### 5.13 Schéma dynamique (infra, pas un tool métier)

| Chantier | Pourquoi |
|----------|----------|
| **Filtrer `TOOLS_SCHEMA` par `type_etablissement`** | Primaire ne voit plus LMD ; supérieur voit ECTS ; CG absente tant que flag False |
| **Flag `est_college_lycee` / `cycle` dans le contexte** | Collège+lycée et mixte |
| **Prompt variant** | Trimestres vs semestres LMD vs instituteur ; ne plus parler d’ECTS en primaire |
| **Permissions personnel** | Secrétaire / caissier / comptable ≠ directeur : sous-ensemble de tools |

---

## 6. Priorisation (validée)

Ordre figé. **Vague 1 et Vague 2 livrées.** Ne pas enchaîner 3–7 sans feu vert.

1. **Socle (fait)** — schéma + prompt filtrés par type ; flags `collège_lycée` / mixte ; `creer_classe` / `creer_professeur` exigent `cycle` ; `_niveau_enseignement` ne retombe plus sur `primaire` ; personnel bridé par `check_permission`.
2. **Pilotage / scolarité (fait)** — `get_statistiques_pilotage`, `get_taux_reussite`, `get_taux_presence`, `get_comparatif_periodes`, `get_repartition_cycles`, `get_bilan_scolarite`, `get_impayes`, fiche scolarité enrichie, `ouvrir_recu`, `get_moratoires`, `verifier_statuts_paiement`, `synchroniser_remises_fratrie`. `get_notes_classe` / `get_moyennes_classe` restent Vague 3 (pédagogie).
3. **Pédagogie quotidienne** — justifications, bulletin, élèves en difficulté, présences classe, EDT prof.
4. **Supérieur** — ECTS / UE / périodes par niveau (bloquant pour un directeur LMD).
5. **RH** — dossier employé, fiche de paie, absences prof, volume horaire paramétrable.
6. **Examens** — créneaux + notes d’examen (collège/lycée).
7. **CG + paie permanents** — seulement après réactivation du module et étapes métier du plan comptable.

---

## 7. Risques

| # | Risque | Gravité | Mitigation |
|---|--------|---------|------------|
| R1 | Un seul schéma pour tous les types → appels LMD en primaire, trimestres mal nommés en supérieur | Haute | Filtrer le schéma + prompt par type |
| R2 | `collège_lycée` / `mixte` mal typés à la création (classe `lycee`, inscription `primaire`) | Haute | Cycle obligatoire ; tests dédiés |
| R3 | Personnel admin = tools directeur (paiement, paie, suppression) | Haute | Filtrer par `check_permission` comme les vues |
| R4 | `enregistrer_paiement` / `ajouter_depense` / `marquer_paie` déclenchent des **ponts CG** dès que le plan est ensemencé, même si l’UI CG est masquée | Haute | Garder l’idempotence ; ne pas inventer d’OD vocale avant spec CG |
| R5 | Hallucination de montants / notes à l’oral | Haute | Interdire de citer un chiffre non issu d’un tool ; tests vocaux |
| R6 | Actions destructives (supprimer classe, dépense, période) | Haute | Confirmation déjà là ; ajouter un second garde-fou si écriture CG liée |
| R7 | `creer_periode` sans `niveau_lmd` en supérieur → semestres « globaux » incohérents | Haute | Champ obligatoire + validation `SEMESTRES_PAR_NIVEAU_LMD` |
| R8 | Double comptage si un futur tool « émission 411 » + ancien pont 70x | Haute | Un seul régime ; hors scope tant que CG masquée |
| R9 | Vacataire vs permanent : `marquer_paie` aujourd’hui = net caisse | Moyenne | Ne pas étendre à CDI avant `BulletinPaie` |
| R10 | Impression / génération document = simple ouverture d’URL | Basse | Le dire dans le prompt ; ne pas promettre l’envoi parent |
| R11 | `chercher_en_base` fourre-tout | Moyenne | Le garder comme filet, mais outiller les intents fréquents |
| R12 | Taille du schéma (~100 fonctions) | Moyenne | Schéma par domaine + type ; cache Gemini déjà en place |

---

## 8. Hors scope

- Implémentation, migrations, changement UI, PR.
- Persona **enseignant primaire** (déjà un set séparé) et futurs personas enseignant collège/lycée.
- Comptabilité **société Aria** (licences, `Facturation`, `Depense` Aria).
- Liasse SYSCOHADA, TVA, déclarations CSS/IPRES EDI, stocks, multi-devises (cf. plan CG §10).
- Paie convention collective complète (13ᵉ mois, heures sup, multi-établissements salarié).
- Envoi WhatsApp / SMS **autonome** hors relance déjà branchée (`relancer_impaye`).
- Modules drapeau peu ou pas vivants : transport, cantine, bibliothèque, santé, orientation (sauf s’ils deviennent des écrans directeur).
- Changer le modèle d’auth (directeur = établissement).
- Brancher les tools CG **tant que** `AFFICHER_MODULE_COMPTABILITE_GENERALE = False`.

---

## 9. Arbitrages validés (2026-09-23)

1. **Filtrer dynamiquement** `TOOLS_SCHEMA` et le prompt par `type_etablissement` dès la Vague 1. Fait (`assistant_schema.py`, `directeur_tools_schema`, `system_prompt_static_for`).
2. **Collège+lycée / mixte** : un seul espace vocal ; **exiger le cycle** (`college` / `lycee`) dans les paramètres des tools concernés (`creer_classe`, `creer_professeur`). Pas deux assistants.
3. **Personnel administratif** : même persona `directeur`, exécution bridée par `check_permission` (permissions Django déjà utilisées par les vues).
4. **Ordre §6 validé.** Vague 1 puis Vague 2 livrées. Pas de Vague 3–6 ni de tools CG.
5. **CG vocale hors schéma** tant que `AFFICHER_MODULE_COMPTABILITE_GENERALE` est False (`CG_TOOLS` + addendum de prompt).
6. **Hors scope §8 validé** (enseignant primaire, compta Aria, liasse, TVA, paie convention complète, etc.).

---

## 10. Vague 2 livrée (2026-09-23)

Module `school_admin/services/assistant_pilotage.py`. Tests : `AssistantDirecteurVague2Tests` (8). Cache Gemini : `aria-directeur-tools-v5-{profile}`.

Phrases vocales utiles (directeur connecté) :

- « Donne-moi le tableau de bord. » → `get_statistiques_pilotage`
- « Quel est le taux de réussite ce trimestre ? » → `get_taux_reussite`
- « Quel est le taux de présence de la 1ère A cette semaine ? » → `get_taux_presence`
- « Compare ce trimestre au précédent. » → `get_comparatif_periodes`
- (mixte / collège+lycée) « Combien d’élèves au collège et au lycée ? » → `get_repartition_cycles`
- « Fiche de scolarité de [nom]. » → `get_fiche_scolarite`
- « Bilan de scolarité de l’établissement. » → `get_bilan_scolarite`
- « Liste les impayés de plus de 60 jours. » → `get_impayes`
- « Ouvre le reçu REC-2026-00001. » / « le dernier reçu de [nom] » → `ouvrir_recu`
- « Quels sont les moratoires en cours ? » → `get_moratoires`
- « Recalcule les statuts de paiement. » → confirmation puis `verifier_statuts_paiement`
- « Applique les remises fratrie. » → confirmation puis `synchroniser_remises_fratrie`
