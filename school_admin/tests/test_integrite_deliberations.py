"""Non-regression : aucun admis faute de donnees, et aucune cloture sur moyennes perimees."""
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from school_admin import tests_deliberations as fixtures
from school_admin.services import deliberations as svc, examens
from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.module_model import ModuleClasse
from school_admin.model.deliberation_model import Deliberation, DecisionJury
from school_admin.model.ponderation_model import Ponderation

class IntegriteJuryTests(fixtures.BaseDelib):
    def controle(self):
        return svc.controle_resultats(self.classe,[self.s1],self.annee)

    def test_vide_n_est_jamais_admis(self):
        self.assertEqual(examens.validation_lmd([],self.regle)['decision'],'Incomplet')
        self.assertFalse(self.controle()['pret'])
        with self.assertRaises(svc.DeliberationErreur):
            self.deliberation(self.s1)
        self.assertFalse(Deliberation.objects.exists())

    def test_moyenne_absente_reste_dans_programme_attendu(self):
        self.notes(self.awa,self.s1,[12,13,14])
        MoyennePeriode.objects.filter(eleve=self.awa,periode=self.s1,est_moyenne_generale=False).exclude(
            matiere=self.ecs[(self.s1.pk,0)]).delete()
        lignes=svc.lignes_eleve(self.awa,self.classe,[self.s1],self.annee)[self.s1.pk]
        self.assertEqual(sum(x['credits'] for x in lignes),Decimal('30'))
        self.assertEqual(sum(x['moyenne'] is None for x in lignes),2)
        self.assertFalse(self.controle()['pret'])

    def test_zero_reel_est_complet(self):
        self.notes(self.awa,self.s1,[0,0,0])
        self.assertTrue(self.controle()['pret'])
        self.assertEqual(self.deliberation(self.s1).decisions.get().decision,DecisionJury.AJOURNE)

    def test_programme_absent_bloque(self):
        ModuleClasse.objects.filter(classe=self.classe,periode=self.s1).delete()
        self.notes(self.awa,self.s1,[12,13,14])
        self.assertFalse(self.controle()['pret'])

    def test_ancienne_moyenne_sans_empreinte_doit_etre_recalculee(self):
        self.notes(self.awa,self.s1,[12,13,14])
        MoyennePeriode.objects.filter(eleve=self.awa,est_moyenne_generale=False).update(empreinte_sources='')
        self.assertEqual(self.controle()['perimes'],3)

    def test_anciennes_moyennes_un_seul_message_clair(self):
        """Après la migration 0256 : un message groupé, pas une ligne par étudiant et par matière."""
        moussa = self._etudiant('Diallo', 'Moussa', 'm')
        self.notes(self.awa,self.s1,[12,13,14])
        self.notes(moussa,self.s1,[11,12,13])
        MoyennePeriode.objects.filter(est_moyenne_generale=False).update(empreinte_sources='')
        c = self.controle()
        self.assertFalse(c['pret'])
        self.assertEqual(c['perimes'], 6)
        self.assertEqual(len(c['problemes']), 1)
        self.assertIn('Semestre 1 (6)', c['problemes'][0])
        self.assertIn('aucune note n’est perdue', c['problemes'][0])
        with self.assertRaises(svc.DeliberationErreur) as err:
            self.deliberation(self.s1)
        self.assertIn('Relancez une fois le calcul', str(err.exception))

    def test_pondere_changement_detecte_sans_signal(self):
        self.notes(self.awa,self.s1,[12,13,14])
        self.assertTrue(self.controle()['pret'])
        Ponderation.objects.filter(etablissement=self.etab).update(poids_classe=50,poids_examen=50)
        self.assertFalse(self.controle()['pret'])

    def test_programme_modifie_invalide_les_moyennes(self):
        self.notes(self.awa,self.s1,[12,13,14])
        ModuleClasse.objects.filter(classe=self.classe,periode=self.s1).update(credits=Decimal('12'))
        self.assertFalse(self.controle()['pret'])

    def test_tamper_moyenne_sans_recalcul_detecte(self):
        self.notes(self.awa,self.s1,[12,13,14])
        MoyennePeriode.objects.filter(eleve=self.awa,matiere=self.ecs[(self.s1.pk,0)]).update(moyenne_matiere=20)
        self.assertEqual(self.controle()['perimes'],1)

    def test_sauver_rang_ne_valide_pas_moyennes_perimees(self):
        self.notes(self.awa,self.s1,[12,13,14])
        r=MoyennePeriode.objects.filter(eleve=self.awa,est_moyenne_generale=False).first()
        avant=r.empreinte_sources
        Ponderation.objects.filter(etablissement=self.etab).update(poids_classe=50)
        r.rang=1; r.save(update_fields=['rang'])
        r.refresh_from_db()
        self.assertEqual(r.empreinte_sources,avant)
        self.assertFalse(self.controle()['pret'])

    def test_cloture_reverifie_les_resultats(self):
        self.notes(self.awa,self.s1,[12,13,14])
        d=self.deliberation(self.s1); d.president='Jury'; d.save()
        MoyennePeriode.objects.filter(eleve=self.awa,est_moyenne_generale=False).delete()
        with self.assertRaises(svc.DeliberationErreur):
            svc.cloturer(d)
        d.refresh_from_db(); self.assertFalse(d.est_cloturee)

    def test_post_ouverture_incomplete_affiche_erreur_sans_creer(self):
        self.client.force_login(self.etab)
        response=self.client.post(reverse('directeur:liste_deliberations'),
          {'classe_id':self.classe.pk,'periode_id':self.s1.pk,'portee':'semestre'},follow=True)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Résultats non prêts')
        self.assertFalse(Deliberation.objects.exists())

    def test_semestre_d_autre_niveau_refuse(self):
        self.notes(self.awa,self.s1,[12,13,14])
        self.s1.niveau_lmd='L3'; self.s1.nom_periode='Semestre 5'; self.s1.save()
        self.assertFalse(self.controle()['pret'])

    def test_note_modifiee_apres_calcul_invalide_et_suppression_aussi(self):
        from school_admin.model.evaluation_model import Evaluation, Note
        from school_admin.model.professeur_model import Professeur
        from datetime import date
        m=self.ecs[(self.s1.pk,0)]
        prof=Professeur.objects.create(nom='Test',prenom='Enseignant',username='jury.note',
            email='jury.note@test.local',numero_employe='JURY01',etablissement=self.etab,matiere_principale=m)
        evaluation=Evaluation.objects.create(titre='Devoir',classe=self.classe,matiere=m,professeur=prof,
            date_evaluation=date(2026,11,1),periode_scolaire=self.s1,annee_scolaire=self.annee)
        n=Note.objects.create(eleve=self.awa,evaluation=evaluation,matiere=m,note=12,annee_scolaire=self.annee)
        self.notes(self.awa,self.s1,[12,13,14])
        self.assertTrue(self.controle()['pret'])
        Note.objects.filter(pk=n.pk).update(note=8)
        self.assertEqual(self.controle()['perimes'],1)
        self.notes(self.awa,self.s1,[8,13,14])
        n.delete()
        self.assertEqual(self.controle()['perimes'],1)

    def test_annuel_refuse_semestre_manquant(self):
        self.notes(self.awa,self.s1,[12,13,14])
        self.s2.delete()
        with self.assertRaises(svc.DeliberationErreur):
            self.deliberation()

    def test_inventaire_sans_ecriture(self):
        from django.core.management import call_command
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from io import StringIO
        out=StringIO()
        with CaptureQueriesContext(connection) as queries:
            call_command('auditer_integrite_examens',etablissement=self.etab.pk,stdout=out)
        self.assertIn('Aucune correction automatique',out.getvalue())
        writes=[q['sql'] for q in queries if q['sql'].lstrip().upper().startswith(('INSERT','UPDATE','DELETE'))]
        self.assertEqual(writes,[])
