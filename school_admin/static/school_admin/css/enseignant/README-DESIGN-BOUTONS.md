# Design des boutons — espace enseignant

Référence à suivre pour **toutes** les pages professeur (primaire, collège, lycée, mixte, supérieur).

Les puces d’action doivent ressembler aux onglets de filtre (classe / période), pas à des barres pleine largeur.

## Mesures

| Propriété | Valeur |
|---|---|
| Hauteur | `2.05rem` (≈ 33 px), identique aux onglets `.ovf-tab` / `.matiere-tab-btn` |
| Largeur | `auto` — uniquement la longueur du texte + icône + padding |
| Padding | `0 0.7rem` |
| Rayon | `8px` |
| Police | `0.75rem`, graisse `600` |
| Icône | `0.72rem`, écart `0.35rem` |
| Retour à la ligne du libellé | `white-space: nowrap` |

Interdit : `width: 100%`, `flex: 1`, `min-width` / `max-width` forcés (ex. 200 px), grille qui étire les boutons.

Sur mobile / tablette, les boutons **s’enveloppent** (`flex-wrap`) en gardant leur largeur naturelle. Ils ne s’étirent pas pour remplir la ligne.

## Variantes de couleur (jetons de l’app, **sans dégradé**)

| Usage | Fond | Texte | Bordure |
|---|---|---|---|
| Neutre (Modifier, Imprimer) | `#fff` | `#374151` | `#e5e7eb` |
| Primaire (Noter, action principale bleue) | `#3b82f6` | `#fff` | `#3b82f6` |
| Succès (Noter les élèves) | `#10b981` | `#fff` | `#10b981` |
| Info / fantôme (Voir relevé) | `rgba(59, 130, 246, 0.1)` | `#1d4ed8` | transparente |
| Danger (Supprimer, Élèves en difficulté) | `#ef4444` | `#fff` | `#ef4444` |

Hover : assombrir légèrement le fond, **sans** `transform` ni ombre.

## HTML

- Lien Django (`<a href="...">`) pour une navigation.
- `<button type="button">` seulement pour une action page (modal, suppression). Pas de JS pour envoyer un formulaire : `action` Django.
- Icône Font Awesome + libellé visible (pas d’icône seule, sauf exception tableau très dense).

```html
<div class="action-buttons">
  <a href="{% url 'enseignant:noter_eleves' classe.id %}" class="btn-action success">
    <i class="fas fa-edit"></i> Noter les élèves
  </a>
  <button type="button" class="eval-btn eval-btn--danger">
    <i class="fas fa-trash"></i> Supprimer
  </button>
</div>
```

## Fichiers CSS

- Notes : `prof_notes_actions.css`
- Évaluations : `evaluations_hub.css` (`.eval-btn`)
- Onglets (référence de hauteur) : `prof_hub_filter_tabs.css`

Ne pas recréer un style de bouton différent par page. Réutiliser ces mesures.

Voir aussi : [README.md](README.md) (index) · [README-DESIGN-LISTES.md](README-DESIGN-LISTES.md)
