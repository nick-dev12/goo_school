# Audit qualité assistant IA (contexte + voix)

**Date** : 2026-09-23  
**Périmètre** : diagnostic + **Vagues A, B, C et D implémentées** (2026-09-23).  
**Persona** : directeur (enseignant primaire hors scope sauf mention).  
**Fichiers lus / touchés** : `gemini_assistant_service.py`, `assistant_consumer.py`, `tts_service.py`, `assistant_intents.py`, `gemini_context_cache.py`, `assistant_vocal.js`, `school/settings.py`.  
**Branche A+B** : `cursor/assistant-qualite-ab-a40c`. Tests : `school_admin/tests/test_assistant_qualite.py`.  
**Suite (Gemini libre, spec seule)** : [audit_assistant_ia_gemini_libre.md](audit_assistant_ia_gemini_libre.md) — retirer les wizards, laisser Gemini exécuter les tools et proposer.

---

## 1. Verdict en une phrase

Gemini **est bien branché** (LLM + tools + TTS). L’assistante **n’est pas « bête »** : le prompt demande déjà de suivre le dernier message. En revanche le **runtime intercepte trop** (actions en attente, regex locales) et le **TTS phrase-par-phrase casse** : la première phrase parle, les suivantes arrivent souvent **sans audio** alors que le texte continue.

**État 2026-09-23** : **A+B+C+D faites**. Causes C1–C12 traitées (C12 = amorce neutralisée, pas réactivée).

---

## 2. Pipeline réel (aujourd’hui)

```
UI (assistant_vocal.js)
  → WebSocket chat | stt | restore_history | stop | confirm/cancel
Consumer (assistant_consumer.py)
  1. pending_action (session Django) ? → _route_pending_reply (regex, parfois Gemini)
  2. sinon intents locaux (annonce / EDT / CRUD / ouvrir page) → BYPASS Gemini
  3. sinon run_assistant_turn (Gemini)
       • défaut : cache native google.genai + tools
       • repli : API OpenAI-compat Gemini (ou DeepSeek si flag)
  4. texte → SentenceAssembler → synthesize_audio (Gemini TTS, 14 s)
  5. WS audio_sentence + text_delta
JS : file audioQueue, typewriter synchro ou fallback texte seul
```

**Gemini est utilisé pour** : réponse métier (sauf intents locaux), tools, classification `continue`/`switch` (cas « ask »), rédaction d’annonce, TTS.  
**Gemini n’est pas utilisé pour** : beaucoup d’ouvertures de pages, annonces guidées, EDT guidé, intents CRUD regex, small-talk (tools coupés).  
**Web Speech API** : **non utilisée** en sortie. Entrée = STT maison (`stt` PCM16). Sortie = Gemini TTS (WAV), pas `speechSynthesis`.

Réglages (`school/settings.py`) :

| Clé | Défaut | Effet |
|-----|--------|--------|
| `ASSISTANT_LLM_PROVIDER` | `gemini` | LLM |
| `GEMINI_MODEL` | `gemini-3.6-flash` | + fallbacks 3 / 3.6 |
| `GEMINI_CONTEXT_CACHE` | true | tour **non streamé** |
| `ASSISTANT_TTS_BACKEND` | `gemini` | `gemini-2.5-flash-preview-tts` |
| `ASSISTANT_TTS_FALLBACK_EDGE` | **false** (setting inchangé) | **A+B** : le repli Edge n’est plus gated par ce flag ; Gemini vide → Edge par phrase |
| `TTS_TIMEOUT_SECONDS` | **25** (était 14) | dans `tts_service.py` |

---

## 3. Contexte : est-elle intelligente ? Suit-elle le sujet ?

### 3.1 Ce qui va dans le bon sens

- Le prompt directeur dit déjà : *dernier message prioritaire*, *changer de sujet = abandonner l’ancienne action*, *ne pas ramener la conversation*.
- Historique envoyé : **24 messages** (`MAX_HISTORY_MESSAGES`) ≈ 12 tours. Ni trop court ni monstrueux.
- `sanitize_dialog_messages` fusionne les `user`/`assistant` consécutifs (retries UI).
- Restauration WS : le JS renvoie le log `sessionStorage` (`restore_history`, troncature 2000 car./message).
- `classify_pending_intent` (Gemini, `temperature=0`) tranche `continue` / `switch` **si** le routeur regex rend `ask`, et **en cas de doute → switch**.

