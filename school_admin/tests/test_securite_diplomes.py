"""Sécurité des attestations : toutes les écritures utilisent la base du runner."""
from unittest.mock import patch

from django.db.models.query import QuerySet
from django.urls import reverse

from school_admin import tests_admissions as fixtures
from school_admin.model.admission_model import Diplome
from school_admin.model.deliberation_model import DecisionJury, UECapitalisee
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.model.sync_action_model import SyncAction
from school_admin.services import diplomes as svc


class SecuriteDiplomesTests(fixtures.DiplomesTests):
    def setUp(self):
        super().setUp()
        self.e2 = fixtures._make_eleve_simple(self.etab, self.l3, 'Ndiaye', 'Awa', 'F', 'securite2')
        fixtures._make_inscription(self.e2, self.l3, self.annee, self.etab)
        for capitalisation in list(UECapitalisee.objects.filter(eleve=self.e)):
            capitalisation.pk = None
            capitalisation.eleve = self.e2
            capitalisation.save()
        decision = DecisionJury.objects.get(eleve=self.e)
        decision.pk = None
        decision.eleve = self.e2
        decision.save()
        self.client.force_login(self.etab)
        self.url = reverse('directeur:diplomes_classe', args=[self.l3.pk])

    def test_selection_absente_vide_invalide(self):
        for valeurs in (None, [], ['abc'], [''], ['²'], ['9' * 100]):
            data = {'action': 'delivrer'}
            if valeurs is not None:
                data['eleves'] = valeurs
            self.client.post(self.url, data)
            self.assertFalse(Diplome.objects.exists())

    def test_selection_explicite_et_double_envoi(self):
        data = {'action': 'delivrer', 'eleves': [self.e2.pk]}
        self.client.post(self.url, data)
        self.client.post(self.url, data)
        self.assertEqual(list(Diplome.objects.values_list('eleve_id', flat=True)), [self.e2.pk])

    def test_selection_etrangere_mixte_ou_ineligible_refusee(self):
        autre = fixtures._make_eleve_simple(self.etab, self.l1, 'Autre', 'Classe', 'M', 'horsclasse')
        for valeurs in ([self.e.pk, autre.pk], [self.e.pk, 'abc']):
            self.assertEqual(self.client.post(self.url, {'action': 'delivrer', 'eleves': valeurs}).status_code, 400)
            self.assertFalse(Diplome.objects.exists())
        UECapitalisee.objects.filter(eleve=self.e2).delete()
        self.assertEqual(self.client.post(self.url, {'action': 'delivrer', 'eleves': [self.e.pk, self.e2.pk]}).status_code, 400)
        self.assertFalse(Diplome.objects.exists())
        with self.assertRaises(ValueError):
            svc.delivrer(self.l3, [autre], self.annee)

    def test_interface_selection_volontaire_et_noms_echappes(self):
        self.e.nom = '<script>alert(1)</script>'
        self.e.save(update_fields=['nom'])
        r = self.client.get(self.url)
        self.assertContains(r, 'id="delivrer" disabled')
        self.assertNotContains(r, ' checked')
        self.assertContains(r, '&lt;SCRIPT&gt;ALERT(1)&lt;/SCRIPT&gt;')
        self.assertContains(r, 'choix.length')
        self.assertFalse(Diplome.objects.exists())

    def test_annulation_confirmation_motif_trace_et_redelivrance(self):
        d = svc.delivrer(self.l3, [self.e], self.annee)[0]
        data = {'action': 'annuler', 'id': d.pk, 'motif': 'Erreur identité'}
        self.assertEqual(self.client.post(self.url, data).status_code, 400)
        data['confirmation'] = 'oui'
        data['motif'] = '   '
        self.assertEqual(self.client.post(self.url, data).status_code, 400)
        d.refresh_from_db()
        self.assertFalse(d.annule)
        data['motif'] = 'Erreur identité'
        self.client.post(self.url, data)
        self.client.post(self.url, data)
        d.refresh_from_db()
        self.assertTrue(d.annule)
        trace = SyncAction.objects.get(resource='diplome')
        self.assertEqual(trace.resultat['motif'], 'Erreur identité')
        self.assertEqual(trace.utilisateur_id, self.etab.pk)
        self.assertEqual(trace.resultat['numero'], d.numero)
        self.assertIn('date', trace.resultat)
        self.assertContains(self.client.get(self.url), 'Erreur identité')
        self.assertEqual(self.client.get(reverse('directeur:imprimer_diplome', args=[d.pk])).status_code, 403)
        nouveau = svc.delivrer(self.l3, [self.e], self.annee)[0]
        self.assertNotEqual(nouveau.numero, d.numero)
        self.assertEqual(Diplome.objects.count(), 2)

    def test_annulation_autre_classe_et_autre_etablissement(self):
        d = svc.delivrer(self.l3, [self.e], self.annee)[0]
        data = {'action': 'annuler', 'id': d.pk, 'motif': 'Erreur', 'confirmation': 'oui'}
        url = reverse('directeur:diplomes_classe', args=[self.l1.pk])
        self.assertEqual(self.client.post(url, data).status_code, 404)
        autre = fixtures._make_etablissement_type('superieur', 'etranger')
        fixtures._make_annee(autre)
        self.client.logout()
        self.client.force_login(autre)
        session = self.client.session
        session['_auth_user_type'] = 'etablissement'
        session.save()
        r = self.client.post(self.url, data)
        self.assertEqual(r.status_code, 404, getattr(r, 'url', ''))
        self.assertEqual(self.client.get(reverse('directeur:imprimer_diplome', args=[d.pk])).status_code, 404)
        d.refresh_from_db()
        self.assertFalse(d.annule)

    def test_lecture_seule_interdit_mutations(self):
        personnel = PersonnelAdministratif.objects.create(
            username='lecture.diplomes', email='lecture@example.test', nom='Lecture', prenom='Seule',
            telephone='770000099', fonction='secretaire', etablissement=self.etab, actif=True,
            permissions={'eleves_liste': True})
        personnel.set_password('Test123!')
        personnel.save()
        self.client.logout()
        self.client.force_login(personnel)
        session = self.client.session
        session['_auth_user_type'] = 'personnel'
        session.save()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200, getattr(r, 'url', ''))
        for action in ('delivrer', 'annuler'):
            self.assertEqual(self.client.post(self.url, {'action': action, 'eleves': [self.e.pk]}).status_code, 403)
        self.assertFalse(Diplome.objects.exists())

    def test_verrous_avant_revalidation(self):
        # SQLite ne réalise pas SELECT FOR UPDATE : vérifier le protocole, sans
        # prétendre simuler la concurrence d'une base de production.
        verrouilles = []
        original = QuerySet.select_for_update
        def verrou(qs, *args, **kwargs):
            verrouilles.append(qs.model.__name__)
            return original(qs, *args, **kwargs)
        with patch.object(QuerySet, 'select_for_update', verrou):
            svc.delivrer(self.l3, [self.e], self.annee)
        self.assertEqual(verrouilles[:2], ['Etablissement', 'Classe'])

    def test_trace_et_annulation_atomiques(self):
        d = svc.delivrer(self.l3, [self.e], self.annee)[0]
        with patch.object(SyncAction.objects, 'create', side_effect=RuntimeError('trace indisponible')):
            with self.assertRaises(RuntimeError):
                svc.annuler(d, self.etab, 'Erreur')
        d.refresh_from_db()
        self.assertFalse(d.annule)

    def test_get_ne_modifie_pas_et_service_annulation_refuse_autre_auteur(self):
        d = svc.delivrer(self.l3, [self.e], self.annee)[0]
        self.client.get(self.url, {'action': 'annuler', 'id': d.pk,
                                   'confirmation': 'oui', 'motif': 'Erreur'})
        d.refresh_from_db()
        self.assertFalse(d.annule)
        with self.assertRaises(PermissionError):
            svc.annuler(d, self.e, 'Erreur')
        self.assertFalse(SyncAction.objects.filter(resource='diplome').exists())
