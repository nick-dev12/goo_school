from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from ..controllers.prospection_controller import ProspectionController
from ..model.prospection_model import Prospection
from ..model.note_commercial_model import NoteCommercial
from ..model.rendez_vous_model import RendezVous
from ..model.compte_rendu_model import CompteRendu
from ..model.message_model import MessageCommercial, ReponseMessage
from ..controllers.commercial_compte_controller import CommercialCompteController
from ..decorators import commercial_required


# ===== TABLEAUX DE BORD PAR FONCTION =====
# ===== COMMERCIAL =====
@commercial_required
def dashboard_commercial(request):
    """
    Tableau de bord pour les commerciaux
    Affiche les statistiques, les rendez-vous à venir, les établissements à prospecter, etc.
    """
    # Récupérer les statistiques spécifiques aux commerciaux
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les établissements du commercial
    etablissements = Prospection.objects.filter(
        cree_par=request.user,
        actif=True
    )
    
    # Récupérer les rendez-vous du commercial
    rendez_vous = RendezVous.objects.filter(
        etablissement__cree_par=request.user,
        etablissement__actif=True,
        actif=True
    )
    
    # Récupérer les comptes rendus du commercial
    comptes_rendus = CompteRendu.objects.filter(
        etablissement__cree_par=request.user,
        etablissement__actif=True,
        actif=True
    )
    
    # Calculer les statistiques
    from datetime import date, timedelta
    today = date.today()
    
    # Statistiques générales
    total_etablissements = etablissements.count()
    total_rendez_vous = rendez_vous.count()
    total_comptes_rendus = comptes_rendus.count()
    
    # Rendez-vous d'aujourd'hui
    rendez_vous_aujourd_hui = rendez_vous.filter(date_rdv=today).count()
    
    # Rendez-vous de cette semaine
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    rendez_vous_semaine = rendez_vous.filter(
        date_rdv__gte=week_start,
        date_rdv__lte=week_end
    ).count()
    
    # Rendez-vous à venir (7 prochains jours)
    prochaine_semaine = today + timedelta(days=7)
    rendez_vous_a_venir = rendez_vous.filter(
        date_rdv__gte=today,
        date_rdv__lte=prochaine_semaine
    ).count()
    
    # Statistiques par statut d'établissement
    etablissements_nouveaux = etablissements.filter(statut_etablissement='nouveau').count()
    etablissements_contactes = etablissements.filter(statut_etablissement='contacte').count()
    etablissements_rdv = etablissements.filter(statut_etablissement='rdv_planifie').count()
    etablissements_proposition = etablissements.filter(statut_etablissement='proposition').count()
    etablissements_signed = etablissements.filter(statut_etablissement='contrat_signe').count()
    
    # Calculer le taux de conversion
    taux_conversion = 0
    if total_etablissements > 0:
        taux_conversion = round((etablissements_signed / total_etablissements) * 100, 1)
    
    # Établissements récents (5 derniers)
    etablissements_recents = etablissements.order_by('-date_creation')[:5]
    
    # Rendez-vous à venir (5 prochains)
    rendez_vous_a_venir_list = rendez_vous.filter(
        date_rdv__gte=today
    ).order_by('date_rdv', 'heure_rdv')[:5]
    
    # Statistiques par pays
    pays_stats = {}
    for etablissement in etablissements:
        pays = etablissement.get_pays_etablissement_display()
        pays_stats[pays] = pays_stats.get(pays, 0) + 1
    
    # Statistiques par type d'établissement
    type_stats = {}
    for etablissement in etablissements:
        type_etab = etablissement.get_type_etablissement_display()
        type_stats[type_etab] = type_stats.get(type_etab, 0) + 1
    
    # Statistiques par priorité
    priorite_stats = {}
    for etablissement in etablissements:
        priorite = etablissement.get_priorite_etablissement_display()
        priorite_stats[priorite] = priorite_stats.get(priorite, 0) + 1
    
    # Statistiques pour le pipeline de vente
    pipeline_stats = {
        'nouveaux': {
            'count': etablissements_nouveaux,
            'percentage': round((etablissements_nouveaux / total_etablissements * 100) if total_etablissements > 0 else 0)
        },
        'contactes': {
            'count': etablissements_contactes,
            'percentage': round((etablissements_contactes / total_etablissements * 100) if total_etablissements > 0 else 0)
        },
        'rdv': {
            'count': etablissements_rdv,
            'percentage': round((etablissements_rdv / total_etablissements * 100) if total_etablissements > 0 else 0)
        },
        'proposition': {
            'count': etablissements_proposition,
            'percentage': round((etablissements_proposition / total_etablissements * 100) if total_etablissements > 0 else 0)
        },
        'signes': {
            'count': etablissements_signed,
            'percentage': round((etablissements_signed / total_etablissements * 100) if total_etablissements > 0 else 0)
        }
    }
    
    # Relances à faire (établissements contactés sans rendez-vous planifié)
    relances_a_faire = etablissements.filter(
        statut_etablissement='contacte'
    ).exclude(
        rendez_vous__date_rdv__gte=today
    ).count()
    
    # Rendez-vous par mois (pour les statistiques)
    from django.db.models import Count
    from django.db.models.functions import TruncMonth
    
    rendez_vous_par_mois = rendez_vous.annotate(
        mois=TruncMonth('date_rdv')
    ).values('mois').annotate(
        count=Count('id')
    ).order_by('mois')
    
    # Contrats signés par mois (pour les statistiques)
    contrats_par_mois = etablissements.filter(
        statut_etablissement='contrat_signe'
    ).annotate(
        mois=TruncMonth('date_creation')
    ).values('mois').annotate(
        count=Count('id')
    ).order_by('mois')
    
    context = {
        'user_commercial': user_commercial,
        
        # Statistiques générales
        'total_etablissements': total_etablissements,
        'total_rendez_vous': total_rendez_vous,
        'total_comptes_rendus': total_comptes_rendus,
        'rendez_vous_aujourd_hui': rendez_vous_aujourd_hui,
        'rendez_vous_semaine': rendez_vous_semaine,
        'rendez_vous_a_venir': rendez_vous_a_venir,
        'relances_a_faire': relances_a_faire,
        'taux_conversion': taux_conversion,
        
        # Statistiques du pipeline
        'etablissements_nouveaux': etablissements_nouveaux,
        'etablissements_contactes': etablissements_contactes,
        'etablissements_rdv': etablissements_rdv,
        'etablissements_proposition': etablissements_proposition,
        'etablissements_signed': etablissements_signed,
        'pipeline_stats': pipeline_stats,
        
        # Listes d'objets
        'etablissements_recents': etablissements_recents,
        'rendez_vous_a_venir_list': rendez_vous_a_venir_list,
        
        # Statistiques détaillées
        'pays_stats': pays_stats,
        'type_stats': type_stats,
        'priorite_stats': priorite_stats,
        'rendez_vous_par_mois': rendez_vous_par_mois,
        'contrats_par_mois': contrats_par_mois,
    }
    
    return render(request, 'school_admin/commercial/dashboard_commercial.html', context)
    
    
