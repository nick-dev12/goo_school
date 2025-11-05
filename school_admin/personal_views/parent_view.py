"""
Vues pour l'espace parent
Les parents peuvent consulter toutes les informations de leurs enfants
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from school_admin.model.parent_model import Parent
from school_admin.model.eleve_model import Eleve
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.demande_liaison_model import DemandeLiaisonParent
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
    
    # Récupérer tous les enfants liés à ce parent
    liens_familiaux = LienFamilial.objects.filter(
        parent=parent,
        actif=True,
        statut='valide'
    ).select_related('eleve__classe', 'eleve__etablissement')
    
    print(f"[DASHBOARD PARENT] Nombre de liens trouvés: {liens_familiaux.count()}")
    
    # Récupérer les IDs des élèves qui ont une demande approuvée
    demandes_approuvees = DemandeLiaisonParent.objects.filter(
        parent_demandeur=parent,
        statut__in=['reussie', 'approuvee']
    ).values_list('eleve_valide_id', flat=True)
    
    print(f"[DASHBOARD PARENT] Demandes approuvées: {len(demandes_approuvees)}")
    
    enfants = []
    for lien in liens_familiaux:
        eleve = lien.eleve
        
        # FILTRAGE : Afficher uniquement :
        # 1. L'enfant inscripteur (lié par défaut lors de l'inscription)
        # 2. Les enfants ajoutés via demande de liaison approuvée
        if not (lien.est_inscripteur or eleve.id in demandes_approuvees):
            print(f"[DASHBOARD PARENT] Enfant {eleve.nom_complet} filtré (ni inscripteur ni demande approuvée)")
            continue
        
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
    
    # Toujours afficher le dashboard parent pour qu'il puisse choisir
    print(f"[DASHBOARD PARENT] Nombre d'enfants à afficher: {len(enfants)}")
    
    # Récupérer les données du formulaire de la session (si échec précédent)
    form_data = request.session.pop('form_data', None)
    
    context = {
        'parent': parent,
        'etablissement': parent.etablissement,
        'enfants': enfants,
        'nombre_enfants': len(enfants),
        'today': timezone.now().date(),
        'form_data': form_data,  # Données du formulaire à réafficher
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


def deconnexion_parent(request):
    """
    Déconnexion du parent
    Nettoie la session avant de déconnecter
    """
    from django.contrib.auth import logout
    
    # Nettoyer les données de session
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
    
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès.")
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
                eleve_valide=eleve
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

