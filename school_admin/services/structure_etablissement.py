"""
Contrôles de cohérence de la structure de l'établissement (classes, matières, modules, périodes),
pour tous les types d'établissement. Chaque fonction renvoie des indicateurs et une liste
« À faire » qui pointe vers la page où corriger. Aucun contrôle ne doit casser la page.
"""
from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone


def _url(nom, *args, suffixe=''):
    try:
        return reverse(nom, args=args) + suffixe
    except NoReverseMatch:
        return None


def _sur(fn, defaut=None):
    try:
        return fn()
    except Exception:
        return defaut


def _alerte(tone, icon, texte, url=None, action=None, details=None):
    return {'tone': tone, 'icon': icon, 'texte': texte, 'url': url, 'action': action, 'details': details or []}


def _noms(qs, n=6):
    noms = [str(x) for x in qs[:n]]
    return noms


def _annee_q(annee, champ_fk='annee_scolaire_fk', champ_lib='annee_scolaire'):
    if annee is None:
        return Q()
    return Q(**{champ_fk: annee}) | Q(**{f'{champ_fk}__isnull': True, champ_lib: annee.libelle})


# --------------------------------------------------------------------------- classes
def controle_classes(etab, annee):
    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.model.classe_model import Classe
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.emploi_du_temps_model import EmploiDuTemps

    sup = etab.type_etablissement == 'superieur'
    primaire = etab.type_etablissement == 'primary'
    classes = Classe.objects.filter(etablissement=etab, actif=True)
    nb = classes.count()
    effectifs = dict(Eleve.objects.filter(etablissement=etab, actif=True, classe__isnull=False)
                     .values_list('classe_id').annotate(n=Count('id')))
    nb_eleves = sum(effectifs.values())
    capacite = sum(c.capacite_max or 0 for c in classes)
    surchargees = [c for c in classes if effectifs.get(c.id, 0) > (c.capacite_max or 0) > 0]
    vides = [c for c in classes if not effectifs.get(c.id)]

    aff = AffectationProfesseur.objects.filter(classe__etablissement=etab, actif=True)
    if annee:
        aff = aff.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True))
    avec_prof = set(aff.values_list('classe_id', flat=True))
    if primaire:
        from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

        avec_prof |= set(AffectationProfesseurPrimaire.objects.filter(classe__etablissement=etab, actif=True)
                         .values_list('classe_id', flat=True))
    sans_prof = [c for c in classes if c.id not in avec_prof]
    edt = EmploiDuTemps.objects.filter(classe__etablissement=etab, est_actif=True, statut_publication='publie')
    if annee:
        edt = edt.filter(_annee_q(annee))
    avec_edt = set(edt.values_list('classe_id', flat=True))
    sans_edt = [c for c in classes if c.id not in avec_edt]

    alertes = []
    if surchargees:
        alertes.append(_alerte('bad', 'fa-people-group', f"{len(surchargees)} classe(s) dépassent leur capacité.",
                               details=[f"{c.nom} : {effectifs.get(c.id)} / {c.capacite_max}" for c in surchargees[:6]]))
    if sans_prof:
        alertes.append(_alerte('warn', 'fa-user-slash', f"{len(sans_prof)} classe(s) sans enseignant affecté.",
                               _url('affectation:affectation_professeurs'), 'Affecter', [c.nom for c in sans_prof[:8]]))
    if sans_edt:
        alertes.append(_alerte('warn', 'fa-calendar-xmark', f"{len(sans_edt)} classe(s) sans emploi du temps publié.",
                               _url('administrateur_etablissement:liste_emplois_du_temps'), 'Publier', [c.nom for c in sans_edt[:8]]))
    if sup:
        sans_filiere = list(classes.filter(department__isnull=True))
        sans_niveau = list(classes.filter(Q(niveau_lmd__isnull=True) | Q(niveau_lmd='')))
        if sans_filiere:
            alertes.append(_alerte('warn', 'fa-sitemap', f"{len(sans_filiere)} promotion(s) sans spécialité.",
                                   details=[c.nom for c in sans_filiere[:8]]))
        if sans_niveau:
            alertes.append(_alerte('warn', 'fa-layer-group', f"{len(sans_niveau)} promotion(s) sans niveau LMD (L1, M1…) : semestres et crédits impossibles.",
                                   details=[c.nom for c in sans_niveau[:8]]))
    if vides and nb:
        alertes.append(_alerte('info', 'fa-user-graduate', f"{len(vides)} classe(s) sans aucun élève inscrit.",
                               details=[c.nom for c in vides[:8]]))

    taux = round(100 * nb_eleves / capacite) if capacite else None
    kpis = [
        {'label': 'Promotions' if sup else 'Classes', 'value': nb, 'icon': 'fa-chalkboard', 'tone': 'blue',
         'caption': f"{nb_eleves} {'étudiants' if sup else 'élèves'}"},
        {'label': 'Remplissage', 'value': f"{taux} %" if taux is not None else '—', 'icon': 'fa-people-group', 'tone': 'teal', 'texte': True,
         'pct': taux, 'caption': f"{nb_eleves} / {capacite} places"},
        {'label': 'Avec enseignant', 'value': f"{nb - len(sans_prof)}/{nb}", 'icon': 'fa-chalkboard-user', 'tone': 'violet', 'texte': True,
         'pct': round(100 * (nb - len(sans_prof)) / nb) if nb else None, 'caption': 'au moins un enseignant affecté'},
        {'label': 'Emploi du temps', 'value': f"{nb - len(sans_edt)}/{nb}", 'icon': 'fa-calendar-week', 'tone': 'green', 'texte': True,
         'pct': round(100 * (nb - len(sans_edt)) / nb) if nb else None, 'caption': 'publié'},
    ]
    return {'kpis': kpis, 'alertes': alertes, 'effectifs': effectifs, 'sans_prof': {c.id for c in sans_prof},
            'sans_edt': {c.id for c in sans_edt}}


