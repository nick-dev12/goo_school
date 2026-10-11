"""Pages hub de la direction, annonces, examens et profil de l'établissement."""
from django.test import TestCase
from django.urls import reverse

from school_admin.model.annonce_model import Annonce
from school_admin.model.classe_model import Classe
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.services import hubs_directeur as hubs
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement_type

PAGES = ('directeur:gestion_etablissement', 'directeur:gestion_pedagogique', 'directeur:gestion_eleves',
         'directeur:gestion_administrative', 'directeur:annonces_directeur', 'directeur:gestion_examens',
         'directeur:profil_etablissement')


class HubsDirecteurTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement_type('lycée', 'hub')
        self.annee = _make_annee(self.etab)
        Classe.objects.create(nom='2nde A', niveau='lycee', code_classe=f'2A-{self.etab.pk}', capacite_max=30,
                              etablissement=self.etab, actif=True)

    def test_toutes_les_pages_s_affichent(self):
        self.client.force_login(self.etab)
        for nom in PAGES:
            r = self.client.get(reverse(nom))
            self.assertEqual(r.status_code, 200, nom)

    def test_hubs_signalent_ce_qui_manque(self):
        h = hubs.hub_etablissement(self.etab, self.etab, self.annee)
        self.assertTrue(any('période' in a['texte'].lower() for a in h['alertes']))
        p = hubs.hub_pedagogique(self.etab, self.etab, self.annee)
        self.assertTrue(any('sans enseignant' in a['texte'] for a in p['alertes']))
        titres = [l['titre'] for s in p['sections'] for l in s['liens']]
        self.assertIn('Cahiers de texte', titres)

    def test_hub_selon_autorisations(self):
        perso = PersonnelAdministratif(username=f'sec.hub.{self.etab.pk}', email=f'sec.hub.{self.etab.pk}@aria-test.local',
                                       nom='Ba', prenom='Ndeye', telephone='770000090', fonction='secretaire',
                                       etablissement=self.etab, actif=True, permissions={'eleves_liste': True})
        perso.set_password('Sec@Test1!')
        perso.save()
        h = hubs.hub_eleves(perso, self.etab, self.annee)
        titres = [l['titre'] for s in h['sections'] for l in s['liens']]
        self.assertIn('Liste des élèves', titres)
        self.assertNotIn('Préinscriptions reçues', titres)

    def test_annonces_actions(self):
        a = Annonce.objects.create(titre='Réunion parents', contenu='Samedi 10h', etablissement=self.etab,
                                   annee_scolaire=self.annee, statut='brouillon', destinataires=['parents'])
        self.client.force_login(self.etab)
        r = self.client.get(reverse('directeur:annonces_directeur'))
        self.assertContains(r, 'Réunion parents')
        self.assertContains(r, reverse('directeur:publier_annonce', args=[a.id]))

    def test_profil_personnel_ne_modifie_pas_l_etablissement(self):
        nom_etab, email_etab = self.etab.nom, self.etab.email
        perso = PersonnelAdministratif(username=f'cpt.hub.{self.etab.pk}', email=f'cpt.hub.{self.etab.pk}@aria-test.local',
                                       nom='Fall', prenom='Ibou', telephone='770000091', fonction='comptable',
                                       etablissement=self.etab, actif=True, permissions={})
        perso.set_password('Cpt@Test1!')
        perso.save()
        self.client.force_login(perso)
        self.client.post(reverse('directeur:profil_etablissement'), {
            'form_type': 'update_information', 'active_tab': 'informations',
            'prenom': 'Ibrahima', 'nom': 'Fall', 'email': f'ibrahima.{self.etab.pk}@aria-test.local', 'telephone': '770000092'})
        self.etab.refresh_from_db()
        perso.refresh_from_db()
        self.assertEqual((self.etab.nom, self.etab.email), (nom_etab, email_etab))
        self.assertEqual(perso.prenom, 'Ibrahima')
        self.assertEqual(perso.telephone, '770000092')
