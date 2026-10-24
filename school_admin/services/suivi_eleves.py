"""
Indicateurs et contrôles des pages de suivi des élèves (liste, scolarité, notes, présence,
bulletins, préinscriptions, réinscriptions), pour tous les types d'établissement.
Chaque calcul est protégé : un module absent ne casse jamais la page.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from school_admin.services.structure_etablissement import _alerte, _sur, _url


def _lib(etab):
    sup = etab.type_etablissement == 'superieur'
    return {'eleves': 'étudiants' if sup else 'élèves', 'Eleves': 'Étudiants' if sup else 'Élèves',
            'classes': 'classes' if sup else 'classes'}


def _kpi(label, value, icon, tone, texte=False, pct=None, bad=False):
    return {'label': label, 'value': value, 'icon': icon, 'tone': tone, 'texte': texte, 'pct': pct, 'bad': bad}


def _eleves(etab):
    from school_admin.model.eleve_model import Eleve

    return Eleve.objects.filter(etablissement=etab, actif=True)


# --------------------------------------------------------------------------- liste des élèves
def controle_liste(etab, annee, stats=None):
    from school_admin.model.lien_familial_model import LienFamilial

    lib = _lib(etab)
    eleves = _eleves(etab)
    nb = eleves.count()
    filles = eleves.filter(sexe='F').count()
    sans_classe = eleves.filter(classe__isnull=True).count()
    lies = set(LienFamilial.objects.filter(eleve__etablissement=etab, actif=True).values_list('eleve_id', flat=True))
    sans_parent = nb - len(lies & set(eleves.values_list('id', flat=True)))
    sans_tel = eleves.filter(Q(parent_telephone__isnull=True) | Q(parent_telephone='')).exclude(id__in=lies).count()
    doublons = list(eleves.values('nom', 'prenom', 'date_naissance').annotate(n=Count('id')).filter(n__gt=1)[:8])
    sans_acte = eleves.filter(document_acte_naissance=False).count()

    alertes = []
    if sans_classe:
        alertes.append(_alerte('bad', 'fa-chalkboard', f"{sans_classe} {lib['eleves']} sans classe : ils n’apparaissent dans aucune liste d’appel ni aucun bulletin."))
    if doublons:
        alertes.append(_alerte('warn', 'fa-clone', f"{len(doublons)} doublon(s) probable(s) (même nom, prénom et date de naissance).",
                               details=[f"{d['prenom']} {d['nom']}" for d in doublons]))
    if sans_parent:
        alertes.append(_alerte('info', 'fa-user-slash', f"{sans_parent} {lib['eleves']} sans compte parent lié : la famille ne suit ni notes ni absences.",
                               _url('directeur:demandes_liaison_liste'), 'Demandes de liaison'))
    if sans_tel:
        alertes.append(_alerte('warn', 'fa-phone-slash', f"{sans_tel} {lib['eleves']} sans aucun téléphone de responsable."))
    if sans_acte and nb:
        alertes.append(_alerte('info', 'fa-file-circle-xmark', f"{sans_acte} dossier(s) sans acte de naissance."))
    occupation = (stats or {}).get('taux_occupation_global')
    kpis = [
        _kpi(lib['Eleves'], nb, 'fa-user-graduate', 'blue'),
        _kpi('Filles / garçons', f"{filles} / {nb - filles}", 'fa-venus-mars', 'violet', texte=True),
        _kpi('Occupation', f"{occupation} %" if occupation is not None else '—', 'fa-people-group', 'teal', texte=True,
             pct=_sur(lambda: round(float(occupation)))),
        _kpi('Sans parent lié', sans_parent, 'fa-user-slash', 'orange', bad=bool(sans_parent)),
    ]
    return {'kpis': kpis, 'alertes': alertes}


# --------------------------------------------------------------------------- scolarité
def controle_compta(etab, annee, stats=None):
    stats = stats or {}
    total = stats.get('total_eleves') or 0
    a_jour = stats.get('eleves_a_jour') or 0
    retard = stats.get('eleves_non_en_regle') or 0
    devise = _sur(lambda: __import__('school_admin.services.recouvrement', fromlist=['devise_etablissement'])
                  .devise_etablissement(etab), 'FCFA')
    alertes = []
    if retard:
        alertes.append(_alerte('warn', 'fa-triangle-exclamation', f"{retard} élève(s) ne sont pas en règle.",
                               _url('directeur:liste_impayes_directeur'), 'Voir les impayés'))
    # (Le module désactivé est déjà signalé par la page elle-même.)
    if total and not stats.get('montant_total'):
        alertes.append(_alerte('warn', 'fa-receipt', "Aucun frais de scolarité configuré : tous les élèves apparaissent « à jour » à 0. "
                               "Définissez les frais pour suivre les paiements.",
                               _url('directeur:parametres_comptabilite_directeur'), 'Paramétrer'))
    kpis = [
        _kpi('Élèves suivis', total, 'fa-users', 'blue'),
        _kpi('À jour', a_jour if stats.get('montant_total') else '—', 'fa-circle-check', 'green', texte=not stats.get('montant_total'),
             pct=round(100 * a_jour / total) if total and stats.get('montant_total') else None),
        _kpi('Non en règle', retard, 'fa-triangle-exclamation', 'orange', bad=bool(retard)),
        _kpi('Encaissé', f"{int(stats.get('montant_paye') or 0):,}".replace(',', ' ') + f" {devise}", 'fa-wallet', 'teal', texte=True),
    ]
    return {'kpis': kpis, 'alertes': alertes}


# --------------------------------------------------------------------------- notes
def controle_notes(etab, annee, stats=None):
    stats = stats or {}
    primaire = etab.type_etablissement == 'primary'
    if primaire:
        from school_admin.model.note_primaire_model import NotePrimaire as N
        notes = N.objects.filter(evaluation_primaire__classe__etablissement=etab)
        sans_periode = _sur(lambda: notes.filter(evaluation_primaire__periode_scolaire__isnull=True).count(), 0)
    else:
        from school_admin.model.evaluation_model import Note as N
        notes = N.objects.filter(evaluation__classe__etablissement=etab)
        sans_periode = _sur(lambda: notes.filter(evaluation__periode_scolaire__isnull=True).count(), 0)
    if annee:
        notes = notes.filter(annee_scolaire=annee)
    total = _sur(lambda: notes.count(), 0)
    brouillons = _sur(lambda: notes.filter(statut_publication='brouillon', note_publiee__isnull=True).count(), 0)
    justifs = _sur(lambda: __import__('school_admin.model.justification_note_model', fromlist=['JustificationNote'])
                   .JustificationNote.objects.filter(etablissement=etab, statut='en_attente').count(), 0)
    alertes = []
    if brouillons:
        alertes.append(_alerte('info', 'fa-eye-slash', f"{brouillons} note(s) saisie(s) mais non publiée(s) : invisibles pour les familles."))
    if sans_periode:
        alertes.append(_alerte('warn', 'fa-calendar-xmark', f"{sans_periode} note(s) rattachée(s) à aucune période : elles ne comptent pas dans les bulletins."))
    if justifs:
        alertes.append(_alerte('warn', 'fa-scale-balanced', f"{justifs} demande(s) de justification de note en attente.",
                               _url('directeur:justifications_notes'), 'Traiter'))
    kpis = [
        _kpi('Notes saisies', total, 'fa-pen-to-square', 'blue'),
        _kpi('Publiées', total - brouillons, 'fa-paper-plane', 'green', pct=round(100 * (total - brouillons) / total) if total else None),
        _kpi('Périodes', stats.get('nombre_periodes', '—'), 'fa-calendar-days', 'orange'),
        _kpi('Justifications', justifs, 'fa-scale-balanced', 'violet', bad=bool(justifs)),
    ]
    return {'kpis': kpis, 'alertes': alertes}


# --------------------------------------------------------------------------- présence
def controle_presence(etab, annee, stats=None):
    from school_admin.model.presence_model import Presence

    lib = _lib(etab)
    today = timezone.localdate()
    jour = Presence.objects.filter(classe__etablissement=etab, date=today)
    agg = jour.aggregate(t=Count('id'), a=Count('id', filter=Q(statut='absent')),
                         j=Count('id', filter=Q(statut='absent_justifie')), r=Count('id', filter=Q(statut='retard')))
    classes_appel = set(jour.values_list('classe_id', flat=True))

    def _classes_sans_appel():
        from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
        from school_admin.services.pointage import JOURS

        cours = set(CreneauEmploiDuTemps.objects.filter(
            emploi_du_temps__classe__etablissement=etab, emploi_du_temps__est_actif=True,
            emploi_du_temps__statut_publication='publie', jour=JOURS[today.weekday()],
            heure_fin__lte=timezone.localtime().time()).exclude(type_cours='pause')
            .values_list('emploi_du_temps__classe__nom', 'emploi_du_temps__classe_id'))
        return sorted({nom for nom, cid in cours if cid not in classes_appel})

    sans_appel = _sur(_classes_sans_appel, [])
    depuis = today - timedelta(days=30)
    recidivistes = _sur(lambda: list(Presence.objects.filter(classe__etablissement=etab, statut='absent', date__gte=depuis)
                                     .values('eleve__prenom', 'eleve__nom').annotate(n=Count('id')).filter(n__gte=3)
                                     .order_by('-n')[:8]), [])
    alertes = []
    if sans_appel:
        alertes.append(_alerte('warn', 'fa-clipboard-question', f"{len(sans_appel)} classe(s) ont eu cours aujourd’hui sans appel enregistré.",
                               details=sans_appel[:10]))
    if recidivistes:
        alertes.append(_alerte('bad', 'fa-user-xmark', f"{len(recidivistes)} {lib['eleves']} cumulent 3 absences non justifiées ou plus sur 30 jours.",
                               details=[f"{r['eleve__prenom']} {r['eleve__nom']} ({r['n']})" for r in recidivistes]))
    taux = round(100 * (agg['t'] - agg['a'] - agg['j']) / agg['t']) if agg['t'] else None
    kpis = [
        _kpi('Présence du jour', f"{taux} %" if taux is not None else '—', 'fa-user-check', 'green', texte=True, pct=taux),
        _kpi('Absents', agg['a'], 'fa-user-xmark', 'red', bad=bool(agg['a'])),
        _kpi('Absences justifiées', agg['j'], 'fa-file-medical', 'teal'),
        _kpi('Retards', agg['r'], 'fa-clock', 'orange'),
    ]
    return {'kpis': kpis, 'alertes': alertes}


# --------------------------------------------------------------------------- bulletins
def controle_bulletins(etab, annee, stats=None):
    stats = stats or {}
    total_cl = stats.get('total_classes') or 0
    terminees = stats.get('classes_terminees') or 0
    alertes = []
    standards = _sur(lambda: __import__('school_admin.model.standards_reussite_model', fromlist=['StandardsReussite'])
                     .StandardsReussite.objects.filter(etablissement=etab).exists(), True)
    if not standards:
        alertes.append(_alerte('warn', 'fa-sliders', "Seuils de réussite non configurés : les décisions de passage ne peuvent pas être calculées.",
                               _url('directeur:configuration_standards_reussite'), 'Configurer'))
    if total_cl and terminees < total_cl:
        alertes.append(_alerte('info', 'fa-hourglass-half', f"{total_cl - terminees} classe(s) dont les bulletins ne sont pas terminés."))
    prog = stats.get('progression_globale')
    kpis = [
        _kpi('Bulletins publiés', stats.get('bulletins_publies', 0), 'fa-paper-plane', 'green'),
        _kpi('Progression', f"{prog} %" if prog is not None else '—', 'fa-bars-progress', 'blue', texte=True,
             pct=_sur(lambda: round(float(prog)))),
        _kpi('Classes terminées', f"{terminees}/{total_cl}", 'fa-check-double', 'teal', texte=True,
             pct=round(100 * terminees / total_cl) if total_cl else None),
        _kpi(_lib(etab)['Eleves'], stats.get('total_eleves', 0), 'fa-user-graduate', 'violet'),
    ]
    return {'kpis': kpis, 'alertes': alertes}


# --------------------------------------------------------------------------- préinscriptions
def controle_preinscriptions(etab, annee, stats=None):
    from school_admin.model.preinscription_model import LienPreinscription, PreinscriptionEleve

    qs = PreinscriptionEleve.objects.filter(etablissement=etab)
    attente = qs.filter(statut='en_attente')
    nb_att = attente.count()
    anciennes = attente.filter(date_soumission__lt=timezone.now() - timedelta(days=7)).count()
    lien = LienPreinscription.objects.filter(etablissement=etab).first()
    alertes = []
    if anciennes:
        alertes.append(_alerte('warn', 'fa-hourglass-end', f"{anciennes} préinscription(s) en attente depuis plus de 7 jours : les familles attendent une réponse."))
    if not lien:
        alertes.append(_alerte('info', 'fa-link', "Aucun lien de préinscription créé : les familles ne peuvent pas se préinscrire en ligne.",
                               _url('directeur:gerer_liens_preinscription'), 'Créer le lien'))
    elif not lien.actif:
        alertes.append(_alerte('warn', 'fa-link-slash', "Le lien de préinscription est désactivé.",
                               _url('directeur:gerer_liens_preinscription'), 'Activer'))
    kpis = [
        _kpi('En attente', nb_att, 'fa-inbox', 'orange', bad=bool(anciennes)),
        _kpi('Validées', qs.filter(statut='validee').count(), 'fa-circle-check', 'green'),
        _kpi('Refusées', qs.filter(statut='rejetee').count(), 'fa-circle-xmark', 'red'),
        _kpi('Lien en ligne', ('Actif' if lien and lien.actif else 'Désactivé' if lien else 'Aucun'), 'fa-link', 'blue', texte=True,
             bad=not (lien and lien.actif)),
    ]
    return {'kpis': kpis, 'alertes': alertes}


def controle_liens(etab, annee, stats=None):
    c = controle_preinscriptions(etab, annee, stats)
    from school_admin.model.preinscription_model import LienPreinscription

    lien = LienPreinscription.objects.filter(etablissement=etab).first()
    c['kpis'] = [c['kpis'][3], _kpi('Utilisations', getattr(lien, 'nombre_utilisations', 0), 'fa-arrow-pointer', 'violet'),
                 c['kpis'][0], c['kpis'][1]]
    c['alertes'] = [a for a in c['alertes'] if 'lien' not in a['texte'].lower() or 'désactivé' in a['texte']]
    return c


# --------------------------------------------------------------------------- réinscriptions
def controle_reinscriptions(etab, annee, stats=None, eleves_data=None):
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    lib = _lib(etab)
    nb = len(eleves_data or [])
    alertes = []
    if annee is None:
        alertes.append(_alerte('bad', 'fa-calendar-xmark', "Aucune année scolaire active : impossible de réinscrire.",
                               _url('directeur:gestion_periodes_scolaires'), 'Créer l’année'))
    else:
        precedente = AnneeScolaire.objects.filter(etablissement=etab, annee_debut__lt=annee.annee_debut).exists()
        if not precedente:
            alertes.append(_alerte('info', 'fa-circle-info', f"Aucune année précédente enregistrée : il n’y a pas encore de {lib['eleves']} à réinscrire."))
    kpis = [
        _kpi('À réinscrire', nb, 'fa-rotate', 'teal'),
        _kpi('Année en cours', annee.libelle if annee else '—', 'fa-calendar-check', 'blue', texte=True),
        _kpi(f"{lib['Eleves']} inscrits", _eleves(etab).count(), 'fa-user-graduate', 'violet'),
    ]
    return {'kpis': kpis, 'alertes': alertes}


FONCTIONS = {'liste': controle_liste, 'compta': controle_compta, 'notes': controle_notes, 'presence': controle_presence,
             'bulletins': controle_bulletins, 'preinscriptions': controle_preinscriptions, 'liens': controle_liens}


def enrichir(request, context, quoi):
    etab = context.get('etablissement')
    annee = context.get('annee_scolaire_active')
    if annee is None and etab is not None:
        annee = _sur(lambda: __import__('school_admin.utils.session_utils', fromlist=['get_session_active'])
                     .get_session_active(request, etab))
        context.setdefault('annee_scolaire_active', annee)
    if etab is None:
        return context
    if quoi == 'reinscriptions':
        context['controle'] = _sur(lambda: controle_reinscriptions(etab, annee, eleves_data=context.get('eleves_data')),
                                   {'kpis': [], 'alertes': []})
    else:
        context['controle'] = _sur(lambda: FONCTIONS[quoi](etab, annee, context.get('stats_generales')),
                                   {'kpis': [], 'alertes': []})
    return context
