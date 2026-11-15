"""Onglets filtres réutilisables — un seul HTML + CSS pour tout le SI."""

from urllib.parse import urlencode

from django import template
from django.urls import NoReverseMatch, reverse

register = template.Library()

KIND_META = {
    'period': {
        'label': 'Période',
        'icon': 'fas fa-calendar-days',
        'block': 'period',
        'bar': 'prof-primaire-periodes-bar',
        'overflow_one': 'période',
        'overflow_many': 'périodes',
    },
    'class': {
        'label': 'Classe',
        'icon': 'fas fa-chalkboard-user',
        'block': 'classe',
        'bar': 'prof-primaire-classes-bar',
        'overflow_one': 'classe',
        'overflow_many': 'classes',
    },
    'subject': {
        'label': 'Matières',
        'icon': 'fas fa-book-open',
        'block': 'matiere',
        'bar': 'notes-subject-bar prof-primaire-matieres-bar',
        'overflow_one': 'matière',
        'overflow_many': 'matières',
    },
    'view': {
        'label': 'Vue',
        'icon': 'fas fa-layer-group',
        'block': 'vue',
        'bar': 'prof-primaire-vues-bar',
        'overflow_one': 'vue',
        'overflow_many': 'vues',
    },
}


def _obj_id(obj):
    if obj is None:
        return None
    if isinstance(obj, dict):
        nested = obj.get('classe') or obj.get('matiere') or obj.get('periode') or obj
        if nested is not obj:
            return _obj_id(nested)
        value = obj.get('id')
        return str(value) if value is not None else None
    value = getattr(obj, 'id', obj)
    return str(value) if value not in (None, '') else None


def _attr(obj, *names, default=''):
    if obj is None:
        return default
    for name in names:
        if isinstance(obj, dict) and name in obj:
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)
        if value not in (None, ''):
            return value
    return default


def _href(request, preserve, updates, drop=()):
    query = {}
    for key in preserve:
        value = request.GET.get(key)
        if value:
            query[key] = value
    for key in drop:
        query.pop(key, None)
    for key, value in updates.items():
        if value in (None, ''):
            query.pop(key, None)
        else:
            query[key] = str(value)
    encoded = urlencode(query)
    path = request.path
    return f'{path}?{encoded}' if encoded else path


def _make_group(kind, items, label=None, search_placeholder='', search_target=''):
    if not items:
        return None
    meta = KIND_META[kind]
    group = {
        'kind': kind,
        'label': label or meta['label'],
        'icon': meta['icon'],
        'block': meta['block'],
        'bar': meta['bar'],
        'overflow_one': meta['overflow_one'],
        'overflow_many': meta['overflow_many'],
        'items': items,
        'search_placeholder': search_placeholder,
        'search_target': search_target,
    }
    return group


def _period_items(request, context, preserve):
    nav = None
    if context.get('est_superieur'):
        active = context.get('classe_data_active') or {}
        nav = active.get('periodes_nav') if isinstance(active, dict) else getattr(active, 'periodes_nav', None)
    if nav:
        classe_id = (
            _obj_id(context.get('classe_selectionnee'))
            or context.get('initial_classe_id')
        )
        items = []
        for entry in nav:
            periode = _attr(entry, 'periode', default=entry)
            query = _attr(entry, 'query', default='')
            href = f'{request.path}?{query}' if query else request.path
            if classe_id:
                href = f'{request.path}?classe={classe_id}&{query}' if query else f'{request.path}?classe={classe_id}'
            items.append({
                'label': _attr(periode, 'libelle_affichage_superieur', 'nom_periode'),
                'href': href,
                'active': bool(_attr(entry, 'active', default=False)),
                'count': 'En cours' if _attr(periode, 'est_en_cours', default=False) else None,
            })
        return items, 'Période du module'

    periodes = context.get('periodes') or context.get('periodes_scolaires') or []
    selected = context.get('periode_selectionnee') or context.get('periode_active')
    selected_id = _obj_id(selected)
    items = []
    for periode in periodes:
        pid = _obj_id(periode)
        items.append({
            'label': _attr(periode, 'nom_periode', 'libelle_affichage_superieur'),
            'href': _href(request, preserve, {'periode': pid}),
            'active': pid == selected_id,
            'count': None,
        })
    return items, None


