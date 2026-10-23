"""
Tableau de bord élève (V3) : la journée, ce qu'il y a à faire et l'évolution.

Sert l'élève connecté et le parent qui consulte son enfant. Règle : on ne
montre que ce que l'établissement a publié (notes publiées, emploi du temps
publié, moyennes publiées).
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta

from django.db import NotSupportedError
from django.db.models import Count, Q
from django.utils import timezone

JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
JOURS_COURTS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']
SEUIL = 10.0
ABSENTS = ('absent', 'absent_justifie')

# Icône et teinte (ax-tone-*) selon la matière, pour repérer un cours d'un coup d'œil.
_MATIERES = [
    (('math',), 'fa-calculator', 'blue'),
    (('français', 'francais', 'lecture', 'dictée', 'grammaire'), 'fa-book-open', 'red'),
    (('anglais', 'espagnol', 'allemand', 'arabe', 'langue'), 'fa-language', 'violet'),
    (('histoire', 'géo', 'geo'), 'fa-earth-africa', 'green'),
    (('svt', 'biologie', 'sciences', 'éveil', 'eveil'), 'fa-leaf', 'teal'),
    (('physique', 'chimie', 'pc'), 'fa-flask', 'cyan'),
    (('sport', 'eps', 'physique et sportive'), 'fa-person-running', 'orange'),
    (('art', 'dessin', 'musique'), 'fa-palette', 'pink'),
    (('philo',), 'fa-brain', 'violet'),
    (('info', 'numérique'), 'fa-laptop-code', 'blue'),
    (('civique', 'morale', 'emc', 'religi', 'coran'), 'fa-scale-balanced', 'violet'),
]


def style_matiere(nom):
    low = (nom or '').lower()
    for clefs, icon, tone in _MATIERES:
        if any(k in low for k in clefs):
            return icon, tone
    return 'fa-book', 'blue'


def _sur20(valeur, bareme):
    try:
        valeur = float(valeur)
        bareme = float(bareme or 20) or 20.0
    except (TypeError, ValueError):
        return None
    return round(valeur / bareme * 20, 2)


def _valeur_publiee(n):
    """Valeur visible par l'élève : dernière note publiée, sinon la note si elle est publiée."""
    if getattr(n, 'note_publiee', None) is not None:
        return n.note_publiee
    if getattr(n, 'statut_publication', '') == 'publiee':
        return n.note
    return None


def _jours_label(delta):
    if delta <= 0:
        return "aujourd'hui"
    if delta == 1:
        return 'demain'
    return f'dans {delta} jours'


def _date_courte(d):
    return f"{JOURS_COURTS[d.weekday()]} {d.day} {MOIS_COURTS[d.month - 1]}"


# --------------------------------------------------------------------------- notes
def notes_publiees(eleve, annee, primaire):
    """Toutes les notes publiées de l'année, du plus ancien au plus récent."""
    rows = []
    if primaire:
        from school_admin.model.note_primaire_model import NotePrimaire

        qs = NotePrimaire.objects.filter(eleve=eleve, absent=False).filter(
            Q(statut_publication='publiee') | Q(note_publiee__isnull=False)
        )
        if annee:
            qs = qs.filter(annee_scolaire=annee)
        for n in qs.select_related('evaluation_primaire__matiere'):
            ev = n.evaluation_primaire
            val = _valeur_publiee(n)
            s20 = _sur20(val, ev.bareme)
            if s20 is None:
                continue
            rows.append({'matiere': getattr(ev.matiere, 'nom', '') or 'Matière', 'titre': ev.titre,
                         'valeur': val, 'bareme': ev.bareme, 'sur20': s20,
                         'date': ev.date_evaluation, 'publiee_le': n.date_publication,
                         'appreciation': getattr(n, 'appreciation', '') or ''})
    else:
        from school_admin.model.evaluation_model import Note

        qs = Note.objects.filter(eleve=eleve, absent=False).filter(
            Q(statut_publication=Note.STATUT_PUBLIEE) | Q(note_publiee__isnull=False)
        )
        if annee:
            qs = qs.filter(annee_scolaire=annee)
        for n in qs.select_related('evaluation__matiere', 'matiere'):
            ev = n.evaluation
            val = _valeur_publiee(n)
            s20 = _sur20(val, ev.bareme)
            if s20 is None:
                continue
            matiere = getattr(n.matiere, 'nom', '') or getattr(ev.matiere, 'nom', '') or 'Matière'
            rows.append({'matiere': matiere, 'titre': ev.titre, 'valeur': val, 'bareme': ev.bareme,
                         'sur20': s20, 'date': ev.date_evaluation, 'publiee_le': n.date_publication,
                         'appreciation': n.appreciation or ''})
    rows.sort(key=lambda r: (r['date'] or timezone.localdate(), r['publiee_le'] or timezone.now()))
    return rows


