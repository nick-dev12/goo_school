"""Service des enseignants du supérieur : grades, service statutaire, équivalent TD, heures complémentaires."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from ..model.professeur_model import Professeur
from ..model.service_enseignant_model import SERVICE_PAR_GRADE_DEFAUT, ReglesService
from ..services import service_enseignant as svc
from ..utils.decorators_permissions import require_permission


def _acces(request):
    from ..utils.decorators_permissions import _get_user_etablissement
    from ..utils.session_utils import get_session_active

    etablissement = _get_user_etablissement(request, 'professeurs_liste')[0]
    if etablissement is None:
        return None, None
    return etablissement, get_session_active(request, etablissement)


def _devise(etablissement):
    return (getattr(etablissement, 'devise_monnaie', '') or '').strip() or 'FCFA'


def _decimal(v, mini, maxi, nom):
    try:
        d = Decimal(str(v or '0').replace(',', '.').replace(' ', ''))
    except InvalidOperation:
        raise ValueError(nom)
    if d < mini or d > maxi:
        raise ValueError(nom)
    return d


@login_required
@require_permission('professeurs_liste')
def service_enseignants(request):
    etablissement, annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    if etablissement.type_etablissement != 'superieur':
        messages.info(request, "Le service en équivalent TD concerne les établissements d'enseignement supérieur.")
        return redirect('directeur:dashboard_directeur')
    regles = ReglesService.pour(etablissement)

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'regles':
                regles.coef_cm = _decimal(request.POST.get('coef_cm'), Decimal('0.5'), Decimal('3'), 'coefficient CM')
                regles.coef_td = _decimal(request.POST.get('coef_td'), Decimal('0.5'), Decimal('3'), 'coefficient TD')
                regles.coef_tp = _decimal(request.POST.get('coef_tp'), Decimal('0.25'), Decimal('3'), 'coefficient TP')
                regles.taux_heure_complementaire = _decimal(request.POST.get('taux'), 0, Decimal('10000000'), 'taux')
                regles.semaines_annee = int(_decimal(request.POST.get('semaines_annee'), 1, 52, 'semaines'))
                regles.service_par_grade = {g: int(_decimal(request.POST.get(f'service_{g}'), 0, 600, g))
                                            for g in SERVICE_PAR_GRADE_DEFAUT}
                regles.save()
                messages.success(request, "Règles de service enregistrées.")
            elif action == 'grades':
                for p in Professeur.objects.filter(etablissement=etablissement, actif=True):
                    grade = request.POST.get(f'grade_{p.id}')
                    if grade is None:
                        continue
                    p.grade_universitaire = grade if grade in dict(Professeur.GRADE_CHOICES) else ''
                    p.service_statutaire = int(_decimal(request.POST.get(f'service_{p.id}'), 0, 600, p.nom_complet))
                    p.save(update_fields=['grade_universitaire', 'service_statutaire'])
                messages.success(request, "Grades et services enregistrés.")
        except ValueError as exc:
            messages.error(request, f"Valeur invalide : {exc}.")
        return redirect('directeur:service_enseignants')

    s = svc.synthese(etablissement, annee)
    filtre = request.GET.get('filtre', '')
    bilans = s['bilans']
    if filtre:
        bilans = [b for b in bilans if b['statut'] == filtre]
    return render(request, 'school_admin/directeur/service/liste.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'synthese': s, 'bilans': bilans,
        'filtre': filtre, 'grades': Professeur.GRADE_CHOICES, 'devise': _devise(etablissement),
        'services_grade': [(g, l, (s['regles'].service_par_grade or {}).get(g, SERVICE_PAR_GRADE_DEFAUT.get(g, 0)))
                           for g, l in Professeur.GRADE_CHOICES],
        'compteurs': {k: sum(1 for b in s['bilans'] if b['statut'] == k)
                      for k in ('complementaires', 'equilibre', 'sous_service', 'vacataire')},
    })


@login_required
@require_permission('professeurs_liste')
def service_enseignant_detail(request, professeur_id):
    etablissement, annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    p = get_object_or_404(Professeur, id=professeur_id, etablissement=etablissement)
    return render(request, 'school_admin/directeur/service/detail.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'b': svc.bilan_enseignant(p, annee),
        'regles': ReglesService.pour(etablissement), 'devise': _devise(etablissement),
    })
