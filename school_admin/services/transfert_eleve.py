from django.db import transaction

from school_admin.model.classe_model import Classe
from school_admin.model.deliberation_model import Deliberation
from school_admin.model.eleve_model import Eleve
from school_admin.model.inscription_eleve_model import InscriptionEleve


class TransfertInvalide(ValueError):
    pass


def inscription_a_transferer(etablissement, annee, eleve_id):
    if annee is None or not annee.est_active or annee.etablissement_id != etablissement.pk:
        raise TransfertInvalide("Sélectionnez l’année scolaire active pour transférer un élève.")
    inscriptions = InscriptionEleve.objects.filter(
        etablissement=etablissement, annee_scolaire=annee, eleve_id=eleve_id,
    )
    resultats = list(inscriptions[:2])
    if len(resultats) != 1 or resultats[0].classe_id is None:
        raise TransfertInvalide("L’élève doit avoir une seule inscription avec une classe pour cette année.")
    return resultats[0]


@transaction.atomic
def transferer(eleve, annee, destination_id, *, origine_attendue=None):
    etablissement = eleve.etablissement
    inscription = inscription_a_transferer(etablissement, annee, eleve.pk)
    classes = {
        classe.pk: classe
        for classe in Classe.objects.select_for_update().filter(
            etablissement=etablissement, pk__in=[inscription.classe_id, destination_id],
        ).order_by('pk')
    }
    origine_id = inscription.classe_id
    inscription.refresh_from_db(fields=['classe'])
    if inscription.classe_id != origine_id or (origine_attendue is not None and origine_id != origine_attendue):
        raise TransfertInvalide("La classe de l’élève a changé. Préparez de nouveau le transfert.")
    destination = classes.get(destination_id)
    origine = classes.get(origine_id)
    if not origine or not destination or not destination.actif:
        raise TransfertInvalide("Classe d’origine ou de destination indisponible.")
    if origine == destination:
        raise TransfertInvalide(f"L’élève est déjà dans la classe {destination.nom}.")
    if Deliberation.objects.filter(
        etablissement=etablissement, classe_id__in=classes,
        annee_scolaire=annee, statut=Deliberation.STATUT_CLOTUREE,
    ).exists():
        raise TransfertInvalide("Une délibération est clôturée pour l’une de ces classes. Vérifiez le dossier du jury.")
    if destination.places_disponibles < 1:
        raise TransfertInvalide(f"La classe {destination.nom} est complète.")
    eleve = Eleve.objects.select_for_update().get(pk=eleve.pk, etablissement=etablissement)
    inscription.classe = destination
    inscription.save(update_fields=['classe'])
    eleve.classe = destination
    eleve.save(update_fields=['classe'])
    return origine, destination