### 3.2 Pourquoi elle « reste coincée » sur l’ancien sujet

Ce n’est **pas** surtout une fenêtre d’historique trop longue. C’est un **garde-fou d’action en attente** trop gourmand, **avant** Gemini.

1. **EDT / créneau : tout le tour suivant est avalé**  
   Dans `_route_pending_reply`, si `pending` = `creer_emploi_du_temps` ou `ajouter_creneau_emploi` :
   - « oui » → confirme ;
   - **sinon → `_continue_emploi_guidee` sans aucun `decide_pending_reply`**.  
   « Quelles sont les notes de la 1ère S ? » pendant un EDT en cours **n’atteint jamais Gemini**. Elle continue l’emploi du temps.

2. **Annonce guidée** : un peu mieux (champ / vague / oui), mais le reste tombe sur `decide_pending_reply`. `TOPIC_SWITCH_RE` ne reconnaît que des formules explicites (`en fait`, `autre chose`, `oublie`, `on change`…). Une question naturelle sans *combien / qui / quel / est-ce que* n’est **pas** un switch automatique.

3. **`NEW_QUESTION_RE` trop étroit**  
   Un switch n’est détecté que si la phrase **commence** par combien, qui, quand, où, pourquoi, comment, quel, est-ce que, peux-tu, dis-moi…  
   « Donne-moi les effectifs », « Fiche de scolarité de Diallo », « Liste les impayés » → souvent `ask` ou, pire, **continue** (EDT).

4. **`pending_action` survit à la coupure WS**  
   `disconnect` vide `self.history` mais **garde `aria_pending` en session**. Au reconnect : carte de confirmation + routage de l’ancienne action, alors que l’utilisateur pose déjà autre chose.

5. **Intents locaux avant Gemini** (`_handle_local_intent`)  
   Regex annonce / EDT / CRUD / ouvrir page. Une phrase mal classée (ex. « ajoute un créneau… » hors examen) **court-circuite** le modèle. L’IA « n’écoute pas » : ce n’est pas elle qui parle.

6. **Résultats d’outils absents de l’historique**  
   `self.history` = uniquement user + phrase orale. Les JSON tools du tour N **ne sont pas** renvoyés au tour N+1. Gemini n’a que ce qu’elle a *dit*. Risque : re-citer un chiffre oral ou rappeler l’ancienne action plutôt que relire la base.

7. **Faux tour « contexte établissement »**  
   Le chemin cache injecte un user/model factice (`Contexte établissement (JSON)` / `Contexte reçu.`) **avant** le dialogue. Ça dilue le « dernier message = la tâche ».

8. **Chemin cache : pas de stream, pas de `temperature`**  
   `generate_content` cache : réponse **d’un bloc**, config sans température (défaut Gemini ~1.0). Le prompt topic-switch n’est pas renforcé côté API (`system_instruction` figée dans le cache v9).

9. **Small-talk = tools off**  
   `is_small_talk` coupe les outils. Un « merci et les effectifs ? » mal matche peut répondre sans base.

10. **`_handle_chat` ne envoie pas `done` si ça réussit**  
    Choix + historique, **pas** de `type: done`. Le front reste `busy` (« Aria réfléchit… ») après la voix. Sensation : elle n’a pas « fini », donc on a l’impression qu’elle rumine l’ancien sujet.

### 3.3 Historique : trop court ou trop long ?

- **24 messages : OK** pour du vocal. Ce n’est pas la cause principale.
- Le vrai bruit : **pending session** + **dernière réponse orale** (annonce / confirmation) qui pèse plus que la nouvelle question, parce que le routeur n’atteint pas le LLM.
- Tronquer à 8–12 messages **sans** corriger le pending ne réglera pas le changement de sujet.

---

## 4. Voix : ça parle, puis plus rien, le texte continue

### 4.1 Symptôme expliqué par le code

Le texte affiché **n’est pas** le `text_delta` en live. Le JS **accumule** `pendingDelta` et n’affiche que via `audio_sentence` (`enqueueSentence` → typewriter).

