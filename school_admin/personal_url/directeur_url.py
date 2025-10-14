from django.urls import path
from ..personal_views.directeur_view import *

app_name = 'directeur'  # ← Changement du namespace pour éviter le conflit

urlpatterns = [
    path('dashboard/directeur/', dashboard_directeur, name='dashboard_directeur'),
    path('facturation/directeur/', facturation_directeur, name='facturation_directeur'),
    path('gestion-pedagogique/', gestion_pedagogique, name='gestion_pedagogique'),
    path('gestion-eleves/', gestion_eleves, name='gestion_eleves'),
    path('gestion-etablissement/', gestion_etablissement, name='gestion_etablissement'),
]
