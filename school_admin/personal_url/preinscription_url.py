from django.urls import path
from ..controllers.preinscription_controller import PreinscriptionController

app_name = 'preinscription'

urlpatterns = [
    path('<str:token>/', PreinscriptionController.formulaire_preinscription, name='formulaire'),
    path('<str:token>/confirmation/<int:preinscription_id>/', PreinscriptionController.confirmation_preinscription, name='confirmation'),
]

