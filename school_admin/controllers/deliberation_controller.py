"""
Délibérations du supérieur (LMD) : liste, jury, points de jury, clôture et procès-verbal.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ..model.classe_model import Classe
from ..model.deliberation_model import DecisionJury, Deliberation
from ..model.periode_model import PeriodeScolaire
from ..services import deliberations as svc
from ..services import examens as moteur
from ..utils.decorators_permissions import require_permission


def _contexte_acces(request):
    from ..utils.decorators_permissions import _get_user_etablissement
    from ..utils.session_utils import get_session_active

    etablissement = _get_user_etablissement(request, 'examens_voir')[0]
    if etablissement is None:
        return None, None
    return etablissement, get_session_active(request, etablissement)


def _nom_utilisateur(request):
    u = request.user
    return getattr(u, 'nom_complet', None) or getattr(u, 'nom', None) or str(u)


@login_required
@require_permission('examens_voir')
def liste_deliberations(request):
    etablissement, annee = _contexte_acces(request)
    if etablissement is None:
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')
    if etablissement.type_etablissement != 'superieur':
        messages.info(request, "Les délibérations de jury concernent les établissements d'enseignement supérieur.")
        return redirect('directeur:gestion_examens')
    if annee is None:
        messages.error(request, "Aucune année académique active.")
        return redirect('directeur:gestion_examens')

    classes = list(Classe.objects.filter(etablissement=etablissement, actif=True, niveau='superieur')
                   .select_related('department').order_by('department__nom', 'nom'))
    if request.method == 'POST':
        classe = get_object_or_404(Classe, id=request.POST.get('classe_id'), etablissement=etablissement)
        periode = None
        if request.POST.get('portee') != 'annuelle':
            periode = get_object_or_404(PeriodeScolaire, id=request.POST.get('periode_id'), etablissement=etablissement)
        session = request.POST.get('session') or Deliberation.SESSION_NORMALE
        if session not in dict(Deliberation.SESSION_CHOICES):
            session = Deliberation.SESSION_NORMALE
        d, cree = svc.creer(etablissement, classe, annee, periode, session)
        if cree:
            messages.success(request, f"Délibération ouverte pour {classe.nom} — {d.libelle_portee}. "
                                      f"Vérifiez les résultats puis attribuez les points de jury.")
        else:
            messages.info(request, "Cette délibération existe déjà : la voici.")
        return redirect('directeur:detail_deliberation', deliberation_id=d.id)

    deliberations = list(Deliberation.objects.filter(etablissement=etablissement, annee_scolaire=annee)
                         .select_related('classe', 'periode').order_by('classe__nom', 'periode__date_debut'))
    for d in deliberations:
        d.stats = svc.statistiques(d)
    periodes = list(PeriodeScolaire.objects.filter(etablissement=etablissement, annee_scolaire_fk=annee)
                    .order_by('niveau_lmd', 'date_debut'))
    context = {
        'etablissement': etablissement,
        'annee_scolaire_active': annee,
        'classes': classes,
        'periodes': periodes,
        'deliberations': deliberations,
        'nb_cloturees': sum(1 for d in deliberations if d.est_cloturee),
        'regles_examen': moteur.regles(etablissement),
        'sessions': Deliberation.SESSION_CHOICES,
    }
    return render(request, 'school_admin/directeur/deliberations/liste.html', context)


def _get_deliberation(request, deliberation_id):
    etablissement, annee = _contexte_acces(request)
    if etablissement is None:
        return None, None
    return etablissement, get_object_or_404(
        Deliberation.objects.select_related('classe', 'periode', 'annee_scolaire', 'classe__department'),
        id=deliberation_id, etablissement=etablissement)


@login_required
@require_permission('examens_voir')
def detail_deliberation(request, deliberation_id):
    etablissement, d = _get_deliberation(request, deliberation_id)
    if d is None:
        return redirect('directeur:dashboard_directeur')
    url = reverse('directeur:detail_deliberation', args=[d.id])

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'recalculer':
                svc.preparer(d)
                messages.success(request, "Résultats recalculés à partir des moyennes enregistrées.")
            elif action == 'points':
                saisies = {}
                for dj in d.decisions.all():
                    saisies[dj.eleve_id] = (request.POST.get(f'points_{dj.eleve_id}', '0'),
                                            request.POST.get(f'motif_{dj.eleve_id}', ''))
                erreurs = svc.enregistrer_points(d, saisies)
                for e in erreurs:
                    messages.error(request, e)
                if not erreurs:
                    messages.success(request, "Points de jury enregistrés ; décisions mises à jour.")
            elif action == 'jury':
                if d.est_cloturee:
                    raise svc.DeliberationErreur("La délibération est clôturée.")
                d.president = request.POST.get('president', '').strip()[:150]
                d.membres = request.POST.get('membres', '').strip()
                d.observations = request.POST.get('observations', '').strip()
                date_txt = request.POST.get('date_deliberation') or ''
                if date_txt:
                    from datetime import date
                    d.date_deliberation = date.fromisoformat(date_txt)
                d.save()
                messages.success(request, "Composition du jury enregistrée.")
            elif action == 'cloturer':
                if not d.president:
                    raise svc.DeliberationErreur("Indiquez le président du jury avant de clôturer.")
                svc.cloturer(d, _nom_utilisateur(request))
                messages.success(request, "Délibération clôturée : décisions publiées sur les relevés, UE acquises "
                                          "capitalisées et notes verrouillées.")
            elif action == 'rouvrir':
                svc.rouvrir(d)
                messages.warning(request, "Délibération rouverte : les notes sont de nouveau modifiables.")
        except (svc.DeliberationErreur, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect(url)

    if not d.est_cloturee and not d.decisions.exists():
        svc.preparer(d)
    decisions = list(d.decisions.select_related('eleve').order_by('eleve__nom', 'eleve__prenom'))
    filtre = request.GET.get('filtre', '')
    if filtre == 'dettes':
        decisions = [x for x in decisions if x.dettes]
    elif filtre in dict(DecisionJury.DECISION_CHOICES):
        decisions = [x for x in decisions if x.decision == filtre]
    context = {
        'etablissement': etablissement,
        'deliberation': d,
        'decisions': decisions,
        'stats': svc.statistiques(d),
        'regles_examen': moteur.regles(etablissement),
        'filtre': filtre,
        'decision_choices': DecisionJury.DECISION_CHOICES,
    }
    return render(request, 'school_admin/directeur/deliberations/detail.html', context)


@login_required
@require_permission('examens_voir')
def pv_deliberation(request, deliberation_id):
    etablissement, d = _get_deliberation(request, deliberation_id)
    if d is None:
        return redirect('directeur:dashboard_directeur')
    decisions = list(d.decisions.select_related('eleve').order_by('eleve__nom', 'eleve__prenom'))
    context = {
        'etablissement': etablissement,
        'deliberation': d,
        'decisions': decisions,
        'stats': svc.statistiques(d),
        'regles_examen': moteur.regles(etablissement),
        'date_impression': timezone.localdate(),
    }
    return render(request, 'school_admin/directeur/deliberations/pv.html', context)
