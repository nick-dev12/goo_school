from django.urls import path

from ..personal_views.administrateur_etablissement_view import *
from ..controllers.classe_controller import ClasseController

app_name = 'administrateur_etablissement'

urlpatterns = [
    path('dashboard/administrateur_etablissement/', dashboard_administrateur_etablissement, name='dashboard_administrateur_etablissement'),
    
    # URLs pour la gestion des classes
    path('classes/', ClasseController.liste_classes, name='liste_classes'),
    path('classes/ajouter/', ClasseController.ajouter_classe, name='ajouter_classe'),
    path('classes/<int:classe_id>/', ClasseController.detail_classe, name='detail_classe'),
    path('classes/<int:classe_id>/toggle/', ClasseController.toggle_actif, name='toggle_actif'),
]