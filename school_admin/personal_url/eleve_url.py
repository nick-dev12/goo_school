"""
URLs pour l'espace élève
"""
from django.urls import path
from school_admin.personal_views import eleve_view

app_name = 'eleve'

urlpatterns = [
    # Dashboard
    path('eleve/dashboard/', eleve_view.dashboard_eleve, name='dashboard_eleve'),
    
    # Emploi du temps
    path('eleve/emploi-du-temps/', eleve_view.emploi_du_temps_eleve, name='emploi_du_temps'),
    
    # Notes et évaluations
    path('eleve/notes-evaluations/', eleve_view.notes_evaluations_eleve, name='notes_evaluations'),
    
    # Absences et retards
    path('eleve/absences-retards/', eleve_view.absences_retards_eleve, name='absences_retards'),
    
    # Profil
    path('eleve/profil/', eleve_view.profil_eleve, name='profil_eleve'),
    
    # Sanctions (uniquement pour les parents)
    path('eleve/sanctions/', eleve_view.sanctions_eleve, name='sanctions_eleve'),
    
    # Annonces
    path('eleve/annonces/', eleve_view.annonces_eleve, name='annonces_eleve'),

    # Notifications
    path('eleve/notifications/', eleve_view.notifications_eleve, name='notifications_eleve'),
    
    # Déconnexion
    path('eleve/deconnexion/', eleve_view.deconnexion_eleve, name='deconnexion_eleve'),
]