# ===== AJOUTER UN ÉTABLISSEMENT =====

@commercial_required
def commercial_ajouter_etablissement(request):
    """
    Vue pour l'ajout d'un établissement
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    if request.method == 'POST':
        # Utiliser le contrôleur de prospection pour traiter les données
        result = ProspectionController.ajouter_prospection(request)
        
        if isinstance(result, tuple):
            # Il y a des erreurs de validation
            context = {
                'field_errors': result[0]['field_errors'],
                'form_data': result[0]['form_data'],
            }
            return render(request, 'school_admin/commercial/ajouter_etablissement.html', context)
        else:
            # Redirection après succès (le message est géré par le contrôleur)
            return result
    
    # Affichage initial du formulaire
    return render(request, 'school_admin/commercial/ajouter_etablissement.html')




# ===== LISTE DES ÉTABLISSEMENTS =====

@commercial_required
def commercial_liste_etablissements(request):
    """
    Vue pour lister les établissements du commercial
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les paramètres de recherche et filtres
    search_query = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    statut_filter = request.GET.get('statut', '')
    potentiel_filter = request.GET.get('potentiel', '')
    priorite_filter = request.GET.get('priorite', '')
    pays_filter = request.GET.get('pays', '')
    
    # Récupérer les établissements du commercial connecté
    etablissements = Prospection.objects.filter(
        cree_par=user_commercial,   # Remplace request.user par user_commercial
        actif=True
    ).order_by('-date_creation')
    
    # Appliquer les filtres de recherche
    if search_query:
        etablissements = etablissements.filter(
            Q(nom_etablissement__icontains=search_query) |
            Q(ville_etablissement__icontains=search_query) |
            Q(adresse_etablissement__icontains=search_query)
        )
    
    if type_filter:
        etablissements = etablissements.filter(type_etablissement=type_filter)
    
    if statut_filter:
        etablissements = etablissements.filter(statut_etablissement=statut_filter)
    
    if potentiel_filter:
        etablissements = etablissements.filter(potentiel_etablissement=potentiel_filter)
    
    if priorite_filter:
        etablissements = etablissements.filter(priorite_etablissement=priorite_filter)
    
    if pays_filter:
        etablissements = etablissements.filter(pays_etablissement=pays_filter)
    
    # Statistiques
    total_etablissements = etablissements.count()
    stats = {
        'total': total_etablissements,
        'par_type': {},
        'par_potentiel': {},
        'par_priorite': {}
    }
    
    # Calculer les statistiques
    for etablissement in etablissements:
        # Par type
        type_key = etablissement.get_type_etablissement_display()
        stats['par_type'][type_key] = stats['par_type'].get(type_key, 0) + 1
        
        # Par potentiel
        potentiel_key = etablissement.get_potentiel_etablissement_display()
        stats['par_potentiel'][potentiel_key] = stats['par_potentiel'].get(potentiel_key, 0) + 1
        
        # Par priorité
        priorite_key = etablissement.get_priorite_etablissement_display()
        stats['par_priorite'][priorite_key] = stats['par_priorite'].get(priorite_key, 0) + 1
    
    context = {
        'etablissements': etablissements,
        'search_query': search_query,
        'type_filter': type_filter,
        'statut_filter': statut_filter,
        'potentiel_filter': potentiel_filter,
        'priorite_filter': priorite_filter,
        'pays_filter': pays_filter,
        'stats': stats,
    }
    
    return render(request, 'school_admin/commercial/liste_etablissements.html', context)




