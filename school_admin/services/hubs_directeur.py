"""
Pages « hub » de l'espace direction (établissement, pédagogie, élèves, administration).

Chaque hub est décrit en données : sections, liens, chiffre clé de chaque lien et points
d'attention. Les liens dépendent des autorisations du personnel et des modules activés.
Chaque chiffre est calculé séparément : si un module manque, le lien reste affiché sans chiffre.
"""
from __future__ import annotations

from django.db.models import Count, Q, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from school_admin.model.etablissement_model import Etablissement
from school_admin.utils.decorators_permissions import check_permission


def _peut(user, *cles):
    if isinstance(user, Etablissement):
        return True
    return any(check_permission(user, c) for c in cles)


def _url(nom, *args, suffixe=''):
    try:
        return reverse(nom, args=args) + suffixe
    except NoReverseMatch:
        return None


def _sur(fn, defaut=None):
    """Calcule un chiffre sans jamais casser la page."""
    try:
        return fn()
    except Exception:
        return defaut


def _lien(titre, desc, url, icon, tone, stat=None, stat_label='', alerte=None, nouveau=False):
    return {'titre': titre, 'desc': desc, 'url': url, 'icon': icon, 'tone': tone, 'stat': stat,
            'stat_label': stat_label, 'alerte': alerte, 'nouveau': nouveau}


def _nettoyer(sections):
    out = []
    for s in sections:
        liens = [l for l in s['liens'] if l and l['url']]
        if liens:
            out.append(dict(s, liens=liens))
    return out


def _type_libelles(etab):
    sup = etab.type_etablissement == 'superieur'
    return {'eleves': 'étudiants' if sup else 'élèves', 'Eleves': 'Étudiants' if sup else 'Élèves',
            'classes': 'promotions' if sup else 'classes', 'periodes': 'semestres' if sup else 'trimestres'}


