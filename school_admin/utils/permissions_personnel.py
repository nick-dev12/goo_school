# school_admin/utils/permissions_personnel.py
"""
Système de permissions pour le personnel administratif
Définit les autorisations par fonction selon les rôles dans les établissements scolaires
"""

# Définition des permissions disponibles dans le système
PERMISSIONS_DISPONIBLES = {
    # Gestion des élèves
    'eleves_liste': {
        'label': 'Voir la liste des élèves',
        'description': 'Accès à la liste complète des élèves de l\'établissement',
        'category': 'Élèves'
    },
    'eleves_detail': {
        'label': 'Voir les détails d\'un élève',
        'description': 'Accès aux informations détaillées d\'un élève',
        'category': 'Élèves'
    },
    'eleves_modifier': {
        'label': 'Modifier les informations d\'un élève',
        'description': 'Modifier les données personnelles et scolaires d\'un élève',
        'category': 'Élèves'
    },
    'eleves_inscrire': {
        'label': 'Inscrire un nouvel élève',
        'description': 'Créer une nouvelle inscription d\'élève',
        'category': 'Élèves'
    },
    'eleves_transferer': {
        'label': 'Transférer un élève',
        'description': 'Transférer un élève vers une autre classe',
        'category': 'Élèves'
    },
    'eleves_reinscrire': {
        'label': 'Réinscrire un élève',
        'description': 'Réinscrire un élève pour une nouvelle année scolaire',
        'category': 'Élèves'
    },
    
    # Gestion des notes
    'notes_liste': {
        'label': 'Voir la liste des notes',
        'description': 'Accès à la liste des notes et évaluations',
        'category': 'Notes'
    },
    'notes_detail': {
        'label': 'Voir les détails des notes',
        'description': 'Accès aux détails des notes d\'un élève',
        'category': 'Notes'
    },
    'notes_justifications_voir': {
        'label': 'Voir les justifications de notes',
        'description': 'Accès à la page des justifications de notes',
        'category': 'Notes'
    },
    'bulletins_voir': {
        'label': 'Voir les bulletins scolaires',
        'description': 'Accès aux bulletins scolaires des élèves',
        'category': 'Notes'
    },
    
    # Gestion des présences
    'presences_liste': {
        'label': 'Voir la liste des présences',
        'description': 'Accès à la liste des présences et absences',
        'category': 'Présences'
    },
    'presences_detail': {
        'label': 'Voir les détails des présences',
        'description': 'Accès aux détails des présences d\'un élève',
        'category': 'Présences'
    },
    
    # Gestion des sanctions
    'sanctions_liste': {
        'label': 'Voir la liste des sanctions',
        'description': 'Accès à la liste des sanctions disciplinaires',
        'category': 'Sanctions'
    },
    'sanctions_detail': {
        'label': 'Voir les détails d\'une sanction',
        'description': 'Accès aux détails d\'une sanction',
        'category': 'Sanctions'
    },
    'sanctions_creer': {
        'label': 'Créer une sanction',
        'description': 'Créer une nouvelle sanction disciplinaire',
        'category': 'Sanctions'
    },
    'sanctions_modifier': {
        'label': 'Modifier une sanction',
        'description': 'Modifier ou annuler une sanction',
        'category': 'Sanctions'
    },
    
    # Gestion des classes
    'classes_liste': {
        'label': 'Voir la liste des classes',
        'description': 'Accès à la liste des classes',
        'category': 'Classes'
    },
    'classes_detail': {
        'label': 'Voir les détails d\'une classe',
        'description': 'Accès aux détails d\'une classe',
        'category': 'Classes'
    },
    'classes_modifier': {
        'label': 'Modifier les classes',
        'description': 'Modifier les informations d\'une classe',
        'category': 'Classes'
    },
    
    # Gestion des professeurs
    'professeurs_liste': {
        'label': 'Voir la liste des professeurs',
        'description': 'Accès à la liste des professeurs',
        'category': 'Professeurs'
    },
    'professeurs_detail': {
        'label': 'Voir les détails d\'un professeur',
        'description': 'Accès aux détails d\'un professeur',
        'category': 'Professeurs'
    },
    'professeurs_modifier': {
        'label': 'Modifier les professeurs',
        'description': 'Modifier les informations d\'un professeur',
        'category': 'Professeurs'
    },
    
    # Gestion du personnel
    'personnel_liste': {
        'label': 'Voir la liste du personnel',
        'description': 'Accès à la liste du personnel administratif',
        'category': 'Personnel'
    },
    'personnel_detail': {
        'label': 'Voir les détails d\'un membre du personnel',
        'description': 'Accès aux détails d\'un membre du personnel',
        'category': 'Personnel'
    },
    'personnel_modifier': {
        'label': 'Modifier le personnel',
        'description': 'Modifier les informations du personnel',
        'category': 'Personnel'
    },
    
    # Configuration et paramètres
    'config_voir': {
        'label': 'Voir la configuration',
        'description': 'Accès en lecture seule à la configuration',
        'category': 'Configuration'
    },
    'config_modifier': {
        'label': 'Modifier la configuration',
        'description': 'Modifier les paramètres de l\'établissement',
        'category': 'Configuration'
    },
    
    # Gestion administrative
    'administrative_voir': {
        'label': 'Voir la gestion administrative',
        'description': 'Accès à la page de gestion administrative (documents, certificats, etc.)',
        'category': 'Administration'
    },
    
    # Gestion des annonces
    'annonces_voir': {
        'label': 'Voir les annonces',
        'description': 'Accès à la gestion des annonces',
        'category': 'Annonces'
    },
    
    # Gestion des examens
    'examens_voir': {
        'label': 'Voir la gestion des examens',
        'description': 'Accès à la gestion des examens',
        'category': 'Examens'
    },
    
    # Comptabilité
    'comptabilite_voir': {
        'label': 'Accès à la comptabilité',
        'description': 'Accès à la page principale de comptabilité et aux détails financiers des élèves',
        'category': 'Comptabilité'
    },
    'comptabilite_paiements': {
        'label': 'Gérer les paiements de la scolarité',
        'description': 'Effectuer et renseigner les paiements (frais d\'inscription et mensualités)',
        'category': 'Comptabilité'
    },
    'comptabilite_bilans': {
        'label': 'Accès aux bilans comptables',
        'description': 'Accès aux bilans comptables (annuels et par classe)',
        'category': 'Comptabilité'
    },
    'comptabilite_scan_qr': {
        'label': 'Voir la comptabilité via scan QR',
        'description': 'Accès aux informations de comptabilité lors du scan du QR code d\'un élève',
        'category': 'Comptabilité'
    },
}

