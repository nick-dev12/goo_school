from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Count, Q, Prefetch
import logging
import random
import string

from ..model.matiere_model import Matiere
from ..model.etablissement_model import Etablissement
from ..model.classe_model import Classe
from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
from ..model.academic_structure_model import Department
from ..model.module_model import Module
from ..model.classe_model import libelle_cle_niveau_superieur
from ..services.realtime_helpers import wants_json_response, json_ok, json_fail, emit_live
from ..services.live_serializers import serialize_matiere_item

logger = logging.getLogger(__name__)

# Clé interne pour l’onglet « sans niveau LMD » (modules sans niveau ni classes côté filière)
NIVEAU_TAB_SANS_NIVEAU = '__sans_niveau__'

_ORDER_NIVEAUX_SUP_TAB = {
    'L1': 1, 'L2': 2, 'L3': 3, 'BTS': 4, 'DUT': 5, 'BUT': 6, 'BT': 7, 'LP': 8,
    'M1': 9, 'M2': 10, 'D1': 11, 'D2': 12, 'D3': 13, 'CERT': 14, 'DIPL': 15, 'AUTRE': 98,
}


def _niveau_key_from_classe(classe):
    if not classe or not classe.niveau_lmd:
        return None
    if classe.niveau_lmd == 'AUTRE':
        return (classe.niveau_libelle or 'AUTRE').strip()
    return classe.niveau_lmd


def _niveau_keys_for_module_in_dep(module, dep_id):
    """Niveaux LMD d’un module pour une filière (code module ou classes liées)."""
    if module.niveau_lmd and module.niveau_lmd != 'AUTRE':
        return {module.niveau_lmd}
    keys = set()
    for c in module.classes.all():
        if c.department_id == dep_id:
            k = _niveau_key_from_classe(c)
            if k:
                keys.add(k)
    if not keys and module.niveau_lmd == 'AUTRE':
        keys.add('AUTRE')
    if not keys:
        keys.add(NIVEAU_TAB_SANS_NIVEAU)
    return keys


def _niveau_keys_for_matiere_in_dep(matiere, dep_id):
    keys = set()
    for c in matiere.classes.all():
        if c.department_id == dep_id:
            k = _niveau_key_from_classe(c)
            if k:
                keys.add(k)
    if not keys:
        keys.add(NIVEAU_TAB_SANS_NIVEAU)
    return keys


def _classe_matches_niveau_tab(classe, dep_id, nk):
    """True si la classe est dans la filière et son niveau LMD correspond à l’onglet nk."""
    if not classe or classe.department_id != dep_id:
        return False
    key = _niveau_key_from_classe(classe)
    if nk == NIVEAU_TAB_SANS_NIVEAU:
        return key is None
    if key is None:
        return False
    return key == nk


def _matiere_a_pour_niveau_dans_dep(matiere, dep_id, nk):
    """Matière rattachée au niveau nk via au moins une classe de la filière (comme sur la fiche module)."""
    for c in matiere.classes.all():
        if _classe_matches_niveau_tab(c, dep_id, nk):
            return True
    return False


def _classes_matiere_pour_niveau_tab(matiere, dep_id, nk):
    """Classes de la matière dans la filière, limitées au niveau de l’onglet."""
    result = []
    for c in matiere.classes.filter(department_id=dep_id).order_by('niveau_lmd', 'nom'):
        if _classe_matches_niveau_tab(c, dep_id, nk):
            result.append(c)
    return result


def _sort_niveau_tab_keys(keys):
    def sort_key(k):
        if k == NIVEAU_TAB_SANS_NIVEAU:
            return (1000, '')
        return (_ORDER_NIVEAUX_SUP_TAB.get(k, 500), k)

    return sorted(keys, key=sort_key)


def _label_for_niveau_tab(niveau_key):
    if niveau_key == NIVEAU_TAB_SANS_NIVEAU:
        return 'Sans niveau'
    return libelle_cle_niveau_superieur(niveau_key)


def build_matieres_par_filiere_superieur(matieres_qs, departments, modules_by_department, classes_by_department):
    """
    Filière → onglets par niveau LMD → modules → matières (vue liste supérieur).
    """
    matieres_par_filiere = []
    for dep in departments:
        modules_dep = modules_by_department.get(dep.id, [])
        classes_dep = classes_by_department.get(dep.id, [])

        all_keys = set()
        for mod in modules_dep:
            all_keys |= _niveau_keys_for_module_in_dep(mod, dep.id)
        for c in classes_dep:
            k = _niveau_key_from_classe(c)
            if k:
                all_keys.add(k)
            elif c.niveau == 'superieur':
                all_keys.add(NIVEAU_TAB_SANS_NIVEAU)

        sans_mod_qs = matieres_qs.filter(department=dep, module__isnull=True)
        sans_mod_list = list(sans_mod_qs.order_by('nom'))
        for m in sans_mod_list:
            all_keys |= _niveau_keys_for_matiere_in_dep(m, dep.id)

        if not all_keys:
            all_keys.add(NIVEAU_TAB_SANS_NIVEAU)

        sorted_keys = _sort_niveau_tab_keys(all_keys)
        niveaux_list = []

        for nk in sorted_keys:
            modules_avec_matieres = []
            for mod in modules_dep:
                if nk not in _niveau_keys_for_module_in_dep(mod, dep.id):
                    continue
                matieres_mod = matieres_qs.filter(department=dep, module=mod).order_by('nom')
                matieres_list = []
                dep_id = dep.id
                for m in matieres_mod:
                    if not _matiere_a_pour_niveau_dans_dep(m, dep_id, nk):
                        continue
                    matieres_list.append({
                        'matiere': m,
                        'classes': _classes_matiere_pour_niveau_tab(m, dep_id, nk),
                    })
                modules_avec_matieres.append({'module': mod, 'matieres': matieres_list})

            matieres_sans = []
            dep_id = dep.id
            for m in sans_mod_list:
                if nk in _niveau_keys_for_matiere_in_dep(m, dep_id):
                    matieres_sans.append({
                        'matiere': m,
                        'classes': _classes_matiere_pour_niveau_tab(m, dep_id, nk),
                    })
            if matieres_sans:
                modules_avec_matieres.append({'module': None, 'matieres': matieres_sans})

            niveaux_list.append({
                'niveau_key': nk,
                'niveau_label': _label_for_niveau_tab(nk),
                'modules': modules_avec_matieres,
            })

        matieres_par_filiere.append({
            'department': dep,
            'niveaux': niveaux_list,
        })

    return matieres_par_filiere


