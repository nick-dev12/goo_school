"""
Conflits de ressources dans les emplois du temps (enseignant, salle).

Au supérieur, un cours mutualisé — même matière, même enseignant, mêmes horaires, suivi par
plusieurs classes (CM en amphi pour L1 Droit et L1 Gestion, par exemple) — n'est pas un conflit :
on le saisit dans l'emploi du temps de chaque classe concernée.
"""
from __future__ import annotations

JOURS = {
    'lundi': 'lundi', 'mardi': 'mardi', 'mercredi': 'mercredi', 'jeudi': 'jeudi',
    'vendredi': 'vendredi', 'samedi': 'samedi', 'dimanche': 'dimanche',
}


def _chevauche(debut, fin, autre_debut, autre_fin):
    return bool(autre_debut and autre_fin and debut < autre_fin and fin > autre_debut)


def creneaux_compatibles(creneau, periode_id=None, groupe_id=None):
    """
    Deux créneaux qui se chevauchent n'entrent pas en conflit s'ils sont dans des semestres différents,
    ou (pour la même classe) s'ils concernent deux groupes différents (TD G1 et TD G2 en parallèle).
    """
    pid = int(periode_id) if periode_id and str(periode_id).isdigit() else None
    gid = int(groupe_id) if groupe_id and str(groupe_id).isdigit() else None
    if pid and creneau.periode_scolaire_id and creneau.periode_scolaire_id != pid:
        return True
    if gid and creneau.groupe_id and creneau.groupe_id != gid:
        return True
    return False


def _mutualise(creneau, debut, fin, matiere_id, professeur_id):
    """Même cours suivi par une autre classe : même matière, même enseignant, mêmes horaires."""
    return bool(
        matiere_id and creneau.matiere_id == int(matiere_id)
        and professeur_id and creneau.professeur_id == int(professeur_id)
        and creneau.heure_debut == debut and creneau.heure_fin == fin
    )


def conflit_ressources(etablissement, annee_scolaire, emploi_du_temps, jour, debut, fin,
                       professeur_id=None, salle_id=None, matiere_id=None, exclure_creneau_id=None,
                       periode_id=None):
    """
    Renvoie un message d'erreur (str) ou None.
    Contrôle les créneaux des autres emplois du temps actifs de l'établissement pour la même année.
    """
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps

    if not (professeur_id or salle_id):
        return None
    superieur = getattr(etablissement, 'type_etablissement', None) == 'superieur'
    qs = CreneauEmploiDuTemps.objects.filter(
        jour=jour,
        emploi_du_temps__est_actif=True,
        emploi_du_temps__classe__etablissement=etablissement,
    ).select_related('emploi_du_temps__classe', 'matiere', 'salle')
    if annee_scolaire is not None:
        qs = qs.filter(emploi_du_temps__annee_scolaire_fk=annee_scolaire)
    if exclure_creneau_id:
        qs = qs.exclude(id=exclure_creneau_id)
    jour_txt = jour.capitalize()
    for c in qs:
        if not _chevauche(debut, fin, c.heure_debut, c.heure_fin):
            continue
        if creneaux_compatibles(c, periode_id):
            continue  # autre semestre
        meme_edt = emploi_du_temps is not None and c.emploi_du_temps_id == emploi_du_temps.id
        if superieur and not meme_edt and _mutualise(c, debut, fin, matiere_id, professeur_id):
            continue  # cours commun à plusieurs classes
        classe = c.emploi_du_temps.classe.nom
        matiere = c.matiere.nom if c.matiere else 'Sans matière'
        horaire = f"{c.heure_debut:%H:%M}–{c.heure_fin:%H:%M}"
        if professeur_id and c.professeur_id == int(professeur_id) and not meme_edt:
            aide = (" Pour un cours commun à plusieurs classes, gardez exactement la même matière et les mêmes horaires."
                    if superieur else "")
            return (f"L'enseignant a déjà cours le {jour_txt} de {horaire} ({matiere}, {classe}).{aide}")
        if salle_id and c.salle_id == int(salle_id):
            return (f"« {c.salle.nom} » est déjà occupée le {jour_txt} de {horaire} "
                    f"({matiere}, {classe}). Choisissez une autre salle ou un autre horaire.")
    return None