# --------------------------------------------------------------------------- établissement
def hub_etablissement(user, etab, annee):
    from school_admin.model.classe_model import Classe
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.periode_model import PeriodeScolaire
    from school_admin.model.salle_model import Salle

    lib = _type_libelles(etab)
    today = timezone.localdate()
    classes = Classe.objects.filter(etablissement=etab, actif=True)
    nb_classes = classes.count()
    capacite = _sur(lambda: classes.aggregate(t=Sum('capacite_max'))['t'] or 0, 0)
    nb_eleves = _sur(lambda: Eleve.objects.filter(etablissement=etab, actif=True).count(), 0)
    periodes = PeriodeScolaire.objects.filter(etablissement=etab)
    if annee:
        periodes = periodes.filter(Q(annee_scolaire_fk=annee) | Q(annee_scolaire_fk__isnull=True, annee_scolaire=annee.libelle))
    nb_periodes = periodes.count()
    en_cours = _sur(lambda: periodes.filter(date_debut__lte=today, date_fin__gte=today).first())
    nb_matieres = Matiere.objects.filter(etablissement=etab).count()
    nb_salles = _sur(lambda: Salle.objects.filter(etablissement=etab, actif=True).count(), 0)

    profil_manquants = [l for c, l in (('logo', 'logo'), ('telephone', 'téléphone'), ('adresse', 'adresse'))
                        if not getattr(etab, c, None)]

    alertes = []
    if not nb_periodes:
        alertes.append({'tone': 'bad', 'icon': 'fa-calendar-xmark', 'texte': f"Aucune période ({lib['periodes']}) pour cette année : notes et bulletins en dépendent.",
                        'url': _url('directeur:gestion_periodes_scolaires'), 'action': 'Créer les périodes'})
    elif not en_cours:
        alertes.append({'tone': 'warn', 'icon': 'fa-calendar-day', 'texte': "Aucune période en cours aujourd'hui.",
                        'url': _url('directeur:gestion_periodes_scolaires'), 'action': 'Vérifier les dates'})
    if capacite and nb_eleves > capacite:
        alertes.append({'tone': 'warn', 'icon': 'fa-people-group', 'texte': f"{nb_eleves} {lib['eleves']} pour {capacite} places déclarées dans les {lib['classes']}.",
                        'url': _url('administrateur_etablissement:liste_classes'), 'action': 'Ajuster les capacités'})
    if profil_manquants:
        alertes.append({'tone': 'info', 'icon': 'fa-id-card', 'texte': "Profil incomplet : " + ', '.join(profil_manquants) + " (utilisés sur les documents officiels).",
                        'url': _url('directeur:profil_etablissement'), 'action': 'Compléter'})

    structure = _peut(user, 'classes_liste')
    finances = etab.module_comptabilite and _peut(user, 'comptabilite_voir')
    cg = etab.module_comptabilite and _peut(user, 'comptabilite_bilans')
    sections = [
        {'titre': 'Structure de l’établissement', 'desc': 'À configurer dans cet ordre en début d’année.', 'liens': [
            structure and _lien('Périodes scolaires', f"Découpage de l’année en {lib['periodes']}", _url('directeur:gestion_periodes_scolaires'),
                                'fa-calendar-days', 'orange', nb_periodes, 'période(s)',
                                None if nb_periodes else 'À créer'),
            structure and _lien(lib['classes'].capitalize(), f"Niveaux, effectifs et capacités", _url('administrateur_etablissement:liste_classes'),
                                'fa-chalkboard', 'blue', nb_classes, f"{nb_eleves} {lib['eleves']}"),
            structure and _lien('Matières', 'Programme, coefficients et rattachement aux classes', _url('matiere:liste_matieres'),
                                'fa-book-open', 'violet', nb_matieres, 'matière(s)', None if nb_matieres else 'À créer'),
            structure and _lien('Salles', 'Salles de cours et capacités', _url('salle:liste_salles'),
                                'fa-door-open', 'teal', nb_salles, 'salle(s)'),
            structure and _lien('Profil de l’établissement', 'Identité, logo, coordonnées et modules', _url('directeur:profil_etablissement'),
                                'fa-id-card', 'green', None, '', 'À compléter' if profil_manquants else None),
        ]},
        {'titre': 'Finances', 'desc': 'Suivi financier de l’établissement.', 'liens': [
            finances and _lien('Finances', 'Situation, encaissements, dépenses et trésorerie', _url('directeur:finances_situation'),
                               'fa-wallet', 'green'),
            cg and _lien('Comptabilité générale', 'SYSCOHADA : journaux, grand livre, états financiers', _url('directeur:cg_hub_directeur'),
                         'fa-scale-balanced', 'violet'),
        ]},
    ]
    kpis = [
        {'label': lib['Eleves'], 'value': nb_eleves, 'icon': 'fa-user-graduate', 'tone': 'blue',
         'caption': f"{nb_classes} {lib['classes']}", 'pct': round(100 * nb_eleves / capacite) if capacite else None,
         'pct_label': f"{round(100 * nb_eleves / capacite) if capacite else 0} % de la capacité"},
        {'label': 'Période en cours', 'value': (getattr(en_cours, 'nom_periode', '') or '—'), 'icon': 'fa-calendar-check', 'tone': 'orange',
         'caption': f"jusqu’au {en_cours.date_fin:%d/%m}" if en_cours else f"{nb_periodes} période(s)", 'texte': True},
        {'label': 'Matières', 'value': nb_matieres, 'icon': 'fa-book-open', 'tone': 'violet', 'caption': 'au programme'},
        {'label': 'Salles', 'value': nb_salles, 'icon': 'fa-door-open', 'tone': 'teal', 'caption': 'actives'},
    ]
    return {'titre': 'Établissement', 'icone': 'fa-building', 'tone': 'blue',
            'sous_titre': 'Structure de l’année scolaire, profil et finances.', 'kpis': kpis,
            'alertes': alertes, 'sections': _nettoyer(sections)}


