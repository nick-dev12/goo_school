# Audit + feuille de route — Assistant IA Professeur

**Date** : 2026-09-23  
**Statut** : feuille de route **validée**. **P0–P8 livrées** (assistant professeur multi-types).  
**Branche** : `cursor/assistant-prof-p8-recette-a40c`  
**Workspace** : `C:\wamp64\www\goo_school`  
**Références** :
- Approche Directeur (tools, schéma filtré, confirmation) : [audit_assistant_ia_directeur.md](audit_assistant_ia_directeur.md)
- Runtime Gemini libre (G1–G7, recette) : [audit_assistant_ia_gemini_libre.md](audit_assistant_ia_gemini_libre.md)

**Objectif** : brancher Aria sur **toutes les pages** des espaces enseignant — **primaire**, **secondaire** (collège / lycée / collège+lycée / mixte) et **supérieur** — avec la **même philosophie** que le Directeur : **Gemini = cerveau**, **outils Django = commandes serveur**, **carte oui / modifier / annuler** pour les écritures, **schéma d’outils filtré** selon le type d’établissement et le **périmètre du professeur connecté** (classes / matières affectées).

---

## 1. Verdict en une phrase

Le **primaire** a une **première tranche** (UI + ~25 outils + 8 actions confirmées + persona WS), mais **sans parité G1–G7** ni couverture de toutes les pages ; le **secondaire et le supérieur** n’ont **ni widget vocal ni authentification WebSocket** — seulement les vues Django classiques.

---

## 2. Architecture cible (alignée Directeur)

| Couche | Fichiers existants à étendre | Rôle cible |
|--------|------------------------------|------------|
| UI | `assistant_vocal.js` (partagé directeur), partial HTML par espace | Bulle Aria, STT/TTS, chips, carte confirmation |
| WebSocket | `school_admin/consumers/assistant_consumer.py` | Persona prof, pending, navigation, **ne pas couper Gemini après un tool** (G1) |
| LLM | `school_admin/services/gemini_assistant_service.py` | Prompt + `thought_signature`, repli oral, `working_refs` (« cette classe ») |
| Cache | `school_admin/services/gemini_context_cache.py` | Cache prompt + schéma par persona / profil type établissement |
| Lecture | `assistant_*_tools.py` + `assistant_*_scope.py` | ORM filtré **uniquement** sur affectations du prof |
| Écriture | `assistant_enseignant_actions.py` (pattern `ActionSpec`) | Brouillon → confirmation → `apply` (mêmes modèles que les vues) |
| Navigation | `assistant_pages_enseignant_*.py` | `lister_pages` / `ouvrir_page` / `ouvrir_classe` |
| Qualité | `test_assistant_qualite.py`, tests persona | Régression G1–G7 + périmètre prof |

**Personas proposés** (à valider en vague 0) :

| Persona | Utilisateur | Condition |
|---------|-------------|-----------|
| `enseignant_primaire` | `Professeur` | `etablissement.type_etablissement == 'primary'` (déjà en place) |
| `enseignant` | `Professeur` | Tous les autres types (`collège`, `lycée`, `collège_lycée`, `mixte`, `superieur`) |

Le **filtrage par type** (supérieur : « étudiant », modules, périodes LMD, crédits) reprend `classify_etablissement` / flags déjà injectés dans `build_assistant_context`, comme pour le directeur — **pas** un schéma unique aveugle.

**Règle d’écriture** : identique directeur — **rien n’est persisté sans confirmation explicite**.

---

## 3. État actuel — stack assistant

### 3.1 WebSocket et contexte

- Route WS : `/ws/assistant/` (même consumer que le directeur).
- `_resolve_etablissement` (`assistant_consumer.py`) :
  - Accepte `Professeur` **uniquement** si `actif`, `etablissement_id` renseigné, et **`niveau_enseignement == 'primaire'`**.
  - Persona alors : `enseignant_primaire`.
  - **Tout professeur collège / lycée / supérieur est rejeté** à la connexion WS, même si l’UI existait.
- **Incohérence à corriger** (vague 0) : la connexion OTP (`views.py`) redirige selon `type_etablissement == 'primary'`, pas selon `niveau_enseignement`. Un prof mal typé en base peut avoir l’UI primaire sans WS, ou l’inverse.

`build_assistant_context` remplit déjà `professeur`, `persona`, flags `est_*`, et pour `enseignant_primaire` un résumé `affectations_resume` via `AffectationProfesseurPrimaire`.

### 3.2 UI vocale

| Espace | Partial assistant | Inclusion |
|--------|-------------------|-----------|
| **Primaire** | `enseignant/primaire/partials/assistant_vocal_enseignant_primaire.html` | Via `bottom_nav_primaire.html` → **~35 pages** avec barre du bas |
| **Secondaire / supérieur** | **Aucun** | `bottom_nav_enseignant.html` **sans** include assistant |

