from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.db.models import Sum, Count
from ..model.etablissement_model import Etablissement
from ..model.eleve_model import Eleve
from ..model.facturation_model import Facturation
from ..model.depense_model import Depense
from ..model.budget_model import Budget
from django.contrib import messages
from django.db import transaction





def dashboard_comptable(request):
    """
    Dashboard comptable avec données dynamiques
    """
    
    # Statistiques générales
    total_etablissements = Etablissement.objects.filter(actif=True).count()
    total_eleves = Eleve.objects.filter(actif=True).count()
    
    # Revenus totaux collectés (factures payées)
    revenus_collectes = Facturation.objects.filter(statut='paye').aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montants en attente (factures en attente)
    montants_en_attente = Facturation.objects.filter(statut='en_attente').aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montants en retard
    montants_en_retard = Facturation.objects.filter(statut='en_retard').aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montant total attendu (toutes les factures)
    montant_total_attendu = Facturation.objects.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Calcul du taux de collecte
    taux_collecte = 0
    if montant_total_attendu > 0:
        taux_collecte = round((revenus_collectes / montant_total_attendu) * 100, 1)
    
    # Établissements avec leurs statistiques
    etablissements_stats = []
    for etablissement in Etablissement.objects.filter(actif=True):
        nombre_eleves = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
        montant_du = etablissement.montant_total_facturation - (
            Facturation.objects.filter(etablissement=etablissement, statut='paye').aggregate(
                total=Sum('montant_total')
            )['total'] or 0
        )
        
        etablissements_stats.append({
            'etablissement': etablissement,
            'nombre_eleves': nombre_eleves,
            'montant_total': etablissement.montant_total_facturation,
            'montant_du': montant_du,
            'statut_paiement': etablissement.get_statut_paiement_display(),
        })
    
    # Activité récente (dernières factures)
    activites_recentes = Facturation.objects.select_related('etablissement').order_by('-date_creation')[:6]
    
    # Inscriptions en retard (établissements avec factures en retard)
    inscriptions_retard = Etablissement.objects.filter(
        statut_paiement='en_retard'
    ).count()
    
    # Personnel (nombre d'employés actifs - à adapter selon votre modèle)
    # Pour l'instant, on utilise un nombre statique car le modèle personnel n'est pas encore implémenté
    personnel_actif = 6  # À remplacer par Personnel.objects.filter(actif=True).count()
    personnel_total = 6  # À remplacer par Personnel.objects.count()
    
    # Bénéfices (revenus - coûts)
    # Pour l'instant, on calcule une estimation basée sur les revenus
    benefices_estimes = revenus_collectes * 0.2  # Estimation 20% de marge
    
    # Paiements personnel (données statiques pour l'instant)
    paiements_personnel = {
        'montant_total': 2500000,  # 2 500 000 FCFA
        'dernier_paiement': '30 novembre 2023',
        'prochain_paiement': '30 décembre 2023'
    }
    
    context = {
        'total_etablissements': total_etablissements,
        'total_eleves': total_eleves,
        'revenus_collectes': revenus_collectes,
        'montants_en_attente': montants_en_attente,
        'montants_en_retard': montants_en_retard,
        'montant_total_attendu': montant_total_attendu,
        'taux_collecte': taux_collecte,
        'etablissements_stats': etablissements_stats,
        'activites_recentes': activites_recentes,
        'inscriptions_retard': inscriptions_retard,
        'personnel_actif': personnel_actif,
        'personnel_total': personnel_total,
        'benefices_estimes': benefices_estimes,
        'paiements_personnel': paiements_personnel,
    }
    
    return render(request, 'school_admin/gestion_comptable/dashboard_comptable.html', context)


def suivi_revenus(request):
    """
    Vue pour le suivi des revenus avec données dynamiques
    """
    # Statistiques générales
    total_etablissements = Etablissement.objects.filter(actif=True).count()
    total_eleves = Eleve.objects.filter(actif=True).count()
    
    # Revenus attendus (toutes les factures)
    revenus_attendus = Facturation.objects.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montants en attente
    montants_en_attente = Facturation.objects.filter(statut='en_attente').aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Revenus collectés (factures payées)
    revenus_collectes = Facturation.objects.filter(statut='paye').aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montants en retard
    montants_en_retard = Facturation.objects.filter(statut='en_retard').aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Établissements avec leurs statistiques détaillées
    etablissements_detailed = []
    for etablissement in Etablissement.objects.filter(actif=True):
        nombre_eleves = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
        montant_total = etablissement.montant_total_facturation
        
        # Premier versement (première facture payée avec montant versé)
        premier_versement = Facturation.objects.filter(
            etablissement=etablissement, 
            statut='paye'
        ).order_by('date_creation').first()
        
        montant_premier_versement = 0
        date_premier_versement = None
        
        if premier_versement:
            # Utiliser le montant_verse si disponible, sinon le montant_total
            montant_premier_versement = premier_versement.montant_verse if premier_versement.montant_verse > 0 else premier_versement.montant_total
            date_premier_versement = premier_versement.date_paiement or premier_versement.date_creation
        
        # Montant dû (total - montant versé sur toutes les factures)
        montant_verse_total = Facturation.objects.filter(
            etablissement=etablissement, 
            statut='paye'
        ).aggregate(total=Sum('montant_verse'))['total'] or 0
        
        # Si montant_verse_total est 0, utiliser l'ancien calcul
        if montant_verse_total == 0:
            montant_paye = Facturation.objects.filter(
                etablissement=etablissement, 
                statut='paye'
            ).aggregate(total=Sum('montant_total'))['total'] or 0
        else:
            montant_paye = montant_verse_total
        
        montant_du = montant_total - montant_paye
        
        # Statut de l'inscription basé sur la facture si elle existe, sinon "Aucune facture pour le moment"
        derniere_facture = Facturation.objects.filter(
            etablissement=etablissement
        ).order_by('-date_creation').first()
        
        if derniere_facture:
            statut_inscription = derniere_facture.get_statut_display()
            nombre_eleves_factures = derniere_facture.quantite
        else:
            statut_inscription = "Aucune facture pour le moment"
            nombre_eleves_factures = 0
        
        etablissements_detailed.append({
            'etablissement': etablissement,
            'nombre_eleves': nombre_eleves,
            'montant_total': montant_total,
            'montant_premier_versement': montant_premier_versement,
            'date_premier_versement': date_premier_versement,
            'montant_du': montant_du,
            'statut_inscription': statut_inscription,
            'nombre_eleves_factures': nombre_eleves_factures,
        })
    
    # Dépenses (données statiques pour l'instant - à adapter selon votre modèle de dépenses)
    depenses_stats = {
        'personnel': 2500000,  # 2 500 000 FCFA
        'maintenance': 450000,  # 450 000 FCFA
        'loyer': 800000,  # 800 000 FCFA
        'marketing': 300000,  # 300 000 FCFA
        'total': 4050000,  # 4 050 000 FCFA
    }
    
    # Liste des dépenses détaillées
    depenses_detailed = [
        {
            'type': 'Personnel',
            'description': 'Salaires du mois de novembre',
            'details': 'Paiement des 6 employés',
            'montant': 2500000,
            'date': '30 Nov 2023',
            'statut': 'Payé',
            'icon': 'fas fa-users',
            'icon_class': 'personnel'
        },
        {
            'type': 'Maintenance',
            'description': 'Réparation serveurs',
            'details': 'Maintenance système informatique',
            'montant': 450000,
            'date': '28 Nov 2023',
            'statut': 'Payé',
            'icon': 'fas fa-tools',
            'icon_class': 'maintenance'
        },
        {
            'type': 'Loyer',
            'description': 'Loyer bureau principal',
            'details': 'Mois de novembre 2023',
            'montant': 800000,
            'date': '25 Nov 2023',
            'statut': 'Payé',
            'icon': 'fas fa-building',
            'icon_class': 'loyer'
        },
        {
            'type': 'Marketing',
            'description': 'Campagne publicitaire',
            'details': 'Publicité radio et affichage',
            'montant': 300000,
            'date': '20 Nov 2023',
            'statut': 'En attente',
            'icon': 'fas fa-bullhorn',
            'icon_class': 'marketing'
        }
    ]
    
    context = {
        'total_etablissements': total_etablissements,
        'total_eleves': total_eleves,
        'revenus_attendus': revenus_attendus,
        'montants_en_attente': montants_en_attente,
        'revenus_collectes': revenus_collectes,
        'montants_en_retard': montants_en_retard,
        'etablissements_detailed': etablissements_detailed,
        'depenses_stats': depenses_stats,
        'depenses_detailed': depenses_detailed,
    }
    
    return render(request, 'school_admin/gestion_comptable/suivi_revenus.html', context)


