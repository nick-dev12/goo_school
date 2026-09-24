# Audit + feuille de route — Assistant IA Parent (conseil & suivi enfant)

**Date** : 2026-09-23  
**Statut** : **Par0–Par4 livrées** (2026-09-24). Par5+ **non démarrées**.  
**Branche** : `cursor/assistant-parent-par4-a40c`  
**Workspace** : `C:\wamp64\www\goo_school`  
**Références** :
- Directeur (tools, schéma, confirmation) : [audit_assistant_ia_directeur.md](audit_assistant_ia_directeur.md)
- Runtime Gemini libre (G1–G7) : [audit_assistant_ia_gemini_libre.md](audit_assistant_ia_gemini_libre.md)
- Professeur (UI 100 % pages, persona, vagues) : [audit_assistant_ia_professeur.md](audit_assistant_ia_professeur.md)

**Objectif utilisateur** : connecter Aria sur **toutes** les pages du **tableau de bord parent** et sur **toutes** les pages **élève** accessibles via le compte parent (consultation enfant en session). Persona orienté **conseil, orientation, efficacité au quotidien** — pas le pilotage d’établissement. L’assistant doit **comprendre et répondre en wolof** lorsque le parent s’exprime en wolof (oral ou écrit).

---

## 1. Verdict en une phrase

**Aucun assistant parent aujourd’hui** : le WebSocket refuse `Parent` / `Eleve`, il n’y a **aucun partial vocal** dans les templates parent/élève, et les ~100 outils existants sont calibrés **directeur / enseignant** — il faut un **persona `parent` dédié**, un **périmètre strict « mes enfants liés »**, un **catalogue de pages parent + élève**, et une **stratégie Wolof** (prompt + STT/TTS), en reprenant la stack post-G7 sans ouvrir les tools direction.

---

## 2. Périmètre produit (à ne pas diluer)

### 2.1 Ce que le parent doit vivre avec Aria

| Attendu | Exemples |
|---------|----------|
| **Comprendre la scolarité de l’enfant** | Notes, moyennes, bulletin, devoirs, EDT, absences, sanctions, convocations |
| **Anticiper l’organisation** | « Qu’est-ce qu’il a demain ? », « Quels devoirs cette semaine ? », « Prochaine échéance de paiement ? » |
| **Conseil & orientation** | Expliquer une moyenne, rassurer, proposer des routines (révisions, sommeil, communication avec l’école) — **sans remplacer le directeur ni le prof** |
| **Efficacité dans l’app** | Ouvrir la bonne page, résumer une annonce, rappeler une notification non lue |
| **Wolof** | Parent parle ou écrit en wolof → réponses **dans la même langue** (français si le parent repasse en français) |

### 2.2 Ce qui est hors persona (même si le LLM « sait »)

- Effectifs établissement, stats globales, caisse, RH, préinscriptions, liaisons **côté directeur**, examens session/créneaux, bulletins **publication**, paiements **enregistrement**, comptabilité générale, shell / VPS / SQL.
- Données d’**autres élèves** que ceux liés par `LienFamilial` (`statut='valide'`, `actif=True`).
- Actions qui contournent les vues Django (pas de paiement vocal « enregistré » si la vue parent ne le permet pas).

---

## 3. Architecture actuelle (stack assistant)

| Couche | Fichier | État pour le parent |
|--------|---------|---------------------|
| WebSocket | `school_admin/consumers/assistant_consumer.py` | `_resolve_etablissement` accepte `Etablissement`, `PersonnelAdministratif`, `Professeur` uniquement → **`Parent` / `Eleve` = refus** |
| Contexte | `build_assistant_context` (`assistant_tools.py`) | Conçu établissement + personnel/prof ; **pas** `parent`, **pas** `eleve_consulte_id` |
| LLM | `gemini_assistant_service.py` | Prompts directeur / enseignant ; **pas** `SYSTEM_PROMPT_PARENT` |
| Schéma | `assistant_schema.py`, caches Gemini | **Aucun** tool parent |
| UI | `static/.../directeur/assistant_vocal.js` + partials enseignant/directeur | **0** include dans `parent/*` ni `eleve/*` |
| STT | `stt_service.py` | `transcribe_pcm16(..., language='fr-FR')` **fixe** dans le consumer |
| TTS | `tts_service.py` | Gemini TTS + consigne **français** ; pas de branche wolof |
| Traduction page | `gtranslate_header_bar.html` sur **header élève** | Traduit le **DOM**, pas la voix Aria ; **ne remplace pas** le wolof conversationnel |

