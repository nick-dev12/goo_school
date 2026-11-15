import uuid
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from school_admin.services.family_events import notify_family

EVALUATIONS = {'school_admin.evaluation', 'school_admin.evaluationprimaire'}
EXERCICES = {'school_admin.exercicemaison'}
WATCHED = EVALUATIONS | EXERCICES | {'school_admin.choixfraisannexeeleve'}


@receiver(pre_save)
def remember_family_change(sender, instance, raw=False, **kwargs):
    if raw or sender._meta.label_lower not in WATCHED:
        return
    if sender._meta.label_lower in EVALUATIONS:
        fields = ['titre', 'description', 'date_evaluation', 'bareme', 'matiere_id', 'actif']
    elif sender._meta.label_lower in EXERCICES:
        fields = ['titre', 'description', 'date_rendu', 'matiere_id', 'actif']
    else:
        fields = ['statut']
    instance._family_old = sender.objects.filter(pk=instance.pk).values(*fields).first() if instance.pk else None


@receiver(post_save)
def notify_family_change(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    model = sender._meta.label_lower
    if model in EVALUATIONS | EXERCICES:
        old = getattr(instance, '_family_old', None)
        if created or not old or all(str(value) == str(getattr(instance, key)) for key, value in old.items()):
            return
        if not old.get('actif') and not instance.actif:
            return
        from school_admin.services.notification_tasks import eleves_inscrits_classe
        if model in EXERCICES:
            title = 'Devoir modifié' if instance.actif else 'Devoir annulé'
            date_evenement = instance.date_rendu
        else:
            title = 'Évaluation modifiée' if instance.actif else 'Évaluation annulée'
            date_evenement = instance.date_evaluation
        text = f'{instance.titre} — {date_evenement}.'
        event = f'{model}:{instance.pk}:{uuid.uuid4()}'
        for eleve in eleves_inscrits_classe(instance.classe, instance.annee_scolaire):
            notify_family(eleve, title, text, f'{event}:{eleve.pk}')
    elif model == 'school_admin.paiementeleve' and created:
        notify_family(instance.eleve, 'Paiement reçu', f'Paiement de {instance.montant} {instance.etablissement.devise_monnaie or "FCFA"} enregistré.', f'paiement:{instance.pk}', True)
    elif model == 'school_admin.inscriptioneleve' and created:
        title = 'Réinscription confirmée' if instance.statut == 'reinscription' else 'Inscription confirmée'
        notify_family(instance.eleve, title, f'Inscription confirmée pour {instance.annee_scolaire.libelle}.', f'inscription:{instance.pk}')
    elif model == 'school_admin.choixfraisannexeeleve':
        old = getattr(instance, '_family_old', None)
        notify = not created and old and old['statut'] != instance.statut
        if created and instance.statut == 'inscrit':
            from school_admin.model.inscription_eleve_model import InscriptionEleve
            from school_admin.controllers.comptabilite_controller import ComptabiliteController
            from school_admin.utils.frais_annexes import frais_au_choix_pour_parametres
            inscription = InscriptionEleve.objects.filter(eleve=instance.eleve, annee_scolaire=instance.annee_scolaire).select_related('classe').first()
            if inscription and inscription.classe:
                params = ComptabiliteController._get_parametres_for_classe(instance.etablissement, inscription.classe)
                notify = instance.code in {item['code'] for item in frais_au_choix_pour_parametres(params)}
        if notify:
            state = dict(instance.STATUT_CHOICES).get(instance.statut, instance.statut)
            notify_family(instance.eleve, 'Frais annexe mis à jour', f'Choix pour {instance.code} : {state}.', f'choix:{instance.pk}:{uuid.uuid4()}', True)
