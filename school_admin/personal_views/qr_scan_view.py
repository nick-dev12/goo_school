# school_admin/personal_views/qr_scan_view.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from decimal import Decimal

from ..model.eleve_model import Eleve
from ..model.inscription_eleve_model import InscriptionEleve
from ..model.lien_familial_model import LienFamilial
from ..model.comptabilite_eleve_model import ComptabiliteEleve, FraisInscription, Mensualite
from ..model.parametres_comptabilite_model import ParametresComptabilite
from ..model.parametres_comptabilite_groupe_classe_model import ParametresComptabiliteGroupeClasse
from ..model.annee_scolaire_model import AnneeScolaire
from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif


def scan_qr_eleve(request, qr_identifier):
    """
    Page publique pour afficher les informations d'un élève lorsqu'on scanne son QR code.
    Affiche uniquement les informations de base pour les utilisateurs non authentifiés.
    """
    # Récupérer l'élève par son identifiant QR
    try:
        eleve = Eleve.objects.get(qr_code_identifier=qr_identifier, actif=True)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève introuvable. Le QR code scanné n'est pas valide.")
        return render(request, 'school_admin/qr_scan/eleve_not_found.html', {})
    
    etablissement = eleve.etablissement
    if not etablissement:
        messages.error(request, "Établissement introuvable.")
        return render(request, 'school_admin/qr_scan/eleve_not_found.html', {})
    
    # Vérifier si l'utilisateur est authentifié (directeur ou personnel administratif)
    # Si oui, rediriger vers la page authentifiée
    is_authenticated = False
    current_user = None
    
    # Vérifier d'abord si request.user est authentifié
    if hasattr(request, 'user') and request.user.is_authenticated:
        current_user = request.user
        is_authenticated = True
    else:
        # Si request.user n'est pas authentifié, vérifier la session directement
        user_id = request.session.get('_auth_user_id')
        user_type = request.session.get('_auth_user_type')
        
        if user_id and user_type:
            try:
                # Récupérer l'utilisateur selon son type depuis la session
                if user_type == 'etablissement':
                    current_user = Etablissement.objects.get(pk=user_id)
                    is_authenticated = True
                elif user_type == 'personnel':
                    current_user = PersonnelAdministratif.objects.get(pk=user_id)
                    is_authenticated = True
            except (Etablissement.DoesNotExist, PersonnelAdministratif.DoesNotExist, ValueError):
                pass
    
    # Si l'utilisateur est authentifié comme directeur ou personnel administratif, rediriger
    if is_authenticated and current_user:
        if isinstance(current_user, Etablissement) or isinstance(current_user, PersonnelAdministratif):
            return redirect('school_admin:scan_qr_eleve_authenticated', qr_identifier=qr_identifier)
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = AnneeScolaire.get_session_active(etablissement)
    
    # Récupérer l'inscription de l'élève pour l'année scolaire active
    inscription = None
    classe = None
    if annee_scolaire_active:
        inscription = InscriptionEleve.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        ).select_related('classe').first()
        
        if inscription:
            classe = inscription.classe
    
    # Si pas de classe via inscription, utiliser la classe de l'élève
    if not classe:
        classe = eleve.classe
    
    # Informations du parent qui a inscrit l'élève
    parent_inscripteur = None
    parent_info = None
    
    # Chercher le parent via InscriptionEleve
    if inscription:
        parent_info = {
            'nom': inscription.parent_nom,
            'prenom': inscription.parent_prenom,
            'nom_complet': f"{inscription.parent_nom} {inscription.parent_prenom}",
            'telephone': inscription.parent_telephone,
            'email': inscription.parent_email if hasattr(inscription, 'parent_email') else None,
        }
        parent_inscripteur = parent_info
    
    # Si pas trouvé via inscription, chercher via LienFamilial
    if not parent_inscripteur:
        lien_inscripteur = LienFamilial.objects.filter(
            eleve=eleve,
            est_inscripteur=True,
            actif=True,
            statut='valide'
        ).select_related('parent').first()
        
        if lien_inscripteur and lien_inscripteur.parent:
            parent_inscripteur = {
                'nom': lien_inscripteur.parent.nom,
                'prenom': lien_inscripteur.parent.prenom,
                'nom_complet': lien_inscripteur.parent.nom_complet,
                'telephone': lien_inscripteur.parent.telephone,
                'email': lien_inscripteur.parent.email,
            }
    
    # Si toujours pas trouvé, utiliser les informations de l'élève
    if not parent_inscripteur:
        parent_inscripteur = {
            'nom': eleve.parent_nom if hasattr(eleve, 'parent_nom') else None,
            'prenom': eleve.parent_prenom if hasattr(eleve, 'parent_prenom') else None,
            'nom_complet': f"{eleve.parent_nom} {eleve.parent_prenom}" if hasattr(eleve, 'parent_nom') and eleve.parent_nom else "Non renseigné",
            'telephone': eleve.parent_telephone if hasattr(eleve, 'parent_telephone') else None,
            'email': eleve.parent_email if hasattr(eleve, 'parent_email') else None,
        }
    
    # Récupérer la devise monétaire
    devise_monnaie = etablissement.devise_monnaie if etablissement and etablissement.devise_monnaie else 'FCFA'
    
    context = {
        'eleve': eleve,
        'etablissement': etablissement,
        'classe': classe,
        'annee_scolaire_active': annee_scolaire_active,
        'parent_inscripteur': parent_inscripteur,
        'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
    }
    
    return render(request, 'school_admin/qr_scan/scan_eleve_info.html', context)


