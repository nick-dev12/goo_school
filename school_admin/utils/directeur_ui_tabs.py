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
    tab_legacy = (request.GET.get('tab') or '').strip().lower()
    if not niveau_param and tab_legacy.startswith('tab-'):
        try:
            idx = int(tab_legacy.replace('tab-', '', 1))
            if 1 <= idx <= len(ordered_keys):
                default_niveau = ordered_keys[idx - 1]
        except (TypeError, ValueError):
            pass
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


LIAISON_ONGLET_CHOICES = ('a-approuver', 'reussies', 'refusees')


def resolve_liaison_onglet(request):
    """Demandes liaison parent — ?onglet=a-approuver|reussies|refusees."""
    raw = _normalize_niveau_key(request.GET.get('onglet')).replace('_', '-')
    alias = {
        'a-approuver': 'a-approuver',
        'approuver': 'a-approuver',
        'reussies': 'reussies',
        'reussie': 'reussies',
        'refusees': 'refusees',
        'refusee': 'refusees',
    }
    return alias.get(raw, 'a-approuver')


def attach_liaison_tab_context(request, context):
    onglet = resolve_liaison_onglet(request)
    context['initial_liaison_onglet'] = onglet
    context['initial_liaison_tab_id'] = f'tab-{onglet}'
    return context


def resolve_annonce_statut_filtre(request):
    """Annonces directeur — ?statut=publiee|brouillon|archivee ou vide = toutes."""
    raw = (request.GET.get('statut') or '').strip().lower()
    allowed = {'publiee', 'brouillon', 'archivee'}
    return raw if raw in allowed else ''


DASHBOARD_ACTIVITE_CHOICES = ('absences', 'notes', 'sanctions', 'justifications')


def resolve_dashboard_activite(request):
    """Tableau de bord — ?activite=absences|notes|sanctions|justifications."""
    return resolve_main_section_tab(
        request, 'activite', DASHBOARD_ACTIVITE_CHOICES, 'absences'
    )


def attach_dashboard_tab_context(request, context):
    activite = resolve_dashboard_activite(request)
    context['initial_dashboard_activite'] = activite
    context['initial_dashboard_tab_id'] = 'tab-' + activite
    return context


ETABLISSEMENT_SECTION_CHOICES = ('structure', 'finances')


def resolve_etablissement_section(request):
    """Hub établissement — ?section=structure|finances."""
    return resolve_main_section_tab(
        request, 'section', ETABLISSEMENT_SECTION_CHOICES, 'structure'
    )


def attach_etablissement_hub_context(request, context):
    section = resolve_etablissement_section(request)
    context['initial_etab_section'] = section
    context['initial_etab_tab_id'] = 'tab-etab-' + section
    return context


PROFIL_TAB_DIRECTEUR = ('informations', 'logo', 'modules', 'facturation', 'securite')
PROFIL_TAB_PERSONNEL = ('informations', 'securite')


def resolve_profil_tab(request, is_directeur):
    allowed = PROFIL_TAB_DIRECTEUR if is_directeur else PROFIL_TAB_PERSONNEL
    return resolve_main_section_tab(request, 'tab', allowed, 'informations')


def attach_profil_tab_context(request, context, is_directeur):
    tab = resolve_profil_tab(request, is_directeur)
    context['active_tab'] = tab
    context['initial_profil_tab'] = tab
    return context


def resolve_personnel_onglet(request, category_keys):
    """Liste personnel — ?onglet=professeurs|<clé catégorie>."""
    allowed = ['professeurs'] + [str(k).lower() for k in (category_keys or [])]
    return resolve_main_section_tab(request, 'onglet', tuple(allowed), 'professeurs')


def resolve_personnel_matiere_filtre(request):
    raw = (request.GET.get('matiere') or 'all').strip()
    return raw if raw else 'all'


def resolve_personnel_statut_filtre(request):
    raw = (request.GET.get('statut') or 'all').strip().lower()
    return raw if raw in ('all', 'active', 'inactive') else 'all'


