import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "school_admin/templates/school_admin/enseignant"
LIVE_INCLUDE = "{% include 'school_admin/partials/enseignant_live_scripts.html' %}\n"
MODALS_CSS = (
    "    <link rel=\"stylesheet\" "
    "href=\"{% static 'school_admin/css/enseignant/enseignant_modals.css' %}?v=1.0.0\">\n"
)

PAGES = {
    "noter_eleves.html": "notes-noter",
    "noter_examen.html": "notes-noter",
    "liste_evaluations.html": "evaluations-liste",
    "liste_presence.html": "presence-liste",
    "historique_presence_eleve.html": "presence-historique",
    "gestion_eleves.html": "eleves-gestion",
    "detail_eleve.html": "eleve-detail",
    "exercices_maison.html": "exercices",
    "justifications_notes.html": "justifications",
    "parametres_profil.html": "profil",
    "primaire/gestion_notes_primaire.html": "notes-gestion",
    "primaire/noter_eleves_primaire.html": "notes-noter",
    "primaire/liste_evaluations_primaire.html": "evaluations-liste",
    "primaire/evaluations_classe_primaire.html": "evaluations-liste",
    "primaire/liste_presence_primaire.html": "presence-liste",
    "primaire/gestion_eleves_primaire.html": "eleves-gestion",
    "primaire/detail_eleve_primaire.html": "eleve-detail",
    "primaire/exercices_maison_primaire.html": "exercices",
    "primaire/justifications_notes_primaire.html": "justifications",
    "primaire/parametres_profil_primaire.html": "profil",
}

MODAL_PAGES = {
    "eleves-gestion",
    "exercices",
    "justifications",
    "profil",
    "eleve-detail",
    "presence-historique",
    "notes-gestion",
}

for rel, page in PAGES.items():
    path = BASE / rel
    if not path.exists():
        print("SKIP missing", rel)
        continue
    text = path.read_text(encoding="utf-8")
    orig = text
    if "data-live-page" not in text:
        if re.search(r"<body\s[^>]*>", text):
            text = re.sub(
                r"<body(\s[^>]*)?>",
                f'<body data-live-page="{page}"\\1>',
                text,
                count=1,
            )
        else:
            text = text.replace("<body>", f'<body data-live-page="{page}">', 1)
    if "enseignant_live_scripts.html" not in text:
        text = text.replace("</body>", LIVE_INCLUDE + "</body>", 1)
    if page in MODAL_PAGES and "enseignant_modals.css" not in text and "</head>" in text:
        text = text.replace("</head>", MODALS_CSS + "</head>", 1)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print("UPDATED", rel)

print("done")
