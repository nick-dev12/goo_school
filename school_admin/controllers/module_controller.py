# school_admin/controllers/module_controller.py

from decimal import Decimal
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db.models import Prefetch
from django.urls import reverse
from collections import OrderedDict, defaultdict
from urllib.parse import urlencode
import logging
import random
import re

from django.utils.translation import gettext as _

from ..model.module_model import Module, ModuleClasse, ModuleDepartment
from ..model.matiere_model import Matiere
from ..model.etablissement_model import Etablissement
from ..model.academic_structure_model import Department
from ..model.classe_model import Classe, libelle_cle_niveau_superieur
from ..model.periode_model import PeriodeScolaire
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..utils.session_utils import get_session_active

logger = logging.getLogger(__name__)


def _redirect_liste_matieres_tab(tab='matieres', **query):
    """Redirige vers la page matières avec l'onglet principal demandé."""
    url = reverse('matiere:liste_matieres')
    params = {}
    if tab == 'modules':
        params['tab'] = 'modules'
    for key, value in query.items():
        if value is None or value == '':
            continue
        if isinstance(value, (list, tuple)):
            cleaned = [v for v in value if v is not None and v != '']
            if cleaned:
                params[key] = cleaned
        else:
            params[key] = value
    if params:
        return redirect(f'{url}?{urlencode(params, doseq=True)}')
    return redirect(url)

NIVEAUX_SUPERIEUR = [
    ('L1', 'L1'), ('L2', 'L2'), ('L3', 'L3'),
    ('BTS', 'BTS'), ('DUT', 'DUT'), ('BUT', 'BUT'), ('BT', 'BT'), ('LP', 'Licence pro'),
    ('M1', 'M1'), ('M2', 'M2'), ('D1', 'D1'), ('D2', 'D2'), ('D3', 'D3'),
    ('CERT', 'Certificat'), ('DIPL', 'Diplôme'), ('AUTRE', 'Autre'),
]

_SANS_CLASSE_MODULE_KEY = '__sans_classe__'


def _niveau_groupe_key_classe(classe):
    """Clé de regroupement LMD (identique à la logique des groupes classes / matières)."""
    if classe.niveau_lmd == 'AUTRE':
        return (classe.niveau_libelle or classe.niveau_lmd) or 'Sans niveau'
    return classe.niveau_lmd or 'Sans niveau'


def _groupes_classes_par_niveau(etablissement, department_id):
    """
    Retourne les classes de la spécialité groupées par niveau LMD.
    Format: { 'L1': [classe1, classe2], 'L2': [classe3], ... }
    Seuls les niveaux ayant des classes sont retournés.
    """
    if not department_id:
        return OrderedDict()
    classes = Classe.objects.filter(
        etablissement=etablissement,
        department_id=department_id,
        niveau='superieur',
        actif=True
    ).select_related('department', 'academic_level').order_by('niveau_lmd', 'nom')
    groupes = OrderedDict()
    for c in classes:
        niveau = _niveau_groupe_key_classe(c)
        if niveau not in groupes:
            groupes[niveau] = []
        groupes[niveau].append(c)
    return groupes


def _groupes_classes_par_niveau_multi(etablissement, department_ids):
    """Fusionne les classes de plusieurs spécialités, groupées par niveau LMD."""
    merged = OrderedDict()
    seen_by_niveau = defaultdict(set)
    for dep_id in department_ids:
        for niveau, classes_list in _groupes_classes_par_niveau(etablissement, dep_id).items():
            if niveau not in merged:
                merged[niveau] = []
            for classe in classes_list:
                if classe.id not in seen_by_niveau[niveau]:
                    seen_by_niveau[niveau].add(classe.id)
                    merged[niveau].append(classe)
    return merged


def _niveau_field_key(department_id, niveau_key):
    """Clé unique formulaire modale : spécialité + niveau LMD."""
    return f'dep_{department_id}__{niveau_key}'


def _parse_niveau_field_key(field_key):
    """Retourne (department_id ou None, niveau_lmd)."""
    raw = (field_key or '').strip()
    if raw.startswith('dep_') and '__' in raw:
        dep_part, niveau_key = raw.split('__', 1)
        dep_id_str = dep_part.replace('dep_', '', 1)
        if dep_id_str.isdigit():
            return int(dep_id_str), niveau_key
    return None, raw


def _build_modal_niveaux_par_filiere(etablissement, department_ids):
    """
    Niveaux LMD par spécialité pour la modale de création.
    [{department, niveaux: {L1: [classes], ...}}, ...]
    """
    if not department_ids:
        return []
    dep_ints = [int(x) for x in department_ids if str(x).isdigit()]
    departments = Department.objects.filter(
        id__in=dep_ints,
        etablissement=etablissement,
    ).order_by('ordre', 'nom')
    blocks = []
    for dep in departments:
        niveaux = _groupes_classes_par_niveau(etablissement, dep.id)
        if niveaux:
            blocks.append({
                'department': dep,
                'niveaux': niveaux,
                'niveaux_items': [
                    {
                        'niveau_key': niveau_key,
                        'field_key': _niveau_field_key(dep.id, niveau_key),
                        'classes': classes_list,
                    }
                    for niveau_key, classes_list in niveaux.items()
                ],
            })
    return blocks


def _build_all_modal_niveaux_par_filiere(etablissement):
    """Toutes les spécialités et niveaux LMD (filtrage côté client)."""
    dep_ids = Department.objects.filter(
        etablissement=etablissement,
    ).order_by('ordre', 'nom').values_list('id', flat=True)
    return _build_modal_niveaux_par_filiere(
        etablissement,
        [str(d) for d in dep_ids],
    )


def _build_modal_periodes_par_niveau(request, etablissement, niveaux_par_filiere):
    periodes_map = _periodes_par_niveau_superieur(request, etablissement)
    periodes_par_niveau = {}
    for block in niveaux_par_filiere:
        for niveau_key in block['niveaux'].keys():
            if niveau_key not in periodes_par_niveau:
                periodes_par_niveau[niveau_key] = _periodes_disponibles_pour_niveau(
                    periodes_map, niveau_key
                )
    return periodes_par_niveau, periodes_map


def _parse_niveau_form_from_post(request):
    niveaux_selectionnes = request.POST.getlist('niveaux')
    credits_per_niveau = {}
    numeros_per_niveau = {}
    periodes_per_niveau = {}
    for field_key in niveaux_selectionnes:
        raw = request.POST.get(f'credits_{field_key}', '0').strip()
        try:
            credits_per_niveau[field_key] = Decimal(raw) if raw else Decimal('0')
            if credits_per_niveau[field_key] < 0:
                credits_per_niveau[field_key] = Decimal('0')
        except Exception:
            credits_per_niveau[field_key] = Decimal('0')
        numeros_per_niveau[field_key] = (request.POST.get(f'numero_{field_key}', '') or '').strip()[:80]
        periodes_per_niveau[field_key] = (request.POST.get(f'periode_{field_key}', '') or '').strip()
    return niveaux_selectionnes, credits_per_niveau, numeros_per_niveau, periodes_per_niveau


