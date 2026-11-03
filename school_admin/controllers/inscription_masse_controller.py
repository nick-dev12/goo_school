"""
Inscription des élèves en masse : modèle Excel, import de fichier ou saisie en grille, aperçu, confirmation.
"""
import json

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from ..model.classe_model import Classe
from ..services import inscription_masse as svc
from ..utils.decorators_permissions import require_permission

CLE_SESSION = 'inscription_masse_apercu'


def _acces(request):
    from ..utils.decorators_permissions import _get_user_etablissement
    from ..utils.session_utils import get_session_active

    etablissement = _get_user_etablissement(request, 'eleves_inscrire')[0]
    if etablissement is None:
        return None, None
    return etablissement, get_session_active(request, etablissement)


def _classes(etablissement):
    from ..services.structure_v4 import rang_scolaire

    return sorted(Classe.objects.filter(etablissement=etablissement, actif=True),
                  key=lambda c: (rang_scolaire(c.nom), c.nom))


def _contexte(etablissement, annee, **extra):
    est_sup = etablissement.type_etablissement == 'superieur'
    ctx = {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'classes': _classes(etablissement),
        'est_superieur': est_sup, 'mot_eleves': 'étudiants' if est_sup else 'élèves',
        'colonnes': svc.COLONNES, 'module_comptabilite': etablissement.module_comptabilite,
    }
    ctx.update(extra)
    return ctx


FRAGMENTS = 'school_admin/directeur/inscription_masse/'


def _liste_avec_modal(mode='fichier'):
    """L'inscription en masse se fait dans une fenêtre de la liste des élèves : on y renvoie."""
    return redirect(reverse('secretaire:liste_eleves') + f'?masse={mode}')


@require_permission('eleves_inscrire')
def inscription_masse(request):
    """
    Étapes de la fenêtre « Inscription en masse » (liste des élèves), chargées en AJAX :
    saisie (fichier ou grille) → aperçu → résultat avec les identifiants.
    Une visite directe de l'adresse ouvre la liste des élèves avec la fenêtre.
    """
    etablissement, annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return _liste_avec_modal(request.GET.get('mode') if request.GET.get('mode') == 'grille' else 'fichier')

    def saisie(erreur=None, onglet='fichier'):
        return render(request, FRAGMENTS + '_saisie.html', _contexte(etablissement, annee, onglet=onglet, erreur=erreur))

    if annee is None:
        return saisie("Définissez d'abord l'année scolaire active avant d'inscrire des élèves.")

    action = request.POST.get('action') if request.method == 'POST' else None
    if action in ('analyser_fichier', 'analyser_grille'):
        onglet = 'grille' if action == 'analyser_grille' else 'fichier'
        try:
            if action == 'analyser_fichier':
                fichier = request.FILES.get('fichier')
                if not fichier:
                    raise svc.ImportErreur("Choisissez un fichier Excel (.xlsx) ou CSV.")
                lignes = svc.lire_fichier(fichier)
                source = fichier.name
            else:
                brutes = json.loads(request.POST.get('grille') or '[]')
                lignes = [dict(l, _ligne=i) for i, l in enumerate(brutes, start=1)
                          if any(str(v).strip() for k, v in l.items() if k != 'classe')]
                if not lignes:
                    raise svc.ImportErreur("La grille est vide : saisissez au moins un élève.")
                source = 'saisie rapide'
        except svc.ImportErreur as exc:
            return saisie(str(exc), onglet)
        except (ValueError, TypeError):
            return saisie("La saisie n'a pas pu être lue. Réessayez.", onglet)
        classe_defaut = None
        if request.POST.get('classe_defaut'):
            classe_defaut = Classe.objects.filter(etablissement=etablissement, id=request.POST['classe_defaut']).first()
        analyse = svc.analyser(etablissement, lignes, classe_defaut)
        request.session[CLE_SESSION] = {'lignes': analyse['lignes'], 'source': source}
        return render(request, FRAGMENTS + '_apercu.html', _contexte(etablissement, annee, analyse=analyse, source=source))

    if action == 'confirmer':
        donnees = request.session.get(CLE_SESSION)
        if not donnees:
            return saisie("L'aperçu a expiré : relancez l'import.")
        statut = request.POST.get('statut') if request.POST.get('statut') in ('nouvelle', 'reinscription', 'transfert') else 'nouvelle'
        creer_frais = request.POST.get('creer_frais') == '1'
        try:
            crees = svc.importer(etablissement, annee, donnees['lignes'], statut=statut, creer_frais=creer_frais)
        except Exception:  # noqa: BLE001 — tout ou rien : rien n'est enregistré
            import logging

            logging.getLogger(__name__).exception("Import en masse des élèves")
            return saisie("L'import a échoué : aucun élève n'a été enregistré. Vérifiez le fichier et réessayez.")
        request.session.pop(CLE_SESSION, None)
        sans_parent = sum(1 for c in crees if not c['eleve'].parent_telephone)
        return render(request, FRAGMENTS + '_resultat.html',
                      _contexte(etablissement, annee, crees=crees, sans_parent=sans_parent,
                                parents_crees=sum(1 for c in crees if c['parent_cree'])))

    return saisie(onglet=request.GET.get('mode') if request.GET.get('mode') == 'grille' else 'fichier')


@require_permission('eleves_inscrire')
def modele_inscription_masse(request):
    etablissement, _annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    contenu = svc.generer_modele(etablissement)
    reponse = HttpResponse(contenu, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    reponse['Content-Disposition'] = 'attachment; filename="modele_inscription_eleves.xlsx"'
    return reponse
