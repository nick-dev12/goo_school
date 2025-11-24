"""
Utilitaires pour la gestion des sessions (années scolaires)
"""
from django.utils import timezone
from ..model.annee_scolaire_model import AnneeScolaire
from ..model.etablissement_model import Etablissement


def get_session_active(request, etablissement):
    """
    Récupère la session active pour un établissement
    
    Args:
        request: La requête HTTP
        etablissement (Etablissement): L'établissement concerné
        
    Returns:
        AnneeScolaire|None: La session active ou None
    """
    if not etablissement:
        return None
    
    return AnneeScolaire.get_session_active(etablissement)


def get_session_consultee(request, etablissement):
    """
    Récupère la session consultée par l'utilisateur
    Peut être différente de la session active si l'utilisateur consulte une ancienne session
    
    Args:
        request: La requête HTTP
        etablissement (Etablissement): L'établissement concerné
        
    Returns:
        AnneeScolaire|None: La session consultée ou la session active par défaut
    """
    if not etablissement:
        return None
    
    # Vérifier si l'utilisateur a sélectionné une session spécifique
    session_id = request.session.get('annee_scolaire_consultee_id')
    
    if session_id:
        try:
            session_consultee = AnneeScolaire.objects.get(
                pk=session_id,
                etablissement=etablissement
            )
            return session_consultee
        except AnneeScolaire.DoesNotExist:
            # Si la session n'existe plus, utiliser la session active
            pass
    
    # Par défaut, retourner la session active
    return get_session_active(request, etablissement)


def set_session_consultee(request, annee_scolaire):
    """
    Définit la session consultée par l'utilisateur
    
    Args:
        request: La requête HTTP
        annee_scolaire (AnneeScolaire): La session à consulter
    """
    if annee_scolaire:
        request.session['annee_scolaire_consultee_id'] = annee_scolaire.pk
    else:
        request.session.pop('annee_scolaire_consultee_id', None)


def filter_by_session(queryset, annee_scolaire):
    """
    Filtre un queryset par année scolaire
    
    Args:
        queryset: Le queryset à filtrer
        annee_scolaire (AnneeScolaire|None): L'année scolaire pour filtrer
        
    Returns:
        QuerySet: Le queryset filtré
    """
    if annee_scolaire:
        # Vérifier si le modèle a un champ annee_scolaire
        if hasattr(queryset.model, 'annee_scolaire'):
            return queryset.filter(annee_scolaire=annee_scolaire)
        # Sinon, filtrer par date si le modèle a un champ date
        elif hasattr(queryset.model, 'date'):
            return queryset.filter(
                date__gte=annee_scolaire.date_debut,
                date__lte=annee_scolaire.date_fin
            )
        elif hasattr(queryset.model, 'date_creation'):
            return queryset.filter(
                date_creation__date__gte=annee_scolaire.date_debut,
                date_creation__date__lte=annee_scolaire.date_fin
            )
    
    return queryset


def get_session_ouverte(etablissement):
    """
    Récupère la session ouverte pour un établissement
    (est_ouverte=True et date_debut <= aujourd'hui)
    
    Args:
        etablissement (Etablissement): L'établissement concerné
        
    Returns:
        AnneeScolaire|None: La session ouverte ou None
    """
    if not etablissement:
        return None
    
    return AnneeScolaire.get_session_ouverte(etablissement)


def should_redirect_to_new_session(request, etablissement):
    """
    Détermine si l'utilisateur doit être redirigé vers une nouvelle session
    
    Args:
        request: La requête HTTP
        etablissement (Etablissement): L'établissement concerné
        
    Returns:
        tuple: (should_redirect: bool, session_ouverte: AnneeScolaire|None)
    """
    if not etablissement:
        return False, None
    
    session_ouverte = get_session_ouverte(etablissement)
    session_active = get_session_active(request, etablissement)
    
    # Rediriger si:
    # 1. Il existe une session ouverte
    # 2. Cette session est différente de la session actuellement consultée
    # 3. L'utilisateur n'a pas encore été informé de cette nouvelle session
    if session_ouverte:
        session_consultee = get_session_consultee(request, etablissement)
        
        # Si la session consultée est différente de la session ouverte
        if not session_consultee or session_consultee.pk != session_ouverte.pk:
            # Vérifier si l'utilisateur a déjà été informé
            session_info_key = f'session_info_shown_{session_ouverte.pk}'
            if not request.session.get(session_info_key, False):
                return True, session_ouverte
    
    return False, None


def mark_session_info_shown(request, annee_scolaire):
    """
    Marque que l'utilisateur a été informé d'une nouvelle session
    
    Args:
        request: La requête HTTP
        annee_scolaire (AnneeScolaire): La session pour laquelle l'info a été montrée
    """
    if annee_scolaire:
        session_info_key = f'session_info_shown_{annee_scolaire.pk}'
        request.session[session_info_key] = True

