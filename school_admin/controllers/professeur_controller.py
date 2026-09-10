# school_admin/controllers/professeur_controller.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
import logging

from ..model.professeur_model import Professeur
from ..model.etablissement_model import Etablissement

logger = logging.getLogger(__name__)

# Ordre d'affichage des niveaux LMD (formulaire professeur supérieur)
_NIVEAU_LMD_FORM_ORDER = [
    'L1', 'L2', 'L3', 'M1', 'M2', 'D1', 'D2', 'D3',
    'BTS', 'DUT', 'BUT', 'BT', 'LP', 'CERT', 'DIPL', 'AUTRE',
]

SANS_NIVEAU_MODULE_KEY = '__SANS_NIVEAU__'


def _niveau_lmd_sort_tuple(key: str):
    if key == SANS_NIVEAU_MODULE_KEY:
        return (4000, key)
    if key.startswith('AUTRE::'):
        return (3000, key)
    if key == 'AUTRE':
        return (2999, key)
    try:
        return (_NIVEAU_LMD_FORM_ORDER.index(key), key)
    except ValueError:
        return (2000, key)


def _niveaux_lmd_disponibles_pour_department(etablissement, department_id):
    """
    Niveaux LMD proposés pour une filière : niveaux des modules, des classes actives,
    et entrée « sans niveau » si des matières ont un module sans niveau renseigné.
    """
    from ..model.classe_model import Classe, libelle_cle_niveau_superieur
    from ..model.module_model import Module
    from ..model.matiere_model import Matiere

    keys_seen = {}

    mod_niveaux = (
        Module.objects.filter(
            etablissement=etablissement,
            department_id=department_id,
            actif=True,
        )
        .exclude(niveau_lmd__isnull=True)
        .exclude(niveau_lmd='')
        .values_list('niveau_lmd', flat=True)
        .distinct()
    )
    for nl in mod_niveaux:
        nk = (nl or '').strip()
        if nk == 'AUTRE':
            continue
        keys_seen[nk] = libelle_cle_niveau_superieur(nk)

    classes_qs = Classe.objects.filter(
        etablissement=etablissement,
        department_id=department_id,
        niveau='superieur',
        actif=True,
    )
    for c in classes_qs:
        nk = (c.niveau_lmd or '').strip()
        if not nk:
            continue
        if nk == 'AUTRE' and (c.niveau_libelle or '').strip():
            k = f"AUTRE::{(c.niveau_libelle or '').strip()}"
            keys_seen[k] = (c.niveau_libelle or '').strip()
        elif nk == 'AUTRE':
            keys_seen['AUTRE'] = libelle_cle_niveau_superieur('AUTRE')
        else:
            keys_seen[nk] = libelle_cle_niveau_superieur(nk)

    if Matiere.objects.filter(
        etablissement=etablissement,
        department_id=department_id,
        actif=True,
    ).filter(
        Q(module__isnull=True)
        | Q(module__niveau_lmd__isnull=True)
        | Q(module__niveau_lmd='')
    ).exists():
        keys_seen[SANS_NIVEAU_MODULE_KEY] = 'Sans niveau LMD sur le module'

    sorted_pairs = sorted(keys_seen.items(), key=lambda item: _niveau_lmd_sort_tuple(item[0]))
    return [{'key': k, 'label': v} for k, v in sorted_pairs]


def _niveau_lmd_key_from_classe_superieur(classe):
    """Clé du select « Niveau » pour une classe supérieur (identique au menu déroulant)."""
    if not classe:
        return None
    cn = (classe.niveau_lmd or '').strip()
    if not cn:
        return None
    if cn == 'AUTRE' and (classe.niveau_libelle or '').strip():
        return f"AUTRE::{(classe.niveau_libelle or '').strip()}"
    if cn == 'AUTRE':
        return 'AUTRE'
    return cn


def _niveau_lmd_keys_for_matiere_superieur(matiere):
    """
    Clés de niveau pour le formulaire professeur (strict).

    Règle principale : seules les classes de la filière où la matière est **réellement**
    rattachée (M2M ``matiere.classes``) déterminent les niveaux. Ainsi, un module commun
    L1+L2 n'affiche une matière au niveau L2 que si elle est liée à au moins une classe L2.

    Repli (aucune classe dans la filière) : niveau déclaré sur le **module** uniquement,
    jamais la liste de toutes les classes du module (évite de propager L1 aux matières L2).
    """
    dept_id = matiere.department_id
    keys = []
    seen = set()

    def add(k):
        if not k:
            return
        if k not in seen:
            seen.add(k)
            keys.append(k)

    if not dept_id:
        add(SANS_NIVEAU_MODULE_KEY)
        return keys

    classes_dept = matiere.classes.filter(
        department_id=dept_id, niveau='superieur', actif=True
    )
    for c in classes_dept:
        k = _niveau_lmd_key_from_classe_superieur(c)
        if k:
            add(k)

    if keys:
        return keys

    mod = matiere.module
    if mod:
        nk = (mod.niveau_lmd or '').strip()
        if nk == 'AUTRE':
            found_lib = False
            for mc in mod.module_classes.select_related('classe').filter(
                classe__department_id=dept_id
            ):
                c = mc.classe
                lib = (c.niveau_libelle or '').strip()
                if lib:
                    add(f'AUTRE::{lib}')
                    found_lib = True
            if not found_lib:
                add('AUTRE')
        elif nk:
            add(nk)

    if not keys:
        add(SANS_NIVEAU_MODULE_KEY)
    return keys


def _niveau_lmd_key_for_matiere_superieur(matiere):
    """Première clé (rétrocompatibilité) ; préférer _niveau_lmd_keys_for_matiere_superieur."""
    ks = _niveau_lmd_keys_for_matiere_superieur(matiere)
    return ks[0] if ks else SANS_NIVEAU_MODULE_KEY


def _matiere_conforme_department_et_niveau(matiere, department_id, niveau_key):
    if not matiere or str(matiere.department_id) != str(department_id):
        return False
    nk = (niveau_key or '').strip()
    return nk in _niveau_lmd_keys_for_matiere_superieur(matiere)


_NIVEAU_KEYS_SEP = '\x1f'  # aligné avec data-niveau-lmd-keys (JS ajouter / détail professeur)


def _build_matieres_superieur_flat(etablissement):
    """
    Liste des matières supérieur (par filière) avec clés LMD strictes, pour formulaires et modals.
    """
    from ..model.matiere_model import Matiere

    matieres_superieur_qs = (
        Matiere.objects.filter(
            etablissement=etablissement,
            department__isnull=False,
            actif=True,
        )
        .select_related('department', 'module')
        .prefetch_related('module__module_classes__classe', 'classes')
        .order_by('department__nom', 'module__nom', 'nom')
    )
    out = []
    for m in matieres_superieur_qs:
        keys_list = _niveau_lmd_keys_for_matiere_superieur(m)
        out.append(
            {
                'id': m.id,
                'nom': m.nom,
                'code': m.code or '',
                'department_id': m.department_id,
                'department_nom': m.department.nom if m.department else '',
                'module_nom': m.module.nom if m.module else '',
                'niveau_lmd_keys_list': keys_list,
                'niveau_lmd_keys_csv': _NIVEAU_KEYS_SEP.join(keys_list),
            }
        )
    return out


_DETAIL_ONGLET_LEGACY = {
    'informations': 'profil',
    'connexion': 'profil',
    'classes': 'enseignement',
    'cahier_notes': 'enseignement',
    'complementaire': 'dossier',
}


