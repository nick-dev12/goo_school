import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date
from django_countries import countries
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.etablissement_model import Etablissement
from ..model.classe_model import Classe
from ..model.academic_structure_model import Department
from ..model.eleve_model import Eleve
from ..model.inscription_eleve_model import InscriptionEleve
from ..model.inscription_parent_model import InscriptionParent
from ..model.facturation_model import Facturation
from ..model.ponderation_model import Ponderation
from ..utils.session_utils import get_session_active, get_session_consultee
from ..utils.formatting_utils import formater_nom, formater_prenom


def _build_classes_grouped_data(etablissement, annee_scolaire_active=None):
    """
    Construit la structure regroupant les classes et les élèves avec statistiques.
    Si annee_scolaire_active est fournie, filtre les élèves par année scolaire.
    """
    from collections import OrderedDict
    from school_admin.model.presence_model import Presence
    from school_admin.model.sanction_model import Sanction
    import re

    classes = (
        Classe.objects.filter(etablissement=etablissement, actif=True)
        .select_related('department', 'academic_level')
        .order_by('niveau', 'nom')
    )

    classes_grouped = OrderedDict()
    total_eleves = 0
    total_capacite = 0

    for classe in classes:
        nom = classe.nom
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom.strip())

        if match:
            raw_categorie = match.group(1)
        else:
            raw_categorie = nom

        categorie_label = re.sub(r'[\s\-_/]+$', '', raw_categorie).strip()
        if not categorie_label:
            categorie_label = raw_categorie.strip() or nom.strip()

        categorie_key = categorie_label.lower()

        if categorie_key not in classes_grouped:
            classes_grouped[categorie_key] = {
                'label': categorie_label,
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'total_capacite': 0,
                'nombre_classes': 0
            }

        from django.db.models.functions import Lower
        
        # Filtrer les élèves par année scolaire active si fournie
        if annee_scolaire_active:
            # Récupérer directement les inscriptions pour cette classe et cette année scolaire
            inscriptions = InscriptionEleve.objects.filter(
                annee_scolaire=annee_scolaire_active,
                classe=classe,
                etablissement=etablissement
            ).select_related('eleve').order_by(Lower('eleve__nom'), Lower('eleve__prenom'))
            
            # Récupérer les élèves depuis les inscriptions (inclure tous les élèves, actifs et désactivés)
            eleves_list = [inscription.eleve for inscription in inscriptions if inscription.eleve]
            
            # Créer un queryset à partir de la liste pour maintenir la compatibilité (inclure tous les élèves)
            eleves_ids = [eleve.id for eleve in eleves_list]
            eleves_queryset = Eleve.objects.filter(id__in=eleves_ids).order_by(Lower('nom'), Lower('prenom'))
        else:
            # Comportement par défaut : tous les élèves (actifs et désactivés)
            eleves_queryset = Eleve.objects.filter(classe=classe).order_by(Lower('nom'), Lower('prenom'))

        eleves_data = []
        for eleve in eleves_queryset:
            # Filtrer les absences par année scolaire active si disponible
            nombre_absences = Presence.get_nombre_absences(eleve, annee_scolaire=annee_scolaire_active)
            nombre_sanctions = Sanction.get_nombre_sanctions(eleve)

            eleves_data.append({
                'eleve': eleve,
                'nombre_absences': nombre_absences,
                'nombre_sanctions': nombre_sanctions,
            })

        nombre_eleves_classe = eleves_queryset.count()
        stats_classe = {
            'total_eleves': nombre_eleves_classe,
            'nouveaux_eleves': eleves_queryset.filter(statut='nouvelle').count(),
            'transferts': eleves_queryset.filter(statut='transfert').count(),
            'reinscriptions': eleves_queryset.filter(statut='reinscription').count(),
            'taux_occupation': classe.taux_occupation,
            'places_disponibles': classe.places_disponibles,
        }

        classe_info = {
            'classe': classe,
            'eleves': eleves_data,
            'stats': stats_classe,
            'nombre_eleves': nombre_eleves_classe,
            'capacite_max': classe.capacite_max,
        }

        classes_grouped[categorie_key]['classes'].append(classe_info)
        classes_grouped[categorie_key]['total_eleves'] += nombre_eleves_classe
        classes_grouped[categorie_key]['total_capacite'] += classe.capacite_max
        classes_grouped[categorie_key]['nombre_classes'] += 1

        total_eleves += nombre_eleves_classe
        total_capacite += classe.capacite_max

    total_nouveaux = 0
    total_transferts = 0
    total_reinscriptions = 0
    for data in classes_grouped.values():
        for classe_info in data['classes']:
            total_nouveaux += classe_info['stats']['nouveaux_eleves']
            total_transferts += classe_info['stats']['transferts']
            total_reinscriptions += classe_info['stats']['reinscriptions']

    tab_index = 0
    for categorie_key in classes_grouped.keys():
        tab_index += 1
        main_tab_id = f'tab-{tab_index}'
        for classe_info in classes_grouped[categorie_key]['classes']:
            classe_info['main_tab_id'] = main_tab_id

    stats_generales = {
        'total_eleves': total_eleves,
        'total_classes': classes.count(),
        'taux_occupation_global': round((total_eleves / total_capacite * 100), 1) if total_capacite > 0 else 0,
        'nouveaux_eleves': total_nouveaux,
        'transferts': total_transferts,
        'reinscriptions': total_reinscriptions,
    }

    return classes_grouped, stats_generales


def _main_tab_id_for_classe(etablissement, classe_id, annee_scolaire_active=None):
    classes_grouped, _ = _build_classes_grouped_data(etablissement, annee_scolaire_active)
    for data in classes_grouped.values():
        for classe_info in data['classes']:
            if classe_info['classe'].id == classe_id:
                return classe_info.get('main_tab_id', 'tab-1')
    return 'tab-1'


def _resolve_eleves_access(request, permission_inscrire=False):
    from ..utils.decorators_permissions import check_permission

    user = request.user
    if isinstance(user, PersonnelAdministratif):
        if permission_inscrire:
            if not check_permission(user, 'eleves_inscrire') and user.fonction != 'secretaire_principal':
                messages.error(request, "Vous n'avez pas la permission d'inscrire des élèves.")
                return None, None, redirect('directeur:dashboard_directeur')
        elif not check_permission(user, 'eleves_liste'):
            messages.error(request, "Vous n'avez pas la permission de voir la liste des élèves.")
            return None, None, redirect('directeur:dashboard_directeur')
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return None, None, redirect('school_admin:connexion_compte_user')

    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return None, None, redirect('school_admin:connexion_compte_user')

    return user, etablissement, None


def _default_inscription_form_data():
    return {
        'statut': 'nouvelle',
        'date_inscription': date.today().strftime('%Y-%m-%d'),
        'nationalite': '',
        'department_inscription': '',
        'parent_nom': '',
        'parent_prenom': '',
        'parent_telephone': '',
        'parent_adresse': '',
        'parent_profession': '',
        'parent_lien': '',
    }


def _build_inscription_form_context(etablissement, form_data=None, field_errors=None):
    est_superieur = etablissement.type_etablissement == 'superieur'
    if est_superieur:
        classes = (
            Classe.objects.filter(etablissement=etablissement, actif=True, niveau='superieur')
            .select_related('department', 'academic_level')
            .order_by('department__nom', 'nom')
        )
        departments_inscription = list(
            Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
        )
    else:
        classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
        departments_inscription = []

    try:
        pays_list = [(code, str(nom)) for code, nom in countries]
    except Exception as exc:
        logging.getLogger(__name__).error("Erreur lors de la récupération des pays: %s", exc)
        pays_list = []

    return {
        'classes': classes,
        'est_superieur': est_superieur,
        'departments_inscription': departments_inscription,
        'form_data': form_data or _default_inscription_form_data(),
        'field_errors': field_errors or {},
        'pays_list': pays_list,
    }


def _archiver_inscription_eleve_parent(eleve, parent, etablissement, annee_scolaire, date_inscription):
    """
    Crée ou met à jour les enregistrements d'archivage d'inscription
    pour l'élève et le parent, liés à l'année scolaire active.
    """
    if not annee_scolaire:
        return

    logger = logging.getLogger(__name__)

    try:
        # Inscription élève
        InscriptionEleve.objects.update_or_create(
            annee_scolaire=annee_scolaire,
            matricule_eleve=eleve.matricule_eleve,
            defaults={
                'eleve': eleve,
                'nom': eleve.nom,
                'prenom': eleve.prenom,
                'date_naissance': eleve.date_naissance,
                'lieu_naissance': eleve.lieu_naissance,
                'sexe': eleve.sexe,
                'nationalite': eleve.nationalite,
                'adresse': eleve.adresse,
                'telephone': eleve.telephone,
                'email': eleve.email,
                'numero_eleve': eleve.numero_eleve,
                'etablissement': etablissement,
                'classe': eleve.classe,
                'date_inscription': date_inscription or eleve.date_inscription,
                'statut': eleve.statut,
                'parent_nom': eleve.parent_nom,
                'parent_prenom': eleve.parent_prenom,
                'parent_telephone': eleve.parent_telephone,
                'parent_email': eleve.parent_email,
                'parent_adresse': eleve.parent_adresse,
                'parent_profession': eleve.parent_profession,
                'parent_lien': eleve.parent_lien,
                'document_acte_naissance': eleve.document_acte_naissance,
                'document_cni': eleve.document_cni,
                'document_passeport': eleve.document_passeport,
                'document_bulletin_precedent': eleve.document_bulletin_precedent,
                'document_certificat_scolarite': eleve.document_certificat_scolarite,
                'document_livret_scolaire': eleve.document_livret_scolaire,
                'document_certificat_medical': eleve.document_certificat_medical,
                'document_carnet_vaccination': eleve.document_carnet_vaccination,
                'document_assurance_maladie': eleve.document_assurance_maladie,
                'document_justificatif_domicile': eleve.document_justificatif_domicile,
                'document_photo_identite': eleve.document_photo_identite,
                'document_autorisation_parentale': eleve.document_autorisation_parentale,
            }
        )

        # Inscription parent
        if parent:
            type_parent = parent.type_parent if parent.type_parent in ['mere', 'pere', 'tuteur'] else 'tuteur'
            InscriptionParent.objects.update_or_create(
                annee_scolaire=annee_scolaire,
                matricule_parental=parent.matricule_parental,
                defaults={
                    'parent': parent,
                    'nom': parent.nom,
                    'prenom': parent.prenom,
                    'telephone': parent.telephone,
                    'email': parent.email,
                    'type_parent': type_parent,
                    'adresse': parent.adresse,
                    'profession': parent.profession,
                    'etablissement': etablissement,
                    'date_inscription': date_inscription or eleve.date_inscription,
                }
            )
    except Exception as archive_error:
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de l'archivage des inscriptions pour {eleve.nom_complet}: {archive_error}", exc_info=True)


