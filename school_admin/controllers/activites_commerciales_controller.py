from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from ..model.prospection_model import Prospection
from ..model.rendez_vous_model import RendezVous
from ..model.compte_rendu_model import CompteRendu
from ..model.compte_user import CompteUser


class ActivitesCommercialesController:
    
    @staticmethod
    @login_required
    def liste_prospects(request):
        """
        Vue pour afficher la liste des prospects avec vue d'ensemble
        """
        # Statistiques générales
        total_prospects = Prospection.objects.filter(actif=True).count()
        prospects_contactes = Prospection.objects.filter(
            actif=True, 
            statut_etablissement='contacte'
        ).count()
        prospects_interesses = Prospection.objects.filter(
            actif=True,
            statut_etablissement__in=['interesse', 'rendez_vous', 'negociation']
        ).count()
        contrats_signes = Prospection.objects.filter(
            actif=True,
            statut_etablissement='contrat_signe'
        ).count()
        
        # Statistiques par statut
        stats_par_statut = Prospection.objects.filter(actif=True).values(
            'statut_etablissement'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Statistiques par potentiel
        stats_par_potentiel = Prospection.objects.filter(actif=True).values(
            'potentiel_etablissement'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Statistiques récentes (30 derniers jours)
        date_limite = timezone.now() - timedelta(days=30)
        nouveaux_prospects = Prospection.objects.filter(
            actif=True,
            date_creation__gte=date_limite
        ).count()
        
        # Récupération des prospects avec pagination
        prospects = Prospection.objects.filter(actif=True).select_related(
            'cree_par'
        ).prefetch_related(
            'rendez_vous',
            'comptes_rendus'
        ).order_by('-date_creation')
        
        # Filtres
        statut_filter = request.GET.get('statut', '')
        commercial_filter = request.GET.get('commercial', '')
        potentiel_filter = request.GET.get('potentiel', '')
        recherche = request.GET.get('recherche', '')
        
        if statut_filter:
            prospects = prospects.filter(statut_etablissement=statut_filter)
        if commercial_filter:
            prospects = prospects.filter(cree_par_id=commercial_filter)
        if potentiel_filter:
            prospects = prospects.filter(potentiel_etablissement=potentiel_filter)
        if recherche:
            prospects = prospects.filter(
                Q(nom_etablissement__icontains=recherche) |
                Q(ville_etablissement__icontains=recherche) |
                Q(pays_etablissement__icontains=recherche)
            )
        
        # Liste des commerciaux pour le filtre
        commerciaux = CompteUser.objects.filter(
            fonction='commercial',
            is_active=True
        ).order_by('nom', 'prenom')
        
        context = {
            'total_prospects': total_prospects,
            'prospects_contactes': prospects_contactes,
            'prospects_interesses': prospects_interesses,
            'contrats_signes': contrats_signes,
            'nouveaux_prospects': nouveaux_prospects,
            'stats_par_statut': stats_par_statut,
            'stats_par_potentiel': stats_par_potentiel,
            'prospects': prospects,
            'commerciaux': commerciaux,
            'statut_filter': statut_filter,
            'commercial_filter': commercial_filter,
            'potentiel_filter': potentiel_filter,
            'recherche': recherche,
            'STATUT_CHOICES': Prospection.STATUT_CHOICES,
            'POTENTIEL_CHOICES': Prospection.POTENTIEL_CHOICES,
        }
        
        return render(
            request,
            'school_admin/administrateur/activites_commerciales/liste_prospects.html',
            context
        )
    
    @staticmethod
    @login_required
    def detail_prospect(request, prospect_id):
        """
        Vue pour afficher les détails complets d'un prospect
        """
        prospect = get_object_or_404(
            Prospection.objects.select_related('cree_par').prefetch_related(
                'rendez_vous',
                'comptes_rendus'
            ),
            id=prospect_id,
            actif=True
        )
        
        # Rendez-vous associés
        rendez_vous = prospect.rendez_vous.filter(actif=True).order_by('-date_rdv', '-heure_rdv')
        
        # Comptes rendus associés
        comptes_rendus = prospect.comptes_rendus.filter(actif=True).order_by('-date_visite')
        
        # Statistiques pour ce prospect
        nb_rendez_vous = rendez_vous.count()
        nb_comptes_rendus = comptes_rendus.count()
        dernier_rendez_vous = rendez_vous.first()
        dernier_compte_rendu = comptes_rendus.first()
        
        context = {
            'prospect': prospect,
            'rendez_vous': rendez_vous,
            'comptes_rendus': comptes_rendus,
            'nb_rendez_vous': nb_rendez_vous,
            'nb_comptes_rendus': nb_comptes_rendus,
            'dernier_rendez_vous': dernier_rendez_vous,
            'dernier_compte_rendu': dernier_compte_rendu,
        }
        
        return render(
            request,
            'school_admin/administrateur/activites_commerciales/detail_prospect.html',
            context
        )
    
    @staticmethod
    @login_required
    def analyse_performances(request):
        """
        Vue pour analyser les performances des commerciaux
        """
        # Récupération de tous les commerciaux actifs
        commerciaux = CompteUser.objects.filter(
            fonction='commercial',
            is_active=True
        ).order_by('nom', 'prenom')
        
        # Calcul des statistiques pour chaque commercial
        performances = []
        for commercial in commerciaux:
            # Prospects créés
            nb_prospects = Prospection.objects.filter(
                cree_par=commercial,
                actif=True
            ).count()
            
            # Prospects par statut
            prospects_contactes = Prospection.objects.filter(
                cree_par=commercial,
                actif=True,
                statut_etablissement='contacte'
            ).count()
            
            prospects_interesses = Prospection.objects.filter(
                cree_par=commercial,
                actif=True,
                statut_etablissement__in=['interesse', 'rendez_vous', 'negociation']
            ).count()
            
            contrats_signes = Prospection.objects.filter(
                cree_par=commercial,
                actif=True,
                statut_etablissement='contrat_signe'
            ).count()
            
            # Rendez-vous organisés
            nb_rendez_vous = RendezVous.objects.filter(
                cree_par=commercial,
                actif=True
            ).count()
            
            # Comptes rendus rédigés
            nb_comptes_rendus = CompteRendu.objects.filter(
                cree_par=commercial,
                actif=True
            ).count()
            
            # Taux de conversion (contrats signés / prospects totaux)
            taux_conversion = (contrats_signes / nb_prospects * 100) if nb_prospects > 0 else 0
            
            # Prospects créés ce mois
            date_debut_mois = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            prospects_ce_mois = Prospection.objects.filter(
                cree_par=commercial,
                actif=True,
                date_creation__gte=date_debut_mois
            ).count()
            
            # Prospects créés ce mois dernier
            date_debut_mois_dernier = (date_debut_mois - timedelta(days=1)).replace(day=1)
            date_fin_mois_dernier = date_debut_mois - timedelta(days=1)
            prospects_mois_dernier = Prospection.objects.filter(
                cree_par=commercial,
                actif=True,
                date_creation__gte=date_debut_mois_dernier,
                date_creation__lte=date_fin_mois_dernier
            ).count()
            
            # Évolution
            evolution = prospects_ce_mois - prospects_mois_dernier if prospects_mois_dernier > 0 else 0
            pourcentage_evolution = (evolution / prospects_mois_dernier * 100) if prospects_mois_dernier > 0 else 0
            
            # ===== CALCUL DU SCORE PONDÉRÉ =====
            # Système de points selon différents critères avec poids
            
            # 1. CONTRATS SIGNÉS (Poids: 50% - Critère principal)
            # Points: 100 points par contrat signé
            points_contrats = contrats_signes * 100
            
            # 2. TAUX DE CONVERSION (Poids: 20% - Efficacité)
            # Points: 10 points par % de conversion (max 1000 points pour 100%)
            points_conversion = taux_conversion * 10
            
            # 3. PROSPECTS INTÉRESSÉS (Poids: 12% - Pipeline actif)
            # Points: 20 points par prospect intéressé
            points_interesses = prospects_interesses * 20
            
            # 4. ACTIVITÉ RENDEZ-VOUS (Poids: 8% - Suivi client)
            # Points: 15 points par rendez-vous
            points_rendez_vous = nb_rendez_vous * 15
            
            # 5. COMPTES RENDUS (Poids: 5% - Qualité du suivi)
            # Points: 10 points par compte rendu
            points_comptes_rendus = nb_comptes_rendus * 10
            
            # 6. VOLUME DE PROSPECTS (Poids: 3% - Effort de prospection)
            # Points: 2 points par prospect créé (bonus pour l'effort)
            points_volume = nb_prospects * 2
            
            # 7. ÉVOLUTION POSITIVE (Poids: 2% - Progression)
            # Bonus: 50 points si évolution positive ce mois
            points_evolution = 50 if evolution > 0 else 0
            
            # Score total pondéré
            score_total = (
                points_contrats * 0.50 +      # 50%
                points_conversion * 0.20 +    # 20%
                points_interesses * 0.12 +    # 12%
                points_rendez_vous * 0.08 +   # 8%
                points_comptes_rendus * 0.05 + # 5%
                points_volume * 0.03 +        # 3%
                points_evolution * 0.02        # 2%
            )
            
            # Détail des points pour affichage
            detail_points = {
                'contrats': round(points_contrats * 0.50, 2),
                'conversion': round(points_conversion * 0.20, 2),
                'interesses': round(points_interesses * 0.12, 2),
                'rendez_vous': round(points_rendez_vous * 0.08, 2),
                'comptes_rendus': round(points_comptes_rendus * 0.05, 2),
                'volume': round(points_volume * 0.03, 2),
                'evolution': round(points_evolution * 0.02, 2),
            }
            
            performances.append({
                'commercial': commercial,
                'nb_prospects': nb_prospects,
                'prospects_contactes': prospects_contactes,
                'prospects_interesses': prospects_interesses,
                'contrats_signes': contrats_signes,
                'nb_rendez_vous': nb_rendez_vous,
                'nb_comptes_rendus': nb_comptes_rendus,
                'taux_conversion': round(taux_conversion, 2),
                'prospects_ce_mois': prospects_ce_mois,
                'prospects_mois_dernier': prospects_mois_dernier,
                'evolution': evolution,
                'pourcentage_evolution': round(pourcentage_evolution, 2),
                'score_performance': round(score_total, 2),
                'detail_points': detail_points,
            })
        
        # Tri par score de performance total (décroissant)
        # En cas d'égalité: par contrats signés, puis par taux de conversion
        performances.sort(
            key=lambda x: (x['score_performance'], x['contrats_signes'], x['taux_conversion']), 
            reverse=True
        )
        
        # Statistiques globales
        total_prospects_globaux = Prospection.objects.filter(actif=True).count()
        total_contrats_signes = Prospection.objects.filter(
            actif=True,
            statut_etablissement='contrat_signe'
        ).count()
        taux_conversion_global = (total_contrats_signes / total_prospects_globaux * 100) if total_prospects_globaux > 0 else 0
        
        context = {
            'performances': performances,
            'total_prospects_globaux': total_prospects_globaux,
            'total_contrats_signes': total_contrats_signes,
            'taux_conversion_global': round(taux_conversion_global, 2),
        }
        
        return render(
            request,
            'school_admin/administrateur/activites_commerciales/analyse_performances.html',
            context
        )