def _normalize_detail_onglet(raw):
    """Normalise les anciens identifiants d'onglet vers profil | enseignement | dossier."""
    if not raw:
        return 'profil'
    if raw in _DETAIL_ONGLET_LEGACY:
        return _DETAIL_ONGLET_LEGACY[raw]
    if raw in ('profil', 'enseignement', 'dossier'):
        return raw
    return 'profil'


def _dossier_section_from_request(request, onglet_raw):
    """Section active du dossier RH : consulter ou completer."""
    if onglet_raw == 'complementaire' or request.GET.get('section') == 'completer':
        return 'completer'
    return 'consulter'


def _enseignement_section_from_request(request, onglet_raw):
    """Sous-section Enseignement : classes ou notes."""
    if onglet_raw == 'cahier_notes' or request.GET.get('section') == 'notes' or request.GET.get('matiere'):
        return 'notes'
    return 'classes'


def _redirect_detail_professeur(professeur_id, onglet='profil', **query):
    """Redirection vers la fiche professeur avec onglet normalisé."""
    base = reverse('professeur:detail_professeur', kwargs={'professeur_id': professeur_id})
    params = {'onglet': onglet}
    params.update(query)
    qs = '&'.join(f'{k}={v}' for k, v in params.items() if v is not None)
    return redirect(f'{base}?{qs}')


def _redirect_detail_professeur_informations(professeur_id):
    """Redirection fiche professeur, onglet Profil (après POST matières secondaires, etc.)."""
    return _redirect_detail_professeur(professeur_id, 'profil')