@login_required
def dashboard_secretaire(request):
    """
    Dashboard pour le secrétaire d'établissement ou le directeur
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'année scolaire active ou consultée
    # Si c'est un directeur, utiliser la session consultée, sinon la session active
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True)
    
    # Statistiques des élèves et classes filtrées par année scolaire active
    total_eleves = 0
    nouveaux_eleves = 0
    if annee_scolaire_active:
        # Compter les élèves via InscriptionEleve pour l'année scolaire active
        total_eleves = InscriptionEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        ).count()
        nouveaux_eleves = InscriptionEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            statut='nouvelle'
        ).count()
    
    # Statistiques de l'utilisateur
    if isinstance(user, PersonnelAdministratif):
        stats = {
            'nom_complet': user.nom_complet,
            'fonction': user.get_fonction_display(),
            'etablissement': etablissement.nom,
            'date_creation': user.date_creation,
            'actif': user.actif,
            'numero_employe': user.numero_employe,
        }
    else:  # Directeur
        stats = {
            'nom_complet': f"{etablissement.directeur_prenom} {etablissement.directeur_nom}",
            'fonction': "Directeur",
            'etablissement': etablissement.nom,
            'date_creation': etablissement.date_creation,
            'actif': True,
            'numero_employe': "DIR-001",
        }
    
    # Statistiques de l'établissement
    etablissement_stats = {
        'nom': etablissement.nom,
        'type': etablissement.get_type_etablissement_display(),
        'code': etablissement.code_etablissement,
        'ville': etablissement.ville,
        'pays': etablissement.pays,
    }
    
    # Statistiques des élèves et classes filtrées par année scolaire active
    dashboard_stats = {
        'total_eleves': total_eleves,
        'nouveaux_eleves': nouveaux_eleves,
        'total_classes': classes.count(),
        'evaluations_en_cours': 0,  # TODO: Implémenter le comptage des évaluations
        'taches_urgentes': 3,  # Placeholder
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'stats': stats,
        'etablissement_stats': etablissement_stats,
        'dashboard_stats': dashboard_stats,
        'classes': classes,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/secretaire/dashboard_secretaire.html', context)


@login_required
def inscription_eleves(request):
    """
    Traite l'inscription des élèves (POST JSON). GET redirige vers la liste.
    """
    user, etablissement, denied = _resolve_eleves_access(request, permission_inscrire=True)
    if denied:
        return denied

    if request.method == 'GET':
        return redirect('secretaire:liste_eleves')

    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    if not annee_scolaire_active:
        from ..services.realtime_helpers import wants_json_response, json_fail
        message = (
            "Aucune année scolaire active n'a été trouvée. "
            "Créez ou activez d'abord une session pour continuer l'inscription."
        )
        if wants_json_response(request):
            return json_fail(message=message)
        messages.error(request, message)
        if isinstance(user, Etablissement):
            return redirect('directeur:creer_annee_scolaire_obligatoire')
        return redirect('secretaire:dashboard_secretaire')

    est_superieur = etablissement.type_etablissement == 'superieur'
    if est_superieur:
        departments_inscription = list(
            Department.objects.filter(etablissement=etablissement).order_by('ordre', 'nom')
        )
    else:
        departments_inscription = []

    form_data = _default_inscription_form_data()
    field_errors = {}
    # Récupération des données
    form_data = {
        'nom': request.POST.get('nom', '').strip(),
        'prenom': request.POST.get('prenom', '').strip(),
        'date_naissance': request.POST.get('date_naissance', ''),
        'lieu_naissance': request.POST.get('lieu_naissance', '').strip(),
        'sexe': request.POST.get('sexe', ''),
        'nationalite': request.POST.get('nationalite', '').strip(),
        'adresse': request.POST.get('adresse', '').strip(),
        'classe': request.POST.get('classe', ''),
        'date_inscription': request.POST.get('date_inscription', ''),
        'statut': request.POST.get('statut', ''),
        # Champs parent/tuteur
        'parent_nom': request.POST.get('parent_nom', '').strip(),
        'parent_prenom': request.POST.get('parent_prenom', '').strip(),
        # Pour le téléphone parent, utiliser le numéro formaté (parent_telephone_full) s'il existe, sinon utiliser parent_telephone
        'parent_telephone': request.POST.get('parent_telephone_full', '').strip() or request.POST.get('parent_telephone', '').strip(),
        'parent_adresse': request.POST.get('parent_adresse', '').strip(),
        'parent_profession': request.POST.get('parent_profession', '').strip(),
        'parent_lien': request.POST.get('parent_lien', ''),
        # Mot de passe provisoire
        'mot_de_passe_provisoire': request.POST.get('mot_de_passe_provisoire', ''),
        # Documents d'identité
        'document_acte_naissance': request.POST.get('document_acte_naissance') == 'true',
        'document_cni': request.POST.get('document_cni') == 'true',
        'document_passeport': request.POST.get('document_passeport') == 'true',
        # Documents scolaires
        'document_bulletin_precedent': request.POST.get('document_bulletin_precedent') == 'true',
        'document_certificat_scolarite': request.POST.get('document_certificat_scolarite') == 'true',
        'document_livret_scolaire': request.POST.get('document_livret_scolaire') == 'true',
        # Documents médicaux
        'document_certificat_medical': request.POST.get('document_certificat_medical') == 'true',
        'document_carnet_vaccination': request.POST.get('document_carnet_vaccination') == 'true',
        'document_assurance_maladie': request.POST.get('document_assurance_maladie') == 'true',
        # Documents administratifs
        'document_justificatif_domicile': request.POST.get('document_justificatif_domicile') == 'true',
        'document_photo_identite': request.POST.get('document_photo_identite') == 'true',
        'document_autorisation_parentale': request.POST.get('document_autorisation_parentale') == 'true',
        'department_inscription': request.POST.get('department_inscription', '').strip(),
    }
    
    # Validation
    is_valid = True
    inscription_date_obj = None
    
    # Champs obligatoires (adresse supprimée de la liste)
    required_fields = ['nom', 'prenom', 'date_naissance', 'lieu_naissance', 'sexe', 'nationalite', 'classe', 'date_inscription', 'statut']
    for field in required_fields:
        if not form_data[field]:
            field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
            is_valid = False
    
    # Validation des champs parent/tuteur
    parent_required = ['parent_nom', 'parent_prenom', 'parent_telephone', 'parent_lien']
    for field in parent_required:
        if not form_data[field]:
            field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
            is_valid = False
    
    # Validation de la date de naissance
    if form_data['date_naissance']:
        try:
            birth_date = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
            if birth_date > date.today():
                field_errors['date_naissance'] = "La date de naissance ne peut pas être dans le futur."
                is_valid = False
        except ValueError:
            field_errors['date_naissance'] = "Format de date invalide."
            is_valid = False
    
    # Validation de la date d'inscription
    if form_data['date_inscription']:
        try:
            inscription_date = datetime.strptime(form_data['date_inscription'], '%Y-%m-%d').date()
            inscription_date_obj = inscription_date
            if inscription_date > date.today():
                field_errors['date_inscription'] = "La date d'inscription ne peut pas être dans le futur."
                is_valid = False
        except ValueError:
            field_errors['date_inscription'] = "Format de date invalide."
            is_valid = False
    
    # Génération automatique du matricule et mots de passe
    import random
    # Générer le matricule élève (nouveau format)
    matricule_eleve = Eleve.generer_matricule_eleve(etablissement)
    form_data['matricule_eleve'] = matricule_eleve
    
    # Générer le mot de passe élève (format XXXXXX - 6 chiffres sans tiret)
    mot_de_passe_eleve = Eleve.generer_mot_de_passe()
    form_data['mot_de_passe_provisoire'] = mot_de_passe_eleve
    
    # Générer le matricule parent et mot de passe parent
    from ..model.parent_model import Parent
    matricule_parent = Parent.generer_matricule_parent(etablissement)
    mot_de_passe_parent = Parent.generer_mot_de_passe()
    form_data['matricule_parent'] = matricule_parent
    form_data['mot_de_passe_parent'] = mot_de_passe_parent
    
    # Validation de la classe
    if form_data['classe']:
        try:
            classe = Classe.objects.select_related('department', 'academic_level').get(
                id=form_data['classe'], etablissement=etablissement
            )
            if est_superieur and classe.niveau != 'superieur':
                field_errors['classe'] = "La classe sélectionnée n'est pas valide pour un établissement supérieur."
                is_valid = False
            elif est_superieur and departments_inscription and classe.department_id:
                dep_sel = form_data.get('department_inscription', '')
                if not dep_sel:
                    field_errors['department_inscription'] = (
                        "Veuillez sélectionner une filière avant la classe."
                    )
                    is_valid = False
                elif str(classe.department_id) != dep_sel:
                    field_errors['classe'] = "La classe ne correspond pas à la filière sélectionnée."
                    is_valid = False
            
            # Vérifier les places disponibles dans la classe
            if 'classe' not in field_errors and 'department_inscription' not in field_errors:
                places_disponibles = classe.places_disponibles
                if places_disponibles <= 0:
                    field_errors['classe'] = f"La classe {classe.nom} est pleine. Aucune place disponible ({classe.capacite_max}/{classe.capacite_max} élèves)."
                    is_valid = False
                elif places_disponibles == 1:
                    # Avertissement si il ne reste qu'une place
                    messages.warning(request, f"Attention : Il ne reste qu'une place disponible dans la classe {classe.nom}.")
                
        except Classe.DoesNotExist:
            field_errors['classe'] = "La classe sélectionnée n'existe pas."
            is_valid = False
    
    # Validation du sexe
    if form_data['sexe'] not in ['M', 'F']:
        field_errors['sexe'] = "Le sexe doit être Masculin ou Féminin."
        is_valid = False
    
    # Validation du statut
    if form_data['statut'] not in ['nouvelle', 'transfert', 'reinscription']:
        field_errors['statut'] = "Le type d'inscription sélectionné n'est pas valide."
        is_valid = False
    
    # Validation du lien parent/tuteur
    if form_data['parent_lien'] not in ['pere', 'mere', 'grand_parent', 'oncle_tante', 'frere_soeur', 'autre_famille', 'tuteur_legal', 'autre']:
        field_errors['parent_lien'] = "Le lien avec l'élève sélectionné n'est pas valide."
        is_valid = False
    
    # Si tout est valide, traiter l'inscription
    if is_valid:
        try:
            with transaction.atomic():
                
                # Récupérer la classe et vérifier à nouveau les places disponibles
                classe = Classe.objects.get(id=form_data['classe'], etablissement=etablissement)
                
                # Vérification finale des places disponibles (au cas où la capacité aurait changé)
                if classe.places_disponibles <= 0:
                    field_errors['classe'] = f"La classe {classe.nom} est maintenant pleine. Aucune place disponible ({classe.capacite_max}/{classe.capacite_max} élèves)."
                    is_valid = False
                    raise Exception("Classe pleine")
                
                # Formater les noms et prénoms
                nom_formate = formater_nom(form_data['nom'])
                prenom_formate = formater_prenom(form_data['prenom'])
                parent_nom_formate = formater_nom(form_data['parent_nom'])
                parent_prenom_formate = formater_prenom(form_data['parent_prenom'])
                
                # Créer l'élève
                eleve = Eleve(
                    nom=nom_formate,
                    prenom=prenom_formate,
                    date_naissance=datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date(),
                    lieu_naissance=form_data['lieu_naissance'],
                    sexe=form_data['sexe'],
                    nationalite=form_data['nationalite'],
                    adresse=form_data['adresse'] if form_data['adresse'] else None,
                    numero_eleve=form_data['matricule_eleve'],  # Assigner numero_eleve avec le matricule
                    matricule_eleve=form_data['matricule_eleve'],
                    etablissement=etablissement,
                    classe=classe,
                    date_inscription=inscription_date_obj or datetime.strptime(form_data['date_inscription'], '%Y-%m-%d').date(),
                    statut=form_data['statut'],
                    # Champs parent/tuteur
                    parent_nom=parent_nom_formate,
                    parent_prenom=parent_prenom_formate,
                    parent_telephone=form_data['parent_telephone'],
                    parent_adresse=form_data['parent_adresse'] if form_data['parent_adresse'] else None,
                    parent_profession=form_data['parent_profession'] if form_data['parent_profession'] else None,
                    parent_lien=form_data['parent_lien'],
                    # Mot de passe provisoire
                    mot_de_passe_provisoire=form_data['mot_de_passe_provisoire'],
                    mot_de_passe_eleve_modifie=False,
                    # Documents d'identité
                    document_acte_naissance=form_data['document_acte_naissance'],
                    document_cni=form_data['document_cni'],
                    document_passeport=form_data['document_passeport'],
                    # Documents scolaires
                    document_bulletin_precedent=form_data['document_bulletin_precedent'],
                    document_certificat_scolarite=form_data['document_certificat_scolarite'],
                    document_livret_scolaire=form_data['document_livret_scolaire'],
                    # Documents médicaux
                    document_certificat_medical=form_data['document_certificat_medical'],
                    document_carnet_vaccination=form_data['document_carnet_vaccination'],
                    document_assurance_maladie=form_data['document_assurance_maladie'],
                    # Documents administratifs
                    document_justificatif_domicile=form_data['document_justificatif_domicile'],
                    document_photo_identite=form_data['document_photo_identite'],
                    document_autorisation_parentale=form_data['document_autorisation_parentale'],
                    # Configuration de base
                    username=form_data['matricule_eleve'],  # Utiliser le nouveau matricule comme username
                    is_active=True,
                    is_staff=False,
                    is_superuser=False,
                )
                
                # Définir le mot de passe pour la connexion AVANT la sauvegarde
                eleve.set_password(form_data['mot_de_passe_provisoire'])
                
                # Sauvegarder l'élève
                eleve.save()
                
                # Créer le compte Parent
                from ..model.parent_model import Parent
                from ..model.lien_familial_model import LienFamilial
                from django.contrib.auth.hashers import make_password
                
                # Vérifier si un parent avec ce téléphone existe déjà
                parent_existant = None
                if form_data['parent_telephone']:
                    parent_existant = Parent.objects.filter(
                        telephone=form_data['parent_telephone'],
                        etablissement=etablissement
                    ).first()
                
                if parent_existant:
                    # Utiliser le parent existant et créer le lien
                    parent = parent_existant
                    print(f"[INFO] Parent existant trouvé : {parent.nom_complet}")
                else:
                    # Créer un nouveau compte parent
                    parent = Parent(
                        matricule_parental=form_data['matricule_parent'],
                        type_parent=form_data['parent_lien'] if form_data['parent_lien'] in ['mere', 'pere', 'tuteur'] else 'tuteur',
                        nom=parent_nom_formate,
                        prenom=parent_prenom_formate,
                        telephone=form_data['parent_telephone'],
                        email='',
                        adresse=form_data['parent_adresse'] if form_data['parent_adresse'] else '',
                        profession=form_data['parent_profession'] if form_data['parent_profession'] else '',
                        etablissement=etablissement,
                        mot_de_passe_provisoire=form_data['mot_de_passe_parent'],
                        mot_de_passe_modifie=False,
                        username=form_data['matricule_parent'],
                        is_active=True,
                        is_staff=False,
                        is_superuser=False,
                    )
                    parent.set_password(form_data['mot_de_passe_parent'])
                    parent.save()
                    print(f"[INFO] Nouveau parent créé : {parent.nom_complet}")
                
                # Créer le lien familial
                lien = LienFamilial.objects.create(
                    parent=parent,
                    eleve=eleve,
                    type_lien=form_data['parent_lien'] if form_data['parent_lien'] in ['mere', 'pere', 'tuteur'] else 'tuteur',
                    statut='valide',
                    est_inscripteur=True,
                    actif=True
                )
                print(f"[INFO] Lien familial créé : {parent.nom_complet} -> {eleve.nom_complet}")
                
                # Stocker les informations du parent dans form_data pour le reçu
                form_data['parent_cree'] = parent
                
                # Archiver l'inscription dans les tables dédiées
                _archiver_inscription_eleve_parent(
                    eleve=eleve,
                    parent=parent,
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active,
                    date_inscription=inscription_date_obj or eleve.date_inscription
                )
                
                # Créer les frais d'inscription si le module comptabilité est activé
                if etablissement.module_comptabilite:
                    from ..utils.comptabilite_utils import creer_frais_inscription
                    type_frais = 'inscription' if form_data['statut'] == 'nouvelle' else 'reinscription'
                    try:
                        creer_frais_inscription(eleve, annee_scolaire_active, type_frais)
                    except Exception as e:
                        # Logger l'erreur mais ne pas bloquer l'inscription
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Erreur lors de la création des frais d'inscription pour {eleve.nom_complet}: {str(e)}")
                
                # La facturation de l'établissement est automatiquement mise à jour
                # par la méthode save() du modèle Eleve via recalculer_facturation()
                
                # Mettre à jour la date de dernière facturation
                from django.utils import timezone
                etablissement.date_derniere_facturation = timezone.now()
                etablissement.save(update_fields=['date_derniere_facturation'])
                
                # Log des documents fournis
                documents_fournis = eleve.documents_fournis_liste
                documents_text = ", ".join(documents_fournis) if documents_fournis else "Aucun document"
                
                # Récupérer le montant par élève pour le message
                montant_par_eleve = etablissement.montant_par_eleve
                
                # Formater le montant avec la devise si disponible
                devise_etablissement = etablissement.devise_monnaie
                if devise_etablissement:
                    montant_affiche = f"{montant_par_eleve} {devise_etablissement}"
                else:
                    montant_affiche = str(montant_par_eleve)
                
                messages.success(request, f"L'élève {form_data['prenom']} {form_data['nom']} a été inscrit avec succès ! Montant ajouté: {montant_affiche}. Documents fournis: {documents_text}")

                from ..services.realtime_helpers import wants_json_response, json_ok, emit_live
                from ..services.live_serializers import serialize_eleve_inscrit_item
                from ..model.presence_model import Presence

                main_tab_id = _main_tab_id_for_classe(
                    etablissement, classe.id, annee_scolaire_active
                )
                nombre_absences = Presence.get_nombre_absences(eleve, annee_scolaire=annee_scolaire_active)
                item = serialize_eleve_inscrit_item(
                    eleve, classe, main_tab_id, nombre_absences=nombre_absences
                )
                item['mot_de_passe_parent'] = form_data.get('mot_de_passe_parent', '')
                item['matricule_parent'] = form_data.get('matricule_parent', '')
                success_message = (
                    f"L'élève {eleve.nom_complet} a été inscrit avec succès. "
                    f"Identifiant élève : {item['matricule']} — "
                    f"Mot de passe provisoire : {item['mot_de_passe_provisoire']}"
                )
                emit_live(
                    etablissement.id,
                    'eleve.inscrit',
                    {'event': 'eleve.inscrit', 'item': item},
                )
                from django.urls import reverse
                recu_url = reverse('secretaire:reçu_inscription_eleve', args=[eleve.id])
                if wants_json_response(request):
                    return json_ok(item=item, recu_url=recu_url)
                return redirect('secretaire:liste_eleves')
                
        except Exception as e:
            field_errors['__all__'] = f"Une erreur est survenue lors de l'inscription: {str(e)}. Veuillez réessayer."
            is_valid = False

    from ..services.realtime_helpers import wants_json_response, json_fail
    if not is_valid:
        if wants_json_response(request):
            return json_fail(field_errors=field_errors)
        request.session['inscription_form_data'] = form_data
        request.session['inscription_field_errors'] = field_errors
        return redirect('secretaire:liste_eleves?inscrire=1')

    return redirect('secretaire:liste_eleves')


@login_required
def liste_eleves(request):
    """
    Page de liste des élèves inscrits par classe
    """
    user, etablissement, denied = _resolve_eleves_access(request, permission_inscrire=False)
    if denied:
        return denied
    
    # Récupérer l'année scolaire active ou consultée
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Les élèves affichés ne sont pas filtrés par session.")
    
    classes_grouped, stats_generales = _build_classes_grouped_data(etablissement, annee_scolaire_active)

    session_form_data = request.session.pop('inscription_form_data', None)
    session_field_errors = request.session.pop('inscription_field_errors', None)
    inscription_ctx = _build_inscription_form_context(
        etablissement,
        form_data=session_form_data,
        field_errors=session_field_errors or {},
    )

    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'classes_grouped': classes_grouped,
        'stats_generales': stats_generales,
        'annee_scolaire_active': annee_scolaire_active,
        'est_superieur': etablissement.type_etablissement == 'superieur',
        'open_inscription_modal': request.GET.get('inscrire') == '1' or bool(session_field_errors),
        **inscription_ctx,
    }
    
    return render(request, 'school_admin/directeur/secretaire/liste_eleves.html', context)


@login_required
def cartes_identite_eleves(request):
    """
    Page listant les cartes d'identité scolaires par classe.
    """
    user = request.user

    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')

    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')

    # Récupérer l'année scolaire active ou consultée
    from ..utils.session_utils import get_session_active, get_session_consultee, get_session_consultee
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)

    classes_grouped, stats_generales = _build_classes_grouped_data(etablissement, annee_scolaire_active)
    
    # Récupérer les personnalisations de la carte d'identité
    from ..model.carte_identite_personnalisation_model import CarteIdentitePersonnalisation
    personnalisation = CarteIdentitePersonnalisation.get_or_create_for_etablissement(etablissement)

    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'classes_grouped': classes_grouped,
        'stats_generales': stats_generales,
        'annee_scolaire_active': annee_scolaire_active,
        'personnalisation': personnalisation,
        'est_superieur': etablissement.type_etablissement == 'superieur',
    }

    return render(request, 'school_admin/directeur/secretaire/cartes_identite_eleves.html', context)


@login_required
def carte_identite_eleve(request, eleve_id):
    """
    Page dédiée à l'affichage de la carte d'identité scolaire d'un élève.
    """
    user = request.user

    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')

    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')

    try:
        eleve = Eleve.objects.select_related(
            'classe', 'classe__academic_level',
        ).get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:cartes_identite_eleves')

    if not eleve.qr_code_image or not eleve.qr_code_identifier or not eleve.qr_code_data:
        try:
            eleve.save()
        except RuntimeError as qr_error:
            messages.warning(request, f"QR code indisponible : {qr_error}")

    # Récupérer l'année scolaire active ou consultée
    from ..utils.session_utils import get_session_active, get_session_consultee, get_session_consultee
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    # Récupérer les personnalisations de la carte d'identité
    from ..model.carte_identite_personnalisation_model import CarteIdentitePersonnalisation
    personnalisation = CarteIdentitePersonnalisation.get_or_create_for_etablissement(etablissement)
    
    context = {
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'eleve': eleve,
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
        'personnalisation': personnalisation,
    }
    
    return render(request, 'school_admin/directeur/secretaire/carte_identite_eleve.html', context)


@login_required
def cartes_identite_classe(request, classe_id):
    """Page d'impression regroupant les cartes d'identité d'une classe."""
    user = request.user

    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')

    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')

    try:
        classe = Classe.objects.select_related('academic_level').get(
            id=classe_id, etablissement=etablissement, actif=True
        )
    except Classe.DoesNotExist:
        messages.error(request, "Classe introuvable ou non autorisée.")
        return redirect('secretaire:cartes_identite_eleves')

    # Récupérer l'année scolaire active ou consultée
    from ..model.inscription_eleve_model import InscriptionEleve
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'imprimer les cartes d'identité.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    # Filtrer les élèves par année scolaire active via InscriptionEleve
    # Utiliser la même logique que _build_classes_grouped_data
    from django.db.models.functions import Lower
    inscriptions = InscriptionEleve.objects.filter(
        annee_scolaire=annee_scolaire_active,
        classe=classe,
        etablissement=etablissement
    ).select_related('eleve').order_by(Lower('eleve__nom'), Lower('eleve__prenom'))
    
    # Récupérer les élèves depuis les inscriptions (inclure tous les élèves, actifs et désactivés)
    eleves_list = [inscription.eleve for inscription in inscriptions if inscription.eleve]
    
    # Créer un queryset à partir de la liste pour maintenir la compatibilité
    eleves_ids = [eleve.id for eleve in eleves_list]
    eleves_queryset = Eleve.objects.filter(id__in=eleves_ids).select_related(
        'classe', 'classe__academic_level',
    ).order_by(Lower('nom'), Lower('prenom'))
    eleves = list(eleves_queryset)

    erreurs_qr = []
    for eleve in eleves:
        if not eleve.qr_code_image or not eleve.qr_code_identifier or not eleve.qr_code_data:
            try:
                eleve.save()
            except RuntimeError as qr_error:
                erreurs_qr.append(f"{eleve.nom_complet} : {qr_error}")

    if erreurs_qr:
        messages.warning(
            request,
            "Certaines cartes n'ont pas pu être générées : " + "; ".join(erreurs_qr)
        )

    # Déterminer l'année scolaire à afficher
    annee_scolaire_libelle = annee_scolaire_active.libelle if annee_scolaire_active else 'Non spécifiée'
    
    # Récupérer les personnalisations de la carte d'identité
    from ..model.carte_identite_personnalisation_model import CarteIdentitePersonnalisation
    personnalisation = CarteIdentitePersonnalisation.get_or_create_for_etablissement(etablissement)

    context = {
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'classe': classe,
        'eleves': eleves,
        'annee_scolaire': annee_scolaire_libelle,
        'annee_scolaire_active': annee_scolaire_active,
        'personnalisation': personnalisation,
    }

    return render(
        request,
        'school_admin/directeur/secretaire/cartes_identite_classe.html',
        context
    )


