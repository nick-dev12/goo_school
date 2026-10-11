"""Pages de structure (classes, matières, modules, périodes) pour tous les types d'établissement."""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from school_admin.model.classe_model import Classe
from school_admin.model.matiere_model import Matiere
from school_admin.model.module_model import Module
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.services import structure_etablissement as se
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
)


class StructureTests(TestCase):
    def _monter(self, type_etab, prefix, niveau):
        self.etab = _make_etablissement_type(type_etab, prefix)
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.classe = Classe.objects.create(nom='Classe A', niveau=niveau, code_classe=f'CA-{s}', capacite_max=1,
                                            etablissement=self.etab, actif=True)
        self.matiere = Matiere.objects.create(nom=f'Mathématiques {s}', code=f'MA{s}'[:10], etablissement=self.etab,
                                              actif=True)
        self.client.force_login(self.etab)

    def _pages(self):
        urls = [reverse('administrateur_etablissement:liste_classes'), reverse('matiere:liste_matieres'),
                reverse('directeur:gestion_periodes_scolaires'),
                reverse('administrateur_etablissement:detail_classe', args=[self.classe.id]),
                reverse('matiere:detail_matiere', args=[self.matiere.id])]
        for u in urls:
            r = self.client.get(u)
            self.assertEqual(r.status_code, 200, u)
            self.assertContains(r, 'hb-head', msg_prefix=u)
        return urls

    def test_lycee(self):
        self._monter('lycée', 'stl', 'lycee')
        self._pages()
        c = se.controle_classes(self.etab, self.annee)
        self.assertTrue(any('sans enseignant' in a['texte'] for a in c['alertes']))
        m = se.controle_matieres(self.etab, self.annee)
        self.assertTrue(any('aucune classe' in a['texte'] for a in m['alertes']))
        # Classe surchargée.
        _make_eleve_simple(self.etab, self.classe, 'Ba', 'Awa', suffix='s1')
        _make_eleve_simple(self.etab, self.classe, 'Ba', 'Moussa', sexe='M', suffix='s2')
        c = se.controle_classes(self.etab, self.annee)
        self.assertTrue(any('capacité' in a['texte'] for a in c['alertes']))

    def test_primaire(self):
        self._monter('primary', 'stp', 'primaire')
        self._pages()

    def test_superieur_module_et_semestres(self):
        self._monter('superieur', 'sts', 'superieur')
        module = Module.objects.create(nom='UE Analyse', code='UE1', etablissement=self.etab, actif=True)
        r = self.client.get(reverse('matiere:detail_module', args=[module.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Aucune matière dans ce module')
        self._pages()
        c = se.controle_classes(self.etab, self.annee)
        self.assertTrue(any('niveau LMD' in a['texte'] for a in c['alertes']))
        m = se.controle_matieres(self.etab, self.annee)
        self.assertTrue(any('hors module' in a['texte'] for a in m['alertes']))

    def test_periodes(self):
        self._monter('collège', 'stc', 'college')
        p = se.controle_periodes(self.etab, self.annee)
        self.assertTrue(any('Aucune période' in a['texte'] for a in p['alertes']))
        r = self.client.get(reverse('directeur:gestion_periodes_scolaires'))
        self.assertContains(r, 'Aucune période pour cette année')
        PeriodeScolaire.objects.create(etablissement=self.etab, nom_periode='1er Trimestre', type_periode='trimestre',
                                       date_debut=date(2026, 9, 1), date_fin=date(2026, 12, 20),
                                       annee_scolaire=self.annee.libelle, annee_scolaire_fk=self.annee, est_active=True)
        p = se.controle_periodes(self.etab, self.annee)
        self.assertFalse(any('Aucune période' in a['texte'] for a in p['alertes']))
        self.assertEqual(p['kpis'][0]['value'], 1)
