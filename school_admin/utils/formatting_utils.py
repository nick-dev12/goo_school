# school_admin/utils/formatting_utils.py
"""
Utilitaires pour le formatage des noms et prénoms
"""


def formater_nom(nom):
    """
    Formate un nom en majuscules.
    
    Args:
        nom (str): Le nom à formater
        
    Returns:
        str: Le nom formaté en majuscules
    """
    if not nom:
        return ''
    # Convertir en majuscules et supprimer les espaces en début/fin
    return nom.strip().upper()


def formater_prenom(prenom):
    """
    Formate un prénom avec la première lettre en majuscule et le reste en minuscules.
    
    Args:
        prenom (str): Le prénom à formater
        
    Returns:
        str: Le prénom formaté (Première lettre majuscule, reste minuscule)
    """
    if not prenom:
        return ''
    # Supprimer les espaces en début/fin
    prenom = prenom.strip()
    if not prenom:
        return ''
    # Première lettre en majuscule, reste en minuscules
    return prenom[0].upper() + prenom[1:].lower() if len(prenom) > 1 else prenom.upper()


def formater_nom_complet(nom, prenom):
    """
    Formate un nom complet en combinant nom (MAJUSCULES) et prénom (Première lettre majuscule).
    Retourne le format "NOM Prénom"
    
    Args:
        nom (str): Le nom de famille
        prenom (str): Le prénom
        
    Returns:
        str: Le nom complet formaté "NOM Prénom"
    """
    nom_formate = formater_nom(nom)
    prenom_formate = formater_prenom(prenom)
    
    if nom_formate and prenom_formate:
        return f"{nom_formate} {prenom_formate}"
    elif nom_formate:
        return nom_formate
    elif prenom_formate:
        return prenom_formate
    else:
        return ''