@login_required
def sauvegarder_personnalisation_carte_identite(request):
    """Sauvegarde les personnalisations de l'en-tête de la carte d'identité"""
    from django.http import JsonResponse
    from ..model.carte_identite_personnalisation_model import CarteIdentitePersonnalisation
    
    user = request.user
    
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        return JsonResponse({'success': False, 'message': 'Accès non autorisé.'}, status=403)
    
    if not etablissement:
        return JsonResponse({'success': False, 'message': 'Aucun établissement associé.'}, status=400)
    
    if request.method == 'POST':
        try:
            personnalisation = CarteIdentitePersonnalisation.get_or_create_for_etablissement(etablissement)
            
            # Récupérer les données du formulaire
            pays_nom = request.POST.get('pays_nom', '').strip()
            devise_pays = request.POST.get('devise_pays', '').strip()
            titre_carte = request.POST.get('titre_carte', '').strip()
            devise_etablissement = request.POST.get('devise_etablissement', '').strip()
            
            # Validation
            if not pays_nom:
                return JsonResponse({'success': False, 'message': 'Le nom du pays est obligatoire.'}, status=400)
            if not devise_pays:
                return JsonResponse({'success': False, 'message': 'La devise du pays est obligatoire.'}, status=400)
            if not titre_carte:
                return JsonResponse({'success': False, 'message': 'Le titre de la carte est obligatoire.'}, status=400)
            if not devise_etablissement:
                return JsonResponse({'success': False, 'message': 'La devise de l\'établissement est obligatoire.'}, status=400)
            
            # Mettre à jour
            personnalisation.pays_nom = pays_nom
            personnalisation.devise_pays = devise_pays
            personnalisation.titre_carte = titre_carte
            personnalisation.devise_etablissement = devise_etablissement
            personnalisation.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Personnalisation enregistrée avec succès.',
                'data': {
                    'pays_nom': personnalisation.pays_nom,
                    'devise_pays': personnalisation.devise_pays,
                    'titre_carte': personnalisation.titre_carte,
                    'devise_etablissement': personnalisation.devise_etablissement,
                }
            })
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de la sauvegarde de la personnalisation: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'message': f'Une erreur est survenue: {str(e)}'}, status=500)
    
    return JsonResponse({'success': False, 'message': 'Méthode non autorisée.'}, status=405)


