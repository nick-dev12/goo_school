from django.urls import path
from . import views
from .controllers.administrateur_compte_controller import AdministrateurCompteController
from .personal_views.administrateur_view import *
from .personal_views.commercial_view import *
from .personal_views.comptable_view import *
app_name = 'school_admin'

urlpatterns =[
    # Autres routes existantes
    path('', dashboard_administrateur, name='dashboard'),
    path('etablissements/',etablissements, name='etablissements'),
    path('etablissements/ajouter', ajout_etablissement, name='ajout_etablissement'),
    path('etablissements/detaille/', detaille_etablissement, name='detaille_etablissement'),
    path('etablissements/update/', administrateur_update_etablissement, name='administrateur_update_etablissement'),
    path('etablissements/messages/', message_etablissement, name='message_etablissement'),
    path('etablissements/messages/detail/', detail_message, name='detail_message'),
    path('annonces/', annonces, name='annonces'),
    
    path('parametres/administrateur/', parametres, name='parametres_administrateur'),
    path('management_equipes/', management_equipes, name='management_equipes'),
    
    # Gestion des équipes
    path('management_equipes/ajouter/', add_team_member, name='add_team_member'),
    path('commercial/profile/<int:commercial_id>/', commercial_profile, name='commercial_profile'),
   
    
    # Authentification
    path('inscription/', views.inscription_compte_user, name='inscription_compte_user'),
    path('connexion/', views.connexion_compte_user, name='connexion_compte_user'),
    
    # Tableaux de bord par fonction
    path('dashboard/support/', views.dashboard_support, name='dashboard_support'),
    path('dashboard/developpeur/', views.dashboard_developpeur, name='dashboard_developpeur'),
    path('dashboard/marketing/', views.dashboard_marketing, name='dashboard_marketing'),
    path('dashboard/rh/', views.dashboard_rh, name='dashboard_rh'),
 
    
    #deconnexion par fonction
    path('deconnexion/commercial/', views.deconnexion_compte_commercial, name='deconnexion_compte_commercial'),
    path('deconnexion/administrateur/', views.deconnexion_compte_administrateur, name='deconnexion_compte_administrateur'),
    
    
    #profil administrateur
    path('profil_admin/', AdministrateurCompteController.profil_admin, name='profil_admin'),
    path('profil_admin/update/', AdministrateurCompteController.update_profil_admin, name='update_profil_admin'),
    path('profil_admin/update_password/', AdministrateurCompteController.update_password_admin, name='update_password_admin'),
   
        #commercial
        path('commercial/ajouter_etablissement/', commercial_ajouter_etablissement, name='commercial_ajouter_etablissement'),
        path('commercial/liste_etablissements/', commercial_liste_etablissements, name='commercial_liste_etablissements'),
        path('commercial/detail_etablissement/<int:etablissement_id>/', commercial_detail_etablissement, name='commercial_detail_etablissement'),
        path('commercial/update_status/<int:etablissement_id>/', commercial_update_status, name='commercial_update_status'),
        path('commercial/update_priority/<int:etablissement_id>/', commercial_update_priority, name='commercial_update_priority'),
        path('commercial/add_notes/<int:etablissement_id>/', commercial_add_notes, name='commercial_add_notes'),
        path('commercial/schedule_meeting/<int:etablissement_id>/', commercial_schedule_meeting, name='commercial_schedule_meeting'),
        path('commercial/update_general_info/<int:etablissement_id>/', commercial_update_general_info, name='commercial_update_general_info'),
        path('commercial/update_location/<int:etablissement_id>/', commercial_update_location, name='commercial_update_location'),
        path('commercial/delete_meeting/<int:etablissement_id>/', commercial_delete_meeting, name='commercial_delete_meeting'),
        path('commercial/delete_note/<int:etablissement_id>/', commercial_delete_note, name='commercial_delete_note'),
        path('commercial/rendez_vous/', commercial_rendez_vous, name='commercial_rendez_vous'),
        path('commercial/comptes_rendus/', commercial_comptes_rendus, name='commercial_comptes_rendus'),
        path('commercial/creer_rapport/<int:rendez_vous_id>/', commercial_creer_rapport, name='commercial_creer_rapport'),
        path('commercial/messages/', commercial_messages, name='commercial_messages'),
        path('commercial/conversation_etablissement/', commercial_conversation_etablissement, name='commercial_conversation_etablissement'),
        path('commercial/profil/', commercial_profil, name='commercial_profil'),
        path('dashboard/commercial/',dashboard_commercial, name='dashboard_commercial'),
        
        
        
        
        #comptable
        path('dashboard/comptable/',dashboard_comptable, name='dashboard_comptable'),
        path('suivi_revenus/',suivi_revenus, name='suivi_revenus'),
        path('paiements_retard/',paiements_retard, name='paiements_retard'),
        path('calculs_automatiques/',calculs_automatiques, name='calculs_automatiques'),
        path('rapports_mensuels/',rapports_mensuels, name='rapports_mensuels'),
        path('rapports_annuels/',rapports_annuels, name='rapports_annuels'),
        path('gestion_etablissements/',gestion_etablissements, name='gestion_etablissements'),
        path('details_financiers_etablissement',details_financiers_etablissement, name='details_financiers_etablissement'),
        path('facture_etablissement/',facture_etablissement, name='facture_etablissement'),
        path('gestion_personnel_financier/',gestion_personnel_financier, name='gestion_personnel_financier'),
        path('gestion_depenses/',gestion_depenses, name='gestion_depenses'),
]

