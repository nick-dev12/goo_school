"""
Signals pour la gestion automatique des notes d'examens
"""
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.db import transaction
from ..model.session_examen_model import SessionExamen
from ..model.note_examen_model import NoteExamen
from ..model.eleve_model import Eleve
from ..model.affectation_model import AffectationProfesseur


@receiver(m2m_changed, sender=SessionExamen.classes.through)
def creer_notes_examen_automatiques_classes(sender, instance, action, **kwargs):
    """
    Créer automatiquement les notes d'examen quand des classes sont ajoutées à une session
    """
    if action == "post_add":
        with transaction.atomic():
            creer_notes_pour_session(instance)


@receiver(m2m_changed, sender=SessionExamen.matieres.through)
def creer_notes_examen_automatiques_matieres(sender, instance, action, **kwargs):
    """
    Créer automatiquement les notes d'examen quand des matières sont ajoutées à une session
    """
    if action == "post_add":
        with transaction.atomic():
            creer_notes_pour_session(instance)


def creer_notes_pour_session(session):
    """
    Créer les notes d'examen pour tous les élèves des classes de la session,
    pour toutes les matières de la session.
    
    Règle : UNE note d'examen par (eleve, session, matiere)
    """
    # Récupérer toutes les classes et matières de la session
    classes = session.classes.all()
    matieres = session.matieres.all()
    
    # Si pas de classes ou pas de matières, ne rien faire
    if not classes.exists() or not matieres.exists():
        return
    
    # Pour chaque classe
    for classe in classes:
        # Récupérer tous les élèves de la classe
        eleves = Eleve.objects.filter(
            classe=classe,
            actif=True
        )
        
        # Pour chaque élève
        for eleve in eleves:
            # Pour chaque matière de la session
            for matiere in matieres:
                # Déterminer le professeur selon le type d'établissement
                professeur = None
                
                # Vérifier le type d'établissement
                etablissement = classe.etablissement
                if etablissement and etablissement.type_etablissement not in ['primaire', 'primary']:
                    # Pour collège/lycée, récupérer le professeur via AffectationProfesseur
                    affectation = AffectationProfesseur.objects.filter(
                        classe=classe,
                        matiere=matiere,
                        actif=True
                    ).first()
                    
                    if affectation and affectation.professeur:
                        professeur = affectation.professeur
                    else:
                        # Si aucune affectation trouvée, essayer de trouver un professeur
                        # qui enseigne cette matière dans cette classe
                        from ..model.professeur_model import Professeur
                        professeur_matiere = Professeur.objects.filter(
                            etablissement=etablissement,
                            matiere_principale=matiere,
                            actif=True
                        ).first()
                        
                        if not professeur_matiere:
                            # Vérifier les matières secondaires
                            professeur_matiere = Professeur.objects.filter(
                                etablissement=etablissement,
                                matieres_secondaires=matiere,
                                actif=True
                            ).first()
                        
                        professeur = professeur_matiere
                
                # Si aucun professeur trouvé, on ne peut pas créer la note
                # (le champ professeur est NOT NULL)
                if not professeur:
                    continue
                
                # Créer la note d'examen (ou la récupérer si elle existe déjà)
                NoteExamen.objects.get_or_create(
                    eleve=eleve,
                    session_examen=session,
                    matiere=matiere,
                    defaults={
                        'classe': classe,
                        'professeur': professeur,
                        'absent': False,
                        'note': None,
                        'bareme': 20,
                    }
                )

