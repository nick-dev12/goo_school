# Design des listes — espace enseignant

Source de vérité pour **transformer tout ancien tableau** de l’espace professeur en liste colonnes, et pour **créer** un relevé / une liste d’élèves.

Règle Cursor : `.cursor/rules/design-listes-enseignant.mdc`  
Index : `school_admin/static/school_admin/css/enseignant/README.md`  
CSS : `school_admin/static/school_admin/css/enseignant/prof_notes_list.css`  
JS (onglets notes) : `school_admin/static/school_admin/js/enseignant/prof_notes_list.js`  
Référence HTML : `school_admin/templates/school_admin/enseignant/partials/notes_releve_list.html`

S’applique à **tous les types d’établissement** (primaire, collège, lycée, supérieur) et à **toutes les pages professeur** qui affichent des lignes d’élèves (notes, relevés, élèves en difficulté, justifications, présence, liste d’élèves). Adapter les **colonnes** à la structure de données de la page, pas le principe visuel.

---

## 1. Principe final (obligatoire)

1. **Pas de `<table>` HTML** dans l’UI écran professeur (notes, relevés, élèves, justifications, présence).
2. **Pas de cartes empilées** sur mobile. Même structure en colonnes que sur PC, sur **tous les écrans**.
3. Une **ligne = un élève**. CSS Grid, pas de tableau.
4. **Numéro** (`forloop.counter`) = **colonne tout à gauche**, jamais collé au nom.
5. **Nom compact** : `~0.81rem` mobile, `~0.88rem` tablette, `~0.9rem` PC. Nom en `uppercase` + prénom, `nowrap`.
6. **PC (≥ 1025px)** : afficher **toutes** les colonnes de la page. Pas d’onglets pour masquer des colonnes. Scroll horizontal seulement si la largeur PC ne suffit vraiment pas.
   **Mobile / tablette (≤ 1024px) uniquement** : s’il n’y a pas assez de place, **ne pas empiler en cartes** — créer un **système d’onglets** au-dessus de la liste. Chaque onglet n’affiche que les colonnes utiles (identité élève + la donnée choisie). **Ne jamais appliquer ce mode onglets sur PC** : ça éviterait d’afficher le tableau complet. Exemple hub Classe mobile : liste par défaut = n° · Élève · Sexe · Actions ; onglets **Absences** / **Sanctions**. JS uniquement pour afficher / masquer (`data-view`). Même principe que Moyenne / onglets d’évaluation du relevé Notes.
7. Formulaires : `action` Django. JS **uniquement** pour onglets, overflow, infobulle, afficher/masquer.
8. **Pas de dégradé CSS.** Jetons : `.cursor/rules/code-couleur-de-app.mdc`.
9. Templates Django **autonomes** (pas de `base.html`).
10. Pages **impression / PDF** : les `<table>` restent autorisés.

Ne pas recréer `.repartition-container` (barre « Répartition des moyennes ») dans le relevé Notes.

---

## 2. Anatomie d’une liste

```html
<div class="notes-eval-block" data-view="eval">  <!-- data-view seulement si onglets notes -->
  <!-- barre d’outils propre à la page (Moyenne + onglets, ou rien) -->

  <div class="notes-list" role="list">
    <div class="notes-list-head">
      <span class="notes-list-head__index" aria-hidden="true"></span>
      <span class="notes-list-head__eleve">Élève</span>
      <!-- ensuite : colonnes métier de LA page -->
    </div>

    {% for item in lignes %}
    <article class="notes-list-row" role="listitem">
      <span class="notes-list-row__index">{{ forloop.counter }}</span>
      <div class="notes-list-row__eleve">
        <div class="notes-list-row__name">
          <span class="nom">{{ item.eleve.nom|upper }}</span>
          <span class="prenom">{{ item.eleve.prenom }}</span>
        </div>
      </div>
      <!-- cellules alignées sur le head -->
    </article>
    {% empty %}
    <p class="notes-list-empty">Aucun élève</p>
    {% endfor %}
  </div>
</div>
```

Chaque **enfant direct** de `.notes-list-head` et de `.notes-list-row` occupe **une colonne** de la grille. Le `grid-template-columns` doit avoir **autant de pistes que d’enfants visibles**.

Index **hors** de `.notes-list-row__eleve` (frère, pas enfant).

`{% load notes_tags %}` dans **chaque** partial inclus (`get_item`, `get_note_color_class`, `evals_incluses_moyenne`).

---

## 3. Relevé Notes (approche canonique)

Fichiers :

