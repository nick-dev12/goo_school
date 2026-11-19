"""Mots de passe provisoires : génération sûre, changement imposé, effacement du texte en clair.

Règle unique pour les élèves, parents, professeurs et personnel administratif :
- un mot de passe provisoire est tiré avec le module ``secrets`` (8 chiffres, faciles à dicter) ;
- tant qu'il est en vigueur, la personne doit en choisir un nouveau à sa connexion ;
- dès qu'elle l'a remplacé, le texte en clair est effacé de la base (``effacer_si_remplace``) ;
- si elle l'oublie, la direction en génère un nouveau (``attribuer_provisoire``).
"""
from __future__ import annotations

import secrets

LONGUEUR = 8
MODELES = ('eleve', 'parent', 'professeur', 'personneladministratif')
# Indicateur « mot de passe modifié » propre à certains modèles.
INDICATEURS = {'eleve': 'mot_de_passe_eleve_modifie', 'parent': 'mot_de_passe_modifie'}
SESSION_CLE = 'doit_changer_mot_de_passe'


def generer_provisoire(longueur: int = LONGUEUR) -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(longueur))


def concerne(user) -> bool:
    return user is not None and getattr(user, '_meta', None) is not None and user._meta.model_name in MODELES


def provisoire_en_vigueur(user) -> bool:
    """Vrai si la personne se connecte encore avec le mot de passe que l'établissement lui a donné."""
    provisoire = getattr(user, 'mot_de_passe_provisoire', '') or ''
    return concerne(user) and bool(provisoire) and user.check_password(provisoire)


def attribuer_provisoire(user) -> str:
    """Nouveau mot de passe provisoire (oubli, compte perdu). Coupe les sessions ouvertes de la personne."""
    mot = generer_provisoire()
    user.set_password(mot)
    user.mot_de_passe_provisoire = mot
    champs = ['password', 'mot_de_passe_provisoire']
    indicateur = INDICATEURS.get(user._meta.model_name)
    if indicateur:
        setattr(user, indicateur, False)
        champs.append(indicateur)
    user.save(update_fields=champs)
    return mot


def effacer_si_remplace(sender, instance, **kwargs):
    """post_save : si la personne a choisi un mot de passe différent du provisoire, on efface ce dernier.

    ``set_password`` garde le mot de passe en clair dans ``_password`` jusqu'à la fin de l'enregistrement :
    la comparaison se fait donc sans calcul coûteux.
    """
    brut = getattr(instance, '_password', None)
    provisoire = getattr(instance, 'mot_de_passe_provisoire', '') or ''
    if brut is None or not provisoire or brut == provisoire:
        return
    valeurs = {'mot_de_passe_provisoire': ''}
    indicateur = INDICATEURS.get(instance._meta.model_name)
    if indicateur:
        valeurs[indicateur] = True
    type(instance).objects.filter(pk=instance.pk).update(**valeurs)
    for champ, valeur in valeurs.items():
        setattr(instance, champ, valeur)
