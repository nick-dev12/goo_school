# Audit — Aria Gemini libre (intelligence d’abord)

**Date** : 2026-09-23  
**Statut** : audit **validé** le 2026-09-23. **G1–G5 validées**. G6–G7 **non commencées**.  
**Branche G0** : `cursor/audit-gemini-libre-a40c`  
**Branche G1** : `cursor/assistant-g1-takeover-a40c`  
**Branche G2** : `cursor/assistant-g2-pending-a40c`  
**Branche G3** : `cursor/assistant-g3-regex-a40c`  
**Branche G4** : `cursor/assistant-g4-suggestions-a40c`  
**Branche G5** : `cursor/assistant-g5-multitools-a40c`  
**Persona** : directeur (personnel admin via `check_permission`). Enseignant primaire : même esprit, hors implémentation ici.  
**Préalable validé** : Vagues métier 1–6 + qualité A+B+C+D + correctif « succès outil ≠ erreur rouge ».  
**Audits liés** : [audit_assistant_ia_directeur.md](audit_assistant_ia_directeur.md) · [audit_assistant_ia_qualite.md](audit_assistant_ia_qualite.md)

---

## 0. Intention (à ne pas diluer)

Gemini est conçu pour **comprendre et exécuter des tâches complexes**. Aria doit sentir cette intelligence : elle comprend, elle agit, elle propose, elle relance. Elle n’est **pas** un formulaire vocal, **pas** une machine à regex, **pas** un wizard champ-par-champ.

Le directeur (et le personnel autorisé) a déjà, via les outils Django, **accès à presque tout l’espace direction**. Le goulot n’est plus « il manque des tools ». Le goulot est le **runtime qui intercepte Gemini** : wizards guidés, takeover après outil, regex de pending, small-talk qui coupe les tools, prompt-catalogue, suggestions presque mortes.

**Objectif de cette transformation** : un seul cerveau (Gemini) planifie et parle ; les outils Django **sont** les commandes serveur ; une carte oui/non protège les écritures ; après chaque tour, Aria propose la suite comme une vraie assistante.

**Interdit de cette transformation** : shell OS, SSH, `manage.py` arbitraire, SQL brut, lecture de fichiers hors outils, tools CG tant que `AFFICHER_MODULE_COMPTABILITE_GENERALE` est False, nouvelle vague métier hors spec déjà validée.

---

## 1. Verdict en une phrase

Aria a déjà Gemini + ~100 outils + confirmation d’écriture. Elle **ne s’exprime pas** parce que, dès qu’un outil d’action répond, le consumer **arrête Gemini** et bascule dans un wizard Python. L’utilisateur parle à une machine à états, pas à une assistante.

---

## 2. Ce que « exécuter des commandes sur le serveur » veut dire

### 2.1 Sens correct (à implémenter)

Quand le directeur dit « publie une annonce aux parents », « ajoute un créneau lundi 8h–10h en 3e A », « quels sont les impayés de la 6e A ? », Gemini doit **appeler les outils Django déjà branchés**. Ces outils :

- tournent **dans le process Django** (WebSocket → `execute_tool` → `TOOL_HANDLERS` / `ACTION_SPECS.prepare` puis `.apply`) ;
- réutilisent les **mêmes contrôleurs / modèles** que les vues de l’espace directeur ;
- sont **filtrés** par type d’établissement (`assistant_schema.py`) et par `check_permission` ;
- pour toute écriture : **brouillon → confirmation explicite → apply**. Rien n’est persisté avant le oui (G1 : plus d’`auto_appliquer` sur les sanctions).

C’est déjà « commander le serveur » : créer une classe, enregistrer un paiement, justifier une absence, publier des bulletins. Pas besoin d’un interpréteur de commandes système.

### 2.2 Sens interdit (à ne jamais ouvrir)

| Demande tentante | Réponse |
|------------------|---------|
| `os.system`, PowerShell, bash | Non |
| SSH VPS, `deploy.sh`, restart services | Non |
| SQL brut, ORM hors handler | Non |
| Lire / écrire des fichiers de config, `.env`, logs | Non |
| Appeler une URL interne non listée dans `ouvrir_page` | Non |
| Tools CG (`get_plan_comptable`, OD, clôture…) | Non tant que le flag est False |
| Contourner `check_permission` « parce que Gemini a tout vu » | Non : le schéma filtré **est** son accès |