def attach_personnel_tab_context(request, context, category_keys):
    onglet = resolve_personnel_onglet(request, category_keys)
    context['initial_personnel_onglet'] = onglet
    context['initial_matiere'] = resolve_personnel_matiere_filtre(request)
    context['initial_statut_filtre'] = resolve_personnel_statut_filtre(request)
    return context


BILAN_SECTION_CHOICES = (
    'synthese', 'graphiques', 'mois', 'classes', 'modes', 'annexes', 'inscription',
)
BILAN_SECTION_PANEL = {
    'synthese': 'scb-panel-synthese',
    'graphiques': 'scb-panel-graphiques',
    'mois': 'scb-panel-mois',
    'classes': 'scb-panel-classes',
    'modes': 'scb-panel-modes',
    'annexes': 'scb-panel-annexes',
    'inscription': 'scb-panel-inscription',
}


def attach_bilan_tab_context(request, context):
    section = resolve_main_section_tab(
        request, 'section', BILAN_SECTION_CHOICES, 'synthese'
    )
    context['initial_bilan_section'] = section
    context['initial_bilan_panel_id'] = BILAN_SECTION_PANEL[section]
    return context


BILAN_CLASSE_SECTION_CHOICES = (
    'synthese', 'graphiques', 'mois', 'eleves', 'modes', 'annexes', 'inscription',
)
BILAN_CLASSE_SECTION_PANEL = {
    'synthese': 'scb-panel-synthese',
    'graphiques': 'scb-panel-graphiques',
    'mois': 'scb-panel-mois',
    'eleves': 'scb-panel-eleves',
    'modes': 'scb-panel-modes',
    'annexes': 'scb-panel-annexes',
    'inscription': 'scb-panel-inscription',
}


def attach_bilan_classe_tab_context(request, context):
    section = resolve_main_section_tab(
        request, 'section', BILAN_CLASSE_SECTION_CHOICES, 'synthese'
    )
    context['initial_bilan_section'] = section
    context['initial_bilan_panel_id'] = BILAN_CLASSE_SECTION_PANEL[section]
    return context


DETAILS_COMPTA_SECTION_CHOICES = ('frais', 'mensualites', 'annexes', 'historique')
DETAILS_COMPTA_PANEL = {
    'frais': 'scd-panel-frais',
    'mensualites': 'comptaMensualitesSection',
    'annexes': 'scd-panel-annexes',
    'historique': 'scd-panel-historique',
}


def attach_details_compta_tab_context(request, context):
    section = resolve_main_section_tab(
        request, 'section', DETAILS_COMPTA_SECTION_CHOICES, 'frais'
    )
    context['initial_compta_details_section'] = section
    context['initial_compta_details_panel_id'] = DETAILS_COMPTA_PANEL[section]
    return context


def resolve_impayes_classe(request, classe_ids):
    """Impayés — ?classe=tous|<id>."""
    allowed = ['tous'] + [str(int(cid)) for cid in (classe_ids or []) if cid]
    raw = (request.GET.get('classe') or 'tous').strip().lower()
    if raw == 'tous':
        return 'tous', None
    try:
        cid = int(raw)
    except (TypeError, ValueError):
        return 'tous', None
    if str(cid) in allowed[1:]:
        return str(cid), cid
    return 'tous', None


def attach_impayes_tab_context(request, context, groupes):
    ids = []
    for g in groupes or []:
        cid = g.get('classe_id')
        if cid is not None:
            ids.append(cid)
    key, cid = resolve_impayes_classe(request, ids)
    context['initial_impayes_classe_key'] = key
    context['initial_impayes_classe_id'] = cid
    context['initial_impayes_panel_id'] = (
        'imp-panel-tous' if key == 'tous' else 'imp-panel-classe-' + key
    )
    return context


CAISSE_VUE_CHOICES = ('entrees', 'sorties')


def attach_caisse_tab_context(request, context):
    vue = resolve_main_section_tab(request, 'vue', CAISSE_VUE_CHOICES, 'entrees')
    context['initial_caisse_vue'] = vue
    context['initial_caisse_panel_id'] = 'caisse-panel-' + vue
    return context