@login_required
def scan_qr_eleve_authenticated(request, qr_identifier):
    """
    Page authentifiée pour afficher les informations complètes d'un élève lorsqu'on scanne son QR code.
    Accessible uniquement aux directeurs et au personnel administratif.
    Affiche toutes les informations y compris la comptabilité.
    """
    # Vérifier que l'utilisateur est bien un directeur ou un personnel administratif
    user = request.user
    if not isinstance(user, (Etablissement, PersonnelAdministratif)):
        messages.error(request, "Accès non autorisé. Cette page est réservée aux directeurs et au personnel administratif.")
        return redirect('school_admin:scan_qr_eleve', qr_identifier=qr_identifier)
    
    # Pas de restriction d'accès à la page - tous les utilisateurs authentifiés peuvent y accéder
    # La section comptabilité sera affichée uniquement si l'utilisateur a la permission comptabilite_scan_qr
    
    # Récupérer l'élève par son identifiant QR
    try:
        eleve = Eleve.objects.get(qr_code_identifier=qr_identifier, actif=True)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève introuvable. Le QR code scanné n'est pas valide.")
        return render(request, 'school_admin/qr_scan/eleve_not_found.html', {})
    
    etablissement = eleve.etablissement
    if not etablissement:
        messages.error(request, "Établissement introuvable.")
        return render(request, 'school_admin/qr_scan/eleve_not_found.html', {})
    
    # Vérifier que l'utilisateur a accès à cet établissement
    if isinstance(user, PersonnelAdministratif):
        if user.etablissement != etablissement:
            messages.error(request, "Vous n'avez pas accès aux informations de cet établissement.")
            return redirect('directeur:dashboard_directeur')
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if etablissement:
        annee_scolaire_active = AnneeScolaire.get_session_active(etablissement)
    
    # Récupérer l'inscription de l'élève pour l'année scolaire active
    inscription = None
    classe = None
    if annee_scolaire_active:
        inscription = InscriptionEleve.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        ).select_related('classe').first()
        
        if inscription:
            classe = inscription.classe
    
    # Si pas de classe via inscription, utiliser la classe de l'élève
    if not classe:
        classe = eleve.classe
    
    # Informations du parent qui a inscrit l'élève
    parent_inscripteur = None
    
    # Chercher le parent via InscriptionEleve
    if inscription:
        parent_info = {
            'nom': inscription.parent_nom,
            'prenom': inscription.parent_prenom,
            'nom_complet': f"{inscription.parent_nom} {inscription.parent_prenom}",
            'telephone': inscription.parent_telephone,
            'email': inscription.parent_email if hasattr(inscription, 'parent_email') else None,
        }
        parent_inscripteur = parent_info
    
    # Si pas trouvé via inscription, chercher via LienFamilial
    if not parent_inscripteur:
        lien_inscripteur = LienFamilial.objects.filter(
            eleve=eleve,
            est_inscripteur=True,
            actif=True,
            statut='valide'
        ).select_related('parent').first()
        
        if lien_inscripteur and lien_inscripteur.parent:
            parent_inscripteur = {
                'nom': lien_inscripteur.parent.nom,
                'prenom': lien_inscripteur.parent.prenom,
                'nom_complet': lien_inscripteur.parent.nom_complet,
                'telephone': lien_inscripteur.parent.telephone,
                'email': lien_inscripteur.parent.email,
            }
    
    # Si toujours pas trouvé, utiliser les informations de l'élève
    if not parent_inscripteur:
        parent_inscripteur = {
            'nom': eleve.parent_nom if hasattr(eleve, 'parent_nom') else None,
            'prenom': eleve.parent_prenom if hasattr(eleve, 'parent_prenom') else None,
            'nom_complet': f"{eleve.parent_nom} {eleve.parent_prenom}" if hasattr(eleve, 'parent_nom') and eleve.parent_nom else "Non renseigné",
            'telephone': eleve.parent_telephone if hasattr(eleve, 'parent_telephone') else None,
            'email': eleve.parent_email if hasattr(eleve, 'parent_email') else None,
        }
    
    # Informations de comptabilité (uniquement si l'utilisateur a la permission comptabilite_scan_qr)
    comptabilite_info = None
    can_see_comptabilite = False
    
    # Le directeur a toujours accès
    if isinstance(user, Etablissement):
        can_see_comptabilite = True
    # Pour le personnel administratif, vérifier uniquement la permission comptabilite_scan_qr
    elif isinstance(user, PersonnelAdministratif):
        # Rafraîchir l'utilisateur depuis la base de données pour avoir les permissions à jour
        try:
            user.refresh_from_db()
        except Exception:
            pass
        
        # Vérifier directement dans les permissions
        permissions_dict = user.permissions if user.permissions else {}
        
        # Vérifier la permission comptabilite_scan_qr directement
        if 'comptabilite_scan_qr' in permissions_dict:
            permission_value = permissions_dict['comptabilite_scan_qr']
            # Si c'est un booléen True, autoriser
            if isinstance(permission_value, bool) and permission_value:
                can_see_comptabilite = True
            # Si c'est une chaîne, vérifier les valeurs positives
            elif isinstance(permission_value, str) and permission_value.lower() in ('true', '1', 'on', 'yes'):
                can_see_comptabilite = True
            # Si c'est un entier, vérifier si c'est 1
            elif isinstance(permission_value, int) and permission_value == 1:
                can_see_comptabilite = True
            else:
                can_see_comptabilite = False
        else:
            # Si la permission n'est pas dans le dict, vérifier via has_permission (permissions par défaut)
            from ..utils.permissions_personnel import has_permission
            can_see_comptabilite = has_permission(user, 'comptabilite_scan_qr')
        
        # Log pour déboguer
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[QR_SCAN] Permissions pour {user.username} (ID: {user.id}): {permissions_dict}")
        logger.info(f"[QR_SCAN] Permission comptabilite_scan_qr dans dict: {permissions_dict.get('comptabilite_scan_qr', 'NOT FOUND')}")
        logger.info(f"[QR_SCAN] Type de valeur: {type(permissions_dict.get('comptabilite_scan_qr'))}")
        logger.info(f"[QR_SCAN] can_see_comptabilite: {can_see_comptabilite}")
    
    if can_see_comptabilite and annee_scolaire_active:
        try:
            comptabilite = ComptabiliteEleve.objects.get(
                eleve=eleve,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active
            )
            
            # Récupérer les paramètres de comptabilité (spécifiques si disponibles, sinon généraux)
            parametres = None
            if classe:
                # Utiliser la méthode du contrôleur pour récupérer les bons paramètres
                from ..controllers.comptabilite_controller import ComptabiliteController
                parametres = ComptabiliteController._get_parametres_for_classe(etablissement, classe)
            
            # Si pas de paramètres spécifiques trouvés, utiliser les paramètres généraux
            if not parametres:
                try:
                    parametres = ParametresComptabilite.objects.get(etablissement=etablissement)
                except ParametresComptabilite.DoesNotExist:
                    parametres = None
            
            # Frais d'inscription
            frais_inscription = FraisInscription.objects.filter(
                comptabilite_eleve=comptabilite
            ).first()
            
            frais_inscription_paye = False
            frais_inscription_montant = Decimal('0.00')
            frais_inscription_montant_paye = Decimal('0.00')
            frais_inscription_reste = Decimal('0.00')
            
            if frais_inscription:
                frais_inscription_paye = frais_inscription.est_totalement_paye()
                frais_inscription_montant = frais_inscription.montant
                frais_inscription_reste = frais_inscription.reste_a_payer
                frais_inscription_montant_paye = frais_inscription_montant - frais_inscription_reste
            
            # Mensualités
            mensualites = Mensualite.objects.filter(
                comptabilite_eleve=comptabilite
            ).order_by('annee', 'mois')
            
            mensualites_payees = []
            mensualites_impayees = []
            mensualites_a_venir = []
            
            from django.utils import timezone
            maintenant = timezone.now().date()
            
            for mensualite in mensualites:
                if parametres:
                    mensualite.mettre_a_jour_statut(parametres)
                
                mensualite_info = {
                    'id': mensualite.id,
                    'periode': mensualite.periode,
                    'mois': mensualite.mois,
                    'annee': mensualite.annee,
                    'montant': mensualite.montant,
                    'montant_paye': mensualite.montant_paye,
                    'reste_a_payer': mensualite.get_reste_a_payer(),
                    'statut': mensualite.statut,
                    'date_echeance': mensualite.date_echeance,
                }
                
                if mensualite.est_totalement_paye():
                    mensualites_payees.append(mensualite_info)
                elif mensualite.date_echeance < maintenant:
                    # Mensualité passée non payée
                    mensualites_impayees.append(mensualite_info)
                else:
                    # Mensualité à venir
                    mensualites_a_venir.append(mensualite_info)
            
            # Calculer les totaux
            total_du = comptabilite.calculer_total_du()
            total_paye = comptabilite.calculer_total_paye()
            reste_a_payer = total_du - total_paye
            
            # Vérifier si l'élève est à jour
            est_a_jour = comptabilite.statut_paiement == 'a_jour'
            est_non_en_regle = comptabilite.est_non_en_regle(parametres) if parametres else False
            
            comptabilite_info = {
                'comptabilite': comptabilite,
                'est_a_jour': est_a_jour,
                'est_non_en_regle': est_non_en_regle,
                'statut': comptabilite.get_statut_paiement_display(),
                'frais_inscription_paye': frais_inscription_paye,
                'frais_inscription_montant': frais_inscription_montant,
                'frais_inscription_montant_paye': frais_inscription_montant_paye,
                'frais_inscription_reste': frais_inscription_reste,
                'mensualites_payees': mensualites_payees,
                'mensualites_impayees': mensualites_impayees,
                'mensualites_a_venir': mensualites_a_venir,
                'total_du': total_du,
                'total_paye': total_paye,
                'reste_a_payer': reste_a_payer,
            }
        except ComptabiliteEleve.DoesNotExist:
            comptabilite_info = None
    
    # Déterminer le type d'utilisateur pour l'affichage
    is_directeur = isinstance(user, Etablissement)
    is_personnel = isinstance(user, PersonnelAdministratif)
    
    # Déterminer l'URL du dashboard pour le bouton retour
    from django.urls import reverse
    if is_directeur:
        dashboard_url = reverse('directeur:dashboard_directeur')
    elif is_personnel:
        # Pour le personnel administratif, vérifier la fonction
        fonction = user.fonction if hasattr(user, 'fonction') else None
        if fonction == 'secretaire':
            dashboard_url = reverse('secretaire:dashboard_secretaire')
        else:
            dashboard_url = reverse('directeur:dashboard_directeur')
    else:
        dashboard_url = reverse('directeur:dashboard_directeur')
    
    # Récupérer la devise monétaire
    devise_monnaie = etablissement.devise_monnaie if etablissement and etablissement.devise_monnaie else 'FCFA'
    
    context = {
        'eleve': eleve,
        'etablissement': etablissement,
        'classe': classe,
        'annee_scolaire_active': annee_scolaire_active,
        'parent_inscripteur': parent_inscripteur,
        'comptabilite_info': comptabilite_info,
        'is_authenticated': True,
        'is_directeur': is_directeur,
        'is_personnel': is_personnel,
        'current_user': user,
        'dashboard_url': dashboard_url,  # URL du dashboard pour le bouton retour
        'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
        'can_see_comptabilite': can_see_comptabilite,  # Variable pour afficher/masquer la comptabilité
    }
    
    return render(request, 'school_admin/qr_scan/scan_eleve_info_authenticated.html', context)
