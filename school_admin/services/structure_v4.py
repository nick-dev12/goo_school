"""
Données des écrans de structure v4 (classes / filières) : lignes de classes prêtes à afficher,
cartes de filières et tableau de cursus (une colonne par niveau LMD).
"""
from __future__ import annotations

import re

from school_admin.model.classe_model import libelle_cle_niveau_superieur

ORDRE_LMD = [
    'L1', 'L2', 'L3', 'LP', 'M1', 'M2', 'D1', 'D2', 'D3', 'BTS1', 'BTS2', 'DUT1', 'DUT2', 'CPI1', 'CPI2',
    'ING1', 'ING2', 'ING3', 'MBA1', 'MBA2', 'DU', 'MED1', 'MED2', 'MED3', 'MED4', 'MED5', 'MED6', 'MED7', 'AUTRE',
]
RANG = {c: i for i, c in enumerate(ORDRE_LMD)}
# Libellés courts pour les pastilles (le libellé long reste en info-bulle).
COURT = {'LP': 'Licence pro', 'DU': 'DU', 'AUTRE': 'Autre'}


def _cycle(code):
    """Préfixe de cycle d'un niveau : L1 → L, ING2 → ING ; LP / DU / AUTRE n'ont pas de suite."""
    m = re.match(r'^([A-Z]+?)(\d+)$', code or '')
    return m.group(1) if m else None


def court(code):
    return COURT.get(code, code)


def niveau_de(classe):
    code = (classe.niveau_lmd or '').strip() or 'L1'
    if code == 'AUTRE':
        return (classe.niveau_libelle or 'Autre'), (classe.niveau_libelle or 'Autre')
    return code, libelle_cle_niveau_superieur(code)


ORDRE_SCOLAIRE = ['tps', 'ps', 'ms', 'gs', 'ci', 'cp', 'ce1', 'ce2', 'cm1', 'cm2']


def rang_scolaire(categorie):
    """Rang d'un niveau du primaire au lycée : CI < CP < … < CM2 < 6e < … < 3e < 2nde < 1re < Terminale."""
    import unicodedata

    t = unicodedata.normalize('NFD', (categorie or '').lower())
    t = ''.join(ch for ch in t if not unicodedata.combining(ch)).strip()
    if t.startswith('mat'):
        return 0
    for i, cle in enumerate(ORDRE_SCOLAIRE):
        if re.match(rf'^{cle}(?![a-z0-9])', t):
            return 1 + i
    m = re.match(r'^([3-6])\s*(e|eme|ieme)(?![a-z])', t)
    if m:
        return 20 + (6 - int(m.group(1)))
    if t.startswith('2'):
        return 30
    if t.startswith('1'):
        return 31
    if t.startswith('t'):
        return 32
    return 50


def lignes_classes(classes_with_teachers, est_superieur, categorie_de=None):
    """Une ligne par classe : effectif, remplissage, niveau, filière (supérieur) ou catégorie (autres)."""
    lignes = []
    for data in classes_with_teachers:
        c = data['classe']
        effectif = c.nombre_eleves
        pct = round(100 * effectif / c.capacite_max) if c.capacite_max else 0
        ligne = {
            'classe': c, 'enseignants': data.get('nombre_enseignants', 0), 'effectif': effectif,
            'capacite': c.capacite_max, 'pct': pct, 'pct_barre': min(pct, 100),
            'niveau_etat': 'is-full' if pct >= 100 else ('is-high' if pct >= 90 else ''),
        }
        if est_superieur:
            code, libelle = niveau_de(c)
            ligne.update(niveau_code=code, niveau_court=court(code), niveau_label=libelle,
                         filiere_id=c.department_id or 0,
                         filiere_nom=c.department.nom if c.department_id else 'Sans filière',
                         filiere_sigle=(c.department.sigle if c.department_id else '') or '',
                         rang=(c.department.nom if c.department_id else 'zzz', RANG.get(code, 99), c.nom))
        else:
            cat = categorie_de(c.nom) if categorie_de else c.get_niveau_display()
            ligne.update(groupe=cat, niveau_label=c.get_niveau_display(), rang=(rang_scolaire(cat), cat, c.nom))
        lignes.append(ligne)
    lignes.sort(key=lambda l: l['rang'])
    return lignes


def niveaux_presents(lignes):
    vus = {}
    for l in lignes:
        vus.setdefault(l['niveau_code'], l['niveau_label'])
    return sorted(vus.items(), key=lambda kv: RANG.get(kv[0], 99))


