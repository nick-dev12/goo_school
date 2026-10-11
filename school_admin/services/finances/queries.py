"""Listes et filtres de l'interface Finances. Aucune écriture."""
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Q, Sum
from django.utils import timezone

from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.comptabilite_eleve_model import PaiementEleve
from school_admin.model.comptabilite_generale_model import FactureFournisseur, MouvementTresorerie
from school_admin.model.finances_model import (
    PaiementCharge,
    PretEtablissement,
    RecetteEtablissement,
    RemboursementPret,
)
from school_admin.services.caisse import bornes_mois, parser_mois

ZERO = Decimal('0.00')
VUES_ENTREES = ('scolarite', 'activite', 'subvention', 'divers')
VUES_SORTIES = ('jour', 'mois')
VUES_TRESORERIE = ('comptes', 'pointage')


def lire_filtres(request, vues_autorisees=(), vue_defaut=''):
    aujourdhui = timezone.now().date()
    bornes = bornes_mois(parser_mois(request.GET.get('mois') or request.POST.get('mois'), aujourdhui))
    vue = (request.GET.get('vue') or request.POST.get('vue') or vue_defaut or '').strip()
    if vues_autorisees and vue not in vues_autorisees:
        vue = vue_defaut
    return {
        'bornes': bornes,
        'compte_id': (request.GET.get('compte') or request.POST.get('compte') or '').strip(),
        'statut': (request.GET.get('statut') or request.POST.get('statut') or '').strip(),
        'q': (request.GET.get('q') or request.POST.get('q') or '').strip(),
        'vue': vue,
        'releve_id': (request.GET.get('releve') or request.POST.get('releve') or '').strip(),
    }


def query_filtres(filtres, **extra):
    data = {'mois': filtres['bornes'].valeur}
    for cle in ('compte_id', 'statut', 'q', 'vue', 'releve_id'):
        valeur = extra[cle] if cle in extra else filtres.get(cle)
        if valeur:
            nom = {'compte_id': 'compte', 'releve_id': 'releve'}.get(cle, cle)
            data[nom] = valeur
    for nom, valeur in extra.items():
        if nom in ('compte_id', 'releve_id', 'statut', 'q', 'vue'):
            continue
        if valeur not in (None, ''):
            data[nom] = valeur
    return urlencode(data)


def _dec(valeur):
    if valeur is None:
        return ZERO
    return Decimal(str(valeur))


def totaux_subventions(etablissement, date_debut, date_fin):
    lignes = RecetteEtablissement.objects.filter(
        etablissement=etablissement,
        nature='subvention',
        statut='validee',
        date_recette__gte=date_debut,
        date_recette__lte=date_fin,
    ).select_related('categorie__compte_comptable')
    par_destination = []
    hors_classe_7 = ZERO
    for code, label in RecetteEtablissement.DESTINATION_CHOICES:
        choisi = [item for item in lignes if item.destination == code]
        if not choisi:
            continue
        net = sum((item.net() for item in choisi), ZERO)
        dans_resultat = sum((item.net() for item in choisi if item.dans_le_resultat()), ZERO)
        hors = sum((item.net() for item in choisi if not item.dans_le_resultat()), ZERO)
        hors_classe_7 += hors
        par_destination.append({
            'code': code,
            'label': label,
            'net': net,
            'dans_resultat': dans_resultat,
            'hors_resultat': hors,
        })
    return {
        'lignes': par_destination,
        'hors_classe_7': hors_classe_7,
        'equipement': sum(
            (item['net'] for item in par_destination if item['code'] == 'equipement'),
            ZERO,
        ),
    }


def dernieres_operations(etablissement, date_debut, date_fin, limite=3):
    items = []
    for paiement in PaiementEleve.objects.filter(
        etablissement=etablissement,
        date_paiement__date__gte=date_debut,
        date_paiement__date__lte=date_fin,
    ).select_related('eleve').order_by('-date_paiement')[:limite]:
        jour = paiement.date_paiement.date() if paiement.date_paiement else date_debut
        items.append({
            'date': jour,
            'libelle': f"Scolarité — {paiement.eleve.nom_complet}",
            'montant': paiement.montant,
            'sens': 'entree',
            'statut': 'validee',
        })
    for recette in RecetteEtablissement.objects.filter(
        etablissement=etablissement,
        date_recette__gte=date_debut,
        date_recette__lte=date_fin,
    ).order_by('-date_recette', '-id')[:limite]:
        items.append({
            'date': recette.date_recette,
            'libelle': recette.libelle or recette.get_nature_display(),
            'montant': recette.montant,
            'sens': 'entree',
            'statut': recette.statut,
        })
    for depense in DepenseEtablissement.objects.filter(
        etablissement=etablissement,
        date_depense__gte=date_debut,
        date_depense__lte=date_fin,
    ).order_by('-date_depense', '-id')[:limite]:
        items.append({
            'date': depense.date_depense,
            'libelle': depense.libelle_affiche() if hasattr(depense, 'libelle_affiche') else (
                depense.libelle or depense.get_motif_display()
            ),
            'montant': depense.montant,
            'sens': 'sortie',
            'statut': depense.statut,
        })
    for paiement in PaiementCharge.objects.filter(
        etablissement=etablissement,
        date_paiement__gte=date_debut,
        date_paiement__lte=date_fin,
    ).select_related('facture').order_by('-date_paiement', '-id')[:limite]:
        items.append({
            'date': paiement.date_paiement,
            'libelle': f"Paiement facture {paiement.facture.numero}",
            'montant': paiement.montant,
            'sens': 'sortie',
            'statut': paiement.statut,
        })
    for mouvement in MouvementTresorerie.objects.filter(
        etablissement=etablissement,
        date_mouvement__gte=date_debut,
        date_mouvement__lte=date_fin,
    ).select_related('compte_source', 'compte_destination').order_by('-date_mouvement', '-id')[:limite]:
        items.append({
            'date': mouvement.date_mouvement,
            'libelle': mouvement.libelle or 'Transfert',
            'montant': mouvement.montant,
            'sens': 'transfert',
            'statut': getattr(mouvement, 'statut', 'validee'),
        })
    for pret in PretEtablissement.objects.filter(
        etablissement=etablissement,
        date_reception__gte=date_debut,
        date_reception__lte=date_fin,
    ).order_by('-date_reception', '-id')[:limite]:
        items.append({
            'date': pret.date_reception,
            'libelle': f"Prêt {pret.reference}",
            'montant': pret.montant,
            'sens': 'dette',
            'statut': pret.statut,
        })
    for remb in RemboursementPret.objects.filter(
        etablissement=etablissement,
        date_remboursement__gte=date_debut,
        date_remboursement__lte=date_fin,
    ).select_related('pret').order_by('-date_remboursement', '-id')[:limite]:
        items.append({
            'date': remb.date_remboursement,
            'libelle': f"Remboursement {remb.pret.reference}",
            'montant': remb.total,
            'sens': 'dette',
            'statut': remb.statut,
        })
    items.sort(key=lambda ligne: ligne['date'], reverse=True)
    return items[:limite]


