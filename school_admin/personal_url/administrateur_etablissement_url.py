from django.urls import path

from ..personal_views.administrateur_etablissement_view import *
from ..controllers.classe_controller import ClasseController
from ..controllers.emploi_du_temps_controller import EmploiDuTempsController

app_name = 'administrateur_etablissement'

urlpatterns = [
    path('dashboard/administrateur_etablissement/', dashboard_administrateur_etablissement, name='dashboard_administrateur_etablissement'),
    
    # URLs pour la gestion des classes
    path('classes/', ClasseController.liste_classes, name='liste_classes'),
    path('classes/ajouter/', ClasseController.ajouter_classe, name='ajouter_classe'),
    path('classes/<int:classe_id>/', ClasseController.detail_classe, name='detail_classe'),
    path('classes/<int:classe_id>/toggle/', ClasseController.toggle_actif, name='toggle_actif'),
    
    # URLs pour la gestion des emplois du temps
    path('emplois-du-temps/', EmploiDuTempsController.liste_emplois_du_temps, name='liste_emplois_du_temps'),
    path('emplois-du-temps/classe/<int:classe_id>/', EmploiDuTempsController.detail_emploi_du_temps, name='detail_emploi_du_temps'),
    path('emplois-du-temps/classe/<int:classe_id>/creer/', EmploiDuTempsController.creer_emploi_du_temps, name='creer_emploi_du_temps'),
    
    # URLs pour la gestion des créneaux
    path('emplois-du-temps/<int:emploi_id>/ajouter-creneau/', EmploiDuTempsController.ajouter_creneau, name='ajouter_creneau'),
    path('emplois-du-temps/creneau/<int:creneau_id>/modifier/', EmploiDuTempsController.modifier_creneau, name='modifier_creneau'),
    path('emplois-du-temps/creneau/<int:creneau_id>/supprimer/', EmploiDuTempsController.supprimer_creneau, name='supprimer_creneau'),
]