# --------------------------------------------------------------------------- pédagogie
def hub_pedagogique(user, etab, annee):
    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.model.classe_model import Classe
    from school_admin.model.emploi_du_temps_model import EmploiDuTemps
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur

    today = timezone.localdate()
    profs = Professeur.objects.filter(etablissement=etab, actif=True)
    nb_profs = profs.count()
    nb_perso = _sur(lambda: PersonnelAdministratif.objects.filter(etablissement=etab, actif=True).count(), 0)
    classes = Classe.objects.filter(etablissement=etab, actif=True)
    nb_classes = classes.count()
    edt = EmploiDuTemps.objects.filter(classe__etablissement=etab, est_actif=True)
    if annee:
        edt = edt.filter(Q(annee_scolaire_fk=annee) | Q(annee_scolaire_fk__isnull=True, annee_scolaire=annee.libelle))
    nb_edt_publies = _sur(lambda: edt.filter(statut_publication='publie').values('classe').distinct().count(), 0)

    def _classes_sans_prof():
        aff = AffectationProfesseur.objects.filter(classe__etablissement=etab, actif=True)
        if annee:
            aff = aff.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True))
        avec = set(aff.values_list('classe_id', flat=True))
        if etab.type_etablissement == 'primary':
            from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

            avec |= set(AffectationProfesseurPrimaire.objects.filter(classe__etablissement=etab, actif=True)
                        .values_list('classe_id', flat=True))
        return classes.exclude(id__in=avec).count()

    sans_prof = _sur(_classes_sans_prof, 0)
    a_verifier = _sur(lambda: __import__('school_admin.model.pointage_model', fromlist=['SeanceCours']).SeanceCours.objects
                      .filter(etablissement=etab, statut__in=['a_verifier', 'contestee']).count(), 0)
    cahier = _sur(lambda: _taux_cahier(etab, annee))
    sans_compte = _sur(lambda: profs.filter(last_login__isnull=True).count(), 0)

    alertes = []
    if sans_prof:
        alertes.append({'tone': 'warn', 'icon': 'fa-user-slash', 'texte': f"{sans_prof} classe(s) sans enseignant affecté.",
                        'url': _url('affectation:affectation_professeurs'), 'action': 'Affecter'})
    if nb_classes and nb_edt_publies < nb_classes:
        alertes.append({'tone': 'warn', 'icon': 'fa-calendar-xmark', 'texte': f"{nb_classes - nb_edt_publies} classe(s) sans emploi du temps publié : pas de pointage ni de cahier de texte pour elles.",
                        'url': _url('administrateur_etablissement:liste_emplois_du_temps'), 'action': 'Publier'})
    if a_verifier:
        alertes.append({'tone': 'info', 'icon': 'fa-qrcode', 'texte': f"{a_verifier} séance(s) de cours à vérifier avant la paie.",
                        'url': _url('directeur:liste_volume_horaire'), 'action': 'Contrôler'})

    perso = _peut(user, 'professeurs_liste')
    sections = [
        {'titre': 'Équipe', 'desc': 'Enseignants, personnel et répartition des classes.', 'liens': [
            perso and _lien('Enseignants', 'Fiches, matières, contrats et dossiers', _url('professeur:liste_professeurs'),
                            'fa-chalkboard-user', 'blue', nb_profs, 'actif(s)',
                            f"{sans_compte} jamais connecté(s)" if sans_compte else None),
            _peut(user, 'personnel_liste') and _lien('Personnel administratif', 'Fonctions et autorisations', _url('personnel:liste_personnel'),
                            'fa-user-tie', 'violet', nb_perso, 'membre(s)'),
            perso and _lien('Affectation des enseignants', 'Qui enseigne quoi, dans quelle classe', _url('affectation:affectation_professeurs'),
                            'fa-people-arrows', 'teal', nb_classes - sans_prof if nb_classes else 0, f"/ {nb_classes} classes couvertes",
                            f"{sans_prof} sans enseignant" if sans_prof else None),
        ]},
        {'titre': 'Organisation des cours', 'desc': 'Emplois du temps, présence des enseignants et suivi des séances.', 'liens': [
            _peut(user, 'classes_liste') and _lien('Emplois du temps', 'Créneaux par classe, publication', _url('administrateur_etablissement:liste_emplois_du_temps'),
                                                                      'fa-calendar-week', 'green', nb_edt_publies, f"/ {nb_classes} publiés"),
            _peut(user, 'pointage_controle', 'professeurs_detail') and _lien('Pointage des enseignants', 'QR code en classe, validation et anomalies',
                                                                              _url('directeur:liste_volume_horaire'), 'fa-qrcode', 'orange',
                                                                              a_verifier, 'à vérifier', None),
            _peut(user, 'professeurs_detail', 'pointage_controle') and _lien('Cahiers de texte', 'Leçons validées par les enseignants',
                                                                              _url('directeur:cahiers_texte'), 'fa-book-open', 'teal',
                                                                              f"{cahier} %" if cahier is not None else None, 'renseignés (14 j)'),
        ]},
    ]
    kpis = [
        {'label': 'Enseignants', 'value': nb_profs, 'icon': 'fa-chalkboard-user', 'tone': 'blue', 'caption': f"{nb_perso} personnel administratif"},
        {'label': 'Classes couvertes', 'value': f"{nb_classes - sans_prof}/{nb_classes}", 'icon': 'fa-people-arrows', 'tone': 'teal',
         'caption': 'avec un enseignant affecté', 'pct': round(100 * (nb_classes - sans_prof) / nb_classes) if nb_classes else None, 'texte': True},
        {'label': 'Emplois du temps', 'value': f"{nb_edt_publies}/{nb_classes}", 'icon': 'fa-calendar-week', 'tone': 'green',
         'caption': 'classes publiées', 'pct': round(100 * nb_edt_publies / nb_classes) if nb_classes else None, 'texte': True},
        {'label': 'Séances à vérifier', 'value': a_verifier, 'icon': 'fa-qrcode', 'tone': 'orange', 'caption': 'pointage', 'bad': bool(a_verifier)},
    ]
    return {'titre': 'Pédagogie', 'icone': 'fa-graduation-cap', 'tone': 'violet',
            'sous_titre': 'Équipe enseignante, répartition des classes et organisation des cours.', 'kpis': kpis,
            'alertes': alertes, 'sections': _nettoyer(sections)}


