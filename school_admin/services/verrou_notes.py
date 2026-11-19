"""Verrou commun aux saisies ORM et a la cloture du jury (PostgreSQL)."""
from contextlib import contextmanager
from django.core.exceptions import ValidationError
from django.db import transaction

@contextmanager
def verrou_note(classe_id, periode, saisie=True):
    from school_admin.model.classe_model import Classe
    from school_admin.services.deliberations import periode_verrouillee
    with transaction.atomic():
        classe = Classe.objects.select_for_update().get(pk=classe_id)
        if saisie and classe.niveau == 'superieur' and periode and periode_verrouillee(classe, periode):
            raise ValidationError('Les notes de ce semestre sont verrouillées par le jury.')
        yield