**Règle à conserver** (alignement directeur / prof / G7) : écritures sensibles → **brouillon → carte oui / modifier / annuler → apply** ; pas de takeover wizard qui coupe Gemini pour les **lectures** et les **conseils**.

---

## 4. Parcours utilisateur parent (session & sécurité)

### 4.1 Authentification

- Modèle : `Parent` (`school_admin/model/parent_model.py`), rattaché à un `Etablissement` (compte créé par l’établissement).
- Connexion : même portail `connexion_compte_user` que les autres profils (backend multi-modèles).

### 4.2 Deux modes dans l’app

| Mode | Session | Pages |
|------|---------|-------|
| **Hub parent** | Pas de `eleve_consulte_id` (ou effacé via `retour_selection_enfant`) | Espace `school_admin:…` (dashboard, scolarité agrégée, annonces, convocations, profil, notifications) |
| **Consultation enfant** | `eleve_consulte_id`, `mode_consultation_parent=True` (posé par `dashboard_enfant`) | Espace `eleve:…` (même UI que l’élève, flag `est_parent` dans les templates) |

Helper central : `get_eleve_from_request()` (`eleve_view.py`) — vérifie `LienFamilial` pour tout accès parent aux vues élève.

### 4.3 Implications assistant

- Le consumer doit lire **`eleve_consulte_id`** (session WS = session HTTP Django Channels).
- **Hub parent** : tools agrégés multi-enfants (`lister_mes_enfants`, scolarité par enfant, choix enfant).
- **Consultation enfant** : tools **scopés** à cet `eleve_id` ; refus explicite si l’ID n’est pas dans les liens valides.
- **`select_enfant` / `ouvrir_espace_enfant`** : équivalent vocal de `dashboard_enfant` (mise à jour session + éventuelle redirection via `ouvrir_page`).

---

## 5. Inventaire — URLs & vues Django

### 5.1 Espace parent (`school_admin/personal_url/parent_url.py`)

| Route | Vue | Template | Bottom nav | Rôle métier |
|-------|-----|----------|------------|-------------|
| `parent/dashboard/` | `dashboard_parent` | `parent/dashboard_parent.html` | Oui | Liste enfants, synthèse absences, dette scolarité, notifications récentes, formulaire liaison |
| `parent/enfant/<id>/` | `dashboard_enfant` | — (redirect) | — | Pose session → redirect `eleve:dashboard_eleve` |
| `parent/retour/` | `retour_selection_enfant` | — (redirect) | — | Efface consultation enfant |
| `parent/demande-liaison/` | `demande_liaison_enfant` | — (POST) | — | Liaison matricule + mot de passe élève (anti-brute-force) |
| `parent/annonces/` | `annonces_parent` | `annonces_parent.html` | Oui | Annonces `parents` / `tous`, multi-établissement si plusieurs enfants |
| `parent/notifications/` | `notifications_parent` | `notifications_parent.html` | Oui | Notifications parent ; purge après consultation |
| `parent/notifications/<id>/marquer-lue/` | `marquer_notification_parent` | — (POST) | — | Marquer lu |
| `parent/notifications/<id>/click/` | `notification_parent_click` | — (redirect) | — | Deep link |
| `parent/profil/` | `profil_parent` | `profil_parent.html` | Oui | Infos + **changement mot de passe** (POST Django) |
| `parent/convocations/` | `convocations_parent` | `convocations_parent.html` | Oui | Convocations tous enfants, filtres établissement |
| `parent/scolarite/` | `scolarite_parent` | `scolarite_parent.html` | Oui | Reste dû, échéances, reçus récents par enfant |
| `parent/scolarite/recu/<paiement_id>/` | `recu_paiement_parent` | `directeur/comptabilite/recu_paiement.html` | **Non** | Reçu PDF-like ; contrôle lien familial |
| `parent/deconnexion/` | `deconnexion_parent` | — | — | Logout |

**Templates parent** : 9 fichiers HTML (+ partials `bottom_nav_parent.html`, `navigation_panel.html`, `annee_scolaire_badge.html`).

**Nav parent (bottom)** : Accueil, Scolarité, Annonces, Convocations (responsive), Liaison, Profil, Retour enfant, Déconnexion, Menu overlay.

**Gap UI** : pas de lien bottom nav direct vers **notifications** (accessibles depuis le dashboard) — le catalogue `ouvrir_page` doit inclure `notifications_parent`.

### 5.2 Espace élève consulté par le parent (`eleve:` — `eleve_url.py`)

Toutes les vues ci-dessous passent par `get_eleve_from_request()` (parent **ou** élève connecté).

