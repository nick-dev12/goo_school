# school_admin/controllers/module_controller.py

from decimal import Decimal
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

from ..model.module_model import Module, ModuleClasse
from ..model.matiere_model import Matiere
from ..model.etablissement_model import Etablissement
from ..model.academic_structure_model import Department
from ..model.classe_model import Classe, libelle_cle_niveau_superieur
from ..model.periode_model import PeriodeScolaire
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..utils.session_utils import get_session_active

logger = logging.getLogger(__name__)

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
        Prefetch('classes', queryset=classes_prefetch),
    ).order_by('department', 'ordre', 'nom')

    stats = {
        'total': modules.count(),
        'actives': modules.filter(actif=True).count(),
    }

    modules_par_filiere = []
    departments = Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
    for dep in departments:
        mods_dep = [m for m in modules if m.department_id == dep.id]
        if mods_dep:
            modules_par_filiere.append({
                'department': dep,
                'modules': mods_dep,
                'niveaux': _modules_par_niveau_panels(mods_dep),
            })
    mods_sans_filiere = [m for m in modules if m.department_id is None]
    if mods_sans_filiere:
        modules_par_filiere.insert(0, {
            'department': None,
            'modules': mods_sans_filiere,
            'niveaux': _modules_par_niveau_panels(mods_sans_filiere),
        })

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
            'credits_per_niveau': {},
            'numeros_per_niveau': {},
            'periodes_per_niveau': {},
        },
        'modal_field_errors': {},
        'modal_groupes_classes': OrderedDict(),
        'modal_periodes_par_niveau': {},
    }


