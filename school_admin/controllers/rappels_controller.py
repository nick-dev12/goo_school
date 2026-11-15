"""Page direction « Rappels automatiques » : réglages, état du planificateur et journal des envois."""
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from school_admin.model.etablissement_model import Etablissement
from school_admin.model.rappel_model import RappelEnvoye
from school_admin.services.rappels import moteur

ROLES = {'etablissement': 'Direction', 'personneladministratif': 'Personnel', 'professeur': 'Professeur',
         'eleve': 'Élève', 'parent': 'Parent'}


def libelle_seuil(stage):
    if stage == 'j-3':
        return 'Avant l’échéance'
    if stage == 'j-1':
        return 'La veille'
    if stage == 'j':
        return 'Le jour même'
    if stage.startswith('retard-'):
        return 'En retard'
    if stage == 'initial':
        return 'Premier rappel'
    if stage.startswith('relance-'):
        return f"Relance n° {stage.split('-')[1]}"
    if stage.startswith('nouveau-'):
        return 'Nouveaux dossiers'
    return 'Synthèse du jour'


def _heure(valeur, defaut):
    try:
        return datetime.strptime(valeur or '', '%H:%M').time()
    except ValueError:
        return defaut


def _journal(etablissement, limite=60):
    """Derniers rappels émis, avec le nom du destinataire résolu par type de compte."""
    rows = list(RappelEnvoye.objects.filter(etablissement=etablissement)
                .select_related('content_type').order_by('-created_at')[:limite])
    par_type = {}
    for row in rows:
        par_type.setdefault(row.content_type, set()).add(row.object_id)
    noms = {}
    for content_type, ids in par_type.items():
        model = content_type.model_class()
        if model is None:
            continue
        for obj in model.objects.filter(pk__in=ids):
            if content_type.model == 'etablissement':
                nom = f'{obj.directeur_prenom} {obj.directeur_nom}'.strip() or obj.nom
            else:
                nom = f"{getattr(obj, 'prenom', '')} {getattr(obj, 'nom', '')}".strip()
            noms[(content_type.pk, obj.pk)] = nom
    return [{'date': row.created_at, 'titre': row.titre, 'code': row.code,
             'seuil': libelle_seuil(row.stage), 'role': ROLES.get(row.content_type.model, ''),
             'nom': noms.get((row.content_type_id, row.object_id), '—')} for row in rows]


class RappelsController:
    @staticmethod
    @login_required
    def parametres(request):
        if not isinstance(request.user, Etablissement):
            messages.error(request, "Les réglages des rappels sont réservés à la direction.")
            return redirect('directeur:dashboard_directeur')
        etab = request.user
        params = moteur.parametres(etab.pk)
        simulation = None

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'enregistrer':
                params.actif = request.POST.get('actif') == 'on'
                params.rappel_cours_demain = request.POST.get('cours_demain') == 'on'
                params.debut_heures_calmes = _heure(request.POST.get('debut'), params.debut_heures_calmes)
                params.fin_heures_calmes = _heure(request.POST.get('fin'), params.fin_heures_calmes)
                try:
                    params.plafond_quotidien = max(1, min(10, int(request.POST.get('plafond', 4))))
                except (TypeError, ValueError):
                    pass
                actives = set(request.POST.getlist('familles'))
                params.familles_desactivees = [key for key in moteur.FAMILLES if key not in actives]
                params.save()
                messages.success(request, "Réglages des rappels enregistrés.")
                return redirect('directeur:rappels_automatiques')
            if action == 'simuler':
                stats = moteur.generer(etablissement_ids=[etab.pk], dry_run=True)
                simulation = {'stats': stats, 'lignes': [
                    {'role': ROLES.get(role, role), 'code': code, 'seuil': libelle_seuil(stage), 'titre': titre}
                    for role, _pk, code, stage, titre in stats['detail'][:80]]}
            elif action == 'envoyer':
                stats = moteur.generer(etablissement_ids=[etab.pk])
                if stats['calmes']:
                    messages.warning(request, "Heures calmes en cours : les rappels partiront à la reprise.")
                elif not params.actif:
                    messages.warning(request, "Les rappels automatiques sont désactivés pour l’établissement.")
                else:
                    messages.success(request, f"{stats['rappels']} rappel(s) envoyé(s) à l’instant.")
                return redirect('directeur:rappels_automatiques')

        now = timezone.now()
        semaine = RappelEnvoye.objects.filter(etablissement=etab, created_at__gte=now - timedelta(days=7))
        passage = params.dernier_passage
        return render(request, 'school_admin/directeur/rappels_automatiques.html', {
            'etablissement': etab, 'is_directeur': True, 'personnel': None,
            'params': params,
            'familles': [{'key': key, 'label': label, 'active': key not in (params.familles_desactivees or [])}
                         for key, label in moteur.FAMILLES.items()],
            'envoyes_semaine': semaine.count(),
            'personnes_semaine': semaine.values('content_type', 'object_id').distinct().count(),
            'planificateur_ok': bool(passage and now - passage < timedelta(hours=2)),
            'en_heures_calmes': moteur.heures_calmes(params, now),
            'journal': _journal(etab),
            'simulation': simulation,
        })