@login_required
def reçu_inscription_eleve(request, eleve_id):
    """
    Page de reçu d'inscription pour un élève (secrétaire ou directeur)
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer l'élève
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:liste_eleves')
    
    # Informations de l'établissement
    etablissement_info = {
        'nom': etablissement.nom,
        'type': etablissement.get_type_etablissement_display(),
        'code': etablissement.code_etablissement,
        'adresse': etablissement.adresse,
        'ville': etablissement.ville,
        'pays': etablissement.pays,
        'telephone': etablissement.telephone,
        'email': etablissement.email,
    }
    
    # Informations de l'élève
    eleve_info = {
        'nom_complet': eleve.nom_complet,
        'numero_eleve': eleve.numero_eleve,
        'date_naissance': eleve.date_naissance,
        'lieu_naissance': eleve.lieu_naissance,
        'sexe': eleve.get_sexe_display(),
        'nationalite': eleve.nationalite,
        'adresse': eleve.adresse,
        'telephone': eleve.telephone,
        'email': eleve.email,
        'classe': eleve.classe.nom if eleve.classe else "Non assigné",
        'niveau_classe': eleve.classe.get_niveau_display() if eleve.classe else "",
        'date_inscription': eleve.date_inscription,
        'statut': eleve.get_statut_display(),
        'parent_lien': eleve.get_parent_lien_display(),
        'mot_de_passe_provisoire': eleve.mot_de_passe_provisoire,
        'documents_fournis': eleve.documents_fournis_liste,
        'nombre_documents': eleve.nombre_documents_fournis,
    }
    
    # Informations du parent/tuteur
    responsable_info = {
        'nom_complet': f"{eleve.parent_prenom or ''} {eleve.parent_nom or ''}".strip() or "Non renseigné",
        'telephone': eleve.parent_telephone or "Non renseigné",
        'email': eleve.parent_email or "Non renseigné",
        'adresse': eleve.parent_adresse or "Non renseigné",
        'profession': eleve.parent_profession or "Non renseigné",
        'lien': eleve.get_parent_lien_display() or "Non renseigné",
    }
    
    # Récupérer le compte parent lié (inscripteur)
    from ..model.lien_familial_model import LienFamilial
    from ..model.parent_model import Parent
    
    parent_inscripteur = None
    lien_inscripteur = LienFamilial.objects.filter(
        eleve=eleve,
        est_inscripteur=True,
        actif=True
    ).first()
    
    if lien_inscripteur:
        parent_inscripteur = lien_inscripteur.parent
    
    # Générer les tokens QR si nécessaire
    if not eleve.qr_auth_token:
        eleve.generer_et_sauvegarder_token_qr()
    
    if parent_inscripteur and not parent_inscripteur.qr_auth_token:
        parent_inscripteur.generer_et_sauvegarder_token_qr()
    
    # Informations d'identification pour le reçu
    identifiants_info = {
        'matricule_eleve': eleve.matricule_eleve or "Non généré",
        'mot_de_passe_eleve': eleve.mot_de_passe_provisoire or "Non généré",
        'matricule_parent': parent_inscripteur.matricule_parental if parent_inscripteur else "Non généré",
        'mot_de_passe_parent': parent_inscripteur.mot_de_passe_provisoire if parent_inscripteur else "Non généré",
        'type_parent': parent_inscripteur.get_type_parent_display() if parent_inscripteur else eleve.get_parent_lien_display(),
        'nom_parent': parent_inscripteur.nom_complet if parent_inscripteur else responsable_info['nom_complet'],
        'qr_auth_url_eleve': eleve.get_qr_auth_url(request) if eleve.qr_auth_token else None,
        'qr_auth_url_parent': parent_inscripteur.get_qr_auth_url(request) if parent_inscripteur and parent_inscripteur.qr_auth_token else None,
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'etablissement_info': etablissement_info,
        'eleve': eleve,
        'eleve_info': eleve_info,
        'responsable_info': responsable_info,
        'identifiants_info': identifiants_info,
        'parent_inscripteur': parent_inscripteur,
    }

    from ..services.realtime_helpers import wants_json_response
    if wants_json_response(request) or request.GET.get('partial') == '1':
        return render(
            request,
            'school_admin/directeur/secretaire/partials/recu_inscription_eleve_inner.html',
            context,
        )

    return render(request, 'school_admin/directeur/secretaire/reçu_inscription_eleve.html', context)


@login_required
def detail_eleve(request, eleve_id):
    """
    Page de détails d'un élève avec formulaire de modification (secrétaire ou directeur)
    """
    # Import explicite pour éviter les problèmes de scope
    # InscriptionEleve et InscriptionParent sont déjà importés en haut du fichier
    from ..model.inscription_eleve_model import InscriptionEleve as InscriptionEleveModel
    from ..model.inscription_parent_model import InscriptionParent as InscriptionParentModel
    
    # Utiliser les alias pour éviter les conflits
    InscriptionEleve = InscriptionEleveModel
    InscriptionParent = InscriptionParentModel
    
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un directeur soit un personnel avec la permission eleves_detail
    from ..utils.decorators_permissions import check_permission
    
    if isinstance(user, Etablissement):
        etablissement = user
    elif isinstance(user, PersonnelAdministratif):
        # Recharger le personnel depuis la base de données pour avoir les permissions à jour
        user.refresh_from_db()
        # Vérifier la permission eleves_detail
        if not check_permission(user, 'eleves_detail'):
            messages.error(request, "Accès non autorisé. Vous n'avez pas la permission d'accéder aux détails des élèves.")
            return redirect('directeur:dashboard_directeur')
        etablissement = user.etablissement
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer l'élève
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:liste_eleves')
    
    # Générer automatiquement le QR code si nécessaire
    if not eleve.qr_code_image or not eleve.qr_code_identifier or not eleve.qr_code_data:
        try:
            eleve.save()
        except RuntimeError as qr_error:
            messages.warning(request, f"QR code indisponible : {qr_error}")
    
    # Récupérer l'année scolaire active ou consultée
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.warning(request, "Aucune année scolaire active. Les données affichées ne sont pas filtrées par session.")
    
    # Récupérer l'inscription de l'élève pour l'année scolaire active
    # Cela nous permet d'afficher la classe et le statut corrects pour cette année scolaire
    inscription_eleve = None
    classe_eleve_annee = None
    statut_eleve_annee = None
    
    if annee_scolaire_active:
        try:
            inscription_eleve = InscriptionEleve.objects.get(
                eleve=eleve,
                annee_scolaire=annee_scolaire_active,
                etablissement=etablissement
            )
            classe_eleve_annee = inscription_eleve.classe
            statut_eleve_annee = inscription_eleve.statut
        except InscriptionEleve.DoesNotExist:
            # Si pas d'inscription pour cette année, utiliser les valeurs par défaut de l'élève
            classe_eleve_annee = eleve.classe
            statut_eleve_annee = eleve.statut
    else:
        # Si pas d'année scolaire active, utiliser les valeurs par défaut de l'élève
        classe_eleve_annee = eleve.classe
        statut_eleve_annee = eleve.statut
    
    # Créer un objet proxy pour l'élève avec la classe et le statut de l'année scolaire active
    # Cela permet au template d'utiliser eleve.classe et eleve.statut sans modification
    class EleveProxy:
        def __init__(self, eleve, classe, statut):
            self._eleve = eleve
            self._classe = classe
            self._statut = statut
        
        def __getattr__(self, name):
            # Déléguer tous les attributs non définis à l'élève original
            return getattr(self._eleve, name)
        
        @property
        def classe(self):
            return self._classe
        
        @property
        def statut(self):
            return self._statut
        
        def get_statut_display(self):
            # Utiliser les choix du modèle Eleve pour obtenir le libellé
            choices = dict(self._eleve._meta.get_field('statut').choices)
            return choices.get(self._statut, self._statut)
    
    # Utiliser le proxy si on a une inscription, sinon utiliser l'élève original
    if inscription_eleve:
        eleve_display = EleveProxy(eleve, classe_eleve_annee, statut_eleve_annee)
    else:
        eleve_display = eleve
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Récupérer les présences groupées par mois
    from collections import defaultdict
    from datetime import datetime
    from school_admin.model.presence_model import Presence
    from school_admin.model.evaluation_model import Note, Evaluation
    from school_admin.model.sanction_model import Sanction
    
    # Filtrer les présences par année scolaire active si disponible
    presences = Presence.objects.filter(eleve=eleve).select_related('classe', 'professeur').order_by('-date')
    if annee_scolaire_active:
        presences = presences.filter(annee_scolaire=annee_scolaire_active)
    
    # Grouper les présences par mois
    presences_par_mois = defaultdict(list)
    for presence in presences:
        mois_key = f"{presence.date.year}-{presence.date.month:02d}"
        mois_nom = presence.date.strftime('%B %Y')
        presences_par_mois[mois_key].append({
            'presence': presence,
            'mois_nom': mois_nom
        })
    
    # Statistiques de présence par mois
    stats_presences_par_mois = {}
    for mois_key, pres_list in presences_par_mois.items():
        total = len(pres_list)
        presents = sum(1 for p in pres_list if p['presence'].statut == 'present')
        absents = sum(1 for p in pres_list if p['presence'].statut == 'absent')
        absents_justifies = sum(1 for p in pres_list if p['presence'].statut == 'absent_justifie')
        retards = sum(1 for p in pres_list if p['presence'].statut == 'retard')
        
        stats_presences_par_mois[mois_key] = {
            'mois_nom': pres_list[0]['mois_nom'],
            'total': total,
            'presents': presents,
            'absents': absents,
            'absents_justifies': absents_justifies,
            'retards': retards,
            'taux_presence': round((presents / total * 100), 1) if total > 0 else 0
        }
    
    # Récupérer les notes groupées par matière et trimestre
    # Différencier primaire et non-primaire
    if etablissement.type_etablissement == 'primary':
        # Pour le primaire, utiliser MoyenneMatierePrimaire
        from school_admin.model.note_primaire_model import MoyenneMatierePrimaire
        from school_admin.model.periode_model import PeriodeScolaire
        
        # Filtrer les périodes par année scolaire active si disponible
        if annee_scolaire_active:
            periodes = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True,
                annee_scolaire_fk=annee_scolaire_active
            ).order_by('date_debut')
        else:
            periodes = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True
            ).order_by('date_debut')
        
        notes_par_trimestre = defaultdict(lambda: defaultdict(list))
        
        for periode in periodes:
            # Mapper le nom de la période vers le code
            if '1er Trimestre' in periode.nom_periode:
                trimestre = 'trimestre1'
            elif '2ème Trimestre' in periode.nom_periode or '2e Trimestre' in periode.nom_periode:
                trimestre = 'trimestre2'
            elif '3ème Trimestre' in periode.nom_periode or '3e Trimestre' in periode.nom_periode:
                trimestre = 'trimestre3'
            elif '1er Semestre' in periode.nom_periode:
                trimestre = 'semestre1'
            elif '2ème Semestre' in periode.nom_periode or '2e Semestre' in periode.nom_periode:
                trimestre = 'semestre2'
            else:
                trimestre = 'trimestre1'
            
            # Récupérer toutes les moyennes de l'élève pour cette période
            moyennes_qs = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                periode_scolaire=periode
            )
            # Filtrer par année scolaire active si disponible
            if annee_scolaire_active:
                moyennes_qs = moyennes_qs.filter(annee_scolaire=annee_scolaire_active)
            moyennes = moyennes_qs.select_related('matiere')
            
            for moyenne_obj in moyennes:
                if moyenne_obj.moyenne is not None:
                    # Récupérer les notes retenues pour cette matière et période
                    from school_admin.model.note_primaire_model import NotePrimaire
                    from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
                    from school_admin.model.note_examen_model import NoteExamen, CreneauExamen
                    
                    notes_retenues_detail = []
                    
                    # Récupérer les notes de devoirs/interrogations retenues
                    notes_primaires_qs = NotePrimaire.objects.filter(
                        eleve=eleve,
                        evaluation_primaire__matiere=moyenne_obj.matiere,
                        evaluation_primaire__periode_scolaire=periode,
                        retenue=True
                    )
                    # Filtrer par année scolaire active si disponible
                    if annee_scolaire_active:
                        notes_primaires_qs = notes_primaires_qs.filter(annee_scolaire=annee_scolaire_active)
                    notes_primaires = notes_primaires_qs.select_related('evaluation_primaire')
                    
                    for note in notes_primaires:
                        eval_type = "Devoir" if note.evaluation_primaire.bareme == 20 else "Interrogation"
                        notes_retenues_detail.append({
                            'type': eval_type,
                            'nom': note.evaluation_primaire.titre,
                            'note': note.note,
                            'bareme': note.evaluation_primaire.bareme,
                            'absent': note.absent
                        })
                    
                    # Récupérer la note d'examen (basée sur session, pas créneau)
                    from ..model.session_examen_model import SessionExamen
                    note_examen_qs = NoteExamen.objects.filter(
                        eleve=eleve,
                        matiere=moyenne_obj.matiere,
                        session_examen__periode=periode
                    )
                    # Filtrer par année scolaire active si disponible
                    if annee_scolaire_active:
                        note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
                    note_examen_obj = note_examen_qs.select_related('session_examen').first()
                    
                    note_examen_valeur = None
                    nom_examen = None
                    if note_examen_obj and not note_examen_obj.absent and note_examen_obj.note is not None:
                        note_examen_valeur = float(note_examen_obj.note)
                        nom_examen = note_examen_obj.session_examen.nom_examen if note_examen_obj.session_examen else 'Examen'
                    
                    notes_par_trimestre[trimestre][moyenne_obj.matiere.nom].append({
                        'moyenne': moyenne_obj.moyenne,
                        'matiere': moyenne_obj.matiere,
                        'matiere_id': moyenne_obj.matiere.id,
                        'note_sur_20': moyenne_obj.moyenne,
                        'soumis': moyenne_obj.soumis,
                        'notes_detaillees': notes_retenues_detail,
                        'note_examen': note_examen_valeur,
                        'nom_examen': nom_examen
                    })
    else:
        # Pour les autres établissements, utiliser le système standard
        notes_qs = Note.objects.filter(eleve=eleve).select_related('evaluation', 'evaluation__professeur')
        # Filtrer par année scolaire active si disponible
        if annee_scolaire_active:
            notes_qs = notes_qs.filter(annee_scolaire=annee_scolaire_active)
        notes = notes_qs.order_by('-evaluation__date_evaluation')
        
        # Grouper les notes par trimestre et matière
        notes_par_trimestre = defaultdict(lambda: defaultdict(list))
        for note in notes:
            evaluation = note.evaluation
            # Obtenir la période depuis periode_scolaire
            if evaluation.periode_scolaire:
                periode_nom = evaluation.periode_scolaire.nom_periode
                # Mapper le nom de la période vers le code
                if '1er Trimestre' in periode_nom:
                    trimestre = 'trimestre1'
                elif '2ème Trimestre' in periode_nom or '2e Trimestre' in periode_nom:
                    trimestre = 'trimestre2'
                elif '3ème Trimestre' in periode_nom or '3e Trimestre' in periode_nom:
                    trimestre = 'trimestre3'
                elif '1er Semestre' in periode_nom:
                    trimestre = 'semestre1'
                elif '2ème Semestre' in periode_nom or '2e Semestre' in periode_nom:
                    trimestre = 'semestre2'
                else:
                    trimestre = 'trimestre1'
            else:
                trimestre = 'trimestre1'
            
            # Utiliser la matière principale du professeur
            matiere_nom = evaluation.professeur.matiere_principale.nom if evaluation.professeur and evaluation.professeur.matiere_principale else 'Autre'
            
            notes_par_trimestre[trimestre][matiere_nom].append({
                'note': note,
                'evaluation': evaluation,
                'note_sur_20': note.note_sur_20
            })

    # === Ajout secondaire: matières de la classe et moyennes par matière (toutes périodes) ===
    # Initialiser les variables pour tous les types d'établissements
    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.moyenne_model import Moyenne
    from school_admin.model.periode_model import PeriodeScolaire
    from collections import defaultdict
    
    matieres_classe = []
    moyennes_par_matiere = {}
    periode_active_notes = None
    periodes_actives = []
    moyennes_par_periode = defaultdict(dict)  # {periode_id: {matiere_id: moyenne_obj}}
    
    # Remplir les données uniquement pour les établissements secondaires
    if etablissement.type_etablissement in ['lycée', 'collège', 'collège_lycée']:
        # Utiliser la classe de l'année scolaire active
        classe_eleve_actuelle = classe_eleve_annee if classe_eleve_annee else eleve.classe
        matieres_aff_qs = AffectationProfesseur.objects.filter(
            classe=classe_eleve_actuelle,
            actif=True
        )
        # Filtrer par année scolaire active si disponible
        if annee_scolaire_active:
            matieres_aff_qs = matieres_aff_qs.filter(annee_scolaire=annee_scolaire_active)
        matieres_aff = matieres_aff_qs.select_related('matiere').values_list('matiere', flat=True)
        matieres_classe = list(Matiere.objects.filter(id__in=matieres_aff, actif=True).order_by('nom'))
        
        # Récupérer toutes les périodes actives filtrées par année scolaire active
        if annee_scolaire_active:
            periodes_actives = list(PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True,
                annee_scolaire_fk=annee_scolaire_active
            ).order_by('date_debut'))
        else:
            periodes_actives = list(PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True
            ).order_by('date_debut'))
        
        # La période active par défaut (filtrée par année scolaire active)
        # Utiliser la première période active de l'année scolaire active
        periode_active_notes = periodes_actives[0] if periodes_actives else None
        
        if matieres_classe and periodes_actives:
            # Récupérer toutes les moyennes pour cet élève pour toutes les périodes
            # Utiliser la classe de l'année scolaire active
            classe_eleve_actuelle = classe_eleve_annee if classe_eleve_annee else eleve.classe
            for periode in periodes_actives:
                moyennes_qs = Moyenne.objects.filter(
                    eleve=eleve,
                    classe=classe_eleve_actuelle,
                    matiere__in=matieres_classe,
                    periode=str(periode.id),
                    actif=True
                )
                # Filtrer par année scolaire active si disponible
                if annee_scolaire_active:
                    moyennes_qs = moyennes_qs.filter(annee_scolaire=annee_scolaire_active)
                moyennes = moyennes_qs.select_related('matiere')
                
                # Créer un dictionnaire avec les moyennes indexées par matière.id pour chaque période
                for m in moyennes:
                    moyennes_par_periode[periode.id][m.matiere.id] = m
            
            # Garder moyennes_par_matiere pour la période active (compatibilité)
            if periode_active_notes:
                moyennes_par_matiere = moyennes_par_periode.get(periode_active_notes.id, {})
    
    # Calculer les moyennes par matière et par trimestre
    # Et vérifier si le relevé a été soumis pour chaque matière
    from ..model.releve_notes_model import ReleveNotes
    
    moyennes_par_trimestre = {}
    releves_soumis_par_trimestre = {}
    
    # Pour le primaire, construire directement les structures depuis notes_par_trimestre
    if etablissement.type_etablissement == 'primary':
        for trimestre, matieres in notes_par_trimestre.items():
            moyennes_matieres = {}
            releves_soumis_matieres = {}
            notes_trimestre = []
            
            for matiere, notes_list in matieres.items():
                if notes_list:
                    moyenne_data = notes_list[0]
                    moyennes_matieres[matiere] = moyenne_data.get('moyenne', 0)
                    releves_soumis_matieres[matiere] = moyenne_data.get('soumis', False)
                    notes_trimestre.append(moyenne_data.get('note_sur_20', 0))
            
            if notes_trimestre:
                moyenne_generale = sum(notes_trimestre) / len(notes_trimestre)
                moyennes_par_trimestre[trimestre] = {
                    'moyennes_matieres': moyennes_matieres,
                    'moyenne_generale': round(moyenne_generale, 2),
                    'nb_releves_soumis': sum(1 for soumis in releves_soumis_matieres.values() if soumis)
                }
                releves_soumis_par_trimestre[trimestre] = releves_soumis_matieres
    else:
        # Pour le non-primaire
        for trimestre, matieres in notes_par_trimestre.items():
            moyennes_matieres = {}
            notes_trimestre = []
            releves_soumis_matieres = {}
            
            for matiere, notes_list in matieres.items():
                notes_valeurs = [n['note_sur_20'] for n in notes_list if not n['note'].absent]
                
                # Vérifier si un relevé a été soumis pour cette matière et ce trimestre
                # Mapper le code trimestre vers la période scolaire
                if trimestre == 'trimestre1':
                    periode_nom_partiel = '1er Trimestre'
                elif trimestre == 'trimestre2':
                    periode_nom_partiel = '2ème Trimestre'
                elif trimestre == 'trimestre3':
                    periode_nom_partiel = '3ème Trimestre'
                elif trimestre == 'semestre1':
                    periode_nom_partiel = '1er Semestre'
                elif trimestre == 'semestre2':
                    periode_nom_partiel = '2ème Semestre'
                else:
                    periode_nom_partiel = None
                
                releve_soumis = False
                if periode_nom_partiel and notes_list:
                    # Chercher dans ReleveNotes
                    premier_note = notes_list[0]
                    if premier_note.get('evaluation') and premier_note['evaluation'].professeur and premier_note['evaluation'].periode_scolaire:
                        # Chercher si un relevé a été soumis pour cette classe, matière, et période
                        from ..model.matiere_model import Matiere
                        try:
                            matiere_obj = Matiere.objects.filter(
                                nom=matiere,
                                etablissement=etablissement
                            ).first()
                            
                            if matiere_obj:
                                # Utiliser la classe de l'année scolaire active
                                classe_eleve_actuelle = classe_eleve_annee if classe_eleve_annee else eleve.classe
                                releve_qs = ReleveNotes.objects.filter(
                                    classe=classe_eleve_actuelle,
                                    matiere=matiere_obj,
                                    periode_scolaire=premier_note['evaluation'].periode_scolaire,
                                    soumis=True,
                                    actif=True
                                )
                                # Filtrer par année scolaire active si disponible
                                if annee_scolaire_active:
                                    releve_qs = releve_qs.filter(annee_scolaire=annee_scolaire_active)
                                releve = releve_qs.first()
                                
                                releve_soumis = releve is not None
                        except Exception as e:
                            releve_soumis = False
                
                releves_soumis_matieres[matiere] = releve_soumis
                
                if notes_valeurs:
                    moyenne_matiere = sum(notes_valeurs) / len(notes_valeurs)
                    moyennes_matieres[matiere] = round(moyenne_matiere, 2)
                    notes_trimestre.extend(notes_valeurs)
            
            # Compter le nombre de relevés soumis pour ce trimestre
            nb_releves_soumis = sum(1 for soumis in releves_soumis_matieres.values() if soumis)
            
            # Moyenne générale du trimestre
            if notes_trimestre:
                moyenne_generale = sum(notes_trimestre) / len(notes_trimestre)
                moyennes_par_trimestre[trimestre] = {
                    'moyennes_matieres': moyennes_matieres,
                    'moyenne_generale': round(moyenne_generale, 2),
                    'nb_releves_soumis': nb_releves_soumis
                }
                releves_soumis_par_trimestre[trimestre] = releves_soumis_matieres
    
    # Récupérer les sanctions de l'élève filtrées par année scolaire active
    sanctions_eleve_qs = Sanction.objects.filter(eleve=eleve).select_related('professeur', 'classe')
    if annee_scolaire_active:
        sanctions_eleve_qs = sanctions_eleve_qs.filter(annee_scolaire=annee_scolaire_active)
    sanctions_eleve = sanctions_eleve_qs.order_by('-date_sanction', '-date_creation')
    
    # Statistiques des sanctions par gravité
    stats_sanctions = {
        'total': sanctions_eleve.count(),
        'legeres': sanctions_eleve.filter(gravite='legere').count(),
        'moyennes': sanctions_eleve.filter(gravite='moyenne').count(),
        'graves': sanctions_eleve.filter(gravite__in=['grave', 'tres_grave']).count(),
    }
    
    # Récupérer les informations du parent inscripteur
    from ..model.parent_model import Parent
    from ..model.lien_familial_model import LienFamilial
    
    parent_inscripteur = None
    lien_inscripteur = None
    
    try:
        # Chercher le lien familial avec le parent inscripteur
        lien_inscripteur = LienFamilial.objects.filter(
            eleve=eleve,
            statut='valide'
        ).select_related('parent').first()
        
        if lien_inscripteur:
            parent_inscripteur = lien_inscripteur.parent
    except Exception as e:
        print(f"[DEBUG] Erreur lors de la récupération du parent inscripteur : {e}")
        parent_inscripteur = None
    
    form_data = {}
    field_errors = {}
    photo_form_errors = []
    photo_modal_open = False

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile_update')

        if form_type == 'photo_upload':
            photo_modal_open = True
            uploaded_file = request.FILES.get('photo_fichier') or request.FILES.get('photo_camera')
            source_choice = request.POST.get('photo_source', '').strip()

            if not source_choice:
                photo_form_errors.append("Veuillez choisir un mode d'ajout de photo.")

            if not uploaded_file:
                photo_form_errors.append("Veuillez fournir une image valide.")
            else:
                content_type = uploaded_file.content_type or ''
                if not content_type.startswith('image/'):
                    photo_form_errors.append("Le fichier doit être une image (JPEG, PNG, WEBP...).")

                max_size = 5 * 1024 * 1024
                if uploaded_file.size and uploaded_file.size > max_size:
                    photo_form_errors.append("La taille de l'image ne doit pas dépasser 5 Mo.")

            if not photo_form_errors and uploaded_file:
                try:
                    with transaction.atomic():
                        if eleve.photo_profil:
                            eleve.photo_profil.delete(save=False)
                        eleve.photo_profil = uploaded_file
                        eleve.save(update_fields=['photo_profil', 'date_modification'])
                    messages.success(request, "La photo de l'élève a été mise à jour avec succès.")
                    return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
                except Exception as exc:
                    photo_form_errors.append(f"Une erreur est survenue lors de l'enregistrement de la photo : {exc}.")

        else:
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'date_naissance': request.POST.get('date_naissance', ''),
                'lieu_naissance': request.POST.get('lieu_naissance', '').strip(),
                'sexe': request.POST.get('sexe', ''),
                'nationalite': request.POST.get('nationalite', '').strip(),
                'adresse': request.POST.get('adresse', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'classe': request.POST.get('classe', ''),
                'date_inscription': request.POST.get('date_inscription', ''),
                'statut': request.POST.get('statut', ''),
                # Champs parent/tuteur
                'parent_nom': request.POST.get('parent_nom', '').strip(),
                'parent_prenom': request.POST.get('parent_prenom', '').strip(),
                # Pour le téléphone parent, utiliser le numéro formaté (parent_telephone_full) s'il existe, sinon utiliser parent_telephone
                'parent_telephone': request.POST.get('parent_telephone_full', '').strip() or request.POST.get('parent_telephone', '').strip(),
                'parent_email': request.POST.get('parent_email', '').strip(),
                'parent_adresse': request.POST.get('parent_adresse', '').strip(),
                'parent_profession': request.POST.get('parent_profession', '').strip(),
                'parent_lien': request.POST.get('parent_lien', ''),
                # Documents d'identité
                'document_acte_naissance': request.POST.get('document_acte_naissance') == 'true',
                'document_cni': request.POST.get('document_cni') == 'true',
                'document_passeport': request.POST.get('document_passeport') == 'true',
                # Documents scolaires
                'document_bulletin_precedent': request.POST.get('document_bulletin_precedent') == 'true',
                'document_certificat_scolarite': request.POST.get('document_certificat_scolarite') == 'true',
                'document_livret_scolaire': request.POST.get('document_livret_scolaire') == 'true',
                # Documents médicaux
                'document_certificat_medical': request.POST.get('document_certificat_medical') == 'true',
                'document_carnet_vaccination': request.POST.get('document_carnet_vaccination') == 'true',
                'document_assurance_maladie': request.POST.get('document_assurance_maladie') == 'true',
                # Documents administratifs
                'document_justificatif_domicile': request.POST.get('document_justificatif_domicile') == 'true',
                'document_photo_identite': request.POST.get('document_photo_identite') == 'true',
                'document_autorisation_parentale': request.POST.get('document_autorisation_parentale') == 'true',
            }

            # Validation
            is_valid = True
            inscription_date_obj = None

            # Champs obligatoires
            required_fields = ['nom', 'prenom', 'date_naissance', 'lieu_naissance', 'sexe', 'nationalite']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False

            # Validation des champs parent/tuteur
            parent_required = ['parent_nom', 'parent_prenom', 'parent_telephone', 'parent_lien']
            for field in parent_required:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False

            # Validation de la date de naissance
            if form_data['date_naissance']:
                try:
                    birth_date = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
                    if birth_date > date.today():
                        field_errors['date_naissance'] = "La date de naissance ne peut pas être dans le futur."
                        is_valid = False
                except ValueError:
                    field_errors['date_naissance'] = "Format de date invalide."
                    is_valid = False

            # Validation de la date d'inscription
            if form_data['date_inscription']:
                try:
                    inscription_date = datetime.strptime(form_data['date_inscription'], '%Y-%m-%d').date()
                    inscription_date_obj = inscription_date
                    if inscription_date > date.today():
                        field_errors['date_inscription'] = "La date d'inscription ne peut pas être dans le futur."
                        is_valid = False
                except ValueError:
                    field_errors['date_inscription'] = "Format de date invalide."
                    is_valid = False

            # Validation de la classe
            classe_obj = None
            if form_data['classe']:
                try:
                    classe_obj = Classe.objects.get(id=form_data['classe'], etablissement=etablissement)
                except Classe.DoesNotExist:
                    field_errors['classe'] = "La classe sélectionnée n'existe pas."
                    is_valid = False

            # Validation du statut
            if form_data['statut'] and form_data['statut'] not in ['nouvelle', 'transfert', 'reinscription']:
                field_errors['statut'] = "Le type d'inscription sélectionné n'est pas valide."
                is_valid = False

            # Validation des emails
            if form_data['email'] and '@' not in form_data['email']:
                field_errors['email'] = "L'adresse email n'est pas valide."
                is_valid = False

            # Validation de l'email parent/tuteur (optionnel)
            if form_data['parent_email'] and '@' not in form_data['parent_email']:
                field_errors['parent_email'] = "L'adresse email du parent/tuteur n'est pas valide."
                is_valid = False

            # Validation du lien parent/tuteur
            if form_data['parent_lien'] and form_data['parent_lien'] not in ['pere', 'mere', 'grand_parent', 'oncle_tante', 'frere_soeur', 'autre_famille', 'tuteur_legal', 'autre']:
                field_errors['parent_lien'] = "Le lien avec l'élève sélectionné n'est pas valide."
                is_valid = False

            # Si tout est valide, sauvegarder les modifications
            if is_valid:
                try:
                    with transaction.atomic():
                        # Formater les noms et prénoms
                        nom_formate = formater_nom(form_data['nom'])
                        prenom_formate = formater_prenom(form_data['prenom'])
                        parent_nom_formate = formater_nom(form_data['parent_nom'])
                        parent_prenom_formate = formater_prenom(form_data['parent_prenom'])
                        
                        # Mettre à jour les informations de base de l'élève
                        eleve.nom = nom_formate
                        eleve.prenom = prenom_formate
                        eleve.date_naissance = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
                        eleve.lieu_naissance = form_data['lieu_naissance']
                        eleve.sexe = form_data['sexe']
                        eleve.nationalite = form_data['nationalite']
                        eleve.adresse = form_data['adresse'] if form_data['adresse'] else None
                        eleve.telephone = form_data['telephone'] if form_data['telephone'] else None
                        eleve.email = form_data['email'] if form_data['email'] else None

                        # Mettre à jour la classe et le statut si fournis
                        if classe_obj:
                            eleve.classe = classe_obj
                        if form_data['date_inscription']:
                            eleve.date_inscription = inscription_date_obj
                        if form_data['statut']:
                            eleve.statut = form_data['statut']

                        # Mettre à jour les informations parent/tuteur dans l'élève
                        eleve.parent_nom = parent_nom_formate
                        eleve.parent_prenom = parent_prenom_formate
                        eleve.parent_telephone = form_data['parent_telephone']
                        eleve.parent_email = form_data['parent_email'] if form_data['parent_email'] else None
                        eleve.parent_adresse = form_data['parent_adresse'] if form_data['parent_adresse'] else None
                        eleve.parent_profession = form_data['parent_profession'] if form_data['parent_profession'] else None
                        eleve.parent_lien = form_data['parent_lien']

                        # Mettre à jour les documents
                        eleve.document_acte_naissance = form_data['document_acte_naissance']
                        eleve.document_cni = form_data['document_cni']
                        eleve.document_passeport = form_data['document_passeport']
                        eleve.document_bulletin_precedent = form_data['document_bulletin_precedent']
                        eleve.document_certificat_scolarite = form_data['document_certificat_scolarite']
                        eleve.document_livret_scolaire = form_data['document_livret_scolaire']
                        eleve.document_certificat_medical = form_data['document_certificat_medical']
                        eleve.document_carnet_vaccination = form_data['document_carnet_vaccination']
                        eleve.document_assurance_maladie = form_data['document_assurance_maladie']
                        eleve.document_justificatif_domicile = form_data['document_justificatif_domicile']
                        eleve.document_photo_identite = form_data['document_photo_identite']
                        eleve.document_autorisation_parentale = form_data['document_autorisation_parentale']

                        # Sauvegarder l'élève
                        eleve.save()

                        # Mettre à jour ou créer le compte Parent
                        from ..model.parent_model import Parent
                        from ..model.lien_familial_model import LienFamilial
                        
                        # Vérifier si un parent avec ce téléphone existe déjà
                        parent_existant = None
                        if form_data['parent_telephone']:
                            parent_existant = Parent.objects.filter(
                                telephone=form_data['parent_telephone'],
                                etablissement=etablissement
                            ).first()
                        
                        if parent_existant:
                            # Utiliser le parent existant et mettre à jour ses informations
                            parent = parent_existant
                            parent.nom = parent_nom_formate
                            parent.prenom = parent_prenom_formate
                            parent.telephone = form_data['parent_telephone']
                            parent.email = form_data['parent_email'] if form_data['parent_email'] else ''
                            parent.adresse = form_data['parent_adresse'] if form_data['parent_adresse'] else ''
                            parent.profession = form_data['parent_profession'] if form_data['parent_profession'] else ''
                            # Mettre à jour le type_parent selon le lien
                            if form_data['parent_lien'] in ['mere', 'pere', 'tuteur']:
                                parent.type_parent = form_data['parent_lien']
                            else:
                                parent.type_parent = 'tuteur'
                            parent.save()
                        else:
                            # Créer un nouveau compte parent si nécessaire
                            matricule_parent = Parent.generer_matricule_parent(etablissement)
                            mot_de_passe_parent = Parent.generer_mot_de_passe()
                            
                            parent = Parent(
                                matricule_parental=matricule_parent,
                                type_parent=form_data['parent_lien'] if form_data['parent_lien'] in ['mere', 'pere', 'tuteur'] else 'tuteur',
                                nom=parent_nom_formate,
                                prenom=parent_prenom_formate,
                                telephone=form_data['parent_telephone'],
                                email=form_data['parent_email'] if form_data['parent_email'] else '',
                                adresse=form_data['parent_adresse'] if form_data['parent_adresse'] else '',
                                profession=form_data['parent_profession'] if form_data['parent_profession'] else '',
                                etablissement=etablissement,
                                mot_de_passe_provisoire=mot_de_passe_parent,
                                mot_de_passe_modifie=False,
                                username=matricule_parent,
                                is_active=True,
                                is_staff=False,
                                is_superuser=False,
                            )
                            parent.set_password(mot_de_passe_parent)
                            parent.save()
                        
                        # Créer ou mettre à jour le lien familial
                        lien_familial, created = LienFamilial.objects.update_or_create(
                            parent=parent,
                            eleve=eleve,
                            defaults={
                                'type_lien': form_data['parent_lien'] if form_data['parent_lien'] in ['mere', 'pere', 'tuteur'] else 'tuteur',
                                'statut': 'valide',
                                'est_inscripteur': True,
                                'actif': True,
                            }
                        )
                        
                        # Mettre à jour ou créer InscriptionEleve pour l'année scolaire active
                        if annee_scolaire_active:
                            inscription_eleve, _ = InscriptionEleve.objects.update_or_create(
                                eleve=eleve,
                                annee_scolaire=annee_scolaire_active,
                                defaults={
                                    'nom': form_data['nom'],
                                    'prenom': form_data['prenom'],
                                    'date_naissance': datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date(),
                                    'lieu_naissance': form_data['lieu_naissance'],
                                    'sexe': form_data['sexe'],
                                    'nationalite': form_data['nationalite'],
                                    'adresse': form_data['adresse'] if form_data['adresse'] else None,
                                    'telephone': form_data['telephone'] if form_data['telephone'] else None,
                                    'email': form_data['email'] if form_data['email'] else None,
                                    'numero_eleve': eleve.numero_eleve,
                                    'matricule_eleve': eleve.matricule_eleve,
                                    'etablissement': etablissement,
                                    'classe': classe_obj if classe_obj else eleve.classe,
                                    'date_inscription': inscription_date_obj if inscription_date_obj else eleve.date_inscription,
                                    'statut': form_data['statut'] if form_data['statut'] else eleve.statut,
                                    'parent_nom': form_data['parent_nom'],
                                    'parent_prenom': form_data['parent_prenom'],
                                    'parent_telephone': form_data['parent_telephone'],
                                    'parent_email': form_data['parent_email'] if form_data['parent_email'] else None,
                                    'parent_adresse': form_data['parent_adresse'] if form_data['parent_adresse'] else None,
                                    'parent_profession': form_data['parent_profession'] if form_data['parent_profession'] else None,
                                    'parent_lien': form_data['parent_lien'],
                                    'document_acte_naissance': form_data['document_acte_naissance'],
                                    'document_cni': form_data['document_cni'],
                                    'document_passeport': form_data['document_passeport'],
                                    'document_bulletin_precedent': form_data['document_bulletin_precedent'],
                                    'document_certificat_scolarite': form_data['document_certificat_scolarite'],
                                    'document_livret_scolaire': form_data['document_livret_scolaire'],
                                    'document_certificat_medical': form_data['document_certificat_medical'],
                                    'document_carnet_vaccination': form_data['document_carnet_vaccination'],
                                    'document_assurance_maladie': form_data['document_assurance_maladie'],
                                    'document_justificatif_domicile': form_data['document_justificatif_domicile'],
                                    'document_photo_identite': form_data['document_photo_identite'],
                                    'document_autorisation_parentale': form_data['document_autorisation_parentale'],
                                }
                            )
                            
                            # Mettre à jour ou créer InscriptionParent pour l'année scolaire active
                            type_parent = parent.type_parent if parent.type_parent in ['mere', 'pere', 'tuteur'] else 'tuteur'
                            inscription_parent, _ = InscriptionParent.objects.update_or_create(
                                parent=parent,
                                annee_scolaire=annee_scolaire_active,
                                defaults={
                                    'nom': parent.nom,
                                    'prenom': parent.prenom,
                                    'telephone': parent.telephone,
                                    'email': parent.email,
                                    'type_parent': type_parent,
                                    'adresse': parent.adresse,
                                    'profession': parent.profession,
                                    'etablissement': etablissement,
                                    'matricule_parental': parent.matricule_parental,
                                    'date_inscription': inscription_date_obj if inscription_date_obj else eleve.date_inscription,
                                }
                            )

                        messages.success(request, f"Les informations de {eleve.prenom} {eleve.nom} ont été mises à jour avec succès !")
                        return redirect('secretaire:detail_eleve', eleve_id=eleve.id)

                except Exception as e:
                    field_errors['__all__'] = f"Une erreur est survenue lors de la modification: {str(e)}. Veuillez réessayer."
                    is_valid = False
    else:
        # Remplir le formulaire avec les données depuis InscriptionEleve et InscriptionParent (priorité)
        # Si pas d'inscription pour l'année active, utiliser les données de l'élève
        inscription_eleve_data = None
        inscription_parent_data = None
        
        # Récupérer les données d'inscription pour l'année scolaire active
        if annee_scolaire_active:
            try:
                inscription_eleve_data = InscriptionEleve.objects.get(
                    eleve=eleve,
                    annee_scolaire=annee_scolaire_active,
                    etablissement=etablissement
                )
            except InscriptionEleve.DoesNotExist:
                inscription_eleve_data = None
            
            # Récupérer les données du parent depuis InscriptionParent
            if parent_inscripteur:
                try:
                    inscription_parent_data = InscriptionParent.objects.get(
                        parent=parent_inscripteur,
                        annee_scolaire=annee_scolaire_active,
                        etablissement=etablissement
                    )
                except InscriptionParent.DoesNotExist:
                    inscription_parent_data = None
        
        # Utiliser les données d'inscription si disponibles, sinon utiliser les données de l'élève
        if inscription_eleve_data:
            form_data = {
                'nom': inscription_eleve_data.nom,
                'prenom': inscription_eleve_data.prenom,
                'date_naissance': inscription_eleve_data.date_naissance.strftime('%Y-%m-%d') if inscription_eleve_data.date_naissance else '',
                'lieu_naissance': inscription_eleve_data.lieu_naissance or '',
                'sexe': inscription_eleve_data.sexe,
                'nationalite': inscription_eleve_data.nationalite or '',
                'adresse': inscription_eleve_data.adresse or '',
                'telephone': inscription_eleve_data.telephone or '',
                'email': inscription_eleve_data.email or '',
                'classe': inscription_eleve_data.classe.id if inscription_eleve_data.classe else '',
                'date_inscription': inscription_eleve_data.date_inscription.strftime('%Y-%m-%d') if inscription_eleve_data.date_inscription else '',
                'statut': inscription_eleve_data.statut,
                # Champs parent/tuteur depuis InscriptionEleve
                'parent_nom': inscription_eleve_data.parent_nom or '',
                'parent_prenom': inscription_eleve_data.parent_prenom or '',
                'parent_telephone': inscription_eleve_data.parent_telephone or '',
                'parent_email': inscription_eleve_data.parent_email or '',
                'parent_adresse': inscription_eleve_data.parent_adresse or '',
                'parent_profession': inscription_eleve_data.parent_profession or '',
                'parent_lien': inscription_eleve_data.parent_lien or '',
                # Documents depuis InscriptionEleve
                'document_acte_naissance': inscription_eleve_data.document_acte_naissance,
                'document_cni': inscription_eleve_data.document_cni,
                'document_passeport': inscription_eleve_data.document_passeport,
                'document_bulletin_precedent': inscription_eleve_data.document_bulletin_precedent,
                'document_certificat_scolarite': inscription_eleve_data.document_certificat_scolarite,
                'document_livret_scolaire': inscription_eleve_data.document_livret_scolaire,
                'document_certificat_medical': inscription_eleve_data.document_certificat_medical,
                'document_carnet_vaccination': inscription_eleve_data.document_carnet_vaccination,
                'document_assurance_maladie': inscription_eleve_data.document_assurance_maladie,
                'document_justificatif_domicile': inscription_eleve_data.document_justificatif_domicile,
                'document_photo_identite': inscription_eleve_data.document_photo_identite,
                'document_autorisation_parentale': inscription_eleve_data.document_autorisation_parentale,
            }
            
            # Si on a aussi les données du parent depuis InscriptionParent, les utiliser pour compléter
            if inscription_parent_data:
                form_data['parent_nom'] = inscription_parent_data.nom or form_data['parent_nom']
                form_data['parent_prenom'] = inscription_parent_data.prenom or form_data['parent_prenom']
                form_data['parent_telephone'] = inscription_parent_data.telephone or form_data['parent_telephone']
                form_data['parent_email'] = inscription_parent_data.email or form_data['parent_email']
                form_data['parent_adresse'] = inscription_parent_data.adresse or form_data['parent_adresse']
                form_data['parent_profession'] = inscription_parent_data.profession or form_data['parent_profession']
        else:
            # Utiliser les données de l'élève si pas d'inscription
            form_data = {
                'nom': eleve.nom,
                'prenom': eleve.prenom,
                'date_naissance': eleve.date_naissance.strftime('%Y-%m-%d') if eleve.date_naissance else '',
                'lieu_naissance': eleve.lieu_naissance or '',
                'sexe': eleve.sexe,
                'nationalite': eleve.nationalite or '',
                'adresse': eleve.adresse or '',
                'telephone': eleve.telephone or '',
                'email': eleve.email or '',
                'classe': eleve.classe.id if eleve.classe else '',
                'date_inscription': eleve.date_inscription.strftime('%Y-%m-%d') if eleve.date_inscription else '',
                'statut': eleve.statut,
                # Champs parent/tuteur
                'parent_nom': eleve.parent_nom or '',
                'parent_prenom': eleve.parent_prenom or '',
                'parent_telephone': eleve.parent_telephone or '',
                'parent_email': eleve.parent_email or '',
                'parent_adresse': eleve.parent_adresse or '',
                'parent_profession': eleve.parent_profession or '',
                'parent_lien': eleve.parent_lien or '',
                # Documents
                'document_acte_naissance': eleve.document_acte_naissance,
                'document_cni': eleve.document_cni,
                'document_passeport': eleve.document_passeport,
                'document_bulletin_precedent': eleve.document_bulletin_precedent,
                'document_certificat_scolarite': eleve.document_certificat_scolarite,
                'document_livret_scolaire': eleve.document_livret_scolaire,
                'document_certificat_medical': eleve.document_certificat_medical,
                'document_carnet_vaccination': eleve.document_carnet_vaccination,
                'document_assurance_maladie': eleve.document_assurance_maladie,
                'document_justificatif_domicile': eleve.document_justificatif_domicile,
                'document_photo_identite': eleve.document_photo_identite,
                'document_autorisation_parentale': eleve.document_autorisation_parentale,
            }
    
    # Récupérer la liste des pays pour le select
    try:
        pays_list = [(code, str(nom)) for code, nom in countries]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la récupération des pays: {str(e)}")
        pays_list = []
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'eleve': eleve_display,  # Utiliser le proxy avec la classe et le statut de l'année scolaire active
        'classes': classes,
        'form_data': form_data,
        'field_errors': field_errors,
        'presences_par_mois': dict(presences_par_mois),
        'stats_presences_par_mois': stats_presences_par_mois,
        'notes_par_trimestre': dict(notes_par_trimestre),
        'moyennes_par_trimestre': moyennes_par_trimestre,
        'releves_soumis_par_trimestre': releves_soumis_par_trimestre,
        'sanctions_eleve': sanctions_eleve,
        'stats_sanctions': stats_sanctions,
        # Ajouts secondaires
        'is_secondaire': etablissement.type_etablissement in ['lycée', 'collège', 'collège_lycée'],
        'matieres_classe': matieres_classe,
        'moyennes_par_matiere': moyennes_par_matiere,
        'periode_active_notes': periode_active_notes,
        'periodes_actives': periodes_actives,
        'moyennes_par_periode': dict(moyennes_par_periode),
        'photo_form_errors': photo_form_errors,
        'photo_modal_open': photo_modal_open,
        # Informations du parent inscripteur
        'parent_inscripteur': parent_inscripteur,
        'lien_inscripteur': lien_inscripteur,
        'annee_scolaire_active': annee_scolaire_active,
        'pays_list': pays_list,
        # Permissions pour masquer les onglets
        'can_view_presences': isinstance(user, Etablissement) or (isinstance(user, PersonnelAdministratif) and check_permission(user, 'presences_detail')),
        'can_view_notes': isinstance(user, Etablissement) or (isinstance(user, PersonnelAdministratif) and check_permission(user, 'notes_detail')),
        'can_view_sanctions': isinstance(user, Etablissement) or (isinstance(user, PersonnelAdministratif) and check_permission(user, 'sanctions_detail')),
    }
    
    return render(request, 'school_admin/directeur/secretaire/detail_eleve.html', context)


@login_required
def transfer_eleve(request, eleve_id):
    """
    Transfert d'un élève vers une autre classe (secrétaire ou directeur)
    Prend en compte l'année scolaire active pour mettre à jour l'InscriptionEleve
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'année scolaire active ou consultée
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(
            request,
            "Aucune année scolaire active n'a été trouvée. Créez ou activez d'abord une session pour continuer."
        )
        return redirect('secretaire:detail_eleve', eleve_id=eleve_id)
    
    try:
        # Récupérer l'élève
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:liste_eleves')
    
    if request.method == 'POST':
        nouvelle_classe_id = request.POST.get('new_class')
        raison_transfert = request.POST.get('transfer_reason', '').strip()
        
        if not nouvelle_classe_id:
            messages.error(request, "Veuillez sélectionner une classe de destination.")
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
        
        try:
            nouvelle_classe = Classe.objects.get(id=nouvelle_classe_id, etablissement=etablissement)
            
            # Récupérer l'inscription de l'élève pour l'année scolaire active
            try:
                inscription_eleve = InscriptionEleve.objects.get(
                    eleve=eleve,
                    annee_scolaire=annee_scolaire_active,
                    etablissement=etablissement
                )
                ancienne_classe_inscription = inscription_eleve.classe
            except InscriptionEleve.DoesNotExist:
                messages.error(
                    request,
                    f"L'élève n'a pas d'inscription pour l'année scolaire active ({annee_scolaire_active.libelle}). "
                    "Veuillez d'abord inscrire l'élève pour cette année."
                )
                return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
            
            # Vérifier si c'est la même classe
            if nouvelle_classe.id == ancienne_classe_inscription.id:
                messages.warning(request, f"L'élève est déjà dans la classe {nouvelle_classe.nom} pour cette année scolaire.")
                return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
            
            # Vérifier les places disponibles
            places_disponibles = nouvelle_classe.places_disponibles
            if places_disponibles <= 0:
                messages.error(
                    request, 
                    f"[ERREUR] Transfert impossible : La classe {nouvelle_classe.nom} est pleine. "
                    f"Capacité : {nouvelle_classe.capacite_max}/{nouvelle_classe.capacite_max} élèves. "
                    f"Aucune place disponible."
                )
                return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
            
            # Avertissement si il ne reste qu'une place
            if places_disponibles == 1:
                messages.warning(
                    request, 
                    f"[ATTENTION] Il ne reste qu'une place disponible dans la classe {nouvelle_classe.nom}."
                )
            
            # Effectuer le transfert avec transaction atomique
            from django.db import transaction
            
            with transaction.atomic():
                # Mettre à jour l'inscription de l'élève pour l'année scolaire active
                inscription_eleve.classe = nouvelle_classe
                inscription_eleve.save()
                
                # Mettre à jour aussi la classe de l'élève (pour compatibilité)
                ancienne_classe = eleve.classe
                eleve.classe = nouvelle_classe
                eleve.save()
            
            # Message de succès
            messages.success(
                request, 
                f"[SUCCES] Transfert réussi : {eleve.nom_complet} a été transféré de {ancienne_classe_inscription.nom} vers {nouvelle_classe.nom} "
                f"pour l'année scolaire {annee_scolaire_active.libelle}. "
                f"Places restantes : {nouvelle_classe.places_disponibles - 1}/{nouvelle_classe.capacite_max}"
            )
            
            # Log du transfert (optionnel)
            if raison_transfert:
                messages.info(request, f"Raison du transfert: {raison_transfert}")
            
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
            
        except Classe.DoesNotExist:
            messages.error(request, "La classe sélectionnée n'existe pas.")
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
        except Exception as e:
            messages.error(request, f"Une erreur est survenue lors du transfert: {str(e)}")
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
    
    # Redirection si accès GET direct
    return redirect('secretaire:detail_eleve', eleve_id=eleve_id)


