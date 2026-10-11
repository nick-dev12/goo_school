"""
Fiche élève vue par l'établissement : direction / personnel (dossier complet) ou enseignant
(ses matières, l'assiduité et la vie scolaire de l'élève). Valable pour tous les types
d'établissement : primaire (notes primaires), secondaire et supérieur (notes classiques).
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import date

from django.db.models import Q
from django.utils import timezone

from school_admin.services.dashboard.student import (
    ABSENTS,
    SEUIL,
    _sur20,
    devoirs_a_faire,
    evaluations_a_venir,
    presence as stats_presence,
    style_matiere,
)

DOCUMENTS = [
    ('document_acte_naissance', 'Acte de naissance'), ('document_cni', "Pièce d'identité"),
    ('document_passeport', 'Passeport'), ('document_bulletin_precedent', 'Bulletin précédent'),
    ('document_certificat_scolarite', 'Certificat de scolarité'), ('document_livret_scolaire', 'Livret scolaire'),
    ('document_certificat_medical', 'Certificat médical'), ('document_carnet_vaccination', 'Carnet de vaccination'),
    ('document_assurance_maladie', 'Assurance maladie'), ('document_justificatif_domicile', 'Justificatif de domicile'),
    ('document_photo_identite', "Photo d'identité"), ('document_autorisation_parentale', 'Autorisation parentale'),
]
# Pièces attendues pour toute inscription (le reste est facultatif).
DOCUMENTS_ESSENTIELS = ('document_acte_naissance', 'document_photo_identite', 'document_certificat_medical')
LIENS = {'pere': 'Père', 'mere': 'Mère', 'tuteur': 'Tuteur', 'tutrice': 'Tutrice', 'autre': 'Autre'}
STATUT_PRESENCE = {'present': 'Présent', 'absent': 'Absent', 'absent_justifie': 'Absence justifiée',
                   'retard': 'Retard', 'excuse': 'Excusé'}


def est_primaire(etablissement):
    return (etablissement.type_etablissement or '') == 'primary'


def _lib_periode(p):
    if p is None:
        return 'Hors période'
    if hasattr(p, 'get_nom_periode_display'):
        try:
            return p.get_nom_periode_display()
        except Exception:
            pass
    return getattr(p, 'nom_periode', '') or str(p)


# --------------------------------------------------------------------------- notes
def notes_eleve(eleve, annee, primaire, matiere_ids=None, publiees_seulement=False):
    """Toutes les notes de l'année (y compris non publiées pour le personnel), par période et matière."""
    rows = []
    if primaire:
        from school_admin.model.note_primaire_model import NotePrimaire

        qs = NotePrimaire.objects.filter(eleve=eleve).select_related(
            'evaluation_primaire__matiere', 'evaluation_primaire__periode_scolaire')
        if annee:
            qs = qs.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True,
                                                       evaluation_primaire__annee_scolaire=annee))
        if matiere_ids is not None:
            qs = qs.filter(evaluation_primaire__matiere_id__in=matiere_ids)
        for n in qs:
            ev = n.evaluation_primaire
            rows.append((n, ev, ev.matiere, ev.periode_scolaire))
    else:
        from school_admin.model.evaluation_model import Note

        qs = Note.objects.filter(eleve=eleve).select_related(
            'evaluation__matiere', 'evaluation__periode_scolaire', 'matiere')
        if annee:
            qs = qs.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True, evaluation__annee_scolaire=annee))
        if matiere_ids is not None:
            qs = qs.filter(Q(matiere_id__in=matiere_ids) | Q(matiere__isnull=True, evaluation__matiere_id__in=matiere_ids))
        for n in qs:
            ev = n.evaluation
            rows.append((n, ev, n.matiere or ev.matiere, ev.periode_scolaire))

    out = []
    for n, ev, matiere, periode in rows:
        publiee = n.statut_publication == 'publiee' or getattr(n, 'note_publiee', None) is not None
        if publiees_seulement and not publiee:
            continue
        valeur = n.note
        out.append({
            'matiere': matiere, 'matiere_nom': getattr(matiere, 'nom', '') or 'Matière',
            'titre': ev.titre, 'date': ev.date_evaluation, 'periode': periode,
            'absent': bool(getattr(n, 'absent', False)), 'valeur': valeur, 'bareme': ev.bareme,
            'sur20': None if getattr(n, 'absent', False) or valeur is None else _sur20(valeur, ev.bareme),
            'publiee': publiee, 'appreciation': getattr(n, 'appreciation', '') or '',
        })
    out.sort(key=lambda r: (r['date'] or timezone.localdate()), reverse=True)
    return out


