# school_admin/personal_url/personnel_administratif_url.py

from django.urls import path
from ..personal_views.personnel_administratif_view import *

app_name = 'personnel_administratif'

urlpatterns = [
    path('', dashboard_personnel_administratif, name='dashboard_personnel_administratif'),
    path('profil/', profil_personnel_administratif, name='profil'),
    path('eleves/', liste_eleves_personnel, name='liste_eleves'),
    path('enseignants/', liste_enseignants_personnel, name='liste_enseignants'),
]