# Définition des permissions par fonction
PERMISSIONS_PAR_FONCTION = {
    # Direction
    'directeur_adjoint_primaire': [
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_inscrire', 'eleves_transferer',
        'notes_liste', 'notes_detail', 'notes_justifications_voir',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail', 'classes_modifier',
        'professeurs_liste', 'professeurs_detail',
        'personnel_liste', 'personnel_detail',
    ],
    'principal_adjoint': [
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_transferer',
        'notes_liste', 'notes_detail', 'notes_justifications_voir',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
        'personnel_liste', 'personnel_detail',
    ],
    'proviseur_adjoint': [
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_transferer',
        'notes_liste', 'notes_detail', 'notes_justifications_voir',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
        'personnel_liste', 'personnel_detail',
    ],
    'directeur_principal': [
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_inscrire', 'eleves_transferer', 'eleves_reinscrire',
        'notes_liste', 'notes_detail', 'notes_justifications_voir', 'bulletins_voir',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail', 'classes_modifier',
        'professeurs_liste', 'professeurs_detail', 'professeurs_modifier',
        'personnel_liste', 'personnel_detail', 'personnel_modifier',
        'config_voir', 'administrative_voir', 'annonces_voir', 'examens_voir',
    ],
    'directeur_section_primaire': [
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_inscrire', 'eleves_transferer', 'eleves_reinscrire',
        'notes_liste', 'notes_detail', 'bulletins_voir',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail', 'classes_modifier',
        'professeurs_liste', 'professeurs_detail',
    ],
    'principal_section_college': [
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_transferer',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail', 'classes_modifier',
        'professeurs_liste', 'professeurs_detail',
    ],
    'proviseur_section_lycee': [
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_transferer',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail', 'classes_modifier',
        'professeurs_liste', 'professeurs_detail',
    ],
    
    # Censeurs
    'censeur': [
        'eleves_liste', 'eleves_detail',
        'notes_liste', 'notes_detail', 'notes_justifications_voir',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
    ],
    'censeur_etudes': [
        'eleves_liste', 'eleves_detail',
        'notes_liste', 'notes_detail', 'notes_justifications_voir',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
    ],
    'censeur_adjoint': [
        'eleves_liste', 'eleves_detail',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer',
        'classes_liste', 'classes_detail',
    ],
    'censeur_premier_cycle': [
        'eleves_liste', 'eleves_detail',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer',
        'classes_liste', 'classes_detail',
    ],
    'censeur_second_cycle': [
        'eleves_liste', 'eleves_detail',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer',
        'classes_liste', 'classes_detail',
    ],
    'censeur_pedagogie': [
        'eleves_liste', 'eleves_detail',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
    ],
    'censeur_vie_scolaire': [
        'eleves_liste', 'eleves_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail',
    ],
    
    # Secrétaires
    'secretaire_principal': [
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_inscrire', 'eleves_transferer', 'eleves_reinscrire',
        'notes_liste', 'notes_detail', 'bulletins_voir',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
        'personnel_liste', 'personnel_detail',
    ],
    'secretaire_vie_scolaire': [
        'eleves_liste', 'eleves_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer',
        'classes_liste', 'classes_detail',
    ],
    'secretaire': [
        'eleves_liste', 'eleves_detail',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
    ],
    
    # Surveillants
    'surveillant_general': [
        'eleves_liste', 'eleves_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer',
        'classes_liste', 'classes_detail',
    ],
    'surveillant': [
        'eleves_liste', 'eleves_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer',
        'classes_liste', 'classes_detail',
    ],
    
    # Gestionnaire
    'gestionnaire': [
        'eleves_liste', 'eleves_detail',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
        'personnel_liste', 'personnel_detail',
        'comptabilite_voir', 'comptabilite_paiements', 'comptabilite_bilans',  # Accès complet à la comptabilité
    ],
    
    # Comptable
    'comptable': [
        'eleves_liste', 'eleves_detail',
        'comptabilite_voir', 'comptabilite_paiements', 'comptabilite_bilans',  # Accès complet à la comptabilité
        'classes_liste', 'classes_detail',
    ],
    
    # Intendant
    'intendant': [
        'eleves_liste', 'eleves_detail',
        'classes_liste', 'classes_detail',
        'professeurs_liste', 'professeurs_detail',
        'personnel_liste', 'personnel_detail',
    ],
    
    # Autre
    'autre': [
        # Aucune permission par défaut, à configurer manuellement
    ],
    
    # Administrateur système
    'administrateur': [
        # Toutes les permissions
        'eleves_liste', 'eleves_detail', 'eleves_modifier', 'eleves_inscrire', 'eleves_transferer',
        'notes_liste', 'notes_detail',
        'presences_liste', 'presences_detail',
        'sanctions_liste', 'sanctions_detail', 'sanctions_creer', 'sanctions_modifier',
        'classes_liste', 'classes_detail', 'classes_modifier',
        'professeurs_liste', 'professeurs_detail', 'professeurs_modifier',
        'personnel_liste', 'personnel_detail', 'personnel_modifier',
        'config_voir', 'config_modifier',
    ],
}


