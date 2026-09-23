"""
Tests des outils de l’assistante vocale — espace directeur.
Les outils de lecture retournent des données ; les outils d’écriture
préparent un brouillon et n’écrivent qu’après apply.
"""
from datetime import date, time as datetime_time, timedelta
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
    directeur_tools_schema,
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


class AssistantDirecteurVague3Tests(TestCase):
    """Pédagogie : notes/moyennes/bulletin, justifications, coefficients, difficulté."""

    @classmethod
    def setUpTestData(cls):
        from school_admin.model.evaluation_model import Evaluation, Note
        from school_admin.model.justification_note_model import JustificationNote
        from school_admin.model.matiere_model import Matiere
        from school_admin.model.moyenne_periode_model import MoyennePeriode
        from school_admin.model.professeur_model import Professeur
        from school_admin.model.standards_reussite_model import StandardsReussite

        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='1ère S',
            niveau='lycee',
            code_classe=f'LYC-{cls.etab.pk}-1S',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.periode = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='2e Trimestre',
            type_periode='trimestre',
            date_debut=date(2027, 1, 5),
            date_fin=date(2027, 3, 31),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=True,
        )
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Sy', 'Awa', 'F', 'p')
        cls.faible = _make_eleve_simple(cls.etab, cls.classe, 'Kane', 'Ibra', 'M', 'q')
        suffix = str(cls.etab.pk)
        cls.matiere = Matiere.objects.create(
            nom=f'Mathématiques {suffix}',
            code=f'MAT{suffix}'[:10],
            coefficient=4,
            etablissement=cls.etab,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.v3.{suffix}',
            email=f'prof.v3.{suffix}@aria-test.local',
            password='Prof@Test1!',
            nom='Fall',
            prenom='Omar',
            telephone='770000050',
            numero_employe=f'EMPV3{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='lycee',
            actif=True,
        )
        cls.evaluation = Evaluation.objects.create(
            titre='Devoir 1',
            classe=cls.classe,
            professeur=cls.prof,
            matiere=cls.matiere,
            date_evaluation=date(2027, 1, 20),
            bareme=20,
            periode_scolaire=cls.periode,
            annee_scolaire=cls.annee,
        )
        cls.note = Note.objects.create(
            eleve=cls.eleve,
            evaluation=cls.evaluation,
            matiere=cls.matiere,
            note=14,
            statut_publication=Note.STATUT_PUBLIEE,
        )
        StandardsReussite.objects.create(
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            moyenne_passage='10.00',
        )
        MoyennePeriode.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            periode=cls.periode,
            annee_scolaire=cls.annee,
            est_moyenne_generale=True,
            moyenne_generale='13.50',
            rang=1,
        )
        MoyennePeriode.objects.create(
            eleve=cls.faible,
            etablissement=cls.etab,
            periode=cls.periode,
            annee_scolaire=cls.annee,
            est_moyenne_generale=True,
            moyenne_generale='08.00',
            rang=2,
        )
        cls.justification = JustificationNote.objects.create(
            note=cls.note,
            classe=cls.classe,
            evaluation=cls.evaluation,
            eleve=cls.eleve,
            matiere=cls.matiere,
            professeur=cls.prof,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            ancienne_note=14,
            nouvelle_note=16,
            motif='Erreur de saisie',
        )
        cls.ctx = build_assistant_context(cls.etab)

    def test_schema_expose_pedagogie_sans_cg(self):
        from school_admin.services.assistant_schema import CG_TOOLS
        from school_admin.services.assistant_tools import directeur_tools_schema

        names = {
            item['function']['name']
            for item in directeur_tools_schema(self.ctx)
            if item.get('function')
        }
        for name in (
            'get_notes_classe',
            'get_moyennes_classe',
            'get_bulletin_eleve',
            'imprimer_bulletins_classe',
            'get_eleves_difficulte',
            'get_justifications_notes',
            'traiter_justification',
            'get_coefficients',
            'configurer_coefficient',
            'get_evaluations',
            'calculer_moyenne_annuelle',
            'get_statistiques_pilotage',
        ):
            self.assertIn(name, names)
        for name in CG_TOOLS:
            self.assertNotIn(name, names)

    def test_notes_moyennes_bulletin_evaluations(self):
        notes = execute_tool(self.ctx, 'get_notes_classe', {'classe': '1ère S'})
        self.assertEqual(notes['nb'], 1)
        self.assertEqual(notes['notes'][0]['note'], 14.0)
        moyennes = execute_tool(self.ctx, 'get_moyennes_classe', {'classe': '1ère S'})
        self.assertEqual(moyennes['nb'], 2)
        self.assertEqual(moyennes['moyennes'][0]['moyenne'], 13.5)
        bulletin = execute_tool(self.ctx, 'get_bulletin_eleve', {'query': 'Sy'})
        self.assertTrue(bulletin['ouvrir'])
        self.assertEqual(bulletin['moyenne'], 13.5)
        self.assertIn(str(self.eleve.id), bulletin['url'] or '')
        impression = execute_tool(self.ctx, 'imprimer_bulletins_classe', {'classe': '1ère S'})
        self.assertTrue(impression['ouvrir'])
        self.assertIn(str(self.classe.id), impression['url'] or '')
        evs = execute_tool(self.ctx, 'get_evaluations', {'classe': '1ère S'})
        self.assertEqual(evs['nb'], 1)
        found = execute_tool(
            self.ctx,
            'chercher_en_base',
            {'question': 'notes de la classe 1ère S', 'classe': '1ère S'},
        )
        self.assertEqual(found['source'], 'notes_classe')

    def test_eleves_difficulte_et_coefficients(self):
        from decimal import Decimal

        difficulte = execute_tool(self.ctx, 'get_eleves_difficulte', {})
        self.assertEqual(difficulte['nb'], 1)
        self.assertEqual(difficulte['eleves'][0]['eleve'], self.faible.nom_complet)
        coefs = execute_tool(self.ctx, 'get_coefficients', {'query': 'Math'})
        self.assertGreaterEqual(coefs['nb'], 1)
        self.assertEqual(coefs['matieres'][0]['coefficient'], 4.0)
        draft = execute_tool(
            self.ctx,
            'configurer_coefficient',
            {'matiere': 'Math', 'coefficient': '5'},
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.matiere.refresh_from_db()
        self.assertEqual(self.matiere.coefficient, Decimal('4.0'))
        result = ACTION_SPECS['configurer_coefficient'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.matiere.refresh_from_db()
        self.assertEqual(self.matiere.coefficient, Decimal('5.0'))

    def test_justifications_et_traitement_confirme(self):
        liste = execute_tool(self.ctx, 'get_justifications_notes', {})
        self.assertEqual(liste['nb'], 1)
        self.assertEqual(liste['justifications'][0]['eleve'], self.eleve.nom_complet)
        draft = execute_tool(
            self.ctx,
            'traiter_justification',
            {'query': 'Sy', 'decision': 'valider'},
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.note.refresh_from_db()
        self.assertEqual(float(self.note.note), 14.0)
        result = ACTION_SPECS['traiter_justification'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.note.refresh_from_db()
        self.assertEqual(float(self.note.note), 16.0)
        refuse_draft = execute_tool(
            self.ctx,
            'calculer_moyenne_annuelle',
            {'classe': '1ère S'},
        )
        self.assertEqual(refuse_draft['statut'], 'en_attente_confirmation')
        applied = ACTION_SPECS['calculer_moyenne_annuelle'].apply(self.ctx, refuse_draft)
        self.assertTrue(applied.get('ouvrir'))

    def test_personnel_sans_droit_notes(self):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        personnel = PersonnelAdministratif(
            username=f'caissier.v3.{self.etab.pk}',
            email=f'caissier.v3.{self.etab.pk}@aria-test.local',
            nom='Sow',
            prenom='Awa',
            telephone='770000060',
            fonction='caissier',
            etablissement=self.etab,
            actif=True,
            permissions={},
        )
        personnel.set_password('Caissier@Test1!')
        personnel.save()
        ctx = build_assistant_context(self.etab, personnel=personnel)
        refused = execute_tool(ctx, 'get_notes_classe', {'classe': '1ère S'})
        self.assertIn('autorisation', refused.get('erreur', '').lower())
        refused_j = execute_tool(ctx, 'traiter_justification', {'query': 'Sy', 'decision': 'valider'})
        self.assertIn('autorisation', refused_j.get('erreur', '').lower())


class AssistantDirecteurVague4Tests(TestCase):
    """Supérieur LMD : ECTS, modules/UE, périodes par niveau. Filtrage type."""

    VAGUE4_TOOLS = (
        'get_ects_etudiant',
        'get_ects_classe',
        'get_modules_classe',
        'affecter_module_classe',
        'fixer_credits_module',
        'get_releve_ects',
        'get_structure_superieur',
        'creer_module',
    )

    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal

        from school_admin.model.academic_structure_model import Department
        from school_admin.model.matiere_model import Matiere
        from school_admin.model.module_model import Module, ModuleClasse
        from school_admin.model.moyenne_periode_model import MoyennePeriode

        cls.etab = _make_etablissement_type('superieur', 'sup4')
        cls.annee = _make_annee(cls.etab)
        cls.dept = Department.objects.create(
            nom='Génie Logiciel',
            sigle='GL',
            etablissement=cls.etab,
        )
        cls.classe = Classe.objects.create(
            nom='L1 A',
            niveau='superieur',
            niveau_lmd='L1',
            code_classe=f'SUP-{cls.etab.pk}-L1A',
            capacite_max=40,
            etablissement=cls.etab,
            department=cls.dept,
        )
        cls.periode = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='Semestre 1',
            type_periode='semestre',
            niveau_lmd='L1',
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 1, 31),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=True,
        )
        cls.periode_s2 = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='Semestre 2',
            type_periode='semestre',
            niveau_lmd='L1',
            date_debut=date(2027, 2, 1),
            date_fin=date(2027, 6, 30),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=False,
        )
        cls.etudiant = _make_eleve_simple(cls.etab, cls.classe, 'Ndoye', 'Awa', 'F', 's4')
        _make_inscription(cls.etudiant, cls.classe, cls.annee, cls.etab)
        cls.module_algo = Module.objects.create(
            nom='Algorithmique',
            code=f'ALG{cls.etab.pk}'[:20],
            etablissement=cls.etab,
            department=cls.dept,
            niveau_lmd='L1',
        )
        cls.module_bdd = Module.objects.create(
            nom='Bases de données',
            code=f'BDD{cls.etab.pk}'[:20],
            etablissement=cls.etab,
            department=cls.dept,
            niveau_lmd='L1',
        )
        ModuleClasse.objects.create(
            module=cls.module_algo,
            classe=cls.classe,
            credits=Decimal('6.00'),
            numero_ue='UE1.1',
            periode=cls.periode,
        )
        ModuleClasse.objects.create(
            module=cls.module_bdd,
            classe=cls.classe,
            credits=Decimal('4.00'),
            numero_ue='UE1.2',
            periode=cls.periode,
        )
        suffix = str(cls.etab.pk)
        cls.matiere = Matiere.objects.create(
            nom=f'Algo {suffix}',
            code=f'AL{suffix}'[:10],
            coefficient=1,
            etablissement=cls.etab,
            credits=Decimal('6.00'),
        )
        cls.matiere_bdd = Matiere.objects.create(
            nom=f'BDD {suffix}',
            code=f'BD{suffix}'[:10],
            coefficient=1,
            etablissement=cls.etab,
            credits=Decimal('4.00'),
        )
        MoyennePeriode.objects.create(
            eleve=cls.etudiant,
            etablissement=cls.etab,
            periode=cls.periode,
            annee_scolaire=cls.annee,
            matiere=cls.matiere,
            est_moyenne_generale=False,
            moyenne_matiere=Decimal('12.00'),
            credits=Decimal('6.00'),
        )
        MoyennePeriode.objects.create(
            eleve=cls.etudiant,
            etablissement=cls.etab,
            periode=cls.periode,
            annee_scolaire=cls.annee,
            matiere=cls.matiere_bdd,
            est_moyenne_generale=False,
            moyenne_matiere=Decimal('08.00'),
            credits=Decimal('4.00'),
        )
        cls.ctx = build_assistant_context(cls.etab)

    def _schema_names(self, etab):
        return {
            item['function']['name']
            for item in directeur_tools_schema(build_assistant_context(etab))
            if item.get('function')
        }

    def test_schema_superieur_seulement(self):
        from school_admin.services.assistant_schema import CG_TOOLS
        from school_admin.services.assistant_tools import directeur_tools_schema

        names_sup = self._schema_names(self.etab)
        names_prim = self._schema_names(_make_etablissement_type('primary', 'p4'))
        names_lyc = self._schema_names(_make_etablissement_type('lycée', 'l4'))
        for name in self.VAGUE4_TOOLS:
            self.assertIn(name, names_sup)
            self.assertNotIn(name, names_prim)
            self.assertNotIn(name, names_lyc)
        for name in CG_TOOLS:
            self.assertNotIn(name, names_sup)
        creer = next(
            item for item in directeur_tools_schema(self.ctx)
            if item.get('function', {}).get('name') == 'creer_periode'
        )
        self.assertIn('niveau_lmd', creer['function']['parameters']['required'])

    def test_ects_etudiant_et_classe(self):
        ects = execute_tool(self.ctx, 'get_ects_etudiant', {'query': 'Ndoye'})
        self.assertEqual(ects['credits_inscrits'], 10.0)
        self.assertEqual(ects['credits_valides'], 6.0)
        self.assertEqual(ects['credits_restants'], 4.0)
        self.assertFalse(ects['invente'])
        self.assertEqual(ects['niveau_lmd'], 'L1')
        self.assertGreaterEqual(len(ects['par_semestre']), 1)
        classe = execute_tool(self.ctx, 'get_ects_classe', {'classe': 'L1 A'})
        self.assertEqual(classe['credits_maquette'], 10.0)
        self.assertEqual(classe['nb_modules'], 2)
        self.assertEqual(classe['etudiants'][0]['credits_valides'], 6.0)
        modules = execute_tool(self.ctx, 'get_modules_classe', {'classe': 'L1 A'})
        self.assertEqual(modules['nb'], 2)
        codes_ue = {item['numero_ue'] for item in modules['modules']}
        self.assertEqual(codes_ue, {'UE1.1', 'UE1.2'})
        found = execute_tool(
            self.ctx,
            'chercher_en_base',
            {'question': 'crédits ECTS de Ndoye'},
        )
        self.assertEqual(found['source'], 'ects')
        self.assertEqual(found['credits_inscrits'], 10.0)

    def test_periodes_niveau_lmd_et_creation(self):
        periodes = execute_tool(self.ctx, 'get_periodes', {'niveau_lmd': 'L1'})
        noms = {item['nom'] for item in periodes['periodes']}
        self.assertIn('Semestre 1', noms)
        self.assertTrue(all(
            item.get('niveau_lmd') in (None, '', 'L1')
            for item in periodes['periodes']
        ))
        incomplet = execute_tool(
            self.ctx,
            'creer_periode',
            {
                'nom': 'Semestre 1',
                'date_debut': '2026-09-01',
                'date_fin': '2027-01-31',
            },
        )
        self.assertEqual(incomplet['statut'], 'incomplet')
        self.assertIn('niveau_lmd', incomplet['manquants'])
        refuse = execute_tool(
            self.ctx,
            'creer_periode',
            {
                'nom': 'Semestre 7',
                'niveau_lmd': 'L1',
                'date_debut': '2026-09-01',
                'date_fin': '2027-01-31',
            },
        )
        self.assertIn('semestre officiel', refuse.get('erreur', '').lower())
        draft = execute_tool(
            self.ctx,
            'creer_periode',
            {
                'nom': 'S7',
                'niveau_lmd': 'M1',
                'date_debut': '2026-09-01',
                'date_fin': '2027-01-31',
            },
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertEqual(draft['nom'], 'Semestre 7')
        self.assertEqual(draft['niveau_lmd'], 'M1')
        self.assertFalse(
            PeriodeScolaire.objects.filter(
                etablissement=self.etab, nom_periode='Semestre 7', niveau_lmd='M1'
            ).exists()
        )
        result = ACTION_SPECS['creer_periode'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        created = PeriodeScolaire.objects.get(
            etablissement=self.etab, nom_periode='Semestre 7', niveau_lmd='M1'
        )
        self.assertEqual(created.type_periode, 'semestre')

    def test_affecter_et_fixer_credits(self):
        from decimal import Decimal

        from school_admin.model.module_model import Module, ModuleClasse

        module = Module.objects.create(
            nom='Réseaux',
            code=f'RES{self.etab.pk}'[:20],
            etablissement=self.etab,
            department=self.dept,
            niveau_lmd='L1',
        )
        draft = execute_tool(
            self.ctx,
            'affecter_module_classe',
            {
                'module': 'Réseaux',
                'classe': 'L1 A',
                'credits': '5',
                'numero_ue': 'UE1.3',
                'periode': 'Semestre 1',
            },
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertFalse(ModuleClasse.objects.filter(module=module, classe=self.classe).exists())
        applied = ACTION_SPECS['affecter_module_classe'].apply(self.ctx, draft)
        self.assertEqual(applied['statut'], 'ok')
        mc = ModuleClasse.objects.get(module=module, classe=self.classe)
        self.assertEqual(mc.credits, Decimal('5.00'))
        self.assertEqual(mc.numero_ue, 'UE1.3')
        self.assertEqual(mc.periode_id, self.periode.id)
        fix = execute_tool(
            self.ctx,
            'fixer_credits_module',
            {'module': 'Réseaux', 'classe': 'L1 A', 'credits': '6'},
        )
        self.assertEqual(fix['statut'], 'en_attente_confirmation')
        mc.refresh_from_db()
        self.assertEqual(mc.credits, Decimal('5.00'))
        ACTION_SPECS['fixer_credits_module'].apply(self.ctx, fix)
        mc.refresh_from_db()
        self.assertEqual(mc.credits, Decimal('6.00'))

    def test_creer_module_credits_et_releve(self):
        from school_admin.model.module_model import Module, ModuleClasse

        draft = execute_tool(
            self.ctx,
            'creer_module',
            {
                'nom': 'Compilation',
                'filiere': 'Génie Logiciel',
                'credits': '3',
                'numero_ue': 'UE2.1',
                'niveau_lmd': 'L1',
                'classe': 'L1 A',
            },
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertFalse(Module.objects.filter(etablissement=self.etab, nom='Compilation').exists())
        result = ACTION_SPECS['creer_module'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        module = Module.objects.get(etablissement=self.etab, nom='Compilation')
        self.assertEqual(module.niveau_lmd, 'L1')
        mc = ModuleClasse.objects.get(module=module, classe=self.classe)
        self.assertEqual(float(mc.credits), 3.0)
        self.assertEqual(mc.numero_ue, 'UE2.1')
        structure = execute_tool(self.ctx, 'get_structure_superieur', {'query': 'Algo'})
        self.assertTrue(structure['modules'])
        self.assertIn('credits_totaux', structure['modules'][0])
        releve = execute_tool(self.ctx, 'get_releve_ects', {'query': 'Ndoye'})
        self.assertTrue(releve['ouvrir'])
        self.assertIn(str(self.etudiant.id), releve['url'] or '')
        self.assertEqual(releve['credits_valides'], 6.0)

    def test_personnel_sans_droit_ects(self):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        personnel = PersonnelAdministratif(
            username=f'caissier.v4.{self.etab.pk}',
            email=f'caissier.v4.{self.etab.pk}@aria-test.local',
            nom='Fall',
            prenom='Awa',
            telephone='770000070',
            fonction='caissier',
            etablissement=self.etab,
            actif=True,
            permissions={},
        )
        personnel.set_password('Caissier@Test1!')
        personnel.save()
        ctx = build_assistant_context(self.etab, personnel=personnel)
        refused = execute_tool(ctx, 'get_ects_etudiant', {'query': 'Ndoye'})
        self.assertIn('autorisation', refused.get('erreur', '').lower())
        refused_w = execute_tool(
            ctx,
            'affecter_module_classe',
            {'module': 'Algorithmique', 'classe': 'L1 A', 'credits': '6'},
        )
        self.assertIn('autorisation', refused_w.get('erreur', '').lower())

    def test_primaire_ne_voit_pas_ects(self):
        primaire = _make_etablissement_type('primary', 'p4b')
        ctx = build_assistant_context(primaire)
        result = execute_tool(ctx, 'get_ects_etudiant', {'query': 'Ndoye'})
        self.assertIn('type d’établissement', result.get('erreur', '').lower())


class AssistantDirecteurVague5Tests(TestCase):
    """RH : dossier employé, fiche de paie vacataire, absences prof."""

    VAGUE5_TOOLS = (
        'get_dossier_employe',
        'modifier_dossier_employe',
        'get_absences_professeur',
        'supprimer_absence_professeur',
        'ouvrir_fiche_paie',
        'get_volume_horaire',
    )

    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal

        from school_admin.model.caisse_etablissement_model import (
            AbsenceEnseignant,
            PaieProfesseurPeriode,
        )
        from school_admin.model.employe_dossier_model import DossierEmployeComplementaire
        from school_admin.model.matiere_model import Matiere
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif
        from school_admin.model.professeur_model import Professeur

        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        suffix = str(cls.etab.pk)
        cls.matiere = Matiere.objects.create(
            nom=f'Physique {suffix}',
            code=f'PH{suffix}'[:10],
            coefficient=2,
            etablissement=cls.etab,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.v5.{suffix}',
            email=f'prof.v5.{suffix}@aria-test.local',
            password='Prof@Test1!',
            nom='Diop',
            prenom='Mamadou',
            telephone='770000080',
            numero_employe=f'EMPV5{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='lycee',
            prix_volume_horaire=Decimal('5000.00'),
            date_embauche=date(2024, 9, 1),
            actif=True,
        )
        DossierEmployeComplementaire.objects.create(
            professeur=cls.prof,
            type_contrat='vacataire',
            numero_cnss='CNSS-12345',
            salaire_base=Decimal('150000.00'),
            banque='SGBS',
            numero_compte_bancaire='SN08 SN012 0100123456789012',
        )
        cls.personnel = PersonnelAdministratif(
            username=f'sec.v5.{suffix}',
            email=f'sec.v5.{suffix}@aria-test.local',
            nom='Ba',
            prenom='Awa',
            telephone='770000081',
            fonction='secretaire',
            etablissement=cls.etab,
            numero_employe=f'SECV5{suffix}',
            actif=True,
            permissions={},
        )
        cls.personnel.set_password('Secret@Test1!')
        cls.personnel.save()
        DossierEmployeComplementaire.objects.create(
            personnel_administratif=cls.personnel,
            type_contrat='cdi',
            numero_cnss='CNSS-67890',
            salaire_base=Decimal('200000.00'),
        )
        cls.absence = AbsenceEnseignant.objects.create(
            etablissement=cls.etab,
            professeur=cls.prof,
            date=date(2026, 10, 5),
            minutes=120,
        )
        cls.paie = PaieProfesseurPeriode.objects.create(
            etablissement=cls.etab,
            professeur=cls.prof,
            annee_scolaire=cls.annee,
            date_debut=date(2026, 10, 1),
            date_fin=date(2026, 10, 31),
            heures=Decimal('12.00'),
            montant_brut=Decimal('60000.00'),
            montant_net=Decimal('60000.00'),
        )
        cls.ctx = build_assistant_context(cls.etab)

    def test_schema_expose_rh_sans_cg_ni_paie_permanente(self):
        from school_admin.services.assistant_schema import CG_TOOLS

        names = {
            item['function']['name']
            for item in directeur_tools_schema(self.ctx)
            if item.get('function')
        }
        for name in self.VAGUE5_TOOLS:
            self.assertIn(name, names)
        for name in CG_TOOLS:
            self.assertNotIn(name, names)
        self.assertNotIn('get_paie_permanents', names)
        self.assertNotIn('creer_bulletin_paie', names)
        self.assertNotIn('valider_bulletin_paie', names)
        primaire = _make_etablissement_type('primary', 'p5')
        names_p = {
            item['function']['name']
            for item in directeur_tools_schema(build_assistant_context(primaire))
            if item.get('function')
        }
        self.assertIn('get_dossier_employe', names_p)
        self.assertNotIn('get_ects_etudiant', names_p)

    def test_dossier_et_modification_confirmee(self):
        from decimal import Decimal

        dossier = execute_tool(self.ctx, 'get_dossier_employe', {'query': 'Diop'})
        self.assertEqual(dossier['role'], 'professeur')
        self.assertEqual(dossier['type_contrat'], 'vacataire')
        self.assertEqual(dossier['numero_cnss'], 'CNSS-12345')
        self.assertEqual(dossier['salaire_base'], 150000.0)
        self.assertEqual(dossier['rib'], 'SN08 SN012 0100123456789012')
        self.assertEqual(dossier['tarif_horaire'], 5000.0)
        self.assertIsNone(dossier['charges_sociales'])
        admin = execute_tool(
            self.ctx,
            'get_dossier_employe',
            {'query': 'Ba', 'role': 'personnel'},
        )
        self.assertEqual(admin['role'], 'personnel')
        self.assertEqual(admin['type_contrat'], 'cdi')
        draft = execute_tool(
            self.ctx,
            'modifier_dossier_employe',
            {'query': 'Diop', 'salaire_base': '160000', 'type_contrat': 'cdd'},
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.prof.dossier_complementaire.refresh_from_db()
        self.assertEqual(self.prof.dossier_complementaire.salaire_base, Decimal('150000.00'))
        result = ACTION_SPECS['modifier_dossier_employe'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.prof.dossier_complementaire.refresh_from_db()
        self.assertEqual(self.prof.dossier_complementaire.salaire_base, Decimal('160000.00'))
        self.assertEqual(self.prof.dossier_complementaire.type_contrat, 'cdd')
        found = execute_tool(
            self.ctx,
            'chercher_en_base',
            {'question': 'CNSS de Diop'},
        )
        self.assertEqual(found['source'], 'dossier_employe')

    def test_absences_et_suppression_confirmee(self):
        from school_admin.model.caisse_etablissement_model import AbsenceEnseignant

        liste = execute_tool(self.ctx, 'get_absences_professeur', {'query': 'Diop'})
        self.assertEqual(liste['nb'], 1)
        self.assertEqual(liste['heures_totales'], 2.0)
        self.assertEqual(liste['absences'][0]['date'], '2026-10-05')
        draft = execute_tool(
            self.ctx,
            'supprimer_absence_professeur',
            {'query': 'Diop', 'date': '2026-10-05'},
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertTrue(
            AbsenceEnseignant.objects.filter(pk=self.absence.pk).exists()
        )
        result = ACTION_SPECS['supprimer_absence_professeur'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.assertFalse(
            AbsenceEnseignant.objects.filter(pk=self.absence.pk).exists()
        )

    def test_fiche_paie_et_volume_horaire_periode(self):
        fiche = execute_tool(
            self.ctx,
            'ouvrir_fiche_paie',
            {'query': 'Diop', 'mois': '2026-10'},
        )
        self.assertTrue(fiche['ouvrir'])
        self.assertIn(str(self.prof.id), fiche['url'] or '')
        self.assertEqual(fiche['montant_net'], 60000.0)
        vide = execute_tool(
            self.ctx,
            'ouvrir_fiche_paie',
            {'query': 'Diop', 'mois': '2026-09'},
        )
        self.assertIn('aucune paie', vide.get('erreur', '').lower())
        volume = execute_tool(
            self.ctx,
            'get_volume_horaire',
            {'query': 'Diop', 'periode': 'mois', 'mois': '2026-10'},
        )
        self.assertEqual(volume['periode_kind'], 'mois')
        self.assertTrue(volume['lignes'])
        self.assertEqual(volume['lignes'][0]['professeur'], self.prof.nom_complet)

    def test_personnel_sans_droit_rh(self):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        caissier = PersonnelAdministratif(
            username=f'caissier.v5.{self.etab.pk}',
            email=f'caissier.v5.{self.etab.pk}@aria-test.local',
            nom='Kane',
            prenom='Ibra',
            telephone='770000082',
            fonction='caissier',
            etablissement=self.etab,
            actif=True,
            permissions={},
        )
        caissier.set_password('Caissier@Test1!')
        caissier.save()
        ctx = build_assistant_context(self.etab, personnel=caissier)
        refused = execute_tool(ctx, 'get_dossier_employe', {'query': 'Diop'})
        self.assertIn('autorisation', refused.get('erreur', '').lower())
        refused_w = execute_tool(
            ctx,
            'modifier_dossier_employe',
            {'query': 'Diop', 'salaire_base': '1'},
        )
        self.assertIn('autorisation', refused_w.get('erreur', '').lower())


class AssistantDirecteurVague6Tests(TestCase):
    """Examens : créneaux, notes, modifier session. Masqués en primaire."""

    VAGUE6_NEW_TOOLS = (
        'modifier_session_examen',
        'get_emploi_examens',
        'ajouter_creneau_examen',
        'supprimer_creneau_examen',
        'get_notes_examen',
    )

    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal

        from school_admin.model.creneau_examen_model import CreneauExamen
        from school_admin.model.matiere_model import Matiere
        from school_admin.model.note_examen_model import NoteExamen
        from school_admin.model.professeur_model import Professeur
        from school_admin.model.session_examen_model import SessionExamen

        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='1ère S',
            niveau='lycee',
            code_classe=f'LYC-{cls.etab.pk}-1S',
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
        suffix = str(cls.etab.pk)
        cls.matiere = Matiere.objects.create(
            nom=f'Mathématiques {suffix}',
            code=f'MA{suffix}'[:10],
            coefficient=4,
            etablissement=cls.etab,
        )
        cls.matiere_fr = Matiere.objects.create(
            nom=f'Français {suffix}',
            code=f'FR{suffix}'[:10],
            coefficient=3,
            etablissement=cls.etab,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.v6.{suffix}',
            email=f'prof.v6.{suffix}@aria-test.local',
            password='Prof@Test1!',
            nom='Fall',
            prenom='Omar',
            telephone='770000090',
            numero_employe=f'EMPV6{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='lycee',
            actif=True,
        )
        cls.salle = Salle.objects.create(
            nom='Salle A1',
            numero=f'A1{suffix}'[:10],
            etablissement=cls.etab,
            type_salle='classe',
            actif=True,
        )
        cls.salle_b = Salle.objects.create(
            nom='Salle B2',
            numero=f'B2{suffix}'[:10],
            etablissement=cls.etab,
            type_salle='classe',
            actif=True,
        )
        cls.session = SessionExamen.objects.create(
            nom_examen='Composition 1',
            etablissement=cls.etab,
            periode=cls.periode,
            date_debut=date(2026, 10, 6),
            date_fin=date(2026, 10, 10),
            annee_scolaire=cls.annee,
        )
        cls.session.classes.add(cls.classe)
        cls.session.matieres.add(cls.matiere)
        cls.creneau = CreneauExamen.objects.create(
            session_examen=cls.session,
            matiere=cls.matiere,
            date_examen=date(2026, 10, 7),
            heure_debut=datetime_time(8, 0),
            heure_fin=datetime_time(10, 0),
            surveillant=cls.prof,
            salle=cls.salle,
            annee_scolaire=cls.annee,
        )
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Diallo', 'Awa', 'F', 'v6')
        cls.note = NoteExamen.objects.create(
            eleve=cls.eleve,
            session_examen=cls.session,
            creneau_examen=cls.creneau,
            matiere=cls.matiere,
            professeur=cls.prof,
            classe=cls.classe,
            note=Decimal('14.50'),
            bareme=Decimal('20.00'),
            statut_publication=NoteExamen.STATUT_PUBLIEE,
            annee_scolaire=cls.annee,
        )
        cls.ctx = build_assistant_context(cls.etab)

    def test_schema_lycee_college_pas_primaire_sans_cg(self):
        from school_admin.services.assistant_schema import CG_TOOLS

        names = {
            item['function']['name']
            for item in directeur_tools_schema(self.ctx)
            if item.get('function')
        }
        for name in self.VAGUE6_NEW_TOOLS:
            self.assertIn(name, names)
        self.assertIn('get_examens', names)
        for name in CG_TOOLS:
            self.assertNotIn(name, names)

        college = _make_etablissement_type('collège', 'c6')
        names_c = {
            item['function']['name']
            for item in directeur_tools_schema(build_assistant_context(college))
            if item.get('function')
        }
        for name in self.VAGUE6_NEW_TOOLS:
            self.assertIn(name, names_c)

        primaire = _make_etablissement_type('primary', 'p6')
        names_p = {
            item['function']['name']
            for item in directeur_tools_schema(build_assistant_context(primaire))
            if item.get('function')
        }
        for name in self.VAGUE6_NEW_TOOLS:
            self.assertNotIn(name, names_p)
        self.assertIn('get_examens', names_p)
        self.assertIn('creer_session_examen', names_p)
        self.assertNotIn('get_ects_etudiant', names_p)

        superieur = _make_etablissement_type('superieur', 's6')
        names_s = {
            item['function']['name']
            for item in directeur_tools_schema(build_assistant_context(superieur))
            if item.get('function')
        }
        self.assertIn('get_emploi_examens', names_s)
        self.assertIn('get_notes_examen', names_s)

    def test_examens_enrichis_emploi_et_notes(self):
        sessions = execute_tool(self.ctx, 'get_examens', {})
        self.assertEqual(sessions['nb'], 1)
        item = sessions['sessions'][0]
        self.assertEqual(item['nom'], 'Composition 1')
        self.assertEqual(item['nb_creneaux'], 1)
        self.assertIn('1ère S', item['classes'])

        emploi = execute_tool(self.ctx, 'get_emploi_examens', {'query': 'Composition'})
        self.assertEqual(emploi['nb'], 1)
        self.assertEqual(emploi['creneaux'][0]['salle'], 'Salle A1')
        self.assertEqual(emploi['creneaux'][0]['surveillant'], self.prof.nom_complet)
        self.assertEqual(emploi['creneaux'][0]['heure_debut'], '08:00')

        notes = execute_tool(
            self.ctx,
            'get_notes_examen',
            {'session': 'Composition', 'eleve': 'Diallo'},
        )
        self.assertEqual(notes['nb'], 1)
        self.assertEqual(notes['notes'][0]['note_sur_20'], 14.5)
        self.assertEqual(notes['notes'][0]['eleve'], self.eleve.nom_complet)

        found = execute_tool(
            self.ctx,
            'chercher_en_base',
            {'question': 'notes d’examen de Diallo'},
        )
        self.assertEqual(found['source'], 'notes_examen')
        self.assertEqual(found['nb'], 1)

    def test_modifier_session_et_creneau_conflit(self):
        from school_admin.model.creneau_examen_model import CreneauExamen
        from school_admin.model.session_examen_model import SessionExamen

        draft = execute_tool(
            self.ctx,
            'modifier_session_examen',
            {
                'query': 'Composition',
                'nouveau_nom': 'Composition blanche',
                'date_debut': '2026-10-06',
                'date_fin': '2026-10-12',
            },
        )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.session.refresh_from_db()
        self.assertEqual(self.session.nom_examen, 'Composition 1')
        result = ACTION_SPECS['modifier_session_examen'].apply(self.ctx, draft)
        self.assertEqual(result['statut'], 'ok')
        self.session.refresh_from_db()
        self.assertEqual(self.session.nom_examen, 'Composition blanche')
        self.assertEqual(self.session.date_fin, date(2026, 10, 12))

        add = execute_tool(
            self.ctx,
            'ajouter_creneau_examen',
            {
                'session': 'Composition blanche',
                'matiere': self.matiere_fr.nom,
                'date': '2026-10-08',
                'heure_debut': '8h',
                'heure_fin': '10h',
                'salle': 'Salle B2',
                'surveillant': 'Fall',
            },
        )
        self.assertEqual(add['statut'], 'en_attente_confirmation')
        self.assertFalse(
            CreneauExamen.objects.filter(
                session_examen=self.session, matiere=self.matiere_fr
            ).exists()
        )
        applied = ACTION_SPECS['ajouter_creneau_examen'].apply(self.ctx, add)
        self.assertEqual(applied['statut'], 'ok')
        self.assertTrue(
            CreneauExamen.objects.filter(
                session_examen=self.session, matiere=self.matiere_fr
            ).exists()
        )

        conflit = execute_tool(
            self.ctx,
            'ajouter_creneau_examen',
            {
                'session': 'Composition blanche',
                'matiere': self.matiere_fr.nom,
                'date': '2026-10-07',
                'heure_debut': '8h30',
                'heure_fin': '10h30',
                'salle': 'Salle A1',
            },
        )
        self.assertEqual(conflit['statut'], 'en_attente_confirmation')
        refused = ACTION_SPECS['ajouter_creneau_examen'].apply(self.ctx, conflit)
        self.assertIn('salle', refused.get('erreur', '').lower())

        delete = execute_tool(
            self.ctx,
            'supprimer_creneau_examen',
            {
                'session': 'Composition blanche',
                'matiere': self.matiere_fr.nom,
                'date': '2026-10-08',
            },
        )
        self.assertEqual(delete['statut'], 'en_attente_confirmation')
        self.assertTrue(delete.get('destructive'))
        gone = ACTION_SPECS['supprimer_creneau_examen'].apply(self.ctx, delete)
        self.assertEqual(gone['statut'], 'ok')
        self.assertFalse(
            CreneauExamen.objects.filter(
                session_examen=self.session, matiere=self.matiere_fr
            ).exists()
        )
        self.assertTrue(SessionExamen.objects.filter(pk=self.session.pk).exists())

    def test_personnel_sans_droit_examens(self):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        caissier = PersonnelAdministratif(
            username=f'caissier.v6.{self.etab.pk}',
            email=f'caissier.v6.{self.etab.pk}@aria-test.local',
            nom='Kane',
            prenom='Ibra',
            telephone='770000091',
            fonction='caissier',
            etablissement=self.etab,
            actif=True,
            permissions={},
        )
        caissier.set_password('Caissier@Test1!')
        caissier.save()
        ctx = build_assistant_context(self.etab, personnel=caissier)
        refused = execute_tool(ctx, 'get_notes_examen', {'session': 'Composition'})
        self.assertIn('autorisation', refused.get('erreur', '').lower())
        refused_w = execute_tool(
            ctx,
            'ajouter_creneau_examen',
            {'session': 'Composition', 'matiere': 'Maths'},
        )
        self.assertIn('autorisation', refused_w.get('erreur', '').lower())

    def test_intents_examens(self):
        self.assertEqual(
            resolve_action_intent('Modifie la session d’examen Composition')[0],
            'modifier_session_examen',
        )
        self.assertEqual(
            resolve_action_intent('Ajoute un créneau d’examen de maths')[0],
            'ajouter_creneau_examen',
        )
        self.assertEqual(
            resolve_action_intent('Supprime le créneau d’examen de maths')[0],
            'supprimer_creneau_examen',
        )
        self.assertIsNone(resolve_emploi_intent('Ajoute un créneau d’examen de maths'))