@login_required
def desactiver_compte_eleve(request, eleve_id):
    """
    Désactive ou réactive le compte d'un élève
    """
    from django.contrib import messages
    from django.shortcuts import redirect, get_object_or_404
    
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un directeur soit un personnel avec la permission
    if isinstance(user, Etablissement):
        etablissement = user
    elif isinstance(user, PersonnelAdministratif):
        # Vérifier la permission eleves_modifier
        from ..utils.decorators_permissions import check_permission
        if not check_permission(user, 'eleves_modifier'):
            messages.error(request, "Accès non autorisé. Vous n'avez pas la permission de modifier les élèves.")
            return redirect('directeur:dashboard_directeur')
        etablissement = user.etablissement
    else:
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'élève
    eleve = get_object_or_404(Eleve, id=eleve_id, etablissement=etablissement)
    
    # Inverser le statut actif
    eleve.actif = not eleve.actif
    eleve.is_active = eleve.actif  # Synchroniser avec is_active
    eleve.save(update_fields=['actif', 'is_active'])
    
    # Message de confirmation
    if eleve.actif:
        messages.success(request, f"Le compte de {eleve.nom_complet} a été réactivé avec succès.")
    else:
        messages.success(request, f"Le compte de {eleve.nom_complet} a été désactivé avec succès.")
    
    return redirect('secretaire:detail_eleve', eleve_id=eleve_id)


