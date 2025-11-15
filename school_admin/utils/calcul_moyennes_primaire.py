# school_admin/utils/calcul_moyennes_primaire.py

"""
Utilitaires pour le calcul des moyennes multi-matières pour les enseignants du primaire.
"""

from decimal import Decimal
from django.db.models import Avg, Count, Q
from ..model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire
from ..model.evaluation_primaire_model import EvaluationPrimaire
import math


def arrondir_note_intelligemment(note):
    """
    Arrondit une note de manière intelligente selon sa proximité avec les paliers.
    
    Règles d'arrondi :
    - Si la décimale est >= 0.80 : arrondir à l'entier supérieur
      Ex: 8.80 → 9.00, 12.85 → 13.00
    
    - Si la décimale est entre 0.33 et 0.79 : arrondir à X.50
      Ex: 8.33 → 8.50, 8.40 → 8.50, 8.75 → 9.00
    
    - Si la décimale est < 0.33 : garder l'entier
      Ex: 8.20 → 8.00, 8.32 → 8.00
    
    Args:
        note: float ou Decimal - la note brute
    
    Returns:
        Decimal: La note arrondie
    """
    if note is None:
        return None
    
    note_float = float(note)
    partie_entiere = math.floor(note_float)
    partie_decimale = note_float - partie_entiere
    
    # Si >= 0.80 : arrondir à l'entier supérieur
    if partie_decimale >= 0.80:
        note_arrondie = partie_entiere + 1.0
    
    # Si >= 0.33 et < 0.80 : arrondir à X.50
    elif partie_decimale >= 0.33:
        note_arrondie = partie_entiere + 0.5
    
    # Si < 0.33 : garder l'entier
    else:
        note_arrondie = float(partie_entiere)
    
    return Decimal(str(note_arrondie))


def calculer_moyenne_matiere(eleve, matiere, periode):
    """
    Calcule la moyenne d'un élève pour une matière donnée sur une période.
    
    Args:
        eleve: Instance de l'élève
        matiere: Instance de la matière
        periode: Instance de la période scolaire
    
    Returns:
        Decimal: La moyenne sur 20, ou None si aucune note
    """
    # Récupérer toutes les évaluations de la matière pour cette période
    evaluations = EvaluationPrimaire.objects.filter(
        classe=eleve.classe,
        matiere=matiere,
        periode_scolaire=periode,
        actif=True
    )
    
    # Récupérer les notes de l'élève pour ces évaluations
    notes = NotePrimaire.objects.filter(
        eleve=eleve,
        evaluation_primaire__in=evaluations,
        absent=False
    ).exclude(note__isnull=True)
    
    if not notes.exists():
        return None
    
    # Calculer la moyenne sur 20
    total = sum(note.note_sur_20 for note in notes if note.note_sur_20 is not None)
    nombre_notes = notes.count()
    
    if nombre_notes == 0:
        return None
    
    moyenne = round(Decimal(total) / Decimal(nombre_notes), 2)
    
    # Enregistrer la moyenne dans la base de données
    evaluations_ids = list(evaluations.values_list('id', flat=True))
    MoyenneMatierePrimaire.calculer_et_enregistrer(
        eleve,
        matiere,
        periode,
        mode_calcul='toutes',
        evaluations_utilisees=[str(eval_id) for eval_id in evaluations_ids],
        ponderation='50_50',
    )
    
    return moyenne


