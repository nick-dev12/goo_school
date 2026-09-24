"""
Scolarité parent — dettes, échéances, reçus (Par5, parité vues parent).
"""
from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.services.assistant_parent_scope import get_eleve_lie, liens_valides_qs


def _dec(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _annee_eleve(eleve):
    etab = eleve.etablissement
    if not etab:
        return None
    return AnneeScolaire.get_session_active(etab)


def _resume_payload(eleve, resume, devise):
    prochaines = []
    for charge in (resume.charges or [])[:5]:
        if getattr(charge, 'reste', None) and charge.reste > 0:
            prochaines.append({
                'libelle': charge.libelle,
                'reste': _dec(charge.reste),
                'date_echeance': (
                    charge.date_echeance.isoformat() if charge.date_echeance else None
                ),
            })
    return {
        'eleve_id': eleve.id,
        'nom': getattr(eleve, 'nom_complet', None) or f'{eleve.prenom} {eleve.nom}',
        'devise': devise,
        'total_du': _dec(resume.total_du),
        'total_paye': _dec(resume.total_paye),
        'reste': _dec(resume.reste),
        'statut': resume.statut,
        'prochaine_echeance': (
            resume.prochaine_echeance.isoformat() if resume.prochaine_echeance else None
        ),
        'prochaine_libelle': resume.prochaine_libelle or '',
        'prochaines_charges': prochaines[:3],
    }


def read_scolarite_enfant(eleve, ctx):
    from school_admin.model.comptabilite_eleve_model import PaiementEleve
    from school_admin.services.recouvrement import devise_etablissement, resume_dette_eleve

    etab = eleve.etablissement
    annee = ctx.annee_scolaire or _annee_eleve(eleve)
    if not etab or not annee:
        return {'erreur': 'Année scolaire ou établissement introuvable pour cet enfant.'}

    resume = resume_dette_eleve(eleve, etab, annee)
    devise = devise_etablissement(etab)
    payload = _resume_payload(eleve, resume, devise)
    recus = []
    for p in PaiementEleve.objects.filter(eleve=eleve, annee_scolaire=annee).order_by(
        '-date_paiement'
    )[:8]:
        recus.append({
            'paiement_id': p.id,
            'numero_recu': p.numero_recu or '',
            'montant': _dec(p.montant),
            'date_paiement': p.date_paiement.isoformat() if p.date_paiement else None,
            'mode': getattr(p, 'mode_paiement', None),
        })
    payload['recus_recents'] = recus
    payload['url_scolarite'] = reverse('school_admin:scolarite_parent')
    payload['message'] = (
        f"Scolarité de {eleve.prenom} : reste {_dec(resume.reste)} {devise}"
        + (
            f", prochaine échéance {resume.prochaine_echeance.isoformat()}"
            if resume.prochaine_echeance
            else ''
        )
        + '.'
    )
    return payload


def read_scolarite_famille(parent, ctx):
    from school_admin.services.recouvrement import devise_etablissement, resume_dette_eleve

    total_reste = Decimal('0.00')
    prochaine = None
    prochaine_enfant = None
    enfants = []
    devise = devise_etablissement(parent.etablissement) if parent.etablissement else ''

    for lien in liens_valides_qs(parent).filter(eleve__actif=True):
        eleve = lien.eleve
        if not eleve or not eleve.etablissement:
            continue
        annee = AnneeScolaire.get_session_active(eleve.etablissement)
        if not annee:
            continue
        resume = resume_dette_eleve(eleve, eleve.etablissement, annee)
        dev = devise_etablissement(eleve.etablissement)
        if dev and not devise:
            devise = dev
        total_reste += resume.reste
        if resume.prochaine_echeance:
            if prochaine is None or resume.prochaine_echeance < prochaine:
                prochaine = resume.prochaine_echeance
                prochaine_enfant = getattr(eleve, 'nom_complet', None) or eleve.prenom
        enfants.append(_resume_payload(eleve, resume, dev))
    return {
        'nb_enfants': len(enfants),
        'enfants': enfants,
        'dette_totale': _dec(total_reste),
        'devise': devise,
        'prochaine_echeance': prochaine.isoformat() if prochaine else None,
        'prochaine_echeance_enfant': prochaine_enfant,
        'url_scolarite': reverse('school_admin:scolarite_parent'),
        'message': (
            f"Dette totale scolarité : {_dec(total_reste)} {devise}"
            + (
                f". Prochaine échéance {prochaine.isoformat()}"
                + (f" ({prochaine_enfant})" if prochaine_enfant else '')
                if prochaine
                else ''
            )
            + '.'
        ),
    }


def paiement_autorise_parent(parent, paiement_id):
    from school_admin.model.comptabilite_eleve_model import PaiementEleve

    if not parent or not paiement_id:
        return None, {'erreur': 'Paiement invalide.', 'statut': 'erreur'}
    try:
        pid = int(paiement_id)
    except (TypeError, ValueError):
        return None, {'erreur': 'Identifiant de paiement invalide.'}
    paiement = PaiementEleve.objects.filter(pk=pid).select_related('eleve').first()
    if not paiement or not paiement.eleve_id:
        return None, {'erreur': 'Reçu introuvable.', 'statut': 'introuvable'}
    eleve = get_eleve_lie(parent, paiement.eleve_id)
    if not eleve:
        return None, {
            'erreur': "Vous n'avez pas accès à ce reçu (enfant non lié).",
            'statut': 'acces_refuse',
            'paiement_id': pid,
        }
    return paiement, None


def ouvrir_recu_parent(parent, paiement_id, ouvrir=True):
    paiement, err = paiement_autorise_parent(parent, paiement_id)
    if err:
        return err
    url = reverse('school_admin:recu_paiement_parent', args=[paiement.id])
    return {
        'statut': 'ok',
        'paiement_id': paiement.id,
        'numero_recu': paiement.numero_recu or '',
        'eleve_id': paiement.eleve_id,
        'montant': _dec(paiement.montant),
        'url': url,
        'ouvrir': bool(ouvrir),
        'message': f"J’ouvre le reçu {paiement.numero_recu or paiement.id}.",
    }