def _validate_niveau_form(niveaux_selectionnes, credits_per_niveau, periodes_per_niveau, periodes_map, field_errors):
    is_valid = True
    if not niveaux_selectionnes:
        field_errors['niveaux'] = "Sélectionnez au moins un niveau."
        is_valid = False
    for field_key in niveaux_selectionnes:
        if credits_per_niveau.get(field_key, Decimal('0')) < 0:
            field_errors['credits_per_niveau'] = "Les crédits ne peuvent pas être négatifs."
            is_valid = False
            break
        _dep_id, niveau_lmd = _parse_niveau_field_key(field_key)
        periode_id_raw = periodes_per_niveau.get(field_key, '')
        periodes_autorisees = _periodes_disponibles_pour_niveau(periodes_map, niveau_lmd)
        periodes_autorisees_ids = {str(p.id) for p in periodes_autorisees}
        if periode_id_raw and periode_id_raw not in periodes_autorisees_ids:
            field_errors['periodes_per_niveau'] = (
                "La période choisie ne correspond pas au niveau sélectionné."
            )
            is_valid = False
            break
    return is_valid


def _persist_module_niveaux(
    module,
    etablissement,
    departments_objs,
    niveaux_selectionnes,
    credits_per_niveau,
    numeros_per_niveau,
    periodes_per_niveau,
):
    departments_by_id = {d.id: d for d in departments_objs}
    for field_key in niveaux_selectionnes:
        dep_id, niveau_lmd = _parse_niveau_field_key(field_key)
        credits_val = credits_per_niveau.get(field_key, Decimal('0'))
        if credits_val < 0:
            credits_val = Decimal('0')
        numero_val = numeros_per_niveau.get(field_key, '')[:80]
        periode_obj = None
        periode_id_raw = periodes_per_niveau.get(field_key, '')
        if periode_id_raw.isdigit():
            periode_obj = PeriodeScolaire.objects.filter(
                id=int(periode_id_raw),
                etablissement=etablissement,
            ).first()
        if dep_id and dep_id in departments_by_id:
            target_departments = [departments_by_id[dep_id]]
        else:
            target_departments = list(departments_objs)
        for department_obj in target_departments:
            classes_niveau = _classes_pour_department_et_niveau(
                etablissement, department_obj, niveau_lmd
            )
            for classe in classes_niveau:
                ModuleClasse.objects.update_or_create(
                    module=module,
                    classe=classe,
                    defaults={
                        'credits': credits_val,
                        'numero_ue': numero_val,
                        'periode': periode_obj,
                    },
                )


def _module_niveau_form_data_from_module(module):
    """Données formulaire (niveaux LMD) depuis un module existant."""
    groups = defaultdict(list)
    for mc in module.module_classes.select_related('classe__department'):
        classe = mc.classe
        if not classe.department_id:
            continue
        field_key = _niveau_field_key(
            classe.department_id,
            _niveau_groupe_key_classe(classe),
        )
        groups[field_key].append(mc)
    niveaux = []
    credits_per_niveau = {}
    numeros_per_niveau = {}
    periodes_per_niveau = {}
    for field_key in sorted(groups.keys()):
        mc0 = groups[field_key][0]
        niveaux.append(field_key)
        credits_per_niveau[field_key] = mc0.credits
        numeros_per_niveau[field_key] = (mc0.numero_ue or '').strip()
        periodes_per_niveau[field_key] = str(mc0.periode_id) if mc0.periode_id else ''
    return {
        'niveaux': niveaux,
        'credits_per_niveau': credits_per_niveau,
        'numeros_per_niveau': numeros_per_niveau,
        'periodes_per_niveau': periodes_per_niveau,
    }


def _classes_pour_department_et_niveau(etablissement, department, niveau):
    """Classes actives d'une spécialité pour un niveau LMD donné."""
    if niveau == 'Sans niveau':
        return Classe.objects.filter(
            etablissement=etablissement,
            department=department,
            niveau_lmd__isnull=True,
            actif=True,
        )
    if niveau in [n[0] for n in NIVEAUX_SUPERIEUR]:
        return Classe.objects.filter(
            etablissement=etablissement,
            department=department,
            niveau_lmd=niveau,
            actif=True,
        )
    return Classe.objects.filter(
        etablissement=etablissement,
        department=department,
        niveau_lmd='AUTRE',
        niveau_libelle=niveau,
        actif=True,
    )


def _sync_module_departments(module, department_ids):
    """Met à jour les liaisons module ↔ spécialités et la FK legacy."""
    dep_ids = sorted({int(x) for x in department_ids if str(x).isdigit()})
    ModuleDepartment.objects.filter(module=module).exclude(department_id__in=dep_ids).delete()
    for dep_id in dep_ids:
        ModuleDepartment.objects.get_or_create(module=module, department_id=dep_id)
    if len(dep_ids) == 1:
        module.department_id = dep_ids[0]
    else:
        module.department_id = None
    module.save(update_fields=['department', 'date_modification'])


def _matiere_department_for_module(module):
    """Filière à enregistrer sur une matière (null si module mutualisé)."""
    deps = module.get_linked_departments()
    return deps[0] if len(deps) == 1 else None


def _module_appartient_a_filiere(module, department_id):
    if not department_id:
        return module.department_id is None and not module.module_departments.exists()
    if module.module_departments.filter(department_id=department_id).exists():
        return True
    return module.department_id == department_id


def _parse_departments_ids_from_request(request):
    """IDs spécialités depuis POST/GET (multi-sélection ou legacy department)."""
    raw_list = request.POST.getlist('departments_ids') if request.method == 'POST' else request.GET.getlist('departments')
    if not raw_list and request.method == 'POST':
        raw_list = request.POST.getlist('departments')
    if not raw_list:
        single = (request.POST.get('department') if request.method == 'POST' else request.GET.get('department')) or ''
        single = single.strip()
        if single.isdigit():
            raw_list = [single]
    return sorted({x for x in raw_list if str(x).isdigit()}, key=int)


def _sort_niveau_keys_pour_liste_modules(keys):
    """Ordre d'affichage des sous-onglets niveaux (L1, L2, … puis libellés perso, puis hors liste)."""
    order_map = {n[0]: i for i, n in enumerate(NIVEAUX_SUPERIEUR)}
    sans_niveau = 'Sans niveau'

    def sort_key(k):
        if k == _SANS_CLASSE_MODULE_KEY:
            return (40000, '')
        if k in order_map:
            return (order_map[k], '')
        if k == sans_niveau:
            return (35000, '')
        return (20000, str(k))

    return sorted(set(keys), key=sort_key)


