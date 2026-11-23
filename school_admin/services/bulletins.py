"""Opérations communes aux écrans de bulletins et à l’assistant."""

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.ponderation_model import Ponderation
from school_admin.model.standards_reussite_model import (
    AppreciationConseilStandard,
    AppreciationMatiereStandard,
    StandardsReussite,
)

logger = logging.getLogger(__name__)


def periodes_bulletins(etablissement, annee, classe):
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement, annee_scolaire_fk=annee, est_active=True,
    )
    return PeriodeScolaire.filter_queryset_for_classe(
        periodes, etablissement, classe,
    ).order_by('date_debut', 'pk')


def ponderation_bulletin(etablissement, annee):
    actives = Ponderation.objects.filter(etablissement=etablissement, actif=True)
    return actives.filter(annee_scolaire=annee).first() or actives.filter(annee_scolaire='').first()


def bulletins_classe(classe, periode, annee):
    inscriptions = InscriptionEleve.objects.filter(
        etablissement_id=classe.etablissement_id, classe=classe, annee_scolaire=annee,
    )
    return MoyennePeriode.objects.filter(
        etablissement_id=classe.etablissement_id, periode=periode, annee_scolaire=annee,
        est_moyenne_generale=True, moyenne_generale__isnull=False,
        eleve_id__in=inscriptions.values('eleve_id'),
    )


@transaction.atomic
def publier_bulletins(classe, periode, bulletins, *, republier=False):
    from school_admin.services.notification_tasks import schedule_bulletin_publication

    selection = bulletins if republier else bulletins.filter(est_publie=False)
    a_publier = list(selection.order_by('pk').select_for_update())
    if not a_publier:
        return 0
    maintenant = timezone.now()
    publies = MoyennePeriode.objects.filter(pk__in=[m.pk for m in a_publier]).update(
        est_publie=True, date_publication=maintenant, updated_at=maintenant,
    )
    visibles = tuple(m.eleve_id for m in a_publier if m.afficher_bulletin)
    if visibles:
        try:
            schedule_bulletin_publication(
                classe_id=classe.id, periode_id=periode.id,
                etablissement_id=classe.etablissement_id, eleve_ids=visibles,
            )
        except Exception:
            logger.exception("Notification de publication des bulletins de la classe %s", classe.pk)
    return publies


def valider_bareme(section, lignes):
    if section not in ('conseil', 'matieres') or not isinstance(lignes, list) or not lignes:
        raise ValueError("Indiquez au moins un palier et son appréciation.")
    resultat = []
    seuils = set()
    for ligne in lignes:
        try:
            note_min = Decimal(str(ligne['min']).replace(',', '.')).quantize(Decimal('0.01'))
            label = ligne['label'].strip()
            if not note_min.is_finite() or not 0 <= note_min <= 20 or note_min in seuils:
                raise ValueError
            if not label or len(label) > (150 if section == 'matieres' else 200):
                raise ValueError
            palier = {'min': str(note_min), 'label': label}
            if section == 'matieres':
                note_max = Decimal(str(ligne['max']).replace(',', '.')).quantize(Decimal('0.01'))
                if not note_max.is_finite() or not note_min < note_max <= 20:
                    raise ValueError
                palier['max'] = str(note_max)
        except (InvalidOperation, TypeError, AttributeError, KeyError, ValueError) as exc:
            raise ValueError(f"Le palier nº {len(resultat) + 1} est invalide. Vérifiez les notes et le libellé.") from exc
        seuils.add(note_min)
        resultat.append(palier)
    resultat.sort(key=lambda palier: Decimal(palier['min']))
    if section == 'matieres' and any(
        Decimal(a['max']) > Decimal(b['min']) for a, b in zip(resultat, resultat[1:])
    ):
        raise ValueError("Les intervalles des matières se chevauchent.")
    return resultat


@transaction.atomic
def enregistrer_bareme(etablissement, annee, section, lignes):
    lignes = valider_bareme(section, lignes)
    standards, _ = StandardsReussite.objects.select_for_update().get_or_create(
        etablissement=etablissement, defaults={'annee_scolaire': annee},
    )
    if section == 'conseil':
        standards.appreciations_conseil.all().delete()
        AppreciationConseilStandard.objects.bulk_create([
            AppreciationConseilStandard(standards=standards, note_min=p['min'], appreciation=p['label'])
            for p in lignes
        ])
    else:
        standards.appreciations_matieres.all().delete()
        AppreciationMatiereStandard.objects.bulk_create([
            AppreciationMatiereStandard(
                standards=standards, note_min=p['min'], note_max=p['max'], appreciation=p['label'],
            )
            for p in lignes
        ])
    standards.annee_scolaire = annee
    standards.save(update_fields=['annee_scolaire', 'date_modification'])
