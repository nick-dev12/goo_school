"""
Inscription des élèves en masse : modèle Excel, import de fichier ou saisie en grille, aperçu, confirmation,
puis complément des contacts parents laissés vides.
"""
import json
from datetime import date

from django.contrib import messages
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


@require_permission('eleves_inscrire')
def inscription_masse(request):
    etablissement, annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    if annee is None:
        messages.error(request, "Définissez d'abord l'année scolaire active avant d'inscrire des élèves.")
        return redirect('directeur:gestion_eleves')

    action = request.POST.get('action') if request.method == 'POST' else None
    if action in ('analyser_fichier', 'analyser_grille'):
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
            messages.error(request, str(exc))
            return render(request, 'school_admin/directeur/inscription_masse/inscription_masse.html',
                          _contexte(etablissement, annee, onglet='grille' if action == 'analyser_grille' else 'fichier'))
        except (ValueError, TypeError):
            messages.error(request, "La saisie n'a pas pu être lue. Réessayez.")
            return redirect('directeur:inscription_masse')
        classe_defaut = None
        if request.POST.get('classe_defaut'):
            classe_defaut = Classe.objects.filter(etablissement=etablissement, id=request.POST['classe_defaut']).first()
        analyse = svc.analyser(etablissement, lignes, classe_defaut)
        request.session[CLE_SESSION] = {'lignes': analyse['lignes'], 'source': source}
        return render(request, 'school_admin/directeur/inscription_masse/apercu.html',
                      _contexte(etablissement, annee, analyse=analyse, source=source))

    if action == 'confirmer':
        donnees = request.session.get(CLE_SESSION)
        if not donnees:
            messages.error(request, "L'aperçu a expiré : relancez l'import.")
            return redirect('directeur:inscription_masse')
        statut = request.POST.get('statut') if request.POST.get('statut') in ('nouvelle', 'reinscription', 'transfert') else 'nouvelle'
        creer_frais = request.POST.get('creer_frais') == '1'
        try:
            crees = svc.importer(etablissement, annee, donnees['lignes'], statut=statut, creer_frais=creer_frais)
        except Exception:  # noqa: BLE001 — tout ou rien : rien n'est enregistré
            import logging

            logging.getLogger(__name__).exception("Import en masse des élèves")
            messages.error(request, "L'import a échoué : aucun élève n'a été enregistré. Vérifiez le fichier et réessayez.")
            return redirect('directeur:inscription_masse')
        request.session.pop(CLE_SESSION, None)
        sans_parent = sum(1 for c in crees if not c['eleve'].parent_telephone)
        messages.success(request, f"{len(crees)} {'étudiant(s)' if etablissement.type_etablissement == 'superieur' else 'élève(s)'} inscrit(s).")
        return render(request, 'school_admin/directeur/inscription_masse/resultat.html',
                      _contexte(etablissement, annee, crees=crees, sans_parent=sans_parent,
                                parents_crees=sum(1 for c in crees if c['parent_cree'])))

    onglet = request.GET.get('mode') if request.GET.get('mode') in ('fichier', 'grille') else 'fichier'
    return render(request, 'school_admin/directeur/inscription_masse/inscription_masse.html',
                  _contexte(etablissement, annee, onglet=onglet))


