"""F02/F04/F05 : tests uniquement dans la base configurée par le runner."""
from datetime import date, time
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from school_admin.tests_examens import BaseExamens
from school_admin.model.session_examen_model import SessionExamen
from school_admin.model.note_examen_model import NoteExamen
from school_admin.model.creneau_examen_model import CreneauExamen
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.module_model import Module, ModuleClasse
from school_admin.model.classe_model import Classe
from school_admin.tests.test_assistant_directeur_tools import _make_etablissement_type


class SecuriteSessionsTests(BaseExamens):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.etab)

    def url(self, action):
        return reverse('directeur:' + action + '_session_examen', args=[self.compo.pk])

    def test_get_suppression_et_publication_interdits(self):
        for action in ('supprimer', 'publier'):
            self.assertEqual(self.client.get(self.url(action)).status_code, 405)
        self.assertTrue(SessionExamen.objects.filter(pk=self.compo.pk).exists())
        self.compo.refresh_from_db()
        self.assertFalse(self.compo.est_publie)

    def test_suppression_lignes_vides_auto(self):
        self.assertTrue(self.compo.notes.exists())
        self.assertEqual(self.client.post(self.url('supprimer')).status_code, 302)
        self.assertFalse(SessionExamen.objects.filter(pk=self.compo.pk).exists())

    def test_conservation_notes_absences_soumissions_publications(self):
        n = self.note(self.awa, self.compo, soumis=False)
        cas = [dict(note=Decimal('0')), dict(note=Decimal('14')), dict(absent=True),
               dict(absence_justifiee=True), dict(soumis=True),
               dict(statut_publication='publiee'), dict(statut_publication='modifiee'),
               dict(note_publiee=Decimal('0')), dict(date_publication=timezone.now()),
               dict(date_soumission=timezone.now()), dict(commentaire='Travail saisi')]
        for valeurs in cas:
            with self.subTest(valeurs=valeurs):
                NoteExamen.objects.filter(pk=n.pk).update(note=None, note_sur_20=None, absent=False,
                    absence_justifiee=False, soumis=False, statut_publication='brouillon',
                    note_publiee=None, date_publication=None, date_soumission=None, commentaire='', actif=False)
                NoteExamen.objects.filter(pk=n.pk).update(**valeurs)
                self.client.post(self.url('supprimer'))
                self.assertTrue(SessionExamen.objects.filter(pk=self.compo.pk).exists())
                n.refresh_from_db()
                for cle, valeur in valeurs.items():
                    self.assertEqual(getattr(n, cle), valeur)

    def test_csrf_obligatoire(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.etab)
        for action in ('supprimer', 'publier'):
            self.assertEqual(client.post(self.url(action)).status_code, 403)
        self.assertTrue(SessionExamen.objects.filter(pk=self.compo.pk).exists())

    def test_autre_etablissement_refuse(self):
        from django.test import RequestFactory
        from django.http import Http404
        from school_admin.controllers import examen_controller as vues
        autre = _make_etablissement_type('collège', 'autre-exa')
        self.client.force_login(autre)
        for vue in (vues.supprimer_session_examen, vues.publier_session_examen):
            request = RequestFactory().post('/')
            request.user = autre
            with self.assertRaises(Http404):
                vue(request, self.compo.pk)
        for action in ('supprimer', 'publier'):
            self.assertIn(self.client.post(self.url(action)).status_code, (302, 404))
        self.assertTrue(SessionExamen.objects.filter(pk=self.compo.pk).exists())

    def test_consultation_ne_permet_pas_suppression(self):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif
        personnel = PersonnelAdministratif(username='lecteur.examens', email='lecteur@example.test',
            nom='Fall', prenom='Ali', telephone='770000099', fonction='secretaire',
            etablissement=self.etab, actif=True, permissions={'examens_voir': True})
        personnel.set_password('Test-Examens-123')
        personnel.save()
        self.client.force_login(personnel)
        self.assertEqual(self.client.post(self.url('supprimer')).status_code, 403)
        self.assertTrue(SessionExamen.objects.filter(pk=self.compo.pk).exists())

    def test_calendrier_publie_non_modifiable_sans_retrait(self):
        SessionExamen.objects.filter(pk=self.compo.pk).update(est_publie=True)
        self.client.post(reverse('directeur:modifier_session_examen', args=[self.compo.pk]), {
            'nom_examen': 'Modification interdite', 'periode_id': self.periode.pk,
            'date_debut': '2026-12-01', 'date_fin': '2026-12-05',
            'groupes_classes': ['3e'], 'matieres': [self.math.pk]})
        self.compo.refresh_from_db()
        self.assertNotEqual(self.compo.nom_examen, 'Modification interdite')
        self.assertTrue(self.compo.est_publie)

    def creneau(self, matiere, heure=8):
        return CreneauExamen.objects.create(session_examen=self.compo, matiere=matiere,
            date_examen=date(2026, 12, 1), heure_debut=time(heure), heure_fin=time(heure+1),
            annee_scolaire=self.annee)

    def test_calendrier_vide_partiel_annule_bloque(self):
        self.client.post(self.url('publier'))
        self.compo.refresh_from_db()
        self.assertFalse(self.compo.est_publie)
        c = self.creneau(self.math)
        self.client.post(self.url('publier'))
        self.compo.refresh_from_db()
        self.assertFalse(self.compo.est_publie)
        self.creneau(self.fr, 10)
        CreneauExamen.objects.filter(pk=c.pk).update(est_annule=True)
        self.client.post(self.url('publier'))
        self.compo.refresh_from_db()
        self.assertFalse(self.compo.est_publie)

    def test_calendrier_complet_publication_retrait(self):
        self.creneau(self.math)
        self.creneau(self.fr, 10)
        self.client.post(self.url('publier'))
        self.compo.refresh_from_db()
        self.assertTrue(self.compo.est_publie)
        self.client.post(self.url('publier'))
        self.compo.refresh_from_db()
        self.assertFalse(self.compo.est_publie)
        self.assertEqual(self.compo.creneaux.count(), 2)

    def test_conflits_revalides_publication(self):
        self.creneau(self.math)
        c = self.creneau(self.fr, 10)
        CreneauExamen.objects.filter(pk=c.pk).update(heure_debut=time(8), heure_fin=time(9))
        self.client.post(self.url('publier'))
        self.compo.refresh_from_db()
        self.assertFalse(self.compo.est_publie)

    def test_page_formulaires_post(self):
        response = self.client.get(reverse('directeur:gestion_examens'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'onsubmit="return confirmSessionAction(this)"')
        self.assertContains(response, 'Publier le calendrier')
        self.assertNotContains(response, 'onclick="deleteSession(')


class CoherenceSessionsTests(BaseExamens):
    type_etab = 'superieur'

    def setUp(self):
        super().setUp()
        self.classe.niveau = 'superieur'
        self.classe.niveau_lmd = 'L1'
        self.classe.save()
        self.periode.type_periode = 'semestre'
        self.periode.nom_periode = 'Semestre 1'
        self.periode.niveau_lmd = 'L1'
        self.periode.save()
        self.s2 = PeriodeScolaire.objects.create(etablissement=self.etab, nom_periode='Semestre 2',
            type_periode='semestre', niveau_lmd='L1', date_debut=date(2027, 1, 1),
            date_fin=date(2027, 6, 1), annee_scolaire=self.annee.libelle, annee_scolaire_fk=self.annee)
        self.module = Module.objects.create(nom='UE S1', code='UES1', etablissement=self.etab)
        self.mc = ModuleClasse.objects.create(module=self.module, classe=self.classe, periode=self.periode)
        self.math.module = self.module
        self.math.niveau = 'superieur'
        self.math.save()
        self.math.classes.add(self.classe)
        self.client.force_login(self.etab)

    def post(self, **kw):
        donnees = dict(nom_examen='Session cohérente', periode_id=str(self.periode.pk),
            date_debut='2026-12-01', date_fin='2026-12-05', classes_concernees=[str(self.classe.pk)],
            matieres=[str(self.math.pk)])
        donnees.update(kw)
        return donnees

    def verifier_refus_creation_edition(self, **kw):
        initial = SessionExamen.objects.count()
        self.client.post(reverse('directeur:gestion_examens'), self.post(**kw))
        self.assertEqual(SessionExamen.objects.count(), initial)
        nom = self.compo.nom_examen
        self.client.post(reverse('directeur:modifier_session_examen', args=[self.compo.pk]), self.post(**kw))
        self.compo.refresh_from_db()
        self.assertEqual(self.compo.nom_examen, nom)

    def test_matiere_autre_semestre_refusee_creation_edition(self):
        self.verifier_refus_creation_edition(periode_id=str(self.s2.pk), type_session='rattrapage')

    def test_niveau_l3_refuse_creation_edition(self):
        PeriodeScolaire.objects.filter(pk=self.periode.pk).update(niveau_lmd='L3', nom_periode='Semestre 5')
        self.verifier_refus_creation_edition()

    def test_annee_incorrecte_refusee(self):
        PeriodeScolaire.objects.filter(pk=self.periode.pk).update(annee_scolaire_fk=None)
        self.verifier_refus_creation_edition()

    def test_matiere_sans_maquette_refusee(self):
        self.mc.delete()
        self.verifier_refus_creation_edition()

    def test_ids_invalides_refuses(self):
        for kw in [dict(periode_id='abc'), dict(matieres=['abc'])]:
            self.verifier_refus_creation_edition(**kw)

    def test_publication_formulaire_refusee(self):
        self.verifier_refus_creation_edition(est_publie='on', est_publie_present='1')

    def test_creation_edition_s1_et_rattrapage_hors_dates(self):
        response = self.client.post(reverse('directeur:gestion_examens'), self.post())
        self.assertEqual(response.status_code, 302)
        session = SessionExamen.objects.get(nom_examen='Session cohérente')
        self.assertEqual(session.periode_id, self.periode.pk)
        self.client.post(reverse('directeur:modifier_session_examen', args=[session.pk]),
            self.post(nom_examen='Rattrapage S1', type_session='rattrapage', date_debut='2027-07-01', date_fin='2027-07-02'))
        session.refresh_from_db()
        self.assertEqual(session.nom_examen, 'Rattrapage S1')
        self.assertEqual(session.date_debut, date(2027, 7, 1))

    def test_matiere_commune_toutes_associations_verifiees(self):
        b = Classe.objects.create(nom='L1 B', code_classe='L1B', niveau='superieur', niveau_lmd='L1',
            etablissement=self.etab, capacite_max=40)
        self.math.classes.add(b)
        mc = ModuleClasse.objects.create(module=self.module, classe=b, periode=self.s2)
        kw = dict(classes_concernees=[str(self.classe.pk), str(b.pk)])
        self.verifier_refus_creation_edition(**kw)
        mc.periode = self.periode
        mc.save()
        self.client.post(reverse('directeur:gestion_examens'), self.post(**kw))
        self.assertEqual(SessionExamen.objects.get(nom_examen='Session cohérente').classes.count(), 2)

    def test_meta_interface_semestre_programme(self):
        response = self.client.get(reverse('directeur:gestion_examens'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'exam-periodes-data')
        meta = response.context['matieres_session_superieur_meta']
        ligne = next(m for m in meta if m['id'] == self.math.pk)
        self.assertEqual(ligne['associations'], [{'classe_id': self.classe.pk, 'periode_id': self.periode.pk}])