Donc :

- phrase 1 : `audio_base64` plein → `Audio.play()` → on entend, le texte suit ;
- phrases 2…n : `audio_base64` **vide** → `voiceMuted || !item.src` → **typewriter sans son**.

C’est exactement : *la voix commence, puis plus rien, le texte continue*.

### 4.2 Causes audio (par gravité)

1. **TTS en rafale parallèle + timeout 14 s, sans repli**  
   Chaque phrase lance `asyncio.create_task(synthesize_audio)` tout de suite. Chemin cache : **tout le texte arrive d’un coup** → 5–10 appels Gemini TTS simultanés.  
   Timeout 14 s → `None`. `ASSISTANT_TTS_FALLBACK_EDGE=false` → payload avec `audio_base64: ''`. Le consumer **envoie quand même** la phrase. Le JS tape le texte.

2. **Phrases trop longues pour 14 s**  
   `SentenceAssembler` : phrase `[.!?…]` ou **clause ≥ 70 car.** si pas de point. Une phrase orale de 200+ car. dépasse souvent 14 s de synthèse.

3. **Gemini TTS preview fragile**  
   `gemini-2.5-flash-preview-tts`, voix Zephyr. Échec / pas de `inline_data` → log warning, **silence**, pas d’erreur UI.

4. **Autoplay / `play()` rejeté**  
   `playAudioSafely` : 1 retry puis fallback typewriter. Si l’unlock (`audioUnlocked` + beep WAV) a raté (WS reconnect sans geste), **toute la file** après la 1ʳᵉ peut basculer en texte. La 1ʳᵉ a parfois passé grâce au clic micro/envoi.

5. **Course amorce / index TTS**  
   `_start_opening` existe encore mais **n’est plus appelé** (`_send_working_ack` n’envoie qu’un `status: working`). `_flush_tts_queue` appelle `_emit_opening()` (no-op si pas de task). Code mort, pas la cause actuelle — à ne pas réactiver tel quel (double voix).

6. **`done` manquant**  
   Après la dernière phrase, le tour Gemini ne clôt pas. `finishIfIdle` exige `pendingDone`. File vide + pas de `done` → statut bloqué « réfléchit », pas de reset propre.

7. **Ce n’est pas** : Web Speech coupé, mute persistant (sauf `localStorage` `MUTE_KEY`), ni un chunk unique trop gros côté *lecture* (le JS joue phrase par phrase). Le gros chunk est **côté génération TTS**.

### 4.3 Race texte vs parole

- `text_delta` (souvent **tout le paragraphe** d’un coup en cache) ≠ affichage.
- Affichage = `audio_sentence` uniquement.
- Si le 1er audio joue et les suivants sont vides : le texte « rattrape » en silence.  
- Si `done` arrive trop tôt (autres chemins `_speak_and_finish`) : `finishIfIdle` peut typer `pendingDelta` **en plus** → double texte. Sur le chemin cache principal, `done` n’arrive pas : plutôt **voix morte + busy**.

---

## 5. Objectif « IA très intuitive qui utilise vraiment Gemini »

Écart actuel :

| Attendu | Réalité |
|---------|---------|
| Elle comprend le **nouveau** sujet tout de suite | Pending EDT / regex avalent le message |
| Elle **cherche** en base | Oui si le tour Gemini a lieu ; non si intent local / small-talk |
| Voix continue et naturelle | 1ʳᵉ phrase OK, suite souvent muette |
| Conversation fluide | `done` manquant, pending session zombie |
| Un seul cerveau (Gemini) | Deux cerveaux : regex + LLM |

Le modèle **peut** être intuitif (prompt + tools v1–v6). Le **goulot** est le routeur et le TTS, pas l’absence de Gemini.

---

## 6. Causes probables (priorisées)