# ===== FONCTIONS DE TRAITEMENT DES FORMULAIRES =====
# ===== VUES POUR LES FORMULAIRES DE DÉTAIL ÉTABLISSEMENT =====

def commercial_update_status(request, etablissement_id):
    """
    Vue pour mettre à jour le statut d'un établissement
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=user_commercial,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    if request.method == 'POST':
        nouveau_statut = request.POST.get('nouveau_statut')
        if nouveau_statut:
            etablissement.statut_etablissement = nouveau_statut
            etablissement.save()
            messages.success(request, f"Statut mis à jour : {etablissement.get_statut_etablissement_display()}")
        else:
            messages.error(request, "Veuillez sélectionner un statut")
    
    return redirect('school_admin:commercial_detail_etablissement', etablissement_id=etablissement_id)


def commercial_update_priority(request, etablissement_id):
    """
    Vue pour mettre à jour la priorité d'un établissement
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=user_commercial,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    if request.method == 'POST':
        nouvelle_priorite = request.POST.get('nouvelle_priorite')
        if nouvelle_priorite:
            etablissement.priorite_etablissement = nouvelle_priorite
            etablissement.save()
            messages.success(request, f"Priorité mise à jour : {etablissement.get_priorite_etablissement_display()}")
        else:
            messages.error(request, "Veuillez sélectionner une priorité")
    
    return redirect('school_admin:commercial_detail_etablissement', etablissement_id=etablissement_id)


