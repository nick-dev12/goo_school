from decimal import Decimal
from django.urls import reverse
from school_admin import tests_examens as fixtures
from school_admin.model.note_examen_model import NoteExamen
from school_admin.model.sync_action_model import SyncAction

class AnnulationSessionTests(fixtures.BaseExamens):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.etab)
        self.url=reverse('directeur:annuler_session_examen',args=[self.compo.pk])

    def test_confirmation_obligatoire(self):
        self.client.post(self.url,{'motif':'Erreur de planning'})
        self.compo.refresh_from_db()
        self.assertFalse(self.compo.est_annule)
        self.assertFalse(SyncAction.objects.filter(resource='session_examen').exists())

    def test_annulation_conserve_notes_et_trace(self):
        n=self.note(self.awa,self.compo,Decimal('14'))
        self.client.post(self.url,{'motif':'Épreuve remplacée','confirmation':'oui'})
        self.compo.refresh_from_db()
        self.assertTrue(self.compo.est_annule)
        self.assertFalse(self.compo.est_publie)
        self.assertTrue(NoteExamen.objects.filter(pk=n.pk,note=Decimal('14')).exists())
        self.assertEqual(SyncAction.objects.filter(resource='session_examen',action='CANCEL').count(),1)
        self.client.post(self.url,{'motif':'Épreuve remplacée','confirmation':'oui'})
        self.assertEqual(SyncAction.objects.filter(resource='session_examen',action='CANCEL').count(),1)
        self.assertIsNone(self.res(self.awa)['valeur'])

    def test_get_sans_effet(self):
        self.assertEqual(self.client.get(self.url).status_code,405)
        self.compo.refresh_from_db(); self.assertFalse(self.compo.est_annule)