def calculer_moyenne_generale(eleve, periode):
    """
    Calcule la moyenne générale d'un élève (toutes matières confondues) pour une période.
    
    Args:
        eleve: Instance de l'élève
        periode: Instance de la période scolaire
    
    Returns:
        dict: {
            'moyenne': Decimal ou None,
            'nombre_matieres': int,
            'details_matieres': list of dict
        }
    """
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    
    # Récupérer toutes les matières enseignées dans la classe de l'élève
    affectations = AffectationProfesseurPrimaire.objects.filter(
        classe=eleve.classe,
        actif=True
    ).prefetch_related('matieres')
    
    # Collecter toutes les matières uniques
    matieres = set()
    for affectation in affectations:
        matieres.update(affectation.matieres.all())
    
    if not matieres:
        return {
            'moyenne': None,
            'nombre_matieres': 0,
            'details_matieres': []
        }
    
    # Calculer la moyenne pour chaque matière
    moyennes_matieres = []
    total_moyennes = Decimal('0.00')
    nombre_matieres_avec_notes = 0
    
    for matiere in matieres:
        moyenne_matiere = calculer_moyenne_matiere(eleve, matiere, periode)
        
        details = {
            'matiere': matiere,
            'moyenne': moyenne_matiere,
            'nom_matiere': matiere.nom,
            'code_matiere': matiere.code
        }
        moyennes_matieres.append(details)
        
        if moyenne_matiere is not None:
            total_moyennes += moyenne_matiere
            nombre_matieres_avec_notes += 1
    
    # Calculer la moyenne générale
    if nombre_matieres_avec_notes > 0:
        moyenne_generale = round(total_moyennes / Decimal(nombre_matieres_avec_notes), 2)
    else:
        moyenne_generale = None
    
    return {
        'moyenne': moyenne_generale,
        'nombre_matieres': len(matieres),
        'nombre_matieres_avec_notes': nombre_matieres_avec_notes,
        'details_matieres': sorted(moyennes_matieres, key=lambda x: x['nom_matiere'])
    }


def calculer_moyenne_classe_matiere(classe, matiere, periode):
    """
    Calcule la moyenne de la classe pour une matière donnée sur une période.
    
    Args:
        classe: Instance de la classe
        matiere: Instance de la matière
        periode: Instance de la période scolaire
    
    Returns:
        dict: {
            'moyenne': Decimal ou None,
            'nombre_eleves': int,
            'nombre_eleves_notes': int,
            'meilleure_note': Decimal ou None,
            'moins_bonne_note': Decimal ou None
        }
    """
    from ..model.eleve_model import Eleve
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True)
    
    if not eleves.exists():
        return {
            'moyenne': None,
            'nombre_eleves': 0,
            'nombre_eleves_notes': 0,
            'meilleure_note': None,
            'moins_bonne_note': None
        }
    
    # Calculer la moyenne pour chaque élève
    moyennes_eleves = []
    for eleve in eleves:
        moyenne_eleve = calculer_moyenne_matiere(eleve, matiere, periode)
        if moyenne_eleve is not None:
            moyennes_eleves.append(moyenne_eleve)
    
    if not moyennes_eleves:
        return {
            'moyenne': None,
            'nombre_eleves': eleves.count(),
            'nombre_eleves_notes': 0,
            'meilleure_note': None,
            'moins_bonne_note': None
        }
    
    # Calculer la moyenne de la classe
    moyenne_classe = round(sum(moyennes_eleves) / len(moyennes_eleves), 2)
    
    return {
        'moyenne': moyenne_classe,
        'nombre_eleves': eleves.count(),
        'nombre_eleves_notes': len(moyennes_eleves),
        'meilleure_note': max(moyennes_eleves),
        'moins_bonne_note': min(moyennes_eleves)
    }