def paiements_retard(request):
    """
    Vue pour le suivi des paiements en retard avec données dynamiques basées sur le modèle Facturation
    """
    from datetime import datetime, timedelta
    from django.utils import timezone
    from django.db.models import Sum, Count, Q
    
    # Récupérer les établissements avec des factures en retard
    etablissements_avec_factures_retard = Facturation.objects.filter(
        statut='en_retard'
    ).values_list('etablissement_id', flat=True).distinct()
    
    etablissements_retard = Etablissement.objects.filter(
        id__in=etablissements_avec_factures_retard,
        actif=True
    )
    
    # Récupérer les établissements avec des factures impayées
    etablissements_avec_factures_impayees = Facturation.objects.filter(
        statut='impaye'
    ).values_list('etablissement_id', flat=True).distinct()
    
    etablissements_impayes = Etablissement.objects.filter(
        id__in=etablissements_avec_factures_impayees,
        actif=True
    )
    
    # Récupérer les établissements avec des factures en contentieux
    etablissements_avec_factures_contentieux = Facturation.objects.filter(
        statut='contentieux'
    ).values_list('etablissement_id', flat=True).distinct()
    
    etablissements_contentieux = Etablissement.objects.filter(
        id__in=etablissements_avec_factures_contentieux,
        actif=True
    )
    
    # Statistiques générales
    nombre_etablissements_retard = etablissements_retard.count()
    nombre_etablissements_impayes = etablissements_impayes.count()
    nombre_etablissements_contentieux = etablissements_contentieux.count()
    
    # Calcul du montant total impayé (toutes les factures en retard, impayées et contentieux)
    montant_total_impaye = Facturation.objects.filter(
        statut__in=['en_retard', 'impaye', 'contentieux']
    ).aggregate(total=Sum('montant_total'))['total'] or 0
    
    # Calcul des jours de retard moyen
    factures_en_retard = Facturation.objects.filter(
        statut__in=['en_retard', 'impaye', 'contentieux']
    )
    
    total_jours_retard = 0
    nombre_factures_retard = 0
    
    for facture in factures_en_retard:
        if facture.date_echeance:
            jours_retard = (timezone.now().date() - facture.date_echeance.date()).days
            total_jours_retard += jours_retard
            nombre_factures_retard += 1
    
    jours_retard_moyen = 0
    if nombre_factures_retard > 0:
        jours_retard_moyen = round(total_jours_retard / nombre_factures_retard, 1)
    
    # Calcul du taux d'impayés
    montant_total_attendu = Facturation.objects.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    taux_impayes = 0
    if montant_total_attendu > 0:
        taux_impayes = round((montant_total_impaye / montant_total_attendu) * 100, 1)
    
    # Liste détaillée des établissements en retard
    etablissements_retard_detailed = []
    for etablissement in etablissements_retard:
        # Récupérer les factures en retard de cet établissement
        factures_retard = Facturation.objects.filter(
            etablissement=etablissement,
            statut='en_retard'
        )
        
        # Calculer le montant total des factures en retard
        montant_du = factures_retard.aggregate(total=Sum('montant_total'))['total'] or 0
        
        # Calculer les jours de retard (basé sur la facture la plus ancienne)
        facture_plus_ancienne = factures_retard.order_by('date_echeance').first()
        jours_retard = 0
        date_echeance = None
        
        if facture_plus_ancienne and facture_plus_ancienne.date_echeance:
            jours_retard = (timezone.now().date() - facture_plus_ancienne.date_echeance.date()).days
            date_echeance = facture_plus_ancienne.date_echeance
        
        etablissements_retard_detailed.append({
            'etablissement': etablissement,
            'montant_du': montant_du,
            'jours_retard': jours_retard,
            'statut_relance': 'en_retard',
            'derniere_action': 'Facture en retard',
            'date_echeance': date_echeance,
        })
    
    # Liste détaillée des établissements impayés (pour l'onglet relances)
    relances_envoyees = []
    for etablissement in etablissements_impayes:
        # Récupérer les factures impayées de cet établissement
        factures_impayees = Facturation.objects.filter(
            etablissement=etablissement,
            statut='impaye'
        )
        
        # Calculer le montant total des factures impayées
        montant_du = factures_impayees.aggregate(total=Sum('montant_total'))['total'] or 0
        
        # Calculer les jours de retard
        facture_plus_ancienne = factures_impayees.order_by('date_echeance').first()
        jours_retard = 0
        if facture_plus_ancienne and facture_plus_ancienne.date_echeance:
            jours_retard = (timezone.now().date() - facture_plus_ancienne.date_echeance.date()).days
        
        # Déterminer le type de relance basé sur les jours de retard
        if jours_retard > 30:
            type_relance = 'Mise en demeure'
            statut = 'Envoyée'
            reponse = 'Aucune réponse'
        else:
            type_relance = 'Relance simple'
            statut = 'Envoyée'
            reponse = 'Aucune réponse'
        
        relances_envoyees.append({
            'etablissement': etablissement,
            'type_relance': type_relance,
            'date_envoi': facture_plus_ancienne.date_creation.strftime('%d %b %Y') if facture_plus_ancienne else 'N/A',
            'statut': statut,
            'reponse': reponse,
        })
    
    # Liste détaillée des établissements en contentieux
    contentieux = []
    for etablissement in etablissements_contentieux:
        # Récupérer les factures en contentieux de cet établissement
        factures_contentieux = Facturation.objects.filter(
            etablissement=etablissement,
            statut='contentieux'
        )
        
        # Calculer le montant total des factures en contentieux
        montant_reclame = factures_contentieux.aggregate(total=Sum('montant_total'))['total'] or 0
        
        # Calculer les jours de retard
        facture_plus_ancienne = factures_contentieux.order_by('date_echeance').first()
        jours_retard = 0
        if facture_plus_ancienne and facture_plus_ancienne.date_echeance:
            jours_retard = (timezone.now().date() - facture_plus_ancienne.date_echeance.date()).days
        
        # Simuler des dates d'assignation et d'audience
        date_assignation = (timezone.now() - timedelta(days=jours_retard-60)).strftime('%d %b %Y')
        prochaine_audience = (timezone.now() + timedelta(days=30)).strftime('%d %b %Y')
        
        contentieux.append({
            'etablissement': etablissement,
            'montant_reclame': montant_reclame,
            'date_assignation': date_assignation,
            'statut_dossier': 'En cours',
            'prochaine_audience': prochaine_audience,
        })
    
    context = {
        'nombre_etablissements_retard': nombre_etablissements_retard,
        'jours_retard_moyen': jours_retard_moyen,
        'montant_total_impaye': montant_total_impaye,
        'taux_impayes': taux_impayes,
        'etablissements_retard_detailed': etablissements_retard_detailed,
        'relances_envoyees': relances_envoyees,
        'contentieux': contentieux,
    }
    
    return render(request, 'school_admin/gestion_comptable/paiements_retard.html', context)


def calculs_automatiques(request):
    # Vue pour les calculs automatiques
    return render(request, 'school_admin/gestion_comptable/calculs_automatiques.html')


def rapports_mensuels(request):
    # Vue pour les rapports mensuels (bilan mensuel)
    return render(request, 'school_admin/gestion_comptable/rapports_mensuels.html')


def rapports_annuels(request):
    # Vue pour les rapports annuels (bilan annuel)
    return render(request, 'school_admin/gestion_comptable/rapports_annuels.html')


