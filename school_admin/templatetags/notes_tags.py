from typing import Iterable, Set

from django import template
from decimal import Decimal

from ..model.professeur_model import Professeur
from ..model.moyenne_model import Moyenne
from ..model.note_primaire_model import MoyenneMatierePrimaire
from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

register = template.Library()

def _eval_item_id(item):
    if item is None:
        return None
    if isinstance(item, dict):
        evaluation = item.get('evaluation')
        if evaluation is not None:
            return getattr(evaluation, 'id', None)
        return item.get('id')
    return getattr(item, 'id', None)


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@register.filter
def evals_incluses_moyenne(evaluations, eleves):
    """
    Évaluations réellement retenues dans le calcul des moyennes de la classe.
    Si aucune moyenne n'a encore été calculée, retourne toutes les évaluations.
    """
    evaluations = list(evaluations or [])
    ids = set()
    has_moyenne = False
    for eleve_data in eleves or []:
        moyenne = eleve_data.get('moyenne') if isinstance(eleve_data, dict) else None
        used = getattr(moyenne, 'evaluations_utilisees', None)
        if not used and isinstance(moyenne, dict):
            used = moyenne.get('evaluations_utilisees')
        if not used:
            continue
        has_moyenne = True
        for value in used:
            parsed = _as_int(value)
            if parsed is not None:
                ids.add(parsed)
    if not has_moyenne or not ids:
        return evaluations
    filtered = []
    for item in evaluations:
        eval_id = _as_int(_eval_item_id(item))
        if eval_id in ids:
            filtered.append(item)
    return filtered or evaluations


@register.filter
def eval_in_moyenne(eval_id, moy_evals):
    target = _as_int(eval_id)
    if target is None:
        return False
    for item in moy_evals or []:
        if _as_int(_eval_item_id(item)) == target:
            return True
    return False


@register.filter
def get_item(d, key):
    """
    Dict : clé str ou native.
    Liste / tuple : index entier (ex. récap UE bulletin supérieur : recap_ue_slots_s1|get_item:'0').
    """
    if d is None:
        return ''
    if isinstance(d, dict):
        return d.get(str(key), d.get(key, ''))
    if isinstance(d, (list, tuple)):
        try:
            ik = int(key) if not isinstance(key, int) else key
        except (TypeError, ValueError):
            return ''
        if 0 <= ik < len(d):
            return d[ik]
        return ''
    return ''

@register.filter
def get_note(notes_dict, key):
    """
    Récupère une note depuis un dictionnaire imbriqué
    Usage: {{ notes_existantes|get_note:eleve_id|get_note:note_key }}
    """
    if notes_dict and key in notes_dict:
        return notes_dict[key]
    return None

@register.filter
def format_note(value):
    """
    Formate une note pour affichage dans un input de type number
    Convertit les Decimal en format avec point (8.50) au lieu de virgule (8,50)
    """
    if value is None or value == '':
        return ''
    try:
        # Convertir en float puis formater avec point
        float_value = float(value)
        # Formater avec 2 décimales et point comme séparateur
        return f"{float_value:.2f}".replace(',', '.')
    except (ValueError, TypeError):
        return ''

def _note_ratio(note_value, bareme):
    if note_value is None or note_value == '' or bareme is None:
        return None
    try:
        note = float(str(note_value).replace(',', '.'))
        bareme_float = float(str(bareme).replace(',', '.'))
        if bareme_float <= 0:
            return None
        return max(0.0, min(1.0, note / bareme_float))
    except (ValueError, TypeError):
        return None


def _note_hsl(note_value, bareme):
    """HSL : < 10/20 toujours rouge (teintes), >= 10/20 jaune-vert → vert."""
    ratio = _note_ratio(note_value, bareme)
    if ratio is None:
        return None
    sur20 = ratio * 20.0
    if sur20 < 10:
        t = sur20 / 10.0
        hue = t * 4
        sat = 90 - t * 10
        light = 22 + t * 26
        return hue, sat, light
    t = (sur20 - 10.0) / 10.0
    hue = 78 + t * 42
    sat = 76
    light = 32
    return hue, sat, light


