"""Caisse du mois : recettes automatiques, dépenses, solde."""
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from school_admin.controllers.comptabilite_controller import ComptabiliteController
from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.compte_user import CompteUser
from school_admin.services.caisse import (
    bornes_mois,
    depenses_mois,
    parser_mois,
    parser_montant,
    recettes_mois,
    solde_mois,
    total_depenses,
    total_recettes,
)
from school_admin.services.recouvrement import devise_etablissement


def _require_caisse(request):
    from school_admin.controllers.recouvrement_controller import _require_compta

    return _require_compta(request, permission='comptabilite_voir')


class CaisseController:
    @staticmethod
    @login_required
    def caisse_mois_directeur(request):
        etablissement, is_directeur, personnel, denied = _require_caisse(request)
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        aujourdhui = date.today()
        reference = parser_mois(request.GET.get('mois'), aujourdhui)
        bornes = bornes_mois(reference)
        devise = devise_etablissement(etablissement)

        recettes = list(recettes_mois(etablissement, bornes.debut, bornes.fin)[:80])
        depenses = list(depenses_mois(etablissement, bornes.debut, bornes.fin))
        entrees = total_recettes(etablissement, bornes.debut, bornes.fin)
        sorties = total_depenses(etablissement, bornes.debut, bornes.fin)
        solde = solde_mois(etablissement, bornes.debut, bornes.fin)

        from ..utils.directeur_ui_tabs import attach_caisse_tab_context

        context = {
            'etablissement': etablissement,
            'annee_scolaire_active': annee,
            'is_directeur': is_directeur,
            'personnel': personnel,
            'devise_monnaie': devise,
            'bornes': bornes,
            'recettes': recettes,
            'depenses': depenses,
            'entrees': entrees,
            'sorties': sorties,
            'solde': solde,
            'motifs': DepenseEtablissement.MOTIF_CHOICES,
            'date_defaut': aujourdhui.isoformat(),
        }
        attach_caisse_tab_context(request, context)
        return render(
            request,
            'school_admin/directeur/caisse/caisse_mois.html',
            context,
        )

    @staticmethod
    @login_required
    @require_POST
    def ajouter_depense_directeur(request):
        etablissement, is_directeur, personnel, denied = _require_caisse(request)
        if denied:
            return denied

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        mois_retour = (request.POST.get('mois') or '').strip()

        def _retour():
            if mois_retour:
                from django.http import HttpResponseRedirect
                from django.urls import reverse

                return HttpResponseRedirect(
                    f"{reverse('directeur:caisse_mois_directeur')}?mois={mois_retour}"
                )
            return redirect('directeur:caisse_mois_directeur')

        montant = parser_montant(request.POST.get('montant'))
        if montant is None:
            messages.error(request, "Indiquez un montant supérieur à 0.")
            return _retour()

        motif = (request.POST.get('motif') or 'autre').strip()
        motifs_ok = {code for code, _label in DepenseEtablissement.MOTIF_CHOICES}
        if motif not in motifs_ok:
            motif = 'autre'

        date_brute = (request.POST.get('date_depense') or '').strip()
        try:
            date_depense = datetime.strptime(date_brute, '%Y-%m-%d').date()
        except ValueError:
            date_depense = date.today()

        enregistre_par = request.user if isinstance(request.user, CompteUser) else None
        depense = DepenseEtablissement.objects.create(
            etablissement=etablissement,
            annee_scolaire=annee,
            date_depense=date_depense,
            motif=motif,
            libelle=(request.POST.get('libelle') or '').strip()[:160],
            montant=montant,
            enregistre_par=enregistre_par,
        )
        try:
            from school_admin.services.comptabilite_generale import pont_depense

            pont_depense(depense, annee_scolaire=annee, user=enregistre_par)
        except Exception:
            pass
        from school_admin.services.realtime_helpers import emit_live

        emit_live(
            etablissement.id,
            'caisse.mise_a_jour',
            {'event': 'caisse.mise_a_jour', 'id': depense.id, 'action': 'ajoutee'},
        )
        messages.success(
            request,
            f"Dépense de {montant} {devise_etablissement(etablissement)} enregistrée.",
        )
        return _retour()

    @staticmethod
    @login_required
    @require_POST
    def supprimer_depense_directeur(request, depense_id):
        etablissement, _is_directeur, _personnel, denied = _require_caisse(request)
        if denied:
            return denied

        depense = get_object_or_404(
            DepenseEtablissement,
            pk=depense_id,
            etablissement=etablissement,
        )
        depense.delete()
        from school_admin.services.realtime_helpers import emit_live

        emit_live(
            etablissement.id,
            'caisse.mise_a_jour',
            {'event': 'caisse.mise_a_jour', 'id': depense_id, 'action': 'supprimee'},
        )
        messages.success(request, "Dépense supprimée.")
        mois_retour = (request.POST.get('mois') or '').strip()
        if mois_retour:
            from django.http import HttpResponseRedirect
            from django.urls import reverse

            return HttpResponseRedirect(
                f"{reverse('directeur:caisse_mois_directeur')}?mois={mois_retour}"
            )
        return redirect('directeur:caisse_mois_directeur')
