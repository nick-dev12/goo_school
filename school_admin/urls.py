from django.urls import path, include
from . import views
from . import pwa_views
from .controllers.administrateur_compte_controller import AdministrateurCompteController
from .personal_views.administrateur_view import *
from .personal_views.commercial_view import *
from .personal_views.comptable_view import *
from .controllers.activites_commerciales_controller import ActivitesCommercialesController
from .personal_views.directeur_view import verifier_bulletin_qr
from .api_views import fcm_views, fcm_test_views, test_notes_notifications

app_name = 'school_admin'

urlpatterns =[
    # PWA - Routes pour la Progressive Web App (doivent être en premier)
    path('manifest.json', pwa_views.manifest_view, name='manifest'),
    path('service-worker.js', pwa_views.service_worker_view, name='service_worker'),
    path('offline/', pwa_views.offline_view, name='offline'),
    
    # Service Worker Firebase (doit être à la racine)
    path('firebase-messaging-sw.js', views.firebase_messaging_sw, name='firebase_messaging_sw'),
    
    # API FCM
    path('api/fcm/save-token/', fcm_views.save_fcm_token, name='save_fcm_token'),
    path('api/fcm/delete-token/', fcm_views.delete_fcm_token, name='delete_fcm_token'),
    path('api/fcm/test-notification/', fcm_test_views.test_notification, name='test_notification'),
    path('api/fcm/check-status/', fcm_test_views.check_fcm_status, name='check_fcm_status'),
    
    # Page de test FCM
    path('test-fcm/', views.test_fcm_page, name='test_fcm_page'),
    
    # API Test Notifications de Notes
    path('api/test/send-note-notification/', test_notes_notifications.test_send_note_notification, name='test_send_note_notification'),
    path('api/test/get-eleves-with-tokens/', test_notes_notifications.get_eleves_with_tokens, name='get_eleves_with_tokens'),
    path('test-notes-notifications/', test_notes_notifications.test_notes_notifications_page, name='test_notes_notifications_page'),
    

    # Autres routes existantes
    path('', dashboard_administrateur, name='dashboard'),
    path('etablissements/',etablissements, name='etablissements'),
    
    # Suivi des activités commerciales
    path('activites-commerciales/', ActivitesCommercialesController.liste_prospects, name='suivi_activites_commerciales'),
    path('activites-commerciales/prospect/<int:prospect_id>/', ActivitesCommercialesController.detail_prospect, name='detail_prospect'),
    path('activites-commerciales/performances/', ActivitesCommercialesController.analyse_performances, name='analyse_performances_commerciaux'),
    path('etablissements/ajouter', ajout_etablissement, name='ajout_etablissement'),
    path('etablissements/detaille/', detaille_etablissement, name='detaille_etablissement'),
    path('etablissements/update/', administrateur_update_etablissement, name='administrateur_update_etablissement'),
    path('etablissements/messages/', message_etablissement, name='message_etablissement'),
    path('etablissements/messages/detail/', detail_message, name='detail_message'),
    path('annonces/', annonces, name='annonces'),
    path('bulletins/verifier/', verifier_bulletin_qr, name='verifier_bulletin_qr'),
    
    path('parametres/administrateur/', parametres, name='parametres_administrateur'),
    path('management_equipes/', management_equipes, name='management_equipes'),
    
    # Gestion des équipes
    path('management_equipes/ajouter/', add_team_member, name='add_team_member'),
    path('commercial/profile/<int:commercial_id>/', commercial_profile, name='commercial_profile'),
    path('team_member/profile/<int:member_id>/', team_member_profile, name='team_member_profile'),
    path('team_member/update/<int:member_id>/', update_team_member, name='update_team_member'),
    path('team_member/toggle_status/<int:member_id>/', toggle_team_member_status, name='toggle_team_member_status'),
    path('team_member/delete/<int:member_id>/', delete_team_member, name='delete_team_member'),
   
    
    # Authentification
    path('inscription/', views.inscription_compte_user, name='inscription_compte_user'),
    path('connexion/', views.connexion_compte_user, name='connexion_compte_user'),
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/verify/<str:identifier>/<str:user_type>/', views.password_reset_verify, name='password_reset_verify'),
    path('password-reset/professeur/verify/<str:matricule>/', views.password_reset_professeur_verify, name='password_reset_professeur_verify'),
    path('password-reset/professeur/reset/<str:matricule>/', views.password_reset_professeur_reset, name='password_reset_professeur_reset'),
    path('password-reset/eleve/verify/<str:matricule>/', views.password_reset_eleve_verify, name='password_reset_eleve_verify'),
    path('password-reset/eleve/reset/<str:matricule>/', views.password_reset_eleve_reset, name='password_reset_eleve_reset'),
    path('password-reset/parent/verify/<str:matricule>/', views.password_reset_parent_verify, name='password_reset_parent_verify'),
    path('password-reset/parent/reset/<str:matricule>/', views.password_reset_parent_reset, name='password_reset_parent_reset'),
    path(
        'connexion/professeurs/otp/',
        views.professeur_connexion_otp_request,
        name='prof_connexion_otp',
    ),
    path(
        'connexion/professeurs/otp/verification/<uuid:token>/',
        views.professeur_connexion_otp_verification,
        name='prof_connexion_otp_verify',
    ),
    
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
        path('gestion_comptable/depense/<int:depense_id>/', depense_detail_json, name='depense_detail_json'),
        path('gestion_comptable/depenses/<int:depense_id>/', depense_detail, name='depense_detail'),
        path('paiements_retard/',paiements_retard, name='paiements_retard'),
        path('calculs_automatiques/',calculs_automatiques, name='calculs_automatiques'),
        path('rapports_mensuels/',rapports_mensuels, name='rapports_mensuels'),
        path('rapports_annuels/',rapports_annuels, name='rapports_annuels'),
        path('gestion_etablissements/',gestion_etablissements, name='gestion_etablissements'),
        path('details_financiers_etablissement/<int:etablissement_id>/',details_financiers_etablissement, name='details_financiers_etablissement'),
        path('traiter_paiement_facture/<int:etablissement_id>/',traiter_paiement_facture, name='traiter_paiement_facture'),
        path('facture_etablissement/',facture_etablissement, name='facture_etablissement'),
        path('envoyer_facture/<str:facture_numero>/<int:etablissement_id>/',envoyer_facture, name='envoyer_facture'),
        path('mettre_a_jour_statuts_factures/',mettre_a_jour_statuts_factures, name='mettre_a_jour_statuts_factures'),
        path('gestion_personnel_financier/',gestion_personnel_financier, name='gestion_personnel_financier'),
        path('gestion_depenses/',gestion_depenses, name='gestion_depenses'),
        path('modifier_depense/<int:depense_id>/',modifier_depense, name='modifier_depense'),
        path('confirmer_depense/<int:depense_id>/',confirmer_depense, name='confirmer_depense'),
        path('ajouter_budget/',ajouter_budget, name='ajouter_budget'),
        path('modifier_budget/<int:budget_id>/',modifier_budget, name='modifier_budget'),
        path('supprimer_budget/<int:budget_id>/',supprimer_budget, name='supprimer_budget'),
]

# Inclure les URLs des professeurs
from .personal_url.professeur_url import urlpatterns as professeur_urls
urlpatterns += professeur_urls

# Inclure les URLs des matières
from .personal_url.matiere_url import urlpatterns as matiere_urls
urlpatterns += matiere_urls

# Inclure les URLs d'affectation
from .personal_url.affectation_url import urlpatterns as affectation_urls
urlpatterns += affectation_urls

# Inclure les URLs des salles
from .personal_url.salle_url import urlpatterns as salle_urls
urlpatterns += salle_urls

# Inclure les URLs des affectations de salles
from .personal_url.affectation_salle_url import urlpatterns as affectation_salle_urls
urlpatterns += affectation_salle_urls

# Inclure les URLs des enseignants
from .personal_url.enseignant_url import urlpatterns as enseignant_urls
urlpatterns += enseignant_urls

# Inclure les URLs des élèves
from .personal_url.eleve_url import urlpatterns as eleve_urls
urlpatterns += eleve_urls

# Inclure les URLs du directeur
from .personal_url.directeur_url import urlpatterns as directeur_urls
urlpatterns += directeur_urls

# Inclure les URLs des parents
from .personal_url.parent_url import urlpatterns as parent_urls
urlpatterns += parent_urls