@login_required
def gestion_classes(request):
    """
    Page de gestion des classes pour le secrétaire ou le directeur
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'année scolaire active ou consultée
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Calculer les statistiques en filtrant par année scolaire active
    total_eleves = 0
    total_capacite = sum(classe.capacite_max for classe in classes)
    
    # Préparer les données pour chaque classe
    classes_data = []
    for classe in classes:
        # Filtrer les élèves par année scolaire active via InscriptionEleve
        if annee_scolaire_active:
            eleves_count = InscriptionEleve.objects.filter(
                classe=classe,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active
            ).count()
        else:
            eleves_count = classe.eleves.filter(actif=True).count()
        
        total_eleves += eleves_count
        
        classes_data.append({
            'classe': classe,
            'eleves_count': eleves_count,
            'places_disponibles': classe.places_disponibles,
            'taux_occupation': classe.taux_occupation,
            'statut_capacite': 'pleine' if classe.places_disponibles == 0 else 'libre' if classe.places_disponibles == classe.capacite_max else 'partielle',
        })
    
    # Statistiques des classes
    stats_classes = {
        'total_classes': classes.count(),
        'total_capacite': total_capacite,
        'total_eleves': total_eleves,
        'taux_occupation_moyen': 0,
    }
    
    if stats_classes['total_capacite'] > 0:
        stats_classes['taux_occupation_moyen'] = round(
            (stats_classes['total_eleves'] / stats_classes['total_capacite']) * 100, 1
        )
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'classes_data': classes_data,
        'stats_classes': stats_classes,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/secretaire/gestion_classes.html', context)


@login_required
def detail_classe(request, classe_id):
    """
    Page de détails d'une classe avec liste des élèves (secrétaire ou directeur)
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer la classe
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement, actif=True)
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('secretaire:gestion_classes')
    
    # Récupérer l'année scolaire active ou consultée
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    # Récupérer les élèves de la classe filtrés par année scolaire active
    from django.db.models.functions import Lower
    if annee_scolaire_active:
        # Filtrer via InscriptionEleve pour l'année scolaire active
        eleves_ids_inscrits = InscriptionEleve.objects.filter(
            annee_scolaire=annee_scolaire_active,
            classe=classe,
            etablissement=etablissement
        ).values_list('eleve_id', flat=True)
        eleves = Eleve.objects.filter(
            id__in=eleves_ids_inscrits,
            classe=classe,
            actif=True
        ).order_by(Lower('nom'), Lower('prenom'))
    else:
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by(Lower('nom'), Lower('prenom'))
    
    # Statistiques de la classe
    stats_classe = {
        'total_eleves': eleves.count(),
        'nouveaux_eleves': eleves.filter(statut='nouvelle').count(),
        'transferts': eleves.filter(statut='transfert').count(),
        'reinscriptions': eleves.filter(statut='reinscription').count(),
        'taux_occupation': classe.taux_occupation,
        'places_disponibles': classe.places_disponibles,
        'capacite_max': classe.capacite_max,
    }
    
    # Statistiques par sexe
    stats_sexe = {
        'masculin': eleves.filter(sexe='M').count(),
        'feminin': eleves.filter(sexe='F').count(),
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'classe': classe,
        'eleves': eleves,
        'stats_classe': stats_classe,
        'stats_sexe': stats_sexe,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/secretaire/detail_classe.html', context)


@login_required
def imprimer_liste_eleves(request, classe_id):
    """
    Page d'impression de la liste des élèves d'une classe (secrétaire ou directeur)
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer la classe
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement, actif=True)
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('secretaire:gestion_classes')
    
    # Récupérer l'année scolaire active ou consultée
    from ..utils.session_utils import get_session_active, get_session_consultee, get_session_consultee
    from ..model.inscription_eleve_model import InscriptionEleve
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'imprimer la liste des élèves.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    # Filtrer les élèves par année scolaire active via InscriptionEleve
    eleves_ids_inscrits = InscriptionEleve.objects.filter(
        annee_scolaire=annee_scolaire_active,
        classe=classe,
        etablissement=etablissement
    ).values_list('eleve_id', flat=True)
    
    # Récupérer les élèves de la classe filtrés par année scolaire active
    from django.db.models.functions import Lower
    eleves = Eleve.objects.filter(
        id__in=eleves_ids_inscrits,
        classe=classe,
        actif=True
    ).order_by(Lower('nom'), Lower('prenom'))
    
    # Informations de l'établissement
    etablissement_info = {
        'nom': etablissement.nom,
        'type': etablissement.get_type_etablissement_display(),
        'code': etablissement.code_etablissement,
        'adresse': etablissement.adresse,
        'ville': etablissement.ville,
        'pays': etablissement.pays,
        'telephone': etablissement.telephone,
        'email': etablissement.email,
    }
    
    # Informations de la classe
    classe_info = {
        'nom': classe.nom,
        'niveau': classe.get_niveau_display(),
        'capacite_max': classe.capacite_max,
        'total_eleves': eleves.count(),
        'places_disponibles': classe.places_disponibles,
        'taux_occupation': classe.taux_occupation,
        'description': classe.description,
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'etablissement_info': etablissement_info,
        'classe': classe,
        'classe_info': classe_info,
        'eleves': eleves,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/directeur/secretaire/imprimer_liste_eleves.html', context)


@login_required
def desactiver_eleve(request, eleve_id):
    """
    Désactiver un élève et mettre à jour la facturation (secrétaire ou directeur)
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer l'élève
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:liste_eleves')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Désactiver l'élève
                eleve.actif = False
                eleve.save()
                
                # Mettre à jour les données de facturation de l'établissement
                montant_par_eleve = etablissement.montant_par_eleve
                
                # Décrémenter le nombre d'élèves facturés
                if etablissement.nombre_eleves_factures > 0:
                    etablissement.nombre_eleves_factures -= 1
                
                # Décrémenter le montant total de facturation
                if etablissement.montant_total_facturation >= montant_par_eleve:
                    etablissement.montant_total_facturation -= montant_par_eleve
                
                # Mettre à jour la date de dernière facturation
                etablissement.date_derniere_facturation = timezone.now()
                
                # Sauvegarder les modifications de l'établissement
                etablissement.save()
                
                messages.success(request, f"L'élève {eleve.nom_complet} a été désactivé avec succès. Montant déduit: {montant_par_eleve} FCFA.")
                return redirect('secretaire:liste_eleves')
                
        except Exception as e:
            messages.error(request, f"Une erreur est survenue lors de la désactivation: {str(e)}")
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'eleve': eleve,
    }
    
    return render(request, 'school_admin/directeur/secretaire/confirmer_desactivation_eleve.html', context)