Le partial primaire réutilise `assistant_vocal.js` du directeur avec `data-persona="enseignant_primaire"` et CSS dédié `assistant_vocal_enseignant.css`.

**Pages enseignant sans barre du bas** (assistant absent même si on généralisait le partial au nav) :

- Relevés / impression : `voir_releve_notes.html`, `imprimer_releve_notes*.html`, `imprimer_tableau_presence*.html`
- Communication : `annonces_enseignant.html` (secondaire), `notifications_enseignant.html`
- Historique : `historique_annees*.html`, `historique_annee_detail*.html` (primaire + secondaire)
- Partials / fragments live uniquement

**Stratégie pages** : inclure le partial dans **header** ou **fragment commun** (comme le directeur via `header_directeur.html`) pour couvrir **100 %** des écrans métier, y compris ceux sans bottom nav.

### 3.3 Gemini / cache

- Prompt dédié : `SYSTEM_PROMPT_ENSEIGNANT_PRIMAIRE` (`gemini_assistant_service.py`).
- Schéma : `get_enseignant_primaire_tools_schema()` — **pas** de `proposer_actions` dans le schéma enseignant (présent côté directeur).
- Cache : `CACHE_DISPLAY_NAME_ENSEIGNANT = 'aria-enseignant-primaire-tools-v2'`.
- Repli oral : `spoken_from_enseignant_tool` (local, plus simple que le directeur post-G7 : pas de `enrich_class_snapshot` / `suggestions_after_read` branchés explicitement pour le persona enseignant).

### 3.4 Consumer — actions confirmées

Le consumer route déjà :
- `_pending_action_names` → `ENSEIGNANT_ACTION_SPECS` si primaire ;
- `_action_spec` / `choices_for_enseignant_action` ;
- apply via le même chemin que le directeur (`spec.apply`).

---

## 4. Inventaire fonctionnel — vues Django (hors assistant)

Deux **namespaces URL** distincts (pas de duplication supérieur : même espace `enseignant:` que collège/lycée).

### 4.1 Primaire (`enseignant_primaire:` — `enseignant_primaire_url.py`)

| Domaine | Routes / vues | Rôle |
|---------|---------------|------|
| Accueil | `dashboard` | Synthèse classes, prochaines évaluations, notifications |
| Classes | `gestion_classes`, `detail_classe/<id>` | Liste + fiche |
| Élèves | `gestion_eleves`, `detail_eleve/<id>` | Liste filtrée affectations |
| Notes | `gestion_notes`, `noter/<classe>`, `voir_releve`, `soumettre_releve`, `imprimer_releve` | Saisie, relevé, verrouillage matière |
| Évaluations | `creer/modifier/supprimer_evaluation`, `liste_evaluations`, `evaluations_classe/<id>`, `calculer_moyennes` | Cycle pédagogique primaire (`EvaluationPrimaire`, `NotePrimaire`, `MoyenneMatierePrimaire`) |
| Difficulté | `eleves_en_difficulte` | Seuil moyenne |
| Exercices | `exercices_maison` | Devoirs |
| Présences | `gestion_presence`, `liste_presence/<classe>`, `valider_presence`, `modifier_presence`, `historique_presence`, `justifier_absence`, `imprimer_tableau_presence` | Appel, validation |
| Discipline | `soumettre_sanction`, `historique_sanctions`, `liste_sanctions_classe` | Sanctions soumises au directeur |
| Vie scolaire | `emploi_du_temps`, `annonces_enseignant`, `justifications_notes` | EDT classe, comm interne, demandes correction notes |
| Compte | `parametres_profil`, `historique_annees`, `historique_annee_detail` | Profil, archives |

Modèle d’affectation : **`AffectationProfesseurPrimaire`** (multi-matières par classe).

### 4.2 Secondaire + supérieur (`enseignant:` — `enseignant_url.py`)

Même découpage fonctionnel avec **~40 routes**, plus :

| Spécificité | Routes | Remarque |
|-------------|--------|----------|
| **Examens** | `noter_examen/<classe>`, `noter_examen/<classe>/<session>` | Absent du primaire |
| **Relevé API** | `api/releve-modal/<classe>` | Modal AJAX |
| **Impression relevé prof** | `imprimer_releve_enseignant/<classe>` | Variante secondaire |
| **Présence par matière** | `selection_matiere_presence` (template dédié) | Secondaire : présence liée matière / créneau |
| **Notifications** | `notifications_enseignant` | Pas d’équivalent URL primaire |

Modèle d’affectation : **`AffectationProfesseur`** (classe + **une matière** par ligne).

