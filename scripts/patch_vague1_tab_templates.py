"""Patch templates Vague 1 — persistance onglets niveau/classe."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "school_admin" / "templates" / "school_admin" / "directeur"

FILES = [
    "certificat_scolarite_liste.html",
    "attestation_reussite_liste.html",
    "attestation_conduite_liste.html",
    "fiche_inscription_liste.html",
    "convocation_liste.html",
]


def patch_file(text: str) -> str:
    text = text.replace(
        '{% if forloop.first %}active{% endif %}"\n                                    data-tab="tab-{{ forloop.counter }}"\n                                    aria-selected="{% if forloop.first %}true{% else %}false{% endif %}">',
        '{% if categorie|lower == initial_niveau_key %}active{% endif %}"\n                                    data-tab="tab-{{ forloop.counter }}"\n                                    data-niveau-key="{{ categorie|lower }}"\n                                    aria-selected="{% if categorie|lower == initial_niveau_key %}true{% else %}false{% endif %}">',
    )
    text = text.replace(
        '<div class="tab-panel {% if forloop.first %}active{% endif %}" id="tab-{{ forloop.counter }}">',
        '<div class="tab-panel {% if categorie|lower == initial_niveau_key %}active{% endif %}" id="tab-{{ forloop.counter }}"{% if categorie|lower != initial_niveau_key %} hidden{% endif %}>',
    )
    text = text.replace(
        'class="classe-subtab-btn matiere-tab-btn {% if forloop.first %}active{% endif %}"\n                                                data-subtab="classe-{{ classe_data.classe.id }}"\n                                                aria-selected="{% if forloop.first %}true{% else %}false{% endif %}">',
        'class="classe-subtab-btn matiere-tab-btn {% if categorie|lower == initial_niveau_key and classe_data.classe.id == initial_classe_id %}active{% endif %}"\n                                                data-subtab="classe-{{ classe_data.classe.id }}"\n                                                data-classe-id="{{ classe_data.classe.id }}"\n                                                aria-selected="{% if categorie|lower == initial_niveau_key and classe_data.classe.id == initial_classe_id %}true{% else %}false{% endif %}">',
    )
    for panel_class in (
        "csc-classe-panel",
        "atr-classe-panel",
        "acd-classe-panel",
        "fic-classe-panel",
        "cnv-classe-panel",
    ):
        old = f'<div class="classe-subtab-content {panel_class} {{% if forloop.first %}}active{{% endif %}}" id="classe-{{{{ classe_data.classe.id }}}}">'
        new = (
            f'<div class="classe-subtab-content {panel_class} '
            f'{{% if categorie|lower == initial_niveau_key and classe_data.classe.id == initial_classe_id %}}active{{% endif %}}" '
            f'id="classe-{{{{ classe_data.classe.id }}}}"'
            f'{{% if categorie|lower != initial_niveau_key or classe_data.classe.id != initial_classe_id %}} hidden{{% endif %}}>'
        )
        text = text.replace(old, new)
    # convocation multiline variant
    text = text.replace(
        'class="classe-subtab-btn matiere-tab-btn {% if forloop.first %}active{% endif %}"\n                                                data-subtab="classe-{{ classe_data.classe.id }}"\n                                                data-classe-id="{{ classe_data.classe.id }}"\n                                                aria-selected="{% if forloop.first %}true{% else %}false{% endif %}">',
        'class="classe-subtab-btn matiere-tab-btn {% if categorie|lower == initial_niveau_key and classe_data.classe.id == initial_classe_id %}active{% endif %}"\n                                                data-subtab="classe-{{ classe_data.classe.id }}"\n                                                data-classe-id="{{ classe_data.classe.id }}"\n                                                aria-selected="{% if categorie|lower == initial_niveau_key and classe_data.classe.id == initial_classe_id %}true{% else %}false{% endif %}">',
    )
    return text


def main():
    for name in FILES:
        path = ROOT / name
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        updated = patch_file(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            print("ok", name)


if __name__ == "__main__":
    main()