class ProfesseurController:
    """
    Contrôleur pour gérer les professeurs
    """
    
    @staticmethod
    def generate_numero_employe(etablissement):
        """
        Génère un numéro d'employé unique pour un professeur
        """
        code_etab = etablissement.code_etablissement[:3]
        
        # Générer un numéro séquentiel
        count = Professeur.objects.filter(
            etablissement=etablissement
        ).count() + 1
        
        numero = f"PROF-{code_etab}-{count:03d}"
        
        # Vérifier l'unicité
        while Professeur.objects.filter(numero_employe=numero).exists():
            count += 1
            numero = f"PROF-{code_etab}-{count:03d}"
        
        return numero
    
    @staticmethod
    def generate_matricule_professeur(etablissement):
        """
        Génère un matricule unique pour un professeur avec des chiffres aléatoires
        Format : [XX][6 chiffres aléatoires]
        Exemple : BP482937 (Blaise Pascal, professeur avec chiffres aléatoires)
        Le matricule sera enregistré dans numero_employe
        Vérifie l'unicité dans la base de données avant de retourner
        """
        import random
        
        # Extraire les initiales de l'établissement (2 premiers mots)
        mots = etablissement.nom.split()[:2]
        initiales = ''.join([mot[0].upper() for mot in mots if mot])
        
        # Si moins de 2 mots, utiliser les 2 premières lettres du nom
        if len(initiales) < 2:
            initiales = etablissement.nom[:2].upper()
        
        # Générer un matricule avec des chiffres aléatoires
        max_tentatives = 10000  # Augmenter le nombre de tentatives pour plus de robustesse
        tentatives = 0
        
        while tentatives < max_tentatives:
            # Générer 6 chiffres aléatoires
            chiffres_aleatoires = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            matricule = f"{initiales}{chiffres_aleatoires}"
            
            # Vérifier l'unicité dans la base de données
            # Vérifier dans numero_employe (champ principal)
            if not Professeur.objects.filter(numero_employe=matricule).exists():
                # Vérifier aussi dans username pour éviter les conflits
                if not Professeur.objects.filter(username=matricule).exists():
                    return matricule
            
            tentatives += 1
        
        # Fallback avec timestamp si trop de tentatives (très rare)
        import time
        timestamp = int(time.time() * 1000) % 1000000
        matricule_fallback = f"{initiales}{timestamp:06d}"
        
        # Vérifier l'unicité du fallback
        if not Professeur.objects.filter(numero_employe=matricule_fallback).exists() and \
           not Professeur.objects.filter(username=matricule_fallback).exists():
            return matricule_fallback
        
        # Dernier recours : utiliser un UUID tronqué (6 derniers chiffres)
        import uuid
        uuid_int = abs(uuid.uuid4().int) % 1000000  # Prendre les 6 derniers chiffres
        uuid_part = f"{uuid_int:06d}"
        matricule_uuid = f"{initiales}{uuid_part}"
        
        # Vérifier une dernière fois
        if not Professeur.objects.filter(numero_employe=matricule_uuid).exists() and \
           not Professeur.objects.filter(username=matricule_uuid).exists():
            return matricule_uuid
        
        # Si vraiment aucun matricule unique n'a pu être généré (extrêmement rare)
        # Essayer une dernière fois avec un mélange timestamp + random
        import time
        final_random = random.randint(100000, 999999)
        final_timestamp = int(time.time()) % 1000000
        final_matricule = f"{initiales}{(final_random + final_timestamp) % 1000000:06d}"
        
        if not Professeur.objects.filter(numero_employe=final_matricule).exists() and \
           not Professeur.objects.filter(username=final_matricule).exists():
            return final_matricule
        
        raise ValueError(f"Impossible de générer un matricule unique pour l'établissement {etablissement.nom} après {max_tentatives} tentatives")
    
    @staticmethod
    @login_required
    def liste_professeurs(request):
        """
        Affiche la liste des professeurs de l'établissement
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
        
        # Récupérer les professeurs de l'établissement
        professeurs = Professeur.objects.filter(
            etablissement=etablissement
        ).select_related('matiere_principale').order_by('-date_creation')
        
        # Récupérer les matières avec le nombre de professeurs
        from ..model.matiere_model import Matiere
        matieres_avec_compteurs = []
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        for matiere in matieres:
            count = professeurs.filter(matiere_principale=matiere).count()
            matieres_avec_compteurs.append({
                'matiere': matiere,
                'count': count,
                'professeurs': professeurs.filter(matiere_principale=matiere)
            })
        
        # Statistiques
        stats = {
            'total': professeurs.count(),
            'actifs': professeurs.filter(actif=True).count(),
            'inactifs': professeurs.filter(actif=False).count(),
            'par_niveau': {}
        }
        
        # Compter par niveau
        for niveau, label in Professeur.NIVEAU_CHOICES:
            count = professeurs.filter(niveau_enseignement=niveau).count()
            if count > 0:
                stats['par_niveau'][label] = count
        
        context = {
            'professeurs': professeurs,
            'matieres_avec_compteurs': matieres_avec_compteurs,
            'etablissement': etablissement,
            'stats': stats,
        }
        
        return render(request, 'school_admin/directeur/personnel/professeurs/liste_professeurs.html', context)

    @staticmethod
    def build_ajouter_form_context(etablissement, form_data=None, field_errors=None, is_valid=True):
        """Contexte partagé pour le formulaire d'ajout de professeur (page ou modal)."""
        from ..model.employe_dossier_model import TYPE_CONTRAT_CHOICES
        from ..utils.employe_dossier_utils import DOSSIER_FORM_FIELDS

        if form_data is None:
            form_data = {
                'department': '',
                'niveau_lmd': '',
                'matiere_principale': '',
                'matieres_secondaires': [],
                'nom': '',
                'prenom': '',
                'email': '',
                'telephone': '',
                'sexe': '',
                'date_embauche': '',
                'prix_volume_horaire': '',
            }
            for field in DOSSIER_FORM_FIELDS:
                form_data.setdefault(field, '')
        if field_errors is None:
            field_errors = {}

        from ..model.matiere_model import Matiere
        from ..model.academic_structure_model import Department

        matieres = Matiere.objects.filter(etablissement=etablissement).select_related(
            'department', 'module'
        ).order_by('nom')

        departments = []
        matieres_superieur_flat = []
        if etablissement.type_etablissement == 'superieur':
            departments = Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
            matieres_superieur_flat = _build_matieres_superieur_flat(etablissement)

        niveaux_lmd_options_selection = []
        if etablissement.type_etablissement == 'superieur' and form_data.get('department'):
            try:
                dep_sel = int(form_data['department'])
                niveaux_lmd_options_selection = _niveaux_lmd_disponibles_pour_department(
                    etablissement, dep_sel
                )
            except (TypeError, ValueError):
                niveaux_lmd_options_selection = []

        niveaux_par_department = {}
        if etablissement.type_etablissement == 'superieur':
            for dep in departments:
                niveaux_par_department[str(dep.id)] = _niveaux_lmd_disponibles_pour_department(
                    etablissement, dep.id
                )

        return {
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'matieres': matieres,
            'departments': departments,
            'matieres_superieur_flat': matieres_superieur_flat,
            'niveaux_lmd_options_selection': niveaux_lmd_options_selection,
            'niveaux_par_department': niveaux_par_department,
            'niveau_choices': Professeur.NIVEAU_CHOICES,
            'type_etablissement': etablissement.type_etablissement,
            'est_superieur': etablissement.type_etablissement == 'superieur',
            'type_contrat_choices': TYPE_CONTRAT_CHOICES,
        }

    @staticmethod
    def build_modifier_form_context(professeur, etablissement, form_data=None, field_errors=None, is_valid=True):
        """Contexte partagé pour le formulaire de modification (page ou modal détail)."""
        from ..model.matiere_model import Matiere
        from ..model.academic_structure_model import Department
        from ..model.employe_dossier_model import TYPE_CONTRAT_CHOICES
        from ..utils.employe_dossier_utils import (
            dossier_form_data_from_dossier,
            get_or_create_dossier,
        )

        if field_errors is None:
            field_errors = {}

        dossier = get_or_create_dossier(professeur=professeur)

        if form_data is None:
            if etablissement.type_etablissement == 'primary':
                matieres_secondaires_ids = [str(m.id) for m in professeur.matieres_secondaires.all()]
                form_data = {
                    'nom': professeur.nom,
                    'prenom': professeur.prenom,
                    'email': professeur.email if professeur.email else '',
                    'telephone': professeur.telephone,
                    'sexe': professeur.sexe or '',
                    'date_embauche': (
                        professeur.date_embauche.strftime('%Y-%m-%d')
                        if professeur.date_embauche else ''
                    ),
                    'prix_volume_horaire': (
                        str(professeur.prix_volume_horaire)
                        if professeur.prix_volume_horaire is not None else ''
                    ),
                    'department': '',
                    'niveau_lmd': '',
                    'matiere_principale': '',
                    'matieres_secondaires': matieres_secondaires_ids,
                }
            elif etablissement.type_etablissement == 'superieur':
                mp = professeur.matiere_principale
                dept_s, niv_s, mp_id = '', '', ''
                if mp and mp.department_id:
                    mp_id = str(mp.id)
                    dept_s = str(mp.department_id)
                    keys_list = _niveau_lmd_keys_for_matiere_superieur(mp)
                    opts = _niveaux_lmd_disponibles_pour_department(
                        etablissement, mp.department_id
                    )
                    available_keys = {o['key'] for o in opts}
                    chosen = ''
                    for k in keys_list:
                        if k in available_keys:
                            chosen = k
                            break
                    if not chosen and keys_list:
                        chosen = keys_list[0]
                    niv_s = chosen
                form_data = {
                    'nom': professeur.nom,
                    'prenom': professeur.prenom,
                    'email': professeur.email if professeur.email else '',
                    'telephone': professeur.telephone,
                    'sexe': professeur.sexe or '',
                    'date_embauche': (
                        professeur.date_embauche.strftime('%Y-%m-%d')
                        if professeur.date_embauche else ''
                    ),
                    'prix_volume_horaire': (
                        str(professeur.prix_volume_horaire)
                        if professeur.prix_volume_horaire is not None else ''
                    ),
                    'department': dept_s,
                    'niveau_lmd': niv_s,
                    'matiere_principale': mp_id,
                    'matieres_secondaires': [],
                }
            else:
                form_data = {
                    'nom': professeur.nom,
                    'prenom': professeur.prenom,
                    'email': professeur.email if professeur.email else '',
                    'telephone': professeur.telephone,
                    'sexe': professeur.sexe or '',
                    'date_embauche': (
                        professeur.date_embauche.strftime('%Y-%m-%d')
                        if professeur.date_embauche else ''
                    ),
                    'prix_volume_horaire': (
                        str(professeur.prix_volume_horaire)
                        if professeur.prix_volume_horaire is not None else ''
                    ),
                    'department': '',
                    'niveau_lmd': '',
                    'matiere_principale': (
                        str(professeur.matiere_principale.id)
                        if professeur.matiere_principale else ''
                    ),
                    'matieres_secondaires': [],
                }
            form_data.update(dossier_form_data_from_dossier(dossier))

        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        matieres_selectionnees_ids = []
        if etablissement.type_etablissement == 'primary':
            matieres_selectionnees_ids = [str(m.id) for m in professeur.matieres_secondaires.all()]

        departments = []
        matieres_superieur_flat = []
        niveaux_par_department = {}
        niveaux_lmd_options_selection = []
        est_superieur = etablissement.type_etablissement == 'superieur'
        if est_superieur:
            departments = list(
                Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
            )
            matieres_superieur_flat = _build_matieres_superieur_flat(etablissement)
            for dep in departments:
                niveaux_par_department[str(dep.id)] = _niveaux_lmd_disponibles_pour_department(
                    etablissement, dep.id
                )
            if form_data.get('department'):
                try:
                    dep_sel = int(form_data['department'])
                    niveaux_lmd_options_selection = _niveaux_lmd_disponibles_pour_department(
                        etablissement, dep_sel
                    )
                except (TypeError, ValueError):
                    niveaux_lmd_options_selection = []

        return {
            'professeur': professeur,
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'matieres': matieres,
            'type_etablissement': etablissement.type_etablissement,
            'matieres_selectionnees_ids': matieres_selectionnees_ids,
            'est_superieur': est_superieur,
            'departments': departments,
            'matieres_superieur_flat': matieres_superieur_flat,
            'niveaux_par_department': niveaux_par_department,
            'niveaux_lmd_options_selection': niveaux_lmd_options_selection,
            'dossier': dossier,
            'type_contrat_choices': TYPE_CONTRAT_CHOICES,
        }
    
    @staticmethod
    @login_required
    def ajouter_professeur(request):
        """
        Affiche le formulaire d'ajout de professeur et traite la soumission
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
        
        form_data = {
            'department': '',
            'niveau_lmd': '',
            'matiere_principale': '',
            'matieres_secondaires': [],
        }
        field_errors = {}
        is_valid = True  # Initialiser is_valid
        
        if request.method == 'POST':
            # Fonction pour déterminer automatiquement le niveau d'enseignement selon le type d'établissement
            def get_niveau_from_etablissement(type_etablissement):
                """Mappe le type d'établissement vers le niveau d'enseignement"""
                mapping = {
                    'primary': 'primaire',
                    'collège': 'college',
                    'lycée': 'lycee',
                    'lycee': 'lycee',  # Version sans accent (base de données)
                    'collège_lycée': 'college',  # Par défaut pour collège+lycée
                    'coll�ge_lyc�e': 'college',  # Version avec caractères spéciaux
                    'mixte': 'primaire',  # Par défaut pour mixte
                    'superieur': 'superieur',
                }
                niveau = mapping.get(type_etablissement, 'primaire')
                logger.info(f"Niveau professeur déterminé: '{niveau}' pour établissement type '{type_etablissement}'")
                return niveau
            
            # Récupération des données
            # Pour le téléphone, utiliser le numéro formaté (telephone_full) s'il existe, sinon utiliser telephone
            telephone_value = request.POST.get('telephone_full', '').strip()
            if not telephone_value:
                telephone_value = request.POST.get('telephone', '').strip()
            
            from ..utils.employe_dossier_utils import dossier_form_data_from_post

            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': telephone_value,
                'sexe': request.POST.get('sexe', '').strip(),
                'date_embauche': request.POST.get('date_embauche', '').strip(),
                'prix_volume_horaire': request.POST.get('prix_volume_horaire', '').strip(),
                'department': request.POST.get('department', ''),
                'niveau_lmd': (request.POST.get('niveau_lmd') or '').strip(),
                'matiere_principale': request.POST.get('matiere_principale', ''),
                'matieres_secondaires': request.POST.getlist('matieres_secondaires', []),
            }
            form_data.update(dossier_form_data_from_post(request.POST))
            
            # Déterminer automatiquement le niveau d'enseignement
            niveau_enseignement_auto = get_niveau_from_etablissement(etablissement.type_etablissement)
            form_data['niveau_enseignement'] = niveau_enseignement_auto
            
            # Validation
            is_valid = True
            
            # Pour le supérieur : filière + matière principale (pas de matières secondaires à l'ajout)
            if etablissement.type_etablissement == 'superieur':
                required_fields = [
                    'nom', 'prenom', 'telephone', 'department', 'niveau_lmd', 'matiere_principale',
                ]
                for field in required_fields:
                    if not form_data[field]:
                        if field == 'niveau_lmd':
                            field_errors[field] = "Le niveau (Licence, Master, doctorat, etc.) est obligatoire."
                        else:
                            field_errors[field] = (
                                f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                            )
                        is_valid = False
                
                matiere_principale_obj = None
                if (
                    form_data['matiere_principale']
                    and form_data['department']
                    and form_data.get('niveau_lmd')
                ):
                    try:
                        from ..model.matiere_model import Matiere
                        matiere_principale_obj = Matiere.objects.select_related(
                            'module', 'department'
                        ).prefetch_related(
                            'module__module_classes__classe',
                        ).get(
                            id=form_data['matiere_principale'],
                            etablissement=etablissement,
                            department_id=form_data['department'],
                        )
                        if not _matiere_conforme_department_et_niveau(
                            matiere_principale_obj,
                            form_data['department'],
                            form_data['niveau_lmd'],
                        ):
                            field_errors['matiere_principale'] = (
                                "La matière ne correspond pas à la filière et au niveau choisis."
                            )
                            matiere_principale_obj = None
                            is_valid = False
                    except Matiere.DoesNotExist:
                        field_errors['matiere_principale'] = (
                            "La matière sélectionnée n'existe pas ou n'appartient pas à cette filière."
                        )
                        is_valid = False
            # Pour le primaire, on n'exige pas de matière principale
            # À la place, on exige au moins une matière secondaire
            elif etablissement.type_etablissement == 'primary':
                # Champs obligatoires pour le primaire (sans matière principale, email facultatif)
                required_fields = ['nom', 'prenom', 'telephone']
                for field in required_fields:
                    if not form_data[field]:
                        field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                        is_valid = False
                
                # Vérifier qu'au moins une matière est sélectionnée
                if not form_data['matieres_secondaires']:
                    field_errors['matieres_secondaires'] = "Veuillez sélectionner au moins une matière pour le primaire."
                    is_valid = False
                
                # Pour le primaire, la matière principale sera la première matière secondaire
                matiere_principale_obj = None
            else:
                # Champs obligatoires pour collège/lycée (email facultatif)
                required_fields = ['nom', 'prenom', 'telephone', 'matiere_principale']
                for field in required_fields:
                    if not form_data[field]:
                        field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                        is_valid = False
                
                # Validation de la matière
                matiere_principale_obj = None
                if form_data['matiere_principale']:
                    try:
                        from ..model.matiere_model import Matiere
                        matiere_principale_obj = Matiere.objects.get(id=form_data['matiere_principale'], etablissement=etablissement)
                    except Matiere.DoesNotExist:
                        field_errors['matiere_principale'] = "La matière sélectionnée n'existe pas."
                        is_valid = False

            if form_data.get('sexe') not in ('M', 'F'):
                field_errors['sexe'] = "Le sexe est obligatoire."
                is_valid = False

            from ..utils.employe_dossier_utils import parse_optional_date, parse_optional_decimal
            date_embauche_val = parse_optional_date(form_data.get('date_embauche'))
            prix_horaire_val = parse_optional_decimal(form_data.get('prix_volume_horaire'))
            if form_data.get('prix_volume_horaire') and prix_horaire_val is None:
                field_errors['prix_volume_horaire'] = "Le prix horaire n'est pas valide."
                is_valid = False
            
            # Validation de l'email (seulement si fourni)
            if form_data['email']:
                if '@' not in form_data['email']:
                    field_errors['email'] = "L'adresse email n'est pas valide."
                    is_valid = False
                # Vérification de l'unicité de l'email (seulement si fourni)
                elif Professeur.objects.filter(email=form_data['email']).exists():
                    field_errors['email'] = "Cette adresse email est déjà utilisée."
                    is_valid = False
            
            # Si tout est valide, créer le professeur
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer le matricule : initiales + 6 chiffres (sera utilisé comme numero_employe)
                        matricule = ProfesseurController.generate_matricule_professeur(etablissement)
                        
                        # Générer un mot de passe provisoire de 4 chiffres
                        import random
                        mot_de_passe_provisoire = ''.join([str(random.randint(0, 9)) for _ in range(4)])
                        
                        # Pour le primaire, si pas de matière principale, prendre la première matière secondaire
                        from ..model.matiere_model import Matiere
                        if etablissement.type_etablissement == 'primary' and not matiere_principale_obj:
                            if form_data['matieres_secondaires']:
                                matiere_principale_obj = Matiere.objects.get(id=form_data['matieres_secondaires'][0])
                        
                        # Créer le professeur
                        # Gérer l'email : utiliser None si vide, sinon utiliser la valeur
                        email_value = form_data['email'] if form_data['email'] else None
                        
                        professeur = Professeur(
                            nom=form_data['nom'],
                            prenom=form_data['prenom'],
                            sexe=form_data['sexe'],
                            email=email_value,  # Peut être None si non fourni
                            telephone=form_data['telephone'],
                            date_embauche=date_embauche_val,
                            prix_volume_horaire=prix_horaire_val,
                            matiere_principale=matiere_principale_obj,
                            niveau_enseignement=form_data['niveau_enseignement'],
                            numero_employe=matricule,  # Le matricule est enregistré dans numero_employe
                            etablissement=etablissement,
                            mot_de_passe_provisoire=mot_de_passe_provisoire,
                        )
                        
                        # Définir le username avec le matricule pour compatibilité
                        professeur.username = matricule
                        
                        # Définir le mot de passe provisoire hashé
                        professeur.set_password(mot_de_passe_provisoire)
                        professeur.save()

                        from ..utils.employe_dossier_utils import (
                            save_documents_from_request,
                            save_dossier_from_post_if_any,
                        )
                        save_dossier_from_post_if_any(professeur=professeur, post_data=request.POST)
                        save_documents_from_request(request, professeur=professeur)
                        
                        # Matières secondaires (primaire / collège-lycée uniquement — pas pour le supérieur)
                        if (
                            form_data['matieres_secondaires']
                            and etablissement.type_etablissement != 'superieur'
                        ):
                            matieres_secondaires_qs = Matiere.objects.filter(
                                id__in=form_data['matieres_secondaires'],
                                etablissement=etablissement
                            )
                            professeur.matieres_secondaires.set(matieres_secondaires_qs)
                        
                        from ..services.realtime_helpers import wants_json_response, json_ok, emit_live
                        from ..services.live_serializers import serialize_professeur_liste_item

                        success_message = (
                            f"Le professeur {professeur.nom_complet} a été ajouté avec succès ! "
                            f"Mot de passe provisoire : {mot_de_passe_provisoire}"
                        )
                        item = serialize_professeur_liste_item(professeur)
                        emit_live(
                            etablissement.id,
                            'professeur.cree',
                            {'event': 'professeur.cree', 'item': item},
                        )
                        if wants_json_response(request):
                            return json_ok(message=success_message, item=item)

                        messages.success(request, success_message)
                        return redirect('professeur:detail_professeur', professeur_id=professeur.id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout du professeur: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de l'ajout du professeur."
                    is_valid = False
        
        from ..services.realtime_helpers import wants_json_response, json_fail

        if request.method == 'POST' and not is_valid and wants_json_response(request):
            return json_fail(field_errors=field_errors)

        context = ProfesseurController.build_ajouter_form_context(
            etablissement,
            form_data=form_data,
            field_errors=field_errors,
            is_valid=is_valid,
        )
        
        return render(request, 'school_admin/directeur/personnel/professeurs/ajouter_professeur.html', context)
    
    @staticmethod
    @login_required
    def detail_professeur(request, professeur_id):
        """
        Affiche les détails d'un professeur
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
            professeur = Professeur.objects.select_related(
                'matiere_principale',
                'etablissement'
            ).prefetch_related(
                'matieres_secondaires',
                'classes',
                'classes__eleves'
            ).get(
                id=professeur_id,
                etablissement=etablissement
            )
        except Professeur.DoesNotExist:
            messages.error(request, "Professeur non trouvé.")
            return redirect('professeur:liste_professeurs')
        
        # Récupérer les classes affectées avec leurs informations
        classes_affectees = professeur.classes.all().order_by('nom')
        
        # Onglet principal (profil | enseignement | dossier)
        onglet_raw = request.GET.get('onglet', 'profil')
        onglet_actif = _normalize_detail_onglet(onglet_raw)
        dossier_section = _dossier_section_from_request(request, onglet_raw)
        enseignement_section = _enseignement_section_from_request(request, onglet_raw)
        
        # Gérer l'ajout/suppression de matières secondaires (POST)
        if request.method == 'POST':
            action = request.POST.get('action')

            if action == 'update_dossier':
                from ..utils.employe_dossier_utils import get_or_create_dossier, update_dossier_from_post
                dossier = get_or_create_dossier(professeur=professeur)
                update_dossier_from_post(dossier, request.POST)
                messages.success(request, "Les informations complémentaires ont été enregistrées.")
                return _redirect_detail_professeur(professeur.id, 'dossier', section='completer')

            if action == 'ajouter_documents':
                from ..utils.employe_dossier_utils import save_documents_from_request
                docs = save_documents_from_request(request, professeur=professeur)
                if docs:
                    messages.success(request, f"{len(docs)} document(s) ajouté(s) au dossier.")
                else:
                    messages.info(request, "Aucun fichier sélectionné.")
                return _redirect_detail_professeur(professeur.id, 'dossier', section='completer')
            
            if action == 'ajouter_matiere_secondaire':
                matiere_id = request.POST.get('matiere_id', '').strip()
                department_post = request.POST.get('department', '').strip()
                niveau_lmd_post = (request.POST.get('niveau_lmd') or '').strip()

                def _finalize_add_matiere_secondaire(matiere_obj):
                    if matiere_obj in professeur.matieres_secondaires.all():
                        messages.warning(
                            request,
                            "Cette matière est déjà dans les matières secondaires.",
                        )
                    elif professeur.matiere_principale == matiere_obj:
                        messages.warning(
                            request,
                            "Cette matière est déjà la matière principale.",
                        )
                    else:
                        professeur.matieres_secondaires.add(matiere_obj)
                        messages.success(
                            request,
                            f"Matière « {matiere_obj.nom} » ajoutée avec succès.",
                        )

                if not matiere_id:
                    messages.warning(request, "Veuillez sélectionner une matière à ajouter.")
                else:
                    try:
                        from ..model.matiere_model import Matiere
                        from ..model.academic_structure_model import Department

                        if etablissement.type_etablissement == 'superieur':
                            if not department_post:
                                messages.error(request, "Veuillez sélectionner une filière.")
                            elif not niveau_lmd_post:
                                messages.error(
                                    request,
                                    "Veuillez sélectionner le niveau (L1, L2, M1…) correspondant à la matière.",
                                )
                            elif not Department.objects.filter(
                                id=department_post,
                                etablissement=etablissement,
                            ).exists():
                                messages.error(request, "Filière invalide pour cet établissement.")
                            else:
                                matiere = Matiere.objects.select_related(
                                    'department', 'module'
                                ).prefetch_related(
                                    'module__module_classes__classe',
                                    'classes',
                                ).get(
                                    id=matiere_id,
                                    etablissement=etablissement,
                                    department_id=department_post,
                                    actif=True,
                                )
                                if not _matiere_conforme_department_et_niveau(
                                    matiere,
                                    department_post,
                                    niveau_lmd_post,
                                ):
                                    messages.error(
                                        request,
                                        "Cette matière ne correspond pas à la filière et au niveau choisis.",
                                    )
                                else:
                                    _finalize_add_matiere_secondaire(matiere)
                        else:
                            matiere = Matiere.objects.select_related('department', 'module').get(
                                id=matiere_id,
                                etablissement=etablissement,
                                actif=True,
                            )
                            _finalize_add_matiere_secondaire(matiere)
                    except Matiere.DoesNotExist:
                        messages.error(
                            request,
                            "Matière introuvable, inactive ou ne correspond pas à la filière choisie.",
                        )
                    except ValueError:
                        messages.error(request, "Identifiant de matière ou de filière invalide.")

                return _redirect_detail_professeur_informations(professeur.id)

            elif action == 'retirer_matiere_secondaire':
                matiere_id = request.POST.get('matiere_id')
                if matiere_id:
                    try:
                        from ..model.matiere_model import Matiere
                        matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
                        professeur.matieres_secondaires.remove(matiere)
                        messages.success(request, f"Matière « {matiere.nom} » retirée avec succès.")
                    except Matiere.DoesNotExist:
                        messages.error(request, "Matière non trouvée.")

                return _redirect_detail_professeur_informations(professeur.id)
        
        # Pour les enseignants primaires, récupérer les affectations et les données de notes
        affectations_primaire = []
        cahier_notes_data = []
        
        if etablissement.type_etablissement == 'primary':
            from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
            from ..model.periode_model import PeriodeScolaire
            from ..model.note_primaire_model import MoyenneMatierePrimaire
            
            # Récupérer les affectations primaires
            affectations_primaire = AffectationProfesseurPrimaire.objects.filter(
                professeur=professeur,
                actif=True
            ).select_related('classe').prefetch_related('matieres').order_by('classe__nom')
            
            # Récupérer la période active
            periodes = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True
            ).order_by('date_debut')
            
            periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
            
            # Pour chaque affectation, récupérer les moyennes par matière
            if periode_selectionnee:
                from ..model.evaluation_primaire_model import EvaluationPrimaire
                from ..model.note_primaire_model import NotePrimaire
                
                # Récupérer la matière sélectionnée dans le sous-onglet
                matiere_selectionnee_id = request.GET.get('matiere')
                
                for affectation in affectations_primaire:
                    matieres_info = []
                    
                    for matiere in affectation.matieres.all():
                        # Récupérer les évaluations normales pour cette matière
                        evaluations_list = list(EvaluationPrimaire.objects.filter(
                            classe=affectation.classe,
                            professeur=professeur,
                            matiere=matiere,
                            periode_scolaire=periode_selectionnee,
                            actif=True
                        ).order_by('date_evaluation'))
                        
                        # Récupérer aussi les créneaux d'examens
                        from ..model.creneau_examen_model import CreneauExamen
                        creneaux_examens_list = list(CreneauExamen.objects.filter(
                            session_examen__classes=affectation.classe,
                            session_examen__periode=periode_selectionnee,
                            matiere=matiere,
                            actif=True
                        ).select_related('session_examen').order_by('date_examen'))
                        
                        # Ajouter des numéros pour devoirs, interrogations et examens
                        compteur_devoirs = 0
                        compteur_interrogations = 0
                        compteur_examens = 0
                        evaluations_data = []
                        
                        # Traiter les évaluations normales
                        for eval in evaluations_list:
                            eval_dict = {
                                'obj': eval,
                                'id': eval.id,
                                'titre': eval.titre,
                                'bareme': eval.bareme,
                                'date_evaluation': eval.date_evaluation,
                                'est_examen': False
                            }
                            
                            if eval.bareme == 20:
                                compteur_devoirs += 1
                                eval_dict['type_label'] = f'Devoir {compteur_devoirs}'
                            else:
                                compteur_interrogations += 1
                                eval_dict['type_label'] = f'Interrogation {compteur_interrogations}'
                            
                            evaluations_data.append(eval_dict)
                        
                        # Traiter les examens
                        for creneau in creneaux_examens_list:
                            compteur_examens += 1
                            evaluations_data.append({
                                'obj': creneau,
                                'id': f'examen_{creneau.id}',
                                'creneau_id': creneau.id,
                                'titre': creneau.session_examen.nom_examen,
                                'bareme': 20,
                                'date_evaluation': creneau.date_examen,
                                'est_examen': True,
                                'type_label': f'Examen {compteur_examens}'
                            })
                        
                        # Récupérer les moyennes
                        moyennes_list = MoyenneMatierePrimaire.objects.filter(
                            classe=affectation.classe,
                            matiere=matiere,
                            periode_scolaire=periode_selectionnee
                        ).select_related('eleve').order_by('-moyenne')
                        
                        # Si cette matière est sélectionnée, récupérer aussi les notes détaillées
                        notes_detaillees = []
                        evaluations_utilisees = []  # Liste des évaluations qui ont des notes
                        
                        if str(matiere.id) == matiere_selectionnee_id:
                            from ..model.eleve_model import Eleve
                            eleves = Eleve.objects.filter(
                                classe=affectation.classe,
                                actif=True
                            ).order_by('nom', 'prenom')
                            
                            # Identifier les évaluations qui ont au moins une note saisie
                            evals_avec_notes = set()
                            
                            for eleve in eleves:
                                # Récupérer la moyenne
                                moyenne_obj = moyennes_list.filter(eleve=eleve).first()
                                
                                # Récupérer les notes pour chaque évaluation (normales + examens)
                                from ..model.note_examen_model import NoteExamen
                                
                                notes_evaluations = {}
                                for eval_dict in evaluations_data:
                                    # Si c'est un examen, chercher dans NoteExamen
                                    if eval_dict.get('est_examen'):
                                        note_obj = NoteExamen.objects.filter(
                                            eleve=eleve,
                                            creneau_examen_id=eval_dict['creneau_id'],
                                            matiere=matiere,
                                            retenue=True  # ✅ Ne prendre que les notes retenues
                                        ).first()
                                    else:
                                        # Sinon, chercher dans NotePrimaire
                                        note_obj = NotePrimaire.objects.filter(
                                            eleve=eleve,
                                            evaluation_primaire_id=eval_dict['id'],
                                            retenue=True  # ✅ Ne prendre que les notes retenues
                                        ).first()
                                    
                                    # Si la note retenue existe, inclure cette évaluation
                                    if note_obj:
                                        evals_avec_notes.add(eval_dict['id'])
                                    
                                    # Calculer la couleur
                                    if note_obj and note_obj.note is not None and not note_obj.absent:
                                        note_sur_20 = (float(note_obj.note) / float(eval_dict['bareme'])) * 20
                                        
                                        if note_sur_20 >= 16:
                                            couleur = '#10b981'
                                        elif note_sur_20 >= 14:
                                            couleur = '#3b82f6'
                                        elif note_sur_20 >= 12:
                                            couleur = '#8b5cf6'
                                        elif note_sur_20 >= 10:
                                            couleur = '#f59e0b'
                                        elif note_sur_20 >= 8:
                                            couleur = '#f97316'
                                        else:
                                            couleur = '#ef4444'
                                        
                                        notes_evaluations[eval_dict['id']] = {
                                            'note_obj': note_obj,
                                            'couleur': couleur
                                        }
                                    else:
                                        notes_evaluations[eval_dict['id']] = {
                                            'note_obj': note_obj,
                                            'couleur': None
                                        }
                                
                                notes_detaillees.append({
                                    'eleve': eleve,
                                    'moyenne': moyenne_obj.moyenne if moyenne_obj else None,
                                    'appreciation': moyenne_obj.appreciation if moyenne_obj else None,
                                    'notes_evaluations': notes_evaluations
                                })
                            
                            # Filtrer evaluations_data pour ne garder que celles avec des notes
                            evaluations_utilisees = [e for e in evaluations_data if e['id'] in evals_avec_notes]
                        
                        matieres_info.append({
                            'matiere': matiere,
                            'moyennes': moyennes_list,
                            'nombre_moyennes': moyennes_list.count(),
                            'evaluations': evaluations_utilisees if evaluations_utilisees else evaluations_data,
                            'notes_detaillees': notes_detaillees,
                            'est_selectionnee': str(matiere.id) == matiere_selectionnee_id
                        })
                    
                    cahier_notes_data.append({
                        'classe': affectation.classe,
                        'matieres_info': matieres_info
                    })
        
        # Matières encore ajoutables comme secondaires (modal)
        from ..model.matiere_model import Matiere
        from ..model.academic_structure_model import Department

        md_qs = Matiere.objects.filter(etablissement=etablissement, actif=True).select_related(
            'department', 'module'
        )
        secondary_ids = list(professeur.matieres_secondaires.values_list('id', flat=True))
        if secondary_ids:
            md_qs = md_qs.exclude(id__in=secondary_ids)
        if professeur.matiere_principale_id:
            md_qs = md_qs.exclude(id=professeur.matiere_principale_id)

        modal_superieur_departments = []
        modal_superieur_matieres_flat = []
        modal_niveaux_par_department = {}
        matieres_disponibles = Matiere.objects.none()

        if etablissement.type_etablissement == 'superieur':
            modal_superieur_departments = list(
                Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
            )
            for dep in modal_superieur_departments:
                modal_niveaux_par_department[str(dep.id)] = _niveaux_lmd_disponibles_pour_department(
                    etablissement, dep.id
                )
            excluded_ids = set(secondary_ids)
            if professeur.matiere_principale_id:
                excluded_ids.add(professeur.matiere_principale_id)
            full_flat = _build_matieres_superieur_flat(etablissement)
            modal_superieur_matieres_flat = [row for row in full_flat if row['id'] not in excluded_ids]
        else:
            matieres_disponibles = md_qs.order_by('nom')

        from ..model.employe_dossier_model import TYPE_CONTRAT_CHOICES
        from ..utils.employe_dossier_utils import (
            dossier_form_data_from_dossier,
            get_or_create_dossier,
            get_documents_for_employe,
            get_sexe_display,
        )
        dossier = get_or_create_dossier(professeur=professeur)
        documents = get_documents_for_employe(professeur=professeur)

        modifier_field_errors = request.session.pop('modifier_prof_errors', {})
        modifier_form_data = request.session.pop('modifier_prof_form', None)
        show_modifier_modal = request.GET.get('modifier') == '1' or bool(modifier_field_errors)

        modifier_ctx = ProfesseurController.build_modifier_form_context(
            professeur,
            etablissement,
            form_data=modifier_form_data,
            field_errors=modifier_field_errors,
            is_valid=not modifier_field_errors,
        )

        context = {
            'professeur': professeur,
            'etablissement': etablissement,
            'classes_affectees': classes_affectees,
            'affectations_primaire': affectations_primaire,
            'onglet_actif': onglet_actif,
            'dossier_section': dossier_section,
            'enseignement_section': enseignement_section,
            'cahier_notes_data': cahier_notes_data,
            'matieres_disponibles': matieres_disponibles,
            'modal_superieur_departments': modal_superieur_departments,
            'modal_superieur_matieres_flat': modal_superieur_matieres_flat,
            'modal_niveaux_par_department': modal_niveaux_par_department,
            'dossier': dossier,
            'documents': documents,
            'sexe_display': get_sexe_display(professeur.sexe),
            'type_contrat_choices': TYPE_CONTRAT_CHOICES,
            'document_download_url_name': 'professeur:telecharger_document',
            'show_modifier_modal': show_modifier_modal,
            'employe': professeur,
            'dossier_form_data': dossier_form_data_from_dossier(dossier) if dossier else {},
        }
        context.update(modifier_ctx)

        return render(
            request,
            'school_admin/directeur/personnel/professeurs/detail_professeur.html',
            context,
        )
    
    @staticmethod
    @login_required
    def toggle_actif(request, professeur_id):
        """
        Active/désactive un professeur
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
            professeur = Professeur.objects.get(
                id=professeur_id,
                etablissement=etablissement
            )
            
            professeur.actif = not professeur.actif
            professeur.save()
            
            status = "activé" if professeur.actif else "désactivé"
            messages.success(request, f"{professeur.nom_complet} a été {status}.")
            
        except Professeur.DoesNotExist:
            messages.error(request, "Professeur non trouvé.")
        
        return redirect('professeur:detail_professeur', professeur_id=professeur_id)

    @staticmethod
    @login_required
    def telecharger_document(request, document_id):
        """Affiche ou télécharge un document du dossier professeur."""
        from django.http import FileResponse, Http404
        from ..model.employe_dossier_model import DocumentEmploye

        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')

        try:
            document = DocumentEmploye.objects.select_related('professeur').get(
                id=document_id,
                professeur__etablissement=etablissement,
            )
        except DocumentEmploye.DoesNotExist:
            raise Http404("Document introuvable.")

        response = FileResponse(document.fichier.open('rb'), as_attachment=bool(request.GET.get('download')))
        response['Content-Disposition'] = (
            f'attachment; filename="{document.nom_fichier}"'
            if request.GET.get('download')
            else f'inline; filename="{document.nom_fichier}"'
        )
        return response
    
    @staticmethod
    @login_required
    def modifier_professeur(request, professeur_id):
        """
        Modifie les informations d'un professeur
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
            professeur = Professeur.objects.select_related(
                'matiere_principale',
                'etablissement'
            ).prefetch_related(
                'matieres_secondaires',
                'classes'
            ).get(
                id=professeur_id,
                etablissement=etablissement
            )
        except Professeur.DoesNotExist:
            messages.error(request, "Professeur non trouvé.")
            return redirect('professeur:liste_professeurs')
        
        # Fonction pour déterminer le niveau d'enseignement en fonction du type d'établissement
        def get_niveau_from_type_etablissement(type_etablissement):
            """Détermine le niveau d'enseignement en fonction du type d'établissement"""
            type_etablissement_str = str(type_etablissement)
            
            # Mapping direct pour éviter les problèmes d'encodage
            mapping = {
                'primary': 'primaire',
                'primaire': 'primaire',
                'collège': 'college',
                'college': 'college',
                'lycée': 'lycee',
                'lycee': 'lycee',
                'collège_lycée': 'lycee',  # Par défaut pour collège+lycée
                'college_lycee': 'lycee',
                'lycee_college': 'lycee',
                'collège_lycée': 'lycee',  # Version avec caractères spéciaux
                'mixte': 'primaire',  # Par défaut pour mixte
                'superieur': 'superieur',
            }
            
            niveau = mapping.get(type_etablissement_str, 'primaire')
            logger.info(f"Niveau professeur (modification) déterminé: '{niveau}' pour établissement type '{type_etablissement_str}'")
            return niveau
        
        form_data = {}
        field_errors = {}
        is_valid = True
        
        if request.method == 'POST':
            # Récupération des données
            # Pour le téléphone, utiliser le numéro formaté (telephone_full) s'il existe, sinon utiliser telephone
            telephone_value = request.POST.get('telephone_full', '').strip()
            if not telephone_value:
                telephone_value = request.POST.get('telephone', '').strip()
            
            from ..utils.employe_dossier_utils import dossier_form_data_from_post

            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': telephone_value,
                'sexe': request.POST.get('sexe', '').strip(),
                'date_embauche': request.POST.get('date_embauche', '').strip(),
                'prix_volume_horaire': request.POST.get('prix_volume_horaire', '').strip(),
                'department': request.POST.get('department', ''),
                'niveau_lmd': (request.POST.get('niveau_lmd') or '').strip(),
                'matiere_principale': request.POST.get('matiere_principale', ''),
                'matieres_secondaires': request.POST.getlist('matieres_secondaires', []),
            }
            form_data.update(dossier_form_data_from_post(request.POST))
            from_detail = request.POST.get('from_detail') == '1'
            
            # Déterminer automatiquement le niveau d'enseignement en fonction du type d'établissement
            niveau_enseignement = get_niveau_from_type_etablissement(etablissement.type_etablissement)
            
            # Validation
            is_valid = True
            
            # Pour le primaire, on n'exige pas de matière principale
            # À la place, on exige au moins une matière secondaire
            if etablissement.type_etablissement == 'primary':
                # Champs obligatoires pour le primaire (sans matière principale, email facultatif)
                required_fields = ['nom', 'prenom', 'telephone']
                for field in required_fields:
                    if not form_data[field]:
                        field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                        is_valid = False
                
                # Vérifier qu'au moins une matière est sélectionnée
                if not form_data['matieres_secondaires']:
                    field_errors['matieres_secondaires'] = "Veuillez sélectionner au moins une matière pour le primaire."
                    is_valid = False
                
                # Pour le primaire, la matière principale sera la première matière secondaire
                matiere_principale_obj = None
            elif etablissement.type_etablissement == 'superieur':
                required_fields = [
                    'nom', 'prenom', 'telephone', 'department', 'niveau_lmd', 'matiere_principale',
                ]
                for field in required_fields:
                    if not form_data.get(field):
                        if field == 'niveau_lmd':
                            field_errors[field] = (
                                "Le niveau (Licence, Master, doctorat, etc.) est obligatoire."
                            )
                        elif field == 'department':
                            field_errors[field] = "La filière est obligatoire."
                        else:
                            field_errors[field] = (
                                f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                            )
                        is_valid = False
                matiere_principale_obj = None
                if (
                    form_data['matiere_principale']
                    and form_data['department']
                    and form_data.get('niveau_lmd')
                ):
                    try:
                        from ..model.matiere_model import Matiere
                        matiere_principale_obj = Matiere.objects.select_related(
                            'module', 'department'
                        ).prefetch_related(
                            'module__module_classes__classe',
                            'classes',
                        ).get(
                            id=form_data['matiere_principale'],
                            etablissement=etablissement,
                            department_id=form_data['department'],
                        )
                        if not _matiere_conforme_department_et_niveau(
                            matiere_principale_obj,
                            form_data['department'],
                            form_data['niveau_lmd'],
                        ):
                            field_errors['matiere_principale'] = (
                                "La matière ne correspond pas à la filière et au niveau choisis."
                            )
                            matiere_principale_obj = None
                            is_valid = False
                    except Matiere.DoesNotExist:
                        field_errors['matiere_principale'] = (
                            "La matière sélectionnée n'existe pas ou n'appartient pas à cette filière."
                        )
                        is_valid = False
            else:
                # Champs obligatoires pour collège/lycée (email facultatif)
                required_fields = ['nom', 'prenom', 'telephone', 'matiere_principale']
                for field in required_fields:
                    if not form_data[field]:
                        field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                        is_valid = False
                
                # Validation de la matière principale
                matiere_principale_obj = None
                if form_data['matiere_principale']:
                    try:
                        from ..model.matiere_model import Matiere
                        matiere_principale_obj = Matiere.objects.get(
                            id=form_data['matiere_principale'], etablissement=etablissement
                        )
                    except Matiere.DoesNotExist:
                        field_errors['matiere_principale'] = "La matière sélectionnée n'existe pas."
                        is_valid = False
            
            if form_data.get('sexe') not in ('M', 'F'):
                field_errors['sexe'] = "Le sexe est obligatoire."
                is_valid = False

            from ..utils.employe_dossier_utils import parse_optional_date, parse_optional_decimal
            date_embauche_val = parse_optional_date(form_data.get('date_embauche'))
            prix_horaire_val = parse_optional_decimal(form_data.get('prix_volume_horaire'))
            if form_data.get('prix_volume_horaire') and prix_horaire_val is None:
                field_errors['prix_volume_horaire'] = "Le prix horaire n'est pas valide."
                is_valid = False

            # Validation de l'email (seulement si fourni)
            if form_data['email']:
                if '@' not in form_data['email']:
                    field_errors['email'] = "L'adresse email n'est pas valide."
                    is_valid = False
                # Vérification de l'unicité de l'email (sauf si c'est le même)
                elif form_data['email'] != professeur.email:
                    if Professeur.objects.filter(email=form_data['email']).exists():
                        field_errors['email'] = "Cette adresse email est déjà utilisée."
                        is_valid = False
            
            # Si tout est valide, mettre à jour le professeur
            if is_valid:
                try:
                    with transaction.atomic():
                        from ..model.matiere_model import Matiere
                        
                        # Pour le primaire, si pas de matière principale, prendre la première matière secondaire
                        if etablissement.type_etablissement == 'primary' and not matiere_principale_obj:
                            if form_data['matieres_secondaires']:
                                matiere_principale_obj = Matiere.objects.get(id=form_data['matieres_secondaires'][0], etablissement=etablissement)
                        
                        # Gérer l'email : utiliser None si vide, sinon utiliser la valeur
                        email_value = form_data['email'] if form_data['email'] else None
                        
                        professeur.nom = form_data['nom']
                        professeur.prenom = form_data['prenom']
                        professeur.email = email_value  # Peut être None si non fourni
                        professeur.telephone = form_data['telephone']
                        professeur.sexe = form_data['sexe']
                        professeur.date_embauche = date_embauche_val
                        professeur.prix_volume_horaire = prix_horaire_val
                        professeur.matiere_principale = matiere_principale_obj
                        # Définir automatiquement le niveau d'enseignement
                        professeur.niveau_enseignement = niveau_enseignement
                        
                        # Le username doit toujours être le matricule (numero_employe), jamais l'email
                        # Cela garantit que l'identifiant de connexion reste le matricule
                        professeur.username = professeur.numero_employe
                        
                        professeur.save()
                        
                        # Gérer les matières secondaires
                        if etablissement.type_etablissement == 'primary':
                            # Pour le primaire, enregistrer toutes les matières secondaires
                            if form_data['matieres_secondaires']:
                                matieres_secondaires_objs = Matiere.objects.filter(
                                    id__in=form_data['matieres_secondaires'],
                                    etablissement=etablissement
                                )
                                professeur.matieres_secondaires.set(matieres_secondaires_objs)
                            else:
                                professeur.matieres_secondaires.clear()
                        else:
                            # Collège / lycée / supérieur : pas de matières secondaires via ce formulaire
                            professeur.matieres_secondaires.clear()

                        from ..utils.employe_dossier_utils import (
                            get_or_create_dossier,
                            update_dossier_from_post,
                        )
                        dossier = get_or_create_dossier(professeur=professeur)
                        update_dossier_from_post(dossier, request.POST)
                        
                        messages.success(request, f"Les informations de {professeur.nom_complet} ont été mises à jour avec succès !")
                        return redirect('professeur:detail_professeur', professeur_id=professeur.id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de la modification du professeur: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de la modification du professeur."
                    is_valid = False

            if not is_valid and from_detail:
                request.session['modifier_prof_errors'] = field_errors
                request.session['modifier_prof_form'] = form_data
                return redirect(
                    f"{reverse('professeur:detail_professeur', args=[professeur.id])}?modifier=1"
                )
        
        context = ProfesseurController.build_modifier_form_context(
            professeur,
            etablissement,
            form_data=form_data if form_data else None,
            field_errors=field_errors,
            is_valid=is_valid,
        )
        
        return render(request, 'school_admin/directeur/personnel/professeurs/modifier_professeur.html', context)