def get_permissions_par_fonction(fonction):
    """
    Retourne la liste des permissions par défaut pour une fonction donnée
    """
    permissions = PERMISSIONS_PAR_FONCTION.get(fonction, [])
    # Filtrer les chaînes vides
    return [p for p in permissions if p]


def get_permissions_disponibles():
    """
    Retourne toutes les permissions disponibles organisées par catégorie
    """
    permissions_par_categorie = {}
    for key, perm in PERMISSIONS_DISPONIBLES.items():
        category = perm['category']
        if category not in permissions_par_categorie:
            permissions_par_categorie[category] = []
        permissions_par_categorie[category].append({
            'key': key,
            'label': perm['label'],
            'description': perm['description'],
        })
    return permissions_par_categorie


def has_permission(personnel, permission_key):
    """
    Vérifie si un membre du personnel a une permission donnée
    """
    if not personnel or not hasattr(personnel, 'permissions'):
        return False
    
    # Si c'est un établissement (directeur), il a toutes les permissions
    from ..model.etablissement_model import Etablissement
    if isinstance(personnel, Etablissement):
        return True
    
    # Récupérer les permissions du personnel
    # S'assurer que permissions est un dictionnaire
    if not hasattr(personnel, 'permissions') or personnel.permissions is None:
        permissions = {}
    else:
        permissions = personnel.permissions if isinstance(personnel.permissions, dict) else {}
    
    # Si la permission est explicitement définie dans personnel.permissions, utiliser cette valeur
    # Cela permet de respecter les désactivations explicites
    if permission_key in permissions:
        permission_value = permissions[permission_key]
        
        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Permission {permission_key} trouvée dans permissions: {permission_value} (type: {type(permission_value)})")
        
        # Si c'est un booléen False, la permission est refusée
        if isinstance(permission_value, bool):
            logger.info(f"Permission {permission_key} retourne: {permission_value} (booléen)")
            return permission_value
        # Si c'est une chaîne, vérifier les valeurs positives
        if isinstance(permission_value, str):
            result = permission_value.lower() in ('true', '1', 'on', 'yes')
            logger.info(f"Permission {permission_key} retourne: {result} (chaîne: '{permission_value}')")
            return result
        # Si c'est un entier, vérifier si c'est 1
        if isinstance(permission_value, int):
            result = permission_value == 1
            logger.info(f"Permission {permission_key} retourne: {result} (entier: {permission_value})")
            return result
        # Pour toute autre valeur, considérer comme False
        logger.warning(f"Permission {permission_key} a une valeur inattendue: {permission_value} (type: {type(permission_value)})")
        return False
    
    # Si la permission n'est pas explicitement définie, vérifier les permissions par défaut de la fonction
    permissions_defaut = get_permissions_par_fonction(personnel.fonction)
    if permission_key in permissions_defaut:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Permission {permission_key} trouvée dans les permissions par défaut de la fonction {personnel.fonction}")
        return True
    
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Permission {permission_key} non trouvée pour {personnel.username} (fonction: {personnel.fonction})")
    return False