def synthese_notes(notes):
    """Regroupe par période puis par matière, avec moyennes sur 20 (simple, non coefficientée)."""
    periodes = OrderedDict()
    # Les notes sans période passent en premier : l'onglet actif par défaut est la dernière vraie période.
    for n in sorted(notes, key=lambda r: (getattr(r['periode'], 'date_debut', None) or date.min,
                                          r['date'] or timezone.localdate())):
        key = getattr(n['periode'], 'id', 0)
        if key not in periodes:
            periodes[key] = {'periode': n['periode'], 'libelle': _lib_periode(n['periode']),
                             'matieres': OrderedDict()}
        mat = periodes[key]['matieres']
        mk = getattr(n['matiere'], 'id', 0)
        if mk not in mat:
            icon, tone = style_matiere(n['matiere_nom'])
            mat[mk] = {'matiere': n['matiere'], 'nom': n['matiere_nom'], 'icon': icon, 'tone': tone, 'notes': []}
        mat[mk]['notes'].append(n)
    result = []
    for p in periodes.values():
        lignes = []
        for m in p['matieres'].values():
            vals = [x['sur20'] for x in m['notes'] if x['sur20'] is not None]
            m['moyenne'] = round(sum(vals) / len(vals), 2) if vals else None
            m['nb'] = len(m['notes'])
            m['absences'] = sum(1 for x in m['notes'] if x['absent'])
            m['brouillons'] = sum(1 for x in m['notes'] if not x['publiee'])
            lignes.append(m)
        lignes.sort(key=lambda m: m['nom'])
        moys = [m['moyenne'] for m in lignes if m['moyenne'] is not None]
        result.append({'periode': p['periode'], 'libelle': p['libelle'], 'matieres': lignes,
                       'moyenne': round(sum(moys) / len(moys), 2) if moys else None,
                       'id': getattr(p['periode'], 'id', 0)})
    return result


def moyennes_officielles(eleve, annee, publiees_seulement=False):
    """Moyennes générales calculées pour les bulletins (une par période)."""
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    qs = MoyennePeriode.objects.filter(eleve=eleve, est_moyenne_generale=True, moyenne_generale__isnull=False)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    if publiees_seulement:
        qs = qs.filter(est_publie=True)
    return [{'periode': _lib_periode(m.periode), 'moyenne': float(m.moyenne_generale), 'rang': m.rang,
             'publie': m.est_publie, 'decision': getattr(m, 'decision_conseil', '') or '',
             'appreciation': getattr(m, 'appreciation_generale', '') or ''}
            for m in qs.select_related('periode').order_by('periode__date_debut')]


# --------------------------------------------------------------------------- vie scolaire
def presences_eleve(eleve, annee, classe=None, limit=12):
    from school_admin.model.presence_model import Presence

    qs = Presence.objects.filter(eleve=eleve)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    stats = stats_presence(eleve, annee, timezone.localdate())
    justifiees = qs.filter(statut='absent_justifie').count()
    recentes = list(qs.exclude(statut='present').select_related('classe', 'professeur').order_by('-date')[:limit])
    for p in recentes:
        p.libelle = STATUT_PRESENCE.get(p.statut, p.statut)
    stats['mois_items'] = list(zip(stats['mois']['labels'], stats['mois']['values']))
    stats.update({'justifiees': justifiees, 'non_justifiees': stats['absences'] - justifiees,
                  'recentes': recentes, 'qs': qs})
    return stats