def _taux_cahier(etab, annee):
    from school_admin.services.cahier_texte import stats_professeur
    from school_admin.model.professeur_model import Professeur

    cours = faits = 0
    for p in Professeur.objects.filter(etablissement=etab, actif=True)[:200]:
        s = stats_professeur(p, annee, jours=14)
        cours += s['cours']
        faits += s['renseignes']
    return round(100 * faits / cours) if cours else None


# --------------------------------------------------------------------------- élèves
def hub_eleves(user, etab, annee):
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.presence_model import Presence

    lib = _type_libelles(etab)
    today = timezone.localdate()
    eleves = Eleve.objects.filter(etablissement=etab, actif=True)
    nb = eleves.count()
    filles = _sur(lambda: eleves.filter(sexe='F').count(), 0)
    nouveaux = _sur(lambda: eleves.filter(date_inscription__gte=today.replace(day=1)).count(), 0)
    pres = _sur(lambda: Presence.objects.filter(classe__etablissement=etab, date=today)
                .aggregate(t=Count('id'), a=Count('id', filter=Q(statut__in=['absent', 'absent_justifie'])),
                           r=Count('id', filter=Q(statut='retard'))), {'t': 0, 'a': 0, 'r': 0})
    preins = _sur(lambda: __import__('school_admin.model.preinscription_model', fromlist=['PreinscriptionEleve'])
                  .PreinscriptionEleve.objects.filter(etablissement=etab, statut='en_attente').count(), 0)

    alertes = []
    if preins:
        alertes.append({'tone': 'info', 'icon': 'fa-inbox', 'texte': f"{preins} préinscription(s) en attente de traitement.",
                        'url': _url('directeur:liste_preinscriptions'), 'action': 'Traiter'})
    if pres['t'] and pres['a']:
        alertes.append({'tone': 'warn', 'icon': 'fa-user-xmark', 'texte': f"{pres['a']} absence(s) aujourd'hui sur {pres['t']} appels.",
                        'url': _url('directeur:suivi_presence'), 'action': 'Voir'})

    sections = [
        {'titre': 'Inscriptions', 'desc': f"Arrivée des {lib['eleves']} et renouvellement d’une année sur l’autre.", 'liens': [
            _peut(user, 'eleves_inscrire') and _lien(f"Inscrire un {'étudiant' if lib['eleves'] == 'étudiants' else 'élève'}", 'Nouvelle inscription avec compte parent',
                                                      _url('secretaire:liste_eleves', suffixe='?inscrire=1'), 'fa-user-plus', 'green',
                                                      nouveaux, 'ce mois-ci'),
            _peut(user, 'eleves_liste') and _lien(f"Liste des {lib['eleves']}", 'Recherche, fiches et dossiers', _url('secretaire:liste_eleves'),
                                                   'fa-users', 'blue', nb, 'inscrit(s)'),
            _peut(user, 'eleves_reinscrire') and _lien('Réinscriptions', 'Passage à l’année suivante', _url('directeur:liste_reinscription'),
                                                        'fa-rotate', 'teal'),
            isinstance(user, Etablissement) and _lien('Liens de préinscription', 'Formulaire en ligne pour les familles', _url('directeur:gerer_liens_preinscription'),
                                                       'fa-link', 'violet'),
            isinstance(user, Etablissement) and _lien('Préinscriptions reçues', 'Valider ou refuser les demandes', _url('directeur:liste_preinscriptions'),
                                                       'fa-inbox', 'orange', preins, 'en attente', 'À traiter' if preins else None),
        ]},
        {'titre': 'Suivi scolaire', 'desc': 'Résultats, assiduité et bulletins.', 'liens': [
            _peut(user, 'notes_liste') and _lien('Notes et résultats', 'Moyennes par classe et par matière', _url('directeur:notes_et_resultats'),
                                                  'fa-chart-line', 'blue'),
            _peut(user, 'presences_liste') and _lien('Suivi de présence', 'Appels du jour, absences et retards', _url('directeur:suivi_presence'),
                                                      'fa-user-check', 'green', pres['a'] if pres['t'] else None, 'absent(s) aujourd’hui'),
            _peut(user, 'bulletins_voir') and _lien('Bulletins', 'Calcul, publication et impression', _url('directeur:bulletins_notes'),
                                                     'fa-file-lines', 'violet'),
        ]},
    ]
    kpis = [
        {'label': lib['Eleves'], 'value': nb, 'icon': 'fa-user-graduate', 'tone': 'blue', 'caption': f"{filles} fille(s) · {nb - filles} garçon(s)"},
        {'label': 'Nouveaux ce mois', 'value': nouveaux, 'icon': 'fa-user-plus', 'tone': 'green', 'caption': 'inscriptions'},
        {'label': 'Présence du jour', 'value': f"{round(100 * (pres['t'] - pres['a']) / pres['t'])} %" if pres['t'] else '—',
         'icon': 'fa-user-check', 'tone': 'teal', 'texte': True,
         'caption': f"{pres['a']} absent(s) · {pres['r']} retard(s)" if pres['t'] else 'Aucun appel aujourd’hui'},
        {'label': 'Préinscriptions', 'value': preins, 'icon': 'fa-inbox', 'tone': 'orange', 'caption': 'en attente', 'bad': bool(preins)},
    ]
    return {'titre': lib['Eleves'], 'icone': 'fa-user-graduate', 'tone': 'green',
            'sous_titre': f"Inscriptions, suivi scolaire et bulletins des {lib['eleves']}.", 'kpis': kpis,
            'alertes': alertes, 'sections': _nettoyer(sections)}


