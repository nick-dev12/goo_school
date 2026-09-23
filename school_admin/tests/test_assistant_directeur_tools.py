"""
Tests des outils de l’assistante vocale — espace directeur.
Les outils de lecture retournent des données ; les outils d’écriture
préparent un brouillon et n’écrivent qu’après apply.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.annonce_model import Annonce
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.eleve_model import Eleve
from school_admin.model.salle_model import Salle
from school_admin.model.sanction_model import Sanction
from school_admin.services.assistant_actions import ACTION_SPECS, is_write_action
from school_admin.services.assistant_intents import (
    is_affectation_read_request,
    is_small_talk,
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
    context_snapshot,
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
        module_comptabilite=True,
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
            'get_caisse',
            'get_volume_horaire',
            'get_sanctions',
            'get_affectations',
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
            'inscription_eleves', 'certificats', 'caisse', 'volume_horaire',
            'affectations',
        ):
            self.assertIn(key, keys)
        for page in PAGE_CATALOG:
            try:
                reverse(page['route'])
            except NoReverseMatch:
                self.fail(f'Route invalide : {page["route"]}')

    def test_lecture_sanctions_et_chercher_en_base(self):
        with patch.object(Eleve, '_should_regenerate_qr', return_value=False):
            eleve_a = Eleve(
                username=f'sanc-a-{self.etab.pk}'[:20],
                numero_eleve=f'SA{self.etab.pk:04d}'[:20],
                nom='Diallo',
                prenom='Awa',
                date_naissance=date(2010, 1, 1),
                lieu_naissance='Dakar',
                sexe='F',
                nationalite='Sénégalaise',
                etablissement=self.etab,
                classe=self.classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom='Diallo',
                parent_prenom='Amadou',
                parent_telephone='770000010',
                parent_lien='pere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            eleve_a.set_password('Eleve@Test1!')
            eleve_a.save()
            eleve_b = Eleve(
                username=f'sanc-b-{self.etab.pk}'[:20],
                numero_eleve=f'SB{self.etab.pk:04d}'[:20],
                nom='Sow',
                prenom='Ibra',
                date_naissance=date(2010, 2, 2),
                lieu_naissance='Dakar',
                sexe='M',
                nationalite='Sénégalaise',
                etablissement=self.etab,
                classe=self.classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom='Sow',
                parent_prenom='Fatou',
                parent_telephone='770000011',
                parent_lien='mere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            eleve_b.set_password('Eleve@Test1!')
            eleve_b.save()
        Sanction.objects.create(
            eleve=eleve_a,
            classe=self.classe,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            type_sanction='avertissement',
            raison='indiscipline',
            gravite='legere',
            attribue_par_type='directeur',
            attribue_par_nom='Directeur test',
        )
        Sanction.objects.create(
            eleve=eleve_b,
            classe=self.classe,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            type_sanction='blame',
            raison='perturbation_cours',
            gravite='moyenne',
            attribue_par_type='directeur',
            attribue_par_nom='Directeur test',
        )
        Sanction.objects.create(
            eleve=eleve_a,
            classe=self.classe,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            type_sanction='retenue',
            raison='retards_repetes',
            gravite='moyenne',
            attribue_par_type='directeur',
            attribue_par_nom='Directeur test',
        )
        stats = execute_tool(self.ctx, 'get_sanctions', {})
        self.assertEqual(stats['nb_sanctions'], 3)
        self.assertEqual(stats['nb_eleves_avec_sanction'], 2)
        detail = execute_tool(self.ctx, 'get_sanctions', {'query': 'Diallo'})
        self.assertEqual(detail['nb_sanctions'], 2)
        self.assertEqual(len(detail['sanctions']), 2)
        found = execute_tool(
            self.ctx,
            'chercher_en_base',
            {'question': 'combien d eleves ont des sanctions'},
        )
        self.assertEqual(found['source'], 'sanctions')
        self.assertTrue(found['trouve'])
        self.assertEqual(found['nb_eleves_avec_sanction'], 2)

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
        self.assertEqual(
            resolve_action_intent('Réinscrire Diallo en 3e A')[0],
            'reinscrire_eleve',
        )
        reinscrire_direct = resolve_action_intent('Réinscrire ATEMKENG Julie')
        self.assertEqual(reinscrire_direct[0], 'reinscrire_eleve')
        self.assertIn('ATEMKENG', (reinscrire_direct[1].get('query') or '').upper())
        reinscrire_classe = resolve_action_intent('Réinscrire Diallo en 3e A')
        self.assertEqual(reinscrire_classe[1].get('query'), 'Diallo')
        self.assertIn('3', reinscrire_classe[1].get('classe') or '')
        from school_admin.services.assistant_intents import decide_pending_reply
        pending_reins = {
            'name': 'reinscrire_eleve',
            'draft': {'statut': 'incomplet', 'manquants': ['query']},
        }
        self.assertEqual(
            decide_pending_reply("Combien d'élèves y a-t-il ?", pending_reins),
            'switch',
        )
        self.assertEqual(
            decide_pending_reply('Configure les moyennes', pending_reins),
            'switch',
        )
        self.assertTrue(is_small_talk('bonjours'))
        self.assertTrue(is_small_talk('bonjour'))
        sanction_intent = resolve_action_intent(
            'je veux que tu donne une sanction a CLÉ Jason'
        )
        self.assertEqual(sanction_intent[0], 'donner_sanction')
        self.assertIn('Jason', (sanction_intent[1].get('query') or ''))
        avertissement = resolve_action_intent(
            'Donne un avertissement à Diallo pour indiscipline'
        )
        self.assertEqual(avertissement[0], 'donner_sanction')
        self.assertEqual(avertissement[1].get('query'), 'Diallo')
        self.assertEqual(avertissement[1].get('type_sanction'), 'avertissement')
        self.assertEqual(avertissement[1].get('raison'), 'indiscipline')
        self.assertEqual(
            resolve_action_intent('Modifie le dossier de Diallo')[0],
            'modifier_eleve',
        )
        self.assertEqual(
            resolve_action_intent('Configure les moyennes en classique')[0],
            'configurer_moyennes',
        )
        self.assertEqual(
            resolve_action_intent('Crée un moratoire pour Diallo')[0],
            'creer_moratoire',
        )
        self.assertEqual(
            resolve_action_intent('Fixe la moyenne de passage à 10')[0],
            'configurer_standards',
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

    def test_parametres_comptabilite_creation(self):
        lecture = execute_tool(self.ctx, 'get_parametres_comptabilite', {})
        self.assertIn('2nde', lecture['groupes_disponibles'])
        draft = execute_tool(
            self.ctx,
            'creer_parametres_comptabilite',
            {
                'nom': 'Tarifs lycée',
                'groupes_classes': '2nde',
                'montant_frais_inscription': '25000',
                'montant_mensualite': '15000',
            },
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        from school_admin.model.parametres_comptabilite_groupe_classe_model import (
            ParametresComptabiliteGroupeClasse,
        )
        self.assertFalse(
            ParametresComptabiliteGroupeClasse.objects.filter(etablissement=self.etab).exists()
        )
        from unittest.mock import patch

        with patch('school_admin.services.realtime_helpers.emit_live') as emit_live:
            result = ACTION_SPECS['creer_parametres_comptabilite'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        parametre = ParametresComptabiliteGroupeClasse.objects.get(etablissement=self.etab)
        self.assertEqual(parametre.nom, 'Tarifs lycée')
        self.assertIn('2nde', parametre.groupes_classes)
        emit_live.assert_called()
        emit_args = emit_live.call_args[0]
        self.assertEqual(emit_args[1], 'comptabilite.parametres')
        self.assertEqual(emit_live.call_args[0][2]['item']['action'], 'created')
        self.assertEqual(resolve_action_intent('Crée les paramètres de comptabilité')[0],
                         'creer_parametres_comptabilite')
        intent = resolve_action_intent(
            'suprime les parametre de scolariter de la premier'
        )
        self.assertEqual(intent[0], 'supprimer_parametres_comptabilite')
        self.assertEqual(intent[1].get('query'), 'premier')

    def test_write_action_registry(self):
        self.assertTrue(is_write_action('creer_classe'))
        self.assertTrue(is_write_action('creer_publier_annonce'))
        self.assertTrue(is_write_action('inscrire_eleve'))
        self.assertTrue(is_write_action('creer_professeur'))
        self.assertTrue(is_write_action('ajouter_depense'))
        self.assertFalse(is_write_action('get_effectifs'))
        self.assertFalse(is_write_action('get_caisse'))
        self.assertGreaterEqual(len(ACTION_SPECS), 40)

    def test_donner_sanction_listes_et_groupe(self):
        from school_admin.services.assistant_dossiers import choices_for_donner_sanction

        with patch.object(Eleve, '_should_regenerate_qr', return_value=False):
            premier = Eleve(
                username=f'sanc-g1-{self.etab.pk}'[:20],
                numero_eleve=f'SG{self.etab.pk:04d}'[:20],
                nom='Abega',
                prenom='Franck',
                date_naissance=date(2010, 3, 2),
                lieu_naissance='Yaoundé',
                sexe='M',
                nationalite='Camerounaise',
                etablissement=self.etab,
                classe=self.classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom='Abega',
                parent_prenom='Paul',
                parent_telephone='770000020',
                parent_lien='pere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            premier.set_password('Eleve@Test1!')
            premier.save()
            second = Eleve(
                username=f'sanc-g2-{self.etab.pk}'[:20],
                numero_eleve=f'SH{self.etab.pk:04d}'[:20],
                nom='Ngo',
                prenom='Marie',
                date_naissance=date(2010, 4, 2),
                lieu_naissance='Yaoundé',
                sexe='F',
                nationalite='Camerounaise',
                etablissement=self.etab,
                classe=self.classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom='Ngo',
                parent_prenom='Claire',
                parent_telephone='770000021',
                parent_lien='mere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            second.set_password('Eleve@Test1!')
            second.save()
        draft = execute_tool(
            self.ctx,
            'donner_sanction',
            {'query': 'Abega Franck et Ngo Marie'},
        )
        self.assertEqual(draft['statut'], 'incomplet')
        self.assertEqual(draft['manquants'], ['type_sanction'])
        self.assertNotIn('Avertissement', draft['message'])
        self.assertNotIn('Blâme', draft['message'])
        type_choices = choices_for_donner_sanction(draft)
        self.assertGreaterEqual(len(type_choices), 8)
        self.assertEqual(type_choices[0]['widget'], 'select')
        draft = execute_tool(
            self.ctx,
            'donner_sanction',
            {**draft, 'type_sanction': 'blame'},
        )
        self.assertEqual(draft['manquants'], ['raison'])
        raison_choices = choices_for_donner_sanction(draft)
        self.assertGreaterEqual(len(raison_choices), 10)
        draft = execute_tool(
            self.ctx,
            'donner_sanction',
            {**draft, 'raison': 'indiscipline'},
        )
        self.assertEqual(draft['manquants'], ['gravite'])
        draft = execute_tool(
            self.ctx,
            'donner_sanction',
            {**draft, 'gravite': 'grave'},
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertTrue(draft.get('auto_appliquer'))
        self.assertIn('Abega', draft['description'])
        self.assertIn('Ngo', draft['description'])
        self.assertEqual(set(draft['eleves_ids']), {premier.id, second.id})
        with patch('school_admin.services.realtime_helpers.emit_live'):
            result = ACTION_SPECS['donner_sanction'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.assertEqual(
            Sanction.objects.filter(etablissement=self.etab, eleve__in=[premier, second]).count(),
            2,
        )
        duo = resolve_action_intent('Donne une sanction à Abega et Ngo')
        self.assertEqual(duo[0], 'donner_sanction')
        self.assertIn('Abega', duo[1].get('query') or '')

        from school_admin.services.assistant_intents import (
            annonce_field_request,
            is_vague_annonce_modify,
        )
        self.assertTrue(is_vague_annonce_modify('Je veux modifier.'))
        self.assertTrue(is_vague_annonce_modify('Modifier'))
        self.assertFalse(is_vague_annonce_modify('Modifie le texte.'))
        self.assertFalse(is_vague_annonce_modify('Modifie le titre.'))
        self.assertEqual(annonce_field_request('Modifie le texte.'), 'contenu')
        self.assertEqual(annonce_field_request('Le texte'), 'contenu')
        self.assertEqual(annonce_field_request('Modifie le titre.'), 'titre')
        self.assertEqual(annonce_field_request('Change les destinataires.'), 'destinataires')
        pending_annonce = {
            'name': 'annonce_guidee',
            'draft': {'titre': 'Info', 'contenu': 'Texte', 'destinataires': ['tous']},
        }
        self.assertEqual(
            decide_pending_reply('Modifie le texte.', pending_annonce),
            'continue',
        )
        self.assertEqual(
            decide_pending_reply("Combien d'élèves y a-t-il ?", pending_annonce),
            'switch',
        )
        self.assertEqual(
            decide_pending_reply('Donne une sanction à Diallo', pending_annonce),
            'switch',
        )
        self.assertIsNone(
            resolve_action_intent(
                'je veux que tu me donne la listes des affectations de professeur'
            )
        )
        self.assertTrue(
            is_affectation_read_request(
                'je veux que tu me donne la listes des affectations de professeur'
            )
        )
        affecte = resolve_action_intent('Affecte Diallo en 6e A')
        self.assertEqual(affecte[0], 'affecter_professeur')


def _make_etablissement_type(type_etab, prefix):
    suffix = date.today().strftime('%Y%m%d%H%M%S%f')
    email = f'{prefix}.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'{prefix} Aria {suffix[-6:]}',
        code_etablissement=f'{prefix[:3].upper()}-{suffix[-6:]}',
        adresse='1 rue des Tests',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement=type_etab,
        directeur_prenom='Awa',
        directeur_nom='Ndiaye',
        directeur_email=f'dir.{prefix}.{suffix}@aria-test.local',
        module_comptabilite=True,
        actif=True,
    )
    etab.set_password('Vague1@Test1!')
    etab.save()
    return etab


class AssistantDirecteurVague1Tests(TestCase):
    """Filtrage schéma/prompt, cycle collège+lycée, permissions personnel."""

    def _schema_names(self, etab):
        from school_admin.services.assistant_tools import directeur_tools_schema

        ctx = build_assistant_context(etab)
        return {
            item['function']['name']
            for item in directeur_tools_schema(ctx)
            if item.get('function')
        }

    def test_contexte_flags_par_type(self):
        primaire = _make_etablissement_type('primary', 'prim')
        dual = _make_etablissement_type('collège_lycée', 'dual')
        mixte = _make_etablissement_type('mixte', 'mix')
        ctx_p = build_assistant_context(primaire)
        ctx_d = build_assistant_context(dual)
        ctx_m = build_assistant_context(mixte)
        self.assertTrue(ctx_p.est_primaire)
        self.assertFalse(ctx_p.cycle_requis)
        self.assertTrue(ctx_d.est_college_lycee)
        self.assertTrue(ctx_d.cycle_requis)
        self.assertTrue(ctx_m.est_college_lycee)
        snap = context_snapshot(ctx_d)
        self.assertTrue(snap['est_college_lycee'])
        self.assertTrue(snap['cycle_requis'])

    def test_schema_filtre_lmd_et_cg(self):
        from school_admin.services.assistant_schema import CG_TOOLS, SUPERIEUR_ONLY_TOOLS

        lycee = _make_etablissement_type('lycée', 'lyc')
        primaire = _make_etablissement_type('primary', 'prm')
        superieur = _make_etablissement_type('superieur', 'sup')
        names_lycee = self._schema_names(lycee)
        names_prim = self._schema_names(primaire)
        names_sup = self._schema_names(superieur)
        for name in SUPERIEUR_ONLY_TOOLS:
            self.assertNotIn(name, names_lycee)
            self.assertNotIn(name, names_prim)
            self.assertIn(name, names_sup)
        for name in CG_TOOLS:
            self.assertNotIn(name, names_lycee)
            self.assertNotIn(name, names_sup)
        self.assertIn('creer_classe', names_lycee)
        self.assertIn('get_effectifs', names_prim)

    def test_prompt_varie_selon_le_type(self):
        from school_admin.services.gemini_assistant_service import system_prompt_static_for

        primaire = build_assistant_context(_make_etablissement_type('primary', 'prp'))
        dual = build_assistant_context(_make_etablissement_type('mixte', 'mxp'))
        superieur = build_assistant_context(_make_etablissement_type('superieur', 'spp'))
        p_prompt = system_prompt_static_for(primaire)
        d_prompt = system_prompt_static_for(dual)
        s_prompt = system_prompt_static_for(superieur)
        self.assertIn('primaire', p_prompt.lower())
        self.assertIn('ects', p_prompt.lower())
        self.assertIn('cycle', d_prompt.lower())
        self.assertIn('étudiants', s_prompt.lower())
        self.assertIn('comptabilité générale : indisponible', d_prompt.lower())

    def test_creer_classe_dual_exige_le_cycle(self):
        etab = _make_etablissement_type('collège_lycée', 'cyc')
        ctx = build_assistant_context(etab)
        draft = execute_tool(ctx, 'creer_classe', {'nom': '6e A'})
        self.assertEqual(draft['statut'], 'incomplet')
        self.assertIn('cycle', draft['manquants'])
        self.assertFalse(Classe.objects.filter(etablissement=etab, nom='6e A').exists())
        draft_ok = execute_tool(ctx, 'creer_classe', {'nom': '6e A', 'cycle': 'college'})
        self.assertEqual(draft_ok['statut'], 'en_attente_confirmation')
        self.assertEqual(draft_ok['niveau'], 'college')
        result = ACTION_SPECS['creer_classe'].apply(ctx, draft_ok)
        self.assertEqual(result['statut'], 'ok')
        classe = Classe.objects.get(etablissement=etab, nom='6e A')
        self.assertEqual(classe.niveau, 'college')

    def test_creer_classe_lycee_sans_cycle(self):
        etab = _make_etablissement_type('lycée', 'ly2')
        ctx = build_assistant_context(etab)
        draft = execute_tool(ctx, 'creer_classe', {'nom': '1ère S'})
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertEqual(draft['niveau'], 'lycee')

    def test_niveau_enseignement_mixte_sans_defaut_primaire(self):
        from school_admin.services.assistant_schema import resolve_niveau_enseignement

        etab = _make_etablissement_type('mixte', 'nvx')
        self.assertIsNone(resolve_niveau_enseignement(etab))
        self.assertEqual(resolve_niveau_enseignement(etab, 'lycée'), 'lycee')
        self.assertEqual(resolve_niveau_enseignement(etab, 'collège'), 'college')

    def test_personnel_sans_droit_ne_cree_pas_de_classe(self):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        etab = _make_etablissement_type('lycée', 'per')
        suffix = str(etab.pk)
        personnel = PersonnelAdministratif(
            username=f'caissier.{suffix}',
            email=f'caissier.{suffix}@aria-test.local',
            nom='Fall',
            prenom='Ibra',
            telephone='770000099',
            fonction='caissier',
            etablissement=etab,
            actif=True,
            permissions={},
        )
        personnel.set_password('Caissier@Test1!')
        personnel.save()
        ctx = build_assistant_context(etab, personnel=personnel)
        refused = execute_tool(ctx, 'creer_classe', {'nom': '2nde B'})
        self.assertIn('autorisation', refused.get('erreur', '').lower())
        self.assertFalse(Classe.objects.filter(etablissement=etab, nom='2nde B').exists())
        allowed = execute_tool(ctx, 'get_caisse', {})
        self.assertNotIn('erreur', allowed)
        search_notes = execute_tool(
            ctx,
            'chercher_en_base',
            {'question': 'notes de Diallo'},
        )
        self.assertIn('autorisation', search_notes.get('erreur', '').lower())


def _make_eleve_simple(etab, classe, nom, prenom, sexe='F', suffix='1'):
    from school_admin.model.eleve_model import Eleve

    with patch.object(Eleve, '_should_regenerate_qr', return_value=False):
        with patch.object(Etablissement, 'recalculer_facturation', return_value=None):
            eleve = Eleve(
                username=f'v2-{suffix}-{etab.pk}'[:20],
                numero_eleve=f'V2{etab.pk}{suffix}'[:20],
                nom=nom,
                prenom=prenom,
                date_naissance=date(2010, 3, 3),
                lieu_naissance='Dakar',
                sexe=sexe,
                nationalite='Sénégalaise',
                etablissement=etab,
                classe=classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom=nom,
                parent_prenom='Parent',
                parent_telephone='770000020',
                parent_lien='pere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            eleve.set_password('Eleve@Test1!')
            eleve.save()
    return eleve


def _make_inscription(eleve, classe, annee, etab):
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    return InscriptionEleve.objects.create(
        annee_scolaire=annee,
        eleve=eleve,
        nom=eleve.nom,
        prenom=eleve.prenom,
        date_naissance=eleve.date_naissance,
        lieu_naissance=eleve.lieu_naissance,
        sexe=eleve.sexe,
        nationalite=eleve.nationalite,
        numero_eleve=eleve.numero_eleve,
        matricule_eleve=eleve.matricule_eleve,
        etablissement=etab,
        classe=classe,
        date_inscription=date(2026, 9, 1),
        statut='nouvelle',
        parent_nom=eleve.parent_nom,
        parent_prenom=eleve.parent_prenom,
        parent_telephone=eleve.parent_telephone,
        parent_lien=eleve.parent_lien,
    )


class AssistantDirecteurVague2Tests(TestCase):
    """Pilotage + scolarité : schéma filtré, lecture, écritures confirmées."""

    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='1ère A',
            niveau='lycee',
            code_classe=f'LYC-{cls.etab.pk}-1A',
            capacite_max=25,
            etablissement=cls.etab,
        )
        cls.periode_1 = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='1er Trimestre',
            type_periode='trimestre',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 15),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=False,
        )
        cls.periode_2 = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='2e Trimestre',
            type_periode='trimestre',
            date_debut=date(2027, 1, 5),
            date_fin=date(2027, 3, 31),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=True,
        )
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Ba', 'Awa', 'F', 'a')
        cls.inscription = _make_inscription(cls.eleve, cls.classe, cls.annee, cls.etab)
        cls.ctx = build_assistant_context(cls.etab)

    def test_schema_expose_vague2_sauf_cycles_hors_dual(self):
        from school_admin.services.assistant_schema import CG_TOOLS, DUAL_ONLY_TOOLS
        from school_admin.services.assistant_tools import directeur_tools_schema

        names = {
            item['function']['name']
            for item in directeur_tools_schema(self.ctx)
            if item.get('function')
        }
        for name in (
            'get_statistiques_pilotage',
            'get_taux_reussite',
            'get_taux_presence',
            'get_comparatif_periodes',
            'get_fiche_scolarite',
            'get_bilan_scolarite',
            'get_impayes',
            'ouvrir_recu',
            'get_moratoires',
            'verifier_statuts_paiement',
            'synchroniser_remises_fratrie',
        ):
            self.assertIn(name, names)
        for name in DUAL_ONLY_TOOLS:
            self.assertNotIn(name, names)
        for name in CG_TOOLS:
            self.assertNotIn(name, names)

        dual = _make_etablissement_type('mixte', 'v2d')
        dual_names = {
            item['function']['name']
            for item in directeur_tools_schema(build_assistant_context(dual))
            if item.get('function')
        }
        self.assertIn('get_repartition_cycles', dual_names)
        for name in CG_TOOLS:
            self.assertNotIn(name, dual_names)

    def test_effectifs_capacite_et_pilotage(self):
        effectifs = execute_tool(self.ctx, 'get_effectifs', {})
        self.assertEqual(effectifs['capacite_totale'], 25)
        self.assertEqual(effectifs['places_libres'], 24)
        dash = execute_tool(self.ctx, 'get_statistiques_pilotage', {})
        self.assertEqual(dash['effectifs']['nb_eleves'], 1)
        self.assertEqual(dash['effectifs']['nb_filles'], 1)
        self.assertIn('taux_recouvrement', dash['scolarite'])
        found = execute_tool(
            self.ctx,
            'chercher_en_base',
            {'question': 'tableau de bord de l etablissement'},
        )
        self.assertEqual(found['source'], 'pilotage')

    def test_taux_reussite_et_comparatif(self):
        from school_admin.model.moyenne_periode_model import MoyennePeriode
        from school_admin.model.standards_reussite_model import StandardsReussite

        StandardsReussite.objects.create(
            etablissement=self.etab,
            annee_scolaire=self.annee,
            moyenne_passage='10.00',
        )
        MoyennePeriode.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            periode=self.periode_1,
            annee_scolaire=self.annee,
            est_moyenne_generale=True,
            moyenne_generale='09.00',
        )
        MoyennePeriode.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            periode=self.periode_2,
            annee_scolaire=self.annee,
            est_moyenne_generale=True,
            moyenne_generale='12.50',
        )
        reussite = execute_tool(self.ctx, 'get_taux_reussite', {'periode': '2e'})
        self.assertEqual(reussite['nb_moyennes'], 1)
        self.assertEqual(reussite['nb_au_dessus'], 1)
        self.assertEqual(reussite['taux_reussite'], 100.0)
        self.assertNotIn('credits', reussite)
        comparatif = execute_tool(self.ctx, 'get_comparatif_periodes', {})
        self.assertEqual(comparatif['periode']['moyenne'], 12.5)
        self.assertEqual(comparatif['periode_precedente']['moyenne'], 9.0)
        self.assertEqual(comparatif['delta_moyenne'], 3.5)

    def test_taux_presence(self):
        from school_admin.model.matiere_model import Matiere
        from school_admin.model.presence_model import Presence
        from school_admin.model.professeur_model import Professeur

        suffix = str(self.etab.pk)
        matiere = Matiere.objects.create(
            nom=f'Histoire {suffix}',
            code=f'HIST{suffix}'[:10],
            etablissement=self.etab,
        )
        prof = Professeur.objects.create_user(
            username=f'prof.v2.{suffix}',
            email=f'prof.v2.{suffix}@aria-test.local',
            password='Prof@Test1!',
            nom='Ndiaye',
            prenom='Omar',
            telephone='770000030',
            numero_employe=f'EMPV2{suffix}',
            matiere_principale=matiere,
            etablissement=self.etab,
            niveau_enseignement='lycee',
            actif=True,
        )
        today = date.today()
        Presence.objects.create(
            eleve=self.eleve,
            classe=self.classe,
            professeur=prof,
            etablissement=self.etab,
            date=today,
            statut='present',
            annee_scolaire=self.annee,
        )
        Presence.objects.create(
            eleve=self.eleve,
            classe=self.classe,
            professeur=prof,
            etablissement=self.etab,
            date=today - timedelta(days=1),
            statut='absent',
            annee_scolaire=self.annee,
            numero_appel=1,
        )
        taux = execute_tool(self.ctx, 'get_taux_presence', {'jours': 7})
        self.assertEqual(taux['nb_enregistrements'], 2)
        self.assertEqual(taux['taux_presence'], 50.0)
        eleve_taux = execute_tool(self.ctx, 'get_taux_presence', {'query': 'Ba'})
        self.assertEqual(eleve_taux['eleve'], self.eleve.nom_complet)
        self.assertEqual(eleve_taux['taux_presence'], 50.0)

    def test_repartition_cycles_dual_seulement(self):
        refuse = execute_tool(self.ctx, 'get_repartition_cycles', {})
        self.assertIn('pas proposé', refuse.get('erreur', '').lower())
        dual = _make_etablissement_type('collège_lycée', 'v2c')
        annee = _make_annee(dual, libelle='2026-2027-d')
        college = Classe.objects.create(
            nom='6e A',
            niveau='college',
            code_classe=f'COL-{dual.pk}-6A',
            capacite_max=20,
            etablissement=dual,
        )
        lycee = Classe.objects.create(
            nom='2nde B',
            niveau='lycee',
            code_classe=f'LYC-{dual.pk}-2B',
            capacite_max=20,
            etablissement=dual,
        )
        eleve_c = _make_eleve_simple(dual, college, 'Fall', 'Ibra', 'M', 'c')
        eleve_l = _make_eleve_simple(dual, lycee, 'Diop', 'Sira', 'F', 'l')
        _make_inscription(eleve_c, college, annee, dual)
        _make_inscription(eleve_l, lycee, annee, dual)
        ctx = build_assistant_context(dual)
        data = execute_tool(ctx, 'get_repartition_cycles', {})
        self.assertNotIn('erreur', data)
        cycles = {row['cycle']: row['effectif'] for row in data['cycles']}
        self.assertEqual(cycles.get('college'), 1)
        self.assertEqual(cycles.get('lycee'), 1)

    def test_fiche_bilan_impayes_recu_moratoire(self):
        from decimal import Decimal

        from school_admin.model.comptabilite_eleve_model import (
            ComptabiliteEleve,
            FraisInscription,
            PaiementEleve,
        )
        from school_admin.model.recouvrement_model import EcheanceMoratoire, Moratoire

        fiche = ComptabiliteEleve.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            statut_paiement='en_retard',
        )
        frais = FraisInscription.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            comptabilite_eleve=fiche,
            montant=Decimal('50000'),
            montant_paye=Decimal('10000'),
            reste_a_payer=Decimal('40000'),
            date_echeance=date(2026, 8, 1),
            statut='en_retard',
            type_frais='inscription',
        )
        paiement = PaiementEleve.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            type_paiement='frais_inscription',
            frais_inscription=frais,
            montant=Decimal('10000'),
            mode_paiement='especes',
            numero_recu='REC-2026-00001',
        )

        fiche_data = execute_tool(self.ctx, 'get_fiche_scolarite', {'query': 'Ba'})
        self.assertEqual(fiche_data['eleve'], self.eleve.nom_complet)
        self.assertEqual(fiche_data['reste'], 40000.0)
        self.assertTrue(fiche_data['inscription'])
        self.assertEqual(fiche_data['dernier_recu'], 'REC-2026-00001')
        self.assertIsNotNone(fiche_data['parent_a_relancer'])

        via_compta = execute_tool(self.ctx, 'get_comptabilite', {'query': 'Ba'})
        self.assertEqual(via_compta['dernier_recu'], 'REC-2026-00001')

        bilan = execute_tool(self.ctx, 'get_bilan_scolarite', {})
        self.assertEqual(bilan['total_du'], 50000.0)
        self.assertEqual(bilan['total_paye'], 10000.0)
        self.assertEqual(bilan['reste'], 40000.0)

        impayes = execute_tool(self.ctx, 'get_impayes', {})
        self.assertGreaterEqual(impayes['nb'], 1)
        self.assertEqual(impayes['impayes'][0]['eleve'], self.eleve.nom_complet)

        recu = execute_tool(self.ctx, 'ouvrir_recu', {'numero': 'REC-2026-00001'})
        self.assertTrue(recu['ouvrir'])
        self.assertIn(str(paiement.id), recu['url'] or '')

        mora = Moratoire.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            comptabilite_eleve=fiche,
            motif='Échéancier parental',
            montant_total=Decimal('40000'),
            statut='actif',
        )
        EcheanceMoratoire.objects.create(
            moratoire=mora,
            numero=1,
            date_echeance=date(2026, 10, 1),
            montant=Decimal('20000'),
        )
        moratoires = execute_tool(self.ctx, 'get_moratoires', {'query': 'Ba'})
        self.assertEqual(moratoires['nb'], 1)
        self.assertEqual(len(moratoires['moratoires'][0]['echeances']), 1)
        fiche_mora = execute_tool(self.ctx, 'get_fiche_scolarite', {'query': 'Ba'})
        self.assertIsNotNone(fiche_mora['moratoire'])

    def test_ecritures_exigent_confirmation(self):
        from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve

        fiche = ComptabiliteEleve.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            statut_paiement='a_jour',
        )
        draft = execute_tool(self.ctx, 'verifier_statuts_paiement', {})
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        fiche.refresh_from_db()
        self.assertEqual(fiche.statut_paiement, 'a_jour')
        result = ACTION_SPECS['verifier_statuts_paiement'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')

        remises = execute_tool(self.ctx, 'synchroniser_remises_fratrie', {})
        self.assertEqual(remises['statut'], 'en_attente_confirmation')
        self.assertEqual(remises['perimetre'], 'etablissement')

    def test_personnel_sans_droit_scolarite(self):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        personnel = PersonnelAdministratif(
            username=f'caissier.v2.{self.etab.pk}',
            email=f'caissier.v2.{self.etab.pk}@aria-test.local',
            nom='Kane',
            prenom='Awa',
            telephone='770000040',
            fonction='secretaire',
            etablissement=self.etab,
            actif=True,
            permissions={},
        )
        personnel.set_password('Secret@Test1!')
        personnel.save()
        ctx = build_assistant_context(self.etab, personnel=personnel)
        refused = execute_tool(ctx, 'get_impayes', {})
        self.assertIn('autorisation', refused.get('erreur', '').lower())
        refused_write = execute_tool(ctx, 'verifier_statuts_paiement', {})
        self.assertIn('autorisation', refused_write.get('erreur', '').lower())