# --------------------------------------------------------------------------- matières et modules
def controle_matieres(etab, annee):
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.module_model import Module

    sup = etab.type_etablissement == 'superieur'
    matieres = Matiere.objects.filter(etablissement=etab, actif=True)
    nb = matieres.count()
    non_rattachees = list(matieres.annotate(n=Count('classes')).filter(n=0))
    if etab.type_etablissement == 'primary':
        # Au primaire, une matière peut aussi être confiée via l'affectation du maître de classe.
        from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

        confiees = set(_sur(lambda: AffectationProfesseurPrimaire.matieres.through.objects.filter(
            affectationprofesseurprimaire__classe__etablissement=etab).values_list('matiere_id', flat=True), []))
        non_rattachees = [m for m in non_rattachees if m.id not in confiees]
    sans_coef = list(matieres.filter(Q(coefficient__isnull=True) | Q(coefficient=0))) if not sup else []
    if sans_coef:
        # Au lycée, le coefficient peut être défini par groupe de classes (série) plutôt que sur la matière.
        from school_admin.model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe

        par_groupe = set(_sur(lambda: CoefficientMatiereGroupe.objects.filter(matiere__in=sans_coef)
                              .values_list('matiere_id', flat=True), []))
        sans_coef = [m for m in sans_coef if m.id not in par_groupe]

    def _sans_prof():
        from school_admin.model.affectation_model import AffectationProfesseur
        from school_admin.model.professeur_model import Professeur

        enseignees = set(AffectationProfesseur.objects.filter(classe__etablissement=etab, actif=True)
                         .values_list('matiere_id', flat=True))
        enseignees |= set(Professeur.objects.filter(etablissement=etab, actif=True).values_list('matiere_principale_id', flat=True))
        enseignees |= set(Professeur.matieres_secondaires.through.objects.filter(professeur__etablissement=etab)
                          .values_list('matiere_id', flat=True))
        return [m for m in matieres if m.id not in enseignees]

    sans_prof = _sur(_sans_prof, []) if etab.type_etablissement != 'primary' else []

    alertes = []
    if non_rattachees:
        alertes.append(_alerte('warn', 'fa-link-slash', f"{len(non_rattachees)} matière(s) rattachée(s) à aucune classe : elles n’apparaissent ni dans les notes ni dans les bulletins.",
                               details=[m.nom for m in non_rattachees[:8]]))
    if sans_coef:
        alertes.append(_alerte('warn', 'fa-scale-unbalanced', f"{len(sans_coef)} matière(s) sans coefficient : la moyenne générale sera faussée.",
                               details=[m.nom for m in sans_coef[:8]]))
    if sans_prof:
        alertes.append(_alerte('info', 'fa-chalkboard-user', f"{len(sans_prof)} matière(s) qu’aucun enseignant n’enseigne.",
                               _url('professeur:liste_professeurs'), 'Voir les enseignants', [m.nom for m in sans_prof[:8]]))

    kpis = [
        {'label': 'Matières', 'value': nb, 'icon': 'fa-book-open', 'tone': 'violet', 'caption': 'actives'},
        {'label': 'Rattachées à une classe', 'value': f"{nb - len(non_rattachees)}/{nb}", 'icon': 'fa-link', 'tone': 'blue', 'texte': True,
         'pct': round(100 * (nb - len(non_rattachees)) / nb) if nb else None, 'caption': 'utilisables pour les notes'},
    ]
    if sup:
        modules = Module.objects.filter(etablissement=etab, actif=True)
        nb_mod = modules.count()
        modules_vides = list(modules.annotate(n=Count('matieres')).filter(n=0)) if hasattr(Module, 'matieres') else []
        sans_module = list(matieres.filter(module__isnull=True))
        sans_credits = _sur(lambda: list(modules.annotate(c=Count('module_classes', filter=Q(module_classes__credits__gt=0)))
                                         .filter(c=0)), [])
        if sans_module:
            alertes.append(_alerte('warn', 'fa-cubes', f"{len(sans_module)} matière(s) hors module (UE) : elles ne comptent pas dans les crédits ECTS.",
                                   details=[m.nom for m in sans_module[:8]]))
        if sans_credits:
            alertes.append(_alerte('warn', 'fa-coins', f"{len(sans_credits)} module(s) sans crédits ECTS définis pour leurs promotions.",
                                   details=[m.nom for m in sans_credits[:8]]))
        if modules_vides:
            alertes.append(_alerte('info', 'fa-box-open', f"{len(modules_vides)} module(s) sans aucune matière.",
                                   details=[m.nom for m in modules_vides[:8]]))
        kpis += [
            {'label': 'Modules (UE)', 'value': nb_mod, 'icon': 'fa-cubes', 'tone': 'teal', 'caption': f"{len(sans_credits)} sans crédits"},
            {'label': 'Matières hors module', 'value': len(sans_module), 'icon': 'fa-cube', 'tone': 'orange', 'caption': 'à rattacher', 'bad': bool(sans_module)},
        ]
    else:
        kpis += [
            {'label': 'Sans coefficient', 'value': len(sans_coef), 'icon': 'fa-scale-unbalanced', 'tone': 'orange', 'caption': 'à compléter', 'bad': bool(sans_coef)},
            {'label': 'Sans enseignant', 'value': len(sans_prof), 'icon': 'fa-chalkboard-user', 'tone': 'teal', 'caption': 'matière(s)'},
        ]
    return {'kpis': kpis, 'alertes': alertes}


