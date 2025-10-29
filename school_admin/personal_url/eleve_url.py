"""
URLs pour l'espace élève
"""
from django.urls import path
from school_admin.personal_views import eleve_view

app_name = 'eleve'

urlpatterns = [
    # Dashboard
    path('eleve/dashboard/', eleve_view.dashboard_eleve, name='dashboard_eleve'),
    
    # Déconnexion
    path('eleve/deconnexion/', eleve_view.deconnexion_eleve, name='deconnexion_eleve'),
]