def _periodes_par_niveau_superieur(request, etablissement):
    """
    Retourne les périodes actives indexées par niveau LMD.
    Les périodes globales (niveau vide) sont conservées comme fallback.
    """
    annee_active = get_session_active(request, etablissement)
    periodes_qs = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True,
    ).order_by('date_debut', 'id')
    if annee_active:
        periodes_qs = periodes_qs.filter(annee_scolaire_fk=annee_active)

    periodes_map = defaultdict(list)
    for periode in periodes_qs:
        niveau_key = (periode.niveau_lmd or '').strip()
        periodes_map[niveau_key].append(periode)
    return periodes_map


def _periodes_disponibles_pour_niveau(periodes_map, niveau_key):
    """
    Périodes d'un niveau LMD donné; fallback sur périodes globales (niveau vide).
    """
    nk = (niveau_key or '').strip()
    return list(periodes_map.get(nk, [])) or list(periodes_map.get('', []))


def _modules_par_niveau_panels(modules_ordered):
    """
    Regroupe les modules par niveau LMD (d'après les classes liées).
    Un même module peut apparaître sous plusieurs niveaux s'il couvre plusieurs classes.
    """
    niveau_to_modules = defaultdict(list)
    seen_ids = defaultdict(set)

    for mod in modules_ordered:
        classes = list(mod.classes.all())
        key_set = set()
        if not classes:
            key_set.add(_SANS_CLASSE_MODULE_KEY)
        else:
            for c in classes:
                key_set.add(_niveau_groupe_key_classe(c))
        for k in key_set:
            if mod.id not in seen_ids[k]:
                seen_ids[k].add(mod.id)
                niveau_to_modules[k].append(mod)

    panels = []
    for k in _sort_niveau_keys_pour_liste_modules(niveau_to_modules.keys()):
        if k == _SANS_CLASSE_MODULE_KEY:
            label = _('Sans classe associée')
        else:
            label = libelle_cle_niveau_superieur(k)
        panels.append({
            'niveau_key': k,
            'niveau_label': label,
            'modules': niveau_to_modules[k],
        })
    return panels


def _get_etablissement(request):
    if isinstance(request.user, Etablissement):
        return request.user
    if isinstance(request.user, PersonnelAdministratif):
        return request.user.etablissement
    return None


def _classe_ids_du_module(module):
    return set(module.classes.values_list('id', flat=True))


def _generate_unique_matiere_code(nom):
    """Code unique pour Matiere (max 10 caractères, champ model)."""
    raw = re.sub(r'[^a-zA-Z0-9]', '', (nom or '')[:12])
    base = (raw[:3].upper() if len(raw) >= 3 else (raw.upper() + 'MAT')[:3])
    if not base:
        base = 'MAT'
    code = base[:10]
    counter = 1
    while Matiere.objects.filter(code=code).exists():
        suffix = str(counter)
        code = (base[: (10 - len(suffix))] + suffix)[:10]
        counter += 1
        if counter > 500:
            code = f'M{random.randint(10000, 99999)}'[:10]
            while Matiere.objects.filter(code=code).exists():
                code = f'M{random.randint(10000, 99999)}'[:10]
            break
    return code


def _matieres_visibles_pour_classe(matiere_qs_or_list, classe):
    """Matières du module : sans restriction M2M (toutes les classes) ou classe incluse."""
    if hasattr(matiere_qs_or_list, 'prefetch_related'):
        iterable = matiere_qs_or_list.prefetch_related('classes')
    else:
        iterable = matiere_qs_or_list
    out = []
    for m in iterable:
        if m.classes.count() == 0:
            out.append(m)
        elif m.classes.filter(pk=classe.pk).exists():
            out.append(m)
    return out


def _module_classes_by_niveau(module):
    """Classes du module regroupées par niveau LMD (ordre L1, L2, …)."""
    buckets = defaultdict(list)
    for mc in module.module_classes.select_related(
        'classe__academic_level', 'classe__department', 'periode'
    ).order_by('classe__niveau_lmd', 'classe__nom'):
        niveau_key = _niveau_groupe_key_classe(mc.classe)
        buckets[niveau_key].append({'mc': mc, 'classe': mc.classe})
    ordered = OrderedDict()
    for niveau_key in _sort_niveau_keys_pour_liste_modules(buckets.keys()):
        ordered[niveau_key] = buckets[niveau_key]
    return ordered


def _module_classes_by_filiere_and_niveau(module):
    """Classes du module indexées par filière puis niveau LMD."""
    by_dep = defaultdict(lambda: defaultdict(list))
    for mc in module.module_classes.select_related(
        'classe__academic_level', 'classe__department', 'periode'
    ).order_by('classe__department__ordre', 'classe__department__nom', 'classe__niveau_lmd', 'classe__nom'):
        dep_id = mc.classe.department_id
        if not dep_id:
            continue
        niveau_key = _niveau_groupe_key_classe(mc.classe)
        by_dep[dep_id][niveau_key].append({'mc': mc, 'classe': mc.classe})
    return by_dep


def _classes_for_department_niveau_in_module(module, department_id, niveau_key):
    """Classes d'une filière et d'un niveau LMD rattachées au module."""
    return [
        item['classe']
        for item in _module_classes_by_filiere_and_niveau(module)
        .get(int(department_id), {})
        .get(niveau_key, [])
    ]


def _classe_ids_for_department_niveau_in_module(module, department_id, niveau_key):
    return [c.id for c in _classes_for_department_niveau_in_module(module, department_id, niveau_key)]


def _classe_ids_for_niveau_in_module(module, niveau_key):
    return [
        item['classe'].id
        for item in _module_classes_by_niveau(module).get(niveau_key, [])
    ]


def _classes_for_niveau_in_module(module, niveau_key):
    return [
        item['classe']
        for item in _module_classes_by_niveau(module).get(niveau_key, [])
    ]


def _matieres_pour_niveau(matieres, niveau_classe_ids, niveau_key=None, department_id=None):
    """Matières visibles pour un niveau (optionnellement scoping filière)."""
    niveau_set = set(niveau_classe_ids)
    dep_id = int(department_id) if department_id else None
    out = []
    for matiere in matieres:
        matiere_niveau = (getattr(matiere, 'niveau_lmd_key', None) or '').strip()
        if matiere_niveau:
            if niveau_key and matiere_niveau == niveau_key:
                if dep_id is None:
                    out.append(matiere)
                elif matiere.department_id is None:
                    m_class_ids = set(matiere.classes.values_list('id', flat=True))
                    if not m_class_ids or niveau_set & m_class_ids:
                        out.append(matiere)
                elif matiere.department_id == dep_id:
                    out.append(matiere)
            continue
        m_class_ids = set(matiere.classes.values_list('id', flat=True))
        if not m_class_ids or niveau_set & m_class_ids:
            if dep_id is None or matiere.department_id in (None, dep_id):
                out.append(matiere)
    return out


