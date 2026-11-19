"""
Diplômes du supérieur : éligibilité selon les crédits capitalisés, mention, numérotation, délivrance.

Un étudiant inscrit dans une classe de fin de cycle (L3, M2, BTS 2, ING 3…) obtient le diplôme lorsque
ses UE capitalisées (délibérations clôturées) atteignent les crédits du cycle. La mention vient de la
moyenne du dernier bilan annuel (après points de jury).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

# niveau de sortie : (intitulé du diplôme, grade, crédits du cycle)
DIPLOMES = {
    'L3': ('Licence', 'Licence', 180),
    'LP': ('Licence professionnelle', 'Licence', 60),
    'M2': ('Master', 'Master', 120),
    'BTS2': ('Brevet de technicien supérieur (BTS)', 'BTS', 120),
    'DUT2': ('Diplôme universitaire de technologie (DUT)', 'DUT', 120),
    'ING3': ("Diplôme d'ingénieur", 'Ingénieur', 180),
    'MBA2': ('Master of Business Administration (MBA)', 'Master', 120),
    'DU': ('Diplôme universitaire', 'DU', 60),
    'MED7': ('Diplôme de docteur en médecine', 'Doctorat', 420),
}
D0 = Decimal('0')


def _f(valeur):
    v = Decimal(str(valeur or 0)).normalize()
    return format(v, 'f').replace('.', ',')


def diplome_de(classe):
    return DIPLOMES.get((classe.niveau_lmd or '').strip())


def credits_capitalises(eleve):
    from school_admin.model.deliberation_model import UECapitalisee

    return sum((Decimal(str(c.credits or 0)) for c in UECapitalisee.objects.filter(eleve=eleve)), D0)


def derniere_decision_annuelle(eleve, classe):
    from school_admin.model.deliberation_model import DecisionJury, Deliberation

    return (DecisionJury.objects.filter(eleve=eleve, deliberation__classe=classe, deliberation__periode__isnull=True,
                                        deliberation__statut=Deliberation.STATUT_CLOTUREE)
            .order_by('-deliberation__annee_scolaire__annee_debut').first())


def situation(classe, eleves):
    """Pour chaque étudiant : crédits, éligibilité, diplôme déjà délivré."""
    from school_admin.model.admission_model import Diplome

    info = diplome_de(classe)
    requis = Decimal(info[2]) if info else None
    lignes = []
    for e in eleves:
        cr = credits_capitalises(e)
        dj = derniere_decision_annuelle(e, classe)
        deja = Diplome.objects.filter(eleve=e, classe=classe, annule=False).first()
        eligible = bool(info and cr >= requis and dj is not None and dj.est_admis)
        motif = ''
        if not info:
            motif = "Classe qui n'est pas de fin de cycle"
        elif dj is None:
            motif = "Pas de bilan annuel clôturé"
        elif not dj.est_admis:
            motif = f"Décision du jury : {dj.get_decision_display()}"
        elif cr < requis:
            motif = f"{_f(cr)} crédits capitalisés sur {_f(requis)}"
        lignes.append({'eleve': e, 'credits': cr, 'requis': requis, 'eligible': eligible, 'diplome': deja,
                       'decision': dj, 'moyenne': dj.moyenne_jury if dj else None,
                       'mention': (dj.mention if dj else ''), 'motif': motif,
                       'pct': int(min(100, cr / requis * 100)) if requis else 0})
    return lignes


def _numero(etablissement, annee, niveau):
    from school_admin.model.admission_model import Diplome

    code = (etablissement.code_etablissement or 'DIP').split('-')[0][:6]
    an = annee.annee_fin if annee else timezone.localdate().year
    prefixe = f"{code}-{an}-{niveau}-"
    n = Diplome.objects.filter(numero__startswith=prefixe).count() + 1
    while Diplome.objects.filter(numero=f"{prefixe}{n:05d}").exists():
        n += 1
    return f"{prefixe}{n:05d}"


def delivrer(classe, eleves, annee, date=None):
    """Délivre le diplôme aux étudiants éligibles (pas de doublon). Renvoie la liste des diplômes créés."""
    from school_admin.model.admission_model import Diplome

    crees = []
    with transaction.atomic():
        from school_admin.model.classe_model import Classe
        from school_admin.model.etablissement_model import Etablissement
        from school_admin.services.deliberations import etudiants

        # Même ordre pour délivrance et annulation. Le verrou établissement protège
        # aussi la numérotation partagée par plusieurs classes du même niveau.
        Etablissement.objects.select_for_update().get(pk=classe.etablissement_id)
        classe = Classe.objects.select_for_update().get(pk=classe.pk)
        if classe.niveau != 'superieur' or classe.etablissement.type_etablissement != 'superieur':
            raise ValueError("Classe non autorisée pour une attestation.")
        info = diplome_de(classe)
        if not info or not annee or annee.etablissement_id != classe.etablissement_id:
            return []
        intitule, grade, _ = info
        domaine = ''
        if classe.department_id:
            dep = classe.department
            domaine = dep.mention or dep.nom
        demandes = {e.pk for e in eleves}
        autorises = {e.pk: e for e in etudiants(classe, annee)
                     if e.etablissement_id == classe.etablissement_id}
        if not demandes <= autorises.keys():
            raise ValueError("La sélection contient un étudiant étranger à la classe.")
        lignes = situation(classe, [autorises[pk] for pk in sorted(demandes)])
        if any(not l['eligible'] and not l['diplome'] for l in lignes):
            raise ValueError("La sélection contient un étudiant inéligible.")
        for l in lignes:
            if not l['eligible'] or l['diplome']:
                continue
            crees.append(Diplome.objects.create(
                eleve=l['eleve'], etablissement=classe.etablissement, annee_scolaire=annee, classe=classe,
                intitule=f"{intitule}{' en ' + domaine if domaine else ''}", grade=grade,
                domaine=(classe.department.domaine if classe.department_id else '') or '',
                mention=l['mention'], moyenne=l['moyenne'], credits=l['credits'],
                numero=_numero(classe.etablissement, annee, (classe.niveau_lmd or 'X')),
                date_delivrance=date or timezone.localdate()))
    return crees


def annuler(diplome, auteur, motif):
    """Annulation tracée ; une redélivrance conserve cette référence et sa trace."""
    from uuid import uuid4
    from school_admin.model.admission_model import Diplome
    from school_admin.model.classe_model import Classe
    from school_admin.model.etablissement_model import Etablissement
    from school_admin.model.sync_action_model import SyncAction

    motif = (motif or '').strip()
    if not isinstance(auteur, Etablissement) or auteur.pk != diplome.etablissement_id:
        raise PermissionError("Seul le directeur de cet établissement peut annuler.")
    if not motif:
        raise ValueError("Le motif d'annulation est obligatoire.")
    with transaction.atomic():
        Etablissement.objects.select_for_update().get(pk=diplome.etablissement_id)
        if diplome.classe_id:
            Classe.objects.select_for_update().get(pk=diplome.classe_id)
        d = Diplome.objects.select_for_update().get(pk=diplome.pk)
        if d.annule:
            return
        SyncAction.objects.create(
            client_uuid=str(uuid4()), resource='diplome', action='CANCEL',
            utilisateur_id=auteur.pk, utilisateur_type='etablissement',
            resultat={'diplome_id': d.pk, 'numero': d.numero, 'classe_id': d.classe_id,
                      'etablissement_id': d.etablissement_id, 'motif': motif,
                      'auteur': str(auteur), 'date': timezone.now().isoformat()})
        d.annule = True
        d.save(update_fields=['annule'])
        diplome.annule = True
    return diplome