Gemini a accès à **tout ce que le directeur a le droit de faire dans Aria**, pas à la machine.

### 2.3 Pourquoi on n’a pas besoin de plus de règles métier

Les outils portent déjà la vérité métier (conflit de créneau, classe introuvable, période LMD obligatoire, personnel sans droit). Gemini n’a pas à re-coder ces règles en regex. Il doit **lire le JSON de l’outil**, reformuler, proposer, rappeler le même outil avec le champ manquant.

Plus on ajoute de regex « pour le protéger », plus on le **ralentit** et on le rend **bête** : une phrase naturelle qui ne matche pas le motif n’atteint jamais le modèle.

---

## 3. Pipeline réel (après A+B+C+D)

```
UI assistant_vocal.js
  → WS chat | stt | confirm | cancel | choice
Consumer assistant_consumer.py
  1. reconnect : 1er chat ≠ oui/non → drop aria_pending
  2. pending_action ? → _route_pending_reply
        • oui/annuler
        • champ / jour / horaire « évident » (regex)
        • sinon classify_pending_intent (Gemini, temp 0)
        • si continue → wizard Python (_continue_*_guidee)
  3. sinon _handle_local_intent : seulement « ouvre / va sur » + ouvrir_page|ouvrir_classe
  4. sinon run_assistant_turn (Gemini cache native, tools, stream)
        • is_small_talk(question) → use_tools=False
        • MAX_TOOL_ROUNDS = 8 (G5)
        • on_tool_result :
            ACTION_SPECS | annonce | EDT | créneau → TAKEOVER
            Gemini s’arrête (stop_after_tools)
            wizard _start_*_guidee / _start_generic_action
  5. TTS séquentiel Gemini (25 s) + Edge si vide
  6. suggestions : presque jamais (voir §5.7)
```

**Gemini juge déjà** : le sujet du tour ouvert, `classify_pending_intent` en cas de doute, la rédaction d’annonce (`generate_written_draft`), le texte oral, le TTS.

**Gemini ne juge plus** dès qu’un outil d’écriture a répondu : le wizard prend la main, pose les questions suivantes **sans** le modèle, et le tour suivant est d’abord avalé par `_route_pending_reply`.

---

## 4. Ce qui va déjà dans le bon sens

Ne pas casser ça.

| Élément | Pourquoi le garder |
|---------|-------------------|
| `prepare` → carte → `apply` | Seule barrière d’écriture saine |
| `check_permission` + schéma filtré | Le personnel ne voit que ses droits ; le primaire ne voit pas les tools LMD / examens secondaires |
| `CG_TOOLS` masqués | Flag compta générale toujours False |
| Vague C : nav locale = `ouvre` / `va sur` seulement | Le reste des **nouveaux** messages va déjà à Gemini |
| Reconnect drop pending | Plus de zombie EDT après refresh |
| `_pending_decision` + doute → switch | Un « quels sont les effectifs ? » pendant un EDT peut déjà sortir |
| `compact_tool_memory` | Chiffres du dernier outil au tour suivant, sans JSON énorme |
| Cache `aria-directeur-tools-v12` + stream | Prompt + tools stables, parole au fil de l’eau |
| `spoken_from_tool_result` | Repli oral si Gemini lâche après un outil réussi |
| Carte `action.pending` + boutons Oui / Annuler | Confirmation tactile + vocale |
| Canal unique d’affichage `audio_sentence` | Texte et voix restent alignés |

---

## 5. Freins à l’intelligence (inventaire)

### 5.1 Takeover après outil — le plus grave

Dans `on_tool_result` (`assistant_consumer.py`) :

- nom ∈ `ACTION_SPECS` → `_start_generic_action` puis **`return True`**
- `creer_publier_annonce` → `_start_annonce_guidee` puis stop
- `creer_emploi_du_temps` → `_start_emploi_guidee` puis stop
- `ajouter_creneau_emploi` → `_start_creneau_guidee` puis stop