class MatiereController:
    """
    Contrôleur pour la gestion des matières
    """
    
    @staticmethod
    def get_niveau_from_type_etablissement(type_etablissement):
        """
        Détermine le niveau de matière à partir du type d'établissement
        
        Args:
            type_etablissement: Le type d'établissement (primary, collège, lycée, collège_lycée, mixte)
            
        Returns:
            str: Le niveau correspondant (primaire, college, lycee, tous)
        """
        mapping = {
            'primary': 'primaire',
            'collège': 'college',
            'lycée': 'lycee',
            'lycee': 'lycee',  # Version sans accent (base de données)
            'collège_lycée': 'college',  # Par défaut pour collège+lycée
            'coll�ge_lyc�e': 'college',  # Version avec caractères spéciaux
            'mixte': 'tous',  # Pour mixte, on peut utiliser "tous" pour permettre tous les niveaux
            'superieur': 'superieur',  # Enseignement supérieur (modules et crédits LMD)
        }
        return mapping.get(type_etablissement, 'tous')
    
    @staticmethod
    @login_required
    def liste_matieres(request):
        """
        Affiche la liste des matières avec possibilité d'ajout
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        # Récupérer les matières (avec department pour affichage filière)
        _classes_qs = Classe.objects.select_related('department', 'academic_level')
        matieres = Matiere.objects.filter(etablissement=etablissement).select_related(
            'department', 'module'
        ).prefetch_related(Prefetch('classes', queryset=_classes_qs)).order_by('nom')
        
        # Récupérer les classes et créer les groupes
        import re
        classes = Classe.objects.filter(etablissement=etablissement).select_related(
            'department', 'academic_level'
        ).order_by('niveau', 'nom')
        
        # Créer les groupes de classes
        groupes_classes = {}
        for classe in classes:
            # Extraire le niveau de base (ex: "6eme" de "6eme A", "Premiere L" de "Premiere L1", etc.)
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            if match:
                groupe_nom = match.group(1)  # "6eme", "Premiere L", "Terminale S", etc.
            else:
                groupe_nom = classe.nom
            
            if groupe_nom not in groupes_classes:
                groupes_classes[groupe_nom] = {
                    'nom': groupe_nom,
                    'niveau': classe.niveau,
                    'classes': [],
                    'count': 0
                }
            
            groupes_classes[groupe_nom]['classes'].append(classe)
            groupes_classes[groupe_nom]['count'] += 1
        
        # Convertir en liste triée
        groupes_liste = sorted(groupes_classes.values(), key=lambda x: (x['niveau'], x['nom']))
        
        # Statistiques
        stats = {
            'total': matieres.count(),
            'actives': matieres.filter(actif=True).count(),
            'inactives': matieres.filter(actif=False).count(),
            'par_type': {},
            'par_niveau': {},
        }
        
        # Compter par type
        for type_matiere, label in Matiere.TYPE_MATIERE_CHOICES:
            count = matieres.filter(type_matiere=type_matiere).count()
            if count > 0:
                stats['par_type'][label] = count
        
        # Compter par niveau
        for niveau, label in Matiere.NIVEAU_CHOICES:
            count = matieres.filter(niveau=niveau).count()
            if count > 0:
                stats['par_niveau'][label] = count
        
        # Vérifier si c'est un établissement de type lycée
        est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
        # Vérifier si c'est un établissement supérieur (modules et crédits LMD)
        est_superieur = etablissement.type_etablissement == 'superieur'

        # Pour chaque matière, récupérer les coefficients par groupe (si établissement lycée)
        matieres_avec_coefficients = []
        for matiere in matieres:
            matiere_data = {
                'matiere': matiere,
                'coefficients_par_groupe': {}
            }
            
            if est_lycee:
                # Récupérer les coefficients par groupe pour cette matière
                coeffs = CoefficientMatiereGroupe.objects.filter(
                    matiere=matiere,
                    etablissement=etablissement
                )
                for coeff in coeffs:
                    matiere_data['coefficients_par_groupe'][coeff.nom_groupe] = coeff.coefficient
            
            matieres_avec_coefficients.append(matiere_data)
        
        departments = Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom') if est_superieur else []
        
        # Pour supérieur : classes et modules groupés par filière
        classes_by_department = {}
        modules_by_department = {}
        if est_superieur:
            department_ids = list(Department.objects.filter(etablissement=etablissement).values_list('id', flat=True))
            classes_superieur = Classe.objects.filter(
                etablissement=etablissement,
                department_id__in=department_ids
            ).select_related('department').order_by('department', 'niveau_lmd', 'nom')
            for classe in classes_superieur:
                dep_id = classe.department_id
                if dep_id not in classes_by_department:
                    classes_by_department[dep_id] = []
                classes_by_department[dep_id].append(classe)
            modules_list = Module.objects.filter(
                etablissement=etablissement,
                department_id__in=department_ids,
                actif=True
            ).select_related('department').prefetch_related('classes').order_by('department', 'ordre', 'nom')
            for dep_id in department_ids:
                modules_by_department[dep_id] = [m for m in modules_list if m.department_id == dep_id]
        
        form_data = {'department': '', 'module': '', 'departments_ids': [], 'modules_ids': [], 'credits': '', 'classes_ids': []}
        
        # Pour supérieur : filières -> niveaux LMD -> modules -> matières
        matieres_par_filiere = []
        if est_superieur and departments:
            matieres_par_filiere = build_matieres_par_filiere_superieur(
                matieres, departments, modules_by_department, classes_by_department
            )
        
        context = {
            'matieres': matieres,
            'matieres_avec_coefficients': matieres_avec_coefficients,
            'matieres_par_filiere': matieres_par_filiere,
            'classes': classes,
            'groupes_classes': groupes_liste,
            'etablissement': etablissement,
            'stats': stats,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'est_lycee': est_lycee,
            'est_superieur': est_superieur,
            'departments': departments,
            'classes_by_department': classes_by_department,
            'modules_by_department': modules_by_department,
            'form_data': form_data,
            'field_errors': {},
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/liste_matieres.html', context)
    
    @staticmethod
    @login_required
    def ajouter_matiere(request):
        """
        Affiche le formulaire d'ajout de matière et traite la soumission
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        form_data = {}
        field_errors = {}
        is_valid = True
        
        if request.method == 'POST':
            # Récupération automatique du niveau depuis le type_etablissement
            niveau_auto = MatiereController.get_niveau_from_type_etablissement(etablissement.type_etablissement)
            
            # Vérifier si c'est un établissement de type lycée ou supérieur
            est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
            est_superieur = etablissement.type_etablissement == 'superieur'
            
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'type_matiere': request.POST.get('type_matiere', ''),
                'coefficient': request.POST.get('coefficient', '1.0'),
                'credits': request.POST.get('credits', '').strip() or None,
                'groupes_classes': request.POST.getlist('groupes_classes', []),
                'classes_ids': [x for x in request.POST.getlist('classes_ids') if x.isdigit()],
                'departments_ids': [x for x in request.POST.getlist('departments_ids') if x.isdigit()],
                'modules_ids': [x for x in request.POST.getlist('modules_ids') if x.isdigit()],
            }
            
            # Pour les établissements lycée, récupérer les coefficients par groupe
            if est_lycee:
                coefficients_par_groupe = {}
                for groupe in form_data['groupes_classes']:
                    coeff_key = f'coefficient_{groupe}'
                    coeff_value = request.POST.get(coeff_key, form_data['coefficient'])
                    if coeff_value:
                        try:
                            coefficients_par_groupe[groupe] = float(coeff_value)
                        except ValueError:
                            coefficients_par_groupe[groupe] = float(form_data['coefficient'])
                form_data['coefficients_par_groupe'] = coefficients_par_groupe
            
            # Ajouter le niveau récupéré automatiquement
            form_data['niveau'] = niveau_auto
            
            # Validation
            is_valid = True
            
            # Champs obligatoires (niveau n'est plus requis car récupéré automatiquement)
            required_fields = ['nom', 'type_matiere']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation filières et modules obligatoires pour enseignement supérieur
            modules_objs = []
            any_module_without_credits = False
            if est_superieur:
                if not form_data['departments_ids']:
                    field_errors['departments_ids'] = "Sélectionnez au moins une filière."
                    is_valid = False
                if not form_data['modules_ids']:
                    field_errors['modules_ids'] = "Sélectionnez au moins un module."
                    is_valid = False
                else:
                    modules_objs = list(Module.objects.filter(
                        id__in=form_data['modules_ids'],
                        etablissement=etablissement,
                        department_id__in=form_data['departments_ids']
                    ).select_related('department'))
                    if len(modules_objs) != len(form_data['modules_ids']):
                        field_errors['modules_ids'] = "Un ou plusieurs modules sont invalides ou n'appartiennent pas aux filières sélectionnées."
                        is_valid = False
                    else:
                        any_module_without_credits = any(
                            m.credits is None or m.credits <= 0 for m in modules_objs
                        )
            
            # Validation du nom
            if form_data['nom'] and len(form_data['nom']) < 2:
                field_errors['nom'] = "Le nom de la matière doit contenir au moins 2 caractères."
                is_valid = False
            
            # Vérification de l'unicité du nom (selon filière et module pour supérieur - permet plusieurs "Mathématiques" dans différents modules)
            if form_data['nom'] and is_valid:
                if est_superieur and modules_objs:
                    for mod in modules_objs:
                        if Matiere.objects.filter(
                            nom__iexact=form_data['nom'],
                            etablissement=etablissement,
                            department=mod.department,
                            module=mod
                        ).exists():
                            field_errors['nom'] = f"Cette matière existe déjà dans le module '{mod.nom}'."
                            is_valid = False
                            break
                elif not est_superieur:
                    if Matiere.objects.filter(
                        nom__iexact=form_data['nom'],
                        etablissement=etablissement,
                        department__isnull=True
                    ).exists():
                        field_errors['nom'] = "Cette matière existe déjà dans cet établissement."
                        is_valid = False
            
            # Validation du coefficient (primaire/secondaire) ou crédits (supérieur)
            if est_superieur:
                if any_module_without_credits:
                    if not form_data['credits']:
                        field_errors['credits'] = "Les crédits sont obligatoires (au moins un module n'a pas de crédits définis)."
                        is_valid = False
                    else:
                        try:
                            credits_val = float(form_data['credits'])
                            if credits_val < 0:
                                field_errors['credits'] = "Les crédits doivent être positifs."
                                is_valid = False
                        except ValueError:
                            field_errors['credits'] = "Les crédits doivent être un nombre valide."
                            is_valid = False
            else:
                try:
                    coefficient = float(form_data['coefficient'])
                    if coefficient < 0 or coefficient > 10:
                        field_errors['coefficient'] = "Le coefficient doit être entre 0 et 10."
                        is_valid = False
                except ValueError:
                    field_errors['coefficient'] = "Le coefficient doit être un nombre valide."
                    is_valid = False
            
            # Validation du niveau (vérifier qu'il est valide)
            valid_niveaux = [choice[0] for choice in Matiere.NIVEAU_CHOICES]
            if form_data['niveau'] not in valid_niveaux:
                logger.error(f"Niveau invalide déterminé: '{form_data['niveau']}' depuis type_etablissement: '{etablissement.type_etablissement}'. Niveaux valides: {valid_niveaux}")
                field_errors['__all__'] = f"Erreur de niveau: Le niveau '{form_data['niveau']}' déterminé depuis le type d'établissement '{etablissement.type_etablissement}' n'est pas valide. Niveaux valides: {', '.join(valid_niveaux)}"
                is_valid = False
            
            # Si tout est valide, créer la/les matière(s)
            if is_valid:
                try:
                    with transaction.atomic():
                        if est_superieur and modules_objs:
                            # Supérieur : une matière par module sélectionné
                            matieres_creees = []
                            for mod in modules_objs:
                                credits_matiere = None
                                if mod.credits is not None and mod.credits > 0:
                                    credits_matiere = float(mod.credits)
                                elif form_data.get('credits'):
                                    try:
                                        credits_matiere = float(form_data['credits'])
                                    except (ValueError, TypeError):
                                        credits_matiere = None
                                base_code = form_data['nom'][:3].upper()
                                code = base_code
                                counter = 1
                                while Matiere.objects.filter(code=code).exists():
                                    code = f"{base_code}{counter}"
                                    counter += 1
                                    if counter > 100:
                                        code = f"{base_code}{random.randint(1000, 9999)}"
                                        break
                                matiere = Matiere(
                                    nom=form_data['nom'],
                                    code=code,
                                    type_matiere=form_data['type_matiere'],
                                    niveau=form_data['niveau'],
                                    coefficient=1.0,
                                    credits=credits_matiere,
                                    etablissement=etablissement,
                                    department=mod.department,
                                    module=mod,
                                )
                                matiere.save()
                                # Classes définies lors de la création du module
                                if mod.classes.exists():
                                    matiere.classes.set(mod.classes.all())
                                matieres_creees.append(matiere)
                            messages.success(
                                request,
                                f"{len(matieres_creees)} matière(s) '{form_data['nom']}' ajoutée(s) avec succès !"
                            )
                            items = [
                                serialize_matiere_item(m, est_superieur=True)
                                for m in matieres_creees
                            ]
                            emit_live(
                                etablissement.id,
                                'matiere.creee',
                                {'event': 'matiere.creee', 'items': items},
                            )
                            if wants_json_response(request):
                                return json_ok(
                                    message=f"{len(items)} matière(s) ajoutée(s).",
                                    items=items,
                                )
                            return redirect('matiere:liste_matieres')
                        else:
                            # Primaire / Lycée : une seule matière
                            import re
                            base_code = form_data['nom'][:3].upper()
                            code = base_code
                            counter = 1
                            while Matiere.objects.filter(code=code).exists():
                                code = f"{base_code}{counter}"
                                counter += 1
                                if counter > 100:
                                    code = f"{base_code}{random.randint(1000, 9999)}"
                                    break
                            matiere = Matiere(
                                nom=form_data['nom'],
                                code=code,
                                type_matiere=form_data['type_matiere'],
                                niveau=form_data['niveau'],
                                coefficient=float(form_data['coefficient']),
                                credits=None,
                                etablissement=etablissement,
                                department=None,
                                module=None,
                            )
                            matiere.save()
                            classes_a_assigner = []
                            for groupe in form_data['groupes_classes']:
                                classes_groupe = Classe.objects.filter(
                                    etablissement=etablissement,
                                    nom__startswith=groupe
                                )
                                classes_a_assigner.extend(list(classes_groupe))
                            classes_uniques = list(set(classes_a_assigner))
                            matiere.classes.set(classes_uniques)
                            if est_lycee and 'coefficients_par_groupe' in form_data:
                                for groupe, coefficient in form_data['coefficients_par_groupe'].items():
                                    CoefficientMatiereGroupe.objects.update_or_create(
                                        matiere=matiere,
                                        etablissement=etablissement,
                                        nom_groupe=groupe,
                                        defaults={'coefficient': coefficient}
                                    )
                            messages.success(request, f"La matière '{matiere.nom_complet}' a été ajoutée avec succès !")
                            item = serialize_matiere_item(
                                matiere,
                                est_superieur=False,
                                est_lycee=est_lycee,
                                coefficients_par_groupe=form_data.get('coefficients_par_groupe'),
                            )
                            emit_live(
                                etablissement.id,
                                'matiere.creee',
                                {'event': 'matiere.creee', 'item': item},
                            )
                            if wants_json_response(request):
                                return json_ok(message=f"Matière '{matiere.nom}' ajoutée.", item=item)
                            return redirect('matiere:liste_matieres')
                        
                except Exception as e:
                    error_message = str(e)
                    error_type = type(e).__name__
                    logger.error(f"Erreur lors de l'ajout de la matière [{error_type}]: {error_message}")
                    
                    # Détecter les types d'erreurs spécifiques
                    if 'unique constraint' in error_message.lower() or 'duplicate key' in error_message.lower() or 'UNIQUE constraint' in error_message or 'IntegrityError' in error_type:
                        if 'code' in error_message.lower():
                            field_errors['nom'] = "Une matière avec ce code existe déjà. Le code est généré automatiquement à partir des 3 premières lettres du nom."
                        elif 'nom' in error_message.lower() or 'unique_together' in error_message.lower():
                            field_errors['nom'] = "Une matière avec ce nom existe déjà dans cet établissement."
                        else:
                            field_errors['__all__'] = "Une erreur est survenue lors de l'ajout de la matière. Veuillez réessayer."
                    else:
                        field_errors['__all__'] = "Une erreur est survenue lors de l'ajout de la matière. Veuillez réessayer."
                    is_valid = False
        
        # Récupérer les classes et créer les groupes
        import re
        classes = Classe.objects.filter(etablissement=etablissement).select_related(
            'department', 'academic_level'
        ).order_by('niveau', 'nom')
        
        # Créer les groupes de classes
        groupes_classes = {}
        for classe in classes:
            # Extraire le niveau de base (ex: "6eme" de "6eme A", "Premiere L" de "Premiere L1", etc.)
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            if match:
                groupe_nom = match.group(1)  # "6eme", "Premiere L", "Terminale S", etc.
            else:
                groupe_nom = classe.nom
            
            if groupe_nom not in groupes_classes:
                groupes_classes[groupe_nom] = {
                    'nom': groupe_nom,
                    'niveau': classe.niveau,
                    'classes': [],
                    'count': 0
                }
            
            groupes_classes[groupe_nom]['classes'].append(classe)
            groupes_classes[groupe_nom]['count'] += 1
        
        # Convertir en liste triée
        groupes_liste = sorted(groupes_classes.values(), key=lambda x: (x['niveau'], x['nom']))
        
        # Vérifier si c'est un établissement de type lycée ou supérieur
        est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
        est_superieur = etablissement.type_etablissement == 'superieur'
        
        # Pour les établissements lycée, récupérer les coefficients existants par groupe (vide pour nouveau formulaire)
        coefficients_existants = {}
        
        # Contexte complet pour le template (liste_matieres.html)
        _classes_prefetch = Classe.objects.select_related('department', 'academic_level')
        matieres = Matiere.objects.filter(etablissement=etablissement).select_related(
            'department', 'module'
        ).prefetch_related(Prefetch('classes', queryset=_classes_prefetch)).order_by('nom')
        matieres_avec_coefficients = []
        for matiere in matieres:
            matiere_data = {
                'matiere': matiere,
                'coefficients_par_groupe': {}
            }
            if est_lycee:
                coeffs = CoefficientMatiereGroupe.objects.filter(
                    matiere=matiere,
                    etablissement=etablissement
                )
                for coeff in coeffs:
                    matiere_data['coefficients_par_groupe'][coeff.nom_groupe] = coeff.coefficient
            matieres_avec_coefficients.append(matiere_data)
        
        stats = {
            'total': matieres.count(),
            'actives': matieres.filter(actif=True).count(),
            'inactives': matieres.filter(actif=False).count(),
            'par_type': {},
            'par_niveau': {},
        }
        for type_matiere, label in Matiere.TYPE_MATIERE_CHOICES:
            count = matieres.filter(type_matiere=type_matiere).count()
            if count > 0:
                stats['par_type'][label] = count
        for niveau, label in Matiere.NIVEAU_CHOICES:
            count = matieres.filter(niveau=niveau).count()
            if count > 0:
                stats['par_niveau'][label] = count
        
        departments = Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom') if est_superieur else []
        
        matieres_par_filiere = []
        classes_by_department = {}
        modules_by_department = {}
        if est_superieur:
            department_ids = list(
                Department.objects.filter(etablissement=etablissement).values_list('id', flat=True)
            )
            classes_superieur = Classe.objects.filter(
                etablissement=etablissement,
                department_id__in=department_ids
            ).select_related('department').order_by('department', 'niveau_lmd', 'nom')
            for classe in classes_superieur:
                dep_id = classe.department_id
                if dep_id not in classes_by_department:
                    classes_by_department[dep_id] = []
                classes_by_department[dep_id].append(classe)
            modules_list = Module.objects.filter(
                etablissement=etablissement,
                department_id__in=department_ids,
                actif=True
            ).select_related('department').prefetch_related('classes').order_by('department', 'ordre', 'nom')
            for dep_id in department_ids:
                modules_by_department[dep_id] = [m for m in modules_list if m.department_id == dep_id]
        
        if est_superieur and departments:
            matieres_par_filiere = build_matieres_par_filiere_superieur(
                matieres, departments, modules_by_department, classes_by_department
            )
        
        # S'assurer que form_data a tous les champs pour le template
        if 'department' not in form_data:
            form_data['department'] = ''
        if 'module' not in form_data:
            form_data['module'] = ''
        if 'departments_ids' not in form_data:
            form_data['departments_ids'] = []
        if 'modules_ids' not in form_data:
            form_data['modules_ids'] = []
        if 'credits' not in form_data:
            form_data['credits'] = ''
        if 'classes_ids' not in form_data:
            form_data['classes_ids'] = []

        if request.method == 'POST' and field_errors and wants_json_response(request):
            return json_fail(field_errors=field_errors)
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'classes': classes,
            'groupes_classes': groupes_liste,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'est_lycee': est_lycee,
            'est_superieur': est_superieur,
            'coefficients_existants': coefficients_existants,
            'matieres': matieres,
            'matieres_avec_coefficients': matieres_avec_coefficients,
            'matieres_par_filiere': matieres_par_filiere,
            'stats': stats,
            'departments': departments,
            'classes_by_department': classes_by_department,
            'modules_by_department': modules_by_department,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/liste_matieres.html', context)
    
    @staticmethod
    @login_required
    def detail_matiere(request, matiere_id):
        """
        Affiche les détails d'une matière avec possibilité de modification
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        try:
            matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
            return redirect('matiere:liste_matieres')
        
        # Récupérer les professeurs associés à cette matière
        from ..model.professeur_model import Professeur
        professeurs_principaux = Professeur.objects.filter(
            matiere_principale=matiere,
            etablissement=etablissement
        ).select_related('matiere_principale')
        
        professeurs_secondaires = Professeur.objects.filter(
            matieres_secondaires=matiere,
            etablissement=etablissement
        ).select_related('matiere_principale')
        
        # Récupérer les classes associées
        classes_associees = matiere.classes.select_related(
            'department', 'academic_level'
        ).order_by('nom')
        
        # Récupérer toutes les classes pour le formulaire de modification
        toutes_classes = Classe.objects.filter(etablissement=etablissement).select_related(
            'department', 'academic_level'
        ).order_by('nom')
        
        # Créer des groupes de classes pour l'affichage
        import re
        groupes_classes = {}
        for classe in toutes_classes:
            # Extraire le niveau (ex: "6eme" de "6eme A", "5eme" de "5eme B")
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            if match:
                groupe_nom = match.group(1)  # "6eme", "5eme", etc.
            else:
                groupe_nom = classe.nom
            
            if groupe_nom not in groupes_classes:
                groupes_classes[groupe_nom] = {
                    'nom': groupe_nom,
                    'niveau': classe.niveau,
                    'classes': [],
                    'count': 0
                }
            
            groupes_classes[groupe_nom]['classes'].append(classe)
            groupes_classes[groupe_nom]['count'] += 1
        
        # Convertir en liste triée
        groupes_liste = sorted(groupes_classes.values(), key=lambda x: (x['niveau'], x['nom']))
        
        # Regrouper les classes associées par niveau
        classes_par_groupe = {}
        for classe in classes_associees:
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            if match:
                groupe_nom = match.group(1)
            else:
                groupe_nom = classe.nom
            
            if groupe_nom not in classes_par_groupe:
                classes_par_groupe[groupe_nom] = []
            classes_par_groupe[groupe_nom].append(classe)
        
        # Données du formulaire de modification
        form_data = {}
        field_errors = {}
        is_valid = True
        
        if request.method == 'POST':
            # Récupération automatique du niveau depuis le type_etablissement
            niveau_auto = MatiereController.get_niveau_from_type_etablissement(etablissement.type_etablissement)
            
            # Vérifier si c'est un établissement de type lycée ou supérieur
            est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
            est_superieur = etablissement.type_etablissement == 'superieur'
            
            # Récupération des données (utiliser 'groupes_classes' pour les groupes)
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'type_matiere': request.POST.get('type_matiere', ''),
                'coefficient': request.POST.get('coefficient', '1.0'),
                'credits': request.POST.get('credits', '').strip() or None,
                'groupes_classes': request.POST.getlist('groupes_classes', []),
                'classes_ids': [x for x in request.POST.getlist('classes_ids') if x.isdigit()],
                'department': request.POST.get('department', '').strip() or None,
                'module': request.POST.get('module', '').strip() or None,
            }
            
            # Pour les établissements lycée, récupérer les coefficients par groupe
            if est_lycee:
                coefficients_par_groupe = {}
                for groupe in form_data['groupes_classes']:
                    coeff_key = f'coefficient_{groupe}'
                    coeff_value = request.POST.get(coeff_key, form_data['coefficient'])
                    if coeff_value:
                        try:
                            coefficients_par_groupe[groupe] = float(coeff_value)
                        except ValueError:
                            coefficients_par_groupe[groupe] = float(form_data['coefficient'])
                form_data['coefficients_par_groupe'] = coefficients_par_groupe
            
            # Ajouter le niveau récupéré automatiquement
            form_data['niveau'] = niveau_auto
            
            # Validation
            is_valid = True
            
            # Champs obligatoires (niveau n'est plus requis car récupéré automatiquement)
            required_fields = ['nom', 'type_matiere']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation filière et module pour supérieur
            department_obj = None
            module_obj = None
            module_a_des_credits = False
            if est_superieur:
                if not form_data['department']:
                    field_errors['department'] = "La filière est obligatoire pour les établissements supérieurs."
                    is_valid = False
                else:
                    try:
                        department_obj = Department.objects.get(
                            id=int(form_data['department']),
                            etablissement=etablissement
                        )
                    except (ValueError, Department.DoesNotExist):
                        field_errors['department'] = "Filière invalide."
                        is_valid = False
                if not form_data['module']:
                    field_errors['module'] = "Le module est obligatoire pour les établissements supérieurs."
                    is_valid = False
                elif department_obj:
                    try:
                        module_obj = Module.objects.get(
                            id=int(form_data['module']),
                            etablissement=etablissement,
                            department=department_obj
                        )
                        module_a_des_credits = module_obj.credits is not None and module_obj.credits > 0
                    except (ValueError, Module.DoesNotExist):
                        field_errors['module'] = "Module invalide ou n'appartient pas à cette filière."
                        is_valid = False
            
            # Validation du nom
            if form_data['nom'] and len(form_data['nom']) < 2:
                field_errors['nom'] = "Le nom de la matière doit contenir au moins 2 caractères."
                is_valid = False
            
            # Vérification de l'unicité du nom (sauf pour la matière actuelle, selon module pour supérieur)
            if form_data['nom']:
                if est_superieur and department_obj and module_obj:
                    if Matiere.objects.filter(
                        nom__iexact=form_data['nom'],
                        etablissement=etablissement,
                        department=department_obj,
                        module=module_obj
                    ).exclude(id=matiere.id).exists():
                        field_errors['nom'] = "Cette matière existe déjà dans ce module."
                        is_valid = False
                elif not est_superieur:
                    if Matiere.objects.filter(
                        nom__iexact=form_data['nom'],
                        etablissement=etablissement,
                        department__isnull=True
                    ).exclude(id=matiere.id).exists():
                        field_errors['nom'] = "Cette matière existe déjà dans cet établissement."
                        is_valid = False
            
            # Validation du coefficient (primaire/secondaire) ou crédits (supérieur)
            if est_superieur:
                if not module_a_des_credits:
                    if not form_data['credits']:
                        field_errors['credits'] = "Les crédits sont obligatoires (le module n'a pas de crédits définis)."
                        is_valid = False
                    else:
                        try:
                            credits_val = float(form_data['credits'])
                            if credits_val < 0:
                                field_errors['credits'] = "Les crédits doivent être positifs."
                                is_valid = False
                        except ValueError:
                            field_errors['credits'] = "Les crédits doivent être un nombre valide."
                            is_valid = False
            else:
                try:
                    coefficient = float(form_data['coefficient'])
                    if coefficient < 0 or coefficient > 10:
                        field_errors['coefficient'] = "Le coefficient doit être entre 0 et 10."
                        is_valid = False
                except ValueError:
                    field_errors['coefficient'] = "Le coefficient doit être un nombre valide."
                    is_valid = False
            
            # Validation du niveau (vérifier qu'il est valide)
            valid_niveaux = [choice[0] for choice in Matiere.NIVEAU_CHOICES]
            if form_data['niveau'] not in valid_niveaux:
                logger.error(f"Niveau invalide déterminé: '{form_data['niveau']}' depuis type_etablissement: '{etablissement.type_etablissement}'. Niveaux valides: {valid_niveaux}")
                field_errors['__all__'] = f"Erreur de niveau: Le niveau '{form_data['niveau']}' déterminé depuis le type d'établissement '{etablissement.type_etablissement}' n'est pas valide. Niveaux valides: {', '.join(valid_niveaux)}"
                is_valid = False
            
            # Si tout est valide, modifier la matière
            if is_valid:
                try:
                    with transaction.atomic():
                        # Vérifier si le nom a changé
                        nom_ancien = matiere.nom
                        nom_nouveau = form_data['nom']
                        
                        # Si le nom a changé, générer un nouveau code unique
                        if nom_ancien != nom_nouveau:
                            base_code = nom_nouveau[:3].upper()
                            code = base_code
                            counter = 1
                            
                            # Vérifier si le code existe déjà (en excluant la matière actuelle)
                            while Matiere.objects.filter(code=code).exclude(id=matiere.id).exists():
                                code = f"{base_code}{counter}"
                                counter += 1
                                if counter > 100:  # Sécurité pour éviter une boucle infinie
                                    code = f"{base_code}{random.randint(1000, 9999)}"
                                    break
                            matiere.code = code
                        # Si le nom n'a pas changé, on garde le code actuel (pas besoin de le modifier)
                        
                        # Modifier la matière
                        credits_matiere = None
                        if est_superieur and module_obj:
                            if not module_a_des_credits and form_data.get('credits'):
                                try:
                                    credits_matiere = float(form_data['credits'])
                                except (ValueError, TypeError):
                                    credits_matiere = None
                        matiere.nom = form_data['nom']
                        matiere.type_matiere = form_data['type_matiere']
                        matiere.niveau = form_data['niveau']
                        matiere.coefficient = float(form_data['coefficient']) if not est_superieur else 1.0
                        matiere.credits = credits_matiere
                        matiere.department = department_obj if est_superieur else None
                        matiere.module = module_obj if est_superieur else None
                        matiere.save()
                        
                        # Assigner les classes selon le type d'établissement
                        if est_superieur and form_data['classes_ids']:
                            # Supérieur : classes sélectionnées par ID (filtrées par filière et niveau LMD du module)
                            classes_qs = Classe.objects.filter(
                                id__in=form_data['classes_ids'],
                                etablissement=etablissement,
                                department=department_obj
                            )
                            if module_obj and module_obj.niveau_lmd:
                                classes_qs = classes_qs.filter(niveau_lmd=module_obj.niveau_lmd)
                            matiere.classes.set(classes_qs)
                        elif form_data['groupes_classes']:
                            import re
                            classes_a_assigner = []
                            
                            for groupe in form_data['groupes_classes']:
                                # Récupérer toutes les classes de ce groupe
                                classes_groupe = Classe.objects.filter(
                                    etablissement=etablissement,
                                    nom__startswith=groupe
                                )
                                classes_a_assigner.extend(list(classes_groupe))
                            
                            # Supprimer les doublons
                            classes_uniques = list(set(classes_a_assigner))
                            matiere.classes.set(classes_uniques)
                            
                            # Pour les établissements lycée, mettre à jour les coefficients par groupe
                            if est_lycee and 'coefficients_par_groupe' in form_data:
                                # Supprimer les anciens coefficients pour les groupes non sélectionnés
                                CoefficientMatiereGroupe.objects.filter(
                                    matiere=matiere,
                                    etablissement=etablissement
                                ).exclude(nom_groupe__in=form_data['groupes_classes']).delete()
                                
                                # Créer ou mettre à jour les coefficients pour les groupes sélectionnés
                                for groupe, coefficient in form_data['coefficients_par_groupe'].items():
                                    CoefficientMatiereGroupe.objects.update_or_create(
                                        matiere=matiere,
                                        etablissement=etablissement,
                                        nom_groupe=groupe,
                                        defaults={'coefficient': coefficient}
                                    )
                        else:
                            matiere.classes.clear()
                            # Supprimer tous les coefficients par groupe si aucune classe n'est assignée
                            if est_lycee:
                                CoefficientMatiereGroupe.objects.filter(
                                    matiere=matiere,
                                    etablissement=etablissement
                                ).delete()
                        
                        messages.success(request, f"La matière '{matiere.nom_complet}' a été modifiée avec succès !")

                        coeffs = {}
                        if est_lycee:
                            for coeff in CoefficientMatiereGroupe.objects.filter(
                                matiere=matiere, etablissement=etablissement
                            ):
                                coeffs[coeff.nom_groupe] = float(coeff.coefficient)
                        item = serialize_matiere_item(
                            matiere,
                            est_superieur=est_superieur,
                            est_lycee=est_lycee,
                            coefficients_par_groupe=coeffs,
                        )
                        emit_live(
                            etablissement.id,
                            'matiere.modifiee',
                            {'event': 'matiere.modifiee', 'item': item},
                        )
                        if wants_json_response(request):
                            return json_ok(message=f"Matière '{matiere.nom}' mise à jour.", item=item)
                        return redirect('matiere:detail_matiere', matiere_id=matiere.id)
                        
                except Exception as e:
                    error_message = str(e)
                    error_type = type(e).__name__
                    logger.error(f"Erreur lors de la modification de la matière [{error_type}]: {error_message}")
                    
                    # Détecter les types d'erreurs spécifiques
                    if 'unique constraint' in error_message.lower() or 'duplicate key' in error_message.lower() or 'UNIQUE constraint' in error_message or 'IntegrityError' in error_type:
                        if 'code' in error_message.lower():
                            field_errors['nom'] = "Une matière avec ce code existe déjà. Le code est généré automatiquement à partir des 3 premières lettres du nom."
                        elif 'nom' in error_message.lower() or 'unique_together' in error_message.lower():
                            field_errors['nom'] = "Une matière avec ce nom existe déjà dans cet établissement."
                        else:
                            field_errors['__all__'] = "Une erreur est survenue lors de la modification de la matière. Veuillez réessayer."
                    else:
                        field_errors['__all__'] = "Une erreur est survenue lors de la modification de la matière. Veuillez réessayer."
                    is_valid = False

        if request.method == 'POST' and not is_valid and wants_json_response(request):
            return json_fail(
                message=field_errors.get('__all__', 'Corrigez les erreurs du formulaire.'),
                field_errors=field_errors,
            )

        if request.method != 'POST':
            # Pré-remplir le formulaire avec les données actuelles
            # Extraire les groupes de classes associées
            groupes_selectionnes = set()
            for classe in classes_associees:
                import re
                match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
                if match:
                    groupes_selectionnes.add(match.group(1))
                else:
                    groupes_selectionnes.add(classe.nom)
            
            form_data = {
                'nom': matiere.nom,
                'type_matiere': matiere.type_matiere,
                'niveau': matiere.niveau,
                'coefficient': str(matiere.coefficient),
                'credits': str(matiere.credits) if matiere.credits is not None else '',
                'groupes_classes': list(groupes_selectionnes),
                'classes_ids': [str(c.id) for c in matiere.classes.all()],
                'department': str(matiere.department_id) if matiere.department_id else '',
                'module': str(matiere.module_id) if matiere.module_id else '',
            }
        
        # Vérifier si c'est un établissement de type lycée ou supérieur
        est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée','lycee_college','mixte','lycee','college']
        est_superieur = etablissement.type_etablissement == 'superieur'
        
        # Pour les établissements lycée, récupérer les coefficients existants par groupe
        coefficients_existants = {}
        if est_lycee:
            coeffs = CoefficientMatiereGroupe.objects.filter(
                matiere=matiere,
                etablissement=etablissement
            )
            for coeff in coeffs:
                coefficients_existants[coeff.nom_groupe] = coeff.coefficient
        
        departments = Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom') if est_superieur else []
        
        # Pour supérieur : classes et modules groupés par filière (modification)
        classes_by_department = {}
        modules_by_department = {}
        if est_superieur:
            department_ids = list(Department.objects.filter(etablissement=etablissement).values_list('id', flat=True))
            classes_superieur = Classe.objects.filter(
                etablissement=etablissement,
                department_id__in=department_ids
            ).select_related('department').order_by('department', 'niveau_lmd', 'nom')
            for classe in classes_superieur:
                dep_id = classe.department_id
                if dep_id not in classes_by_department:
                    classes_by_department[dep_id] = []
                classes_by_department[dep_id].append(classe)
            modules_list = Module.objects.filter(
                etablissement=etablissement,
                department_id__in=department_ids,
                actif=True
            ).select_related('department').prefetch_related('classes').order_by('department', 'ordre', 'nom')
            for dep_id in department_ids:
                modules_by_department[dep_id] = [m for m in modules_list if m.department_id == dep_id]
        
        context = {
            'matiere': matiere,
            'professeurs_principaux': professeurs_principaux,
            'professeurs_secondaires': professeurs_secondaires,
            'classes_associees': classes_associees,
            'classes_par_groupe': classes_par_groupe,
            'toutes_classes': toutes_classes,
            'groupes_classes': groupes_liste,
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'est_lycee': est_lycee,
            'est_superieur': est_superieur,
            'departments': departments,
            'classes_by_department': classes_by_department,
            'modules_by_department': modules_by_department,
            'coefficients_existants': coefficients_existants,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/detail_matiere.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, matiere_id):
        """
        Active/désactive une matière
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        try:
            matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
            matiere.actif = not matiere.actif
            matiere.save()
            
            status = "activée" if matiere.actif else "désactivée"
            messages.success(request, f"La matière '{matiere.nom_complet}' a été {status}.")

            est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
            est_superieur = etablissement.type_etablissement == 'superieur'
            item = serialize_matiere_item(matiere, est_superieur=est_superieur, est_lycee=est_lycee)
            emit_live(
                etablissement.id,
                'matiere.modifiee',
                {'event': 'matiere.modifiee', 'item': item},
            )
            if wants_json_response(request):
                return json_ok(message=f"Matière {status}.", item=item)
            
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
            if wants_json_response(request):
                return json_fail(message="Matière non trouvée.", status=404)
        
        return redirect('matiere:liste_matieres')
    
    @staticmethod
    @login_required
    def supprimer_matiere(request, matiere_id):
        """
        Supprime une matière
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        try:
            from django.db import transaction
            from ..model.professeur_model import Professeur
            
            with transaction.atomic():
                matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
                nom_matiere = matiere.nom_complet
                
                # Vérifier s'il y a des professeurs associés
                professeurs_principaux = Professeur.objects.filter(matiere_principale=matiere, etablissement=etablissement)
                professeurs_secondaires = Professeur.objects.filter(matieres_secondaires=matiere, etablissement=etablissement)
                
                total_professeurs = professeurs_principaux.count() + professeurs_secondaires.count()
                
                if total_professeurs > 0:
                    # Retirer les associations avec les professeurs avant de supprimer
                    # Pour les professeurs avec cette matière principale, on doit leur assigner une autre matière
                    # ou les laisser sans matière principale (nécessite que le champ accepte null)
                    # Pour l'instant, on va chercher une autre matière du même établissement
                    autres_matieres = Matiere.objects.filter(etablissement=etablissement).exclude(id=matiere_id)
                    
                    if autres_matieres.exists():
                        matiere_remplacement = autres_matieres.first()
                        # Assigner une autre matière comme matière principale
                        professeurs_principaux.update(matiere_principale=matiere_remplacement)
                        messages.info(request, f"Les {professeurs_principaux.count()} professeur(s) ayant '{nom_matiere}' comme matière principale ont été réassignés à '{matiere_remplacement.nom}'.")
                    else:
                        # Si aucune autre matière n'existe, on ne peut pas supprimer
                        err_msg = f"Impossible de supprimer la matière '{nom_matiere}' car elle est la seule matière de l'établissement et {total_professeurs} professeur(s) en dépendent."
                        messages.error(request, err_msg + " Veuillez d'abord créer une autre matière ou réassigner les professeurs.")
                        if wants_json_response(request):
                            return json_fail(message=err_msg)
                        return redirect('matiere:detail_matiere', matiere_id=matiere_id)
                    
                    # Retirer la matière des matières secondaires
                    for professeur in professeurs_secondaires:
                        professeur.matieres_secondaires.remove(matiere)
                    
                    if professeurs_secondaires.exists():
                        messages.info(request, f"La matière '{nom_matiere}' a été retirée des matières secondaires de {professeurs_secondaires.count()} professeur(s).")
                
                # Supprimer la matière
                matiere_id_deleted = matiere.id
                deleted_item = {'id': matiere_id_deleted, 'nom': nom_matiere}
                matiere.delete()
                messages.success(request, f"La matière '{nom_matiere}' a été supprimée avec succès !")
                emit_live(
                    etablissement.id,
                    'matiere.supprimee',
                    {'event': 'matiere.supprimee', 'item': deleted_item},
                )
                if wants_json_response(request):
                    return json_ok(message=f"Matière '{nom_matiere}' supprimée.", item=deleted_item)
            
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
            if wants_json_response(request):
                return json_fail(message="Matière non trouvée.", status=404)
        
        return redirect('matiere:liste_matieres')