def gestion_etablissements(request):
    """
    Vue pour la gestion des établissements avec données dynamiques
    """
    from django.db.models import Sum, Count, Q
    from datetime import datetime, timedelta
    from django.utils import timezone
    
    # Statistiques générales
    total_etablissements = Etablissement.objects.filter(actif=True).count()
    
    # Établissements en règle (pas de factures impayées ou en retard)
    # Un établissement est en règle s'il n'a pas de factures avec statut 'en_retard', 'impaye', 'contentieux'
    etablissements_avec_factures_problematiques = Facturation.objects.filter(
        statut__in=['en_retard', 'impaye', 'contentieux']
    ).values_list('etablissement_id', flat=True)
    
    etablissements_en_regle = Etablissement.objects.filter(
        actif=True
    ).exclude(id__in=etablissements_avec_factures_problematiques)
    nombre_en_regle = etablissements_en_regle.count()
    
    # Établissements non en règle (avec factures en retard, impayées ou contentieux)
    etablissements_non_en_regle = Etablissement.objects.filter(
        actif=True,
        id__in=etablissements_avec_factures_problematiques
    )
    nombre_non_en_regle = etablissements_non_en_regle.count()
    
    # Calcul du pourcentage en règle
    pourcentage_en_regle = 0
    if total_etablissements > 0:
        pourcentage_en_regle = round((nombre_en_regle / total_etablissements) * 100, 1)
    
    # Calcul du pourcentage non en règle
    pourcentage_non_en_regle = 0
    if total_etablissements > 0:
        pourcentage_non_en_regle = round((nombre_non_en_regle / total_etablissements) * 100, 1)
    
    # Factures générées (toutes les factures)
    factures_generees = Facturation.objects.count()
    pourcentage_factures = 0
    if total_etablissements > 0:
        pourcentage_factures = round((factures_generees / total_etablissements) * 100, 1)
    
    # Établissements en règle avec détails
    etablissements_en_regle_detailed = []
    for etablissement in etablissements_en_regle:
        nombre_eleves = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
        montant_total = etablissement.montant_total_facturation
        
        # Récupérer la dernière facture de l'établissement
        derniere_facture = Facturation.objects.filter(
            etablissement=etablissement
        ).order_by('-date_creation').first()
        
        # Déterminer le statut basé sur la facture
        if derniere_facture:
            if derniere_facture.statut == 'paye':
                statut_display = "En règle"
            elif derniere_facture.statut == 'en_attente':
                statut_display = "Paiement en attente"
            elif derniere_facture.statut == 'en_retard':
                statut_display = "Paiement en retard"
            elif derniere_facture.statut in ['impaye', 'contentieux']:
                # Vérifier si la date d'échéance a dépassé 1 mois
                from django.utils import timezone
                from datetime import timedelta
                
                if derniere_facture.date_echeance:
                    jours_retard = (timezone.now().date() - derniere_facture.date_echeance.date()).days
                    if jours_retard >= 30:  # 1 mois
                        statut_display = "Non en règle"
                    else:
                        statut_display = "Paiement en retard"
                else:
                    statut_display = "Non en règle"
            else:
                statut_display = "Non en règle"
        else:
            # Pas de facture = en règle
            statut_display = "En règle"
        
        # Dernier paiement (dernière facture payée)
        dernier_paiement = Facturation.objects.filter(
            etablissement=etablissement, 
            statut='paye'
        ).order_by('-date_creation').first()
        
        date_dernier_paiement = dernier_paiement.date_creation if dernier_paiement else None
        
        etablissements_en_regle_detailed.append({
            'etablissement': etablissement,
            'nombre_eleves': nombre_eleves,
            'montant_total': montant_total,
            'date_dernier_paiement': date_dernier_paiement,
            'statut_display': statut_display,
        })
    
    # Établissements non en règle avec détails
    etablissements_non_en_regle_detailed = []
    for etablissement in etablissements_non_en_regle:
        nombre_eleves = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
        
        # Calculer le montant dû (somme des factures en retard, impayées ou contentieux)
        montant_du = Facturation.objects.filter(
            etablissement=etablissement,
            statut__in=['en_retard', 'impaye', 'contentieux']
        ).aggregate(total=Sum('montant_total'))['total'] or 0
        
        # Calculer les jours de retard (basé sur la facture la plus ancienne en retard)
        facture_plus_ancienne = Facturation.objects.filter(
            etablissement=etablissement,
            statut__in=['en_retard', 'impaye', 'contentieux']
        ).order_by('date_echeance').first()
        
        jours_retard = 0
        if facture_plus_ancienne:
            jours_retard = (timezone.now().date() - facture_plus_ancienne.date_echeance.date()).days
        
        etablissements_non_en_regle_detailed.append({
            'etablissement': etablissement,
            'nombre_eleves': nombre_eleves,
            'montant_du': montant_du,
            'jours_retard': jours_retard,
        })
    
    # Factures avec détails basées sur le modèle Facturation
    factures_detailed = []
    for facture in Facturation.objects.select_related('etablissement').order_by('-date_creation'):
        # Calculer le montant payé selon le statut
        montant_paye = 0
        if facture.statut == 'paye':
            if facture.paiement_partiel:
                # Paiement partiel : montant total - reste à payer
                montant_paye = facture.montant_total - facture.reste_a_payer
            else:
                # Paiement complet
                montant_paye = facture.montant_total
        elif facture.statut == 'en_attente':
            montant_paye = 0
        elif facture.statut in ['en_retard', 'impaye', 'contentieux']:
            montant_paye = 0
        
        # Le montant restant est le reste à payer ou le montant total si non payé
        if facture.statut == 'paye' and facture.paiement_partiel:
            montant_restant = facture.reste_a_payer
        elif facture.statut == 'paye' and not facture.paiement_partiel:
            montant_restant = 0
        else:
            montant_restant = facture.montant_total
        
        factures_detailed.append({
            'facture': facture,
            'montant_total': facture.montant_total,
            'montant_paye': montant_paye,
            'montant_restant': montant_restant,
            'statut_display': facture.get_statut_display(),
            'statut_color': facture.get_statut_display_color(),
            'type_facture_display': facture.get_type_facture_display_detailed(),
            'date_creation': facture.date_creation,
            'date_echeance': facture.date_echeance,
            'date_paiement': facture.date_paiement,
            'paiement_partiel': facture.paiement_partiel,
            'reste_a_payer': facture.reste_a_payer,
            'date_echeance_reste': facture.date_echeance_reste,
            'statut_envoi': facture.statut_envoi,
        })
    
    context = {
        'total_etablissements': total_etablissements,
        'nombre_en_regle': nombre_en_regle,
        'nombre_non_en_regle': nombre_non_en_regle,
        'pourcentage_en_regle': pourcentage_en_regle,
        'pourcentage_non_en_regle': pourcentage_non_en_regle,
        'factures_generees': factures_generees,
        'pourcentage_factures': pourcentage_factures,
        'etablissements_en_regle_detailed': etablissements_en_regle_detailed,
        'etablissements_non_en_regle_detailed': etablissements_non_en_regle_detailed,
        'factures_detailed': factures_detailed,
    }
    
    return render(request, 'school_admin/gestion_comptable/gestion_etablissements.html', context)


