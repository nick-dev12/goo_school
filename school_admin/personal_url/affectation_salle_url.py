from django.urls import path
from ..controllers.affectation_salle_controller import AffectationSalleController

app_name = 'affectation_salle'

urlpatterns = [
    path('affectations-salles/', AffectationSalleController.liste_affectations, name='liste_affectations'),
    path('affectations-salles/ajouter/', AffectationSalleController.ajouter_affectation, name='ajouter_affectation'),
    path('affectations-salles/<int:affectation_id>/', AffectationSalleController.detail_affectation, name='detail_affectation'),
    path('affectations-salles/<int:affectation_id>/modifier/', AffectationSalleController.modifier_affectation, name='modifier_affectation'),
    path('affectations-salles/<int:affectation_id>/supprimer/', AffectationSalleController.supprimer_affectation, name='supprimer_affectation'),
    path('affectations-salles/<int:affectation_id>/toggle/', AffectationSalleController.toggle_actif, name='toggle_actif'),
    path('api/disponibilites-salle/', AffectationSalleController.get_disponibilites_salle, name='get_disponibilites_salle'),
]
