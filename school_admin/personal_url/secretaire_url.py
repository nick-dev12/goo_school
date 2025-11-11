from django.urls import path
from ..personal_views.secretaire_view import *

app_name = 'secretaire'

urlpatterns = [
    path('dashboard/secretaire/', dashboard_secretaire, name='dashboard_secretaire'),
    path('inscription/eleves/', inscription_eleves, name='inscription_eleves'),
    path('liste/eleves/', liste_eleves, name='liste_eleves'),
    path('cartes-identite/eleves/', cartes_identite_eleves, name='cartes_identite_eleves'),
    path('detail/eleve/<int:eleve_id>/', detail_eleve, name='detail_eleve'),
    path('carte-identite/eleve/<int:eleve_id>/', carte_identite_eleve, name='carte_identite_eleve'),
    path('cartes-identite/classe/<int:classe_id>/', cartes_identite_classe, name='cartes_identite_classe'),
    path('transfer/eleve/<int:eleve_id>/', transfer_eleve, name='transfer_eleve'),
    path('reçu/eleve/<int:eleve_id>/', reçu_inscription_eleve, name='reçu_inscription_eleve'),
    path('supprimer/eleve/<int:eleve_id>/', supprimer_eleve, name='supprimer_eleve'),
    path('synchroniser/facturation/', synchroniser_facturation, name='synchroniser_facturation'),
    # Notes détaillées par matière
    path('api/notes-detail/<int:eleve_id>/<int:matiere_id>/', get_notes_detail_matiere, name='get_notes_detail_matiere'),
    # Gestion des classes
    path('gestion/classes/', gestion_classes, name='gestion_classes'),
    path('detail/classe/<int:classe_id>/', detail_classe, name='detail_classe'),
    path('imprimer/liste/eleves/<int:classe_id>/', imprimer_liste_eleves, name='imprimer_liste_eleves'),
    # Gestion des sanctions
    path('directeur/soumettre-sanction/', soumettre_sanction_directeur, name='soumettre_sanction_directeur'),
]