| Route | Vue | Template | Bottom nav | Notes parent |
|-------|-----|----------|------------|--------------|
| `eleve/dashboard/` | `dashboard_eleve` | `dashboard_eleve.html` | Oui | Moyenne, dernières notes, raccourcis ; header avec gtranslate |
| `eleve/devoirs/` | `devoirs_eleve` | `devoirs_eleve.html` | Oui | Exercices / devoirs |
| `eleve/bulletin/` | `bulletin_eleve` | `bulletin_eleve.html` ou `bulletin_eleve_superieur.html` | **Non** | Bulletin publié ; variante LMD |
| `eleve/emploi-du-temps/` | `emploi_du_temps_eleve` | `emploi_du_temps_eleve.html` | Oui | EDT classe active |
| `eleve/notes-evaluations/` | `notes_evaluations_eleve` | `notes_evaluations_eleve.html` | Oui | Primaire vs secondaire vs supérieur dans la vue |
| `eleve/absences-retards/` | `absences_retards_eleve` | `absences_retards_eleve.html` | Oui | Stats + listes récentes |
| `eleve/profil/` | `profil_eleve` | `profil_eleve.html` | Oui | **Lecture seule** |
| `eleve/sanctions/` | `sanctions_eleve` | `sanctions_eleve.html` | Oui | Discipline |
| `eleve/convocations/` | `convocations_eleve` | `convocations_eleve.html` | Oui | Convocations de **l’enfant courant** |
| `eleve/annonces/` | `annonces_eleve` | `annonces_eleve.html` | Oui | Annonces élèves/parents |
| `eleve/notifications/` | `notifications_eleve` | `notifications_eleve.html` | **Non** | Accès header cloche |
| `eleve/historique-annees/` | `historique_annees_eleve` | `historique_annees_eleve.html` | **Non** | Archives |
| `eleve/historique-annees/<annee_id>/` | `detail_historique_annee_eleve` | `historique_annee_detail_eleve.html` | **Non** | Détail archive |
| `eleve/deconnexion/` | `deconnexion_eleve` | — | — | Parent utilise plutôt `deconnexion_parent` |

**Templates élève** : 16 HTML (+ `partials/header.html`, `bottom_nav_eleve.html`).

**Particularité nav élève** : annonces / profil dans le bottom nav **conditionnels** (bloc `{% if request.resolver_match.url_name == 'annonces_eleve' %}`) — le menu « … » / header compense ; l’assistant doit quand même connaître toutes les clés.

### 5.3 Synthèse couverture UI cible

| Zone | Pages métier à couvrir | Stratégie widget (comme prof P6+) |
|------|------------------------|-----------------------------------|
| Parent | 8 écrans + reçu | Partial dans `bottom_nav_parent.html` **+** `dashboard_parent.html` (liaison modal) **+** reçu |
| Élève (parent) | 13 écrans + bulletin | Partial dans `bottom_nav_eleve.html` **+** `eleve/partials/header.html` **+** bulletin / historique / notifications |

Objectif : **100 %** des écrans où le parent passe du temps, pas seulement ceux avec bottom nav.

---

## 6. Inventaire fonctionnel (données exposées par les vues)

Domaines **déjà calculés** côté Django (sources de vérité pour les futurs tools) :

| Domaine | Vues / services | Modèles / remarques |
|---------|-----------------|---------------------|
| **Lien familial** | `dashboard_parent`, `demande_liaison_enfant` | `LienFamilial`, blocage tentatives liaison |
| **Notes & moyennes** | `dashboard_eleve`, `notes_evaluations_eleve`, `bulletin_eleve` | `Note` / `NotePrimaire`, `MoyennePeriode`, visibilité bulletin |
| **Devoirs** | `devoirs_eleve` | Exercices maison / devoirs selon type établissement |
| **Présences** | `absences_retards_eleve`, stats dashboard | `Presence` (présent, absent, absent_justifie, retard) — **pas** d’action parent « justifier » dans le code actuel |
| **Sanctions** | `sanctions_eleve` | `Sanction`, gravité, période |
| **Convocations** | `convocations_parent`, `convocations_eleve` | Agrégation multi-enfant vs enfant courant |
| **Annonces** | `annonces_parent`, `annonces_eleve` | `Annonce`, destinataires `parents` / `tous` / élèves |
| **Notifications** | `notifications_parent`, `notifications_eleve` | `NotificationParent`, notifications élève ; marquer lu (parent POST) |
| **Scolarité** | `scolarite_parent`, `dashboard_parent` | `resume_dette_eleve` (`recouvrement`), `PaiementEleve`, reçus |
| **EDT** | `emploi_du_temps_eleve` | EDT classe active (même logique que côté élève) |
| **Profil** | `profil_parent`, `profil_eleve` | Parent : mot de passe ; élève : lecture seule + parents liés |
| **Historique** | `historique_annees_eleve` | Années archivées, bulletins passés |

