"""
Planning des examens : classes concernées par une épreuve, contrôles d'un créneau
(conflits, capacité, surveillance) et état d'avancement d'une session.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError


def classes_concernees(session, matiere):
    """Classes de la session qui passent cette épreuve (au supérieur : selon les liaisons matière / classes)."""
    classes = list(session.classes.all())
    if getattr(session.etablissement, 'type_etablissement', None) == 'superieur':
        ids = set(matiere.get_classe_ids_pour_affectation_superieur())
        if ids:
            classes = [c for c in classes if c.id in ids]
    return classes


def _effectif(classe):
    from school_admin.model.eleve_model import Eleve
    return Eleve.objects.filter(classe=classe, actif=True).count()


def messages_validation(exc):
    if hasattr(exc, 'message_dict'):
        return [m for msgs in exc.message_dict.values() for m in msgs]
    return list(getattr(exc, 'messages', [str(exc)]))


def verifier_creneau(creneau):
    """
    Renvoie (erreurs, avertissements) pour un créneau non encore enregistré.
    Erreurs bloquantes : règles du modèle (horaires, dates de session, salle, surveillant, classes).
    Avertissements : capacité de salle, surveillant qui enseigne la matière à ces classes.
    """
    erreurs, avertissements = [], []
    try:
        creneau.clean()
    except ValidationError as exc:
        erreurs.extend(messages_validation(exc))
    if erreurs:
        return erreurs, avertissements

    classes = classes_concernees(creneau.session_examen, creneau.matiere)
    if creneau.salle_id:
        effectif = sum(_effectif(c) for c in classes)
        cap = creneau.salle.capacite_max or 0
        if cap and effectif > cap:
            avertissements.append(
                f"La salle {creneau.salle.nom} ({cap} places) est trop petite pour {effectif} candidats : "
                f"prévoyez une deuxième salle.")
    if creneau.surveillant_id:
        from school_admin.model.affectation_model import AffectationProfesseur
        if AffectationProfesseur.objects.filter(professeur_id=creneau.surveillant_id, matiere=creneau.matiere,
                                                classe__in=classes, actif=True).exists():
            avertissements.append(
                f"{creneau.surveillant.nom_complet} enseigne {creneau.matiere.nom} à ces classes : "
                f"il est d'usage qu'un autre enseignant surveille l'épreuve.")
    return erreurs, avertissements


def avancement_session(session):
    """Contrôles pour l'écran de gestion : épreuves non planifiées, notes saisies / attendues."""
    from school_admin.model.note_examen_model import NoteExamen
    from school_admin.model.eleve_model import Eleve

    matieres = list(session.matieres.all())
    planifiees = set(session.creneaux.filter(actif=True, est_annule=False).values_list('matiere_id', flat=True))
    attendues = 0
    for m in matieres:
        attendues += Eleve.objects.filter(classe__in=classes_concernees(session, m), actif=True).count()
    notes = NoteExamen.objects.filter(session_examen=session, actif=True)
    saisies = notes.filter(soumis=True).count() + notes.filter(soumis=False).exclude(statut_publication='brouillon').count()
    return {
        'non_planifiees': [m for m in matieres if m.id not in planifiees],
        'nb_epreuves': len(matieres),
        'nb_planifiees': len([m for m in matieres if m.id in planifiees]),
        'notes_attendues': attendues,
        'notes_validees': saisies,
        'notes_brouillon': notes.filter(soumis=False, statut_publication='brouillon').exclude(note__isnull=True, absent=False).count(),
        'taux_notes': round(100 * saisies / attendues) if attendues else 0,
    }
