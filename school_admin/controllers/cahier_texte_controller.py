"""Cahier de texte : espace enseignant, rédaction par Aria, consultation direction et élèves."""
import json
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from school_admin.model.cahier_texte_model import CahierTexte
from school_admin.model.classe_model import Classe
from school_admin.model.matiere_model import Matiere
from school_admin.model.professeur_model import Professeur
from school_admin.services import cahier_texte as ct


def _date(valeur, defaut=None):
    try:
        return date.fromisoformat((valeur or '')[:10])
    except ValueError:
        return defaut


def _heure(valeur):
    try:
        return time.fromisoformat(valeur) if valeur else None
    except ValueError:
        return None


def _annee(request, etablissement):
    from school_admin.utils.session_utils import get_session_active

    return get_session_active(request, etablissement) if etablissement else None


def _paires_prof(professeur, annee):
    """Classes et matières du professeur d'après l'emploi du temps publié."""
    from school_admin.services.pointage import creneaux_publies

    paires = {}
    for c in creneaux_publies(professeur.etablissement, annee, professeur=professeur):
        classe = getattr(c.emploi_du_temps, 'classe', None)
        if classe is None:
            continue
        paires.setdefault(classe.id, {'classe': classe, 'matieres': {}})
        if c.matiere_id:
            paires[classe.id]['matieres'][c.matiere_id] = c.matiere
    return sorted(paires.values(), key=lambda p: p['classe'].nom)


def _serialiser(e):
    return {
        'id': e.id, 'classe_id': e.classe_id, 'matiere_id': e.matiere_id, 'date': e.date.isoformat(),
        'heure_debut': e.heure_debut.strftime('%H:%M') if e.heure_debut else '',
        'heure_fin': e.heure_fin.strftime('%H:%M') if e.heure_fin else '',
        'titre': e.titre, 'objectifs': e.objectifs, 'contenu': e.contenu, 'travail_a_faire': e.travail_a_faire,
        'date_travail': e.date_travail.isoformat() if e.date_travail else '', 'observations': e.observations,
        'statut': e.statut, 'modifiable': e.modifiable, 'classe': e.classe.nom,
        'matiere': getattr(e.matiere, 'nom', ''),
    }