**Supérieur** (`type_etablissement == 'superieur'`) : **mêmes URLs** ; la logique métier diverge dans `enseignant_view.py` (périodes liées **modules** / `ModuleClasse`, navigation semestres LMD, barèmes, crédits dans moyennes — fonctions `_periode_*_superieur`, etc.). Pas d’espace URL « prof supérieur » séparé.

### 4.3 Temps réel (hors vocal)

- `enseignant_live.js`, fragments `gestion_*_live_*` : mises à jour live notes/présences.
- L’assistant vocal **n’est pas** branché sur ces événements ; les tools doivent continuer à passer par l’ORM / services des vues.

---

## 5. État actuel — outils assistant (primaire uniquement)

### 5.1 Lecture / navigation (déjà implémentés)

| Tool | Couverture métier | Limite |
|------|-------------------|--------|
| `chercher_en_base` | Routeur lexical interne | Moins riche que le directeur |
| `get_mes_classes` | Affectations + matières | — |
| `get_effectifs` | Par classe ou agrégé | Périmètre prof OK |
| `rechercher_eleves` | Nom / classe | Pas de fiche complète |
| `get_evaluations_classe` | `EvaluationPrimaire` du prof | — |
| `get_notes_eleve` / `get_notes_classe` | `NotePrimaire` | Pas relevé soumis / verrou |
| `get_eleves_difficulte` | `MoyenneMatierePrimaire` | Seuil fixe défaut 9 |
| `get_exercices_maison` | Liste | — |
| `get_presences` | Totaux ou détail élève | Pas matière / pas « liste du jour » |
| `get_sanctions` | Sanctions du prof | — |
| `get_periodes` | Délègue `tool_periodes` | Pas LMD (N/A primaire) |
| `get_emploi_du_temps` | EDT **classe** | Pas EDT personnel prof |
| `get_annonces` / `get_notifications` | Lecture | Pas marquer lu |
| `lister_pages` / `ouvrir_page` / `ouvrir_classe` | Catalogue `assistant_pages_enseignant_primaire` | Manque historique, relevé, sanctions détail, notifications |

### 5.2 Écriture confirmée (déjà implémentées — primaire)

| Tool | Alignement vue Django |
|------|------------------------|
| `enregistrer_note` | `noter_eleves_primaire` |
| `creer_evaluation` | `creer_evaluation_primaire` |
| `creer_exercice_maison` | `exercices_maison_primaire` |
| `enregistrer_presences` | `liste_presence` / modification |
| `valider_presence_classe` | `valider_presence_primaire` |
| `soumettre_sanction` | `soumettre_sanction_eleve_primaire` |
| `soumettre_releve_matiere` | `soumettre_releve_primaire` |
| `calculer_moyennes_matiere` | `calculer_moyennes_classe_primaire` |

**Non couvert par des tools** (alors que les vues existent) : `modifier_evaluation`, `supprimer_evaluation`, `justifier_absence`, traitement **justifications de notes** (côté prof : consultation seulement), changement profil, soumission exercice, etc.

### 5.3 Tests

- `test_assistant_enseignant_primaire_tools.py` : périmètre scope + quelques handlers + pages.
- **Pas** de tests WS recette prof ; **pas** de tests qualité G1–G7 persona enseignant.

---

## 6. Particularités par type d’établissement (professeur)

| Type | UI | Affectation | Notes / évaluations | Présence | Assistant aujourd’hui |
|------|-----|-------------|---------------------|----------|------------------------|
| **Primaire** | `enseignant/primaire/*` | Multi-matières / classe | `EvaluationPrimaire`, `NotePrimaire`, moyennes matière | Appel classe | Partiel (UI + tools) |
| **Collège / lycée / mixte / collège_lycée** | `enseignant/*` | 1 matière / affectation | `Evaluation`, `Note`, `MoyennePeriode`, coefficients | Souvent **par matière** | **Rien** |
| **Supérieur** | Même UI secondaire | `AffectationProfesseur` + **modules** (`ModuleClasse`) | Périodes **LMD** / semestre, **crédits** dans moyennes | Idem secondaire | **Rien** |

Points de filtrage schéma (comme directeur) :

- **Supérieur** : libellé « étudiant » ; tools optionnels `get_modules_classe`, `get_credits_etudiant` (lecture), période avec `niveau_lmd` si création évaluation ; **pas** de tools directeur (scolarité, caisse, RH globale).
- **Collège+lycée / mixte** : si une action touche une classe, respecter le **cycle** de la classe (pattern `cycle_requis` du directeur).
- **Primaire** : conserver persona séparé (URLs et modèles distincts).

---

## 7. Écart vs approche Directeur / Gemini libre (G1–G7)