@register.filter
def note_hue(note_value, bareme):
    """Teinte HSL. Sous 10/20 : rouge (0–8). Au-dessus : vert."""
    hsl = _note_hsl(note_value, bareme)
    if hsl is None:
        return ''
    return str(int(round(hsl[0])))


@register.filter
def note_color_css(note_value, bareme):
    """Couleur CSS hsl() rouge variable sous 10/20, vert au-dessus."""
    hsl = _note_hsl(note_value, bareme)
    if hsl is None:
        return ''
    hue, sat, light = hsl
    return f'hsl({hue:.0f}, {sat:.0f}%, {light:.0f}%)'


@register.filter
def note_sort_attr(value):
    """Valeur numérique stable (point) pour le tri décroissant."""
    if value is None or value == '':
        return ''
    try:
        return f"{float(str(value).replace(',', '.')):.4f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return ''


@register.filter
def get_note_color_class(note_value, bareme):
    """
    Retourne la classe CSS selon la performance de la note.
    Échelle rouge → vert, sans bleu.
    """
    ratio = _note_ratio(note_value, bareme)
    if ratio is None:
        return ''
    pourcentage = ratio * 100
    if pourcentage < 50:
        return 'note-faible' if pourcentage < 25 else 'note-moyenne-faible'
    if pourcentage < 70:
        return 'note-bonne'
    return 'note-excellente'

@register.filter
def classes_niveaux_lmd(classes):
    """
    Retourne la liste des libellés de niveau uniques (ex: Licence 1, Master 1).
    Usage: {{ module.classes.all|classes_niveaux_lmd }}
    """
    if not classes:
        return []
    seen = set()
    result = []
    for c in classes:
        label = c.get_libelle_niveau_superieur_complet()
        if not label:
            label = 'Sans niveau'
        if label not in seen:
            seen.add(label)
            result.append(label)
    return sorted(result, key=lambda x: (x == 'Sans niveau', x.lower()))


@register.filter
def group_classes(classes):
    """
    Regroupe les classes par niveau et retourne une liste de noms de groupes
    Par exemple: ["6eme A", "6eme B", "6eme C"] devient ["6eme"]
    """
    import re
    if not classes:
        return []
    
    groupes = {}
    for classe in classes:
        # Extraire le niveau de base
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
        if match:
            groupe_nom = match.group(1)
        else:
            groupe_nom = classe.nom
        
        if groupe_nom not in groupes:
            groupes[groupe_nom] = []
        groupes[groupe_nom].append(classe)
    
    # Retourner la liste des noms de groupes avec le nombre de classes
    result = []
    from school_admin.services.structure_v4 import rang_scolaire

    # Ordre scolaire (CI…CM2, 6e…3e, 2nde, 1re, Terminale), puis alphabétique.
    for groupe_nom, classes_list in sorted(groupes.items(), key=lambda kv: (rang_scolaire(kv[0]), kv[0])):
        result.append({
            'nom': groupe_nom,
            'count': len(classes_list)
        })
    return result

# Dictionnaire de correspondance matière -> (icône, couleur)
MATIERES_CONFIG = {
    'Mathématiques': ('calculator', '#3b82f6'),
    'Mathématiques Approfondies': ('calculator', '#3b82f6'),
    'Français': ('book-open', '#10b981'),
    'Anglais': ('globe', '#8b5cf6'),
    'Histoire': ('landmark', '#f59e0b'),
    'Géographie': ('map-marked-alt', '#14b8a6'),
    'Physique-Chimie': ('flask', '#ec4899'),
    'Sciences Physiques': ('flask', '#ec4899'),
    'Sciences Naturelles': ('microscope', '#22c55e'),
    'SVT': ('leaf', '#22c55e'),
    'EPS': ('running', '#ef4444'),
    'Éducation Civique': ('balance-scale', '#6366f1'),
    'Philosophie': ('brain', '#6366f1'),
    'Sciences Économiques': ('chart-line', '#f43f5e'),
    'Arabe': ('language', '#84cc16'),
    'Wolof': ('language', '#84cc16'),
    'Pulaar': ('language', '#84cc16'),
    'Informatique': ('laptop-code', '#06b6d4'),
    'Musique': ('music', '#a855f7'),
    'Arts': ('palette', '#f97316'),
}