| Rôle | Lycée / collège / supérieur | Primaire |
|---|---|---|
| Onglets | `enseignant/partials/notes_eval_tabs.html` | `enseignant/primaire/partials/notes_eval_tabs_primaire.html` |
| Liste | `enseignant/partials/notes_releve_list.html` | `enseignant/primaire/partials/notes_releve_list_primaire.html` |

### 3.1 Barre sous les stats de classe

Ordre **fixe** :

1. Bouton **Moyenne** (vert `#10b981`) — `data-view="moyenne"`
2. **Onglets d’évaluation** (violet `#7c3aed`) — un bouton par devoir, overflow `matiere-tabs-bar` + `tabs_nav_overflow.js`

Pas de bouton « Évaluation ». Pas de bouton « Vue globale ». Pas de barre de répartition des moyennes.

Clic **Moyenne** → `data-view="moyenne"`.  
Clic **onglet devoir** → `data-view="eval"` + `data-eval-id`.

### 3.2 Vue devoir (`data-view="eval"`)

Colonnes visibles : **n° · Élève · Devoir · Note**

- Une seule évaluation à la fois.
- Cellules `.notes-list-row__devoir` / `__note` avec `data-eval-id` ; seule `.is-active` est affichée.
- Titre de devoir : 2 lignes max, tap = infobulle (JS).
- Note colorée + `/barème`. Classes : `note-faible` / `note-moyenne-faible` / `note-bonne` / `note-excellente` (`get_note_color_class`).

### 3.3 Vue moyenne (`data-view="moyenne"`)

Colonnes : **n° · Élève · chiffres des notes retenues · Moy.**

- Uniquement les évaluations **incluses dans le calcul** (`evaluations_utilisees` via filtre `evals_incluses_moyenne`). Si aucune moyenne calculée : toutes les évaluations, Moy. = `—`.
- Chiffres seuls (pas `/barème`).
- `--moy-n` sur `.notes-list` pour la grille.

### 3.4 Données — collège / lycée / supérieur

Contexte : `classe_data` (boucle des classes du hub Notes).

| Besoin | Chemin |
|---|---|
| Élèves | `classe_data.eleves` → `eleve_data.eleve` |
| Évaluations | `classe_data.evaluations` → `eval_item.evaluation.id` / `.titre` / `.bareme` |
| Note d’un devoir | `eleve_data.notes\|get_item:eval_id` (objet `Note`) |
| Examen | `classe_data.has_examen`, `eleve_data.note_examen` (`data-eval-id="examen"`) |
| Moyenne | `eleve_data.moyenne.moyenne`, `eleve_data.moyenne.evaluations_utilisees` |

Partial : `{% include 'school_admin/enseignant/partials/notes_releve_list.html' %}`

### 3.5 Données — primaire (une matière)

| Besoin | Chemin |
|---|---|
| Élèves | `releve_data` → `data.eleve` |
| Évaluations | `evaluations_matiere` → `eval.id` / `eval.type_label` / `eval.bareme` |
| Note | `data.notes_evaluations\|get_item:eval.id` → `.note_obj` |
| Moyenne | `data.moyenne` (nombre) |

Partial : `notes_releve_list_primaire.html`

### 3.6 Données — relevé complet primaire (toutes matières)

Pas d’onglets par devoir. Colonnes : **n° · Élève · une colonne chiffrée par matière**.

| Besoin | Chemin |
|---|---|
| Matières | `matieres_releve_complet` (`.nom`, `.code`) |
| Lignes | `resultats_releve_complet` |
| Moyenne matière | `result.moyennes_par_matiere\|get_item:matiere.code` |

Classe : `.notes-list.notes-list--complet`. Index toujours colonne gauche.

---

## 4. Autres pages — mapper les colonnes, garder la même liste

Quand on touche une de ces pages, **remplacer le `<table>`** par `.notes-list` / `.notes-list-row`. Réutiliser `prof_notes_list.css`. Ne pas inventer un second système.

### 4.1 Élèves en difficulté

Données souvent identiques à Notes (`classe_data.eleves`, `.evaluations`, `.moyenne`).

Colonnes conseillées : **n° · Élève · notes (vue Moyenne ou onglets) · Moy. · Appréciation**  
`eleve_data.moyenne.appreciation` si présent. Pas d’avatar. Pas de dégradé.

Fichiers typiques : `eleves_en_difficulte_enseignant_hub_panel.html`, `eleves_en_difficulte_primaire_hub_panel.html`

### 4.2 Justifications de notes

Même `classe_data.evaluations` / `eleve_data.notes` (souvent `{note, justification}`).

