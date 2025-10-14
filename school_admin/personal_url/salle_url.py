from django.urls import path
from ..controllers.salle_controller import SalleController

app_name = 'salle'

urlpatterns = [
    path('salles/', SalleController.liste_salles, name='liste_salles'),
    path('salles/ajouter/', SalleController.ajouter_salle, name='ajouter_salle'),
    path('salles/<int:salle_id>/', SalleController.detail_salle, name='detail_salle'),
    path('salles/<int:salle_id>/toggle/', SalleController.toggle_actif, name='toggle_actif'),
    path('salles/<int:salle_id>/modifier/', SalleController.modifier_salle, name='modifier_salle'),
]