@login_required
def supprimer_eleve(request, eleve_id):
    """
    Supprimer définitivement un élève (secrétaire ou directeur)
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer l'élève
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:liste_eleves')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupérer les informations avant suppression
                eleve_nom = eleve.nom_complet
                montant_par_eleve = etablissement.montant_par_eleve
                
                # Supprimer définitivement l'élève
                eleve.delete()
                
                # Mettre à jour les données de facturation de l'établissement
                # Décrémenter le nombre d'élèves facturés
                if etablissement.nombre_eleves_factures > 0:
                    etablissement.nombre_eleves_factures -= 1
                
                # Décrémenter le montant total de facturation
                if etablissement.montant_total_facturation >= montant_par_eleve:
                    etablissement.montant_total_facturation -= montant_par_eleve
                
                # Mettre à jour la date de dernière facturation
                etablissement.date_derniere_facturation = timezone.now()
                
                # Sauvegarder les modifications de l'établissement
                etablissement.save()
                
                messages.success(request, f"L'élève {eleve_nom} a été supprimé définitivement. Montant déduit: {montant_par_eleve} FCFA.")
                return redirect('secretaire:liste_eleves')
                
        except Exception as e:
            messages.error(request, f"Une erreur est survenue lors de la suppression: {str(e)}")
            return redirect('secretaire:liste_eleves')
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'eleve': eleve,
    }
    
    return render(request, 'school_admin/directeur/secretaire/confirmer_suppression_eleve.html', context)


@login_required
def synchroniser_facturation(request):
    """
    Synchroniser les données de facturation avec les élèves actifs (secrétaire ou directeur)
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire ou un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'année scolaire active ou consultée
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant de synchroniser la facturation.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Compter les élèves actifs filtrés par année scolaire active via InscriptionEleve
                eleves_actifs = InscriptionEleve.objects.filter(
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active
                ).count()
                montant_par_eleve = etablissement.montant_par_eleve
                montant_total_calcule = eleves_actifs * montant_par_eleve
                
                # Mettre à jour les données de facturation
                etablissement.nombre_eleves_factures = eleves_actifs
                etablissement.montant_total_facturation = montant_total_calcule
                etablissement.date_derniere_facturation = timezone.now()
                etablissement.save()
                
                devise = etablissement.devise_monnaie if hasattr(etablissement, 'devise_monnaie') and etablissement.devise_monnaie else ''
                devise_text = f" {devise}" if devise else ""
                messages.success(
                    request, 
                    f"Synchronisation réussie ! "
                    f"Élèves actifs: {eleves_actifs}, "
                    f"Montant total: {montant_total_calcule}{devise_text}"
                )
                return redirect('secretaire:dashboard_secretaire')
                
        except Exception as e:
            messages.error(request, f"Erreur lors de la synchronisation: {str(e)}")
            return redirect('secretaire:dashboard_secretaire')
    
    # Statistiques actuelles filtrées par année scolaire active
    eleves_actifs = InscriptionEleve.objects.filter(
        etablissement=etablissement,
        annee_scolaire=annee_scolaire_active
    ).count()
    montant_par_eleve = etablissement.montant_par_eleve
    montant_total_calcule = eleves_actifs * montant_par_eleve
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'is_directeur': isinstance(user, Etablissement),
        'is_personnel_administratif': isinstance(user, PersonnelAdministratif),
        'personnel': user if isinstance(user, PersonnelAdministratif) else None,
        'eleves_actifs': eleves_actifs,
        'montant_par_eleve': montant_par_eleve,
        'montant_total_calcule': montant_total_calcule,
        'montant_actuel': etablissement.montant_total_facturation,
        'nombre_actuel': etablissement.nombre_eleves_factures,
        'annee_scolaire_active': annee_scolaire_active,
        'devise_etablissement': etablissement.devise_monnaie if hasattr(etablissement, 'devise_monnaie') and etablissement.devise_monnaie else None,
    }
    
    return render(request, 'school_admin/directeur/secretaire/synchroniser_facturation.html', context)


