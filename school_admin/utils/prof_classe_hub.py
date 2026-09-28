"""Helpers for prof « Mes classes » hub (single-class focus)."""


def classe_hub_entries(classes_grouped, classe_id):
    """
    Return (entries, categorie_label) for a selected class id.
    entries: list of classe_data dicts (several if secondaire / multi-matière).
    """
    if not classe_id:
        return [], ''
    try:
        cid = int(classe_id)
    except (TypeError, ValueError):
        return [], ''
    entries = []
    categorie = ''
    for cat, data in (classes_grouped or {}).items():
        for cd in data.get('classes') or []:
            if cd.get('classe') and cd['classe'].id == cid:
                entries.append(cd)
                categorie = cat
    return entries, categorie