# --------------------------------------------------------------------------- emploi du temps
def emploi_du_temps(classe, annee, today, now_time, eleve=None):
    """Créneaux publiés de la semaine, regroupés par jour, et l'état du jour.
    Supérieur : seulement le semestre en cours, le groupe de TD / TP et les UE suivies par l'étudiant."""
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps

    out = {'publie': False, 'non_publie': False, 'jours': [], 'aujourdhui': [], 'en_cours': None,
           'prochain': None, 'heures_semaine': 0}
    if not classe:
        return out
    edts = EmploiDuTemps.objects.filter(classe=classe, est_actif=True)
    if annee:
        edts = edts.filter(annee_scolaire_fk=annee)
    edt = edts.filter(statut_publication='publie').first()
    if not edt:
        out['non_publie'] = edts.exists()
        return out
    out['publie'] = True

    par_jour = defaultdict(list)
    minutes = 0
    qs = CreneauEmploiDuTemps.objects.filter(emploi_du_temps=edt).select_related(
        'matiere', 'professeur', 'salle', 'periode_etablissement', 'periode_scolaire', 'groupe')
    if eleve is not None and getattr(classe.etablissement, 'type_etablissement', None) == 'superieur':
        from school_admin.services.maquette import creneaux_etudiant
        qs = creneaux_etudiant(list(qs), eleve, classe, annee, today)
    for c in qs:
        pe = c.periode_etablissement
        if pe is not None and getattr(pe, 'est_pause', False):
            continue
        debut = c.heure_debut or (pe.heure_debut if pe else None)
        fin = c.heure_fin or (pe.heure_fin if pe else None)
        if not debut or not fin or c.jour not in JOURS:
            continue
        nom = c.matiere.nom if c.matiere else (c.get_type_cours_display() if hasattr(c, 'get_type_cours_display') else 'Cours')
        icon, tone = style_matiere(nom)
        duree = int((datetime.combine(today, fin) - datetime.combine(today, debut)).total_seconds() // 60)
        minutes += max(duree, 0)
        par_jour[c.jour].append({
            'matiere': nom, 'icon': icon, 'tone': tone, 'debut': debut, 'fin': fin, 'duree': duree,
            'debut_txt': debut.strftime('%H:%M'), 'fin_txt': fin.strftime('%H:%M'),
            'salle': getattr(c.salle, 'numero', '') or '',
            'prof': c.professeur.nom_complet if c.professeur else '',
            'type': (c.get_type_cours_display() if c.type_cours and c.type_cours != 'cours' else '')
                    + (f" · {c.groupe.nom}" if getattr(c, 'groupe_id', None) else ''),
        })
    out['heures_semaine'] = round(minutes / 60, 1)

    jour_idx = today.weekday()
    lundi = today - timedelta(days=jour_idx)
    nb_jours = 6 if par_jour.get('samedi') or jour_idx == 5 else 5
    for i in range(nb_jours):
        nom_jour = JOURS[i]
        cours = sorted(par_jour.get(nom_jour, []), key=lambda r: r['debut'])
        date_jour = lundi + timedelta(days=i)
        if i == jour_idx:
            for r in cours:
                if r['fin'] <= now_time:
                    r['etat'] = 'passe'
                elif r['debut'] <= now_time < r['fin']:
                    r['etat'] = 'en_cours'
                    out['en_cours'] = r
                else:
                    r['etat'] = 'a_venir'
                    if out['prochain'] is None:
                        r['dans_min'] = int((datetime.combine(today, r['debut'])
                                             - datetime.combine(today, now_time)).total_seconds() // 60)
                        out['prochain'] = r
            out['aujourdhui'] = cours
        out['jours'].append({'code': nom_jour, 'court': JOURS_COURTS[i], 'date': date_jour,
                             'est_aujourdhui': i == jour_idx, 'cours': cours})
    # Le dimanche, on affiche la semaine qui vient avec lundi sélectionné.
    if jour_idx == 6 and out['jours']:
        out['jours'][0]['est_aujourdhui'] = True
    return out


# --------------------------------------------------------------------------- travail
def devoirs_a_faire(eleve, classe, annee, today, limit=6):
    from school_admin.model.exercice_maison_model import ExerciceMaison

    if not classe:
        return []
    qs = ExerciceMaison.objects.filter(classe=classe, actif=True, date_rendu__gte=today)
    if eleve.etablissement_id:
        qs = qs.filter(etablissement_id=eleve.etablissement_id)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    out = []
    for ex in qs.select_related('matiere').order_by('date_rendu')[:limit]:
        delta = (ex.date_rendu - today).days
        nom = ex.matiere.nom if ex.matiere else 'Matière'
        icon, tone = style_matiere(nom)
        out.append({'titre': ex.titre, 'matiere': nom, 'icon': icon, 'tone': tone,
                    'description': (ex.description or '').strip(), 'date': ex.date_rendu,
                    'jours': delta, 'quand': _jours_label(delta), 'urgent': delta <= 1})
    return out


def evaluations_a_venir(classe, annee, today, primaire, horizon=21, limit=6):
    if not classe:
        return []
    if primaire:
        from school_admin.model.evaluation_primaire_model import EvaluationPrimaire as Ev
    else:
        from school_admin.model.evaluation_model import Evaluation as Ev
    qs = Ev.objects.filter(classe=classe, actif=True,
                           date_evaluation__gte=today, date_evaluation__lte=today + timedelta(days=horizon))
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    out = []
    for ev in qs.select_related('matiere').order_by('date_evaluation')[:limit]:
        delta = (ev.date_evaluation - today).days
        nom = ev.matiere.nom if ev.matiere else 'Matière'
        icon, tone = style_matiere(nom)
        out.append({'titre': ev.titre, 'matiere': nom, 'icon': icon, 'tone': tone, 'date': ev.date_evaluation,
                    'jours': delta, 'quand': _jours_label(delta), 'proche': delta <= 3})
    return out


# --------------------------------------------------------------------------- présence
def presence(eleve, annee, today):
    from school_admin.model.presence_model import Presence

    qs = Presence.objects.filter(eleve=eleve)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    agg = qs.aggregate(total=Count('id'), absents=Count('id', filter=Q(statut__in=ABSENTS)),
                       retards=Count('id', filter=Q(statut='retard')))
    total = agg['total'] or 0
    taux = round((total - agg['absents']) / total * 100, 1) if total else None

    # Assiduité des 6 derniers mois (part des appels où l'élève n'était pas absent).
    mois = OrderedDict()
    y, m = today.year, today.month
    for _ in range(6):
        mois[(y, m)] = [0, 0]
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    debut = min(mois)
    for date, statut in qs.filter(date__gte=datetime(debut[0], debut[1], 1).date()).values_list('date', 'statut'):
        clef = (date.year, date.month)
        if clef in mois:
            mois[clef][0] += 1
            if statut not in ABSENTS:
                mois[clef][1] += 1
    labels, values = [], []
    for (yy, mm), (tot, ok) in sorted(mois.items()):
        if tot:
            labels.append(MOIS_COURTS[mm - 1])
            values.append(round(ok / tot * 100, 1))
    return {'taux': taux, 'total': total, 'absences': agg['absents'] or 0, 'retards': agg['retards'] or 0,
            'mois': {'labels': labels, 'values': values}}


# --------------------------------------------------------------------------- moyenne
def moyenne_publiee(eleve):
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    rows = list(
        MoyennePeriode.objects.filter(eleve=eleve, est_moyenne_generale=True, est_publie=True,
                                      moyenne_generale__isnull=False)
        .select_related('periode').order_by('-periode__date_debut')[:2]
    )
    if not rows:
        return None
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    return {'valeur': float(cur.moyenne_generale), 'periode': cur.periode.nom_periode if cur.periode_id else '',
            'rang': cur.rang, 'delta': round(float(cur.moyenne_generale) - float(prev.moyenne_generale), 2) if prev else None}


# --------------------------------------------------------------------------- assemblage
def build_student_dashboard(eleve, classe, annee, primaire, est_parent=False, now=None):
    from school_admin.model.convocation_model import Convocation

    now = timezone.localtime(now or timezone.now())
    today = now.date()
    edt = emploi_du_temps(classe, annee, today, now.time(), eleve=eleve)
    devoirs = devoirs_a_faire(eleve, classe, annee, today)
    evals = evaluations_a_venir(classe, annee, today, primaire)
    notes = notes_publiees(eleve, annee, primaire)
    pres = presence(eleve, annee, today)
    moy = moyenne_publiee(eleve)
    convocation = (Convocation.objects.filter(eleve=eleve, actif=True, date_convocation__gte=today)
                   .order_by('date_convocation', 'heure_convocation').first())

    moy_notes = round(sum(n['sur20'] for n in notes) / len(notes), 2) if notes else None
    recentes = [n for n in notes if n['publiee_le'] and n['publiee_le'] >= now - timedelta(days=7)]

    # Tendance : moyenne des 5 dernières notes comparée aux 5 précédentes.
    tendance = None
    if len(notes) >= 6:
        last = [n['sur20'] for n in notes[-5:]]
        before = [n['sur20'] for n in notes[-10:-5]]
        tendance = round(sum(last) / len(last) - sum(before) / len(before), 2)

    tu = not est_parent
    alertes = []
    if edt['en_cours']:
        c = edt['en_cours']
        alertes.append({'tone': 'blue', 'icon': 'fa-chalkboard-user', 'titre': f"En cours : {c['matiere']}",
                        'texte': f"Jusqu'à {c['fin_txt']}" + (f" · salle {c['salle']}" if c['salle'] else ''), 'live': True})
    if edt['prochain']:
        c = edt['prochain']
        dans = c['dans_min']
        quand = f"dans {dans} min" if dans < 60 else f"à {c['debut_txt']}"
        alertes.append({'tone': 'blue', 'icon': 'fa-bell', 'titre': f"Prochain cours : {c['matiere']}",
                        'texte': f"{quand.capitalize()}" + (f" · salle {c['salle']}" if c['salle'] else '')
                                 + (f" · {c['prof']}" if c['prof'] else '')})
    for d in devoirs:
        if d['jours'] <= 1:
            alertes.append({'tone': 'orange', 'icon': 'fa-pen-to-square',
                            'titre': f"Devoir à rendre {d['quand']}", 'texte': f"{d['matiere']} · {d['titre']}"})
    for e in evals:
        if e['jours'] <= 3:
            alertes.append({'tone': 'red', 'icon': 'fa-book-open-reader',
                            'titre': (f"Révise : {e['titre']}" if tu else f"Évaluation : {e['titre']}"),
                            'texte': f"{e['matiere']} · {e['quand']} ({_date_courte(e['date'])})"})
    if convocation:
        alertes.append({'tone': 'red', 'icon': 'fa-calendar-check', 'titre': 'Convocation',
                        'texte': f"{convocation.objet} · {_date_courte(convocation.date_convocation)} à "
                                 f"{convocation.heure_convocation.strftime('%H:%M')}"})
    if recentes:
        n = len(recentes)
        alertes.append({'tone': 'green', 'icon': 'fa-star', 'titre': f"{n} nouvelle{'s' if n > 1 else ''} note{'s' if n > 1 else ''}",
                        'texte': ', '.join(sorted({r['matiere'] for r in recentes}))})

    # Moyenne par matière (notes publiées).
    par_matiere = defaultdict(list)
    for n in notes:
        par_matiere[n['matiere']].append(n['sur20'])
    matieres = sorted(({'matiere': k, 'moyenne': round(sum(v) / len(v), 2), 'nb': len(v)}
                       for k, v in par_matiere.items()), key=lambda r: -r['moyenne'])

    mini = [
        {'label': 'Moyenne générale' if moy else 'Moyenne de mes notes' if tu else 'Moyenne des notes',
         'value': moy['valeur'] if moy else moy_notes, 'unit': '/20', 'icon': 'fa-chart-line', 'tone': 'blue',
         'caption': (f"{moy['periode']}" + (f" · rang {moy['rang']}" if moy.get('rang') else '')) if moy
                    else f"{len(notes)} note{'s' if len(notes) > 1 else ''} publiée{'s' if len(notes) > 1 else ''}",
         'trend': ('up' if (moy['delta'] if moy and moy['delta'] is not None else tendance or 0) > 0
                   else 'down' if (moy['delta'] if moy and moy['delta'] is not None else tendance or 0) < 0 else None),
         'delta': moy['delta'] if moy and moy['delta'] is not None else tendance,
         'bad': (moy['valeur'] if moy else (moy_notes or SEUIL)) < SEUIL},
        {'label': 'Assiduité', 'value': pres['taux'], 'unit': '%', 'icon': 'fa-user-check', 'tone': 'green',
         'caption': f"{pres['absences']} absence{'s' if pres['absences'] > 1 else ''} · {pres['retards']} retard{'s' if pres['retards'] > 1 else ''}",
         'bad': pres['taux'] is not None and pres['taux'] < 85},
        {'label': 'Devoirs à rendre', 'value': len(devoirs), 'unit': '', 'icon': 'fa-pen-to-square', 'tone': 'orange',
         'caption': (f"Le prochain {devoirs[0]['quand']}" if devoirs else 'Rien à rendre'), 'bad': any(d['urgent'] for d in devoirs)},
        {'label': 'Évaluations à venir', 'value': len(evals), 'unit': '', 'icon': 'fa-book-open-reader', 'tone': 'red',
         'caption': (f"La prochaine {evals[0]['quand']}" if evals else 'Aucune dans les 3 semaines'),
         'bad': any(e['proche'] for e in evals)},
    ]

    charts = {
        'evolution': {
            'labels': [n['date'].strftime('%d/%m') if n['date'] else '' for n in notes[-20:]],
            'values': [n['sur20'] for n in notes[-20:]],
            'details': [f"{n['matiere']} · {n['titre']}" for n in notes[-20:]],
        },
        'matieres': matieres[:10],
        'presence_mois': pres['mois'],
    }

    return {
        'now': now, 'today': today, 'est_parent': est_parent, 'primaire': primaire,
        'edt': edt, 'devoirs': devoirs, 'evaluations': evals, 'alertes': alertes[:6],
        'notes_recentes': list(reversed(notes[-5:])), 'nb_notes': len(notes),
        'presence': pres, 'moyenne': moy, 'moyenne_notes': moy_notes, 'tendance': tendance,
        'matieres': matieres, 'mini': mini, 'charts': charts, 'convocation': convocation, 'seuil': SEUIL,
    }


def annonces_eleves(etablissement, annee, limit=3):
    from school_admin.model.annonce_model import Annonce

    if not etablissement:
        return [], 0
    base = Annonce.objects.filter(etablissement=etablissement, statut='publiee', actif=True)
    if annee:
        base = base.filter(annee_scolaire=annee)
    base = base.order_by('-date_publication')
    try:
        qs = base.filter(Q(destinataires__contains=['tous']) | Q(destinataires__contains=['eleves']))
        return list(qs[:limit]), qs.count()
    except NotSupportedError:
        rows = [a for a in base if {'tous', 'eleves'} & set(a.destinataires or [])]
        return rows[:limit], len(rows)
