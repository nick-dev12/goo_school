"""Outils de l'assistant direction pour les modules de gestion récents.

Finances (situation, recettes, sorties, charges, transferts, prêts), Salaires et paiements, Contrôle des
cours (pointage), Cahiers de texte et Rappels automatiques.

Chaque écriture passe par les mêmes services que les pages (écritures comptables, soldes de trésorerie,
journal) et reste soumise à la carte de confirmation « oui / modifier / annuler ».
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone

from school_admin.services.assistant_actions import (
    ActionSpec,
    _emit,
    _err,
    _incomplete,
    _ok,
    _parse_date,
    _parse_money,
    _pending,
    _reverse,
    register_action,
)

_STR = {'type': 'string'}
LIMITE = 25

MOIS_FR = {
    'janvier': 1, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6, 'juillet': 7,
    'aout': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12,
}


# --------------------------------------------------------------------------- utilitaires
def _sans_accents(texte):
    return ''.join(c for c in unicodedata.normalize('NFD', texte or '') if unicodedata.category(c) != 'Mn').lower()


def _utilisateur(ctx):
    """Auteur des écritures : le membre du personnel connecté, sinon l'établissement (directeur)."""
    return getattr(ctx, 'personnel', None) or ctx.etablissement


def _devise(ctx):
    from school_admin.services.recouvrement import devise_etablissement

    return devise_etablissement(ctx.etablissement)


def _fmt(montant, ctx=None):
    if montant is None:
        return '—'
    texte = f"{Decimal(str(montant)):,.0f}".replace(',', ' ')
    return f"{texte} {_devise(ctx)}" if ctx is not None else texte


