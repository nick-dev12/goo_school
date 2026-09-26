"""Contrôleur recouvrement : impayés, relances, reçus, moratoires."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from school_admin.controllers.comptabilite_controller import ComptabiliteController
from school_admin.model.compte_user import CompteUser
from school_admin.model.comptabilite_eleve_model import PaiementEleve
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.recouvrement_model import EcheanceMoratoire, Moratoire
from school_admin.services.recouvrement import (
    collecter_impayes_par_classe,
    creer_moratoire,
    devise_etablissement,
    envoyer_relance_eleve,
    moratoire_actif,
    payer_echeance_moratoire,
    resume_dette_eleve,
    verifier_rupture_moratoire,
)


def _user_as_compte(user):
    return user if isinstance(user, CompteUser) else None


def _require_compta(request, permission='comptabilite_voir'):
    result = ComptabiliteController._get_user_etablissement(request)
    if result[0] is None:
        return None, None, None, redirect('directeur:dashboard_directeur')
    etablissement, is_directeur, personnel = result
    if not is_directeur:
        from school_admin.utils.decorators_permissions import check_permission

        if not check_permission(request.user, permission):
            messages.error(request, "Vous n'avez pas l'autorisation d'accéder à la comptabilité.")
            return None, None, None, redirect('directeur:dashboard_directeur')
    return etablissement, is_directeur, personnel, None


class RecouvrementController:
    @staticmethod
    @login_required
    def liste_impayes_directeur(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:liste_comptabilite_eleves_directeur')

        for moratoire in Moratoire.objects.filter(
            etablissement=etablissement, annee_scolaire=annee, statut='actif'
        ).prefetch_related('echeances'):
            verifier_rupture_moratoire(moratoire)

        groupes = collecter_impayes_par_classe(etablissement, annee)
        total_reste = sum((g['total_reste'] for g in groupes), Decimal('0.00'))
        total_eleves = sum(len(g['eleves']) for g in groupes)
        devise = devise_etablissement(etablissement)

        from ..utils.directeur_ui_tabs import attach_impayes_tab_context

        context = {
            'etablissement': etablissement,
            'annee_scolaire_active': annee,
            'groupes': groupes,
            'total_reste': total_reste,
            'total_eleves': total_eleves,
            'devise_monnaie': devise,
            'is_directeur': is_directeur,
            'personnel': personnel,
        }
        attach_impayes_tab_context(request, context, groupes)
        return render(
            request,
            'school_admin/directeur/comptabilite/liste_impayes.html',
            context,
        )

    @staticmethod
    @login_required
    @require_POST
    def relancer_impaye_directeur(request, eleve_id=None):
        etablissement, is_directeur, personnel, denied = _require_compta(
            request, permission='comptabilite_paiements'
        )
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:liste_impayes_directeur')

        cible_eleve_id = eleve_id or request.POST.get('eleve_id')
        classe_id = request.POST.get('classe_id')
        next_url = request.POST.get('next') or 'directeur:liste_impayes_directeur'

        envoyees = 0
        if cible_eleve_id:
            try:
                inscription = InscriptionEleve.objects.select_related('eleve').get(
                    eleve_id=int(cible_eleve_id),
                    etablissement=etablissement,
                    annee_scolaire=annee,
                )
            except (InscriptionEleve.DoesNotExist, ValueError, TypeError):
                messages.error(request, "Élève introuvable pour cette année scolaire.")
                return redirect('directeur:liste_impayes_directeur')
            relance = envoyer_relance_eleve(
                inscription.eleve,
                etablissement,
                annee,
                declenche_par='manuel',
                user=_user_as_compte(request.user),
                ignorer_doublon_jour=True,
            )
            if relance:
                envoyees = 1
        elif classe_id:
            inscriptions = InscriptionEleve.objects.filter(
                etablissement=etablissement,
                annee_scolaire=annee,
                classe_id=classe_id,
                eleve__actif=True,
            ).select_related('eleve')
            for inscription in inscriptions:
                resume = resume_dette_eleve(inscription.eleve, etablissement, annee)
                if resume.reste <= 0:
                    continue
                relance = envoyer_relance_eleve(
                    inscription.eleve,
                    etablissement,
                    annee,
                    declenche_par='manuel',
                    user=_user_as_compte(request.user),
                    ignorer_doublon_jour=True,
                )
                if relance:
                    envoyees += 1
        else:
            messages.error(request, "Aucune cible de relance.")
            return redirect('directeur:liste_impayes_directeur')

        if envoyees:
            messages.success(
                request,
                f"{envoyees} relance(s) SMS / WhatsApp envoyée(s) aux familles.",
            )
        else:
            messages.warning(request, "Aucune relance envoyée (rien à recouvrer).")

        if next_url.startswith('/'):
            return redirect(next_url)
        try:
            return redirect(next_url)
        except Exception:
            return redirect('directeur:liste_impayes_directeur')

    @staticmethod
    @login_required
    def recu_paiement_directeur(request, paiement_id):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied

        paiement = get_object_or_404(
            PaiementEleve.objects.select_related(
                'eleve', 'etablissement', 'annee_scolaire', 'mensualite',
                'frais_inscription', 'frais_annexe',
            ),
            id=paiement_id,
            etablissement=etablissement,
        )
        if not paiement.numero_recu:
            from school_admin.services.recouvrement import attribuer_numero_recu

            attribuer_numero_recu(paiement)
            paiement.refresh_from_db()

        inscription = InscriptionEleve.objects.filter(
            eleve=paiement.eleve,
            etablissement=etablissement,
            annee_scolaire=paiement.annee_scolaire,
        ).select_related('classe').first()

        from school_admin.services.recouvrement import build_recu_paiement_extra_context

        extra = build_recu_paiement_extra_context(paiement)
        context = {
            'paiement': paiement,
            'eleve': paiement.eleve,
            'etablissement': etablissement,
            'annee_scolaire': paiement.annee_scolaire,
            'inscription': inscription,
            'devise_monnaie': devise_etablissement(etablissement),
            'is_directeur': is_directeur,
            'personnel': personnel,
            'auto_print': request.GET.get('auto_print') == '1',
        }
        context.update(extra)
        return render(request, 'school_admin/directeur/comptabilite/recu_paiement.html', context)

    @staticmethod
    @login_required
    def creer_moratoire_directeur(request, eleve_id):
        etablissement, is_directeur, personnel, denied = _require_compta(
            request, permission='comptabilite_paiements'
        )
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        if not annee:
            messages.warning(request, "Aucune année scolaire active trouvée.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)

        try:
            inscription = InscriptionEleve.objects.select_related('eleve', 'classe').get(
                eleve_id=eleve_id,
                etablissement=etablissement,
                annee_scolaire=annee,
            )
        except InscriptionEleve.DoesNotExist:
            messages.error(request, "Élève non inscrit dans l'année scolaire active.")
            return redirect('directeur:liste_comptabilite_eleves_directeur')

        eleve = inscription.eleve
        existant = moratoire_actif(eleve, etablissement, annee)
        if existant:
            messages.warning(request, "Un moratoire actif existe déjà pour cet élève.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve.id)

        resume = resume_dette_eleve(eleve, etablissement, annee)
        devise = devise_etablissement(etablissement)

        if request.method == 'POST':
            motif = (request.POST.get('motif') or '').strip()
            if not motif:
                messages.error(request, "Le motif du moratoire est obligatoire.")
                return redirect('directeur:creer_moratoire_directeur', eleve_id=eleve.id)

            lignes = []
            dates = request.POST.getlist('echeance_date')
            montants = request.POST.getlist('echeance_montant')
            for raw_date, raw_montant in zip(dates, montants):
                raw_date = (raw_date or '').strip()
                raw_montant = (raw_montant or '').strip()
                if not raw_date and not raw_montant:
                    continue
                try:
                    jour = datetime.strptime(raw_date, '%Y-%m-%d').date()
                    montant = Decimal(raw_montant.replace(',', '.'))
                except (ValueError, InvalidOperation, TypeError):
                    messages.error(request, "Date ou montant d'échéance invalide.")
                    return redirect('directeur:creer_moratoire_directeur', eleve_id=eleve.id)
                if montant <= 0:
                    messages.error(request, "Chaque échéance doit avoir un montant positif.")
                    return redirect('directeur:creer_moratoire_directeur', eleve_id=eleve.id)
                lignes.append({'date': jour, 'montant': montant})

            try:
                creer_moratoire(
                    eleve,
                    etablissement,
                    annee,
                    motif,
                    lignes,
                    user=_user_as_compte(request.user),
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('directeur:creer_moratoire_directeur', eleve_id=eleve.id)

            messages.success(request, "Moratoire enregistré. La nouvelle grille d'échéances est active.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve.id)

        return render(
            request,
            'school_admin/directeur/comptabilite/form_moratoire.html',
            {
                'eleve': eleve,
                'inscription': inscription,
                'etablissement': etablissement,
                'annee_scolaire': annee,
                'resume': resume,
                'devise_monnaie': devise,
                'is_directeur': is_directeur,
                'personnel': personnel,
            },
        )

    @staticmethod
    @login_required
    @require_POST
    def payer_echeance_moratoire_directeur(request, eleve_id, echeance_id):
        etablissement, is_directeur, personnel, denied = _require_compta(
            request, permission='comptabilite_paiements'
        )
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        echeance = get_object_or_404(
            EcheanceMoratoire.objects.select_related('moratoire'),
            id=echeance_id,
            moratoire__eleve_id=eleve_id,
            moratoire__etablissement=etablissement,
            moratoire__annee_scolaire=annee,
        )
        montant_raw = (request.POST.get('montant') or '').strip()
        try:
            montant = Decimal(montant_raw.replace(',', '.'))
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, "Montant invalide.")
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)

        try:
            payer_echeance_moratoire(
                echeance,
                montant,
                user=_user_as_compte(request.user),
                mode_paiement=request.POST.get('mode_paiement') or 'especes',
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)

        devise = devise_etablissement(etablissement)
        messages.success(request, f"Paiement de {montant} {devise} enregistré sur le moratoire.")
        return redirect('directeur:details_comptabilite_eleve_directeur', eleve_id=eleve_id)
