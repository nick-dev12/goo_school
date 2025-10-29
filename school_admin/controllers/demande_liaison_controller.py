"""
Contrôleur pour la gestion des demandes de liaison parent-élève
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from school_admin.model.demande_liaison_model import DemandeLiaisonParent
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.parent_model import Parent
from school_admin.model.eleve_model import Eleve
from school_admin.decorators import parent_required


class DemandeLiaisonController:
    """
    Contrôleur pour la gestion des demandes de liaison parent-élève
    """
    
    @staticmethod
    @login_required
    @parent_required
    def creer_demande_liaison(request):
        """
        Permet au parent de créer une demande de liaison avec un élève
        
        Args:
            request: Requête HTTP
            
        Returns:
            HttpResponse: Page de création de demande
        """
        try:
            parent = request.user
            
            if request.method == 'POST':
                matricule_eleve = request.POST.get('matricule_eleve', '').strip()
                nom_eleve = request.POST.get('nom_eleve', '').strip()
                prenom_eleve = request.POST.get('prenom_eleve', '').strip()
                date_naissance_str = request.POST.get('date_naissance_eleve', '').strip()
                type_lien = request.POST.get('type_lien', '').strip()
                
                # Validations
                if not all([matricule_eleve, nom_eleve, prenom_eleve, date_naissance_str, type_lien]):
                    messages.error(request, "Tous les champs sont obligatoires.")
                    return redirect('creer_demande_liaison')
                
                # Convertir la date de naissance
                try:
                    from datetime import datetime
                    date_naissance_eleve = datetime.strptime(date_naissance_str, '%Y-%m-%d').date()
                except ValueError:
                    messages.error(request, "Format de date invalide.")
                    return redirect('creer_demande_liaison')
                
                # Vérifier si une demande similaire existe déjà
                demande_existante = DemandeLiaisonParent.objects.filter(
                    parent_demandeur=parent,
                    matricule_eleve=matricule_eleve,
                    statut__in=['en_attente', 'valide']
                ).first()
                
                if demande_existante:
                    if demande_existante.statut == 'valide':
                        messages.warning(request, "Vous êtes déjà lié à cet élève.")
                    else:
                        messages.warning(request, "Une demande est déjà en attente pour cet élève.")
                    return redirect('mes_demandes_liaison')
                
                # Créer la demande
                demande = DemandeLiaisonParent.objects.create(
                    parent_demandeur=parent,
                    matricule_eleve=matricule_eleve,
                    nom_eleve=nom_eleve.upper(),
                    prenom_eleve=prenom_eleve.title(),
                    date_naissance_eleve=date_naissance_eleve,
                    type_lien=type_lien,
                    etablissement=parent.etablissement
                )
                
                messages.success(
                    request,
                    "Votre demande de liaison a été créée avec succès. "
                    "Elle sera traitée par l'administration de l'établissement."
                )
                return redirect('mes_demandes_liaison')
            
            context = {
                'parent': parent
            }
            
            return render(request, 'school_admin/parent/creer_demande_liaison.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors de la création de la demande : {str(e)}")
            return redirect('dashboard_parent')
    
    
    @staticmethod
    @login_required
    @parent_required
    def mes_demandes_liaison(request):
        """
        Affiche la liste des demandes de liaison du parent
        
        Args:
            request: Requête HTTP
            
        Returns:
            HttpResponse: Page liste des demandes
        """
        try:
            parent = request.user
            
            # Récupérer toutes les demandes du parent
            demandes = DemandeLiaisonParent.objects.filter(
                parent_demandeur=parent
            ).order_by('-date_demande')
            
            context = {
                'parent': parent,
                'demandes': demandes
            }
            
            return render(request, 'school_admin/parent/mes_demandes_liaison.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors du chargement des demandes : {str(e)}")
            return redirect('dashboard_parent')
    
    
    @staticmethod
    @login_required
    def liste_demandes_liaison(request):
        """
        Affiche la liste de toutes les demandes de liaison (pour l'administration)
        
        Args:
            request: Requête HTTP
            
        Returns:
            HttpResponse: Page liste des demandes (admin)
        """
        try:
            # Filtrer les demandes selon le statut
            statut_filtre = request.GET.get('statut', 'en_attente')
            
            demandes = DemandeLiaisonParent.objects.select_related(
                'parent_demandeur',
                'parent_demandeur__etablissement',
                'eleve_valide',
                'traite_par'
            ).filter(etablissement=request.user.etablissement)
            
            if statut_filtre and statut_filtre != 'tous':
                demandes = demandes.filter(statut=statut_filtre)
            
            demandes = demandes.order_by('-date_demande')
            
            context = {
                'demandes': demandes,
                'statut_filtre': statut_filtre
            }
            
            return render(request, 'school_admin/directeur/secretaire/liste_demandes_liaison.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors du chargement des demandes : {str(e)}")
            return redirect('dashboard_directeur')
    
    
    @staticmethod
    @login_required
    @transaction.atomic
    def traiter_demande_liaison(request, demande_id):
        """
        Traite une demande de liaison (validation ou refus)
        
        Args:
            request: Requête HTTP
            demande_id: ID de la demande
            
        Returns:
            HttpResponse: Redirection
        """
        try:
            demande = get_object_or_404(
                DemandeLiaisonParent,
                id=demande_id,
                etablissement=request.user.etablissement,
                statut='en_attente'
            )
            
            if request.method == 'POST':
                action = request.POST.get('action')
                
                if action == 'valider':
                    # Rechercher l'élève correspondant
                    eleve = Eleve.objects.filter(
                        matricule_eleve=demande.matricule_eleve,
                        nom__iexact=demande.nom_eleve,
                        prenom__iexact=demande.prenom_eleve,
                        date_naissance=demande.date_naissance_eleve
                    ).first()
                    
                    if not eleve:
                        messages.error(
                            request,
                            "Aucun élève ne correspond aux informations fournies."
                        )
                        return redirect('detail_demande_liaison', demande_id=demande_id)
                    
                    # Vérifier qu'un lien n'existe pas déjà
                    lien_existant = LienFamilial.objects.filter(
                        parent=demande.parent_demandeur,
                        eleve=eleve
                    ).first()
                    
                    if lien_existant:
                        messages.warning(request, "Un lien existe déjà entre ce parent et cet élève.")
                        demande.statut = 'refuse'
                        demande.motif_refus = "Lien familial déjà existant"
                        demande.date_traitement = timezone.now()
                        demande.traite_par = request.user
                        demande.save()
                        return redirect('liste_demandes_liaison')
                    
                    # Créer le lien familial
                    LienFamilial.objects.create(
                        parent=demande.parent_demandeur,
                        eleve=eleve,
                        type_lien=demande.type_lien,
                        est_inscripteur=False,  # Ce n'est pas le parent inscripteur
                        statut='valide',
                        etablissement=demande.etablissement
                    )
                    
                    # Mettre à jour la demande
                    demande.statut = 'valide'
                    demande.eleve_valide = eleve
                    demande.date_traitement = timezone.now()
                    demande.traite_par = request.user
                    demande.save()
                    
                    messages.success(
                        request,
                        f"La demande a été validée. Le lien familial entre "
                        f"{demande.parent_demandeur.nom_complet} et {eleve.nom_complet} a été créé."
                    )
                    
                elif action == 'refuser':
                    motif_refus = request.POST.get('motif_refus', '').strip()
                    
                    if not motif_refus:
                        messages.error(request, "Vous devez fournir un motif de refus.")
                        return redirect('detail_demande_liaison', demande_id=demande_id)
                    
                    demande.statut = 'refuse'
                    demande.motif_refus = motif_refus
                    demande.date_traitement = timezone.now()
                    demande.traite_par = request.user
                    demande.save()
                    
                    messages.success(request, "La demande a été refusée.")
                
                return redirect('liste_demandes_liaison')
            
            context = {
                'demande': demande
            }
            
            return render(request, 'school_admin/directeur/secretaire/traiter_demande_liaison.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors du traitement de la demande : {str(e)}")
            return redirect('liste_demandes_liaison')
    
    
    @staticmethod
    @login_required
    def detail_demande_liaison(request, demande_id):
        """
        Affiche les détails d'une demande de liaison
        
        Args:
            request: Requête HTTP
            demande_id: ID de la demande
            
        Returns:
            HttpResponse: Page de détail
        """
        try:
            demande = get_object_or_404(
                DemandeLiaisonParent,
                id=demande_id,
                etablissement=request.user.etablissement
            )
            
            # Rechercher les élèves potentiellement correspondants
            eleves_potentiels = Eleve.objects.filter(
                matricule_eleve=demande.matricule_eleve,
                etablissement=request.user.etablissement
            )
            
            context = {
                'demande': demande,
                'eleves_potentiels': eleves_potentiels
            }
            
            return render(request, 'school_admin/directeur/secretaire/detail_demande_liaison.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors du chargement des détails : {str(e)}")
            return redirect('liste_demandes_liaison')
    
    
    @staticmethod
    @login_required
    @parent_required
    def annuler_demande_liaison(request, demande_id):
        """
        Permet au parent d'annuler une demande en attente
        
        Args:
            request: Requête HTTP
            demande_id: ID de la demande
            
        Returns:
            HttpResponse: Redirection
        """
        try:
            parent = request.user
            
            demande = get_object_or_404(
                DemandeLiaisonParent,
                id=demande_id,
                parent_demandeur=parent,
                statut='en_attente'
            )
            
            if request.method == 'POST':
                demande.statut = 'annule'
                demande.date_traitement = timezone.now()
                demande.save()
                
                messages.success(request, "Votre demande a été annulée.")
                return redirect('mes_demandes_liaison')
            
            context = {
                'demande': demande,
                'parent': parent
            }
            
            return render(request, 'school_admin/parent/annuler_demande_liaison.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors de l'annulation : {str(e)}")
            return redirect('mes_demandes_liaison')