def details_financiers_etablissement(request, etablissement_id):
    """
    Vue pour les détails financiers d'un établissement avec données dynamiques
    """
    from django.db.models import Sum, Count, Q
    from datetime import datetime, timedelta
    from django.utils import timezone
    from django.shortcuts import redirect
    from django.contrib import messages
    from ..model.facturation_model import Facturation
    
    # Récupérer l'établissement par son ID
    try:
        etablissement = Etablissement.objects.get(id=etablissement_id, actif=True)
    except Etablissement.DoesNotExist:
        # Rediriger vers la liste des établissements si aucun trouvé
        return redirect('school_admin:gestion_etablissements')
    
    # Traitement du formulaire de facturation
    if request.method == 'POST' and 'create_invoice' in request.POST:
        try:
            # Récupérer les données du formulaire
            type_facture = request.POST.get('type_facture')
            description = request.POST.get('description', '')
            date_echeance_str = request.POST.get('date_echeance')
            montant_module_supplementaire = request.POST.get('montant_module_supplementaire', '')
            modules_selectionnes = request.POST.getlist('modules_selectionnes')
            
            # Convertir la date d'échéance
            date_echeance = datetime.strptime(date_echeance_str, '%Y-%m-%d')
            date_echeance = timezone.make_aware(date_echeance)
            
            # Utiliser le nombre d'élèves de l'établissement comme quantité
            quantite = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
            
            # Déterminer le montant unitaire selon le type de facture
            if type_facture == 'frais_service_mensuel':
                montant_unitaire = etablissement.montant_par_eleve
            elif type_facture == 'frais_service_annuel':
                montant_unitaire = etablissement.montant_par_eleve * 12  # Facturation annuelle
            elif type_facture == 'module_supplementaire':
                # Pour les modules supplémentaires, utiliser le montant saisi
                if not montant_module_supplementaire or float(montant_module_supplementaire) <= 0:
                    messages.error(request, "Le montant des modules supplémentaires doit être supérieur à 0")
                    return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
                
                montant_unitaire = float(montant_module_supplementaire)
                quantite = 1  # Pour les modules supplémentaires, quantité = 1
                
                # Vérifier qu'au moins un module est sélectionné
                if not modules_selectionnes:
                    messages.error(request, "Veuillez sélectionner au moins un module supplémentaire")
                    return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
                
                # Ajouter les modules sélectionnés à la description
                modules_mapping = {
                    'module_surveillance': 'Surveillance et sécurité',
                    'module_communication': 'Communication parents',
                    'module_orientation': 'Orientation scolaire',
                    'module_formation': 'Formation continue',
                    'module_transport_scolaire': 'Transport scolaire',
                    'module_cantine': 'Gestion de la cantine',
                    'module_bibliotheque': 'Gestion de la bibliothèque',
                    'module_sante': 'Suivi médical',
                    'module_activites': 'Activités extra-scolaires',
                    'module_comptabilite': 'Comptabilité',
                    'module_censeurs': 'Censeurs',
                }
                
                modules_titres = [modules_mapping.get(module_nom, module_nom) for module_nom in modules_selectionnes]
                if modules_titres:
                    description = f"Modules supplémentaires: {', '.join(modules_titres)}. {description}"
            
            # Créer la facture
            facture = Facturation(
                etablissement=etablissement,
                type_facture=type_facture,
                montant_unitaire=montant_unitaire,
                quantite=quantite,
                date_echeance=date_echeance,
                description=description
            )
            facture.save()
            
            # Traiter les modules supplémentaires si c'est une facture de module
            if type_facture == 'module_supplementaire' and modules_selectionnes:
                # Activer les modules sélectionnés
                for module_nom in modules_selectionnes:
                    if hasattr(facture, module_nom):
                        setattr(facture, module_nom, True)
                facture.save()
            
            # Message de succès avec détails
            if type_facture == 'module_supplementaire' and modules_selectionnes:
                modules_display = facture.get_modules_supplementaires_display()
                messages.success(request, f"Facture {facture.numero_facture} créée avec succès pour {etablissement.nom} ! Montant: {facture.montant_total} FCFA - Modules: {modules_display}")
            else:
                messages.success(request, f"Facture {facture.numero_facture} créée avec succès pour {etablissement.nom} ! Montant: {facture.montant_total} FCFA")
            
        except Exception as e:
            messages.error(request, f"Erreur lors de la création de la facture : {str(e)}")
        
        # Rediriger vers la même page pour éviter la double soumission
        return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
    
    
    # Statistiques de base de l'établissement
    nombre_eleves = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
    
    # Calculs financiers
    montant_total_facture = etablissement.montant_total_facturation
    
    # Montant payé (somme des factures payées)
    montant_paye = Facturation.objects.filter(
        etablissement=etablissement,
        statut='paye'
    ).aggregate(total=Sum('montant_total'))['total'] or 0
    
    # Montant restant à payer
    montant_restant = montant_total_facture - montant_paye
    
    # Taux de paiement
    taux_paiement = 0
    if montant_total_facture > 0:
        taux_paiement = round((montant_paye / montant_total_facture) * 100, 1)
    
    # Dernier paiement
    dernier_paiement = Facturation.objects.filter(
        etablissement=etablissement,
        statut='paye'
    ).order_by('-date_paiement').first()
    
    # Nombre de factures générées
    nombre_factures = Facturation.objects.filter(etablissement=etablissement).count()
    
    # Nombre de retards
    nombre_retards = Facturation.objects.filter(
        etablissement=etablissement,
        statut__in=['en_retard', 'impaye', 'contentieux']
    ).count()
    
    # Historique des paiements (toutes les factures payées)
    historique_paiements = []
    for facture in Facturation.objects.filter(
        etablissement=etablissement,
        statut='paye'
    ).order_by('-date_paiement'):
        historique_paiements.append({
            'numero_facture': facture.numero_facture,
            'date_paiement': facture.date_paiement,
            'date_creation': facture.date_creation,
            'type_paiement': facture.get_type_facture_display_detailed(),
            'montant_facture': facture.montant_total,
            'montant_verse': facture.montant_total - facture.reste_a_payer,
            'reste_a_payer': facture.reste_a_payer,
            'paiement_partiel': facture.paiement_partiel,
            'date_echeance_reste': facture.date_echeance_reste,
            'methode': facture.mode_paiement or 'Non spécifié',
            'reference': facture.reference_paiement or 'N/A',
            'statut': 'Payé',
            'statut_detaille': 'Paiement complet' if not facture.paiement_partiel else 'Paiement partiel'
        })
    
    # Factures avec détails
    factures_detailed = []
    for facture in Facturation.objects.filter(etablissement=etablissement).order_by('-date_creation'):
        factures_detailed.append({
            'numero_facture': facture.numero_facture,
            'periode': facture.date_creation.strftime('%b %Y'),
            'montant': facture.montant_total,
            'statut': facture.get_statut_display(),
            'date_emission': facture.date_creation,
            'date_echeance': facture.date_echeance,
            'statut_color': facture.get_statut_display_color(),
            'type_facture_detailed': facture.get_type_facture_display_detailed(),
            'modules_supplementaires': facture.get_modules_supplementaires_display(),
            'montant_par_eleve': facture.get_montant_par_eleve(),
            'nombre_eleves_concernes': facture.get_nombre_eleves_concernes(),
            'est_facture_service': facture.est_facture_service(),
            'est_facture_module': facture.est_facture_module(),
            'reste_a_payer': facture.reste_a_payer,
            'est_paiement_complet': facture.est_paiement_complet(),
            'est_paiement_partiel': facture.est_paiement_partiel(),
            'paiement_partiel': facture.paiement_partiel,
            'date_echeance_reste': facture.date_echeance_reste,
        })
    
    # Statistiques des méthodes de paiement
    methodes_paiement = {}
    for facture in Facturation.objects.filter(etablissement=etablissement, statut='paye'):
        methode = facture.mode_paiement or 'Non spécifié'
        if methode not in methodes_paiement:
            methodes_paiement[methode] = 0
        methodes_paiement[methode] += 1
    
    # Calculer les pourcentages
    total_paiements = sum(methodes_paiement.values())
    methodes_stats = []
    for methode, count in methodes_paiement.items():
        pourcentage = round((count / total_paiements) * 100, 1) if total_paiements > 0 else 0
        methodes_stats.append({
            'nom': methode,
            'pourcentage': pourcentage,
            'count': count
        })
    
    # Résumé financier
    total_facture_historique = Facturation.objects.filter(
        etablissement=etablissement
    ).aggregate(total=Sum('montant_total'))['total'] or 0
    
    total_paye_historique = Facturation.objects.filter(
        etablissement=etablissement,
        statut='paye'
    ).aggregate(total=Sum('montant_total'))['total'] or 0
    
    en_attente_historique = total_facture_historique - total_paye_historique
    
    taux_recouvrement = 0
    if total_facture_historique > 0:
        taux_recouvrement = round((total_paye_historique / total_facture_historique) * 100, 1)
    
    # Modules disponibles dans le système
    tous_les_modules = [
        {'nom': 'module_surveillance', 'titre': 'Surveillance et sécurité', 'icon': 'fas fa-shield-alt'},
        {'nom': 'module_communication', 'titre': 'Communication parents', 'icon': 'fas fa-comments'},
        {'nom': 'module_orientation', 'titre': 'Orientation scolaire', 'icon': 'fas fa-graduation-cap'},
        {'nom': 'module_formation', 'titre': 'Formation continue', 'icon': 'fas fa-book-reader'},
        {'nom': 'module_transport_scolaire', 'titre': 'Transport scolaire', 'icon': 'fas fa-bus'},
        {'nom': 'module_cantine', 'titre': 'Gestion de la cantine', 'icon': 'fas fa-utensils'},
        {'nom': 'module_bibliotheque', 'titre': 'Gestion de la bibliothèque', 'icon': 'fas fa-book'},
        {'nom': 'module_sante', 'titre': 'Suivi médical', 'icon': 'fas fa-heartbeat'},
        {'nom': 'module_activites', 'titre': 'Activités extra-scolaires', 'icon': 'fas fa-futbol'},
        {'nom': 'module_comptabilite', 'titre': 'Comptabilité', 'icon': 'fas fa-calculator'},
        {'nom': 'module_censeurs', 'titre': 'Censeurs', 'icon': 'fas fa-user-shield'},
    ]
    
    # Modules non activés (pas encore activés par l'établissement)
    modules_non_actives = []
    for module in tous_les_modules:
        # Vérifier si le module n'est pas activé (simulation - à adapter selon votre logique)
        # Pour l'instant, on considère que tous les modules sont disponibles
        modules_non_actives.append(module)
    
    # Documents (simulation pour l'instant)
    documents = [
        {
            'nom': 'Contrat de Service',
            'type': 'PDF',
            'date': '15 Jan 2023',
            'icon': 'fas fa-file-pdf'
        },
        {
            'nom': 'Liste des Élèves',
            'type': 'Excel',
            'date': '15 Jan 2024',
            'icon': 'fas fa-file-excel'
        },
        {
            'nom': 'Reçu de Paiement',
            'type': 'Image',
            'date': '15 Jan 2024',
            'icon': 'fas fa-file-image'
        }
    ]
    
    context = {
        'etablissement': etablissement,
        'etablissement_id': etablissement.id,
        'nombre_eleves': nombre_eleves,
        'montant_total_facture': montant_total_facture,
        'montant_paye': montant_paye,
        'montant_restant': montant_restant,
        'taux_paiement': taux_paiement,
        'dernier_paiement': dernier_paiement,
        'nombre_factures': nombre_factures,
        'nombre_retards': nombre_retards,
        'historique_paiements': historique_paiements,
        'factures_detailed': factures_detailed,
        'methodes_stats': methodes_stats,
        'total_facture_historique': total_facture_historique,
        'total_paye_historique': total_paye_historique,
        'en_attente_historique': en_attente_historique,
        'taux_recouvrement': taux_recouvrement,
        'documents': documents,
        'modules_non_actives': modules_non_actives,
    }
    
    return render(request, 'school_admin/gestion_comptable/details_financiers_etablissement.html', context)


