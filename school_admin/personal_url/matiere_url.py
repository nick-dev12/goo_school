from django.urls import path
from ..controllers.matiere_controller import MatiereController

app_name = 'matiere'

urlpatterns = [
    path('matieres/', MatiereController.liste_matieres, name='liste_matieres'),
    path('matieres/ajouter/', MatiereController.ajouter_matiere, name='ajouter_matiere'),
    path('matieres/<int:matiere_id>/', MatiereController.detail_matiere, name='detail_matiere'),
    path('matieres/<int:matiere_id>/toggle/', MatiereController.toggle_actif, name='toggle_actif'),
    path('matieres/<int:matiere_id>/supprimer/', MatiereController.supprimer_matiere, name='supprimer_matiere'),
]
