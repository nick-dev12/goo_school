# school_admin/personal_url/eleve_url.py

from django.urls import path
from ..personal_views.eleve_view import *

app_name = 'eleve'

urlpatterns = [
    path('dashboard/eleve/', dashboard_eleve, name='dashboard_eleve'),
]
