"""
Vues pour l'espace élève
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from datetime import datetime, timedelta
from school_admin.model.eleve_model import Eleve
from school_admin.model.evaluation_model import Note
from school_admin.model.presence_model import Presence
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
import logging

logger = logging.getLogger(__name__)


def dashboard_eleve(request):
    """
    Tableau de bord principal de l'élève
    """
    print(f"\n[DASHBOARD ELEVE] User: {request.user}, Type: {type(request.user).__name__}, Authenticated: {request.user.is_authenticated}")
    logger.info(f"Dashboard eleve - User: {request.user}, Type: {type(request.user).__name__}, Authenticated: {request.user.is_authenticated}")
    
    # Vérifier que l'utilisateur est bien un élève
    if not isinstance(request.user, Eleve):
        print(f"[DASHBOARD ELEVE] Accès refusé - Type: {type(request.user).__name__}")
        logger.warning(f"Accès refusé au dashboard eleve - Type d'utilisateur: {type(request.user).__name__}")
        messages.error(request, "Accès non autorisé. Cette page est réservée aux élèves.")
        return redirect('school_admin:connexion_compte_user')
    
    eleve = request.user
    
    try:
        # Date d'aujourd'hui
        date_aujourdhui = timezone.now().date()
        
        # Calculer la moyenne générale (désactivé temporairement pour debug)
        moyenne_generale = None
        
        # Dernières notes (désactivé temporairement pour debug)
        dernieres_notes = []
        
        # Calculer les statistiques de présence
        debut_annee = timezone.now().replace(month=9, day=1, hour=0, minute=0, second=0, microsecond=0)
        if timezone.now().month < 9:
            debut_annee = debut_annee.replace(year=debut_annee.year - 1)
        
        presences = Presence.objects.filter(
            eleve=eleve,
            date__gte=debut_annee
        )
        
        total_presences = presences.count()
        presences_absentes = presences.filter(statut='absent').count()
        presences_retards = presences.filter(statut='retard').count()
        jours_present = total_presences - presences_absentes
        
        if total_presences > 0:
            taux_presence = round((jours_present / total_presences) * 100, 1)
        else:
            taux_presence = 100
        
        # Récupérer les prochains cours d'aujourd'hui
        prochains_cours = []
        if eleve.classe:
            creneaux = CreneauEmploiDuTemps.objects.filter(
                emploi_du_temps__classe=eleve.classe,
                jour=date_aujourdhui.weekday()
            ).select_related('matiere', 'professeur', 'periode_etablissement').order_by('periode_etablissement__ordre')
            
            for creneau in creneaux:
                # Définir icône et couleur selon la matière
                icon = 'fas fa-book'
                icon_color = 'neo-blue'
                
                if creneau.matiere:
                    matiere_nom = creneau.matiere.nom.lower()
                    if 'math' in matiere_nom:
                        icon = 'fas fa-square-root-alt'
                        icon_color = 'neo-blue'
                    elif 'français' in matiere_nom or 'francais' in matiere_nom:
                        icon = 'fas fa-book'
                        icon_color = 'neo-red'
                    elif 'anglais' in matiere_nom:
                        icon = 'fas fa-language'
                        icon_color = 'neo-purple'
                    elif 'histoire' in matiere_nom or 'géographie' in matiere_nom or 'geographie' in matiere_nom:
                        icon = 'fas fa-globe-europe'
                        icon_color = 'neo-green'
                    elif 'svt' in matiere_nom or 'biologie' in matiere_nom:
                        icon = 'fas fa-leaf'
                        icon_color = 'neo-teal'
                    elif 'physique' in matiere_nom or 'chimie' in matiere_nom:
                        icon = 'fas fa-flask'
                        icon_color = 'neo-cyan'
                    elif 'sport' in matiere_nom or 'eps' in matiere_nom:
                        icon = 'fas fa-running'
                        icon_color = 'neo-orange'
                
                prochains_cours.append({
                    'matiere': creneau.matiere.nom if creneau.matiere else 'Non défini',
                    'icon': icon,
                    'icon_color': icon_color,
                    'heure_debut': creneau.periode_etablissement.heure_debut.strftime('%H:%M') if creneau.periode_etablissement else 'N/A',
                    'heure_fin': creneau.periode_etablissement.heure_fin.strftime('%H:%M') if creneau.periode_etablissement else 'N/A',
                    'salle': creneau.salle.nom if creneau.salle else None,
                    'enseignant': creneau.professeur.nom_complet if creneau.professeur else None
                })
        
        # Devoirs à faire (simulés pour l'instant)
        devoirs = []
        total_devoirs = 0
        
        context = {
            'page_title': 'Tableau de bord',
            'eleve': eleve,
            'moyenne_generale': moyenne_generale,
            'dernieres_notes': dernieres_notes,
            'taux_presence': taux_presence,
            'jours_present': jours_present,
            'total_absences': presences_absentes,
            'total_retards': presences_retards,
            'prochains_cours': prochains_cours,
            'devoirs': devoirs,
            'total_devoirs': total_devoirs,
            'date_aujourdhui': date_aujourdhui,
        }
        
        return render(request, 'school_admin/eleve/dashboard_eleve.html', context)
        
    except Exception as e:
        messages.error(request, f"Erreur lors du chargement du tableau de bord : {str(e)}")
        return redirect('school_admin:connexion_compte_user')


def deconnexion_eleve(request):
    """
    Déconnexion de l'élève
    """
    from django.contrib.auth import logout
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès.")
    return redirect('school_admin:connexion_compte_user')