**Multi-établissement** : possible si enfants dans des établissements différents (annonces / convocations parent déjà gérés par `etablissement_id`). L’assistant doit **nommer l’enfant** ou l’établissement en cas d’ambiguïté.

**Type d’établissement de l’enfant** (pas celui du compte parent seul) : primaire (`NotePrimaire`), secondaire (`Note`), supérieur (bulletin LMD, libellé « étudiant ») — **filtrer le schéma** comme pour le prof, mais **par l’établissement de l’élève consulté**.

---

## 7. Écart vs outils directeur / enseignant

| Tool directeur (ex.) | Réutilisable tel quel ? | Version parent |
|----------------------|---------------------------|----------------|
| `get_notes_eleve` | **Non** (périmètre tout l’établissement) | `get_notes_enfant` — ORM limité aux IDs liés |
| `get_comptabilite` | **Non** | `get_scolarite_enfant` — `resume_dette_eleve` + derniers paiements |
| `get_presences` | **Non** | `get_absences_enfant` — stats + récent |
| `get_sanctions` | **Non** | `get_sanctions_enfant` |
| `get_emploi_du_temps` | **Non** (directeur choisit classe) | `get_emploi_enfant` — classe active inscription |
| `get_annonces` | **Non** | `get_annonces_parent` / filtre destinataires |
| `get_liaisons` | **Non** (vue directeur) | `get_mes_enfants` / statut liens |
| `rechercher_eleves` | **Interdit** | Remplacé par liste fermée des enfants liés |
| `ouvrir_page` | **Non** | Catalogue `assistant_pages_parent.py` + routes `eleve:` |
| Actions inscription / paiement / discipline | **Interdit** | Voir §8 |

---

## 8. Catalogue d’outils à créer (spec)

### 8.1 Persona & routing

- **`persona = 'parent'`** pour tout utilisateur `Parent` authentifié.
- **Option ultérieure** (hors vague 1) : persona `eleve` si connexion directe élève — **non demandé** pour la validation initiale ; les mêmes tools scopés pourraient servir les deux.
- Fichiers suggérés (miroir prof) :
  - `assistant_parent_scope.py` — résolution enfant(s), vérif lien, classe active, type établissement enfant
  - `assistant_parent_tools.py` — handlers lecture
  - `assistant_parent_actions.py` — écritures confirmées (peu nombreuses)
  - `assistant_pages_parent.py` — catalogue navigation
  - `assistant_parent_schema.py` — schéma Gemini filtré (`primary` / secondaire / `superieur` **de l’enfant**)
  - Extension `build_assistant_context(..., parent=, eleve_consulte=)`
  - Extension `_resolve_etablissement` : `Parent` → `etablissement` du parent + objet `parent` ; **etablissement effectif métier** = celui de l’enfant consulté quand pertinent

### 8.2 Lecture / navigation (priorité haute)

| Tool | Description | Alignement vue |
|------|-------------|----------------|
| `get_mes_enfants` | Liste {id, nom, classe, établissement, reste scolarité court} | `dashboard_parent` |
| `select_enfant` | Pose `eleve_consulte_id` (session) après vérif lien | `dashboard_enfant` |
| `get_resume_enfant` | Synthèse : moyenne, absences, prochain devoir, notif non lues | `dashboard_eleve` |
| `get_notes_enfant` | Notes + moyennes période (branche primaire / secondaire / sup.) | `notes_evaluations_eleve` |
| `get_bulletin_enfant` | État publication + moyenne générale (pas PDF binaire) | `bulletin_eleve` |
| `get_devoirs_enfant` | Devoirs à faire / récents | `devoirs_eleve` |
| `get_absences_enfant` | Totaux + derniers événements | `absences_retards_eleve` |
| `get_sanctions_enfant` | Liste + gravité | `sanctions_eleve` |
| `get_convocations_enfant` | À venir / passées (enfant courant ou param `eleve_id`) | `convocations_eleve` |
| `get_convocations_famille` | Tous enfants (hub parent) | `convocations_parent` |
| `get_annonces` | Filtre parent / élève + période | `annonces_*` |
| `get_notifications` | Non lues + récentes (type parent ou enfant) | `notifications_*` |
| `get_scolarite_enfant` | Reste, échéance, derniers reçus | `scolarite_parent` |
| `get_emploi_enfant` | Créneaux semaine | `emploi_du_temps_eleve` |
| `get_profil_parent` | Infos compte (sans mot de passe) | `profil_parent` |
| `lister_pages` / `ouvrir_page` | Nav parent + élève + reçu + bulletin | §5 |
| `ouvrir_recu` | URL reçu si paiement appartient à un enfant lié | `recu_paiement_parent` |
| `chercher_en_base` | Routeur lexical **parent** (pas effectifs établissement) | Pattern directeur |

