"""Parcours de toutes les pages (GET) pour les établissements primaire, collège, lycée, collège + lycée et mixte.

Chaque type reçoit un jeu de données complet (classes, enseignants, élèves, parent, notes, emploi du temps) puis
toutes les routes sont ouvertes avec le compte concerné : aucune ne doit répondre par une erreur serveur.
"""
import traceback
from datetime import date, time
from decimal import Decimal as D
from unittest.mock import patch

from django.db import NotSupportedError
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver, reverse, NoReverseMatch

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from school_admin.model.classe_model import Classe
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
from school_admin.model.evaluation_model import Evaluation, Note
from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.matiere_model import Matiere
from school_admin.model.note_primaire_model import NotePrimaire
from school_admin.model.parent_model import Parent
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.model.professeur_model import Professeur
from school_admin.utils.permissions_personnel import PERMISSIONS_DISPONIBLES, get_permissions_par_fonction
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee, _make_eleve_simple, _make_etablissement_type, _make_inscription)

MDP = 'Smoke@Test1!'

# Routes exclues : déconnexion, effets de bord destructifs, services externes, exports lourds.
EXCLUS = ('logout', 'deconnexion', 'supprimer', 'delete', 'desactiver', 'annuler', 'reset', 'vider', 'fcm',
          'assistant', 'tts', 'gemini', 'test_', 'sync_', 'service_worker', 'firebase', 'manifest', 'robots',
          'sitemap', 'offline', 'commercial', 'prospect', 'administrateur_', 'stream', 'sse', 'realtime')

NAMESPACES_DIRECTION = {'directeur', 'administrateur_etablissement', 'matiere', 'affectation', 'salle',
                        'affectation_salle', 'secretaire', 'personnel', 'personnel_administratif'}

# niveau de classe -> (nom, niveau du professeur)
CLASSES = {
    'primary': [('CM2 A', 'primaire'), ('CE1 A', 'primaire')],
    'collège': [('3ème A', 'college'), ('6ème A', 'college')],
    'lycée': [('Tle S1', 'lycee'), ('2nde L', 'lycee')],
    'collège_lycée': [('4ème A', 'college'), ('1ère S', 'lycee')],
    'mixte': [('CM1 A', 'primaire'), ('5ème A', 'college'), ('Tle L', 'lycee')],
}


def _routes():
    """(namespace, nom, motif) pour chaque route nommée de premier niveau."""
    out = []

    def walk(patterns, ns, prefix):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, p.namespace or ns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern) and p.name:
                out.append((ns, p.name, prefix + str(p.pattern)))

    walk(get_resolver().url_patterns, None, '')
    return out


