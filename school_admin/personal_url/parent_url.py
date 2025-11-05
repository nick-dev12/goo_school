"""
URLs pour l'espace parent
"""
from django.urls import path
from school_admin.personal_views import parent_view

urlpatterns = [
    # Dashboard principal (liste des enfants)
    path('parent/dashboard/', parent_view.dashboard_parent, name='dashboard_parent'),
    
    # Dashboard d'un enfant spécifique
    path('parent/enfant/<int:eleve_id>/', parent_view.dashboard_enfant, name='dashboard_enfant'),
    
    # Demande de liaison avec un enfant
    path('parent/demande-liaison/', parent_view.demande_liaison_enfant, name='demande_liaison_enfant'),
    
    # Retour à la sélection d'enfant
    path('parent/retour/', parent_view.retour_selection_enfant, name='retour_selection_enfant'),
    
    # Déconnexion
    path('parent/deconnexion/', parent_view.deconnexion_parent, name='deconnexion_parent'),
]

