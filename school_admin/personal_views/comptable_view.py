from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.db.models import Sum, Count
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, time
import json
from ..model.etablissement_model import Etablissement
from ..model.eleve_model import Eleve
from ..model.facturation_model import Facturation
from ..model.depense_model import Depense
from ..model.budget_model import Budget
from django.contrib import messages
from django.db import transaction
from ..decorators import comptable_required, comptable_or_admin_required
def ensure_datetime(value):
    if isinstance(value, datetime):
        return value, True
    if isinstance(value, date):
        return datetime.combine(value, time.min), False
    return value, isinstance(value, datetime)






@comptable_required
def dashboard_comptable(request):
    """
    Dashboard comptable avec données dynamiques basées sur les modèles réels
    """
    from django.db.models import Sum, Count, Q, Avg
    from django.utils import timezone
    from datetime import datetime, timedelta
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..model.depense_model import Depense
    
    # Mettre à jour les statuts de réglementation de tous les établissements
    for etablissement in Etablissement.objects.filter(actif=True):
        etablissement.mettre_a_jour_statut_reglementation()
    
    # Statistiques générales
    total_etablissements = Etablissement.objects.filter(actif=True).count()
    total_eleves = Eleve.objects.filter(actif=True).count()
    
    # Revenus totaux collectés (somme de tous les montant_verse des factures payées)
    factures_payees = Facturation.objects.filter(statut='paye').exclude(statut='annule')
    revenus_collectes = factures_payees.aggregate(
        total=Sum('montant_verse')
    )['total'] or 0
    
    # Si montant_verse est None ou 0, utiliser montant_total pour les factures complètement payées
    if revenus_collectes == 0:
        revenus_collectes = factures_payees.filter(paiement_partiel=False).aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montants en attente (somme de tous les reste_a_payer des factures en attente)
    factures_attente = Facturation.objects.filter(statut='en_attente').exclude(statut='annule')
    montants_en_attente = factures_attente.aggregate(
        total=Sum('reste_a_payer')
    )['total'] or 0
    
    # Si reste_a_payer est None ou 0, utiliser montant_total
    if montants_en_attente == 0:
        montants_en_attente = factures_attente.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montants en retard (somme de tous les reste_a_payer des factures en retard, impayées, contentieux)
    factures_retard = Facturation.objects.filter(
        statut__in=['en_retard', 'impaye', 'contentieux']
    ).exclude(statut='annule')
    
    montants_en_retard = factures_retard.aggregate(
        total=Sum('reste_a_payer')
    )['total'] or 0
    
    # Si reste_a_payer est None ou 0, utiliser montant_total
    if montants_en_retard == 0:
        montants_en_retard = factures_retard.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montant total attendu (toutes les factures non annulées)
    factures_actives = Facturation.objects.exclude(statut='annule')
    montant_total_attendu = factures_actives.aggregate(
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
        
        # Montant total : somme de toutes les factures (non annulées)
        factures_etablissement = Facturation.objects.filter(
            etablissement=etablissement
        ).exclude(statut='annule')
        
        montant_total = factures_etablissement.aggregate(
                total=Sum('montant_total')
            )['total'] or 0
        
        # Montant dû : somme de tous les reste_a_payer
        montant_du = factures_etablissement.aggregate(
            total=Sum('reste_a_payer')
        )['total'] or 0
        
        # Si reste_a_payer est None ou 0, calculer à partir des factures non payées
        if montant_du == 0:
            factures_non_payees = factures_etablissement.exclude(statut='paye')
            montant_du = factures_non_payees.aggregate(
                total=Sum('montant_total')
            )['total'] or 0
        
        etablissements_stats.append({
            'etablissement': etablissement,
            'nombre_eleves': nombre_eleves,
            'montant_total': montant_total,
            'montant_du': montant_du,
            'statut_reglementation': etablissement.get_statut_reglementation_display(),
        })
    
    # Activité récente (dernières factures)
    activites_recentes = Facturation.objects.select_related('etablissement').exclude(
        statut='annule'
    ).order_by('-date_creation')[:6]
    
    # Inscriptions en retard (établissements avec statut_reglementation différent de 'en_regle')
    inscriptions_retard = Etablissement.objects.filter(
        actif=True
    ).exclude(statut_reglementation='en_regle').count()
    
    # Personnel (nombre d'employés actifs)
    personnel_actif = PersonnelAdministratif.objects.filter(is_active=True).count()
    personnel_total = PersonnelAdministratif.objects.count()
    
    # Calcul des tendances mensuelles
    maintenant = timezone.now()
    mois_actuel = maintenant.month
    annee_actuelle = maintenant.year
    
    # Établissements ce mois vs mois précédent
    etablissements_ce_mois = Etablissement.objects.filter(
        date_creation__year=annee_actuelle,
        date_creation__month=mois_actuel
    ).count()
    
    if mois_actuel == 1:
        mois_precedent = 12
        annee_precedente = annee_actuelle - 1
    else:
        mois_precedent = mois_actuel - 1
        annee_precedente = annee_actuelle
    
    etablissements_mois_precedent = Etablissement.objects.filter(
        date_creation__year=annee_precedente,
        date_creation__month=mois_precedent
    ).count()
    
    # Élèves ce mois vs mois précédent
    eleves_ce_mois = Eleve.objects.filter(
        date_inscription__year=annee_actuelle,
        date_inscription__month=mois_actuel
    ).count()
    
    eleves_mois_precedent = Eleve.objects.filter(
        date_inscription__year=annee_precedente,
        date_inscription__month=mois_precedent
    ).count()
    
    pourcentage_evolution_eleves = 0
    if eleves_mois_precedent > 0:
        pourcentage_evolution_eleves = round(((eleves_ce_mois - eleves_mois_precedent) / eleves_mois_precedent) * 100, 1)
    
    # Revenus ce mois vs mois précédent
    factures_mois_actuel = Facturation.objects.filter(
        date_creation__year=annee_actuelle,
        date_creation__month=mois_actuel
    ).exclude(statut='annule')
    
    revenus_mois_actuel = factures_mois_actuel.filter(statut='paye').aggregate(
        total=Sum('montant_verse')
    )['total'] or 0
    
    if revenus_mois_actuel == 0:
        revenus_mois_actuel = factures_mois_actuel.filter(statut='paye', paiement_partiel=False).aggregate(
            total=Sum('montant_total')
        )['total'] or 0
    
    factures_mois_precedent = Facturation.objects.filter(
        date_creation__year=annee_precedente,
        date_creation__month=mois_precedent
    ).exclude(statut='annule')
    
    revenus_mois_precedent = factures_mois_precedent.filter(statut='paye').aggregate(
        total=Sum('montant_verse')
    )['total'] or 0
    
    if revenus_mois_precedent == 0:
        revenus_mois_precedent = factures_mois_precedent.filter(statut='paye', paiement_partiel=False).aggregate(
            total=Sum('montant_total')
        )['total'] or 0
    
    pourcentage_evolution_revenus = 0
    if revenus_mois_precedent > 0:
        pourcentage_evolution_revenus = round(((revenus_mois_actuel - revenus_mois_precedent) / revenus_mois_precedent) * 100, 1)
    
    # Bénéfices (revenus collectés - dépenses payées)
    depenses_payees = Depense.objects.filter(statut='paye').aggregate(
        total=Sum('montant')
    )['total'] or 0
    
    benefices_estimes = revenus_collectes - depenses_payees
    if benefices_estimes < 0:
        benefices_estimes = 0
    
    # Pourcentage de bénéfices (comparaison mois actuel vs mois précédent)
    depenses_mois_actuel = Depense.objects.filter(
        date_depense__year=annee_actuelle,
        date_depense__month=mois_actuel,
        statut='paye'
    ).aggregate(total=Sum('montant'))['total'] or 0
    
    benefices_mois_actuel = revenus_mois_actuel - depenses_mois_actuel
    if benefices_mois_actuel < 0:
        benefices_mois_actuel = 0
    
    depenses_mois_precedent = Depense.objects.filter(
        date_depense__year=annee_precedente,
        date_depense__month=mois_precedent,
        statut='paye'
    ).aggregate(total=Sum('montant'))['total'] or 0
    
    benefices_mois_precedent = revenus_mois_precedent - depenses_mois_precedent
    if benefices_mois_precedent < 0:
        benefices_mois_precedent = 0
    
    pourcentage_evolution_benefices = 0
    if benefices_mois_precedent > 0:
        pourcentage_evolution_benefices = round(((benefices_mois_actuel - benefices_mois_precedent) / benefices_mois_precedent) * 100, 1)
    elif benefices_mois_actuel > 0 and benefices_mois_precedent == 0:
        pourcentage_evolution_benefices = 100  # Nouveau bénéfice
    
    # Paiements personnel (dépenses de catégorie 'personnel')
    depenses_personnel = Depense.objects.filter(
        categorie='personnel',
        statut='paye'
    )
    
    montant_total_personnel = depenses_personnel.aggregate(
        total=Sum('montant')
    )['total'] or 0
    
    # Dernier paiement personnel
    dernier_paiement_personnel = depenses_personnel.order_by('-date_depense').first()
    dernier_paiement_date = None
    if dernier_paiement_personnel:
        dernier_paiement_date = dernier_paiement_personnel.date_depense.strftime('%d %B %Y')
    
    # Prochain paiement (estimation : fin du mois en cours)
    prochain_paiement_date = datetime(annee_actuelle, mois_actuel, 28).strftime('%d %B %Y')
    
    paiements_personnel = {
        'montant_total': montant_total_personnel,
        'dernier_paiement': dernier_paiement_date or 'Aucun paiement',
        'prochain_paiement': prochain_paiement_date
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
        'etablissements_ce_mois': etablissements_ce_mois,
        'pourcentage_evolution_eleves': pourcentage_evolution_eleves,
        'pourcentage_evolution_revenus': pourcentage_evolution_revenus,
        'pourcentage_evolution_benefices': pourcentage_evolution_benefices,
    }
    
    return render(request, 'school_admin/gestion_comptable/dashboard_comptable.html', context)


@comptable_or_admin_required
def suivi_revenus(request):
    """
    Vue pour le suivi des revenus avec données dynamiques et gestion des dépenses
    Accessible aux comptables et administrateurs
    """
    from django.contrib import messages
    from django.utils import timezone
    
    # Traitement des formulaires de dépenses
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'ajouter_depense':
            description = request.POST.get('description', '').strip()
            montant = request.POST.get('montant', '').strip()
            categorie = request.POST.get('categorie', '').strip()
            type_depense = request.POST.get('type_depense', 'unique').strip()
            date_depense = request.POST.get('date_depense', '').strip()
            fournisseur = request.POST.get('fournisseur', '').strip()
            numero_facture = request.POST.get('numero_facture', '').strip()
            methode_paiement = request.POST.get('methode_paiement', 'virement').strip()
            statut = request.POST.get('statut', 'en_attente').strip()
            notes = request.POST.get('notes', '').strip()
            etablissement_id = request.POST.get('etablissement', '').strip()
            
            # Validation
            if not description:
                messages.error(request, "La description est obligatoire.")
            elif not montant:
                messages.error(request, "Le montant est obligatoire.")
            elif not categorie:
                messages.error(request, "La catégorie est obligatoire.")
            elif not date_depense:
                messages.error(request, "La date de dépense est obligatoire.")
            elif not fournisseur:
                messages.error(request, "Le fournisseur est obligatoire.")
            elif type_depense not in dict(Depense.TYPE_DEPENSE_CHOICES).keys():
                messages.error(request, "Le type de dépense sélectionné est invalide.")
            else:
                try:
                    montant_decimal = Decimal(montant)
                    if montant_decimal <= 0:
                        messages.error(request, "Le montant doit être supérieur à 0.")
                    else:
                        try:
                            date_depense_obj = datetime.strptime(date_depense, '%Y-%m-%d').date()
                            
                            # Date de paiement si la dépense est payée
                            date_paiement_obj = None
                            if statut == 'paye':
                                date_paiement_str = request.POST.get('date_paiement', '').strip()
                                if date_paiement_str:
                                    date_paiement_obj = datetime.strptime(date_paiement_str, '%Y-%m-%d').date()
                                else:
                                    date_paiement_obj = timezone.now().date()
                            
                            # Établissement (optionnel)
                            etablissement = None
                            if etablissement_id:
                                try:
                                    etablissement = Etablissement.objects.get(id=int(etablissement_id))
                                except (Etablissement.DoesNotExist, ValueError):
                                    pass
                            
                            # Créer la dépense
                            depense = Depense.objects.create(
                                description=description,
                                montant=montant_decimal,
                                categorie=categorie,
                                type_depense=type_depense,
                                date_depense=date_depense_obj,
                                fournisseur=fournisseur,
                                numero_facture=numero_facture if numero_facture else None,
                                methode_paiement=methode_paiement,
                                statut=statut,
                                date_paiement=date_paiement_obj,
                                notes=notes if notes else None,
                                etablissement=etablissement,
                            )
                            
                            # Gérer la pièce jointe si fournie
                            if 'piece_jointe' in request.FILES:
                                depense.piece_jointe = request.FILES['piece_jointe']
                                depense.save()
                            
                            messages.success(request, f"Dépense '{description}' ajoutée avec succès.")
                        except ValueError as ve:
                            messages.error(request, f"Format de date invalide : {str(ve)}")
                except ValueError:
                    messages.error(request, "Le montant doit être un nombre valide.")
                except Exception as e:
                    messages.error(request, f"Erreur lors de l'ajout de la dépense : {str(e)}")
        
        elif action == 'modifier_depense':
            depense_id = request.POST.get('depense_id')
            try:
                depense = Depense.objects.get(id=depense_id)
                
                description = request.POST.get('description', '').strip()
                montant = request.POST.get('montant', '').strip()
                categorie = request.POST.get('categorie', '').strip()
                type_depense = request.POST.get('type_depense', depense.type_depense).strip()
                date_depense = request.POST.get('date_depense', '').strip()
                fournisseur = request.POST.get('fournisseur', '').strip()
                numero_facture = request.POST.get('numero_facture', '').strip()
                methode_paiement = request.POST.get('methode_paiement', 'virement').strip()
                statut = request.POST.get('statut', 'en_attente').strip()
                notes = request.POST.get('notes', '').strip()
                etablissement_id = request.POST.get('etablissement', '').strip()
                
                # Validation
                if not description:
                    messages.error(request, "La description est obligatoire.")
                elif not montant:
                    messages.error(request, "Le montant est obligatoire.")
                elif not categorie:
                    messages.error(request, "La catégorie est obligatoire.")
                elif not date_depense:
                    messages.error(request, "La date de dépense est obligatoire.")
                elif not fournisseur:
                    messages.error(request, "Le fournisseur est obligatoire.")
                elif type_depense not in dict(Depense.TYPE_DEPENSE_CHOICES).keys():
                    messages.error(request, "Le type de dépense sélectionné est invalide.")
                else:
                    try:
                        montant_decimal = Decimal(montant)
                        if montant_decimal <= 0:
                            messages.error(request, "Le montant doit être supérieur à 0.")
                        else:
                            date_depense_obj = datetime.strptime(date_depense, '%Y-%m-%d').date()
                            
                            # Date de paiement si la dépense est payée
                            date_paiement_obj = None
                            if statut == 'paye':
                                date_paiement_str = request.POST.get('date_paiement', '').strip()
                                if date_paiement_str:
                                    date_paiement_obj = datetime.strptime(date_paiement_str, '%Y-%m-%d').date()
                                elif not depense.date_paiement:
                                    date_paiement_obj = timezone.now().date()
                                else:
                                    date_paiement_obj = depense.date_paiement
                            else:
                                date_paiement_obj = None
                            
                            # Établissement (optionnel)
                            etablissement = None
                            if etablissement_id:
                                try:
                                    etablissement = Etablissement.objects.get(id=int(etablissement_id))
                                except (Etablissement.DoesNotExist, ValueError):
                                    pass
                            
                            # Mettre à jour la dépense
                            depense.description = description
                            depense.montant = montant_decimal
                            depense.categorie = categorie
                            depense.type_depense = type_depense
                            depense.date_depense = date_depense_obj
                            depense.fournisseur = fournisseur
                            depense.numero_facture = numero_facture if numero_facture else None
                            depense.methode_paiement = methode_paiement
                            depense.statut = statut
                            depense.date_paiement = date_paiement_obj
                            depense.notes = notes if notes else None
                            depense.etablissement = etablissement
                            
                            # Gérer la pièce jointe si fournie
                            if 'piece_jointe' in request.FILES:
                                depense.piece_jointe = request.FILES['piece_jointe']
                            
                            depense.save()
                            messages.success(request, f"Dépense '{description}' modifiée avec succès.")
                    except ValueError:
                        messages.error(request, "Le montant ou la date doit être valide.")
                    except Exception as e:
                        messages.error(request, f"Erreur lors de la modification de la dépense : {str(e)}")
            except Depense.DoesNotExist:
                messages.error(request, "Dépense introuvable.")
        
        elif action == 'supprimer_depense':
            depense_id = request.POST.get('depense_id')
            try:
                depense = Depense.objects.get(id=depense_id)
                description = depense.description
                depense.delete()
                messages.success(request, f"Dépense '{description}' supprimée avec succès.")
            except Depense.DoesNotExist:
                messages.error(request, "Dépense introuvable.")
    
        # Toujours rediriger après un POST pour éviter les resoumissions
        return redirect('school_admin:suivi_revenus')

    # Statistiques générales
    total_etablissements = Etablissement.objects.filter(actif=True).count()
    total_eleves = Eleve.objects.filter(actif=True).count()
    
    # Revenus attendus (somme de tous les montants_total_facturation des établissements actifs)
    revenus_attendus = Etablissement.objects.filter(actif=True).aggregate(
        total=Sum('montant_total_facturation')
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
        
        # Utiliser le nombre d'élèves facturés depuis l'établissement (calculé automatiquement)
        nombre_eleves_factures = etablissement.nombre_eleves_factures
        
        if derniere_facture:
            statut_inscription = derniere_facture.get_statut_display()
        else:
            statut_inscription = "Aucune facture pour le moment"
        
        # Mettre à jour le statut de réglementation de l'établissement
        etablissement.mettre_a_jour_statut_reglementation()
        statut_reglementation = etablissement.get_statut_reglementation_display()
        
        etablissements_detailed.append({
            'etablissement': etablissement,
            'nombre_eleves': nombre_eleves,
            'montant_total': montant_total,
            'montant_premier_versement': montant_premier_versement,
            'date_premier_versement': date_premier_versement,
            'montant_du': montant_du,
            'statut_inscription': statut_inscription,
            'statut_reglementation': statut_reglementation,
            'statut_reglementation_code': etablissement.statut_reglementation,
            'nombre_eleves_factures': nombre_eleves_factures,
        })
    
    # Dépenses - Statistiques par catégorie
    depenses_personnel = Depense.objects.filter(categorie='personnel', statut='paye').aggregate(
        total=Sum('montant')
    )['total'] or 0
    
    depenses_maintenance = Depense.objects.filter(categorie='maintenance', statut='paye').aggregate(
        total=Sum('montant')
    )['total'] or 0
    
    depenses_loyer = Depense.objects.filter(categorie='loyer', statut='paye').aggregate(
        total=Sum('montant')
    )['total'] or 0
    
    depenses_total = Depense.objects.filter(statut='paye').aggregate(
        total=Sum('montant')
    )['total'] or 0
    
    depenses_stats = {
        'personnel': depenses_personnel,
        'maintenance': depenses_maintenance,
        'loyer': depenses_loyer,
        'total': depenses_total,
    }
    
    # Liste des dépenses détaillées depuis la base de données
    depenses_queryset = Depense.objects.all().order_by('-date_creation')
    depenses_detailed = []
    depenses_par_categorie = {}
    
    # Mapping des catégories vers les icônes
    categorie_icons = {
        'personnel': ('fas fa-users', 'personnel'),
        'equipement': ('fas fa-laptop', 'equipement'),
        'maintenance': ('fas fa-tools', 'maintenance'),
        'formation': ('fas fa-graduation-cap', 'formation'),
        'marketing': ('fas fa-bullhorn', 'marketing'),
        'bureau': ('fas fa-briefcase', 'bureau'),
        'transport': ('fas fa-car', 'transport'),
        'loyer': ('fas fa-building', 'loyer'),
        'autre': ('fas fa-file-invoice', 'autre'),
    }
    
    # Initialiser les dictionnaires par catégorie
    for cat_key, cat_display in Depense.CATEGORIE_CHOICES:
        depenses_par_categorie[cat_key] = []
    
    for depense in depenses_queryset:
        icon, icon_class = categorie_icons.get(depense.categorie, ('fas fa-file-invoice', 'autre'))
        
        # Détails supplémentaires
        details_parts = []
        if depense.numero_facture:
            details_parts.append(f"Facture: {depense.numero_facture}")
        if depense.etablissement:
            details_parts.append(f"Établissement: {depense.etablissement.nom}")
        if depense.methode_paiement:
            details_parts.append(f"Paiement: {depense.get_methode_paiement_display()}")
        details = " • ".join(details_parts) if details_parts else depense.notes or ""
        
        from datetime import datetime
        try:
            date_str = depense.date_depense.strftime('%d %b %Y')
        except:
            date_str = depense.date_depense.strftime('%d/%m/%Y') if depense.date_depense else 'N/A'
        
        try:
            date_paiement_str = depense.date_paiement.strftime('%d %b %Y') if depense.date_paiement else None
        except:
            date_paiement_str = depense.date_paiement.strftime('%d/%m/%Y') if depense.date_paiement else None
        
        depense_data = {
            'id': depense.id,
            'type': depense.get_categorie_display(),
            'categorie': depense.categorie,
            'description': depense.description,
            'details': details,
            'montant': depense.montant,
            'date': date_str,
            'statut': depense.get_statut_display(),
            'statut_code': depense.statut,
            'icon': icon,
            'icon_class': icon_class,
            'fournisseur': depense.fournisseur,
            'numero_facture': depense.numero_facture,
            'methode_paiement': depense.get_methode_paiement_display(),
            'date_paiement': date_paiement_str,
            'notes': depense.notes,
            'piece_jointe': depense.piece_jointe.url if depense.piece_jointe else None,
            'etablissement': depense.etablissement,
            'type_depense': depense.type_depense,
            'type_depense_label': depense.get_type_depense_display(),
        }
        
        depenses_detailed.append(depense_data)
        # Organiser par catégorie
        if depense.categorie in depenses_par_categorie:
            depenses_par_categorie[depense.categorie].append(depense_data)
    
    # Liste des établissements pour le formulaire (optionnel)
    etablissements_list = Etablissement.objects.filter(actif=True).order_by('nom')
    
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
        'depenses_par_categorie': depenses_par_categorie,
        'etablissements_list': etablissements_list,
        'type_depense_choices': Depense.TYPE_DEPENSE_CHOICES,
        'categorie_choices': Depense.CATEGORIE_CHOICES,
    }
    
    return render(request, 'school_admin/gestion_comptable/suivi_revenus.html', context)


@comptable_required
def depense_detail_json(request, depense_id):
    """
    Vue pour récupérer les détails d'une dépense en JSON
    """
    from django.http import JsonResponse
    from datetime import datetime
    
    try:
        depense = Depense.objects.get(id=depense_id)
        
        # Mapping des statuts vers les classes CSS
        statut_classes = {
            'en_attente': 'en-attente',
            'approuve': 'en-cours',
            'paye': 'termine',
            'rejete': 'rejete',
        }
        
        # Formatage des dates
        try:
            date_depense_display = depense.date_depense.strftime('%d %b %Y')
        except:
            date_depense_display = depense.date_depense.strftime('%d/%m/%Y') if depense.date_depense else 'N/A'
        
        try:
            date_paiement_display = depense.date_paiement.strftime('%d %b %Y') if depense.date_paiement else None
        except:
            date_paiement_display = depense.date_paiement.strftime('%d/%m/%Y') if depense.date_paiement else None
        
        data = {
            'success': True,
            'depense': {
                'id': depense.id,
                'description': depense.description,
                'montant': str(depense.montant),
                'montant_formatted': depense.get_montant_formatted(),
                'categorie': depense.categorie,
                'categorie_display': depense.get_categorie_display(),
                'type_depense': depense.type_depense,
                'type_depense_label': depense.get_type_depense_display(),
                'type_depense_display': depense.get_type_depense_display(),
                'date_depense': depense.date_depense.strftime('%Y-%m-%d') if depense.date_depense else None,
                'date_depense_display': date_depense_display,
                'statut': depense.statut,
                'statut_display': depense.get_statut_display(),
                'statut_class': statut_classes.get(depense.statut, 'en-attente'),
                'fournisseur': depense.fournisseur,
                'numero_facture': depense.numero_facture or '',
                'methode_paiement': depense.methode_paiement,
                'methode_paiement_display': depense.get_methode_paiement_display(),
                'date_paiement': depense.date_paiement.strftime('%Y-%m-%d') if depense.date_paiement else None,
                'date_paiement_display': date_paiement_display,
                'notes': depense.notes or '',
                'piece_jointe': depense.piece_jointe.url if depense.piece_jointe else None,
                'etablissement_id': depense.etablissement.id if depense.etablissement else None,
                'etablissement_nom': depense.etablissement.nom if depense.etablissement else None,
                'etablissement': depense.etablissement is not None,
            }
        }
        
        return JsonResponse(data)
    except Depense.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Dépense introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@comptable_required
def depense_detail(request, depense_id):
    """
    Page de détail pour consulter et modifier une dépense
    """
    from datetime import datetime
    from django.utils import timezone
    
    depense = get_object_or_404(Depense, id=depense_id)
    
    # Autorisations basiques : seuls les utilisateurs administrateurs/comptables peuvent accéder à la page
    if hasattr(request.user, 'fonction') and request.user.fonction not in ['administrateur', 'comptable', 'administrateur_service_gestion_scolaire']:
        messages.error(request, "Vous n'avez pas les droits nécessaires pour accéder à cette page.")
        return redirect('school_admin:suivi_revenus')
    
    etablissements_list = Etablissement.objects.filter(actif=True).order_by('nom')
    categorie_choices = Depense.CATEGORIE_CHOICES
    statut_choices = Depense.STATUT_CHOICES
    methode_choices = Depense._meta.get_field('methode_paiement').choices
    
    if request.method == 'POST':
        description = request.POST.get('description', '').strip()
        montant = request.POST.get('montant', '').strip()
        categorie = request.POST.get('categorie', '').strip()
        date_depense = request.POST.get('date_depense', '').strip()
        fournisseur = request.POST.get('fournisseur', '').strip()
        numero_facture = request.POST.get('numero_facture', '').strip()
        methode_paiement = request.POST.get('methode_paiement', 'virement').strip()
        statut = request.POST.get('statut', depense.statut).strip()
        date_paiement = request.POST.get('date_paiement', '').strip()
        notes = request.POST.get('notes', '').strip()
        etablissement_id = request.POST.get('etablissement', '').strip()
        
        errors = []
        if not description:
            errors.append("La description est obligatoire.")
        if not montant:
            errors.append("Le montant est obligatoire.")
        if not categorie:
            errors.append("La catégorie est obligatoire.")
        if not date_depense:
            errors.append("La date de dépense est obligatoire.")
        if not fournisseur:
            errors.append("Le fournisseur est obligatoire.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                montant_decimal = Decimal(montant)
                if montant_decimal <= 0:
                    messages.error(request, "Le montant doit être supérieur à 0.")
                else:
                    try:
                        date_depense_obj = datetime.strptime(date_depense, '%Y-%m-%d').date()
                    except ValueError:
                        messages.error(request, "Le format de la date de dépense est invalide.")
                        return redirect('school_admin:depense_detail', depense_id=depense.id)
                    
                    date_paiement_obj = None
                    if statut == 'paye':
                        if date_paiement:
                            try:
                                date_paiement_obj = datetime.strptime(date_paiement, '%Y-%m-%d').date()
                            except ValueError:
                                messages.error(request, "Le format de la date de paiement est invalide.")
                                return redirect('school_admin:depense_detail', depense_id=depense.id)
                        else:
                            date_paiement_obj = timezone.now().date()
                    elif date_paiement:
                        try:
                            date_paiement_obj = datetime.strptime(date_paiement, '%Y-%m-%d').date()
                        except ValueError:
                            messages.error(request, "Le format de la date de paiement est invalide.")
                            return redirect('school_admin:depense_detail', depense_id=depense.id)
                    
                    etablissement = None
                    if etablissement_id:
                        try:
                            etablissement = Etablissement.objects.get(id=int(etablissement_id))
                        except (Etablissement.DoesNotExist, ValueError):
                            messages.warning(request, "Établissement introuvable, la dépense sera enregistrée sans établissement.")
                    
                    depense.description = description
                    depense.montant = montant_decimal
                    depense.categorie = categorie
                    depense.date_depense = date_depense_obj
                    depense.fournisseur = fournisseur
                    depense.numero_facture = numero_facture if numero_facture else None
                    depense.methode_paiement = methode_paiement
                    depense.statut = statut
                    depense.date_paiement = date_paiement_obj
                    depense.notes = notes if notes else None
                    depense.etablissement = etablissement
                    
                    if request.POST.get('supprimer_piece_jointe') == '1' and depense.piece_jointe:
                        depense.piece_jointe.delete(save=False)
                        depense.piece_jointe = None
                    
                    if 'piece_jointe' in request.FILES:
                        depense.piece_jointe = request.FILES['piece_jointe']
                    
                    depense.save()
                    messages.success(request, "La dépense a été mise à jour avec succès.")
                    return redirect('school_admin:depense_detail', depense_id=depense.id)
            except (ValueError, InvalidOperation):
                messages.error(request, "Le montant doit être un nombre valide.")
    
    # Statistiques additionnelles liées à la dépense
    depenses_fournisseur = Depense.objects.filter(fournisseur=depense.fournisseur).exclude(id=depense.id).order_by('-date_depense')[:5]
    total_depenses_fournisseur = Depense.objects.filter(fournisseur=depense.fournisseur).aggregate(total=Sum('montant'))['total'] or 0
    
    statut_classes = {
        'en_attente': 'status-badge en-attente',
        'approuve': 'status-badge en-cours',
        'paye': 'status-badge termine',
        'rejete': 'status-badge rejete',
    }
    
    timeline = []
    if depense.date_creation:
        creation_dt, creation_has_time = ensure_datetime(depense.date_creation)
        timeline.append({
            'label': "Création de la dépense",
            'date': creation_dt,
            'icon': 'fas fa-plus-circle',
            'show_time': creation_has_time,
        })
    if depense.date_depense:
        depense_dt, depense_has_time = ensure_datetime(depense.date_depense)
        timeline.append({
            'label': "Dépense effectuée",
            'date': depense_dt,
            'icon': 'fas fa-receipt',
            'show_time': depense_has_time,
        })
    if depense.date_paiement:
        paiement_dt, paiement_has_time = ensure_datetime(depense.date_paiement)
        timeline.append({
            'label': "Paiement enregistré",
            'date': paiement_dt,
            'icon': 'fas fa-check-circle',
            'show_time': paiement_has_time,
        })
    if depense.updated_at and (not depense.date_creation or depense.updated_at.date() != depense.date_creation.date()):
        update_dt, update_has_time = ensure_datetime(depense.updated_at)
        timeline.append({
            'label': "Dernière mise à jour",
            'date': update_dt,
            'icon': 'fas fa-edit',
            'show_time': update_has_time,
        })
    
    context = {
        'depense': depense,
        'etablissements_list': etablissements_list,
        'categorie_choices': categorie_choices,
        'statut_choices': statut_choices,
        'methode_choices': methode_choices,
        'type_depense_choices': Depense.TYPE_DEPENSE_CHOICES,
        'depenses_fournisseur': depenses_fournisseur,
        'total_depenses_fournisseur': total_depenses_fournisseur,
        'statut_class': statut_classes.get(depense.statut, 'status-badge en-attente'),
        'timeline': timeline,
    }
    
    return render(request, 'school_admin/gestion_comptable/depense_detail.html', context)

@comptable_required
def paiements_retard(request):
    """
    Vue pour le suivi des paiements en retard avec données dynamiques basées sur statut_reglementation
    """
    from datetime import datetime, timedelta
    from django.utils import timezone
    from django.db.models import Sum, Count, Q
    
    # Mettre à jour les statuts de réglementation de tous les établissements
    for etablissement in Etablissement.objects.filter(actif=True):
        etablissement.mettre_a_jour_statut_reglementation()
    
    # Récupérer les établissements en retard (basé sur statut_reglementation)
    etablissements_retard = Etablissement.objects.filter(
        actif=True,
        statut_reglementation='en_retard'
    )
    
    # Récupérer les établissements non en règle (pour les relances)
    etablissements_non_en_regle = Etablissement.objects.filter(
        actif=True,
        statut_reglementation='non_en_regle'
    )
    
    # Récupérer les établissements en contentieux
    etablissements_contentieux = Etablissement.objects.filter(
        actif=True,
        statut_reglementation='contentieux'
    )
    
    # Statistiques générales
    nombre_etablissements_retard = etablissements_retard.count()
    nombre_etablissements_impayes = etablissements_non_en_regle.count()
    nombre_etablissements_contentieux = etablissements_contentieux.count()
    
    # Calcul du montant total impayé (somme de tous les reste_a_payer des factures non payées)
    factures_actives = Facturation.objects.exclude(statut='annule')
    montant_total_impaye = factures_actives.aggregate(
        total=Sum('reste_a_payer')
    )['total'] or 0
    
    # Si reste_a_payer est None ou 0, utiliser montant_total des factures non payées
    if montant_total_impaye == 0:
        factures_non_payees = factures_actives.exclude(statut='paye')
        montant_total_impaye = factures_non_payees.aggregate(
            total=Sum('montant_total')
        )['total'] or 0
    
    # Calcul des jours de retard moyen (basé sur les factures avec reste_a_payer > 0)
    factures_avec_reste = factures_actives.filter(
        reste_a_payer__gt=0
    )
    
    total_jours_retard = 0
    nombre_factures_retard = 0
    
    for facture in factures_avec_reste:
        date_echeance = None
        if facture.date_echeance_reste:
            date_echeance = facture.date_echeance_reste
        elif facture.date_echeance:
            date_echeance = facture.date_echeance
        
        if date_echeance:
            jours_retard = max(0, (timezone.now().date() - date_echeance.date()).days)
            total_jours_retard += jours_retard
            nombre_factures_retard += 1
    
    jours_retard_moyen = 0
    if nombre_factures_retard > 0:
        jours_retard_moyen = round(total_jours_retard / nombre_factures_retard, 1)
    
    # Calcul du taux d'impayés
    montant_total_attendu = factures_actives.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    taux_impayes = 0
    if montant_total_attendu > 0:
        taux_impayes = round((montant_total_impaye / montant_total_attendu) * 100, 1)
    
    # Liste détaillée des établissements en retard
    etablissements_retard_detailed = []
    for etablissement in etablissements_retard:
        # Récupérer toutes les factures actives de cet établissement avec reste à payer
        factures_actives_etablissement = Facturation.objects.filter(
            etablissement=etablissement
        ).exclude(statut='annule')
        
        # Calculer le montant dû (somme de tous les reste_a_payer)
        montant_du = factures_actives_etablissement.aggregate(
            total=Sum('reste_a_payer')
        )['total'] or 0
        
        # Si reste_a_payer est None ou 0, utiliser montant_total des factures non payées
        if montant_du == 0:
            factures_non_payees = factures_actives_etablissement.exclude(statut='paye')
            montant_du = factures_non_payees.aggregate(
                total=Sum('montant_total')
            )['total'] or 0
        
        # Calculer les jours de retard (basé sur la facture la plus ancienne avec reste à payer)
        facture_plus_ancienne = factures_actives_etablissement.filter(
            reste_a_payer__gt=0
        ).order_by('date_echeance').first()
        
        jours_retard = 0
        date_echeance = None
        
        if facture_plus_ancienne:
            if facture_plus_ancienne.date_echeance_reste:
                date_echeance = facture_plus_ancienne.date_echeance_reste
                jours_retard = max(0, (timezone.now().date() - date_echeance.date()).days)
            elif facture_plus_ancienne.date_echeance:
                date_echeance = facture_plus_ancienne.date_echeance
                jours_retard = max(0, (timezone.now().date() - date_echeance.date()).days)
        
        # Déterminer le statut de relance basé sur statut_reglementation et jours de retard
        if etablissement.statut_reglementation == 'contentieux':
            statut_relance = 'contentieux'
            derniere_action = 'Contentieux en cours'
        elif etablissement.statut_reglementation == 'non_en_regle':
            statut_relance = 'mise_en_demeure'
            derniere_action = 'Mise en demeure'
        elif jours_retard > 15:
            statut_relance = 'relance_envoyee'
            derniere_action = 'Relance envoyée'
        else:
            statut_relance = 'en_retard'
            derniere_action = 'Facture en retard'
        
        etablissements_retard_detailed.append({
            'etablissement': etablissement,
            'montant_du': montant_du,
            'jours_retard': jours_retard,
            'statut_relance': statut_relance,
            'derniere_action': derniere_action,
            'date_echeance': date_echeance,
        })
    
    # Liste détaillée des établissements non en règle (pour l'onglet relances)
    relances_envoyees = []
    for etablissement in etablissements_non_en_regle:
        # Récupérer toutes les factures actives de cet établissement avec reste à payer
        factures_actives_etablissement = Facturation.objects.filter(
            etablissement=etablissement
        ).exclude(statut='annule')
        
        # Calculer les jours de retard
        facture_plus_ancienne = factures_actives_etablissement.filter(
            reste_a_payer__gt=0
        ).order_by('date_echeance').first()
        
        jours_retard = 0
        if facture_plus_ancienne:
            if facture_plus_ancienne.date_echeance_reste:
                jours_retard = max(0, (timezone.now().date() - facture_plus_ancienne.date_echeance_reste.date()).days)
            elif facture_plus_ancienne.date_echeance:
                jours_retard = max(0, (timezone.now().date() - facture_plus_ancienne.date_echeance.date()).days)
        
        # Déterminer le type de relance basé sur statut_reglementation et jours de retard
        if etablissement.statut_reglementation == 'non_en_regle' and jours_retard > 10:
            type_relance = 'Mise en demeure'
            statut = 'Envoyée'
            reponse = 'Aucune réponse'
        else:
            type_relance = 'Relance simple'
            statut = 'Envoyée'
            reponse = 'Aucune réponse'
        
        date_envoi = 'N/A'
        if facture_plus_ancienne:
            if facture_plus_ancienne.date_creation:
                date_envoi = facture_plus_ancienne.date_creation.strftime('%d %b %Y')
        
        relances_envoyees.append({
            'etablissement': etablissement,
            'type_relance': type_relance,
            'date_envoi': date_envoi,
            'statut': statut,
            'reponse': reponse,
        })
    
    # Liste détaillée des établissements en contentieux
    contentieux = []
    for etablissement in etablissements_contentieux:
        # Récupérer toutes les factures actives de cet établissement avec reste à payer
        factures_actives_etablissement = Facturation.objects.filter(
            etablissement=etablissement
        ).exclude(statut='annule')
        
        # Calculer le montant réclamé (somme de tous les reste_a_payer)
        montant_reclame = factures_actives_etablissement.aggregate(
            total=Sum('reste_a_payer')
        )['total'] or 0
        
        # Si reste_a_payer est None ou 0, utiliser montant_total des factures non payées
        if montant_reclame == 0:
            factures_non_payees = factures_actives_etablissement.exclude(statut='paye')
            montant_reclame = factures_non_payees.aggregate(
                total=Sum('montant_total')
            )['total'] or 0
        
        # Calculer les jours de retard
        facture_plus_ancienne = factures_actives_etablissement.filter(
            reste_a_payer__gt=0
        ).order_by('date_echeance').first()
        
        jours_retard = 0
        if facture_plus_ancienne:
            if facture_plus_ancienne.date_echeance_reste:
                jours_retard = max(0, (timezone.now().date() - facture_plus_ancienne.date_echeance_reste.date()).days)
            elif facture_plus_ancienne.date_echeance:
                jours_retard = max(0, (timezone.now().date() - facture_plus_ancienne.date_echeance.date()).days)
        
        # Simuler des dates d'assignation et d'audience (basé sur les jours de retard)
        if jours_retard > 30:
            date_assignation = (timezone.now() - timedelta(days=jours_retard-30)).strftime('%d %b %Y')
        else:
            date_assignation = (timezone.now() - timedelta(days=30)).strftime('%d %b %Y')
        
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


@comptable_required
def calculs_automatiques(request):
    # Vue pour les calculs automatiques
    return render(request, 'school_admin/gestion_comptable/calculs_automatiques.html')


@comptable_required
def rapports_mensuels(request):
    """
    Vue pour la gestion des rapports mensuels avec données dynamiques
    """
    from django.db.models import Sum, Count, Q, Avg
    from django.utils import timezone
    from datetime import datetime, timedelta
    from ..model.rapport_mensuel_model import RapportMensuel
    from ..model.facturation_model import Facturation
    from ..model.etablissement_model import Etablissement
    from ..model.eleve_model import Eleve
    from django.contrib import messages
    import json
    
    # Traitement des formulaires
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'generer_rapport':
            # Génération d'un nouveau rapport
            try:
                mois = int(request.POST.get('mois'))
                annee = int(request.POST.get('annee'))
                type_rapport = request.POST.get('type_rapport', 'complet')
                
                # Vérifier si un rapport existe déjà pour cette période
                rapport_existant = RapportMensuel.objects.filter(
                    mois=mois,
                    annee=annee,
                    type_rapport=type_rapport
                ).first()
                
                if rapport_existant:
                    messages.warning(request, f"Un rapport {rapport_existant.get_type_rapport_display()} existe déjà pour {rapport_existant.get_periode_display()}.")
                else:
                    # Créer le nouveau rapport
                    nom = f"Rapport {RapportMensuel(mois=mois, annee=annee).get_mois_display()} {annee}"
                    if type_rapport != 'complet':
                        nom += f" - {dict(RapportMensuel.TYPE_RAPPORT_CHOICES)[type_rapport]}"
                    
                    # Calculer les dates de début et fin du mois
                    date_debut = datetime(annee, mois, 1).date()
                    if mois == 12:
                        date_fin = datetime(annee + 1, 1, 1).date() - timedelta(days=1)
                    else:
                        date_fin = datetime(annee, mois + 1, 1).date() - timedelta(days=1)
                    
                    # Récupérer les sections à inclure
                    inclure_resume_executif = request.POST.get('inclure_resume_executif') == 'on'
                    inclure_donnees_financieres = request.POST.get('inclure_donnees_financieres') == 'on'
                    inclure_analyse_etablissements = request.POST.get('inclure_analyse_etablissements') == 'on'
                    inclure_graphiques = request.POST.get('inclure_graphiques') == 'on'
                    inclure_recommandations = request.POST.get('inclure_recommandations') == 'on'
                    
                    # Calculer les données du rapport
                    debut_traitement = timezone.now()
                    
                    # Statistiques financières
                    factures_mois = Facturation.objects.filter(
                        date_creation__year=annee,
                        date_creation__month=mois
                    ).exclude(statut='annule')
                    
                    montant_total_facture = factures_mois.aggregate(
                        total=Sum('montant_total')
                    )['total'] or 0
                    
                    montant_total_paye = factures_mois.filter(statut='paye').aggregate(
                        total=Sum('montant_verse')
                    )['total'] or 0
                    
                    montant_total_impaye = factures_mois.exclude(statut='paye').aggregate(
                        total=Sum('reste_a_payer')
                    )['total'] or 0
                    
                    # Statistiques des établissements
                    nombre_etablissements_actifs = Etablissement.objects.filter(actif=True).count()
                    nombre_etablissements_nouveaux = Etablissement.objects.filter(
                        date_creation__year=annee,
                        date_creation__month=mois
                    ).count()
                    
                    # Statistiques des élèves
                    nombre_eleves_actifs = Eleve.objects.filter(actif=True).count()
                    nombre_eleves_nouveaux = Eleve.objects.filter(
                        date_inscription__year=annee,
                        date_inscription__month=mois
                    ).count()
                    
                    # Taux de paiement
                    taux_paiement = 0
                    if montant_total_facture > 0:
                        taux_paiement = round((montant_total_paye / montant_total_facture) * 100, 2)
                    
                    # Calculer le temps de génération
                    temps_generation = (timezone.now() - debut_traitement).total_seconds()
                    
                    # Préparer les données du rapport
                    donnees_rapport = {
                        'statistiques_financieres': {
                            'montant_total_facture': float(montant_total_facture),
                            'montant_total_paye': float(montant_total_paye),
                            'montant_total_impaye': float(montant_total_impaye),
                            'taux_paiement': taux_paiement,
                            'nombre_factures': factures_mois.count(),
                        },
                        'statistiques_etablissements': {
                            'nombre_actifs': nombre_etablissements_actifs,
                            'nombre_nouveaux': nombre_etablissements_nouveaux,
                        },
                        'statistiques_eleves': {
                            'nombre_actifs': nombre_eleves_actifs,
                            'nombre_nouveaux': nombre_eleves_nouveaux,
                        },
                    }
                    
                    # Créer le rapport
                    rapport = RapportMensuel.objects.create(
                        nom=nom,
                        type_rapport=type_rapport,
                        mois=mois,
                        annee=annee,
                        date_debut=date_debut,
                        date_fin=date_fin,
                        statut='genere',
                        inclure_resume_executif=inclure_resume_executif,
                        inclure_donnees_financieres=inclure_donnees_financieres,
                        inclure_analyse_etablissements=inclure_analyse_etablissements,
                        inclure_graphiques=inclure_graphiques,
                        inclure_recommandations=inclure_recommandations,
                        donnees_rapport=donnees_rapport,
                        date_generation=timezone.now(),
                        temps_generation=temps_generation,
                    )
                    
                    messages.success(request, f"Rapport généré avec succès pour {rapport.get_periode_display()}.")
                    
            except Exception as e:
                messages.error(request, f"Erreur lors de la génération du rapport : {str(e)}")
        
        elif action == 'supprimer_rapport':
            rapport_id = request.POST.get('rapport_id')
            try:
                rapport = RapportMensuel.objects.get(id=rapport_id)
                rapport.delete()
                messages.success(request, "Rapport supprimé avec succès.")
            except RapportMensuel.DoesNotExist:
                messages.error(request, "Rapport introuvable.")
    
    # Récupérer tous les rapports
    rapports = RapportMensuel.objects.all().order_by('-annee', '-mois', '-date_creation')
    
    # Statistiques générales
    nombre_rapports = rapports.count()
    rapports_generees = rapports.filter(statut='genere').count()
    
    # Calculer la croissance mensuelle (comparaison avec le mois précédent)
    maintenant = timezone.now()
    mois_actuel = maintenant.month
    annee_actuelle = maintenant.year
    
    # Revenus du mois actuel
    factures_mois_actuel = Facturation.objects.filter(
        date_creation__year=annee_actuelle,
        date_creation__month=mois_actuel
    ).exclude(statut='annule')
    
    revenus_mois_actuel = factures_mois_actuel.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Revenus du mois précédent
    if mois_actuel == 1:
        mois_precedent = 12
        annee_precedente = annee_actuelle - 1
    else:
        mois_precedent = mois_actuel - 1
        annee_precedente = annee_actuelle
    
    factures_mois_precedent = Facturation.objects.filter(
        date_creation__year=annee_precedente,
        date_creation__month=mois_precedent
    ).exclude(statut='annule')
    
    revenus_mois_precedent = factures_mois_precedent.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Calculer la croissance
    croissance_mensuelle = 0
    if revenus_mois_precedent > 0:
        croissance_mensuelle = round(((revenus_mois_actuel - revenus_mois_precedent) / revenus_mois_precedent) * 100, 1)
    
    # Revenus totaux (toutes les factures)
    revenus_totaux = Facturation.objects.exclude(statut='annule').aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Temps de génération moyen
    temps_generation_moyen = rapports.filter(
        temps_generation__isnull=False
    ).aggregate(
        moyen=Avg('temps_generation')
    )['moyen'] or 0
    
    # Préparer les options de mois pour le formulaire
    mois_options = []
    for i in range(12, 0, -1):
        mois_nom = RapportMensuel(mois=i, annee=annee_actuelle).get_mois_display()
        mois_options.append({
            'value': i,
            'label': f"{mois_nom} {annee_actuelle}"
        })
    
    # Rapports par type
    rapports_complets = rapports.filter(type_rapport='complet').count()
    rapports_resumes = rapports.filter(type_rapport='resume').count()
    rapports_financiers = rapports.filter(type_rapport='financier').count()
    rapports_operationnels = rapports.filter(type_rapport='operational').count()
    
    context = {
        'rapports': rapports,
        'nombre_rapports': nombre_rapports,
        'rapports_generees': rapports_generees,
        'croissance_mensuelle': croissance_mensuelle,
        'revenus_totaux': revenus_totaux,
        'temps_generation_moyen': round(temps_generation_moyen, 1) if temps_generation_moyen else 0,
        'mois_options': mois_options,
        'annee_actuelle': annee_actuelle,
        'rapports_complets': rapports_complets,
        'rapports_resumes': rapports_resumes,
        'rapports_financiers': rapports_financiers,
        'rapports_operationnels': rapports_operationnels,
    }
    
    return render(request, 'school_admin/gestion_comptable/rapports_mensuels.html', context)


@comptable_required
def rapports_annuels(request):
    # Vue pour les rapports annuels (bilan annuel)
    return render(request, 'school_admin/gestion_comptable/rapports_annuels.html')


@comptable_required
def gestion_etablissements(request):
    """
    Vue pour la gestion des établissements avec données dynamiques
    """
    from django.db.models import Sum, Count, Q
    from datetime import datetime, timedelta
    from django.utils import timezone
    
    # Statistiques générales
    total_etablissements = Etablissement.objects.filter(actif=True).count()
    
    # Mettre à jour les statuts de réglementation de tous les établissements
    for etablissement in Etablissement.objects.filter(actif=True):
        etablissement.mettre_a_jour_statut_reglementation()
    
    # Établissements en règle (basé sur statut_reglementation)
    # Un établissement est en règle si son statut_reglementation est 'en_regle'
    etablissements_en_regle = Etablissement.objects.filter(
        actif=True,
        statut_reglementation='en_regle'
    )
    nombre_en_regle = etablissements_en_regle.count()
    
    # Établissements non en règle (statut_reglementation différent de 'en_regle')
    etablissements_non_en_regle = Etablissement.objects.filter(
        actif=True
    ).exclude(statut_reglementation='en_regle')
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
        
        # Montant total : somme de toutes les factures (non annulées)
        factures_actives = Facturation.objects.filter(
            etablissement=etablissement
        ).exclude(statut='annule')
        montant_total = factures_actives.aggregate(
            total=Sum('montant_total')
        )['total'] or 0
        
        # Statut basé sur statut_reglementation
        statut_display = etablissement.get_statut_reglementation_display()
        
        # Dernier paiement (dernière facture payée avec date_paiement)
        dernier_paiement = Facturation.objects.filter(
            etablissement=etablissement, 
            statut='paye',
            date_paiement__isnull=False
        ).order_by('-date_paiement').first()
        
        date_dernier_paiement = dernier_paiement.date_paiement if dernier_paiement else None
        
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
        
        # Calculer le montant dû (somme de tous les reste_a_payer de toutes les factures)
        # Cela inclut les factures partiellement payées
        factures_actives = Facturation.objects.filter(
            etablissement=etablissement
        ).exclude(statut='annule')
        
        montant_du = factures_actives.aggregate(
            total=Sum('reste_a_payer')
        )['total'] or 0
        
        # Si reste_a_payer est None ou 0 pour toutes les factures, vérifier les factures non payées
        if montant_du == 0:
            factures_non_payees = factures_actives.exclude(statut='paye')
            montant_du = factures_non_payees.aggregate(
                total=Sum('montant_total')
            )['total'] or 0
        
        # Calculer les jours de retard (basé sur la facture la plus ancienne avec reste à payer)
        facture_plus_ancienne = factures_actives.filter(
            reste_a_payer__gt=0
        ).order_by('date_echeance').first()
        
        jours_retard = 0
        if facture_plus_ancienne:
            if facture_plus_ancienne.date_echeance_reste:
                # Priorité à la date d'échéance du reste à payer
                jours_retard = max(0, (timezone.now().date() - facture_plus_ancienne.date_echeance_reste.date()).days)
            elif facture_plus_ancienne.date_echeance:
                # Sinon utiliser la date d'échéance principale
                jours_retard = max(0, (timezone.now().date() - facture_plus_ancienne.date_echeance.date()).days)
        
        etablissements_non_en_regle_detailed.append({
            'etablissement': etablissement,
            'nombre_eleves': nombre_eleves,
            'montant_du': montant_du,
            'jours_retard': jours_retard,
        })
    
    # Factures avec détails basées sur le modèle Facturation
    factures_detailed = []
    for facture in Facturation.objects.select_related('etablissement').order_by('-date_creation'):
        # Montant payé : utiliser directement montant_verse de la base de données
        montant_paye = facture.montant_verse if facture.montant_verse else 0
        
        # Montant restant : utiliser directement reste_a_payer de la base de données
        # Si reste_a_payer est None ou 0 et que la facture n'est pas payée, utiliser montant_total
        if facture.reste_a_payer is not None and facture.reste_a_payer > 0:
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


@comptable_required
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
    
    # Mettre à jour automatiquement le statut de réglementation
    etablissement.mettre_a_jour_statut_reglementation()
    
    # Détecter les périodes sans facture
    # Une période est considérée comme facturée si :
    # 1. Le champ periode_facture correspond exactement
    # 2. OU la date d'échéance correspond au même mois/année
    periodes_sans_facture = []
    date_creation_etablissement = etablissement.date_creation.date()
    aujourdhui = timezone.now().date()
    
    # Récupérer toutes les factures de service (mensuel/annuel) existantes
    # Exclure les factures annulées car elles ne comptent pas comme facturées
    factures_existantes = Facturation.objects.filter(
        etablissement=etablissement,
        type_facture__in=['frais_service_mensuel', 'frais_service_annuel']
    ).exclude(statut='annule').order_by('date_echeance')
    
    if etablissement.type_facturation == 'mensuel':
        # Pour facturation mensuelle : détecter les mois sans facture
        mois_fr = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        
        # Créer un set des périodes déjà facturées (par periode_facture)
        # On normalise les chaînes pour éviter les problèmes d'espaces ou de casse
        periodes_facturees_par_champ = set()
        for facture in factures_existantes:
            if facture.periode_facture:
                # Normaliser la chaîne (supprimer les espaces multiples, trim, etc.)
                periode_normalisee = ' '.join(str(facture.periode_facture).strip().split())
                periodes_facturees_par_champ.add(periode_normalisee)
        
        # Créer un set des périodes facturées par date d'échéance
        # Format: (année, mois) pour comparaison
        # On vérifie uniquement les factures mensuelles pour éviter les faux positifs
        periodes_facturees_par_date = set()
        for facture in factures_existantes:
            if facture.date_echeance and facture.type_facture == 'frais_service_mensuel':
                date_echeance = facture.date_echeance.date()
                periodes_facturees_par_date.add((date_echeance.year, date_echeance.month))
        
        # Parcourir tous les mois depuis la création de l'établissement jusqu'à aujourd'hui
        # Exclure les périodes déjà facturées
        date_courante = date_creation_etablissement.replace(day=1)
        while date_courante <= aujourdhui:
            periode_str = f"{mois_fr[date_courante.month]} {date_courante.year}"
            periode_normalisee = ' '.join(periode_str.split())
            
            # Vérifier si cette période a déjà été facturée
            # Vérification 1 : Par le champ periode_facture (méthode principale)
            deja_facturee_par_champ = periode_normalisee in periodes_facturees_par_champ
            
            # Vérification 2 : Par la date d'échéance (fallback)
            deja_facturee_par_date = (date_courante.year, date_courante.month) in periodes_facturees_par_date
            
            # Vérification 3 : Vérification directe en base de données pour être absolument sûr
            # Cette vérification supplémentaire garantit qu'on ne rate aucune facture
            deja_facturee_directe = Facturation.objects.filter(
                etablissement=etablissement,
                type_facture='frais_service_mensuel',
                periode_facture__icontains=periode_str
            ).exclude(statut='annule').exists()
            
            # Si la période est déjà facturée (par n'importe quelle méthode), on l'exclut de la liste
            if deja_facturee_par_champ or deja_facturee_par_date or deja_facturee_directe:
                # Période déjà facturée, on passe au mois suivant
                pass
            else:
                # Période non facturée, on l'ajoute à la liste
                periodes_sans_facture.append({
                    'valeur': f"{date_courante.year}-{date_courante.month:02d}",
                    'label': periode_str,
                    'type': 'mois'
                })
            
            # Passer au mois suivant
            if date_courante.month == 12:
                date_courante = date_courante.replace(year=date_courante.year + 1, month=1)
            else:
                date_courante = date_courante.replace(month=date_courante.month + 1)
    
    elif etablissement.type_facturation == 'annuel':
        # Pour facturation annuelle : détecter les années sans facture
        # Créer un set des périodes déjà facturées (par periode_facture)
        # On normalise les chaînes pour éviter les problèmes d'espaces ou de casse
        periodes_facturees_par_champ = set()
        for facture in factures_existantes:
            if facture.periode_facture:
                # Normaliser la chaîne (trim, etc.)
                periode_normalisee = str(facture.periode_facture).strip()
                periodes_facturees_par_champ.add(periode_normalisee)
        
        # Créer un set des années facturées par date d'échéance
        # On vérifie uniquement les factures annuelles pour éviter les faux positifs
        annees_facturees_par_date = set()
        for facture in factures_existantes:
            if facture.date_echeance and facture.type_facture == 'frais_service_annuel':
                date_echeance = facture.date_echeance.date()
                annees_facturees_par_date.add(date_echeance.year)
        
        # Parcourir toutes les années depuis la création de l'établissement jusqu'à aujourd'hui
        # Exclure les années déjà facturées
        annee_courante = date_creation_etablissement.year
        annee_actuelle = aujourdhui.year
        
        while annee_courante <= annee_actuelle:
            annee_str = str(annee_courante)
            
            # Vérifier si cette année a déjà été facturée
            # Vérification 1 : Par le champ periode_facture (méthode principale)
            deja_facturee_par_champ = annee_str in periodes_facturees_par_champ
            
            # Vérification 2 : Par la date d'échéance (fallback)
            deja_facturee_par_date = annee_courante in annees_facturees_par_date
            
            # Vérification 3 : Vérification directe en base de données pour être absolument sûr
            deja_facturee_directe = Facturation.objects.filter(
                etablissement=etablissement,
                type_facture='frais_service_annuel',
                periode_facture__icontains=annee_str
            ).exclude(statut='annule').exists()
            
            # Si l'année est déjà facturée (par n'importe quelle méthode), on l'exclut de la liste
            if deja_facturee_par_champ or deja_facturee_par_date or deja_facturee_directe:
                # Année déjà facturée, on passe à l'année suivante
                pass
            else:
                # Année non facturée, on l'ajoute à la liste
                periodes_sans_facture.append({
                    'valeur': annee_str,
                    'label': annee_str,
                    'type': 'annee'
                })
            annee_courante += 1
    
    # Traitement du formulaire de facturation
    if request.method == 'POST' and 'create_invoice' in request.POST:
        try:
            # Récupérer les données du formulaire
            type_facture = request.POST.get('type_facture')
            description = request.POST.get('description', '')
            date_echeance_str = request.POST.get('date_echeance')
            periode_selectionnee = request.POST.get('periode_selectionnee', '')  # Format: "YYYY-MM" pour mois, "YYYY" pour année
            montant_module_supplementaire = request.POST.get('montant_module_supplementaire', '')
            modules_selectionnes = request.POST.getlist('modules_selectionnes')
            
            # Convertir la date d'échéance
            date_echeance = datetime.strptime(date_echeance_str, '%Y-%m-%d')
            date_echeance = timezone.make_aware(date_echeance)
            
            # Calculer automatiquement la période de facturation
            periode_facture = None
            date_reference_periode = date_echeance  # Par défaut, utiliser la date d'échéance
            
            # Si une période spécifique est sélectionnée, l'utiliser
            if periode_selectionnee:
                if type_facture == 'frais_service_mensuel':
                    # Format: "YYYY-MM"
                    annee, mois = map(int, periode_selectionnee.split('-'))
                    date_reference_periode = datetime(annee, mois, 1)
                    date_reference_periode = timezone.make_aware(date_reference_periode)
                    mois_fr = {
                        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
                        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
                        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
                    }
                    periode_facture = f"{mois_fr[mois]} {annee}"
                elif type_facture == 'frais_service_annuel':
                    # Format: "YYYY"
                    annee = int(periode_selectionnee)
                    date_reference_periode = datetime(annee, 1, 1)
                    date_reference_periode = timezone.make_aware(date_reference_periode)
                    periode_facture = str(annee)
            else:
                # Calculer automatiquement selon la date d'échéance
                if type_facture == 'frais_service_mensuel':
                    mois_fr = {
                        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
                        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
                        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
                    }
                    periode_facture = f"{mois_fr[date_echeance.month]} {date_echeance.year}"
                elif type_facture == 'frais_service_annuel':
                    periode_facture = str(date_echeance.year)
            
            # Calculer le nombre d'élèves actifs pour la période sélectionnée
            # LOGIQUE CUMULATIVE (Option A) :
            # La facture d'un mois donné compte TOUS les élèves actifs qui étaient inscrits
            # jusqu'à la fin de ce mois (facturation cumulative).
            # 
            # Exemple :
            # - Septembre : 40 élèves inscrits → facture pour 40 élèves
            # - Octobre : 50 élèves inscrits (40 + 10 nouveaux) → facture pour 50 élèves
            # - Novembre : 60 élèves inscrits (50 + 10 nouveaux) → facture pour 60 élèves
            #
            # Pour une facture de rattrapage d'une période passée :
            # - On compte tous les élèves ACTIFS maintenant qui ont été créés avant ou pendant cette période
            # - On ne peut pas savoir rétrospectivement si un élève était actif à une date donnée,
            #   donc on utilise l'approximation : élève actif maintenant + créé avant/pendant période
            #   = probablement actif pendant cette période
            
            if periode_selectionnee:
                # Facture de rattrapage pour une période passée
                if type_facture == 'frais_service_mensuel':
                    # Pour un mois spécifique : compter les élèves ACTIFS créés avant ou pendant ce mois
                    # Calculer la fin du mois sélectionné (dernier jour du mois à 23:59:59)
                    if date_reference_periode.month == 12:
                        fin_mois = datetime(date_reference_periode.year + 1, 1, 1) - timedelta(days=1)
                    else:
                        fin_mois = datetime(date_reference_periode.year, date_reference_periode.month + 1, 1) - timedelta(days=1)
                    fin_mois = timezone.make_aware(datetime(fin_mois.year, fin_mois.month, fin_mois.day, 23, 59, 59))
                    
                    # Facturation cumulative : compter tous les élèves actifs maintenant
                    # qui ont été créés avant ou pendant ce mois
                    # Cela représente l'effectif actif à la fin de ce mois
                    quantite = Eleve.objects.filter(
                        etablissement=etablissement,
                        actif=True,  # Seulement les élèves actifs maintenant
                        date_creation__lte=fin_mois  # Créés avant ou pendant ce mois
                    ).count()
                    
                elif type_facture == 'frais_service_annuel':
                    # Pour une année spécifique : compter les élèves ACTIFS créés avant ou pendant cette année
                    fin_annee = datetime(date_reference_periode.year, 12, 31, 23, 59, 59)
                    fin_annee = timezone.make_aware(fin_annee)
                    
                    # Facturation cumulative : compter tous les élèves actifs maintenant
                    # qui ont été créés avant ou pendant cette année
                    quantite = Eleve.objects.filter(
                        etablissement=etablissement,
                        actif=True,  # Seulement les élèves actifs maintenant
                        date_creation__lte=fin_annee  # Créés avant ou pendant cette année
                    ).count()
                else:
                    # Pour les autres types de factures, utiliser le nombre d'élèves actifs actuel
                    quantite = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
            else:
                # Facture pour la période actuelle : compter uniquement les élèves actifs maintenant
                # (facturation cumulative : tous les élèves actifs à ce jour)
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
                periode_facture=periode_facture,
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
            
            # Mettre à jour automatiquement le statut de réglementation de l'établissement
            etablissement.mettre_a_jour_statut_reglementation()
            
            # Message de succès avec détails
            if type_facture == 'module_supplementaire' and modules_selectionnes:
                modules_display = facture.get_modules_supplementaires_display()
                messages.success(request, f"Facture {facture.numero_facture} créée avec succès pour {etablissement.nom} ! Montant: {facture.montant_total} FCFA - Modules: {modules_display}")
            else:
                periode_msg = f" - Période: {periode_facture}" if periode_facture else ""
                messages.success(request, f"Facture {facture.numero_facture} créée avec succès pour {etablissement.nom} ! Montant: {facture.montant_total} FCFA{periode_msg} - {quantite} élève(s) facturé(s)")
            
        except Exception as e:
            messages.error(request, f"Erreur lors de la création de la facture : {str(e)}")
        
        # Rediriger vers la même page pour éviter la double soumission
        return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
    
    
    # Statistiques de base de l'établissement
    nombre_eleves = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
    
    # Calculs financiers basés sur TOUTES les factures de l'établissement
    # Exclure les factures annulées car elles ne comptent pas dans les statistiques
    factures_actives = Facturation.objects.filter(
        etablissement=etablissement
    ).exclude(statut='annule')
    
    # Montant total : somme de tous les montant_total de toutes les factures
    montant_total_facture = factures_actives.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    # Montant payé : somme de tous les montant_verse de toutes les factures
    # Cela prend en compte les paiements partiels
    montant_paye = factures_actives.aggregate(
        total=Sum('montant_verse')
    )['total'] or 0
    
    # Reste à payer : somme de tous les reste_a_payer de toutes les factures
    # Cela donne le montant global restant à payer pour toutes les factures
    montant_restant = factures_actives.aggregate(
        total=Sum('reste_a_payer')
    )['total'] or 0
    
    # Taux de paiement : pourcentage basé sur le montant total des factures
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
    
    # Historique des paiements (toutes les factures payées ou partiellement payées)
    historique_paiements = []
    maintenant = timezone.now()
    for facture in Facturation.objects.filter(
        etablissement=etablissement,
        statut='paye'
    ).order_by('-date_paiement'):
        # Calculer le statut de réglementation basé sur la date d'échéance du reste
        statut_reglementation = 'en_regle'
        if facture.paiement_partiel and facture.date_echeance_reste and facture.reste_a_payer > 0:
            if facture.date_echeance_reste < maintenant:
                jours_retard = (maintenant - facture.date_echeance_reste).days
                if jours_retard > 30:
                    statut_reglementation = 'contentieux'
                elif jours_retard > 10:
                    statut_reglementation = 'non_en_regle'
                else:
                    statut_reglementation = 'en_retard'
        
        historique_paiements.append({
            'numero_facture': facture.numero_facture,
            'date_paiement': facture.date_paiement,
            'date_creation': facture.date_creation,
            'type_paiement': facture.get_type_facture_display_detailed(),
            'montant_facture': facture.montant_total,
            'montant_verse': facture.montant_verse if facture.montant_verse else (facture.montant_total - facture.reste_a_payer),
            'reste_a_payer': facture.reste_a_payer,
            'paiement_partiel': facture.paiement_partiel,
            'date_echeance_reste': facture.date_echeance_reste,
            'methode': facture.mode_paiement or 'Non spécifié',
            'reference': facture.reference_paiement or 'N/A',
            'statut': 'Payé',
            'statut_detaille': 'Paiement complet' if not facture.paiement_partiel else 'Paiement partiel',
            'statut_reglementation': statut_reglementation,
        })
    
    # Factures avec détails
    # Exclure les factures complètement payées de la liste (ou les marquer différemment)
    factures_detailed = []
    for facture in Facturation.objects.filter(etablissement=etablissement).order_by('-date_creation'):
        # Ne pas exclure les factures payées, mais les marquer comme telles
        # pour permettre de voir l'historique complet
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
            # IMPORTANT : Récupérer directement les colonnes brutes depuis la DB
            # - reste_a_payer : colonne reste_a_payer (déjà calculée dans le modèle)
            # - montant_verse : colonne montant_verse (montant total déjà versé)
            # Le modèle initialise automatiquement reste_a_payer = montant_total pour les nouvelles factures
            'reste_a_payer': facture.reste_a_payer if facture.reste_a_payer else (facture.montant_total if facture.statut != 'paye' else Decimal('0.00')),
            'montant_verse': facture.montant_verse if facture.montant_verse else Decimal('0.00'),
            'est_paiement_complet': facture.est_paiement_complet(),
            'est_paiement_partiel': facture.est_paiement_partiel(),
            'paiement_partiel': facture.paiement_partiel,
            'date_echeance_reste': facture.date_echeance_reste,
            'date_paiement': facture.date_paiement,
            'mode_paiement': facture.mode_paiement,
            'reference_paiement': facture.reference_paiement,
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
    
    # Résumé financier (basé sur toutes les factures, pas seulement les payées)
    factures_toutes = Facturation.objects.filter(
        etablissement=etablissement
    ).exclude(statut='annule')
    
    total_facture_historique = factures_toutes.aggregate(
        total=Sum('montant_total')
    )['total'] or 0
    
    total_paye_historique = factures_toutes.aggregate(
        total=Sum('montant_verse')
    )['total'] or 0
    
    en_attente_historique = factures_toutes.aggregate(
        total=Sum('reste_a_payer')
    )['total'] or 0
    
    taux_recouvrement = 0
    if total_facture_historique > 0:
        taux_recouvrement = round((total_paye_historique / total_facture_historique) * 100, 1)
    
    # Statistiques mensuelles pour les graphiques (6 derniers mois)
    from datetime import datetime, timedelta
    from django.utils import timezone
    from collections import defaultdict
    
    evolution_paiements = []
    evolution_factures = []
    labels_mois = []
    
    aujourdhui = timezone.now().date()
    for i in range(5, -1, -1):  # 6 derniers mois
        date_mois = aujourdhui - timedelta(days=30 * i)
        mois_debut = date_mois.replace(day=1)
        if date_mois.month == 12:
            mois_fin = date_mois.replace(year=date_mois.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            mois_fin = date_mois.replace(month=date_mois.month + 1, day=1) - timedelta(days=1)
        
        # Factures créées ce mois
        factures_mois = factures_toutes.filter(
            date_creation__date__gte=mois_debut,
            date_creation__date__lte=mois_fin
        )
        montant_factures_mois = factures_mois.aggregate(
            total=Sum('montant_total')
        )['total'] or 0
        
        # Paiements effectués ce mois
        paiements_mois = factures_toutes.filter(
            date_paiement__date__gte=mois_debut,
            date_paiement__date__lte=mois_fin
        )
        montant_paiements_mois = paiements_mois.aggregate(
            total=Sum('montant_verse')
        )['total'] or 0
        
        mois_nom = date_mois.strftime('%b %Y')
        labels_mois.append(mois_nom)
        evolution_factures.append(float(montant_factures_mois))
        evolution_paiements.append(float(montant_paiements_mois))
    
    # Statistiques par statut
    factures_par_statut = {
        'paye': factures_toutes.filter(statut='paye').count(),
        'en_attente': factures_toutes.filter(statut='en_attente').count(),
        'en_retard': factures_toutes.filter(statut='en_retard').count(),
        'impaye': factures_toutes.filter(statut='impaye').count(),
    }
    
    # Montants par statut
    montants_par_statut = {
        'paye': factures_toutes.filter(statut='paye').aggregate(
            total=Sum('montant_total')
        )['total'] or 0,
        'en_attente': factures_toutes.filter(statut='en_attente').aggregate(
            total=Sum('montant_total')
        )['total'] or 0,
        'en_retard': factures_toutes.filter(statut='en_retard').aggregate(
            total=Sum('montant_total')
        )['total'] or 0,
        'impaye': factures_toutes.filter(statut='impaye').aggregate(
            total=Sum('montant_total')
        )['total'] or 0,
    }
    
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
        'evolution_paiements': evolution_paiements,
        'evolution_factures': evolution_factures,
        'labels_mois': labels_mois,
        'factures_par_statut': factures_par_statut,
        'montants_par_statut': montants_par_statut,
        'evolution_paiements_json': json.dumps(evolution_paiements),
        'evolution_factures_json': json.dumps(evolution_factures),
        'labels_mois_json': json.dumps(labels_mois),
        'factures_par_statut_json': json.dumps(factures_par_statut),
        'methodes_stats_json': json.dumps(methodes_stats),
        'documents': documents,
        'modules_non_actives': modules_non_actives,
        'periodes_sans_facture': periodes_sans_facture,
    }
    
    return render(request, 'school_admin/gestion_comptable/details_financiers_etablissement.html', context)


@comptable_required
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
            
            # IMPORTANT : Utiliser directement la colonne reste_a_payer de la base de données
            # Le reste_a_payer représente déjà ce qui reste après tous les paiements précédents
            montant_deja_paye = facture.montant_verse if facture.montant_verse else Decimal('0.00')
            
            # Calculer le reste à payer actuel
            # Si reste_a_payer est None ou 0 mais qu'aucun paiement n'a été fait, 
            # alors reste_a_payer = montant_total
            if facture.reste_a_payer is None or facture.reste_a_payer == 0:
                if montant_deja_paye == 0:
                    # Aucun paiement n'a été fait, le reste = montant total
                    reste_a_payer_actuel = facture.montant_total
                else:
                    # Il y a eu un paiement mais reste_a_payer n'est pas initialisé, le calculer
                    reste_a_payer_actuel = facture.montant_total - montant_deja_paye
            else:
                # Utiliser directement la valeur de la colonne DB
                reste_a_payer_actuel = facture.reste_a_payer
            
            # Vérifier si la facture est déjà complètement payée
            # Une facture est complètement payée si reste_a_payer == 0 ET montant_verse >= montant_total
            if reste_a_payer_actuel == Decimal('0.00') and montant_deja_paye >= facture.montant_total:
                messages.warning(request, f"La facture {facture_numero} est déjà complètement payée")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            # Vérifier que le montant versé ne dépasse pas le reste à payer actuel (colonne reste_a_payer)
            if montant_verse > reste_a_payer_actuel:
                messages.error(request, f"Le montant versé ({montant_verse} FCFA) ne peut pas être supérieur au reste à payer ({reste_a_payer_actuel} FCFA)")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            # Si c'est un paiement partiel, vérifier qu'une date d'échéance est fournie
            nouveau_montant_verse = montant_deja_paye + montant_verse
            if nouveau_montant_verse < facture.montant_total:
                if not date_echeance_reste_str:
                    messages.error(request, "Une date d'échéance pour le reste à payer est requise pour les paiements partiels")
                return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
            
            # Traitement du paiement
            if date_echeance_reste_str:
                from datetime import datetime
                date_echeance_reste = datetime.strptime(date_echeance_reste_str, '%Y-%m-%d')
                date_echeance_reste = timezone.make_aware(date_echeance_reste)
            else:
                date_echeance_reste = None
            
            # Calculer le nouveau montant total versé (ancien + nouveau)
            montant_total_verse = montant_deja_paye + montant_verse
            
            # Utiliser la méthode du modèle pour traiter le paiement
            # Cette méthode gère automatiquement les paiements partiels et complets
            facture.traiter_paiement_partiel(montant_total_verse, date_echeance_reste)
            
            # Mettre à jour les informations de paiement
            if mode_paiement:
                facture.mode_paiement = mode_paiement
            if reference_paiement:
                facture.reference_paiement = reference_paiement
            facture.save()
            
            # IMPORTANT : Si reste_a_payer = 0, la facture est réglée et en règle
            # Le modèle met déjà à jour automatiquement les colonnes montant_verse et reste_a_payer
            # Recharger la facture depuis la DB pour avoir les valeurs à jour
            facture.refresh_from_db()
            
            # Mettre à jour automatiquement le statut de réglementation de l'établissement
            etablissement.mettre_a_jour_statut_reglementation()
            
            # Message de succès selon le type de paiement
            if facture.est_paiement_complet():
                # Paiement complet : facture réglée et en règle
                messages.success(request, f"Paiement complet enregistré pour la facture {facture_numero} ! Montant: {montant_verse} FCFA. La facture est maintenant réglée et en règle.")
            else:
                # Paiement partiel : il reste encore à payer
                messages.success(request, f"Paiement partiel enregistré pour la facture {facture_numero} ! Montant versé: {montant_verse} FCFA. Reste à payer: {facture.reste_a_payer} FCFA")
            
        except Exception as e:
            messages.error(request, f"Erreur lors du traitement du paiement : {str(e)}")
        
        # Rediriger vers la page des détails financiers
        return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)
    
    # Si ce n'est pas une requête POST, rediriger vers la page des détails
    return redirect('school_admin:details_financiers_etablissement', etablissement_id=etablissement_id)


@comptable_required
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

@comptable_required
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


@comptable_required
def mettre_a_jour_statuts_factures(request):
    """
    Vue pour mettre à jour manuellement les statuts des factures
    """
    if request.method == 'POST':
        try:
            # Exécuter la mise à jour
            nombre_mises_a_jour = Facturation.mettre_a_jour_tous_les_statuts()
            
            if nombre_mises_a_jour > 0:
                messages.success(request, f"[SUCCES] Mise a jour terminee: {nombre_mises_a_jour} factures mises a jour")
            else:
                messages.info(request, "[INFO] Aucune facture a mettre a jour")
                
        except Exception as e:
            messages.error(request, f"[ERREUR] Erreur lors de la mise a jour: {str(e)}")
    
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

@comptable_required
def gestion_personnel_financier(request):
    # Vue pour la gestion financière du personnel
    return render(request, 'school_admin/gestion_comptable/gestion_personnel_financier.html')


@comptable_required
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


@comptable_required
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


@comptable_required
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


@comptable_required
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


@comptable_required
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


@comptable_required
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