`run_assistant_turn` voit `stop_after_tools` : il **n’enchaîne pas** le tour Gemini post-outil. Le modèle n’a pas le droit de :

- reformuler le brouillon comme une assistante (« J’ai préparé l’annonce aux parents, titre… On publie ? ») ;
- proposer une variante (« Je peux aussi n’envoyer qu’aux enseignants ») ;
- enchaîner une lecture utile (« Avant de publier, 12 parents n’ont pas de compte — je les liste ? ») ;
- corriger un champ manquant en langage naturel plutôt qu’un prompt Python figé (`next_emploi_prompt`, `default_prompt`).

**Effet ressenti** : dès qu’on demande une action, Aria bascule en mode questionnaire. Ce n’est plus Gemini.

`GUIDED_ACTIONS` = `{creer_publier_annonce, annonce_guidee, creer_emploi_du_temps, ajouter_creneau_emploi}`. Plus `_start_generic_action` pour **toutes** les autres écritures (classe, paiement, sanction, période, etc.).

### 5.2 Wizards Python = second cerveau

Toujours présents, longs, regex-driven :

| Wizard | Fichiers | Ce qu’il vole à Gemini |
|--------|----------|------------------------|
| Annonce guidée | `_start_annonce_guidee`, `_continue_annonce_guidee`, `ANNONCE_*_RE`, `WRITE_SPEC_RE` | Sujet → titre → texte → destinataires, champ par champ |
| EDT / créneau | `_start_emploi_guidee`, `_continue_emploi_guidee`, `extract_*_draft`, `CRENEAU_ADD_RE` | Classe → jour → horaires via extracteurs |
| Action générique | `_continue_generic_action` | 1er `manquant` = tout le message utilisateur collé dans un champ |

`_continue_generic_action` est particulièrement brutal : si `manquants = ['classe']`, **toute** la phrase (« non, plutôt la 4e B et aussi le coefficient ») est fourrée dans `classe`. Gemini aurait compris. Le wizard non.

Les fonctions `next_emploi_prompt`, `_next_annonce_prompt`, `default_prompt` sont des **scripts de conversation**. Elles parlent à la place du modèle.

### 5.3 Regex encore partout (même si plus en entrée)

Vague C a retiré les regex **d’entrée** (annonce / EDT / CRUD ne court-circuitent plus Gemini sur un message neuf). Elles **vivent** encore :

- `ACTION_INTENT_RES` : ~50 motifs, encore utilisés par `_continue_generic_action` (`resolve_action_intent`) et par des tests ;
- `ANNONCE_CREATE_RE`, `EDT_CREATE_RE`, extracteurs jour / heure / matière / prof / salle ;
- `decide_pending_reply` / `looks_like_new_topic` / `TOPIC_SWITCH_RE` / `NEW_QUESTION_RE` / `METIER_SWITCH_RE` ;
- `is_obvious_pending_continue` (jour, horaire, champ, choix) — filet utile, mais trop large il redevient un portier.

Chaque motif **manqué** = Gemini n’est pas consulté, ou le wizard mal-remplit un champ. C’est exactement le « ralentissement par les règles » à supprimer.

### 5.4 `is_small_talk` coupe les tools

`use_tools=not is_small_talk(question)`.  
« Merci, et les effectifs ? » ou « Bonjour, publie l’annonce de demain » : si le regex accroche trop large, Gemini **parle sans base**.  
À l’inverse, un vrai « merci » n’a pas besoin d’outil — Gemini sait déjà (prompt : *sans appeler d’outil*). Le garde-fou Python est redondant et dangereux.

### 5.5 `MAX_TOOL_ROUNDS` — **levé en G5**

`MAX_TOOL_ROUNDS` est passé de 3 à **8** (plafond de sécurité). Chaque round et le total sont logués (`Gemini tool round N/8`, `Gemini tool rounds: N/8`). Une demande riche (effectifs + impayés + ouvrir + proposer) tient dans un seul tour. G6 ne retouche pas ce plafond.

### 5.6 Prompt-catalogue vs autonomie

`SYSTEM_PROMPT` (~150 lignes) est un **inventaire de noms d’outils** (« Années : creer_annee… Périodes : … Absences : … »). Utile pour le cache tools, **nuisible** s’il devient la seule façon de penser : le modèle se sent tenu de coller au menu.