def commercial_add_notes(request, etablissement_id):
    """
    Vue pour ajouter une note commerciale
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=user_commercial,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '').strip()
        if notes:
            NoteCommercial.objects.create(
                etablissement=etablissement,
                contenu=notes,
                cree_par=user_commercial,
            )
            messages.success(request, "Note ajoutée avec succès")
        else:
            messages.error(request, "Veuillez saisir une note")
    
    return redirect('school_admin:commercial_detail_etablissement', etablissement_id=etablissement_id)


def commercial_schedule_meeting(request, etablissement_id):
    """
    Vue pour programmer un rendez-vous
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=user_commercial,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    if request.method == 'POST':
        date_rdv = request.POST.get('date_rdv')
        heure_rdv = request.POST.get('heure_rdv')
        type_rdv = request.POST.get('type_rdv')
        notes_rdv = request.POST.get('notes_rdv', '')

        if date_rdv and heure_rdv and type_rdv:
            RendezVous.objects.create(
                etablissement=etablissement,
                type_rdv=type_rdv,
                date_rdv=date_rdv,
                heure_rdv=heure_rdv,
                notes_rdv=notes_rdv,
                cree_par=user_commercial,
            )
            messages.success(request, "Rendez-vous programmé avec succès")
        else:
            messages.error(request, "Veuillez remplir tous les champs obligatoires")
    
    return redirect('school_admin:commercial_detail_etablissement', etablissement_id=etablissement_id)


def commercial_update_general_info(request, etablissement_id):
    """
    Vue pour mettre à jour les informations générales d'un établissement
    """
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=request.user if request.user.is_authenticated else None,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    if request.method == 'POST':
        nom_etablissement = request.POST.get('nom_etablissement', '').strip()
        type_etablissement = request.POST.get('type_etablissement', '')
        
        if nom_etablissement and type_etablissement:
            etablissement.nom_etablissement = nom_etablissement
            etablissement.type_etablissement = type_etablissement
            etablissement.save()
            messages.success(request, "Informations générales mises à jour avec succès")
        else:
            messages.error(request, "Veuillez remplir tous les champs obligatoires")
    
    return redirect('school_admin:commercial_detail_etablissement', etablissement_id=etablissement_id)


def commercial_update_location(request, etablissement_id):
    """
    Vue pour mettre à jour la localisation d'un établissement
    """
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=request.user if request.user.is_authenticated else None,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    if request.method == 'POST':
        ville_etablissement = request.POST.get('ville_etablissement', '').strip()
        pays_etablissement = request.POST.get('pays_etablissement', '')
        adresse_etablissement = request.POST.get('adresse_etablissement', '').strip()
        
        if ville_etablissement and pays_etablissement and adresse_etablissement:
            etablissement.ville_etablissement = ville_etablissement
            etablissement.pays_etablissement = pays_etablissement
            etablissement.adresse_etablissement = adresse_etablissement
            etablissement.save()
            messages.success(request, "Informations de localisation mises à jour avec succès")
        else:
            messages.error(request, "Veuillez remplir tous les champs obligatoires")
    
    return redirect('school_admin:commercial_detail_etablissement', etablissement_id=etablissement_id)


def commercial_delete_meeting(request, etablissement_id):
    """
    Vue pour supprimer un rendez-vous
    """
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=request.user if request.user.is_authenticated else None,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    if request.method == 'POST':
        meeting_id = request.POST.get('meeting_id')
        if meeting_id:
            try:
                rendez_vous = RendezVous.objects.get(
                    id=meeting_id,
                    etablissement=etablissement,
                    actif=True
                )
                rendez_vous.actif = False
                rendez_vous.save()
                messages.success(request, "Rendez-vous supprimé avec succès")
            except RendezVous.DoesNotExist:
                messages.error(request, "Rendez-vous non trouvé")
        else:
            messages.error(request, "ID de rendez-vous manquant")
    
    return redirect('school_admin:commercial_detail_etablissement', etablissement_id=etablissement_id)