@login_required
def get_notes_detail_matiere(request, eleve_id, matiere_id):
    """
    Vue AJAX pour récupérer les notes détaillées d'un élève pour une matière spécifique
    Uniquement pour les établissements de type secondaire (lycée, collège, lycée+collège)
    """
    from django.http import JsonResponse
    from ..model.eleve_model import Eleve
    from ..model.matiere_model import Matiere
    from ..model.evaluation_model import Note
    from ..model.note_examen_model import NoteExamen
    from ..model.moyenne_model import Moyenne
    from ..model.periode_model import PeriodeScolaire
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..model.etablissement_model import Etablissement
    
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est soit un secrétaire soit un directeur
    if isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    elif isinstance(user, Etablissement):
        etablissement = user
    else:
        return JsonResponse({'error': 'Accès non autorisé'}, status=403)
    
    # Vérifier que l'établissement est de type secondaire
    if etablissement.type_etablissement not in ['lycée', 'collège', 'collège_lycée']:
        return JsonResponse({'error': 'Cette fonctionnalité est réservée aux établissements secondaires'}, status=403)
    
    # Récupérer l'année scolaire active ou consultée
    from ..utils.session_utils import get_session_active, get_session_consultee, get_session_consultee
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    try:
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
        matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
        
        # Récupérer la période depuis les paramètres GET ou utiliser la période active
        periode_id = request.GET.get('periode_id')
        if periode_id:
            try:
                periode_qs = PeriodeScolaire.objects.filter(id=int(periode_id), etablissement=etablissement)
                if annee_scolaire_active:
                    periode_qs = periode_qs.filter(annee_scolaire_fk=annee_scolaire_active)
                periode_active = periode_qs.first()
                if not periode_active:
                    raise PeriodeScolaire.DoesNotExist
            except (PeriodeScolaire.DoesNotExist, ValueError):
                # Utiliser la première période active de l'année scolaire active
                periode_qs = PeriodeScolaire.objects.filter(
                    etablissement=etablissement,
                    est_active=True
                )
                if annee_scolaire_active:
                    periode_qs = periode_qs.filter(annee_scolaire_fk=annee_scolaire_active)
                periode_active = periode_qs.order_by('date_debut').first()
        else:
            # Utiliser la première période active de l'année scolaire active
            periode_qs = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True
            )
            if annee_scolaire_active:
                periode_qs = periode_qs.filter(annee_scolaire_fk=annee_scolaire_active)
            periode_active = periode_qs.order_by('date_debut').first()
        
        if not periode_active:
            return JsonResponse({'error': 'Aucune période active trouvée'}, status=404)
        
        # Récupérer toutes les notes de devoirs/interrogations retenues pour cette matière
        notes_devoirs_qs = Note.objects.filter(
            eleve=eleve,
            evaluation__matiere=matiere,
            evaluation__periode_scolaire=periode_active,
            retenue=True
        )
        # Filtrer par année scolaire active si disponible
        if annee_scolaire_active:
            notes_devoirs_qs = notes_devoirs_qs.filter(annee_scolaire=annee_scolaire_active)
        notes_devoirs = notes_devoirs_qs.select_related('evaluation').order_by('evaluation__date_evaluation')
        
        # Récupérer la note d'examen
        note_examen_qs = NoteExamen.objects.filter(
            eleve=eleve,
            matiere=matiere,
            session_examen__periode=periode_active
        )
        # Filtrer par année scolaire active si disponible
        if annee_scolaire_active:
            note_examen_qs = note_examen_qs.filter(annee_scolaire=annee_scolaire_active)
        note_examen = note_examen_qs.select_related('session_examen').first()
        
        # Récupérer la moyenne
        moyenne_qs = Moyenne.objects.filter(
            eleve=eleve,
            matiere=matiere,
            periode=str(periode_active.id),
            actif=True
        )
        # Filtrer par année scolaire active si disponible
        if annee_scolaire_active:
            moyenne_qs = moyenne_qs.filter(annee_scolaire=annee_scolaire_active)
        moyenne_obj = moyenne_qs.first()
        
        # Construire la réponse
        notes_data = []
        for note in notes_devoirs:
            notes_data.append({
                'type': 'Devoir' if note.evaluation.bareme == 20 else 'Interrogation',
                'titre': note.evaluation.titre,
                'date': note.evaluation.date_evaluation.strftime('%d/%m/%Y') if note.evaluation.date_evaluation else '',
                'note': str(note.note) if not note.absent else None,
                'bareme': str(note.evaluation.bareme),
                'absent': note.absent,
                'note_sur_20': float(note.note_sur_20) if not note.absent else None
            })
        
        examen_data = None
        if note_examen and not note_examen.absent:
            examen_data = {
                'note': float(note_examen.note),
                'bareme': 20,
                'nom_examen': note_examen.session_examen.nom_examen if note_examen.session_examen else 'Examen'
            }
        
        response_data = {
            'success': True,
            'eleve': {
                'nom': eleve.nom,
                'prenom': eleve.prenom,
                'nom_complet': eleve.nom_complet
            },
            'matiere': {
                'nom': matiere.nom
            },
            'notes_devoirs': notes_data,
            'note_examen': examen_data,
            'moyenne': float(moyenne_obj.moyenne) if moyenne_obj and moyenne_obj.moyenne else None,
            'soumis': moyenne_obj.soumis if moyenne_obj else False
        }
        
        return JsonResponse(response_data)
        
    except Eleve.DoesNotExist:
        return JsonResponse({'error': 'Élève non trouvé'}, status=404)
    except Matiere.DoesNotExist:
        return JsonResponse({'error': 'Matière non trouvée'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def soumettre_sanction_directeur(request):
    """
    Traite le formulaire de soumission d'une sanction par le directeur
    """
    if request.method != 'POST':
        messages.error(request, "Méthode non autorisée.")
        return redirect('secretaire:liste_eleves')
    
    # Vérifier que l'utilisateur est un directeur
    user = request.user
    if not isinstance(user, Etablissement):
        messages.error(request, "Accès non autorisé. Vous devez être un directeur.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = user
    from ..model.eleve_model import Eleve
    from ..model.classe_model import Classe
    from ..model.sanction_model import Sanction
    from django.shortcuts import get_object_or_404
    
    # Récupérer l'année scolaire active ou consultée
    if isinstance(user, Etablissement):
        annee_scolaire_active = get_session_consultee(request, etablissement)
    else:
        annee_scolaire_active = get_session_active(request, etablissement)
    
    if not annee_scolaire_active:
        messages.error(request, "Aucune année scolaire active. Veuillez créer et activer une année scolaire avant d'ajouter une sanction.")
        return redirect('directeur:creer_annee_scolaire_obligatoire')
    
    # Récupérer les données du formulaire
    eleve_id = request.POST.get('eleve_id')
    classe_id = request.POST.get('classe_id')
    type_sanction = request.POST.get('type_sanction')
    raison = request.POST.get('raison')
    gravite = request.POST.get('gravite', 'moyenne')
    description = request.POST.get('description', '')
    date_sanction_str = request.POST.get('date_sanction')
    
    # Validation des données
    if not all([eleve_id, classe_id, type_sanction, raison, date_sanction_str]):
        messages.error(request, "Tous les champs obligatoires doivent être remplis.")
        return redirect('secretaire:liste_eleves')
    
    try:
        # Récupérer l'élève et la classe
        eleve = get_object_or_404(Eleve, id=eleve_id, actif=True, etablissement=etablissement)
        classe = get_object_or_404(Classe, id=classe_id, actif=True, etablissement=etablissement)
        
        # Convertir la date
        date_sanction = datetime.strptime(date_sanction_str, '%Y-%m-%d').date()
        
        # Créer la sanction avec l'année scolaire active
        sanction = Sanction.objects.create(
            eleve=eleve,
            classe=classe,
            professeur=None,  # Pas de professeur car c'est le directeur
            etablissement=etablissement,
            type_sanction=type_sanction,
            raison=raison,
            gravite=gravite,
            description=description,
            date_sanction=date_sanction,
            attribue_par_type='directeur',
            attribue_par_nom=f"{etablissement.directeur_prenom} {etablissement.directeur_nom}",
            annee_scolaire=annee_scolaire_active
        )
        
        messages.success(request, f"Sanction enregistrée avec succès pour {eleve.nom_complet}.")
        
    except Exception as e:
        messages.error(request, f"Erreur lors de l'enregistrement de la sanction : {str(e)}")
    
    return redirect('secretaire:liste_eleves')


