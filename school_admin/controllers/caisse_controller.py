"""Caisse du mois : recettes automatiques, dépenses, solde."""
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from school_admin.controllers.comptabilite_controller import ComptabiliteController
from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.services.caisse import (
    bornes_mois,
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


def _fournisseurs_caisse(etablissement):
    from school_admin.model.comptabilite_generale_model import FournisseurEtablissement

    return FournisseurEtablissement.objects.filter(etablissement=etablissement, actif=True).order_by('nom')


def _peut_annuler(request, is_directeur):
    if is_directeur:
        return True
    from school_admin.utils.decorators_permissions import check_permission

    return check_permission(request.user, 'comptabilite_bilans')


def _retour_caisse(mois_retour):
    if mois_retour:
        from django.http import HttpResponseRedirect
        from django.urls import reverse

        return HttpResponseRedirect(
            f"{reverse('directeur:caisse_mois_directeur')}?mois={mois_retour}"
        )
    return redirect('directeur:caisse_mois_directeur')


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

        from school_admin.model.comptabilite_generale_model import EcritureComptable

        recettes = list(recettes_mois(etablissement, bornes.debut, bornes.fin)[:80])
        depenses = list(
            DepenseEtablissement.objects.filter(
                etablissement=etablissement,
                date_depense__gte=bornes.debut,
                date_depense__lte=bornes.fin,
            ).annotate(
                ecrite=Exists(
                    EcritureComptable.objects.filter(
                        etablissement=etablissement,
                        source='depense',
                        source_id=OuterRef('pk'),
                    )
                )
            )
        )
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
            'peut_annuler': _peut_annuler(request, is_directeur),
            'fournisseurs': _fournisseurs_caisse(etablissement),
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

        from school_admin.model.comptabilite_generale_model import FournisseurEtablissement
        from school_admin.services.finances.operations import enregistrer_sortie

        fournisseur = None
        fournisseur_id = (request.POST.get('fournisseur_id') or '').strip()
        if fournisseur_id:
            fournisseur = FournisseurEtablissement.objects.filter(
                pk=fournisseur_id, etablissement=etablissement, actif=True
            ).first()
            if fournisseur is None:
                messages.error(request, "Fournisseur introuvable pour cette école.")
                return _retour()

        try:
            depense, ecriture = enregistrer_sortie(
                etablissement,
                date_depense,
                motif,
                montant,
                libelle=(request.POST.get('libelle') or '').strip(),
                annee_scolaire=annee,
                user=request.user,
                fichier=request.FILES.get('justificatif'),
                fournisseur=fournisseur,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return _retour()
        from school_admin.services.realtime_helpers import emit_live

        emit_live(
            etablissement.id,
            'caisse.mise_a_jour',
            {'event': 'caisse.mise_a_jour', 'id': depense.id, 'action': 'ajoutee'},
        )
        if ecriture is None:
            messages.warning(
                request,
                "Sortie enregistrée. L'écriture comptable n'a pas été générée : "
                "le plan de comptes n'est pas prêt.",
            )
        else:
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
        if depense.statut != 'brouillon':
            messages.error(
                request,
                "Une sortie validée ne se supprime pas. Annulez-la avec un motif.",
            )
            mois_retour = (request.POST.get('mois') or '').strip()
            if mois_retour:
                from django.http import HttpResponseRedirect
                from django.urls import reverse

                return HttpResponseRedirect(
                    f"{reverse('directeur:caisse_mois_directeur')}?mois={mois_retour}"
                )
            return redirect('directeur:caisse_mois_directeur')
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

    @staticmethod
    @login_required
    @require_POST
    def annuler_depense_directeur(request, depense_id):
        etablissement, is_directeur, _personnel, denied = _require_caisse(request)
        if denied:
            return denied
        mois_retour = (request.POST.get('mois') or '').strip()
        if not _peut_annuler(request, is_directeur):
            messages.error(request, "Vous ne pouvez pas annuler une sortie.")
            return _retour_caisse(mois_retour)
        depense = get_object_or_404(
            DepenseEtablissement,
            pk=depense_id,
            etablissement=etablissement,
        )
        from school_admin.services.finances.operations import annuler_sortie

        try:
            annuler_sortie(depense, request.POST.get('motif'), user=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return _retour_caisse(mois_retour)
        from school_admin.services.realtime_helpers import emit_live

        emit_live(
            etablissement.id,
            'caisse.mise_a_jour',
            {'event': 'caisse.mise_a_jour', 'id': depense.id, 'action': 'annulee'},
        )
        messages.success(request, "Sortie annulée. Elle reste dans l'historique.")
        return _retour_caisse(mois_retour)
