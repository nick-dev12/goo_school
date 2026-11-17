from django.test import TestCase
from django.urls import reverse

from school_admin.model.carte_identite_personnalisation_model import CarteIdentitePersonnalisation
from school_admin import tests_smoke_primaire_secondaire as smoke


class CartesPersonnalisationTests(TestCase):
    def setUp(self):
        self.d = smoke.SmokePrimaireSecondaire._peupler(None, 'lycée')
        self.url = reverse('secretaire:personnaliser_cartes_identite')
        self.connecter(self.d['etab'], 'etablissement')

    def connecter(self, user, role):
        self.client.force_login(user, backend='school_admin.authentication_backends.MultiUserBackend')
        session = self.client.session
        session['_auth_user_type'] = role
        session.save()

    def donnees(self):
        return dict(pays_nom='RÉPUBLIQUE EXEMPLE', devise_pays='Unité et savoir',
                    titre_carte='CARTE DE CAMPUS', devise_etablissement='Apprendre ensemble',
                    modele='moderne', couleur_principale='#185a42', couleur_secondaire='#e4b840',
                    couleur_fond='#fffdf5', couleur_texte='#18352c')

    def test_apercu_est_fictif_et_une_seule_carte(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'DEMO0001')
        for code in ('classique', 'moderne', 'horizon', 'signature', 'elan', 'campus', 'prisme', 'rivage', 'academie', 'equateur'):
            self.assertContains(r, f'data-modele="{code}"')
        self.assertContains(r, 'id="modeles-dialog"')
        self.assertContains(r, 'id="choisir-modele"')
        self.assertContains(r, 'class="student-idcard-front"', count=1)
        self.assertContains(r, 'class="student-idcard-back"', count=1)
        self.assertNotContains(r, self.d['eleves'][0].numero_eleve)

    def test_enregistrement_commun_aux_cartes_et_au_profil(self):
        r = self.client.post(self.url, self.donnees())
        self.assertRedirects(r, self.url)
        reglages = CarteIdentitePersonnalisation.objects.get(etablissement=self.d['etab'])
        self.assertEqual(reglages.titre_carte, 'CARTE DE CAMPUS')
        for nom, kwargs in [('secretaire:carte_identite_eleve', {'eleve_id': self.d['eleves'][0].pk}),
                            ('secretaire:cartes_identite_classe', {'classe_id': self.d['classes'][0].pk})]:
            r = self.client.get(reverse(nom, kwargs=kwargs))
            self.assertContains(r, 'CARTE DE CAMPUS')
            self.assertContains(r, 'Apprendre ensemble')
            self.assertContains(r, 'data-carte-modele="moderne"')
            self.assertContains(r, '--carte-principale:#185a42')
            self.assertNotContains(r, 'id="btn-personnaliser"')
        self.connecter(self.d['eleves'][0], 'eleve')
        self.assertContains(self.client.get(reverse('eleve:profil_eleve')), 'CARTE DE CAMPUS')

    def test_champs_vides_et_trop_longs_refuses(self):
        data = self.donnees()
        data['pays_nom'] = ' ' * 3
        data['titre_carte'] = 'A' * 256
        r = self.client.post(self.url, data)
        self.assertEqual(r.status_code, 200)
        self.assertIn('pays_nom', r.context['form'].errors)
        self.assertIn('titre_carte', r.context['form'].errors)
        self.assertNotEqual(CarteIdentitePersonnalisation.objects.get(etablissement=self.d['etab']).devise_pays,
                            data['devise_pays'])

    def test_couleurs_et_modele_invalides_refuses(self):
        data = self.donnees()
        data['couleur_principale'] = 'red; background:url(https://example.com)'
        data['modele'] = 'inconnu'
        r = self.client.post(self.url, data)
        self.assertIn('couleur_principale', r.context['form'].errors)
        self.assertIn('modele', r.context['form'].errors)

    def test_styles_css_proteges(self):
        from school_admin.templatetags.carte_style_tags import couleur_carte, contraste_carte
        self.assertEqual(couleur_carte('red;display:none'), '#3b82f6')
        self.assertEqual(contraste_carte('#ffffff'), '#111827')
        self.assertEqual(contraste_carte('#000000'), '#ffffff')

    def test_nouveaux_modeles_persistes_et_affiches(self):
        for modele in ('horizon', 'signature', 'elan', 'campus', 'prisme', 'rivage', 'academie', 'equateur'):
            with self.subTest(modele=modele):
                data = self.donnees()
                data['modele'] = modele
                self.assertRedirects(self.client.post(self.url, data), self.url)
                self.assertEqual(CarteIdentitePersonnalisation.objects.get(etablissement=self.d['etab']).modele,
                                 modele)
                for nom, kwargs in [('secretaire:carte_identite_eleve', {'eleve_id': self.d['eleves'][0].pk}),
                                    ('secretaire:cartes_identite_classe', {'classe_id': self.d['classes'][0].pk})]:
                    self.assertContains(self.client.get(reverse(nom, kwargs=kwargs)), f'data-carte-modele="{modele}"')

    def test_professeur_ne_peut_modifier(self):
        self.connecter(next(iter(self.d['profs'].values())), 'professeur')
        self.assertEqual(self.client.post(self.url, self.donnees()).status_code, 403)

    def test_secretaire_et_isolation_entre_etablissements(self):
        from school_admin.tests.test_assistant_directeur_tools import _make_etablissement_type
        autre = _make_etablissement_type('lycée', 'iso')
        autre_reglage = CarteIdentitePersonnalisation.get_or_create_for_etablissement(autre)
        ancien_titre = autre_reglage.titre_carte
        secretaire = next(p for p in self.d['personnel'] if p.fonction == 'secretaire')
        self.connecter(secretaire, 'personnel')
        data = self.donnees()
        data['etablissement'] = autre.pk  # même une tentative de changer la cible est ignorée
        self.assertRedirects(self.client.post(self.url, data), self.url)
        autre_reglage.refresh_from_db()
        self.assertEqual(autre_reglage.titre_carte, ancien_titre)
        self.assertEqual(CarteIdentitePersonnalisation.objects.get(etablissement=self.d['etab']).titre_carte,
                         data['titre_carte'])

    def test_liste_actions_dans_meme_onglet(self):
        r = self.client.get(reverse('secretaire:cartes_identite_eleves'))
        self.assertContains(r, self.url)
        self.assertNotContains(r, 'class="sci-hero-stats"')
        self.assertNotContains(r, 'class="sci-hero-actions"')
        self.assertNotContains(r, 'Imprimer la liste nominative')
        # Vérifie les liens de carte, même lorsqu'ils sont repris par le modal responsive.
        from html.parser import HTMLParser
        class Liens(HTMLParser):
            def handle_starttag(inner, tag, attrs):
                attrs = dict(attrs)
                if tag == 'a' and ('/carte-identite/' in attrs.get('href', '') or
                                   '/cartes-identite/classe/' in attrs.get('href', '')):
                    self.assertNotEqual(attrs.get('target'), '_blank')
        Liens().feed(r.content.decode())

    def test_qr_compact_vectoriel_et_ancienne_adresse_compatible(self):
        import base64
        import qrcode
        from django.test import override_settings
        from django.urls import resolve
        from school_admin.templatetags.carte_style_tags import qr_carte
        from school_admin.personal_views.qr_scan_view import scan_qr_eleve
        eleve = self.d['eleves'][0]
        original_identifier = eleve.qr_code_identifier
        with override_settings(SITE_URL='https://ecole.example'):
            payload = eleve._build_qr_payload()
            self.assertEqual(payload, 'https://ecole.example' + reverse(
                'school_admin:scan_qr_eleve_court', kwargs={'qr_identifier': original_identifier}))
            image = qr_carte(eleve)
        svg = base64.b64decode(image.split(',', 1)[1]).decode()
        self.assertIn('<svg', svg)
        self.assertIn('fill="white"', svg)
        self.assertNotIn(eleve.nom, payload)
        for route in ('scan_qr_eleve', 'scan_qr_eleve_court'):
            match = resolve(reverse('school_admin:' + route, kwargs={'qr_identifier': original_identifier}))
            self.assertEqual(match.func, scan_qr_eleve)
            self.assertEqual(match.kwargs['qr_identifier'], original_identifier)
        dense = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=3)
        dense.add_data(payload.replace('/q/', '/scan-qr/eleve/')); dense.make(fit=True)
        compact = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
        compact.add_data(payload); compact.make(fit=True)
        self.assertLess(compact.modules_count, dense.modules_count)
        eleve.refresh_from_db()
        self.assertEqual(eleve.qr_code_identifier, original_identifier)

    def test_contacts_verso_utilisent_parent_lie_et_telephone_etablissement(self):
        from school_admin.model.parent_model import Parent
        parent = self.d['parent']
        Parent.objects.filter(pk=parent.pk).update(telephone='+221 77 111 22 33')
        self.d['etab'].telephone = '+221 33 444 55 66'
        self.d['etab'].save(update_fields=['telephone'])
        for name, kwargs in [('secretaire:carte_identite_eleve', {'eleve_id': self.d['eleves'][0].pk}),
                             ('secretaire:cartes_identite_classe', {'classe_id': self.d['classes'][0].pk})]:
            response = self.client.get(reverse(name, kwargs=kwargs))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '+221 77 111 22 33')
            self.assertContains(response, '+221 33 444 55 66')
            self.assertNotContains(response, 'Téléphone du Directeur')

    def test_contacts_lies_valides_repli_et_chargement_groupe(self):
        from school_admin.services.carte_contacts import precharger_contacts_cartes, telephone_parent_carte
        from school_admin.model.lien_familial_model import LienFamilial
        from school_admin.model.eleve_model import Eleve
        eleves = list(Eleve.objects.filter(pk__in=[e.pk for e in self.d['eleves']]))
        with self.assertNumQueries(1):
            precharger_contacts_cartes(eleves)
        with self.assertNumQueries(0):
            for eleve in eleves:
                self.assertEqual(telephone_parent_carte(eleve), self.d['parent'].telephone)
        LienFamilial.objects.filter(eleve=eleves[0]).update(statut='en_attente')
        eleve = Eleve.objects.get(pk=eleves[0].pk)
        eleve.parent_telephone = '+221 70 999 88 77'
        self.assertEqual(telephone_parent_carte(eleve), '+221 70 999 88 77')
        eleve.parent_telephone = ''
        self.assertEqual(telephone_parent_carte(eleve), 'Non renseigné')

    def test_indicatifs_contacts_cartes(self):
        from school_admin.services.carte_contacts import telephone_international_carte as formater
        for numero, pays, attendu in [
            ('770001122', 'Sénégal', '+221 770001122'),
            ('33 444 55 66', 'sn', '+221 334445566'),
            ('+221 77 000 11 22', 'SN', '+221 77 000 11 22'),
            ('00221770001122', 'sn', '+221770001122'),
            ('221770001122', 'senegal', '+221770001122'),
            ('0701020304', "Côte d’Ivoire", '+225 0701020304'),
            ('0612345678', 'France', '+33 612345678'),
            ('770001122', 'pays inconnu', '770001122'),
            ('', 'sn', 'Non renseigné'),
            ('Non renseigné', 'sn', 'Non renseigné'),
        ]:
            with self.subTest(numero=numero, pays=pays):
                self.assertEqual(formater(numero, pays), attendu)
