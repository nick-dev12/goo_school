"""Sélection d'onglets niveau/classe (UI directeur — persistance URL)."""


def _normalize_niveau_key(raw):
    return (raw or '').strip().lower()


def resolve_niveau_classe_tab_selection(request, classes_grouped):
    """
    Retourne (niveau_key, classe_id) pour l'état initial des onglets.
    Query : ?niveau= & ?classe= (insensible à la casse pour niveau).
    """
    if not classes_grouped:
        return '', None

    key_by_norm = {}
    ordered_keys = []
    for key in classes_grouped.keys():
        norm = _normalize_niveau_key(key)
        ordered_keys.append(key)
        key_by_norm.setdefault(norm, key)

    default_niveau = ordered_keys[0]
    niveau_param = _normalize_niveau_key(request.GET.get('niveau'))
    classe_raw = request.GET.get('classe')
    classe_id = None
    if classe_raw not in (None, ''):
        try:
            classe_id = int(classe_raw)
        except (TypeError, ValueError):
            classe_id = None

    active_niveau = default_niveau
    active_classe_id = None

    if classe_id is not None:
        for key, data in classes_grouped.items():
            for classe_info in data.get('classes') or []:
                cid = classe_info.get('classe')
                pk = getattr(cid, 'id', None) if cid is not None else classe_info.get('classe_id')
                if pk == classe_id:
                    active_niveau = key
                    active_classe_id = classe_id
                    break
            if active_classe_id is not None:
                break

    if active_classe_id is None and niveau_param in key_by_norm:
        active_niveau = key_by_norm[niveau_param]

    classes_in_niveau = classes_grouped.get(active_niveau, {}).get('classes') or []
    if active_classe_id is None and classes_in_niveau:
        first = classes_in_niveau[0]
        cl = first.get('classe')
        active_classe_id = getattr(cl, 'id', None) if cl is not None else first.get('classe_id')

    return _normalize_niveau_key(active_niveau), active_classe_id


def attach_niveau_classe_tab_context(request, context, classes_grouped):
    niveau_key, classe_id = resolve_niveau_classe_tab_selection(request, classes_grouped)
    context['initial_niveau_key'] = niveau_key
    context['initial_classe_id'] = classe_id
    return context


def resolve_main_section_tab(request, param_name, allowed_values, default=None):
    """Onglet principal (?section=, ?tab=, …)."""
    allowed = {v.lower(): v for v in allowed_values}
    raw = _normalize_niveau_key(request.GET.get(param_name))
    if raw in allowed:
        return allowed[raw]
    if default is not None:
        return default
    return allowed_values[0] if allowed_values else ''


def resolve_examens_tab_selection(request, periodes_avec_stats, groupe_keys):
    """
    Retourne (periode_id, groupe_key, groupe_index) pour gestion examens.
    Query : ?periode= & ?groupe= (clé groupe_classes).
    """
    from urllib.parse import unquote

    if not periodes_avec_stats:
        return None, None, 0

    periode_ids = [item['periode'].id for item in periodes_avec_stats]
    default_periode = periode_ids[0]
    default_groupe = groupe_keys[0] if groupe_keys else None

    active_periode = default_periode
    periode_raw = request.GET.get('periode')
    if periode_raw not in (None, ''):
        try:
            pid = int(periode_raw)
            if pid in periode_ids:
                active_periode = pid
        except (TypeError, ValueError):
            pass

    active_groupe = default_groupe
    groupe_raw = request.GET.get('groupe')
    if groupe_raw not in (None, ''):
        decoded = unquote(str(groupe_raw)).strip()
        if decoded in groupe_keys:
            active_groupe = decoded

    groupe_index = 0
    if active_groupe in groupe_keys:
        groupe_index = groupe_keys.index(active_groupe)

    return active_periode, active_groupe, groupe_index


def resolve_session_tab_selection(request, session_ids):
    """Emploi du temps examens — ?session= id session."""
    if not session_ids:
        return None
    default_id = session_ids[0]
    raw = request.GET.get('session')
    if raw in (None, ''):
        return default_id
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return default_id
    return sid if sid in session_ids else default_id


def attach_gestion_periodes_tab_context(request, context, periodes_tabs):
    section = resolve_main_section_tab(
        request, 'section', ('annees', 'periodes'), 'annees'
    )
    context['gps_main_section'] = section

    niveau_code = ''
    if periodes_tabs:
        codes = [tab['code'] for tab in periodes_tabs]
        raw = (request.GET.get('niveau_lmd') or '').strip()
        if raw in codes:
            niveau_code = raw
        else:
            niveau_code = codes[0]
    context['gps_initial_niveau_tab'] = niveau_code
    return context
