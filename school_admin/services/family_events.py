from school_admin.services.parent_notification_service import ParentNotificationService
from school_admin.services.eleve_notification_service import EleveNotificationService


def notify_family(eleve, title, message, event_key, scolarite=False):
    if not eleve or not eleve.actif:
        return
    data = {'event_key': event_key, 'eleve_id': str(eleve.pk)}
    student_url = '/eleve/scolarite/' if scolarite else '/eleve/notifications/'
    parent_url = '/parent/scolarite/' if scolarite else '/parent/notifications/'
    EleveNotificationService._dispatch(
        eleve, 'information', title, message, payload={**data, 'url': student_url},
        push_title=title, push_body=message, push_data={**data, 'url': student_url},
    )
    ParentNotificationService.notify_custom(
        eleve, 'information', title, f'{eleve.nom_complet} : {message}',
        payload={**data, 'url': parent_url}, push_data={**data, 'url': parent_url},
    )
