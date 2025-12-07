from django.urls import path
from ..controllers.personnel_controller import PersonnelController

app_name = 'personnel'

urlpatterns = [
    path('personnel/', PersonnelController.liste_personnel, name='liste_personnel'),
    path('personnel/ajouter/', PersonnelController.ajouter_personnel, name='ajouter_personnel'),
    path('personnel/get-permissions/', PersonnelController.get_permissions_par_fonction, name='get_permissions'),
    path('personnel/<int:personnel_id>/', PersonnelController.detail_personnel, name='detail_personnel'),
    path('personnel/<int:personnel_id>/modifier/', PersonnelController.modifier_personnel, name='modifier_personnel'),
    path('personnel/<int:personnel_id>/toggle/', PersonnelController.toggle_actif, name='toggle_actif'),
]