# --------------------------------------------------------------------------- périodes
def controle_periodes(etab, annee):
    from school_admin.model.periode_model import PeriodeScolaire

    sup = etab.type_etablissement == 'superieur'
    today = timezone.localdate()
    periodes = PeriodeScolaire.objects.filter(etablissement=etab)
    if annee:
        periodes = periodes.filter(_annee_q(annee))
    periodes = list(periodes.order_by('date_debut'))
    alertes = []
    if not periodes:
        alertes.append(_alerte('bad', 'fa-calendar-xmark', "Aucune période pour cette année scolaire : notes, examens et bulletins en dépendent."))
    # Chevauchements (par niveau LMD au supérieur).
    groupes = defaultdict(list)
    for p in periodes:
        groupes[getattr(p, 'niveau_lmd', '') or ''].append(p)
    chev = []
    for niveau, ps in groupes.items():
        ps = [p for p in ps if p.date_debut and p.date_fin]
        for a, b in zip(ps, ps[1:]):
            if b.date_debut <= a.date_fin:
                chev.append(f"{a.nom_periode} / {b.nom_periode}{' (' + niveau + ')' if niveau else ''}")
    if chev:
        alertes.append(_alerte('warn', 'fa-calendar-days', f"{len(chev)} chevauchement(s) de dates entre périodes.", details=chev[:6]))
    inversees = [p for p in periodes if p.date_debut and p.date_fin and p.date_fin < p.date_debut]
    if inversees:
        alertes.append(_alerte('bad', 'fa-arrow-right-arrow-left', f"{len(inversees)} période(s) avec une date de fin avant la date de début.",
                               details=[p.nom_periode for p in inversees]))
    if annee and periodes:
        hors = [p for p in periodes if (annee.date_debut and p.date_debut and p.date_debut < annee.date_debut)
                or (annee.date_fin and p.date_fin and p.date_fin > annee.date_fin)]
        if hors:
            alertes.append(_alerte('warn', 'fa-calendar-minus', f"{len(hors)} période(s) débordent de l’année scolaire {annee.libelle}.",
                                   details=[p.nom_periode for p in hors]))
    en_cours = [p for p in periodes if p.date_debut and p.date_fin and p.date_debut <= today <= p.date_fin]
    if periodes and not en_cours and annee and annee.date_debut and annee.date_fin and annee.date_debut <= today <= annee.date_fin:
        alertes.append(_alerte('info', 'fa-calendar-day', "Aucune période ne couvre la date d’aujourd’hui."))
    if sup:
        from school_admin.model.classe_model import Classe

        niveaux = set(Classe.objects.filter(etablissement=etab, actif=True).exclude(niveau_lmd__isnull=True)
                      .exclude(niveau_lmd='').values_list('niveau_lmd', flat=True))
        sans = sorted(n for n in niveaux if not groupes.get(n))
        if sans:
            alertes.append(_alerte('warn', 'fa-layer-group', f"Niveaux sans semestres : {', '.join(sans)}."))
    actives = [p for p in periodes if getattr(p, 'est_active', True)]
    kpis = [
        {'label': 'Semestres' if sup else 'Périodes', 'value': len(periodes), 'icon': 'fa-calendar-days', 'tone': 'orange',
         'caption': f"{len(actives)} active(s)"},
        {'label': 'En cours', 'value': ', '.join(p.nom_periode for p in en_cours[:2]) or '—', 'icon': 'fa-calendar-check', 'tone': 'green',
         'texte': True, 'caption': (f"jusqu’au {en_cours[0].date_fin:%d/%m/%Y}" if en_cours else 'aucune aujourd’hui')},
        {'label': 'Année scolaire', 'value': annee.libelle if annee else '—', 'icon': 'fa-calendar', 'tone': 'blue', 'texte': True,
         'caption': (f"{annee.date_debut:%d/%m/%Y} → {annee.date_fin:%d/%m/%Y}" if annee and annee.date_debut and annee.date_fin else '')},
    ]
    return {'kpis': kpis, 'alertes': alertes}


