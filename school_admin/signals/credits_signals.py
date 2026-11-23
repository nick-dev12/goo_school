"""
Supérieur (LMD) : garde à jour les crédits enregistrés avec les moyennes quand la structure change.

Les crédits d'une matière (EC) dans une classe dépendent des crédits de son module (UE) pour cette classe
et des poids de ses matières (services/credits_lmd). Dès qu'un de ces réglages change, les moyennes
déjà enregistrées de l'année active sont remises à jour.
"""
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from school_admin.model.matiere_model import Matiere
from school_admin.model.module_model import ModuleClasse


def _actualiser(*module_ids):
    from school_admin.services.credits_lmd import actualiser_credits_enregistres

    for module_id in {m for m in module_ids if m}:
        try:
            actualiser_credits_enregistres(module_id)
        except Exception:  # ne jamais bloquer l'enregistrement d'un réglage
            import logging
            logging.getLogger(__name__).exception("Actualisation des crédits enregistrés impossible (UE %s)", module_id)


@receiver(post_save, sender=ModuleClasse, dispatch_uid='credits_lmd_module_classe_save')
@receiver(post_delete, sender=ModuleClasse, dispatch_uid='credits_lmd_module_classe_delete')
def credits_module_classe(sender, instance, **kwargs):
    _actualiser(instance.module_id)


@receiver(pre_save, sender=Matiere, dispatch_uid='credits_lmd_matiere_avant')
def memoriser_matiere(sender, instance, **kwargs):
    instance._credits_avant = None
    if instance.pk:
        instance._credits_avant = (Matiere.objects.filter(pk=instance.pk)
                                   .values_list('module_id', 'credits', 'actif').first())


@receiver(post_save, sender=Matiere, dispatch_uid='credits_lmd_matiere_save')
def credits_matiere(sender, instance, created, **kwargs):
    avant = getattr(instance, '_credits_avant', None)
    if not instance.module_id and not (avant and avant[0]):
        return
    if created or avant is None or avant != (instance.module_id, instance.credits, instance.actif):
        _actualiser(instance.module_id, avant[0] if avant else None)


@receiver(post_delete, sender=Matiere, dispatch_uid='credits_lmd_matiere_delete')
def credits_matiere_supprimee(sender, instance, **kwargs):
    _actualiser(instance.module_id)


@receiver(m2m_changed, sender=Matiere.classes.through, dispatch_uid='credits_lmd_matiere_classes')
def credits_classes_matiere(sender, instance, action, reverse, **kwargs):
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return
    if not reverse:
        _actualiser(instance.module_id)
    else:  # classe.matieres.add(...) : instance est la classe
        pk_set = kwargs.get('pk_set') or ()
        _actualiser(*Matiere.objects.filter(pk__in=pk_set).values_list('module_id', flat=True))
