"""Navigation commune des enseignants, quel que soit le cycle de l'établissement."""

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def enseignant_nav(context):
    request = context["request"]
    primary = request.resolver_match.namespace == "enseignant_primaire"
    ns = "enseignant_primaire" if primary else "enseignant"
    current = request.resolver_match.url_name
    entries = [
        ("accueil", "Accueil", "fa-house", "blue", "dashboard" if primary else "dashboard_enseignant", {"dashboard", "dashboard_enseignant"}),
        ("eleves", "Classe", "fa-chalkboard", "violet", "gestion_eleves", {"gestion_eleves", "detail_eleve", "gestion_classes", "detail_classe"}),
        ("notes", "Notes", "fa-pen-to-square", "orange", "gestion_notes", {"gestion_notes", "noter_eleves", "noter_examen"}),
        ("evaluations", "Évaluations", "fa-clipboard-list", "amber", "liste_evaluations", {"liste_evaluations", "creer_evaluation", "modifier_evaluation", "evaluations_classe"}),
        ("exercices", "Exercices", "fa-book-open", "green", "exercices_maison", {"exercices_maison"}),
        ("presence", "Présence", "fa-calendar-check", "sky", "gestion_presence", {"gestion_presence", "liste_presence", "selection_matiere_presence", "historique_presence", "historique_presence_eleve"}),
        ("profil", "Profil", "fa-user-gear", "slate", "parametres_profil", {"parametres_profil"}),
    ]
    links = [
        {"key": key, "label": label, "icon": icon, "tone": tone,
         "url": reverse(f"{ns}:{route}"), "active": current in active}
        for key, label, icon, tone, route, active in entries
    ]
    by_key = {link["key"]: link for link in links}
    mobile_keys = ("accueil", "eleves", "notes", "evaluations")
    mobile = [by_key[key] for key in mobile_keys if key in by_key]
    extra = [link for link in links if link["key"] not in mobile_keys]
    return {
        "bar": links,
        "mobile": mobile,
        "extra": extra,
        "by_key": by_key,
        "ns": ns,
        "more_active": any(link["active"] for link in extra) or current == "justifications_notes",
        "primary": primary,
    }