def _mois(raw):
    """Premier jour du mois demandé : « 2026-11 », « novembre », « novembre 2026 », « mois dernier »… ;
    le mois en cours par défaut."""
    aujourd_hui = date.today()
    texte = _sans_accents(str(raw or '')).strip()
    if not texte or 'ce mois' in texte or 'courant' in texte:
        return date(aujourd_hui.year, aujourd_hui.month, 1)
    if 'dernier' in texte or 'precedent' in texte or 'passe' in texte:
        total = aujourd_hui.year * 12 + aujourd_hui.month - 2
        return date(total // 12, total % 12 + 1, 1)
    m = re.search(r'(\d{4})-(\d{1,2})', texte)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    m = re.search(r'(\d{1,2})[/-](\d{4})', texte)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    for nom, numero in MOIS_FR.items():
        if nom in texte:
            annee = re.search(r'(\d{4})', texte)
            if annee:
                return date(int(annee.group(1)), numero, 1)
            # Sans année : le dernier mois de ce nom qui n'est pas dans le futur.
            an = aujourd_hui.year if numero <= aujourd_hui.month else aujourd_hui.year - 1
            return date(an, numero, 1)
    return date(aujourd_hui.year, aujourd_hui.month, 1)


def _libelle_mois(premier):
    from school_admin.services.salaires import libelle_mois

    return libelle_mois(premier)


def _comptes(ctx):
    from school_admin.model.finances_model import CompteTresorerie
    from school_admin.services.finances.tresorerie import assurer_comptes_defaut

    assurer_comptes_defaut(ctx.etablissement)
    return list(CompteTresorerie.objects.filter(etablissement=ctx.etablissement, actif=True, statut='ouvert'))


def _compte(ctx, raw, defaut='caisse'):
    """Compte de trésorerie par son nom ou son type (caisse, banque, mobile money, wave, orange money)."""
    comptes = _comptes(ctx)
    texte = _sans_accents(str(raw or '')).strip()
    if texte:
        for c in comptes:
            if texte == _sans_accents(c.libelle) or texte in _sans_accents(c.libelle):
                return c
        types = (('banque', 'banque'), ('bancaire', 'banque'), ('caisse', 'caisse'), ('espece', 'caisse'),
                 ('cash', 'caisse'), ('mobile', 'mobile_money'), ('wave', 'mobile_money'),
                 ('orange', 'mobile_money'), ('free money', 'mobile_money'))
        for mot, type_compte in types:
            if mot in texte:
                for c in comptes:
                    if c.type_compte == type_compte:
                        return c
        return None
    if defaut:
        for c in comptes:
            if c.type_compte == defaut:
                return c
    return comptes[0] if comptes else None


def _noms_comptes(ctx):
    return ', '.join(c.libelle for c in _comptes(ctx))


def _choix_comptes(ctx):
    return [{'value': c.libelle, 'label': c.libelle} for c in _comptes(ctx)]


def _decimal(raw, defaut=None):
    texte = str(raw if raw is not None else '').strip().replace(' ', '').replace(',', '.')
    if not texte:
        return defaut
    try:
        return Decimal(texte)
    except (InvalidOperation, ValueError):
        return defaut


def _erreur_service(exc):
    return _err(str(exc) or "Action impossible.")


def _trouver_personne(ctx, query, type_personne=''):
    """Enseignant ou membre du personnel par son nom. Renvoie (type, objet)."""
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur

    raw = (query or '').strip()
    if not raw:
        return None, None
    morceaux = [m for m in re.split(r'\s+', raw) if m]

    def chercher(modele):
        qs = modele.objects.filter(etablissement=ctx.etablissement, actif=True)
        for m in morceaux:
            qs = qs.filter(Q(nom__icontains=m) | Q(prenom__icontains=m))
        return qs.first()

    voulu = _sans_accents(type_personne)
    if not voulu.startswith('perso'):
        prof = chercher(Professeur)
        if prof:
            return 'enseignant', prof
    if not voulu.startswith('ensei') and not voulu.startswith('prof'):
        pers = chercher(PersonnelAdministratif)
        if pers:
            return 'personnel', pers
    return None, None


# =========================================================================== LECTURE
def tool_situation_financiere(ctx, args):
    from school_admin.services.caisse import bornes_mois
    from school_admin.services.finances.metrics import calculer_indicateurs
    from school_admin.services.finances.queries import dernieres_operations
    from school_admin.services.finances.tresorerie import solde_calcule

    premier = _mois(args.get('mois'))
    bornes = bornes_mois(premier)
    data = calculer_indicateurs(ctx.etablissement, bornes.debut, bornes.fin, ctx.annee_scolaire)
    ind = data['indicateurs']
    comptes = [{'compte': c.libelle, 'solde': _fmt(solde_calcule(c, a_date=bornes.fin), ctx)} for c in _comptes(ctx)]
    operations = [
        {'date': op['date'].isoformat() if op.get('date') else '', 'libelle': op['libelle'],
         'sens': op['sens'], 'montant': _fmt(op['montant'], ctx), 'statut': op.get('statut', '')}
        for op in dernieres_operations(ctx.etablissement, bornes.debut, bornes.fin, limite=6)
    ]
    return {
        'mois': bornes.label,
        'entrees': _fmt(ind['encaisse']['valeur'], ctx),
        'sorties': _fmt(ind['paye']['valeur'], ctx),
        'resultat': _fmt(ind['resultat']['valeur'], ctx),
        'disponible': _fmt(ind['disponible']['valeur'], ctx),
        'reste_a_recevoir_scolarite': _fmt(ind['creances']['valeur'], ctx),
        'charges_a_payer': _fmt(ind['engagements']['valeur'], ctx),
        'dettes': _fmt(ind['dettes']['valeur'], ctx),
        'soldes_comptes': comptes,
        'dernieres_operations': operations,
        'url': (_reverse('directeur:finances_situation') or '') + f'?mois={bornes.valeur}',
    }


def tool_paie_du_mois(ctx, args):
    from school_admin.services.salaires import paie_du_mois

    premier = _mois(args.get('mois'))
    paie = paie_du_mois(ctx.etablissement, ctx.annee_scolaire, premier)
    type_voulu = _sans_accents(args.get('type') or '')
    statuts = {'paye': 'payé', 'a_payer': 'à payer', 'a_saisir': 'heures à saisir', 'a_renseigner': 'à renseigner',
               'a_verifier': 'séances à vérifier', 'rien': 'rien à payer'}
    lignes = []
    for l in paie['lignes']:
        if type_voulu.startswith('ensei') and l.type != 'enseignant':
            continue
        if type_voulu.startswith('perso') and l.type != 'personnel':
            continue
        lignes.append({
            'nom': l.nom, 'type': l.type, 'mode': 'au mois' if l.mode == 'fixe' else "à l'heure",
            'montant_du': _fmt(l.montant, ctx) if l.montant is not None else None,
            'statut': statuts.get(l.statut, l.statut),
            'paye_le': l.paye_le.isoformat() if l.paye_le else None,
            'montant_paye': _fmt(l.montant_paye, ctx) if l.montant_paye else None,
            'blocage': l.bloque or None,
        })
    return {
        'mois': paie['libelle_mois'],
        'reste_a_verser': _fmt(paie['reste_a_verser'], ctx),
        'deja_verse': _fmt(paie['deja_verse'], ctx),
        'nb_prets_a_payer': len(paie['pretes']),
        'agents_payes_par_l_etat': paie['agents_etat'],
        'lignes': lignes[:60],
        'url': (_reverse('directeur:salaires') or '') + f'?mois={premier:%Y-%m}',
    }


def tool_historique_salaire(ctx, args):
    from school_admin.services.salaires import historique

    type_personne, personne = _trouver_personne(ctx, args.get('query') or args.get('nom'), args.get('type') or '')
    if not personne:
        return {'erreur': "Je ne trouve pas cette personne parmi les enseignants et le personnel actifs."}
    histo = historique(ctx.etablissement, type_personne, personne.id)
    mois = [{'mois': bloc['mois'],
             'paiements': [{'paye_le': x['paye_le'], 'montant': x['montant'], 'moyen': x['moyen'],
                            'detail': x['detail']} for x in bloc['paiements']]}
            for bloc in histo['mois'][:12]]
    return {
        'personne': personne.nom_complet,
        'type': type_personne,
        'total_verse': f"{histo['total']} {_devise(ctx)}",
        'nb_paiements': histo['nb'],
        'mois': mois,
        'url': (_reverse('directeur:salaires') or '') + f'?onglet={type_personne}',
    }


def tool_controle_cours(ctx, args):
    from school_admin.model.pointage_model import SeanceCours
    from school_admin.services import pointage as pt

    jour = _parse_date(args.get('date') or args.get('jour') or '') or timezone.localdate()
    a_verifier = SeanceCours.objects.filter(
        etablissement=ctx.etablissement, statut__in=('a_verifier', 'contestee'),
    ).select_related('professeur', 'classe', 'matiere').order_by('-date', 'heure_debut')
    prof = (args.get('professeur') or '').strip()
    if prof:
        for m in prof.split():
            a_verifier = a_verifier.filter(Q(professeur__nom__icontains=m) | Q(professeur__prenom__icontains=m))
    items = [{
        'id': s.id, 'date': s.date.isoformat(), 'heure': f"{s.heure_debut:%H:%M}",
        'enseignant': s.professeur.nom_complet, 'classe': s.classe.nom,
        'matiere': getattr(s.matiere, 'nom', ''), 'statut': s.get_statut_display(),
        'anomalies': pt.libelles_anomalies(s),
    } for s in a_verifier[:LIMITE]]
    resume = pt.resume_jour(ctx.etablissement, jour)
    return {
        'jour': jour.isoformat(),
        'seances_du_jour': resume.get('total', 0),
        'faites': resume.get('validee', 0) + resume.get('remplacee', 0),
        'non_faites': resume.get('absente', 0),
        'en_cours': resume.get('en_cours', 0),
        'nb_a_verifier': a_verifier.count(),
        'a_verifier': items,
        'pointage_en_service': bool(pt.date_activation(ctx.etablissement)),
        'url': _reverse('directeur:pointage_controle'),
    }


def tool_cahiers_texte(ctx, args):
    from school_admin.model.cahier_texte_model import CahierTexte
    from school_admin.model.professeur_model import Professeur
    from school_admin.services import cahier_texte as ct
    from school_admin.services.assistant_tools import _find_classe

    qs = CahierTexte.objects.filter(etablissement=ctx.etablissement, statut='valide').select_related(
        'classe', 'matiere', 'professeur')
    classe = _find_classe(ctx, args.get('classe')) if args.get('classe') else None
    if classe:
        qs = qs.filter(classe=classe)
    prof_q = (args.get('professeur') or '').strip()
    profs = Professeur.objects.filter(etablissement=ctx.etablissement, actif=True)
    if prof_q:
        for m in prof_q.split():
            profs = profs.filter(Q(nom__icontains=m) | Q(prenom__icontains=m))
        qs = qs.filter(professeur__in=profs)
    entrees = [{
        'date': e.date.isoformat(), 'classe': e.classe.nom, 'matiere': getattr(e.matiere, 'nom', ''),
        'enseignant': e.professeur.nom_complet, 'titre': e.titre,
        'contenu': (e.contenu or '')[:240], 'travail_a_faire': (e.travail_a_faire or '')[:160],
    } for e in qs.order_by('-date', '-heure_debut')[:15]]
    suivi = []
    for p in profs.order_by('nom', 'prenom')[:60]:
        s = ct.stats_professeur(p, ctx.annee_scolaire, jours=14)
        if s['cours']:
            suivi.append({'enseignant': p.nom_complet, 'cours_14_jours': s['cours'], 'renseignes': s['renseignes'],
                          'manquants': s['manquants'], 'taux': s['taux']})
    suivi.sort(key=lambda r: r['taux'] if r['taux'] is not None else 101)
    return {
        'classe': classe.nom if classe else None,
        'dernieres_entrees': entrees,
        'suivi_14_jours': suivi[:LIMITE],
        'url': _reverse('directeur:cahiers_texte'),
    }


def tool_parametres_rappels(ctx, args):
    from school_admin.services.rappels import moteur

    p = moteur.parametres(ctx.etablissement.pk)
    off = set(p.familles_desactivees or [])
    return {
        'actif': p.actif,
        'rappel_cours_du_lendemain': p.rappel_cours_demain,
        'heures_calmes': f"{p.debut_heures_calmes:%H:%M} – {p.fin_heures_calmes:%H:%M}",
        'plafond_par_jour': p.plafond_quotidien,
        'familles': [{'code': k, 'libelle': v, 'active': k not in off} for k, v in moteur.FAMILLES.items()],
        'url': _reverse('directeur:rappels_automatiques'),
    }


GESTION_READ_HANDLERS = {
    'get_situation_financiere': tool_situation_financiere,
    'get_paie_du_mois': tool_paie_du_mois,
    'get_historique_salaire': tool_historique_salaire,
    'get_controle_cours': tool_controle_cours,
    'get_cahiers_texte': tool_cahiers_texte,
    'get_parametres_rappels': tool_parametres_rappels,
}


def _schema(nom, description, proprietes=None, requis=()):
    return {'type': 'function', 'function': {
        'name': nom, 'description': description,
        'parameters': {'type': 'object', 'properties': proprietes or {}, 'required': list(requis)}}}


_MOIS = {'type': 'string', 'description': 'Mois voulu : « 2026-11 », « novembre », « mois dernier ». Mois en cours par défaut.'}
GESTION_READ_SCHEMA = [
    _schema('get_situation_financiere',
            "Finances de l'école pour un mois : entrées, sorties, résultat, argent disponible, soldes de chaque "
            "caisse ou compte, reste à recevoir, charges à payer, dettes et dernières opérations.",
            {'mois': _MOIS}),
    _schema('get_paie_du_mois',
            "Salaires du mois : pour chaque enseignant et membre du personnel, montant dû, payé ou non, et ce qui "
            "bloque. Les agents payés par l'État sont exclus.",
            {'mois': _MOIS, 'type': {'type': 'string', 'description': 'enseignant ou personnel (facultatif)'}}),
    _schema('get_historique_salaire', "Historique des salaires versés à une personne, mois par mois.",
            {'query': {'type': 'string', 'description': 'Nom de l’enseignant ou du membre du personnel'},
             'type': {'type': 'string', 'description': 'enseignant ou personnel (facultatif)'}}, ('query',)),
    _schema('get_controle_cours',
            "Contrôle des cours (pointage des enseignants) : séances à vérifier ou contestées, et bilan d'un jour "
            "(faites, non faites, en cours).",
            {'date': {'type': 'string', 'description': 'Jour à résumer (AAAA-MM-JJ), aujourd’hui par défaut'},
             'professeur': {'type': 'string', 'description': 'Filtrer sur un enseignant'}}),
    _schema('get_cahiers_texte',
            "Cahiers de texte : dernières séances renseignées (contenu, travail à faire) et suivi par enseignant "
            "sur 14 jours (cours renseignés ou manquants).",
            {'classe': {'type': 'string', 'description': 'Nom ou code de classe'},
             'professeur': {'type': 'string', 'description': 'Nom de l’enseignant'}}),
    _schema('get_parametres_rappels',
            "Réglages des rappels automatiques envoyés aux familles, élèves et enseignants (actifs, heures calmes, "
            "plafond quotidien, familles de rappels).", {}),
]


# =========================================================================== ÉCRITURES — FINANCES
def prepare_ajouter_depense(ctx, args):
    from school_admin.model.caisse_etablissement_model import DepenseEtablissement

    montant = _parse_money(args.get('montant'))
    if not montant:
        return _incomplete('ajouter_depense', ['montant'], 'Quel montant pour cette dépense ?')
    motifs = dict(DepenseEtablissement.MOTIF_CHOICES)
    motif = args.get('motif') if args.get('motif') in motifs else _motif_depuis_texte(
        f"{args.get('motif') or ''} {args.get('libelle') or ''}")
    compte = _compte(ctx, args.get('compte'))
    if compte is None:
        return _incomplete('ajouter_depense', ['compte'],
                           f"Depuis quel compte part l’argent ? ({_noms_comptes(ctx)})",
                           montant=str(montant), motif=motif, libelle=args.get('libelle') or '')
    jour = _parse_date(args.get('date_depense') or args.get('date') or '') or date.today()
    libelle = (args.get('libelle') or motifs[motif])[:160]
    return _pending(
        'ajouter_depense',
        f"enregistre une sortie de {_fmt(montant, ctx)} ({libelle}) payée depuis {compte.libelle} le {jour:%d/%m/%Y}",
        montant=str(montant), motif=motif, libelle=libelle, compte_id=compte.id, compte=compte.libelle,
        date_depense=jour.isoformat(),
    )


def _motif_depuis_texte(texte):
    t = _sans_accents(texte)
    for mots, motif in ((('salaire', 'vacataire', 'paie'), 'salaire'), (('loyer',), 'loyer'),
                        (('electric', 'eau', 'senelec', 'courant'), 'electricite'),
                        (('fourniture', 'papier', 'craie', 'cahier', 'encre'), 'fournitures'),
                        (('carburant', 'essence', 'gasoil', 'transport', 'taxi'), 'carburant')):
        if any(m in t for m in mots):
            return motif
    return 'autre'


def apply_ajouter_depense(ctx, draft):
    from school_admin.model.finances_model import CompteTresorerie
    from school_admin.services.finances.operations import enregistrer_sortie

    compte = CompteTresorerie.objects.filter(pk=draft.get('compte_id'), etablissement=ctx.etablissement).first()
    montant = _parse_money(draft.get('montant'))
    if not montant or compte is None:
        return _err('Montant ou compte invalide.')
    try:
        depense, _e = enregistrer_sortie(
            ctx.etablissement, _parse_date(draft.get('date_depense')) or date.today(), draft.get('motif') or 'autre',
            montant, libelle=draft.get('libelle') or '', annee_scolaire=ctx.annee_scolaire,
            user=_utilisateur(ctx), compte_tresorerie=compte,
        )
    except ValueError as exc:
        return _erreur_service(exc)
    _emit(ctx, 'caisse.mise_a_jour', {'id': depense.id, 'action': 'ajoutee'})
    return _ok(f"Sortie de {_fmt(montant, ctx)} enregistrée depuis {compte.libelle}.", id=depense.id,
               url=(_reverse('directeur:finances_sorties') or '') + '?vue=jour')


def prepare_supprimer_depense(ctx, args):
    """Annule une sortie (la trace reste, une contre-écriture est passée). Jamais de choix au hasard."""
    from school_admin.model.caisse_etablissement_model import DepenseEtablissement

    query = (args.get('query') or args.get('libelle') or '').strip()
    if not query:
        return _incomplete('supprimer_depense', ['query'], 'Quelle dépense dois-je annuler ? Donnez son libellé ou son montant.')
    qs = DepenseEtablissement.objects.filter(etablissement=ctx.etablissement, statut='validee')
    depense = None
    montant = _parse_money(query)
    if query.isdigit():
        depense = qs.filter(pk=int(query)).first()
    if depense is None:
        depense = qs.filter(libelle__icontains=query).order_by('-date_depense', '-id').first()
    if depense is None and montant:
        depense = qs.filter(montant=montant).order_by('-date_depense', '-id').first()
    if depense is None:
        return _err(f"Je ne trouve aucune sortie validée correspondant à « {query} ».")
    motif = (args.get('motif') or '').strip()
    if not motif:
        return _incomplete('supprimer_depense', ['motif'], 'Pour quelle raison faut-il l’annuler ?',
                           query=query)
    return _pending(
        'supprimer_depense',
        f"annule la sortie « {depense.libelle or depense.get_motif_display()} » de {_fmt(depense.montant, ctx)} "
        f"du {depense.date_depense:%d/%m/%Y} (motif : {motif}). La trace reste dans l’historique.",
        id=depense.id, libelle=depense.libelle, motif=motif,
    )


def apply_supprimer_depense(ctx, draft):
    from school_admin.model.caisse_etablissement_model import DepenseEtablissement
    from school_admin.services.finances.operations import annuler_sortie

    depense = DepenseEtablissement.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not depense:
        return _err('Sortie introuvable.')
    try:
        annuler_sortie(depense, draft.get('motif') or '', user=_utilisateur(ctx))
    except ValueError as exc:
        return _erreur_service(exc)
    _emit(ctx, 'caisse.mise_a_jour', {'id': depense.id, 'action': 'annulee'})
    return _ok('Sortie annulée. Elle reste visible comme « annulée ».',
               url=(_reverse('directeur:finances_sorties') or '') + '?vue=jour')


def prepare_enregistrer_recette(ctx, args):
    from school_admin.model.finances_model import RecetteEtablissement

    natures = dict(RecetteEtablissement.NATURE_CHOICES)
    nature_txt = _sans_accents(args.get('nature') or '')
    nature = next((code for code in natures if code in nature_txt), None)
    if nature is None:
        if 'subv' in nature_txt or 'don' in nature_txt:
            nature = 'subvention'
        elif 'activ' in nature_txt or 'sortie' in nature_txt or 'kermesse' in nature_txt or 'fete' in nature_txt:
            nature = 'activite'
        elif nature_txt:
            nature = 'divers'
    montant = _parse_money(args.get('montant'))
    if not montant:
        return _incomplete('enregistrer_recette', ['montant'], 'Quel montant a été reçu ?', nature=nature or '')
    if nature is None:
        return _incomplete('enregistrer_recette', ['nature'],
                           'C’est une recette d’activité, une subvention ou une recette diverse ?',
                           montant=str(montant))
    destination = ''
    if nature == 'subvention':
        dest_txt = _sans_accents(args.get('destination') or '')
        destination = next((code for code, _l in RecetteEtablissement.DESTINATION_CHOICES if code in dest_txt), '')
        if not destination:
            return _incomplete('enregistrer_recette', ['destination'],
                               'Cette subvention sert au fonctionnement, à l’équipement, à un projet ou autre ?',
                               montant=str(montant), nature=nature)
    compte = _compte(ctx, args.get('compte'))
    if compte is None:
        return _incomplete('enregistrer_recette', ['compte'], f"Sur quel compte l’argent est-il arrivé ? ({_noms_comptes(ctx)})",
                           montant=str(montant), nature=nature)
    jour = _parse_date(args.get('date') or '') or date.today()
    libelle = (args.get('libelle') or natures[nature])[:200]
    origine = (args.get('origine') or '')[:160]
    return _pending(
        'enregistrer_recette',
        f"enregistre une entrée de {_fmt(montant, ctx)} ({natures[nature].lower()} : {libelle}"
        f"{' — ' + origine if origine else ''}) sur {compte.libelle} le {jour:%d/%m/%Y}",
        montant=str(montant), nature=nature, destination=destination, compte_id=compte.id, compte=compte.libelle,
        libelle=libelle, origine=origine, date=jour.isoformat(),
    )


def apply_enregistrer_recette(ctx, draft):
    from school_admin.controllers.finances_controller import NATURE_VERS_CATEGORIE
    from school_admin.model.finances_model import CategorieFinanciere, CompteTresorerie
    from school_admin.services.finances.categories import assurer_categories
    from school_admin.services.finances.recettes import enregistrer_recette

    assurer_categories(ctx.etablissement)
    nature = draft.get('nature')
    categorie = CategorieFinanciere.objects.filter(
        etablissement=ctx.etablissement, type_categorie='recette', actif=True,
        libelle=NATURE_VERS_CATEGORIE.get(nature, ''),
    ).first() or CategorieFinanciere.objects.filter(
        etablissement=ctx.etablissement, type_categorie='recette', actif=True).first()
    compte = CompteTresorerie.objects.filter(pk=draft.get('compte_id'), etablissement=ctx.etablissement).first()
    montant = _parse_money(draft.get('montant'))
    if not (categorie and compte and montant):
        return _err('Recette incomplète : montant, compte ou catégorie manquant.')
    try:
        recette, _ecriture = enregistrer_recette(
            ctx.etablissement, nature, categorie, compte, _parse_date(draft.get('date')) or date.today(), montant,
            libelle=draft.get('libelle') or '', origine=draft.get('origine') or '',
            destination=draft.get('destination') or '', annee_scolaire=ctx.annee_scolaire, user=_utilisateur(ctx),
        )
    except ValueError as exc:
        return _erreur_service(exc)
    return _ok(f"Entrée de {_fmt(montant, ctx)} enregistrée sur {compte.libelle}.", id=recette.id,
               url=(_reverse('directeur:finances_entrees') or '') + f'?vue={nature}')


def _trouver_fournisseur(ctx, nom):
    from school_admin.model.comptabilite_generale_model import FournisseurEtablissement

    raw = (nom or '').strip()
    if not raw:
        return None
    return FournisseurEtablissement.objects.filter(etablissement=ctx.etablissement, nom__icontains=raw).first()


def prepare_enregistrer_charge(ctx, args):
    fournisseur_nom = (args.get('fournisseur') or '').strip()
    montant = _parse_money(args.get('montant'))
    if not fournisseur_nom:
        return _incomplete('enregistrer_charge', ['fournisseur'], 'Quel est le fournisseur de cette facture ?',
                           montant=str(montant or ''))
    if not montant:
        return _incomplete('enregistrer_charge', ['montant'], 'Quel est le montant de la facture ?',
                           fournisseur=fournisseur_nom)
    fournisseur = _trouver_fournisseur(ctx, fournisseur_nom)
    libelle = (args.get('libelle') or 'Facture').strip()[:200]
    jour = _parse_date(args.get('date_facture') or '') or date.today()
    echeance = _parse_date(args.get('echeance') or '') or jour
    if echeance < jour:
        echeance = jour
    numero = (args.get('numero') or f"F{jour:%Y%m%d}-{timezone.now():%H%M%S}")[:40]
    motif = _motif_depuis_texte(f"{args.get('categorie') or ''} {libelle} {fournisseur_nom}")
    nouveau = '' if fournisseur else ' (nouveau fournisseur, il sera créé)'
    return _pending(
        'enregistrer_charge',
        f"enregistre une charge à payer de {_fmt(montant, ctx)} : {libelle}, fournisseur {fournisseur.nom if fournisseur else fournisseur_nom}"
        f"{nouveau}, échéance le {echeance:%d/%m/%Y}. Aucun argent ne sort tant qu’elle n’est pas payée.",
        fournisseur_id=getattr(fournisseur, 'id', None), fournisseur=fournisseur.nom if fournisseur else fournisseur_nom,
        montant=str(montant), libelle=libelle, numero=numero, motif=motif,
        date_facture=jour.isoformat(), echeance=echeance.isoformat(),
    )


def apply_enregistrer_charge(ctx, draft):
    from school_admin.model.comptabilite_generale_model import FournisseurEtablissement
    from school_admin.services.finances.categories import categorie_pour_motif
    from school_admin.services.finances.charges import enregistrer_facture

    fournisseur = None
    if draft.get('fournisseur_id'):
        fournisseur = FournisseurEtablissement.objects.filter(pk=draft['fournisseur_id'],
                                                              etablissement=ctx.etablissement).first()
    if fournisseur is None:
        fournisseur, _c = FournisseurEtablissement.objects.get_or_create(
            etablissement=ctx.etablissement, nom=(draft.get('fournisseur') or 'Fournisseur')[:160],
            defaults={'actif': True})
    try:
        facture, _ecriture = enregistrer_facture(
            ctx.etablissement, fournisseur, draft.get('numero'), draft.get('libelle') or 'Facture',
            _parse_money(draft.get('montant')), _parse_date(draft.get('date_facture')) or date.today(),
            _parse_date(draft.get('echeance')) or date.today(), categorie_pour_motif(ctx.etablissement, draft.get('motif')),
            annee_scolaire=ctx.annee_scolaire, user=_utilisateur(ctx),
        )
    except (ValueError, TypeError) as exc:
        return _erreur_service(exc)
    return _ok(f"Charge de {_fmt(facture.montant, ctx)} enregistrée pour {fournisseur.nom}.", id=facture.id,
               url=(_reverse('directeur:finances_sorties') or '') + '?vue=mois')


def _trouver_facture(ctx, query):
    from school_admin.model.comptabilite_generale_model import FactureFournisseur

    qs = FactureFournisseur.objects.filter(etablissement=ctx.etablissement).exclude(
        statut__in=('payee', 'annulee')).select_related('fournisseur')
    raw = (query or '').strip()
    if raw.isdigit():
        f = qs.filter(pk=int(raw)).first()
        if f:
            return f
    if raw:
        return qs.filter(Q(numero__icontains=raw) | Q(libelle__icontains=raw) | Q(fournisseur__nom__icontains=raw)
                         ).order_by('date_echeance').first()
    return None


def prepare_payer_charge(ctx, args):
    facture = _trouver_facture(ctx, args.get('query') or args.get('fournisseur'))
    if facture is None:
        return _incomplete('payer_charge', ['query'], 'Quelle facture faut-il payer ? Donnez le fournisseur ou le numéro.')
    reste = facture.reste_a_payer()
    montant = _parse_money(args.get('montant')) or reste
    if montant > reste:
        return _err(f"Il ne reste que {_fmt(reste, ctx)} à payer sur cette facture.")
    compte = _compte(ctx, args.get('compte'))
    if compte is None:
        return _incomplete('payer_charge', ['compte'], f"Depuis quel compte ? ({_noms_comptes(ctx)})",
                           query=args.get('query') or '')
    return _pending(
        'payer_charge',
        f"paie {_fmt(montant, ctx)} sur la facture {facture.numero} de {facture.fournisseur.nom} "
        f"(reste {_fmt(reste, ctx)}) depuis {compte.libelle}",
        facture_id=facture.id, montant=str(montant), compte_id=compte.id, compte=compte.libelle,
    )


def apply_payer_charge(ctx, draft):
    from school_admin.model.comptabilite_generale_model import FactureFournisseur
    from school_admin.model.finances_model import CompteTresorerie
    from school_admin.services.finances.charges import enregistrer_paiement

    facture = FactureFournisseur.objects.filter(pk=draft.get('facture_id'), etablissement=ctx.etablissement).first()
    compte = CompteTresorerie.objects.filter(pk=draft.get('compte_id'), etablissement=ctx.etablissement).first()
    if not facture or not compte:
        return _err('Facture ou compte introuvable.')
    try:
        enregistrer_paiement(facture, date.today(), _parse_money(draft.get('montant')), compte_tresorerie=compte,
                             annee_scolaire=ctx.annee_scolaire, user=_utilisateur(ctx))
    except ValueError as exc:
        return _erreur_service(exc)
    return _ok(f"Paiement de {_fmt(draft.get('montant'), ctx)} enregistré pour {facture.fournisseur.nom}.",
               url=(_reverse('directeur:finances_sorties') or '') + '?vue=mois')


def prepare_transfert_comptes(ctx, args):
    montant = _parse_money(args.get('montant'))
    source = _compte(ctx, args.get('source'), defaut=None)
    destination = _compte(ctx, args.get('destination'), defaut=None)
    if not montant:
        return _incomplete('transfert_comptes', ['montant'], 'Quel montant faut-il déplacer ?')
    if source is None or destination is None:
        return _incomplete('transfert_comptes', ['source', 'destination'],
                           f"De quel compte vers quel compte ? ({_noms_comptes(ctx)})", montant=str(montant))
    if source.id == destination.id:
        return _err('Le compte de départ et le compte d’arrivée doivent être différents.')
    motif = (args.get('motif') or f"Transfert {source.libelle} vers {destination.libelle}")[:200]
    return _pending(
        'transfert_comptes',
        f"déplace {_fmt(montant, ctx)} de {source.libelle} vers {destination.libelle} ({motif}). "
        f"Ce n’est ni une entrée ni une sortie.",
        montant=str(montant), source_id=source.id, destination_id=destination.id, motif=motif,
    )


def apply_transfert_comptes(ctx, draft):
    from school_admin.model.finances_model import CompteTresorerie
    from school_admin.services.finances.transferts import enregistrer_transfert

    comptes = CompteTresorerie.objects.filter(etablissement=ctx.etablissement)
    source = comptes.filter(pk=draft.get('source_id')).first()
    destination = comptes.filter(pk=draft.get('destination_id')).first()
    try:
        enregistrer_transfert(ctx.etablissement, source, destination, date.today(), _parse_money(draft.get('montant')),
                              motif=draft.get('motif') or '', annee_scolaire=ctx.annee_scolaire,
                              user=_utilisateur(ctx))
    except ValueError as exc:
        return _erreur_service(exc)
    return _ok(f"Transfert de {_fmt(draft.get('montant'), ctx)} enregistré.",
               url=_reverse('directeur:finances_tresorerie'))


def prepare_enregistrer_pret(ctx, args):
    montant = _parse_money(args.get('montant'))
    objet = (args.get('objet') or '').strip()
    if not montant:
        return _incomplete('enregistrer_pret', ['montant'], 'Quel est le montant du prêt reçu ?')
    if not objet:
        return _incomplete('enregistrer_pret', ['objet'], 'À quoi sert ce prêt ?', montant=str(montant))
    compte = _compte(ctx, args.get('compte'), defaut='banque')
    if compte is None:
        return _incomplete('enregistrer_pret', ['compte'], f"Sur quel compte le prêt est-il arrivé ? ({_noms_comptes(ctx)})",
                           montant=str(montant), objet=objet)
    reference = (args.get('reference') or f"PRET-{date.today():%Y%m%d}-{timezone.now():%H%M}")[:80]
    taux = _decimal(args.get('taux'), Decimal('0'))
    duree = args.get('duree_mois')
    return _pending(
        'enregistrer_pret',
        f"enregistre un prêt de {_fmt(montant, ctx)} reçu sur {compte.libelle} ({objet}, référence {reference}"
        f"{', taux ' + str(taux) + ' %' if taux else ''}{', ' + str(duree) + ' mois' if duree else ''})",
        montant=str(montant), objet=objet[:200], compte_id=compte.id, reference=reference, taux=str(taux),
        duree_mois=str(duree or ''),
    )


def apply_enregistrer_pret(ctx, draft):
    from school_admin.model.finances_model import CompteTresorerie
    from school_admin.services.finances.prets import enregistrer_pret

    compte = CompteTresorerie.objects.filter(pk=draft.get('compte_id'), etablissement=ctx.etablissement).first()
    duree = draft.get('duree_mois')
    try:
        pret, _ecriture = enregistrer_pret(ctx.etablissement, compte, date.today(), _parse_money(draft.get('montant')),
                                draft.get('reference'), draft.get('objet'), taux=draft.get('taux') or 0,
                                duree_mois=int(duree) if str(duree or '').isdigit() else None,
                                annee_scolaire=ctx.annee_scolaire, user=_utilisateur(ctx))
    except ValueError as exc:
        return _erreur_service(exc)
    return _ok(f"Prêt de {_fmt(draft.get('montant'), ctx)} enregistré.", id=getattr(pret, 'id', None),
               url=_reverse('directeur:finances_financements'))


def prepare_rembourser_pret(ctx, args):
    from school_admin.model.finances_model import PretEtablissement

    qs = PretEtablissement.objects.filter(etablissement=ctx.etablissement, statut='en_cours')
    raw = (args.get('query') or '').strip()
    pret = qs.filter(Q(reference__icontains=raw) | Q(objet__icontains=raw)).first() if raw else None
    if pret is None and qs.count() == 1:
        pret = qs.first()
    if pret is None:
        return _incomplete('rembourser_pret', ['query'], 'Quel prêt faut-il rembourser ? Donnez sa référence ou son objet.')
    capital = _decimal(args.get('capital'), Decimal('0')) or Decimal('0')
    interets = _decimal(args.get('interets'), Decimal('0')) or Decimal('0')
    frais = _decimal(args.get('frais'), Decimal('0')) or Decimal('0')
    if capital + interets + frais <= 0:
        return _incomplete('rembourser_pret', ['capital'], 'Quel montant de capital (et d’intérêts) remboursez-vous ?',
                           query=raw)
    if capital > pret.capital_restant():
        return _err(f"Le capital restant n’est que de {_fmt(pret.capital_restant(), ctx)}.")
    compte = _compte(ctx, args.get('compte'), defaut='banque') or pret.compte_tresorerie
    motif = (args.get('motif') or f"Remboursement {pret.reference}")[:200]
    total = capital + interets + frais
    return _pending(
        'rembourser_pret',
        f"rembourse {_fmt(total, ctx)} sur le prêt {pret.reference} ({pret.objet}) : capital {_fmt(capital, ctx)}, "
        f"intérêts {_fmt(interets, ctx)}, frais {_fmt(frais, ctx)}, depuis {compte.libelle}",
        pret_id=pret.id, capital=str(capital), interets=str(interets), frais=str(frais), compte_id=compte.id,
        motif=motif,
    )


def apply_rembourser_pret(ctx, draft):
    from school_admin.model.finances_model import CompteTresorerie, PretEtablissement
    from school_admin.services.finances.prets import enregistrer_remboursement

    pret = PretEtablissement.objects.filter(pk=draft.get('pret_id'), etablissement=ctx.etablissement).first()
    compte = CompteTresorerie.objects.filter(pk=draft.get('compte_id'), etablissement=ctx.etablissement).first()
    if not pret:
        return _err('Prêt introuvable.')
    try:
        enregistrer_remboursement(pret, date.today(), capital=draft.get('capital') or 0,
                                  interets=draft.get('interets') or 0, frais=draft.get('frais') or 0,
                                  motif=draft.get('motif') or 'Remboursement', compte_tresorerie=compte,
                                  user=_utilisateur(ctx))
    except ValueError as exc:
        return _erreur_service(exc)
    return _ok('Remboursement enregistré.', url=_reverse('directeur:finances_financements'))


# =========================================================================== ÉCRITURES — SALAIRES
def _prepare_payer_salaire(nom_action):
    def prepare(ctx, args):
        from school_admin.services.salaires import paie_du_mois

        type_personne, personne = _trouver_personne(ctx, args.get('query') or args.get('professeur') or args.get('nom'),
                                                    args.get('type') or '')
        if not personne:
            return _incomplete(nom_action, ['query'], 'Qui dois-je payer ? Donnez le nom de l’enseignant ou de l’employé.')
        if getattr(personne, 'prise_en_charge', '') == 'etat':
            return _err(f"{personne.nom_complet} est payé par l’État : l’école ne lui verse pas de salaire.")
        premier = _mois(args.get('mois'))
        ligne = next((l for l in paie_du_mois(ctx.etablissement, ctx.annee_scolaire, premier)['lignes']
                      if l.type == type_personne and l.personne.id == personne.id), None)
        if ligne is None:
            return _err(f"{personne.nom_complet} n’a rien à percevoir pour {_libelle_mois(premier)}.")
        if ligne.statut == 'paye':
            return _err(f"Le salaire de {_libelle_mois(premier)} de {personne.nom_complet} est déjà versé.")
        if ligne.bloque:
            return _err(f"Paiement impossible pour {personne.nom_complet} : {ligne.bloque}.")
        heures = args.get('heures')
        montant = ligne.montant
        if type_personne == 'personnel' and ligne.statut == 'a_saisir':
            if heures in (None, ''):
                return _incomplete(nom_action, ['heures'],
                                   f"Combien d’heures {personne.nom_complet} a-t-il faites en {_libelle_mois(premier)} ?",
                                   query=personne.nom_complet, mois=f"{premier:%Y-%m}")
            h = _decimal(heures)
            if not h or not personne.prix_volume_horaire:
                return _err('Nombre d’heures invalide, ou prix de l’heure absent de sa fiche.')
            montant = h * Decimal(str(personne.prix_volume_horaire))
        if not montant:
            return _err(f"Aucun montant à payer à {personne.nom_complet} pour {_libelle_mois(premier)}.")
        retenue = _decimal(args.get('retenue_pct'), Decimal('0')) or Decimal('0')
        compte = _compte(ctx, args.get('compte'))
        if compte is None:
            return _incomplete(nom_action, ['compte'], f"Depuis quel compte ? ({_noms_comptes(ctx)})",
                               query=personne.nom_complet)
        detail = f" avec {retenue} % de retenue" if retenue and type_personne == 'enseignant' else ''
        return _pending(
            nom_action,
            f"verse le salaire de {_libelle_mois(premier)} à {personne.nom_complet} : {_fmt(montant, ctx)}{detail}, "
            f"payé depuis {compte.libelle}",
            type_personne=type_personne, id=personne.id, nom=personne.nom_complet, mois=f"{premier:%Y-%m}",
            montant=str(montant), heures=str(heures or ''), retenue_pct=str(retenue), compte_id=compte.id,
        )
    return prepare


def apply_payer_salaire(ctx, draft):
    from school_admin.model.finances_model import CompteTresorerie
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur
    from school_admin.services.salaires import payer_enseignant, payer_personnel

    premier = _mois(draft.get('mois'))
    compte = CompteTresorerie.objects.filter(pk=draft.get('compte_id'), etablissement=ctx.etablissement).first()
    try:
        if draft.get('type_personne') == 'enseignant':
            prof = Professeur.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
            if not prof:
                return _err('Enseignant introuvable.')
            payer_enseignant(ctx.etablissement, prof, premier, ctx.annee_scolaire,
                             _decimal(draft.get('retenue_pct'), Decimal('0')), compte, _utilisateur(ctx))
        else:
            pers = PersonnelAdministratif.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
            if not pers:
                return _err('Membre du personnel introuvable.')
            heures = draft.get('heures') or None
            payer_personnel(ctx.etablissement, pers, premier,
                            montant=None if heures else _decimal(draft.get('montant')),
                            annee_scolaire=ctx.annee_scolaire, user=_utilisateur(ctx), heures=heures,
                            compte_tresorerie=compte)
    except ValueError as exc:
        return _erreur_service(exc)
    _emit(ctx, 'paie.mise_a_jour', {'id': draft.get('id')})
    onglet = 'enseignant' if draft.get('type_personne') == 'enseignant' else 'personnel'
    return _ok(f"Salaire de {_libelle_mois(premier)} versé à {draft.get('nom')}.",
               url=(_reverse('directeur:salaires') or '') + f"?mois={premier:%Y-%m}&onglet={onglet}")


def prepare_payer_tous_salaires(ctx, args):
    from school_admin.services.salaires import paie_du_mois

    premier = _mois(args.get('mois'))
    paie = paie_du_mois(ctx.etablissement, ctx.annee_scolaire, premier)
    if not paie['pretes']:
        return _err(f"Personne n’est prêt à être payé pour {_libelle_mois(premier)}.")
    compte = _compte(ctx, args.get('compte'))
    if compte is None:
        return _incomplete('payer_tous_salaires', ['compte'], f"Depuis quel compte ? ({_noms_comptes(ctx)})")
    noms = ', '.join(l.nom for l in paie['pretes'][:8])
    return _pending(
        'payer_tous_salaires',
        f"verse les salaires de {_libelle_mois(premier)} à {len(paie['pretes'])} personne(s) ({noms}"
        f"{'…' if len(paie['pretes']) > 8 else ''}) pour {_fmt(paie['total_pretes'], ctx)}, depuis {compte.libelle}. "
        f"Les personnes bloquées ou à saisir ne sont pas payées.",
        mois=f"{premier:%Y-%m}", compte_id=compte.id, total=str(paie['total_pretes']),
    )


def apply_payer_tous_salaires(ctx, draft):
    from school_admin.model.finances_model import CompteTresorerie
    from school_admin.services.salaires import payer_tout

    premier = _mois(draft.get('mois'))
    compte = CompteTresorerie.objects.filter(pk=draft.get('compte_id'), etablissement=ctx.etablissement).first()
    payes, ignores = payer_tout(ctx.etablissement, ctx.annee_scolaire, premier, compte_tresorerie=compte,
                                user=_utilisateur(ctx))
    message = f"{len(payes)} salaire(s) versé(s) pour {_libelle_mois(premier)}."
    if ignores:
        message += f" {len(ignores)} non payé(s) : " + '; '.join(f"{n} ({r})" for n, r in ignores[:4])
    return _ok(message, url=(_reverse('directeur:salaires') or '') + f"?mois={premier:%Y-%m}")


# =========================================================================== ÉCRITURES — CONTRÔLE DES COURS
DECISIONS = {'valider': 'valider (cours fait)', 'refuser': 'marquer non fait (non payé)',
             'justifier': 'justifier l’absence', 'annuler': 'annuler la séance', 'remplacer': 'noter un remplaçant'}


def prepare_decider_seance(ctx, args):
    from school_admin.model.pointage_model import SeanceCours
    from school_admin.model.professeur_model import Professeur

    texte = _sans_accents(args.get('decision') or '')
    decision = ('valider' if 'valid' in texte or 'fait' == texte else
                'refuser' if 'refus' in texte or 'non fait' in texte or 'absent' in texte else
                'justifier' if 'justif' in texte else
                'remplacer' if 'rempla' in texte else
                'annuler' if 'annul' in texte else None)
    if decision is None:
        return _incomplete('decider_seance', ['decision'],
                           'Je valide la séance, je la marque non faite, je justifie l’absence ou je note un remplaçant ?')
    qs = SeanceCours.objects.filter(etablissement=ctx.etablissement, paie__isnull=True).select_related(
        'professeur', 'classe', 'matiere')
    if args.get('seance_id') and str(args['seance_id']).isdigit():
        qs = qs.filter(pk=int(args['seance_id']))
    else:
        prof = (args.get('professeur') or args.get('query') or '').strip()
        if not prof:
            return _incomplete('decider_seance', ['professeur'], 'La séance de quel enseignant ?', decision=decision)
        for m in prof.split():
            qs = qs.filter(Q(professeur__nom__icontains=m) | Q(professeur__prenom__icontains=m))
        jour = _parse_date(args.get('date') or '')
        if jour:
            qs = qs.filter(date=jour)
        if args.get('classe'):
            qs = qs.filter(classe__nom__icontains=args['classe'])
        qs = qs.filter(statut__in=('a_verifier', 'contestee', 'absente', 'en_cours', 'prevue'))
    # Les séances à vérifier ou contestées passent d'abord, puis la plus récente.
    s = (qs.filter(statut__in=('a_verifier', 'contestee')).order_by('-date', '-heure_debut').first()
         or qs.order_by('-date', '-heure_debut').first())
    if s is None:
        return _err('Je ne trouve pas de séance à décider pour cet enseignant.')
    remplacant = None
    if decision == 'remplacer':
        nom = (args.get('remplacant') or '').strip()
        cand = Professeur.objects.filter(etablissement=ctx.etablissement, actif=True)
        for m in nom.split():
            cand = cand.filter(Q(nom__icontains=m) | Q(prenom__icontains=m))
        remplacant = cand.exclude(pk=s.professeur_id).first() if nom else None
        if remplacant is None:
            return _incomplete('decider_seance', ['remplacant'], 'Quel enseignant a assuré le cours ?',
                               decision=decision, seance_id=s.id)
    return _pending(
        'decider_seance',
        f"{DECISIONS[decision]} : séance de {s.professeur.nom_complet}, {s.classe.nom}"
        f"{' (' + s.matiere.nom + ')' if s.matiere_id else ''}, le {s.date:%d/%m/%Y} à {s.heure_debut:%H:%M}"
        f"{', remplacé par ' + remplacant.nom_complet if remplacant else ''}",
        seance_id=s.id, decision=decision, remplacant_id=getattr(remplacant, 'id', None),
        commentaire=(args.get('commentaire') or '')[:255],
    )


def apply_decider_seance(ctx, draft):
    from school_admin.model.pointage_model import SeanceCours
    from school_admin.model.professeur_model import Professeur
    from school_admin.services import pointage as pt

    seance = SeanceCours.objects.filter(pk=draft.get('seance_id'), etablissement=ctx.etablissement).first()
    if not seance:
        return _err('Séance introuvable.')
    remplacant = None
    if draft.get('remplacant_id'):
        remplacant = Professeur.objects.filter(pk=draft['remplacant_id'], etablissement=ctx.etablissement).first()
    try:
        pt.decider(seance, _utilisateur(ctx), draft.get('decision'), draft.get('commentaire') or '',
                   remplacant=remplacant)
    except ValueError as exc:
        return _erreur_service(exc)
    return _ok(f"Séance de {seance.professeur.nom_complet} : {seance.get_statut_display().lower()}.",
               url=_reverse('directeur:pointage_controle'))


# =========================================================================== ÉCRITURES — RAPPELS
def _oui_non(valeur):
    if valeur is None or valeur == '':
        return None
    if isinstance(valeur, bool):
        return valeur
    t = _sans_accents(str(valeur))
    if t in ('oui', 'true', '1', 'active', 'activer', 'on', 'actif'):
        return True
    if t in ('non', 'false', '0', 'desactive', 'desactiver', 'off', 'couper', 'inactif'):
        return False
    return None


def prepare_configurer_rappels(ctx, args):
    from school_admin.services.rappels import moteur

    p = moteur.parametres(ctx.etablissement.pk)
    changements, draft = [], {}
    actif = _oui_non(args.get('actif'))
    if actif is not None and actif != p.actif:
        draft['actif'] = actif
        changements.append('rappels ' + ('activés' if actif else 'désactivés'))
    demain = _oui_non(args.get('cours_demain'))
    if demain is not None and demain != p.rappel_cours_demain:
        draft['cours_demain'] = demain
        changements.append('rappel des cours du lendemain ' + ('activé' if demain else 'coupé'))
    for cle, champ, nom in (('debut_heures_calmes', 'debut', 'début des heures calmes'),
                            ('fin_heures_calmes', 'fin', 'fin des heures calmes')):
        m = re.search(r'(\d{1,2})\s*[h:]\s*(\d{2})?', str(args.get(cle) or ''))
        if m:
            heure = f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"
            draft[champ] = heure
            changements.append(f"{nom} à {heure}")
    plafond = args.get('plafond_quotidien')
    if str(plafond or '').strip().isdigit():
        draft['plafond'] = max(1, min(10, int(plafond)))
        changements.append(f"{draft['plafond']} rappels par jour au plus")
    off = set(p.familles_desactivees or [])
    for cle, ajout in (('familles_a_couper', True), ('familles_a_activer', False)):
        for mot in re.split(r'[,;]| et ', str(args.get(cle) or '')):
            mot = _sans_accents(mot).strip()
            if not mot:
                continue
            code = next((k for k, v in moteur.FAMILLES.items() if mot in k or mot in _sans_accents(v)), None)
            if code:
                (off.add if ajout else off.discard)(code)
                changements.append(f"{moteur.FAMILLES[code]} {'coupés' if ajout else 'activés'}")
    if set(off) != set(p.familles_desactivees or []):
        draft['familles_desactivees'] = sorted(off)
    if not changements:
        return _incomplete('configurer_rappels', ['actif'],
                           'Que voulez-vous changer : activer ou couper les rappels, les heures calmes, le plafond par '
                           'jour ou un type de rappel ?')
    return _pending('configurer_rappels', 'modifie les rappels automatiques : ' + ', '.join(changements), **draft)


def apply_configurer_rappels(ctx, draft):
    from datetime import time

    from school_admin.services.rappels import moteur

    p = moteur.parametres(ctx.etablissement.pk)
    if 'actif' in draft:
        p.actif = bool(draft['actif'])
    if 'cours_demain' in draft:
        p.rappel_cours_demain = bool(draft['cours_demain'])
    for champ, attr in (('debut', 'debut_heures_calmes'), ('fin', 'fin_heures_calmes')):
        if draft.get(champ):
            h, m = (int(x) for x in str(draft[champ]).split(':'))
            setattr(p, attr, time(min(h, 23), min(m, 59)))
    if draft.get('plafond'):
        p.plafond_quotidien = int(draft['plafond'])
    if 'familles_desactivees' in draft:
        p.familles_desactivees = [k for k in draft['familles_desactivees'] if k in moteur.FAMILLES]
    p.save()
    return _ok('Réglages des rappels enregistrés.', url=_reverse('directeur:rappels_automatiques'))


# =========================================================================== ENREGISTREMENT
_COMPTE = {'type': 'string', 'description': 'Caisse, banque, mobile money… (caisse par défaut)'}
_PAIE_PROPS = {
    'query': {'type': 'string', 'description': 'Nom de l’enseignant ou du membre du personnel'},
    'type': {'type': 'string', 'description': 'enseignant ou personnel (facultatif)'},
    'mois': _MOIS,
    'heures': {'type': 'string', 'description': 'Personnel payé à l’heure : heures du mois'},
    'retenue_pct': {'type': 'string', 'description': 'Enseignant : retenue en %, 0 par défaut'},
    'compte': _COMPTE,
}

SPECS = [
    ActionSpec('ajouter_depense',
               "Enregistre une sortie d'argent payée tout de suite (achat, loyer, électricité, transport…). "
               "L'argent sort de la caisse ou du compte choisi et l'écriture comptable est passée.",
               {'montant': _STR, 'motif': {'type': 'string', 'description': 'salaire, loyer, electricite, fournitures, carburant ou autre'},
                'libelle': _STR, 'compte': _COMPTE, 'date_depense': _STR},
               required=('montant',), prepare=prepare_ajouter_depense, apply=apply_ajouter_depense),
    ActionSpec('supprimer_depense',
               "Annule une sortie d'argent déjà enregistrée (motif obligatoire). Elle reste visible comme annulée et "
               "une contre-écriture est passée. Ne choisit jamais une dépense au hasard.",
               {'query': {'type': 'string', 'description': 'Libellé, montant ou numéro de la sortie'}, 'motif': _STR},
               required=('query',), destructive=True, prepare=prepare_supprimer_depense, apply=apply_supprimer_depense),
    ActionSpec('enregistrer_recette',
               "Enregistre une entrée d'argent qui n'est pas de la scolarité : recette d'activité (sortie, kermesse, "
               "fête), subvention ou don, recette diverse.",
               {'nature': {'type': 'string', 'description': 'activite, subvention ou divers'}, 'montant': _STR,
                'libelle': _STR, 'origine': {'type': 'string', 'description': 'Qui a donné ou payé'},
                'destination': {'type': 'string', 'description': 'Subvention : fonctionnement, equipement, projet ou autre'},
                'compte': _COMPTE, 'date': _STR},
               required=('montant',), prepare=prepare_enregistrer_recette, apply=apply_enregistrer_recette),
    ActionSpec('enregistrer_charge',
               "Enregistre une facture fournisseur à payer plus tard (charge du mois). Crée le fournisseur s'il "
               "n'existe pas. Aucun argent ne sort avant le paiement.",
               {'fournisseur': _STR, 'montant': _STR, 'libelle': _STR, 'numero': _STR,
                'echeance': {'type': 'string', 'description': 'Date limite de paiement'},
                'categorie': {'type': 'string', 'description': 'loyer, electricite, fournitures, carburant…'}},
               required=('fournisseur', 'montant'), prepare=prepare_enregistrer_charge, apply=apply_enregistrer_charge),
    ActionSpec('payer_charge',
               "Paie tout ou partie d'une facture fournisseur déjà enregistrée (le reste par défaut).",
               {'query': {'type': 'string', 'description': 'Fournisseur, numéro ou libellé de la facture'},
                'montant': _STR, 'compte': _COMPTE},
               required=('query',), prepare=prepare_payer_charge, apply=apply_payer_charge),
    ActionSpec('transfert_comptes',
               "Déplace de l'argent d'un compte de l'école vers un autre (ex. dépôt de la caisse à la banque). "
               "Ce n'est ni une entrée ni une sortie.",
               {'source': {'type': 'string', 'description': 'Compte de départ'},
                'destination': {'type': 'string', 'description': 'Compte d’arrivée'}, 'montant': _STR, 'motif': _STR},
               required=('montant',), prepare=prepare_transfert_comptes, apply=apply_transfert_comptes),
    ActionSpec('enregistrer_pret',
               "Enregistre un prêt reçu par l'école (argent emprunté à une banque ou un organisme).",
               {'montant': _STR, 'objet': _STR, 'reference': _STR, 'compte': _COMPTE,
                'taux': {'type': 'string', 'description': 'Taux annuel en %'},
                'duree_mois': {'type': 'string', 'description': 'Durée en mois'}},
               required=('montant', 'objet'), prepare=prepare_enregistrer_pret, apply=apply_enregistrer_pret),
    ActionSpec('rembourser_pret',
               "Enregistre un remboursement de prêt (capital, intérêts, frais).",
               {'query': {'type': 'string', 'description': 'Référence ou objet du prêt'}, 'capital': _STR,
                'interets': _STR, 'frais': _STR, 'compte': _COMPTE, 'motif': _STR},
               prepare=prepare_rembourser_pret, apply=apply_rembourser_pret),
    ActionSpec('payer_salaire',
               "Verse le salaire du mois à un enseignant ou un membre du personnel, comme la page Salaires : montant "
               "calculé (séances validées × tarif, ou salaire mensuel), sortie de caisse et écriture comptable. "
               "Refuse les agents payés par l'État et les mois déjà payés.",
               _PAIE_PROPS, required=('query',), prepare=_prepare_payer_salaire('payer_salaire'),
               apply=apply_payer_salaire),
    ActionSpec('marquer_paie',
               "Ancien nom de payer_salaire : verse le salaire du mois d'un enseignant ou d'un employé.",
               _PAIE_PROPS, required=('query',), prepare=_prepare_payer_salaire('marquer_paie'),
               apply=apply_payer_salaire),
    ActionSpec('payer_tous_salaires',
               "Verse en une fois les salaires du mois de toutes les personnes prêtes à être payées.",
               {'mois': _MOIS, 'compte': _COMPTE}, prepare=prepare_payer_tous_salaires,
               apply=apply_payer_tous_salaires),
    ActionSpec('decider_seance',
               "Contrôle des cours : valide une séance d'un enseignant, la marque non faite, justifie l'absence, "
               "l'annule ou note le remplaçant qui a assuré le cours.",
               {'professeur': _STR, 'decision': {'type': 'string', 'description': 'valider, refuser, justifier, remplacer ou annuler'},
                'date': {'type': 'string', 'description': 'Jour de la séance'}, 'classe': _STR,
                'remplacant': _STR, 'commentaire': _STR, 'seance_id': _STR},
               required=('decision',), prepare=prepare_decider_seance, apply=apply_decider_seance),
    ActionSpec('configurer_rappels',
               "Règle les rappels automatiques : les activer ou les couper, les heures calmes, le nombre de rappels "
               "par jour, le rappel des cours du lendemain, ou couper / réactiver un type de rappel (devoirs, "
               "évaluations, convocations, scolarité, inscriptions, notes, présences, cahier, planning).",
               {'actif': _STR, 'cours_demain': _STR, 'debut_heures_calmes': _STR, 'fin_heures_calmes': _STR,
                'plafond_quotidien': _STR, 'familles_a_couper': _STR, 'familles_a_activer': _STR},
               prepare=prepare_configurer_rappels, apply=apply_configurer_rappels),
]

for _spec in SPECS:
    register_action(_spec)
