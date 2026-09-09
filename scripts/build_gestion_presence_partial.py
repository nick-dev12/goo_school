"""Génère les partials gestion_presence live en UTF-8."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "school_admin/templates/school_admin/enseignant/gestion_presence.html"
INNER = ROOT / "school_admin/templates/school_admin/enseignant/partials/gestion_presence_live_inner.html"
FRAGMENT = ROOT / "school_admin/templates/school_admin/enseignant/partials/gestion_presence_live_fragment.html"

lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
IF_START = next(i for i, l in enumerate(lines) if '{% if stats.total_classes > 0 %}' in l)
ELSE_START = next(i for i, l in enumerate(lines) if i > IF_START and '{% else %}' in l)

inner_body = "\n".join(lines[IF_START + 1 : ELSE_START])
old_btn = """<a href="{% url 'enseignant:liste_presence' classe_data.classe.id %}{% if classe_data.matiere %}?matiere={{ classe_data.matiere.id }}{% endif %}" class="btn-action primary" title="Faire la liste de présence">
                                            <i class="fas fa-calendar-check"></i>
                                            <span>Faire l'appel</span>
                                        </a>"""
new_btn = """<button type="button"
                                                class="btn-action primary"
                                                title="Faire la liste de présence"
                                                data-open-presence-modal
                                                data-classe-id="{{ classe_data.classe.id }}"
                                                data-matiere-id="{% if classe_data.matiere %}{{ classe_data.matiere.id }}{% endif %}">
                                            <i class="fas fa-calendar-check"></i>
                                            <span>Faire l'appel</span>
                                        </button>"""
inner_body = inner_body.replace(old_btn, new_btn)

INNER.write_text(inner_body + "\n", encoding="utf-8")
FRAGMENT.write_text(
    '<div id="gestion-presence-live-root">\n'
    "{% include 'school_admin/enseignant/partials/gestion_presence_live_inner.html' %}\n"
    "</div>\n",
    encoding="utf-8",
)

new_lines = lines[: IF_START + 1]
new_lines.extend(
    [
        '            <div id="gestion-presence-live-root">',
        "            {% include 'school_admin/enseignant/partials/gestion_presence_live_inner.html' %}",
        "            </div>",
    ]
)
new_lines.extend(lines[ELSE_START:])
TEMPLATE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print("OK gestion_presence partials")