def commercial_delete_note(request, etablissement_id):
    """
    Vue pour supprimer une note commerciale
    """
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=request.user if request.user.is_authenticated else None,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    if request.method == 'POST':
        note_id = request.POST.get('note_id')
        if note_id:
            try:
                note = NoteCommercial.objects.get(
                    id=note_id,
                    etablissement=etablissement,
                    actif=True
                )
                note.actif = False
                note.save()
                messages.success(request, "Note supprimée avec succès")
            except NoteCommercial.DoesNotExist:
                messages.error(request, "Note non trouvée")
        else:
            messages.error(request, "ID de note manquant")
    
    return redirect('school_admin:commercial_detail_etablissement', etablissement_id=etablissement_id)





# vue pour afficher les détails d'un établissement avec les options de prospection
def commercial_detail_etablissement(request, etablissement_id):
    """
    Vue pour afficher les détails d'un établissement avec les options de prospection
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        etablissement = Prospection.objects.get(
            id=etablissement_id,
            cree_par=user_commercial,
            actif=True
        )
    except Prospection.DoesNotExist:
        messages.error(request, "Établissement non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_liste_etablissements')
    
    # Récupérer les rendez-vous depuis la base de données
    rendez_vous_list = RendezVous.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('-date_creation')
    
    # Récupérer les notes commerciales depuis la base de données
    notes_commercial_list = NoteCommercial.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('-date_creation')
    
    context = {
        'etablissement': etablissement,
        'rendez_vous_list': rendez_vous_list,
        'notes_commercial_list': notes_commercial_list,
    }
    
    return render(request, 'school_admin/commercial/detail_etablissement.html', context)









@commercial_required
def commercial_rendez_vous(request):
    """
    Vue pour afficher tous les rendez-vous programmés
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer tous les rendez-vous du commercial connecté
    rendez_vous_list = RendezVous.objects.filter(
        etablissement__cree_par=user_commercial,
        etablissement__actif=True,
        actif=True
    ).order_by('-date_creation')
    
    # Récupérer tous les établissements pour le filtre
    etablissements = Prospection.objects.filter(
        cree_par=user_commercial,
        actif=True
    ).order_by('nom_etablissement')
    
    # Calculer les statistiques
    total_rendez_vous = rendez_vous_list.count()
    
    # Rendez-vous d'aujourd'hui
    from datetime import date
    today = date.today()
    rendez_vous_aujourd_hui = rendez_vous_list.filter(date_rdv=today).count()
    
    # Rendez-vous de cette semaine
    from datetime import timedelta
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    rendez_vous_semaine = rendez_vous_list.filter(
        date_rdv__gte=week_start,
        date_rdv__lte=week_end
    ).count()
    
    # Nombre d'établissements avec des rendez-vous
    etablissements_avec_rdv = etablissements.filter(rendez_vous__actif=True).distinct().count()
    
    # Traitement des actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'delete_meeting':
            meeting_id = request.POST.get('meeting_id')
            if meeting_id:
                try:
                    rendez_vous = RendezVous.objects.get(
                        id=meeting_id,
                        etablissement__cree_par=user_commercial,
                        actif=True
                    )
                    rendez_vous.actif = False
                    rendez_vous.save()
                    messages.success(request, "Rendez-vous supprimé avec succès")
                except RendezVous.DoesNotExist:
                    messages.error(request, "Rendez-vous non trouvé")
            else:
                messages.error(request, "ID de rendez-vous manquant")
            
            return redirect('school_admin:commercial_rendez_vous')
    
    context = {
        'rendez_vous_list': rendez_vous_list,
        'etablissements': etablissements,
        'total_rendez_vous': total_rendez_vous,
        'rendez_vous_aujourd_hui': rendez_vous_aujourd_hui,
        'rendez_vous_semaine': rendez_vous_semaine,
        'etablissements_avec_rdv': etablissements_avec_rdv,
    }
    
    return render(request, 'school_admin/commercial/rendez_vous.html', context)