Colonnes : **n° · Élève · une colonne chiffrée par évaluation** (comme vue moyenne) **· Justification · Action**  
Actions = boutons Django (`<a>` / `<form action>`), largeur du texte (voir README-DESIGN-BOUTONS).

### 4.3 Liste des élèves (hub Classe)

`eleves_classe_entry` / `cd.eleves`.

**PC (≥ 1025px)** — tout le tableau, **sans onglets** :  
**n° · Élève · Sexe · Absences · Sanctions · Actions**.

**Mobile / tablette (≤ 1024px) seulement** — onglets au-dessus de la liste (pas sur PC) :  
vue **liste** (défaut) : n° · Élève · Sexe · Actions ; **Absences** → n° · Élève · Sexe · Absences ; **Sanctions** → n° · Élève · Sexe · Sanctions.  
Recliquer l’onglet actif revient à la vue liste.

Nom : même `.notes-list-row__name`. Sexe : **Fille** / **Garçon**. Pas d’avatar. Boutons Profil / Sanction compact (`~1.45rem`).

### 4.4 Présence

**Hub** (`cd.eleves` avec compteurs) : **n° · Élève · Présences · Absences · Retards · Jours · Actions**  
Chiffres centrés, nom à gauche.

**Faire l’appel** (`liste_presence_*`, tous types) : **n° · Élève · Présent · Absent**  
Radios Django (`name="presence_{id}"`). Pas de `<table>`, pas d’avatar, pas de dégradé. Même grille sur tous les écrans. CSS : `.notes-list--appel` + `prof_presence_appel.css`.

### 4.5 Saisie des notes (`noter_eleves`)

**Tableau HTML d’origine** (`notation-table`) : élève, champ note, moyenne, badges retenue.
**Onglets par devoir** au-dessus : une seule colonne d’évaluation visible à la fois (Élève · devoir choisi · Moy.).
Les inputs restent dans le formulaire Django (`name="note_{eleve}_{key}"`). Carte « Calcul de la moyenne » inchangée.

### 4.6 Impression

`imprimer_releve_*.html`, `imprimer_tableau_presence.html` : **tableaux HTML conservés**.

---

## 5. CSS — grille

Toujours :

```css
.notes-list-head,
.notes-list-row {
  display: grid;
  align-items: center;
  column-gap: 0.45rem;
}
```

Exemples (à caler sur le **nombre réel** de colonnes visibles) :

| Vue | Grille |
|---|---|
| Devoir (n° + élève + devoir + note) | `1.4rem minmax(7rem, 1.5fr) minmax(6.25rem, 1.2fr) 4.5rem` |
| Moyenne (n° + élève + N notes + moy) | `1.4rem minmax(7rem, 1.3fr) repeat(var(--moy-n, 0), minmax(2.45rem, 1fr)) 3.4rem` |
| Liste élèves / présence | `1.4rem minmax(7rem, 1.4fr)` puis `minmax(3.5rem, 1fr)` par champ |

`.notes-list { overflow-x: auto; }`  
Cellules masquées : `display: none` pour qu’elles **ne prennent pas** de piste grid.

Couleurs notes : `#dc2626` / `#ea580c` / `#2563eb` / `#059669`.  
Onglets devoirs : `#7c3aed`. Bouton Moyenne : `#10b981`. Index : `#9ca3af`.

---

## 6. JS

- `prof_notes_list.js` : changement `data-view`, `.is-active` sur `data-eval-id`, infobulle titre, `layoutTabsOverflowNav()`.
- Écouter `prof-hub-panel-loaded` (hub XHR).
- Overflow onglets : `tabs_nav_overflow.js`. Le bouton Moyenne a `data-tabs-overflow="off"` pour **ne pas** être avalé par l’overflow.
- `{% load notes_tags %}` dans chaque include. Assets : `prof_notes_list.css` + `.js` (bumps `?v=`).

---

## 7. Checklist agent (toute page professeur avec lignes d’élèves)

1. Identifier le **queryset / dict** de la page (tableau ci-dessus).
2. Remplacer `<table class="releve-table">` (ou équivalent) par `.notes-list`.
3. Colonnes = champs déjà affichés, **plus** n° à gauche et nom compact.
4. Mobile = **mêmes colonnes** + scroll horizontal si besoin. Pas de cartes.
5. Notes : onglets par évaluation + bouton Moyenne, comme le relevé Notes.
6. Pas d’avatars, pas de dégradé, pas de JS de formulaire.
7. Impression : ne pas convertir.
8. Vérifier mobile (~390) et tablette (~768 / 1024).

Référence visuelle : hub Notes, `notes_releve_list.html`.
