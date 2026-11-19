"""Diplômes du supérieur : classes de fin de cycle, éligibilité, délivrance, impression."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from ..model.admission_model import Diplome
from ..model.classe_model import Classe
from ..model.etablissement_model import Etablissement
from ..services import diplomes as svc
from ..services.deliberations import etudiants
from ..utils.decorators_permissions import require_permission


def _acces(request):
    from ..utils.decorators_permissions import _get_user_etablissement
    from ..utils.session_utils import get_session_active

    etablissement = _get_user_etablissement(request, 'eleves_liste')[0]
    if etablissement is None:
        return None, None
    return etablissement, get_session_active(request, etablissement)


@login_required
@require_permission('eleves_liste')
def liste_diplomes(request):
    etablissement, annee = _acces(request)
    if etablissement is None or etablissement.type_etablissement != 'superieur':
        return redirect('directeur:dashboard_directeur')
    classes = [c for c in Classe.objects.filter(etablissement=etablissement, actif=True, niveau='superieur')
               .select_related('department').order_by('nom') if svc.diplome_de(c)]
    for c in classes:
        lignes = svc.situation(c, etudiants(c, annee)) if annee else []
        c.dip_info = svc.diplome_de(c)
        c.nb_etudiants = len(lignes)
        c.nb_eligibles = sum(1 for l in lignes if l['eligible'] and not l['diplome'])
        c.nb_delivres = sum(1 for l in lignes if l['diplome'])
    return render(request, 'school_admin/directeur/diplomes/liste.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'classes': classes,
        'derniers': Diplome.objects.filter(etablissement=etablissement).select_related('eleve', 'classe')[:12],
        'total': Diplome.objects.filter(etablissement=etablissement, annule=False).count(),
        'nb_eligibles_total': sum(c.nb_eligibles for c in classes),
    })


@login_required
@require_permission('eleves_liste')
def diplomes_classe(request, classe_id):
    etablissement, annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement, niveau='superieur')
    if etablissement.type_etablissement != 'superieur':
        return HttpResponseForbidden()
    peut_modifier = isinstance(request.user, Etablissement)
    eleves = etudiants(classe, annee) if annee else []
    if request.method == 'POST':
        if not peut_modifier:
            return HttpResponseForbidden("Seul le directeur peut délivrer ou annuler une attestation.")
        action = request.POST.get('action')
        if action == 'delivrer':
            valeurs = request.POST.getlist('eleves')
            ids = {int(x) for x in valeurs if x.isascii() and x.isdigit() and len(x) < 20}
            if not ids:
                messages.warning(request, "Sélectionnez au moins un étudiant")
            elif len(ids) != len(set(valeurs)) or not ids <= {e.pk for e in eleves}:
                return HttpResponseBadRequest("Sélection invalide ou étrangère à la classe.")
            else:
                try:
                    crees = svc.delivrer(classe, [e for e in eleves if e.pk in ids], annee)
                except ValueError as exc:
                    return HttpResponseBadRequest(str(exc))
                messages.success(request, f"{len(crees)} attestation(s) provisoire(s) délivrée(s).")
        elif action == 'annuler':
            if request.POST.get('confirmation') != 'oui':
                return HttpResponseBadRequest("Confirmez l'annulation.")
            identifiant = request.POST.get('id', '')
            if not identifiant.isascii() or not identifiant.isdigit() or len(identifiant) > 18:
                return HttpResponseBadRequest("Référence invalide.")
            d = get_object_or_404(Diplome, id=identifiant,
                                  classe=classe, etablissement=etablissement)
            try:
                svc.annuler(d, request.user, request.POST.get('motif'))
            except ValueError as exc:
                return HttpResponseBadRequest(str(exc))
            messages.warning(request, f"Attestation {d.numero} annulée.")
        else:
            return HttpResponseBadRequest("Action inconnue.")
        return redirect('directeur:diplomes_classe', classe_id=classe.id)
    lignes = svc.situation(classe, eleves)
    from ..model.sync_action_model import SyncAction
    historique = list(Diplome.objects.filter(classe=classe, etablissement=etablissement, annule=True))
    traces = {t.resultat.get('diplome_id'): t for t in SyncAction.objects.filter(
        resource='diplome', action='CANCEL', resultat__etablissement_id=etablissement.pk,
        resultat__classe_id=classe.pk)}
    for document in historique:
        document.trace_annulation = traces.get(document.pk)
    return render(request, 'school_admin/directeur/diplomes/classe.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'classe': classe,
        'info': svc.diplome_de(classe), 'lignes': lignes, 'peut_modifier': peut_modifier,
        'historique': historique,
        'nb_eligibles': sum(1 for l in lignes if l['eligible'] and not l['diplome']),
        'nb_delivres': sum(1 for l in lignes if l['diplome']),
    })


@login_required
@require_permission('eleves_liste')
def imprimer_diplome(request, diplome_id):
    etablissement, _annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    d = get_object_or_404(Diplome.objects.select_related('eleve', 'classe', 'annee_scolaire'), id=diplome_id,
                          etablissement=etablissement)
    if d.annule:
        return HttpResponseForbidden("Cette attestation est annulée et ne peut plus être imprimée.")
    return render(request, 'school_admin/directeur/diplomes/attestation.html', {'d': d, 'etablissement': etablissement})