def filieres(departments, lignes):
    """Cartes de filières : niveaux couverts (avec nombre de classes), étudiants, enseignants."""
    cartes = []
    for dep in departments:
        les_siennes = [l for l in lignes if l['filiere_id'] == dep.id]
        par_niveau = {}
        for l in les_siennes:
            par_niveau.setdefault(l['niveau_code'], []).append(l)
        niveaux = [{'code': code, 'court': court(code), 'label': libelle_cle_niveau_superieur(code), 'nb': len(v)}
                   for code, v in sorted(par_niveau.items(), key=lambda kv: RANG.get(kv[0], 99))]
        cartes.append({
            'department': dep,
            'nb_classes': len(les_siennes),
            'nb_actives': sum(1 for l in les_siennes if l['classe'].actif),
            'nb_inactives': sum(1 for l in les_siennes if not l['classe'].actif),
            'etudiants': sum(l['effectif'] for l in les_siennes),
            'capacite': sum(l['capacite'] for l in les_siennes),
            'enseignants': sum(l['enseignants'] for l in les_siennes),
            'niveaux': niveaux,
            'texte': ' '.join(filter(None, [dep.nom, dep.sigle, dep.domaine, dep.mention])),
        })
    return cartes


def cursus(lignes):
    """Colonnes du tableau de cursus : niveaux occupés + niveaux manquants du même cycle (L1…L3, M1…M2…)."""
    presents = {l['niveau_code'] for l in lignes}
    cycles = {_cycle(c) for c in presents if _cycle(c)}
    codes = set(presents) | {c for c in ORDRE_LMD if _cycle(c) in cycles}
    if not codes:
        codes = {'L1', 'L2', 'L3'}
    colonnes = []
    for code in sorted(codes, key=lambda c: RANG.get(c, 99)):
        les_siennes = [l for l in lignes if l['niveau_code'] == code]
        colonnes.append({
            'code': code, 'court': court(code), 'label': libelle_cle_niveau_superieur(code), 'lignes': les_siennes,
            'etudiants': sum(l['effectif'] for l in les_siennes),
            'ajout_possible': code in RANG and code != 'AUTRE',
            'suffixe': chr(ord('A') + min(len(les_siennes), 25)),
        })
    return colonnes


def enrichir_modules(modules):
    """Ajoute à chaque module (UE) : EC avec enseignants, semestres, classes et points d'attention.

    Attributs posés : sx_ec (liste), sx_semestres, sx_classes, sx_credits, sx_nb_ec, sx_alertes, sx_texte.
    """
    from decimal import Decimal

    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.module_model import ModuleClasse

    modules = [m for m in modules if m is not None]
    ids = {m.id for m in modules}
    if not ids:
        return modules
    matieres = list(Matiere.objects.filter(module_id__in=ids).order_by('nom'))
    profs = {}
    for aff in AffectationProfesseur.objects.filter(matiere__in=matieres, actif=True).select_related('professeur'):
        nom = f"{aff.professeur.prenom} {aff.professeur.nom}"
        role = aff.libelle_role
        profs.setdefault(aff.matiere_id, [])
        etiquette = f"{nom} ({role})" if role else nom
        if etiquette not in profs[aff.matiere_id]:
            profs[aff.matiere_id].append(etiquette)
    par_module = {}
    for m in matieres:
        par_module.setdefault(m.module_id, []).append(m)
    liens = {}
    for mc in ModuleClasse.objects.filter(module_id__in=ids).select_related('classe', 'periode'):
        liens.setdefault(mc.module_id, []).append(mc)
    for mod in modules:
        ecs = par_module.get(mod.id, [])
        mcs = liens.get(mod.id, [])
        mod.sx_ec = [{'matiere': m, 'coefficient': m.coefficient, 'credits': m.credits,
                      'enseignants': profs.get(m.id, [])} for m in ecs]
        mod.sx_nb_ec = len(ecs)
        mod.sx_semestres = sorted({mc.periode.nom_periode for mc in mcs if mc.periode_id})
        mod.sx_classes = [mc.classe for mc in mcs]
        mod.sx_numero = next((mc.numero_ue for mc in mcs if mc.numero_ue), '')
        credits = next((mc.credits for mc in mcs if mc.credits), None)
        if credits is None:
            credits = sum((m.credits or Decimal('0') for m in ecs), Decimal('0'))
        mod.sx_credits = credits
        alertes = []
        if not ecs:
            alertes.append('Aucun EC')
        if not credits:
            alertes.append('Crédits ECTS manquants')
        if ecs and any(not profs.get(m.id) for m in ecs):
            alertes.append(f"{sum(1 for m in ecs if not profs.get(m.id))} EC sans enseignant")
        mod.sx_alertes = alertes
        mod.sx_texte = ' '.join([mod.nom, mod.code or ''] + [m.nom for m in ecs])
    return modules
