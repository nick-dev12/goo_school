"""Rappels personnels demandés à l'assistant : envoyés à l'heure dite (cloche + push).

Contrairement aux rappels automatiques, ils ne tiennent pas compte des heures calmes ni des réglages de
l'école : c'est la personne elle-même qui a choisi l'heure.
"""
import logging

from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


def _url_notifications(personnel):
    try:
        return reverse('directeur:notifications_directeur')
    except NoReverseMatch:
        return '/'


def envoyer_rappels_personnels(maintenant=None) -> int:
    """Envoie les rappels arrivés à échéance. Renvoie le nombre de rappels envoyés."""
    from school_admin.model.notification_directeur_model import NotificationDirecteur
    from school_admin.model.rappel_model import NotificationPersonnel, RappelPersonnel
    from school_admin.services.push_delivery import enqueue

    maintenant = maintenant or timezone.now()
    envoyes = 0
    dus = RappelPersonnel.objects.filter(envoye=False, echeance__lte=maintenant).select_related(
        'etablissement', 'personnel')[:200]
    for rappel in dus:
        try:
            with transaction.atomic():
                verrou = RappelPersonnel.objects.select_for_update().filter(pk=rappel.pk, envoye=False).first()
                if verrou is None:
                    continue  # déjà envoyé par un autre passage
                url = _url_notifications(rappel.personnel)
                donnees = {'rappel': 'PERSONNEL', 'rappel_personnel_id': rappel.pk, 'url': url, 'redirect_url': url}
                titre = 'Rappel'
                if rappel.personnel_id:
                    destinataire = rappel.personnel
                    notif = NotificationPersonnel.objects.create(
                        personnel=destinataire, titre=titre, message=rappel.texte, type_notification='rappel',
                        donnees=donnees)
                else:
                    destinataire = rappel.etablissement
                    notif = NotificationDirecteur.objects.create(
                        etablissement=destinataire, titre=titre, message=rappel.texte,
                        type_notification='information', donnees=donnees)
                verrou.envoye = True
                verrou.date_envoi = maintenant
                verrou.save(update_fields=['envoye', 'date_envoi'])
                enqueue([destinataire], titre, rappel.texte[:400],
                        {'type': 'rappel', 'url': url, 'redirect_url': url,
                         'event_key': f'rappel-personnel:{rappel.pk}',
                         '_push_notification_ids': {str(destinataire.pk): notif.pk}})
                envoyes += 1
        except Exception:
            logger.exception('Rappel personnel %s non envoyé', rappel.pk)
    return envoyes