def calculer_toutes_moyennes_classe(classe, periode):
    """
    Calcule toutes les moyennes pour tous les élèves d'une classe sur une période.
    Utile pour générer les relevés de notes.
    
    Args:
        classe: Instance de la classe
        periode: Instance de la période scolaire
    
    Returns:
        list: Liste de dictionnaires contenant les moyennes par élève
    """
    from ..model.eleve_model import Eleve
    from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    
    # Récupérer tous les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
    
    # Récupérer toutes les matières enseignées dans la classe
    affectations = AffectationProfesseurPrimaire.objects.filter(
        classe=classe,
        actif=True
    ).prefetch_related('matieres')
    
    matieres = set()
    for affectation in affectations:
        matieres.update(affectation.matieres.all())
    
    matieres_list = sorted(matieres, key=lambda m: m.nom)
    
    # Récupérer les moyennes ENREGISTRÉES (pas de recalcul)
    resultats = []
    for eleve in eleves:
        moyennes_par_matiere = {}
        total_moyennes = Decimal('0.00')
        nombre_matieres_avec_notes = 0
        
        for matiere in matieres_list:
            # Récupérer la moyenne ENREGISTRÉE depuis la base de données
            moyenne_obj = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                matiere=matiere,
                periode_scolaire=periode
            ).first()
            
            moyenne = moyenne_obj.moyenne if moyenne_obj and moyenne_obj.moyenne is not None else None
            moyennes_par_matiere[matiere.code] = {
                'matiere': matiere,
                'moyenne': moyenne
            }
        
            if moyenne is not None:
                total_moyennes += moyenne
                nombre_matieres_avec_notes += 1
        
        # Calculer la moyenne générale à partir des moyennes enregistrées
        moyenne_generale = round(total_moyennes / Decimal(nombre_matieres_avec_notes), 2) if nombre_matieres_avec_notes > 0 else None
        
        resultats.append({
            'eleve': eleve,
            'moyennes_par_matiere': moyennes_par_matiere,
            'moyenne_generale': moyenne_generale,
            'nombre_matieres_avec_notes': nombre_matieres_avec_notes
        })
    
    return resultats