| Capacité Directeur (post-G7) | Enseignant primaire |
|------------------------------|---------------------|
| Gemini enchaîne après tool (G1, pas takeover wizard) | Consumer partagé → **OK en théorie** |
| `thought_signature` replay | Code partagé → **OK si cache persona enseignant testé** |
| Repli oral riche + listes nommées | `spoken_from_enseignant_tool` **plus minimal** |
| `working_refs` (« cette classe ») | Partiellement via consumer global ; **prompt enseignant ne le mentionne pas** |
| `proposer_actions` + `suggestions_after_read` | **Absent** du schéma enseignant |
| Télémetrie `assistant.turn` | Persona directeur surtout |
| Recette WS scénarisée | **Non** documentée prof |

**Conclusion** : avant d’étendre au secondaire, une vague **P1** doit **aligner le primaire** sur G1–G7 (recette vocale prof), sinon on réplique une stack « pré-Gemini libre ».

---

## 8. Tools à créer ou étendre (backlog)

Légende : **E** = existe primaire · **N** = à créer · **A** = adapter secondaire/supérieur · **F** = filtrer hors schéma selon type

### 8.1 Socle (tous profs, par persona)

| Tool | Primaire | Secondaire | Supérieur | Notes |
|------|----------|------------|-----------|-------|
| `proposer_actions` | N | N | N | Chips suite ; même sémantique G4 |
| `get_mes_classes` | E | A | A | `AffectationProfesseur` + matière unique |
| `get_effectifs` | E | A | A | Libellé étudiant si supérieur |
| `rechercher_eleves` | E | A | A | — |
| `ouvrir_classe` / `ouvrir_page` / `lister_pages` | E | A | A | Catalogue `assistant_pages_enseignant` secondaire |
| `chercher_en_base` | E | A | A | — |

### 8.2 Pédagogie

| Tool | Primaire | Secondaire | Supérieur |
|------|----------|------------|-----------|
| `get_evaluations_classe` | E | A (`Evaluation`) | A (+ filtre module si besoin) |
| `get_notes_eleve` / `get_notes_classe` | E | A (`Note`) | A (+ crédits / UE en lecture) |
| `get_eleves_difficulte` | E | A (`MoyennePeriode`) | A (seuil + crédits insuffisants) |
| `get_moyennes_classe` | N (partiel via difficulté) | N | N |
| `enregistrer_note` | E | A | A |
| `creer_evaluation` | E | A | A (+ période LMD / module) |
| `modifier_evaluation` / `supprimer_evaluation` | N | N | N |
| `calculer_moyennes_matiere` | E | A (`calculer_moyennes_classe`) | A |
| `soumettre_releve_matiere` | E | A (`soumettre_releve_notes`) | A |
| `get_examens_prof` / `get_notes_examen` / `enregistrer_note_examen` | F | N | N (examens secondaire) |
| `get_justifications_notes` | N | N | N (lecture demandes) |

### 8.3 Vie scolaire

| Tool | Primaire | Secondaire | Supérieur |
|------|----------|------------|-----------|
| `get_presences` | E | A (matière / sélection) | A |
| `enregistrer_presences` / `valider_presence_classe` | E | A | A |
| `justifier_absence` | N | N | N |
| `get_sanctions` / `soumettre_sanction` | E / E | A / A | A / A |
| `get_exercices_maison` / `creer_exercice_maison` | E / E | A / A | A / A |
| `get_emploi_du_temps` | E (classe) | A | A |
| `get_emploi_du_temps_prof` | N | N | N (optionnel) |

### 8.4 Communication & compte

| Tool | Primaire | Secondaire | Supérieur |
|------|----------|------------|-----------|
| `get_annonces` | E | A | A |
| `get_notifications` | E | A | A |
| `marquer_notification_lue` | N | N | N |

### 8.5 Supérieur only (lecture)

| Tool | Description |
|------|-------------|
| `get_modules_classe` | Modules / crédits / UE liés à une classe du prof |
| `get_credits_etudiant` | Crédits validés / restants (périmètre classes prof) |

**Interdits dans tous les schémas prof** (comme prompt primaire actuel) : comptabilité, caisse, scolarité globale, préinscriptions, RH, affectations établissement, annonces directeur, CG, shell.

---

## 9. Feuille de route — vagues proposées

Chaque vague = livrable testable + mise à jour de ce fichier. **Ne pas démarrer sans signal utilisateur.**

### Vague P0 — Cadrage technique

- Personas `enseignant_primaire` + `enseignant` ; corriger **WS auth** (`type_etablissement` + cohérence `niveau_enseignement`).
- Décision inclusion UI : **header commun** prof (primaire + secondaire) pour couverture 100 % pages.
- Fichiers cibles listés ; stratégie cache (`aria-enseignant-tools-v*` + suffixe profil `superieur` / `secondaire`).

### Vague P1 — Primaire × parité Gemini libre (G1–G7)