Ce qui manque, et que le directeur doit **sentir** :

- « Tu es autonome. Si la demande est claire, agis (prepare). Si un détail manque, déduis ou pose UNE question. »
- « Après une lecture, propose 1 à 3 suites utiles (pas un catalogue). »
- « Si l’outil dit incomplet / suggestions_possibles, reformule en assistante, ne récite pas le JSON. »
- « Tu peux enchaîner plusieurs outils dans le même tour. »
- « Ne redeviens pas un formulaire : pas de “champ 1, champ 2, champ 3”. »

Le prompt dit déjà *« Tu es autonome : déduis, rédige, propose »* — mais le runtime **empêche** cette phrase de s’appliquer dès qu’un write tool a tourné.

### 5.7 Suggestions sous-utilisées

Le front a déjà :

- `type: suggestions` → `renderSuggestions` (aujourd’hui : force un « Ouvre {titre} », donc **navigation**, pas des propositions métier) ;
- `type: choices` → boutons / select (confirmation, destinataires, classes).

`_infer_choices` ne sort des Oui/Non **que** si la phrase orale se termine par `?` **et** contient « souhaitez-vous / voulez-vous / c’est bon ». Sinon : **aucune** puce.

Résultat : après « Vous avez 12 impayés en 6e A », Aria se tait. Une assistante dirait : « Je peux relancer les familles, ouvrir la fiche de Diallo, ou créer un moratoire. » Ces puces doivent venir de **Gemini** (texte + payload structuré), pas d’un regex sur le point d’interrogation.

### 5.8 `auto_appliquer` sur `donner_sanction`

`prepare_donner_sanction` pose `auto_appliquer=True`. `_start_generic_action` confirme **sans** oui du directeur. C’est l’inverse de la règle d’écriture, et ça a déjà produit le bug « succès + erreur rouge » (Gemini continuait, le consumer envoyait l’erreur générique).

Toute écriture, y compris une sanction, doit **passer par la carte**. Gemini présente, le directeur dit oui. C’est plus sûr **et** plus « assistante » (elle propose le texte de la note, on valide).

### 5.9 Historique sans outils — **enrichi en G5**

`self.history` = toujours user + phrase orale (pas tout le JSON). G5 : `compact_tool_memory` (≤ 400 car.) + `_working_refs` (`classe_id`, `eleve_id`, noms) pour « relance-le ». Les tools lecture (`get_impayes`, `rechercher_eleves`, `get_effectifs`, fiche scolarité) exposent maintenant ces ids.

### 5.10 Navigation locale encore prioritaire

`_handle_local_intent` : `ouvre` / `va sur` → tool nav **sans** Gemini. Acceptable pour un raccourci 100 % sûr. Inacceptable si on veut « ouvre la 6e A et dis-moi les impayés » : aujourd’hui le regex peut **ouvrir et s’arrêter** (`_speak_and_finish`) sans laisser Gemini enchaîner la lecture.

Même les raccourcis doivent **rendre la main** au modèle s’il reste une consigne métier dans la phrase.

---

## 6. Architecture cible (Gemini s’exprime)

```
Message directeur
    │
    ▼
Gemini (seul juge d’intention)
    │
    ├─ conversation / conseil → parle, propose
    ├─ lecture → tools get_* / chercher_en_base (N rounds)
    └─ écriture → tool prepare
            │
            ▼
       Carte unique Oui / Modifier / Annuler
            │
            ├─ Oui → apply (même contrôleur que la vue)
            ├─ Modifier → Gemini (pas un wizard champ)
            └─ Annuler → clear, Gemini propose autre chose
    │
    ▼
Suggestions (1–3) générées par Gemini + éventuellement ids d’outils
```

### 6.1 Un cerveau

- **Plus de takeover.** Après un tool, Gemini reçoit le JSON et **continue le tour** (texte + éventuellement un 2e / 3e tool).
- **Plus de `_continue_*_guidee`.** Un pending n’existe que pour **attendre le oui/non** (ou un choix UI : type de sanction, classe ambiguë).
- **Oui / Non / Annuler** : regex courts, stables, déjà là (`is_affirmative`, `is_cancel`). Le reste du pending → Gemini (il a le brouillon dans le contexte).
- **Nav `ouvre X`** : tool nav **puis** Gemini si la phrase contient autre chose.

