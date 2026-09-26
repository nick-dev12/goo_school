"""Contexte onglets / filtres UI — espace professeur (Vague 0+)."""

from .directeur_ui_tabs import resolve_main_section_tab


STATUTS_PRESENCE_SAISIE = ('present', 'absent')

NOTES_PRIMAIRE_VUE_CHOICES = ('releve', 'saisie', 'evaluations')


def enseignant_est_hub_v3_collège_lycée(professeur):
    """Vague 3 : collège / lycée / mixte — hors primaire et supérieur LMD."""
    etab = getattr(professeur, 'etablissement', None)
    if not etab:
        return False
    te = getattr(etab, 'type_etablissement', None)
    return te not in ('primary', 'superieur')


def classes_flat_from_secondaire_affectations(affectations, nombre_eleves_by_classe=None):
    """Liste plate classes — AffectationProfesseur (collège/lycée)."""
    flat = []
    seen = set()
    counts = nombre_eleves_by_classe or {}
    for aff in affectations or []:
        if aff.classe_id in seen:
            continue
        seen.add(aff.classe_id)
        flat.append({
            'classe': aff.classe,
            'affectation': aff,
            'nombre_eleves': counts.get(aff.classe_id, getattr(aff.classe, 'nombre_eleves', None)),
            'matiere': getattr(aff, 'matiere', None),
        })
    flat.sort(key=lambda item: item['classe'].nom)
    return flat


def classes_flat_from_affectations(affectations):
    """Liste plate des classes du prof (ordre alphabétique)."""
    flat = []
    seen = set()
    for aff in affectations or []:
        classe = getattr(aff, 'classe', None)
        if not classe or aff.classe_id in seen:
            continue
        seen.add(aff.classe_id)
        flat.append({
            'classe': classe,
            'affectation': aff,
            'nombre_eleves': getattr(classe, 'nombre_eleves', None),
        })
    flat.sort(key=lambda item: item['classe'].nom)
    return flat


def attach_primaire_classe_tab_context(
    request, context, classes_flat, param='classe', pick_first_if_missing=False
):
    """Persistance ?classe= pour hubs primaire (Vague 2+)."""
    classe_ids = [str(c['classe'].id) for c in (classes_flat or []) if c.get('classe')]
    raw = (request.GET.get(param) or '').strip()
    if raw.isdigit() and raw in classe_ids:
        classe_key = raw
    elif pick_first_if_missing and classe_ids:
        classe_key = classe_ids[0]
    else:
        classe_key = ''
    context['classes_flat'] = classes_flat or []
    context['initial_classe_id'] = classe_key
    return context


def statut_saisie_presence(presence):
    """Valeur pour les radios Présent/Absent (legacy retard / justifié en lecture)."""
    if not presence:
        return 'present'
    st = getattr(presence, 'statut', None) or 'present'
    if st in STATUTS_PRESENCE_SAISIE:
        return st
    if st == 'absent_justifie':
        return 'absent'
    return ''


def presence_statut_legacy_label(statut):
    if statut == 'retard':
        return 'Retard (historique)'
    if statut == 'absent_justifie':
        return 'Absent justifié (historique)'
    return ''


def enrich_eleve_presence_row(presence):
    """Champs template liste de présence (saisie binaire + legacy)."""
    st = presence.statut if presence else 'present'
    legacy = presence_statut_legacy_label(st) if presence else ''
    return {
        'statut': st,
        'statut_saisie': statut_saisie_presence(presence),
        'statut_legacy': legacy,
    }


def attach_presence_liste_tab_context(request, context, classe_ids=None):
    """Liste présence — persistance ?appel= (primaire) ou date si besoin."""
    appel = (request.GET.get('appel') or '').strip()
    if appel.isdigit():
        context['initial_presence_appel'] = appel
    else:
        context['initial_presence_appel'] = ''
    return context


def attach_notes_primaire_tab_context(request, context, periodes, classes_flat, matieres_ids):
    """Hub notes primaire — ?periode=&classe=&matiere=&vue=."""
    periode_ids = [str(p.id) for p in (periodes or [])]
    raw_per = (request.GET.get('periode') or '').strip()
    if raw_per.isdigit() and raw_per in periode_ids:
        periode_key = raw_per
    elif periode_ids:
        periode_key = periode_ids[0]
    else:
        periode_key = ''

    classe_ids = [str(c['classe'].id) for c in (classes_flat or []) if c.get('classe')]
    raw_cls = (request.GET.get('classe') or '').strip()
    if raw_cls.isdigit() and raw_cls in classe_ids:
        classe_key = raw_cls
    else:
        classe_key = ''

    matiere_ids = [str(mid) for mid in (matieres_ids or [])]
    raw_mat = (request.GET.get('matiere') or '').strip()
    if raw_mat.isdigit() and raw_mat in matiere_ids:
        matiere_key = raw_mat
    elif raw_mat.isdigit() and classe_key and raw_mat not in matiere_ids:
        matiere_key = ''
    else:
        matiere_key = ''

    vue = resolve_main_section_tab(
        request, 'vue', NOTES_PRIMAIRE_VUE_CHOICES, 'releve' if matiere_key else 'releve'
    )
    if not matiere_key and vue == 'saisie':
        vue = 'releve'

    context['initial_notes_periode_id'] = periode_key
    context['initial_notes_classe_id'] = classe_key
    context['initial_notes_matiere_id'] = matiere_key
    context['initial_notes_vue'] = vue
    return context