def traiter_paiement_facture(request, etablissement_id):
    """
    Vue séparée pour traiter le paiement d'une facture
    """
    from django.db.models import Sum, Count, Q
    from datetime import datetime, timedelta
    from django.utils import timezone
    from django.shortcuts import redirect
    from ..model.facturation_model import Facturation
    
    # Récupérer l'établissement par son ID
    try:
        etablissement = Etablissement.objects.get(id=etablissement_id, actif=True)
    except Etablissement.DoesNotExist:
        messages.error(request, "Établissement introuvable")
        return redirect('school_admin:gestion_etablissements')
    
    # Traitement du paiement
    if request.method == 'POST':
        try:
            # Récupérer les données du paiement
            facture_numero = request.POST.get('facture_numero')
            montant_verse_str = request.POST.get('montant_verse', '')
            date_echeance_reste_str = request.POST.get('date_echeance_reste', '')
            mode_paiement = request.POST.get('mode_paiement', '')
            reference_paiement = request.POST.get('reference_paiement', '')
            
            # Validation des champs requis
            if not facture_numero:
                messages.error(request, "Numéro de facture manquant")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            if not montant_verse_str:
                messages.error(request, "Montant versé requis")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            try:
                from decimal import Decimal
                montant_verse = Decimal(montant_verse_str)
            except (ValueError, TypeError):
                messages.error(request, "Le montant versé doit être un nombre valide")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            # Récupérer la facture
            try:
                facture = Facturation.objects.get(numero_facture=facture_numero, etablissement=etablissement)
            except Facturation.DoesNotExist:
                messages.error(request, "Facture introuvable")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            # Validation du montant
            if montant_verse <= 0:
                messages.error(request, "Le montant versé doit être supérieur à 0")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            if montant_verse > facture.montant_total:
                messages.error(request, f"Le montant versé ({montant_verse} FCFA) ne peut pas être supérieur au montant de la facture ({facture.montant_total} FCFA)")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            # Vérifier si la facture est déjà payée
            if facture.statut == 'paye':
                messages.warning(request, f"La facture {facture_numero} est déjà payée")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            # Traitement du paiement
            if date_echeance_reste_str:
                from datetime import datetime
                date_echeance_reste = datetime.strptime(date_echeance_reste_str, '%Y-%m-%d')
                date_echeance_reste = timezone.make_aware(date_echeance_reste)
            else:
                date_echeance_reste = None
            
            # Utiliser la méthode du modèle pour traiter le paiement
            facture.traiter_paiement_partiel(montant_verse, date_echeance_reste)
            
            # Mettre à jour les informations de paiement
            if mode_paiement:
                facture.mode_paiement = mode_paiement
            if reference_paiement:
                facture.reference_paiement = reference_paiement
            facture.save()
            
            # Message de succès
            if facture.est_paiement_complet():
                messages.success(request, f"Paiement complet enregistré pour la facture {facture_numero} ! Montant: {montant_verse} FCFA")
            else:
                messages.success(request, f"Paiement partiel enregistré pour la facture {facture_numero} ! Montant versé: {montant_verse} FCFA, Reste: {facture.reste_a_payer} FCFA")
            
        except Exception as e:
            messages.error(request, f"Erreur lors du traitement du paiement : {str(e)}")
        
        # Rediriger vers la page des détails financiers
        return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
    
    # Si ce n'est pas une requête POST, rediriger vers la page des détails
    return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)


