from django.urls import path

from ..personal_views.administrateur_etablissement_view import *
from ..controllers.classe_controller import ClasseController
from ..controllers.emploi_du_temps_controller import EmploiDuTempsController
from ..controllers.configuration_horaire_controller import ConfigurationHoraireController

app_name = 'administrateur_etablissement'

urlpatterns = [
    path('dashboard/administrateur_etablissement/', dashboard_administrateur_etablissement, name='dashboard_administrateur_etablissement'),
    
    # URLs pour la gestion des classes
    path('classes/', ClasseController.liste_classes, name='liste_classes'),
    path('classes/examens-concours/', ClasseController.liste_classes_examens_concours, name='liste_classes_examens_concours'),
    path('classes/ajouter/', ClasseController.ajouter_classe, name='ajouter_classe'),
    path('classes/filieres/', ClasseController.liste_filieres, name='liste_filieres'),
    path('classes/specialite/<int:specialite_id>/', ClasseController.liste_classes_specialite, name='liste_classes_specialite'),
    path('classes/filieres/ajouter/', ClasseController.ajouter_filiere, name='ajouter_filiere'),
    path('classes/filieres/<int:filiere_id>/modifier/', ClasseController.modifier_filiere, name='modifier_filiere'),
    path('classes/filieres/<int:filiere_id>/supprimer/', ClasseController.supprimer_filiere, name='supprimer_filiere'),
    # URLs spécifiques avant l'URL générique detail_classe pour éviter les conflits
    path('classes/<int:classe_id>/data/', ClasseController.get_classe_data, name='get_classe_data'),
    path('classes/<int:classe_id>/modifier/', ClasseController.modifier_classe, name='modifier_classe'),
    path('classes/<int:classe_id>/supprimer/', ClasseController.supprimer_classe, name='supprimer_classe'),
    path('classes/<int:classe_id>/toggle/', ClasseController.toggle_actif, name='toggle_actif'),
    path('classes/<int:classe_id>/', ClasseController.detail_classe, name='detail_classe'),
    
    # URLs pour la gestion des emplois du temps
    path('emplois-du-temps/', EmploiDuTempsController.liste_emplois_du_temps, name='liste_emplois_du_temps'),
    path('emplois-du-temps/classe/<int:classe_id>/', EmploiDuTempsController.detail_emploi_du_temps, name='detail_emploi_du_temps'),
    path('emplois-du-temps/classe/<int:classe_id>/creer/', EmploiDuTempsController.creer_emploi_du_temps, name='creer_emploi_du_temps'),
    path('emplois-du-temps/classe/<int:classe_id>/imprimer/', EmploiDuTempsController.imprimer_emploi_du_temps, name='imprimer_emploi_du_temps'),
    path('emplois-du-temps/<int:emploi_id>/publier/', EmploiDuTempsController.publier_emploi_du_temps, name='publier_emploi_du_temps'),
    
    # URLs pour la gestion des créneaux
    path('emplois-du-temps/<int:emploi_id>/ajouter-creneau/', EmploiDuTempsController.ajouter_creneau, name='ajouter_creneau'),
    path('emplois-du-temps/creneau/<int:creneau_id>/modifier/', EmploiDuTempsController.modifier_creneau, name='modifier_creneau'),
    path('emplois-du-temps/creneau/<int:creneau_id>/supprimer/', EmploiDuTempsController.supprimer_creneau, name='supprimer_creneau'),
    
    # URLs pour la configuration des horaires
    path('configuration-horaires/', ConfigurationHoraireController.gerer_configuration, name='configuration_horaires'),
    path('configuration-horaires/periodes/', ConfigurationHoraireController.gerer_periodes, name='gerer_periodes'),
]