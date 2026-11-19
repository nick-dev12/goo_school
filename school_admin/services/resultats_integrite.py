"""Empreinte des sources d'une moyenne : notes, évaluations, programme et pondération.
Une modification, y compris par QuerySet.update/delete, impose un nouveau calcul.
Aucune donnée nominative n'est conservée dans cette empreinte.
"""
import hashlib
import json
from decimal import Decimal
from django.db.models import Q


def _valeurs(obj, exclus=()):
    return {f.attname: getattr(obj, f.attname) for f in obj._meta.concrete_fields
            if f.name not in set(exclus) | {'id', 'date_creation', 'date_modification', 'created_at', 'updated_at'}}


def empreinte_moyenne(moyenne, cache=None):
    cache = {} if cache is None else cache
    def lire(cle, lecture):
        if cle not in cache:
            cache[cle] = lecture()
        return cache[cle]
    from school_admin.model.evaluation_model import Note, Evaluation
    from school_admin.model.note_examen_model import NoteExamen
    from school_admin.model.session_examen_model import SessionExamen, ReglesExamen
    from school_admin.model.ponderation_model import Ponderation
    from school_admin.model.module_model import ModuleClasse
    from school_admin.model.inscription_eleve_model import InscriptionEleve
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.maquette_model import InscriptionPedagogique
    if not moyenne.matiere_id or moyenne.est_moyenne_generale:
        return ''
    m = lire(('matiere',moyenne.matiere_id),lambda: Matiere.objects.get(pk=moyenne.matiere_id))
    classe_id = lire(('classe',moyenne.eleve_id,moyenne.annee_scolaire_id),lambda:
        (InscriptionEleve.objects.filter(eleve_id=moyenne.eleve_id,annee_scolaire_id=moyenne.annee_scolaire_id)
        .order_by('-pk').values_list('classe_id',flat=True).first()) or moyenne.eleve.classe_id)
    cle = (classe_id,moyenne.periode_id,m.pk,moyenne.annee_scolaire_id)
    evaluations = lire(('evaluations',cle),lambda: list(Evaluation.objects.filter(classe_id=classe_id,
                   periode_scolaire_id=moyenne.periode_id,matiere_id=m.pk).order_by('pk')))
    notes = lire(('notes',cle),lambda: list(Note.objects.filter(evaluation_id__in=[e.pk for e in evaluations]).order_by('pk')))
    sessions = lire(('sessions',cle),lambda: list(SessionExamen.objects.filter(etablissement_id=moyenne.etablissement_id,
              periode_id=moyenne.periode_id,annee_scolaire_id=moyenne.annee_scolaire_id,
              classes__id=classe_id,matieres__id=m.pk).distinct().order_by('pk')))
    examens = lire(('examens',cle),lambda: list(NoteExamen.objects.filter(matiere_id=m.pk,
                 session_examen_id__in=[session.pk for session in sessions]).order_by('pk')))
    regle = lire(('regle',moyenne.etablissement_id),lambda:
          ReglesExamen.objects.filter(etablissement_id=moyenne.etablissement_id).first()
          or ReglesExamen(etablissement_id=moyenne.etablissement_id))
    ponderations = lire(('ponderations',moyenne.etablissement_id),lambda: list(
        Ponderation.objects.filter(etablissement_id=moyenne.etablissement_id,actif=True).order_by('pk')))
    ins = lire(('inscription',moyenne.eleve_id,moyenne.annee_scolaire_id),lambda:
        InscriptionPedagogique.objects.filter(eleve_id=moyenne.eleve_id,annee_scolaire_id=moyenne.annee_scolaire_id).first())
    data = {
        'v': 1, 'classe': classe_id, 'annee': moyenne.annee_scolaire_id, 'periode': moyenne.periode_id,
        'resultat': [format(Decimal(str(v)).normalize(), 'f') if v is not None else None
                     for v in (moyenne.moyenne_matiere,moyenne.coefficient,moyenne.credits)],
        'matiere': _valeurs(m),
        'programme': lire(('programme',classe_id),lambda: list(ModuleClasse.objects.filter(classe_id=classe_id).order_by('pk').values())),
        'inscription': _valeurs(ins) if ins else None,
        'options': lire(('options',ins.pk),lambda: list(ins.ues_optionnelles.order_by('pk').values_list('pk',flat=True))) if ins else [],
        'evaluations': [_valeurs(e) for e in evaluations],
        'notes': [_valeurs(n, ('date_saisie', 'appreciation')) for n in notes if n.eleve_id == moyenne.eleve_id],
        'examens': [_valeurs(n, ('date_saisie','date_soumission','date_publication')) for n in examens if n.eleve_id == moyenne.eleve_id],
        'sessions': [{k:getattr(session,k) for k in ('id','type_session','compte_bulletin','est_annule','actif')} for session in sessions],
        'regles': {k: getattr(regle, k) for k in ('absence_injustifiee','regle_rattrapage','poids_cc')},
        'ponderations': [_valeurs(p) for p in ponderations],
    }
    return hashlib.sha256(json.dumps(data, default=str, sort_keys=True).encode()).hexdigest()