### 8.3 Conseil (sans tool dédié obligatoire)

- **`conseil_scolaire`** n’a **pas** besoin d’un handler ORM : le **prompt parent** + résultats des tools de lecture suffisent.
- Option : tool **`get_conseils_contexte`** qui renvoie un JSON compact (moyenne, tendance absences, échéance paiement) pour alimenter le conseil — à trancher en Par2.

### 8.4 Écriture confirmée (priorité basse, strict)

| Action | Justification | Alignement |
|--------|---------------|------------|
| `marquer_notification_lue` | Déjà POST côté parent | `marquer_notification_parent` |
| `demande_liaison_enfant` | Sensibilité + rate limit | Reprendre validations `demande_liaison_enfant` |
| *(exclu vocal v1)* | `change_password` | Rester **formulaire** Django (`profil_parent`) — règle projet |

**Interdit** : enregistrer paiement, justifier absence, contacter prof (pas de messagerie), modifier notes, publier quoi que ce soit.

---

## 9. Wolof — détection, réponse, TTS

### 9.1 État actuel

- **Aucune** prise en charge wolof dans STT/TTS assistant.
- STT : Google Speech API v2 via `stt_service.py`, langue **fixée** à `fr-FR` dans `assistant_consumer.py`.
- TTS : consignes **français** (`tts_service.py`, voix Gemini `Zephyr` / Edge Charline).
- gtranslate sur header élève : **UI statique** uniquement ; indépendant de la conversation Aria.

### 9.2 Objectif

| Canal | Comportement cible |
|-------|-------------------|
| **Texte** (chat WS) | Gemini détecte wolof vs français ; répond **dans la langue du dernier message utilisateur** (code-switching autorisé). |
| **Voix entrante** | STT avec langue adaptative ou multi-pass ; si qualité wolof insuffisante, message explicite + invite saisie texte wolof |
| **Voix sortante** | TTS wolof lorsque la réponse est en wolof |

### 9.3 Stratégie technique proposée

1. **Prompt** (`SYSTEM_PROMPT_PARENT`) :
   - Rôle : accompagnatrice des familles sénégalaises ; ton simple, respectueux, **jamais condescendant**.
   - Consigne bilingue : « Si le parent parle wolof, réponds en wolof (latin ou alphabet adapté mobile). Si français, réponds en français. »
   - Interdiction de inventer des notes / paiements : **toujours** appeler un tool avant les chiffres.

2. **Détection langue** :
   - **Primaire** : confiance au modèle Gemini sur le texte utilisateur.
   - **Secours** : heuristique légère (mots courants wolof : « na nga def », « jërëjëf », « waaw », « déedéet », « xale », « école »…) pour choisir STT/TTS — **pas** de blocage regex métier.

3. **STT** :
   - Paramètre `language` dynamique : `fr-FR` par défaut ; tenter `wo-SN` ou locale Google supportée pour wolof si disponible au moment de l’implémentation.
   - Documenter fallback : **double transcription** (fr + wo) + choix Gemini si confiance basse — coût acceptable pour courtes utterances parent.

4. **TTS wolof** :
   - Branche Gemini TTS avec consigne « read aloud in Wolof » + voix compatible multilingue **ou** Edge voix à tester (`wo` si disponible).
   - Réutiliser le pipeline SSML / normalisation **sans** casser le français (détecter langue de la phrase avant `speak()`).

5. **Accessibilité** :
   - Sous-titres dans le panel assistant dans la **langue de réponse**.
   - Chip « Auto / FR / Wolof » (session navigateur + clé Django `aria_parent_lang`) — **Par3**.

6. **Tests recette wolof** (non automatisables à 100 %) :
   - Scénarios manuels : salutation, question notes, question paiement, conseil révisions.
   - Tests auto : mock texte wolof → assert `response_language` / pas d’appel tool hors périmètre.

### 9.4 Limites à assumer dans l’audit

- Qualité STT wolof **variable** selon API ; le produit doit rester **utilisable** (fallback texte).
- mélange wolof-français (**Wolof français**) est fréquent : le prompt doit l’accepter, pas forcer wolof pur.