def get_permissions_personnel(personnel):
    """
    Retourne toutes les permissions d'un membre du personnel (défaut + personnalisées)
    """
    if not personnel:
        return []
    
    # Si c'est un établissement (directeur), retourner toutes les permissions
    from ..model.etablissement_model import Etablissement
    if isinstance(personnel, Etablissement):
        return list(PERMISSIONS_DISPONIBLES.keys())
    
    # Récupérer les permissions par défaut de la fonction
    permissions_defaut = set(get_permissions_par_fonction(personnel.fonction))
    
    # Si le personnel a des permissions personnalisées, les utiliser
    if personnel.permissions:
        permissions = set()
        # Parcourir toutes les permissions disponibles
        for key in PERMISSIONS_DISPONIBLES.keys():
            if key in personnel.permissions:
                # Si la permission est explicitement définie, utiliser sa valeur
                value = personnel.permissions[key]
                # Convertir en booléen si nécessaire
                if isinstance(value, bool):
                    if value:
                        permissions.add(key)
                elif isinstance(value, str) and value.lower() in ('true', '1', 'on', 'yes'):
                    permissions.add(key)
                elif isinstance(value, int) and value == 1:
                    permissions.add(key)
                # Si False, on ne l'ajoute pas (permission désactivée)
            else:
                # Si la permission n'est pas explicitement définie, utiliser la valeur par défaut
                if key in permissions_defaut:
                    permissions.add(key)
        return list(permissions)
    else:
        # Si pas de permissions personnalisées, retourner les permissions par défaut
        return list(permissions_defaut)

