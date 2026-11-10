# Design des onglets — composant unique

Un seul composant pour **tout le SI**. Modifier le HTML ou le CSS ici change toutes les pages qui l’utilisent.

## Fichiers (source de vérité)

| Rôle | Fichier |
|---|---|
| HTML | `templates/school_admin/partials/aria_filter_tabs.html` |
| Une rangée | `templates/school_admin/partials/aria_filter_tab_group.html` |
| Tag Django | `{% load aria_tabs %}` → `{% aria_prof_filters %}` / `{% aria_filter_tabs groups=… %}` |
| CSS | `static/school_admin/css/shared/aria_filter_tabs.css` |
| Règle Cursor | `.cursor/rules/design-onglets.mdc` |

Ne pas recopier le HTML des pastilles dans une page. Ne pas créer `.ex-switch`, barre pleine largeur, ni un second CSS d’onglets.

## Direction

Les pages direction chargent `aria_filter_tabs.css` + `js/shared/aria_direction_tabs.js` via `header_directeur.html`.  
Le script enveloppe toutes les barres (`.matiere-tabs-bar`, `.fe-tabs`, `.adm-onglets`, `.ele-classe-nav`, etc.) dans le composant.  
`tabs_nav_overflow.css` reprend les mêmes pastilles (pas de soulignement secondaire).  
Changer le CSS du composant suffit : ne pas recréer un style d’onglets dans un CSS de page.

## Usage professeur (période / classe / matières)

```django
{% load aria_tabs %}
{% aria_prof_filters %}
```

Options :

- `show_periodes`, `show_classes`, `show_matieres` : `True` / `False` (sinon auto)
- `search_placeholder` + `search_target` : champ recherche dans la rangée Classe
- `classe_url_name` : URL nommée pour changer de classe (ex. appel)
- `preserve` : paramètres GET à garder (`periode,classe,matiere,vue,onglet,appel`)

## Usage générique (groupes déjà construits)

```django
{% load aria_tabs %}
{% aria_filter_tabs groups=mes_groupes %}
```

Chaque groupe : `{kind, label, items:[{label, href, active, count}]}`.  
`kind` : `period` (ambre) · `class` (bleu) · `subject` (violet) · `view` (teal).

## Forme

Hauteur `2.05rem`, largeur `auto`, padding `0 0.7rem`, rayon `8px`, police `0.75rem` / `600`.  
Liens GET Django. JS seulement pour overflow **Plus**. Pas de dégradé.

## Interdit

`width: 100%`, `flex: 1`, `.ex-switch`, HTML d’onglets recopié page par page.
