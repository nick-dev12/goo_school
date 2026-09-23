"""Comptabilité générale : hub, paramétrage, journaux, états, trésorerie, fournisseurs."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from school_admin.controllers.comptabilite_controller import ComptabiliteController
from school_admin.controllers.recouvrement_controller import _require_compta
from school_admin.model.compte_user import CompteUser
from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve, PaiementEleve
from school_admin.model.comptabilite_generale_model import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    FactureFournisseur,
    FournisseurEtablissement,
    Immobilisation,
    JournalComptable,
    LigneEcriture,
    MouvementTresorerie,
    PeriodeComptable,
)
from school_admin.services.comptabilite_generale import (
    enregistrer_regime_comptable,
    ensure_exercice,
    ensure_journaux,
    ensure_plan_comptable,
    get_or_create_parametres_comptabilite,
    kpi_cg,
    pont_amortissement,
    pont_virement_interne,
    regime_est_verrouille,
    soldes_par_compte,
    synthese_bilan,
)
from school_admin.services.recouvrement import collecter_impayes_par_classe, devise_etablissement


def _user(request):
    return request.user if isinstance(request.user, CompteUser) else None


class ComptabiliteGeneraleController:
    @staticmethod
    def _exercice(etablissement, annee):
        return ensure_exercice(etablissement, annee)

    @staticmethod
    @login_required
    def hub(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)
        kpis = kpi_cg(etablissement, annee)
        synthese = synthese_bilan(etablissement, exercice)
        params = get_or_create_parametres_comptabilite(etablissement)
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/hub.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'exercice': exercice,
                'kpis': kpis,
                'synthese': synthese,
                'devise_monnaie': devise_etablissement(etablissement),
                'nb_comptes': CompteComptable.objects.filter(etablissement=etablissement).count(),
                'nb_journaux': JournalComptable.objects.filter(etablissement=etablissement).count(),
                'nb_periodes': exercice.periodes.count(),
                'regime_comptable': params.regime_comptable,
            },
        )

    @staticmethod
    @login_required
    def plan_comptable(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)

        if request.method == 'POST' and request.POST.get('action') == 'ajouter_compte':
            numero = (request.POST.get('numero') or '').strip()
            libelle = (request.POST.get('libelle') or '').strip()
            classe = (request.POST.get('classe') or (numero[:1] if numero else '6')).strip()[:1]
            nature = (request.POST.get('nature') or 'charge').strip()
            if numero and libelle:
                CompteComptable.objects.get_or_create(
                    etablissement=etablissement,
                    numero=numero,
                    defaults={'libelle': libelle, 'classe': classe, 'nature': nature},
                )
                messages.success(request, f"Compte {numero} ajouté.")
            return redirect('directeur:cg_plan_comptable')

        comptes = CompteComptable.objects.filter(etablissement=etablissement, actif=True)
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/plan_comptable.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'exercice': exercice,
                'comptes': comptes,
                'annee_scolaire_active': annee,
            },
        )

    @staticmethod
    @login_required
    def journaux(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)
        journaux = JournalComptable.objects.filter(etablissement=etablissement).prefetch_related(
            Prefetch(
                'ecritures',
                queryset=EcritureComptable.objects.filter(exercice=exercice).order_by('-date_ecriture'),
                to_attr='dernieres_ecritures',
            )
        )
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/journaux.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'exercice': exercice,
                'journaux': journaux,
                'annee_scolaire_active': annee,
            },
        )

    @staticmethod
    @login_required
    def exercices(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'verrouiller':
                periode = get_object_or_404(PeriodeComptable, pk=request.POST.get('periode_id'), exercice=exercice)
                periode.verrouillee = True
                periode.date_verrouillage = timezone.now()
                periode.save(update_fields=['verrouillee', 'date_verrouillage'])
                messages.success(request, f"Période « {periode.libelle} » verrouillée.")
            elif action == 'deverrouiller':
                periode = get_object_or_404(PeriodeComptable, pk=request.POST.get('periode_id'), exercice=exercice)
                periode.verrouillee = False
                periode.date_verrouillage = None
                periode.save(update_fields=['verrouillee', 'date_verrouillage'])
                messages.success(request, f"Période « {periode.libelle} » déverrouillée.")
            elif action == 'cloturer' and exercice.statut == 'ouvert':
                exercice.statut = 'cloture'
                exercice.date_cloture = timezone.now()
                exercice.save(update_fields=['statut', 'date_cloture'])
                messages.success(request, "Exercice clôturé.")
            elif action == 'rouvrir' and exercice.statut == 'cloture':
                exercice.statut = 'ouvert'
                exercice.date_cloture = None
                exercice.save(update_fields=['statut', 'date_cloture'])
                messages.success(request, "Exercice rouvert.")
            elif action == 'enregistrer_regime':
                nouveau = (request.POST.get('regime_comptable') or '').strip()
                try:
                    _, changed = enregistrer_regime_comptable(
                        etablissement, nouveau, annee_scolaire=annee
                    )
                    if changed:
                        messages.success(request, "Régime comptable enregistré.")
                    else:
                        messages.info(request, "Le régime comptable est déjà à jour.")
                except ValueError as exc:
                    messages.error(request, str(exc))
            return redirect('directeur:cg_exercices')

        params = get_or_create_parametres_comptabilite(etablissement)
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/exercices.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'exercice': exercice,
                'periodes_mois': exercice.periodes.filter(type_periode='mois'),
                'periodes_autres': exercice.periodes.exclude(type_periode='mois'),
                'annee_scolaire_active': annee,
                'parametres_comptabilite': params,
                'regime_comptable': params.regime_comptable,
                'regime_verrouille': regime_est_verrouille(etablissement, annee),
            },
        )

    @staticmethod
    @login_required
    def clients(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        groupes = collecter_impayes_par_classe(etablissement, annee)
        today = timezone.now().date()
        buckets = {'j0_30': Decimal('0'), 'j31_60': Decimal('0'), 'j61_90': Decimal('0'), 'j90': Decimal('0')}
        nb_creances = 0
        for groupe in groupes:
            for item in groupe.get('eleves', []):
                resume = item.get('resume')
                reste = getattr(resume, 'reste', Decimal('0')) or Decimal('0')
                if reste <= 0:
                    continue
                nb_creances += 1
                echeance = getattr(resume, 'prochaine_echeance', None) or today
                if hasattr(echeance, 'date'):
                    echeance = echeance.date()
                age = (today - echeance).days if echeance else 0
                if age <= 30:
                    buckets['j0_30'] += reste
                elif age <= 60:
                    buckets['j31_60'] += reste
                elif age <= 90:
                    buckets['j61_90'] += reste
                else:
                    buckets['j90'] += reste
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/clients.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'groupes': groupes,
                'buckets': buckets,
                'nb_creances': nb_creances,
                'devise_monnaie': devise_etablissement(etablissement),
            },
        )

    @staticmethod
    @login_required
    def fournisseurs(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        ComptabiliteGeneraleController._exercice(etablissement, annee)

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'ajouter_fournisseur':
                nom = (request.POST.get('nom') or '').strip()
                if nom:
                    FournisseurEtablissement.objects.get_or_create(
                        etablissement=etablissement,
                        nom=nom,
                        defaults={
                            'telephone': (request.POST.get('telephone') or '').strip(),
                            'email': (request.POST.get('email') or '').strip(),
                        },
                    )
                    messages.success(request, "Fournisseur enregistré.")
            elif action == 'ajouter_facture':
                try:
                    fournisseur = FournisseurEtablissement.objects.get(
                        pk=request.POST.get('fournisseur_id'), etablissement=etablissement
                    )
                    montant = Decimal(str(request.POST.get('montant') or '0').replace(',', '.'))
                    date_facture = datetime.strptime(request.POST.get('date_facture'), '%Y-%m-%d').date()
                    date_echeance = datetime.strptime(request.POST.get('date_echeance'), '%Y-%m-%d').date()
                    FactureFournisseur.objects.create(
                        etablissement=etablissement,
                        fournisseur=fournisseur,
                        numero=(request.POST.get('numero') or '').strip()[:40],
                        libelle=(request.POST.get('libelle') or '').strip()[:200],
                        date_facture=date_facture,
                        date_echeance=date_echeance,
                        montant=montant,
                    )
                    messages.success(request, "Facture fournisseur enregistrée.")
                except (FournisseurEtablissement.DoesNotExist, ValueError, InvalidOperation):
                    messages.error(request, "Données de facture invalides.")
            elif action == 'ajouter_immo':
                libelle = (request.POST.get('libelle') or '').strip()
                try:
                    valeur = Decimal(str(request.POST.get('valeur_origine') or '0').replace(',', '.'))
                    duree = int(request.POST.get('duree_annees') or 5)
                    date_acq = datetime.strptime(request.POST.get('date_acquisition'), '%Y-%m-%d').date()
                except (ValueError, InvalidOperation):
                    messages.error(request, "Données d'immobilisation invalides.")
                    return redirect('directeur:cg_fournisseurs')
                if libelle and valeur > 0:
                    Immobilisation.objects.create(
                        etablissement=etablissement,
                        libelle=libelle,
                        categorie=request.POST.get('categorie') or 'autre',
                        date_acquisition=date_acq,
                        valeur_origine=valeur,
                        duree_annees=max(duree, 1),
                    )
                    messages.success(request, "Immobilisation enregistrée.")
            elif action == 'amortir':
                immo = get_object_or_404(
                    Immobilisation, pk=request.POST.get('immo_id'), etablissement=etablissement
                )
                try:
                    pont_amortissement(immo, annee_scolaire=annee, user=_user(request))
                    messages.success(request, f"Dotation d'amortissement générée pour {immo.libelle}.")
                except Exception as exc:
                    messages.error(request, str(exc))
            return redirect('directeur:cg_fournisseurs')

        return render(
            request,
            'school_admin/directeur/comptabilite_generale/fournisseurs.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'fournisseurs': FournisseurEtablissement.objects.filter(etablissement=etablissement, actif=True),
                'factures': FactureFournisseur.objects.filter(etablissement=etablissement).select_related('fournisseur')[:80],
                'immobilisations': Immobilisation.objects.filter(etablissement=etablissement, actif=True),
                'devise_monnaie': devise_etablissement(etablissement),
            },
        )

    @staticmethod
    @login_required
    def tresorerie(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'virement':
                try:
                    montant = Decimal(str(request.POST.get('montant') or '0').replace(',', '.'))
                    date_mvt = datetime.strptime(request.POST.get('date_mouvement'), '%Y-%m-%d').date()
                except (ValueError, InvalidOperation):
                    messages.error(request, "Montant ou date invalide.")
                    return redirect('directeur:cg_tresorerie')
                if montant > 0:
                    try:
                        with transaction.atomic():
                            mvt = MouvementTresorerie.objects.create(
                                etablissement=etablissement,
                                type_mouvement='virement_interne',
                                date_mouvement=date_mvt,
                                montant=montant,
                                libelle=(request.POST.get('libelle') or 'Virement caisse vers banque')[:200],
                            )
                            pont_virement_interne(mvt, annee_scolaire=annee, user=_user(request))
                        messages.success(request, "Virement interne enregistré.")
                    except Exception as exc:
                        messages.error(request, str(exc))
            elif action == 'pointer':
                mvt = get_object_or_404(
                    MouvementTresorerie, pk=request.POST.get('mvt_id'), etablissement=etablissement
                )
                mvt.pointe = True
                mvt.date_pointage = timezone.now()
                mvt.save(update_fields=['pointe', 'date_pointage'])
                messages.success(request, "Opération pointée (rapprochement).")
            return redirect('directeur:cg_tresorerie')

        return render(
            request,
            'school_admin/directeur/comptabilite_generale/tresorerie.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'exercice': exercice,
                'mouvements': MouvementTresorerie.objects.filter(etablissement=etablissement)[:60],
                'ecritures_caisse': EcritureComptable.objects.filter(
                    etablissement=etablissement, journal__code='CAI', exercice=exercice
                ).prefetch_related('lignes')[:40],
                'devise_monnaie': devise_etablissement(etablissement),
            },
        )

    @staticmethod
    @login_required
    def paie(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)
        ecritures_qs = EcritureComptable.objects.filter(
            etablissement=etablissement, journal__code='PAI', exercice=exercice
        )
        charges = LigneEcriture.objects.filter(
            ecriture__etablissement=etablissement,
            ecriture__journal__code='PAI',
            ecriture__exercice=exercice,
            compte__numero__in=['637', '6611', '6641', '6642'],
        ).aggregate(s=Sum('debit'))['s'] or Decimal('0')
        ecritures = ecritures_qs.prefetch_related('lignes__compte')[:50]
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/paie.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'exercice': exercice,
                'ecritures': ecritures,
                'charges': charges,
                'devise_monnaie': devise_etablissement(etablissement),
            },
        )

    @staticmethod
    @login_required
    def etats(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)
        synthese = synthese_bilan(etablissement, exercice)
        fmt = (request.GET.get('export') or '').strip()
        if fmt == 'csv':
            buf = StringIO()
            buf.write('Numero;Libelle;Debit;Credit;Solde\n')
            for row in synthese['rows']:
                buf.write(
                    f"{row['compte'].numero};{row['compte'].libelle};"
                    f"{row['debit']};{row['credit']};{row['solde']}\n"
                )
            response = HttpResponse(buf.getvalue(), content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="balance-{exercice.libelle}.csv"'
            return response
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/etats.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'exercice': exercice,
                'synthese': synthese,
                'devise_monnaie': devise_etablissement(etablissement),
                'kpis': kpi_cg(etablissement, annee),
            },
        )
