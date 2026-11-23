"""Courriers libres (lettre, note de service, compte rendu) rédigés avec l'assistant, imprimables avec l'en-tête."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from school_admin.model.rappel_model import CourrierEtablissement


def _acces(request):
    from school_admin.controllers.pointage_controller import acces_direction

    return acces_direction(request, 'administrative_voir')


class CourrierController:
    @staticmethod
    @login_required
    def liste(request):
        acces = _acces(request)
        if acces is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        etab, is_directeur, personnel = acces
        return render(request, 'school_admin/directeur/courriers/liste.html', {
            'etablissement': etab, 'is_directeur': is_directeur, 'personnel': personnel,
            'courriers': CourrierEtablissement.objects.filter(etablissement=etab)[:100],
        })

    @staticmethod
    @login_required
    def detail(request, courrier_id):
        acces = _acces(request)
        if acces is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        etab, _is_directeur, _personnel = acces
        courrier = get_object_or_404(CourrierEtablissement, pk=courrier_id, etablissement=etab)
        return render(request, 'school_admin/directeur/courriers/imprimer.html', {
            'etablissement': etab, 'courrier': courrier,
            'paragraphes': [p.strip() for p in courrier.contenu.split('\n\n') if p.strip()],
        })

    @staticmethod
    @login_required
    @require_POST
    def supprimer(request, courrier_id):
        acces = _acces(request)
        if acces is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('directeur:dashboard_directeur')
        etab = acces[0]
        courrier = get_object_or_404(CourrierEtablissement, pk=courrier_id, etablissement=etab)
        courrier.delete()
        messages.success(request, "Courrier supprimé.")
        return redirect('directeur:courriers')