def sanctions_eleve(eleve, annee, classe=None):
    from school_admin.model.sanction_model import Sanction

    qs = Sanction.objects.filter(eleve=eleve)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    if classe is not None:
        qs = qs.filter(classe=classe)
    items = list(qs.select_related('professeur').order_by('-date_sanction', '-date_creation'))
    return {'items': items, 'total': len(items),
            'graves': sum(1 for s in items if s.gravite in ('grave', 'tres_grave')),
            'non_executees': sum(1 for s in items if not s.executee)}


def famille(eleve):
    from school_admin.model.lien_familial_model import LienFamilial

    comptes = []
    for lien in (LienFamilial.objects.filter(eleve=eleve, actif=True).select_related('parent')
                 .order_by('-est_inscripteur', 'type_lien')):
        p = lien.parent
        comptes.append({'parent': p, 'lien': LIENS.get(lien.type_lien, lien.get_type_lien_display()),
                        'inscripteur': lien.est_inscripteur, 'valide': lien.statut == 'valide',
                        'statut': lien.get_statut_display(), 'email': getattr(p, 'email', '') or '',
                        'connecte': bool(getattr(p, 'last_login', None))})
    fiche = None
    if eleve.parent_nom or eleve.parent_telephone:
        fiche = {'nom': f"{eleve.parent_prenom or ''} {eleve.parent_nom or ''}".strip(),
                 'lien': LIENS.get(eleve.parent_lien, eleve.parent_lien or ''), 'telephone': eleve.parent_telephone,
                 'email': eleve.parent_email, 'profession': eleve.parent_profession, 'adresse': eleve.parent_adresse}
    return {'comptes': comptes, 'fiche': fiche,
            'contact': (comptes[0]['parent'].telephone if comptes else None) or eleve.parent_telephone}


def documents_eleve(eleve):
    lignes = [{'champ': c, 'libelle': l, 'fourni': bool(getattr(eleve, c, False)),
               'essentiel': c in DOCUMENTS_ESSENTIELS} for c, l in DOCUMENTS]
    manquants = [d['libelle'] for d in lignes if d['essentiel'] and not d['fourni']]
    return {'lignes': lignes, 'nb': sum(1 for d in lignes if d['fourni']), 'total': len(lignes),
            'manquants_essentiels': manquants}


def completude(eleve, fam, docs):
    manquants = []
    for champ, libelle in (('date_naissance', 'Date de naissance'), ('lieu_naissance', 'Lieu de naissance'),
                           ('sexe', 'Sexe'), ('nationalite', 'Nationalité'), ('adresse', 'Adresse'),
                           ('photo_profil', 'Photo')):
        if not getattr(eleve, champ, None):
            manquants.append(libelle)
    if not fam['contact']:
        manquants.append('Téléphone du responsable')
    if not fam['comptes']:
        manquants.append('Compte parent lié')
    manquants += docs['manquants_essentiels']
    total = 6 + 2 + len(DOCUMENTS_ESSENTIELS)
    return {'taux': round(100 * (total - len(manquants)) / total), 'manquants': manquants}


def finances(eleve, etablissement, annee):
    try:
        from school_admin.services.recouvrement import devise_etablissement, resume_dette_eleve

        r = resume_dette_eleve(eleve, etablissement, annee)
        devise = devise_etablissement(etablissement)
    except Exception:  # module comptable non configuré : la fiche reste lisible
        return None
    pct = round(float(r.total_paye) / float(r.total_du) * 100) if r.total_du else None
    return {'du': r.total_du, 'paye': r.total_paye, 'reste': r.reste, 'statut': r.statut, 'pct': pct,
            'prochaine': r.prochaine_echeance, 'prochaine_libelle': r.prochaine_libelle,
            'charges': [c for c in r.charges if c.reste > 0][:6], 'devise': devise,
            'libelle_statut': {'a_jour': 'À jour', 'en_attente': 'Échéance à venir', 'en_retard': 'En retard',
                               'impaye': 'Impayé'}.get(r.statut, r.statut)}