- Schéma : `proposer_actions` ; prompt : `working_refs`, consignes synthèse.
- Repli oral enseignant = même niveau que directeur (`spoken_from_tool_results`, `suggestions_after_read`, enrichissement fiche classe).
- Télémetrie persona ; tests qualité + recette WS prof primaire (listes, carte oui, pas de bulle rouge).
- Bump cache enseignant.

### Vague P2 — Shell secondaire + supérieur

- Partial `assistant_vocal_enseignant.html` + CSS ; `data-persona="enseignant"`.
- WS : accepter prof non-primary ; `build_assistant_context` avec affectations secondaires.
- **Aucun tool métier** encore : navigation + message de périmètre OK.

### Vague P3 — Scope + lecture secondaire (collège / lycée / mixte)

- `assistant_enseignant_scope.py` (générique) + `assistant_enseignant_secondaire_tools.py` (ou module unique paramétré).
- Tools lecture §8.1–8.3 (sans examens ni supérieur LMD).
- Catalogue pages secondaire ; tests ORM + périmètre (« pas ma classe »).

### Vague P4 — Écriture confirmée secondaire

- Portage `assistant_enseignant_actions` : note, évaluation, présence, sanction, relevé, moyennes, exercice.
- Parité carte confirmation avec directeur.
- Tests prepare/apply.

### Vague P5 — Supérieur (LMD)

- Filtrage schéma + prompt addendum (`est_superieur`).
- Tools modules / crédits ; création évaluation avec période LMD.
- Recette sur établissement test supérieur (cf. comptes directeur supérieur dans rules).

### Vague P6 — Examens (secondaire)

- Tools session / noter examen ; liens `ouvrir_page` vers `noter_examen`.

### Vague P7 — Compléments transverses

- Justifier absence ; modifier/supprimer évaluation ; notifications lues ; pages historique / relevé / impression via `ouvrir_page` uniquement.
- Pages sans bottom nav : assistant via header.

### Vague P8 — Recette finale multi-types

- Parcours vocal par type (primaire Artisant, collège+lycée, supérieur) : voix, switch sujet, multi-tools, listes, suggestions, pas d’écriture sans oui.
- Mise à jour statut dans ce document.

---

## 10. Hors scope (explicitement)

- Outils **Directeur** (scolarité, impayés, caisse, RH, bulletins établissement, préinscriptions, EDT établissement complet).
- **Comptabilité générale** et tout tool CG.
- Commandes **OS / SSH / deploy / manage.py** arbitraire.
- Création / désactivation de **comptes prof** ou **affectations globales** par le prof.
- **Publication d’annonces établissement** (réservé direction — le prof **consulte** les annonces).
- Remplacement du **live JS** notes/présences par l’assistant.
- **Vagues directeur 4–6** non liées prof (ECTS pilotage direction, etc.) — seulement ce qui sert le **périmètre classe du prof**.

---

## 11. Critères de validation (pour le métier)

1. **Couverture UI** : bouton Aria visible sur dashboard, notes, présence, élèves, examens (secondaire), annonces, notifications, paramètres.
2. **Périmètre** : impossible d’obtenir notes ou élèves d’une classe non affectée (test automatisé).
3. **Voix** : questions naturelles → outils → réponse **avec chiffres / noms** ; si Gemini échoue, repli Django **non vide** + 2–3 chips.
4. **Écriture** : toute saisie (note, présence, sanction) → **carte oui/modifier/annuler** ; pas de persistance avant oui.
5. **Types** : libellés et tools supérieur cohérents (étudiant, semestre / module).
6. **Régression** : suite tests assistant existante + tests persona prof green.

---

## 12. Synthèse pour validation utilisateur

| Question | Proposition |
|----------|-------------|
| Découpage | **8 vagues P0–P8**, primaire d’abord (parité G7), puis secondaire, puis LMD, puis examens |
| Personas | **`enseignant_primaire`** + **`enseignant`** (schéma filtré `est_superieur` / cycles) |
| UI | Partial vocal dans **nav/header commun**, pas seulement bottom nav |
| Priorité métier | Lecture classes/notes/présences → écriture confirmée → supérieur → examens |

**Prochaine étape** : maintenance / retours métier (pas de vague P9 prévue).

---

## 13. Livraison P0 + P1 (2026-09-23)

### P0 — Cadrage

| Élément | Livré |
|---------|--------|
| Persona WS | `assistant_prof_persona.resolve_professeur_assistant_persona` — primaire si `type_etablissement == 'primary'` (plus de blocage sur `niveau_enseignement` seul) |
| Cloisonnement | Inchangé : `assistant_enseignant_scope` (affectations actives, année) |
| UI 100 % primaire | Widget Aria dans `header_primaire.html` ; retiré du `bottom_nav_primaire` (évite double instance) |
| Pages sans header | Assistant sur `imprimer_releve_primaire`, `imprimer_tableau_presence` ; gate `assistant_vocal_primaire_if_primary` sur `historique_presence_eleve` / `historique_sanctions_eleve` (vues déléguées secondaire) |

