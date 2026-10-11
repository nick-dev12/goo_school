"""Pages de suivi des élèves (liste, scolarité, notes, présence, bulletins, préinscriptions, réinscriptions)."""
from django.test import TestCase
from django.urls import reverse

from school_admin.model.classe_model import Classe
from school_admin.services import suivi_eleves as se
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
)

PAGES = ('secretaire:liste_eleves', 'directeur:notes_et_resultats', 'directeur:suivi_presence',
         'directeur:bulletins_notes', 'directeur:liste_preinscriptions', 'directeur:gerer_liens_preinscription',
         'directeur:liste_reinscription', 'directeur:liste_comptabilite_eleves_directeur')


class SuiviElevesTests(TestCase):
    def _monter(self, type_etab, prefix, niveau):
        self.etab = _make_etablissement_type(type_etab, prefix)
        self.annee = _make_annee(self.etab)
        self.classe = Classe.objects.create(nom='Classe A', niveau=niveau, code_classe=f'SA-{self.etab.pk}',
                                            capacite_max=30, etablissement=self.etab, actif=True)
        self.client.force_login(self.etab)

    def _toutes_les_pages(self):
        for nom in PAGES:
            r = self.client.get(reverse(nom))
            self.assertIn(r.status_code, (200, 302), nom)
            if r.status_code == 200:
                self.assertContains(r, 'hb-head', msg_prefix=nom)

    def test_lycee(self):
        self._monter('lycée', 'sel', 'lycee')
        e1 = _make_eleve_simple(self.etab, self.classe, 'Ba', 'Awa', suffix='d1')
        _make_eleve_simple(self.etab, self.classe, 'Ba', 'Awa', suffix='d2')
        p = se.controle_preinscriptions(self.etab, self.annee)
        self.assertTrue(any('Aucun lien' in a['texte'] for a in p['alertes']))
        self._toutes_les_pages()
        c = se.controle_liste(self.etab, self.annee)
        self.assertTrue(any('doublon' in a['texte'] for a in c['alertes']))
        self.assertTrue(any('sans compte parent' in a['texte'] for a in c['alertes']))
        # Visiter la page des liens crée un lien actif : l'alerte disparaît.
        p = se.controle_preinscriptions(self.etab, self.annee)
        self.assertFalse(any('Aucun lien' in a['texte'] for a in p['alertes']))
        self.assertTrue(e1.pk)

    def test_primaire_et_superieur(self):
        for t, prefix, niveau in (('primary', 'sep', 'primaire'), ('superieur', 'ses', 'superieur')):
            self._monter(t, prefix, niveau)
            self._toutes_les_pages()
        r = self.client.get(reverse('secretaire:liste_eleves'))
        self.assertContains(r, 'Étudiants')