### 6.2 Commandes = tools

Gemini « exécute sur le serveur » uniquement via `execute_tool`.  
Si un tool renvoie `incomplet` / `suggestions_possibles` / `plusieurs` : Gemini reformule, pose UNE question ou propose des puces. Il **rappelle** le même tool avec le complément. Pas de machine à états Python.

### 6.3 Confirmation unique

Une seule UX d’écriture :

1. Gemini (ou le prepare) résume ce qui va être fait.
2. Carte + voix : « Je m’apprête à … C’est bon ? »
3. Oui → `apply`. Non / annuler → rien. « Change le titre » → Gemini ajuste le brouillon et **représente** la carte.

Exception **à supprimer** : `auto_appliquer`.

### 6.4 Interaction sentie (propositions)

Après une lecture ou une action, Gemini doit **naturellement** enchaîner une proposition. Le runtime lui fournit un canal :

- oral : une phrase de relance (« Je peux relancer les familles si vous voulez. ») ;
- UI : 1 à 3 chips (`suggestions` métier, pas seulement « Ouvre page »).

Exemples d’interaction cible :

| L’utilisateur | Aria aujourd’hui | Aria cible |
|---------------|------------------|------------|
| « Crée un EDT pour la 3e A » | Wizard : quelle classe ? (alors qu’elle l’a) puis jour… | « Je prépare la grille de la 3e A. On ajoute le premier cours ? Lundi 8h–10h maths avec Mme X, par exemple. » + puces |
| « Les impayés » | Liste orale, silence | Liste + « Je peux relancer, ou ouvrir la fiche de Diallo (le plus élevé). » |
| « Blâme à Diallo » | `auto_appliquer` parfois + erreur rouge | Présente type / raison / note rédigée → « J’enregistre ? » |
| « Merci et les effectifs » | Small-talk, tools off | « Avec plaisir. Vous avez 412 élèves… » |
| « Ouvre la 6e A et les notes » | Ouvre et s’arrête | Ouvre **et** résume les notes |

### 6.5 Ce qu’on retire vs ce qu’on garde

| Retirer (runtime) | Garder |
|-------------------|--------|
| `_start_annonce_guidee` / `_continue_annonce_guidee` comme FSM | `generate_written_draft` **appelé par Gemini** (rédaction) |
| `_start_emploi_guidee` / `_continue_emploi_guidee` / `_start_creneau_guidee` | `enrich_*` / `apply_*` comme **tools** |
| `_continue_generic_action` (coller le texte dans `manquants[0]`) | `_confirm_generic_action` / `_cancel_pending` |
| Takeover `return True` sur writes | `on_tool_result` pour nav + mémoire + carte pending **sans stopper le modèle** |
| `ACTION_INTENT_RES` sur le chemin conversation | Tests d’outils directs (`ACTION_SPECS['x'].prepare`) |
| `is_small_talk` → `use_tools=False` | Prompt : *salutations sans outil* |
| `auto_appliquer` | Confirmation sanction |
| Prompt-menu comme seule boussole | Addendum type d’établissement + droits |

Regex **conservables** (filets courts, pas portiers) :

- `is_affirmative` / `is_cancel` ;
- `is_explicit_navigation` **si** on laisse Gemini finir le tour ;
- `is_obvious_pending_continue` **très** étroit (un seul mot = « lundi », « 8h-10h », un label de puce cliquée).

---

## 7. Garde-fous minimaux (sécurité, pas « règles qui ralentissent »)

Ces garde-fous restent **non négociables**. Ils ne sont pas des regex d’intention.

1. **Schéma filtré** : type d’établissement + `check_permission`. Gemini ne peut pas appeler un tool absent du schéma.
2. **Écriture = confirmation** (carte + oui vocal ou bouton). Destructif (`supprimer_*`) : libellé plus fort déjà prévu (`DESTRUCTIVE_CHOICES`).
3. **Aucun tool CG** tant que le flag est False.
4. **Aucun exécuteur OS / SQL / fichiers.**
5. **Timeouts** LLM / TTS déjà en place.
6. **Personnel** : même persona, droits plus étroits — ne pas « tout ouvrir » pour le caissier.
7. **Logs** : nom d’outil, pending, décision confirm/cancel (déjà partiellement là). Utile pour la recette, pas pour brider le modèle.