---

## 10. UI & UX assistant parent

### 10.1 Partial proposé

- `school_admin/templates/school_admin/parent/partials/assistant_vocal_parent.html`
- Variante ou même partial avec `data-persona="parent"` sur espace élève (contexte `est_parent`).
- CSS : réutiliser `assistant_vocal.css` + fichier léger `assistant_vocal_parent.css` (couleurs ARIA `--primary`, `--success`).
- Sous-titre panel : « Assistante famille — conseils & suivi scolaire » (pas « directrice »).

### 10.2 Points d’inclusion

| Fichier | Raison |
|---------|--------|
| `parent/partials/bottom_nav_parent.html` | Couvre la majorité hub parent |
| `eleve/partials/bottom_nav_eleve.html` | Parcours enfant |
| `eleve/partials/header.html` | Notifications, bulletin, historique |
| `parent/dashboard_parent.html` | Page d’accueil sans partial ailleurs |
| `directeur/comptabilite/recu_paiement.html` | Condition `is_parent` — include conditionnel |
| `eleve/bulletin_eleve*.html`, `historique_*.html`, `notifications_eleve.html` | Sans bottom nav |

### 10.3 Comportement UX spécifique

- Si **aucun enfant lié** : Aria explique la **liaison** et propose `ouvrir_page` vers dashboard + guide vocal du formulaire.
- Si **plusieurs enfants** sans session enfant : toute question « ses notes » → demander **quel enfant** ou appeler `get_mes_enfants` + `select_enfant`.
- Chips suggestions (post-G7) : « Notes de ce trimestre », « Prochaine échéance », « Devoirs de la semaine », « Parler en wolof » (Par3).

---

## 11. Alignement Gemini libre (G1–G7)

| Capacité | Application parent |
|----------|-------------------|
| G1 — pas de takeover après **lecture** | Indispensable : la majorité des tours parent = `get_*` + conseil |
| G2 — pending intelligent | Liaison enfant = seule action multi-champs |
| G3 — regex pending minimales | Oui/non sur notifications |
| G4 — suggestions | Après lecture notes / scolarité / absences |
| G5 — multi-tools | Ex. « notes et absences de Fatou » en un tour |
| G6 — prompt autonomie | Prompt parent conseil, pas catalogue directeur |
| G7 — recette WS | Fichier `test_assistant_parent_ws.py` + qualité wolof smoke |

**Ne pas** réintroduire wizards EDT / annonce directeur dans le consumer pour le persona parent.

---

## 12. Particularités par type d’établissement (enfant consulté)

| Type enfant | Données | Tools |
|-------------|---------|-------|
| **Primaire** | `NotePrimaire`, évaluations primaire | Branche notes comme `eleve_view` |
| **Collège / lycée / mixte / collège+lycée** | `Note`, coefficients, périodes trimestre | Pas d’examens direction |
| **Supérieur** | Bulletin LMD, libellé étudiant, crédits si affichés | Schéma sans tools LMD **direction** ; lecture crédits/moyennes si vue élève les expose |

Le **parent.etablissement** peut différer de l’enfant dans des cas rares ; le scope doit toujours utiliser **`eleve.etablissement`**.

---

## 13. Feuille de route — vagues proposées

Chaque vague = livrable testable + mise à jour de ce fichier. **Ne pas démarrer sans validation utilisateur.**

### Vague Par0 — Cadrage & sécurité

- Persona WS `parent`, session `eleve_consulte_id`, refus `Eleve` seul (ou décision explicite d’inclure élève).
- `assistant_parent_scope.py` + tests scope (accès refusé élève non lié).
- Pas de UI.

### Vague Par1 — UI 100 % pages + WS connecté

- Partial vocal parent + includes (§10).
- Connexion WS sans tools (small talk + message d’accueil bilingue).
- Cache Gemini vide ou prompt minimal.

### Vague Par2 — Lecture socle + navigation

- Tools : `get_mes_enfants`, `select_enfant`, `get_resume_enfant`, `lister_pages`, `ouvrir_page`, `get_notifications`, `get_annonces`.
- Catalogue pages complet (§5).
- Tests handlers + pages.

### Vague Par3 — Wolof v1

- Prompt bilingue ; STT/TTS dynamique (§9).
- Recette manuelle wolof documentée.
- Chip préférence langue (optionnel).

### Vague Par4 — Suivi scolaire

- Tools : notes, devoirs, absences, sanctions, convocations, EDT, bulletin (lecture).
- Filtrage schéma par type établissement enfant.
- `spoken_from_parent_tool` + suggestions G4.