def _build_niveau_card_for_module(module, niveau_key, items, matieres, department_id=None):
    """Construit une carte niveau (optionnellement pour une filière)."""
    classes = [item['classe'] for item in items]
    mcs = [item['mc'] for item in items]
    classe_ids = [c.id for c in classes]
    numeros_ue = sorted({(mc.numero_ue or '').strip() for mc in mcs if (mc.numero_ue or '').strip()})
    periodes = []
    seen_periodes = set()
    for mc in mcs:
        if mc.periode_id and mc.periode_id not in seen_periodes:
            seen_periodes.add(mc.periode_id)
            periodes.append(mc.periode)
    credits_total = sum((mc.credits or Decimal('0')) for mc in mcs)
    return {
        'niveau_key': niveau_key,
        'niveau_label': libelle_cle_niveau_superieur(niveau_key),
        'department_id': department_id,
        'classes': classes,
        'classe_ids': classe_ids,
        'nb_classes': len(classes),
        'numeros_ue': numeros_ue,
        'periodes': periodes,
        'credits_total': credits_total,
        'matieres_pour_niveau': _matieres_pour_niveau(
            matieres, classe_ids, niveau_key, department_id=department_id
        ),
    }


def _build_filiere_panels_for_module_detail(module, matieres):
    """Panneaux filière → sous-onglets niveau pour la page détail module."""
    by_dep_niveau = _module_classes_by_filiere_and_niveau(module)
    linked_departments = module.get_linked_departments()
    panels = []
    for dep in linked_departments:
        niveau_buckets = by_dep_niveau.get(dep.id, {})
        if not niveau_buckets:
            continue
        niveaux_cards = []
        for niveau_key in _sort_niveau_keys_pour_liste_modules(niveau_buckets.keys()):
            niveaux_cards.append(
                _build_niveau_card_for_module(
                    module,
                    niveau_key,
                    niveau_buckets[niveau_key],
                    matieres,
                    department_id=dep.id,
                )
            )
        panels.append({
            'department': dep,
            'niveaux_cards': niveaux_cards,
        })
    return panels


def _serialize_matiere_niveaux_par_filiere(blocks):
    """Structure JSON pour la modale ajout matière (sans objets ORM)."""
    return [
        {
            'department': {
                'id': block['department'].id,
                'nom': block['department'].nom,
                'sigle': (block['department'].sigle or '').strip(),
            },
            'niveaux_items': [
                {
                    'niveau_key': item['niveau_key'],
                    'niveau_label': item['niveau_label'],
                    'field_key': item['field_key'],
                }
                for item in block['niveaux_items']
            ],
        }
        for block in blocks
    ]


def _build_module_niveaux_par_filiere_for_matiere(module):
    """Niveaux LMD du module par filière (modale ajout matière)."""
    by_dep_niveau = _module_classes_by_filiere_and_niveau(module)
    blocks = []
    for dep in module.get_linked_departments():
        buckets = by_dep_niveau.get(dep.id, {})
        if not buckets:
            continue
        niveaux_items = []
        for niveau_key in _sort_niveau_keys_pour_liste_modules(buckets.keys()):
            classes = [item['classe'] for item in buckets[niveau_key]]
            niveaux_items.append({
                'niveau_key': niveau_key,
                'niveau_label': libelle_cle_niveau_superieur(niveau_key),
                'field_key': _niveau_field_key(dep.id, niveau_key),
                'classes': classes,
            })
        if niveaux_items:
            blocks.append({
                'department': dep,
                'niveaux_items': niveaux_items,
            })
    return blocks


def _parse_coef_from_post(request, field_name, default='1.0'):
    raw = (request.POST.get(field_name) or default).strip()
    try:
        coef = Decimal(raw).quantize(Decimal('0.1'))
        if coef < 0 or coef > 10:
            return None, "Le coefficient doit être entre 0 et 10."
    except Exception:
        return None, "Coefficient invalide."
    return coef, None


def _creer_matiere_pour_filiere_niveau(
    module,
    etablissement,
    nom_m,
    department,
    niveau_key,
    coef_dec,
):
    """Crée une matière pour une filière + niveau LMD dans le module."""
    classes_niveau = _classes_for_department_niveau_in_module(
        module, department.id, niveau_key
    )
    if not classes_niveau:
        return None, f"Aucune classe pour {department.nom} — {libelle_cle_niveau_superieur(niveau_key)}."
    niveau_label = libelle_cle_niveau_superieur(niveau_key)
    if Matiere.objects.filter(
        nom__iexact=nom_m,
        etablissement=etablissement,
        department=department,
        module=module,
        niveau_lmd_key=niveau_key,
    ).exists():
        return None, (
            f"« {nom_m} » existe déjà pour {department.nom} — {niveau_label}."
        )
    matiere = Matiere(
        nom=nom_m[:100],
        code=_generate_unique_matiere_code(nom_m),
        etablissement=etablissement,
        department=department,
        module=module,
        niveau_lmd_key=niveau_key,
        niveau='superieur',
        coefficient=coef_dec,
        credits=coef_dec,
        actif=True,
    )
    matiere.save()
    matiere.classes.add(*classes_niveau)
    return matiere, None


def _niveaux_labels_for_matiere(matiere, module_by_niveau):
    """Libellés des niveaux couverts par une matière dans ce module."""
    matiere_niveau = (getattr(matiere, 'niveau_lmd_key', None) or '').strip()
    if matiere_niveau:
        return [libelle_cle_niveau_superieur(matiere_niveau)]
    m_class_ids = set(matiere.classes.values_list('id', flat=True))
    if not m_class_ids:
        return []
    labels = []
    for niveau_key, items in module_by_niveau.items():
        niveau_ids = {item['classe'].id for item in items}
        if niveau_ids & m_class_ids:
            labels.append(libelle_cle_niveau_superieur(niveau_key))
    return labels


def _attach_matiere_to_niveau(matiere, module, niveau_key):
    """Lie une matière à toutes les classes du module pour ce niveau."""
    classes = _classes_for_niveau_in_module(module, niveau_key)
    if classes:
        matiere.classes.add(*classes)


def _detach_matiere_from_niveau(matiere, module, niveau_key):
    """Retire une matière des classes du module pour ce niveau."""
    classe_ids = _classe_ids_for_niveau_in_module(module, niveau_key)
    if classe_ids:
        matiere.classes.remove(*Classe.objects.filter(id__in=classe_ids))


def _build_niveaux_cards_for_module(module, matieres):
    """Cartes par niveau pour la page détail module (vue agrégée legacy)."""
    module_by_niveau = _module_classes_by_niveau(module)
    cards = []
    for niveau_key, items in module_by_niveau.items():
        cards.append(_build_niveau_card_for_module(module, niveau_key, items, matieres))
    return cards