def _class_items(request, context, preserve, classe_url_name, drop_matiere):
    rows = context.get('classes_flat') or []
    selected = context.get('classe_selectionnee') or context.get('classe')
    selected_id = _obj_id(selected) or str(context.get('initial_classe_id') or '')
    drop = ('matiere',) if drop_matiere else ()
    items = []
    for row in rows:
        classe = row.get('classe') if isinstance(row, dict) else getattr(row, 'classe', row)
        cid = _obj_id(classe)
        if not cid:
            continue
        if classe_url_name:
            try:
                path = reverse(classe_url_name, args=[int(cid)])
            except (NoReverseMatch, TypeError, ValueError):
                path = request.path
            query = _href(request, preserve, {'classe': cid}, drop=drop).split('?', 1)
            href = path + (('?' + query[1]) if len(query) > 1 else '')
        else:
            href = _href(request, preserve, {'classe': cid}, drop=drop)
        count = row.get('nombre_eleves') if isinstance(row, dict) else getattr(row, 'nombre_eleves', None)
        items.append({
            'label': _attr(classe, 'nom'),
            'href': href,
            'active': cid == selected_id,
            'count': count,
        })
    return items


def _subject_items(request, context, preserve):
    rows = context.get('matieres_data') or context.get('matieres_appel') or []
    selected = context.get('matiere_selectionnee') or context.get('matiere')
    selected_id = _obj_id(selected)
    items = []
    for row in rows:
        matiere = row.get('matiere') if isinstance(row, dict) else getattr(row, 'matiere', row)
        mid = _obj_id(matiere)
        if not mid:
            continue
        if isinstance(row, dict):
            count = row.get('nombre_evaluations')
            if count is None:
                count = row.get('nombre_exercices')
            if count is None and row.get('evaluations') is not None:
                count = len(row.get('evaluations') or [])
        else:
            count = getattr(row, 'nombre_evaluations', None)
        items.append({
            'label': _attr(matiere, 'nom'),
            'href': _href(request, preserve, {'matiere': mid}),
            'active': mid == selected_id,
            'count': count,
        })
    return items


def _as_bool(value, default=None):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() not in ('0', 'false', 'none', '')


@register.inclusion_tag('school_admin/partials/aria_filter_tabs.html', takes_context=True)
def aria_filter_tabs(context, groups=None):
    return {'groups': groups or context.get('groups') or []}


@register.inclusion_tag('school_admin/partials/aria_filter_tabs.html', takes_context=True)
def aria_prof_filters(
    context,
    show_periodes=None,
    show_classes=None,
    show_matieres=None,
    preserve='periode,classe,matiere,vue,onglet,appel',
    classe_url_name=None,
    search_placeholder='',
    search_target='',
    drop_matiere_on_classe=True,
):
    """Construit Période / Classe / Matières à partir du contexte professeur."""
    request = context.get('request')
    if request is None:
        return {'groups': []}

    keys = [part.strip() for part in str(preserve).split(',') if part.strip()]
    seeded = request.GET.copy()
    defaults = {
        'periode': _obj_id(context.get('periode_selectionnee') or context.get('periode_active')),
        'classe': _obj_id(context.get('classe_selectionnee') or context.get('classe')) or context.get('initial_classe_id'),
        'matiere': _obj_id(context.get('matiere_selectionnee') or context.get('matiere')),
        'vue': context.get('notes_vue'),
        'onglet': context.get('onglet_actif'),
    }
    for key in keys:
        if not seeded.get(key) and defaults.get(key):
            seeded[key] = str(defaults[key])
    wrapped = type('Req', (), {})()
    wrapped.path = request.path
    wrapped.GET = seeded
    request = wrapped

    groups = []
    want_periodes = _as_bool(show_periodes, None)
    want_classes = _as_bool(show_classes, None)
    want_matieres = _as_bool(show_matieres, None)

    period_items, period_label = _period_items(request, context, keys)
    if want_periodes is None:
        if context.get('est_superieur') and period_label != 'Période du module':
            want_periodes = False
        else:
            want_periodes = bool(period_items)
    if want_periodes:
        group = _make_group('period', period_items, label=period_label)
        if group:
            groups.append(group)

    class_items = _class_items(
        request, context, keys, classe_url_name, _as_bool(drop_matiere_on_classe, True)
    )
    if want_classes is None:
        want_classes = bool(class_items)
    if want_classes:
        group = _make_group(
            'class',
            class_items,
            search_placeholder=search_placeholder,
            search_target=search_target,
        )
        if group:
            groups.append(group)

    subject_items = _subject_items(request, context, keys)
    classe_selected = bool(
        context.get('classe_selectionnee') or context.get('classe') or context.get('initial_classe_id')
    )
    if want_matieres is None:
        want_matieres = bool(subject_items) and (classe_selected or bool(context.get('matieres_appel')))
    if want_matieres:
        group = _make_group('subject', subject_items)
        if group:
            groups.append(group)

    return {'groups': groups}


