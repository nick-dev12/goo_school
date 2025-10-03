from django.urls import path
from ..personal_views.directeur_view import *

app_name = 'directeur'  # ← Changement du namespace pour éviter le conflit

urlpatterns = [
    path('dashboard/directeur/', dashboard_directeur, name='dashboard_directeur'),
]