### Vague Par5 — Scolarité & multi-enfant

- Tools : `get_scolarite_enfant`, `ouvrir_recu`, agrégats hub parent (dette totale, prochaine échéance).
- Parité avec `resume_dette_eleve` / reçus.

### Vague Par6 — Parité G1–G7 persona parent

- Consumer : pas takeover sur lectures ; multi-tools ; tests `test_assistant_parent_ws.py`, `test_assistant_qualite.py` (persona parent).
- Cache `aria-parent-tools-v1`.

### Vague Par7 — Actions confirmées

- `marquer_notification_lue`, éventuellement `demande_liaison_enfant` (carte confirmation).
- **Pas** de paiement vocal.

### Vague Par8 — Recette multi-types & doc

- Jeu de tests : parent avec enfant primaire + secondaire + supérieur (fixtures).
- Mise à jour statut audit ; checklist métier (§14).

---

## 14. Hors scope (explicitement)

- Assistant **élève connecté seul** (sans passer par compte parent) — sauf décision ultérieure partage tools.
- Tools **directeur** : effectifs, caisse, RH, préinscriptions, validation liaisons, publication bulletins, examens, CG.
- Tools **enseignant** : saisie notes, présences, sanctions.
- **Shell**, SQL, déploiement VPS, `manage.py` arbitraire.
- **Paiement en ligne** ou enregistrement caisse par le parent via voix.
- **Justification d’absence** parent (fonctionnalité métier absente des vues).
- Messagerie directe prof/directeur (hors annonces / convocations existantes).
- Traduction gtranslate comme substitut au wolof **vocal** Aria.

---

## 15. Critères de validation métier

1. Parent connecté : bulle Aria visible sur **chaque** page listée §5 (hub + enfant + reçu + bulletin).
2. Question « Combien je dois pour l’école de X ? » → chiffres = tool scolarité, pas hallucination.
3. Question notes / absences **uniquement** pour enfants liés ; autre matricule → refus clair.
4. Parler wolof : réponse principale en wolof + TTS audible (ou message fallback honnête).
5. « Ouvre les devoirs » → navigation `eleve:devoirs_eleve` (session enfant valide).
6. Aucun tool directeur / caisse / effectifs dans le schéma parent (scan auto tests).
7. Écriture : notification marquée lue **seulement** après confirmation.

---

## 16. Synthèse pour validation utilisateur

| Sujet | Proposition |
|-------|-------------|
| Persona | **`parent`** unique ; scope **enfants liés** + session `eleve_consulte_id` |
| Philosophie | **Gemini = conseil + orchestration** ; Django tools = **vérité** notes / scolarité / vie scolaire |
| Pages | **~8 hub parent + ~13 élève + reçu + bulletin** — widget via bottom nav + header + cas particuliers |
| Tools neufs | **~18 lecture/nav** + **1–2 actions** confirmées ; pas de réexport directeur |
| Wolof | Prompt bilingue + STT/TTS adaptatif + fallback texte ; gtranslate **complémentaire** UI seulement |
| Vagues | **Par0–Par8** : sécurité → UI → lecture → wolof → scolarité → G7 → actions → recette |
| Prochaine étape | **Validation de cette feuille** puis implémentation **Par0** uniquement sur signal |

---

## 17. Compteurs (état au audit)

| Élément | Nombre |
|---------|--------|
| Routes parent (`parent_url.py`) | 13 (dont POST / redirect) |
| Écrans parent rendus | 8 + reçu partagé |
| Routes élève (`eleve_url.py`) | 14 |
| Écrans élève rendus | 13 |
| Templates parent / élève | 9 + 16 |
| Partials assistant parent | **1** (`assistant_vocal_parent.html`) |
| Tools assistant parent | **15** (Par2 navigation + Par4 suivi scolaire) |
| Tests assistant parent | **39+** (scope + tools + scolaire + Wolof + WS) |
| Personas WS acceptés | directeur, enseignant, enseignant_primaire, **`parent`** |

---

## 18. Livraison Par0 + Par1 (2026-09-24)

### Par0 — Sécurité / scope

- WebSocket : persona **`parent`**, refus **`Eleve`** seul.
- `assistant_parent_scope.py` : liens `LienFamilial`, session `eleve_consulte_id`, refus élève non lié.
- `execute_tool` → `execute_parent_tool` : blocage tools directeur/enseignant/CG ; schéma Gemini **vide**.
- `build_assistant_context(..., parent=)` + champs `eleve_consulte`, `enfants_lies`.
- Prompt `SYSTEM_PROMPT_PARENT` (conseil, bilingue, pas d’invention de chiffres).

