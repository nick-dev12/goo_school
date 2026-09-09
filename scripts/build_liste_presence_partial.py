"""Génère le partial liste_presence_inner.html en UTF-8."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "school_admin/templates/school_admin/enseignant/liste_presence.html"
out = ROOT / "school_admin/templates/school_admin/enseignant/partials/liste_presence_inner.html"

lines = src.read_text(encoding="utf-8").splitlines()
inner = "\n".join(lines[50:256])
old_retour = """<a href="{% url 'enseignant:gestion_eleves' %}" class="btn-secondary">
                        <i class="fas fa-arrow-left"></i>
                        Retour
                    </a>"""
new_retour = """{% if modal_mode %}
                    <button type="button" class="btn-secondary" data-close-presence-modal>
                        <i class="fas fa-times"></i>
                        Fermer
                    </button>
                    {% else %}
                    <a href="{% url 'enseignant:gestion_presence' %}" class="btn-secondary">
                        <i class="fas fa-arrow-left"></i>
                        Retour
                    </a>
                    {% endif %}"""
inner = inner.replace(old_retour, new_retour)
out.write_text('<div class="presence-modal-content">\n' + inner + "\n</div>\n", encoding="utf-8")
assert "Élève" in out.read_text(encoding="utf-8")
print("OK:", out)
