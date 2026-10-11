"""Comptabilité générale (V3) : tableau de bord, écritures, grand livre, balance, états, clôture, immobilisations."""
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from school_admin.controllers.comptabilite_controller import ComptabiliteController
from school_admin.controllers.recouvrement_controller import _require_compta
from school_admin.model.compte_user import CompteUser
from school_admin.model.comptabilite_generale_model import (
    CompteComptable,
    EcritureComptable,
    FournisseurEtablissement,
    Immobilisation,
    JournalComptable,
    LigneEcriture,
    PeriodeComptable,
)
from school_admin.services import compta_etats as ce
from school_admin.services import comptabilite_generale as cg
from school_admin.services.recouvrement import devise_etablissement


def _user(request):
    return request.user if isinstance(request.user, CompteUser) else None


def _date(valeur, defaut=None):
    try:
        return datetime.strptime((valeur or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return defaut


def _contexte(request, permission='comptabilite_bilans'):
    """(contexte commun, réponse de refus). Le contexte porte l'exercice choisi et la liste des exercices."""
    etablissement, is_directeur, personnel, denied = _require_compta(request, permission=permission)
    if denied:
        return None, denied
    annee = ComptabiliteController._get_session_directeur(request, etablissement)
    exercice = ce.exercice_selectionne(request, etablissement, annee)
    return {
        'etablissement': etablissement,
        'is_directeur': is_directeur,
        'personnel': personnel,
        'annee_scolaire_active': annee,
        'exercice': exercice,
        'exercices': ce.exercices(etablissement),
        'devise_monnaie': devise_etablissement(etablissement),
        'aujourdhui': timezone.localdate(),
    }, None


def _csv(nom, entetes, lignes):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nom}.csv"'
    response.write('﻿')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(entetes)
    for ligne in lignes:
        writer.writerow(ligne)
    return response


def _num(valeur):
    return f"{valeur:.2f}".replace('.', ',')


class ComptaEtatsController:
    # ------------------------------------------------------------------ tableau de bord
    @staticmethod
    @login_required
    def hub(request):
        ctx, denied = _contexte(request)
        if denied:
            messages.error(request, "Accès non autorisé.")
            return denied
        etab, exo = ctx['etablissement'], ctx['exercice']
        cr = ce.compte_de_resultat(etab, exo)
        b = ce.bilan(etab, exo)
        series = ce.series_mensuelles(etab, exo, jusqu_a=min(exo.date_fin, ctx['aujourdhui'])
                                      if exo.date_debut <= ctx['aujourdhui'] else None)
        soldes = ce.soldes_comptes(etab, exo)
        creances = sum((r['solde'] for r in soldes.values() if r['compte'].numero.startswith('41') and r['solde'] > 0),
                       Decimal('0'))
        dettes_fourn = sum((-r['solde'] for r in soldes.values() if r['compte'].numero.startswith('40') and r['solde'] < 0),
                           Decimal('0'))
        nb_ecritures = EcritureComptable.objects.filter(etablissement=etab, exercice=exo).count()
        ctx.update({
            'cg_nav': 'hub',
            'cr': cr,
            'bilan': b,
            'creances': creances,
            'dettes_fournisseurs': dettes_fourn,
            'nb_ecritures': nb_ecritures,
            'controles': ce.controles(etab, exo),
            'tresorerie_comptes': ce.soldes_tresorerie(etab, exo),
            'dernieres': ce.ecritures_filtrees(etab, exo)[:6],
            'regime_comptable': cg.get_or_create_parametres_comptabilite(etab).regime_comptable,
            'charts': {
                'mensuel': series,
                'charges': ce.repartition(etab, exo, '6'),
                'produits': ce.repartition(etab, exo, '7', limite=5),
            },
        })
        return render(request, 'school_admin/directeur/comptabilite_generale/hub.html', ctx)

    # ------------------------------------------------------------------ journaux et saisie
    @staticmethod
    @login_required
    def journaux(request):
        ctx, denied = _contexte(request)
        if denied:
            return denied
        etab, exo = ctx['etablissement'], ctx['exercice']
        cg.ensure_journaux(etab)
        if request.method == 'POST':
            action = request.POST.get('action')
            try:
                if action == 'saisir':
                    jnl = get_object_or_404(JournalComptable, pk=request.POST.get('journal_id'), etablissement=etab)
                    jour = _date(request.POST.get('date_ecriture'))
                    if jour is None:
                        raise ValueError("Date de pièce invalide.")
                    lignes = [
                        {'compte_id': c, 'libelle': l, 'debit': d, 'credit': k, 'auxiliaire': a}
                        for c, l, d, k, a in zip(
                            request.POST.getlist('compte_id'), request.POST.getlist('ligne_libelle'),
                            request.POST.getlist('debit'), request.POST.getlist('credit'),
                            request.POST.getlist('auxiliaire'),
                        )
                    ]
                    e = ce.saisir_ecriture(etab, jnl, jour, request.POST.get('libelle'), lignes,
                                           reference=request.POST.get('reference') or '', user=_user(request))
                    messages.success(request, f"Écriture {e.journal.code}-{e.numero} enregistrée.")
                elif action == 'extourner':
                    e = get_object_or_404(EcritureComptable, pk=request.POST.get('ecriture_id'), etablissement=etab)
                    jour = _date(request.POST.get('date_extourne'), timezone.localdate())
                    ext = cg.extourner(e, jour, (request.POST.get('motif') or '').strip(), user=_user(request))
                    messages.success(request, f"Écriture contrepassée par la pièce {ext.journal.code}-{ext.numero}.")
            except ValueError as exc:
                messages.error(request, str(exc))
            params = request.GET.copy()
            params.pop('saisie', None)
            return redirect(f"{request.path}?{params.urlencode()}" if params else request.path)

        f = {
            'journal': request.GET.get('journal', ''),
            'du': _date(request.GET.get('du')),
            'au': _date(request.GET.get('au')),
            'q': (request.GET.get('q') or '').strip(),
            'compte': request.GET.get('compte') or '',
        }
        qs = ce.ecritures_filtrees(etab, exo, f['journal'], f['du'], f['au'], f['q'], f['compte'] or None)
        if request.GET.get('export') == 'csv':
            rows = []
            for e in qs:
                for l in e.lignes.all():
                    rows.append([e.journal.code, e.numero, e.date_ecriture.strftime('%d/%m/%Y'), l.compte.numero,
                                 l.compte.libelle, l.libelle or e.libelle, l.auxiliaire, e.reference,
                                 _num(l.debit), _num(l.credit)])
            return _csv(f"journal-{exo.libelle}", ['Journal', 'Pièce', 'Date', 'Compte', 'Intitulé', 'Libellé',
                                                   'Tiers', 'Référence', 'Débit', 'Crédit'], rows)
        from django.core.paginator import Paginator
        from django.db.models import Sum

        page = Paginator(qs, 20).get_page(request.GET.get('page'))
        ecritures = list(page.object_list)
        total_d = (LigneEcriture.objects.filter(ecriture__in=qs.values('id')).aggregate(s=Sum('debit'))['s']
                   or Decimal('0'))
        params = request.GET.copy()
        params.pop('page', None)
        params.pop('saisie', None)
        ctx.update({
            'cg_nav': 'journaux',
            'filtres': f,
            'ecritures': ecritures,
            'page': page,
            'params_sans_page': params.urlencode(),
            'nb_resultats': page.paginator.count,
            'total_debit': total_d,
            'stats_journaux': ce.stats_journaux(etab, exo),
            'journaux_saisie': JournalComptable.objects.filter(etablissement=etab, actif=True).exclude(code='AN'),
            'comptes': CompteComptable.objects.filter(etablissement=etab, actif=True).order_by('numero'),
            'extournees': ce.ids_extournees(etab),
            'exercice_ouvert': exo.est_ouvert(),
        })
        return render(request, 'school_admin/directeur/comptabilite_generale/journaux.html', ctx)

    # ------------------------------------------------------------------ grand livre
    @staticmethod
    @login_required
    def grand_livre(request):
        ctx, denied = _contexte(request)
        if denied:
            return denied
        etab, exo = ctx['etablissement'], ctx['exercice']
        compte = None
        if request.GET.get('compte'):
            compte = CompteComptable.objects.filter(etablissement=etab, pk=request.GET['compte']).first()
        du, au = _date(request.GET.get('du')), _date(request.GET.get('au'))
        blocs = ce.grand_livre(etab, exo, compte=compte, du=du, au=au, limite_comptes=None if compte else 40)
        if request.GET.get('export') == 'csv':
            rows = []
            for b in blocs:
                rows.append([b['compte'].numero, b['compte'].libelle, '', '', 'Report', '', '', _num(b['report'])])
                for r in b['rows']:
                    rows.append([b['compte'].numero, b['compte'].libelle, r['date'].strftime('%d/%m/%Y'),
                                 f"{r['journal']}-{r['piece']}", r['libelle'], _num(r['debit']), _num(r['credit']),
                                 _num(r['solde'])])
            return _csv(f"grand-livre-{exo.libelle}", ['Compte', 'Intitulé', 'Date', 'Pièce', 'Libellé', 'Débit',
                                                       'Crédit', 'Solde'], rows)
        ctx.update({
            'cg_nav': 'grand_livre',
            'blocs': blocs,
            'compte_choisi': compte,
            'du': du, 'au': au,
            'comptes': CompteComptable.objects.filter(etablissement=etab).order_by('numero'),
        })
        return render(request, 'school_admin/directeur/comptabilite_generale/grand_livre.html', ctx)

    # ------------------------------------------------------------------ balance
    @staticmethod
    @login_required
    def balance(request):
        ctx, denied = _contexte(request)
        if denied:
            return denied
        etab, exo = ctx['etablissement'], ctx['exercice']
        du, au = _date(request.GET.get('du')), _date(request.GET.get('au'))
        bal = ce.balance_generale(etab, exo, du, au)
        if request.GET.get('export') == 'csv':
            rows = []
            for bloc in bal['classes']:
                for r in bloc['rows']:
                    rows.append([r['compte'].numero, r['compte'].libelle, _num(r['ouv_debit']), _num(r['ouv_credit']),
                                 _num(r['mvt_debit']), _num(r['mvt_credit']), _num(r['solde_debit']),
                                 _num(r['solde_credit'])])
            return _csv(f"balance-{exo.libelle}", ['Compte', 'Intitulé', 'Ouverture débit', 'Ouverture crédit',
                                                   'Mouvements débit', 'Mouvements crédit', 'Solde débiteur',
                                                   'Solde créditeur'], rows)
        ctx.update({'cg_nav': 'balance', 'balance': bal, 'du': du, 'au': au,
                    'charts': {'classes': [{'label': f"Classe {b['classe']}",
                                            'debit': float(b['totaux'].get('mvt_debit', 0)),
                                            'credit': float(b['totaux'].get('mvt_credit', 0))}
                                           for b in bal['classes']]}})
        return render(request, 'school_admin/directeur/comptabilite_generale/balance.html', ctx)

    # ------------------------------------------------------------------ états financiers
    @staticmethod
    @login_required
    def etats(request):
        ctx, denied = _contexte(request)
        if denied:
            return denied
        etab, exo = ctx['etablissement'], ctx['exercice']
        cr = ce.compte_de_resultat(etab, exo)
        b = ce.bilan(etab, exo)
        if request.GET.get('export') == 'csv':
            rows = [['COMPTE DE RÉSULTAT', '', '']]
            rows += [['Produits', p['code'], _num(p['montant'])] for p in cr['produits']]
            rows += [['Charges', c['code'], _num(c['montant'])] for c in cr['charges']]
            rows += [['Résultat net', '', _num(cr['resultat'])], ['BILAN', '', '']]
            rows += [[r['cote'], r['libelle'], _num(r['montant'])] for r in b['rubriques'].values()]
            rows += [['Total actif', '', _num(b['total_actif'])], ['Total passif', '', _num(b['total_passif'])]]
            return _csv(f"etats-financiers-{exo.libelle}", ['Rubrique', 'Détail', 'Montant'], rows)
        ctx.update({
            'cg_nav': 'etats',
            'cr': cr,
            'bilan': b,
            'onglet': request.GET.get('vue', 'resultat'),
            'charts': {
                'mensuel': ce.series_mensuelles(etab, exo),
                'charges': ce.repartition(etab, exo, '6'),
                'bilan': {
                    'actif': [float(b['actif_immo_net']), float(b['actif_circulant']), float(b['tresorerie_actif'])],
                    'passif': [float(b['capitaux_propres']), float(b['dettes_financieres']),
                               float(b['passif_circulant']), float(b['tresorerie_passif'])],
                },
            },
        })
        return render(request, 'school_admin/directeur/comptabilite_generale/etats.html', ctx)

    # ------------------------------------------------------------------ exercices et clôture
    @staticmethod
    @login_required
    def exercices(request):
        ctx, denied = _contexte(request)
        if denied:
            return denied
        etab, exo = ctx['etablissement'], ctx['exercice']
        if request.method == 'POST':
            action = request.POST.get('action')
            try:
                if action in ('verrouiller', 'deverrouiller'):
                    periode = get_object_or_404(PeriodeComptable, pk=request.POST.get('periode_id'), exercice=exo)
                    periode.verrouillee = action == 'verrouiller'
                    periode.date_verrouillage = timezone.now() if periode.verrouillee else None
                    periode.save(update_fields=['verrouillee', 'date_verrouillage'])
                    messages.success(request, f"Période « {periode.libelle} » "
                                              f"{'verrouillée' if periode.verrouillee else 'déverrouillée'}.")
                elif action == 'cloturer':
                    res = ce.cloturer_exercice(exo, user=_user(request))
                    messages.success(request, f"Exercice {exo.libelle} clôturé. Résultat reporté : "
                                              f"{res['resultat']:,.0f}".replace(',', ' ')
                                     + f" — à-nouveaux passés dans {res['suivant'].libelle}.")
                elif action == 'rouvrir':
                    ce.rouvrir_exercice(exo)
                    messages.success(request, f"Exercice {exo.libelle} rouvert. Les à-nouveaux générés ont été retirés.")
                elif action == 'creer_exercice':
                    annee = int(request.POST.get('annee'))
                    nouveau = cg.exercice_pour_date(etab, date(annee, 1, 1))
                    request.session['cg_exercice_id'] = nouveau.pk
                    messages.success(request, f"Exercice {nouveau.libelle} prêt.")
                elif action == 'enregistrer_regime':
                    _, changed = cg.enregistrer_regime_comptable(
                        etab, (request.POST.get('regime_comptable') or '').strip(),
                        annee_scolaire=ctx['annee_scolaire_active'])
                    messages.success(request, "Régime comptable enregistré." if changed
                                     else "Le régime comptable est déjà à jour.")
            except (ValueError, TypeError) as exc:
                messages.error(request, str(exc))
            return redirect('directeur:cg_exercices')

        params = cg.get_or_create_parametres_comptabilite(etab)
        periodes = list(exo.periodes.filter(type_periode='mois'))
        mensuel = ce.series_mensuelles(etab, exo)
        for i, p in enumerate(periodes):
            p.nb_ecritures = EcritureComptable.objects.filter(
                etablissement=etab, exercice=exo, date_ecriture__gte=p.date_debut, date_ecriture__lte=p.date_fin,
            ).count()
            p.resultat = (mensuel['produits'][i] - mensuel['charges'][i]) if i < len(mensuel['labels']) else 0
        ctx.update({
            'cg_nav': 'exercices',
            'periodes_mois': periodes,
            'nb_verrouillees': sum(1 for p in periodes if p.verrouillee),
            'periodes_autres': exo.periodes.exclude(type_periode='mois'),
            'parametres_comptabilite': params,
            'regime_comptable': params.regime_comptable,
            'regime_verrouille': cg.regime_est_verrouille(etab, ctx['annee_scolaire_active']),
            'controles': ce.controles(etab, exo),
            'cr': ce.compte_de_resultat(etab, exo),
            'an_existe': EcritureComptable.objects.filter(etablissement=etab, source='a_nouveaux',
                                                          source_id=exo.id).exists(),
            'annee_suivante': max([e.date_debut.year for e in ctx['exercices']] + [exo.date_debut.year]) + 1,
        })
        return render(request, 'school_admin/directeur/comptabilite_generale/exercices.html', ctx)

    # ------------------------------------------------------------------ immobilisations
    @staticmethod
    @login_required
    def immobilisations(request):
        ctx, denied = _contexte(request)
        if denied:
            return denied
        etab, exo = ctx['etablissement'], ctx['exercice']
        from school_admin.model.finances_model import CompteTresorerie

        if request.method == 'POST':
            action = request.POST.get('action')
            try:
                if action == 'ajouter_immo':
                    libelle = (request.POST.get('libelle') or '').strip()
                    valeur = Decimal(str(request.POST.get('valeur_origine') or '0').replace(' ', '').replace(',', '.'))
                    duree = max(int(request.POST.get('duree_annees') or 5), 1)
                    jour = _date(request.POST.get('date_acquisition'))
                    if not libelle or valeur <= 0 or jour is None:
                        raise ValueError("Libellé, valeur et date d'acquisition sont obligatoires.")
                    categorie = request.POST.get('categorie') or 'autre'
                    cpt_num = cg.COMPTES_IMMOBILISATION.get(categorie, cg.COMPTES_IMMOBILISATION['autre'])[0]
                    immo = Immobilisation.objects.create(
                        etablissement=etab, libelle=libelle, categorie=categorie, date_acquisition=jour,
                        valeur_origine=valeur, duree_annees=duree, compte_immobilisation=cg.compte(etab, cpt_num),
                    )
                    financement = request.POST.get('financement') or 'aucun'
                    if financement == 'comptant':
                        treso = CompteTresorerie.objects.get(pk=request.POST.get('compte_id'), etablissement=etab)
                        cg.pont_acquisition_immobilisation(immo, compte_tresorerie=treso, user=_user(request))
                    elif financement == 'credit':
                        fournisseur = FournisseurEtablissement.objects.filter(
                            pk=request.POST.get('fournisseur_id') or 0, etablissement=etab).first()
                        cg.pont_acquisition_immobilisation(immo, fournisseur=fournisseur, user=_user(request))
                    messages.success(request, f"« {libelle} » enregistré"
                                              + (" et comptabilisé." if financement != 'aucun' else " (sans écriture d'achat)."))
                elif action == 'amortir':
                    immo = get_object_or_404(Immobilisation, pk=request.POST.get('immo_id'), etablissement=etab)
                    cg.pont_amortissement(immo, user=_user(request), exercice=exo)
                    messages.success(request, f"Dotation {exo.libelle} passée pour « {immo.libelle} ».")
                elif action == 'amortir_tout':
                    nb = 0
                    for immo in Immobilisation.objects.filter(etablissement=etab, actif=True):
                        try:
                            cg.pont_amortissement(immo, user=_user(request), exercice=exo)
                            nb += 1
                        except ValueError:
                            continue
                    messages.success(request, f"{nb} dotation(s) passée(s) pour {exo.libelle}.")
            except (ValueError, TypeError, InvalidOperation, CompteTresorerie.DoesNotExist) as exc:
                messages.error(request, str(exc) or "Données invalides.")
            return redirect('directeur:cg_immobilisations')

        biens = []
        total = {'brut': Decimal('0'), 'amort': Decimal('0'), 'vnc': Decimal('0'), 'dotation': Decimal('0')}
        passees = set(EcritureComptable.objects.filter(etablissement=etab, source__startswith='amort-',
                                                       exercice=exo).values_list('source_id', flat=True))
        for immo in Immobilisation.objects.filter(etablissement=etab, actif=True).select_related('compte_immobilisation'):
            plan = cg.plan_amortissement(immo)
            amort = cg.amortissements_comptabilises(immo)
            dotation = cg.dotation_pour_annee(immo, exo.date_debut.year)
            vnc = immo.valeur_origine - amort
            pct = int(amort / immo.valeur_origine * 100) if immo.valeur_origine else 0
            biens.append({'immo': immo, 'plan': plan, 'amort': amort, 'vnc': vnc, 'dotation': dotation,
                          'dotation_passee': immo.id in passees, 'pct': pct,
                          'acquise': EcritureComptable.objects.filter(source='acquisition_immo', source_id=immo.id).exists()})
            total['brut'] += immo.valeur_origine
            total['amort'] += amort
            total['vnc'] += vnc
            total['dotation'] += dotation
        par_categorie = {}
        for b in biens:
            cat = b['immo'].get_categorie_display()
            par_categorie[cat] = par_categorie.get(cat, 0) + float(b['vnc'])
        ctx.update({
            'cg_nav': 'immobilisations',
            'biens': biens,
            'total': total,
            'categories': Immobilisation._meta.get_field('categorie').choices,
            'comptes_tresorerie': CompteTresorerie.objects.filter(etablissement=etab, actif=True, statut='ouvert'),
            'fournisseurs': FournisseurEtablissement.objects.filter(etablissement=etab, actif=True),
            'charts': {'categories': [{'label': k, 'montant': v} for k, v in par_categorie.items()]},
        })
        return render(request, 'school_admin/directeur/comptabilite_generale/immobilisations.html', ctx)