# --------------------------------------------------------------------------- fiches détaillées
def controle_classe(classe, annee):
    """Fiche d'une classe : effectif, matières, enseignants, emploi du temps."""
    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps

    etab = classe.etablissement
    sup = etab.type_etablissement == 'superieur'
    primaire = etab.type_etablissement == 'primary'
    effectif = Eleve.objects.filter(classe=classe, actif=True).count()
    filles = Eleve.objects.filter(classe=classe, actif=True, sexe='F').count()
    matieres = list(classe.matieres.filter(actif=True))
    aff = AffectationProfesseur.objects.filter(classe=classe, actif=True)
    if annee:
        aff = aff.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True))
    profs = set(aff.values_list('professeur_id', flat=True))
    matieres_couvertes = set(aff.values_list('matiere_id', flat=True))
    if primaire:
        from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

        for a in AffectationProfesseurPrimaire.objects.filter(classe=classe, actif=True).prefetch_related('matieres'):
            profs.add(a.professeur_id)
            matieres_couvertes |= {m.id for m in a.matieres.all()}
    creneaux = CreneauEmploiDuTemps.objects.filter(emploi_du_temps__classe=classe, emploi_du_temps__est_actif=True,
                                                   emploi_du_temps__statut_publication='publie').exclude(type_cours='pause')
    minutes = sum(((c.heure_fin.hour * 60 + c.heure_fin.minute) - (c.heure_debut.hour * 60 + c.heure_debut.minute))
                  for c in creneaux if c.heure_debut and c.heure_fin)
    # Matières réellement enseignées (affectations, emploi du temps) mais absentes du programme de la classe.
    from school_admin.model.matiere_model import Matiere

    ids_edt = set(creneaux.exclude(matiere__isnull=True).values_list('matiere_id', flat=True))
    hors_programme = list(Matiere.objects.filter(id__in=(matieres_couvertes | ids_edt) - {m.id for m in matieres}))
    sans_prof = [m for m in matieres if m.id not in matieres_couvertes]
    alertes = []
    if hors_programme:
        alertes.append(_alerte('warn', 'fa-link-slash', f"{len(hors_programme)} matière(s) enseignée(s) dans cette classe mais non rattachée(s) à son programme.",
                               _url('matiere:liste_matieres'), 'Rattacher', [m.nom for m in hors_programme]))
    if classe.capacite_max and effectif > classe.capacite_max:
        alertes.append(_alerte('bad', 'fa-people-group', f"Effectif ({effectif}) supérieur à la capacité ({classe.capacite_max})."))
    if not matieres and not hors_programme:
        alertes.append(_alerte('warn', 'fa-book-open', "Aucune matière rattachée à cette classe.",
                               _url('matiere:liste_matieres'), 'Rattacher'))
    elif sans_prof and not primaire:
        alertes.append(_alerte('warn', 'fa-user-slash', f"{len(sans_prof)} matière(s) sans enseignant dans cette classe.",
                               _url('affectation:affectation_professeurs'), 'Affecter', [m.nom for m in sans_prof]))
    if not profs:
        alertes.append(_alerte('warn', 'fa-chalkboard-user', "Aucun enseignant affecté.", _url('affectation:affectation_professeurs'), 'Affecter'))
    if not minutes:
        alertes.append(_alerte('warn', 'fa-calendar-xmark', "Pas d’emploi du temps publié pour cette classe.",
                               _url('administrateur_etablissement:liste_emplois_du_temps'), 'Créer'))
    if sup:
        if not classe.department_id:
            alertes.append(_alerte('warn', 'fa-sitemap', "Promotion sans spécialité."))
        if not classe.niveau_lmd:
            alertes.append(_alerte('warn', 'fa-layer-group', "Niveau LMD non défini : semestres et crédits impossibles."))
        sans_cred = _sur(lambda: list(classe.module_classe_credits.filter(Q(credits__isnull=True) | Q(credits=0))
                                      .select_related('module')), [])
        if sans_cred:
            alertes.append(_alerte('warn', 'fa-coins', f"{len(sans_cred)} module(s) sans crédits ECTS pour cette promotion.",
                                   details=[mc.module.nom for mc in sans_cred]))
    pct = round(100 * effectif / classe.capacite_max) if classe.capacite_max else None
    kpis = [
        {'label': 'Étudiants' if sup else 'Élèves', 'value': f"{effectif}/{classe.capacite_max}", 'icon': 'fa-user-graduate', 'tone': 'blue',
         'texte': True, 'pct': pct, 'caption': f"{filles} fille(s) · {effectif - filles} garçon(s)"},
        {'label': 'Matières', 'value': len(matieres) + len(hors_programme), 'icon': 'fa-book-open', 'tone': 'violet',
         'caption': (f"{len(matieres)} au programme · {len(hors_programme)} hors programme" if hors_programme
                     else (f"{len(matieres) - len(sans_prof)} avec enseignant" if not primaire else 'au programme'))},
        {'label': 'Enseignants', 'value': len(profs), 'icon': 'fa-chalkboard-user', 'tone': 'teal', 'caption': 'affectés'},
        {'label': 'Heures / semaine', 'value': f"{round(minutes / 60, 1):g} h", 'icon': 'fa-calendar-week', 'tone': 'green',
         'texte': True, 'caption': f"{creneaux.count()} créneau(x) publiés"},
    ]
    return {'kpis': kpis, 'alertes': alertes}