### P1 — Parité Gemini libre (primaire)

| Élément | Livré |
|---------|--------|
| G1 / thought_signature | Runtime partagé `gemini_assistant_service` (inchangé, actif pour persona enseignant) |
| `proposer_actions` | Schéma + handler enseignant |
| `working_refs` | `CLASSE_ARG_TOOLS` étendu (tools prof) ; prompt « cette classe » ; `extract_working_refs` sur `get_mes_classes` |
| Repli oral | `spoken_from_enseignant_tool` enrichi ; `enrich_class_snapshot` / `suggestions_after_read` avec branche `enseignant_primaire` (sans impayés / caisse) |
| Cache | `aria-enseignant-primaire-tools-v3` |
| Tests | `test_assistant_enseignant_primaire_tools` : 11 OK (`--keepdb`) |

### Recette vocale prof primaire (manuelle)

1. Connexion prof **établissement primaire** (ex. Artisant), **Ctrl+F5** sur le dashboard.
2. Bulle Aria visible en bas (header) sur dashboard, notes, présence, historique, impressions.
3. **« Quelles sont mes classes ? »** → noms des classes (pas seulement « 1 classe(s) »).
4. **« Ouvre CE1 A »** → navigation + effectif si disponible ; chips (élèves / notes / appel).
5. **« Donne-moi les infos de cette classe »** → effectifs + élèves (repli enrichi si Gemini coupe).
6. **« Note … »** (brouillon) → carte **oui / modifier / annuler**, rien en base avant oui.
7. Pas de bulle rouge « aucune réponse » après une lecture réussie.

### Fragile / hors P0–P1

- ~~Secondaire / supérieur : pas de WS~~ → corrigé en **P2** (voir §14).
- Pages secondaire réutilisées (historique) : nav du bas « enseignant » générique ; gates **primaire** + **secondaire** sur historiques.

---

## 14. Livraison P2–P4 (secondaire / collège–lycée, 2026-09-23)

### P2 — Shell WS + UI

| Élément | Livré |
|---------|--------|
| Persona WS | `enseignant` si établissement ≠ `primary` (`assistant_prof_persona`) |
| UI header | `assistant_vocal_enseignant.html` dans `header_enseignant_new.html` (`data-persona="enseignant"`) |
| Pages sans header | Gate `assistant_vocal_secondaire_if_not_primary` : notifications, annonces, historiques présence/sanctions, `imprimer_releve_notes_enseignant` |

### P3 — Tools lecture / écriture

| Élément | Livré |
|---------|--------|
| Scope | `assistant_enseignant_scope` : affectations `AffectationProfesseur` + `matiere_ids_for_prof` |
| Tools | `assistant_enseignant_secondaire_tools.py` (ORM `Evaluation` / `Note`, `MoyennePeriode`, pages `assistant_pages_enseignant.py`) |
| Actions | `assistant_enseignant_secondaire_actions.py` (notes, relevé, moyennes, présences `niveau: secondaire`, etc.) |
| Gemini | `SYSTEM_PROMPT_ENSEIGNANT`, cache `aria-enseignant-tools-v1-{superieur\|secondaire}` |
| Consumer | Branche persona `enseignant`, specs actions secondaire, choix classe `enseignant:detail_classe` |

### P4 — Tests

| Élément | Livré |
|---------|--------|
| Régression primaire | `test_assistant_enseignant_primaire_tools` : 11 OK |
| Secondaire | `test_assistant_enseignant_secondaire_tools` : 9 OK |
| Total | **20 tests** (`manage.py test … --keepdb`) |

### Recette vocale prof secondaire (manuelle)

1. Connexion prof **collège / lycée / collège+lycée** (ex. compte directeur collège+lycée pour créer un prof test), **Ctrl+F5** dashboard `enseignant`.
2. Bulle Aria visible (header) ; idem sur annonces / notifications.
3. **« Quelles sont mes classes ? »** → classes affectées (`AffectationProfesseur`).
4. **« Ouvre … »** → fiche classe ; chips élèves / notes.
5. Brouillon **enregistrer note** → carte confirmation avant écriture.

### Hors P2–P4 (P6+)

- **`noter_examen`**, impressions secondaire restantes — **P6–P7**.
- Recette multi-types établissement — **P8**.

---

## 15. Livraison P5 — Supérieur LMD (2026-09-23)

### P5 — Tools prof supérieur