Ce n’est **pas** un garde-fou : intercepter « créer une classe » par regex pour lancer un wizard. Le tool `creer_classe` + confirmation suffit.

---

## 8. Plan d’actions futures (ordre d’implémentation)

Audit **validé**. Une vague à la fois, tests ciblés, pas de nouvelle vue globale, pas de tools CG, pas de PR sauf demande. **G1–G5 validées.** **Stop après G5** : ne pas démarrer G6 sans feu vert.

Cache prompt : chaque vague qui touche le texte système **bump** `CACHE_DISPLAY_NAME` (`aria-directeur-tools-v11`, puis v12…).

### Vague G0 — déjà faite ici

Livrable : ce fichier. Zéro code.

### Vague G1 — Couper les takeovers (fondation) — **FAITE** (2026-09-23)

**But** : Gemini **termine** le tour après un tool d’écriture. La carte pending s’affiche, le modèle parle.

Actions :

1. `on_tool_result` : si write/incomplet/pending → **persister le brouillon + envoyer `action.pending`**, `return False` (ne plus stopper).
2. Ne plus appeler `_start_annonce_guidee` / `_start_emploi_guidee` / `_start_creneau_guidee` / `_start_generic_action` depuis le takeover.
3. Si `statut == en_attente_confirmation` : carte + Gemini oral. Si `incomplet` : pas de carte apply, Gemini pose la question.
4. Supprimer `auto_appliquer` (sanction = carte comme les autres).
5. `spoken_from_tool_result` reste un **repli** si Gemini se tait, plus la voix principale.

Tests : un prepare `creer_classe` / `donner_sanction` n’arrête pas le mock Gemini ; pas d’`auto_appliquer` ; pas d’erreur générique après succès.

**Hors G1** : `_route_pending_reply` reste pour le tour **suivant** (oui/non / wizard). Pas touché.

**Livré G1** : `on_tool_result` persiste le brouillon + carte si `en_attente_confirmation`, **return False**. Plus de `_start_*_guidee` / `_start_generic_action` depuis le tour Gemini. `auto_appliquer` retiré de `donner_sanction`. `spoken_from_tool_result` = repli seulement. Tests : `school_admin.tests.test_assistant_qualite.GeminiG1TakeoverTests` + sanction sans auto-apply.

### Vague G2 — Pending = oui/non, plus wizard — **FAITE** (2026-09-23)

**But** : le tour suivant n’est plus un FSM. Validé utilisateur : seuls **oui / modifier / annuler** consomment `aria_pending`. Toute autre phrase = nouveau sujet Gemini, pending droppé.

Actions :

1. `_route_pending_reply` : `is_affirmative` → apply (si brouillon prêt), `is_cancel` → cancel, `is_pending_modify` → garde la carte et laisse Gemini (overlay brouillon).
2. Toute autre phrase → **clear silencieux**, puis `_handle_chat` (Gemini). Plus de `classify_pending_intent` / wizard continue sur le chemin live.
3. `_continue_*` hors du chemin live (G3 les a ensuite retirés du consumer). `apply` / `confirm` / `cancel` conservés.
4. Carte Oui / Modifier / Annuler inchangée. Boutons UI `confirm` / `cancel` / `modify` inchangés.
5. Extracteurs jour/heure plus appelés depuis le routeur pending.

Tests : `school_admin.tests.test_assistant_qualite.GeminiG2PendingTests`.

**Hors G2** : pas de G3 (regex hors conversation).

### Vague G3 — Regex hors du chemin conversation — **FAITE** (2026-09-23)

**But** : `assistant_intents.py` n’est plus un routeur métier. Gemini gère le sujet.

Actions :

