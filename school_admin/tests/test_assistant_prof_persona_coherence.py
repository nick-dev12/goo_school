"""
Cohérence persona / niveau_enseignement prof (source de vérité : type_etablissement).
"""
from datetime import date

from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from school_admin.model.professeur_model import Professeur
from school_admin.services.assistant_prof_persona import (
    expected_niveau_enseignement,
    is_professeur_etablissement_primaire,
    niveau_enseignement_for_type_etablissement,
    professeur_niveau_coherent_avec_etablissement,
    resolve_professeur_assistant_persona,
    sync_professeur_niveau_from_etablissement,
)
from school_admin.tests.test_assistant_enseignant_primaire_tools import (
    _make_etablissement_primaire,
)
from school_admin.tests.test_assistant_directeur_tools import _make_etablissement


class ProfPersonaCoherenceTests(TestCase):
    def test_persona_depends_on_type_not_niveau_field(self):
        etab = _make_etablissement_primaire()
        mat = Matiere.objects.create(
            nom='EPS',
            code='EPS-COH',
            etablissement=etab,
            actif=True,
        )
        prof = Professeur(
            username='prof.coh.mismatch',
            email='prof.coh.mismatch@test.local',
            nom='Test',
            prenom='Mismatch',
            telephone='770000099',
            numero_employe='COH99',
            matiere_principale=mat,
            etablissement=etab,
            niveau_enseignement='lycee',
            actif=True,
        )
        prof.set_password('Prof@Test1!')
        self.assertEqual(
            resolve_professeur_assistant_persona(prof),
            'enseignant_primaire',
        )
        self.assertFalse(professeur_niveau_coherent_avec_etablissement(prof))

    def test_save_syncs_niveau_from_etablissement_type(self):
        etab = _make_etablissement()
        mat = Matiere.objects.create(
            nom='Physique',
            code='PHY-COH',
            etablissement=etab,
            actif=True,
        )
        prof = Professeur.objects.create_user(
            username='prof.coh.sync',
            email='prof.coh.sync@test.local',
            password='Prof@Test1!',
            nom='Sync',
            prenom='Auto',
            telephone='770000098',
            numero_employe='COH98',
            matiere_principale=mat,
            etablissement=etab,
            niveau_enseignement='primaire',
            actif=True,
        )
        prof.refresh_from_db()
        self.assertEqual(
            prof.niveau_enseignement,
            niveau_enseignement_for_type_etablissement(etab.type_etablissement),
        )
        self.assertTrue(professeur_niveau_coherent_avec_etablissement(prof))

    def test_is_professeur_primaire_uses_etablissement_type(self):
        etab = _make_etablissement_primaire()
        mat = Matiere.objects.create(
            nom='Lecture',
            code='LEC-COH',
            etablissement=etab,
            actif=True,
        )
        prof = Professeur(
            username='prof.coh.pri',
            email='prof.coh.pri@test.local',
            nom='Pri',
            prenom='Maire',
            telephone='770000097',
            numero_employe='COH97',
            matiere_principale=mat,
            etablissement=etab,
            niveau_enseignement='lycee',
            actif=True,
        )
        self.assertTrue(is_professeur_etablissement_primaire(prof))
        sync_professeur_niveau_from_etablissement(prof)
        self.assertEqual(prof.niveau_enseignement, 'primaire')

    def test_expected_niveau_superieur(self):
        suffix = date.today().strftime('%H%M%S')
        email = f'sup.coh.{suffix}@test.local'
        etab = Etablissement(
            username=email,
            email=email,
            nom='Sup Coherence',
            code_etablissement=f'SC{suffix}'[:12],
            adresse='1 rue',
            pays='SN',
            ville='Dakar',
            type_etablissement='superieur',
            directeur_prenom='A',
            directeur_nom='B',
            directeur_email=f'd.{suffix}@t.local',
            actif=True,
        )
        etab.set_password('Test1234!')
        etab.save()
        mat = Matiere.objects.create(
            nom='Algo',
            code=f'AL{suffix}'[:10],
            etablissement=etab,
            actif=True,
        )
        prof = Professeur(
            etablissement=etab,
            matiere_principale=mat,
            niveau_enseignement='college',
        )
        self.assertEqual(expected_niveau_enseignement(prof), 'superieur')
