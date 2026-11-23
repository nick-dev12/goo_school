import json
from decimal import Decimal

from django.test import SimpleTestCase

from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.services.assistant_actions import ACTION_SPECS
from school_admin.services.assistant_stream_text import split_spoken_and_suggestions
from school_admin.services.assistant_tools import build_assistant_context, execute_tool, suggestions_after_read
from school_admin.tests_examens import BaseExamens


class AssistantAdministrationTests(BaseExamens):
    def setUp(self):
        super().setUp()
        self.ctx = build_assistant_context(self.etab)
        self.cible = self.awa.numero_eleve

    def test_transfert_synchronise_le_dossier_et_l_inscription(self):
        demande = {'query': self.cible, 'classe': self.classe_b.nom}
        draft = execute_tool(self.ctx, 'transferer_eleve', demande)
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.awa.refresh_from_db()
        self.assertEqual(self.awa.classe, self.classe)
        app = ACTION_SPECS['transferer_eleve'].apply
        self.assertEqual(app(self.ctx, draft)['statut'], 'ok')
        self.awa.refresh_from_db()
        self.assertEqual(self.awa.classe, self.classe_b)
        from school_admin.model.inscription_eleve_model import InscriptionEleve

        self.assertEqual(InscriptionEleve.objects.get(eleve=self.awa, annee_scolaire=self.annee).classe,
                         self.classe_b)
        self.assertIn('a changé', app(self.ctx, draft)['erreur'])

    def test_transfert_refuse_si_la_capacite_change(self):
        draft = execute_tool(self.ctx, 'transferer_eleve', {'query': self.cible, 'classe': self.classe_b.nom})
        self.classe_b.capacite_max = 0
        self.classe_b.save(update_fields=['capacite_max'])
        result = ACTION_SPECS['transferer_eleve'].apply(self.ctx, draft)
        self.assertIn('complète', result['erreur'])
        self.awa.refresh_from_db()
        self.assertEqual(self.awa.classe, self.classe)

    def test_notes_et_transfert_sont_soumis_aux_droits(self):
        personne = PersonnelAdministratif.objects.create(
            username='aria.administration', email='aria-administration@example.test',
            nom='Fall', prenom='Ali', telephone='770000112', fonction='caissier',
            etablissement=self.etab, permissions={'eleves_modifier': True, 'notes_detail': False},
        )
        ctx = build_assistant_context(self.etab, personnel=personne)
        self.assertIn('autorisation', execute_tool(ctx, 'transferer_eleve', {})['erreur'])
        self.assertIn('autorisation', execute_tool(ctx, 'get_moyenne_matiere', {})['erreur'])

    def test_moyenne_zero_et_absence_de_moyenne(self):
        MoyennePeriode.objects.create(
            etablissement=self.etab, eleve=self.awa, annee_scolaire=self.annee,
            periode=self.periode, matiere=self.math, moyenne_matiere=Decimal('0'),
            est_moyenne_generale=False,
        )
        arguments = {'query': self.cible, 'matiere': self.math.code, 'periode': self.periode.nom_periode}
        result = execute_tool(self.ctx, 'get_moyenne_matiere', arguments)
        self.assertEqual(result['moyennes'][0]['moyenne_sur_20'], 0)
        absent = execute_tool(self.ctx, 'get_moyenne_matiere', {**arguments, 'matiere': self.fr.code})
        self.assertEqual(absent['moyennes'], [])
        boutons = suggestions_after_read([('get_moyenne_matiere', result)], ctx=self.ctx)
        self.assertEqual(len(boutons), 5)
        self.assertTrue(all(self.cible in bouton['value'] for bouton in boutons))

    def test_modification_du_dossier_apres_confirmation(self):
        draft = execute_tool(self.ctx, 'modifier_eleve', {'query': self.cible, 'adresse': '12, rue du Test'})
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.awa.refresh_from_db()
        self.assertNotEqual(self.awa.adresse, '12, rue du Test')
        result = ACTION_SPECS['modifier_eleve'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.awa.refresh_from_db()
        self.assertEqual(self.awa.adresse, '12, rue du Test')
        self.assertEqual(self.awa.classe, self.classe)

    def test_moyenne_matiere_du_primaire(self):
        from school_admin.model.note_primaire_model import MoyenneMatierePrimaire

        self.etab.type_etablissement = 'primary'
        MoyenneMatierePrimaire.objects.create(
            eleve=self.awa, classe=self.classe, matiere=self.math,
            periode_scolaire=self.periode, annee_scolaire=self.annee, moyenne=Decimal('14.50'),
        )
        ctx = build_assistant_context(self.etab)
        result = execute_tool(ctx, 'get_moyenne_matiere', {'query': self.cible, 'matiere': self.math.code})
        self.assertEqual(result['moyennes'][0]['moyenne_sur_20'], 14.5)

    def test_inscription_refusee_si_la_derniere_place_est_prise(self):
        draft = execute_tool(self.ctx, 'inscrire_eleve', {
            'nom': 'Exemple', 'prenom': 'Nora', 'classe': self.classe_b.nom,
            'sexe': 'F', 'date_naissance': '2012-01-01', 'lieu_naissance': 'Dakar',
            'nationalite': 'Sénégalaise', 'parent_nom': 'Exemple', 'parent_prenom': 'Sira',
            'parent_telephone': '770000143', 'parent_lien': 'mere',
        })
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.classe_b.capacite_max = 0
        self.classe_b.save(update_fields=['capacite_max'])
        result = ACTION_SPECS['inscrire_eleve'].apply(self.ctx, draft)
        self.assertIn('complète', result['erreur'])


class AssistantSuggestionsTests(SimpleTestCase):
    def test_cinq_suggestions_uniques_sur_le_flux(self):
        propositions = [{'label': f'Suite {n}'} for n in (1, 1, 2, 3, 4, 5, 6)]
        texte, suggestions = split_spoken_and_suggestions(
            'Voici le résultat. [[ARIA_SUGGESTIONS:' + json.dumps(propositions) + ']]',
        )
        self.assertEqual(texte, 'Voici le résultat.')
        self.assertEqual([s['label'] for s in suggestions], [f'Suite {n}' for n in range(1, 6)])