def convocations(eleve, annee):
    from school_admin.model.convocation_model import Convocation

    qs = Convocation.objects.filter(eleve=eleve)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    today = timezone.localdate()
    items = list(qs.order_by('-date_convocation')[:5])
    for c in items:
        c.a_venir = c.date_convocation >= today
    return items


# --------------------------------------------------------------------------- assemblage
def construire(eleve, classe, etablissement, annee, vue='direction', professeur=None, matieres_prof=None):
    """
    vue='direction' : dossier complet (notes brouillons comprises, finances, documents).
    vue='enseignant' : notes des matières de l'enseignant (toutes) + moyennes générales publiées.
    """
    primaire = est_primaire(etablissement)
    today = timezone.localdate()
    matiere_ids = [m.id for m in matieres_prof] if matieres_prof is not None else None
    notes = notes_eleve(eleve, annee, primaire, matiere_ids=matiere_ids)
    synth = synthese_notes(notes)
    officielles = moyennes_officielles(eleve, annee, publiees_seulement=(vue != 'direction'))
    pres = presences_eleve(eleve, annee, classe)
    sanc = sanctions_eleve(eleve, annee, classe if vue == 'enseignant' else None)
    fam = famille(eleve)
    docs = documents_eleve(eleve)

    vals = [n['sur20'] for n in notes if n['sur20'] is not None]
    moyenne_notes = round(sum(vals) / len(vals), 2) if vals else None
    derniere = officielles[-1] if officielles else None

    # Évolution des notes (ordre chronologique, 20 dernières) pour le graphique.
    chrono = [n for n in reversed(notes) if n['sur20'] is not None][-20:]
    evolution = {'labels': [n['date'].strftime('%d/%m') if n['date'] else '' for n in chrono],
                 'values': [n['sur20'] for n in chrono],
                 'details': [f"{n['matiere_nom']} · {n['titre']}" for n in chrono]}

    alertes = []
    if pres['taux'] is not None and pres['taux'] < 85:
        alertes.append({'tone': 'bad', 'icon': 'fa-user-xmark',
                        'texte': f"Assiduité faible : {pres['taux']} % ({pres['non_justifiees']} absence(s) non justifiée(s))."})
    if moyenne_notes is not None and moyenne_notes < SEUIL:
        alertes.append({'tone': 'bad', 'icon': 'fa-chart-line',
                        'texte': f"Moyenne des notes sous la moyenne : {moyenne_notes}/20."})
    if sanc['graves']:
        alertes.append({'tone': 'warn', 'icon': 'fa-gavel', 'texte': f"{sanc['graves']} sanction(s) grave(s) cette année."})
    if not fam['contact']:
        alertes.append({'tone': 'warn', 'icon': 'fa-phone-slash', 'texte': "Aucun téléphone de responsable enregistré."})

    fiche = {
        'vue': vue, 'primaire': primaire, 'type_etab': etablissement.type_etablissement, 'classe': classe,
        'notes': notes, 'periodes': synth, 'nb_notes': len(notes), 'moyenne_notes': moyenne_notes,
        'brouillons': sum(1 for n in notes if not n['publiee']),
        'sans_periode': sum(1 for n in notes if n['periode'] is None),
        'officielles': officielles, 'derniere_moyenne': derniere, 'evolution': evolution,
        'presence': pres, 'sanctions': sanc, 'famille': fam, 'documents': docs,
        'convocations': convocations(eleve, annee),
        'alertes': alertes, 'seuil': SEUIL,
        'devoirs': devoirs_a_faire(eleve, classe, annee, today) if classe else [],
        'evaluations': evaluations_a_venir(classe, annee, today, primaire) if classe else [],
        'matieres_prof': matieres_prof or [],
    }
    if vue == 'direction':
        fiche['finances'] = finances(eleve, etablissement, annee)
        fiche['completude'] = completude(eleve, fam, docs)
    if matieres_prof is not None and vue == 'enseignant':
        for m in fiche['matieres_prof']:
            m.style_icon, m.style_tone = style_matiere(m.nom)
    return fiche