@register.filter
def get_matiere_icon(matiere_nom):
    """Retourne l'icône FontAwesome pour une matière"""
    if not matiere_nom:
        return 'book'
    
    # Recherche exacte d'abord
    if matiere_nom in MATIERES_CONFIG:
        return MATIERES_CONFIG[matiere_nom][0]
    
    # Recherche partielle (nom contient la clé OU clé contient le nom)
    for key, (icon, _) in MATIERES_CONFIG.items():
        if key.lower() in matiere_nom.lower() or matiere_nom.lower() in key.lower():
            return icon
    return 'book'

@register.filter
def get_matiere_color(matiere_nom):
    """Retourne la couleur hexadécimale pour une matière"""
    if not matiere_nom:
        return '#64748b'
    
    # Recherche exacte d'abord
    if matiere_nom in MATIERES_CONFIG:
        return MATIERES_CONFIG[matiere_nom][1]
    
    # Recherche partielle (nom contient la clé OU clé contient le nom)
    for key, (_, color) in MATIERES_CONFIG.items():
        if key.lower() in matiere_nom.lower() or matiere_nom.lower() in key.lower():
            return color
    return '#64748b'


@register.filter
def sum_notes_sur_20(notes_list):
    """
    Calcule la somme des notes sur 20
    """
    if not notes_list:
        return 0
    total = 0
    for note in notes_list:
        if isinstance(note, dict) and 'note_sur_20' in note:
            total += float(note['note_sur_20'])
    return total


@register.filter
def divide(value, divisor):
    """
    Divise une valeur par un diviseur
    """
    try:
        if divisor == 0:
            return 0
        return float(value) / float(divisor)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def max_note_sur_20(notes_list):
    """
    Retourne la note maximale sur 20
    """
    if not notes_list:
        return 0
    notes = []
    for note in notes_list:
        if isinstance(note, dict) and 'note_sur_20' in note:
            notes.append(float(note['note_sur_20']))
    return max(notes) if notes else 0


@register.filter
def min_note_sur_20(notes_list):
    """
    Retourne la note minimale sur 20
    """
    if not notes_list:
        return 0
    notes = []
    for note in notes_list:
        if isinstance(note, dict) and 'note_sur_20' in note:
            notes.append(float(note['note_sur_20']))
    return min(notes) if notes else 0


def _collect_affectations_professeur_primaire(professeur: Professeur) -> tuple[Set[int], Set[int]]:
    """
    Rassemble les classes et matières qu'un professeur du primaire enseigne.
    """
    classe_ids: Set[int] = set()
    matiere_ids: Set[int] = set()

    affectations: Iterable[AffectationProfesseurPrimaire] = (
        AffectationProfesseurPrimaire.objects.filter(
            professeur=professeur,
            actif=True,
        )
        .select_related("classe")
        .prefetch_related("matieres")
    )

    for affectation in affectations:
        if affectation.classe_id:
            classe_ids.add(affectation.classe_id)
        matiere_ids.update(
            affectation.matieres.values_list("id", flat=True)
        )

    return classe_ids, matiere_ids


@register.filter
def peut_justifier_notes(professeur: Professeur) -> bool:
    """
    Indique si le professeur peut accéder à la justification de notes,
    c'est-à-dire si des moyennes ont déjà été soumises à la direction.
    """
    if not isinstance(professeur, Professeur) or not professeur.pk:
        return False

    if professeur.niveau_enseignement == "primaire":
        classe_ids, matiere_ids = _collect_affectations_professeur_primaire(professeur)

        if not classe_ids or not matiere_ids:
            return False

        return MoyenneMatierePrimaire.objects.filter(
            classe_id__in=classe_ids,
            matiere_id__in=matiere_ids,
            soumis=True,
        ).exists()

    return Moyenne.objects.filter(
        professeur=professeur,
        soumis=True,
        actif=True,
    ).exists()

