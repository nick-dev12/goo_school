# school_admin/personal_url/enseignant_primaire_url.py

from django.urls import path
from ..personal_views.enseignant_primaire_view import (
    dashboard_enseignant_primaire,
    gestion_classes_primaire,
    gestion_eleves_primaire,
    gestion_notes_primaire,
    exercices_maison_primaire,
    gestion_presence_primaire,
    eleves_en_difficulte_primaire,
    noter_eleves_primaire,
    voir_releve_primaire,
    soumettre_releve_primaire,
    imprimer_releve_primaire,
    creer_evaluation_primaire,
    modifier_evaluation_primaire,
    supprimer_evaluation_primaire,
    liste_evaluations_primaire,
    evaluations_classe_primaire,
    calculer_moyennes_classe_primaire,
    liste_presence_primaire,
    valider_presence_primaire,
    detail_eleve_primaire,
    modifier_presence_eleve_primaire,
    historique_presence_eleve_primaire,
    justifier_absence_eleve_primaire,
    detail_classe_primaire,
    soumettre_sanction_eleve_primaire,
    historique_sanctions_eleve_primaire,
    liste_sanctions_classe_primaire,
    parametres_profil_primaire,
    historique_annees_primaire,
    detail_historique_annee_primaire,
    emploi_du_temps_primaire,
    imprimer_tableau_presence,
    annonces_enseignant_primaire,
    justifications_notes_primaire,
)

app_name = 'enseignant_primaire'

urlpatterns = [
    # Dashboard
    path('enseignant/primaire/dashboard/', dashboard_enseignant_primaire, name='dashboard'),
    
    # Gestion des classes
    path('enseignant/primaire/classes/', gestion_classes_primaire, name='gestion_classes'),
    path('enseignant/primaire/classe/<int:classe_id>/', detail_classe_primaire, name='detail_classe'),
    
    # Gestion des élèves
    path('enseignant/primaire/eleves/', gestion_eleves_primaire, name='gestion_eleves'),
    path('enseignant/primaire/eleve/<int:eleve_id>/', detail_eleve_primaire, name='detail_eleve'),
    
    # Gestion des notes et évaluations
    path('enseignant/primaire/notes/', gestion_notes_primaire, name='gestion_notes'),
    path('enseignant/primaire/justifications-notes/', justifications_notes_primaire, name='justifications_notes'),
    path('enseignant/primaire/exercices/', exercices_maison_primaire, name='exercices_maison'),
    path('enseignant/primaire/presence/', gestion_presence_primaire, name='gestion_presence'),
    path('enseignant/primaire/eleves-difficulte/', eleves_en_difficulte_primaire, name='eleves_en_difficulte'),
    path('enseignant/primaire/noter/<int:classe_id>/', noter_eleves_primaire, name='noter_eleves'),
    path('enseignant/primaire/releve/<int:classe_id>/', voir_releve_primaire, name='voir_releve'),
    path('enseignant/primaire/soumettre-releve/<int:classe_id>/', soumettre_releve_primaire, name='soumettre_releve'),
    path('enseignant/primaire/imprimer-releve/<int:classe_id>/', imprimer_releve_primaire, name='imprimer_releve'),
    path('enseignant/primaire/evaluation/creer/<int:classe_id>/', creer_evaluation_primaire, name='creer_evaluation'),
    path('enseignant/primaire/modifier-evaluation/<int:evaluation_id>/', modifier_evaluation_primaire, name='modifier_evaluation'),
    path('enseignant/primaire/supprimer-evaluation/<int:evaluation_id>/', supprimer_evaluation_primaire, name='supprimer_evaluation'),
    path('enseignant/primaire/evaluations/', liste_evaluations_primaire, name='liste_evaluations'),
    path('enseignant/primaire/evaluations-classe/<int:classe_id>/', evaluations_classe_primaire, name='evaluations_classe'),
    path('enseignant/primaire/calculer-moyennes/<int:classe_id>/', calculer_moyennes_classe_primaire, name='calculer_moyennes'),
    
    # Gestion des présences
    path('enseignant/primaire/presence/<int:classe_id>/', liste_presence_primaire, name='liste_presence'),
    path('enseignant/primaire/valider-presence/<int:classe_id>/', valider_presence_primaire, name='valider_presence'),
    path('enseignant/primaire/modifier-presence/<int:presence_id>/', modifier_presence_eleve_primaire, name='modifier_presence'),
    path('enseignant/primaire/historique-presence/<int:eleve_id>/', historique_presence_eleve_primaire, name='historique_presence'),
    path('enseignant/primaire/justifier-absence/', justifier_absence_eleve_primaire, name='justifier_absence'),
    path('enseignant/primaire/imprimer-tableau-presence/<int:classe_id>/', imprimer_tableau_presence, name='imprimer_tableau_presence'),
    
    # Gestion des sanctions
    path('enseignant/primaire/soumettre-sanction/', soumettre_sanction_eleve_primaire, name='soumettre_sanction'),
    path('enseignant/primaire/historique-sanctions/<int:eleve_id>/', historique_sanctions_eleve_primaire, name='historique_sanctions'),
    path('enseignant/primaire/sanctions-classe/<int:classe_id>/', liste_sanctions_classe_primaire, name='liste_sanctions_classe'),
    
    # Paramètres et emploi du temps
    path('enseignant/primaire/parametres-profil/', parametres_profil_primaire, name='parametres_profil'),
    path('enseignant/primaire/historique-annees/', historique_annees_primaire, name='historique_annees'),
    path('enseignant/primaire/historique-annees/<int:annee_id>/', detail_historique_annee_primaire, name='historique_annee_detail'),
    path('enseignant/primaire/emploi-du-temps/', emploi_du_temps_primaire, name='emploi_du_temps'),
    
    # Annonces
    path('enseignant/primaire/annonces/', annonces_enseignant_primaire, name='annonces_enseignant'),
]

