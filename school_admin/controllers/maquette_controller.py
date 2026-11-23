"""
Maquette pédagogique du supérieur : UE / EC, volumes CM-TD-TP-TPE, types d'UE, options, parcours,
groupes de TD / TP et inscriptions pédagogiques.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..model.classe_model import Classe
from ..model.maquette_model import GroupeEnseignement, InscriptionPedagogique, Parcours
from ..model.module_model import ModuleClasse
from ..services import maquette as svc
from ..services.deliberations import etudiants
from ..utils.decorators_permissions import check_permission, require_permission


def _acces(request):
    from ..utils.decorators_permissions import _get_user_etablissement
    from ..utils.session_utils import get_session_active

    etablissement = _get_user_etablissement(request)[0]
    if etablissement is None:
        return None, None
    return etablissement, get_session_active(request, etablissement)


def _entier(valeur, defaut=0, maxi=999):
    try:
        return max(0, min(maxi, int(str(valeur or defaut).strip() or defaut)))
    except ValueError:
        return defaut


@login_required
@require_permission('config_voir')
def liste_maquettes(request):
    return redirect(reverse('matiere:liste_matieres') + '?tab=modules')


@login_required
@require_permission('config_voir')
def maquette_classe(request, classe_id):
    etablissement, _ = _acces(request)
    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement)
    return redirect('administrateur_etablissement:detail_classe', classe_id=classe.id)


@login_required
@require_permission('config_modifier')
@require_POST
def gerer_groupes_parcours(request, classe_id):
    etablissement, annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement)
    if etablissement.type_etablissement != 'superieur':
        return redirect('directeur:dashboard_directeur')
    url = reverse('administrateur_etablissement:detail_classe', args=[classe.id])

    action = request.POST.get('action')
    try:
        if action == 'parcours_ajouter':
            nom = request.POST.get('nom', '').strip()
            if not nom:
                messages.error(request, "Donnez un nom au parcours.")
            else:
                Parcours.objects.create(classe=classe, nom=nom[:120], code=request.POST.get('code', '').strip()[:20])
                messages.success(request, f"Parcours « {nom} » ajouté.")
        elif action == 'parcours_supprimer':
            Parcours.objects.filter(classe=classe, id=request.POST.get('id')).delete()
            messages.success(request, "Parcours supprimé (ses UE redeviennent du tronc commun).")
        elif action == 'groupe_ajouter':
            nom = request.POST.get('nom', '').strip().upper()
            type_g = request.POST.get('type_groupe') if request.POST.get('type_groupe') in ('td', 'tp') else 'td'
            if not nom:
                messages.error(request, "Donnez un nom au groupe (ex. G1).")
            else:
                GroupeEnseignement.objects.create(classe=classe, nom=nom[:30], type_groupe=type_g,
                                                  capacite=_entier(request.POST.get('capacite'), 40, 500))
                messages.success(request, f"Groupe {type_g.upper()} {nom} ajouté.")
        elif action == 'groupe_supprimer':
            GroupeEnseignement.objects.filter(classe=classe, id=request.POST.get('id')).delete()
            messages.success(request, "Groupe supprimé.")
        elif action == 'groupes_repartir' and annee:
            type_g = request.POST.get('type_groupe') if request.POST.get('type_groupe') in ('td', 'tp') else 'td'
            n = svc.repartir_groupes(classe, etudiants(classe, annee), type_g)
            if n:
                messages.success(request, f"Étudiants répartis équitablement dans {n} groupe(s) de {type_g.upper()}.")
            else:
                messages.error(request, f"Créez d'abord des groupes de {type_g.upper()}.")
    except IntegrityError:
        messages.error(request, "Ce nom existe déjà pour cette classe.")
    except ValueError as exc:
        messages.error(request, f"Valeur invalide : {exc}")
    return redirect(url + '?groupes=1#groupes-parcours')


@login_required
@require_permission('config_voir')
def inscriptions_pedagogiques(request, classe_id):
    etablissement, annee = _acces(request)
    if etablissement is None or annee is None:
        return redirect('directeur:dashboard_directeur')
    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement)
    eleves = etudiants(classe, annee)
    parcours = list(Parcours.objects.filter(classe=classe))
    options = list(ModuleClasse.objects.filter(classe=classe, optionnelle=True)
                   .select_related('module', 'periode').order_by('periode__date_debut', 'groupe_options', 'module__nom'))
    groupes_opt = {}
    for mc in options:
        groupes_opt.setdefault((mc.periode.nom_periode if mc.periode else '', mc.groupe_options or 'Options'), []).append(mc)
    groupes = list(GroupeEnseignement.objects.filter(classe=classe).prefetch_related('etudiants'))
    types_groupes = sorted({g.type_groupe for g in groupes})

    if request.method == 'POST':
        if not check_permission(request.user, 'config_modifier'):
            messages.error(request, "Vous ne pouvez pas modifier les choix étudiants.")
            return redirect('directeur:inscriptions_pedagogiques', classe_id=classe.id)
        saisies = {e.id: {'parcours': request.POST.get(f'parcours_{e.id}') or None,
                          'options': request.POST.getlist(f'options_{e.id}')} for e in eleves}
        erreurs = svc.enregistrer_inscriptions(classe, annee, saisies)
        for err in erreurs:
            messages.error(request, err)
        if not erreurs:
            with transaction.atomic():
                for t in types_groupes:
                    for g in [x for x in groupes if x.type_groupe == t]:
                        g.etudiants.remove(*eleves)
                    for e in eleves:
                        gid = request.POST.get(f'groupe_{t}_{e.id}')
                        g = next((x for x in groupes if str(x.id) == gid and x.type_groupe == t), None)
                        if g:
                            g.etudiants.add(e)
            messages.success(request, "Inscriptions pédagogiques enregistrées.")
        return redirect('directeur:inscriptions_pedagogiques', classe_id=classe.id)

    inscriptions = {i.eleve_id: i for i in InscriptionPedagogique.objects.filter(classe=classe, annee_scolaire=annee)
                    .prefetch_related('ues_optionnelles')}
    membres = {}
    for g in groupes:
        for e in g.etudiants.all():
            membres[(g.type_groupe, e.id)] = g.id
    lignes = []
    for e in eleves:
        ins = inscriptions.get(e.id)
        lignes.append({'eleve': e, 'parcours_id': ins.parcours_id if ins else None,
                       'options': set(ins.ues_optionnelles.values_list('id', flat=True)) if ins else set(),
                       'groupes': {t: membres.get((t, e.id)) for t in types_groupes}})
    sans_choix = sum(1 for l in lignes if options and not l['options'])
    return render(request, 'school_admin/directeur/maquette/inscriptions.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'classe': classe,
        'lignes': lignes, 'parcours': parcours, 'groupes_opt': groupes_opt, 'options': options,
        'groupes': groupes, 'types_groupes': types_groupes, 'sans_choix': sans_choix,
        'sans_parcours': sum(1 for l in lignes if parcours and not l['parcours_id']),
    })