| # | Sujet | Cause | Gravité |
|---|--------|--------|---------|
| C1 | Voix | TTS parallèle + timeout 14 s + pas de repli → `audio_base64` vide | Haute |
| C2 | Voix | Chemin cache : texte entier d’un coup → N synthèses d’un coup | Haute |
| C3 | Contexte | Pending EDT/créneau **sans** test de changement de sujet | Haute |
| C4 | Contexte | `NEW_QUESTION_RE` / `TOPIC_SWITCH_RE` trop étroits | Haute |
| C5 | Contexte | `aria_pending` survit au reconnect | Haute |
| C6 | UX | `_handle_chat` succès **sans** `done` | Moyenne |
| C7 | Contexte | Intents locaux avant Gemini | Moyenne |
| C8 | Contexte | Tools absents de l’historique du tour suivant | Moyenne |
| C9 | Voix | Autoplay / play() → fallback texte silencieux | Moyenne |
| C10 | Qualité | Pas de température / stream sur le tour cache | Basse |
| C11 | Qualité | Faux tour « contexte reçu » | Basse |
| C12 | Voix | Code amorce (`_start_opening`) mort ; ne pas le relancer tel quel | Info |

---

## 7. Optimisations (spec, pas de code)

### 7.1 Quick wins (peu invasif)

1. **Toujours envoyer `done`** à la fin d’un tour réussi (`_handle_chat`), comme `_speak_and_finish`.
2. **TTS séquentiel** (ou parallélisme 2 max) : attendre la phrase *n* avant de lancer *n+1*. Coupe les timeouts / rate-limits.
3. **Si TTS = None** : soit repli Edge **pour cette phrase** (même si voix un peu différente, mieux que le silence), soit **ne pas** envoyer `audio_sentence` sans audio et typer depuis `text_delta` **avec** un log UI discret — aujourd’hui le silence est invisible.
4. **Allonger le timeout TTS** (14 → 25–30 s) **et** couper plus tôt (`SentenceAssembler` : max ~120–160 car. ou 2 virgules).
5. **Pending EDT** : passer par `decide_pending_reply` + `classify_pending_intent` (comme les autres writes). En cas de doute : **switch**.
6. **Élargir le switch** : impératifs métier (`donne-moi`, `liste`, `affiche`, `fiche de`, `notes de`, `impayés`, `effectifs`) + toute phrase qui matche un **autre** tool que l’action en cours.
7. **Reconnect** : si le nouveau `chat` n’est pas une confirmation/annulation, **dropper** `aria_pending` ou demander « On abandonne l’action en cours ? ».
8. **Unlock audio** à chaque envoi / micro, pas seulement au 1er geste.

### 7.2 Fond (intuitivité Gemini)

1. **Un seul juge de sujet** : Gemini `classify_pending_intent` **avant** tout continue d’annonce/EDT/CRUD, dès que le message n’est pas oui/non/champ évident. Regex = filet, pas portier.
2. **Réduire les bypass locaux** aux cas 100 % sûrs (ouvrir « tableau de bord », oui/non). Le reste : tools Gemini (déjà là).
3. **Stream du tour cache** (`generate_content_stream`) pour TTS au fil de l’eau — aujourd’hui le cache **interdit** le vrai stream.
4. **Historique** : garder 8–12 tours **parlés** +, pour le *dernier* tour seulement, un résumé compact du dernier tool (chiffres), pas tout le JSON. Ne pas réinjecter 24 tours de tools.
5. **Renforcer le cache prompt** (bump `aria-directeur-tools-v10`) : *« Si le dernier message n’est pas une réponse à la question que TU viens de poser, ignore l’historique métier et réponds à CE message. »*
6. **Température** ~0.4–0.6 sur le tour outils (moins de divagation), 0.7 sur le small-talk.
7. **Retirer le faux échange** « Contexte reçu » ; passer le snapshot en `system` overlay hors cache (déjà le cas côté OpenAI-compat via `build_system_message`).
8. **Télémetrie** : loguer `tts_ok/tts_fail` par phrase, `pending_name` + `decision`, `done` émis ou non. Sans ça on débogue à l’oreille.

---

## 8. Plan de correction ordonné

À n’implémenter **que** sur feu vert. Une vague à la fois.

### Vague A — voix (quick) — **FAITE** (2026-09-23)

1. `done` systématique en fin de `_handle_chat` (succès, erreur LLM, `_speak_and_finish`).
2. Queue TTS **série** : `_flush_tts_queue` synthétise une phrase, l’émet, puis la suivante. Plus de N `synthesize_audio` d’un coup.
3. Timeout TTS **25 s** ; `SentenceAssembler` coupe vers **120–150 car.** ; log warning si audio vide.
4. Repli **Edge par phrase** dès que Gemini TTS est vide (plus gated par `ASSISTANT_TTS_FALLBACK_EDGE`). Si les deux échouent : `voice_failed: true` sur `audio_sentence` (le JS tape encore le texte ; plus de silence invisible).

