# school_admin/personal_url/professeur_url.py

from django.urls import path
from ..controllers.professeur_controller import ProfesseurController

app_name = 'professeur'

urlpatterns = [
    path('professeurs/', ProfesseurController.liste_professeurs, name='liste_professeurs'),
    path('professeurs/ajouter/', ProfesseurController.ajouter_professeur, name='ajouter_professeur'),
    path('professeurs/<int:professeur_id>/', ProfesseurController.detail_professeur, name='detail_professeur'),
    path('professeurs/<int:professeur_id>/modifier/', ProfesseurController.modifier_professeur, name='modifier_professeur'),
    path('professeurs/<int:professeur_id>/toggle/', ProfesseurController.toggle_actif, name='toggle_actif'),
]
