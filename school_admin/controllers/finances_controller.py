"""Interface Finances. Les écritures passent par les services, jamais par objects.create."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from school_admin.controllers.comptabilite_controller import ComptabiliteController
from school_admin.controllers.recouvrement_controller import _require_compta
from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.comptabilite_generale_model import (
    EcritureComptable,
    FactureFournisseur,
    FournisseurEtablissement,
    MouvementTresorerie,
)
from school_admin.model.finances_model import (
    CategorieFinanciere,
    CompteTresorerie,
    PaiementCharge,
    PretEtablissement,
    RecetteEtablissement,
    RemboursementOperation,
    RemboursementPret,
)
from school_admin.services.caisse import parser_montant
from school_admin.services.comptabilite_generale import ensure_exercice
from school_admin.services.finances.categories import assurer_categories
from school_admin.services.finances.metrics import calculer_indicateurs
from school_admin.services.finances.queries import (
    VUES_ENTREES,
    VUES_SORTIES,
    VUES_TRESORERIE,
    dernieres_operations,
    filtrer_factures,
    filtrer_paiements_scolarite,
    filtrer_recettes,
    filtrer_sorties,
    lire_filtres,
    query_filtres,
    total_exploitation_entrees,
    totaux_subventions,
)
from school_admin.services.finances.tresorerie import assurer_comptes_defaut, solde_calcule
from school_admin.services.recouvrement import devise_etablissement
from school_admin.utils.decorators_permissions import check_permission

NATURE_VERS_CATEGORIE = {
    'activite': 'Activité',
    'subvention': 'Subvention',
    'divers': 'Recette diverse',
}


def _require_finances(request):
    return _require_compta(request, permission='comptabilite_voir')


def _peut_annuler(request, is_directeur):
    if is_directeur:
        return True
    return check_permission(request.user, 'comptabilite_bilans')


def _exiger_bilans(request, is_directeur):
    if _peut_annuler(request, is_directeur):
        return True
    messages.error(request, "Vous n'avez pas l'autorisation d'effectuer cette action.")
    return False


def _retour(request, name, extra=None):
    filtres = lire_filtres(request)
    if extra:
        filtres.update({cle: extra[cle] for cle in extra if extra[cle] is not None})
        if 'releve' in extra:
            filtres['releve_id'] = extra['releve']
    qs = query_filtres(filtres)
    url = reverse(name)
    return redirect(f"{url}?{qs}" if qs else url)


def _date(valeur):
    return datetime.strptime(valeur, '%Y-%m-%d').date()


def _contexte(request, etablissement, is_directeur, personnel, annee, filtres, fin_nav):
    if not CompteTresorerie.objects.filter(etablissement=etablissement, actif=True).exists():
        assurer_comptes_defaut(etablissement)
        assurer_categories(etablissement)
    elif not CategorieFinanciere.objects.filter(etablissement=etablissement, actif=True).exists():
        assurer_categories(etablissement)
    nav_filtres = dict(filtres)
    nav_filtres['vue'] = ''
    nav_filtres['releve_id'] = ''
    return {
        'etablissement': etablissement,
        'is_directeur': is_directeur,
        'personnel': personnel,
        'annee_scolaire_active': annee,
        'exercice': ensure_exercice(etablissement, annee),
        'filtres': filtres,
        'bornes': filtres['bornes'],
        'vue': filtres['vue'],
        'filtre_qs': query_filtres(filtres),
        'filtre_nav': query_filtres(nav_filtres),
        'fin_nav': fin_nav,
        'peut_annuler': _peut_annuler(request, is_directeur),
        'devise_monnaie': devise_etablissement(etablissement),
        'date_defaut': timezone.now().date(),
        'comptes_tresorerie': CompteTresorerie.objects.filter(
            etablissement=etablissement, actif=True, statut='ouvert',
        ),
    }


class FinancesController:
    @staticmethod
    @login_required
    def situation(request):
        etablissement, is_directeur, personnel, denied = _require_finances(request)
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        filtres = lire_filtres(request)
        bornes = filtres['bornes']
        data = calculer_indicateurs(etablissement, bornes.debut, bornes.fin, annee)
        indicateurs = data['indicateurs']
        subventions = totaux_subventions(etablissement, bornes.debut, bornes.fin)
        contexte = _contexte(request, etablissement, is_directeur, personnel, annee, filtres, 'situation')
        contexte.update({
            'indicateurs': indicateurs,
            'regime': data['regime'],
            'operations': dernieres_operations(etablissement, bornes.debut, bornes.fin),
            'subventions': subventions,
        })
        return render(request, 'school_admin/directeur/finances/situation.html', contexte)

    @staticmethod
    @login_required
    def entrees(request):
        etablissement, is_directeur, personnel, denied = _require_finances(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        filtres = lire_filtres(request, VUES_ENTREES, 'scolarite')
        if request.method == 'POST':
            return FinancesController._post_entrees(request, etablissement, is_directeur, annee)
        paiements = []
        recettes = []
        if filtres['vue'] == 'scolarite':
            paiements = filtrer_paiements_scolarite(etablissement, filtres, annee)
        elif filtres['vue'] in ('activite', 'subvention', 'divers'):
            recettes = filtrer_recettes(etablissement, filtres, filtres['vue'])
        exploitation, hors = total_exploitation_entrees(etablissement, filtres)
        categories = CategorieFinanciere.objects.filter(
            etablissement=etablissement, type_categorie='recette', actif=True,
        )
        libelle_cat = NATURE_VERS_CATEGORIE.get(filtres['vue'])
        contexte = _contexte(request, etablissement, is_directeur, personnel, annee, filtres, 'entrees')
        contexte.update({
            'liens_vue': {code: query_filtres(filtres, vue=code) for code in VUES_ENTREES},
            'paiements_scolarite': paiements,
            'recettes': recettes,
            'categories': categories.filter(libelle=libelle_cat) if libelle_cat else categories,
            'natures': RecetteEtablissement.NATURE_CHOICES,
            'destinations_choices': RecetteEtablissement.DESTINATION_CHOICES,
            'total_exploitation': exploitation,
            'hors_classe_7': hors,
            'subventions': totaux_subventions(
                etablissement, filtres['bornes'].debut, filtres['bornes'].fin,
            ),
        })
        return render(request, 'school_admin/directeur/finances/entrees.html', contexte)

    @staticmethod
    def _post_entrees(request, etablissement, is_directeur, annee):
        from django.contrib.contenttypes.models import ContentType

        from school_admin.services.finances.recettes import (
            annuler_recette,
            annuler_remboursement,
            enregistrer_recette,
            enregistrer_remboursement,
        )

        action = request.POST.get('action')
        if action in ('annuler_recette', 'annuler_remboursement') and not _exiger_bilans(request, is_directeur):
            return _retour(request, 'directeur:finances_entrees')
        try:
            if action == 'ajouter_recette':
                nature = (request.POST.get('nature') or '').strip()
                categorie = CategorieFinanciere.objects.get(
                    pk=request.POST.get('categorie_id'),
                    etablissement=etablissement,
                    type_categorie='recette',
                    actif=True,
                )
                attendu = NATURE_VERS_CATEGORIE.get(nature)
                if attendu and categorie.libelle != attendu:
                    messages.error(request, "La catégorie ne correspond pas à cette nature d'entrée.")
                    return _retour(request, 'directeur:finances_entrees')
                compte_treso = CompteTresorerie.objects.get(
                    pk=request.POST.get('compte_id'), etablissement=etablissement,
                )
                montant = parser_montant(request.POST.get('montant'))
                if montant is None:
                    raise ValueError("Indiquez un montant supérieur à 0.")
                _recette, ecriture = enregistrer_recette(
                    etablissement,
                    nature,
                    categorie,
                    compte_treso,
                    _date(request.POST.get('date_recette')),
                    montant,
                    libelle=request.POST.get('libelle') or '',
                    origine=request.POST.get('origine') or '',
                    reference=request.POST.get('reference') or '',
                    destination=request.POST.get('destination') or '',
                    annee_scolaire=annee,
                    user=request.user,
                    fichier=request.FILES.get('justificatif'),
                )
                if ecriture is None:
                    messages.warning(
                        request,
                        "Entrée enregistrée. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                    )
                else:
                    messages.success(request, "Entrée enregistrée.")
            elif action == 'annuler_recette':
                recette = get_object_or_404(
                    RecetteEtablissement, pk=request.POST.get('recette_id'), etablissement=etablissement,
                )
                annuler_recette(recette, request.POST.get('motif'), user=request.user)
                messages.success(request, "Entrée annulée. La ligne est conservée.")
            elif action == 'rembourser_recette':
                recette = get_object_or_404(
                    RecetteEtablissement, pk=request.POST.get('recette_id'), etablissement=etablissement,
                )
                compte_treso = None
                if request.POST.get('compte_id'):
                    compte_treso = CompteTresorerie.objects.get(
                        pk=request.POST.get('compte_id'), etablissement=etablissement,
                    )
                montant = parser_montant(request.POST.get('montant'))
                if montant is None:
                    raise ValueError("Indiquez un montant supérieur à 0.")
                enregistrer_remboursement(
                    recette,
                    _date(request.POST.get('date_remboursement')),
                    montant,
                    request.POST.get('motif') or '',
                    compte_tresorerie=compte_treso,
                    user=request.user,
                )
                messages.success(request, "Remboursement enregistré. L'entrée d'origine est conservée.")
            elif action == 'annuler_remboursement':
                remboursement = get_object_or_404(
                    RemboursementOperation,
                    pk=request.POST.get('remboursement_id'),
                    etablissement=etablissement,
                    content_type=ContentType.objects.get_for_model(RecetteEtablissement),
                )
                annuler_remboursement(remboursement, request.POST.get('motif'), user=request.user)
                messages.success(request, "Remboursement annulé. La ligne est conservée.")
        except (CategorieFinanciere.DoesNotExist, CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError) as exc:
            messages.error(
                request,
                str(exc) if isinstance(exc, ValueError) else "Données d'entrée invalides.",
            )
        return _retour(request, 'directeur:finances_entrees')

    @staticmethod
    @login_required
    def sorties(request):
        etablissement, is_directeur, personnel, denied = _require_finances(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        filtres = lire_filtres(request, VUES_SORTIES, 'jour')
        if request.method == 'POST':
            return FinancesController._post_sorties(request, etablissement, is_directeur, annee)
        from school_admin.services.finances.charges import factures_historique_sans_lignes, preparer_referentiels

        preparer_referentiels(etablissement)
        contexte = _contexte(request, etablissement, is_directeur, personnel, annee, filtres, 'sorties')
        contexte.update({
            'liens_vue': {code: query_filtres(filtres, vue=code) for code in VUES_SORTIES},
            'depenses': filtrer_sorties(etablissement, filtres),
            'factures': filtrer_factures(etablissement, filtres).prefetch_related(
                Prefetch('paiements', queryset=PaiementCharge.objects.select_related('compte_tresorerie'))
            ),
            'factures_historiques': list(factures_historique_sans_lignes(etablissement)[:50]),
            'fournisseurs': FournisseurEtablissement.objects.filter(etablissement=etablissement, actif=True),
            'categories': CategorieFinanciere.objects.filter(
                etablissement=etablissement, type_categorie='sortie', actif=True,
            ),
            'motifs': DepenseEtablissement.MOTIF_CHOICES,
        })
        return render(request, 'school_admin/directeur/finances/sorties.html', contexte)

    @staticmethod
    def _post_sorties(request, etablissement, is_directeur, annee):
        from school_admin.services.finances.charges import (
            annuler_facture,
            annuler_paiement,
            enregistrer_facture,
            enregistrer_paiement,
        )
        from school_admin.services.finances.operations import annuler_sortie, enregistrer_sortie

        action = request.POST.get('action')
        if action in ('annuler_sortie', 'annuler_facture', 'annuler_paiement', 'ajouter_facture', 'ajouter_fournisseur'):
            if action != 'ajouter_fournisseur' and action.startswith('annuler') and not _exiger_bilans(request, is_directeur):
                return _retour(request, 'directeur:finances_sorties')
            if action in ('ajouter_facture', 'ajouter_fournisseur') and not _exiger_bilans(request, is_directeur):
                return _retour(request, 'directeur:finances_sorties')
        try:
            if action == 'ajouter_sortie':
                montant = parser_montant(request.POST.get('montant'))
                if montant is None:
                    raise ValueError("Indiquez un montant supérieur à 0.")
                motif = (request.POST.get('motif') or 'autre').strip()
                if motif not in {code for code, _label in DepenseEtablissement.MOTIF_CHOICES}:
                    motif = 'autre'
                fournisseur = None
                if request.POST.get('fournisseur_id'):
                    fournisseur = FournisseurEtablissement.objects.get(
                        pk=request.POST.get('fournisseur_id'), etablissement=etablissement, actif=True,
                    )
                _depense, ecriture = enregistrer_sortie(
                    etablissement,
                    _date(request.POST.get('date_depense')),
                    motif,
                    montant,
                    libelle=(request.POST.get('libelle') or '').strip(),
                    annee_scolaire=annee,
                    user=request.user,
                    fichier=request.FILES.get('justificatif'),
                    fournisseur=fournisseur,
                )
                if ecriture is None:
                    messages.warning(
                        request,
                        "Sortie enregistrée. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                    )
                else:
                    messages.success(request, "Sortie du jour enregistrée.")
            elif action == 'annuler_sortie':
                depense = get_object_or_404(
                    DepenseEtablissement, pk=request.POST.get('depense_id'), etablissement=etablissement,
                )
                annuler_sortie(depense, request.POST.get('motif'), user=request.user)
                messages.success(request, "Sortie annulée. La ligne est conservée.")
            elif action == 'ajouter_fournisseur':
                nom = (request.POST.get('nom') or '').strip()
                if not nom:
                    raise ValueError("Le nom du fournisseur est obligatoire.")
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
                fournisseur = FournisseurEtablissement.objects.get(
                    pk=request.POST.get('fournisseur_id'), etablissement=etablissement,
                )
                categorie = CategorieFinanciere.objects.get(
                    pk=request.POST.get('categorie_id'),
                    etablissement=etablissement,
                    type_categorie='sortie',
                    actif=True,
                )
                montant = parser_montant(request.POST.get('montant'))
                if montant is None:
                    raise ValueError("Indiquez un montant supérieur à 0.")
                facture, ecriture = enregistrer_facture(
                    etablissement,
                    fournisseur,
                    request.POST.get('numero'),
                    request.POST.get('libelle'),
                    montant,
                    _date(request.POST.get('date_facture')),
                    _date(request.POST.get('date_echeance')),
                    categorie,
                    annee_scolaire=annee,
                    user=request.user,
                )
                if ecriture is None:
                    messages.success(
                        request,
                        "Charge du mois enregistrée. En trésorerie, l'écriture sera passée au paiement.",
                    )
                else:
                    messages.success(request, "Charge du mois enregistrée.")
            elif action == 'payer_facture':
                facture = get_object_or_404(
                    FactureFournisseur, pk=request.POST.get('facture_id'), etablissement=etablissement,
                )
                montant = parser_montant(request.POST.get('montant'))
                if montant is None:
                    raise ValueError("Indiquez un montant supérieur à 0.")
                compte = None
                if request.POST.get('compte_tresorerie_id'):
                    compte = CompteTresorerie.objects.get(
                        pk=request.POST.get('compte_tresorerie_id'), etablissement=etablissement,
                    )
                _paiement, ecriture = enregistrer_paiement(
                    facture,
                    _date(request.POST.get('date_paiement')),
                    montant,
                    compte_tresorerie=compte,
                    annee_scolaire=annee,
                    user=request.user,
                )
                if ecriture is None:
                    messages.warning(
                        request,
                        "Paiement enregistré. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                    )
                else:
                    messages.success(request, "Paiement enregistré sur la charge.")
            elif action == 'annuler_paiement':
                paiement = get_object_or_404(
                    PaiementCharge, pk=request.POST.get('paiement_id'), etablissement=etablissement,
                )
                annuler_paiement(paiement, request.POST.get('motif'), user=request.user)
                messages.success(request, "Paiement annulé. La ligne reste dans l'historique.")
            elif action == 'annuler_facture':
                facture = get_object_or_404(
                    FactureFournisseur, pk=request.POST.get('facture_id'), etablissement=etablissement,
                )
                annuler_facture(facture, request.POST.get('motif'), user=request.user)
                messages.success(request, "Charge annulée. Elle reste dans l'historique.")
        except (
            FournisseurEtablissement.DoesNotExist,
            CategorieFinanciere.DoesNotExist,
            CompteTresorerie.DoesNotExist,
            ValueError,
            InvalidOperation,
            TypeError,
        ) as exc:
            messages.error(
                request,
                str(exc) if isinstance(exc, ValueError) else "Données de sortie invalides.",
            )
        return _retour(request, 'directeur:finances_sorties')

    @staticmethod
    @login_required
    def tresorerie(request):
        etablissement, is_directeur, personnel, denied = _require_finances(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        filtres = lire_filtres(request, VUES_TRESORERIE, 'comptes')
        if request.method == 'POST':
            return FinancesController._post_tresorerie(request, etablissement, is_directeur, annee)
        from school_admin.model.finances_model import ReleveBancaire
        from school_admin.services.finances.rapprochement import (
            TYPES_RELEVE,
            candidats_pour_ligne,
            operations_non_pointees_detail,
            synthese_releve,
        )
        from school_admin.services.finances.transferts import rattacher_virements_historiques

        rattacher_virements_historiques(etablissement)
        comptes = list(
            CompteTresorerie.objects.filter(
                etablissement=etablissement, actif=True, statut='ouvert',
            ).select_related('compte_comptable')
        )
        for compte_treso in comptes:
            compte_treso.solde_affiche = solde_calcule(compte_treso, a_date=filtres['bornes'].fin)
        mouvements = MouvementTresorerie.objects.filter(etablissement=etablissement)
        if filtres['q']:
            mouvements = mouvements.filter(libelle__icontains=filtres['q'])
        if filtres['statut']:
            mouvements = mouvements.filter(statut=filtres['statut'])
        releve = None
        synthese = None
        lignes = []
        operations = []
        if filtres['releve_id']:
            releve = get_object_or_404(
                ReleveBancaire, pk=filtres['releve_id'], etablissement=etablissement,
            )
            synthese = synthese_releve(releve)
            lignes = list(releve.lignes.select_related('ecriture', 'mouvement'))
            for ligne in lignes:
                ligne.candidats = candidats_pour_ligne(ligne) if not ligne.pointe else []
            operations = operations_non_pointees_detail(releve)
        contexte = _contexte(request, etablissement, is_directeur, personnel, annee, filtres, 'tresorerie')
        contexte.update({
            'liens_vue': {code: query_filtres(filtres, vue=code) for code in VUES_TRESORERIE},
            'comptes_soldes': comptes,
            'mouvements': mouvements.select_related('compte_source', 'compte_destination')[:60],
            'releves': ReleveBancaire.objects.filter(etablissement=etablissement).select_related(
                'compte_tresorerie'
            )[:80],
            'comptes_releve': CompteTresorerie.objects.filter(
                etablissement=etablissement,
                type_compte__in=TYPES_RELEVE,
                statut='ouvert',
                actif=True,
            ),
            'releve': releve,
            'synthese_releve': synthese,
            'lignes_releve': lignes,
            'operations_releve': operations,
        })
        return render(request, 'school_admin/directeur/finances/tresorerie.html', contexte)

    @staticmethod
    def _post_tresorerie(request, etablissement, is_directeur, annee):
        from school_admin.model.finances_model import LigneReleve, ReleveBancaire
        from school_admin.services.finances.rapprochement import (
            ajouter_ligne,
            cloturer_releve,
            creer_releve,
            depointer_ligne,
            pointer_ligne,
        )
        from school_admin.services.finances.transferts import annuler_transfert, enregistrer_transfert

        action = request.POST.get('action')
        actions_bilans = {
            'annuler_transfert', 'creer_releve', 'ajouter_ligne', 'pointer', 'depointer', 'cloturer',
        }
        if action in actions_bilans and not _exiger_bilans(request, is_directeur):
            return _retour(request, 'directeur:finances_tresorerie')
        releve = None
        try:
            if action == 'virement':
                montant = parser_montant(request.POST.get('montant'))
                if montant is None:
                    raise ValueError("Indiquez un montant supérieur à 0.")
                source = CompteTresorerie.objects.get(
                    pk=request.POST.get('compte_source_id'), etablissement=etablissement,
                )
                destination = CompteTresorerie.objects.get(
                    pk=request.POST.get('compte_destination_id'), etablissement=etablissement,
                )
                _mouvement, ecriture = enregistrer_transfert(
                    etablissement,
                    source,
                    destination,
                    _date(request.POST.get('date_mouvement')),
                    montant,
                    reference=request.POST.get('reference') or '',
                    motif=request.POST.get('libelle') or '',
                    annee_scolaire=annee,
                    user=request.user,
                )
                if ecriture is None:
                    messages.warning(
                        request,
                        "Transfert enregistré. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                    )
                else:
                    messages.success(request, "Transfert enregistré. Ce n'est pas une entrée.")
            elif action == 'annuler_transfert':
                mouvement = get_object_or_404(
                    MouvementTresorerie, pk=request.POST.get('mvt_id'), etablissement=etablissement,
                )
                annuler_transfert(mouvement, request.POST.get('motif'), user=request.user)
                messages.success(request, "Transfert annulé. Il reste dans l'historique.")
            elif action == 'creer_releve':
                compte_treso = CompteTresorerie.objects.get(
                    pk=request.POST.get('compte_id'), etablissement=etablissement,
                )
                releve = creer_releve(
                    etablissement,
                    compte_treso,
                    request.POST.get('reference') or '',
                    _date(request.POST.get('date_debut')),
                    _date(request.POST.get('date_fin')),
                    request.POST.get('solde_ouverture') or 0,
                    request.POST.get('solde_cloture') or 0,
                    user=request.user,
                )
                messages.success(request, "Relevé enregistré. Aucune écriture n'a été passée.")
            elif action == 'ajouter_ligne':
                releve = get_object_or_404(
                    ReleveBancaire, pk=request.POST.get('releve_id'), etablissement=etablissement,
                )
                ajouter_ligne(
                    releve,
                    _date(request.POST.get('date_operation')),
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
                    EcritureComptable, pk=request.POST.get('ecriture_id'), etablissement=etablissement,
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
                releve = get_object_or_404(
                    ReleveBancaire, pk=request.POST.get('releve_id'), etablissement=etablissement,
                )
                cloturer_releve(releve, user=request.user)
                messages.success(request, "Relevé clôturé.")
        except (CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError) as exc:
            messages.error(
                request,
                str(exc) if isinstance(exc, ValueError) else "Données de trésorerie invalides.",
            )
        extra = {'vue': 'pointage'} if action in (
            'creer_releve', 'ajouter_ligne', 'pointer', 'depointer', 'cloturer',
        ) else None
        if extra and releve is not None:
            extra['releve_id'] = str(releve.pk)
        return _retour(request, 'directeur:finances_tresorerie', extra)

    @staticmethod
    @login_required
    def financements(request):
        etablissement, is_directeur, personnel, denied = _require_finances(request)
        if denied:
            return denied
        annee = ComptabiliteController._get_session_directeur(request, etablissement)
        filtres = lire_filtres(request)
        if request.method == 'POST':
            return FinancesController._post_financements(request, etablissement, is_directeur, annee)
        prets = PretEtablissement.objects.filter(etablissement=etablissement).select_related(
            'compte_tresorerie'
        ).prefetch_related(
            'echeances',
            Prefetch('remboursements', queryset=RemboursementPret.objects.select_related('compte_tresorerie')),
        )
        if filtres['q']:
            prets = prets.filter(Q(reference__icontains=filtres['q']) | Q(objet__icontains=filtres['q']))
        if filtres['statut']:
            prets = prets.filter(statut=filtres['statut'])
        contexte = _contexte(request, etablissement, is_directeur, personnel, annee, filtres, 'financements')
        contexte['prets'] = list(prets.order_by('-date_reception', '-id')[:80])
        return render(request, 'school_admin/directeur/finances/financements.html', contexte)

    @staticmethod
    def _post_financements(request, etablissement, is_directeur, annee):
        from school_admin.services.finances.prets import (
            ajouter_echeance,
            annuler_pret,
            annuler_remboursement,
            enregistrer_pret,
            enregistrer_remboursement,
        )

        if not _exiger_bilans(request, is_directeur):
            return _retour(request, 'directeur:finances_financements')
        action = request.POST.get('action')
        try:
            if action == 'ajouter_pret':
                compte_treso = CompteTresorerie.objects.get(
                    pk=request.POST.get('compte_id'), etablissement=etablissement,
                )
                montant = parser_montant(request.POST.get('montant'))
                if montant is None:
                    raise ValueError("Indiquez un montant supérieur à 0.")
                _pret, ecriture = enregistrer_pret(
                    etablissement,
                    compte_treso,
                    _date(request.POST.get('date_reception')),
                    montant,
                    request.POST.get('reference') or '',
                    request.POST.get('objet') or '',
                    taux=Decimal(str(request.POST.get('taux') or '0').replace(',', '.')),
                    duree_mois=request.POST.get('duree_mois') or None,
                    annee_scolaire=annee,
                    user=request.user,
                    fichier=request.FILES.get('justificatif'),
                )
                if ecriture is None:
                    messages.warning(
                        request,
                        "Prêt enregistré. L'écriture n'a pas été générée : le plan de comptes n'est pas prêt.",
                    )
                else:
                    messages.success(
                        request,
                        "Prêt enregistré. La trésorerie et la dette augmentent, pas le résultat.",
                    )
            elif action == 'ajouter_echeance':
                pret = get_object_or_404(
                    PretEtablissement, pk=request.POST.get('pret_id'), etablissement=etablissement,
                )
                ajouter_echeance(
                    pret,
                    _date(request.POST.get('date_echeance')),
                    request.POST.get('capital_prevu') or 0,
                    request.POST.get('interets_prevus') or 0,
                    request.POST.get('frais_prevus') or 0,
                )
                messages.success(request, "Échéance prévue enregistrée. Aucune écriture n'a été passée.")
            elif action == 'rembourser_pret':
                pret = get_object_or_404(
                    PretEtablissement, pk=request.POST.get('pret_id'), etablissement=etablissement,
                )
                compte_treso = None
                if request.POST.get('compte_id'):
                    compte_treso = CompteTresorerie.objects.get(
                        pk=request.POST.get('compte_id'), etablissement=etablissement,
                    )
                enregistrer_remboursement(
                    pret,
                    _date(request.POST.get('date_remboursement')),
                    capital=request.POST.get('capital') or 0,
                    interets=request.POST.get('interets') or 0,
                    frais=request.POST.get('frais') or 0,
                    motif=request.POST.get('motif') or '',
                    compte_tresorerie=compte_treso,
                    user=request.user,
                )
                messages.success(
                    request,
                    "Remboursement enregistré. Le capital diminue la dette. Intérêts et frais sont des charges.",
                )
            elif action == 'annuler_remboursement':
                remboursement = get_object_or_404(
                    RemboursementPret, pk=request.POST.get('remboursement_id'), etablissement=etablissement,
                )
                annuler_remboursement(remboursement, request.POST.get('motif'), user=request.user)
                messages.success(request, "Remboursement annulé. La ligne est conservée.")
            elif action == 'annuler_pret':
                pret = get_object_or_404(
                    PretEtablissement, pk=request.POST.get('pret_id'), etablissement=etablissement,
                )
                annuler_pret(pret, request.POST.get('motif'), user=request.user)
                messages.success(request, "Prêt annulé. La ligne est conservée.")
        except (CompteTresorerie.DoesNotExist, ValueError, InvalidOperation, TypeError) as exc:
            messages.error(
                request,
                str(exc) if isinstance(exc, ValueError) else "Données de financement invalides.",
            )
        return _retour(request, 'directeur:finances_financements')