**Test** : `school_admin.tests.test_assistant_qualite` (assembleur, flush séquentiel, fallback Edge). Recette vocale : « tableau de bord » — la voix doit tenir jusqu’à la dernière phrase ; statut « Prête ».

### Vague B — changement de sujet (quick) — **FAITE** (2026-09-23)

1. EDT/créneau : `_pending_decision` (`decide_pending_reply` + `classify_pending_intent` si `ask`). Switch → clear pending, le tour va à Gemini.
2. `NEW_QUESTION_RE` élargi (`donne-moi`, `liste`, `affiche`, `montre`) + `METIER_SWITCH_RE` (effectifs, impayés, scolarité, caisse, notes de la, CNSS…). `looks_like_new_topic` court-circuite aussi les wizards regex locaux (`_handle_local_intent`).
3. Premier chat après reconnect WS ≠ oui/non → drop `aria_pending` (`_socket_fresh`).

**Test unitaire** : EDT pending + « quels sont les effectifs ? » / « donne-moi les effectifs » → `switch`.  
**Test vocal** :  
- « Crée un emploi du temps pour la 1ère S. » → elle demande des précisions.  
- « Quels sont les effectifs ? » → **effectifs**, plus l’EDT.

### Vague C — Gemini vraiment au centre (fond) — **FAITE** (2026-09-23)

1. Bypass local réduit à la nav 100 % sûre (`ouvre` / `va sur`). Annonce, EDT, CRUD → tools Gemini. Pending : regex `switch` / continue évident (jour, horaire, champ) ; le reste → `classify_pending_intent`.
2. Cache : `generate_content_stream` (repli `generate_content`). Overlay snapshot + mémoire outil collés au **dernier** message user — plus de faux tour « Contexte reçu ».
3. `compact_tool_memory` (chiffres du dernier outil, ≤ 280 car.) pour le tour suivant seulement.
4. Cache prompt **`aria-directeur-tools-v10`**. Température 0.5 (outils) / 0.7 (small-talk).

**Test** : `QualiteCGeminiTests`. Recette : effectifs → notes 1ère S → CNSS d’un prof, sans « autre chose ».

### Vague D — polish voix (fond) — **FAITE** (2026-09-23)

1. `unlockAudio(true)` à chaque envoi / micro / choix ; `playAudioSafely` 3 tentatives.
2. Amorce vocale neutralisée (`_start_opening` no-op, plus d’`_emit_opening` dans la file TTS).
3. Affichage = `audio_sentence` uniquement. `text_delta` n’est tapé que s’il n’y a eu **aucune** phrase vocale (`receivedVoiceSentence`).

JS : `assistant_vocal.js?v=1.9.11`. Aucune vue globale nouvelle.

---

## 9. Hors scope de cet audit

- Nouvelle vague métier (Vague 7 CG, EDT prof, etc.).
- Changer de modèle (rester Gemini).
- Web Speech API en sortie (garder Gemini TTS ; Edge = secours).
- Persona enseignant primaire (même JS/consumer : les correctifs A/B l’aideront aussi).
- Tuning CosyVoice / SSML Charline (Edge n’est pas le moteur défaut).

---

## 10. Recette vocale (Vagues A+B)

**Contexte**

1. Lancer une action à confirmer (annonce ou EDT).  
2. Poser **sans lien** : « Quel est le taux de présence cette semaine ? »  
3. Attendu : elle **lâche** l’action, appelle le bon tool, répond à **cette** question.

**Voix**

1. « Donne-moi le tableau de bord. » (réponse longue).  
2. Attendu : parole **continue** jusqu’au bout ; le texte ne « dépasse » pas une voix morte ; statut « Prête » à la fin.

**Gemini**

1. Dans les logs : `generate_content` / cache hit, **pas** seulement un intent regex, pour les questions ouvertes.  
2. Tools visibles dans le consumer (`on_tool_result`) pour toute donnée chiffrée.