@require_permission('eleves_inscrire')
def modele_inscription_masse(request):
    etablissement, _annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    contenu = svc.generer_modele(etablissement)
    reponse = HttpResponse(contenu, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    reponse['Content-Disposition'] = 'attachment; filename="modele_inscription_eleves.xlsx"'
    return reponse


@require_permission('eleves_modifier')
def contacts_parents(request):
    """Élèves sans contact parent, classe par classe, avec une saisie rapide du parent."""
    from ..model.eleve_model import Eleve
    from ..model.lien_familial_model import LienFamilial
    from ..model.parent_model import Parent

    from ..utils.decorators_permissions import _get_user_etablissement
    from ..utils.session_utils import get_session_active

    etablissement = _get_user_etablissement(request, 'eleves_modifier')[0]
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    annee = get_session_active(request, etablissement)

    if request.method == 'POST':
        n_maj, n_comptes = 0, 0
        ids = [i for i in request.POST.getlist('eleve') if i.isdigit()]
        for eleve in Eleve.objects.filter(etablissement=etablissement, id__in=ids):
            p = lambda champ: (request.POST.get(f'{champ}_{eleve.id}') or '').strip()  # noqa: E731
            tel = svc._telephone(p('tel'))
            nom, prenom, lien = svc._nom(p('nom')), svc._prenom(p('prenom')), p('lien')
            if not (tel or nom):
                continue
            eleve.parent_nom, eleve.parent_prenom = nom or eleve.parent_nom, prenom or eleve.parent_prenom
            eleve.parent_telephone = tel or eleve.parent_telephone
            eleve.parent_lien = lien or eleve.parent_lien or 'pere'
            eleve.save(update_fields=['parent_nom', 'parent_prenom', 'parent_telephone', 'parent_lien'])
            n_maj += 1
            if tel and not LienFamilial.objects.filter(eleve=eleve, actif=True).exists():
                parent = Parent.objects.filter(telephone=tel, etablissement=etablissement).first()
                if parent is None:
                    matricule = Parent.generer_matricule_parent(etablissement)
                    mdp = Parent.generer_mot_de_passe()
                    parent = Parent(matricule_parental=matricule, username=matricule,
                                    type_parent=eleve.parent_lien if eleve.parent_lien in ('mere', 'pere') else 'tuteur',
                                    nom=nom or eleve.nom, prenom=prenom or '', telephone=tel, email='', adresse='', profession='',
                                    etablissement=etablissement, mot_de_passe_provisoire=mdp, mot_de_passe_modifie=False,
                                    is_active=True)
                    parent.set_password(mdp)
                    parent.save()
                    n_comptes += 1
                LienFamilial.objects.get_or_create(parent=parent, eleve=eleve, defaults={
                    'type_lien': eleve.parent_lien if eleve.parent_lien in ('mere', 'pere') else 'tuteur',
                    'statut': 'valide', 'est_inscripteur': True, 'actif': True})
        if n_maj:
            messages.success(request, f"{n_maj} contact(s) parent enregistré(s)" + (f", {n_comptes} compte(s) parent créé(s)." if n_comptes else "."))
        else:
            messages.info(request, "Aucun contact saisi.")
        suite = reverse('directeur:contacts_parents')
        if request.POST.get('classe'):
            suite += f"?classe={request.POST['classe']}"
        return redirect(suite)

    from django.db.models import Q
    from ..services.structure_v4 import rang_scolaire

    manquants = (Eleve.objects.filter(etablissement=etablissement, actif=True)
                 .filter(Q(parent_telephone__isnull=True) | Q(parent_telephone=''))
                 .select_related('classe').order_by('nom', 'prenom'))
    par_classe = {}
    for e in manquants:
        par_classe.setdefault(e.classe, []).append(e)
    groupes = sorted(par_classe.items(), key=lambda kv: (rang_scolaire(kv[0].nom if kv[0] else 'zz'), kv[0].nom if kv[0] else ''))
    classe_choisie = request.GET.get('classe')
    return render(request, 'school_admin/directeur/inscription_masse/contacts_parents.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'groupes': groupes,
        'total': manquants.count(), 'classe_choisie': classe_choisie,
        'mot_eleves': 'étudiants' if etablissement.type_etablissement == 'superieur' else 'élèves',
        'liens': [('pere', 'Père'), ('mere', 'Mère'), ('tuteur_legal', 'Tuteur'), ('grand_parent', 'Grand-parent'),
                  ('oncle_tante', 'Oncle / Tante'), ('frere_soeur', 'Frère / Sœur'), ('autre', 'Autre')],
    })