1. `resolve_action_intent` / `ACTION_INTENT_RES` : plus importés ni appelés par le consumer. Restent en **legacy** pour les tests d’outils (`test_assistant_directeur_tools`).
2. `is_small_talk` ne coupe plus `use_tools` (toujours True). Le prompt suffit pour un « merci ».
3. Nav raccourci seulement si `is_navigation_only` (« ouvre / va sur » **sans** « et / puis / ensuite » + consigne). « Ouvre la 6e A et les notes » → Gemini.
4. FSM morts retirés du consumer : `_start_*_guidee`, `_continue_*`, extracteurs annonce/EDT, `generate_written_draft` côté WS. Carte Oui / Modifier / Annuler + `confirm` / `apply` conservés.

Tests : `school_admin.tests.test_assistant_qualite.GeminiG3RegexTests`.

**Hors G3** : pas de G4 (suggestions).

### Vague G4 — Suggestions vraiment assistante — **FAITE** (2026-09-23)

**But** : on **sent** l’interaction.

Actions :

1. `choices` = confirmation / select métier. `suggestions` = suites proposées (WS `type: suggestions`).
2. `renderSuggestions` : `{label, value, intent: chat|open, url}`. Plus de préfixe forcé « Ouvre… ». Un clic chat renvoie `value` à Gemini.
3. Tool lecture-seule `proposer_actions` (max 3 puces). Prompt + cache **`aria-directeur-tools-v11`**. Pas d’énumération orale.
4. `_infer_choices` ne fabrique plus de Oui/Non depuis la phrase. Carte oui / modifier / annuler inchangée ; pas de suggestions si une confirmation est prête.

Tests : `school_admin.tests.test_assistant_qualite.GeminiG4SuggestionTests`. JS `assistant_vocal.js?v=1.9.13`.

**Hors G4** : pas de G5 (MAX_TOOL_ROUNDS).

### Vague G5 — Tâches complexes (plusieurs tools) — **FAITE** (2026-09-23)

**But** : laisser Gemini enchaîner.

Actions :

1. `MAX_TOOL_ROUNDS` : 3 → **8** (plafond de sécurité, pas une cible à viser). Loguer le nombre de rounds.
2. Prompt : *tu peux enchaîner ; une demande riche = plusieurs tools puis une synthèse orale.*
3. Mémoire de travail : dernier outil + ids/noms cités (classe_id, eleve_id) pour « relance-le ».
4. Nav + métier dans la même phrase : un seul tour Gemini.

**Livré G5** : plafond 8 + logs `Gemini tool round N/8`. Prompt + cache **`aria-directeur-tools-v12`**. `extract_working_refs` / `_working_refs` (classe_id, eleve_id, noms). Ids ajoutés aux JSON `get_impayes`, `rechercher_eleves`, `get_effectifs` (si classe), fiche scolarité. Nav + métier toujours un seul tour Gemini (G3). Écritures toujours carte Oui / Modifier / Annuler. Tests : `school_admin.tests.test_assistant_qualite.GeminiG5MultiToolTests`.

Recette : « Prépare la 3e A : effectifs, impayés, et une annonce aux parents s’il y a des dettes. » → 2–3 tools + brouillon d’annonce + carte, **sans** wizard.

**Hors G5** : pas de G6 (réécriture du prompt-catalogue) ni G7.

### Vague G6 — Prompt d’autonomie (cache v11+)

**But** : le texte système **autorise** ce que G1–G5 rendent possible.

Actions :

1. Raccourcir le catalogue (garder les pièges : LMD, primaire, « n’invente pas d’ECTS », destinataires d’annonce). Le schéma tools **est** le catalogue.
2. Bloc « Assistante » en tête : comprendre, agir, proposer, une seule question si vraiment bloquée, jamais un formulaire.
3. Bloc « Après une action » : confirmer clairement + une suite possible.
4. Bump cache. Températures : garder 0.5 tools / 0.7 conversation (déjà Vague C).

### Vague G7 — Recette vocale + télémétrie

Sans nouvelle UI globale.

1. Logs structurés : `tool`, `rounds`, `pending_shown`, `suggestions_count`, `takeover` (doit rester à 0).
2. Parcours directeur primaire (compte Artisant / `oyonoeffe09`) : effectifs → impayés → proposition → annonce → oui/non → changement de sujet.
3. Parcours collège+lycée : EDT + notes d’examen + switch.
4. Régression : tests `test_assistant_qualite` + `test_assistant_directeur_tools` (prepare/apply inchangés).

