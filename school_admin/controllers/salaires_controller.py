"""Salaires et paiements : toutes les personnes payées par l'établissement, mois par mois."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.professeur_model import Professeur
from ..services import salaires as svc
from ..services.caisse import parser_montant
from ..services.recouvrement import devise_etablissement


def _acces(request):
    from school_admin.controllers.pointage_controller import acces_direction

    return acces_direction(request, 'comptabilite_paiements')


def _mois(request):
    texte = (request.POST.get('mois') or request.GET.get('mois') or '').strip()
    try:
        annee, mois = (int(x) for x in texte.split('-')[:2])
        return date(annee, mois, 1)
    except (ValueError, TypeError):
        aujourd_hui = date.today()
        return date(aujourd_hui.year, aujourd_hui.month, 1)


def _decale(mois, n):
    total = mois.year * 12 + (mois.month - 1) + n
    return date(total // 12, total % 12 + 1, 1)


def _url(nom, *args):
    return reverse(nom, args=args)


def _comptes(etablissement):
    from ..model.finances_model import CompteTresorerie
    from ..services.finances.tresorerie import assurer_comptes_defaut

    assurer_comptes_defaut(etablissement)
    comptes = list(CompteTresorerie.objects.filter(etablissement=etablissement, actif=True, statut='ouvert'))
    # La caisse d'abord : c'est le moyen de paiement le plus courant.
    return sorted(comptes, key=lambda c: (c.type_compte != 'caisse', c.libelle))


def _compte(request, etablissement):
    from ..model.finances_model import CompteTresorerie

    pk = request.POST.get('compte_tresorerie_id')
    return CompteTresorerie.objects.filter(pk=pk, etablissement=etablissement).first() if pk else None


def _retenue(request):
    try:
        return Decimal(str(request.POST.get('retenue_pct') or '0').replace(',', '.'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


@login_required
def salaires(request):
    acces = _acces(request)
    if acces is None:
        messages.error(request, "Accès réservé à la direction et à la comptabilité.")
        return redirect('directeur:dashboard_directeur')
    etablissement, _is_directeur, _personnel = acces
    from ..utils.session_utils import get_session_active

    annee = get_session_active(request, etablissement)
    mois = _mois(request)
    onglet = request.POST.get('onglet') or request.GET.get('onglet') or 'enseignant'
    retour = f"{reverse('directeur:salaires')}?mois={mois:%Y-%m}&onglet={onglet}"

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'payer':
                compte = _compte(request, etablissement)
                if request.POST.get('type') == 'enseignant':
                    prof = get_object_or_404(Professeur, pk=request.POST.get('id'), etablissement=etablissement)
                    paie = svc.payer_enseignant(etablissement, prof, mois, annee, _retenue(request), compte, request.user)
                    messages.success(request, f"Paiement enregistré pour {prof.nom_complet}, {svc.libelle_mois(mois)} : "
                                              f"{svc.fmt(paie.montant_net)} {devise_etablissement(etablissement)} net.")
                else:
                    pers = get_object_or_404(PersonnelAdministratif, pk=request.POST.get('id'), etablissement=etablissement)
                    jour = date.fromisoformat(request.POST['date']) if request.POST.get('date') else None
                    paie = svc.payer_personnel(etablissement, pers, mois, parser_montant(request.POST.get('montant')),
                                               jour=jour, annee_scolaire=annee, user=request.user,
                                               heures=request.POST.get('heures') or None, compte_tresorerie=compte)
                    messages.success(request, f"Paiement enregistré pour {pers.nom_complet}, {svc.libelle_mois(mois)} : "
                                              f"{svc.fmt(paie.montant)} {devise_etablissement(etablissement)}.")
            elif action == 'payer_tout':
                payes, ignores = svc.payer_tout(etablissement, annee, mois, _retenue(request),
                                                _compte(request, etablissement), request.user)
                total = sum((m for _n, m in payes), Decimal('0'))
                if payes:
                    messages.success(request, f"Paiement enregistré pour {len(payes)} personne(s), {svc.libelle_mois(mois)} : "
                                              f"{svc.fmt(total)} {devise_etablissement(etablissement)} au total.")
                if ignores:
                    messages.warning(request, "Non payé(s) : " + " ; ".join(f"{n} ({r})" for n, r in ignores[:8])
                                     + (" …" if len(ignores) > 8 else ""))
                if not payes and not ignores:
                    messages.info(request, "Tout le monde est déjà payé pour ce mois.")
        except (ValueError, InvalidOperation) as exc:
            messages.error(request, str(exc))
        return redirect(retour)

    paie = svc.paie_du_mois(etablissement, annee, mois, url_resolver=_url)
    return render(request, 'school_admin/directeur/salaires/liste.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'paie': paie,
        'devise': devise_etablissement(etablissement), 'onglet': onglet if onglet in ('enseignant', 'personnel') else 'enseignant',
        'mois_precedent': _decale(mois, -1), 'mois_suivant': _decale(mois, 1), 'aujourd_hui': date.today(),
        'comptes_tresorerie': _comptes(etablissement),
    })


@login_required
def historique_salaires(request, type_personne, personne_id):
    acces = _acces(request)
    if acces is None:
        raise Http404
    etablissement = acces[0]
    if type_personne == 'enseignant':
        personne = get_object_or_404(Professeur, pk=personne_id, etablissement=etablissement)
    elif type_personne == 'personnel':
        personne = get_object_or_404(PersonnelAdministratif, pk=personne_id, etablissement=etablissement)
    else:
        raise Http404
    data = svc.historique(etablissement, type_personne, personne_id, url_resolver=_url)
    data.update({'nom': personne.nom_complet, 'devise': devise_etablissement(etablissement)})
    return JsonResponse(data)
