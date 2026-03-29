from django.urls import path
from ..personal_views.directeur_view import *
from ..controllers.examen_controller import *
from ..controllers.preinscription_controller import PreinscriptionController

app_name = 'directeur'  # ← Changement du namespace pour éviter le conflit

urlpatterns = [
    path('dashboard/directeur/', dashboard_directeur, name='dashboard_directeur'),
    path('notifications/', notifications_directeur, name='notifications_directeur'),
    path('facturation/directeur/', facturation_directeur, name='facturation_directeur'),
    path('gestion-pedagogique/', gestion_pedagogique, name='gestion_pedagogique'),
    path('gestion-eleves/', gestion_eleves, name='gestion_eleves'),
    path('gestion-eleves/reinscription/', liste_reinscription_eleves, name='liste_reinscription'),
    path('gestion-eleves/reinscription/<int:eleve_id>/', reinscription_eleve, name='reinscription_eleve'),
    
    # Préinscriptions
    path('preinscription/liens/', PreinscriptionController.gerer_liens_preinscription, name='gerer_liens_preinscription'),
    path('preinscription/liens/toggle/', PreinscriptionController.toggle_lien_actif, name='toggle_lien_preinscription'),
    path('preinscription/liste/', PreinscriptionController.liste_preinscriptions, name='liste_preinscriptions'),
    path('preinscription/<int:preinscription_id>/', PreinscriptionController.detail_preinscription, name='detail_preinscription'),
    path('preinscription/<int:preinscription_id>/valider/', PreinscriptionController.valider_preinscription, name='valider_preinscription'),
    path('preinscription/<int:preinscription_id>/rejeter/', PreinscriptionController.rejeter_preinscription, name='rejeter_preinscription'),
    path('notes-et-resultats/', notes_et_resultats, name='notes_et_resultats'),
    path('notes-et-resultats/justifications/', justifications_notes_directeur, name='justifications_notes'),
    path('notes-et-resultats/justifications/classe/<int:classe_id>/', justifications_notes_classe_directeur, name='justifications_notes_classe'),
    path('bulletins/', bulletins_notes, name='bulletins_notes'),
    path('bulletins/voir/<int:classe_id>/<int:eleve_id>/', voir_bulletin_eleve, name='voir_bulletin_eleve'),
    path('bulletins/calculer-moyenne/<int:classe_id>/<int:eleve_id>/', calculer_moyenne_eleve, name='calculer_moyenne_eleve'),
    path('bulletins/imprimer/<int:classe_id>/<int:eleve_id>/', imprimer_bulletin_eleve, name='imprimer_bulletin_eleve'),
    path('bulletins/imprimer-classe/<int:classe_id>/', imprimer_bulletins_classe, name='imprimer_bulletins_classe'),
    path('bulletins/publier/<int:classe_id>/', publier_bulletins_classe, name='publier_bulletins_classe'),
    path('bulletins/visibilite/<int:classe_id>/', mettre_a_jour_visibilite_bulletins, name='mettre_a_jour_visibilite_bulletins'),
    path('bulletins/calculer-moyennes/<int:classe_id>/', calculer_moyennes_periode, name='calculer_moyennes_periode'),
    path('bulletins/calculer-moyenne-annuelle/<int:classe_id>/', calculer_moyenne_annuelle, name='calculer_moyenne_annuelle'),
    path('bulletins/configuration-moyennes/', configuration_moyennes_generales, name='configuration_moyennes_generales'),
    path('bulletins/configuration-standards/', configuration_standards_reussite, name='configuration_standards_reussite'),
    path('suivi-presence/', suivi_presence, name='suivi_presence'),
    path('suivi-presence/justifier/', justifier_absence_directeur, name='justifier_absence'),
    path('gestion-etablissement/', gestion_etablissement, name='gestion_etablissement'),
    path('gestion-administrative/', gestion_administrative, name='gestion_administrative'),
    path('periodes-scolaires/', gestion_periodes_scolaires, name='gestion_periodes_scolaires'),
    path('profil/etablissement/', profil_etablissement, name='profil_etablissement'),
    
    # Gestion des années scolaires
    path('annees-scolaires/', liste_annees_scolaires, name='liste_annees_scolaires'),
    path('annees-scolaires/creer/', creer_annee_scolaire, name='creer_annee_scolaire'),
    path('annees-scolaires/creer-obligatoire/', creer_annee_scolaire_obligatoire, name='creer_annee_scolaire_obligatoire'),
    path('annees-scolaires/<int:annee_id>/activer/', activer_annee_scolaire, name='activer_annee_scolaire'),
    path('annees-scolaires/<int:annee_id>/desactiver/', desactiver_annee_scolaire, name='desactiver_annee_scolaire'),
    path('annees-scolaires/<int:annee_id>/modifier/', modifier_annee_scolaire, name='modifier_annee_scolaire'),
    path('annees-scolaires/<int:annee_id>/', detail_annee_scolaire, name='detail_annee_scolaire'),
    path('changer-session/', changer_session_directeur, name='changer_session_directeur'),
    
    # API pour les détails des notes
    path('api/details-notes-matiere/', api_details_notes_matiere, name='api_details_notes_matiere'),
    path('api/details-notes-matiere-secondaire/', api_details_notes_matiere_secondaire, name='api_details_notes_matiere_secondaire'),
    path('api/debloquer-releve-matiere/', api_debloquer_releve_matiere, name='api_debloquer_releve_matiere'),
    
    # Impression du relevé de notes
    path('imprimer-releve-notes/<int:classe_id>/', imprimer_releve_notes, name='imprimer_releve_notes'),
    
    # Certificats de scolarité
    path('certificat-scolarite/liste/', certificat_scolarite_liste, name='certificat_scolarite_liste'),
    path('certificat-scolarite/generer/<int:eleve_id>/', generer_certificat_scolarite, name='generer_certificat_scolarite'),
    
    # Attestations de réussite
    path('attestation-reussite/liste/', attestation_reussite_liste, name='attestation_reussite_liste'),
    path('attestation-reussite/generer/<int:eleve_id>/', generer_attestation_reussite, name='generer_attestation_reussite'),
    
    # Attestations de conduite
    path('attestation-conduite/liste/', attestation_conduite_liste, name='attestation_conduite_liste'),
    path('attestation-conduite/generer/<int:eleve_id>/', generer_attestation_conduite, name='generer_attestation_conduite'),
    
    # Fiches d'inscription/réinscription
    path('fiche-inscription/liste/', fiche_inscription_liste, name='fiche_inscription_liste'),
    path('fiche-inscription/generer/<int:eleve_id>/', generer_fiche_inscription, name='generer_fiche_inscription'),
    path('fiche-inscription/classe/<int:classe_id>/imprimer/', imprimer_fiches_classe, name='imprimer_fiches_classe'),
    
    # Certificats de radiation/transfert
    path('certificat-radiation/liste/', certificat_radiation_liste, name='certificat_radiation_liste'),
    path('certificat-radiation/generer/<int:eleve_id>/', generer_certificat_radiation, name='generer_certificat_radiation'),
    
    # Liste nominative
    path('liste-nominative/<int:classe_id>/imprimer/', imprimer_liste_nominative, name='imprimer_liste_nominative'),
    
    # Liste de présence
    path('liste-presence/<int:classe_id>/<int:mois_numero>/<int:mois_annee>/imprimer/', imprimer_liste_presence, name='imprimer_liste_presence'),
    
    # Convocations
    path('convocation/liste/', convocation_liste, name='convocation_liste'),
    path('convocation/generer/<int:eleve_id>/', generer_convocation, name='generer_convocation'),
    path('convocation/voir/<int:eleve_id>/', voir_convocations_eleve, name='voir_convocations_eleve'),
    path('convocation/apercu/<int:convocation_id>/', apercu_convocation, name='apercu_convocation'),
    path('convocation/classe/<int:classe_id>/', convocation_classe, name='convocation_classe'),
    path('convocation/classe/<int:classe_id>/liste/', convocations_classe_liste, name='convocations_classe_liste'),
    path('convocation/classe/<int:classe_id>/imprimer/', imprimer_convocations_classe, name='imprimer_convocations_classe'),
    
    # Demandes de liaison parent-enfant
    path('demandes-liaison/', demandes_liaison_liste, name='demandes_liaison_liste'),
    path('demandes-liaison/<int:demande_id>/approuver/', approuver_demande_liaison, name='approuver_demande_liaison'),
    path('demandes-liaison/<int:demande_id>/rejeter/', rejeter_demande_liaison, name='rejeter_demande_liaison'),
    path('demandes-liaison/<int:demande_id>/desapprouver/', desapprouver_demande_liaison, name='desapprouver_demande_liaison'),
    
    # Gestion des examens
    path('gestion-examens/', gestion_examens, name='gestion_examens'),
    path('emploi-du-temps-examens/', emploi_du_temps_examens, name='emploi_du_temps_examens'),
    path('configurer-creneaux-examen/<int:session_id>/', configurer_creneaux_examen, name='configurer_creneaux_examen'),
    path('modifier-session-examen/<int:session_id>/', modifier_session_examen, name='modifier_session_examen'),
    path('supprimer-session-examen/<int:session_id>/', supprimer_session_examen, name='supprimer_session_examen'),
    
    # Gestion des annonces
    path('directeur/annonces/', annonces_directeur, name='annonces_directeur'),
    path('directeur/annonces/creer/', creer_annonce, name='creer_annonce'),
    path('directeur/annonces/<int:annonce_id>/modifier/', modifier_annonce, name='modifier_annonce'),
    path('directeur/annonces/<int:annonce_id>/apercu/', apercu_annonce, name='apercu_annonce'),
    path('directeur/annonces/<int:annonce_id>/imprimer/', imprimer_annonce, name='imprimer_annonce'),
    path('directeur/annonces/<int:annonce_id>/publier/', publier_annonce, name='publier_annonce'),
    path('directeur/annonces/<int:annonce_id>/archiver/', archiver_annonce, name='archiver_annonce'),
    path('directeur/annonces/<int:annonce_id>/supprimer/', supprimer_annonce, name='supprimer_annonce'),
    
    # Gestion comptabilité des élèves
    path('comptabilite/eleves/', liste_comptabilite_eleves_directeur, name='liste_comptabilite_eleves_directeur'),
    path('comptabilite/eleve/<int:eleve_id>/details/', details_comptabilite_eleve_directeur, name='details_comptabilite_eleve_directeur'),
    path('comptabilite/eleve/<int:eleve_id>/paiement/', enregistrer_paiement_directeur, name='enregistrer_paiement_directeur'),
    path('comptabilite/eleve/<int:eleve_id>/frais-inscription/<int:frais_id>/payer/', payer_frais_inscription_directeur, name='payer_frais_inscription_directeur'),
    path('comptabilite/eleve/<int:eleve_id>/mensualite/<int:mensualite_id>/payer/', payer_mensualite_directeur, name='payer_mensualite_directeur'),
    path('comptabilite/verifier-statuts/', verifier_statuts_paiement_directeur, name='verifier_statuts_paiement_directeur'),
    path('comptabilite/parametres/', parametres_comptabilite_directeur, name='parametres_comptabilite_directeur'),
    path('comptabilite/parametres-groupes/', liste_parametres_groupes_directeur, name='liste_parametres_groupes_directeur'),
    path('comptabilite/parametres-groupes/ajouter/', ajouter_modifier_parametres_groupe_directeur, name='ajouter_parametres_groupe_directeur'),
    path('comptabilite/parametres-groupes/<int:parametre_id>/modifier/', ajouter_modifier_parametres_groupe_directeur, name='modifier_parametres_groupe_directeur'),
    path('comptabilite/parametres-groupes/<int:parametre_id>/supprimer/', supprimer_parametres_groupe_directeur, name='supprimer_parametres_groupe_directeur'),
    path('comptabilite/bilan/', bilan_comptable_directeur, name='bilan_comptable_directeur'),
    path('comptabilite/classe/<int:classe_id>/bilan/', bilan_comptable_classe_directeur, name='bilan_comptable_classe_directeur'),
]
