"""Personnalisation commune des cartes d'un établissement, avec un aperçu fictif."""
from datetime import date
from types import SimpleNamespace

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from school_admin.model.carte_identite_personnalisation_model import CarteIdentitePersonnalisation
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.utils.session_utils import get_session_active, get_session_consultee


class PersonnalisationCarteForm(forms.ModelForm):
    class Meta:
        model = CarteIdentitePersonnalisation
        fields = ('modele', 'couleur_principale', 'couleur_secondaire', 'couleur_fond', 'couleur_texte',
                  'pays_nom', 'devise_pays', 'titre_carte', 'devise_etablissement')
        widgets = {champ: forms.TextInput(attrs={'class': 'personnalisation-input'}) for champ in fields}
        help_texts = {champ: '' for champ in fields}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['modele'].widget = forms.HiddenInput()
        for champ in ('couleur_principale', 'couleur_secondaire', 'couleur_fond', 'couleur_texte'):
            self.fields[champ].widget = forms.TextInput(attrs={
                'type': 'color', 'class': 'personnalisation-input personnalisation-color'})

    def clean(self):
        valeurs = super().clean()
        for champ in self.Meta.fields:
            if champ in valeurs:
                valeurs[champ] = valeurs[champ].strip()
                if not valeurs[champ]:
                    self.add_error(champ, 'Ce champ est obligatoire.')
        return valeurs


@login_required
def personnaliser_cartes_identite(request):
    user = request.user
    if isinstance(user, Etablissement):
        etablissement = user
    elif isinstance(user, PersonnelAdministratif) and user.fonction == 'secretaire':
        etablissement = user.etablissement
    else:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Accès non autorisé.')
    if not etablissement:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Aucun établissement associé.')

    personnalisation = CarteIdentitePersonnalisation.get_or_create_for_etablissement(etablissement)
    form = PersonnalisationCarteForm(request.POST if request.method == 'POST' else None,
                                    instance=personnalisation)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'La personnalisation est appliquée à toutes les cartes de votre établissement.')
        return redirect('secretaire:personnaliser_cartes_identite')

    annee = (get_session_consultee(request, etablissement) if isinstance(user, Etablissement)
             else get_session_active(request, etablissement))
    niveau = 'Licence 1' if etablissement.type_etablissement == 'superieur' else 'CM2'
    classe = SimpleNamespace(nom='L1 A' if etablissement.type_etablissement == 'superieur' else 'CM2 A',
                             get_libelle_niveau_complet_pour_eleve=niveau)
    eleve = SimpleNamespace(nom='EXEMPLE', prenom='Aminata', nom_complet='EXEMPLE Aminata',
                            date_naissance=date(2005, 2, 15), lieu_naissance='Ville exemple',
                            classe=classe, get_sexe_display='Féminin', matricule_eleve='DEMO0001',
                            numero_eleve='DEMO0001', photo_profil=None, qr_code_image=None,
                            parent_telephone='+221 77 000 00 00')
    return render(request, 'school_admin/directeur/secretaire/personnaliser_cartes_identite.html', {
        'etablissement': etablissement, 'personnalisation': personnalisation, 'form': form,
        'eleve': eleve, 'annee_scolaire_active': annee, 'apercu_fictif': True,
        'modeles_cartes': [
            ('classique', 'Classique', 'Un cadre épuré et une présentation institutionnelle.'),
            ('moderne', 'Moderne', 'Un bandeau affirmé et une photo arrondie.'),
            ('horizon', 'Horizon', 'Une composition graphique aux lignes diagonales.'),
            ('signature', 'Signature', 'Un style élégant, des détails fins et un médaillon photo.'),
            ('elan', 'Élan', 'Un titre en cartouche et un pied de carte aux lignes courbes.'),
            ('campus', 'Campus', 'Un bandeau arrondi et une photo à droite, comme un badge de campus.'),
            ('prisme', 'Prisme', 'Une grande photo à gauche et une composition géométrique affirmée.'),
            ('rivage', 'Rivage', 'Un fond clair et une courbe latérale colorée, façon carte de campus.'),
            ('academie', 'Académie', 'Une grande photo et un bandeau de nom d’établissement au pied de la carte.'),
            ('equateur', 'Équateur', 'Un cadre uni affirmé, un titre souligné et une identité bien structurée.'),
        ],
    })
