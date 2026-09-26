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