| Élément | Livré |
|---------|--------|
| Schéma filtré | `get_enseignant_secondaire_tools_schema(ctx)` n’ajoute **get_modules_classe** / **get_credits_etudiant** que si `ctx.est_superieur` |
| Lecture LMD | `assistant_enseignant_superieur_tools.py` — maquette modules (UE, crédits, semestre) et crédits étudiant (inscrits / validés / restants), **périmètre affectations prof** |
| Périodes LMD | `_resolve_periode` enseignant : semestre + `niveau_lmd` via helpers `assistant_superieur` ; **creer_evaluation** avec params `semestre` / `niveau_lmd` |
| Gemini | Prompt addendum supérieur (ECTS, pas d’invention) ; cache enseignant **v2** (`aria-enseignant-tools-v2-{superieur\|secondaire}`) |
| Repli | `chercher_en_base` (modules / crédits) ; chips LMD dans `suggestions_after_read` |
| Scope | Correctif `find_classe_prof` : recherche `code_classe` |
| Tests | `test_assistant_enseignant_superieur_tools` (5) + régression primaire / collège — **25 tests** OK |

### Recette vocale prof supérieur (manuelle)

1. Connexion **prof** sur établissement `type_etablissement == superieur` (ou créer un prof affecté à une promotion L1), **Ctrl+F5** dashboard enseignant.
2. **« Quels modules en L1 A ? »** → liste modules, crédits, UE (uniquement **vos** promotions).
3. **« Combien de crédits pour [étudiant] ? »** → inscrits / validés / restants (données ORM, pas inventées).
4. **« Crée une évaluation … semestre 1 »** → carte **oui / modifier / annuler** avant création en base.
5. Vérifier qu’un prof **collège** n’a **pas** les tools `get_modules_classe` / `get_credits_etudiant` dans le schéma (cache profil `secondaire`).

### Hors P5 (P7+)

- Compléments transverses — **P7** ; recette multi-types — **P8**.

---

## 16. Livraison P6 — Examens enseignant (2026-09-23)

### P6 — College / lycee (pas primaire, pas supérieur LMD)

| Élément | Livré |
|---------|--------|
| Filtrage | Tools visibles si `persona=enseignant`, `not est_superieur`, `not est_primaire` |
| Lecture | `get_examens_prof`, `get_notes_examen` (périmètre affectations + matières prof) |
| Navigation | `ouvrir_noter_examen` → `enseignant:noter_examen(_session)` ; page catalogue `noter_examen` |
| Écriture | `enregistrer_note_examen` — carte **oui / modifier / annuler** (`NoteExamen`, respect `soumis`) |
| Intégration | `assistant_enseignant_examens_tools.py` + `assistant_enseignant_examens_actions.py` ; cache **v3** profil `secondaire` |
| Tests | `test_assistant_enseignant_examens_tools` (6) + régression — **31 tests** enseignant OK |

### Recette vocale prof collège / lycée

1. Prof affecté à une classe avec **session d’examen** incluant sa matière.
2. **« Quelles sessions d’examen pour ma classe ? »** → `get_examens_prof`.
3. **« Notes d’examen de … »** → chiffres réels ou message « aucune note ».
4. **« Ouvre noter examen en … »** → navigation vers la page de saisie.
5. **« Note … au BAC blanc »** → brouillon + confirmation avant enregistrement.

### Hors P6 (P7–P8)

- Justifier absence, modifier/supprimer évaluation, notifications lues — **P7**.
- Recette finale multi-types — **P8**.

---

## 17. Livraison P7 — Compléments transverses (2026-09-23)

### P7 — Actions + UI + navigation

| Élément | Livré |
|---------|--------|
| Justifier absence | `justifier_absence` — carte confirmation, aligné vue prof (`absent_justifie`, `type_justificatif`), périmètre affectations |
| Évaluations | `modifier_evaluation`, `supprimer_evaluation` (primaire `EvaluationPrimaire` + secondaire/supérieur `Evaluation`) |
| Notifications | `marquer_notification_lue` ; correctif lecture `get_notifications` (`enseignant`, `lu`) |
| Lecture | `get_justifications_notes` (demandes du prof, classes affectées) |
| Pages catalogue | `voir_releve`, `imprimer_releve`, `imprimer_releve_enseignant`, `imprimer_tableau_presence`, `historique_annee_detail`, `historique_presence` (primaire + secondaire) |
| UI sans header | Widget Aria sur `imprimer_releve_notes.html`, `imprimer_tableau_presence.html` (gate secondaire) |
| Intégration | `assistant_enseignant_complements_actions.py`, `assistant_enseignant_complements_tools.py` ; cache **v4** |
| Tests | `test_assistant_enseignant_complements_tools` (5) + régression — **36 tests** enseignant OK |

### Recette vocale P7 (manuelle)

