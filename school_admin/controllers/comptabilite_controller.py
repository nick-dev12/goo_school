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
    frais_annexes_actifs,
    get_frais_annexes_from_parametres,
)
from ..model.parametres_comptabilite_model import ParametresComptabilite
from ..model.parametres_comptabilite_groupe_classe_model import ParametresComptabiliteGroupeClasse
from ..model.compte_user import CompteUser
from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.eleve_model import Eleve
from ..model.classe_model import Classe
from school_admin.services.comptabilite_generale import pont_paiement_eleve
from school_admin.utils.tarifs_mensualite import (
    etat_depuis_mensualite,
    etat_ligne_frais,
    etat_mois_impayes,
    extraire_tarifs_par_mois,
    mois_ordre_form,
    phrase_paliers,
    tranches_form,
)


def frais_annexes_en_transition(parametre, annee_scolaire):
    """Anciennes charges sans choix explicite, limitées aux classes du jeu."""
    from ..model.inscription_eleve_model import InscriptionEleve
    from ..model.comptabilite_eleve_model import ChoixFraisAnnexeEleve
    from ..utils.frais_annexes import frais_au_choix_pour_parametres

    if annee_scolaire is None:
        return {}
    options = {item['code']: item for item in frais_au_choix_pour_parametres(parametre)}
    if not options:
        return {}
    inscriptions = {
        row.eleve_id: row
        for row in InscriptionEleve.objects.filter(
            etablissement=parametre.etablissement,
            annee_scolaire=annee_scolaire,
            eleve__isnull=False,
        ).select_related('classe', 'eleve')
        if row.classe and ComptabiliteController._nom_groupe_classe(row.classe) in (parametre.groupes_classes or [])
    }
    if not inscriptions:
        return {}
    choix_existants = set(ChoixFraisAnnexeEleve.objects.filter(
        eleve_id__in=inscriptions,
        annee_scolaire=annee_scolaire,
        code__in=options,
    ).values_list('eleve_id', 'code'))
    transitions = {}
    for charge in FraisAnnexe.objects.filter(
        etablissement=parametre.etablissement,
        annee_scolaire=annee_scolaire,
        eleve_id__in=inscriptions,
        code__in=options,
    ).exclude(statut='clos'):
        if (charge.eleve_id, charge.code) not in choix_existants:
            transitions.setdefault(charge.code, []).append((charge, inscriptions[charge.eleve_id]))
    return transitions


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
    def _compta_redirect_apres_paiement(
        request,
        paiement,
        eleve_id,
        success_msg,
        etablissement,
        annee_scolaire_active,
        devise_monnaie,
    ):
        """Après encaissement : live update + affichage du reçu imprimable."""
        from django.urls import reverse
        from ..services.realtime_helpers import wants_json_response, json_ok, emit_live
        from ..services.live_serializers import (
            serialize_comptabilite_paiement_result,
            serialize_comptabilite_eleve_snapshot,
        )

        paiement.refresh_from_db()
        recu_url = reverse('directeur:recu_paiement_directeur', args=[paiement.id])

        snapshot = serialize_comptabilite_eleve_snapshot(
            eleve_id, etablissement, annee_scolaire_active, devise_monnaie
        )
        live_item = serialize_comptabilite_paiement_result(
            eleve_id, success_msg, snapshot=snapshot, paiement_id=paiement.id, recu_url=recu_url
        )
        emit_live(
            etablissement.id,
            'comptabilite.mise_a_jour',
            {'event': 'comptabilite.mise_a_jour', 'item': live_item},
        )
        if wants_json_response(request):
            return json_ok(
                message=success_msg,
                item=live_item,
                paiement_id=paiement.id,
                recu_url=recu_url,
            )

        return redirect(f'{recu_url}?auto_print=1')

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
        
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)

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
            
            parametres_groupe = ComptabiliteController._parametres_groupe_for_classe(
                etablissement, classe
            )
            parametres = parametres_groupe
            show_colonne_mensualite = bool(
                parametres_groupe
                and etablissement.type_etablissement_comptabilite == 'prive'
                and parametres_groupe.type_facturation == 'mensuel'
                and (
                    (parametres_groupe.montant_mensualite or Decimal('0')) > 0
                    or parametres_groupe.montants_mensualite_par_mois
                )
            )
            show_colonne_annexes = bool(
                parametres_groupe
                and frais_annexes_actifs(getattr(parametres_groupe, 'frais_annexes', None))
            )

            eleves_comptabilite = []
            aujourdhui = timezone.now().date()
            cle_aujourdhui = (aujourdhui.year, aujourdhui.month)
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
                
                total_du = Decimal('0.00')
                total_paye = Decimal('0.00')
                reste_a_payer = Decimal('0.00')
                frais_inscription = Decimal('0.00')
                mensualites_total = Decimal('0.00')
                mensualites_reste = Decimal('0.00')
                frais_annexes_total = Decimal('0.00')
                frais_annexes_paye = Decimal('0.00')
                frais_annexes_reste = Decimal('0.00')
                est_non_en_regle = False
                inscription_etat = etat_ligne_frais(0, 0)
                mensualites_etat = etat_ligne_frais(0, 0)
                mois_en_cours_etat = etat_ligne_frais(0, 0)
                mois_suivant_etat = etat_ligne_frais(0, 0)
                mois_impaye_etat = etat_ligne_frais(0, 0)
                annexes_etat = etat_ligne_frais(0, 0)

                if parametres_groupe:
                    comptabilite.verifier_statut_paiement()
                    mensualites_qs = list(
                        Mensualite.objects.filter(comptabilite_eleve=comptabilite).order_by(
                            'annee', 'mois'
                        )
                    )
                    for mensualite in mensualites_qs:
                        mensualite.mettre_a_jour_statut(parametres)
                    est_non_en_regle = comptabilite.est_non_en_regle(parametres)
                    total_du = comptabilite.calculer_total_du()
                    total_paye = comptabilite.calculer_total_paye()
                    reste_a_payer = total_du - total_paye
                    frais_inscription_obj = FraisInscription.objects.filter(
                        comptabilite_eleve=comptabilite
                    ).first()
                    if frais_inscription_obj:
                        frais_inscription = frais_inscription_obj.montant
                        inscription_etat = etat_ligne_frais(
                            frais_inscription_obj.montant,
                            frais_inscription_obj.montant_paye,
                        )
                        inscription_etat['mois_nom'] = (
                            'Réinscription'
                            if frais_inscription_obj.type_frais == 'reinscription'
                            else 'Inscription'
                        )
                    mensualites_paye = Decimal('0.00')
                    mois_en_cours_obj = None
                    mois_suivant_obj = None
                    for mensualite in mensualites_qs:
                        mensualites_total += mensualite.montant
                        mensualites_paye += mensualite.montant_paye or Decimal('0.00')
                        mensualites_reste += mensualite.get_reste_a_payer()
                        cle_mois = (mensualite.annee, mensualite.mois)
                        if cle_mois == cle_aujourdhui:
                            mois_en_cours_obj = mensualite
                        elif cle_mois > cle_aujourdhui and mois_suivant_obj is None:
                            mois_suivant_obj = mensualite
                    mensualites_etat = etat_ligne_frais(mensualites_total, mensualites_paye)
                    mois_en_cours_etat = etat_depuis_mensualite(mois_en_cours_obj)
                    mois_suivant_etat = etat_depuis_mensualite(mois_suivant_obj)
                    mois_impaye_etat = etat_mois_impayes(mensualites_qs, cle_aujourdhui)
                    for frais in FraisAnnexe.objects.filter(comptabilite_eleve=comptabilite):
                        frais_annexes_total += frais.montant
                        frais_annexes_paye += frais.montant_paye
                    frais_annexes_reste = frais_annexes_total - frais_annexes_paye
                    annexes_etat = etat_ligne_frais(frais_annexes_total, frais_annexes_paye)
                    if frais_annexes_total > 0:
                        show_colonne_annexes = True

                eleves_comptabilite.append({
                    'eleve': eleve,
                    'comptabilite': comptabilite,
                    'total_du': total_du,
                    'total_paye': total_paye,
                    'reste_a_payer': reste_a_payer,
                    'frais_inscription': frais_inscription,
                    'mensualites_total': mensualites_total,
                    'mensualites_reste': mensualites_reste,
                    'frais_annexes_total': frais_annexes_total,
                    'frais_annexes_paye': frais_annexes_paye,
                    'frais_annexes_reste': frais_annexes_reste,
                    'est_non_en_regle': est_non_en_regle,
                    'inscription_etat': inscription_etat,
                    'mensualites_etat': mensualites_etat,
                    'mois_en_cours_etat': mois_en_cours_etat,
                    'mois_suivant_etat': mois_suivant_etat,
                    'mois_impaye_etat': mois_impaye_etat,
                    'annexes_etat': annexes_etat,
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
                'parametres_configures': parametres_groupe is not None,
                'show_colonne_mensualite': show_colonne_mensualite,
                'show_colonne_annexes': show_colonne_annexes,
                'paliers_mensualite': parametres_groupe.paliers_mensualite if parametres_groupe else [],
                'phrase_paliers': phrase_paliers(parametres_groupe, devise_monnaie) if parametres_groupe else '',
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
        
        from ..utils.directeur_ui_tabs import attach_niveau_classe_tab_context

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
        attach_niveau_classe_tab_context(request, context, dict(classes_grouped))
        
        from ..services.suivi_eleves import enrichir as _enrichir_suivi
        _enrichir_suivi(request, context, 'compta')
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
        ).select_related(
            'frais_annexe', 'mensualite', 'frais_inscription'
        ).order_by('-date_paiement')
        
        # Calculer le montant déjà payé depuis la table PaiementEleve pour chaque frais d'inscription
        frais_inscription_avec_paiements = []
        for frais in frais_inscription:
            # Calculer le montant total payé depuis les paiements liés à ce frais
            # Utiliser Decimal pour éviter les problèmes de précision
            montant_paye_depuis_paiements = Decimal('0.00')
            
            paiements_frais = list(
                PaiementEleve.objects.filter(
                    frais_inscription=frais,
                    eleve=eleve,
                    annee_scolaire=annee_scolaire_active,
                    type_paiement='frais_inscription',
                ).order_by('-date_paiement')
            )

            for paiement in paiements_frais:
                montant_paye_depuis_paiements += Decimal(str(paiement.montant))

            reste_a_payer_frais = Decimal(str(frais.montant)) - montant_paye_depuis_paiements
            frais_inscription_avec_paiements.append({
                'frais': frais,
                'montant_total': frais.montant,
                'montant_paye': montant_paye_depuis_paiements,
                'reste_a_payer': reste_a_payer_frais if reste_a_payer_frais > Decimal('0.00') else Decimal('0.00'),
                'paiements': paiements_frais,
            })
        
        # Calculer le montant déjà payé depuis la table PaiementEleve pour chaque mensualité
        mensualites_avec_paiements = []
        for mensualite in mensualites:
            # Calculer le montant total payé depuis les paiements liés à cette mensualité
            # Utiliser Decimal pour éviter les problèmes de précision
            montant_paye_depuis_paiements = Decimal('0.00')
            
            paiements_mensualite = list(
                PaiementEleve.objects.filter(
                    mensualite=mensualite,
                    eleve=eleve,
                    annee_scolaire=annee_scolaire_active,
                    type_paiement='mensualite',
                ).order_by('-date_paiement')
            )

            for paiement in paiements_mensualite:
                montant_paye_depuis_paiements += Decimal(str(paiement.montant))

            reste_a_payer_mensualite = Decimal(str(mensualite.montant)) - montant_paye_depuis_paiements
            mensualites_avec_paiements.append({
                'mensualite': mensualite,
                'montant_total': mensualite.montant,
                'montant_paye': montant_paye_depuis_paiements,
                'reste_a_payer': reste_a_payer_mensualite if reste_a_payer_mensualite > Decimal('0.00') else Decimal('0.00'),
                'paiements': paiements_mensualite,
            })

        frais_annexes = FraisAnnexe.objects.filter(
            comptabilite_eleve=comptabilite
        ).order_by('libelle')
        frais_annexes_avec_paiements = []
        for frais in frais_annexes:
            montant_paye_depuis_paiements = Decimal('0.00')
            paiements_annexe = list(
                PaiementEleve.objects.filter(
                    frais_annexe=frais,
                    eleve=eleve,
                    annee_scolaire=annee_scolaire_active,
                    type_paiement='frais_annexe',
                ).order_by('-date_paiement')
            )
            for paiement in paiements_annexe:
                montant_paye_depuis_paiements += Decimal(str(paiement.montant))
            reste_a_payer_annexe = Decimal(str(frais.montant)) - montant_paye_depuis_paiements
            frais_annexes_avec_paiements.append({
                'frais': frais,
                'montant_total': frais.montant,
                'montant_paye': montant_paye_depuis_paiements,
                'reste_a_payer': reste_a_payer_annexe if reste_a_payer_annexe > Decimal('0.00') else Decimal('0.00'),
                'paiements': paiements_annexe,
            })

        from school_admin.model.comptabilite_eleve_model import ChoixFraisAnnexeEleve
        from school_admin.utils.frais_annexes import (
            CHOIX_INSCRIT,
            MODE_AU_CHOIX,
            frais_annexes_actifs,
            periodicite_label,
        )

        charges_par_code = {
            row['frais'].code: row for row in frais_annexes_avec_paiements
        }
        params_actifs = frais_annexes_actifs(
            getattr(parametres, 'frais_annexes', None) if parametres else None
        )
        choix_existants = {
            c.code: c.statut
            for c in ChoixFraisAnnexeEleve.objects.filter(
                eleve=eleve,
                annee_scolaire=annee_scolaire_active,
            )
        }
        frais_annexes_lignes = []
        codes_vus = set()
        for item in params_actifs:
            code = item['code']
            codes_vus.add(code)
            charge_row = charges_par_code.get(code)
            frais_obj = charge_row['frais'] if charge_row else None
            au_choix = item.get('mode_application') == MODE_AU_CHOIX
            if au_choix:
                actif = choix_existants.get(code) == CHOIX_INSCRIT
            else:
                actif = True
            if charge_row and frais_obj and frais_obj.statut != 'clos':
                montant_total = charge_row['montant_total']
                montant_paye = charge_row['montant_paye']
                reste = charge_row['reste_a_payer']
                paiements_ligne = charge_row['paiements']
                date_echeance = frais_obj.date_echeance
                periodicite_display = frais_obj.get_periodicite_display()
            elif charge_row and frais_obj and frais_obj.statut == 'clos':
                # Clos = inactif (historique), montants affichés depuis la charge close
                actif = False
                montant_total = charge_row['montant_total']
                montant_paye = charge_row['montant_paye']
                reste = Decimal('0.00')
                paiements_ligne = charge_row['paiements']
                date_echeance = frais_obj.date_echeance
                periodicite_display = frais_obj.get_periodicite_display()
            else:
                montant_total = item['montant_decimal']
                montant_paye = Decimal('0.00')
                reste = montant_total if actif else Decimal('0.00')
                paiements_ligne = []
                date_echeance = None
                periodicite_display = item.get('periodicite_display') or periodicite_label(
                    item.get('periodicite')
                )
            frais_annexes_lignes.append({
                'code': code,
                'libelle': item['libelle'],
                'au_choix': au_choix,
                'actif': actif,
                'frais': frais_obj,
                'montant_total': montant_total,
                'montant_paye': montant_paye,
                'reste_a_payer': reste,
                'paiements': paiements_ligne,
                'date_echeance': date_echeance,
                'periodicite_display': periodicite_display,
            })
        for code, charge_row in charges_par_code.items():
            if code in codes_vus:
                continue
            frais_obj = charge_row['frais']
            actif = frais_obj.statut != 'clos'
            frais_annexes_lignes.append({
                'code': code,
                'libelle': frais_obj.libelle,
                'au_choix': True,
                'actif': actif,
                'frais': frais_obj,
                'montant_total': charge_row['montant_total'],
                'montant_paye': charge_row['montant_paye'],
                'reste_a_payer': charge_row['reste_a_payer'] if actif else Decimal('0.00'),
                'paiements': charge_row['paiements'],
                'date_echeance': frais_obj.date_echeance,
                'periodicite_display': frais_obj.get_periodicite_display(),
            })
        frais_annexes_lignes.sort(key=lambda row: (not row['actif'], row['libelle'].lower()))

        # Calculer les totaux
        total_du = comptabilite.calculer_total_du()
        total_paye = comptabilite.calculer_total_paye()
        reste_a_payer = total_du - total_paye
        
        # Récupérer la devise monétaire
        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)
        
        pct_paye = 0
        if total_du and total_du > 0:
            pct_paye = int((total_paye / total_du) * 100)

        from school_admin.services.recouvrement import (
            compter_enfants_famille,
            moratoire_actif,
            verifier_rupture_moratoire,
        )

        moratoire = moratoire_actif(eleve, etablissement, annee_scolaire_active)
        if moratoire:
            verifier_rupture_moratoire(moratoire)
            moratoire.refresh_from_db()
            moratoire_echeances = list(moratoire.echeances.all())
        else:
            moratoire_echeances = []

        nombre_fratrie = compter_enfants_famille(eleve, etablissement)
        remise_active = bool(
            parametres and getattr(parametres, 'appliquer_remise_famille_nombreuse', False)
        )
        remise_pct = (
            getattr(parametres, 'pourcentage_remise_famille_nombreuse', 0) if parametres else 0
        )

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
            'frais_annexes_lignes': frais_annexes_lignes,
            'paiements': paiements,
            'total_du': total_du,
            'total_paye': total_paye,
            'reste_a_payer': reste_a_payer,
            'is_directeur': is_directeur,
            'personnel': personnel,
            'parametres': parametres,
            'paliers_mensualite': getattr(parametres, 'paliers_mensualite', []) if parametres else [],
            'phrase_paliers': phrase_paliers(parametres, devise_monnaie) if parametres and hasattr(parametres, 'montant_pour_mois') else '',
            'devise_monnaie': devise_monnaie,  # Ajouter la devise au contexte
            'moratoire': moratoire,
            'moratoire_echeances': moratoire_echeances,
            'nombre_fratrie': nombre_fratrie,
            'remise_fratrie_active': remise_active,
            'remise_fratrie_pct': remise_pct,
        }

        from ..utils.directeur_ui_tabs import attach_details_compta_tab_context

        attach_details_compta_tab_context(request, context)
        
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
            ).exclude(statut='clos').order_by('date_echeance')
        
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
                        frais_annexe_obj = FraisAnnexe.objects.select_for_update().get(pk=frais_annexe_obj.pk)
                        if frais_annexe_obj.statut == 'clos':
                            raise ValueError("Ce frais est clôturé et ne peut plus recevoir de paiement.")
                        reste_a_payer = frais_annexe_obj.get_reste_a_payer()
                        if montant_decimal > reste_a_payer:
                            messages.error(request, f"Le montant ({montant_decimal}) dépasse le reste à payer ({reste_a_payer}).")
                            return redirect('directeur:enregistrer_paiement_directeur', eleve_id=eleve_id)
                        frais_annexe_obj.ajouter_paiement(montant_decimal)
                    
                    # Créer le paiement
                    enregistre_par_user = None
                    if isinstance(request.user, CompteUser):
                        enregistre_par_user = request.user
                    
                    paiement = PaiementEleve.objects.create(
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
                    pont_paiement_eleve(paiement, annee_scolaire=annee_scolaire_active, user=enregistre_par_user)
                    
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

                    mode_paiement = (request.POST.get('mode_paiement') or 'especes').strip()
                    if mode_paiement not in {
                        'especes', 'mobile_money', 'virement', 'cheque', 'carte', 'autre'
                    }:
                        mode_paiement = 'especes'
                    reference_paiement = (request.POST.get('reference_paiement') or '').strip()[:100]
                    
                    paiement = PaiementEleve.objects.create(
                        eleve=eleve,
                        etablissement=etablissement,
                        annee_scolaire=annee_scolaire_active,
                        type_paiement='frais_inscription',
                        frais_inscription=frais_inscription,
                        montant=montant_decimal,
                        mode_paiement=mode_paiement,
                        reference_paiement=reference_paiement,
                        notes='',
                        enregistre_par=enregistre_par_user
                    )
                    pont_paiement_eleve(paiement, annee_scolaire=annee_scolaire_active, user=enregistre_par_user)
                    
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

                    return ComptabiliteController._compta_redirect_apres_paiement(
                        request,
                        paiement,
                        eleve_id_int,
                        success_msg,
                        etablissement,
                        annee_scolaire_active,
                        devise_monnaie,
                    )
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

                    mode_paiement = (request.POST.get('mode_paiement') or 'especes').strip()
                    if mode_paiement not in {
                        'especes', 'mobile_money', 'virement', 'cheque', 'carte', 'autre'
                    }:
                        mode_paiement = 'especes'
                    reference_paiement = (request.POST.get('reference_paiement') or '').strip()[:100]
                    
                    paiement = PaiementEleve.objects.create(
                        eleve=eleve,
                        etablissement=etablissement,
                        annee_scolaire=annee_scolaire_active,
                        type_paiement='mensualite',
                        mensualite=mensualite,
                        montant=montant_decimal,
                        mode_paiement=mode_paiement,
                        reference_paiement=reference_paiement,
                        notes='',
                        enregistre_par=enregistre_par_user
                    )
                    pont_paiement_eleve(paiement, annee_scolaire=annee_scolaire_active, user=enregistre_par_user)
                    
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

                    return ComptabiliteController._compta_redirect_apres_paiement(
                        request,
                        paiement,
                        eleve_id_int,
                        success_msg,
                        etablissement,
                        annee_scolaire_active,
                        devise_monnaie,
                    )
            except Exception as e:
                messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
                return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)
        
        return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id_int)

    @staticmethod
    @login_required
    def gerer_choix_frais_annexes_directeur(request, eleve_id):
        """Enregistre les frais annexes « au choix » pour un élève (POST Django)."""
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
        redirect_details = redirect(
            'directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id
        )
        if not annee_scolaire_active:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect_details

        if request.method != 'POST':
            return redirect_details

        from ..model.inscription_eleve_model import InscriptionEleve
        from school_admin.utils.frais_annexes import appliquer_choix_frais_au_choix

        try:
            inscription = InscriptionEleve.objects.select_related('eleve', 'classe').get(
                eleve_id=int(eleve_id),
                etablissement=etablissement,
                annee_scolaire=annee_scolaire_active,
                eleve__isnull=False,
            )
        except (InscriptionEleve.DoesNotExist, ValueError, TypeError):
            messages.error(request, "Élève introuvable pour cette année scolaire.")
            return redirect_details

        eleve = inscription.eleve
        parametres = ComptabiliteController._get_parametres_for_classe(
            etablissement, inscription.classe
        )
        if parametres is None:
            messages.error(request, "Aucun paramètre de scolarité pour la classe de cet élève.")
            return redirect_details

        comptabilite, _ = ComptabiliteEleve.objects.get_or_create(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire_active,
            defaults={'statut_paiement': 'a_jour'},
        )

        from school_admin.model.comptabilite_eleve_model import ChoixFraisAnnexeEleve
        from school_admin.utils.frais_annexes import CHOIX_INSCRIT, frais_au_choix_pour_parametres

        action = (request.POST.get('action') or '').strip()
        code = (request.POST.get('code') or '').strip()
        au_choix_codes = {item['code'] for item in frais_au_choix_pour_parametres(parametres)}

        if action in ('activer', 'desactiver') and code:
            if code not in au_choix_codes:
                messages.error(request, "Ce frais n'est pas configurable au choix pour cet élève.")
                return redirect_details
            from school_admin.utils.frais_annexes import enregistrer_choix_frais_annexe, synchroniser_frais_annexes_eleve
            with transaction.atomic():
                enregistrer_choix_frais_annexe(
                    eleve, etablissement, annee_scolaire_active, code,
                    CHOIX_INSCRIT if action == 'activer' else 'refuse',
                )
                synchroniser_frais_annexes_eleve(
                    eleve, etablissement, annee_scolaire_active,
                    comptabilite, parametres, inscription=inscription,
                )
            message_ok = "Le choix de ce frais annexe a été mis à jour pour cet élève."
            messages.success(request, message_ok)
        else:
            codes = request.POST.getlist('frais_annexe_choix')
            appliquer_choix_frais_au_choix(
                eleve,
                etablissement,
                annee_scolaire_active,
                comptabilite,
                parametres,
                codes,
                inscription=inscription,
            )
            messages.success(request, "Les frais annexes au choix ont été mis à jour pour cet élève.")

        comptabilite.verifier_statut_paiement()
        from django.urls import reverse
        return redirect(
            reverse('directeur:details_comptabilite_eleve_directeur', kwargs={'eleve_id': eleve.id})
            + '?section=annexes'
        )

    @staticmethod
    @login_required
    def frais_au_choix_pour_classe_directeur(request, classe_id):
        """JSON : frais annexes « au choix » liés aux paramètres de la classe."""
        from django.http import JsonResponse
        from school_admin.utils.frais_annexes import frais_au_choix_pour_parametres

        result = ComptabiliteController._get_user_etablissement(request)
        if result[0] is None:
            return JsonResponse({'ok': False, 'message': 'Accès non autorisé.'}, status=403)

        etablissement = result[0]
        try:
            classe = Classe.objects.get(
                id=int(classe_id),
                etablissement=etablissement,
                actif=True,
            )
        except (Classe.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'ok': False, 'message': 'Classe introuvable.'}, status=404)

        parametres = ComptabiliteController._get_parametres_for_classe(etablissement, classe)
        devise = ComptabiliteController._get_devise_monnaie(etablissement)
        frais = []
        for item in frais_au_choix_pour_parametres(parametres):
            montant = item.get('montant_decimal') or Decimal('0.00')
            frais.append({
                'code': item['code'],
                'libelle': item['libelle'],
                'icon': item.get('icon') or 'fa-tag',
                'montant': float(montant),
                'montant_display': f'{int(montant)}',
            })
        return JsonResponse({'ok': True, 'frais': frais, 'devise': devise or 'FCFA'})

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
                frais_annexe = FraisAnnexe.objects.select_for_update().get(pk=frais_annexe.pk)
                if frais_annexe.statut == 'clos' or montant_decimal > frais_annexe.get_reste_a_payer():
                    raise ValueError("Le reste à payer a changé. Actualisez la fiche avant de recommencer.")
                frais_annexe.ajouter_paiement(montant_decimal)
                frais_annexe.refresh_from_db()

                enregistre_par_user = request.user if isinstance(request.user, CompteUser) else None
                mode_paiement = (request.POST.get('mode_paiement') or 'especes').strip()
                if mode_paiement not in {
                    'especes', 'mobile_money', 'virement', 'cheque', 'carte', 'autre'
                }:
                    mode_paiement = 'especes'
                reference_paiement = (request.POST.get('reference_paiement') or '').strip()[:100]
                paiement = PaiementEleve.objects.create(
                    eleve=eleve,
                    etablissement=etablissement,
                    annee_scolaire=annee_scolaire_active,
                    type_paiement='frais_annexe',
                    frais_annexe=frais_annexe,
                    montant=montant_decimal,
                    mode_paiement=mode_paiement,
                    reference_paiement=reference_paiement,
                    notes='',
                    enregistre_par=enregistre_par_user,
                )
                pont_paiement_eleve(paiement, annee_scolaire=annee_scolaire_active, user=enregistre_par_user)

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

                return ComptabiliteController._compta_redirect_apres_paiement(
                    request,
                    paiement,
                    eleve_id_int,
                    success_msg,
                    etablissement,
                    annee_scolaire_active,
                    devise_monnaie,
                )
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

        if request.method == 'POST' and request.POST.get('action') == 'transition_frais_annexe':
            from ..utils.frais_annexes import (
                frais_au_choix_pour_parametres,
                enregistrer_choix_frais_annexe,
                synchroniser_frais_annexes_eleve,
                CHOIX_INSCRIT,
                CHOIX_REFUSE,
            )

            annee = ComptabiliteController._get_session_directeur(request, etablissement)
            parametre = ParametresComptabiliteGroupeClasse.objects.filter(
                pk=request.POST.get('parametre_id'), etablissement=etablissement
            ).first()
            code = request.POST.get('code', '').strip()
            decision = request.POST.get('decision', '').strip()
            if not annee or not parametre or decision not in (CHOIX_INSCRIT, CHOIX_REFUSE):
                messages.error(request, "Décision de transition invalide.")
                return redirect('directeur:parametres_comptabilite_directeur')
            if code not in {item['code'] for item in frais_au_choix_pour_parametres(parametre)}:
                messages.error(request, "Ce frais n'est pas proposé au choix dans ce jeu.")
                return redirect('directeur:parametres_comptabilite_directeur')
            lignes = frais_annexes_en_transition(parametre, annee).get(code, [])
            with transaction.atomic():
                for charge, inscription in lignes:
                    enregistrer_choix_frais_annexe(
                        inscription.eleve, etablissement, annee, code, decision
                    )
                    synchroniser_frais_annexes_eleve(
                        inscription.eleve, etablissement, annee,
                        charge.comptabilite_eleve, parametre, inscription
                    )
                    charge.comptabilite_eleve.verifier_statut_paiement()
            messages.success(request, f"{len(lignes)} élève(s) classé(s) « {decision} » pour ce frais.")
            return redirect('directeur:parametres_comptabilite_directeur')

        if request.method == 'POST' and request.POST.get('action') == 'enregistrer_regime':
            from school_admin.services.comptabilite_generale import enregistrer_regime_comptable

            annee = ComptabiliteController._get_session_directeur(request, etablissement)
            try:
                _, changed = enregistrer_regime_comptable(
                    etablissement,
                    (request.POST.get('regime_comptable') or '').strip(),
                    annee_scolaire=annee,
                )
                if changed:
                    messages.success(request, "Régime comptable enregistré.")
                else:
                    messages.info(request, "Le régime comptable est déjà à jour.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect('directeur:parametres_comptabilite_directeur')

        parametres_groupes = list(ParametresComptabiliteGroupeClasse.objects.filter(
            etablissement=etablissement
        ).order_by('-date_modification'))

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        from ..utils.frais_annexes import frais_au_choix_pour_parametres
        for parametre in parametres_groupes:
            transitions = frais_annexes_en_transition(parametre, annee)
            parametre.transitions_frais = [
                {'code': item['code'], 'libelle': item['libelle'], 'nombre': len(transitions[item['code']])}
                for item in frais_au_choix_pour_parametres(parametre)
                if transitions.get(item['code'])
            ]

        groupes_disponibles = ParametresComptabiliteGroupeClasse.get_groupes_disponibles(etablissement)
        groupes_deja_assignes = ParametresComptabiliteGroupeClasse.get_groupes_deja_assignes(etablissement)

        devise_monnaie = ComptabiliteController._get_devise_monnaie(etablissement)

        stats_generales = {
            'total_parametres': len(parametres_groupes),
            'groupes_assignes': len(groupes_deja_assignes),
            'groupes_disponibles': len(groupes_disponibles),
        }

        from school_admin.services.comptabilite_generale import regime_est_verrouille

        params_generaux = ParametresComptabilite.objects.filter(etablissement=etablissement).first()
        context = {
            'etablissement': etablissement,
            'parametres_groupes': parametres_groupes,
            'groupes_disponibles': groupes_disponibles,
            'groupes_deja_assignes': groupes_deja_assignes,
            'frais_annexes_form': get_frais_annexes_from_parametres(None),
            'tranches_form': tranches_form(),
            'mois_ordre': mois_ordre_form(),
            'stats_generales': stats_generales,
            'open_ajouter_modal': request.GET.get('modal') == 'ajouter',
            'is_directeur': is_directeur,
            'personnel': personnel,
            'devise_monnaie': devise_monnaie,
            'parametres_comptabilite': params_generaux,
            'regime_comptable': params_generaux.regime_comptable if params_generaux else 'engagement',
            'regime_verrouille': regime_est_verrouille(etablissement),
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
            'frais_annexes_par_type': ComptabiliteController._aggreger_frais_annexes(frais_annexes_qs),
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

        from ..utils.directeur_ui_tabs import attach_bilan_tab_context

        attach_bilan_tab_context(request, context)
        
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
        ).select_related('eleve').prefetch_related('frais_annexes')
        
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
        compta_par_eleve = {comptabilite.eleve_id: comptabilite for comptabilite in comptabilites}
        for eleve in eleves_classe:
            comptabilite = compta_par_eleve.get(eleve.id)
            if comptabilite:
                montant_du_eleve = comptabilite.calculer_total_du()
                montant_paye_eleve = comptabilite.calculer_total_paye()
                reste_a_payer_eleve = montant_du_eleve - montant_paye_eleve
                annexes_du = Decimal('0.00')
                annexes_paye = Decimal('0.00')
                for frais in comptabilite.frais_annexes.all():
                    annexes_du += frais.montant
                    annexes_paye += frais.montant_paye

                eleves_stats.append({
                    'eleve': eleve,
                    'comptabilite': comptabilite,
                    'montant_du': montant_du_eleve,
                    'montant_paye': montant_paye_eleve,
                    'reste_a_payer': reste_a_payer_eleve,
                    'frais_annexes_du': annexes_du,
                    'frais_annexes_paye': annexes_paye,
                    'frais_annexes_reste': annexes_du - annexes_paye,
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
            'frais_annexes_par_type': ComptabiliteController._aggreger_frais_annexes(frais_annexes_classe),
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

        from ..utils.directeur_ui_tabs import attach_bilan_classe_tab_context

        attach_bilan_classe_tab_context(request, context)

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
                montants_mensualite_par_mois = extraire_tarifs_par_mois(
                    request.POST,
                    debut=mois_debut_facturation,
                    fin=mois_fin_facturation,
                )
                # Plus de montant « mois non cochés » : seuls les tarifs cochés comptent.
                montant_mensualite = '0'

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
                        'montants_mensualite_par_mois': montants_mensualite_par_mois,
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
                        if not parametre.mettre_a_jour_systeme_comptabilite():
                            raise ValueError("La mise à jour des mensualités a échoué.")
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
                    parametre.montants_mensualite_par_mois = montants_mensualite_par_mois
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
                        if not parametre.mettre_a_jour_systeme_comptabilite():
                            raise ValueError("La mise à jour des mensualités a échoué.")
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
            'tranches_form': tranches_form(parametre),
            'mois_ordre': mois_ordre_form(
                getattr(parametre, 'mois_debut_facturation', 9) if parametre else 9,
                getattr(parametre, 'mois_fin_facturation', 6) if parametre else 6,
            ),
            'is_directeur': is_directeur,
            'personnel': personnel,
            'devise_monnaie': devise_monnaie,
        }
        
        return render(request, 'school_admin/directeur/comptabilite/ajouter_modifier_parametres_groupe.html', context)

    @staticmethod
    def _aggreger_frais_annexes(frais_annexes_qs):
        """Regroupe les échéances annexes par code (dû, payé, reste)."""
        par_code = {}
        for frais in frais_annexes_qs:
            row = par_code.get(frais.code)
            if row is None:
                row = {
                    'code': frais.code,
                    'libelle': frais.libelle,
                    'montant_du': Decimal('0.00'),
                    'montant_paye': Decimal('0.00'),
                }
                par_code[frais.code] = row
            row['montant_du'] += frais.montant or Decimal('0.00')
            row['montant_paye'] += frais.montant_paye or Decimal('0.00')
            row['libelle'] = frais.libelle
        result = []
        for row in par_code.values():
            row['reste'] = row['montant_du'] - row['montant_paye']
            result.append(row)
        result.sort(key=lambda item: item['libelle'])
        return result

    @staticmethod
    def _nom_groupe_classe(classe):
        nom = classe.nom
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        if match:
            return match.group(1).strip()
        return nom.strip()

    @staticmethod
    def _parametres_groupe_for_classe(etablissement, classe):
        """Paramètres de scolarité du jeu de groupe (1ère, 2nde…), sans repli général."""
        nom_groupe = ComptabiliteController._nom_groupe_classe(classe)
        return ParametresComptabiliteGroupeClasse.get_parametres_for_classe(
            etablissement,
            nom_groupe,
        )

    @staticmethod
    def _get_parametres_for_classe(etablissement, classe):
        """
        Retourne les paramètres de comptabilité appropriés pour une classe donnée.
        Retourne les paramètres spécifiques si disponibles, sinon les paramètres généraux.
        Retourne None si aucun paramètre n'est configuré.
        """
        parametres_specifiques = ComptabiliteController._parametres_groupe_for_classe(
            etablissement, classe
        )
        if parametres_specifiques:
            return parametres_specifiques
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