def commercial_comptes_rendus(request):
    """
    Vue pour afficher et gérer les comptes rendus de visite
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer tous les comptes rendus du commercial connecté
    comptes_rendus_list = CompteRendu.objects.filter(
        etablissement__cree_par=user_commercial,
        etablissement__actif=True,
        actif=True
    ).order_by('-date_creation')
    
    # Récupérer tous les établissements pour le filtre
    etablissements = Prospection.objects.filter(
        cree_par=user_commercial,
        actif=True
    ).order_by('nom_etablissement')
    
    # Récupérer tous les rendez-vous pour le formulaire
    rendez_vous_list = RendezVous.objects.filter(
        etablissement__cree_par=user_commercial,
        etablissement__actif=True,
        actif=True
    ).order_by('-date_rdv')
    
    # Calculer les statistiques
    total_comptes_rendus = comptes_rendus_list.count()
    
    # Comptes rendus de ce mois
    from datetime import date
    today = date.today()
    month_start = today.replace(day=1)
    comptes_rendus_mois = comptes_rendus_list.filter(
        date_visite__gte=month_start
    ).count()
    
    # Nombre d'établissements avec des comptes rendus
    etablissements_avec_cr = etablissements.filter(comptes_rendus__actif=True).distinct().count()
    
    # Traitement des actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_compte_rendu':
            rendez_vous_id = request.POST.get('rendez_vous_id')
            titre = request.POST.get('titre', '').strip()
            contenu = request.POST.get('contenu', '').strip()
            satisfaction_client = request.POST.get('satisfaction_client')
            
            if rendez_vous_id and titre and contenu and satisfaction_client:
                try:
                    # Récupérer le rendez-vous
                    rendez_vous = RendezVous.objects.get(
                        id=rendez_vous_id,
                        etablissement__cree_par=user_commercial,
                        actif=True
                    )
                    
                    # Créer le compte rendu avec les informations du rendez-vous
                    compte_rendu = CompteRendu.objects.create(
                        etablissement=rendez_vous.etablissement,
                        rendez_vous=rendez_vous,
                        titre=titre,
                        contenu=contenu,
                        date_visite=rendez_vous.date_rdv,  # Utiliser la date du rendez-vous
                        satisfaction_client=satisfaction_client,
                        cree_par=user_commercial,
                    )
                    messages.success(request, "Compte rendu ajouté avec succès")
                except RendezVous.DoesNotExist:
                    messages.error(request, "Rendez-vous non trouvé")
                except Exception as e:
                    messages.error(request, f"Erreur lors de la création : {str(e)}")
            else:
                messages.error(request, "Veuillez remplir tous les champs obligatoires")
            
            return redirect('school_admin:commercial_comptes_rendus')
        
        elif action == 'delete_compte_rendu':
            compte_rendu_id = request.POST.get('compte_rendu_id')
            if compte_rendu_id:
                try:
                    compte_rendu = CompteRendu.objects.get(
                        id=compte_rendu_id,
                        etablissement__cree_par=request.user if request.user.is_authenticated else None,
                        actif=True
                    )
                    compte_rendu.actif = False
                    compte_rendu.save()
                    messages.success(request, "Compte rendu supprimé avec succès")
                except CompteRendu.DoesNotExist:
                    messages.error(request, "Compte rendu non trouvé")
            else:
                messages.error(request, "ID de compte rendu manquant")
            
            return redirect('school_admin:commercial_comptes_rendus')
    
    context = {
        'comptes_rendus_list': comptes_rendus_list,
        'etablissements': etablissements,
        'rendez_vous_list': rendez_vous_list,
        'total_comptes_rendus': total_comptes_rendus,
        'comptes_rendus_mois': comptes_rendus_mois,
        'etablissements_avec_cr': etablissements_avec_cr,
    }
    
    return render(request, 'school_admin/commercial/comptes_rendus.html', context)


def commercial_creer_rapport(request, rendez_vous_id):
    """
    Vue pour créer un rapport de visite basé sur un rendez-vous
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        rendez_vous = RendezVous.objects.get(
            id=rendez_vous_id,
            etablissement__cree_par=user_commercial,
            actif=True
        )
    except RendezVous.DoesNotExist:
        messages.error(request, "Rendez-vous non trouvé ou accès non autorisé.")
        return redirect('school_admin:commercial_rendez_vous')
    
    # Vérifier si un rapport existe déjà pour ce rendez-vous
    rapport_existant = CompteRendu.objects.filter(
        rendez_vous=rendez_vous,
        actif=True
    ).first()
    
    if rapport_existant:
        messages.info(request, "Un rapport existe déjà pour ce rendez-vous.")
        return redirect('school_admin:commercial_comptes_rendus')
    
    # Traitement du formulaire
    if request.method == 'POST':
        titre = request.POST.get('titre', '').strip()
        contenu = request.POST.get('contenu', '').strip()
        satisfaction_client = request.POST.get('satisfaction_client')
        
        if titre and contenu and satisfaction_client:
            CompteRendu.objects.create(
                etablissement=rendez_vous.etablissement,
                rendez_vous=rendez_vous,
                titre=titre,
                contenu=contenu,
                date_visite=rendez_vous.date_rdv,
                satisfaction_client=satisfaction_client,
                cree_par=user_commercial,
            )
            messages.success(request, "Rapport créé avec succès")
            return redirect('school_admin:commercial_comptes_rendus')
        else:
            messages.error(request, "Veuillez remplir tous les champs obligatoires")
    
    context = {
        'rendez_vous': rendez_vous,
        'etablissement': rendez_vous.etablissement,
    }
    
    return render(request, 'school_admin/commercial/creer_rapport.html', context)


