from django.urls import path
from ..controllers.affectation_controller import AffectationController

app_name = 'affectation'

urlpatterns = [
    path('affectation/professeurs/', AffectationController.affectation_professeurs, name='affectation_professeurs'),
    path('affectation/affecter/', AffectationController.affecter_professeur, name='affecter_professeur'),
    path('affectation/professeur/<int:professeur_id>/affectations/', AffectationController.get_affectations_professeur, name='get_affectations_professeur'),
]
