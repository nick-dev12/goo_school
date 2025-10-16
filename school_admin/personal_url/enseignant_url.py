# school_admin/personal_url/enseignant_url.py

from django.urls import path
from ..personal_views.enseignant_view import (
    dashboard_enseignant,
    gestion_classes_enseignant,
    gestion_eleves_enseignant,
    gestion_notes_enseignant,
    noter_eleves_enseignant,
    creer_evaluation_enseignant,
    liste_evaluations_enseignant,
    calculer_moyennes_classe,
    soumettre_releve_notes,
    liste_presence_enseignant,
    valider_presence_enseignant,
    detail_eleve_enseignant,
    modifier_presence_eleve,
    historique_presence_eleve,
    justifier_absence_eleve,
    detail_classe_enseignant,
    soumettre_sanction_eleve,
    historique_sanctions_eleve,
    liste_sanctions_classe,
    parametres_profil_enseignant,
    emploi_du_temps_enseignant
)

app_name = 'enseignant'

urlpatterns = [
    path('dashboard/enseignant/', dashboard_enseignant, name='dashboard_enseignant'),
    path('enseignant/classes/', gestion_classes_enseignant, name='gestion_classes'),
    path('enseignant/eleves/', gestion_eleves_enseignant, name='gestion_eleves'),
    path('enseignant/notes/', gestion_notes_enseignant, name='gestion_notes'),
    path('enseignant/noter/<int:classe_id>/', noter_eleves_enseignant, name='noter_eleves'),
    path('enseignant/evaluation/creer/<int:classe_id>/', creer_evaluation_enseignant, name='creer_evaluation'),
    path('enseignant/evaluations/', liste_evaluations_enseignant, name='liste_evaluations'),
    path('enseignant/calculer-moyennes/<int:classe_id>/', calculer_moyennes_classe, name='calculer_moyennes'),
    path('enseignant/soumettre-releve/<int:classe_id>/', soumettre_releve_notes, name='soumettre_releve'),
    path('enseignant/presence/<int:classe_id>/', liste_presence_enseignant, name='liste_presence'),
    path('enseignant/valider-presence/<int:classe_id>/', valider_presence_enseignant, name='valider_presence'),
    path('enseignant/eleve/<int:eleve_id>/', detail_eleve_enseignant, name='detail_eleve'),
    path('enseignant/modifier-presence/<int:presence_id>/', modifier_presence_eleve, name='modifier_presence'),
    path('enseignant/historique-presence/<int:eleve_id>/', historique_presence_eleve, name='historique_presence'),
    path('enseignant/justifier-absence/', justifier_absence_eleve, name='justifier_absence'),
    path('enseignant/classe/<int:classe_id>/', detail_classe_enseignant, name='detail_classe'),
    path('enseignant/soumettre-sanction/', soumettre_sanction_eleve, name='soumettre_sanction'),
    path('enseignant/historique-sanctions/<int:eleve_id>/', historique_sanctions_eleve, name='historique_sanctions'),
    path('enseignant/sanctions-classe/<int:classe_id>/', liste_sanctions_classe, name='liste_sanctions_classe'),
    path('enseignant/parametres-profil/', parametres_profil_enseignant, name='parametres_profil'),
    path('enseignant/emploi-du-temps/', emploi_du_temps_enseignant, name='emploi_du_temps'),
]

