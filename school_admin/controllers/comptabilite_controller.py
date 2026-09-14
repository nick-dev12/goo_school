# school_admin/controllers/comptabilite_controller.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from datetime import datetime, timedelta
from calendar import monthrange
import re

from ..model.comptabilite_eleve_model import (
    ComptabiliteEleve, FraisInscription, FraisAnnexe, Mensualite, PaiementEleve
)
from ..utils.frais_annexes import (
    extraire_frais_annexes_depuis_post,
    get_frais_annexes_from_parametres,
)
from ..model.parametres_comptabilite_model import ParametresComptabilite
from ..model.parametres_comptabilite_groupe_classe_model import ParametresComptabiliteGroupeClasse
from ..model.compte_user import CompteUser
from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.eleve_model import Eleve
from ..model.classe_model import Classe
from ..model.classe_model import Classe


class ComptabiliteController:
    """
    Contrôleur pour gérer toute la logique de comptabilité
    """

    @staticmethod
    def _get_user_etablissement(request):
        """
        Helper pour récupérer l'établissement de l'utilisateur
        Retourne (etablissement, is_directeur, personnel) ou (None, False, None) si accès refusé
        """
        from ..personal_views.directeur_view import _get_user_etablissement as helper
        return helper(request)

    @staticmethod
    def _get_session_directeur(request, etablissement):
        """
        Helper pour récupérer l'année scolaire active
        """
        from ..personal_views.directeur_view import _get_session_directeur as helper
        return helper(request, etablissement)
    
    @staticmethod
    def _get_devise_monnaie(etablissement):
        """
        Helper pour récupérer la devise monétaire de l'établissement
        Retourne la devise ou 'FCFA' par défaut si non configurée
        """
        if etablissement and etablissement.devise_monnaie:
            return etablissement.devise_monnaie.strip()
        return 'FCFA'  # Valeur par défaut

    @staticmethod
    def _get_eleves_classe_par_inscription(classe, etablissement, annee_scolaire):
        """
        Helper pour récupérer les élèves d'une classe par inscription
        """
        from ..personal_views.directeur_view import _get_eleves_classe_par_inscription as helper
        return helper(classe, etablissement, annee_scolaire)

    @staticmethod
    @login_required
    def liste_comptabilite_eleves_directeur(request):
        """
        Liste tous les élèves avec leur statut de paiement pour l'établissement du directeur
        Structure avec onglets par niveau et sous-onglets par classe
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions : le directeur a accès à tout, sinon vérifier la permission
        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_voir'):
                messages.error(request, "Vous n'avez pas l'autorisation d'accéder à la comptabilité.")
                return redirect('directeur:dashboard_directeur')
        
        # Vérifier les permissions : le directeur a accès à tout, sinon vérifier la permission
        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_voir'):
                messages.error(request, "Vous n'avez pas l'autorisation d'accéder à la comptabilité.")
                return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée pour cet établissement.")
            return redirect('directeur:dashboard_directeur')
        
        # Récupérer toutes les classes de l'établissement
        classes = (
            Classe.objects.filter(etablissement=etablissement, actif=True)
            .select_related('department', 'academic_level')
            .order_by('niveau', 'nom')
        )
        
        # Grouper les classes par niveau
        classes_grouped = {}
        
        for classe in classes:
            nom = classe.nom
            
            # Pattern pour extraire le niveau
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
            
            if match:
                categorie = match.group(1)  # "CE1", "CE2", etc.
            else:
                categorie = nom
            
            # Initialiser la catégorie si elle n'existe pas
            if categorie not in classes_grouped:
                classes_grouped[categorie] = {
                    'classes': [],
                    'total_eleves': 0
                }
            
            # Récupérer les élèves depuis InscriptionEleve pour l'année scolaire active
            eleves = ComptabiliteController._get_eleves_classe_par_inscription(
                classe, etablissement, annee_scolaire_active
            )
            
            # Récupérer les paramètres de comptabilité spécifiques pour cette classe (ou généraux si pas de paramètres spécifiques)
            parametres = ComptabiliteController._get_parametres_for_classe(etablissement, classe)
            
            eleves_comptabilite = []
            for eleve in eleves:
                # Récupérer ou créer la comptabilité
                comptabilite, created = ComptabiliteEleve.objects.get_or_create(
                    eleve=eleve,
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active,
                    defaults={'statut_paiement': 'a_jour'}
                )
                
                # NE PAS créer automatiquement les frais d'inscription
                # Les données doivent être créées uniquement via l'interface de gestion
                # ou lors de la configuration des paramètres
                
                # NE PAS générer automatiquement les mensualités
                # Les données doivent être créées uniquement via l'interface de gestion
                # ou lors de la configuration des paramètres
                # Cette fonctionnalité a été désactivée pour éviter la création automatique
                # Les données affichées proviennent uniquement de la base de données
                
                # Vérifier et mettre à jour le statut
                comptabilite.verifier_statut_paiement()
                
                # Mettre à jour les statuts des mensualités si paramètres existent
                if parametres:
                    mensualites = Mensualite.objects.filter(comptabilite_eleve=comptabilite)
                    for mensualite in mensualites:
                        mensualite.mettre_a_jour_statut(parametres)
                
                # Vérifier si l'élève est "non en règle" selon les nouveaux critères
                est_non_en_regle = comptabilite.est_non_en_regle(parametres)
                
                total_du = comptabilite.calculer_total_du()
                total_paye = comptabilite.calculer_total_paye()
                reste_a_payer = total_du - total_paye
                
                # Récupérer les frais d'inscription pour cet élève
                frais_inscription_obj = FraisInscription.objects.filter(
                    comptabilite_eleve=comptabilite
                ).first()
                frais_inscription = frais_inscription_obj.montant if frais_inscription_obj else Decimal('0.00')

                frais_annexes_total = Decimal('0.00')
                frais_annexes_reste = Decimal('0.00')
                for frais_annexe in FraisAnnexe.objects.filter(comptabilite_eleve=comptabilite):
                    frais_annexes_total += frais_annexe.montant
                    frais_annexes_reste += frais_annexe.get_reste_a_payer()
                
                eleves_comptabilite.append({
                    'eleve': eleve,
                    'comptabilite': comptabilite,
                    'total_du': total_du,
                    'total_paye': total_paye,
                    'reste_a_payer': reste_a_payer,
                    'frais_inscription': frais_inscription,
                    'frais_annexes_total': frais_annexes_total,
                    'frais_annexes_reste': frais_annexes_reste,
                    'est_non_en_regle': est_non_en_regle,
                })
            
            # Calculer les statistiques spécifiques à la classe
            montant_total_classe = Decimal('0.00')
            montant_total_paye_classe = Decimal('0.00')
            eleves_en_regle_classe = 0
            eleves_non_en_regle_classe = 0
            
            for eleve_data in eleves_comptabilite:
                montant_total_classe += eleve_data['total_du']
                montant_total_paye_classe += eleve_data['total_paye']
                if eleve_data.get('est_non_en_regle', False):
                    eleves_non_en_regle_classe += 1
                else:
                    eleves_en_regle_classe += 1
            
            classe_data = {
                'classe': classe,
                'eleves': eleves_comptabilite,
                'nombre_eleves': len(eleves_comptabilite),
                'montant_total_classe': montant_total_classe,
                'montant_total_paye_classe': montant_total_paye_classe,
                'montant_reste_classe': montant_total_classe - montant_total_paye_classe,
                'eleves_en_regle_classe': eleves_en_regle_classe,
                'eleves_non_en_regle_classe': eleves_non_en_regle_classe,
            }
            
            classes_grouped[categorie]['classes'].append(classe_data)
            classes_grouped[categorie]['total_eleves'] += len(eleves_comptabilite)
        
        # Statistiques globales - uniquement 2 catégories : À jour et Non en règle
        total_eleves = sum(data['total_eleves'] for data in classes_grouped.values())
        eleves_a_jour = 0
        eleves_non_en_regle = 0
        montant_total_global = Decimal('0.00')
        montant_paye_global = Decimal('0.00')

        for categorie_data in classes_grouped.values():
            for classe_data in categorie_data['classes']:
                montant_total_global += classe_data.get('montant_total_classe', Decimal('0.00'))
                montant_paye_global += classe_data.get('montant_total_paye_classe', Decimal('0.00'))
                for eleve_data in classe_data['eleves']:
                    if eleve_data.get('est_non_en_regle', False):
                        eleves_non_en_regle += 1
                    else:
                        eleves_a_jour += 1

        stats_generales = {
            'total_eleves': total_eleves,
            'total_classes': classes.count(),
            'eleves_a_jour': eleves_a_jour,
            'eleves_non_en_regle': eleves_non_en_regle,
            'montant_total': montant_total_global,
            'montant_paye': montant_paye_global,
            'montant_reste': montant_total_global - montant_paye_global,
        }
        
        # Récupérer la devise monétaire
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
        
        context = {
            'etablissement': etablissement,
            'annee_scolaire_active': annee_scolaire_active,
            'classes_grouped': dict(classes_grouped),
            'stats_generales': stats_generales,
            'total_eleves': total_eleves,
            'eleves_a_jour': eleves_a_jour,
            'eleves_non_en_regle': eleves_non_en_regle,
            'is_directeur': is_directeur,
            'personnel': personnel,
            'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
            'est_superieur': etablissement.type_etablissement == 'superieur',
        }
        
        return render(request, 'school_admin/directeur/comptabilite/liste_comptabilite_eleves.html', context)

    @staticmethod
    @login_required
    def details_comptabilite_eleve_directeur(request, eleve_id):
        """
        Détails complets de la comptabilité d'un élève pour le directeur
        Le directeur de l'établissement a accès à toutes les pages
        """
        # Vérifier directement si l'utilisateur est un établissement (directeur)
        if not isinstance(request.user, Etablissement):
            # Si ce n'est pas un établissement, vérifier si c'est un personnel administratif
            if isinstance(request.user, PersonnelAdministratif):
                # Le personnel administratif peut aussi accéder
                etablissement = request.user.etablissement
                if not etablissement:
                    messages.error(request, "Aucun établissement associé à votre compte.")
                    return redirect('directeur:dashboard_directeur')
                is_directeur = False
                personnel = request.user
            else:
                messages.error(request, "Accès non autorisé. Seuls les directeurs et le personnel administratif peuvent accéder à cette page.")
                return redirect('directeur:dashboard_directeur')
        else:
            # C'est un établissement (directeur)
            etablissement = request.user
            is_directeur = True
            personnel = None
        
        # Récupérer l'année scolaire active AVANT de récupérer l'élève
        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:liste_comptabilite_eleves_directeur')
        
        # Récupérer l'inscription de l'élève depuis InscriptionEleve pour l'année scolaire active
        from ..model.inscription_eleve_model import InscriptionEleve
        try:
            inscription = InscriptionEleve.objects.select_related('eleve').get(
                eleve_id=eleve_id,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active,
                eleve__isnull=False  # S'assurer que l'élève existe toujours
            )
            eleve = inscription.eleve
            # Vérifier que l'élève est actif
            if not eleve or not eleve.actif:
                messages.error(request, f"Élève introuvable ou inactif (ID: {eleve_id}). L'élève doit être inscrit dans l'année scolaire active et être actif.")
                return redirect('directeur:liste_comptabilite_eleves_directeur')
        except InscriptionEleve.DoesNotExist:
            # Essayer de récupérer l'élève directement pour voir s'il existe
            try:
                eleve_temp = Eleve.objects.get(id=eleve_id, etablissement=etablissement, actif=True)
                messages.error(request, f"Élève non inscrit dans l'année scolaire active (ID: {eleve_id}). L'élève existe mais n'est pas inscrit via InscriptionEleve pour l'année scolaire {annee_scolaire_active}.")
            except Eleve.DoesNotExist:
                messages.error(request, f"Élève introuvable (ID: {eleve_id}). Vérifiez que l'élève existe et est actif dans cet établissement.")
            return redirect('directeur:liste_comptabilite_eleves_directeur')
        
        # Récupérer ou créer la comptabilité de l'élève
        comptabilite, created = ComptabiliteEleve.objects.get_or_create(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            defaults={'statut_paiement': 'a_jour'}
        )
        
        # Récupérer les paramètres de comptabilité spécifiques à la classe de l'élève (ou généraux)
        parametres = None
        if inscription.classe:
            parametres = ComptabiliteController._get_parametres_for_classe(etablissement, inscription.classe)
        
        # NE PAS créer automatiquement les frais d'inscription
        # Les données doivent être créées uniquement via l'interface de gestion
        # ou lors de la configuration des paramètres
        
        # NE PAS générer automatiquement les mensualités
        # Les données doivent être créées uniquement via l'interface de gestion
        # ou lors de la configuration des paramètres
        # Cette fonctionnalité a été désactivée pour éviter la création automatique
        # Les données affichées proviennent uniquement de la base de données
        
        # Vérifier le statut
        comptabilite.verifier_statut_paiement()
        
        # Récupérer les frais d'inscription
        frais_inscription = FraisInscription.objects.filter(
            comptabilite_eleve=comptabilite
        ).order_by('-date_creation')
        
        # Récupérer les mensualités
        mensualites = Mensualite.objects.filter(
            comptabilite_eleve=comptabilite
        ).order_by('annee', 'mois')
        
        # Mettre à jour automatiquement les statuts des mensualités si les paramètres existent
        if parametres:
            for mensualite in mensualites:
                mensualite.mettre_a_jour_statut(parametres)
        
        # Récupérer les paiements
        paiements = PaiementEleve.objects.filter(
            eleve=eleve,
            annee_scolaire=annee_scolaire_active
        ).order_by('-date_paiement')
        
        # Calculer le montant déjà payé depuis la table PaiementEleve pour chaque frais d'inscription
        frais_inscription_avec_paiements = []
        for frais in frais_inscription:
            # Calculer le montant total payé depuis les paiements liés à ce frais
            # Utiliser Decimal pour éviter les problèmes de précision
            montant_paye_depuis_paiements = Decimal('0.00')
            
            # Récupérer tous les paiements liés à ce frais d'inscription
            paiements_frais = PaiementEleve.objects.filter(
                frais_inscription=frais,
                eleve=eleve,
                annee_scolaire=annee_scolaire_active,
                type_paiement='frais_inscription'
            )
            
            for paiement in paiements_frais:
                montant_paye_depuis_paiements += Decimal(str(paiement.montant))
            
            reste_a_payer_frais = Decimal(str(frais.montant)) - montant_paye_depuis_paiements
            frais_inscription_avec_paiements.append({
                'frais': frais,
                'montant_total': frais.montant,
                'montant_paye': montant_paye_depuis_paiements,
                'reste_a_payer': reste_a_payer_frais if reste_a_payer_frais > Decimal('0.00') else Decimal('0.00')
            })
        
        # Calculer le montant déjà payé depuis la table PaiementEleve pour chaque mensualité
        mensualites_avec_paiements = []
        for mensualite in mensualites:
            # Calculer le montant total payé depuis les paiements liés à cette mensualité
            # Utiliser Decimal pour éviter les problèmes de précision
            montant_paye_depuis_paiements = Decimal('0.00')
            
            # Récupérer tous les paiements liés à cette mensualité
            paiements_mensualite = PaiementEleve.objects.filter(
                mensualite=mensualite,
                eleve=eleve,
                annee_scolaire=annee_scolaire_active,
                type_paiement='mensualite'
            )
            
            for paiement in paiements_mensualite:
                montant_paye_depuis_paiements += Decimal(str(paiement.montant))
            
            reste_a_payer_mensualite = Decimal(str(mensualite.montant)) - montant_paye_depuis_paiements
            mensualites_avec_paiements.append({
                'mensualite': mensualite,
                'montant_total': mensualite.montant,
                'montant_paye': montant_paye_depuis_paiements,
                'reste_a_payer': reste_a_payer_mensualite if reste_a_payer_mensualite > Decimal('0.00') else Decimal('0.00')
            })

        frais_annexes = FraisAnnexe.objects.filter(
            comptabilite_eleve=comptabilite
        ).order_by('libelle')
        frais_annexes_avec_paiements = []
        for frais in frais_annexes:
            montant_paye_depuis_paiements = Decimal('0.00')
            paiements_annexe = PaiementEleve.objects.filter(
                frais_annexe=frais,
                eleve=eleve,
                annee_scolaire=annee_scolaire_active,
                type_paiement='frais_annexe',
            )
            for paiement in paiements_annexe:
                montant_paye_depuis_paiements += Decimal(str(paiement.montant))
            reste_a_payer_annexe = Decimal(str(frais.montant)) - montant_paye_depuis_paiements
            frais_annexes_avec_paiements.append({
                'frais': frais,
                'montant_total': frais.montant,
                'montant_paye': montant_paye_depuis_paiements,
                'reste_a_payer': reste_a_payer_annexe if reste_a_payer_annexe > Decimal('0.00') else Decimal('0.00'),
            })
        
        # Calculer les totaux
        total_du = comptabilite.calculer_total_du()
        total_paye = comptabilite.calculer_total_paye()
        reste_a_payer = total_du - total_paye
        
        # Récupérer la devise monétaire
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
        
        pct_paye = 0
        if total_du and total_du > 0:
            pct_paye = int((total_paye / total_du) * 100)

        context = {
            'eleve': eleve,
            'inscription': inscription,
            'etablissement': etablissement,
            'annee_scolaire': annee_scolaire_active,
            'comptabilite': comptabilite,
            'pct_paye': pct_paye,
            'frais_inscription': frais_inscription,  # Garder pour compatibilité
            'frais_inscription_avec_paiements': frais_inscription_avec_paiements,  # Nouveau avec montants calculés depuis PaiementEleve
            'mensualites': mensualites,  # Garder pour compatibilité
            'mensualites_avec_paiements': mensualites_avec_paiements,  # Nouveau avec montants calculés depuis PaiementEleve
            'frais_annexes': frais_annexes,
            'frais_annexes_avec_paiements': frais_annexes_avec_paiements,
            'paiements': paiements,
            'total_du': total_du,
            'total_paye': total_paye,
            'reste_a_payer': reste_a_payer,
            'is_directeur': is_directeur,
            'personnel': personnel,
            'parametres': parametres,
            'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
        }
        
        return render(request, 'school_admin/directeur/comptabilite/details_comptabilite_eleve.html', context)

    @staticmethod
    @login_required
    def enregistrer_paiement_directeur(request, eleve_id):
        """
        Formulaire pour enregistrer un paiement pour un élève (directeur)
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions pour les paiements : le directeur a accès à tout, sinon vérifier la permission
        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_paiements'):
                messages.error(request, "Vous n'avez pas l'autorisation d'enregistrer des paiements.")
                return redirect('directeur:dashboard_directeur')
        
        # Récupérer l'année scolaire active AVANT de récupérer l'élève
        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)
        
        # Vérifier que eleve_id est bien un entier
        try:
            eleve_id_int = int(eleve_id)
        except (ValueError, TypeError):
            messages.error(request, f"ID d'élève invalide : {eleve_id}")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)
        
        # Récupérer l'inscription de l'élève depuis InscriptionEleve pour l'année scolaire active
        from ..model.inscription_eleve_model import InscriptionEleve
        try:
            inscription = InscriptionEleve.objects.select_related('eleve').get(
                eleve_id=eleve_id_int,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active,
                eleve__isnull=False  # S'assurer que l'élève existe toujours
            )
            eleve = inscription.eleve
            # Vérifier que l'élève est actif
            if not eleve or not eleve.actif:
                messages.error(request, f"Élève introuvable ou inactif (ID: {eleve_id_int}). L'élève doit être inscrit dans l'année scolaire active et être actif.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        except InscriptionEleve.DoesNotExist:
            # Essayer de récupérer l'élève directement pour voir s'il existe
            try:
                eleve_temp = Eleve.objects.get(id=eleve_id_int, etablissement=etablissement, actif=True)
                messages.error(request, f"Élève non inscrit dans l'année scolaire active (ID: {eleve_id_int}). L'élève existe mais n'est pas inscrit via InscriptionEleve pour l'année scolaire {annee_scolaire_active}.")
            except Eleve.DoesNotExist:
                messages.error(request, f"Élève introuvable (ID: {eleve_id_int}). Vérifiez que l'élève existe et est actif dans cet établissement.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        
        # Récupérer les frais d'inscription non payés pour l'année scolaire active
        comptabilite = ComptabiliteEleve.objects.filter(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        ).first()
        
        frais_inscription_non_payes = []
        mensualites_non_payees = []
        frais_annexes_non_payes = []
        
        if comptabilite:
            frais_inscription_non_payes = FraisInscription.objects.filter(
                comptabilite_eleve=comptabilite,
                annee_scolaire=annee_scolaire_active,
                statut__in=['en_attente', 'en_retard']
            ).order_by('date_echeance')
            
            mensualites_non_payees = Mensualite.objects.filter(
                comptabilite_eleve=comptabilite,
                annee_scolaire=annee_scolaire_active,
                statut__in=['en_attente', 'en_retard', 'impaye']
            ).order_by('date_echeance')

            frais_annexes_non_payes = FraisAnnexe.objects.filter(
                comptabilite_eleve=comptabilite,
                annee_scolaire=annee_scolaire_active,
                statut__in=['en_attente', 'en_retard']
            ).order_by('date_echeance')
        
        if request.method == 'POST':
            type_paiement = request.POST.get('type_paiement')
            montant = request.POST.get('montant')
            mode_paiement = request.POST.get('mode_paiement')
            reference_paiement = request.POST.get('reference_paiement', '')
            notes = request.POST.get('notes', '')
            
            # Validation
            errors = {}
            if not type_paiement:
                errors['type_paiement'] = "Le type de paiement est obligatoire."
            if not montant:
                errors['montant'] = "Le montant est obligatoire."
            else:
                try:
                    montant_decimal = Decimal(montant)
                    if montant_decimal <= 0:
                        errors['montant'] = "Le montant doit être positif."
                except (ValueError, InvalidOperation):
                    errors['montant'] = "Le montant doit être un nombre valide."
            
            if not mode_paiement:
                errors['mode_paiement'] = "Le mode de paiement est obligatoire."
            
            if errors:
                # Récupérer la devise monétaire
                devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
                context = {
                    'eleve': eleve,
                    'etablissement': etablissement,
                    'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
                    'annee_scolaire': annee_scolaire_active,
                    'frais_inscription_non_payes': frais_inscription_non_payes,
                    'mensualites_non_payees': mensualites_non_payees,
                    'frais_annexes_non_payes': frais_annexes_non_payes,
                    'errors': errors,
                    'form_data': request.POST,
                    'is_directeur': is_directeur,
                    'personnel': personnel,
                }
                return render(request, 'school_admin/directeur/comptabilite/enregistrer_paiement.html', context)
            
            # Créer le paiement
            try:
                with transaction.atomic():
                    frais_inscription_obj = None
                    mensualite_obj = None
                    frais_annexe_obj = None
                    
                    if type_paiement == 'frais_inscription':
                        frais_id = request.POST.get('frais_inscription_id')
                        if frais_id:
                            try:
                                frais_inscription_obj = FraisInscription.objects.get(
                                    id=frais_id,
                                    eleve=eleve,
                                    annee_scolaire=annee_scolaire_active
                                )
                            except FraisInscription.DoesNotExist:
                                messages.error(request, "Frais d'inscription introuvable pour cette année scolaire active.")
                                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
                    elif type_paiement == 'mensualite':
                        mensualite_id = request.POST.get('mensualite_id')
                        if mensualite_id:
                            try:
                                mensualite_obj = Mensualite.objects.get(
                                    id=mensualite_id,
                                    eleve=eleve,
                                    etablissement=etablissement,
                                    annee_scolaire=annee_scolaire_active
                                )
                            except Mensualite.DoesNotExist:
                                messages.error(request, "Mensualité introuvable pour cette année scolaire active.")
                                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
                    elif type_paiement == 'frais_annexe':
                        frais_annexe_id = request.POST.get('frais_annexe_id')
                        if frais_annexe_id:
                            try:
                                frais_annexe_obj = FraisAnnexe.objects.get(
                                    id=frais_annexe_id,
                                    eleve=eleve,
                                    etablissement=etablissement,
                                    annee_scolaire=annee_scolaire_active,
                                )
                            except FraisAnnexe.DoesNotExist:
                                messages.error(request, "Frais annexe introuvable pour cette année scolaire active.")
                                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
                    
                    # Vérifier que le montant ne dépasse pas le reste à payer
                    if type_paiement == 'frais_inscription' and frais_inscription_obj:
                        reste_a_payer = frais_inscription_obj.get_reste_a_payer()
                        if montant_decimal > reste_a_payer:
                            messages.error(request, f"Le montant ({montant_decimal}) dépasse le reste à payer ({reste_a_payer}).")
                            return redirect('directeur:enregistrer_paiement_directeur', eleve_id=eleve_id)
                        # Ajouter le paiement aux frais d'inscription
                        frais_inscription_obj.ajouter_paiement(montant_decimal)
                    elif type_paiement == 'mensualite' and mensualite_obj:
                        reste_a_payer = mensualite_obj.get_reste_a_payer()
                        if montant_decimal > reste_a_payer:
                            messages.error(request, f"Le montant ({montant_decimal}) dépasse le reste à payer ({reste_a_payer}).")
                            return redirect('directeur:enregistrer_paiement_directeur', eleve_id=eleve_id)
                        # Ajouter le paiement à la mensualité
                        mensualite_obj.ajouter_paiement(montant_decimal)
                    elif type_paiement == 'frais_annexe' and frais_annexe_obj:
                        reste_a_payer = frais_annexe_obj.get_reste_a_payer()
                        if montant_decimal > reste_a_payer:
                            messages.error(request, f"Le montant ({montant_decimal}) dépasse le reste à payer ({reste_a_payer}).")
                            return redirect('directeur:enregistrer_paiement_directeur', eleve_id=eleve_id)
                        frais_annexe_obj.ajouter_paiement(montant_decimal)
                    
                    # Créer le paiement
                    enregistre_par_user = None
                    if isinstance(request.user, CompteUser):
                        enregistre_par_user = request.user
                    
                    PaiementEleve.objects.create(
                        eleve=eleve,
                        etablissement=etablissement,
                        annee_scolaire=annee_scolaire_active,
                        type_paiement=type_paiement,
                        frais_inscription=frais_inscription_obj,
                        mensualite=mensualite_obj,
                        frais_annexe=frais_annexe_obj,
                        montant=montant_decimal,
                        mode_paiement=mode_paiement,
                        reference_paiement=reference_paiement,
                        notes=notes,
                        enregistre_par=enregistre_par_user
                    )
                    
                    # Mettre à jour le statut de la comptabilité
                    if comptabilite:
                        comptabilite.verifier_statut_paiement()
                    
                    # Récupérer la devise monétaire pour le message
                    devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
                    messages.success(request, f"Paiement de {montant_decimal} {devise_monnaie} enregistré avec succès.")
                    return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            except Exception as e:
                messages.error(request, f"Erreur lors de l'enregistrement du paiement : {str(e)}")
        
        # Récupérer la devise monétaire
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
        context = {
            'eleve': eleve,
            'etablissement': etablissement,
            'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
            'annee_scolaire': annee_scolaire_active,
            'frais_inscription_non_payes': frais_inscription_non_payes,
            'mensualites_non_payees': mensualites_non_payees,
            'frais_annexes_non_payes': frais_annexes_non_payes,
            'is_directeur': is_directeur,
            'personnel': personnel,
        }
        
        return render(request, 'school_admin/directeur/comptabilite/enregistrer_paiement.html', context)

    @staticmethod
    @login_required
    def payer_frais_inscription_directeur(request, eleve_id, frais_id):
        """
        Vue pour enregistrer un paiement partiel ou total des frais d'inscription
        
        IMPORTANT: eleve_id doit être l'ID de l'élève depuis l'URL, pas l'ID du frais
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions : le directeur a accès à tout, sinon vérifier la permission
        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_voir'):
                messages.error(request, "Vous n'avez pas l'autorisation d'accéder à la comptabilité.")
                return redirect('directeur:dashboard_directeur')
        
        # Récupérer l'année scolaire active AVANT de récupérer l'élève
        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)
        
        # Vérifier que eleve_id est bien un entier et non un ID de frais
        # IMPORTANT: eleve_id vient de l'URL et doit être l'ID de l'élève, pas l'ID du frais
        try:
            eleve_id_int = int(eleve_id)
            # Vérifier que frais_id est différent de eleve_id pour éviter les confusions
            frais_id_int = int(frais_id)
            if eleve_id_int == frais_id_int:
                # Si les IDs sont identiques, c'est probablement une erreur de construction d'URL
                messages.error(request, f"Erreur: L'ID de l'élève ({eleve_id_int}) ne peut pas être identique à l'ID du frais ({frais_id_int}). Vérifiez l'URL.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)
        except (ValueError, TypeError) as e:
            messages.error(request, f"ID invalide - Élève: {eleve_id}, Frais: {frais_id}. Erreur: {str(e)}")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id if isinstance(eleve_id, int) else 0)
        
        # Récupérer l'inscription de l'élève depuis InscriptionEleve pour l'année scolaire active
        from ..model.inscription_eleve_model import InscriptionEleve
        try:
            inscription = InscriptionEleve.objects.select_related('eleve').get(
                eleve_id=eleve_id_int,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active,
                eleve__isnull=False  # S'assurer que l'élève existe toujours
            )
            eleve = inscription.eleve
            # Vérifier que l'élève est actif
            if not eleve or not eleve.actif:
                messages.error(request, f"Élève introuvable ou inactif (ID: {eleve_id_int}). L'élève doit être inscrit dans l'année scolaire active et être actif.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        except InscriptionEleve.DoesNotExist:
            # Essayer de récupérer l'élève directement pour voir s'il existe
            try:
                eleve_temp = Eleve.objects.get(id=eleve_id_int, etablissement=etablissement, actif=True)
                messages.error(request, f"Élève non inscrit dans l'année scolaire active (ID: {eleve_id_int}). L'élève existe mais n'est pas inscrit via InscriptionEleve pour l'année scolaire {annee_scolaire_active}.")
            except Eleve.DoesNotExist:
                messages.error(request, f"Élève introuvable (ID: {eleve_id_int}). Vérifiez que l'élève existe et est actif dans cet établissement.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        
        # Vérifier que le frais d'inscription existe et appartient à l'élève ET à l'année scolaire active
        try:
            frais_inscription = FraisInscription.objects.get(
                id=frais_id, 
                eleve=eleve,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active
            )
        except FraisInscription.DoesNotExist:
            # Si le frais n'existe pas, essayer de le créer automatiquement
            comptabilite, _ = ComptabiliteEleve.objects.get_or_create(
                eleve=eleve,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active,
                defaults={'statut_paiement': 'a_jour'}
            )
            
            # Récupérer les paramètres de comptabilité spécifiques à la classe de l'élève (ou généraux)
            parametres = None
            if inscription.classe:
                parametres = ComptabiliteController._get_parametres_for_classe(etablissement, inscription.classe)
            
            # Déterminer le type de frais et le montant
            annee_precedente = annee_scolaire_active.annee_debut - 1
            type_frais = 'reinscription'
            
            if eleve.date_inscription and eleve.date_inscription.year == annee_scolaire_active.annee_debut:
                type_frais = 'inscription'
            
            montant = Decimal('0.00')
            if parametres:
                if etablissement.type_etablissement_comptabilite == 'prive':
                    if type_frais == 'reinscription' and parametres.montant_frais_reinscription:
                        montant = parametres.montant_frais_reinscription
                    else:
                        montant = parametres.montant_frais_inscription or Decimal('0.00')
                else:
                    montant = parametres.montant_facturation_annuelle or Decimal('0.00')
            else:
                if etablissement.type_etablissement_comptabilite == 'prive':
                    montant = etablissement.montant_frais_inscription or Decimal('0.00')
                else:
                    montant = etablissement.montant_facturation_annuelle or Decimal('0.00')
            
            if montant > Decimal('0.00'):
                date_echeance = timezone.now().date() + timedelta(days=30)
                frais_inscription = FraisInscription.objects.create(
                    eleve=eleve,
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active,
                    comptabilite_eleve=comptabilite,
                    montant=montant,
                    date_echeance=date_echeance,
                    type_frais=type_frais,
                    statut='en_attente',
                    montant_paye=Decimal('0.00'),
                    reste_a_payer=montant
                )
                messages.info(request, "Frais d'inscription créé automatiquement.")
            else:
                messages.error(request, f"Frais d'inscription introuvable (ID: {frais_id}) et aucun montant configuré.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        
        if request.method == 'POST':
            montant = request.POST.get('montant', '').strip()
            
            # Validation simple et claire du montant
            if not montant:
                messages.error(request, "Veuillez renseigner le montant donné par l'élève.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            try:
                montant_decimal = Decimal(str(montant).replace(',', '.'))
            except (ValueError, InvalidOperation, TypeError):
                messages.error(request, f"Montant invalide : '{montant}'. Veuillez entrer un nombre valide (ex: 5000 ou 5000.50).")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            # Vérifier que le montant est positif
            if montant_decimal <= 0:
                messages.error(request, "Le montant doit être supérieur à 0.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            # IMPORTANT : Recharger l'objet depuis la base de données pour avoir les valeurs à jour
            frais_inscription.refresh_from_db()
            
            # Calculer le reste à payer actuel
            reste_a_payer = frais_inscription.get_reste_a_payer()
            
            # Vérifier que le montant ne dépasse pas le reste à payer
            devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
            if montant_decimal > reste_a_payer:
                messages.error(request, f"Le montant ({montant_decimal} {devise_monnaie}) dépasse le reste à payer ({reste_a_payer} {devise_monnaie}).")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            # Enregistrer le paiement
            try:
                with transaction.atomic():
                    # Ajouter le paiement aux frais d'inscription (met à jour montant_paye automatiquement)
                    frais_inscription.ajouter_paiement(montant_decimal)
                    
                    # IMPORTANT : Recharger l'objet depuis la base de données pour avoir les valeurs à jour
                    frais_inscription.refresh_from_db()
                    
                    # Créer l'enregistrement du paiement dans l'historique
                    enregistre_par_user = None
                    if isinstance(request.user, CompteUser):
                        enregistre_par_user = request.user
                    
                    PaiementEleve.objects.create(
                        eleve=eleve,
                        etablissement=etablissement,
                        annee_scolaire=annee_scolaire_active,
                        type_paiement='frais_inscription',
                        frais_inscription=frais_inscription,
                        montant=montant_decimal,
                        mode_paiement='especes',  # Par défaut
                        reference_paiement='',
                        notes='',
                        enregistre_par=enregistre_par_user
                    )
                    
                    # Mettre à jour le statut de la comptabilité
                    if frais_inscription.comptabilite_eleve:
                        frais_inscription.comptabilite_eleve.verifier_statut_paiement()
                    
                    # Message de succès avec le nouveau reste à payer (après refresh_from_db)
                    nouveau_reste = frais_inscription.get_reste_a_payer()
                    if nouveau_reste == 0:
                        success_msg = f"Paiement complet enregistré ! Frais d'inscription totalement payé ({montant_decimal} {devise_monnaie})."
                    else:
                        success_msg = f"Paiement de {montant_decimal} {devise_monnaie} enregistré. Reste à payer : {nouveau_reste} {devise_monnaie}."
                    messages.success(request, success_msg)

                    from ..services.realtime_helpers import wants_json_response, json_ok, emit_live
                    from ..services.live_serializers import (
                        serialize_comptabilite_paiement_result,
                        serialize_comptabilite_eleve_snapshot,
                    )

                    snapshot = serialize_comptabilite_eleve_snapshot(
                        eleve_id_int, etablissement, annee_scolaire_active, devise_monnaie
                    )
                    live_item = serialize_comptabilite_paiement_result(eleve_id_int, success_msg, snapshot=snapshot)
                    emit_live(
                        etablissement.id,
                        'comptabilite.mise_a_jour',
                        {'event': 'comptabilite.mise_a_jour', 'item': live_item},
                    )
                    if wants_json_response(request):
                        return json_ok(message=success_msg, item=live_item)

                    return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            except Exception as e:
                messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        
        return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

    @staticmethod
    @login_required
    def payer_mensualite_directeur(request, eleve_id, mensualite_id):
        """
        Vue pour enregistrer un paiement partiel ou total d'une mensualité
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions : le directeur a accès à tout, sinon vérifier la permission
        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_voir'):
                messages.error(request, "Vous n'avez pas l'autorisation d'accéder à la comptabilité.")
                return redirect('directeur:dashboard_directeur')
        
        # Récupérer l'année scolaire active AVANT de récupérer l'élève
        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)
        
        # Vérifier que eleve_id est bien un entier et non un ID de mensualité
        try:
            eleve_id_int = int(eleve_id)
        except (ValueError, TypeError):
            messages.error(request, f"ID d'élève invalide : {eleve_id}")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)
        
        # Récupérer l'inscription de l'élève depuis InscriptionEleve pour l'année scolaire active
        from ..model.inscription_eleve_model import InscriptionEleve
        try:
            inscription = InscriptionEleve.objects.select_related('eleve').get(
                eleve_id=eleve_id_int,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active,
                eleve__isnull=False  # S'assurer que l'élève existe toujours
            )
            eleve = inscription.eleve
            # Vérifier que l'élève est actif
            if not eleve or not eleve.actif:
                messages.error(request, f"Élève introuvable ou inactif (ID: {eleve_id_int}). L'élève doit être inscrit dans l'année scolaire active et être actif.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        except InscriptionEleve.DoesNotExist:
            # Essayer de récupérer l'élève directement pour voir s'il existe
            try:
                eleve_temp = Eleve.objects.get(id=eleve_id_int, etablissement=etablissement, actif=True)
                messages.error(request, f"Élève non inscrit dans l'année scolaire active (ID: {eleve_id_int}). L'élève existe mais n'est pas inscrit via InscriptionEleve pour l'année scolaire {annee_scolaire_active}.")
            except Eleve.DoesNotExist:
                messages.error(request, f"Élève introuvable (ID: {eleve_id_int}). Vérifiez que l'élève existe et est actif dans cet établissement.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        
        # Vérifier que la mensualité existe et appartient à l'élève ET à l'année scolaire active
        try:
            mensualite = Mensualite.objects.get(
                id=mensualite_id,
                eleve=eleve,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active
            )
        except Mensualite.DoesNotExist:
            messages.error(request, f"Mensualité introuvable (ID: {mensualite_id}) pour cette année scolaire active. Veuillez vérifier que les mensualités ont été générées pour cet élève.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        
        if request.method == 'POST':
            montant = request.POST.get('montant', '').strip()
            
            # Validation simple et claire du montant
            if not montant:
                messages.error(request, "Veuillez renseigner le montant donné par l'élève.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            try:
                montant_decimal = Decimal(str(montant).replace(',', '.'))
            except (ValueError, InvalidOperation, TypeError):
                messages.error(request, f"Montant invalide : '{montant}'. Veuillez entrer un nombre valide (ex: 5000 ou 5000.50).")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            # Vérifier que le montant est positif
            if montant_decimal <= 0:
                messages.error(request, "Le montant doit être supérieur à 0.")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            # IMPORTANT : Recharger l'objet depuis la base de données pour avoir les valeurs à jour
            mensualite.refresh_from_db()
            
            # Calculer le reste à payer actuel
            reste_a_payer = mensualite.get_reste_a_payer()
            
            # Vérifier que le montant ne dépasse pas le reste à payer
            devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
            if montant_decimal > reste_a_payer:
                messages.error(request, f"Le montant ({montant_decimal} {devise_monnaie}) dépasse le reste à payer ({reste_a_payer} {devise_monnaie}).")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            
            # Enregistrer le paiement
            try:
                with transaction.atomic():
                    # Ajouter le paiement à la mensualité (met à jour montant_paye automatiquement)
                    mensualite.ajouter_paiement(montant_decimal)
                    
                    # IMPORTANT : Recharger l'objet depuis la base de données pour avoir les valeurs à jour
                    mensualite.refresh_from_db()
                    
                    # Créer l'enregistrement du paiement dans l'historique
                    enregistre_par_user = None
                    if isinstance(request.user, CompteUser):
                        enregistre_par_user = request.user
                    
                    PaiementEleve.objects.create(
                        eleve=eleve,
                        etablissement=etablissement,
                        annee_scolaire=annee_scolaire_active,
                        type_paiement='mensualite',
                        mensualite=mensualite,
                        montant=montant_decimal,
                        mode_paiement='especes',  # Par défaut
                        reference_paiement='',
                        notes='',
                        enregistre_par=enregistre_par_user
                    )
                    
                    # Mettre à jour le statut de la comptabilité
                    if mensualite.comptabilite_eleve:
                        mensualite.comptabilite_eleve.verifier_statut_paiement()
                    
                    # Message de succès avec le nouveau reste à payer (après refresh_from_db)
                    nouveau_reste = mensualite.get_reste_a_payer()
                    if nouveau_reste == 0:
                        success_msg = f"Paiement complet enregistré ! Mensualité {mensualite.periode} totalement payée ({montant_decimal} {devise_monnaie})."
                    else:
                        success_msg = f"Paiement de {montant_decimal} {devise_monnaie} enregistré. Reste à payer : {nouveau_reste} {devise_monnaie}."
                    messages.success(request, success_msg)

                    from ..services.realtime_helpers import wants_json_response, json_ok, emit_live
                    from ..services.live_serializers import (
                        serialize_comptabilite_paiement_result,
                        serialize_comptabilite_eleve_snapshot,
                    )

                    snapshot = serialize_comptabilite_eleve_snapshot(
                        eleve_id_int, etablissement, annee_scolaire_active, devise_monnaie
                    )
                    live_item = serialize_comptabilite_paiement_result(eleve_id_int, success_msg, snapshot=snapshot)
                    emit_live(
                        etablissement.id,
                        'comptabilite.mise_a_jour',
                        {'event': 'comptabilite.mise_a_jour', 'item': live_item},
                    )
                    if wants_json_response(request):
                        return json_ok(message=success_msg, item=live_item)

                    return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
            except Exception as e:
                messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        
        return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

    @staticmethod
    @login_required
    def payer_frais_annexe_directeur(request, eleve_id, frais_id):
        """Enregistre un paiement partiel ou total d'un frais annexe."""
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')

        etablissement, is_directeur, personnel = result

        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_voir'):
                messages.error(request, "Vous n'avez pas l'autorisation d'accéder à la comptabilité.")
                return redirect('directeur:dashboard_directeur')

        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)

        try:
            eleve_id_int = int(eleve_id)
        except (ValueError, TypeError):
            messages.error(request, f"ID d'élève invalide : {eleve_id}")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)

        from ..model.inscription_eleve_model import InscriptionEleve
        try:
            inscription = InscriptionEleve.objects.select_related('eleve').get(
                eleve_id=eleve_id_int,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active,
                eleve__isnull=False,
            )
            eleve = inscription.eleve
            if not eleve or not eleve.actif:
                messages.error(request, f"Élève introuvable ou inactif (ID: {eleve_id_int}).")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        except InscriptionEleve.DoesNotExist:
            messages.error(request, f"Élève non inscrit dans l'année scolaire active (ID: {eleve_id_int}).")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

        try:
            frais_annexe = FraisAnnexe.objects.get(
                id=frais_id,
                eleve=eleve,
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active,
            )
        except FraisAnnexe.DoesNotExist:
            messages.error(request, "Frais annexe introuvable pour cette année scolaire active.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

        if request.method != 'POST':
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

        montant = request.POST.get('montant', '').strip()
        if not montant:
            messages.error(request, "Veuillez renseigner le montant donné par l'élève.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

        try:
            montant_decimal = Decimal(str(montant).replace(',', '.'))
        except (ValueError, InvalidOperation, TypeError):
            messages.error(request, f"Montant invalide : '{montant}'.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

        if montant_decimal <= 0:
            messages.error(request, "Le montant doit être supérieur à 0.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

        frais_annexe.refresh_from_db()
        reste_a_payer = frais_annexe.get_reste_a_payer()
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
        if montant_decimal > reste_a_payer:
            messages.error(
                request,
                f"Le montant ({montant_decimal} {devise_monnaie}) dépasse le reste à payer ({reste_a_payer} {devise_monnaie}).",
            )
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

        try:
            with transaction.atomic():
                frais_annexe.ajouter_paiement(montant_decimal)
                frais_annexe.refresh_from_db()

                enregistre_par_user = request.user if isinstance(request.user, CompteUser) else None
                PaiementEleve.objects.create(
                    eleve=eleve,
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active,
                    type_paiement='frais_annexe',
                    frais_annexe=frais_annexe,
                    montant=montant_decimal,
                    mode_paiement='especes',
                    reference_paiement='',
                    notes='',
                    enregistre_par=enregistre_par_user,
                )

                if frais_annexe.comptabilite_eleve:
                    frais_annexe.comptabilite_eleve.verifier_statut_paiement()

                nouveau_reste = frais_annexe.get_reste_a_payer()
                if nouveau_reste == 0:
                    success_msg = (
                        f"Paiement complet enregistré ! {frais_annexe.libelle} "
                        f"totalement payé ({montant_decimal} {devise_monnaie})."
                    )
                else:
                    success_msg = (
                        f"Paiement de {montant_decimal} {devise_monnaie} enregistré. "
                        f"Reste à payer : {nouveau_reste} {devise_monnaie}."
                    )
                messages.success(request, success_msg)

                from ..services.realtime_helpers import wants_json_response, json_ok, emit_live
                from ..services.live_serializers import (
                    serialize_comptabilite_paiement_result,
                    serialize_comptabilite_eleve_snapshot,
                )

                snapshot = serialize_comptabilite_eleve_snapshot(
                    eleve_id_int, etablissement, annee_scolaire_active, devise_monnaie
                )
                live_item = serialize_comptabilite_paiement_result(
                    eleve_id_int, success_msg, snapshot=snapshot
                )
                emit_live(
                    etablissement.id,
                    'comptabilite.mise_a_jour',
                    {'event': 'comptabilite.mise_a_jour', 'item': live_item},
                )
                if wants_json_response(request):
                    return json_ok(message=success_msg, item=live_item)

                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        except Exception as exc:
            messages.error(request, f"Erreur lors de l'enregistrement : {str(exc)}")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

    @staticmethod
    @login_required
    def verifier_statuts_paiement_directeur(request):
        """
        Vérifie tous les statuts de paiement des élèves de l'établissement du directeur
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions : le directeur a accès à tout, sinon vérifier la permission
        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_voir'):
                messages.error(request, "Vous n'avez pas l'autorisation d'accéder à la comptabilité.")
                return redirect('directeur:dashboard_directeur')
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:dashboard_directeur')
        
        # Récupérer toutes les comptabilités
        comptabilites = ComptabiliteEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        )
        
        # Vérifier chaque statut
        compteur_modifies = 0
        for comptabilite in comptabilites:
            ancien_statut = comptabilite.statut_paiement
            nouveau_statut = comptabilite.verifier_statut_paiement()
            if ancien_statut != nouveau_statut:
                compteur_modifies += 1
        
        messages.success(
            request,
            f"Vérification terminée. {compteur_modifies} statut(s) modifié(s) sur {comptabilites.count()} élève(s)."
        )
        
        return redirect('directeur:liste_comptabilite_eleves_directeur')

    @staticmethod
    @login_required
    def parametres_comptabilite_directeur(request):
        """
        Page de gestion des paramètres de scolarité par groupes de classes
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')

        etablissement, is_directeur, personnel = result

        if not is_directeur:
            if not personnel or personnel.fonction not in ['gestionnaire', 'comptable']:
                messages.error(request, "Seul le gestionnaire ou le comptable peut modifier les paramètres de scolarité.")
                return redirect('directeur:dashboard_directeur')

        if not etablissement.module_comptabilite:
            messages.warning(request, "Le module scolarité n'est pas activé pour cet établissement.")
            return redirect('directeur:profil_etablissement')

        parametres_groupes = ParametresComptabiliteGroupeClasse.objects.filter(
            etablissement=etablissement
        ).order_by('-date_modification')

        groupes_disponibles = ParametresComptabiliteGroupeClasse.get_groupes_disponibles(etablissement)
        groupes_deja_assignes = ParametresComptabiliteGroupeClasse.get_groupes_deja_assignes(etablissement)

        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)

        stats_generales = {
            'total_parametres': parametres_groupes.count(),
            'groupes_assignes': len(groupes_deja_assignes),
            'groupes_disponibles': len(groupes_disponibles),
        }

        context = {
            'etablissement': etablissement,
            'parametres_groupes': parametres_groupes,
            'groupes_disponibles': groupes_disponibles,
            'groupes_deja_assignes': groupes_deja_assignes,
            'frais_annexes_form': get_frais_annexes_from_parametres(None),
            'stats_generales': stats_generales,
            'open_ajouter_modal': request.GET.get('modal') == 'ajouter',
            'is_directeur': is_directeur,
            'personnel': personnel,
            'devise_monnaie': devise_monnaie,
        }

        return render(request, 'school_admin/directeur/comptabilite/parametres_comptabilite.html', context)

    @staticmethod
    @login_required
    def bilan_comptable_directeur(request):
        """
        Page de bilan comptable avec statistiques détaillées par mois et annuelles
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions pour les bilans : le directeur a accès à tout, sinon vérifier la permission
        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_bilans'):
                messages.error(request, "Vous n'avez pas l'autorisation d'accéder aux bilans comptables.")
                return redirect('directeur:dashboard_directeur')
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:liste_comptabilite_eleves_directeur')
        
        # Récupérer les paramètres généraux (pour les classes sans paramètres spécifiques)
        try:
            parametres_generaux = ParametresComptabilite.objects.get(etablissement=etablissement)
        except ParametresComptabilite.DoesNotExist:
            parametres_generaux = None
        
        # Récupérer tous les élèves inscrits pour l'année scolaire active
        from ..model.inscription_eleve_model import InscriptionEleve
        inscriptions = InscriptionEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            eleve__isnull=False
        ).select_related('eleve', 'classe')
        
        eleves_ids = [ins.eleve_id for ins in inscriptions if ins.eleve and ins.eleve.actif]
        
        # Récupérer toutes les comptabilités des élèves
        comptabilites = ComptabiliteEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            eleve_id__in=eleves_ids
        ).select_related('eleve')
        
        # Récupérer tous les paiements de l'année scolaire
        paiements = PaiementEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        ).order_by('date_paiement')
        
        # Récupérer toutes les mensualités
        mensualites = Mensualite.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        ).order_by('annee', 'mois')
        
        # Récupérer tous les frais d'inscription
        frais_inscription = FraisInscription.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active
        )
        
        # Créer un dictionnaire pour mapper chaque élève à ses paramètres (spécifiques ou généraux)
        parametres_par_eleve = {}
        for ins in inscriptions:
            if ins.eleve and ins.eleve.actif and ins.classe:
                parametres_eleve = ComptabiliteController._get_parametres_for_classe(etablissement, ins.classe)
                parametres_par_eleve[ins.eleve_id] = parametres_eleve or parametres_generaux
            else:
                parametres_par_eleve[ins.eleve_id] = parametres_generaux
        
        # ========== CALCULS PAR MOIS ==========
        mois_stats = {}
        noms_mois = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                     'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        
        # Parcourir tous les mois de l'année scolaire
        annee_debut = annee_scolaire_active.annee_debut
        annee_fin = annee_scolaire_active.annee_fin
        
        # Déterminer la période de facturation (utiliser les paramètres généraux comme base)
        mois_debut = parametres_generaux.mois_debut_facturation if parametres_generaux else 9
        mois_fin = parametres_generaux.mois_fin_facturation if parametres_generaux else 6
        
        # Générer la liste des mois à analyser
        mois_a_analyser = []
        mois_courant = mois_debut
        annee_courante = annee_debut
        
        while True:
            mois_a_analyser.append((mois_courant, annee_courante))
            mois_courant += 1
            if mois_courant > 12:
                mois_courant = 1
                annee_courante += 1
            if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                break
        
        # Calculer les statistiques pour chaque mois
        for mois_num, annee_num in mois_a_analyser:
            mois_key = f"{annee_num}-{mois_num:02d}"
            
            # Mensualités de ce mois
            mensualites_mois = mensualites.filter(mois=mois_num, annee=annee_num)
            
            # Paiements de ce mois (mensualités)
            paiements_mois = paiements.filter(
                date_paiement__year=annee_num,
                date_paiement__month=mois_num,
                type_paiement='mensualite'
            )
            
            # Élèves avec mensualités en retard pour ce mois
            eleves_en_retard_mois = set()
            eleves_impayes_mois = set()
            
            for mensualite in mensualites_mois:
                # Utiliser les paramètres spécifiques de l'élève si disponibles
                parametres_eleve = parametres_par_eleve.get(mensualite.eleve_id, parametres_generaux)
                if parametres_eleve:
                    mensualite.mettre_a_jour_statut(parametres_eleve)
                
                if mensualite.statut == 'en_retard':
                    eleves_en_retard_mois.add(mensualite.eleve_id)
                elif mensualite.statut == 'impaye':
                    eleves_impayes_mois.add(mensualite.eleve_id)
            
            # Montants dus pour ce mois
            montant_du_mois = sum(m.montant for m in mensualites_mois)
            montant_paye_mois = sum(m.montant_paye for m in mensualites_mois)
            reste_a_payer_mois = montant_du_mois - montant_paye_mois
            
            # Montants collectés ce mois (paiements effectués ce mois)
            montant_collecte_mois = sum(p.montant for p in paiements_mois)
            
            # Nombre total d'élèves avec mensualités ce mois
            eleves_avec_mensualite_mois = len(set(m.eleve_id for m in mensualites_mois))
            
            mois_stats[mois_key] = {
                'mois': mois_num,
                'annee': annee_num,
                'nom_mois': noms_mois[mois_num],
                'periode': f"{noms_mois[mois_num]} {annee_num}",
                'eleves_total': eleves_avec_mensualite_mois,
                'eleves_en_retard': len(eleves_en_retard_mois),
                'eleves_impayes': len(eleves_impayes_mois),
                'montant_du': montant_du_mois,
                'montant_paye': montant_paye_mois,
                'montant_collecte': montant_collecte_mois,
                'reste_a_payer': reste_a_payer_mois,
                'taux_recouvrement': (montant_paye_mois / montant_du_mois * 100) if montant_du_mois > 0 else 0,
            }
        
        # ========== BILAN ANNUEL ==========
        # Total des frais d'inscription
        total_frais_inscription_du = sum(f.montant for f in frais_inscription)
        total_frais_inscription_paye = sum(f.montant_paye for f in frais_inscription)
        total_frais_inscription_reste = total_frais_inscription_du - total_frais_inscription_paye
        
        # Total des mensualités
        total_mensualites_du = sum(m.montant for m in mensualites)
        total_mensualites_paye = sum(m.montant_paye for m in mensualites)
        total_mensualites_reste = total_mensualites_du - total_mensualites_paye

        frais_annexes_qs = FraisAnnexe.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
        )
        total_frais_annexes_du = sum((f.montant for f in frais_annexes_qs), Decimal('0.00'))
        total_frais_annexes_paye = sum((f.montant_paye for f in frais_annexes_qs), Decimal('0.00'))
        total_frais_annexes_reste = total_frais_annexes_du - total_frais_annexes_paye
        
        # Total général
        total_du_annuel = total_frais_inscription_du + total_mensualites_du + total_frais_annexes_du
        total_paye_annuel = total_frais_inscription_paye + total_mensualites_paye + total_frais_annexes_paye
        total_reste_annuel = total_du_annuel - total_paye_annuel
        
        # Taux de recouvrement annuel
        taux_recouvrement_annuel = (total_paye_annuel / total_du_annuel * 100) if total_du_annuel > 0 else 0
        
        # Statistiques des élèves
        total_eleves = len(eleves_ids)
        eleves_a_jour = sum(1 for c in comptabilites if c.statut_paiement == 'a_jour')
        eleves_en_retard = sum(1 for c in comptabilites if c.statut_paiement == 'en_retard')
        eleves_impayes = sum(1 for c in comptabilites if c.statut_paiement == 'impaye')
        
        # Élèves non en règle (selon les critères de est_non_en_regle)
        # Utiliser les paramètres spécifiques de chaque élève
        eleves_non_en_regle = 0
        for comptabilite in comptabilites:
            parametres_eleve = parametres_par_eleve.get(comptabilite.eleve_id, parametres_generaux)
            if comptabilite.est_non_en_regle(parametres_eleve):
                eleves_non_en_regle += 1
        
        # Total des paiements effectués
        total_paiements = paiements.count()
        total_montant_collecte = sum(p.montant for p in paiements)
        
        # Paiements par mode
        paiements_par_mode = {}
        for mode, label in PaiementEleve.MODE_PAIEMENT_CHOICES:
            paiements_mode = paiements.filter(mode_paiement=mode)
            montant_mode = sum(p.montant for p in paiements_mode)
            pourcentage_mode = (montant_mode / total_montant_collecte * 100) if total_montant_collecte > 0 else 0
            paiements_par_mode[mode] = {
                'label': label,
                'nombre': paiements_mode.count(),
                'montant': montant_mode,
                'pourcentage': pourcentage_mode
            }
        
        # Statistiques par classe
        from ..model.classe_model import Classe
        classes_stats = []
        classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
        
        for classe in classes:
            eleves_classe = ComptabiliteController._get_eleves_classe_par_inscription(
                classe, etablissement, annee_scolaire_active
            )
            eleves_classe_ids = [e.id for e in eleves_classe]
            
            comptabilites_classe = comptabilites.filter(eleve_id__in=eleves_classe_ids)
            
            # Récupérer les paramètres spécifiques pour cette classe (ou généraux)
            parametres_classe = ComptabiliteController._get_parametres_for_classe(etablissement, classe)
            
            montant_du_classe = Decimal('0.00')
            montant_paye_classe = Decimal('0.00')
            
            for comptabilite in comptabilites_classe:
                montant_du_classe += comptabilite.calculer_total_du()
                montant_paye_classe += comptabilite.calculer_total_paye()
            
            # Compter les élèves non en règle avec les bons paramètres
            eleves_non_en_regle_classe = 0
            for comptabilite in comptabilites_classe:
                if comptabilite.est_non_en_regle(parametres_classe or parametres_generaux):
                    eleves_non_en_regle_classe += 1
            
            classes_stats.append({
                'classe': classe,
                'nombre_eleves': len(eleves_classe_ids),
                'montant_du': montant_du_classe,
                'montant_paye': montant_paye_classe,
                'reste_a_payer': montant_du_classe - montant_paye_classe,
                'eleves_en_retard': sum(1 for c in comptabilites_classe if c.statut_paiement == 'en_retard'),
                'eleves_impayes': sum(1 for c in comptabilites_classe if c.statut_paiement == 'impaye'),
                'parametres_specifiques': parametres_classe is not None,  # Indiquer si cette classe utilise des paramètres spécifiques
            })
        
        # Récupérer la devise monétaire
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)

        stats_generales = {
            'total_eleves': total_eleves,
            'eleves_a_jour': eleves_a_jour,
            'eleves_en_retard': eleves_en_retard,
            'eleves_impayes': eleves_impayes,
            'taux_recouvrement': taux_recouvrement_annuel,
            'total_du': total_du_annuel,
            'total_paye': total_paye_annuel,
            'total_reste': total_reste_annuel,
            'total_paiements': total_paiements,
        }

        mois_chart = {
            'labels': [s['periode'] for s in mois_stats.values()],
            'montantsDus': [float(s['montant_du']) for s in mois_stats.values()],
            'montantsPayes': [float(s['montant_paye']) for s in mois_stats.values()],
            'montantsCollectes': [float(s['montant_collecte']) for s in mois_stats.values()],
            'tauxRecouvrement': [float(s['taux_recouvrement']) for s in mois_stats.values()],
            'elevesEnRetard': [s['eleves_en_retard'] for s in mois_stats.values()],
            'elevesImpayes': [s['eleves_impayes'] for s in mois_stats.values()],
        }
        modes_chart = {
            'labels': [d['label'] for d in paiements_par_mode.values()],
            'montants': [float(d['montant']) for d in paiements_par_mode.values()],
            'couleurs': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'],
        }
        classes_chart = {
            'labels': [cs['classe'].nom for cs in classes_stats],
            'montantsDus': [float(cs['montant_du']) for cs in classes_stats],
            'montantsPayes': [float(cs['montant_paye']) for cs in classes_stats],
        }
        chart_data = {
            'devise': devise_monnaie or 'FCFA',
            'mois': mois_chart,
            'modes': modes_chart,
            'classes': classes_chart,
        }
        
        context = {
            'etablissement': etablissement,
            'annee_scolaire_active': annee_scolaire_active,
            'stats_generales': stats_generales,
            'parametres': parametres_generaux,  # Paramètres généraux pour référence
            'mois_stats': mois_stats,
            'mois_a_analyser': mois_a_analyser,
            'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
            'noms_mois': noms_mois,
            # Bilan annuel
            'total_eleves': total_eleves,
            'eleves_a_jour': eleves_a_jour,
            'eleves_en_retard': eleves_en_retard,
            'eleves_impayes': eleves_impayes,
            'eleves_non_en_regle': eleves_non_en_regle,
            'total_frais_inscription_du': total_frais_inscription_du,
            'total_frais_inscription_paye': total_frais_inscription_paye,
            'total_frais_inscription_reste': total_frais_inscription_reste,
            'total_mensualites_du': total_mensualites_du,
            'total_mensualites_paye': total_mensualites_paye,
            'total_mensualites_reste': total_mensualites_reste,
            'total_frais_annexes_du': total_frais_annexes_du,
            'total_frais_annexes_paye': total_frais_annexes_paye,
            'total_frais_annexes_reste': total_frais_annexes_reste,
            'total_du_annuel': total_du_annuel,
            'total_paye_annuel': total_paye_annuel,
            'total_reste_annuel': total_reste_annuel,
            'taux_recouvrement_annuel': taux_recouvrement_annuel,
            'total_paiements': total_paiements,
            'total_montant_collecte': total_montant_collecte,
            'paiements_par_mode': paiements_par_mode,
            'classes_stats': classes_stats,
            'chart_data': chart_data,
            'is_directeur': is_directeur,
            'personnel': personnel,
        }
        
        return render(request, 'school_admin/directeur/comptabilite/bilan_comptable.html', context)

    @staticmethod
    @login_required
    def bilan_comptable_classe_directeur(request, classe_id):
        """
        Page de bilan comptable spécifique à une classe avec statistiques détaillées par mois et annuelles
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions pour les bilans : le directeur a accès à tout, sinon vérifier la permission
        if not is_directeur:
            from ..utils.decorators_permissions import check_permission
            if not check_permission(request.user, 'comptabilite_bilans'):
                messages.error(request, "Vous n'avez pas l'autorisation d'accéder aux bilans comptables.")
                return redirect('directeur:dashboard_directeur')
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:liste_comptabilite_eleves_directeur')
        
        # Récupérer la classe
        try:
            classe = Classe.objects.get(id=classe_id, etablissement=etablissement, actif=True)
        except Classe.DoesNotExist:
            messages.error(request, "Classe introuvable.")
            return redirect('directeur:liste_comptabilite_eleves_directeur')
        
        # Récupérer les paramètres de comptabilité spécifiques à cette classe (ou généraux)
        parametres = ComptabiliteController._get_parametres_for_classe(etablissement, classe)
        
        # Récupérer les élèves de la classe via InscriptionEleve
        eleves_classe = ComptabiliteController._get_eleves_classe_par_inscription(
            classe, etablissement, annee_scolaire_active
        )
        eleves_ids = [e.id for e in eleves_classe]
        
        # Récupérer toutes les comptabilités des élèves de la classe
        comptabilites = ComptabiliteEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            eleve_id__in=eleves_ids
        ).select_related('eleve')
        
        # Récupérer tous les paiements des élèves de la classe
        paiements = PaiementEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            eleve_id__in=eleves_ids
        ).order_by('date_paiement')
        
        # Récupérer toutes les mensualités des élèves de la classe
        mensualites = Mensualite.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            eleve_id__in=eleves_ids
        ).order_by('annee', 'mois')
        
        # Récupérer tous les frais d'inscription des élèves de la classe
        frais_inscription = FraisInscription.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            eleve_id__in=eleves_ids
        )
        frais_annexes_classe = FraisAnnexe.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            eleve_id__in=eleves_ids,
        )
        
        # ========== METTRE À JOUR TOUS LES STATUTS AVEC LES PARAMÈTRES SPÉCIFIQUES ==========
        # IMPORTANT : Recalculer les statuts de TOUTES les mensualités avec les paramètres spécifiques de la classe
        # avant de faire les calculs de statistiques pour garantir la cohérence
        if parametres:
            for mensualite in mensualites:
                mensualite.mettre_a_jour_statut(parametres)
        
        # Mettre à jour les statuts de toutes les comptabilités élèves avec les paramètres spécifiques
        for comptabilite in comptabilites:
            comptabilite.verifier_statut_paiement()
        
        # ========== CALCULS PAR MOIS ==========
        mois_stats = {}
        noms_mois = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                     'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        
        # Déterminer la période de facturation selon les paramètres spécifiques ou généraux
        mois_debut = parametres.mois_debut_facturation if parametres else 9
        mois_fin = parametres.mois_fin_facturation if parametres else 6
        
        annee_debut = annee_scolaire_active.annee_debut
        annee_fin = annee_scolaire_active.annee_fin
        
        # Générer la liste des mois à analyser
        mois_a_analyser = []
        mois_courant = mois_debut
        annee_courante = annee_debut
        
        while True:
            mois_a_analyser.append((mois_courant, annee_courante))
            mois_courant += 1
            if mois_courant > 12:
                mois_courant = 1
                annee_courante += 1
            if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                break
        
        # Calculer les statistiques pour chaque mois
        for mois_num, annee_num in mois_a_analyser:
            mois_key = f"{annee_num}-{mois_num:02d}"
            
            # Mensualités de ce mois pour les élèves de la classe
            mensualites_mois = mensualites.filter(mois=mois_num, annee=annee_num)
            
            # Paiements de ce mois (mensualités)
            paiements_mois = paiements.filter(
                date_paiement__year=annee_num,
                date_paiement__month=mois_num,
                type_paiement='mensualite'
            )
            
            # Élèves avec mensualités en retard pour ce mois
            eleves_en_retard_mois = set()
            eleves_impayes_mois = set()
            
            for mensualite in mensualites_mois:
                # Les statuts ont déjà été mis à jour avec les paramètres spécifiques avant cette boucle
                # On utilise simplement les statuts déjà calculés
                if mensualite.statut == 'en_retard':
                    eleves_en_retard_mois.add(mensualite.eleve_id)
                elif mensualite.statut == 'impaye':
                    eleves_impayes_mois.add(mensualite.eleve_id)
            
            # Montants dus pour ce mois
            montant_du_mois = sum(m.montant for m in mensualites_mois)
            montant_paye_mois = sum(m.montant_paye for m in mensualites_mois)
            reste_a_payer_mois = montant_du_mois - montant_paye_mois
            
            # Montants collectés ce mois (paiements effectués ce mois)
            montant_collecte_mois = sum(p.montant for p in paiements_mois)
            
            # Nombre total d'élèves avec mensualités ce mois
            eleves_avec_mensualite_mois = len(set(m.eleve_id for m in mensualites_mois))
            
            mois_stats[mois_key] = {
                'mois': mois_num,
                'annee': annee_num,
                'nom_mois': noms_mois[mois_num],
                'periode': f"{noms_mois[mois_num]} {annee_num}",
                'eleves_total': eleves_avec_mensualite_mois,
                'eleves_en_retard': len(eleves_en_retard_mois),
                'eleves_impayes': len(eleves_impayes_mois),
                'montant_du': montant_du_mois,
                'montant_paye': montant_paye_mois,
                'montant_collecte': montant_collecte_mois,
                'reste_a_payer': reste_a_payer_mois,
                'taux_recouvrement': (montant_paye_mois / montant_du_mois * 100) if montant_du_mois > 0 else 0,
            }
        
        # ========== BILAN ANNUEL ==========
        # Total des frais d'inscription
        total_frais_inscription_du = sum(f.montant for f in frais_inscription)
        total_frais_inscription_paye = sum(f.montant_paye for f in frais_inscription)
        total_frais_inscription_reste = total_frais_inscription_du - total_frais_inscription_paye
        
        # Total des mensualités
        total_mensualites_du = sum(m.montant for m in mensualites)
        total_mensualites_paye = sum(m.montant_paye for m in mensualites)
        total_mensualites_reste = total_mensualites_du - total_mensualites_paye

        total_frais_annexes_du = sum((f.montant for f in frais_annexes_classe), Decimal('0.00'))
        total_frais_annexes_paye = sum((f.montant_paye for f in frais_annexes_classe), Decimal('0.00'))
        total_frais_annexes_reste = total_frais_annexes_du - total_frais_annexes_paye
        
        # Total général
        total_du_annuel = total_frais_inscription_du + total_mensualites_du + total_frais_annexes_du
        total_paye_annuel = total_frais_inscription_paye + total_mensualites_paye + total_frais_annexes_paye
        total_reste_annuel = total_du_annuel - total_paye_annuel
        
        # Taux de recouvrement annuel
        taux_recouvrement_annuel = (total_paye_annuel / total_du_annuel * 100) if total_du_annuel > 0 else 0
        
        # Statistiques des élèves
        total_eleves = len(eleves_ids)
        eleves_a_jour = sum(1 for c in comptabilites if c.statut_paiement == 'a_jour')
        eleves_en_retard = sum(1 for c in comptabilites if c.statut_paiement == 'en_retard')
        eleves_impayes = sum(1 for c in comptabilites if c.statut_paiement == 'impaye')
        
        # Élèves non en règle (utiliser les paramètres spécifiques de la classe)
        eleves_non_en_regle = sum(1 for c in comptabilites if c.est_non_en_regle(parametres))
        
        # Total des paiements effectués
        total_paiements = paiements.count()
        total_montant_collecte = sum(p.montant for p in paiements)
        
        # Paiements par mode
        paiements_par_mode = {}
        for mode, label in PaiementEleve.MODE_PAIEMENT_CHOICES:
            paiements_mode = paiements.filter(mode_paiement=mode)
            montant_mode = sum(p.montant for p in paiements_mode)
            pourcentage_mode = (montant_mode / total_montant_collecte * 100) if total_montant_collecte > 0 else 0
            paiements_par_mode[mode] = {
                'label': label,
                'nombre': paiements_mode.count(),
                'montant': montant_mode,
                'pourcentage': pourcentage_mode
            }
        
        # Statistiques par élève
        eleves_stats = []
        for eleve in eleves_classe:
            comptabilite = comptabilites.filter(eleve_id=eleve.id).first()
            if comptabilite:
                montant_du_eleve = comptabilite.calculer_total_du()
                montant_paye_eleve = comptabilite.calculer_total_paye()
                reste_a_payer_eleve = montant_du_eleve - montant_paye_eleve
                
                eleves_stats.append({
                    'eleve': eleve,
                    'comptabilite': comptabilite,
                    'montant_du': montant_du_eleve,
                    'montant_paye': montant_paye_eleve,
                    'reste_a_payer': reste_a_payer_eleve,
                    'statut': comptabilite.statut_paiement,
                    'est_non_en_regle': comptabilite.est_non_en_regle(parametres)
                })
        
        # Récupérer la devise monétaire
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)

        stats_generales = {
            'total_eleves': total_eleves,
            'eleves_a_jour': eleves_a_jour,
            'eleves_en_retard': eleves_en_retard,
            'eleves_impayes': eleves_impayes,
            'taux_recouvrement': taux_recouvrement_annuel,
            'total_du': total_du_annuel,
            'total_paye': total_paye_annuel,
            'total_reste': total_reste_annuel,
            'total_paiements': total_paiements,
        }

        chart_data = {
            'devise': devise_monnaie or 'FCFA',
            'mois': {
                'labels': [s['periode'] for s in mois_stats.values()],
                'montantsDus': [float(s['montant_du']) for s in mois_stats.values()],
                'montantsPayes': [float(s['montant_paye']) for s in mois_stats.values()],
                'montantsCollectes': [float(s['montant_collecte']) for s in mois_stats.values()],
                'tauxRecouvrement': [float(s['taux_recouvrement']) for s in mois_stats.values()],
                'elevesEnRetard': [s['eleves_en_retard'] for s in mois_stats.values()],
                'elevesImpayes': [s['eleves_impayes'] for s in mois_stats.values()],
            },
            'modes': {
                'labels': [d['label'] for d in paiements_par_mode.values()],
                'montants': [float(d['montant']) for d in paiements_par_mode.values()],
                'couleurs': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'],
            },
            'classes': {'labels': [], 'montantsDus': [], 'montantsPayes': []},
        }
        
        context = {
            'etablissement': etablissement,
            'annee_scolaire_active': annee_scolaire_active,
            'classe': classe,
            'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
            'stats_generales': stats_generales,
            'chart_data': chart_data,
            'parametres': parametres,
            'mois_stats': mois_stats,
            'mois_a_analyser': mois_a_analyser,
            'noms_mois': noms_mois,
            # Bilan annuel
            'total_eleves': total_eleves,
            'eleves_a_jour': eleves_a_jour,
            'eleves_en_retard': eleves_en_retard,
            'eleves_impayes': eleves_impayes,
            'eleves_non_en_regle': eleves_non_en_regle,
            'total_frais_inscription_du': total_frais_inscription_du,
            'total_frais_inscription_paye': total_frais_inscription_paye,
            'total_frais_inscription_reste': total_frais_inscription_reste,
            'total_mensualites_du': total_mensualites_du,
            'total_mensualites_paye': total_mensualites_paye,
            'total_mensualites_reste': total_mensualites_reste,
            'total_frais_annexes_du': total_frais_annexes_du,
            'total_frais_annexes_paye': total_frais_annexes_paye,
            'total_frais_annexes_reste': total_frais_annexes_reste,
            'total_du_annuel': total_du_annuel,
            'total_paye_annuel': total_paye_annuel,
            'total_reste_annuel': total_reste_annuel,
            'taux_recouvrement_annuel': taux_recouvrement_annuel,
            'total_paiements': total_paiements,
            'total_montant_collecte': total_montant_collecte,
            'paiements_par_mode': paiements_par_mode,
            'eleves_stats': eleves_stats,
            'is_directeur': is_directeur,
            'personnel': personnel,
        }
        
        return render(request, 'school_admin/directeur/comptabilite/bilan_comptable_classe.html', context)

    @staticmethod
    @login_required
    def liste_parametres_groupes_directeur(request):
        """
        Redirige vers la page principale des paramètres de scolarité
        """
        return redirect('directeur:parametres_comptabilite_directeur')

    @staticmethod
    @login_required
    def ajouter_modifier_parametres_groupe_directeur(request, parametre_id=None):
        """
        Créer ou modifier un paramètre spécifique par groupe de classes
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions pour les paramètres : seul le gestionnaire/comptable ou le directeur peut modifier
        if not is_directeur:
            if not personnel or personnel.fonction not in ['gestionnaire', 'comptable']:
                messages.error(request, "Seul le gestionnaire ou le comptable peut modifier les paramètres de comptabilité.")
                return redirect('directeur:dashboard_directeur')
        
        # Vérifier que le module comptabilité est activé
        if not etablissement.module_comptabilite:
            messages.warning(request, "Le module comptabilité n'est pas activé pour cet établissement.")
            return redirect('directeur:profil_etablissement')
        
        # Récupérer ou créer le paramètre
        parametre = None
        is_edit = False
        if parametre_id:
            try:
                parametre = ParametresComptabiliteGroupeClasse.objects.get(
                    id=parametre_id,
                    etablissement=etablissement
                )
                is_edit = True
            except ParametresComptabiliteGroupeClasse.DoesNotExist:
                messages.error(request, "Paramètre spécifique introuvable.")
                return redirect('directeur:parametres_comptabilite_directeur')
        
        if request.method == 'GET' and not parametre_id:
            from django.urls import reverse
            return redirect(f"{reverse('directeur:parametres_comptabilite_directeur')}?modal=ajouter")

        # Récupérer les groupes de classes disponibles
        groupes_disponibles = ParametresComptabiliteGroupeClasse.get_groupes_disponibles(etablissement)
        groupes_deja_assignes = ParametresComptabiliteGroupeClasse.get_groupes_deja_assignes(
            etablissement,
            exclude_pk=parametre.id if parametre else None
        )
        
        if request.method == 'POST':
            try:
                # Récupérer les données du formulaire
                nom = request.POST.get('nom', '').strip()
                groupes_classes_selected = request.POST.getlist('groupes_classes')
                
                montant_frais_inscription = request.POST.get('montant_frais_inscription', '0')
                montant_frais_reinscription = request.POST.get('montant_frais_reinscription', '0')
                montant_mensualite = request.POST.get('montant_mensualite', '0')
                montant_facturation_annuelle = request.POST.get('montant_facturation_annuelle', '0')
                type_facturation = request.POST.get('type_facturation', 'mensuel')
                
                autoriser_retards = request.POST.get('autoriser_retards') == 'on'
                autoriser_paiements_partiels = request.POST.get('autoriser_paiements_partiels') == 'on'
                delai_tolerance_retard = int(request.POST.get('delai_tolerance_retard', 15))
                
                envoyer_rappels_automatiques = request.POST.get('envoyer_rappels_automatiques') == 'on'
                jours_avant_rappel = int(request.POST.get('jours_avant_rappel', 7))
                jours_apres_retard_rappel = int(request.POST.get('jours_apres_retard_rappel', 3))
                
                mois_debut_facturation = int(request.POST.get('mois_debut_facturation', 9))
                mois_fin_facturation = int(request.POST.get('mois_fin_facturation', 6))
                
                appliquer_remise_famille_nombreuse = request.POST.get('appliquer_remise_famille_nombreuse') == 'on'
                pourcentage_remise_famille_nombreuse = request.POST.get('pourcentage_remise_famille_nombreuse', '0')
                nombre_enfants_minimum_remise = int(request.POST.get('nombre_enfants_minimum_remise', 3))
                
                nombre_max_paiements_partiels = int(request.POST.get('nombre_max_paiements_partiels', 3))
                
                jour_versement = int(request.POST.get('jour_versement', 5)) if etablissement.type_etablissement_comptabilite == 'prive' else 5
                paiement_en_avance = request.POST.get('paiement_en_avance') == 'on' if etablissement.type_etablissement_comptabilite == 'prive' else False
                frais_annexes_data = extraire_frais_annexes_depuis_post(request.POST)
                
                from ..services.realtime_helpers import wants_json_response, json_ok, json_fail, emit_live
                from ..services.live_serializers import serialize_parametres_groupe_classe

                def _parametres_fail(message):
                    if wants_json_response(request):
                        return json_fail(message=message)
                    messages.error(request, message)
                    return redirect('directeur:parametres_comptabilite_directeur')

                # Validation
                if not nom:
                    return _parametres_fail("Le nom du paramètre est obligatoire.")
                
                if not groupes_classes_selected:
                    return _parametres_fail("Vous devez sélectionner au moins un groupe de classes.")
                
                # Vérifier que les groupes sélectionnés ne sont pas déjà assignés
                groupes_deja_utilises = set(groupes_classes_selected) & set(groupes_deja_assignes)
                if groupes_deja_utilises:
                    return _parametres_fail(
                        f"Les groupes suivants sont déjà assignés à un autre paramètre : {', '.join(groupes_deja_utilises)}"
                    )
                
                # Créer ou mettre à jour
                modifie_par_user = None
                if isinstance(request.user, CompteUser):
                    modifie_par_user = request.user
                
                if not parametre:
                    # Créer
                    parametre_data = {
                        'etablissement': etablissement,
                        'nom': nom,
                        'groupes_classes': groupes_classes_selected,
                        'montant_frais_inscription': Decimal(montant_frais_inscription) if montant_frais_inscription else Decimal('0.00'),
                        'montant_frais_reinscription': Decimal(montant_frais_reinscription) if montant_frais_reinscription else Decimal('0.00'),
                        'montant_mensualite': Decimal(montant_mensualite) if montant_mensualite else Decimal('0.00'),
                        'montant_facturation_annuelle': Decimal(montant_facturation_annuelle) if montant_facturation_annuelle else Decimal('0.00'),
                        'type_facturation': type_facturation,
                        'autoriser_retards': autoriser_retards,
                        'autoriser_paiements_partiels': autoriser_paiements_partiels,
                        'delai_tolerance_retard': delai_tolerance_retard,
                        'envoyer_rappels_automatiques': envoyer_rappels_automatiques,
                        'jours_avant_rappel': jours_avant_rappel,
                        'jours_apres_retard_rappel': jours_apres_retard_rappel,
                        'mois_debut_facturation': mois_debut_facturation,
                        'mois_fin_facturation': mois_fin_facturation,
                        'appliquer_remise_famille_nombreuse': appliquer_remise_famille_nombreuse,
                        'pourcentage_remise_famille_nombreuse': Decimal(pourcentage_remise_famille_nombreuse) if pourcentage_remise_famille_nombreuse else Decimal('0.00'),
                        'nombre_enfants_minimum_remise': nombre_enfants_minimum_remise,
                        'nombre_max_paiements_partiels': nombre_max_paiements_partiels,
                        'jour_versement': jour_versement,
                        'paiement_en_avance': paiement_en_avance,
                        'frais_annexes': frais_annexes_data,
                    }
                    if modifie_par_user:
                        parametre_data['modifie_par'] = modifie_par_user
                    
                    parametre = ParametresComptabiliteGroupeClasse.objects.create(**parametre_data)
                    action_live = 'created'
                    
                    # Mettre à jour automatiquement le système de comptabilité
                    try:
                        parametre.mettre_a_jour_systeme_comptabilite()
                        success_msg = "Paramètre spécifique créé avec succès. Le système de comptabilité a été mis à jour automatiquement."
                    except Exception as e:
                        success_msg = f"Paramètre spécifique créé avec succès, mais erreur lors de la mise à jour automatique : {str(e)}"
                else:
                    # Mettre à jour
                    parametre.nom = nom
                    parametre.groupes_classes = groupes_classes_selected
                    parametre.montant_frais_inscription = Decimal(montant_frais_inscription) if montant_frais_inscription else Decimal('0.00')
                    parametre.montant_frais_reinscription = Decimal(montant_frais_reinscription) if montant_frais_reinscription else Decimal('0.00')
                    parametre.montant_mensualite = Decimal(montant_mensualite) if montant_mensualite else Decimal('0.00')
                    parametre.montant_facturation_annuelle = Decimal(montant_facturation_annuelle) if montant_facturation_annuelle else Decimal('0.00')
                    parametre.type_facturation = type_facturation
                    parametre.autoriser_retards = autoriser_retards
                    parametre.autoriser_paiements_partiels = autoriser_paiements_partiels
                    parametre.delai_tolerance_retard = delai_tolerance_retard
                    parametre.envoyer_rappels_automatiques = envoyer_rappels_automatiques
                    parametre.jours_avant_rappel = jours_avant_rappel
                    parametre.jours_apres_retard_rappel = jours_apres_retard_rappel
                    parametre.mois_debut_facturation = mois_debut_facturation
                    parametre.mois_fin_facturation = mois_fin_facturation
                    parametre.appliquer_remise_famille_nombreuse = appliquer_remise_famille_nombreuse
                    parametre.pourcentage_remise_famille_nombreuse = Decimal(pourcentage_remise_famille_nombreuse) if pourcentage_remise_famille_nombreuse else Decimal('0.00')
                    parametre.nombre_enfants_minimum_remise = nombre_enfants_minimum_remise
                    parametre.nombre_max_paiements_partiels = nombre_max_paiements_partiels
                    
                    if etablissement.type_etablissement_comptabilite == 'prive':
                        parametre.jour_versement = jour_versement
                        parametre.paiement_en_avance = paiement_en_avance

                    parametre.frais_annexes = frais_annexes_data
                    
                    if modifie_par_user:
                        parametre.modifie_par = modifie_par_user
                    
                    parametre.save()
                    action_live = 'updated'
                    
                    # Mettre à jour automatiquement le système de comptabilité
                    try:
                        parametre.mettre_a_jour_systeme_comptabilite()
                        success_msg = "Paramètre spécifique modifié avec succès. Le système de comptabilité a été mis à jour automatiquement."
                    except Exception as e:
                        success_msg = f"Paramètre spécifique modifié avec succès, mais erreur lors de la mise à jour automatique : {str(e)}"
                
                live_item = serialize_parametres_groupe_classe(
                    parametre, etablissement, action=action_live
                )
                emit_live(
                    etablissement.id,
                    'comptabilite.parametres',
                    {'event': 'comptabilite.parametres', 'item': live_item},
                )
                if wants_json_response(request):
                    return json_ok(message=success_msg, item=live_item)
                messages.success(request, success_msg)
                return redirect('directeur:parametres_comptabilite_directeur')
            
            except Exception as e:
                from ..services.realtime_helpers import wants_json_response, json_fail
                if wants_json_response(request):
                    return json_fail(message=f"Erreur lors de l'enregistrement : {str(e)}")
                messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
        
        # Récupérer la devise monétaire
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
        
        context = {
            'etablissement': etablissement,
            'parametre': parametre,
            'is_edit': is_edit,
            'groupes_disponibles': groupes_disponibles,
            'groupes_deja_assignes': groupes_deja_assignes,
            'frais_annexes_form': get_frais_annexes_from_parametres(parametre),
            'is_directeur': is_directeur,
            'personnel': personnel,
            'devise_monnaie': devise_monnaie,
        }
        
        return render(request, 'school_admin/directeur/comptabilite/ajouter_modifier_parametres_groupe.html', context)

    @staticmethod
    def _get_parametres_for_classe(etablissement, classe):
        """
        Retourne les paramètres de comptabilité appropriés pour une classe donnée.
        Retourne les paramètres spécifiques si disponibles, sinon les paramètres généraux.
        Retourne None si aucun paramètre n'est configuré.
        """
        import re
        
        # Extraire le nom du groupe de classes depuis le nom de la classe
        nom = classe.nom
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        if match:
            nom_groupe = match.group(1).strip()
        else:
            nom_groupe = nom.strip()
        
        # Chercher les paramètres spécifiques pour ce groupe
        parametres_specifiques = ParametresComptabiliteGroupeClasse.get_parametres_for_classe(
            etablissement,
            nom_groupe
        )
        
        if parametres_specifiques:
            return parametres_specifiques
        
        # Sinon, retourner les paramètres généraux
        try:
            return ParametresComptabilite.objects.get(etablissement=etablissement)
        except ParametresComptabilite.DoesNotExist:
            return None

    @staticmethod
    @login_required
    def supprimer_parametres_groupe_directeur(request, parametre_id):
        """
        Supprimer un paramètre spécifique par groupe de classes
        """
        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        
        etablissement, is_directeur, personnel = result
        
        # Vérifier les permissions
        if not is_directeur:
            if not personnel or personnel.fonction not in ['gestionnaire', 'comptable']:
                messages.error(request, "Seul le gestionnaire ou le comptable peut supprimer les paramètres de comptabilité.")
                return redirect('directeur:dashboard_directeur')
        
        from ..services.realtime_helpers import wants_json_response, json_ok, json_fail, emit_live
        from ..services.live_serializers import serialize_parametres_groupe_deleted

        try:
            parametre = ParametresComptabiliteGroupeClasse.objects.get(
                id=parametre_id,
                etablissement=etablissement
            )
            deleted_id = parametre.id
            parametre.delete()
            success_msg = "Paramètre spécifique supprimé avec succès."
            live_item = serialize_parametres_groupe_deleted(deleted_id, etablissement)
            emit_live(
                etablissement.id,
                'comptabilite.parametres',
                {'event': 'comptabilite.parametres', 'item': live_item},
            )
            if wants_json_response(request):
                return json_ok(message=success_msg, item=live_item)
            messages.success(request, success_msg)
        except ParametresComptabiliteGroupeClasse.DoesNotExist:
            if wants_json_response(request):
                return json_fail(message="Paramètre spécifique introuvable.")
            messages.error(request, "Paramètre spécifique introuvable.")
        
        return redirect('directeur:parametres_comptabilite_directeur')

    @staticmethod
    def _emit_parametres_live(etablissement, parametre, action='updated', parametre_id=None):
        from ..services.live_serializers import serialize_parametres_groupe_classe
        from ..services.realtime_helpers import emit_live

        if parametre is not None:
            item = serialize_parametres_groupe_classe(parametre, etablissement)
            item['action'] = action
        else:
            item = {'id': parametre_id, 'action': action}
        emit_live(
            etablissement.id,
            'comptabilite.parametres',
            {'event': 'comptabilite.parametres', 'item': item},
        )

