"""Diplômes du supérieur : classes de fin de cycle, éligibilité, délivrance, impression."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from ..model.admission_model import Diplome
from ..model.classe_model import Classe
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
    classe = get_object_or_404(Classe, id=classe_id, etablissement=etablissement)
    eleves = etudiants(classe, annee) if annee else []
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delivrer':
            ids = {int(x) for x in request.POST.getlist('eleves') if x.isdigit()}
            choisis = [e for e in eleves if not ids or e.id in ids]
            crees = svc.delivrer(classe, choisis, annee)
            if crees:
                messages.success(request, f"{len(crees)} diplôme(s) délivré(s).")
            else:
                messages.warning(request, "Aucun étudiant éligible sans diplôme dans la sélection.")
        elif action == 'annuler':
            d = get_object_or_404(Diplome, id=request.POST.get('id'), etablissement=etablissement)
            svc.annuler(d)
            messages.warning(request, f"Diplôme {d.numero} annulé.")
        return redirect('directeur:diplomes_classe', classe_id=classe.id)
    lignes = svc.situation(classe, eleves)
    return render(request, 'school_admin/directeur/diplomes/classe.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'classe': classe,
        'info': svc.diplome_de(classe), 'lignes': lignes,
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
    return render(request, 'school_admin/directeur/diplomes/attestation.html', {'d': d, 'etablissement': etablissement})
