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
import logging

logger = logging.getLogger(__name__)


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
    
    # Préparer les notifications récentes pour le parent
    notifications_queryset = NotificationParent.objects.filter(
        parent=parent
    ).select_related('eleve').order_by('-date_creation')[:30]
    notifications_list = list(notifications_queryset)
    notifications_map = {}
    for notification in notifications_list:
        notifications_map.setdefault(notification.eleve_id, []).append(notification)
    notifications_parent_non_lues = NotificationParent.objects.filter(
        parent=parent,
        statut='non_lu'
    ).count()
    
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
                
                # Statistiques de présence et absences
                presences = Presence.objects.filter(eleve=eleve)
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
                })
            except Exception as e:
                print(f"[DASHBOARD PARENT] Erreur pour élève {eleve.nom_complet}: {str(e)}")
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
        nombre_annonces = Annonce.objects.filter(
            Q(etablissement=parent.etablissement) &
            Q(statut='publiee') &
            Q(actif=True) &
            (Q(destinataires__contains=['tous']) | 
             Q(destinataires__contains=['parents']))
        ).count()
    
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
    Système de 3 tentatives maximum avec blocage automatique
    Évite les doublons en mettant à jour la demande existante
    """
    if not isinstance(request.user, Parent):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    if request.method != 'POST':
        return redirect('school_admin:dashboard_parent')
    
    parent = request.user
    matricule_eleve = request.POST.get('matricule_eleve', '').strip()
    classe_eleve = request.POST.get('classe_eleve', '').strip()
    nom_parent_inscripteur = request.POST.get('nom_parent_inscripteur', '').strip()
    type_lien = request.POST.get('type_lien', '')
    
    # Stocker les données saisies dans la session pour les réafficher en cas d'échec
    request.session['form_data'] = {
        'matricule_eleve': matricule_eleve,
        'classe_eleve': classe_eleve,
        'nom_parent_inscripteur': nom_parent_inscripteur,
        'type_lien': type_lien,
    }
    
    print(f"[DEMANDE LIAISON] Parent: {parent.nom_complet}, Matricule: {matricule_eleve}, Classe: {classe_eleve}")
    
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent
    
    # Vérifier s'il existe déjà une demande pour ce parent + matricule
    demande_existante = DemandeLiaisonParent.objects.filter(
        parent_demandeur=parent,
        matricule_eleve=matricule_eleve
    ).order_by('-date_demande').first()
    
    # Si une demande est déjà bloquée, empêcher de nouvelles tentatives
    if demande_existante and demande_existante.statut == 'bloquee':
        messages.warning(request, "❌ Trop de tentatives échouées. Une demande de validation a été envoyée à l'établissement.")
        return redirect('school_admin:dashboard_parent')
    
    # Compter le nombre de tentatives échouées précédentes
    if demande_existante:
        # Incrémenter le compteur si la dernière tentative a échoué
        if demande_existante.statut in ['echec', 'bloquee']:
            tentatives_precedentes = demande_existante.nombre_tentatives
        else:
            tentatives_precedentes = 0
    else:
        tentatives_precedentes = 0
    
    print(f"[DEMANDE LIAISON] Tentatives précédentes: {tentatives_precedentes}")
    
    try:
        # Vérifier que l'élève existe
        eleve = Eleve.objects.filter(
            matricule_eleve=matricule_eleve,
            actif=True
        ).first()
        
        # Si l'élève n'existe pas, afficher un message et ne rien enregistrer
        if not eleve:
            messages.error(request, "❌ Cet élève n'est inscrit dans aucun établissement.")
            return redirect('school_admin:dashboard_parent')
        
        # Vérifier si un lien existe déjà
        lien_existant = LienFamilial.objects.filter(
            parent=parent,
            eleve=eleve,
            actif=True
        ).exists()
        
        if lien_existant:
            messages.warning(request, f"Vous êtes déjà lié à {eleve.nom_complet}.")
            return redirect('school_admin:dashboard_parent')
        
        raison_echec = None
        verification_reussie = True
        
        # Vérifier la classe
        classe_fournie_clean = classe_eleve.strip().lower().replace(' ', '').replace('-', '')
        classe_eleve_clean = eleve.classe.nom.strip().lower().replace(' ', '').replace('-', '') if eleve.classe else ''
        
        if classe_fournie_clean != classe_eleve_clean:
            raison_echec = f"La classe fournie ({classe_eleve}) ne correspond pas à la classe réelle de l'élève"
            verification_reussie = False
        
        # Vérifier le nom du parent inscripteur
        if verification_reussie:
            parent_inscripteur = eleve.parent_inscripteur
            if parent_inscripteur:
                nom_inscripteur = parent_inscripteur.nom.lower()
                prenom_inscripteur = parent_inscripteur.prenom.lower()
                nom_fourni = nom_parent_inscripteur.lower()
                
                if nom_fourni not in nom_inscripteur and nom_fourni not in prenom_inscripteur:
                    raison_echec = f"Le nom du parent inscripteur ({nom_parent_inscripteur}) ne correspond pas"
                    verification_reussie = False
            else:
                raison_echec = "Aucun parent inscripteur enregistré pour cet élève"
                verification_reussie = False
        
        # Calculer le nombre total de tentatives (y compris celle-ci)
        nombre_total_tentatives = tentatives_precedentes + 1
        
        # Déterminer le statut de la demande
        if nombre_total_tentatives >= 3 and not verification_reussie:
            statut_demande = 'bloquee'
        elif verification_reussie:
            statut_demande = 'reussie'
        else:
            statut_demande = 'echec'
        
        # Récupérer l'année scolaire active de l'établissement de l'élève
        from school_admin.utils.session_utils import get_session_active
        annee_scolaire_active = None
        if eleve.etablissement:
            # Créer une requête factice pour récupérer l'année scolaire active
            # On utilise l'établissement de l'élève
            from school_admin.model.annee_scolaire_model import AnneeScolaire
            annee_scolaire_active = AnneeScolaire.objects.filter(
                etablissement=eleve.etablissement,
                est_active=True
            ).first()
        
        # Mettre à jour la demande existante ou créer une nouvelle
        if demande_existante and demande_existante.statut in ['echec', 'en_attente']:
            # Mise à jour de la demande existante au lieu de créer un doublon
            demande = demande_existante
            demande.classe_eleve = classe_eleve
            demande.nom_parent_inscripteur = nom_parent_inscripteur
            demande.type_lien = type_lien
            demande.nom_eleve = eleve.nom
            demande.prenom_eleve = eleve.prenom
            demande.date_naissance_eleve = eleve.date_naissance
            demande.nombre_tentatives = nombre_total_tentatives
            demande.raison_echec = raison_echec
            demande.eleve_valide = eleve
            demande.date_demande = timezone.now()  # Mise à jour de la date
            if annee_scolaire_active:
                demande.annee_scolaire = annee_scolaire_active
            demande.save()
            print(f"[DEMANDE LIAISON] Mise à jour de la demande existante ID: {demande.id}")
        else:
            # Créer une nouvelle demande
            demande = DemandeLiaisonParent.objects.create(
                parent_demandeur=parent,
                matricule_eleve=matricule_eleve,
                nom_eleve=eleve.nom,
                prenom_eleve=eleve.prenom,
                date_naissance_eleve=eleve.date_naissance,
                classe_eleve=classe_eleve,
                nom_parent_inscripteur=nom_parent_inscripteur,
                type_lien=type_lien,
                statut='en_attente',  # Toujours en_attente au départ
                nombre_tentatives=nombre_total_tentatives,
                raison_echec=raison_echec,
                eleve_valide=eleve,
                annee_scolaire=annee_scolaire_active
            )
            print(f"[DEMANDE LIAISON] Nouvelle demande créée ID: {demande.id}")
        
        print(f"[DEMANDE LIAISON] Statut initial: {statut_demande}, Tentatives: {nombre_total_tentatives}")
        
        # Traiter selon le statut déterminé
        if statut_demande == 'reussie':
            # Approuver automatiquement
            try:
                lien = demande.approuver()
                demande.statut = 'reussie'
                demande.save()
                
                # Supprimer les données du formulaire de la session en cas de succès
                if 'form_data' in request.session:
                    del request.session['form_data']
                
                messages.success(request, f"✅ Votre enfant {eleve.nom_complet} a été ajouté avec succès à votre espace !")
                logger.info(f"Liaison réussie - Parent: {parent.matricule_parental}, Élève: {eleve.matricule_eleve}")
            except Exception as e:
                print(f"[DEMANDE LIAISON] Erreur approbation: {str(e)}")
                import traceback
                traceback.print_exc()
                demande.statut = 'en_attente'
                demande.save()
                messages.info(request, f"Votre demande a été enregistrée et sera traitée par l'administration.")
        
        elif statut_demande == 'bloquee':
            # Bloquer après 3 tentatives échouées
            demande.statut = 'bloquee'
            demande.save()
            messages.error(request, 
                f"❌ Votre demande a échoué. Après {nombre_total_tentatives} tentatives, "
                f"une demande a été envoyée à l'établissement pour validation manuelle.")
            logger.warning(f"Demande bloquée après {nombre_total_tentatives} tentatives - Parent: {parent.matricule_parental}, Matricule: {matricule_eleve}")
        
        else:
            # Échec mais tentatives restantes
            demande.statut = 'echec'
            demande.save()
            tentatives_restantes = 3 - nombre_total_tentatives
            messages.error(request, 
                f"❌ {raison_echec}. Il vous reste {tentatives_restantes} tentative{'s' if tentatives_restantes > 1 else ''}.")
        
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

    annonces_queryset = Annonce.objects.filter(
        Q(etablissement_id__in=etablissements_ids),
        Q(statut='publiee'),
        Q(actif=True),
        (
            Q(destinataires__contains=['tous']) |
            Q(destinataires__contains=['parents'])
        )
    ).order_by('-date_publication', '-date_creation')

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

    notifications = list(
        NotificationParent.objects.filter(parent=parent)
        .select_related('eleve', 'eleve__etablissement', 'source_content_type')
        .order_by('-date_creation')
    )

    notification_ids = [n.id for n in notifications]

    for notification in notifications:
        eleve = getattr(notification, "eleve", None)
        etablissement = getattr(eleve, "etablissement", None) if eleve else None
        etab_id = getattr(etablissement, "id", None)
        if etab_id:
            entry = ensure_entry(etablissement, eleve)
            if entry is not None:
                entry["notifications"].append(notification)

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

    if notification_ids:
        NotificationParent.objects.filter(id__in=notification_ids).update(statut='lu', date_lecture=timezone.now())

    context = {
        'parent': parent,
        'etablissements': etablissements_list,
        'notifications_selectionnees': notifications_selectionnees,
        'selected_etablissement_id': selected_etablissement_id,
    }

    response = render(request, 'school_admin/parent/notifications_parent.html', context)

    if notification_ids:
        NotificationParent.objects.filter(id__in=notification_ids).delete()

    return response


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
    ).select_related('eleve__classe', 'eleve__etablissement')
    
    enfants_list = []
    for lien in liens_familiaux:
        enfants_list.append({
            'eleve': lien.eleve,
            'type_lien': lien.get_type_lien_display(),
            'classe': lien.eleve.classe.nom if lien.eleve.classe else 'Non assigné',
        })
    
    context = {
        'parent': parent,
        'etablissement': parent.etablissement,
        'nombre_enfants': nombre_enfants,
        'enfants_list': enfants_list,
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

    # Récupérer toutes les convocations des enfants du parent
    convocations_queryset = Convocation.objects.filter(
        eleve_id__in=all_eleves_ids,
        actif=True
    ).select_related('eleve', 'etablissement').order_by('-date_convocation', '-heure_convocation')

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
    }

    return render(request, 'school_admin/parent/convocations_parent.html', context)

