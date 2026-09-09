"""Restaure gestion_notes.html depuis git et recrée le partial UTF-8."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "school_admin/templates/school_admin/enseignant/gestion_notes.html"
INNER = ROOT / "school_admin/templates/school_admin/enseignant/partials/gestion_notes_live_inner.html"
FRAGMENT = ROOT / "school_admin/templates/school_admin/enseignant/partials/gestion_notes_live_fragment.html"

raw = subprocess.check_output(
    ["git", "show", "HEAD:school_admin/templates/school_admin/enseignant/gestion_notes.html"],
    cwd=ROOT,
)
lines = raw.decode("utf-8").splitlines()

# Ligne 67 = {% if stats.total_classes > 0 %}, ligne 431 = {% else %} état vide
IF_START = 66  # index of {% if stats.total_classes > 0 %}
ELSE_START = 430  # index of {% else %} empty state

inner_body = "\n".join(lines[IF_START + 1 : ELSE_START])
INNER.write_text(
    "{% load notes_tags %}\n{% load exam_filters %}\n" + inner_body + "\n",
    encoding="utf-8",
)

FRAGMENT.write_text(
    "{% load notes_tags %}\n"
    "{% load exam_filters %}\n"
    '<div id="gestion-notes-live-root">\n'
    "{% include 'school_admin/enseignant/partials/gestion_notes_live_inner.html' %}\n"
    "</div>\n",
    encoding="utf-8",
)

new_lines = lines[: IF_START + 1]
new_lines.extend(
    [
        '            <div id="gestion-notes-live-root">',
        "            {% include 'school_admin/enseignant/partials/gestion_notes_live_inner.html' %}",
        "            </div>",
    ]
)
new_lines.extend(lines[ELSE_START:])
TEMPLATE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

text = INNER.read_text(encoding="utf-8")
assert "Élève" in text or "élève" in text, "Accents manquants dans le partial"
assert "Ã" not in text, "Mojibake encore présent"
print("Templates restaurés avec encodage UTF-8 correct.")
