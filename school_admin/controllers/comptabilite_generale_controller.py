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
from django.urls import reverse
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
    infer_classe_nature_compte,
    ecritures_depenses_orphelines,
    kpi_cg,
    pont_amortissement,
    regime_est_verrouille,
    soldes_par_compte,
    synthese_bilan,
)
from school_admin.services.recouvrement import collecter_impayes_par_classe, devise_etablissement


def _solde_clients_comptable(etablissement):
    """Solde débiteur des comptes 41 sur l'exercice en cours (à-nouveaux compris)."""
    from school_admin.services import compta_etats as ce

    exo = ensure_exercice(etablissement)
    return sum((r['solde'] for r in ce.soldes_comptes(etablissement, exo).values()
                if r['compte'].numero.startswith('41')), Decimal('0'))


def _user(request):
    return request.user if isinstance(request.user, CompteUser) else None


class ComptabiliteGeneraleController:
    @staticmethod
    def _exercice(etablissement, annee):
        return ensure_exercice(etablissement, annee)

    @staticmethod
    @login_required
    def plan_comptable(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request, permission='comptabilite_bilans')
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)

        if request.method == 'POST' and request.POST.get('action') == 'ajouter_compte':
            numero = (request.POST.get('numero') or '').strip()
            libelle = (request.POST.get('libelle') or '').strip()
            if not numero or not libelle:
                messages.error(request, 'Numéro et libellé sont obligatoires.')
                return redirect('directeur:cg_plan_comptable')

            classe_inf, nature_inf, err = infer_classe_nature_compte(numero)
            if err:
                messages.error(request, err)
                return redirect('directeur:cg_plan_comptable')

            classe_post = (request.POST.get('classe') or '').strip()[:1]
            nature_post = (request.POST.get('nature') or '').strip()
            if classe_post != classe_inf or nature_post != nature_inf:
                messages.info(
                    request,
                    f'Classe et nature ajustées selon le numéro {numero} '
                    f'(classe {classe_inf}, nature {nature_inf}).',
                )

            _obj, created = CompteComptable.objects.update_or_create(
                etablissement=etablissement,
                numero=numero,
                defaults={
                    'libelle': libelle,
                    'classe': classe_inf,
                    'nature': nature_inf,
                    'actif': True,
                },
            )
            if created:
                messages.success(request, f'Compte {numero} ajouté.')
            else:
                messages.success(request, f'Compte {numero} mis à jour.')
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
    def clients(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request, permission='comptabilite_bilans')
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
                'total_reste': sum((g.get('total_reste') or Decimal('0') for g in groupes), Decimal('0')),
                'solde_411': _solde_clients_comptable(etablissement),
                'devise_monnaie': devise_etablissement(etablissement),
            },
        )

    @staticmethod
    @login_required
    def fournisseurs(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request, permission='comptabilite_bilans')
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
                from school_admin.model.finances_model import CategorieFinanciere
                from school_admin.services.finances.charges import enregistrer_facture

                try:
                    fournisseur = FournisseurEtablissement.objects.get(
                        pk=request.POST.get('fournisseur_id'), etablissement=etablissement
                    )
                    montant = Decimal(str(request.POST.get('montant') or '0').replace(',', '.'))
                    date_facture = datetime.strptime(request.POST.get('date_facture'), '%Y-%m-%d').date()
                    date_echeance = datetime.strptime(request.POST.get('date_echeance'), '%Y-%m-%d').date()
                    categorie = CategorieFinanciere.objects.get(
                        pk=request.POST.get('categorie_id'),
                        etablissement=etablissement,
                        type_categorie='sortie',
                        actif=True,
                    )
                except (FournisseurEtablissement.DoesNotExist, CategorieFinanciere.DoesNotExist, ValueError, InvalidOperation, TypeError):
                    messages.error(request, "Données de facture invalides.")
                    return redirect('directeur:cg_fournisseurs')
                try:
                    facture, ecriture = enregistrer_facture(
                        etablissement,
                        fournisseur,
                        request.POST.get('numero'),
                        request.POST.get('libelle'),
                        montant,
                        date_facture,
                        date_echeance,
                        categorie,
                        annee_scolaire=annee,
                        user=request.user,
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('directeur:cg_fournisseurs')
                if ecriture is None and facture.pk:
                    from school_admin.services.comptabilite_generale import regime_comptable_etablissement, REGIME_ENGAGEMENT

                    if regime_comptable_etablissement(etablissement) == REGIME_ENGAGEMENT:
                        messages.warning(
                            request,
                            "Facture enregistrée. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                        )
                    else:
                        messages.success(
                            request,
                            "Facture enregistrée. En trésorerie, l'écriture sera passée au paiement.",
                        )
                else:
                    messages.success(request, "Facture fournisseur enregistrée.")
            elif action == 'payer_facture':
                from school_admin.model.finances_model import CompteTresorerie
                from school_admin.services.finances.charges import enregistrer_paiement

                facture = get_object_or_404(
                    FactureFournisseur,
                    pk=request.POST.get('facture_id'),
                    etablissement=etablissement,
                )
                try:
                    montant = Decimal(str(request.POST.get('montant') or '0').replace(',', '.'))
                    date_paiement = datetime.strptime(request.POST.get('date_paiement'), '%Y-%m-%d').date()
                    compte = None
                    compte_id = (request.POST.get('compte_tresorerie_id') or '').strip()
                    if compte_id:
                        compte = CompteTresorerie.objects.get(pk=compte_id, etablissement=etablissement)
                except (CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError):
                    messages.error(request, "Paiement invalide.")
                    return redirect('directeur:cg_fournisseurs')
                try:
                    _paiement, ecriture = enregistrer_paiement(
                        facture,
                        date_paiement,
                        montant,
                        compte_tresorerie=compte,
                        annee_scolaire=annee,
                        user=request.user,
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('directeur:cg_fournisseurs')
                if ecriture is None:
                    messages.warning(
                        request,
                        "Paiement enregistré. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                    )
                else:
                    messages.success(request, "Paiement enregistré sur la facture.")
            elif action == 'annuler_paiement':
                from school_admin.model.finances_model import PaiementCharge
                from school_admin.services.finances.charges import annuler_paiement

                paiement = get_object_or_404(
                    PaiementCharge,
                    pk=request.POST.get('paiement_id'),
                    etablissement=etablissement,
                )
                try:
                    annuler_paiement(paiement, request.POST.get('motif'), user=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('directeur:cg_fournisseurs')
                messages.success(request, "Paiement annulé. La ligne reste dans l'historique.")
            elif action == 'annuler_facture':
                from school_admin.services.finances.charges import annuler_facture

                facture = get_object_or_404(
                    FactureFournisseur,
                    pk=request.POST.get('facture_id'),
                    etablissement=etablissement,
                )
                try:
                    annuler_facture(facture, request.POST.get('motif'), user=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('directeur:cg_fournisseurs')
                messages.success(request, "Facture annulée. Elle reste dans l'historique.")
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

        from django.db.models import Prefetch

        from school_admin.model.finances_model import CategorieFinanciere, CompteTresorerie, PaiementCharge
        from school_admin.services.finances.charges import (
            factures_historique_sans_lignes,
            preparer_referentiels,
        )

        preparer_referentiels(etablissement)
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/fournisseurs.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'fournisseurs': FournisseurEtablissement.objects.filter(etablissement=etablissement, actif=True),
                'categories': CategorieFinanciere.objects.filter(
                    etablissement=etablissement, type_categorie='sortie', actif=True
                ),
                'comptes_tresorerie': CompteTresorerie.objects.filter(
                    etablissement=etablissement, actif=True, statut='ouvert'
                ),
                'factures': FactureFournisseur.objects.filter(etablissement=etablissement).select_related(
                    'fournisseur', 'categorie'
                ).prefetch_related(
                    Prefetch('paiements', queryset=PaiementCharge.objects.select_related('compte_tresorerie'))
                )[:80],
                'factures_historiques': list(factures_historique_sans_lignes(etablissement)[:50]),
                'immobilisations': Immobilisation.objects.filter(etablissement=etablissement, actif=True),
                'devise_monnaie': devise_etablissement(etablissement),
                'date_defaut': date.today().isoformat(),
            },
        )

    @staticmethod
    @login_required
    def tresorerie(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request, permission='comptabilite_bilans')
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'virement':
                from school_admin.model.finances_model import CompteTresorerie
                from school_admin.services.finances.transferts import enregistrer_transfert

                try:
                    montant = Decimal(str(request.POST.get('montant') or '0').replace(',', '.'))
                    date_mvt = datetime.strptime(request.POST.get('date_mouvement'), '%Y-%m-%d').date()
                    source = CompteTresorerie.objects.get(
                        pk=request.POST.get('compte_source_id'), etablissement=etablissement
                    )
                    destination = CompteTresorerie.objects.get(
                        pk=request.POST.get('compte_destination_id'), etablissement=etablissement
                    )
                except (CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError):
                    messages.error(request, "Transfert invalide.")
                    return redirect('directeur:cg_tresorerie')
                try:
                    _mouvement, ecriture = enregistrer_transfert(
                        etablissement,
                        source,
                        destination,
                        date_mvt,
                        montant,
                        reference=request.POST.get('reference') or '',
                        motif=request.POST.get('libelle') or '',
                        annee_scolaire=annee,
                        user=request.user,
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('directeur:cg_tresorerie')
                if ecriture is None:
                    messages.warning(
                        request,
                        "Transfert enregistré. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                    )
                else:
                    messages.success(request, "Transfert enregistré.")
            elif action == 'annuler_transfert':
                from school_admin.services.finances.transferts import annuler_transfert

                mouvement = get_object_or_404(
                    MouvementTresorerie,
                    pk=request.POST.get('mvt_id'),
                    etablissement=etablissement,
                )
                try:
                    annuler_transfert(mouvement, request.POST.get('motif'), user=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('directeur:cg_tresorerie')
                messages.success(request, "Transfert annulé. Il reste dans l'historique.")
            elif action == 'pointer':
                messages.warning(
                    request,
                    "Le pointage se fait sur le relevé bancaire, plus ici.",
                )
            return redirect('directeur:cg_tresorerie')

        from school_admin.model.finances_model import CompteTresorerie
        from school_admin.services.finances.transferts import rattacher_virements_historiques
        from school_admin.services.finances.tresorerie import solde_calcule

        rattacher_virements_historiques(etablissement)
        comptes = list(
            CompteTresorerie.objects.filter(
                etablissement=etablissement, actif=True, statut='ouvert'
            ).select_related('compte_comptable')
        )
        for compte_treso in comptes:
            compte_treso.solde_affiche = solde_calcule(compte_treso)
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/tresorerie.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'exercice': exercice,
                'comptes_tresorerie': comptes,
                'mouvements': MouvementTresorerie.objects.filter(etablissement=etablissement).select_related(
                    'compte_source', 'compte_destination'
                )[:60],
                'ecritures_caisse': EcritureComptable.objects.filter(
                    etablissement=etablissement, journal__code='CAI', exercice=exercice
                ).prefetch_related('lignes')[:40],
                'devise_monnaie': devise_etablissement(etablissement),
                'date_defaut': date.today().isoformat(),
            },
        )

    @staticmethod
    def _redirect_rapprochement(releve=None):
        url = reverse('directeur:cg_rapprochement')
        if releve is not None:
            return redirect(f"{url}?releve={releve.pk}")
        return redirect(url)

    @staticmethod
    @login_required
    def rapprochement(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request, permission='comptabilite_bilans')
        if denied:
            return denied
        from school_admin.model.finances_model import CompteTresorerie, LigneReleve, ReleveBancaire
        from school_admin.services.finances.rapprochement import (
            TYPES_RELEVE,
            ajouter_ligne,
            candidats_pour_ligne,
            cloturer_releve,
            creer_releve,
            depointer_ligne,
            operations_non_pointees_detail,
            pointer_ligne,
            synthese_releve,
        )
        from school_admin.services.finances.tresorerie import assurer_comptes_defaut

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)
        ensure_plan_comptable(etablissement)
        assurer_comptes_defaut(etablissement)
        comptes = CompteTresorerie.objects.filter(
            etablissement=etablissement,
            type_compte__in=TYPES_RELEVE,
            statut='ouvert',
            actif=True,
        ).select_related('compte_comptable')

        if request.method == 'POST':
            action = request.POST.get('action')
            releve = None
            if request.POST.get('releve_id'):
                releve = get_object_or_404(
                    ReleveBancaire, pk=request.POST.get('releve_id'), etablissement=etablissement,
                )
            try:
                if action == 'creer_releve':
                    compte_treso = CompteTresorerie.objects.get(
                        pk=request.POST.get('compte_id'), etablissement=etablissement,
                    )
                    releve = creer_releve(
                        etablissement,
                        compte_treso,
                        request.POST.get('reference') or '',
                        datetime.strptime(request.POST.get('date_debut'), '%Y-%m-%d').date(),
                        datetime.strptime(request.POST.get('date_fin'), '%Y-%m-%d').date(),
                        request.POST.get('solde_ouverture') or 0,
                        request.POST.get('solde_cloture') or 0,
                        user=request.user,
                    )
                    messages.success(request, "Relevé enregistré. Aucune écriture n'a été passée.")
                elif action == 'ajouter_ligne':
                    if releve is None:
                        raise ValueError("Choisissez un relevé.")
                    ajouter_ligne(
                        releve,
                        datetime.strptime(request.POST.get('date_operation'), '%Y-%m-%d').date(),
                        request.POST.get('libelle') or '',
                        debit=request.POST.get('debit') or 0,
                        credit=request.POST.get('credit') or 0,
                        reference=request.POST.get('reference') or '',
                        user=request.user,
                    )
                    messages.success(request, "Ligne ajoutée.")
                elif action == 'pointer':
                    ligne = get_object_or_404(
                        LigneReleve, pk=request.POST.get('ligne_id'), releve__etablissement=etablissement,
                    )
                    releve = ligne.releve
                    ecriture = get_object_or_404(
                        EcritureComptable,
                        pk=request.POST.get('ecriture_id'),
                        etablissement=etablissement,
                    )
                    pointer_ligne(ligne, ecriture, user=request.user)
                    messages.success(request, "Ligne pointée. Elle ne se modifie plus.")
                elif action == 'depointer':
                    ligne = get_object_or_404(
                        LigneReleve, pk=request.POST.get('ligne_id'), releve__etablissement=etablissement,
                    )
                    releve = ligne.releve
                    depointer_ligne(ligne, request.POST.get('motif'), user=request.user)
                    messages.success(request, "Pointage retiré. La ligne reste.")
                elif action == 'cloturer':
                    if releve is None:
                        raise ValueError("Choisissez un relevé.")
                    cloturer_releve(releve, user=request.user)
                    messages.success(request, "Relevé clôturé.")
            except (CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError) as exc:
                messages.error(
                    request,
                    str(exc) if isinstance(exc, ValueError) else "Données de rapprochement invalides.",
                )
            return ComptabiliteGeneraleController._redirect_rapprochement(releve)

        releve = None
        synthese = None
        lignes = []
        operations = []
        if request.GET.get('releve'):
            releve = get_object_or_404(
                ReleveBancaire, pk=request.GET.get('releve'), etablissement=etablissement,
            )
            synthese = synthese_releve(releve)
            lignes = list(releve.lignes.select_related('ecriture', 'mouvement'))
            for ligne in lignes:
                ligne.candidats = candidats_pour_ligne(ligne) if not ligne.pointe else []
            operations = operations_non_pointees_detail(releve)

        return render(
            request,
            'school_admin/directeur/comptabilite_generale/rapprochement.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'exercice': exercice,
                'comptes': comptes,
                'releves': ReleveBancaire.objects.filter(etablissement=etablissement).select_related(
                    'compte_tresorerie'
                )[:80],
                'releve': releve,
                'synthese': synthese,
                'lignes': lignes,
                'operations': operations,
                'date_defaut': timezone.now().date(),
                'devise_monnaie': devise_etablissement(etablissement),
            },
        )

    @staticmethod
    @login_required
    def paie(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request, permission='comptabilite_bilans')
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
    def recettes(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request, permission='comptabilite_bilans')
        if denied:
            return denied
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Prefetch

        from school_admin.model.finances_model import (
            CategorieFinanciere,
            CompteTresorerie,
            RecetteEtablissement,
            RemboursementOperation,
        )
        from school_admin.services.finances.categories import assurer_categories
        from school_admin.services.finances.recettes import (
            annuler_recette,
            annuler_remboursement,
            enregistrer_recette,
            enregistrer_remboursement,
            paiements_scolarite,
        )
        from school_admin.services.finances.tresorerie import assurer_comptes_defaut

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)
        assurer_categories(etablissement)
        assurer_comptes_defaut(etablissement)

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'ajouter_recette':
                try:
                    categorie = CategorieFinanciere.objects.get(
                        pk=request.POST.get('categorie_id'),
                        etablissement=etablissement,
                        type_categorie='recette',
                        actif=True,
                    )
                    compte_treso = CompteTresorerie.objects.get(
                        pk=request.POST.get('compte_id'),
                        etablissement=etablissement,
                    )
                    montant = Decimal(str(request.POST.get('montant') or '0').replace(',', '.'))
                    date_recette = datetime.strptime(request.POST.get('date_recette'), '%Y-%m-%d').date()
                except (CategorieFinanciere.DoesNotExist, CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError):
                    messages.error(request, "Données de recette invalides.")
                    return redirect('directeur:cg_recettes')
                try:
                    _recette, ecriture = enregistrer_recette(
                        etablissement,
                        request.POST.get('nature'),
                        categorie,
                        compte_treso,
                        date_recette,
                        montant,
                        libelle=request.POST.get('libelle') or '',
                        origine=request.POST.get('origine') or '',
                        reference=request.POST.get('reference') or '',
                        destination=request.POST.get('destination') or '',
                        annee_scolaire=annee,
                        user=request.user,
                        fichier=request.FILES.get('justificatif'),
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('directeur:cg_recettes')
                if ecriture is None:
                    messages.warning(
                        request,
                        "Recette enregistrée. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                    )
                else:
                    messages.success(request, "Recette enregistrée.")
            elif action == 'annuler_recette':
                recette = get_object_or_404(
                    RecetteEtablissement,
                    pk=request.POST.get('recette_id'),
                    etablissement=etablissement,
                )
                try:
                    annuler_recette(recette, request.POST.get('motif'), user=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Recette annulée. La ligne est conservée.")
            elif action == 'rembourser_recette':
                recette = get_object_or_404(
                    RecetteEtablissement,
                    pk=request.POST.get('recette_id'),
                    etablissement=etablissement,
                )
                try:
                    compte_treso = None
                    if request.POST.get('compte_id'):
                        compte_treso = CompteTresorerie.objects.get(
                            pk=request.POST.get('compte_id'),
                            etablissement=etablissement,
                        )
                    montant = Decimal(str(request.POST.get('montant') or '0').replace(',', '.'))
                    jour = datetime.strptime(request.POST.get('date_remboursement'), '%Y-%m-%d').date()
                    _remb, _ecriture = enregistrer_remboursement(
                        recette,
                        jour,
                        montant,
                        request.POST.get('motif') or '',
                        compte_tresorerie=compte_treso,
                        user=request.user,
                    )
                except (CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError) as exc:
                    messages.error(request, str(exc) if isinstance(exc, ValueError) else "Données de remboursement invalides.")
                else:
                    messages.success(request, "Remboursement enregistré. La recette d'origine est conservée.")
            elif action == 'annuler_remboursement':
                remboursement = get_object_or_404(
                    RemboursementOperation,
                    pk=request.POST.get('remboursement_id'),
                    etablissement=etablissement,
                    content_type=ContentType.objects.get_for_model(RecetteEtablissement),
                )
                try:
                    annuler_remboursement(remboursement, request.POST.get('motif'), user=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Remboursement annulé. La ligne est conservée.")
            return redirect('directeur:cg_recettes')

        recettes = list(
            RecetteEtablissement.objects.filter(etablissement=etablissement)
            .select_related('categorie__compte_comptable', 'compte_tresorerie')
            .prefetch_related(Prefetch(
                'remboursements',
                queryset=RemboursementOperation.objects.select_related('compte_tresorerie'),
            ))
            .order_by('-date_recette', '-id')[:80]
        )
        destinations = []
        for code, label in RecetteEtablissement.DESTINATION_CHOICES:
            lignes = [
                recette for recette in recettes
                if recette.nature == 'subvention' and recette.destination == code and recette.statut == 'validee'
            ]
            if not lignes:
                continue
            destinations.append({
                'label': label,
                'net': sum((recette.net() for recette in lignes), Decimal('0')),
                'dans_resultat': sum((recette.net() for recette in lignes if recette.dans_le_resultat()), Decimal('0')),
                'hors_resultat': sum((recette.net() for recette in lignes if not recette.dans_le_resultat()), Decimal('0')),
            })
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/recettes.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'exercice': exercice,
                'synthese': synthese_bilan(etablissement, exercice),
                'destinations': destinations,
                'recettes': recettes,
                'categories': CategorieFinanciere.objects.filter(
                    etablissement=etablissement, type_categorie='recette', actif=True,
                ),
                'comptes': CompteTresorerie.objects.filter(
                    etablissement=etablissement, statut='ouvert', actif=True,
                ),
                'paiements_scolarite': paiements_scolarite(etablissement, annee),
                'natures': RecetteEtablissement.NATURE_CHOICES,
                'destinations_choices': RecetteEtablissement.DESTINATION_CHOICES,
                'date_defaut': timezone.now().date(),
                'devise_monnaie': devise_etablissement(etablissement),
            },
        )

    @staticmethod
    @login_required
    def prets(request):
        etablissement, is_directeur, personnel, denied = _require_compta(request, permission='comptabilite_bilans')
        if denied:
            return denied
        from django.db.models import Prefetch

        from school_admin.model.finances_model import CompteTresorerie, PretEtablissement, RemboursementPret
        from school_admin.services.finances.prets import (
            ajouter_echeance,
            annuler_pret,
            annuler_remboursement,
            enregistrer_pret,
            enregistrer_remboursement,
        )
        from school_admin.services.finances.tresorerie import assurer_comptes_defaut

        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        exercice = ComptabiliteGeneraleController._exercice(etablissement, annee)
        ensure_plan_comptable(etablissement)
        assurer_comptes_defaut(etablissement)

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'ajouter_pret':
                try:
                    compte_treso = CompteTresorerie.objects.get(
                        pk=request.POST.get('compte_id'), etablissement=etablissement,
                    )
                    montant = Decimal(str(request.POST.get('montant') or '0').replace(',', '.'))
                    taux = Decimal(str(request.POST.get('taux') or '0').replace(',', '.'))
                    jour = datetime.strptime(request.POST.get('date_reception'), '%Y-%m-%d').date()
                    _pret, ecriture = enregistrer_pret(
                        etablissement,
                        compte_treso,
                        jour,
                        montant,
                        request.POST.get('reference') or '',
                        request.POST.get('objet') or '',
                        taux=taux,
                        duree_mois=request.POST.get('duree_mois') or None,
                        annee_scolaire=annee,
                        user=request.user,
                        fichier=request.FILES.get('justificatif'),
                    )
                except (CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError) as exc:
                    messages.error(request, str(exc) if isinstance(exc, ValueError) else "Données de prêt invalides.")
                else:
                    if ecriture is None:
                        messages.warning(request, "Prêt enregistré. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.")
                    else:
                        messages.success(request, "Prêt enregistré. La trésorerie et la dette augmentent, pas le résultat.")
            elif action == 'ajouter_echeance':
                pret = get_object_or_404(PretEtablissement, pk=request.POST.get('pret_id'), etablissement=etablissement)
                try:
                    ajouter_echeance(
                        pret,
                        datetime.strptime(request.POST.get('date_echeance'), '%Y-%m-%d').date(),
                        request.POST.get('capital_prevu') or 0,
                        request.POST.get('interets_prevus') or 0,
                        request.POST.get('frais_prevus') or 0,
                    )
                except (ValueError, InvalidOperation, TypeError) as exc:
                    messages.error(request, str(exc) if isinstance(exc, ValueError) else "Données d'échéance invalides.")
                else:
                    messages.success(request, "Échéance prévue enregistrée. Aucune écriture n'a été passée.")
            elif action == 'rembourser_pret':
                pret = get_object_or_404(PretEtablissement, pk=request.POST.get('pret_id'), etablissement=etablissement)
                try:
                    compte_treso = None
                    if request.POST.get('compte_id'):
                        compte_treso = CompteTresorerie.objects.get(
                            pk=request.POST.get('compte_id'), etablissement=etablissement,
                        )
                    enregistrer_remboursement(
                        pret,
                        datetime.strptime(request.POST.get('date_remboursement'), '%Y-%m-%d').date(),
                        capital=request.POST.get('capital') or 0,
                        interets=request.POST.get('interets') or 0,
                        frais=request.POST.get('frais') or 0,
                        motif=request.POST.get('motif') or '',
                        compte_tresorerie=compte_treso,
                        user=request.user,
                    )
                except (CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError) as exc:
                    messages.error(request, str(exc) if isinstance(exc, ValueError) else "Données de remboursement invalides.")
                else:
                    messages.success(request, "Remboursement enregistré. Le capital diminue la dette. Intérêts et frais sont des charges.")
            elif action == 'annuler_remboursement':
                remboursement = get_object_or_404(
                    RemboursementPret, pk=request.POST.get('remboursement_id'), etablissement=etablissement,
                )
                try:
                    annuler_remboursement(remboursement, request.POST.get('motif'), user=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Remboursement annulé. La ligne est conservée.")
            elif action == 'annuler_pret':
                pret = get_object_or_404(PretEtablissement, pk=request.POST.get('pret_id'), etablissement=etablissement)
                try:
                    annuler_pret(pret, request.POST.get('motif'), user=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Prêt annulé. La ligne est conservée.")
            return redirect('directeur:cg_prets')

        prets = list(
            PretEtablissement.objects.filter(etablissement=etablissement)
            .select_related('compte_tresorerie')
            .prefetch_related(
                'echeances',
                Prefetch('remboursements', queryset=RemboursementPret.objects.select_related('compte_tresorerie')),
            )
            .order_by('-date_reception', '-id')[:80]
        )
        return render(
            request,
            'school_admin/directeur/comptabilite_generale/prets.html',
            {
                'etablissement': etablissement,
                'is_directeur': is_directeur,
                'personnel': personnel,
                'annee_scolaire_active': annee,
                'exercice': exercice,
                'synthese': synthese_bilan(etablissement, exercice),
                'prets': prets,
                'comptes': CompteTresorerie.objects.filter(
                    etablissement=etablissement, statut='ouvert', actif=True,
                ),
                'date_defaut': timezone.now().date(),
                'devise_monnaie': devise_etablissement(etablissement),
            },
        )
