"""
Tests des outils de l’assistante vocale — espace directeur.
Les outils de lecture retournent des données ; les outils d’écriture
préparent un brouillon et n’écrivent qu’après apply.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.annonce_model import Annonce
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.salle_model import Salle
from school_admin.services.assistant_actions import ACTION_SPECS, is_write_action
from school_admin.services.assistant_intents import (
    resolve_action_intent,
    resolve_annonce_intent,
    resolve_emploi_intent,
    resolve_open_intent,
)
from school_admin.services.assistant_pages import PAGE_CATALOG, list_pages
from school_admin.services.assistant_tools import (
    TOOL_HANDLERS,
    TOOLS_SCHEMA,
    build_assistant_context,
    execute_tool,
)


def _make_etablissement():
    suffix = date.today().strftime('%Y%m%d%H%M%S')
    email = f'directeur.aria.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Lycée Aria Test {suffix}',
        code_etablissement=f'LYC-A{suffix[-6:]}',
        adresse='1 rue des Tests',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='lycée',
        directeur_prenom='Moussa',
        directeur_nom='Sarr',
        directeur_email=f'dir.{suffix}@aria-test.local',
        actif=True,
    )
    etab.set_password('Lycee@Test1!')
    etab.save()
    return etab


def _make_annee(etab, libelle='2026-2027', debut=2026, active=True):
    return AnneeScolaire.objects.create(
        etablissement=etab,
        libelle=libelle,
        annee_debut=debut,
        annee_fin=debut + 1,
        date_debut=date(debut, 9, 1),
        date_fin=date(debut + 1, 6, 30),
        est_active=active,
        est_ouverte=True,
    )


class AssistantDirecteurToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='2nde A',
            niveau='lycee',
            code_classe=f'LYC-{cls.etab.pk}-2A',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.periode = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='1er Trimestre',
            type_periode='trimestre',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 15),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=True,
        )
        cls.ctx = build_assistant_context(cls.etab)

    def test_tous_les_outils_sont_enregistres(self):
        schema_names = {
            item['function']['name']
            for item in TOOLS_SCHEMA
            if item.get('function')
        }
        attendus = {
            'chercher_en_base',
            'get_effectifs',
            'rechercher_eleves',
            'ouvrir_page',
            'ouvrir_classe',
            'creer_publier_annonce',
            'creer_emploi_du_temps',
            'ajouter_creneau_emploi',
            'get_notifications',
            'get_preinscriptions',
            'get_liaisons',
            'get_examens',
            'get_annees',
            'get_salles',
            'get_matieres',
            'get_parametres_comptabilite',
        }
        attendus.update(ACTION_SPECS.keys())
        manquants = attendus - schema_names
        self.assertFalse(manquants, f'Outils absents du schéma : {manquants}')
        handler_manquants = attendus - set(TOOL_HANDLERS)
        self.assertFalse(handler_manquants, f'Handlers absents : {handler_manquants}')

    def test_pages_directeur_resolvent(self):
        pages = list_pages()
        self.assertGreaterEqual(len(pages), 30)
        keys = {page['key'] for page in pages}
        for key in (
            'dashboard', 'classes', 'annonces', 'bulletins', 'comptabilite',
            'examens', 'annees', 'preinscriptions', 'liaisons', 'ajouter_classe',
            'inscription_eleves', 'certificats',
        ):
            self.assertIn(key, keys)
        for page in PAGE_CATALOG:
            try:
                reverse(page['route'])
            except NoReverseMatch:
                self.fail(f'Route invalide : {page["route"]}')

    def test_lecture_effectifs_et_annees(self):
        effectifs = execute_tool(self.ctx, 'get_effectifs', {})
        self.assertEqual(effectifs['nb_classes'], 1)
        annees = execute_tool(self.ctx, 'get_annees', {})
        self.assertEqual(annees['annees'][0]['libelle'], '2026-2027')
        periodes = execute_tool(self.ctx, 'get_periodes', {})
        self.assertEqual(periodes['periode_active'], '1er Trimestre')

    def test_annonce_prepare_sans_ecrire(self):
        draft = execute_tool(self.ctx, 'creer_publier_annonce', {
            'titre': 'Conseil',
            'contenu': 'Conseil de classe vendredi.',
            'destinataires': ['enseignants'],
        })
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertEqual(Annonce.objects.filter(etablissement=self.etab).count(), 0)

    def test_creer_classe_prepare_puis_apply(self):
        draft = execute_tool(self.ctx, 'creer_classe', {'nom': '1ère S', 'niveau': 'lycee'})
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertFalse(Classe.objects.filter(etablissement=self.etab, nom='1ère S').exists())
        result = ACTION_SPECS['creer_classe'].apply(self.ctx, draft)
        self.assertNotIn('erreur', result)
        self.assertTrue(Classe.objects.filter(etablissement=self.etab, nom='1ère S').exists())

    def test_creer_salle_et_periode_apres_confirmation(self):
        salle_draft = execute_tool(self.ctx, 'creer_salle', {
            'nom': 'Labo chimie',
            'numero': 'B12',
        })
        self.assertEqual(salle_draft['statut'], 'en_attente_confirmation')
        salle_ok = ACTION_SPECS['creer_salle'].apply(self.ctx, salle_draft)
        self.assertTrue(Salle.objects.filter(etablissement=self.etab, numero='B12').exists())
        self.assertIn('créée', salle_ok['message'])

        periode_draft = execute_tool(self.ctx, 'creer_periode', {
            'nom': '2e Trimestre',
            'type_periode': 'trimestre',
            'date_debut': '2027-01-05',
            'date_fin': '2027-03-31',
        })
        self.assertEqual(periode_draft['statut'], 'en_attente_confirmation')
        periode_ok = ACTION_SPECS['creer_periode'].apply(self.ctx, periode_draft)
        self.assertNotIn('erreur', periode_ok)
        self.assertTrue(
            PeriodeScolaire.objects.filter(
                etablissement=self.etab, nom_periode='2e Trimestre'
            ).exists()
        )

    def test_annee_scolaire_creation_utilise_controleur(self):
        draft = execute_tool(self.ctx, 'creer_annee_scolaire', {
            'date_debut': '2027-09-01',
            'date_fin': '2028-06-30',
        })
        self.assertEqual(draft['libelle'], '2027-2028')
        self.assertEqual(AnneeScolaire.objects.filter(etablissement=self.etab).count(), 1)
        result = ACTION_SPECS['creer_annee_scolaire'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.assertTrue(
            AnneeScolaire.objects.filter(etablissement=self.etab, libelle='2027-2028').exists()
        )

    def test_session_examen_prepare_et_apply(self):
        draft = execute_tool(self.ctx, 'creer_session_examen', {
            'nom': 'Composition 1',
            'periode': '1er Trimestre',
            'date_debut': '2026-11-10',
            'date_fin': '2026-11-20',
        })
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        from school_admin.model.session_examen_model import SessionExamen
        self.assertEqual(SessionExamen.objects.filter(etablissement=self.etab).count(), 0)
        result = ACTION_SPECS['creer_session_examen'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.assertEqual(SessionExamen.objects.filter(etablissement=self.etab).count(), 1)

    def test_actions_destructives_exigent_confirmation(self):
        annonce = Annonce.objects.create(
            etablissement=self.etab,
            auteur_directeur=self.etab,
            titre='À supprimer',
            contenu='Brouillon test',
            destinataires=['tous'],
            statut='brouillon',
            annee_scolaire=self.annee,
        )
        draft = execute_tool(self.ctx, 'supprimer_annonce', {'query': 'À supprimer'})
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertTrue(draft.get('destructive'))
        self.assertTrue(Annonce.objects.filter(pk=annonce.pk, actif=True).exists())
        ACTION_SPECS['supprimer_annonce'].apply(self.ctx, draft)
        self.assertFalse(Annonce.objects.filter(pk=annonce.pk, actif=True).exists())

    def test_intents_actions(self):
        self.assertEqual(
            resolve_action_intent('Justifie l’absence de Diallo')[0],
            'justifier_absence',
        )
        self.assertEqual(
            resolve_action_intent('Crée une classe 3e B')[0],
            'creer_classe',
        )
        self.assertIsNotNone(resolve_annonce_intent('Crée une annonce pour dire que demain est férié'))
        self.assertEqual(
            resolve_emploi_intent('Crée l’emploi du temps de 2nde A')['action'],
            'creer_emploi_du_temps',
        )
        self.assertEqual(
            resolve_open_intent('Ouvre les bulletins')[0],
            'ouvrir_page',
        )

    def test_write_action_registry(self):
        self.assertTrue(is_write_action('creer_classe'))
        self.assertTrue(is_write_action('creer_publier_annonce'))
        self.assertFalse(is_write_action('get_effectifs'))
        self.assertGreaterEqual(len(ACTION_SPECS), 30)

    def test_parametres_comptabilite_lecture_et_mutation(self):
        from decimal import Decimal

        from school_admin.model.parametres_comptabilite_groupe_classe_model import (
            ParametresComptabiliteGroupeClasse,
        )

        self.etab.module_comptabilite = True
        self.etab.save(update_fields=['module_comptabilite'])

        lecture = execute_tool(self.ctx, 'get_parametres_comptabilite', {})
        self.assertTrue(lecture.get('module_actif'))
        self.assertIn('2nde', lecture['groupes_disponibles'])
        self.assertEqual(lecture['nb'], 0)

        draft = execute_tool(self.ctx, 'creer_parametres_comptabilite', {
            'nom': 'Tarifs 2nde',
            'groupes_classes': ['2nde'],
            'montant_frais_inscription': '25000',
            'montant_mensualite': '15000',
        })
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertEqual(
            ParametresComptabiliteGroupeClasse.objects.filter(etablissement=self.etab).count(),
            0,
        )
        created_ok = ACTION_SPECS['creer_parametres_comptabilite'].apply(self.ctx, draft)
        self.assertEqual(created_ok['statut'], 'ok')
        created = ParametresComptabiliteGroupeClasse.objects.get(etablissement=self.etab)
        self.assertEqual(created.nom, 'Tarifs 2nde')
        self.assertEqual(list(created.groupes_classes), ['2nde'])
        self.assertEqual(created.montant_mensualite, Decimal('15000'))

        update_draft = execute_tool(self.ctx, 'modifier_parametres_comptabilite', {
            'query': 'Tarifs 2nde',
            'montant_mensualite': '18000',
        })
        self.assertEqual(update_draft['statut'], 'en_attente_confirmation')
        ACTION_SPECS['modifier_parametres_comptabilite'].apply(self.ctx, update_draft)
        created.refresh_from_db()
        self.assertEqual(created.montant_mensualite, Decimal('18000'))

        delete_draft = execute_tool(self.ctx, 'supprimer_parametres_comptabilite', {
            'query': 'Tarifs 2nde',
        })
        self.assertTrue(delete_draft.get('destructive'))
        ACTION_SPECS['supprimer_parametres_comptabilite'].apply(self.ctx, delete_draft)
        self.assertFalse(
            ParametresComptabiliteGroupeClasse.objects.filter(pk=created.pk).exists()
        )
        self.assertEqual(
            resolve_action_intent('Crée des paramètres de scolarité pour la 2nde')[0],
            'creer_parametres_comptabilite',
        )