### Par1 — UI + WS

- Widget sur hub parent (bottom nav), espace élève parent (bottom nav + pages sans nav : bulletin, historique, notifications, reçu).
- Accueil WS : `assistant.welcome` + TTS (`PARENT_WELCOME_BILINGUAL`) ; chat Gemini **sans tools** (`use_tools=False`).
- JS : accueil parent / `assistant.welcome` dans `assistant_vocal.js` v1.9.14.

### Par2 — Lecture socle + navigation (2026-09-24)

- Fichiers : `assistant_pages_parent.py`, extension `assistant_parent_tools.py` (7 tools).
- Tools : `get_mes_enfants`, `select_enfant`, `get_resume_enfant`, `get_annonces`, `get_notifications`, `lister_pages`, `ouvrir_page`.
- Gemini : schéma parent **uniquement** ces tools ; `use_tools=True` ; prompt mis à jour.
- Session : `select_enfant` pose `eleve_consulte_id` (fix `session or {}` côté consumer).
- Tests : `test_assistant_parent_tools.py` + extension scope/WS (**23** tests OK).

### Par3 — Wolof v1 (2026-09-24)

- `assistant_parent_language.py` : préférence `auto|fr|wo`, heuristiques wolof, choix STT/TTS.
- STT parent : `transcribe_pcm16_multi` (`fr-FR` + `wo-SN`) ; message bilingue si qualité wolof faible.
- TTS parent : `synthesize_audio(..., language='wo')` (consigne Gemini wolof + repli Edge `fr-SN-AissatouNeural`).
- Consumer : STT/chat avec `lang_pref` ; TTS dynamique par phrase ; `set_lang_pref` WS.
- UI : chips Auto / FR / Wolof (`assistant_vocal_parent.html`, JS v1.9.15).
- Tests : `test_assistant_parent_language.py` + extension WS STT.

#### Recette manuelle Wolof (Par3)

1. Connexion parent (hub ou espace enfant) → ouvrir Aria.
2. **Texte wolof** : « Na nga def? Wax ma ci sama xale. » → réponse surtout en wolof + voix (TTS wolof si non muet).
3. **Texte français** : « Quelles annonces pour les parents ? » → réponse FR + TTS français (directeur/enseignant inchangés ailleurs).
4. **Chip Wolof** + note vocale courte → si STT faible : message d’invite à **écrire** en wolof (pas d’envoi automatique du tour).
5. **Chip FR** : question wolof écrite → réponse attendue en **français** (préférence forcée).
6. Vérifier qu’aucun tool directeur n’est invoqué (conseil + tools Par2 seulement).

#### Limites STT wolof (Par3)

- Google Speech `wo-SN` : qualité **variable** (accent, bruit, code-switch).
- Double pass fr+wo : coût x2 sur courtes dictées parent uniquement.
- Fallback produit : saisie **texte** wolof recommandée si `stt_weak`.

### Par4 — Suivi scolaire (2026-09-24)

- Fichiers : `assistant_parent_scolaire.py`, `assistant_parent_schema.py`, extension `assistant_parent_tools.py`.
- **8 tools lecture** : `get_notes_enfant`, `get_bulletin_enfant`, `get_devoirs_enfant`, `get_absences_enfant`, `get_sanctions_enfant`, `get_convocations_enfant`, `get_convocations_famille`, `get_emploi_enfant`.
- Données alignées vues `eleve:*` (notes primaire / secondaire / supérieur, bulletin publié, présences, etc.).
- Schéma Gemini filtré via `get_parent_tools_schema(ctx)` — flags type établissement **de l’enfant** (`eleve_consulte` ou union enfants liés).
- `spoken_from_parent_tool` + `suggestions_after_parent_read` (G4 après lectures).
- Tests : `test_assistant_parent_scolaire.py` + MAJ scope/tools/WS.

#### Recette manuelle Par4

1. Parent + enfant lié en session → « Quelles notes publiées pour mon enfant ? » → chiffres via `get_notes_enfant`, pas d’invention.
2. « Devoirs cette semaine ? » → `get_devoirs_enfant` + suggestion ouvrir page devoirs.
3. « Combien d’absences ? » → `get_absences_enfant`.
4. Hub sans session enfant → « Convocations de la famille ? » → `get_convocations_famille`.
5. `eleve_id` d’un autre élève → refus `acces_refuse`.

### Prochaine étape

**Par5** — scolarité (reste dû, reçus, montants) sur signal. **Par6+** G7 persona : non démarrés.

---

*Stop après Par4 — pas de Par5 dans cette livraison.*
