from django.urls import path
from ..personal_views.directeur_view import *
from ..controllers.examen_controller import *

app_name = 'directeur'  # ← Changement du namespace pour éviter le conflit

urlpatterns = [
    path('dashboard/directeur/', dashboard_directeur, name='dashboard_directeur'),
    path('facturation/directeur/', facturation_directeur, name='facturation_directeur'),
    path('gestion-pedagogique/', gestion_pedagogique, name='gestion_pedagogique'),
    path('gestion-eleves/', gestion_eleves, name='gestion_eleves'),
    path('notes-et-resultats/', notes_et_resultats, name='notes_et_resultats'),
    path('suivi-presence/', suivi_presence, name='suivi_presence'),
    path('gestion-etablissement/', gestion_etablissement, name='gestion_etablissement'),
    path('periodes-scolaires/', gestion_periodes_scolaires, name='gestion_periodes_scolaires'),
    
    # Gestion des examens
    path('gestion-examens/', gestion_examens, name='gestion_examens'),
    path('emploi-du-temps-examens/', emploi_du_temps_examens, name='emploi_du_temps_examens'),
    path('configurer-creneaux-examen/<int:session_id>/', configurer_creneaux_examen, name='configurer_creneaux_examen'),
    path('modifier-session-examen/<int:session_id>/', modifier_session_examen, name='modifier_session_examen'),
    path('supprimer-session-examen/<int:session_id>/', supprimer_session_examen, name='supprimer_session_examen'),
]
