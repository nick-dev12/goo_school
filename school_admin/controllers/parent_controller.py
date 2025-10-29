"""
Contrôleur pour la gestion de l'espace parent
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from school_admin.model.parent_model import Parent
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.eleve_model import Eleve
from school_admin.model.demande_liaison_model import DemandeLiaisonParent
from school_admin.model.note_model import Note
from school_admin.model.evaluation_model import Evaluation
from school_admin.model.presence_model import Presence
from school_admin.model.sanction_model import Sanction
from school_admin.decorators import parent_required


class ParentController:
    """
    Contrôleur pour la gestion de l'espace parent
    """
    
    @staticmethod
    @login_required
    @parent_required
    def dashboard_parent(request):
        """
        Affiche le tableau de bord principal du parent
        
        Args:
            request: Requête HTTP
            
        Returns:
            HttpResponse: Page du tableau de bord parent
        """
        try:
            parent = request.user
            
            # Récupérer tous les enfants liés au parent
            liens_familiaux = LienFamilial.objects.filter(
                parent=parent,
                statut='valide'
            ).select_related('eleve', 'eleve__classe', 'eleve__etablissement')
            
            enfants_data = []
            
            for lien in liens_familiaux:
                eleve = lien.eleve
                
                # Statistiques de présence du mois en cours
                debut_mois = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                presences = Presence.objects.filter(
                    eleve=eleve,
                    date__gte=debut_mois
                )
                
                total_presences = presences.count()
                presences_absences = presences.filter(statut='absent').count()
                taux_presence = ((total_presences - presences_absences) / total_presences * 100) if total_presences > 0 else 0
                
                # Récupérer les dernières notes
                dernieres_notes = Note.objects.filter(
                    eleve=eleve
                ).select_related('evaluation', 'evaluation__matiere').order_by('-date_saisie')[:5]
                
                # Calculer la moyenne générale
                notes_valides = Note.objects.filter(
                    eleve=eleve,
                    note__isnull=False
                ).exclude(note='')
                
                if notes_valides.exists():
                    moyenne_generale = notes_valides.aggregate(Avg('note'))['note__avg']
                else:
                    moyenne_generale = None
                
                # Récupérer les sanctions récentes
                sanctions_recentes = Sanction.objects.filter(
                    eleve=eleve
                ).order_by('-date_sanction')[:3]
                
                enfants_data.append({
                    'eleve': eleve,
                    'lien': lien,
                    'taux_presence': round(taux_presence, 1),
                    'absences_mois': presences_absences,
                    'dernieres_notes': dernieres_notes,
                    'moyenne_generale': round(moyenne_generale, 2) if moyenne_generale else None,
                    'sanctions_recentes': sanctions_recentes
                })
            
            context = {
                'parent': parent,
                'enfants_data': enfants_data,
                'total_enfants': len(enfants_data)
            }
            
            return render(request, 'school_admin/parent/dashboard_parent.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors du chargement du tableau de bord : {str(e)}")
            return redirect('connexion')
    
    
    @staticmethod
    @login_required
    @parent_required
    def detail_enfant(request, eleve_id):
        """
        Affiche les détails complets d'un enfant
        
        Args:
            request: Requête HTTP
            eleve_id: ID de l'élève
            
        Returns:
            HttpResponse: Page de détail de l'enfant
        """
        try:
            parent = request.user
            
            # Vérifier que le parent a bien accès à cet élève
            lien = get_object_or_404(
                LienFamilial,
                parent=parent,
                eleve_id=eleve_id,
                statut='valide'
            )
            
            eleve = lien.eleve
            
            # Récupérer toutes les notes
            notes = Note.objects.filter(
                eleve=eleve
            ).select_related('evaluation', 'evaluation__matiere').order_by('-date_saisie')
            
            # Récupérer les présences
            presences = Presence.objects.filter(
                eleve=eleve
            ).order_by('-date')
            
            # Récupérer les sanctions
            sanctions = Sanction.objects.filter(
                eleve=eleve
            ).order_by('-date_sanction')
            
            context = {
                'parent': parent,
                'eleve': eleve,
                'lien': lien,
                'notes': notes,
                'presences': presences,
                'sanctions': sanctions
            }
            
            return render(request, 'school_admin/parent/detail_enfant.html', context)
            
        except LienFamilial.DoesNotExist:
            messages.error(request, "Vous n'avez pas accès à cet élève.")
            return redirect('dashboard_parent')
        except Exception as e:
            messages.error(request, f"Erreur lors du chargement des détails : {str(e)}")
            return redirect('dashboard_parent')
    
    
    @staticmethod
    @login_required
    @parent_required
    def mes_enfants(request):
        """
        Affiche la liste de tous les enfants du parent
        
        Args:
            request: Requête HTTP
            
        Returns:
            HttpResponse: Page liste des enfants
        """
        try:
            parent = request.user
            
            # Récupérer tous les liens familiaux
            liens = LienFamilial.objects.filter(
                parent=parent
            ).select_related('eleve', 'eleve__classe').order_by('statut', 'eleve__nom')
            
            context = {
                'parent': parent,
                'liens': liens
            }
            
            return render(request, 'school_admin/parent/mes_enfants.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors du chargement de la liste : {str(e)}")
            return redirect('dashboard_parent')
    
    
    @staticmethod
    @login_required
    @parent_required
    def profil_parent(request):
        """
        Affiche et permet de modifier le profil du parent
        
        Args:
            request: Requête HTTP
            
        Returns:
            HttpResponse: Page profil parent
        """
        try:
            parent = request.user
            
            if request.method == 'POST':
                # Mise à jour des informations
                parent.telephone = request.POST.get('telephone', parent.telephone)
                parent.email = request.POST.get('email', parent.email)
                parent.adresse = request.POST.get('adresse', parent.adresse)
                parent.profession = request.POST.get('profession', parent.profession)
                
                # Gestion du changement de mot de passe
                nouveau_mdp = request.POST.get('nouveau_mot_de_passe')
                if nouveau_mdp:
                    parent.set_password(nouveau_mdp)
                    parent.mot_de_passe_modifie = True
                
                parent.save()
                messages.success(request, "Votre profil a été mis à jour avec succès.")
                return redirect('profil_parent')
            
            context = {
                'parent': parent
            }
            
            return render(request, 'school_admin/parent/profil_parent.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors de la mise à jour du profil : {str(e)}")
            return redirect('dashboard_parent')
    
    
    @staticmethod
    @login_required
    @parent_required
    def changer_mot_de_passe_parent(request):
        """
        Permet au parent de changer son mot de passe
        
        Args:
            request: Requête HTTP
            
        Returns:
            HttpResponse: Page changement de mot de passe
        """
        try:
            parent = request.user
            
            if request.method == 'POST':
                ancien_mdp = request.POST.get('ancien_mot_de_passe')
                nouveau_mdp = request.POST.get('nouveau_mot_de_passe')
                confirmation_mdp = request.POST.get('confirmation_mot_de_passe')
                
                # Vérifications
                if not parent.check_password(ancien_mdp):
                    messages.error(request, "L'ancien mot de passe est incorrect.")
                    return redirect('changer_mot_de_passe_parent')
                
                if nouveau_mdp != confirmation_mdp:
                    messages.error(request, "Les mots de passe ne correspondent pas.")
                    return redirect('changer_mot_de_passe_parent')
                
                if len(nouveau_mdp) < 6:
                    messages.error(request, "Le mot de passe doit contenir au moins 6 caractères.")
                    return redirect('changer_mot_de_passe_parent')
                
                # Changer le mot de passe
                parent.set_password(nouveau_mdp)
                parent.mot_de_passe_modifie = True
                parent.save()
                
                messages.success(request, "Votre mot de passe a été changé avec succès.")
                return redirect('profil_parent')
            
            context = {
                'parent': parent
            }
            
            return render(request, 'school_admin/parent/changer_mot_de_passe.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors du changement de mot de passe : {str(e)}")
            return redirect('dashboard_parent')