def _matieres_ajoutables_pour_classe(module, classe, matieres_sans_module_list):
    """
    Matières qu'on peut associer à cette classe : hors module (même département)
    ou déjà dans le module mais pas encore liées à cette classe (scopage explicite).
    """
    ajoutables = []
    seen = set()
    for m in matieres_sans_module_list:
        if m.id not in seen:
            seen.add(m.id)
            ajoutables.append(m)
    for m in module.matieres.filter(actif=True).prefetch_related('classes'):
        if m.classes.count() == 0:
            continue
        if not m.classes.filter(pk=classe.pk).exists() and m.id not in seen:
            seen.add(m.id)
            ajoutables.append(m)
    return ajoutables


def _build_liste_modules_context(request, etablissement):
    """Contexte commun liste + modale d'ajout (departments pour le select)."""
    classes_prefetch = Classe.objects.select_related('department', 'academic_level')
    modules = Module.objects.filter(etablissement=etablissement).select_related(
        'department'
    ).prefetch_related(
        'matieres',
        'module_departments__department',
        Prefetch('classes', queryset=classes_prefetch),
    ).order_by('department', 'ordre', 'nom')

    stats = {
        'total': modules.count(),
        'actives': modules.filter(actif=True).count(),
    }

    modules_par_filiere = []
    departments = Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
    for dep in departments:
        mods_dep = [m for m in modules if _module_appartient_a_filiere(m, dep.id)]
        if mods_dep:
            modules_par_filiere.append({
                'department': dep,
                'modules': mods_dep,
                'niveaux': _modules_par_niveau_panels(mods_dep),
            })
    mods_sans_filiere = [
        m for m in modules
        if not m.get_linked_department_ids() and m.department_id is None
    ]
    if mods_sans_filiere:
        modules_par_filiere.insert(0, {
            'department': None,
            'modules': mods_sans_filiere,
            'niveaux': _modules_par_niveau_panels(mods_sans_filiere),
        })

    all_niveaux = _build_all_modal_niveaux_par_filiere(etablissement)
    return {
        'modules': modules,
        'modules_par_filiere': modules_par_filiere,
        'etablissement': etablissement,
        'stats': stats,
        'departments': departments,
        'show_modal_ajouter': False,
        'modal_form_data': {
            'nom': '',
            'department': None,
            'departments_ids': [],
            'niveaux': [],
            'credits_per_niveau': {},
            'numeros_per_niveau': {},
            'periodes_per_niveau': {},
        },
        'modal_field_errors': {},
        'modal_groupes_classes': OrderedDict(),
        'modal_niveaux_par_filiere': all_niveaux,
        'modal_periodes_par_niveau': _build_modal_periodes_par_niveau(
            request, etablissement, all_niveaux
        )[0],
    }


def _modal_ajouter_from_query(request, etablissement):
    """Ouverture modale via GET (?ouvrir_modal=1&departments=1&departments=2&nom=)."""
    departments_ids = _parse_departments_ids_from_request(request)
    nom = (request.GET.get('nom') or '').strip()
    niveaux_par_filiere = _build_all_modal_niveaux_par_filiere(etablissement)
    periodes_par_niveau, _periodes_map = _build_modal_periodes_par_niveau(
        request, etablissement, niveaux_par_filiere
    )
    return {
        'show_modal_ajouter': True,
        'modal_form_data': {
            'nom': nom,
            'department': departments_ids[0] if len(departments_ids) == 1 else None,
            'departments_ids': departments_ids,
            'niveaux': [],
            'credits_per_niveau': {},
            'numeros_per_niveau': {},
            'periodes_per_niveau': {},
        },
        'modal_field_errors': {},
        'modal_groupes_classes': OrderedDict(),
        'modal_niveaux_par_filiere': niveaux_par_filiere,
        'modal_periodes_par_niveau': periodes_par_niveau,
    }


@login_required
def liste_modules(request):
    """Liste des modules (établissements supérieurs uniquement)."""
    etablissement = _get_etablissement(request)
    if not etablissement:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    if etablissement.type_etablissement != 'superieur':
        messages.info(request, "Les modules sont réservés aux établissements supérieurs.")
        return redirect('matiere:liste_matieres')

    if request.GET.get('ouvrir_modal'):
        return _redirect_liste_matieres_tab('modules', ouvrir_modal='1', **{
            k: v for k, v in request.GET.items()
            if k in ('department', 'nom') and v
        })
    return _redirect_liste_matieres_tab('modules')


@login_required
def ajouter_module(request):
    """
    Création d'un module (POST uniquement depuis la modale sur la liste).
    GET redirige vers la liste avec ouverture de la modale.
    """
    etablissement = _get_etablissement(request)
    if not etablissement:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    if etablissement.type_etablissement != 'superieur':
        return redirect('matiere:liste_matieres')

    if request.method == 'GET':
        nom = (request.GET.get('nom') or '').strip()
        return _redirect_liste_matieres_tab(
            'modules',
            ouvrir_modal='1',
            nom=nom or None,
            departments=_parse_departments_ids_from_request(request) or None,
        )

    # POST
    niveaux_par_filiere = _build_all_modal_niveaux_par_filiere(etablissement)
    periodes_par_niveau_ctx, periodes_map = _build_modal_periodes_par_niveau(
        request, etablissement, niveaux_par_filiere
    )
    niveaux_selectionnes, credits_per_niveau, numeros_per_niveau, periodes_per_niveau = (
        _parse_niveau_form_from_post(request)
    )

    departments_ids = _parse_departments_ids_from_request(request)
    form_data = {
        'nom': (request.POST.get('nom', '') or '').strip(),
        'department': departments_ids[0] if len(departments_ids) == 1 else None,
        'departments_ids': departments_ids,
        'niveaux': niveaux_selectionnes,
        'credits_per_niveau': credits_per_niveau,
        'numeros_per_niveau': numeros_per_niveau,
        'periodes_per_niveau': periodes_per_niveau,
    }

    field_errors = {}
    is_valid = True
    if not form_data['nom']:
        field_errors['nom'] = "Le nom du module est obligatoire."
        is_valid = False

    if not departments_ids:
        field_errors['department'] = "Sélectionnez au moins une spécialité."
        is_valid = False

    departments_objs = Department.objects.none()
    if departments_ids and is_valid:
        departments_objs = Department.objects.filter(
            id__in=[int(x) for x in departments_ids],
            etablissement=etablissement,
        ).order_by('ordre', 'nom')
        if departments_objs.count() != len(departments_ids):
            field_errors['department'] = "Une ou plusieurs spécialités sont invalides."
            is_valid = False

    if is_valid:
        is_valid = _validate_niveau_form(
            form_data['niveaux'],
            credits_per_niveau,
            periodes_per_niveau,
            periodes_map,
            field_errors,
        )

    if is_valid:
        try:
            dernier_num = Module.objects.filter(etablissement=etablissement).count()
            code = f"MOD-{dernier_num + 1:04d}"
            while Module.objects.filter(etablissement=etablissement, code=code).exists():
                dernier_num += 1
                code = f"MOD-{dernier_num:04d}"
            primary_department = departments_objs.first() if departments_objs.count() == 1 else None
            module = Module.objects.create(
                nom=form_data['nom'],
                code=code,
                etablissement=etablissement,
                department=primary_department,
                niveau_lmd=None,
            )
            _sync_module_departments(module, [str(d.id) for d in departments_objs])
            if form_data['niveaux'] and departments_objs.exists():
                _persist_module_niveaux(
                    module,
                    etablissement,
                    departments_objs,
                    form_data['niveaux'],
                    credits_per_niveau,
                    numeros_per_niveau,
                    periodes_per_niveau,
                )
            if departments_objs.count() > 1:
                messages.success(
                    request,
                    f"Le module mutualisé « {form_data['nom']} » a été créé pour "
                    f"{departments_objs.count()} spécialités.",
                )
            else:
                messages.success(request, f"Le module « {form_data['nom']} » a été créé.")
            return _redirect_liste_matieres_tab('modules')
        except Exception as e:
            logger.error(f"Erreur création module: {e}")
            field_errors['non_field'] = "Erreur lors de la création."

    from .matiere_controller import MatiereController, enrich_liste_matieres_superieur_context

    ctx = MatiereController.build_liste_matieres_context(request, etablissement)
    ctx = enrich_liste_matieres_superieur_context(request, etablissement, ctx, matieres_main_tab='modules')
    ctx.update({
        'show_modal_ajouter': True,
        'modal_form_data': form_data,
        'modal_field_errors': field_errors,
        'modal_groupes_classes': OrderedDict(),
        'modal_niveaux_par_filiere': niveaux_par_filiere,
        'modal_periodes_par_niveau': periodes_par_niveau_ctx,
    })
    return render(request, 'school_admin/directeur/pedagogique/matieres/liste_matieres.html', ctx)


