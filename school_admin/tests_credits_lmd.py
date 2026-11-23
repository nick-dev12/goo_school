"""Supérieur (LMD) : crédits d'une matière dans une UE commune à plusieurs classes et filières."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from school_admin.model.academic_structure_model import Department
from school_admin.model.classe_model import Classe
from school_admin.model.matiere_model import Matiere
from school_admin.model.module_model import Module, ModuleClasse
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.services import credits_lmd
from school_admin.services import maquette as mq
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement_type

D = Decimal


class UeMutualiseeTests(TestCase):
    """Une UE « Langues » commune à L1 Droit (6 crédits) et L1 Économie (3 crédits), deux cours de poids 4 et 2."""

    def setUp(self):
        self.etab = _make_etablissement_type('superieur', 'cr')
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.droit = Department.objects.create(nom='Droit', sigle='DRT', etablissement=self.etab)
        self.eco = Department.objects.create(nom='Économie', sigle='ECO', etablissement=self.etab)
        self.l1_droit = Classe.objects.create(nom='L1 Droit', niveau='superieur', niveau_lmd='L1',
                                              code_classe=f'L1D-{s}', capacite_max=80, etablissement=self.etab,
                                              department=self.droit)
        self.l1_eco = Classe.objects.create(nom='L1 Éco', niveau='superieur', niveau_lmd='L1', code_classe=f'L1E-{s}',
                                            capacite_max=80, etablissement=self.etab, department=self.eco)
        self.s1 = PeriodeScolaire.objects.create(
            etablissement=self.etab, nom_periode='Semestre 1', type_periode='semestre', niveau_lmd='L1',
            date_debut=date(2026, 10, 5), date_fin=date(2027, 1, 24), annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee, est_active=True)
        self.ue = Module.objects.create(nom='Langues', code=f'LANG-{s}', etablissement=self.etab, niveau_lmd='L1')
        self.ue.departments.add(self.droit, self.eco)
        self.mc_droit = ModuleClasse.objects.create(module=self.ue, classe=self.l1_droit, credits=D('6'),
                                                    periode=self.s1)
        self.mc_eco = ModuleClasse.objects.create(module=self.ue, classe=self.l1_eco, credits=D('3'), periode=self.s1)
        self.anglais = Matiere.objects.create(nom='Anglais', etablissement=self.etab, module=self.ue,
                                              niveau='superieur', coefficient=1, credits=D('4'), volume_cm=20)
        self.redaction = Matiere.objects.create(nom='Rédaction', etablissement=self.etab, module=self.ue,
                                                niveau='superieur', coefficient=1, credits=D('2'), volume_cm=10)
        for m in (self.anglais, self.redaction):
            m.classes.add(self.l1_droit, self.l1_eco)

    def test_credits_repartis_selon_la_classe(self):
        self.assertEqual(credits_lmd.credits_ec(self.anglais, self.l1_droit), D('4'))
        self.assertEqual(credits_lmd.credits_ec(self.redaction, self.l1_droit), D('2'))
        self.assertEqual(credits_lmd.credits_ec(self.anglais, self.l1_eco), D('2'))
        self.assertEqual(credits_lmd.credits_ec(self.redaction, self.l1_eco), D('1'))

    def test_la_somme_fait_toujours_les_credits_de_l_ue(self):
        ModuleClasse.objects.filter(pk=self.mc_eco.pk).update(credits=D('5'))  # 5 × 4/6 n'est pas rond
        ecs = credits_lmd.matieres_de_ue(self.ue.pk, self.l1_eco)
        self.assertEqual(sum(credits_lmd.repartir(D('5'), ecs).values()), D('5'))

    def test_sans_poids_repartition_egale(self):
        Matiere.objects.filter(module=self.ue).update(credits=None)
        self.assertEqual(credits_lmd.credits_ec(self.anglais, self.l1_eco), D('1.5'))

    def test_classe_hors_ue(self):
        autre = Classe.objects.create(nom='L2 Droit', niveau='superieur', niveau_lmd='L2', code_classe='L2D-x',
                                      capacite_max=80, etablissement=self.etab, department=self.droit)
        self.assertIsNone(credits_lmd.credits_ec(self.anglais, autre))

    def test_bulletin_utilise_les_credits_de_la_classe(self):
        from school_admin.personal_views.directeur_view import _coef_et_credits_ec_superieur
        self.assertEqual(_coef_et_credits_ec_superieur(self.anglais, self.etab, self.l1_eco)[1], D('2'))
        self.assertEqual(_coef_et_credits_ec_superieur(self.anglais, self.etab, self.l1_droit)[1], D('4'))

    def test_maquette_par_classe_sans_fausse_alerte(self):
        semestre = mq.maquette_classe(self.l1_eco, [self.s1])[0]
        lignes = {l['matiere'].pk: l['credits'] for l in semestre['ues'][0]['ecs']}
        self.assertEqual((lignes[self.anglais.pk], lignes[self.redaction.pk]), (D('2'), D('1')))
        self.assertFalse(any('crédits pour l\'UE' in c for c in semestre['controles']))

    def test_filieres_d_une_matiere_commune(self):
        self.assertEqual([f.nom for f in self.anglais.filieres], ['Droit', 'Économie'])
        self.anglais.classes.set([self.l1_droit])
        self.assertEqual([f.nom for f in self.anglais.filieres], ['Droit'])

    def test_creation_dans_un_module_commun_prend_la_filiere_unique(self):
        from school_admin.controllers.matiere_controller import _filiere_unique
        self.assertIsNone(_filiere_unique(self.ue))  # deux filières
        ModuleClasse.objects.filter(pk=self.mc_eco.pk).delete()
        self.assertEqual(_filiere_unique(self.ue), self.droit)

    def test_pages_matiere_et_module_affichent_les_credits_par_classe(self):
        from django.urls import reverse
        self.client.force_login(self.etab)
        page = self.client.get(reverse('matiere:detail_matiere', args=[self.anglais.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Crédits de ce cours')
        self.assertContains(page, 'L1 Éco')
        self.assertContains(page, 'Économie')  # filières de la matière commune
        page = self.client.get(reverse('matiere:detail_module', args=[self.ue.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'crédits dans cette classe')

    def test_creation_d_une_matiere_avec_son_poids(self):
        from django.urls import reverse
        self.client.force_login(self.etab)
        url = reverse('matiere:detail_module', args=[self.ue.pk])
        donnees = {'action': 'creer_matiere_hybride', 'nom_matiere': 'Expression orale', 'niveau_key': 'L1',
                   'filiere_scope': 'single', 'department_id': self.droit.pk, 'choix_classes_matiere': '1',
                   'classes_matiere': [self.l1_droit.pk], f'coef_dep_{self.droit.pk}': '1'}
        self.assertContains(self.client.post(url, {**donnees, 'poids_matiere': 'abc'}), 'Le poids doit être')
        self.assertFalse(Matiere.objects.filter(nom='Expression orale').exists())
        self.assertRedirects(self.client.post(url, {**donnees, 'poids_matiere': '2'}), url)
        cours = Matiere.objects.get(nom='Expression orale')
        self.assertEqual(cours.credits, D('2'))
        # Poids 4 + 2 + 2 dans une UE de 6 crédits en L1 Droit : 3 + 1,5 + 1,5.
        self.assertEqual(credits_lmd.credits_ec(cours, self.l1_droit), D('1.5'))

    def test_indicateur_credits_de_la_page_matiere(self):
        from school_admin.services.structure_etablissement import controle_matiere
        indicateur = controle_matiere(self.anglais)['kpis'][2]
        self.assertEqual((indicateur['label'], indicateur['value']), ('Crédits', '2 à 4'))
        self.anglais.classes.set([self.l1_eco])
        self.assertEqual(controle_matiere(self.anglais)['kpis'][2]['value'], '2')


class LiaisonsUeMutualiseeTests(UeMutualiseeTests):
    """Audit : affectations, fiche de la classe et bulletin suivent la même règle que les crédits."""

    def test_matiere_commune_proposee_a_l_affectation(self):
        from django.urls import reverse
        from school_admin.model.professeur_model import Professeur
        Professeur.objects.create(username=f'prof-cr-{self.etab.pk}', numero_employe=f'CR-{self.etab.pk}', nom='Diop',
                                  prenom='Fatou', etablissement=self.etab, niveau_enseignement='superieur',
                                  matiere_principale=self.anglais)
        self.client.force_login(self.etab)
        page = self.client.get(reverse('affectation:affectation_professeurs'))
        self.assertEqual(page.status_code, 200)
        # Onglet de la matière commune (sans filière unique) et filtre par filière qui la garde pour les deux.
        self.assertContains(page, f'data-matiere="{self.anglais.pk}"')
        self.assertContains(page, f'data-department-ids="{self.droit.pk},{self.eco.pk}"')

    def test_fiche_classe_et_indicateurs_limites_a_la_classe(self):
        from django.urls import reverse
        from school_admin.services.structure_etablissement import controle_classe
        autre = Matiere.objects.create(nom='Histoire du droit', etablissement=self.etab, niveau='superieur',
                                       coefficient=1)  # hors de toute UE de la classe
        heritee = Matiere.objects.create(nom='Lecture guidée', etablissement=self.etab, module=self.ue,
                                         niveau='superieur', coefficient=1)  # sans classes : celles de l'UE
        self.client.force_login(self.etab)
        page = self.client.get(reverse('administrateur_etablissement:detail_classe', args=[self.l1_droit.pk]))
        self.assertEqual(page.status_code, 200)
        noms = [m.nom for m in page.context['matieres_classe']]
        self.assertIn('Lecture guidée', noms)
        self.assertIn('Anglais', noms)
        self.assertNotIn(autre.nom, noms)
        controle = controle_classe(self.l1_droit, self.annee)
        self.assertFalse(any('non rattachée' in a['texte'] for a in controle['alertes']))
        self.assertTrue(heritee.pk)

    def test_bulletin_affiche_les_credits_actuels(self):
        from school_admin.model.moyenne_periode_model import MoyennePeriode
        from school_admin.personal_views.directeur_view import _matieres_table_superieur_depuis_moyennes_periode
        from school_admin.tests.test_assistant_directeur_tools import _make_eleve_simple
        eleve = _make_eleve_simple(self.etab, self.l1_eco, 'Sow', 'Ami', 'F', f'cr{self.etab.pk}')
        # Crédits enregistrés avant un changement de réglage : le bulletin affiche la valeur actuelle.
        MoyennePeriode.objects.create(eleve=eleve, etablissement=self.etab, periode=self.s1, matiere=self.anglais,
                                      est_moyenne_generale=False, moyenne_matiere=D('12'), coefficient=1,
                                      credits=D('4'), annee_scolaire=self.annee)
        table = _matieres_table_superieur_depuis_moyennes_periode(eleve, self.l1_eco, self.s1, self.etab, self.annee)
        self.assertEqual([(l['nom'], l['credits']) for l in table], [('Anglais', 2.0)])

    def _moyenne_enregistree(self, credits):
        from school_admin.model.moyenne_periode_model import MoyennePeriode
        from school_admin.tests.test_assistant_directeur_tools import _make_eleve_simple
        eleve = _make_eleve_simple(self.etab, self.l1_eco, 'Fall', 'Binta', 'F', f'mp{self.etab.pk}')
        return eleve, MoyennePeriode.objects.create(
            eleve=eleve, etablissement=self.etab, periode=self.s1, matiere=self.anglais, est_moyenne_generale=False,
            moyenne_matiere=D('12'), coefficient=1, credits=credits, annee_scolaire=self.annee)

    def test_credits_enregistres_suivent_les_reglages(self):
        _, mp = self._moyenne_enregistree(D('2'))
        self.mc_eco.credits = D('9')  # UE à 9 crédits en L1 Éco : Anglais (poids 4 sur 6) → 6
        self.mc_eco.save()
        mp.refresh_from_db()
        self.assertEqual(mp.credits, D('6'))
        self.redaction.credits = D('4')  # poids 4 et 4 → partage égal : 4,5
        self.redaction.save()
        mp.refresh_from_db()
        self.assertEqual(mp.credits, D('4.5'))

    def test_deliberation_close_signale_les_credits_modifies(self):
        from django.urls import reverse
        from school_admin.model.deliberation_model import DecisionJury, Deliberation
        from school_admin.services import deliberations as svc
        eleve, _ = self._moyenne_enregistree(D('2'))
        d = Deliberation.objects.create(etablissement=self.etab, classe=self.l1_eco, annee_scolaire=self.annee,
                                        periode=self.s1, statut=Deliberation.STATUT_CLOTUREE)
        DecisionJury.objects.create(deliberation=d, eleve=eleve, detail_ues=[
            {'titre': 'Langues', 'moyenne': '12', 'credits': '3', 'acquise': True, 'mode': 'acquise',
             'module_id': self.ue.pk}])
        self.assertEqual(svc.ecarts_credits(d), [])
        self.mc_eco.credits = D('5')
        self.mc_eco.save()
        self.assertEqual(svc.ecarts_credits(d), [{'module': 'Langues', 'avant': D('3'), 'maintenant': D('5')}])
        self.client.force_login(self.etab)
        page = self.client.get(reverse('directeur:detail_deliberation', args=[d.pk]))
        self.assertContains(page, 'Crédits modifiés depuis la clôture')

    def test_assistant_distingue_poids_et_credits(self):
        from types import SimpleNamespace
        from school_admin.services.assistant_pedagogie import tool_coefficients as tool_matieres
        ctx = SimpleNamespace(etablissement=self.etab, est_superieur=True, est_lycee=False, est_college_lycee=False)
        item = next(i for i in tool_matieres(ctx, {'query': 'Anglais'})['matieres'] if i['nom'] == 'Anglais')
        self.assertEqual(item['poids_dans_le_module'], 4.0)
        self.assertEqual({c['classe']: c['credits'] for c in item['credits_par_classe']},
                         {'L1 Droit': 4.0, 'L1 Éco': 2.0})


class AssistantStructureTests(TestCase):
    """L'assistant IA agit sur filières, classes, modules (UE) et matières (EC) avec les règles des écrans."""

    setUp = UeMutualiseeTests.setUp

    def _agir(self, action, args):
        from school_admin.services.assistant_actions import ACTION_SPECS
        from school_admin.services.assistant_tools import build_assistant_context
        self.ctx = build_assistant_context(self.etab)
        spec = ACTION_SPECS[action]
        brouillon = spec.prepare(self.ctx, args)
        if brouillon.get('statut') != 'en_attente_confirmation':
            return brouillon
        return spec.apply(self.ctx, brouillon)

    def test_creer_une_classe_du_superieur_demande_filiere_et_niveau(self):
        reponse = self._agir('creer_classe', {'nom': 'L2 Droit'})
        self.assertEqual(reponse['manquants'], ['filiere'])
        reponse = self._agir('creer_classe', {'nom': 'L2 Droit', 'filiere': 'Droit'})
        self.assertEqual(reponse['manquants'], ['niveau_lmd'])
        reponse = self._agir('creer_classe', {'nom': 'L2 Droit', 'filiere': 'Droit', 'niveau_lmd': 'L2'})
        self.assertEqual(reponse['statut'], 'ok', reponse)
        classe = Classe.objects.get(etablissement=self.etab, nom='L2 Droit')
        self.assertEqual((classe.department, classe.niveau_lmd, classe.niveau), (self.droit, 'L2', 'superieur'))

    def test_creer_une_matiere_dans_un_module(self):
        self.assertEqual(self._agir('creer_matiere', {'nom': 'Oral'})['manquants'], ['module'])
        reponse = self._agir('creer_matiere', {'nom': 'Oral', 'module': 'Langues', 'classes': 'L1 Éco',
                                               'coefficient': '2', 'poids': '2'})
        self.assertEqual(reponse['statut'], 'ok', reponse)
        oral = Matiere.objects.get(nom='Oral')
        self.assertEqual((oral.module, oral.department, oral.coefficient, oral.credits),
                         (self.ue, self.eco, D('2'), D('2')))
        self.assertEqual(list(oral.classes.all()), [self.l1_eco])
        # Poids 4 + 2 + 2 dans une UE de 3 crédits en L1 Éco : 1,5 + 0,75 + 0,75.
        self.assertEqual(credits_lmd.credits_ec(oral, self.l1_eco), D('0.75'))
        # Sans classe précisée : toutes les classes du module, matière commune aux deux filières.
        self._agir('creer_matiere', {'nom': 'Lecture', 'module': 'Langues'})
        lecture = Matiere.objects.get(nom='Lecture')
        self.assertIsNone(lecture.department_id)
        self.assertEqual(set(lecture.classes.all()), {self.l1_droit, self.l1_eco})
        self.assertIsNone(lecture.credits)

    def test_matiere_refusee_pour_une_classe_hors_du_module(self):
        autre = Classe.objects.create(nom='L2 Éco', niveau='superieur', niveau_lmd='L2', code_classe='L2E-x',
                                      capacite_max=80, etablissement=self.etab, department=self.eco)
        reponse = self._agir('creer_matiere', {'nom': 'Oral', 'module': 'Langues', 'classes': autre.nom})
        self.assertIn('ne suit pas le module (UE)', reponse['erreur'])

    def test_modifier_une_matiere(self):
        reponse = self._agir('modifier_matiere', {'query': 'Anglais', 'poids': '2', 'heures_td': '12'})
        self.assertEqual(reponse['statut'], 'ok', reponse)
        self.anglais.refresh_from_db()
        self.assertEqual((self.anglais.credits, self.anglais.volume_td), (D('2'), 12))
        self.assertEqual(credits_lmd.credits_ec(self.anglais, self.l1_droit), D('3'))  # 6 × 2/4

    def test_creer_et_rattacher_un_module(self):
        reponse = self._agir('creer_module', {'nom': 'Méthodes', 'classes': 'L1 Droit, L1 Éco', 'credits': '4',
                                              'periode': 'Semestre 1'})
        self.assertEqual(reponse['statut'], 'ok', reponse)
        module = Module.objects.get(nom='Méthodes')
        self.assertEqual({(mc.classe, mc.credits, mc.periode) for mc in module.module_classes.all()},
                         {(self.l1_droit, D('4'), self.s1), (self.l1_eco, D('4'), self.s1)})
        self.assertEqual({d.nom for d in module.get_linked_departments()}, {'Droit', 'Économie'})
        # Mise à jour des crédits sans préciser le semestre : le semestre est conservé.
        self._agir('affecter_module_classe', {'module': 'Méthodes', 'classe': 'L1 Droit', 'credits': '5'})
        lien = ModuleClasse.objects.get(module=module, classe=self.l1_droit)
        self.assertEqual((lien.credits, lien.periode), (D('5'), self.s1))
        reponse = self._agir('retirer_module_classe', {'module': 'Méthodes', 'classe': 'L1 Droit'})
        self.assertEqual(reponse['statut'], 'ok', reponse)
        self.assertFalse(ModuleClasse.objects.filter(module=module, classe=self.l1_droit).exists())

    def test_affecter_un_enseignant_a_la_matiere_de_la_classe(self):
        from school_admin.model.affectation_model import AffectationProfesseur
        from school_admin.model.professeur_model import Professeur
        # Homonyme d'une autre classe : l'assistant doit retenir l'Anglais suivi par L1 Éco.
        autre_classe = Classe.objects.create(nom='M1 Droit', niveau='superieur', niveau_lmd='M1', code_classe='M1D-x',
                                             capacite_max=80, etablissement=self.etab, department=self.droit)
        homonyme = Matiere.objects.create(nom='Anglais', etablissement=self.etab, niveau='superieur', coefficient=1,
                                           department=self.droit)
        homonyme.classes.add(autre_classe)
        prof = Professeur.objects.create(username=f'prof-st-{self.etab.pk}', numero_employe=f'ST-{self.etab.pk}',
                                         nom='Ba', prenom='Ousmane', etablissement=self.etab,
                                         niveau_enseignement='superieur', matiere_principale=homonyme)
        reponse = self._agir('affecter_professeur', {'professeur': 'Ba', 'classe': 'L1 Éco', 'matiere': 'Anglais'})
        self.assertIn('Ajoutez-la d’abord à sa fiche', reponse['erreur'])
        prof.matieres_secondaires.add(self.anglais)
        reponse = self._agir('affecter_professeur', {'professeur': 'Ba', 'classe': 'L1 Éco', 'matiere': 'Anglais'})
        self.assertEqual(reponse['statut'], 'ok', reponse)
        aff = AffectationProfesseur.objects.get(professeur=prof, classe=self.l1_eco)
        self.assertEqual(aff.matiere, self.anglais)
        reponse = self._agir('affecter_professeur', {'professeur': 'Ba', 'classe': 'L1 Éco', 'matiere': 'Chimie'})
        self.assertNotEqual(reponse.get('statut'), 'ok')

    def test_lecture_des_modules_d_une_classe(self):
        from school_admin.services.assistant_tools import build_assistant_context, execute_tool
        ctx = build_assistant_context(self.etab)
        modules = execute_tool(ctx, 'get_modules_classe', {'classe': 'L1 Éco'})
        matieres = {m['nom']: m['credits_dans_la_classe'] for m in modules['modules'][0]['matieres']}
        self.assertEqual(matieres, {'Anglais': 2.0, 'Rédaction': 1.0})
        structure = execute_tool(ctx, 'get_structure_superieur', {'query': 'Langues'})
        self.assertEqual({c['classe']: c['credits'] for c in structure['modules'][0]['credits_par_classe']},
                         {'L1 Droit': 6.0, 'L1 Éco': 3.0})