class CahierTexteController:
    # ------------------------------------------------------------------ enseignant
    @staticmethod
    @login_required
    def enseignant(request):
        prof = request.user
        if not isinstance(prof, Professeur):
            messages.error(request, "Cette page est réservée aux enseignants.")
            return redirect('school_admin:connexion_compte_user')
        etab = prof.etablissement
        annee = _annee(request, etab)
        if request.method == 'POST':
            action = request.POST.get('action')
            try:
                if action == 'enregistrer':
                    entree = None
                    if request.POST.get('entree_id'):
                        entree = get_object_or_404(CahierTexte, pk=request.POST['entree_id'], professeur=prof)
                    classe = get_object_or_404(Classe, pk=request.POST.get('classe_id'), etablissement=etab)
                    matiere = Matiere.objects.filter(pk=request.POST.get('matiere_id') or 0).first()
                    jour = _date(request.POST.get('date'))
                    if jour is None:
                        raise ValueError("Indiquez la date du cours.")
                    if jour > timezone.localdate():
                        raise ValueError("On ne remplit pas le cahier de texte d'un cours à venir.")
                    e = ct.enregistrer(prof, classe, jour, request.POST, matiere=matiere,
                                       debut=_heure(request.POST.get('heure_debut')),
                                       fin=_heure(request.POST.get('heure_fin')), entree=entree,
                                       annee_scolaire=annee, redige_par_ia=request.POST.get('ia') == '1')
                    if e.statut == 'valide':
                        messages.success(request, f"« {e.titre} » validé et envoyé à la direction ({classe.nom}).")
                    else:
                        messages.success(request, f"« {e.titre} » enregistré en brouillon : vous pouvez encore le modifier.")
                elif action == 'valider':
                    e = get_object_or_404(CahierTexte, pk=request.POST.get('entree_id'), professeur=prof)
                    ct.valider(e)
                    messages.success(request, f"« {e.titre} » validé et envoyé à la direction.")
                elif action == 'supprimer':
                    e = get_object_or_404(CahierTexte, pk=request.POST.get('entree_id'), professeur=prof)
                    ct.supprimer(e)
                    messages.success(request, "Brouillon supprimé.")
                elif action == 'demander_modification':
                    e = get_object_or_404(CahierTexte, pk=request.POST.get('entree_id'), professeur=prof)
                    ct.demander_modification(e, prof, request.POST.get('motif'))
                    messages.success(request, "Demande de modification envoyée à la direction.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(request.get_full_path())

        today = timezone.localdate()
        filtre_classe = request.GET.get('classe') or ''
        cours = ct.cours_du_professeur(prof, today - timedelta(days=21), today, annee)
        maintenant = timezone.localtime().time()
        a_renseigner = [c for c in cours if not c['entree'] and (c['date'] < today or c['debut'] <= maintenant)][:8]
        aujourd_hui = [c for c in cours if c['date'] == today]
        aujourd_hui.sort(key=lambda c: c['debut'])
        qs = CahierTexte.objects.filter(professeur=prof).select_related('classe', 'matiere')
        if filtre_classe:
            qs = qs.filter(classe_id=filtre_classe)
        entrees = list(qs.order_by('-date', '-heure_debut')[:40])
        groupes = []
        for e in entrees:
            if not groupes or groupes[-1]['date'] != e.date:
                groupes.append({'date': e.date, 'entrees': []})
            groupes[-1]['entrees'].append(e)
        paires = _paires_prof(prof, annee)
        ns = 'enseignant_primaire' if request.resolver_match.namespace == 'enseignant_primaire' else 'enseignant'
        return render(request, 'school_admin/enseignant/cahier_texte.html', {
            'professeur': prof, 'etablissement': etab, 'annee_scolaire_active': annee, 'today': today, 'ns': ns,
            'lib': ct.libelles(etab), 'stats': ct.stats_professeur(prof, annee), 'a_renseigner': a_renseigner,
            'aujourd_hui': aujourd_hui, 'groupes': groupes, 'paires': paires, 'filtre_classe': filtre_classe,
            'entrees_json': {e.id: _serialiser(e) for e in entrees},
            'paires_json': [{'id': p['classe'].id, 'nom': p['classe'].nom,
                             'matieres': [{'id': m.id, 'nom': m.nom} for m in p['matieres'].values()]} for p in paires],
            'ia_disponible': bool(getattr(settings, 'GEMINI_API_KEY', '')),
            'aide_validation': ct.AIDE_VALIDATION,
        })

    @staticmethod
    @login_required
    @require_POST
    def rediger(request):
        prof = request.user
        if not isinstance(prof, Professeur):
            return JsonResponse({'ok': False, 'erreur': "Réservé aux enseignants."}, status=403)
        try:
            payload = json.loads(request.body or '{}')
        except ValueError:
            payload = request.POST
        classe = Classe.objects.filter(pk=payload.get('classe_id') or 0, etablissement=prof.etablissement).first()
        if classe is None:
            return JsonResponse({'ok': False, 'erreur': "Choisissez d'abord la classe."}, status=400)
        matiere = Matiere.objects.filter(pk=payload.get('matiere_id') or 0).first()
        jour = _date(payload.get('date'), timezone.localdate())
        debut, fin = _heure(payload.get('heure_debut')), _heure(payload.get('heure_fin'))
        duree = ((fin.hour * 60 + fin.minute) - (debut.hour * 60 + debut.minute)) if debut and fin else None
        try:
            brouillon = ct.rediger(prof, classe, matiere, jour, payload.get('notes') or '', duree)
        except ValueError as exc:
            return JsonResponse({'ok': False, 'erreur': str(exc)}, status=503)
        return JsonResponse({'ok': True, 'proposition': brouillon})

    # ------------------------------------------------------------------ direction
    @staticmethod
    @login_required
    def direction(request):
        from school_admin.controllers.pointage_controller import acces_direction

        acces = acces_direction(request, 'professeurs_detail') or acces_direction(request, 'pointage_controle')
        if acces is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        etab, is_directeur, personnel = acces
        if request.method == 'POST' and request.POST.get('action') == 'traiter_demande':
            e = get_object_or_404(CahierTexte, pk=request.POST.get('entree_id'), etablissement=etab)
            try:
                ct.traiter_demande(e, request.user, request.POST.get('decision') == 'accepter',
                                   request.POST.get('reponse', ''))
                messages.success(request, f"Demande de {e.professeur.nom_complet} "
                                          f"{'acceptée : l’entrée redevient modifiable' if e.demande_statut == 'acceptee' else 'refusée'}.")
            except ValueError as exc:
                messages.error(request, str(exc))
            suivant = request.POST.get('next') or ''
            if not url_has_allowed_host_and_scheme(suivant, {request.get_host()}, request.is_secure()):
                suivant = request.get_full_path()
            return redirect(suivant)
        today = timezone.localdate()
        classe_id = request.GET.get('classe') or ''
        prof_id = request.GET.get('professeur') or ''
        qs = CahierTexte.objects.filter(etablissement=etab, statut='valide').select_related('classe', 'matiere', 'professeur')
        if classe_id:
            qs = qs.filter(classe_id=classe_id)
        if prof_id:
            qs = qs.filter(professeur_id=prof_id)
        entrees = list(qs.order_by('-date', '-heure_debut')[:50])
        annee = _annee(request, etab)
        suivi = []
        for p in Professeur.objects.filter(etablissement=etab, actif=True).order_by('nom', 'prenom'):
            s = ct.stats_professeur(p, annee, jours=14)
            if s['cours']:
                suivi.append({'professeur': p, 'stats': s})
        suivi.sort(key=lambda r: (r['stats']['taux'] if r['stats']['taux'] is not None else 101))
        total = sum(r['stats']['cours'] for r in suivi)
        faits = sum(r['stats']['renseignes'] for r in suivi)
        return render(request, 'school_admin/directeur/cahier_texte/direction.html', {
            'etablissement': etab, 'is_directeur': is_directeur, 'personnel': personnel,
            'annee_scolaire_active': annee, 'today': today, 'entrees': entrees, 'suivi': suivi,
            'taux_global': round(faits / total * 100) if total else None, 'cours_total': total, 'faits': faits,
            'classes': Classe.objects.filter(etablissement=etab, actif=True).order_by('nom'),
            'professeurs': Professeur.objects.filter(etablissement=etab, actif=True).order_by('nom'),
            'classe_id': classe_id, 'prof_id': prof_id, 'lib': ct.libelles(etab),
            'entrees_mois': CahierTexte.objects.filter(etablissement=etab, statut='valide',
                                                       date__gte=today.replace(day=1)).count(),
            'demandes': CahierTexte.objects.filter(etablissement=etab, demande_statut='en_attente')
                                           .select_related('classe', 'matiere', 'professeur').order_by('demande_le'),
            'par_ia': CahierTexte.objects.filter(etablissement=etab, statut='valide', redige_par_ia=True).count(),
        })

    # ------------------------------------------------------------------ élève / parent
    @staticmethod
    @login_required
    def eleve(request):
        from school_admin.personal_views.eleve_view import get_classe_eleve_active, get_eleve_from_request

        eleve, est_parent = get_eleve_from_request(request)
        if not eleve:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        annee = _annee(request, eleve.etablissement)
        classe = get_classe_eleve_active(eleve, annee, eleve.etablissement)
        matiere_id = request.GET.get('matiere') or ''
        qs = CahierTexte.objects.filter(classe=classe, statut='valide').select_related('matiere', 'professeur') \
            if classe else CahierTexte.objects.none()
        matieres = sorted({e.matiere for e in qs if e.matiere_id}, key=lambda m: m.nom)
        if matiere_id:
            qs = qs.filter(matiere_id=matiere_id)
        entrees = list(qs.order_by('-date', '-heure_debut')[:40])
        today = timezone.localdate()
        a_faire = list(CahierTexte.objects.filter(classe=classe, statut='valide', date_travail__gte=today)
                       .exclude(travail_a_faire='').select_related('matiere').order_by('date_travail')[:8]) if classe else []
        groupes = []
        for e in entrees:
            if not groupes or groupes[-1]['date'] != e.date:
                groupes.append({'date': e.date, 'entrees': []})
            groupes[-1]['entrees'].append(e)
        return render(request, 'school_admin/eleve/cahier_texte_eleve.html', {
            'eleve': eleve, 'est_parent': est_parent, 'classe': classe, 'classe_active': classe,
            'annee_scolaire_active': annee, 'groupes': groupes, 'matieres': matieres, 'matiere_id': matiere_id,
            'a_faire': a_faire, 'today': today, 'lib': ct.libelles(eleve.etablissement),
        })
