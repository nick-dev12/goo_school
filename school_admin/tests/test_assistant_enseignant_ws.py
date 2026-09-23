"""
Tests WebSocket assistant professeur (consumer Channels, sans Gemini).
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import (
    AffectationProfesseurPrimaire,
)
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from decimal import Decimal

from school_admin.model.module_model import Module, ModuleClasse
from school_admin.model.professeur_model import Professeur
from school_admin.consumers.assistant_consumer import AssistantConsumer
from school_admin.services.assistant_enseignant_examens_tools import _examens_allowed
from school_admin.services.assistant_enseignant_secondaire_tools import (
    get_enseignant_secondaire_tools_schema,
)
from school_admin.tests.test_assistant_enseignant_primaire_tools import (
    _make_etablissement_primaire,
)
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_etablissement,
)


def _run(coro):
    return asyncio.run(coro)


async def _consumer_for_prof(prof, session=None):
    consumer = AssistantConsumer()
    consumer.scope = {
        'user': prof,
        'session': session or {},
    }
    consumer.accept = AsyncMock()
    consumer.close = AsyncMock()
    consumer._send_json = AsyncMock()
    consumer._load_pending = AsyncMock()
    consumer._restore_pending_ui = AsyncMock()
    allowed = await consumer._resolve_etablissement()
    return consumer, allowed


class AssistantEnseignantWsTests(TransactionTestCase):
    """Parcours WS : résolution persona + outil lecture + filtrage schéma."""

    def setUp(self):
        self.etab_pri = _make_etablissement_primaire()
        self.annee_pri = _make_annee(self.etab_pri)
        self.m_pri = Matiere.objects.create(
            nom='Math WS',
            code='MWS-PRI',
            etablissement=self.etab_pri,
            actif=True,
        )
        self.classe_pri = Classe.objects.create(
            nom='CP WS',
            code_classe='CPWS1',
            niveau='primaire',
            etablissement=self.etab_pri,
            actif=True,
        )
        self.prof_pri = Professeur.objects.create_user(
            username='prof.ws.pri',
            email='prof.ws.pri@test.local',
            password='Prof@Test1!',
            nom='Pri',
            prenom='WS',
            telephone='770000030',
            numero_employe='PWSPRI',
            matiere_principale=self.m_pri,
            etablissement=self.etab_pri,
            actif=True,
        )
        aff_p = AffectationProfesseurPrimaire.objects.create(
            professeur=self.prof_pri,
            classe=self.classe_pri,
            annee_scolaire=self.annee_pri,
            actif=True,
        )
        aff_p.matieres.add(self.m_pri)

        self.etab_col = _make_etablissement()
        self.annee_col = _make_annee(self.etab_col)
        suffix = str(self.etab_col.pk)
        self.m_col = Matiere.objects.create(
            nom=f'Hist WS {suffix}',
            code=f'HW{suffix}'[:10],
            etablissement=self.etab_col,
            actif=True,
        )
        self.classe_col = Classe.objects.create(
            nom='4eme WS',
            niveau='college',
            code_classe=f'4WS-{suffix}',
            capacite_max=30,
            etablissement=self.etab_col,
            actif=True,
        )
        self.prof_col = Professeur.objects.create_user(
            username=f'prof.ws.col.{suffix}',
            email=f'prof.ws.col.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Col',
            prenom='WS',
            telephone='770000031',
            numero_employe=f'PWSC{suffix}',
            matiere_principale=self.m_col,
            etablissement=self.etab_col,
            actif=True,
        )
        AffectationProfesseur.objects.create(
            professeur=self.prof_col,
            classe=self.classe_col,
            matiere=self.m_col,
            annee_scolaire=self.annee_col,
            statut='classique',
            actif=True,
        )

        sup_suffix = date.today().strftime('%H%M%S%f')
        sup_email = f'sup.ws.{sup_suffix}@test.local'
        self.etab_sup = Etablissement(
            username=sup_email,
            email=sup_email,
            nom='Sup WS',
            code_etablissement=f'SW{sup_suffix[-10:]}'[:12],
            adresse='1 rue',
            pays='SN',
            ville='Dakar',
            type_etablissement='superieur',
            directeur_prenom='A',
            directeur_nom='B',
            directeur_email=f'd.{sup_suffix}@t.local',
            actif=True,
        )
        self.etab_sup.set_password('Test1234!')
        self.etab_sup.save()
        self.annee_sup = _make_annee(self.etab_sup)
        self.m_sup = Matiere.objects.create(
            nom='Module WS',
            code=f'MW{sup_suffix}'[:10],
            etablissement=self.etab_sup,
            actif=True,
        )
        from school_admin.model.academic_structure_model import Department

        self.dept_sup = Department.objects.create(
            nom='Info WS',
            sigle='IWS',
            etablissement=self.etab_sup,
        )
        self.classe_sup = Classe.objects.create(
            nom='L1 WS',
            niveau='superieur',
            code_classe=f'L1WS-{sup_suffix[-6:]}',
            niveau_lmd='L1',
            etablissement=self.etab_sup,
            department=self.dept_sup,
            actif=True,
        )
        self.prof_sup = Professeur.objects.create_user(
            username=f'prof.ws.sup.{sup_suffix}',
            email=f'prof.ws.sup.{sup_suffix}@test.local',
            password='Prof@Test1!',
            nom='Sup',
            prenom='WS',
            telephone='770000032',
            numero_employe=f'PWSS{sup_suffix[-6:]}',
            matiere_principale=self.m_sup,
            etablissement=self.etab_sup,
            actif=True,
        )
        AffectationProfesseur.objects.create(
            professeur=self.prof_sup,
            classe=self.classe_sup,
            matiere=self.m_sup,
            annee_scolaire=self.annee_sup,
            statut='classique',
            actif=True,
        )
        from school_admin.model.periode_model import PeriodeScolaire

        self.periode_sup = PeriodeScolaire.objects.create(
            etablissement=self.etab_sup,
            nom_periode='Semestre 1',
            type_periode='semestre',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 31),
            annee_scolaire=self.annee_sup.libelle,
            annee_scolaire_fk=self.annee_sup,
            est_active=True,
            niveau_lmd='L1',
        )
        mod = Module.objects.create(
            nom='Algo WS',
            code='ALGOWS',
            etablissement=self.etab_sup,
            department=self.dept_sup,
            niveau_lmd='L1',
        )
        ModuleClasse.objects.create(
            classe=self.classe_sup,
            module=mod,
            periode=self.periode_sup,
            credits=Decimal('6.00'),
            numero_ue='UE1',
        )

    def test_ws_connect_primaire_persona(self):
        async def _run_async():
            consumer, allowed = await _consumer_for_prof(self.prof_pri)
            self.assertTrue(allowed)
            self.assertEqual(consumer.persona, 'enseignant_primaire')
            await consumer.connect()
            consumer.accept.assert_awaited_once()
            consumer.close.assert_not_awaited()

        _run(_run_async())

    def test_ws_connect_college_persona(self):
        async def _run_async():
            consumer, allowed = await _consumer_for_prof(self.prof_col)
            self.assertTrue(allowed)
            self.assertEqual(consumer.persona, 'enseignant')

        _run(_run_async())

    def test_ws_lecture_mes_classes_primaire(self):
        async def _run_async():
            consumer, allowed = await _consumer_for_prof(
                self.prof_pri,
                {'annee_scolaire_consultee_id': self.annee_pri.id},
            )
            self.assertTrue(allowed)
            ctx = await consumer._build_context()
            result = await consumer._execute_tool(ctx, 'get_mes_classes', {})
            self.assertIn('classes', result)
            self.assertEqual(len(result['classes']), 1)

        _run(_run_async())

    def test_ws_college_examens_autorises_sup_refuses(self):
        async def _run_async():
            consumer_col, _ = await _consumer_for_prof(
                self.prof_col,
                {'annee_scolaire_consultee_id': self.annee_col.id},
            )
            ctx_col = await consumer_col._build_context()
            self.assertTrue(_examens_allowed(ctx_col))
            names_col = {
                item['function']['name']
                for item in get_enseignant_secondaire_tools_schema(ctx_col)
                if item.get('function')
            }
            self.assertIn('get_examens_prof', names_col)
            self.assertNotIn('get_modules_classe', names_col)

            consumer_sup, _ = await _consumer_for_prof(
                self.prof_sup,
                {'annee_scolaire_consultee_id': self.annee_sup.id},
            )
            ctx_sup = await consumer_sup._build_context()
            self.assertFalse(_examens_allowed(ctx_sup))
            names_sup = {
                item['function']['name']
                for item in get_enseignant_secondaire_tools_schema(ctx_sup)
                if item.get('function')
            }
            self.assertIn('get_modules_classe', names_sup)
            self.assertNotIn('get_examens_prof', names_sup)
            result_exam = await consumer_sup._execute_tool(
                ctx_sup,
                'get_examens_prof',
                {},
            )
            self.assertIn('erreur', result_exam)
            result_lmd = await consumer_sup._execute_tool(
                ctx_sup,
                'get_modules_classe',
                {'classe': 'L1'},
            )
            self.assertIn('modules', result_lmd)

        _run(_run_async())

    def test_ws_primaire_refuse_outil_secondaire_examens(self):
        async def _run_async():
            consumer, _ = await _consumer_for_prof(
                self.prof_pri,
                {'annee_scolaire_consultee_id': self.annee_pri.id},
            )
            ctx = await consumer._build_context()
            result = await consumer._execute_tool(ctx, 'get_examens_prof', {})
            self.assertIn('erreur', result)

        _run(_run_async())

    def test_ws_asgi_handshake_anonymous_refused(self):
        async def _run_async():
            from school.asgi import application

            communicator = WebsocketCommunicator(application, '/ws/assistant/')
            connected, _subprotocol = await communicator.connect()
            self.assertFalse(connected)
            await communicator.disconnect()

        _run(_run_async())
