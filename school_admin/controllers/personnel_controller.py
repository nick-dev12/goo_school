# school_admin/controllers/personnel_controller.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from django.template.loader import render_to_string
import logging
import random
import string

from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.etablissement_model import Etablissement

logger = logging.getLogger(__name__)


class PersonnelController:
    """
    Contrôleur pour gérer le personnel administratif
    """
    
    @staticmethod
    def categoriser_personnel(personnel_queryset):
        """
        Catégorise le personnel par type de fonction
        """
        categories = {
            'direction': {'label': 'Direction', 'icon': 'fa-user-tie', 'personnel': []},
            'censeurs': {'label': 'Censeurs', 'icon': 'fa-chalkboard-teacher', 'personnel': []},
            'surveillants': {'label': 'Surveillants', 'icon': 'fa-eye', 'personnel': []},
            'administration': {'label': 'Administration', 'icon': 'fa-briefcase', 'personnel': []},
            'autres': {'label': 'Autres', 'icon': 'fa-users-cog', 'personnel': []},
        }
        
        # Fonctions par catégorie
        fonctions_direction = [
            'directeur_adjoint_primaire', 'principal_adjoint',
            'proviseur_adjoint', 'directeur_principal',
            'directeur_section_primaire', 'principal_section_college', 'proviseur_section_lycee'
        ]
        
        fonctions_censeurs = [
            'censeur', 'censeur_etudes', 'censeur_adjoint',
            'censeur_premier_cycle', 'censeur_second_cycle',
            'censeur_pedagogie', 'censeur_vie_scolaire'
        ]
        
        fonctions_surveillants = [
            'surveillant_general'
        ]
        
        fonctions_administration = [
            'secretaire_principal', 'gestionnaire', 'secretaire_vie_scolaire'
        ]
        
        # Catégoriser chaque personnel
        for personnel in personnel_queryset:
            if personnel.fonction in fonctions_direction:
                categories['direction']['personnel'].append(personnel)
            elif personnel.fonction in fonctions_censeurs:
                categories['censeurs']['personnel'].append(personnel)
            elif personnel.fonction in fonctions_surveillants:
                categories['surveillants']['personnel'].append(personnel)
            elif personnel.fonction in fonctions_administration:
                categories['administration']['personnel'].append(personnel)
            else:
                categories['autres']['personnel'].append(personnel)
        
        return categories
    
    @staticmethod
    def get_fonctions_par_type_etablissement(type_etablissement):
        """
        Retourne les fonctions disponibles selon le type d'établissement
        """
        fonctions = {
            'primary': [
                ('directeur_adjoint_primaire', 'Directeur Adjoint (École Primaire)'),
                ('secretaire_principal', 'Secrétaire Principal'),
                ('gestionnaire', 'Gestionnaire'),
                ('surveillant_general', 'Surveillant Général'),
            ],
            'collège': [
                ('principal_adjoint', 'Principal Adjoint (Collège)'),
                ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
                ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
                ('censeur_premier_cycle', 'Censeur du Premier Cycle (6e à 3e)'),
                ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
                ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
                ('surveillant_general', 'Surveillant Général'),
                ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
            ],
            'lycée': [
                ('proviseur_adjoint', 'Proviseur Adjoint (Lycée)'),
                ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
                ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
                ('censeur_second_cycle', 'Censeur du Second Cycle (2nde à Tle)'),
                ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
                ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
                ('surveillant_general', 'Surveillant Général'),
                ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
            ],
            'collège_lycée': [
                # Direction
                ('principal_adjoint', 'Principal Adjoint (Collège)'),
                ('proviseur_adjoint', 'Proviseur Adjoint (Lycée)'),
                # Administration
                ('secretaire_principal', 'Secrétaire Principal'),
                # Pédagogie - Censeurs
                ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
                ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
                ('censeur_premier_cycle', 'Censeur du Premier Cycle (6e à 3e)'),
                ('censeur_second_cycle', 'Censeur du Second Cycle (2nde à Tle)'),
                ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
                ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
                # Vie Scolaire
                ('surveillant_general', 'Surveillant Général'),
                ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
            ],
            'mixte': [
                # Direction générale
                ('directeur_principal', 'Directeur Principal (Établissement Mixte)'),
                ('directeur_section_primaire', 'Directeur de Section Primaire'),
                ('principal_section_college', 'Principal de Section Collège'),
                ('proviseur_section_lycee', 'Proviseur de Section Lycée'),
                # Direction spécifiques
                ('directeur_adjoint_primaire', 'Directeur Adjoint (École Primaire)'),
                ('principal_adjoint', 'Principal Adjoint (Collège)'),
                ('proviseur_adjoint', 'Proviseur Adjoint (Lycée)'),
                # Administration
                ('secretaire_principal', 'Secrétaire Principal'),
                ('gestionnaire', 'Gestionnaire'),
                # Pédagogie - Censeurs
                ('censeur', 'Censeur'),
                ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
                ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
                ('censeur_premier_cycle', 'Censeur du Premier Cycle (6e à 3e)'),
                ('censeur_second_cycle', 'Censeur du Second Cycle (2nde à Tle)'),
                ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
                ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
                # Vie Scolaire
                ('surveillant_general', 'Surveillant Général'),
                ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
            ],
        }
        
        # Ajouter l'administrateur système à tous les types
        for type_etab in fonctions:
            fonctions[type_etab].append(('administrateur', 'Administrateur Système'))
        
        return fonctions.get(type_etablissement, [])
    
    @staticmethod
    def generate_mot_de_passe_provisoire():
        """
        Génère un mot de passe provisoire de 6 chiffres
        """
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    @staticmethod
    def generate_numero_employe(fonction, etablissement):
        """
        Génère un numéro d'employé unique basé sur le rôle et l'établissement
        """
        # Préfixes selon le rôle
        prefixes = {
            # Direction
            'directeur_adjoint_primaire': 'DIR-ADJ',
            'principal_adjoint': 'PRI-ADJ',
            'proviseur_adjoint': 'PROV-ADJ',
            'directeur_principal': 'DIR-P',
            'directeur_section_primaire': 'DIR-SEC',
            'principal_section_college': 'PRI-SEC',
            'proviseur_section_lycee': 'PROV-SEC',
            # Administration
            'secretaire_principal': 'SEC-P',
            'gestionnaire': 'GES',
            # Pédagogie
            'censeur': 'CEN',
            'censeur_etudes': 'CEN-ET',
            'censeur_adjoint': 'CEN-ADJ',
            'censeur_premier_cycle': 'CEN-C1',
            'censeur_second_cycle': 'CEN-C2',
            'censeur_pedagogie': 'CEN-PED',
            'censeur_vie_scolaire': 'CEN-VS',
            # Vie Scolaire
            'surveillant_general': 'SG',
            'secretaire_vie_scolaire': 'SEC-VS',
            # Autres
            'administrateur': 'ADM',
        }
        
        prefix = prefixes.get(fonction, 'EMP')
        code_etab = etablissement.code_etablissement[:3]  # 3 premiers caractères du code établissement
        
        # Générer un numéro séquentiel
        count = PersonnelAdministratif.objects.filter(
            etablissement=etablissement,
            fonction=fonction
        ).count() + 1
        
        numero = f"{prefix}-{code_etab}-{count:03d}"
        
        # Vérifier l'unicité
        while PersonnelAdministratif.objects.filter(numero_employe=numero).exists():
            count += 1
            numero = f"{prefix}-{code_etab}-{count:03d}"
        
        return numero
    
    @staticmethod
    def generate_username(nom, prenom, etablissement):
        """
        Génère un nom d'utilisateur unique
        """
        # Créer un username basé sur le prénom et nom
        base_username = f"{prenom.lower()}.{nom.lower()}"
        username = base_username
        
        # Vérifier l'unicité et ajouter un suffixe si nécessaire
        counter = 1
        while PersonnelAdministratif.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        return username
    
    @staticmethod
    @login_required
    def liste_personnel(request):
        """
        Affiche la liste du personnel administratif et des professeurs de l'établissement
        """
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = request.user
        
        # Récupérer le personnel administratif de l'établissement
        personnel = PersonnelAdministratif.objects.filter(
            etablissement=etablissement
        ).order_by('-date_creation')
        
        # Catégoriser le personnel
        categories_personnel = PersonnelController.categoriser_personnel(personnel)
        
        # Récupérer les professeurs de l'établissement
        from ..model.professeur_model import Professeur
        from django.db.models.functions import Lower
        professeurs = Professeur.objects.filter(
            etablissement=etablissement
        ).select_related('matiere_principale').order_by(Lower('nom'), Lower('prenom'))
        
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
        
        # Statistiques générales
        stats = {
            'total_personnel': personnel.count(),
            'total_professeurs': professeurs.count(),
            'total_actifs': personnel.filter(actif=True).count() + professeurs.filter(actif=True).count(),
            'total_inactifs': personnel.filter(actif=False).count() + professeurs.filter(actif=False).count(),
            'par_role': {}
        }
        
        # Compter par rôle pour le personnel administratif
        for fonction, label in PersonnelAdministratif.TYPE_FONCTION_CHOICES:
            count = personnel.filter(fonction=fonction).count()
            if count > 0:
                stats['par_role'][label] = count
        
        # Ajouter les professeurs aux statistiques
        if professeurs.count() > 0:
            stats['par_role']['Professeurs'] = professeurs.count()
        
        # Récupérer les données du formulaire depuis la session (si erreur lors de l'ajout)
        form_data = request.session.get('form_data_personnel', {})
        field_errors = request.session.get('field_errors_personnel', {})
        
        # Récupérer les fonctions disponibles pour le formulaire d'ajout
        type_etab = etablissement.type_etablissement
        type_variants_map = {
            'lycee': 'lycée',
            'lycée': 'lycée',
            'college': 'collège',
            'collège': 'collège',
            'college_lycee': 'collège_lycée',
            'collège_lycée': 'collège_lycée',
            'primary': 'primary',
            'mixte': 'mixte',
        }
        type_normalise = type_variants_map.get(type_etab, type_etab)
        fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(type_normalise)
        
        if not fonctions_disponibles:
            fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(type_etab)
        
        # Récupérer les permissions disponibles
        from ..utils.permissions_personnel import get_permissions_disponibles, get_permissions_par_fonction
        permissions_par_categorie = get_permissions_disponibles()
        
        # Si une fonction est sélectionnée, récupérer ses permissions par défaut
        permissions_defaut = []
        if form_data.get('fonction'):
            permissions_defaut = get_permissions_par_fonction(form_data['fonction'])
        
        context = {
            'personnel': personnel,
            'categories_personnel': categories_personnel,
            'professeurs': professeurs,
            'matieres_avec_compteurs': matieres_avec_compteurs,
            'etablissement': etablissement,
            'stats': stats,
            'form_data': form_data,
            'field_errors': field_errors,
            'fonctions_disponibles': fonctions_disponibles,
            'permissions_par_categorie': permissions_par_categorie,
            'permissions_defaut': permissions_defaut,
        }
        
        # Nettoyer la session après utilisation
        if 'form_data_personnel' in request.session:
            del request.session['form_data_personnel']
        if 'field_errors_personnel' in request.session:
            del request.session['field_errors_personnel']
        
        return render(request, 'school_admin/directeur/personnel/liste_personnel.html', context)
    
    @staticmethod
    @login_required
    def ajouter_personnel(request):
        """
        Affiche le formulaire d'ajout de personnel et traite la soumission
        """
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = request.user
        form_data = {}
        field_errors = {}
        
        if request.method == 'POST':
            # Récupération des données
            # Utiliser telephone_full si disponible (format avec indicatif), sinon telephone
            telephone_value = request.POST.get('telephone_full', '').strip()
            if not telephone_value:
                telephone_value = request.POST.get('telephone', '').strip()
            
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': telephone_value,
                'fonction': request.POST.get('fonction', ''),
            }
            
            # Validation
            is_valid = True
            
            # Normaliser le type d'établissement pour la recherche des fonctions
            type_etab = etablissement.type_etablissement
            type_variants_map = {
                'lycee': 'lycée',
                'lycée': 'lycée',
                'college': 'collège',
                'collège': 'collège',
                'college_lycee': 'collège_lycée',
                'collège_lycée': 'collège_lycée',
                'primary': 'primary',
                'mixte': 'mixte',
            }
            type_normalise = type_variants_map.get(type_etab, type_etab)
            
            # Récupérer les fonctions valides pour ce type d'établissement
            fonctions_valides = PersonnelController.get_fonctions_par_type_etablissement(type_normalise)
            
            # Si toujours vide, essayer avec le type original
            if not fonctions_valides:
                fonctions_valides = PersonnelController.get_fonctions_par_type_etablissement(type_etab)
            
            fonctions_valides_codes = [f[0] for f in fonctions_valides]
            
            # Champs obligatoires (email n'est plus obligatoire)
            required_fields = ['nom', 'prenom', 'telephone', 'fonction']
            for field in required_fields:
                if not form_data[field]:
                    field_name = field.replace('_', ' ').title()
                    if field == 'telephone':
                        field_name = 'Téléphone'
                    field_errors[field] = f"Le champ {field_name} est obligatoire."
                    is_valid = False
            
            # Validation de l'email (seulement si fourni)
            if form_data['email']:
                if '@' not in form_data['email']:
                    field_errors['email'] = "L'adresse email n'est pas valide."
                    is_valid = False
                # Vérification de l'unicité de l'email seulement si fourni
                elif PersonnelAdministratif.objects.filter(email=form_data['email']).exists():
                    field_errors['email'] = "Cette adresse email est déjà utilisée."
                    is_valid = False
            
            # Validation du type de personnel selon le type d'établissement
            if form_data['fonction'] and form_data['fonction'] not in fonctions_valides_codes:
                field_errors['fonction'] = f"Cette fonction n'est pas disponible pour un établissement de type {etablissement.get_type_etablissement_display()}."
                is_valid = False
            
            # Récupérer les autorisations depuis le formulaire
            autorisations = {}
            from ..utils.permissions_personnel import get_permissions_par_fonction, PERMISSIONS_DISPONIBLES
            
            # Récupérer les permissions par défaut pour la fonction
            permissions_defaut = get_permissions_par_fonction(form_data['fonction'])
            
            # Récupérer les permissions sélectionnées dans le formulaire
            for perm_key in PERMISSIONS_DISPONIBLES.keys():
                # Si la permission est dans les permissions par défaut, elle est activée par défaut
                if perm_key in permissions_defaut:
                    autorisations[perm_key] = request.POST.get(f'permission_{perm_key}', 'off') == 'on'
                else:
                    # Sinon, elle est désactivée par défaut
                    autorisations[perm_key] = request.POST.get(f'permission_{perm_key}', 'off') == 'on'
            
            # Si il y a des erreurs, stocker dans la session et rediriger
            if not is_valid:
                request.session['form_data_personnel'] = form_data
                request.session['field_errors_personnel'] = field_errors
                return redirect('personnel:liste_personnel')
            
            # Si tout est valide, créer le personnel
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer le numéro d'employé (code unique)
                        numero_employe = PersonnelController.generate_numero_employe(
                            form_data['fonction'], 
                            etablissement
                        )
                        
                        # Générer un identifiant de connexion unique basé sur le numéro d'employé
                        # Format: [XX]PERS[6 chiffres] où XX = initiales établissement
                        mots = etablissement.nom.split()[:2]
                        initiales = ''.join([mot[0].upper() for mot in mots if mot])
                        
                        import random
                        import time
                        max_tentatives = 1000
                        tentatives = 0
                        username = None
                        
                        while True:
                            # Générer un numéro aléatoire de 6 chiffres
                            numero_aleatoire_6 = random.randint(100000, 999999)
                            username = f"{initiales}PERS{numero_aleatoire_6}"
                            
                            # Vérifier l'unicité
                            if not PersonnelAdministratif.objects.filter(username=username).exists() and \
                               not PersonnelAdministratif.objects.filter(numero_employe=username).exists():
                                break
                            
                            tentatives += 1
                            if tentatives >= max_tentatives:
                                # Fallback avec timestamp
                                timestamp = int(time.time() * 1000) % 1000000
                                username = f"{initiales}PERS{timestamp:06d}"
                                if not PersonnelAdministratif.objects.filter(username=username).exists() and \
                                   not PersonnelAdministratif.objects.filter(numero_employe=username).exists():
                                    break
                                raise RuntimeError("Impossible de générer un identifiant unique pour le personnel après de nombreuses tentatives.")
                        
                        # Générer le mot de passe provisoire
                        mot_de_passe = PersonnelController.generate_mot_de_passe_provisoire()
                        
                        # Créer le personnel
                        # Email peut être vide (optionnel) - utiliser None au lieu de chaîne vide
                        email_value = form_data['email'] if form_data['email'] else None
                        
                        personnel = PersonnelAdministratif(
                            nom=form_data['nom'],
                            prenom=form_data['prenom'],
                            email=email_value,  # None si non fourni
                            telephone=form_data['telephone'],  # Contient déjà l'indicatif si telephone_full était fourni
                            fonction=form_data['fonction'],
                            username=username,
                            numero_employe=numero_employe,
                            etablissement=etablissement,
                            mot_de_passe_provisoire=mot_de_passe,
                            permissions=autorisations,  # Enregistrer les autorisations
                        )
                        
                        # Définir le mot de passe (haché)
                        personnel.set_password(mot_de_passe)
                        personnel.save()
                        
                        messages.success(
                            request, 
                            f"Le personnel {personnel.nom_complet} a été ajouté avec succès ! Identifiant: {username} | Mot de passe provisoire: {mot_de_passe}"
                        )
                        
                        return redirect('personnel:liste_personnel')
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout du personnel: {str(e)}")
                    field_errors['__all__'] = [f"Une erreur est survenue lors de l'ajout du personnel: {str(e)}"]
                    is_valid = False
                    request.session['form_data_personnel'] = form_data
                    request.session['field_errors_personnel'] = field_errors
                    return redirect('personnel:liste_personnel')
        
        # Récupérer les fonctions disponibles selon le type d'établissement
        type_etab = etablissement.type_etablissement
        logger.info(f"Type d'établissement récupéré: '{type_etab}' pour l'établissement {etablissement.nom}")
        
        # Normaliser le type d'établissement pour gérer les variantes (sans accent, avec accent, etc.)
        type_normalise = type_etab
        type_variants_map = {
            'lycee': 'lycée',
            'lycée': 'lycée',
            'college': 'collège',
            'collège': 'collège',
            'college_lycee': 'collège_lycée',
            'collège_lycée': 'collège_lycée',
            'primary': 'primary',
            'mixte': 'mixte',
        }
        
        # Normaliser le type (gérer les cas sans accent)
        if type_etab in type_variants_map:
            type_normalise = type_variants_map[type_etab]
        elif type_etab.lower() in [k.lower() for k in type_variants_map.keys()]:
            # Essayer avec une comparaison insensible à la casse
            for key, value in type_variants_map.items():
                if key.lower() == type_etab.lower():
                    type_normalise = value
                    break
        
        # Récupérer les fonctions avec le type normalisé
        fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(type_normalise)
        
        # Si toujours vide, essayer avec le type original
        if not fonctions_disponibles and type_normalise != type_etab:
            logger.warning(f"Essai avec le type original: '{type_etab}'")
            fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(type_etab)
        
        # Si toujours vide, essayer tous les types possibles pour debug
        if not fonctions_disponibles:
            logger.error(f"Type d'établissement non reconnu: '{type_etab}' (normalisé: '{type_normalise}')")
            # Essayer tous les types pour voir lequel fonctionne
            for test_type in ['primary', 'collège', 'lycée', 'collège_lycée', 'mixte']:
                test_fonctions = PersonnelController.get_fonctions_par_type_etablissement(test_type)
                if test_fonctions:
                    logger.info(f"Type '{test_type}' a {len(test_fonctions)} fonctions")
            fonctions_disponibles = []
        
        logger.info(f"Nombre de fonctions disponibles pour '{type_etab}': {len(fonctions_disponibles)}")
        
        # Récupérer les permissions disponibles organisées par catégorie
        from ..utils.permissions_personnel import get_permissions_disponibles, get_permissions_par_fonction
        permissions_par_categorie = get_permissions_disponibles()
        
        # Si une fonction est sélectionnée, récupérer ses permissions par défaut
        permissions_defaut = []
        if form_data.get('fonction'):
            permissions_defaut = get_permissions_par_fonction(form_data['fonction'])
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'etablissement': etablissement,
            'fonctions_disponibles': fonctions_disponibles,
            'permissions_par_categorie': permissions_par_categorie,
            'permissions_defaut': permissions_defaut,
        }
        
        # Rediriger vers la liste du personnel (le formulaire est intégré dans la page)
        return redirect('personnel:liste_personnel')
    
    @staticmethod
    @login_required
    def get_permissions_par_fonction(request):
        """
        Retourne les permissions par défaut pour une fonction donnée (AJAX)
        """
        from django.http import JsonResponse
        
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            return JsonResponse({'success': False, 'message': 'Accès non autorisé.'}, status=403)
        
        fonction = request.GET.get('fonction', '')
        if not fonction:
            return JsonResponse({'success': False, 'message': 'Fonction non fournie.'}, status=400)
        
        from ..utils.permissions_personnel import get_permissions_par_fonction
        permissions = get_permissions_par_fonction(fonction)
        
        return JsonResponse({
            'success': True,
            'permissions': permissions
        })
    
    @staticmethod
    @login_required
    def detail_personnel(request, personnel_id):
        """
        Affiche les détails d'un membre du personnel avec onglets
        """
        from ..model.etablissement_model import Etablissement
        from ..model.personnel_administratif_model import PersonnelAdministratif
        from ..utils.decorators_permissions import check_permission
        
        # Vérifier que l'utilisateur est un directeur ou un personnel avec permission
        user = request.user
        if isinstance(user, Etablissement):
            etablissement = user
        elif isinstance(user, PersonnelAdministratif):
            if not check_permission(user, 'personnel_detail'):
                messages.error(request, "Vous n'avez pas la permission de voir les détails du personnel.")
                return redirect('directeur:dashboard_directeur')
            etablissement = user.etablissement
        else:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            personnel = PersonnelAdministratif.objects.get(
                id=personnel_id,
                etablissement=etablissement
            )
        except PersonnelAdministratif.DoesNotExist:
            messages.error(request, "Personnel non trouvé.")
            return redirect('personnel:liste_personnel')
        
        # Récupérer l'onglet actif
        onglet_actif = request.GET.get('onglet', 'informations')
        
        # Récupérer les données du formulaire depuis la session (si erreur lors de la modification)
        form_data_modifier = request.session.get('form_data_personnel_modifier', {})
        field_errors_modifier = request.session.get('field_errors_personnel_modifier', {})
        
        # Nettoyer la session après utilisation
        if 'form_data_personnel_modifier' in request.session:
            del request.session['form_data_personnel_modifier']
        if 'field_errors_personnel_modifier' in request.session:
            del request.session['field_errors_personnel_modifier']
        
        # Récupérer les permissions du personnel
        from ..utils.permissions_personnel import get_permissions_personnel, get_permissions_disponibles, get_permissions_par_fonction
        user_permissions = get_permissions_personnel(personnel)
        permissions_par_categorie = get_permissions_disponibles()
        
        # Récupérer les fonctions disponibles pour le formulaire de modification
        type_etab = etablissement.type_etablissement
        type_variants_map = {
            'lycee': 'lycée',
            'lycée': 'lycée',
            'college': 'collège',
            'collège': 'collège',
            'college_lycee': 'collège_lycée',
            'collège_lycée': 'collège_lycée',
            'primary': 'primary',
            'mixte': 'mixte',
        }
        type_normalise = type_variants_map.get(type_etab, type_etab)
        fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(type_normalise)
        
        if not fonctions_disponibles:
            fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(type_etab)
        
        # Récupérer les permissions actuelles du personnel
        permissions_actuelles = personnel.permissions if personnel.permissions else {}
        # Utiliser la fonction du formulaire si disponible, sinon celle du personnel
        fonction_actuelle = form_data_modifier.get('fonction', personnel.fonction) if form_data_modifier else personnel.fonction
        permissions_defaut = get_permissions_par_fonction(fonction_actuelle)
        
        # Déterminer les permissions à cocher dans le formulaire
        # Si une permission est explicitement dans permissions_actuelles, utiliser sa valeur
        # Sinon, utiliser la valeur par défaut de la fonction
        permissions_combinees = set()
        from ..utils.permissions_personnel import PERMISSIONS_DISPONIBLES
        for perm_key in PERMISSIONS_DISPONIBLES.keys():
            if perm_key in permissions_actuelles:
                # Permission explicitement définie, utiliser sa valeur
                value = permissions_actuelles[perm_key]
                # Convertir en booléen si nécessaire
                if isinstance(value, bool) and value:
                    permissions_combinees.add(perm_key)
                elif isinstance(value, str) and value.lower() in ('true', '1', 'on', 'yes'):
                    permissions_combinees.add(perm_key)
                elif isinstance(value, int) and value == 1:
                    permissions_combinees.add(perm_key)
                # Si False, ne pas l'ajouter (permission désactivée)
            else:
                # Permission non explicitement définie, utiliser la valeur par défaut
                if perm_key in permissions_defaut:
                    permissions_combinees.add(perm_key)
        
        context = {
            'personnel': personnel,
            'etablissement': etablissement,
            'onglet_actif': onglet_actif,
            'user_permissions': user_permissions,
            'permissions_par_categorie': permissions_par_categorie,
            'fonctions_disponibles': fonctions_disponibles,
            'permissions_combinees': permissions_combinees,
            'form_data_modifier': form_data_modifier,
            'field_errors_modifier': field_errors_modifier,
        }
        
        return render(request, 'school_admin/directeur/personnel/detail_personnel.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, personnel_id):
        """
        Active/désactive un membre du personnel
        """
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        try:
            personnel = PersonnelAdministratif.objects.get(
                id=personnel_id,
                etablissement=request.user
            )
            
            personnel.actif = not personnel.actif
            personnel.save()
            
            status = "activé" if personnel.actif else "désactivé"
            messages.success(request, f"{personnel.nom_complet} a été {status}.")
            
        except PersonnelAdministratif.DoesNotExist:
            messages.error(request, "Personnel non trouvé.")
        
        return redirect('personnel:liste_personnel')
    
    @staticmethod
    @login_required
    def modifier_personnel(request, personnel_id):
        """
        Affiche le formulaire de modification du personnel et traite la soumission
        """
        # Vérifier que l'utilisateur est un directeur
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = request.user
        
        try:
            personnel = PersonnelAdministratif.objects.get(
                id=personnel_id,
                etablissement=etablissement
            )
        except PersonnelAdministratif.DoesNotExist:
            messages.error(request, "Personnel non trouvé.")
            return redirect('personnel:liste_personnel')
        
        # Récupérer les fonctions disponibles pour ce type d'établissement
        type_etab = etablissement.type_etablissement
        type_variants_map = {
            'lycee': 'lycée',
            'lycée': 'lycée',
            'college': 'collège',
            'collège': 'collège',
            'college_lycee': 'collège_lycée',
            'collège_lycée': 'collège_lycée',
            'primary': 'primary',
            'mixte': 'mixte',
        }
        type_normalise = type_variants_map.get(type_etab, type_etab)
        fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(type_normalise)
        
        if not fonctions_disponibles:
            fonctions_disponibles = PersonnelController.get_fonctions_par_type_etablissement(type_etab)
        
        # Récupérer les permissions
        from ..utils.permissions_personnel import get_permissions_disponibles, get_permissions_par_fonction
        permissions_par_categorie = get_permissions_disponibles()
        
        # Récupérer les permissions actuelles du personnel
        permissions_actuelles = personnel.permissions if personnel.permissions else {}
        permissions_defaut = get_permissions_par_fonction(personnel.fonction)
        
        # Combiner les permissions par défaut et personnalisées
        permissions_combinees = set(permissions_defaut)
        for key, value in permissions_actuelles.items():
            if value:
                permissions_combinees.add(key)
            else:
                permissions_combinees.discard(key)
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'fonction': request.POST.get('fonction', ''),
            }
            
            # Validation
            is_valid = True
            field_errors = {}
            
            # Champs obligatoires
            required_fields = ['nom', 'prenom', 'email', 'telephone', 'fonction']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation de l'email
            if form_data['email'] and '@' not in form_data['email']:
                field_errors['email'] = "L'adresse email n'est pas valide."
                is_valid = False
            
            # Vérification de l'unicité de l'email (sauf pour le personnel actuel)
            if form_data['email'] and PersonnelAdministratif.objects.filter(email=form_data['email']).exclude(id=personnel_id).exists():
                field_errors['email'] = "Cette adresse email est déjà utilisée."
                is_valid = False
            
            # Validation du type de personnel selon le type d'établissement
            fonctions_valides_codes = [f[0] for f in fonctions_disponibles]
            if form_data['fonction'] and form_data['fonction'] not in fonctions_valides_codes:
                field_errors['fonction'] = f"Cette fonction n'est pas disponible pour un établissement de type {etablissement.get_type_etablissement_display()}."
                is_valid = False
            
            # Récupérer les autorisations depuis le formulaire
            # IMPORTANT: Toutes les permissions doivent être explicitement définies (True ou False)
            # pour permettre la désactivation explicite des permissions
            autorisations = {}
            from ..utils.permissions_personnel import PERMISSIONS_DISPONIBLES
            
            for perm_key in PERMISSIONS_DISPONIBLES.keys():
                # Si la checkbox est cochée, la permission est activée (True)
                # Si la checkbox n'est pas cochée, la permission est désactivée (False)
                # Cela permet de désactiver explicitement les permissions même si elles sont par défaut
                autorisations[perm_key] = request.POST.get(f'permission_{perm_key}', 'off') == 'on'
            
            # Logger pour déboguer (peut être retiré en production)
            logger.info(f"Permissions enregistrées pour {personnel.nom_complet}: {sum(1 for v in autorisations.values() if v)} activées sur {len(autorisations)} totales")
            
            # Si il y a des erreurs, stocker dans la session et rediriger
            if not is_valid:
                request.session['form_data_personnel_modifier'] = form_data
                request.session['field_errors_personnel_modifier'] = field_errors
                return redirect('personnel:detail_personnel', personnel_id=personnel_id)
            
            # Si tout est valide, modifier le personnel
            if is_valid:
                try:
                    with transaction.atomic():
                        # Mettre à jour les informations
                        personnel.nom = form_data['nom']
                        personnel.prenom = form_data['prenom']
                        personnel.email = form_data['email']
                        personnel.telephone = form_data['telephone']
                        personnel.fonction = form_data['fonction']
                        # S'assurer que toutes les permissions sont explicitement définies (True ou False)
                        # Cela permet de désactiver explicitement les permissions qui ne sont plus accordées
                        personnel.permissions = autorisations
                        personnel.save(update_fields=['nom', 'prenom', 'email', 'telephone', 'fonction', 'permissions', 'date_modification'])
                        
                        messages.success(
                            request, 
                            f"Le personnel {personnel.nom_complet} a été modifié avec succès !"
                        )
                        
                        return redirect('personnel:detail_personnel', personnel_id=personnel_id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de la modification du personnel: {str(e)}")
                    field_errors['__all__'] = [f"Une erreur est survenue lors de la modification du personnel: {str(e)}"]
                    is_valid = False
                    request.session['form_data_personnel_modifier'] = form_data
                    request.session['field_errors_personnel_modifier'] = field_errors
                    return redirect('personnel:detail_personnel', personnel_id=personnel_id)
        
        # Rediriger vers la page de détail (le formulaire est intégré dans la page)
        return redirect('personnel:detail_personnel', personnel_id=personnel_id)