def facture_etablissement(request):
    """
    Vue pour afficher la facture d'un établissement avec données réelles
    """
    from django.shortcuts import get_object_or_404
    from django.contrib import messages
    from ..model.facturation_model import Facturation
    
    # Récupérer les paramètres
    facture_id = request.GET.get('facture_id')
    etablissement_id = request.GET.get('etablissement_id')
    
    if not facture_id or not etablissement_id:
        messages.error(request, "Paramètres de facture manquants")
        return redirect('school_admin:gestion_etablissements')
    
    try:
        # Récupérer l'établissement
        etablissement = Etablissement.objects.get(id=etablissement_id, actif=True)
        
        # Récupérer la facture
        facture = Facturation.objects.get(
            numero_facture=facture_id,
            etablissement=etablissement
        )
        
        
        # Calculer les montants
        montant_verse = facture.montant_total - facture.reste_a_payer
        
        # Informations de l'entreprise (Goo-School)
        company_info = {
            'nom': 'Goo-School',
            'description': 'Plateforme de Gestion Scolaire',
            'adresse': 'Douala, Cameroun',
            'telephone': '+237 6XX XX XX XX',
            'email': 'contact@goo-school.com',
            'banque': 'Afriland First Bank',
            'compte_nom': 'Goo-School SARL',
            'compte_numero': '1234567890123456',
            'bic': 'AFRIXCMCX'
        }
        
        # Informations de l'établissement
        etablissement_info = {
            'nom': etablissement.nom,
            'directeur': etablissement.directeur_nom,
            'adresse': f"{etablissement.ville}, {etablissement.pays}",
            'telephone': etablissement.telephone,
            'email': etablissement.email,
            'type': etablissement.get_type_etablissement_display()
        }
        
        # Détails de la facture
        facture_info = {
            'numero': facture.numero_facture,
            'date_emission': facture.date_creation,
            'date_echeance': facture.date_echeance,
            'date_paiement': facture.date_paiement,
            'statut': facture.get_statut_display(),
            'type_facture': facture.get_type_facture_display_detailed(),
            'description': facture.description,
            'montant_unitaire': facture.montant_unitaire,
            'quantite': facture.quantite,
            'montant_total': facture.montant_total,
            'montant_verse': montant_verse,
            'reste_a_payer': facture.reste_a_payer,
            'paiement_partiel': facture.paiement_partiel,
            'mode_paiement': facture.mode_paiement,
            'reference_paiement': facture.reference_paiement,
            'date_echeance_reste': facture.date_echeance_reste,
            'statut_envoi': facture.statut_envoi
        }
        
        # Modules supplémentaires si applicable
        modules_supplementaires = []
        if facture.est_facture_module() and facture.has_any_module_selected():
            modules_supplementaires = facture.get_modules_selectionnes()
        
        context = {
            'etablissement': etablissement,
            'facture': facture,
            'company_info': company_info,
            'etablissement_info': etablissement_info,
            'facture_info': facture_info,
            'modules_supplementaires': modules_supplementaires,
        }
        
        return render(request, 'school_admin/gestion_comptable/facture_etablissement.html', context)
        
    except Etablissement.DoesNotExist:
        messages.error(request, "Établissement introuvable")
        return redirect('school_admin:gestion_etablissements')
    except Facturation.DoesNotExist:
        messages.error(request, "Facture introuvable")
        return redirect('school_admin:gestion_etablissements')
    except Exception as e:
        messages.error(request, f"Erreur lors du chargement de la facture : {str(e)}")
        return redirect('school_admin:gestion_etablissements')

def envoyer_facture(request, facture_numero, etablissement_id):
    """
    Vue dédiée pour marquer une facture comme envoyée
    """
    try:
        # Récupérer l'établissement
        etablissement = Etablissement.objects.get(id=etablissement_id, actif=True)
        
        # Récupérer la facture
        facture = Facturation.objects.get(
            numero_facture=facture_numero,
            etablissement=etablissement
        )
        
        # Marquer la facture comme envoyée
        facture.marquer_comme_envoyee()
        
        # Message de succès
        messages.success(request, f"Facture {facture.numero_facture} marquée comme envoyée à {etablissement.nom}")
        
        # Rediriger vers la page de la facture avec paramètres GET
        from django.urls import reverse
        url = reverse('school_admin:facture_etablissement') + f'?facture_id={facture_numero}&etablissement_id={etablissement_id}'
        return redirect(url)
        
    except Etablissement.DoesNotExist:
        messages.error(request, "Établissement introuvable")
        return redirect('school_admin:gestion_etablissements')
    except Facturation.DoesNotExist:
        messages.error(request, "Facture introuvable")
        return redirect('school_admin:gestion_etablissements')
    except Exception as e:
        messages.error(request, f"Erreur lors de l'envoi de la facture : {str(e)}")
        return redirect('school_admin:gestion_etablissements')


def mettre_a_jour_statuts_factures(request):
    """
    Vue pour mettre à jour manuellement les statuts des factures
    """
    if request.method == 'POST':
        try:
            # Exécuter la mise à jour
            nombre_mises_a_jour = Facturation.mettre_a_jour_tous_les_statuts()
            
            if nombre_mises_a_jour > 0:
                messages.success(request, f"✅ Mise à jour terminée: {nombre_mises_a_jour} factures mises à jour")
            else:
                messages.info(request, "ℹ️ Aucune facture à mettre à jour")
                
        except Exception as e:
            messages.error(request, f"❌ Erreur lors de la mise à jour: {str(e)}")
    
    # Récupérer les statistiques des statuts
    stats_statuts = {
        'en_attente': Facturation.objects.filter(statut='en_attente').count(),
        'en_retard': Facturation.objects.filter(statut='en_retard').count(),
        'impaye': Facturation.objects.filter(statut='impaye').count(),
        'contentieux': Facturation.objects.filter(statut='contentieux').count(),
        'paye': Facturation.objects.filter(statut='paye').count(),
    }
    
    # Récupérer les factures en retard récentes
    from django.utils import timezone
    from datetime import timedelta
    
    maintenant = timezone.now()
    factures_en_retard = Facturation.objects.filter(
        statut__in=['en_retard', 'impaye', 'contentieux']
    ).select_related('etablissement').order_by('-date_echeance')[:10]
    
    context = {
        'stats_statuts': stats_statuts,
        'factures_en_retard': factures_en_retard,
    }
    
    return render(request, 'school_admin/gestion_comptable/mettre_a_jour_statuts.html', context)

def gestion_personnel_financier(request):
    # Vue pour la gestion financière du personnel
    return render(request, 'school_admin/gestion_comptable/gestion_personnel_financier.html')


