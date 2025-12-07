"""
URLs pour l'espace élève
"""
from django.urls import path
from school_admin.personal_views import eleve_view

app_name = 'eleve'

urlpatterns = [
    # Dashboard
    path('eleve/dashboard/', eleve_view.dashboard_eleve, name='dashboard_eleve'),
    path('eleve/devoirs/', eleve_view.devoirs_eleve, name='devoirs_eleve'),
    path('eleve/bulletin/', eleve_view.bulletin_eleve, name='bulletin_eleve'),
    
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
    
    # Convocations
    path('eleve/convocations/', eleve_view.convocations_eleve, name='convocations_eleve'),
    
    # Annonces
    path('eleve/annonces/', eleve_view.annonces_eleve, name='annonces_eleve'),

    # Notifications
    path('eleve/notifications/', eleve_view.notifications_eleve, name='notifications_eleve'),
    path('eleve/notifications/<int:notification_id>/click/', eleve_view.notification_eleve_click, name='notification_eleve_click'),
    
    # Historique des années scolaires
    path('eleve/historique-annees/', eleve_view.historique_annees_eleve, name='historique_annees'),
    path('eleve/historique-annees/<int:annee_id>/', eleve_view.detail_historique_annee_eleve, name='historique_annee_detail'),
    
    # Déconnexion
    path('eleve/deconnexion/', eleve_view.deconnexion_eleve, name='deconnexion_eleve'),
]