class SmokePrimaireSecondaire(TestCase):
    maxDiff = None

    def _peupler(self, type_etab):
        etab = _make_etablissement_type(type_etab, 'smk')
        annee = _make_annee(etab)
        s = str(etab.pk)
        periode = PeriodeScolaire.objects.create(
            etablissement=etab, nom_periode='Trimestre 1', type_periode='trimestre', date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 20), annee_scolaire=annee.libelle, annee_scolaire_fk=annee, est_active=True)
        maths = Matiere.objects.create(nom='Mathématiques', etablissement=etab, coefficient=4)
        francais = Matiere.objects.create(nom='Français', etablissement=etab, coefficient=3)
        d = {'etab': etab, 'annee': annee, 'periode': periode, 'matiere': maths, 'classes': [], 'eleves': [],
             'profs': {}}
        with patch('school_admin.model.etablissement_model.Etablissement.recalculer_facturation', return_value=None):
            for i, (nom, niveau) in enumerate(CLASSES[type_etab]):
                c = Classe.objects.create(nom=nom, niveau=niveau, code_classe=f'S{i}-{s}', capacite_max=40,
                                          etablissement=etab, actif=True)
                maths.classes.add(c)
                francais.classes.add(c)
                d['classes'].append(c)
                prof = d['profs'].get(niveau)
                if prof is None:
                    prof = Professeur.objects.create_user(
                        username=f'p{niveau[:3]}.{s}', email=f'p{niveau[:3]}.{s}@t.local', password=MDP,
                        nom='Sarr', prenom='Moussa', telephone=f'77{i}{s}'[:12], numero_employe=f'E{i}{s}',
                        matiere_principale=maths, etablissement=etab, niveau_enseignement=niveau, actif=True)
                    prof.matieres_secondaires.add(francais)
                    d['profs'][niveau] = prof
                if type_etab == 'primary':
                    aff = AffectationProfesseurPrimaire.objects.create(professeur=prof, classe=c, annee_scolaire=annee)
                    aff.matieres.add(maths, francais)
                else:
                    AffectationProfesseur.objects.create(professeur=prof, classe=c, matiere=maths, annee_scolaire=annee)
                    AffectationProfesseur.objects.create(professeur=prof, classe=c, matiere=francais,
                                                         annee_scolaire=annee)
                eleve = _make_eleve_simple(etab, c, 'Diallo', f'Eleve{i}', 'F', f'{i}{s}')
                eleve.set_password(MDP)
                eleve.save()
                _make_inscription(eleve, c, annee, etab)
                d['eleves'].append(eleve)
                if type_etab == 'primary':
                    ev = EvaluationPrimaire.objects.create(titre='Dictée', matiere=francais, classe=c, professeur=prof,
                                                           date_evaluation=date(2026, 10, 5), bareme=10,
                                                           periode_scolaire=periode, annee_scolaire=annee)
                    NotePrimaire.objects.create(eleve=eleve, evaluation_primaire=ev, annee_scolaire=annee, note=D('7'))
                else:
                    ev = Evaluation.objects.create(titre='Devoir 1', classe=c, professeur=prof, matiere=maths,
                                                   date_evaluation=date(2026, 10, 5), periode_scolaire=periode,
                                                   annee_scolaire=annee)
                    Note.objects.create(eleve=eleve, evaluation=ev, matiere=maths, note=D('13.5'))
                    d['evaluation'] = ev
                edt = EmploiDuTemps.objects.create(classe=c, annee_scolaire=annee.libelle, annee_scolaire_fk=annee,
                                                   est_actif=True)
                CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='lundi', heure_debut=time(8),
                                                    heure_fin=time(10), matiere=maths)
                d['emploi'] = edt
            parent = Parent(username=f'par.{s}', email=f'par.{s}@t.local', nom='Diallo', prenom='Mamadou',
                            telephone=f'76{s}'[:12], matricule_parental=f'PAR{s}', type_parent='pere',
                            etablissement=etab)
            parent.set_password(MDP)
            parent.save()
            for e in d['eleves']:
                LienFamilial.objects.create(parent=parent, eleve=e, type_lien='pere', statut='valide', actif=True)
            d['parent'] = parent
            d['personnel'] = []
            toutes = {k: True for k in PERMISSIONS_DISPONIBLES}
            for fonction, perms in (('secretaire', toutes), ('comptable', None), ('surveillant_general', None)):
                p = PersonnelAdministratif(username=f'{fonction[:4]}.{s}', email=f'{fonction[:4]}.{s}@t.local',
                                           nom='Ba', prenom='Ndeye', telephone=f'75{s}'[:12], fonction=fonction,
                                           etablissement=etab, actif=True,
                                           permissions=perms if perms is not None else
                                           {k: True for k in get_permissions_par_fonction(fonction)})
                p.set_password(MDP)
                p.save()
                d['personnel'].append(p)
        return d

    def _args(self, motif, d, role):
        """Valeurs des paramètres d'URL à partir du jeu de données ; None si un paramètre est inconnu."""
        import re

        classe = d['classes'][0]
        eleve = d['eleves'][0]
        prof = d['profs'].get(classe.niveau) or next(iter(d['profs'].values()))
        valeurs = {
            'classe_id': classe.id, 'eleve_id': eleve.id, 'etablissement_id': d['etab'].id,
            'professeur_id': prof.id, 'annee_id': d['annee'].id, 'matiere_id': d['matiere'].id,
            'periode_id': d['periode'].id, 'evaluation_id': (d['evaluation'].id if d.get('evaluation') else 0),
            'emploi_id': d['emploi'].id, 'matricule': eleve.matricule_eleve or eleve.numero_eleve,
            'mois_numero': 10, 'mois_annee': 2026, 'user_type': role,
        }
        noms = re.findall(r'<(?:\w+:)?(\w+)>', motif)
        if any(n not in valeurs for n in noms):
            return None
        return {n: valeurs[n] for n in noms}

    def _crawl(self, d, ns_ok, client, role):
        erreurs = []
        for ns, nom, motif in _routes():
            if ns not in ns_ok or any(x in nom.lower() for x in EXCLUS) or 'api' in motif:
                continue
            kwargs = self._args(motif, d, role)
            if kwargs is None:
                continue
            try:
                url = reverse(f'{ns}:{nom}', kwargs=kwargs)
            except NoReverseMatch:
                continue
            try:
                r = client.get(url)
                if r.status_code >= 500:
                    erreurs.append(f'{role} {url} -> {r.status_code}')
            except NotSupportedError:
                continue  # recherche dans un JSONField : PostgreSQL en production, pas SQLite
            except Exception as exc:  # noqa: BLE001
                tb = traceback.extract_tb(exc.__traceback__)
                lieu = next((f'{f.filename.split("goo_school")[-1]}:{f.lineno}' for f in reversed(tb)
                             if 'school_admin' in f.filename), '?')
                erreurs.append(f'{role} {url} -> {type(exc).__name__}: {str(exc)[:160]} @ {lieu}')
        return erreurs

    def _connecter(self, user, user_type):
        self.client.logout()
        self.client.force_login(user, backend='school_admin.authentication_backends.MultiUserBackend')
        session = self.client.session
        session['_auth_user_type'] = user_type
        session.save()

    def _audit(self, type_etab):
        d = self._peupler(type_etab)
        erreurs = []
        self._connecter(d['etab'], 'etablissement')
        erreurs += self._crawl(d, NAMESPACES_DIRECTION | {'school_admin'}, self.client, 'directeur')
        for niveau, prof in d['profs'].items():
            self._connecter(prof, 'professeur')
            ns = {'enseignant_primaire'} if type_etab == 'primary' else {'enseignant', 'professeur'}
            erreurs += self._crawl(d, ns, self.client, f'prof_{niveau}')
        for perso in d['personnel']:
            self._connecter(perso, 'personnel')
            erreurs += self._crawl(d, NAMESPACES_DIRECTION, self.client, perso.fonction)
        self._connecter(d['eleves'][0], 'eleve')
        erreurs += self._crawl(d, {'eleve'}, self.client, 'eleve')
        self._connecter(d['parent'], 'parent')
        erreurs += self._crawl(d, {'school_admin'}, self.client, 'parent')
        return erreurs

    def _verifier(self, type_etab):
        erreurs = self._audit(type_etab)
        self.assertEqual(erreurs, [], f'\n[{type_etab}] ' + f'\n[{type_etab}] '.join(erreurs))

    def test_primaire(self):
        self._verifier('primary')

    def test_college(self):
        self._verifier('collège')

    def test_lycee(self):
        self._verifier('lycée')

    def test_college_lycee(self):
        self._verifier('collège_lycée')

    def test_mixte(self):
        self._verifier('mixte')