def gestion_depenses(request):
    """
    Vue pour la gestion des dépenses avec données dynamiques
    """
    from django.db.models import Sum, Count, Q
    from datetime import datetime, timedelta
    from django.utils import timezone
    
    # Traitement du formulaire d'ajout de dépense
    if request.method == 'POST' and 'add_expense' in request.POST:
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                description = request.POST.get('description', '').strip()
                montant_str = request.POST.get('montant', '').strip()
                categorie = request.POST.get('categorie', '')
                date_depense_str = request.POST.get('date_depense', '')
                fournisseur = request.POST.get('fournisseur', '').strip()
                notes = request.POST.get('notes', '').strip()
                etablissement_id = request.POST.get('etablissement', '')
                
                # Validation des champs obligatoires
                if not description:
                    messages.error(request, "La description est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                if not montant_str:
                    messages.error(request, "Le montant est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                try:
                    from decimal import Decimal
                    montant = Decimal(montant_str)
                    if montant <= 0:
                        messages.error(request, "Le montant doit être supérieur à 0.")
                        return redirect('school_admin:gestion_depenses')
                except (ValueError, TypeError):
                    messages.error(request, "Le montant doit être un nombre valide.")
                    return redirect('school_admin:gestion_depenses')
                
                if not categorie:
                    messages.error(request, "La catégorie est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                if not date_depense_str:
                    messages.error(request, "La date de dépense est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                try:
                    date_depense = datetime.strptime(date_depense_str, '%Y-%m-%d').date()
                except ValueError:
                    messages.error(request, "Format de date invalide.")
                    return redirect('school_admin:gestion_depenses')
                
                if not fournisseur:
                    messages.error(request, "Le fournisseur est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                # Récupérer l'établissement si spécifié
                etablissement = None
                if etablissement_id:
                    try:
                        etablissement = Etablissement.objects.get(id=etablissement_id, actif=True)
                    except Etablissement.DoesNotExist:
                        messages.warning(request, "Établissement non trouvé, la dépense sera enregistrée sans établissement.")
                
                # Créer la dépense
                depense = Depense(
                    description=description,
                    montant=montant,
                    categorie=categorie,
                    date_depense=date_depense,
                    fournisseur=fournisseur,
                    notes=notes if notes else None,
                    etablissement=etablissement
                )
                
                # Gérer le fichier joint
                if 'piece_jointe' in request.FILES:
                    depense.piece_jointe = request.FILES['piece_jointe']
                
                depense.save()
                
                messages.success(request, f"Dépense '{description}' ajoutée avec succès pour {montant:,.0f} FCFA.")
                return redirect('school_admin:gestion_depenses')
                
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout de la dépense: {str(e)}")
            return redirect('school_admin:gestion_depenses')
    
    # Traitement des actions sur les dépenses
    if request.method == 'POST':
        if 'approve_expense' in request.POST:
            depense_id = request.POST.get('depense_id')
            try:
                depense = Depense.objects.get(id=depense_id)
                if depense.can_be_approved():
                    depense.statut = 'approuve'
                    depense.save()
                    messages.success(request, f"Dépense '{depense.description}' approuvée.")
                else:
                    messages.warning(request, "Cette dépense ne peut pas être approuvée.")
            except Depense.DoesNotExist:
                messages.error(request, "Dépense non trouvée.")
            return redirect('school_admin:gestion_depenses')
        
        elif 'reject_expense' in request.POST:
            depense_id = request.POST.get('depense_id')
            try:
                depense = Depense.objects.get(id=depense_id)
                if depense.can_be_rejected():
                    depense.statut = 'rejete'
                    depense.save()
                    messages.success(request, f"Dépense '{depense.description}' rejetée.")
                else:
                    messages.warning(request, "Cette dépense ne peut pas être rejetée.")
            except Depense.DoesNotExist:
                messages.error(request, "Dépense non trouvée.")
            return redirect('school_admin:gestion_depenses')
        
        elif 'pay_expense' in request.POST:
            depense_id = request.POST.get('depense_id')
            try:
                depense = Depense.objects.get(id=depense_id)
                if depense.can_be_paid():
                    depense.statut = 'paye'
                    depense.save()
                    messages.success(request, f"Dépense '{depense.description}' marquée comme payée.")
                else:
                    messages.warning(request, "Cette dépense ne peut pas être payée.")
            except Depense.DoesNotExist:
                messages.error(request, "Dépense non trouvée.")
            return redirect('school_admin:gestion_depenses')
    
    # Récupérer les filtres
    search_query = request.GET.get('search', '')
    categorie_filter = request.GET.get('categorie', '')
    statut_filter = request.GET.get('statut', '')
    montant_filter = request.GET.get('montant', '')
    date_filter = request.GET.get('date', '')
    
    # Construire la requête
    depenses = Depense.objects.all()
    
    if search_query:
        depenses = depenses.filter(
            Q(description__icontains=search_query) |
            Q(fournisseur__icontains=search_query) |
            Q(notes__icontains=search_query)
        )
    
    if categorie_filter:
        depenses = depenses.filter(categorie=categorie_filter)
    
    if statut_filter:
        depenses = depenses.filter(statut=statut_filter)
    
    if montant_filter:
        if montant_filter == '0-50000':
            depenses = depenses.filter(montant__lte=50000)
        elif montant_filter == '50000-200000':
            depenses = depenses.filter(montant__gte=50000, montant__lte=200000)
        elif montant_filter == '200000-500000':
            depenses = depenses.filter(montant__gte=200000, montant__lte=500000)
        elif montant_filter == '500000+':
            depenses = depenses.filter(montant__gte=500000)
    
    if date_filter:
        try:
            date_obj = datetime.strptime(date_filter, '%Y-%m-%d').date()
            depenses = depenses.filter(date_depense=date_obj)
        except ValueError:
            pass
    
    # Statistiques générales
    total_depenses = depenses.count()
    montant_total = depenses.aggregate(total=Sum('montant'))['total'] or 0
    
    # Statistiques par statut
    stats_statuts = Depense.get_stats_by_status()
    
    # Statistiques par catégorie
    stats_categories = {}
    for categorie, _ in Depense.CATEGORIE_CHOICES:
        total_cat = Depense.get_total_by_category(categorie)
        count_cat = depenses.filter(categorie=categorie).count()
        stats_categories[categorie] = {
            'total': total_cat,
            'count': count_cat
        }
    
    # Dépenses récentes
    depenses_recentes = depenses.order_by('-date_creation')[:10]
    
    # Dépenses urgentes (montant >= 500,000 FCFA)
    depenses_urgentes = depenses.filter(montant__gte=500000, statut__in=['en_attente', 'approuve'])
    
    # Établissements pour le formulaire
    etablissements = Etablissement.objects.filter(actif=True)
    
    # Données pour les budgets
    budgets_actifs = Budget.objects.filter(actif=True).order_by('categorie')
    budget_total = Budget.get_budget_total_actuel()
    depenses_total = Budget.get_depenses_total_actuel()
    budget_restant = Budget.get_budget_restant_total()
    
    # Calculer le pourcentage utilisé
    pourcentage_utilise = 0
    if budget_total > 0:
        pourcentage_utilise = round((depenses_total / budget_total) * 100, 1)
    
    context = {
        'depenses': depenses,
        'total_depenses': total_depenses,
        'montant_total': montant_total,
        'stats_statuts': stats_statuts,
        'stats_categories': stats_categories,
        'depenses_recentes': depenses_recentes,
        'depenses_urgentes': depenses_urgentes,
        'etablissements': etablissements,
        'search_query': search_query,
        'categorie_filter': categorie_filter,
        'statut_filter': statut_filter,
        'montant_filter': montant_filter,
        'date_filter': date_filter,
        # Données budget
        'budgets_actifs': budgets_actifs,
        'budget_total': budget_total,
        'depenses_total': depenses_total,
        'budget_restant': budget_restant,
        'pourcentage_utilise': pourcentage_utilise,
    }
    
    return render(request, 'school_admin/gestion_comptable/gestion_depenses.html', context)


@login_required
def modifier_depense(request, depense_id):
    """
    Vue pour modifier une dépense existante
    """
    from datetime import datetime
    try:
        depense = Depense.objects.get(id=depense_id)
    except Depense.DoesNotExist:
        messages.error(request, "Dépense non trouvée.")
        return redirect('school_admin:gestion_depenses')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                description = request.POST.get('description', '').strip()
                montant_str = request.POST.get('montant', '').strip()
                categorie = request.POST.get('categorie', '')
                date_depense_str = request.POST.get('date_depense', '')
                fournisseur = request.POST.get('fournisseur', '').strip()
                notes = request.POST.get('notes', '').strip()
                etablissement_id = request.POST.get('etablissement', '')
                
                # Validation des champs obligatoires
                if not description:
                    messages.error(request, "La description est obligatoire.")
                    return redirect('school_admin:modifier_depense', depense_id=depense_id)
                
                if not montant_str:
                    messages.error(request, "Le montant est obligatoire.")
                    return redirect('school_admin:modifier_depense', depense_id=depense_id)
                
                try:
                    from decimal import Decimal
                    montant = Decimal(montant_str)
                    if montant <= 0:
                        messages.error(request, "Le montant doit être supérieur à 0.")
                        return redirect('school_admin:modifier_depense', depense_id=depense_id)
                except (ValueError, TypeError):
                    messages.error(request, "Le montant doit être un nombre valide.")
                    return redirect('school_admin:modifier_depense', depense_id=depense_id)
                
                if not categorie:
                    messages.error(request, "La catégorie est obligatoire.")
                    return redirect('school_admin:modifier_depense', depense_id=depense_id)
                
                if not date_depense_str:
                    messages.error(request, "La date de dépense est obligatoire.")
                    return redirect('school_admin:modifier_depense', depense_id=depense_id)
                
                try:
                    date_depense = datetime.strptime(date_depense_str, '%Y-%m-%d').date()
                except ValueError:
                    messages.error(request, "Format de date invalide.")
                    return redirect('school_admin:modifier_depense', depense_id=depense_id)
                
                if not fournisseur:
                    messages.error(request, "Le fournisseur est obligatoire.")
                    return redirect('school_admin:modifier_depense', depense_id=depense_id)
                
                # Récupérer l'établissement si spécifié
                etablissement = None
                if etablissement_id:
                    try:
                        etablissement = Etablissement.objects.get(id=etablissement_id, actif=True)
                    except Etablissement.DoesNotExist:
                        messages.warning(request, "Établissement non trouvé, la dépense sera enregistrée sans établissement.")
                
                # Mettre à jour la dépense
                depense.description = description
                depense.montant = montant
                depense.categorie = categorie
                depense.date_depense = date_depense
                depense.fournisseur = fournisseur
                depense.notes = notes if notes else None
                depense.etablissement = etablissement
                
                # Gérer le fichier joint
                if 'piece_jointe' in request.FILES:
                    depense.piece_jointe = request.FILES['piece_jointe']
                
                depense.save()
                
                messages.success(request, f"Dépense '{description}' modifiée avec succès.")
                return redirect('school_admin:gestion_depenses')
                
        except Exception as e:
            messages.error(request, f"Erreur lors de la modification de la dépense: {str(e)}")
            return redirect('school_admin:modifier_depense', depense_id=depense_id)
    
    # Récupérer les établissements pour le formulaire
    etablissements = Etablissement.objects.filter(actif=True)
    
    context = {
        'depense': depense,
        'etablissements': etablissements,
    }
    
    return render(request, 'school_admin/gestion_comptable/modifier_depense.html', context)


@login_required
def confirmer_depense(request, depense_id):
    """
    Vue pour confirmer qu'une dépense a été effectuée
    """
    try:
        depense = Depense.objects.get(id=depense_id)
        
        if depense.statut != 'en_attente':
            messages.warning(request, "Cette dépense ne peut pas être confirmée.")
            return redirect('school_admin:gestion_depenses')
        
        # Mettre à jour le statut
        depense.statut = 'paye'
        depense.save()
        
        messages.success(request, f"Dépense '{depense.description}' confirmée comme effectuée.")
        return redirect('school_admin:gestion_depenses')
        
    except Depense.DoesNotExist:
        messages.error(request, "Dépense non trouvée.")
        return redirect('school_admin:gestion_depenses')


@login_required
def ajouter_budget(request):
    """
    Vue pour ajouter un nouveau budget
    """
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                nom = request.POST.get('nom', '').strip()
                categorie = request.POST.get('categorie', '')
                periode = request.POST.get('periode', '')
                montant_alloue_str = request.POST.get('montant_alloue', '').strip()
                date_debut_str = request.POST.get('date_debut', '')
                date_fin_str = request.POST.get('date_fin', '')
                notes = request.POST.get('notes', '').strip()
                
                # Validation des champs obligatoires
                if not nom:
                    messages.error(request, "Le nom du budget est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                if not categorie:
                    messages.error(request, "La catégorie est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                if not periode:
                    messages.error(request, "La période est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                if not montant_alloue_str:
                    messages.error(request, "Le montant alloué est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                try:
                    from decimal import Decimal
                    montant_alloue = Decimal(montant_alloue_str)
                    if montant_alloue <= 0:
                        messages.error(request, "Le montant alloué doit être supérieur à 0.")
                        return redirect('school_admin:gestion_depenses')
                except (ValueError, TypeError):
                    messages.error(request, "Le montant alloué doit être un nombre valide.")
                    return redirect('school_admin:gestion_depenses')
                
                if not date_debut_str:
                    messages.error(request, "La date de début est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                if not date_fin_str:
                    messages.error(request, "La date de fin est obligatoire.")
                    return redirect('school_admin:gestion_depenses')
                
                try:
                    from datetime import datetime
                    date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                    
                    if date_fin <= date_debut:
                        messages.error(request, "La date de fin doit être postérieure à la date de début.")
                        return redirect('school_admin:gestion_depenses')
                        
                except ValueError:
                    messages.error(request, "Format de date invalide.")
                    return redirect('school_admin:gestion_depenses')
                
                # Vérifier s'il n'y a pas déjà un budget pour cette catégorie dans cette période
                budget_existant = Budget.objects.filter(
                    categorie=categorie,
                    date_debut__lte=date_fin,
                    date_fin__gte=date_debut,
                    actif=True
                ).exists()
                
                if budget_existant:
                    messages.error(request, f"Un budget existe déjà pour la catégorie '{categorie}' dans cette période.")
                    return redirect('school_admin:gestion_depenses')
                
                # Créer le budget
                budget = Budget(
                    nom=nom,
                    categorie=categorie,
                    periode=periode,
                    montant_alloue=montant_alloue,
                    date_debut=date_debut,
                    date_fin=date_fin,
                    notes=notes if notes else None
                )
                budget.save()
                
                messages.success(request, f"Budget '{nom}' ajouté avec succès pour {montant_alloue:,.0f} FCFA.")
                return redirect('school_admin:gestion_depenses')
                
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout du budget: {str(e)}")
            return redirect('school_admin:gestion_depenses')
    
    return redirect('school_admin:gestion_depenses')


@login_required
def modifier_budget(request, budget_id):
    """
    Vue pour modifier un budget existant
    """
    try:
        budget = Budget.objects.get(id=budget_id)
    except Budget.DoesNotExist:
        messages.error(request, "Budget non trouvé.")
        return redirect('school_admin:gestion_depenses')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                nom = request.POST.get('nom', '').strip()
                categorie = request.POST.get('categorie', '')
                periode = request.POST.get('periode', '')
                montant_alloue_str = request.POST.get('montant_alloue', '').strip()
                date_debut_str = request.POST.get('date_debut', '')
                date_fin_str = request.POST.get('date_fin', '')
                notes = request.POST.get('notes', '').strip()
                
                # Validation des champs obligatoires
                if not nom:
                    messages.error(request, "Le nom du budget est obligatoire.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                if not categorie:
                    messages.error(request, "La catégorie est obligatoire.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                if not periode:
                    messages.error(request, "La période est obligatoire.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                if not montant_alloue_str:
                    messages.error(request, "Le montant alloué est obligatoire.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                try:
                    from decimal import Decimal
                    montant_alloue = Decimal(montant_alloue_str)
                    if montant_alloue <= 0:
                        messages.error(request, "Le montant alloué doit être supérieur à 0.")
                        return redirect('school_admin:modifier_budget', budget_id=budget_id)
                except (ValueError, TypeError):
                    messages.error(request, "Le montant alloué doit être un nombre valide.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                if not date_debut_str:
                    messages.error(request, "La date de début est obligatoire.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                if not date_fin_str:
                    messages.error(request, "La date de fin est obligatoire.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                try:
                    from datetime import datetime
                    date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                    
                    if date_fin <= date_debut:
                        messages.error(request, "La date de fin doit être postérieure à la date de début.")
                        return redirect('school_admin:modifier_budget', budget_id=budget_id)
                        
                except ValueError:
                    messages.error(request, "Format de date invalide.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                # Vérifier s'il n'y a pas déjà un autre budget pour cette catégorie dans cette période
                budget_existant = Budget.objects.filter(
                    categorie=categorie,
                    date_debut__lte=date_fin,
                    date_fin__gte=date_debut,
                    actif=True
                ).exclude(id=budget_id).exists()
                
                if budget_existant:
                    messages.error(request, f"Un autre budget existe déjà pour la catégorie '{categorie}' dans cette période.")
                    return redirect('school_admin:modifier_budget', budget_id=budget_id)
                
                # Mettre à jour le budget
                budget.nom = nom
                budget.categorie = categorie
                budget.periode = periode
                budget.montant_alloue = montant_alloue
                budget.date_debut = date_debut
                budget.date_fin = date_fin
                budget.notes = notes if notes else None
                budget.save()
                
                messages.success(request, f"Budget '{nom}' modifié avec succès.")
                return redirect('school_admin:gestion_depenses')
                
        except Exception as e:
            messages.error(request, f"Erreur lors de la modification du budget: {str(e)}")
            return redirect('school_admin:modifier_budget', budget_id=budget_id)
    
    context = {
        'budget': budget,
    }
    
    return render(request, 'school_admin/gestion_comptable/modifier_budget.html', context)


@login_required
def supprimer_budget(request, budget_id):
    """
    Vue pour supprimer un budget
    """
    try:
        budget = Budget.objects.get(id=budget_id)
        budget_nom = budget.nom
        budget.delete()
        messages.success(request, f"Budget '{budget_nom}' supprimé avec succès.")
    except Budget.DoesNotExist:
        messages.error(request, "Budget non trouvé.")
    
    return redirect('school_admin:gestion_depenses')