def calculer_moyenne_avec_mode(
    eleve,
    matiere,
    periode,
    mode_calcul='toutes',
    ponderation='50_50',
    evaluations_selectionnees=None,
):
    """
    Calcule la moyenne d'un élève selon différents modes de calcul.
    
    NOUVELLE LOGIQUE AVEC EXAMENS ET NOTES RETENUES :
    1. Réinitialiser toutes les notes à retenue=False
    2. Séparer les notes d'examens des autres notes
    3. Calculer la moyenne des devoirs/interrogations (selon mode_calcul ou sélection manuelle)
    4. Marquer les notes UTILISÉES comme retenue=True
    5. Si examen présent : combiner moyenne_devoirs et note_examen selon pondération
    6. Si pas d'examen : retourner simplement la moyenne des devoirs/interrogations
    
    Args:
        eleve: Instance de l'élève
        matiere: Instance de la matière
        periode: Instance de la période scolaire
        mode_calcul: str - 'toutes', '2_meilleures', '3_meilleures', '4_meilleures', 'manuel'
        ponderation: str - '40_60', '50_50', '30_70' (devoirs/examen)
        evaluations_selectionnees: list - IDs des évaluations sélectionnées (pour mode 'manuel')
    
    Returns:
        Decimal: La moyenne sur 20, ou None si aucune note
    """
    from ..model.note_examen_model import NoteExamen
    from ..model.creneau_examen_model import CreneauExamen
    from django.db import transaction
    
    with transaction.atomic():
        evaluations_utilisees_set = set(str(value) for value in (evaluations_selectionnees or []))

        # ÉTAPE 0 : Réinitialiser toutes les notes de cet élève à retenue=False
        all_evaluations = EvaluationPrimaire.objects.filter(
            classe=eleve.classe,
            matiere=matiere,
            periode_scolaire=periode,
            actif=True
        )
        
        NotePrimaire.objects.filter(
            eleve=eleve,
            evaluation_primaire__in=all_evaluations
        ).update(retenue=False)
        
        # Réinitialiser aussi les notes d'examens (basé sur la session)
        from ..model.session_examen_model import SessionExamen
        
        sessions_examens_reset = SessionExamen.objects.filter(
            classes=eleve.classe,
            periode=periode,
            matieres=matiere,
            actif=True
        )
        
        NoteExamen.objects.filter(
            eleve=eleve,
            session_examen__in=sessions_examens_reset,
            matiere=matiere
        ).update(retenue=False)
        
        # ÉTAPE 1 : Récupérer les notes de DEVOIRS/INTERROGATIONS selon la sélection
        evaluations_a_utiliser = all_evaluations
        if evaluations_selectionnees:
            # Filtrer uniquement les évaluations sélectionnées (sans les examens)
            eval_ids_normaux = [int(eval_id) for eval_id in evaluations_selectionnees if not str(eval_id).startswith('examen_')]
            evaluations_a_utiliser = all_evaluations.filter(id__in=eval_ids_normaux)
        
        notes_devoirs = NotePrimaire.objects.filter(
            eleve=eleve,
            evaluation_primaire__in=evaluations_a_utiliser,
            absent=False
        ).exclude(note__isnull=True).select_related('evaluation_primaire')
    
        # Convertir les notes et gérer la règle "2 interrogations = 1 devoir"
        notes_devoirs_avec_objets = []  # Liste de tuples (note_sur_20, objets_notes)
        notes_sur_10 = []  # Pour regrouper les interrogations
        
        for note in notes_devoirs:
            if note.note_sur_20 is not None:
                if note.evaluation_primaire.bareme == 10:
                    # C'est une interrogation (sur 10)
                    notes_sur_10.append((float(note.note_sur_20), note))
                else:
                    # C'est un devoir (sur 20)
                    notes_devoirs_avec_objets.append((float(note.note_sur_20), [note]))
        
        # Regrouper les interrogations par paires pour faire des "devoirs équivalents"
        # Trier les interrogations par note décroissante
        notes_sur_10.sort(key=lambda x: x[0], reverse=True)
        
        # Créer des paires d'interrogations
        i = 0
        while i < len(notes_sur_10) - 1:
            # Prendre 2 interrogations consécutives (les meilleures disponibles)
            note1_val, note1_obj = notes_sur_10[i]
            note2_val, note2_obj = notes_sur_10[i + 1]
            
            # Calculer la moyenne des 2 interrogations (ce qui donne une note sur 20)
            moyenne_paire = (note1_val + note2_val) / 2
            
            # Ajouter cette paire comme un "devoir équivalent"
            notes_devoirs_avec_objets.append((moyenne_paire, [note1_obj, note2_obj]))
            i += 2
        
        # Si il reste une interrogation seule, l'ajouter telle quelle
        if i < len(notes_sur_10):
            note_val, note_obj = notes_sur_10[i]
            notes_devoirs_avec_objets.append((note_val, [note_obj]))
    
        # ÉTAPE 2 : Récupérer la note d'EXAMEN (basée sur la session, pas le créneau)
        from ..model.session_examen_model import SessionExamen
        
        sessions_examens = SessionExamen.objects.filter(
            classes=eleve.classe,
            periode=periode,
            matieres=matiere,
            actif=True
        )
        selected_exam_session_ids = []
        if evaluations_selectionnees:
            for eval_id in evaluations_selectionnees:
                eval_id_str = str(eval_id)
                if eval_id_str.startswith('examen_'):
                    session_id_str = eval_id_str.replace('examen_', '')
                    if session_id_str.isdigit():
                        selected_exam_session_ids.append(int(session_id_str))
        
        note_examen_sur_20 = None
        note_examen_obj = None
        note_examen_qs = NoteExamen.objects.filter(
            eleve=eleve,
            matiere=matiere,
            classe=eleve.classe,
            session_examen__periode=periode
        ).select_related('session_examen').order_by('-date_saisie')

        if selected_exam_session_ids:
            note_examen_qs = note_examen_qs.filter(session_examen_id__in=selected_exam_session_ids)

        # Prioriser les notes présentes et non absentes
        note_examen_qs_presentes = note_examen_qs.filter(absent=False).exclude(note__isnull=True)
        note_examen_obj = note_examen_qs_presentes.first() or note_examen_qs.exclude(note__isnull=True).first()

        if note_examen_obj:
            if note_examen_obj.note_sur_20 is not None:
                note_examen_sur_20 = float(note_examen_obj.note_sur_20)
            elif note_examen_obj.note is not None and note_examen_obj.bareme and note_examen_obj.bareme > 0:
                note_examen_sur_20 = float((note_examen_obj.note / note_examen_obj.bareme) * 20)
    
        # ÉTAPE 3 : Calculer la moyenne des devoirs/interrogations
        notes_contribution = []
        
        if notes_devoirs_avec_objets:
            # Trier par ordre décroissant (meilleures en premier)
            notes_devoirs_avec_objets.sort(key=lambda x: x[0], reverse=True)
            
            # Sélectionner selon le mode de calcul
            if mode_calcul == '1_meilleure':
                notes_selectionnees = notes_devoirs_avec_objets[:1]
            elif mode_calcul == '2_meilleures':
                notes_selectionnees = notes_devoirs_avec_objets[:2]
            elif mode_calcul == '3_meilleures':
                notes_selectionnees = notes_devoirs_avec_objets[:3]
            elif mode_calcul == '4_meilleures':
                notes_selectionnees = notes_devoirs_avec_objets[:4]
            else:  # 'toutes'
                notes_selectionnees = notes_devoirs_avec_objets
            
            if notes_selectionnees:
                # Extraire uniquement les valeurs pour le calcul
                valeurs_notes = [n[0] for n in notes_selectionnees]
                notes_contribution.extend(valeurs_notes)
                
                # Marquer les notes sélectionnées comme retenues
                # Chaque élément peut être une liste d'objets (pour les paires d'interrogations)
                for _, notes_objets_list in notes_selectionnees:
                    for note_obj in notes_objets_list:
                        note_obj.retenue = True
                        note_obj.save()
                        evaluations_utilisees_set.add(str(note_obj.evaluation_primaire_id))
        
        # Ajouter la note d'examen aux contributions si disponible
        if note_examen_sur_20 is not None:
            notes_contribution.append(note_examen_sur_20)
            if note_examen_obj:
                note_examen_obj.retenue = True
                note_examen_obj.save()
                if note_examen_obj.session_examen_id:
                    evaluations_utilisees_set.add(f"examen_{note_examen_obj.session_examen_id}")
        
        if notes_contribution:
            moyenne_finale = sum(notes_contribution) / len(notes_contribution)
            return (
                round(Decimal(str(moyenne_finale)), 2),
                sorted(evaluations_utilisees_set),
            )
        
        # Aucune note disponible
        return None, sorted(evaluations_utilisees_set)