class PagesInternesAria(TestCase):
    """Les pages de l'équipe Aria restent fermées aux comptes des établissements et au public."""

    def setUp(self):
        self.etab = _make_etablissement_type('lycée', 'int')
        self.annee = _make_annee(self.etab)
        c = Classe.objects.create(nom='2nde A', niveau='lycee', code_classe=f'IA-{self.etab.pk}', etablissement=self.etab)
        self.eleve = _make_eleve_simple(self.etab, c, 'Faye', 'Awa', 'F', f'i{self.etab.pk}')

    def _connecter(self, user, user_type):
        self.client.force_login(user, backend='school_admin.authentication_backends.MultiUserBackend')
        session = self.client.session
        session['_auth_user_type'] = user_type
        session.save()

    def test_comptes_etablissement_redirigés(self):
        for user, typ in ((self.etab, 'etablissement'), (self.eleve, 'eleve')):
            self._connecter(user, typ)
            for nom in ('ajout_etablissement', 'management_equipes', 'annonces', 'parametres_administrateur', 'dashboard_rh',
                        'dashboard_support', 'inscription_compte_user', 'etablissements', 'profil_admin'):
                r = self.client.get(reverse(f'school_admin:{nom}'))
                self.assertEqual(r.status_code, 302, f'{typ} {nom}')
            self.client.logout()

    def test_inscription_publique_ne_cree_pas_de_compte(self):
        from school_admin.model.compte_user import CompteUser

        avant = CompteUser.objects.count()
        r = self.client.post(reverse('school_admin:inscription_compte_user'), {
            'nom': 'X', 'prenom': 'Y', 'email': 'pirate@t.local', 'telephone': '770000000', 'type_compte': 'interne',
            'departement': 'technique', 'fonction': 'administrateur', 'password': 'Pirate@123456',
            'confirm_password': 'Pirate@123456'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(CompteUser.objects.count(), avant)

    def test_type_etablissement_inconnu_refuse(self):
        from school_admin.model.compte_user import CompteUser

        admin = CompteUser(username='adm.int', email='adm.int@t.local', nom='A', prenom='B', fonction='administrateur')
        admin.set_password(MDP)
        admin.save()
        self._connecter(admin, 'compte_user')
        self.client.post(reverse('school_admin:administrateur_update_etablissement'), {
            'etablissement_id': self.etab.id, 'nom': self.etab.nom, 'type_etablissement': 'lycee'})
        self.etab.refresh_from_db()
        self.assertEqual(self.etab.type_etablissement, 'lycée')