# ===== MESSAGES COMMERCIAUX =====

@commercial_required
def commercial_messages(request):
    """
    Vue pour afficher la liste des messages commerciaux avec système de tickets
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les paramètres de recherche et filtres
    search_query = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    priorite_filter = request.GET.get('priorite', '')
    statut_filter = request.GET.get('statut', '')
    etablissement_filter = request.GET.get('etablissement', '')
    section = request.GET.get('section', 'admin')  # 'admin' ou 'etablissement'
    
    # Récupérer les messages selon la section
    if section == 'admin':
        # Messages envoyés par les administrateurs
        messages_list = MessageCommercial.objects.filter(
            expediteur_type='admin',
            destinataire=user_commercial,
            actif=True
        ).order_by('-date_envoi')
    else:
        # Messages envoyés par les établissements (tickets)
        messages_list = MessageCommercial.objects.filter(
            expediteur_type='etablissement',
            destinataire=user_commercial,
            actif=True
        ).order_by('-date_envoi')
    
    # Appliquer les filtres de recherche
    if search_query:
        messages_list = messages_list.filter(
            Q(sujet__icontains=search_query) |
            Q(contenu__icontains=search_query) |
            Q(etablissement__nom_etablissement__icontains=search_query)
        )
    
    if type_filter:
        messages_list = messages_list.filter(type_message=type_filter)
    
    if priorite_filter:
        messages_list = messages_list.filter(priorite=priorite_filter)
    
    if statut_filter:
        messages_list = messages_list.filter(statut=statut_filter)
    
    if etablissement_filter:
        messages_list = messages_list.filter(etablissement_id=etablissement_filter)
    
    # Récupérer tous les établissements pour le filtre
    etablissements = Prospection.objects.filter(
        cree_par=user_commercial,
        actif=True
    ).order_by('nom_etablissement')
    
    # Calculer les statistiques pour chaque section
    messages_admin = MessageCommercial.objects.filter(
        expediteur_type='admin',
        destinataire=user_commercial,
        actif=True
    )
    
    messages_etablissement = MessageCommercial.objects.filter(
        expediteur_type='etablissement',
        destinataire=user_commercial,
        actif=True
    )
    
    # Statistiques générales
    total_messages = messages_list.count()
    messages_non_lus = messages_list.filter(statut='non_lu').count()
    messages_urgents = messages_list.filter(priorite='urgente').count()
    messages_aujourd_hui = messages_list.filter(date_envoi__date=timezone.now().date()).count()
    
    # Statistiques par section
    stats_admin = {
        'total': messages_admin.count(),
        'non_lus': messages_admin.filter(statut='non_lu').count(),
        'urgents': messages_admin.filter(priorite='urgente').count(),
        'aujourd_hui': messages_admin.filter(date_envoi__date=timezone.now().date()).count(),
    }
    
    stats_etablissement = {
        'total': messages_etablissement.count(),
        'non_lus': messages_etablissement.filter(statut='non_lu').count(),
        'urgents': messages_etablissement.filter(priorite='urgente').count(),
        'aujourd_hui': messages_etablissement.filter(date_envoi__date=timezone.now().date()).count(),
        'tickets_ouverts': messages_etablissement.filter(ticket_statut='ouvert').count(),
        'tickets_en_cours': messages_etablissement.filter(ticket_statut='en_cours').count(),
        'tickets_fermes': messages_etablissement.filter(ticket_statut='ferme').count(),
    }
    
    context = {
        'messages_list': messages_list,
        'etablissements': etablissements,
        'search_query': search_query,
        'type_filter': type_filter,
        'priorite_filter': priorite_filter,
        'statut_filter': statut_filter,
        'etablissement_filter': etablissement_filter,
        'section': section,
        'total_messages': total_messages,
        'messages_non_lus': messages_non_lus,
        'messages_urgents': messages_urgents,
        'messages_aujourd_hui': messages_aujourd_hui,
        'stats_admin': stats_admin,
        'stats_etablissement': stats_etablissement,
    }
    
    return render(request, 'school_admin/commercial/messages.html', context)


@commercial_required
def commercial_conversation_etablissement(request):
    """
    Vue pour afficher les détails d'un message
    """
    return render(request, 'school_admin/commercial/conversation_etablissement.html')


@commercial_required
def commercial_profil(request):
    """
    Vue pour afficher et modifier le profil du commercial
    """
    user_commercial = CommercialCompteController.get_user_compte_commercial(request)
    if not user_commercial:
        messages.error(request, "Erreur lors de la récupération des données commerciales.")
        return redirect('school_admin:connexion_compte_user')
    
    commercial = request.user
    
    # Traitement de la mise à jour du profil
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_profile':
            # Mise à jour des informations personnelles
            nom = request.POST.get('nom', '').strip()
            prenom = request.POST.get('prenom', '').strip()
            email = request.POST.get('email', '').strip()
            telephone = request.POST.get('telephone', '').strip()
            date_naissance = request.POST.get('date_naissance', '')
            
            if nom and prenom and email:
                commercial.nom = nom
                commercial.prenom = prenom
                commercial.email = email
                commercial.telephone = telephone
                if date_naissance:
                    commercial.date_naissance = date_naissance
                commercial.save()
                messages.success(request, "Profil mis à jour avec succès")
            else:
                messages.error(request, "Veuillez remplir tous les champs obligatoires")
        
        elif action == 'change_password':
            # Changement de mot de passe
            ancien_mot_de_passe = request.POST.get('ancien_mot_de_passe', '')
            nouveau_mot_de_passe = request.POST.get('nouveau_mot_de_passe', '')
            confirmer_mot_de_passe = request.POST.get('confirmer_mot_de_passe', '')
            
            if ancien_mot_de_passe and nouveau_mot_de_passe and confirmer_mot_de_passe:
                # Vérifier l'ancien mot de passe
                if commercial.check_password(ancien_mot_de_passe):
                    if nouveau_mot_de_passe == confirmer_mot_de_passe:
                        if len(nouveau_mot_de_passe) >= 8:
                            commercial.set_password(nouveau_mot_de_passe)
                            commercial.save()
                            messages.success(request, "Mot de passe modifié avec succès")
                        else:
                            messages.error(request, "Le nouveau mot de passe doit contenir au moins 8 caractères")
                    else:
                        messages.error(request, "Les nouveaux mots de passe ne correspondent pas")
                else:
                    messages.error(request, "Ancien mot de passe incorrect")
            else:
                messages.error(request, "Veuillez remplir tous les champs")
        
        return redirect('school_admin:commercial_profil')
    
    context = {
        'commercial': commercial,
    }
    
    return render(request, 'school_admin/commercial/profil.html', context)