def get_appreciation_moyenne(moyenne):
    """
    Retourne une appréciation textuelle selon la moyenne.
    
    Args:
        moyenne: Decimal, la moyenne sur 20
    
    Returns:
        str: L'appréciation
    """
    if moyenne is None:
        return "Non évalué"
    elif moyenne >= 16:
        return "Excellent"
    elif moyenne >= 14:
        return "Très bien"
    elif moyenne >= 12:
        return "Bien"
    elif moyenne >= 10:
        return "Assez bien"
    elif moyenne >= 8:
        return "Passable"
    else:
        return "Insuffisant"


def get_repartition_moyennes_classe(classe, matiere, periode):
    """
    Calcule la répartition des moyennes par catégorie pour une classe.
    
    Args:
        classe: Instance de la classe
        matiere: Instance de la matière
        periode: Instance de la période scolaire
    
    Returns:
        dict: Répartition par catégorie
    """
    from ..model.eleve_model import Eleve
    
    eleves = Eleve.objects.filter(classe=classe, actif=True)
    
    repartition = {
        'excellent': 0,      # >= 16
        'tres_bien': 0,      # >= 14
        'bien': 0,           # >= 12
        'assez_bien': 0,     # >= 10
        'passable': 0,       # >= 8
        'insuffisant': 0,    # < 8
        'non_evalue': 0
    }
    
    for eleve in eleves:
        moyenne = calculer_moyenne_matiere(eleve, matiere, periode)
        
        if moyenne is None:
            repartition['non_evalue'] += 1
        elif moyenne >= 16:
            repartition['excellent'] += 1
        elif moyenne >= 14:
            repartition['tres_bien'] += 1
        elif moyenne >= 12:
            repartition['bien'] += 1
        elif moyenne >= 10:
            repartition['assez_bien'] += 1
        elif moyenne >= 8:
            repartition['passable'] += 1
        else:
            repartition['insuffisant'] += 1
    
    # Calculer les pourcentages
    total = eleves.count()
    if total > 0:
        for key in list(repartition.keys()):  # Créer une copie de la liste des clés
            repartition[f'{key}_pct'] = round((repartition[key] / total) * 100, 1)
    
    return repartition

