"""Cahier de texte : saisie, cours à renseigner, rédaction par Aria (simulée), outils de l'assistant, pages."""
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.cahier_texte_model import CahierTexte
from school_admin.model.classe_model import Classe
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
from school_admin.model.matiere_model import Matiere
from school_admin.model.pointage_model import BornePointage, SeanceCours
from school_admin.model.professeur_model import Professeur
from school_admin.services import cahier_texte as ct
from school_admin.services import pointage as pt
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement

PROPOSITION = {'titre': 'Les fractions : addition', 'objectifs': '- Additionner deux fractions',
               'contenu': '- Rappel\n- Exemples au tableau\n- Exercices', 'travail_a_faire': 'Ex 5 et 6 p.48',
               'date_travail': ''}


class CahierTexteTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.classe = Classe.objects.create(nom='6e A', niveau='college', code_classe=f'6A-{s}', capacite_max=30,
                                            etablissement=self.etab, actif=True)
        self.matiere = Matiere.objects.create(nom=f'Mathématiques {s}', code=f'MA{s}'[:10], etablissement=self.etab,
                                              actif=True)
        self.prof = Professeur.objects.create_user(
            username=f'prof.ct.{s}', email=f'prof.ct.{s}@test.local', password='Prof@Test1!', nom='Sarr',
            prenom='Ali', telephone='770000030', numero_employe=f'CT{s}', matiere_principale=self.matiere,
            etablissement=self.etab, niveau_enseignement='college', actif=True)
        AffectationProfesseur.objects.create(professeur=self.prof, classe=self.classe, matiere=self.matiere,
                                             annee_scolaire=self.annee, statut='classique', actif=True)
        edt = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                           annee_scolaire_fk=self.annee, est_actif=True, statut_publication='publie')
        self.today = timezone.localdate()
        jour = ct.JOURS[self.today.weekday()]
        self.creneau = CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour=jour, heure_debut=time(0, 0),
                                                           heure_fin=time(0, 30), matiere=self.matiere,
                                                           professeur=self.prof, type_cours='cours')

    def test_enregistrer_et_cours_renseigne(self):
        cours = ct.cours_du_professeur(self.prof, self.today, self.today, self.annee)
        self.assertEqual(len(cours), 1)
        self.assertIsNone(cours[0]['entree'])
        e = ct.enregistrer(self.prof, self.classe, self.today, PROPOSITION, matiere=self.matiere, debut=time(0, 0),
                           fin=time(0, 30), annee_scolaire=self.annee)
        self.assertEqual(e.statut, 'brouillon')
        self.assertTrue(e.modifiable)
        cours = ct.cours_du_professeur(self.prof, self.today, self.today, self.annee)
        self.assertEqual(cours[0]['entree'], e)
        with self.assertRaises(ValueError):
            ct.enregistrer(self.prof, self.classe, self.today, {'titre': 'x', 'contenu': ''})
        with self.assertRaises(ValueError):
            ct.enregistrer(self.prof, self.classe, self.today,
                           dict(PROPOSITION, date_travail=(self.today - timedelta(days=2)).isoformat()))

    def test_interpretation_reponse_ia(self):
        r = ct.interpreter({'titre': '**Fractions**', 'contenu': '# Étape 1', 'date_travail': '2000-01-01'}, self.today)
        self.assertEqual(r['titre'], 'Fractions')
        self.assertEqual(r['date_travail'], '')
        with self.assertRaises(ValueError):
            ct.interpreter({'titre': ''}, self.today)

    def test_prompt_contient_contexte_et_progression(self):
        ct.enregistrer(self.prof, self.classe, self.today - timedelta(days=2), dict(PROPOSITION, titre='Leçon 1'),
                       matiere=self.matiere)
        consigne, contexte = ct.construire_prompt(self.prof, self.classe, self.matiere, self.today, 'ex 5 p48')
        self.assertIn('6e A', contexte)
        self.assertIn('Leçon 1', contexte)
        self.assertIn('ex 5 p48', contexte)
        self.assertIn('JSON', consigne)

    def test_seance_terminee_alimente_le_cahier(self):
        borne = BornePointage.objects.create(etablissement=self.etab, libelle='B')
        pt.generer_seances(self.etab, self.today, self.today, self.annee)
        s = SeanceCours.objects.get(creneau=self.creneau)
        debut = timezone.make_aware(datetime.combine(self.today, time(0, 1)))
        pt.commencer(s, self.prof, saisie_qr=pt.contenu_qr(borne), maintenant=debut)
        pt.terminer(s, 'Chapitre 2 — Les angles', maintenant=debut + timedelta(minutes=25))
        e = CahierTexte.objects.get(seance=s)
        self.assertEqual(e.titre, 'Chapitre 2')
        self.assertEqual(e.contenu, 'Les angles')

    @patch('school_admin.services.cahier_texte.rediger', return_value=dict(PROPOSITION))
    def test_assistant_redige_puis_enregistre_apres_confirmation(self, _mock):
        from school_admin.services.assistant_enseignant_secondaire_tools import execute_enseignant_secondaire_tool
        from school_admin.services.assistant_enseignant_secondaire_actions import get_enseignant_secondaire_action
        from school_admin.services.assistant_tools import build_assistant_context

        ctx = build_assistant_context(self.etab, {'annee_scolaire_consultee_id': self.annee.id},
                                      professeur=self.prof, persona='enseignant')
        res = execute_enseignant_secondaire_tool(ctx, 'rediger_cahier_texte',
                                                 {'classe': '6e A', 'notes': 'fractions, ex 5 et 6'})
        self.assertEqual(res['statut'], 'en_attente_confirmation', res)
        self.assertEqual(CahierTexte.objects.count(), 0)
        self.assertIn('brouillon', res['resume'])
        self.assertIn('définitif', res['resume'])
        action = get_enseignant_secondaire_action('rediger_cahier_texte')
        modes = [c.get('mode') for c in action.choices(res)]
        self.assertEqual(modes[:2], ['brouillon', 'valider'])
        ok = action.apply(ctx, res)
        self.assertEqual(ok['statut'], 'ok', ok)
        e = CahierTexte.objects.get()
        self.assertEqual(e.statut, 'brouillon')
        self.assertTrue(e.redige_par_ia)
        self.assertEqual(e.heure_debut, time(0, 0))
        lecture = execute_enseignant_secondaire_tool(ctx, 'get_cahier_texte', {'classe': '6e A'})
        self.assertEqual(lecture['nb'], 1)
        self.assertIn('ne peut plus être modifiée', lecture['regle'])
        # Le professeur choisit ensuite « Valider » : l'entrée est verrouillée.
        ok = action.apply(ctx, dict(res, mode='valider'))
        self.assertIn('ne peut plus être modifiée', ok['message'])
        e.refresh_from_db()
        self.assertEqual(e.statut, 'valide')
        self.assertIsNotNone(e.date_validation)
        self.assertEqual(action.apply(ctx, dict(res, mode='brouillon')).get('erreur'), ct.MESSAGE_VERROUILLE)

    @patch('school_admin.services.cahier_texte.rediger', return_value=dict(PROPOSITION))
    def test_assistant_valide_sur_demande_explicite(self, _mock):
        from school_admin.services.assistant_enseignant_secondaire_tools import execute_enseignant_secondaire_tool
        from school_admin.services.assistant_tools import build_assistant_context

        ctx = build_assistant_context(self.etab, {'annee_scolaire_consultee_id': self.annee.id},
                                      professeur=self.prof, persona='enseignant')
        res = execute_enseignant_secondaire_tool(ctx, 'rediger_cahier_texte',
                                                 {'classe': '6e A', 'notes': 'angles', 'valider': True})
        self.assertIn('VALIDER', res['resume'])
        self.assertTrue(res['valider'])

    def test_validation_verrouille_et_demande_de_modification(self):
        e = ct.enregistrer(self.prof, self.classe, self.today, PROPOSITION, matiere=self.matiere)
        ct.valider(e)
        with self.assertRaises(ValueError):
            ct.enregistrer(self.prof, self.classe, self.today, PROPOSITION, entree=e)
        with self.assertRaises(ValueError):
            ct.supprimer(e)
        with self.assertRaises(ValueError):
            ct.demander_modification(e, self.prof, 'court')
        ct.demander_modification(e, self.prof, 'Erreur sur la date du travail à faire.')
        with self.assertRaises(ValueError):
            ct.demander_modification(e, self.prof, 'Encore une demande en double.')
        ct.traiter_demande(e, self.etab, accepter=False, reponse='Non, c’est correct.')
        e.refresh_from_db()
        self.assertEqual((e.statut, e.demande_statut), ('valide', 'refusee'))
        ct.demander_modification(e, self.prof, 'Erreur sur la date du travail à faire.')
        ct.traiter_demande(e, self.etab, accepter=True)
        e.refresh_from_db()
        self.assertEqual((e.statut, e.demande_statut), ('brouillon', 'acceptee'))
        self.assertIsNone(e.date_validation)
        ct.enregistrer(self.prof, self.classe, self.today, dict(PROPOSITION, titre='Corrigé'), entree=e)
        e.refresh_from_db()
        self.assertEqual(e.titre, 'Corrigé')

    @override_settings(GEMINI_API_KEY='test')
    @patch('school_admin.services.cahier_texte.rediger', return_value=dict(PROPOSITION))
    def test_pages(self, _mock):
        self.client.force_login(self.prof)
        url = reverse('enseignant:cahier_texte')
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(reverse('enseignant:cahier_texte_rediger'),
                             data=json.dumps({'classe_id': self.classe.id, 'notes': 'fractions'}),
                             content_type='application/json')
        self.assertEqual(r.json()['proposition']['titre'], PROPOSITION['titre'])
        self.client.post(url, dict(PROPOSITION, action='enregistrer', classe_id=self.classe.id,
                                   matiere_id=self.matiere.id, date=self.today.isoformat(), heure_debut='00:00',
                                   statut='brouillon', ia='1'))
        e = CahierTexte.objects.get(redige_par_ia=True)
        self.assertEqual(e.statut, 'brouillon')
        page = self.client.get(url)
        self.assertContains(page, PROPOSITION['titre'])
        self.assertContains(page, 'Enregistrer en brouillon')
        self.assertContains(page, 'Valider définitivement ?')
        direction = reverse('directeur:cahiers_texte')
        fiche = reverse('professeur:detail_professeur', args=[self.prof.id]) + '?onglet=cahier'
        # Un brouillon n'est visible ni de la direction ni sur la fiche enseignant.
        self.client.force_login(self.etab)
        self.assertNotContains(self.client.get(direction), PROPOSITION['titre'])
        self.assertNotContains(self.client.get(fiche), PROPOSITION['titre'])
        # Validation depuis la page enseignant, puis demande de modification.
        self.client.force_login(self.prof)
        self.client.post(url, {'action': 'valider', 'entree_id': e.id})
        e.refresh_from_db()
        self.assertEqual(e.statut, 'valide')
        self.client.post(url, dict(PROPOSITION, action='enregistrer', entree_id=e.id, classe_id=self.classe.id,
                                   date=self.today.isoformat(), titre='Tentative'))
        e.refresh_from_db()
        self.assertEqual(e.titre, PROPOSITION['titre'])
        self.assertContains(self.client.get(url), 'Demander une modification')
        self.client.post(url, {'action': 'demander_modification', 'entree_id': e.id,
                               'motif': 'Le travail est pour lundi, pas jeudi.'})
        self.client.force_login(self.etab)
        page = self.client.get(direction)
        self.assertContains(page, PROPOSITION['titre'])
        self.assertContains(page, 'Le travail est pour lundi')
        page = self.client.get(fiche)
        self.assertContains(page, 'data-fe-panel="cahier"')
        self.assertContains(page, PROPOSITION['titre'])
        self.client.post(direction, {'action': 'traiter_demande', 'entree_id': e.id, 'decision': 'accepter',
                                     'next': 'https://exemple.invalid/'})
        e.refresh_from_db()
        self.assertEqual(e.statut, 'brouillon')