def controle_module(module):
    sup_classes = list(module.classes.all())
    matieres = list(module.matieres.filter(actif=True)) if hasattr(module, 'matieres') else []
    alertes = []
    if not matieres:
        alertes.append(_alerte('warn', 'fa-box-open', "Aucune matière dans ce module : ajoutez-en depuis cette page."))
    if not sup_classes:
        alertes.append(_alerte('warn', 'fa-chalkboard', "Module rattaché à aucune promotion."))
    sans_cred = _sur(lambda: [mc.classe.nom for mc in module.module_classes.select_related('classe')
                              if not mc.credits], [])
    if sans_cred:
        alertes.append(_alerte('warn', 'fa-coins', f"Crédits ECTS non définis pour {len(sans_cred)} promotion(s).", details=sans_cred))
    sans_coef = [m.nom for m in matieres if not m.coefficient and not m.credits]
    if sans_coef:
        alertes.append(_alerte('info', 'fa-scale-unbalanced', f"{len(sans_coef)} matière(s) sans coefficient ni crédit.", details=sans_coef))
    kpis = [
        {'label': 'Matières', 'value': len(matieres), 'icon': 'fa-book-open', 'tone': 'violet', 'caption': 'dans le module'},
        {'label': 'Crédits ECTS', 'value': getattr(module, 'total_credits', None) or 0, 'icon': 'fa-coins', 'tone': 'orange', 'caption': 'total'},
        {'label': 'Promotions', 'value': len(sup_classes), 'icon': 'fa-chalkboard', 'tone': 'blue', 'caption': 'concernées'},
    ]
    return {'kpis': kpis, 'alertes': alertes}