# --------------------------------------------------------------------------- administration
def hub_administratif(user, etab, annee):
    from school_admin.model.convocation_model import Convocation

    today = timezone.localdate()
    demandes = _sur(lambda: __import__('school_admin.model.demande_liaison_model', fromlist=['DemandeLiaisonParent'])
                    .DemandeLiaisonParent.objects.filter(parent_demandeur__etablissement=etab, statut='en_attente').count(), 0)
    convoc = _sur(lambda: Convocation.objects.filter(etablissement=etab, date_convocation__gte=today).count(), 0)
    peut = _peut(user, 'administrative_voir')
    alertes = []
    if demandes:
        alertes.append({'tone': 'info', 'icon': 'fa-link', 'texte': f"{demandes} demande(s) de liaison parent-enfant en attente : ces parents n’ont pas encore accès au suivi.",
                        'url': _url('directeur:demandes_liaison_liste'), 'action': 'Traiter'})
    sections = [
        {'titre': 'Documents scolaires', 'desc': 'Génération et impression des documents officiels.', 'liens': [
            peut and _lien('Cartes d’identité scolaires', 'Cartes avec QR code, par classe', _url('secretaire:cartes_identite_eleves'), 'fa-id-card', 'blue'),
            peut and _lien('Certificats de scolarité', 'Attestation d’inscription pour l’année', _url('directeur:certificat_scolarite_liste'), 'fa-file-signature', 'green'),
            peut and _lien('Fiches d’inscription', 'Inscription et réinscription', _url('directeur:fiche_inscription_liste'), 'fa-file-lines', 'violet'),
            peut and _lien('Attestations de réussite', 'Passage en classe supérieure', _url('directeur:attestation_reussite_liste'), 'fa-award', 'orange'),
            peut and _lien('Attestations de conduite', 'Certificat de bonne conduite', _url('directeur:attestation_conduite_liste'), 'fa-medal', 'teal'),
            peut and _lien('Radiation / transfert', 'Certificat de départ de l’établissement', _url('directeur:certificat_radiation_liste'), 'fa-right-from-bracket', 'red'),
        ]},
        {'titre': 'Relations avec les familles', 'desc': 'Convocations et accès des parents.', 'liens': [
            peut and _lien('Convocations', 'Parents et élèves convoqués', _url('directeur:convocation_liste'), 'fa-envelope-open-text', 'orange',
                           convoc, 'à venir'),
            peut and _lien('Demandes de liaison parent-enfant', 'Valider les comptes parents', _url('directeur:demandes_liaison_liste'), 'fa-link', 'blue',
                           demandes, 'en attente', 'À traiter' if demandes else None),
        ]},
    ]
    kpis = [
        {'label': 'Demandes de liaison', 'value': demandes, 'icon': 'fa-link', 'tone': 'blue', 'caption': 'en attente', 'bad': bool(demandes)},
        {'label': 'Convocations', 'value': convoc, 'icon': 'fa-envelope-open-text', 'tone': 'orange', 'caption': 'à venir'},
    ]
    return {'titre': 'Administration', 'icone': 'fa-folder-open', 'tone': 'orange',
            'sous_titre': 'Documents officiels, convocations et accès des familles.', 'kpis': kpis,
            'alertes': alertes, 'sections': _nettoyer(sections)}
