from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from ..controllers.administrateur_compte_controller import AdministrateurCompteController
from ..controllers.etablissement_controller import EtablissementController
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from ..controllers.compte_user_controller import CompteUserController
from ..controllers.etablissement_controller import EtablissementController
from ..model.compte_user import CompteUser
from django.db.models import Count, Q as models
from django.core.paginator import Paginator
from datetime import datetime, timedelta





@login_required
def dashboard_administrateur(request):
    """
    Tableau de bord pour les administrateurs
    """
    # Vérifier le type d'utilisateur et rediriger vers le tableau de bord approprié
    from ..model.compte_user import CompteUser
    from ..model.etablissement_model import Etablissement
    from ..model.personnel_administratif_model import PersonnelAdministratif
    from ..model.eleve_model import Eleve
    
    # Si c'est un CompteUser, vérifier sa fonction
    if isinstance(request.user, CompteUser) and hasattr(request.user, 'fonction'):
        fonction = request.user.fonction
        
        # Si c'est un administrateur, continuer vers le dashboard administrateur
        if fonction == 'administrateur':
            pass  # Continuer vers le dashboard administrateur
        elif fonction == 'commercial':
            return redirect('school_admin:dashboard_commercial')
        elif fonction == 'support':
            return redirect('school_admin:dashboard_support')
        elif fonction == 'developpeur':
            return redirect('school_admin:dashboard_developpeur')
        elif fonction == 'marketing':
            return redirect('school_admin:dashboard_marketing')
        elif fonction == 'comptable':
            return redirect('school_admin:dashboard_comptable')
        elif fonction == 'ressources humaines':
            return redirect('school_admin:dashboard_rh')
        else:
            # Si la fonction n'est pas reconnue ou n'est pas administrateur, rediriger vers la connexion
            messages.error(request, "Accès non autorisé. Vous devez être administrateur pour accéder à cette page.")
            return redirect('school_admin:connexion_compte_user')
    
    # Si c'est un Etablissement, rediriger vers le dashboard directeur
    elif isinstance(request.user, Etablissement):
        return redirect('directeur:dashboard_directeur')
    
    # Si c'est un PersonnelAdministratif, rediriger vers le dashboard personnel
    elif isinstance(request.user, PersonnelAdministratif):
        return redirect('personnel_administratif:dashboard_personnel_administratif')
    
    # Si c'est un Eleve, rediriger vers le dashboard élève
    elif isinstance(request.user, Eleve):
        return redirect('eleve:dashboard_eleve')
    
    # Si aucun type reconnu, rediriger vers la connexion
    else:
        messages.error(request, "Type d'utilisateur non reconnu. Veuillez vous reconnecter.")
        return redirect('school_admin:connexion_compte_user')
    
    # Si c'est un administrateur ou si la fonction n'est pas reconnue, afficher le tableau de bord administrateur
    from django.utils import timezone
    from datetime import datetime, timedelta
    from django.db.models import Sum, Q
    from ..model.facturation_model import Facturation
    
    # Mettre à jour les statuts de réglementation de tous les établissements
    for etablissement in Etablissement.objects.filter(actif=True):
        etablissement.mettre_a_jour_statut_reglementation()
    
    # Récupérer les statistiques des établissements
    total_etablissements = EtablissementController.count_all_etablissements()
    active_etablissements = EtablissementController.count_active_etablissements()
    inactive_etablissements = Etablissement.objects.filter(actif=False).count()
    stats_by_country = EtablissementController.get_etablissement_stats_by_country()
    stats_by_type = EtablissementController.get_etablissement_stats_by_type()
    # Limiter à 3 établissements récents
    recent_etablissements = Etablissement.objects.order_by('-date_creation')[:3]
    
    # Récupérer le nombre total d'élèves
    total_eleves = Eleve.objects.filter(actif=True).count()
    
    # Paiements en retard (établissements avec statut_reglementation différent de 'en_regle')
    etablissements_retard = Etablissement.objects.filter(
        actif=True
    ).exclude(statut_reglementation='en_regle').count()
    
    # Calculer l'évolution mensuelle des paiements en retard
    maintenant = timezone.now()
    mois_actuel = maintenant.month
    annee_actuelle = maintenant.year
    
    if mois_actuel == 1:
        mois_precedent = 12
        annee_precedente = annee_actuelle - 1
    else:
        mois_precedent = mois_actuel - 1
        annee_precedente = annee_actuelle
    
    # Compter les établissements en retard ce mois (basé sur les factures créées ce mois avec statut en retard)
    factures_retard_mois_actuel = Facturation.objects.filter(
        date_creation__year=annee_actuelle,
        date_creation__month=mois_actuel,
        statut__in=['en_retard', 'impaye', 'contentieux']
    ).exclude(statut='annule').values('etablissement').distinct().count()
    
    factures_retard_mois_precedent = Facturation.objects.filter(
        date_creation__year=annee_precedente,
        date_creation__month=mois_precedent,
        statut__in=['en_retard', 'impaye', 'contentieux']
    ).exclude(statut='annule').values('etablissement').distinct().count()
    
    pourcentage_evolution_retard = 0
    if factures_retard_mois_precedent > 0:
        pourcentage_evolution_retard = round(((factures_retard_mois_actuel - factures_retard_mois_precedent) / factures_retard_mois_precedent) * 100, 1)
    elif factures_retard_mois_actuel > 0 and factures_retard_mois_precedent == 0:
        pourcentage_evolution_retard = 100  # Nouveau retard
    
    # Établissements en conformité dans les 30 prochains jours
    # (établissements avec des factures dont la date d'échéance est dans les 30 prochains jours)
    date_limite = maintenant.date() + timedelta(days=30)
    factures_prochaines = Facturation.objects.filter(
        date_echeance__gte=maintenant.date(),
        date_echeance__lte=date_limite,
        statut__in=['en_attente', 'en_retard']
    ).exclude(statut='annule').values('etablissement').distinct()
    
    etablissements_en_conformite = factures_prochaines.count()
    
    # Récupérer les membres d'équipe récents (limiter à 3)
    recent_team_members = CompteUser.objects.filter(
        fonction__in=['commercial', 'support', 'developpeur', 'marketing', 'comptable', 'ressources humaines']
    ).order_by('-date_joined')[:3]
    
    context = {
        'total_etablissements': total_etablissements,
        'active_etablissements': active_etablissements,
        'inactive_etablissements': inactive_etablissements,
        'stats_by_country': stats_by_country,
        'stats_by_type': stats_by_type,
        'recent_etablissements': recent_etablissements,
        'recent_team_members': recent_team_members,
        'total_eleves': total_eleves,
        'etablissements_retard': etablissements_retard,
        'pourcentage_evolution_retard': pourcentage_evolution_retard,
        'etablissements_en_conformite': etablissements_en_conformite,
        'user': request.user,
    }
    return render(request, 'school_admin/dashboard.html', context)



