"""Guide examens : contexte isolé, lecture seule et états fondés sur les données."""
from datetime import date, time
from unittest.mock import patch

from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.contrib.auth.models import AnonymousUser

from school_admin.tests_deliberations import BaseDelib
from school_admin.controllers import parcours_examens_controller as guide
from school_admin.model.session_examen_model import SessionExamen
from school_admin.model.creneau_examen_model import CreneauExamen
from school_admin.model.deliberation_model import Deliberation, DecisionJury
from school_admin.model.professeur_model import Professeur
from school_admin.model.note_examen_model import NoteExamen


class ParcoursExamensTests(BaseDelib):
    def requete(self, **params):
        request = RequestFactory().get('/parcours-examens/', params)
        request.user = self.etab
        request.session = {}
        return request

    def contexte(self, **params):
        with patch.object(guide, 'render', side_effect=lambda request, template, context: context):
            return guide.parcours_examens(self.requete(annee_id=self.annee.id, classe_id=self.classe.id, **params))

    def etapes(self):
        return guide.construire_etapes(self.classe, [self.s1], self.annee, 'semestre', 'normale')

    def session(self, **kwargs):
        s = SessionExamen.objects.create(etablissement=self.etab, periode=self.s1,
            annee_scolaire=self.annee, type_session='examen', nom_examen='Examen S1',
            date_debut=date(2026, 11, 1), date_fin=date(2026, 11, 2), **kwargs)
        s.classes.add(self.classe)
        s.matieres.set([self.ecs[(self.s1.id, i)] for i in range(3)])
        return s

    def test_get_reel_sans_ecriture_ni_preparation(self):
        with CaptureQueriesContext(connection) as queries, patch.object(guide.deliberations, 'preparer', side_effect=AssertionError('préparation interdite')):
            response = guide.parcours_examens(self.requete(annee_id=self.annee.id, classe_id=self.classe.id, periode_id=self.s1.id))
        self.assertEqual(response.status_code, 200)
        writes = [q['sql'] for q in queries if q['sql'].lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE', 'REPLACE'}]
        self.assertEqual(writes, [])
        self.assertFalse(Deliberation.objects.exists())
        self.assertFalse(DecisionJury.objects.exists())
        self.assertIn('Examens et jury'.encode(), response.content)

    def test_selection_vide_pas_de_controle(self):
        with patch.object(guide, 'controle_resultats') as controle:
            response = guide.parcours_examens(self.requete())
        self.assertEqual(response.status_code, 200)
        controle.assert_not_called()

    def test_contexte_etranger_refuse(self):
        from django.http import Http404
        from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement_type
        autre = _make_etablissement_type('superieur', 'autre-guide')
        autre_annee = _make_annee(autre)
        with self.assertRaises(Http404):
            self.contexte(periode_id=999999)
        with self.assertRaises(Http404):
            guide.parcours_examens(self.requete(annee_id=autre_annee.id))
        with self.assertRaises(Http404):
            guide.parcours_examens(self.requete(annee_id=self.annee.id, classe_id=999999))

    def test_periode_autre_niveau_refusee(self):
        from django.http import Http404
        self.s1.niveau_lmd = 'L3'
        self.s1.nom_periode = 'Semestre 5'
        self.s1.save()
        with self.assertRaises(Http404):
            self.contexte(periode_id=self.s1.id)

    def test_post_refuse_et_anonyme_redirige(self):
        request = RequestFactory().post('/parcours-examens/')
        request.user = self.etab
        self.assertEqual(guide.parcours_examens(request).status_code, 405)
        request = self.requete()
        request.user = AnonymousUser()
        self.assertEqual(guide.parcours_examens(request).status_code, 302)

    def test_identifiants_et_portee_invalides(self):
        self.assertEqual(guide.parcours_examens(self.requete(classe_id='abc')).status_code, 400)
        self.assertEqual(guide.parcours_examens(self.requete(portee='autre')).status_code, 400)

    def test_programme_present_resultats_absents(self):
        context = self.etapes()
        self.assertTrue(context['etapes'][0]['pret'])
        self.assertFalse(context['etapes'][3]['pret'])
        self.assertTrue(context['problemes'])
        self.assertFalse(context['documents_prets'])

    def test_calendrier_vide_meme_publie_non_pret(self):
        self.session(est_publie=True)
        self.assertFalse(self.etapes()['etapes'][1]['pret'])

    def test_notes_zero_absence_et_soumission(self):
        s = self.session(est_publie=True)
        prof = Professeur.objects.create_user(username='guide-prof', email='guide@test.local',
            password='test', nom='Sarr', prenom='Ali', telephone='770000090', numero_employe='GUIDE',
            matiere_principale=self.ecs[(self.s1.id, 0)], etablissement=self.etab,
            niveau_enseignement='superieur', actif=True)
        for i in range(3):
            m = self.ecs[(self.s1.id, i)]
            CreneauExamen.objects.create(session_examen=s, matiere=m, date_examen=date(2026, 11, 1),
                heure_debut=time(8+i*2), heure_fin=time(9+i*2))
            NoteExamen.objects.create(session_examen=s, eleve=self.awa, classe=self.classe,
                annee_scolaire=self.annee, professeur=prof, matiere=m,
                note=0 if i == 0 else None, absent=i == 1, soumis=True)
        context = self.etapes()
        self.assertTrue(context['etapes'][1]['pret'])
        self.assertFalse(context['etapes'][2]['pret'])
        self.assertEqual(len(context['saisies_manquantes']), 1)
        n = NoteExamen.objects.get(session_examen=s, matiere=self.ecs[(self.s1.id, 2)])
        n.note = 12
        n.save()
        self.assertTrue(self.etapes()['etapes'][2]['pret'])
        n.soumis = False
        n.save()
        self.assertEqual(self.etapes()['saisies_manquantes'][0]['motif'], 'À soumettre')

    def test_fraicheur_et_erreur_service(self):
        with patch.object(guide, 'controle_resultats', return_value={
                'pret': False, 'problemes': ['Moyennes périmées'], 'etudiants': 1, 'manquants': 0, 'perimes': 1}):
            self.assertEqual(self.etapes()['etapes'][3]['etat'], 'À recalculer')
        with patch.object(guide, 'controle_resultats', side_effect=guide.deliberations.DeliberationErreur('Moyennes requises')):
            self.assertFalse(self.etapes()['etapes'][3]['pret'])

    def test_annuel_explicitement_et_contrat_service(self):
        with patch.object(guide, 'controle_resultats', return_value={'pret': False, 'problemes': [], 'etudiants': 1, 'manquants': 1, 'perimes': 0}) as controle:
            context = self.contexte(portee='annuelle')
        self.assertEqual(len(context['etapes']), 6)
        self.assertEqual(controle.call_args.args, (self.classe, [self.s1, self.s2], self.annee))

    def test_cloture_sans_controle_ne_donne_pas_pv_definitif(self):
        Deliberation.objects.create(etablissement=self.etab, classe=self.classe, annee_scolaire=self.annee,
            periode=self.s1, session='normale', statut='cloturee', president='Président', membres='Membre',
            date_deliberation=date(2026, 11, 1))
        self.assertFalse(self.etapes()['etapes'][5]['pret'])

    def test_jury_complet_et_pv_definitif(self):
        d = Deliberation.objects.create(etablissement=self.etab, classe=self.classe, annee_scolaire=self.annee,
            periode=self.s1, session='normale', statut='cloturee', president='Président', membres='Membre',
            date_deliberation=date(2026, 11, 1))
        dj = DecisionJury.objects.create(deliberation=d, eleve=self.awa, decision='admis',
            credits_total=30, credits_acquis=30)
        with patch.object(guide, 'controle_resultats', return_value={
                'pret': True, 'problemes': [], 'etudiants': 1, 'manquants': 0, 'perimes': 0}):
            context = self.etapes()
            self.assertTrue(context['etapes'][5]['pret'])
            self.assertIn('/pv/', context['etapes'][5]['url'])
            self.assertFalse(context['documents_prets'])  # L1 et bilan semestriel
            with patch.object(guide, 'controle_resultats', return_value={
                    'pret': False, 'problemes': ['Moyennes périmées'], 'etudiants': 1, 'manquants': 0, 'perimes': 1}):
                etape = self.etapes()['etapes'][5]
                self.assertEqual(etape['etat'], 'À recalculer')
                self.assertFalse(etape['pret'])
                self.assertNotIn('/pv/', etape['url'])
                self.assertIn(f'/deliberations/{d.id}/', etape['url'])
            dj.points_jury = 1
            dj.motif_jury = ''
            dj.save()
            self.assertFalse(self.etapes()['etapes'][5]['pret'])

    def test_moyennes_sans_empreinte_signalees(self):
        from school_admin.model.moyenne_periode_model import MoyennePeriode
        self.notes(self.awa, self.s1, [0, 12, 14])
        MoyennePeriode.objects.filter(eleve=self.awa, periode=self.s1).update(empreinte_sources='')
        context = self.etapes()
        self.assertEqual(context['etapes'][3]['etat'], 'À recalculer')
        self.assertTrue(context['controle']['perimes'])

    def _cloturee_avec_moyennes(self):
        from school_admin.model.moyenne_periode_model import MoyennePeriode
        self.notes(self.awa, self.s1, [12, 13, 14])
        d = Deliberation.objects.create(etablissement=self.etab, classe=self.classe, annee_scolaire=self.annee,
            periode=self.s1, session='normale', statut='cloturee', president='Président', membres='Membre',
            date_deliberation=date(2026, 11, 1))
        DecisionJury.objects.create(deliberation=d, eleve=self.awa, decision='admis',
            credits_total=30, credits_acquis=30)
        return d, MoyennePeriode.objects.filter(eleve=self.awa, periode=self.s1, est_moyenne_generale=False)

    def test_cloturee_avant_migration_pas_de_recalcul_impossible(self):
        """Moyennes sans empreinte (antérieures à 0256) d'une délibération clôturée : PV définitif."""
        d, moyennes = self._cloturee_avec_moyennes()
        moyennes.update(empreinte_sources='')
        context = self.etapes()
        self.assertTrue(context['etapes'][3]['pret'])
        self.assertTrue(context['etapes'][5]['pret'])
        self.assertIn(f'/deliberations/{d.id}/pv/', context['etapes'][5]['url'])
        self.assertIn('avant la mise à jour', context['problemes'][0])

    def test_cloturee_donnees_modifiees_apres_cloture_signalees(self):
        from decimal import Decimal
        d, moyennes = self._cloturee_avec_moyennes()
        moyennes.filter(matiere=self.ecs[(self.s1.id, 0)]).update(moyenne_matiere=Decimal('20'))
        context = self.etapes()
        self.assertEqual(context['etapes'][5]['etat'], 'À recalculer')
        self.assertFalse(context['etapes'][5]['pret'])
        self.assertIn('rouvrez la délibération', context['problemes'][-1])

    def test_acces_hors_superieur_refuse(self):
        self.etab.type_etablissement = 'college'
        self.assertEqual(guide.parcours_examens(self.requete()).status_code, 403)

    def test_compositions_et_blancs_comptant_au_bulletin_inclus(self):
        s = self.session()
        for type_session in ('composition', 'examen_blanc'):
            SessionExamen.objects.filter(pk=s.id).update(type_session=type_session, compte_bulletin=True)
            self.assertIn('0/3', self.etapes()['etapes'][2]['explication'])
        SessionExamen.objects.filter(pk=s.id).update(compte_bulletin=False)
        self.assertIn('0/0', self.etapes()['etapes'][2]['explication'])
        SessionExamen.objects.filter(pk=s.id).update(type_session='rattrapage', compte_bulletin=True)
        self.assertIn('0/0', self.etapes()['etapes'][2]['explication'])
        context = guide.construire_etapes(self.classe, [self.s1], self.annee, 'semestre', 'rattrapage')
        self.assertIn('0/3', context['etapes'][2]['explication'])

    def test_annuel_incomplet_bloque_meme_si_service_pret(self):
        # Le service ne peut contrôler qu’une période configurée : le guide contrôle aussi la portée.
        self.s2.delete()
        with patch.object(guide, 'controle_resultats', return_value={
                'pret': True, 'problemes': [], 'etudiants': 1, 'manquants': 0, 'perimes': 0}):
            context = self.contexte(portee='annuelle')
        self.assertFalse(context['controle']['pret'])
        self.assertIn('Semestre 2', ' '.join(context['problemes']))
        self.assertTrue(all(not e['pret'] for e in context['etapes']))