def _classe_eleve_count(row):
    if isinstance(row, dict):
        if row.get('nombre_eleves') is not None:
            return row.get('nombre_eleves')
        stats = row.get('stats') or {}
        if isinstance(stats, dict) and stats.get('total_eleves') is not None:
            return stats.get('total_eleves')
        bulletins = row.get('bulletins') or {}
        if isinstance(bulletins, dict) and bulletins.get('eleves_total') is not None:
            return bulletins.get('eleves_total')
        return None
    return getattr(row, 'nombre_eleves', None)


def _dir_period_items(request, context, preserve, periode_param):
    stats_rows = context.get('periodes_avec_stats') or []
    if stats_rows:
        selected_id = str(context.get('initial_periode_id') or '')
        items = []
        for row in stats_rows:
            periode = row.get('periode') if isinstance(row, dict) else row
            pid = _obj_id(periode)
            if not pid:
                continue
            count = row.get('session_count') if isinstance(row, dict) else None
            items.append({
                'label': _attr(periode, 'nom_periode', 'nom'),
                'href': _href(request, preserve, {periode_param: pid}),
                'active': pid == selected_id,
                'count': count,
            })
        return items

    if context.get('est_superieur'):
        return []

    nav = context.get('periodes_nav') or []
    if nav:
        items = []
        for periode in nav:
            pid = _obj_id(periode) or str(_attr(periode, 'id', default=''))
            if not pid:
                continue
            statut = _attr(periode, 'statut', 'statut_periode')
            items.append({
                'label': _attr(periode, 'nom', 'nom_periode'),
                'href': _href(request, preserve, {periode_param: pid}),
                'active': bool(_attr(periode, 'est_active', default=False)),
                'count': 'En cours' if statut == 'en_cours' else None,
            })
        return items

    periodes = context.get('periodes') or context.get('periodes_scolaires') or []
    selected = context.get('periode_selectionnee') or context.get('periode_active')
    selected_id = _obj_id(selected)
    items = []
    for periode in periodes:
        pid = _obj_id(periode)
        if not pid:
            continue
        statut = _attr(periode, 'statut_periode', 'statut')
        items.append({
            'label': _attr(periode, 'nom_periode', 'nom'),
            'href': _href(request, preserve, {periode_param: pid}),
            'active': pid == selected_id,
            'count': 'En cours' if statut == 'en_cours' else None,
        })
    return items


def _dir_niveau_items(request, context, preserve, niveau_param, classe_param):
    grouped = context.get('classes_grouped') or {}
    if grouped:
        selected = (context.get('initial_niveau_key') or '').strip().lower()
        items = []
        for key, data in grouped.items():
            label = ''
            total = None
            if isinstance(data, dict):
                label = data.get('label') or key
                total = data.get('total_eleves')
            else:
                label = key
            norm = str(key).strip().lower()
            items.append({
                'label': label,
                'href': _href(request, preserve, {niveau_param: key}, drop=(classe_param,)),
                'active': norm == selected,
                'count': total,
            })
        return items, 'Niveau'

    groupes = context.get('groupes_classes') or {}
    if not groupes:
        return [], None
    selected = str(context.get('initial_groupe_key') or '')
    counts = {}
    selected_periode = str(context.get('initial_periode_id') or '')
    for row in context.get('periodes_avec_stats') or []:
        if not isinstance(row, dict):
            continue
        periode = row.get('periode')
        if _obj_id(periode) == selected_periode:
            counts = row.get('groupe_counts') or {}
            break
    items = []
    for key, groupe in groupes.items():
        label = key
        if isinstance(groupe, dict):
            label = groupe.get('label') or key
        count = counts.get(key) if isinstance(counts, dict) else None
        items.append({
            'label': label,
            'href': _href(request, preserve, {niveau_param: key}),
            'active': str(key) == selected,
            'count': count,
        })
    label = 'Filière' if context.get('est_superieur') else 'Niveau'
    return items, label


