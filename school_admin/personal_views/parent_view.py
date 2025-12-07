"""
Vues pour l'espace parent
Les parents peuvent consulter toutes les informations de leurs enfants
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.urls import reverse
from school_admin.model.parent_model import Parent
from school_admin.model.eleve_model import Eleve
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.demande_liaison_model import DemandeLiaisonParent
from school_admin.model.notification_parent_model import NotificationParent
from school_admin.model.convocation_model import Convocation
from ..utils.session_utils import get_session_active
from ..model.inscription_eleve_model import InscriptionEleve
import logging

logger = logging.getLogger(__name__)


def get_classe_eleve_active(eleve, annee_scolaire_active, etablissement=None):
    """
    Récupère la classe de l'élève pour l'année scolaire active depuis InscriptionEleve.
    Retourne None si l'élève n'est pas inscrit pour cette année.
    
    Args:
        eleve: L'objet Eleve
        annee_scolaire_active: L'objet AnneeScolaire active
        etablissement: L'établissement (optionnel, utilise eleve.etablissement si non fourni)
    
    Returns:
        Classe ou None
    """
    if not annee_scolaire_active:
        # Fallback sur eleve.classe si pas d'année scolaire active
        return eleve.classe
    
    if not etablissement:
        etablissement = eleve.etablissement
    
    if not etablissement:
        return eleve.classe
    
    try:
        inscription = InscriptionEleve.objects.filter(
            eleve=eleve,
            annee_scolaire=annee_scolaire_active,
            etablissement=etablissement
        ).select_related('classe').first()
        
        if inscription and inscription.classe:
            return inscription.classe
    except Exception:
        pass
    
    # Fallback sur eleve.classe si aucune inscription trouvée
    return eleve.classe


def dashboard_parent(request):
    """
    Tableau de bord principal du parent
    Affiche la liste de ses enfants
    """
    print(f"\n[DASHBOARD PARENT] User: {request.user}, Type: {type(request.user).__name__}, Authenticated: {request.user.is_authenticated}")
    logger.info(f"Dashboard parent - User: {request.user}, Type: {type(request.user).__name__}, Authenticated: {request.user.is_authenticated}")
    
    # Vérifier que l'utilisateur est bien un parent
    if not isinstance(request.user, Parent):
        print(f"[DASHBOARD PARENT] Accès refusé - Type: {type(request.user).__name__}")
        logger.warning(f"Accès refusé au dashboard parent - Type d'utilisateur: {type(request.user).__name__}")
        messages.error(request, "Accès non autorisé. Cette page est réservée aux parents.")
        return redirect('school_admin:connexion_compte_user')
    
    parent = request.user
    
    # Récupérer l'année scolaire active
    annee_scolaire_active = None
    if parent.etablissement:
        annee_scolaire_active = get_session_active(request, parent.etablissement)
    
    # Préparer les notifications récentes pour le parent
    notifications_queryset = NotificationParent.objects.filter(parent=parent)
    if annee_scolaire_active:
        notifications_queryset = notifications_queryset.filter(annee_scolaire=annee_scolaire_active)
    notifications_queryset = notifications_queryset.select_related('eleve').order_by('-date_creation')[:30]
    notifications_list = list(notifications_queryset)
    notifications_map = {}
    for notification in notifications_list:
        notifications_map.setdefault(notification.eleve_id, []).append(notification)
    # Compter les notifications non lues (utiliser lu=False pour être cohérent avec le context processor)
    notifications_non_lues_query = NotificationParent.objects.filter(
        parent=parent,
        lu=False
    )
    if annee_scolaire_active:
        notifications_non_lues_query = notifications_non_lues_query.filter(annee_scolaire=annee_scolaire_active)
    notifications_parent_non_lues = notifications_non_lues_query.count()
    
    # Récupérer tous les enfants liés à ce parent
    liens_familiaux = LienFamilial.objects.filter(
        parent=parent,
        actif=True,
        statut='valide'
    ).select_related('eleve__classe', 'eleve__etablissement')
    
    print(f"[DASHBOARD PARENT] Nombre de liens trouvés: {liens_familiaux.count()}")
    
    # Récupérer les IDs des élèves qui ont une demande approuvée
    enfants = []
    for lien in liens_familiaux:
        eleve = lien.eleve
        
        if eleve and eleve.actif:
            try:
                # Récupérer les statistiques de présence
                from school_admin.model.presence_model import Presence
                from django.db.models import Q
                
                # Récupérer l'année scolaire active pour l'élève
                eleve_annee_scolaire_active = None
                if eleve.etablissement:
                    eleve_annee_scolaire_active = get_session_active(request, eleve.etablissement)
                
                # Récupérer la classe de l'élève pour l'année scolaire active
                classe_eleve_active = get_classe_eleve_active(eleve, eleve_annee_scolaire_active, eleve.etablissement)
                
                # Statistiques de présence et absences
                presences = Presence.objects.filter(eleve=eleve)
                if eleve_annee_scolaire_active:
                    presences = presences.filter(annee_scolaire=eleve_annee_scolaire_active)
                total_presences = presences.filter(statut='present').count()
                total_absences = presences.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
                
                # Calculer l'âge de l'enfant
                age = None
                if eleve.date_naissance:
                    from datetime import date
                    today = date.today()
                    age = today.year - eleve.date_naissance.year
                    if (today.month, today.day) < (eleve.date_naissance.month, eleve.date_naissance.day):
                        age -= 1
                
                enfants.append({
                    'eleve': eleve,
                    'lien': lien.get_type_lien_display(),
                    'total_presences': total_presences,
                    'total_absences': total_absences,
                    'age': age,
                    'classe': classe_eleve_active,
                })
            except Exception as e:
                print(f"[DASHBOARD PARENT] Erreur pour élève {eleve.nom_complet}: {str(e)}")
                # Récupérer l'année scolaire active pour l'élève même en cas d'erreur
                eleve_annee_scolaire_active = None
                if eleve.etablissement:
                    eleve_annee_scolaire_active = get_session_active(request, eleve.etablissement)
                
                # Récupérer la classe de l'élève pour l'année scolaire active
                classe_eleve_active = get_classe_eleve_active(eleve, eleve_annee_scolaire_active, eleve.etablissement)
                
                # Calculer l'âge même en cas d'erreur
                age = None
                if eleve.date_naissance:
                    from datetime import date
                    today = date.today()
                    age = today.year - eleve.date_naissance.year
                    if (today.month, today.day) < (eleve.date_naissance.month, eleve.date_naissance.day):
                        age -= 1
                
                # Ajouter l'enfant quand même avec des valeurs par défaut
                enfants.append({
                    'eleve': eleve,
                    'lien': lien.get_type_lien_display(),
                    'total_presences': 0,
                    'total_absences': 0,
                    'age': age,
                    'classe': classe_eleve_active,
                })

    # Attacher les notifications par enfant
    for enfant_entry in enfants:
        enfant_entry['notifications'] = notifications_map.get(enfant_entry['eleve'].id, [])
    
    # Toujours afficher le dashboard parent pour qu'il puisse choisir
    print(f"[DASHBOARD PARENT] Nombre d'enfants à afficher: {len(enfants)}")
    
    # Récupérer les données du formulaire de la session (si échec précédent)
    form_data = request.session.pop('form_data', None)
    
    # Compter les annonces destinées aux parents
    from ..model.annonce_model import Annonce
    from django.db.models import Q
    
    nombre_annonces = 0
    if parent.etablissement:
        annonces_query = Annonce.objects.filter(
            Q(etablissement=parent.etablissement) &
            Q(statut='publiee') &
            Q(actif=True) &
            (Q(destinataires__contains=['tous']) | 
             Q(destinataires__contains=['parents']))
        )
        if annee_scolaire_active:
            annonces_query = annonces_query.filter(annee_scolaire=annee_scolaire_active)
        nombre_annonces = annonces_query.count()
    
    context = {
        'parent': parent,
        'etablissement': parent.etablissement,
        'enfants': enfants,
        'nombre_enfants': len(enfants),
        'nombre_annonces': nombre_annonces,
        'today': timezone.now().date(),
        'form_data': form_data,  # Données du formulaire à réafficher
        'notifications_recents': notifications_list,
        'notifications_non_lues': notifications_parent_non_lues,
        'notifications_parent_non_lues': notifications_parent_non_lues,
        'current_url': request.get_full_path(),
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/parent/dashboard_parent.html', context)


def dashboard_enfant(request, eleve_id):
    """
    Sélection d'un enfant par le parent
    Stocke les IDs en session et redirige vers le dashboard de l'enfant
    """
    print(f"\n[DASHBOARD ENFANT] User: {request.user}, Eleve ID: {eleve_id}")
    
    # Vérifier que l'utilisateur est bien un parent
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    parent = request.user
    
    # Vérifier que l'élève est bien l'enfant de ce parent
    lien = LienFamilial.objects.filter(
        parent=parent,
        eleve_id=eleve_id,
        actif=True,
        statut='valide'
    ).select_related('eleve').first()
    
    if not lien:
        messages.error(request, "Vous n'avez pas accès aux informations de cet élève.")
        return redirect('school_admin:dashboard_parent')
    
    eleve = lien.eleve
    
    # Stocker les IDs dans la session pour permettre la consultation
    request.session['parent_id'] = parent.id
    request.session['parent_matricule'] = parent.matricule_parental
    request.session['eleve_consulte_id'] = eleve.id
    request.session['eleve_consulte_nom'] = eleve.nom_complet
    request.session['mode_consultation_parent'] = True
    
    print(f"[DASHBOARD ENFANT] Session créée - Parent: {parent.nom_complet}, Enfant: {eleve.nom_complet}")
    logger.info(f"Parent {parent.matricule_parental} consulte l'enfant {eleve.nom_complet} (ID: {eleve.id})")
    
    # Rediriger vers le dashboard élève
    return redirect('eleve:dashboard_eleve')


@require_POST
def marquer_notification_parent(request, notification_id):
    """Permet au parent de marquer une notification comme lue."""
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    notification = get_object_or_404(
        NotificationParent,
        id=notification_id,
        parent=request.user
    )

    notification.marquer_comme_lue()

    next_url = request.POST.get('next') or reverse('school_admin:dashboard_parent')
    messages.success(request, "Notification marquée comme lue.")
    return redirect(next_url)


def deconnexion_parent(request):
    """
    Déconnexion du parent
    Nettoie complètement la session et affiche un message de confirmation
    """
    from django.contrib.auth import logout
    from school_admin.authentication_backends import _user_type_context
    
    # Nettoyer les données de session spécifiques au parent (avant logout)
    # Note: logout() fera flush() de toute la session, mais on nettoie quand même
    # pour être explicite et éviter des problèmes si logout() échoue
    if 'parent_id' in request.session:
        del request.session['parent_id']
    if 'parent_matricule' in request.session:
        del request.session['parent_matricule']
    if 'eleve_consulte_id' in request.session:
        del request.session['eleve_consulte_id']
    if 'eleve_consulte_nom' in request.session:
        del request.session['eleve_consulte_nom']
    if 'mode_consultation_parent' in request.session:
        del request.session['mode_consultation_parent']
    
    # Nettoyer le thread-local
    if hasattr(_user_type_context, 'user_type'):
        delattr(_user_type_context, 'user_type')
    
    # Déconnecter l'utilisateur (nettoie la session avec flush())
    logout(request)
    
    # Ajouter un message de succès APRÈS logout()
    messages.success(request, "Déconnexion réussie. Vous avez été déconnecté avec succès.")
    
    return redirect('school_admin:connexion_compte_user')


def retour_selection_enfant(request):
    """
    Permet au parent de retourner au dashboard parent pour changer d'enfant
    """
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    # Nettoyer uniquement les données de consultation d'enfant
    if 'eleve_consulte_id' in request.session:
        del request.session['eleve_consulte_id']
    if 'eleve_consulte_nom' in request.session:
        del request.session['eleve_consulte_nom']
    if 'mode_consultation_parent' in request.session:
        del request.session['mode_consultation_parent']
    
    return redirect('school_admin:dashboard_parent')


def demande_liaison_enfant(request):
    """
    Traite la demande de liaison d'un parent avec un enfant
    Système simplifié : vérification uniquement du matricule et du mot de passe
    Blocage après 5 tentatives échouées pour ce matricule spécifique (tous parents confondus)
    """
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    if request.method != 'POST':
        return redirect('school_admin:dashboard_parent')
    
    parent = request.user
    matricule_eleve = request.POST.get('matricule_eleve', '').strip()
    mot_de_passe_eleve = request.POST.get('mot_de_passe_eleve', '').strip()
    
    # Stocker les données saisies dans la session pour les réafficher en cas d'échec
    request.session['form_data'] = {
        'matricule_eleve': matricule_eleve,
    }
    
    print(f"[DEMANDE LIAISON] Parent: {parent.nom_complet}, Matricule: {matricule_eleve}")
    
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent
    from django.contrib.auth.hashers import check_password
    
    try:
        # Vérifier que l'élève existe
        eleve = Eleve.objects.filter(
            matricule_eleve=matricule_eleve,
            actif=True
        ).first()
        
        # Si l'élève n'existe pas, afficher un message
        if not eleve:
            messages.error(request, "❌ Matricule incorrect. Cet élève n'est inscrit dans aucun établissement.")
            return redirect('school_admin:dashboard_parent')
        
        # Vérifier si un lien existe déjà
        lien_existant = LienFamilial.objects.filter(
            parent=parent,
            eleve=eleve,
            actif=True
        ).exists()
        
        if lien_existant:
            messages.warning(request, f"Vous êtes déjà lié à {eleve.nom_complet}.")
            # Supprimer les données du formulaire de la session
            if 'form_data' in request.session:
                del request.session['form_data']
            return redirect('school_admin:dashboard_parent')
        
        # Compter toutes les tentatives échouées pour ce matricule (tous parents confondus)
        # Compter le nombre de demandes échouées/bloquées (chaque demande = 1 tentative)
        tentatives_echec = DemandeLiaisonParent.objects.filter(
            matricule_eleve=matricule_eleve,
            statut__in=['echec', 'bloquee']
        ).count()
        
        # Vérifier si ce matricule est déjà bloqué (5 tentatives ou plus)
        if tentatives_echec >= 5:
            messages.error(request, 
                f"❌ Ce matricule a été bloqué après 5 tentatives infructueuses. "
                f"Veuillez contacter l'établissement pour débloquer la liaison.")
            logger.warning(f"Tentative de liaison sur matricule bloqué - Parent: {parent.matricule_parental}, Matricule: {matricule_eleve}")
            return redirect('school_admin:dashboard_parent')
        
        # Vérifier le mot de passe de l'élève
        if not eleve.check_password(mot_de_passe_eleve):
            # Mot de passe incorrect - enregistrer la tentative échouée
            nouvelle_tentative = tentatives_echec + 1
            
            # Récupérer l'année scolaire active
            annee_scolaire_active = None
            if eleve.etablissement:
                annee_scolaire_active = get_session_active(request, eleve.etablissement)
            
            # Créer une nouvelle demande pour enregistrer cette tentative échouée
            # (on crée toujours une nouvelle demande pour compter correctement les tentatives)
            demande = DemandeLiaisonParent.objects.create(
                parent_demandeur=parent,
                matricule_eleve=matricule_eleve,
                nom_eleve=eleve.nom,
                prenom_eleve=eleve.prenom,
                date_naissance_eleve=eleve.date_naissance,
                type_lien='tuteur',  # Type par défaut
                statut='echec',
                nombre_tentatives=1,  # Cette demande représente 1 tentative
                raison_echec="Mot de passe incorrect",
                eleve_valide=eleve,
                annee_scolaire=annee_scolaire_active
            )
            
            # Vérifier si on doit bloquer (5 tentatives atteintes)
            if nouvelle_tentative >= 5:
                demande.statut = 'bloquee'
                demande.save()
                messages.error(request, 
                    f"❌ Mot de passe incorrect. Après 5 tentatives infructueuses pour ce matricule, "
                    f"la liaison est maintenant bloquée. Veuillez contacter l'établissement.")
                logger.warning(f"Matricule bloqué après 5 tentatives - Matricule: {matricule_eleve}")
            else:
                tentatives_restantes = 5 - nouvelle_tentative
                messages.error(request, 
                    f"❌ Mot de passe incorrect. Il reste {tentatives_restantes} tentative{'s' if tentatives_restantes > 1 else ''} "
                    f"avant le blocage de ce matricule.")
            
            return redirect('school_admin:dashboard_parent')
        
        # Mot de passe correct - créer directement le lien familial
        # Récupérer l'année scolaire active
        annee_scolaire_active = None
        if eleve.etablissement:
            annee_scolaire_active = get_session_active(request, eleve.etablissement)
        
        # Déterminer le type de lien (utiliser 'tuteur' par défaut)
        type_lien = 'tuteur'
        
        # Créer le lien familial directement
        lien = LienFamilial.objects.create(
            parent=parent,
            eleve=eleve,
            type_lien=type_lien,
            statut='valide',
            est_inscripteur=False
        )
        lien.valider()
        
        # Enregistrer une demande réussie pour traçabilité
        DemandeLiaisonParent.objects.create(
            parent_demandeur=parent,
            matricule_eleve=matricule_eleve,
            nom_eleve=eleve.nom,
            prenom_eleve=eleve.prenom,
            date_naissance_eleve=eleve.date_naissance,
            type_lien=type_lien,
            statut='reussie',
            nombre_tentatives=1,
            eleve_valide=eleve,
            annee_scolaire=annee_scolaire_active
        )
        
        # Supprimer les données du formulaire de la session en cas de succès
        if 'form_data' in request.session:
            del request.session['form_data']
        
        messages.success(request, f"✅ Votre enfant {eleve.nom_complet} a été lié avec succès à votre espace !")
        logger.info(f"Liaison réussie - Parent: {parent.matricule_parental}, Élève: {eleve.matricule_eleve}")
        
        return redirect('school_admin:dashboard_parent')
        
    except Exception as e:
        print(f"[DEMANDE LIAISON] Erreur: {str(e)}")
        logger.error(f"Erreur demande liaison: {str(e)}", exc_info=True)
        messages.error(request, "Une erreur s'est produite lors du traitement de votre demande.")
        return redirect('school_admin:dashboard_parent')


def annonces_parent(request):
    """
    Affiche les annonces destinées aux parents, regroupées par établissement.
    """
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    parent = request.user

    from ..model.annonce_model import Annonce
    from django.db.models import Q
    from datetime import timedelta

    liens_valides = (
        LienFamilial.objects.filter(
            parent=parent,
            statut='valide',
            actif=True
        )
        .select_related('eleve__etablissement')
    )

    etablissements_map = {}
    for lien in liens_valides:
        eleve = lien.eleve
        etablissement = getattr(eleve, "etablissement", None)

        if not eleve or not eleve.actif or not etablissement:
            continue

        entry = etablissements_map.setdefault(
            etablissement.id,
            {
                "etablissement": etablissement,
                "eleves_ids": set(),
                "annonces": [],
            },
        )
        entry["eleves_ids"].add(eleve.id)

    if not etablissements_map:
        messages.warning(
            request,
            "Aucun établissement associé à vos enfants n'a été trouvé."
        )
        return redirect('school_admin:dashboard_parent')

    etablissements_ids = list(etablissements_map.keys())

    filtre_periode = request.GET.get('periode', '').strip()
    selected_etablissement_id = request.GET.get('etablissement')
    today = timezone.now().date()

    # Récupérer l'année scolaire active pour chaque établissement
    # On prend la première année scolaire active trouvée parmi les établissements
    annee_scolaire_active = None
    for etab_id in etablissements_ids:
        etab = next((data["etablissement"] for data in etablissements_map.values() if data["etablissement"].id == etab_id), None)
        if etab:
            annee_scolaire_active = get_session_active(request, etab)
            if annee_scolaire_active:
                break
    
    annonces_queryset = Annonce.objects.filter(
        Q(etablissement_id__in=etablissements_ids),
        Q(statut='publiee'),
        Q(actif=True),
        (
            Q(destinataires__contains=['tous']) |
            Q(destinataires__contains=['parents'])
        )
    )
    if annee_scolaire_active:
        annonces_queryset = annonces_queryset.filter(annee_scolaire=annee_scolaire_active)
    annonces_queryset = annonces_queryset.order_by('-date_publication', '-date_creation')

    if filtre_periode:
        if filtre_periode == 'semaine':
            date_debut = today - timedelta(days=7)
            annonces_queryset = annonces_queryset.filter(date_publication__gte=date_debut)
        elif filtre_periode == 'mois':
            date_debut = today - timedelta(days=30)
            annonces_queryset = annonces_queryset.filter(date_publication__gte=date_debut)
        elif filtre_periode == 'trimestre':
            date_debut = today - timedelta(days=90)
            annonces_queryset = annonces_queryset.filter(date_publication__gte=date_debut)

    for annonce in annonces_queryset:
        etab_id = annonce.etablissement_id
        if etab_id in etablissements_map:
            etablissements_map[etab_id]["annonces"].append(annonce)

    etablissements_list = sorted(
        [
            {
                "id": etab_id,
                "etablissement": data["etablissement"],
                "annonces": data["annonces"],
            }
            for etab_id, data in etablissements_map.items()
        ],
        key=lambda item: item["etablissement"].nom.lower(),
    )

    etab_ids_sorted = [item["id"] for item in etablissements_list]
    if selected_etablissement_id and selected_etablissement_id.isdigit():
        selected_etablissement_id = int(selected_etablissement_id)
        if selected_etablissement_id not in etab_ids_sorted:
            selected_etablissement_id = None
    else:
        selected_etablissement_id = None

    if selected_etablissement_id is None:
        selected_etablissement_id = etab_ids_sorted[0]

    annonces_selectionnees = next(
        (
            item["annonces"]
            for item in etablissements_list
            if item["id"] == selected_etablissement_id
        ),
        []
    )

    total_annonces = len(annonces_selectionnees)
    date_semaine = today - timedelta(days=7)
    annonces_cette_semaine = sum(
        1 for annonce in annonces_selectionnees
        if annonce.date_publication and annonce.date_publication.date() >= date_semaine
    )

    context = {
        'parent': parent,
        'etablissements': etablissements_list,
        'annonces_selectionnees': annonces_selectionnees,
        'total_annonces': total_annonces,
        'annonces_cette_semaine': annonces_cette_semaine,
        'filtre_periode': filtre_periode,
        'selected_etablissement_id': selected_etablissement_id,
        'today': today,
        'annee_scolaire_active': annee_scolaire_active,
    }

    return render(request, 'school_admin/parent/annonces_parent.html', context)


def notifications_parent(request):
    """Affichage dédié des notifications parentales; purge après consultation."""
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    parent = request.user

    liens_valides = (
        LienFamilial.objects.filter(
            parent=parent,
            statut='valide',
            actif=True
        )
        .select_related('eleve__etablissement')
    )

    etablissements_map: dict[int, dict] = {}

    def ensure_entry(etablissement_obj, eleve_obj=None):
        if not etablissement_obj:
            return None
        entry = etablissements_map.get(etablissement_obj.id)
        if not entry:
            entry = {
                "etablissement": etablissement_obj,
                "notifications": [],
                "eleves_ids": set(),
            }
            etablissements_map[etablissement_obj.id] = entry
        if eleve_obj:
            entry["eleves_ids"].add(eleve_obj.id)
        return entry

    for lien in liens_valides:
        eleve = lien.eleve
        etablissement = getattr(eleve, "etablissement", None)

        if not eleve or not eleve.actif or not etablissement:
            continue

        ensure_entry(etablissement, eleve)

    # Récupérer l'année scolaire active pour chaque établissement
    annee_scolaire_active = None
    for entry in etablissements_map.values():
        etab = entry.get("etablissement")
        if etab:
            annee_scolaire_active = get_session_active(request, etab)
            if annee_scolaire_active:
                break
    
    # Base query pour toutes les notifications du parent (SANS FILTRE de lecture)
    notifications_query = NotificationParent.objects.filter(parent=parent)
    
    # Filtrer par année scolaire si disponible (optionnel)
    # if annee_scolaire_active:
    #     notifications_query = notifications_query.filter(annee_scolaire=annee_scolaire_active)
    
    # Récupérer TOUTES les notifications non lues pour les marquer comme lues
    notifications_non_lues = notifications_query.filter(lu=False)
    notification_ids_non_lues = list(notifications_non_lues.values_list('id', flat=True))
    
    # Marquer TOUTES les notifications non lues comme lues quand on visite la page
    if notification_ids_non_lues:
        NotificationParent.objects.filter(id__in=notification_ids_non_lues).update(
            lu=True,
            statut='lu',
            date_lecture=timezone.now(),
            date_modification=timezone.now(),
        )
    
    # Récupérer TOUTES les notifications pour l'affichage (de la plus récente à la plus ancienne)
    # AUCUN FILTRE - Afficher toutes les notifications, lues ou non lues
    notifications = list(
        notifications_query.select_related('eleve', 'eleve__etablissement', 'source_content_type')
        .order_by('-date_creation')
    )

    # Organiser les notifications par établissement
    for notification in notifications:
        eleve = getattr(notification, "eleve", None)
        etablissement = getattr(eleve, "etablissement", None) if eleve else None
        etab_id = getattr(etablissement, "id", None)
        if etab_id:
            entry = ensure_entry(etablissement, eleve)
            if entry is not None:
                entry["notifications"].append(notification)
    
    # Compter les notifications non lues restantes (après marquage)
    notifications_non_lues_count = notifications_query.filter(lu=False).count()
    
    # Log pour débogage
    logger.info(
        f"Notifications pour parent {parent.id} ({parent.nom_complet}): "
        f"Total={notifications_query.count()}, "
        f"Non lues avant marquage={len(notification_ids_non_lues)}, "
        f"Non lues après marquage={notifications_non_lues_count}, "
        f"À afficher={len(notifications)}"
    )

    etablissements_list = sorted(
        [
            {
                "id": etab_id,
                "etablissement": data["etablissement"],
                "notifications": data["notifications"],
            }
            for etab_id, data in etablissements_map.items()
        ],
        key=lambda item: item["etablissement"].nom.lower(),
    )

    if not etablissements_list:
        etablissements_list = []

    selected_etablissement_id = request.GET.get('etablissement')
    etab_ids_sorted = [item["id"] for item in etablissements_list]
    if selected_etablissement_id and selected_etablissement_id.isdigit():
        selected_etablissement_id = int(selected_etablissement_id)
        if selected_etablissement_id not in etab_ids_sorted:
            selected_etablissement_id = None
    else:
        selected_etablissement_id = None

    if selected_etablissement_id is None and etab_ids_sorted:
        selected_etablissement_id = etab_ids_sorted[0]

    notifications_selectionnees = []
    if selected_etablissement_id:
        notifications_selectionnees = next(
            (
                item["notifications"]
                for item in etablissements_list
                if item["id"] == selected_etablissement_id
            ),
            []
        )

    context = {
        'parent': parent,
        'etablissements': etablissements_list,
        'notifications_selectionnees': notifications_selectionnees,
        'selected_etablissement_id': selected_etablissement_id,
        'annee_scolaire_active': annee_scolaire_active,
        'notifications_parent_non_lues': notifications_non_lues_count,
    }

    return render(request, 'school_admin/parent/notifications_parent.html', context)


def notification_parent_click(request, notification_id):
    """
    Gère le clic sur une notification parent : marque comme lue et redirige vers la page appropriée.
    """
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    parent = request.user
    
    # Récupérer la notification
    notification = get_object_or_404(NotificationParent, id=notification_id, parent=parent)
    
    # Marquer la notification comme lue
    if not notification.lu:
        notification.marquer_comme_lue()
    
    # Récupérer l'URL de redirection depuis les données de la notification
    redirect_url = notification.donnees.get('redirect_url') if notification.donnees else None
    
    # Si pas d'URL dans les données, générer selon le type
    if not redirect_url:
        from school_admin.services.parent_notification_service import ParentNotificationService
        redirect_url = ParentNotificationService._get_redirect_url(
            notification.type_notification,
            notification.donnees,
            notification.eleve
        )
    
    # Rediriger vers l'URL appropriée
    return redirect(redirect_url)


def profil_parent(request):
    """
    Affiche le profil du parent avec toutes ses informations
    Gère également la modification du mot de passe
    """
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    parent = request.user
    
    # Gérer la modification du mot de passe
    if request.method == 'POST' and request.POST.get('action') == 'change_password':
        from django.contrib.auth import update_session_auth_hash
        from django.contrib.auth.hashers import check_password
        
        current_password = request.POST.get('current_password', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        # Validation des champs obligatoires
        validation_errors = []
        
        if not current_password:
            validation_errors.append("Le mot de passe actuel est obligatoire.")
        
        if not new_password:
            validation_errors.append("Le nouveau mot de passe est obligatoire.")
        elif len(new_password) < 8:
            validation_errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères.")
        
        if not confirm_password:
            validation_errors.append("La confirmation du mot de passe est obligatoire.")
        elif new_password and confirm_password and new_password != confirm_password:
            validation_errors.append("Les nouveaux mots de passe ne correspondent pas.")
        
        # Si des erreurs de validation existent, les afficher et arrêter
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
        # Vérifier le mot de passe actuel seulement si toutes les validations précédentes sont passées
        elif not check_password(current_password, parent.password):
            messages.error(request, "Le mot de passe actuel est incorrect.")
        else:
            # Toutes les validations sont passées, changer le mot de passe
            parent.set_password(new_password)
            parent.save()
            # Maintenir la session active après changement de mot de passe
            update_session_auth_hash(request, parent)
            messages.success(request, "Mot de passe modifié avec succès.")
            logger.info(f"Mot de passe changé - Parent: {parent.matricule_parental}")
    
    # Récupérer le nombre d'enfants liés
    nombre_enfants = LienFamilial.objects.filter(
        parent=parent,
        actif=True,
        statut='valide'
    ).count()
    
    # Récupérer la liste des enfants pour affichage
    liens_familiaux = LienFamilial.objects.filter(
        parent=parent,
        actif=True,
        statut='valide'
    ).select_related('eleve__etablissement')
    
    enfants_list = []
    for lien in liens_familiaux:
        eleve = lien.eleve
        # Récupérer l'année scolaire active pour chaque élève
        eleve_annee_scolaire_active = None
        if eleve.etablissement:
            eleve_annee_scolaire_active = get_session_active(request, eleve.etablissement)
        
        # Récupérer la classe de l'élève pour l'année scolaire active
        classe_eleve_active = get_classe_eleve_active(eleve, eleve_annee_scolaire_active, eleve.etablissement)
        
        enfants_list.append({
            'eleve': eleve,
            'type_lien': lien.get_type_lien_display(),
            'classe': classe_eleve_active.nom if classe_eleve_active else 'Non assigné',
        })
    
    # Récupérer l'année scolaire active pour l'établissement du parent
    annee_scolaire_active = None
    if parent.etablissement:
        annee_scolaire_active = get_session_active(request, parent.etablissement)
    
    context = {
        'parent': parent,
        'etablissement': parent.etablissement,
        'nombre_enfants': nombre_enfants,
        'enfants_list': enfants_list,
        'annee_scolaire_active': annee_scolaire_active,
    }
    
    return render(request, 'school_admin/parent/profil_parent.html', context)


def convocations_parent(request):
    """
    Affiche les convocations des enfants du parent, regroupées par établissement.
    """
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')

    parent = request.user

    liens_valides = (
        LienFamilial.objects.filter(
            parent=parent,
            statut='valide',
            actif=True
        )
        .select_related('eleve__etablissement')
    )

    etablissements_map = {}
    for lien in liens_valides:
        eleve = lien.eleve
        etablissement = getattr(eleve, "etablissement", None)

        if not eleve or not eleve.actif or not etablissement:
            continue

        entry = etablissements_map.setdefault(
            etablissement.id,
            {
                "etablissement": etablissement,
                "eleves_ids": set(),
                "convocations": [],
            },
        )
        entry["eleves_ids"].add(eleve.id)

    if not etablissements_map:
        messages.warning(
            request,
            "Aucun établissement associé à vos enfants n'a été trouvé."
        )
        return redirect('school_admin:dashboard_parent')

    etablissements_ids = list(etablissements_map.keys())
    all_eleves_ids = set()
    for entry in etablissements_map.values():
        all_eleves_ids.update(entry["eleves_ids"])

    selected_etablissement_id = request.GET.get('etablissement')
    today = timezone.now().date()

    # Récupérer l'année scolaire active pour chaque établissement
    annee_scolaire_active = None
    for entry in etablissements_map.values():
        etab = entry.get("etablissement")
        if etab:
            annee_scolaire_active = get_session_active(request, etab)
            if annee_scolaire_active:
                break

    # Récupérer toutes les convocations des enfants du parent
    convocations_queryset = Convocation.objects.filter(
        eleve_id__in=all_eleves_ids,
        actif=True
    )
    if annee_scolaire_active:
        convocations_queryset = convocations_queryset.filter(annee_scolaire=annee_scolaire_active)
    convocations_queryset = convocations_queryset.select_related('eleve', 'etablissement').order_by('-date_convocation', '-heure_convocation')

    # Répartir les convocations par établissement
    for convocation in convocations_queryset:
        etab_id = convocation.etablissement_id
        if etab_id in etablissements_map:
            etablissements_map[etab_id]["convocations"].append(convocation)

    etablissements_list = sorted(
        [
            {
                "id": etab_id,
                "etablissement": data["etablissement"],
                "convocations": sorted(
                    data["convocations"],
                    key=lambda c: (c.date_convocation, c.heure_convocation),
                    reverse=True
                ),
                "eleves_count": len(data["eleves_ids"]),
            }
            for etab_id, data in etablissements_map.items()
        ],
        key=lambda item: item["etablissement"].nom.lower(),
    )

    etab_ids_sorted = [item["id"] for item in etablissements_list]
    if selected_etablissement_id and selected_etablissement_id.isdigit():
        selected_etablissement_id = int(selected_etablissement_id)
        if selected_etablissement_id not in etab_ids_sorted:
            selected_etablissement_id = None
    else:
        selected_etablissement_id = None

    if selected_etablissement_id is None:
        selected_etablissement_id = etab_ids_sorted[0] if etab_ids_sorted else None

    convocations_selectionnees = []
    if selected_etablissement_id:
        convocations_selectionnees = next(
            (
                item["convocations"]
                for item in etablissements_list
                if item["id"] == selected_etablissement_id
            ),
            []
        )

    # Statistiques
    total_convocations = sum(len(item["convocations"]) for item in etablissements_list)
    convocations_en_attente = sum(
        1 for conv in convocations_selectionnees
        if conv.statut == 'en_attente'
    )
    convocations_a_venir = sum(
        1 for conv in convocations_selectionnees
        if conv.date_convocation >= today
    )
    convocations_passees = sum(
        1 for conv in convocations_selectionnees
        if conv.date_convocation < today
    )
    convocations_honorees = sum(
        1 for conv in convocations_selectionnees
        if conv.statut == 'honoree'
    )

    context = {
        'parent': parent,
        'etablissements': etablissements_list,
        'convocations_selectionnees': convocations_selectionnees,
        'total_convocations': total_convocations,
        'convocations_en_attente': convocations_en_attente,
        'convocations_a_venir': convocations_a_venir,
        'convocations_passees': convocations_passees,
        'convocations_honorees': convocations_honorees,
        'selected_etablissement_id': selected_etablissement_id,
        'today': today,
        'annee_scolaire_active': annee_scolaire_active,
    }

    return render(request, 'school_admin/parent/convocations_parent.html', context)