1. Prof secondaire : **« Justifie l’absence de … »** → type de justificatif → **oui / modifier / annuler** avant enregistrement.
2. **« Modifie l’évaluation … »** / **« Supprime l’évaluation … »** → confirmation (suppression = action destructive).
3. **« Marque mes notifications comme lues »** → confirmation puis compteur header à jour.
4. **« Ouvre l’impression du relevé en … »** → `ouvrir_page` (`imprimer_releve`).
5. Pages impression présence / relevé (secondaire) : bulle Aria visible (Ctrl+F5).

### Hors P7 (P8)

- Recette finale primaire + collège/lycée + supérieur sur parcours complets — **P8**.

---

## 18. Livraison P8 — Recette multi-types (2026-09-23)

### P8 — Recette (automatisée + manuelle)

| Élément | Résultat |
|---------|----------|
| Suite automatisée | Recette P8 (13) + WS prof (6) + cohérence persona (4) + régression P0–P7 — **59 tests** enseignant **OK** (`--keepdb`) |
| UI (§11.1) | Headers incluent le partial Aria ; gates sur impressions / notifications |
| Périmètre (§11.2) | Couvert par tests scope existants + recette P8 |
| Schéma par type (§11.5) | Primaire : pas LMD / pas examens ; collège : examens sans LMD ; supérieur : LMD sans examens |
| Écriture (§11.4) | `prepare_*` → `en_attente_confirmation` (ex. note, P7 justifier) — pas de persistance directe via tools |
| Repli oral (§11.3) | `spoken_from_enseignant_tool` non vide sur `get_mes_classes` / effectifs ; `chercher_en_base` + `suggestions_after_read` sans chips caisse |
| Persona WS | `resolve_professeur_assistant_persona` : primary → `enseignant_primaire`, sinon `enseignant` |
| Correctif recette | Schéma supérieur : retrait `enregistrer_note_examen` (et outils examens) si profil non éligible — cache secondaire **v5** |

### Recette vocale manuelle (par type)

| Type | Comptes / contexte | Parcours à valider |
|------|-------------------|-------------------|
| **Primaire** | Prof Artisant (cf. rules) | Mes classes → infos classe → brouillon note → carte oui ; pas d’outils examens/LMD |
| **Collège / lycée** | Prof affecté + session examen | Idem + `get_examens_prof` / brouillon note examen ; LMD absent du schéma |
| **Supérieur** | Prof LMD (ex. compte test supérieur) | Modules / crédits ; création éval. semestre ; **pas** d’outils examens |

Après déploiement ou changement de cache : redémarrer **Daphne** (`aria-daphne` sur VPS, ou `daphne` / service ASGI en local) pour recharger le schéma Gemini.

### Fragile / hors automatisé (post-correctifs P8)

- **Voix STT/TTS + Gemini live** : toujours **manuel** (micro, TTS, reformulation Gemini).
- **G1–G7 persona enseignant** : pas de `test_assistant_qualite` dédié enseignant ; runtime partagé avec le directeur.
- **Données réelles** : script ad hoc `school_admin/_tmp_test_assistant_live.py` = directeur Artisant uniquement.

### Correctifs P8 — fragiles traités (2026-09-23)

| Sujet | Livré |
|-------|--------|
| **WS prof automatisé** | `test_assistant_enseignant_ws` : consumer `AssistantConsumer` (persona primaire / collège / supérieur), lecture `get_mes_classes`, filtrage examens vs LMD, handshake ASGI anonyme refusé |
| **Persona / schéma** | Source de vérité : `Etablissement.type_etablissement` (`assistant_prof_persona.py`) ; vues primaire via `is_professeur_etablissement_primaire` |
| **niveau_enseignement** | Dérivé du type établissement : `Professeur.save()` + migration `0224_sync_professeur_niveau_etablissement` |
| **Tests cohérence** | `test_assistant_prof_persona_coherence` : persona inchangé si niveau incohérent ; `save()` resynchronise ; échec explicite via `professeur_niveau_coherent_avec_etablissement` |

Réf. §3.1 : le WS **ne** s’appuie **plus** sur `Professeur.niveau_enseignement` pour le persona (historique corrigé).

### Vérification rapide

```powershell
cd C:\wamp64\www\goo_school
.\env\Scripts\Activate.ps1
python manage.py test school_admin.tests.test_assistant_enseignant_ws `
  school_admin.tests.test_assistant_prof_persona_coherence `
  school_admin.tests.test_assistant_enseignant_recette_p8 `
  school_admin.tests.test_assistant_enseignant_complements_tools `
  school_admin.tests.test_assistant_enseignant_examens_tools `
  school_admin.tests.test_assistant_enseignant_secondaire_tools `
  school_admin.tests.test_assistant_enseignant_primaire_tools `
  school_admin.tests.test_assistant_enseignant_superieur_tools --keepdb
```

Puis Ctrl+F5 sur dashboard prof (primaire / secondaire) : bulle Aria, une question « Quelles sont mes classes ? », une écriture test avec **annuler**.