---

## 9. Ordre et dépendances

```
G0 audit (ici)
  → G1 takeover off          [bloque tout le ressenti]
    → G2 pending mince
      → G3 regex hors chemin
        → G4 suggestions
        → G5 multi-tools      (peut démarrer après G1 si besoin)
      → G6 prompt cache
        → G7 recette
```

G4 et G5 sont parallélisables après G2. G6 idéalement **avec** G1 (sinon le prompt dit « propose » pendant que le runtime coupe encore).

**Effort** : G1–G2 touchent surtout `assistant_consumer.py` + quelques tests. G3 est un ménage. G4 = consumer + `assistant_vocal.js` (cache-bust) + éventuellement un tool. G5 = une constante + prompt. G6 = texte + bump cache.

---

## 10. Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| Gemini applique sans oui | `apply` **jamais** exposé comme tool ; seul le consumer `confirm` l’appelle |
| Gemini invente un paiement / une classe | Tools only ; prompt « n’invente pas » déjà là ; prepare refuse si introuvable |
| Trop de rounds / latence | Plafond 8 + status `searching` déjà envoyé |
| Suggestions qui polluent la voix | Canal UI séparé ; prompt : ne pas les lire |
| Annonce moins « magique » sans wizard | `generate_written_draft` reste un tool/helper appelé **par** Gemini |
| Tests regex cassés | Les réécrire en tests d’outils + consumer (pending oui/non) |
| Personnel / caissier trop puissant | Schéma + `check_permission` inchangés |
| Enseignant primaire | Même consumer : G1–G2 l’aident ; ne pas élargir ses tools |

---

## 11. Recette d’interaction (quand G1–G6 seront faites)

À jouer **à la voix**, pas seulement en tests.

1. **Compréhension** — « Les deux premières classes, cite-moi dix élèves et les profs. » → noms, pas d’erreur rouge, pas de wizard.
2. **Action + proposition** — « Il y a des impayés en 6e A ? » → chiffres + « Je peux relancer ou ouvrir une fiche » + chips.
3. **Écriture confirmée** — « Envoie un blâme à Diallo pour retard. » → elle rédige la note, **demande** le oui, n’enregistre qu’après.
4. **Tâche complexe** — « Prépare la rentrée de la 3e A. » → elle enchaîne (effectifs, EDT, éventuellement brouillon d’annonce), pose au plus une question.
5. **Switch** — au milieu d’une carte : « Et la caisse du mois ? » → elle lâche, répond caisse.
6. **Nav + métier** — « Ouvre la 6e A et dis-moi les notes. » → page **et** oral.
7. **Merci + suite** — « Merci. Et les effectifs ? » → tools on, chiffres.

Critère subjectif (le vrai livrable) : **on a l’impression de parler à quelqu’un qui a accès à l’école et qui prend des initiatives**, pas de remplir un formulaire.

---

## 12. Hors scope (rappel)

- Comptabilité générale (flag False).
- Nouvelle vague de tools métier (EDT professeur, radiation, etc.) sauf trou bloquant constaté en recette.
- Changer de modèle (rester Gemini).
- Web Speech en sortie.
- Shell / VPS / SQL.
- Refonte UI de l’espace directeur (seulement JS/partial assistant si G4 l’exige, cache-bust).
- Persona enseignant : pas de nouveaux tools dans ces vagues.

---

## 13. Décision

**Validé** le 2026-09-23.

1. Gemini est le seul cerveau d’intention ; les tools Django sont les seules « commandes serveur ».
2. On **supprime** les wizards guidés (annonce, EDT, générique) au profit de Gemini + carte oui/non — G1 coupe le takeover ; G2 retirera les FSM du tour suivant.
3. Ordre : G1–G5 (**faites**) → G6 (prompt d’autonomie) puis G7. **Stop après G5.**
4. Pas de tools CG, pas de shell, pas d’`apply` sans confirmation.

**Stop** : G5 livrée. Ne pas démarrer G6 tant que le directeur n’a pas validé G5 en vocal.