def controle_matiere(matiere):
    from school_admin.model.affectation_model import AffectationProfesseur

    classes = list(matiere.classes.filter(actif=True))
    profs = set(AffectationProfesseur.objects.filter(matiere=matiere, actif=True).values_list('professeur_id', flat=True))
    sup = matiere.etablissement.type_etablissement == 'superieur'
    alertes = []
    if not classes:
        alertes.append(_alerte('warn', 'fa-link-slash', "Matière rattachée à aucune classe : elle n’apparaît pas dans les notes."))
    if not profs and matiere.etablissement.type_etablissement != 'primary':
        alertes.append(_alerte('info', 'fa-chalkboard-user', "Aucun enseignant affecté à cette matière.",
                               _url('affectation:affectation_professeurs'), 'Affecter'))
    if not sup and not matiere.coefficient:
        from school_admin.model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe

        if not _sur(lambda: CoefficientMatiereGroupe.objects.filter(matiere=matiere).exists(), False):
            alertes.append(_alerte('warn', 'fa-scale-unbalanced', "Coefficient non défini."))
    if sup and not matiere.module_id:
        alertes.append(_alerte('warn', 'fa-cubes', "Matière hors module : elle ne compte pas dans les crédits ECTS."))
    kpis = [
        {'label': 'Classes', 'value': len(classes), 'icon': 'fa-chalkboard', 'tone': 'blue', 'caption': 'concernées'},
        {'label': 'Enseignants', 'value': len(profs), 'icon': 'fa-chalkboard-user', 'tone': 'teal', 'caption': 'affectés'},
        {'label': 'Crédits' if sup else 'Coefficient', 'value': (matiere.credits if sup else matiere.coefficient) or '—',
         'icon': 'fa-scale-balanced', 'tone': 'orange', 'caption': 'ECTS' if sup else 'dans la moyenne'},
    ]
    return {'kpis': kpis, 'alertes': alertes}


def enrichir(request, context, quoi, objet=None):
    """Ajoute au contexte d'une page de gestion le bloc « controle » (indicateurs + à vérifier)."""
    etab = context.get('etablissement') or getattr(objet, 'etablissement', None)
    annee = context.get('annee_scolaire_active')
    if annee is None and etab is not None:
        annee = _sur(lambda: __import__('school_admin.utils.session_utils', fromlist=['get_session_active'])
                     .get_session_active(request, etab))
        context.setdefault('annee_scolaire_active', annee)
    fonctions = {'classes': lambda: controle_classes(etab, annee), 'matieres': lambda: controle_matieres(etab, annee),
                 'periodes': lambda: controle_periodes(etab, annee), 'classe': lambda: controle_classe(objet, annee),
                 'module': lambda: controle_module(objet), 'matiere': lambda: controle_matiere(objet)}
    context['controle'] = _sur(fonctions[quoi], {'kpis': [], 'alertes': []})
    if quoi == 'classe' and objet is not None:
        if objet.niveau == 'superieur':
            morceaux = [getattr(objet.department, 'nom', ''), objet.niveau_lmd or '', objet.niveau_libelle or '']
        else:
            morceaux = [objet.get_niveau_display(), getattr(objet.academic_level, 'nom', '')]
        context['v3_sous_titre_classe'] = ' · '.join(m for m in morceaux if m) + f" · {objet.code_classe}"
    if quoi == 'matiere' and objet is not None:
        morceaux = [objet.code, getattr(objet, 'type_display', ''), getattr(objet, 'niveau_display', '')]
        if objet.module_id:
            morceaux.append(f"Module {objet.module.nom}")
        context['v3_sous_titre_matiere'] = ' · '.join(str(m) for m in morceaux if m)
    return context