def etablissements(request):
    """
    Gestion des établissements (protégé)
    """
    user_administrateur = AdministrateurCompteController.get_user_compte_administrateur(request)
    # Récupérer les paramètres de filtrage
    search_query = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')
    page = request.GET.get('page', 1)
    
    # Récupérer les établissements
    etablissements_list = EtablissementController.get_all_etablissements(
        search_query=search_query,
        type_filter=type_filter,
        status_filter=status_filter
    )
    
    # Pagination
    paginator = Paginator(etablissements_list, 10)  # 10 établissements par page
    
    try:
        etablissements = paginator.page(page)
    except PageNotAnInteger:
        etablissements = paginator.page(1)
    except EmptyPage:
        etablissements = paginator.page(paginator.num_pages)
    
    context = {
        'etablissements': etablissements,
        'search_query': search_query,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'total_etablissements': etablissements_list.count(),
        'user_administrateur': user_administrateur,
    }
    
    return render(request, 'school_admin/etablissements/etablissement.html', context)


def ajout_etablissement(request):
    """
    Ajout d'un établissement (protégé)
    """
    
    if request.method == 'POST':
        # Utiliser le contrôleur pour traiter l'ajout d'établissement
        context, response = EtablissementController.process_ajout_etablissement(request)
        if response:
            return response
        # Si pas de redirection, afficher le template avec les erreurs
        return render(request, 'school_admin/etablissements/ajout_etablissement.html', context)
    
    # Si GET, afficher simplement le formulaire
    return render(request, 'school_admin/etablissements/ajout_etablissement.html', {'field_errors': {}, 'form_data': {}})


def detaille_etablissement(request):
    """
    Détails d'un établissement (protégé)
    """
    etablissement_id = request.GET.get('id', None)
    etablissement = EtablissementController.get_etablissement_by_id(etablissement_id)
    
    if not etablissement:
        messages.error(request, "Établissement non trouvé.")
        return redirect('school_admin:etablissements')
    
    # Calculer les statistiques de l'établissement
    from ..model.eleve_model import Eleve
    from ..model.professeur_model import Professeur
    from django.utils import timezone
    from datetime import timedelta
    
    # Nombre d'élèves inscrits (actifs)
    nombre_eleves = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
    
    # Nombre d'élèves inscrits ce mois (pour la tendance)
    date_aujourdhui = timezone.now().date()
    premier_jour_mois = date_aujourdhui.replace(day=1)
    eleves_ce_mois = Eleve.objects.filter(
        etablissement=etablissement,
        date_inscription__gte=premier_jour_mois,
        actif=True
    ).count()
    
    # Calculer le pourcentage d'augmentation (tendance)
    eleves_mois_precedent = Eleve.objects.filter(
        etablissement=etablissement,
        date_inscription__gte=premier_jour_mois - timedelta(days=30),
        date_inscription__lt=premier_jour_mois,
        actif=True
    ).count()
    
    pourcentage_evolution = 0
    if eleves_mois_precedent > 0:
        pourcentage_evolution = round(((eleves_ce_mois - eleves_mois_precedent) / eleves_mois_precedent) * 100, 1)
    elif eleves_ce_mois > 0:
        pourcentage_evolution = 100.0
    
    # Nombre d'enseignants (actifs)
    nombre_enseignants = Professeur.objects.filter(etablissement=etablissement, actif=True).count()
    
    context = {
        'etablissement': etablissement,
        'nombre_eleves': nombre_eleves,
        'nombre_enseignants': nombre_enseignants,
        'pourcentage_evolution_eleves': pourcentage_evolution,
    }
    
    return render(request, 'school_admin/etablissements/detaille_etablissement.html', context)