def _modal_ajouter_from_query(request, etablissement):
    """Ouverture modale via GET (?ouvrir_modal=1&department=&nom=)."""
    dep_raw = (request.GET.get('department') or '').strip()
    nom = (request.GET.get('nom') or '').strip()
    groupes_classes = OrderedDict()
    periodes_map = _periodes_par_niveau_superieur(request, etablissement)
    periodes_par_niveau = {}
    if dep_raw.isdigit():
        groupes_classes = _groupes_classes_par_niveau(etablissement, int(dep_raw))
        periodes_par_niveau = {
            niveau: _periodes_disponibles_pour_niveau(periodes_map, niveau)
            for niveau in groupes_classes.keys()
        }
    return {
        'show_modal_ajouter': True,
        'modal_form_data': {
            'nom': nom,
            'department': dep_raw if dep_raw else None,
            'credits_per_niveau': {},
            'numeros_per_niveau': {},
            'periodes_per_niveau': {},
        },
        'modal_field_errors': {},
        'modal_groupes_classes': groupes_classes,
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

    context = _build_liste_modules_context(request, etablissement)
    if request.GET.get('ouvrir_modal'):
        context.update(_modal_ajouter_from_query(request, etablissement))
    return render(request, 'school_admin/directeur/pedagogique/modules/liste_modules.html', context)


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
        q = [('ouvrir_modal', '1')]
        dep = (request.GET.get('department') or '').strip()
        nom = (request.GET.get('nom') or '').strip()
        if dep:
            q.append(('department', dep))
        if nom:
            q.append(('nom', nom))
        return redirect(f"{reverse('matiere:liste_modules')}?{urlencode(q)}")

    # POST
    periodes_map = _periodes_par_niveau_superieur(request, etablissement)
    niveaux_selectionnes = request.POST.getlist('niveaux')
    credits_per_niveau = {}
    numeros_per_niveau = {}
    periodes_per_niveau = {}
    for niveau in niveaux_selectionnes:
        raw = request.POST.get(f'credits_{niveau}', '0').strip()
        try:
            credits_per_niveau[niveau] = Decimal(raw) if raw else Decimal('0')
            if credits_per_niveau[niveau] < 0:
                credits_per_niveau[niveau] = Decimal('0')
        except Exception:
            credits_per_niveau[niveau] = Decimal('0')
        numeros_per_niveau[niveau] = (request.POST.get(f'numero_{niveau}', '') or '').strip()[:80]
        periodes_per_niveau[niveau] = (request.POST.get(f'periode_{niveau}', '') or '').strip()

    dept_post = (request.POST.get('department', '') or '').strip()
    form_data = {
        'nom': (request.POST.get('nom', '') or '').strip(),
        'department': dept_post or None,
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

    if not form_data['department']:
        field_errors['department'] = "La spécialité est obligatoire."
        is_valid = False

    department_obj = None
    if form_data['department']:
        try:
            department_obj = Department.objects.get(
                id=int(form_data['department']),
                etablissement=etablissement
            )
        except (ValueError, Department.DoesNotExist):
            field_errors['department'] = "Spécialité invalide."
            is_valid = False

    if not form_data['niveaux'] and is_valid:
        field_errors['niveaux'] = "Sélectionnez au moins un niveau."
        is_valid = False

    for niveau in form_data['niveaux']:
        if credits_per_niveau.get(niveau, Decimal('0')) < 0:
            field_errors['credits_per_niveau'] = "Les crédits ne peuvent pas être négatifs."
            is_valid = False
            break
        periode_id_raw = periodes_per_niveau.get(niveau, '')
        periodes_autorisees = _periodes_disponibles_pour_niveau(periodes_map, niveau)
        periodes_autorisees_ids = {str(p.id) for p in periodes_autorisees}
        if periode_id_raw and periode_id_raw not in periodes_autorisees_ids:
            field_errors['periodes_per_niveau'] = (
                "La période choisie ne correspond pas au niveau sélectionné."
            )
            is_valid = False
            break

    groupes_classes = OrderedDict()
    periodes_par_niveau = {}
    if form_data.get('department') and str(form_data['department']).isdigit():
        groupes_classes = _groupes_classes_par_niveau(etablissement, int(form_data['department']))
        periodes_par_niveau = {
            niveau: _periodes_disponibles_pour_niveau(periodes_map, niveau)
            for niveau in groupes_classes.keys()
        }

    if is_valid:
        try:
            dernier_num = Module.objects.filter(etablissement=etablissement).count()
            code = f"MOD-{dernier_num + 1:04d}"
            while Module.objects.filter(etablissement=etablissement, code=code).exists():
                dernier_num += 1
                code = f"MOD-{dernier_num:04d}"
            module = Module.objects.create(
                nom=form_data['nom'],
                code=code,
                etablissement=etablissement,
                department=department_obj,
                niveau_lmd=None,
            )
            if form_data['niveaux'] and department_obj:
                for niveau in form_data['niveaux']:
                    credits_val = credits_per_niveau.get(niveau, Decimal('0'))
                    if credits_val < 0:
                        credits_val = Decimal('0')
                    numero_val = numeros_per_niveau.get(niveau, '')[:80]
                    periode_obj = None
                    periode_id_raw = periodes_per_niveau.get(niveau, '')
                    if periode_id_raw.isdigit():
                        periode_obj = PeriodeScolaire.objects.filter(
                            id=int(periode_id_raw),
                            etablissement=etablissement,
                        ).first()
                    if niveau == 'Sans niveau':
                        classes_niveau = Classe.objects.filter(
                            etablissement=etablissement,
                            department=department_obj,
                            niveau_lmd__isnull=True,
                            actif=True,
                        )
                    elif niveau in [n[0] for n in NIVEAUX_SUPERIEUR]:
                        classes_niveau = Classe.objects.filter(
                            etablissement=etablissement,
                            department=department_obj,
                            niveau_lmd=niveau,
                            actif=True,
                        )
                    else:
                        classes_niveau = Classe.objects.filter(
                            etablissement=etablissement,
                            department=department_obj,
                            niveau_lmd='AUTRE',
                            niveau_libelle=niveau,
                            actif=True,
                        )
                    for classe in classes_niveau:
                        ModuleClasse.objects.create(
                            module=module,
                            classe=classe,
                            credits=credits_val,
                            numero_ue=numero_val,
                            periode=periode_obj,
                        )
            messages.success(request, f"Le module « {form_data['nom']} » a été créé.")
            return redirect('matiere:liste_modules')
        except Exception as e:
            logger.error(f"Erreur création module: {e}")
            field_errors['non_field'] = "Erreur lors de la création."

    ctx = _build_liste_modules_context(request, etablissement)
    ctx.update({
        'show_modal_ajouter': True,
        'modal_form_data': form_data,
        'modal_field_errors': field_errors,
        'modal_groupes_classes': groupes_classes,
        'modal_periodes_par_niveau': periodes_par_niveau,
    })
    return render(request, 'school_admin/directeur/pedagogique/modules/liste_modules.html', ctx)


@login_required
def detail_module(request, module_id):
    """Détail d'un module avec ses matières."""
    etablissement = _get_etablissement(request)
    if not etablissement:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    module = get_object_or_404(
        Module.objects.prefetch_related('module_classes__classe', 'module_classes__periode'),
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
    if module.department:
        matieres_sans_module_qs = matieres_sans_module_qs.filter(department=module.department)
    matieres_sans_module = list(matieres_sans_module_qs.order_by('nom'))

    form_data = {}
    field_errors = {}
    open_modal_modifier = False
    matiere_modal_ctx = {
        'errors': {},
        'classe_id': '',
        'classe_nom': '',
        'nom': '',
        'coefficient': '1.0',
    }

    if request.method == 'POST' and request.POST.get('action') == 'creer_matiere_pour_classe':
        nom_m = (request.POST.get('nom_matiere') or '').strip()
        coef_raw = (request.POST.get('coefficient_matiere') or '').strip()
        classe_id_raw = (request.POST.get('classe_id') or '').strip()
        matiere_modal_ctx['nom'] = nom_m
        matiere_modal_ctx['coefficient'] = coef_raw if coef_raw else '1.0'
        matiere_modal_ctx['classe_id'] = classe_id_raw
        err = {}
        coef_dec = Decimal('1.0')
        if not classe_id_raw or not classe_id_raw.isdigit():
            err['classe_id'] = "Classe invalide."
        if not nom_m:
            err['nom_matiere'] = "Le nom de la matière est obligatoire."
        if coef_raw:
            try:
                coef_dec = Decimal(coef_raw).quantize(Decimal('0.1'))
                if coef_dec < 0 or coef_dec > 10:
                    err['coefficient_matiere'] = "Le coefficient doit être entre 0 et 10."
            except Exception:
                err['coefficient_matiere'] = "Coefficient invalide."
        if not err:
            try:
                classe = Classe.objects.get(
                    id=int(classe_id_raw),
                    etablissement=etablissement,
                )
                if classe.id not in _classe_ids_du_module(module):
                    err['classe_id'] = "Cette classe ne fait pas partie du module."
                else:
                    with transaction.atomic():
                        matiere = Matiere(
                            nom=nom_m[:100],
                            code=_generate_unique_matiere_code(nom_m),
                            etablissement=etablissement,
                            department=module.department,
                            module=module,
                            niveau='superieur',
                            coefficient=coef_dec,
                            credits=coef_dec,
                            actif=True,
                        )
                        matiere.save()
                        matiere.classes.add(classe)
                    messages.success(
                        request,
                        f"La matière « {nom_m} » a été créée pour la classe « {classe.nom} ».",
                    )
                    return redirect('matiere:detail_module', module_id=module.id)
            except Classe.DoesNotExist:
                err['classe_id'] = "Classe introuvable."
            except IntegrityError:
                err['nom_matiere'] = (
                    "Une matière avec ce nom existe déjà pour ce module et cette spécialité."
                )
        if err:
            matiere_modal_ctx['errors'] = err
            if classe_id_raw.isdigit():
                try:
                    _cn = Classe.objects.get(
                        id=int(classe_id_raw), etablissement=etablissement
                    ).nom
                    matiere_modal_ctx['classe_nom'] = _cn
                except Classe.DoesNotExist:
                    pass

    if request.method == 'POST' and request.POST.get('action') == 'ajouter_matiere':
        matiere_id = request.POST.get('matiere_id', '').strip()
        classe_id_raw = request.POST.get('classe_id', '').strip()
        credits_matiere = request.POST.get('credits_matiere', '0').strip()
        if not classe_id_raw or not classe_id_raw.isdigit():
            field_errors['classe_id'] = "Classe obligatoire pour rattacher la matière."
        elif matiere_id:
            try:
                classe = Classe.objects.get(
                    id=int(classe_id_raw),
                    etablissement=etablissement,
                )
                if classe.id not in _classe_ids_du_module(module):
                    field_errors['classe_id'] = "Cette classe ne fait pas partie du module."
                else:
                    matiere = Matiere.objects.get(id=int(matiere_id), etablissement=etablissement)
                    credits_val = Decimal(credits_matiere) if credits_matiere else Decimal('0')
                    if credits_val < 0:
                        field_errors['credits_matiere'] = "Les crédits doivent être positifs."
                    elif matiere.module_id and matiere.module_id != module.id:
                        field_errors['matiere_id'] = "Cette matière appartient à un autre module."
                    else:
                        if matiere.module_id == module.id:
                            matiere.classes.add(classe)
                            messages.success(
                                request,
                                f"La matière « {matiere.nom} » est associée à la classe « {classe.nom} ».",
                            )
                            return redirect('matiere:detail_module', module_id=module.id)
                        try:
                            with transaction.atomic():
                                matiere.module = module
                                matiere.credits = credits_val
                                matiere.save()
                                matiere.classes.add(classe)
                        except IntegrityError:
                            field_errors['matiere_id'] = (
                                "Impossible d'ajouter : une matière avec ce nom existe déjà pour ce module."
                            )
                        else:
                            messages.success(
                                request,
                                f"La matière « {matiere.nom} » a été ajoutée au module pour « {classe.nom} ».",
                            )
                            return redirect('matiere:detail_module', module_id=module.id)
            except Classe.DoesNotExist:
                field_errors['classe_id'] = "Classe invalide."
            except Matiere.DoesNotExist:
                field_errors['matiere_id'] = "Matière invalide."
            except ValueError:
                field_errors['matiere_id'] = "Données invalides."

    if request.method == 'POST' and request.POST.get('action') == 'retirer_matiere_classe':
        matiere_id = request.POST.get('matiere_id', '').strip()
        classe_id_raw = request.POST.get('classe_id', '').strip()
        if matiere_id and classe_id_raw and classe_id_raw.isdigit():
            try:
                matiere = Matiere.objects.get(
                    id=int(matiere_id), etablissement=etablissement, module=module
                )
                classe = Classe.objects.get(
                    id=int(classe_id_raw), etablissement=etablissement
                )
                matiere.classes.remove(classe)
                if matiere.classes.count() == 0:
                    matiere.module = None
                    matiere.credits = None
                    matiere.save()
                    messages.success(
                        request,
                        f"La matière « {matiere.nom} » a été retirée (plus aucune classe liée).",
                    )
                else:
                    messages.success(
                        request,
                        f"La matière « {matiere.nom} » n'est plus liée à « {classe.nom} ».",
                    )
                return redirect('matiere:detail_module', module_id=module.id)
            except (Matiere.DoesNotExist, Classe.DoesNotExist, ValueError):
                pass

    if request.method == 'POST' and request.POST.get('action') == 'retirer_matiere':
        matiere_id = request.POST.get('matiere_id', '').strip()
        if matiere_id:
            try:
                matiere = Matiere.objects.get(id=int(matiere_id), etablissement=etablissement, module=module)
                matiere.classes.clear()
                matiere.module = None
                matiere.credits = None
                matiere.save()
                messages.success(request, f"La matière « {matiere.nom} » a été retirée du module.")
                return redirect('matiere:detail_module', module_id=module.id)
            except Matiere.DoesNotExist:
                pass

    if request.method == 'POST' and request.POST.get('action') == 'modifier_module':
        periodes_map = _periodes_par_niveau_superieur(request, etablissement)
        dept_raw = request.POST.get('department', '').strip()
        form_data = {
            'nom': request.POST.get('nom', module.nom).strip(),
            'department': int(dept_raw) if dept_raw and dept_raw.isdigit() else None,
            'classes_ids': [x for x in request.POST.getlist('classes_ids') if x.isdigit()],
        }
        credits_per_classe = {}
        numeros_per_classe = {}
        periodes_per_classe = {}
        for cid in form_data['classes_ids']:
            raw = request.POST.get(f'credits_{cid}', '0').strip()
            try:
                credits_per_classe[cid] = Decimal(raw) if raw else Decimal('0')
                if credits_per_classe[cid] < 0:
                    credits_per_classe[cid] = Decimal('0')
            except Exception:
                credits_per_classe[cid] = Decimal('0')
            numeros_per_classe[cid] = (request.POST.get(f'numero_{cid}', '') or '').strip()[:80]
            periodes_per_classe[cid] = (request.POST.get(f'periode_{cid}', '') or '').strip()
        form_data['credits_per_classe'] = credits_per_classe
        form_data['numeros_per_classe'] = numeros_per_classe
        form_data['periodes_per_classe'] = periodes_per_classe

        is_valid = True
        if not form_data['nom']:
            field_errors['nom'] = "Le nom est obligatoire."
            is_valid = False
        department_obj = None
        classes_valid = Classe.objects.none()
        periodes_obj_par_classe_id = {}
        if form_data['department'] is not None:
            try:
                department_obj = Department.objects.get(id=form_data['department'], etablissement=etablissement)
            except Department.DoesNotExist:
                department_obj = None
                field_errors['department'] = "Filière invalide."
                is_valid = False
        if is_valid and department_obj and form_data['classes_ids']:
            classes_valid = Classe.objects.filter(
                id__in=form_data['classes_ids'],
                etablissement=etablissement,
                department=department_obj,
            ).select_related('academic_level')
            classes_valid_ids = {str(c.id) for c in classes_valid}
            if classes_valid_ids != set(form_data['classes_ids']):
                field_errors['classes_ids'] = "Certaines classes sélectionnées sont invalides."
                is_valid = False
            for classe in classes_valid:
                classe_id_str = str(classe.id)
                credits_val = form_data['credits_per_classe'].get(classe_id_str, Decimal('0'))
                if credits_val < 0:
                    field_errors['credits_per_classe'] = "Les crédits ne peuvent pas être négatifs."
                    is_valid = False
                    break
                periode_id_raw = form_data['periodes_per_classe'].get(classe_id_str, '')
                periodes_autorisees = _periodes_disponibles_pour_niveau(
                    periodes_map,
                    _niveau_groupe_key_classe(classe),
                )
                periodes_autorisees_ids = {str(p.id) for p in periodes_autorisees}
                if periode_id_raw and periode_id_raw not in periodes_autorisees_ids:
                    field_errors['periodes_per_classe'] = (
                        "La période choisie ne correspond pas au niveau de la classe."
                    )
                    is_valid = False
                    break
                periode_obj = None
                if periode_id_raw:
                    periode_obj = next(
                        (p for p in periodes_autorisees if str(p.id) == periode_id_raw),
                        None,
                    )
                    if periode_obj is None:
                        field_errors['periodes_per_classe'] = "Période invalide."
                        is_valid = False
                        break
                periodes_obj_par_classe_id[classe.id] = periode_obj
        if is_valid:
            module.nom = form_data['nom']
            module.department = department_obj
            module.niveau_lmd = None
            module.save()
            ModuleClasse.objects.filter(module=module).delete()
            if department_obj and form_data['classes_ids']:
                for classe in classes_valid:
                    credits_val = form_data['credits_per_classe'].get(str(classe.id), Decimal('0'))
                    numero_val = form_data.get('numeros_per_classe', {}).get(str(classe.id), '')[:80]
                    periode_obj = periodes_obj_par_classe_id.get(classe.id)
                    ModuleClasse.objects.create(
                        module=module,
                        classe=classe,
                        credits=credits_val,
                        numero_ue=numero_val,
                        periode=periode_obj,
                    )
            messages.success(request, "Module modifié.")
            return redirect('matiere:detail_module', module_id=module.id)
        open_modal_modifier = True

    departments = Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
    groupes_classes = _groupes_classes_par_niveau(etablissement, module.department_id) if module.department_id else OrderedDict()
    periodes_map = _periodes_par_niveau_superieur(request, etablissement)
    periodes_par_niveau_edit = {
        niveau: _periodes_disponibles_pour_niveau(periodes_map, niveau)
        for niveau in groupes_classes.keys()
    }
    credits_per_classe = {}
    numeros_per_classe = {}
    periodes_per_classe = {}
    for mc in module.module_classes.select_related(
        'classe__academic_level', 'classe__department', 'periode'
    ).all():
        credits_per_classe[str(mc.classe_id)] = mc.credits
        numeros_per_classe[str(mc.classe_id)] = (mc.numero_ue or '').strip()
        periodes_per_classe[str(mc.classe_id)] = str(mc.periode_id) if mc.periode_id else ''
    form_data_default = {
        'nom': module.nom,
        'department': module.department_id,
        'classes_ids': [str(x) for x in module.classes.values_list('id', flat=True)],
        'credits_per_classe': credits_per_classe,
        'numeros_per_classe': numeros_per_classe,
        'periodes_per_classe': periodes_per_classe,
    }

    classes_cards = []
    for mc in module.module_classes.select_related(
        'classe__academic_level', 'classe__department', 'periode'
    ).order_by('classe__nom'):
        c = mc.classe
        classes_cards.append({
            'mc': mc,
            'classe': c,
            'matieres_pour_classe': _matieres_visibles_pour_classe(matieres, c),
            'matieres_ajoutables': _matieres_ajoutables_pour_classe(
                module, c, matieres_sans_module
            ),
        })
    matieres_toutes_classes = [m for m in matieres if m.classes.count() == 0]

    context = {
        'module': module,
        'matieres': matieres,
        'matieres_sans_module': matieres_sans_module,
        'matieres_toutes_classes': matieres_toutes_classes,
        'classes_cards': classes_cards,
        'etablissement': etablissement,
        'departments': departments,
        'groupes_classes': groupes_classes,
        'form_data': form_data or form_data_default,
        'field_errors': field_errors,
        'open_modal_modifier': open_modal_modifier,
        'matiere_modal': matiere_modal_ctx,
        'periodes_par_niveau_edit': periodes_par_niveau_edit,
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
    return redirect('matiere:liste_modules')
