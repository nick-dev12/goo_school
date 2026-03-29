from django.urls import path
from ..controllers.matiere_controller import MatiereController
from ..controllers.module_controller import (
    liste_modules,
    ajouter_module,
    detail_module,
    supprimer_module,
)

app_name = 'matiere'

urlpatterns = [
    path('matieres/', MatiereController.liste_matieres, name='liste_matieres'),
    path('matieres/ajouter/', MatiereController.ajouter_matiere, name='ajouter_matiere'),
    path('matieres/<int:matiere_id>/', MatiereController.detail_matiere, name='detail_matiere'),
    path('matieres/<int:matiere_id>/toggle/', MatiereController.toggle_actif, name='toggle_actif'),
    path('matieres/<int:matiere_id>/supprimer/', MatiereController.supprimer_matiere, name='supprimer_matiere'),
    # Modules (enseignement supérieur)
    path('matieres/modules/', liste_modules, name='liste_modules'),
    path('matieres/modules/ajouter/', ajouter_module, name='ajouter_module'),
    path('matieres/modules/<int:module_id>/', detail_module, name='detail_module'),
    path('matieres/modules/<int:module_id>/supprimer/', supprimer_module, name='supprimer_module'),
]