@login_required
def detail_module(request, module_id):
    """Détail d'un module avec ses matières."""
    etablissement = _get_etablissement(request)
    if not etablissement:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    module = get_object_or_404(
        Module.objects.prefetch_related(
            'module_classes__classe',
            'module_classes__periode',
            'module_departments__department',
        ),
        id=module_id,
        etablissement=etablissement
    )
    matieres = list(
        module.matieres.filter(actif=True).order_by('nom').prefetch_related('classes')
    )
    # Matières sans module : filtrer par filière du module si définie
    matieres_sans_module_qs = Matiere.objects.filter(
        etablissement=etablissement,
        module__isnull=True,
        actif=True
    )
    linked_dep_ids = module.get_linked_department_ids()
    if linked_dep_ids:
        matieres_sans_module_qs = matieres_sans_module_qs.filter(department_id__in=linked_dep_ids)
    elif module.department_id:
        matieres_sans_module_qs = matieres_sans_module_qs.filter(department=module.department)
    matieres_sans_module = list(matieres_sans_module_qs.order_by('nom'))

    form_data = {}
    field_errors = {}
    open_modal_modifier = False
    matiere_modal_ctx = {
        'errors': {},
        'niveau_key': '',
        'niveau_label': '',
        'nom': '',
        'coefficient': '1.0',
        'filiere_scope': 'single',
        'department_id': '',
        'coefficients_par_filiere': {},
    }

    def _resolve_niveau_key_from_post():
        niveau_key = (request.POST.get('niveau_key') or '').strip()
        if niveau_key and _classe_ids_for_niveau_in_module(module, niveau_key):
            return niveau_key
        classe_id_raw = (request.POST.get('classe_id') or '').strip()
        if classe_id_raw.isdigit():
            try:
                classe = Classe.objects.get(id=int(classe_id_raw), etablissement=etablissement)
                if classe.id in _classe_ids_du_module(module):
                    return _niveau_groupe_key_classe(classe)
            except Classe.DoesNotExist:
                pass
        return ''

    if request.method == 'POST' and request.POST.get('action') == 'creer_matiere_hybride':
        nom_m = (request.POST.get('nom_matiere') or '').strip()
        niveau_key = (request.POST.get('niveau_key') or '').strip()
        filiere_scope = (request.POST.get('filiere_scope') or 'single').strip()
        department_id_raw = (request.POST.get('department_id') or '').strip()
        matiere_modal_ctx.update({
            'nom': nom_m,
            'niveau_key': niveau_key,
            'filiere_scope': filiere_scope,
            'department_id': department_id_raw,
        })
        if niveau_key:
            matiere_modal_ctx['niveau_label'] = libelle_cle_niveau_superieur(niveau_key)
        err = {}
        coefs_ctx = {}
        if not nom_m:
            err['nom_matiere'] = "Le nom de la matière est obligatoire."
        if not niveau_key:
            err['niveau_key'] = "Sélectionnez un niveau LMD."
        linked_deps = list(module.get_linked_departments())
        target_deps = []
        if filiere_scope == 'all':
            target_deps = linked_deps
        elif department_id_raw.isdigit():
            dep_id = int(department_id_raw)
            target_deps = [d for d in linked_deps if d.id == dep_id]
            if not target_deps:
                err['department_id'] = "Filière invalide pour ce module."
        else:
            err['department_id'] = "Sélectionnez une filière ou toutes les filières."
        coef_by_dep = {}
        for dep in target_deps:
            coef_field = f'coef_dep_{dep.id}'
            raw_coef = request.POST.get(coef_field, '1.0')
            coefs_ctx[str(dep.id)] = raw_coef
            coef_val, coef_err = _parse_coef_from_post(request, coef_field)
            if coef_err:
                err[coef_field] = f"{dep.nom} : {coef_err}"
            else:
                coef_by_dep[dep.id] = coef_val
        matiere_modal_ctx['coefficients_par_filiere'] = coefs_ctx
        if not err and target_deps:
            created = []
            dep_errors = []
            try:
                with transaction.atomic():
                    for dep in target_deps:
                        matiere, dep_err = _creer_matiere_pour_filiere_niveau(
                            module,
                            etablissement,
                            nom_m,
                            dep,
                            niveau_key,
                            coef_by_dep[dep.id],
                        )
                        if dep_err:
                            dep_errors.append(dep_err)
                        else:
                            created.append(matiere)
                    if dep_errors:
                        raise ValueError('; '.join(dep_errors))
            except ValueError as exc:
                err['non_field'] = str(exc)
            except IntegrityError:
                err['nom_matiere'] = "Impossible de créer : conflit d'unicité sur le nom."
            else:
                if created:
                    if len(created) == 1:
                        m0 = created[0]
                        messages.success(
                            request,
                            f"La matière « {m0.nom} » a été créée pour "
                            f"{m0.department.nom} — {libelle_cle_niveau_superieur(niveau_key)}.",
                        )
                    else:
                        messages.success(
                            request,
                            f"La matière « {nom_m} » a été créée pour "
                            f"{len(created)} filière(s) au niveau "
                            f"« {libelle_cle_niveau_superieur(niveau_key)} ».",
                        )
                    return redirect('matiere:detail_module', module_id=module.id)
        if err:
            matiere_modal_ctx['errors'] = err

    if request.method == 'POST' and request.POST.get('action') in (
        'creer_matiere_pour_classe',
        'creer_matiere_pour_niveau',
    ):
        nom_m = (request.POST.get('nom_matiere') or '').strip()
        niveau_key = _resolve_niveau_key_from_post()
        department_id_raw = (request.POST.get('department_id') or '').strip()
        matiere_modal_ctx['nom'] = nom_m
        matiere_modal_ctx['niveau_key'] = niveau_key
        matiere_modal_ctx['department_id'] = department_id_raw
        if niveau_key:
            matiere_modal_ctx['niveau_label'] = libelle_cle_niveau_superieur(niveau_key)
        err = {}
        coef_dec, coef_err = _parse_coef_from_post(request, 'coefficient_matiere')
        if coef_err:
            err['coefficient_matiere'] = coef_err
        if not niveau_key:
            err['niveau_key'] = "Niveau invalide."
        if not nom_m:
            err['nom_matiere'] = "Le nom de la matière est obligatoire."
        department_obj = None
        if department_id_raw.isdigit():
            dep_id = int(department_id_raw)
            department_obj = next(
                (d for d in module.get_linked_departments() if d.id == dep_id),
                None,
            )
            if not department_obj:
                err['department_id'] = "Filière invalide."
        elif module.is_shared:
            err['department_id'] = "La filière est obligatoire pour ce module mutualisé."
        if not err:
            if department_obj:
                matiere, dep_err = _creer_matiere_pour_filiere_niveau(
                    module,
                    etablissement,
                    nom_m,
                    department_obj,
                    niveau_key,
                    coef_dec or Decimal('1.0'),
                )
                if dep_err:
                    err['nom_matiere'] = dep_err
                else:
                    messages.success(
                        request,
                        f"La matière « {matiere.nom} » a été créée pour "
                        f"{department_obj.nom} — {libelle_cle_niveau_superieur(niveau_key)}.",
                    )
                    return redirect('matiere:detail_module', module_id=module.id)
            else:
                classes_niveau = _classes_for_niveau_in_module(module, niveau_key)
                niveau_label = libelle_cle_niveau_superieur(niveau_key)
                matiere_department = _matiere_department_for_module(module)
                if Matiere.objects.filter(
                    nom__iexact=nom_m,
                    etablissement=etablissement,
                    department=matiere_department,
                    module=module,
                    niveau_lmd_key=niveau_key,
                ).exists():
                    err['nom_matiere'] = (
                        f"Une matière « {nom_m} » existe déjà pour le niveau « {niveau_label} »."
                    )
                else:
                    try:
                        with transaction.atomic():
                            matiere = Matiere(
                                nom=nom_m[:100],
                                code=_generate_unique_matiere_code(nom_m),
                                etablissement=etablissement,
                                department=matiere_department,
                                module=module,
                                niveau_lmd_key=niveau_key,
                                niveau='superieur',
                                coefficient=coef_dec or Decimal('1.0'),
                                credits=coef_dec or Decimal('1.0'),
                                actif=True,
                            )
                            matiere.save()
                            matiere.classes.add(*classes_niveau)
                        messages.success(
                            request,
                            f"La matière « {nom_m} » a été créée pour le niveau "
                            f"« {niveau_label} » ({len(classes_niveau)} classe(s)).",
                        )
                        return redirect('matiere:detail_module', module_id=module.id)
                    except IntegrityError:
                        err['nom_matiere'] = (
                            f"Une matière « {nom_m} » existe déjà pour le niveau « {niveau_label} »."
                        )
        if err:
            matiere_modal_ctx['errors'] = err

    if request.method == 'POST' and request.POST.get('action') == 'ajouter_matiere':
        matiere_id = request.POST.get('matiere_id', '').strip()
        niveau_key = _resolve_niveau_key_from_post()
        credits_matiere = request.POST.get('credits_matiere', '0').strip()
        if not niveau_key:
            field_errors['niveau_key'] = "Niveau obligatoire pour rattacher la matière."
        elif matiere_id:
            try:
                classes_niveau = _classes_for_niveau_in_module(module, niveau_key)
                matiere = Matiere.objects.get(id=int(matiere_id), etablissement=etablissement)
                credits_val = Decimal(credits_matiere) if credits_matiere else Decimal('0')
                if credits_val < 0:
                    field_errors['credits_matiere'] = "Les crédits doivent être positifs."
                elif matiere.module_id and matiere.module_id != module.id:
                    field_errors['matiere_id'] = "Cette matière appartient à un autre module."
                else:
                    if matiere.module_id == module.id:
                        matiere.classes.add(*classes_niveau)
                        messages.success(
                            request,
                            f"La matière « {matiere.nom} » est associée au niveau "
                            f"« {libelle_cle_niveau_superieur(niveau_key)} ».",
                        )
                        return redirect('matiere:detail_module', module_id=module.id)
                    try:
                        with transaction.atomic():
                            matiere.module = module
                            matiere.niveau_lmd_key = niveau_key
                            matiere.credits = credits_val
                            matiere.save()
                            matiere.classes.add(*classes_niveau)
                    except IntegrityError:
                        field_errors['matiere_id'] = (
                            "Impossible d'ajouter : une matière avec ce nom existe déjà pour ce module."
                        )
                    else:
                        messages.success(
                            request,
                            f"La matière « {matiere.nom} » a été ajoutée au module pour le niveau "
                            f"« {libelle_cle_niveau_superieur(niveau_key)} ».",
                        )
                        return redirect('matiere:detail_module', module_id=module.id)
            except Matiere.DoesNotExist:
                field_errors['matiere_id'] = "Matière invalide."
            except ValueError:
                field_errors['matiere_id'] = "Données invalides."

    if request.method == 'POST' and request.POST.get('action') in (
        'retirer_matiere_classe',
        'retirer_matiere_niveau',
    ):
        matiere_id = request.POST.get('matiere_id', '').strip()
        niveau_key = _resolve_niveau_key_from_post()
        department_id_raw = (request.POST.get('department_id') or '').strip()
        if matiere_id and niveau_key:
            try:
                matiere = Matiere.objects.get(
                    id=int(matiere_id), etablissement=etablissement, module=module
                )
                if department_id_raw.isdigit():
                    classe_ids = _classe_ids_for_department_niveau_in_module(
                        module, int(department_id_raw), niveau_key
                    )
                    if classe_ids:
                        matiere.classes.remove(*Classe.objects.filter(id__in=classe_ids))
                else:
                    _detach_matiere_from_niveau(matiere, module, niveau_key)
                if matiere.classes.count() == 0:
                    matiere.module = None
                    matiere.niveau_lmd_key = ''
                    matiere.credits = None
                    matiere.save()
                    messages.success(
                        request,
                        f"La matière « {matiere.nom} » a été retirée (plus aucune classe liée).",
                    )
                else:
                    messages.success(
                        request,
                        f"La matière « {matiere.nom} » n'est plus liée au niveau "
                        f"« {libelle_cle_niveau_superieur(niveau_key)} ».",
                    )
                return redirect('matiere:detail_module', module_id=module.id)
            except (Matiere.DoesNotExist, ValueError):
                pass

    if request.method == 'POST' and request.POST.get('action') == 'retirer_matiere':
        matiere_id = request.POST.get('matiere_id', '').strip()
        if matiere_id:
            try:
                matiere = Matiere.objects.get(id=int(matiere_id), etablissement=etablissement, module=module)
                matiere.classes.clear()
                matiere.module = None
                matiere.niveau_lmd_key = ''
                matiere.credits = None
                matiere.save()
                messages.success(request, f"La matière « {matiere.nom} » a été retirée du module.")
                return redirect('matiere:detail_module', module_id=module.id)
            except Matiere.DoesNotExist:
                pass

    if request.method == 'POST' and request.POST.get('action') == 'modifier_module':
        all_niveaux = _build_all_modal_niveaux_par_filiere(etablissement)
        periodes_par_niveau_ctx, periodes_map = _build_modal_periodes_par_niveau(
            request, etablissement, all_niveaux
        )
        niveaux_selectionnes, credits_per_niveau, numeros_per_niveau, periodes_per_niveau = (
            _parse_niveau_form_from_post(request)
        )
        departments_ids = _parse_departments_ids_from_request(request)
        form_data = {
            'nom': request.POST.get('nom', module.nom).strip(),
            'department': int(departments_ids[0]) if len(departments_ids) == 1 else None,
            'departments_ids': departments_ids,
            'niveaux': niveaux_selectionnes,
            'credits_per_niveau': credits_per_niveau,
            'numeros_per_niveau': numeros_per_niveau,
            'periodes_per_niveau': periodes_per_niveau,
        }

        is_valid = True
        if not form_data['nom']:
            field_errors['nom'] = "Le nom est obligatoire."
            is_valid = False
        departments_objs = Department.objects.none()
        if not departments_ids:
            field_errors['department'] = "Sélectionnez au moins une spécialité."
            is_valid = False
        elif is_valid:
            departments_objs = Department.objects.filter(
                id__in=[int(x) for x in departments_ids],
                etablissement=etablissement,
            )
            if departments_objs.count() != len(departments_ids):
                field_errors['department'] = "Une ou plusieurs spécialités sont invalides."
                is_valid = False
        if is_valid:
            is_valid = _validate_niveau_form(
                form_data['niveaux'],
                credits_per_niveau,
                periodes_per_niveau,
                periodes_map,
                field_errors,
            )
        if is_valid:
            module.nom = form_data['nom']
            module.niveau_lmd = None
            module.save(update_fields=['nom', 'niveau_lmd', 'date_modification'])
            _sync_module_departments(module, departments_ids)
            ModuleClasse.objects.filter(module=module).delete()
            if departments_objs.exists() and form_data['niveaux']:
                _persist_module_niveaux(
                    module,
                    etablissement,
                    departments_objs,
                    form_data['niveaux'],
                    credits_per_niveau,
                    numeros_per_niveau,
                    periodes_per_niveau,
                )
            messages.success(request, "Module modifié.")
            return redirect('matiere:detail_module', module_id=module.id)
        open_modal_modifier = True

    departments = Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
    linked_dep_ids = module.get_linked_department_ids()
    all_niveaux = _build_all_modal_niveaux_par_filiere(etablissement)
    periodes_par_niveau_edit, _periodes_map_edit = _build_modal_periodes_par_niveau(
        request, etablissement, all_niveaux
    )
    niveau_form_defaults = _module_niveau_form_data_from_module(module)
    form_data_default = {
        'nom': module.nom,
        'department': module.department_id,
        'departments_ids': [str(x) for x in linked_dep_ids],
        **niveau_form_defaults,
    }

    module_by_niveau = _module_classes_by_niveau(module)
    filiere_panels = _build_filiere_panels_for_module_detail(module, matieres)
    niveaux_cards = _build_niveaux_cards_for_module(module, matieres)
    matiere_niveaux_par_filiere = _build_module_niveaux_par_filiere_for_matiere(module)
    matieres_toutes_classes = [m for m in matieres if m.classes.count() == 0]
    matieres_avec_niveaux = [
        {
            'matiere': m,
            'niveaux_labels': _niveaux_labels_for_matiere(m, module_by_niveau),
        }
        for m in matieres
    ]
    nb_niveaux_module = len(niveaux_cards)

    linked_departments = module.get_linked_departments()
    context = {
        'module': module,
        'linked_departments': linked_departments,
        'is_module_shared': module.is_shared,
        'matieres': matieres,
        'matieres_sans_module': matieres_sans_module,
        'matieres_toutes_classes': matieres_toutes_classes,
        'matieres_avec_niveaux': matieres_avec_niveaux,
        'niveaux_cards': niveaux_cards,
        'filiere_panels': filiere_panels,
        'matiere_niveaux_par_filiere': matiere_niveaux_par_filiere,
        'matiere_niveaux_par_filiere_json': json.dumps(
            _serialize_matiere_niveaux_par_filiere(matiere_niveaux_par_filiere)
        ),
        'matiere_modal_coefs_json': json.dumps(matiere_modal_ctx.get('coefficients_par_filiere') or {}),
        'nb_niveaux_module': nb_niveaux_module,
        'etablissement': etablissement,
        'departments': departments,
        'form_data': form_data or form_data_default,
        'field_errors': field_errors,
        'open_modal_modifier': open_modal_modifier,
        'matiere_modal': matiere_modal_ctx,
        'modal_niveaux_par_filiere': all_niveaux,
        'modal_periodes_par_niveau': periodes_par_niveau_edit,
    }
    return render(request, 'school_admin/directeur/pedagogique/modules/detail_module.html', context)


@login_required
def supprimer_module(request, module_id):
    """Supprime un module (retire le lien module des matières)."""
    etablissement = _get_etablissement(request)
    if not etablissement:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    module = get_object_or_404(Module, id=module_id, etablissement=etablissement)
    nom = module.nom
    with transaction.atomic():
        for matiere in module.matieres.all():
            matiere.module = None
            matiere.credits = None
            matiere.save()
        module.delete()
    messages.success(request, f"Le module « {nom} » a été supprimé.")
    return _redirect_liste_matieres_tab('modules')