def filtrer_recettes(etablissement, filtres, nature=None):
    qs = RecetteEtablissement.objects.filter(
        etablissement=etablissement,
        date_recette__gte=filtres['bornes'].debut,
        date_recette__lte=filtres['bornes'].fin,
    ).select_related('categorie__compte_comptable', 'compte_tresorerie')
    if nature:
        qs = qs.filter(nature=nature)
    if filtres['compte_id']:
        qs = qs.filter(compte_tresorerie_id=filtres['compte_id'])
    if filtres['statut']:
        qs = qs.filter(statut=filtres['statut'])
    if filtres['q']:
        qs = qs.filter(
            Q(libelle__icontains=filtres['q'])
            | Q(origine__icontains=filtres['q'])
            | Q(reference__icontains=filtres['q'])
        )
    return qs.order_by('-date_recette', '-id')[:80]


def filtrer_paiements_scolarite(etablissement, filtres, annee_scolaire=None):
    qs = PaiementEleve.objects.filter(
        etablissement=etablissement,
        date_paiement__date__gte=filtres['bornes'].debut,
        date_paiement__date__lte=filtres['bornes'].fin,
    ).select_related('eleve')
    if annee_scolaire is not None:
        qs = qs.filter(annee_scolaire=annee_scolaire)
    if filtres['q']:
        qs = qs.filter(
            Q(eleve__nom__icontains=filtres['q'])
            | Q(eleve__prenom__icontains=filtres['q'])
            | Q(numero_recu__icontains=filtres['q'])
        )
    return qs.order_by('-date_paiement')[:80]


def filtrer_sorties(etablissement, filtres):
    qs = DepenseEtablissement.objects.filter(
        etablissement=etablissement,
        date_depense__gte=filtres['bornes'].debut,
        date_depense__lte=filtres['bornes'].fin,
    ).select_related('fournisseur', 'categorie', 'compte_tresorerie')
    if filtres['compte_id']:
        qs = qs.filter(compte_tresorerie_id=filtres['compte_id'])
    if filtres['statut']:
        qs = qs.filter(statut=filtres['statut'])
    if filtres['q']:
        qs = qs.filter(Q(libelle__icontains=filtres['q']) | Q(motif__icontains=filtres['q']))
    return qs.order_by('-date_depense', '-id')[:80]


def filtrer_factures(etablissement, filtres):
    qs = FactureFournisseur.objects.filter(etablissement=etablissement).select_related(
        'fournisseur', 'categorie'
    )
    if filtres['q']:
        qs = qs.filter(
            Q(numero__icontains=filtres['q'])
            | Q(libelle__icontains=filtres['q'])
            | Q(fournisseur__nom__icontains=filtres['q'])
        )
    if filtres['statut']:
        qs = qs.filter(statut=filtres['statut'])
    return qs.order_by('-date_facture', '-id')[:80]


def total_exploitation_entrees(etablissement, filtres):
    scolarite = PaiementEleve.objects.filter(
        etablissement=etablissement,
        date_paiement__date__gte=filtres['bornes'].debut,
        date_paiement__date__lte=filtres['bornes'].fin,
    ).aggregate(s=Sum('montant'))['s']
    recettes = RecetteEtablissement.objects.filter(
        etablissement=etablissement,
        statut='validee',
        date_recette__gte=filtres['bornes'].debut,
        date_recette__lte=filtres['bornes'].fin,
    )
    if filtres['compte_id']:
        recettes = recettes.filter(compte_tresorerie_id=filtres['compte_id'])
    exploitation = ZERO
    hors = ZERO
    for recette in recettes.select_related('categorie__compte_comptable'):
        net = recette.net()
        if recette.dans_le_resultat():
            exploitation += net
        else:
            hors += net
    return _dec(scolarite) + exploitation, hors