@login_required
def administrateur_update_etablissement(request):
    """
    Vue spéciale pour la mise à jour des paramètres d'un établissement
    """
    # Vérifier que l'utilisateur est un administrateur
    if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction') or request.user.fonction != 'administrateur':
        messages.error(request, "Accès non autorisé. Vous devez être administrateur pour effectuer cette action.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'ID de l'établissement depuis le formulaire
    etablissement_id = request.POST.get('etablissement_id')
    
    if not etablissement_id:
        messages.error(request, "ID de l'établissement manquant.")
        return redirect('school_admin:etablissements')
    
    etablissement = EtablissementController.get_etablissement_by_id(etablissement_id)
    
    if not etablissement:
        messages.error(request, "Établissement non trouvé.")
        return redirect('school_admin:etablissements')
    
    # Validation et traitement du formulaire
    if request.method == 'POST':
        # Validation des champs obligatoires
        required_fields = ['nom', 'type_etablissement', 'adresse', 'email', 'type_facturation', 'montant_par_eleve']
        errors = {}
        
        for field in required_fields:
            if not request.POST.get(field):
                errors[field] = f"Le champ {field} est obligatoire."
        
        # Validation du type de facturation
        valid_facturation_types = ['mensuel', 'annuel']
        if request.POST.get('type_facturation') not in valid_facturation_types:
            errors['type_facturation'] = "Le type de facturation n'est pas valide."
        
        # Validation du montant par élève
        try:
            montant_par_eleve = float(request.POST.get('montant_par_eleve', 0))
            if montant_par_eleve < 0:
                errors['montant_par_eleve'] = "Le montant par élève ne peut pas être négatif."
        except (ValueError, TypeError):
            errors['montant_par_eleve'] = "Le montant par élève doit être un nombre valide."
        
        # Si des erreurs sont détectées, afficher les messages d'erreur
        if errors:
            for field, error in errors.items():
                messages.error(request, error)
            return redirect(f'/school_admin/etablissements/detaille_etablissement?id={etablissement_id}')
        
        try:
            # Récupération des données du formulaire
            data = {
                'nom': request.POST.get('nom', ''),
                'type_etablissement': request.POST.get('type_etablissement', ''),
                'adresse': request.POST.get('adresse', ''),
                'ville': request.POST.get('ville', ''),
                'pays': request.POST.get('pays', ''),
                'telephone': request.POST.get('telephone', ''),
                'email': request.POST.get('email', ''),
                'site_web': request.POST.get('site_web', ''),
                'actif': bool(request.POST.get('actif', False)),
                'type_facturation': request.POST.get('type_facturation', ''),
                'montant_par_eleve': montant_par_eleve,
                
                # Modules de base
                'module_gestion_eleves': bool(request.POST.get('module_gestion_eleves', False)),
                'module_notes_evaluations': bool(request.POST.get('module_notes_evaluations', False)),
                'module_emploi_temps': bool(request.POST.get('module_emploi_temps', False)),
                'module_gestion_personnel': bool(request.POST.get('module_gestion_personnel', False)),
                
                # Modules premium
                'module_surveillance': bool(request.POST.get('module_surveillance', False)),
                'module_communication': bool(request.POST.get('module_communication', False)),
                'module_orientation': bool(request.POST.get('module_orientation', False)),
                'module_formation': bool(request.POST.get('module_formation', False)),
                
                # Modules optionnels
                'module_transport_scolaire': bool(request.POST.get('module_transport_scolaire', False)),
                'module_cantine': bool(request.POST.get('module_cantine', False)),
                'module_bibliotheque': bool(request.POST.get('module_bibliotheque', False)),
                'module_sante': bool(request.POST.get('module_sante', False)),
                'module_activites': bool(request.POST.get('module_activites', False)),
                'module_comptabilite': bool(request.POST.get('module_comptabilite', False)),
                'module_censeurs': bool(request.POST.get('module_censeurs', False)),
            }
            
            # Mise à jour de l'établissement
            etablissement.nom = data['nom']
            etablissement.type_etablissement = data['type_etablissement']
            
            # Traitement de l'adresse (peut contenir ville et pays)
            if ',' in data['adresse']:
                parts = data['adresse'].split(',')
                etablissement.adresse = parts[0].strip()
                if len(parts) > 1:
                    etablissement.ville = parts[1].strip()
                if len(parts) > 2:
                    etablissement.pays = parts[2].strip()
            else:
                etablissement.adresse = data['adresse']
            
            # Mise à jour des autres champs
            etablissement.telephone = data['telephone']
            etablissement.email = data['email']
            etablissement.site_web = data['site_web']
            etablissement.actif = data['actif']
            
            # Mise à jour des champs de facturation
            etablissement.type_facturation = data['type_facturation']
            etablissement.montant_par_eleve = data['montant_par_eleve']
            
            # Mise à jour des modules
            etablissement.module_gestion_eleves = data['module_gestion_eleves']
            etablissement.module_notes_evaluations = data['module_notes_evaluations']
            etablissement.module_emploi_temps = data['module_emploi_temps']
            etablissement.module_gestion_personnel = data['module_gestion_personnel']
            
            etablissement.module_surveillance = data['module_surveillance']
            etablissement.module_communication = data['module_communication']
            etablissement.module_orientation = data['module_orientation']
            etablissement.module_formation = data['module_formation']
            
            etablissement.module_transport_scolaire = data['module_transport_scolaire']
            etablissement.module_cantine = data['module_cantine']
            etablissement.module_bibliotheque = data['module_bibliotheque']
            etablissement.module_sante = data['module_sante']
            etablissement.module_activites = data['module_activites']
            etablissement.module_comptabilite = data['module_comptabilite']
            etablissement.module_censeurs = data['module_censeurs']
            
            # Enregistrement des modifications
            etablissement.save()
            
            messages.success(request, f"Les informations de l'établissement {etablissement.nom} ont été mises à jour avec succès.")
            
        except Exception as e:
            messages.error(request, f"Une erreur s'est produite lors de la mise à jour : {str(e)}")
    
    # Redirection vers la page de détail avec le nom d'URL
    from django.urls import reverse
    return redirect(reverse('school_admin:detaille_etablissement') + f'?id={etablissement_id}')


def message_etablissement(request):
    """
    Messages des établissements (protégé)
    """
    return render(request, 'school_admin/etablissements/message_etablissement.html')


def detail_message(request):
    """
    Détails d'un message (protégé)
    """
    return render(request, 'school_admin/etablissements/detaille_message.html')


def annonces(request):
    """
    Gestion des annonces (protégé)
    """
    return render(request, 'school_admin/annonces.html')





def parametres(request):
    """
    Paramètres du système (protégé)
    """
    return render(request, 'school_admin/profil_admin.html')



def management_equipes(request):
    """
    Gestion des équipes
    """
    
    # Récupérer tous les utilisateurs sauf les administrateurs
    all_team_members = CompteUser.objects.exclude(fonction='administrateur')
    
    # Récupérer directement depuis la base de données toutes les fonctions qui existent
    # et compter le nombre d'utilisateurs pour chaque fonction
    from django.db.models import Count
    
    # Récupérer toutes les fonctions distinctes qui existent dans la base de données
    # Convertir en liste immédiatement pour éviter les problèmes de lazy evaluation
    fonctions_distinctes = list(all_team_members.exclude(
        fonction__isnull=True
    ).exclude(
        fonction=''
    ).values_list('fonction', flat=True).distinct())
    
    # Fonction helper pour obtenir l'icône et la classe CSS selon la fonction
    def get_fonction_icon_class(fonction_code):
        """Retourne l'icône et la classe CSS pour une fonction donnée"""
        icons_map = {
            'commercial': ('fas fa-handshake', 'commercial'),
            'developpeur': ('fas fa-code', 'developer'),
            'comptable': ('fas fa-calculator', 'accountant'),
            'ressources humaines': ('fas fa-users-cog', 'hr'),
            'marketing': ('fas fa-bullhorn', 'marketing'),
            'support': ('fas fa-headset', 'support'),
        }
        return icons_map.get(fonction_code, ('fas fa-user', 'default'))
    
    # Construire la liste des statistiques en comptant directement chaque fonction
    # Cette méthode est plus fiable que la requête groupée
    team_stats_list = []
    fonction_choices_dict = dict(CompteUser.FONCTION_CHOICES)
    
    # Pour chaque fonction distincte trouvée dans la base, compter directement
    for fonction_code in fonctions_distinctes:
        # Compter directement le nombre d'utilisateurs avec cette fonction
        count = all_team_members.filter(fonction=fonction_code).count()
        
        # Ajouter uniquement si count > 0
        if count > 0:
            # Récupérer le label depuis FONCTION_CHOICES
            label = fonction_choices_dict.get(fonction_code, fonction_code)
            
            # Récupérer l'icône et la classe CSS
            icon, css_class = get_fonction_icon_class(fonction_code)
            
            team_stats_list.append({
                'fonction': fonction_code,
                'count': count,
                'icon': icon,
                'class': css_class,
                'label': label
            })
    
    # Trier la liste par fonction pour un affichage cohérent
    team_stats_list.sort(key=lambda x: x['fonction'])
    
    # Récupérer tous les utilisateurs sauf les administrateurs pour l'affichage (avec filtres)
    team_members = all_team_members.order_by('nom', 'prenom')
    
    # Options pour les filtres
    team_member_roles = CompteUser.FONCTION_CHOICES
    team_member_statuses = [('actif', 'Actif'), ('inactif', 'Inactif')]  # À adapter selon votre logique
    team_member_departments = CompteUser.DEPARTEMENT_CHOICES
    
    # Pagination
    paginator = Paginator(team_members, 12)  # 12 membres par page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Informations de pagination pour le template
    pagination = {
        'current_page': page_obj.number,
        'total_pages': paginator.num_pages,
        'has_previous': page_obj.has_previous(),
        'has_next': page_obj.has_next(),
        'previous_page': page_obj.previous_page_number() if page_obj.has_previous() else None,
        'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        'start_index': page_obj.start_index(),
        'end_index': page_obj.end_index(),
        'total_items': paginator.count,
    }
    
    # Filtres de recherche
    search_query = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    department_filter = request.GET.get('department', '')
    
    # Appliquer les filtres
    if search_query:
        team_members = team_members.filter(
            models.Q(nom__icontains=search_query) | 
            models.Q(prenom__icontains=search_query) |
            models.Q(email__icontains=search_query)
        )
    
    if role_filter:
        team_members = team_members.filter(fonction=role_filter)
    
    if department_filter:
        team_members = team_members.filter(departement=department_filter)
    
    if status_filter:
        if status_filter == 'actif':
            team_members = team_members.filter(is_active=True)
        elif status_filter == 'inactif':
            team_members = team_members.filter(is_active=False)
    
    # Re-paginer après filtrage
    paginator = Paginator(team_members, 12)
    page_obj = paginator.get_page(page_number)
    
    # Récupérer les activités globales des commerciaux
    from ..model.prospection_model import Prospection
    from ..model.rendez_vous_model import RendezVous
    from ..model.note_commercial_model import NoteCommercial
    from ..model.compte_rendu_model import CompteRendu
    from django.utils import timezone
    
    # Récupérer toutes les activités des commerciaux
    global_activities = []
    
    # Ajouter les établissements récents
    etablissements_globaux = Prospection.objects.filter(
        cree_par__fonction='commercial',
        actif=True
    ).order_by('-date_creation')[:20]
    
    for etablissement in etablissements_globaux:
        global_activities.append({
            'type': 'prospect',
            'title': f'Nouveau prospect ajouté',
            'description': f'{etablissement.nom_etablissement} - {etablissement.ville_etablissement}',
            'date': etablissement.date_creation,
            'icon': 'fas fa-user-plus',
            'color': 'success',
            'commercial': etablissement.cree_par.nom_complet if etablissement.cree_par else 'Inconnu',
            'etablissement': etablissement.nom_etablissement
        })
    
    # Ajouter les rendez-vous récents
    rendez_vous_globaux = RendezVous.objects.filter(
        etablissement__cree_par__fonction='commercial',
        etablissement__actif=True,
        actif=True
    ).order_by('-date_creation')[:20]
    
    for rdv in rendez_vous_globaux:
        global_activities.append({
            'type': 'rendez_vous',
            'title': f'Rendez-vous programmé',
            'description': f'{rdv.get_type_rdv_display()} - {rdv.etablissement.nom_etablissement}',
            'date': rdv.date_creation,
            'icon': 'fas fa-calendar',
            'color': 'info',
            'commercial': rdv.cree_par.nom_complet if rdv.cree_par else 'Inconnu',
            'etablissement': rdv.etablissement.nom_etablissement
        })
    
    # Ajouter les comptes rendus récents
    comptes_rendus_globaux = CompteRendu.objects.filter(
        etablissement__cree_par__fonction='commercial',
        etablissement__actif=True,
        actif=True
    ).order_by('-date_creation')[:20]
    
    for cr in comptes_rendus_globaux:
        global_activities.append({
            'type': 'compte_rendu',
            'title': f'Compte rendu créé',
            'description': f'{cr.titre} - {cr.etablissement.nom_etablissement}',
            'date': cr.date_creation,
            'icon': 'fas fa-file-alt',
            'color': 'primary',
            'commercial': cr.cree_par.nom_complet if cr.cree_par else 'Inconnu',
            'etablissement': cr.etablissement.nom_etablissement
        })
    
    # Ajouter les notes commerciales récentes
    notes_globales = NoteCommercial.objects.filter(
        etablissement__cree_par__fonction='commercial',
        etablissement__actif=True,
        actif=True
    ).order_by('-date_creation')[:20]
    
    for note in notes_globales:
        global_activities.append({
            'type': 'note',
            'title': f'Note ajoutée',
            'description': f'{note.contenu[:50]}...' if len(note.contenu) > 50 else note.contenu,
            'date': note.date_creation,
            'icon': 'fas fa-sticky-note',
            'color': 'warning',
            'commercial': note.cree_par.nom_complet if note.cree_par else 'Inconnu',
            'etablissement': note.etablissement.nom_etablissement
        })
    
    # Trier par date décroissante et prendre les 20 plus récentes
    global_activities.sort(key=lambda x: x['date'], reverse=True)
    global_activities = global_activities[:20]
    
    # Calculer les statistiques des activités commerciales
    commercial_stats = {
        'total': len(global_activities),
        'prospects': len([a for a in global_activities if a['type'] == 'prospect']),
        'rendez_vous': len([a for a in global_activities if a['type'] == 'rendez_vous']),
        'comptes_rendus': len([a for a in global_activities if a['type'] == 'compte_rendu']),
        'notes': len([a for a in global_activities if a['type'] == 'note'])
    }
    
    # Données statiques pour les activités comptables
    accounting_activities = [
        {
            'id': 'ACC-001',
            'type': 'facture',
            'title': 'Facture créée',
            'description': 'Facture #F2024-001 pour Lycée Saint-Pierre - Montant: 15,000€',
            'date': timezone.now() - timedelta(hours=2),
            'icon': 'fas fa-file-invoice',
            'color': 'success',
            'user': 'Sophie Laurent',
            'amount': 15000
        },
        {
            'id': 'ACC-002',
            'type': 'paiement',
            'title': 'Paiement reçu',
            'description': 'Paiement de 8,500€ reçu de Collège Victor Hugo',
            'date': timezone.now() - timedelta(hours=4),
            'icon': 'fas fa-credit-card',
            'color': 'info',
            'user': 'Pierre Martin',
            'amount': 8500
        },
        {
            'id': 'ACC-003',
            'type': 'rapport',
            'title': 'Rapport mensuel généré',
            'description': 'Rapport financier du mois de septembre 2024',
            'date': timezone.now() - timedelta(days=1),
            'icon': 'fas fa-chart-bar',
            'color': 'primary',
            'user': 'Marie Dubois',
            'amount': None
        },
        {
            'id': 'ACC-004',
            'type': 'budget',
            'title': 'Budget mis à jour',
            'description': 'Budget Q4 2024 - Allocation: 50,000€',
            'date': timezone.now() - timedelta(days=2),
            'icon': 'fas fa-wallet',
            'color': 'warning',
            'user': 'Sophie Laurent',
            'amount': 50000
        },
        {
            'id': 'ACC-005',
            'type': 'facture',
            'title': 'Facture envoyée',
            'description': 'Facture #F2024-002 pour École Primaire Les Lilas - Montant: 12,500€',
            'date': timezone.now() - timedelta(days=3),
            'icon': 'fas fa-file-invoice',
            'color': 'success',
            'user': 'Pierre Martin',
            'amount': 12500
        },
        {
            'id': 'ACC-006',
            'type': 'paiement',
            'title': 'Paiement en attente',
            'description': 'Paiement de 22,000€ en attente de validation',
            'date': timezone.now() - timedelta(days=4),
            'icon': 'fas fa-clock',
            'color': 'warning',
            'user': 'Marie Dubois',
            'amount': 22000
        },
        {
            'id': 'ACC-007',
            'type': 'rapport',
            'title': 'Analyse des coûts',
            'description': 'Analyse détaillée des coûts opérationnels Q3',
            'date': timezone.now() - timedelta(days=5),
            'icon': 'fas fa-chart-line',
            'color': 'primary',
            'user': 'Sophie Laurent',
            'amount': None
        },
        {
            'id': 'ACC-008',
            'type': 'budget',
            'title': 'Révision budgétaire',
            'description': 'Révision du budget marketing - Nouveau montant: 25,000€',
            'date': timezone.now() - timedelta(days=6),
            'icon': 'fas fa-edit',
            'color': 'info',
            'user': 'Pierre Martin',
            'amount': 25000
        },
        {
            'id': 'ACC-009',
            'type': 'facture',
            'title': 'Facture payée',
            'description': 'Facture #F2024-003 marquée comme payée - Montant: 18,750€',
            'date': timezone.now() - timedelta(days=7),
            'icon': 'fas fa-check-circle',
            'color': 'success',
            'user': 'Marie Dubois',
            'amount': 18750
        },
        {
            'id': 'ACC-010',
            'type': 'paiement',
            'title': 'Remboursement effectué',
            'description': 'Remboursement de 3,200€ effectué pour annulation de service',
            'date': timezone.now() - timedelta(days=8),
            'icon': 'fas fa-undo',
            'color': 'warning',
            'user': 'Sophie Laurent',
            'amount': 3200
        }
    ]
    
    # Calculer les statistiques des activités comptables
    accounting_stats = {
        'total': len(accounting_activities),
        'factures': len([a for a in accounting_activities if a['type'] == 'facture']),
        'paiements': len([a for a in accounting_activities if a['type'] == 'paiement']),
        'rapports': len([a for a in accounting_activities if a['type'] == 'rapport']),
        'budgets': len([a for a in accounting_activities if a['type'] == 'budget'])
    }
    
    context = {
        'team_members': page_obj,
        'team_stats_list': team_stats_list,  # Liste dynamique des statistiques par fonction
        'team_member_roles': team_member_roles,
        'team_member_statuses': team_member_statuses,
        'team_member_departments': team_member_departments,
        'pagination': pagination,
        'search_query': search_query,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'department_filter': department_filter,
        'global_activities': global_activities,
        'accounting_activities': accounting_activities,
        'commercial_stats': commercial_stats,
        'accounting_stats': accounting_stats,
    }
    
    return render(request, 'school_admin/management_equipes.html', context)

def commercial_profile(request, commercial_id):
    """
    Profil détaillé d'un commercial avec toutes ses activités
    """
    from ..model.prospection_model import Prospection
    from ..model.rendez_vous_model import RendezVous
    from ..model.note_commercial_model import NoteCommercial
    from ..model.compte_rendu_model import CompteRendu
    from django.db.models import Count, Q
    from django.utils import timezone
    
    try:
        # Récupérer le commercial
        commercial = CompteUser.objects.get(id=commercial_id, fonction='commercial')
    except CompteUser.DoesNotExist:
        messages.error(request, "Commercial non trouvé.")
        return redirect('school_admin:management_equipes')
    
    # Récupérer les données du commercial
    etablissements = Prospection.objects.filter(cree_par=commercial, actif=True)
    rendez_vous = RendezVous.objects.filter(etablissement__cree_par=commercial, actif=True)
    notes_commerciales = NoteCommercial.objects.filter(etablissement__cree_par=commercial, actif=True)
    comptes_rendus = CompteRendu.objects.filter(etablissement__cree_par=commercial, actif=True)
    
    # Statistiques générales
    total_prospects = etablissements.count()
    prospects_actifs = etablissements.filter(statut_etablissement__in=['prospect', 'contacte', 'rendez_vous', 'negociation', 'devis_envoye']).count()
    contrats_signes = etablissements.filter(statut_etablissement='contrat_signe').count()
    
    # Calculer le taux de conversion
    taux_conversion = 0
    if total_prospects > 0:
        taux_conversion = round((contrats_signes / total_prospects) * 100, 1)
    
    # Objectif mensuel (simulé - à configurer selon vos besoins)
    objectif_mensuel = 50000
    objectif_atteint = contrats_signes * 25000  # Estimation 25k par contrat
    
    stats = {
        'total_prospects': total_prospects,
        'prospects_actifs': prospects_actifs,
        'contrats_signes': contrats_signes,
        'revenus_generes': objectif_atteint,
        'taux_conversion': taux_conversion,
        'objectif_mensuel': objectif_mensuel,
        'objectif_atteint': objectif_atteint,
    }
    
    # Établissements récents (4 max pour la vue d'ensemble)
    etablissements_recents = list(etablissements.order_by('-date_creation')[:4])
    
    # Rendez-vous programmés (3 max pour la vue d'ensemble)
    # Pour le test, on prend tous les rendez-vous, pas seulement ceux à venir
    rendez_vous_programmes = list(rendez_vous.order_by('date_rdv', 'heure_rdv')[:3])
    
    # Notes commerciales (2 max pour la vue d'ensemble)
    notes_recents = list(notes_commerciales.order_by('-date_creation')[:2])
    
    # Debug: Afficher le nombre d'éléments trouvés
    print(f"Debug - Établissements trouvés: {len(etablissements_recents)}")
    print(f"Debug - Rendez-vous trouvés: {len(rendez_vous_programmes)}")
    print(f"Debug - Notes trouvées: {len(notes_recents)}")
    
    # Activités récentes - toutes les activités sans limite
    recent_activities = []
    
    # Ajouter tous les établissements récents
    for etablissement in etablissements.order_by('-date_creation'):
        recent_activities.append({
            'type': 'prospect',
            'title': f'Nouveau prospect ajouté',
            'description': f'{etablissement.nom_etablissement} - {etablissement.ville_etablissement}',
            'date': etablissement.date_creation,
            'icon': 'fas fa-user-plus',
            'color': 'success'
        })
    
    # Ajouter tous les rendez-vous récents
    for rdv in rendez_vous.order_by('-date_creation'):
        recent_activities.append({
            'type': 'rendez_vous',
            'title': f'Rendez-vous programmé',
            'description': f'{rdv.get_type_rdv_display()} - {rdv.etablissement.nom_etablissement}',
            'date': rdv.date_creation,
            'icon': 'fas fa-calendar',
            'color': 'info'
        })
    
    # Ajouter tous les comptes rendus récents
    for cr in comptes_rendus.order_by('-date_creation'):
        recent_activities.append({
            'type': 'compte_rendu',
            'title': f'Compte rendu créé',
            'description': f'{cr.titre} - {cr.etablissement.nom_etablissement}',
            'date': cr.date_creation,
            'icon': 'fas fa-file-alt',
            'color': 'primary'
        })
    
    # Ajouter toutes les notes commerciales
    for note in notes_commerciales.order_by('-date_creation'):
        recent_activities.append({
            'type': 'note',
            'title': f'Note ajoutée',
            'description': f'{note.contenu[:50]}...' if len(note.contenu) > 50 else note.contenu,
            'date': note.date_creation,
            'icon': 'fas fa-sticky-note',
            'color': 'warning'
        })
    
    # Trier par date décroissante
    recent_activities.sort(key=lambda x: x['date'], reverse=True)
    
    # Séparer les activités par type pour les sections
    activities_prospects = [a for a in recent_activities if a['type'] == 'prospect']
    activities_rendez_vous = [a for a in recent_activities if a['type'] == 'rendez_vous']
    activities_comptes_rendus = [a for a in recent_activities if a['type'] == 'compte_rendu']
    activities_notes = [a for a in recent_activities if a['type'] == 'note']
    
    # Notes pour la vue d'ensemble
    notes_vue_ensemble = []
    for note in notes_recents:
        notes_vue_ensemble.append({
            'author': note.cree_par.nom_complet if note.cree_par else 'Système',
            'content': note.contenu,
            'date': note.date_creation,
            'type': 'positive'
        })
    
    # Tickets de prise en charge (données statiques provisoires)
    tickets_prise_charge = [
        {
            'id': 'TKT-001',
            'etablissement': 'Lycée Saint-Pierre',
            'sujet': 'Demande de devis pour solution éducative',
            'priorite': 'haute',
            'statut': 'en_cours',
            'date_creation': timezone.now() - timedelta(days=2),
            'date_prise_charge': timezone.now() - timedelta(days=1),
            'description': 'L\'établissement souhaite obtenir un devis détaillé pour notre solution de gestion scolaire.'
        },
        {
            'id': 'TKT-002',
            'etablissement': 'Collège Victor Hugo',
            'sujet': 'Problème technique avec la plateforme',
            'priorite': 'urgente',
            'statut': 'resolu',
            'date_creation': timezone.now() - timedelta(days=5),
            'date_prise_charge': timezone.now() - timedelta(days=4),
            'description': 'Les utilisateurs ne peuvent pas accéder à leurs comptes depuis hier.'
        },
        {
            'id': 'TKT-003',
            'etablissement': 'École Primaire Les Lilas',
            'sujet': 'Formation des enseignants',
            'priorite': 'normale',
            'statut': 'en_attente',
            'date_creation': timezone.now() - timedelta(days=1),
            'date_prise_charge': None,
            'description': 'Demande de formation pour les nouveaux enseignants sur l\'utilisation de la plateforme.'
        }
    ]
    
    context = {
        'commercial': commercial,
        'stats': stats,
        'recent_activities': recent_activities,
        'activities_prospects': activities_prospects,
        'activities_rendez_vous': activities_rendez_vous,
        'activities_comptes_rendus': activities_comptes_rendus,
        'activities_notes': activities_notes,
        'etablissements_recents': etablissements_recents,
        'rendez_vous_programmes': rendez_vous_programmes,
        'notes_vue_ensemble': notes_vue_ensemble,
        'tickets_prise_charge': tickets_prise_charge,
    }
    
    return render(request, 'school_admin/commercial_profile.html', context)

def add_team_member(request):
    """
    Ajouter un membre d'équipe
    """
    return render(request, 'school_admin/add_team_member.html')


@login_required
def team_member_profile(request, member_id):
    """
    Afficher le profil détaillé d'un membre de l'équipe
    """
    # Vérifier que l'utilisateur est un administrateur
    if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction') or request.user.fonction != 'administrateur':
        messages.error(request, "Accès non autorisé. Vous devez être administrateur pour accéder à cette page.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        member = CompteUser.objects.get(id=member_id)
    except CompteUser.DoesNotExist:
        messages.error(request, "Membre de l'équipe non trouvé.")
        return redirect('school_admin:management_equipes')
    
    # Ne pas permettre de voir le profil d'un administrateur
    if member.fonction == 'administrateur':
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:management_equipes')
    
    context = {
        'member': member,
        'fonction_choices': CompteUser.FONCTION_CHOICES,
        'departement_choices': CompteUser.DEPARTEMENT_CHOICES,
    }
    
    return render(request, 'school_admin/team_member_profile.html', context)


@login_required
def update_team_member(request, member_id):
    """
    Modifier les informations d'un membre de l'équipe
    """
    # Vérifier que l'utilisateur est un administrateur
    if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction') or request.user.fonction != 'administrateur':
        messages.error(request, "Accès non autorisé. Vous devez être administrateur pour effectuer cette action.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        member = CompteUser.objects.get(id=member_id)
    except CompteUser.DoesNotExist:
        messages.error(request, "Membre de l'équipe non trouvé.")
        return redirect('school_admin:management_equipes')
    
    # Ne pas permettre de modifier un administrateur
    if member.fonction == 'administrateur':
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:management_equipes')
    
    if request.method == 'POST':
        errors = {}
        
        # Validation des champs obligatoires
        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        email = request.POST.get('email', '').strip()
        username = request.POST.get('username', '').strip()
        fonction = request.POST.get('fonction', '').strip()
        departement = request.POST.get('departement', '').strip()
        
        if not nom:
            errors['nom'] = "Le nom est obligatoire."
        if not prenom:
            errors['prenom'] = "Le prénom est obligatoire."
        if not email:
            errors['email'] = "L'email est obligatoire."
        elif not '@' in email:
            errors['email'] = "L'email n'est pas valide."
        if not username:
            errors['username'] = "Le nom d'utilisateur est obligatoire."
        if not fonction:
            errors['fonction'] = "La fonction est obligatoire."
        if not departement:
            errors['departement'] = "Le département est obligatoire."
        
        # Vérifier que l'email n'est pas déjà utilisé par un autre utilisateur
        if email and email != member.email:
            if CompteUser.objects.filter(email=email).exclude(id=member.id).exists():
                errors['email'] = "Cet email est déjà utilisé par un autre utilisateur."
        
        # Vérifier que le username n'est pas déjà utilisé par un autre utilisateur
        if username and username != member.username:
            if CompteUser.objects.filter(username=username).exclude(id=member.id).exists():
                errors['username'] = "Ce nom d'utilisateur est déjà utilisé par un autre utilisateur."
        
        # Vérifier que la fonction est valide
        valid_fonctions = dict(CompteUser.FONCTION_CHOICES).keys()
        if fonction and fonction not in valid_fonctions:
            errors['fonction'] = "La fonction n'est pas valide."
        
        # Vérifier que le département est valide
        valid_departements = dict(CompteUser.DEPARTEMENT_CHOICES).keys()
        if departement and departement not in valid_departements:
            errors['departement'] = "Le département n'est pas valide."
        
        # Validation de la date de naissance
        date_naissance = None
        if request.POST.get('date_naissance'):
            try:
                from datetime import datetime
                date_naissance = datetime.strptime(request.POST.get('date_naissance'), '%Y-%m-%d').date()
                if date_naissance > datetime.today().date():
                    errors['date_naissance'] = "La date de naissance ne peut pas être dans le futur."
            except ValueError:
                errors['date_naissance'] = "Format de date invalide."
        
        # Validation du salaire
        salaire = None
        salaire_str = request.POST.get('salaire', '').strip()
        if salaire_str:
            try:
                from decimal import Decimal, InvalidOperation
                salaire = Decimal(salaire_str)
                if salaire < 0:
                    errors['salaire'] = "Le salaire ne peut pas être négatif."
            except (ValueError, InvalidOperation):
                errors['salaire'] = "Le salaire doit être un nombre valide."
        
        # Si des erreurs sont détectées, afficher les messages d'erreur
        if errors:
            for field, error in errors.items():
                messages.error(request, error)
        else:
            try:
                # Mise à jour des informations
                member.nom = nom
                member.prenom = prenom
                member.email = email
                member.username = username
                member.fonction = fonction
                member.departement = departement
                member.telephone = request.POST.get('telephone', '').strip()
                
                if date_naissance:
                    member.date_naissance = date_naissance
                
                # Mise à jour du salaire
                if salaire is not None:
                    member.salaire = salaire
                elif salaire_str == '':
                    # Si le champ est vide, mettre à None
                    member.salaire = None
                
                # Gestion de la photo
                if 'photo' in request.FILES:
                    photo = request.FILES['photo']
                    # Valider que c'est une image
                    if photo.content_type.startswith('image/'):
                        member.photo = photo
                    else:
                        messages.error(request, "Le fichier doit être une image.")
                
                member.save()
                messages.success(request, f"Les informations de {member.nom_complet} ont été mises à jour avec succès.")
                
            except Exception as e:
                messages.error(request, f"Une erreur s'est produite lors de la mise à jour : {str(e)}")
    
    return redirect('school_admin:team_member_profile', member_id=member_id)


@login_required
def toggle_team_member_status(request, member_id):
    """
    Activer ou désactiver un membre de l'équipe
    """
    # Vérifier que l'utilisateur est un administrateur
    if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction') or request.user.fonction != 'administrateur':
        messages.error(request, "Accès non autorisé. Vous devez être administrateur pour effectuer cette action.")
        return redirect('school_admin:connexion_compte_user')
    
    if request.method == 'POST':
        try:
            member = CompteUser.objects.get(id=member_id)
        except CompteUser.DoesNotExist:
            messages.error(request, "Membre de l'équipe non trouvé.")
            return redirect('school_admin:management_equipes')
        
        # Ne pas permettre de désactiver un administrateur
        if member.fonction == 'administrateur':
            messages.error(request, "Vous ne pouvez pas désactiver un administrateur.")
            return redirect('school_admin:management_equipes')
        
        # Ne pas permettre de désactiver soi-même
        if member.id == request.user.id:
            messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
            return redirect('school_admin:management_equipes')
        
        try:
            # Inverser le statut
            member.is_active = not member.is_active
            member.save()
            
            status_text = "activé" if member.is_active else "désactivé"
            messages.success(request, f"{member.nom_complet} a été {status_text} avec succès.")
            
        except Exception as e:
            messages.error(request, f"Une erreur s'est produite lors de la modification du statut : {str(e)}")
    
    # Rediriger vers la page d'origine
    referer = request.META.get('HTTP_REFERER', None)
    if referer and 'team_member_profile' in referer:
        return redirect('school_admin:team_member_profile', member_id=member_id)
    else:
        return redirect('school_admin:management_equipes')


@login_required
def delete_team_member(request, member_id):
    """
    Supprimer un membre de l'équipe
    """
    # Vérifier que l'utilisateur est un administrateur
    if not isinstance(request.user, CompteUser) or not hasattr(request.user, 'fonction') or request.user.fonction != 'administrateur':
        messages.error(request, "Accès non autorisé. Vous devez être administrateur pour effectuer cette action.")
        return redirect('school_admin:connexion_compte_user')
    
    if request.method == 'POST':
        try:
            member = CompteUser.objects.get(id=member_id)
        except CompteUser.DoesNotExist:
            messages.error(request, "Membre de l'équipe non trouvé.")
            return redirect('school_admin:management_equipes')
        
        # Ne pas permettre de supprimer un administrateur
        if member.fonction == 'administrateur':
            messages.error(request, "Vous ne pouvez pas supprimer un administrateur.")
            return redirect('school_admin:management_equipes')
        
        # Ne pas permettre de supprimer soi-même
        if member.id == request.user.id:
            messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
            return redirect('school_admin:management_equipes')
        
        try:
            member_name = member.nom_complet
            member.delete()
            messages.success(request, f"{member_name} a été supprimé avec succès.")
            
        except Exception as e:
            messages.error(request, f"Une erreur s'est produite lors de la suppression : {str(e)}")
    
    return redirect('school_admin:management_equipes')