def _dir_classe_items(request, context, preserve, niveau_param, classe_param):
    grouped = context.get('classes_grouped') or {}
    if not grouped:
        return []
    selected_niveau = (context.get('initial_niveau_key') or '').strip().lower()
    selected_classe = str(context.get('initial_classe_id') or '')
    rows = []
    niveau_key = None
    for key, data in grouped.items():
        if str(key).strip().lower() == selected_niveau:
            rows = (data or {}).get('classes') if isinstance(data, dict) else []
            niveau_key = key
            break
    if not rows:
        first_key = next(iter(grouped), None)
        first = grouped.get(first_key) if first_key is not None else {}
        rows = first.get('classes') if isinstance(first, dict) else []
        niveau_key = first_key
    items = []
    for row in rows or []:
        classe = row.get('classe') if isinstance(row, dict) else getattr(row, 'classe', row)
        cid = _obj_id(classe)
        if not cid:
            continue
        updates = {classe_param: cid}
        if niveau_key is not None:
            updates[niveau_param] = niveau_key
        items.append({
            'label': _attr(classe, 'nom'),
            'href': _href(request, preserve, updates),
            'active': cid == selected_classe,
            'count': _classe_eleve_count(row),
        })
    return items


@register.inclusion_tag('school_admin/partials/aria_filter_tabs.html', takes_context=True)
def aria_dir_filters(
    context,
    show_periodes=None,
    show_niveaux=None,
    show_classes=None,
    preserve='periode,niveau,classe,groupe',
    periode_param='periode',
    niveau_param='niveau',
    classe_param='classe',
    niveau_label=None,
):
    """Période / Niveau / Classe en liens GET — même HTML que le composant professeur."""
    request = context.get('request')
    if request is None:
        return {'groups': []}

    keys = [part.strip() for part in str(preserve).split(',') if part.strip()]
    seeded = request.GET.copy()
    defaults = {
        periode_param: (
            context.get('initial_periode_id')
            or _obj_id(context.get('periode_selectionnee') or context.get('periode_active'))
        ),
        niveau_param: context.get('initial_niveau_key') or context.get('initial_groupe_key'),
        classe_param: context.get('initial_classe_id'),
    }
    for key in keys:
        if not seeded.get(key) and defaults.get(key):
            seeded[key] = str(defaults[key])
    wrapped = type('Req', (), {})()
    wrapped.path = request.path
    wrapped.GET = seeded
    request = wrapped

    groups = []
    want_periodes = _as_bool(show_periodes, None)
    want_niveaux = _as_bool(show_niveaux, None)
    want_classes = _as_bool(show_classes, None)

    period_items = _dir_period_items(request, context, keys, periode_param)
    if want_periodes is None:
        want_periodes = bool(period_items)
    if want_periodes:
        group = _make_group('period', period_items)
        if group:
            groups.append(group)

    niveau_items, auto_label = _dir_niveau_items(
        request, context, keys, niveau_param, classe_param
    )
    if want_niveaux is None:
        want_niveaux = bool(niveau_items)
    if want_niveaux:
        group = _make_group('class', niveau_items, label=niveau_label or auto_label or 'Niveau')
        if group:
            groups.append(group)

    classe_items = _dir_classe_items(request, context, keys, niveau_param, classe_param)
    if want_classes is None:
        want_classes = bool(classe_items) and bool(context.get('classes_grouped'))
    if want_classes:
        group = _make_group('class', classe_items, label='Classe')
        if group:
            groups.append(group)

    return {'groups': groups}
