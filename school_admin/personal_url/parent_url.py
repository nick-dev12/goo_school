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
    
    # Annonces
    path('parent/annonces/', parent_view.annonces_parent, name='annonces_parent'),
    
    # Notifications
    path(
        'parent/notifications/<int:notification_id>/marquer-lue/',
        parent_view.marquer_notification_parent,
        name='marquer_notification_parent'
    ),
    path('parent/notifications/', parent_view.notifications_parent, name='notifications_parent'),
    
    # Déconnexion
    path('parent/deconnexion/', parent_view.deconnexion_parent, name='deconnexion_parent'),
    
    # Profil
    path('parent/profil/', parent_view.profil_parent, name='profil_parent'),
]

