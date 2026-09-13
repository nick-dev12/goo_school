"""
Création d’emplois du temps et de créneaux pour l’assistant vocal.
La confirmation du directeur reste obligatoire avant toute écriture.
"""
import logging
import re
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from django.urls import reverse

logger = logging.getLogger(__name__)

JOURS = (
    'lundi',
    'mardi',
    'mercredi',
    'jeudi',
    'vendredi',
    'samedi',
    'dimanche',
)
TYPE_COURS_VALIDES = {
    'cours',
    'td',
    'tp',
    'controle',
    'examen',
    'sport',
    'pause',
    'autre',
}
TYPE_COURS_ALIASES = {
    'td': 'td',
    'travaux dirigés': 'td',
    'travaux diriges': 'td',
    'tp': 'tp',
    'travaux pratiques': 'tp',
    'contrôle': 'controle',
    'controle': 'controle',
    'examen': 'examen',
    'sport': 'sport',
    'pause': 'pause',
    'cours': 'cours',
}


def emploi_detail_url(classe_id):
    return reverse(
        'administrateur_etablissement:detail_emploi_du_temps',
        args=[classe_id],
    )


def _emploi_actif(ctx, classe):
    from school_admin.model.emploi_du_temps_model import EmploiDuTemps

    qs = EmploiDuTemps.objects.filter(classe=classe, est_actif=True)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire_fk=ctx.annee_scolaire)
            | Q(annee_scolaire=ctx.annee_scolaire.libelle)
        )
    return qs.order_by('-date_modification').first()


def _lookup_incomplete_payload(data, error):
    suggestions = (
        (error or {}).get('suggestions_possibles')
        or (error or {}).get('suggestions')
        or []
    )
    classes = (error or {}).get('classes') or []
    payload = dict(data or {})
    payload.pop('erreur', None)
    return {
        **payload,
        'statut': 'incomplet',
        'trouve': False,
        'plusieurs_classes': bool(
            suggestions or classes or (error or {}).get('statut') == 'plusieurs'
        ),
        'query_normalisee': (error or {}).get('query_normalisee'),
        'suggestions': (error or {}).get('suggestions') or [],
        'suggestions_possibles': suggestions,
        'classes': classes,
        'message': (error or {}).get('message') or (
            'Aucune classe exacte. Propose les plus proches à l’oral.'
        ),
    }


def _resolve_classe(ctx, query):
    from school_admin.services.assistant_tools import tool_ouvrir_classe

    raw = (query or '').strip()
    if not raw:
        return None, {
            'statut': 'incomplet',
            'trouve': False,
            'manquants': ['classe'],
            'message': 'Demande le nom de la classe à l’oral.',
        }
    result = tool_ouvrir_classe(ctx, {'query': raw, 'ouvrir': False})
    if result.get('statut') == 'ok' and result.get('id'):
        return result, None
    return None, result


def _parse_time_value(raw):
    text = (raw or '').strip().lower().replace('h', ':')
    text = re.sub(r'\s+', '', text)
    if not text:
        return ''
    if re.fullmatch(r'\d{1,2}', text):
        text = f'{text}:00'
    if text.endswith(':'):
        text += '00'
    try:
        parsed = datetime.strptime(text, '%H:%M').time()
    except ValueError:
        try:
            parsed = datetime.strptime(text, '%H:%M:%S').time()
        except ValueError:
            return ''
    return parsed.strftime('%H:%M')


def _time_obj(value):
    stamp = _parse_time_value(value)
    if not stamp:
        return None
    return datetime.strptime(stamp, '%H:%M').time()


def _normalize_jour(raw):
    text = (raw or '').strip().lower()
    text = text.replace('é', 'e').replace('è', 'e')
    for jour in JOURS:
        if text == jour or text.startswith(jour):
            return jour
    return ''


def _normalize_type_cours(raw):
    text = (raw or '').strip().lower()
    if not text:
        return 'cours'
    return TYPE_COURS_ALIASES.get(text, text if text in TYPE_COURS_VALIDES else 'cours')


def _heures_chevauchent(debut_a, fin_a, debut_b, fin_b):
    return (
        (debut_a <= debut_b < fin_a)
        or (debut_a < fin_b <= fin_a)
        or (debut_b <= debut_a and fin_b >= fin_a)
        or (debut_a <= debut_b and fin_a >= fin_b)
    )


def _find_matiere(ctx, query, classe=None):
    from school_admin.controllers.emploi_du_temps_controller import EmploiDuTempsController
    from school_admin.model.matiere_model import Matiere
    from school_admin.services.assistant_search import pick_unique

    raw = (query or '').strip()
    if not raw:
        return None
    if classe is not None:
        qs = EmploiDuTempsController._matieres_pour_emploi_du_temps_classe(
            ctx.etablissement, classe
        )
    else:
        qs = Matiere.objects.filter(etablissement=ctx.etablissement, actif=True)
    found = qs.filter(Q(nom__icontains=raw) | Q(code__icontains=raw)).order_by('nom').first()
    if found:
        return found
    return pick_unique(
        list(qs.order_by('nom')[:80]),
        raw,
        lambda matiere: f"{matiere.nom} {matiere.code or ''}",
    )


def _find_professeur(ctx, query):
    from school_admin.model.professeur_model import Professeur
    from school_admin.services.assistant_search import pick_unique

    raw = (query or '').strip()
    if not raw:
        return None
    qs = Professeur.objects.filter(etablissement=ctx.etablissement, actif=True)
    found = qs.filter(Q(nom__icontains=raw) | Q(prenom__icontains=raw)).first()
    if found:
        return found
    return pick_unique(
        list(qs.order_by('nom', 'prenom')[:80]),
        raw,
        lambda prof: f"{prof.prenom} {prof.nom}",
    )


def _find_salle(ctx, query):
    from school_admin.model.salle_model import Salle
    from school_admin.services.assistant_search import pick_unique

    raw = (query or '').strip()
    if not raw:
        return None
    qs = Salle.objects.filter(etablissement=ctx.etablissement, actif=True)
    found = qs.filter(Q(nom__icontains=raw) | Q(numero__icontains=raw)).order_by('numero').first()
    if found:
        return found
    return pick_unique(
        list(qs.order_by('numero')[:80]),
        raw,
        lambda salle: f"{salle.nom or ''} {salle.numero or ''}",
    )


def _classe_choices(ctx, limit=5):
    from school_admin.services.assistant_tools import _classe_item, _classes_qs

    items = []
    for classe in _classes_qs(ctx).order_by('niveau', 'nom')[:limit]:
        item = _classe_item(ctx, classe)
        items.append({
            'label': item['nom'],
            'value': item['nom'],
            'intent': 'chat',
        })
    return items


def _resume_creneau(draft):
    pieces = []
    if draft.get('matiere'):
        pieces.append(draft['matiere'])
    else:
        pieces.append('un cours')
    if draft.get('jour'):
        pieces.append(draft['jour'])
    if draft.get('heure_debut') and draft.get('heure_fin'):
        pieces.append(f"de {draft['heure_debut']} à {draft['heure_fin']}")
    if draft.get('professeur'):
        pieces.append(f"avec {draft['professeur']}")
    if draft.get('salle'):
        pieces.append(f"salle {draft['salle']}")
    if draft.get('classe'):
        pieces.append(f"pour {draft['classe']}")
    return ' '.join(pieces)


def _manquants_creneau(draft):
    missing = []
    if not draft.get('classe') and not draft.get('classe_id'):
        missing.append('classe')
    if not draft.get('jour'):
        missing.append('jour')
    if not draft.get('heure_debut'):
        missing.append('heure_debut')
    if not draft.get('heure_fin'):
        missing.append('heure_fin')
    return missing


def enrich_emploi_draft(ctx, draft):
    data = dict(draft or {})
    data['action'] = 'creer_emploi_du_temps'
    known = _classe_from_item(ctx, data)
    if known:
        data['classe'] = known.nom
        data['classe_id'] = known.id
        data['id'] = known.id
        data['url'] = emploi_detail_url(known.id)
        emploi = _emploi_actif(ctx, known)
        if emploi:
            data['emploi_id'] = emploi.id
            data['deja_existant'] = True
            data['statut'] = 'deja_existant'
            data['message'] = (
                f"La classe {data['classe']} a déjà un emploi du temps actif."
            )
            return data
        session = ctx.annee_scolaire.libelle if ctx.annee_scolaire else ''
        data['session'] = session
        data['statut'] = 'en_attente_confirmation'
        data['resume'] = (
            f"emploi du temps de {data['classe']}"
            + (f" pour {session}" if session else '')
        )
        data['message'] = (
            'Rien n’a encore été créé. Demande une confirmation explicite.'
        )
        return data
    classe_item, error = _resolve_classe(ctx, data.get('classe') or data.get('classe_nom'))
    if error:
        return _lookup_incomplete_payload(data, error)
    if classe_item:
        data['classe'] = classe_item.get('nom')
        data['classe_id'] = classe_item.get('id')
        data['id'] = classe_item.get('id')
        data['url'] = emploi_detail_url(classe_item['id'])
        emploi = _emploi_actif(ctx, _classe_from_item(ctx, classe_item))
        if emploi:
            data['emploi_id'] = emploi.id
            data['deja_existant'] = True
            data['statut'] = 'deja_existant'
            data['message'] = (
                f"La classe {data['classe']} a déjà un emploi du temps actif."
            )
            return data
    session = ctx.annee_scolaire.libelle if ctx.annee_scolaire else ''
    data['session'] = session
    if data.get('classe_id'):
        data['statut'] = 'en_attente_confirmation'
        data['resume'] = (
            f"emploi du temps de {data['classe']}"
            + (f" pour {session}" if session else '')
        )
        data['message'] = (
            'Rien n’a encore été créé. Demande une confirmation explicite.'
        )
    else:
        data['statut'] = 'incomplet'
        data['manquants'] = ['classe']
    return data


def enrich_creneau_draft(ctx, draft):
    data = dict(draft or {})
    data['action'] = 'ajouter_creneau_emploi'
    data['jour'] = _normalize_jour(data.get('jour'))
    data['heure_debut'] = _parse_time_value(data.get('heure_debut'))
    data['heure_fin'] = _parse_time_value(data.get('heure_fin'))
    data['type_cours'] = _normalize_type_cours(data.get('type_cours'))

    classe = _classe_from_item(ctx, data)
    if classe:
        data['classe'] = classe.nom
        data['classe_id'] = classe.id
        data['id'] = classe.id
        data['url'] = emploi_detail_url(classe.id)
        emploi = _emploi_actif(ctx, classe)
        if emploi:
            data['emploi_id'] = emploi.id
            data['emploi_manquant'] = False
        else:
            data['emploi_manquant'] = True
        classe_item, error = None, None
    else:
        classe_item, error = _resolve_classe(ctx, data.get('classe') or data.get('classe_nom'))
    if error:
        return _lookup_incomplete_payload(data, error)
    if classe_item:
        data['classe'] = classe_item.get('nom')
        data['classe_id'] = classe_item.get('id')
        data['id'] = classe_item.get('id')
        data['url'] = emploi_detail_url(classe_item['id'])
        classe = _classe_from_item(ctx, classe_item)
        emploi = _emploi_actif(ctx, classe) if classe else None
        if emploi:
            data['emploi_id'] = emploi.id
            data['emploi_manquant'] = False
        else:
            data['emploi_manquant'] = True

    if data.get('matiere') and classe is not None:
        matiere = _find_matiere(ctx, data['matiere'], classe)
        if matiere:
            data['matiere'] = matiere.nom
            data['matiere_id'] = matiere.id
        else:
            data['matiere_introuvable'] = data['matiere']
            data.pop('matiere_id', None)
    if data.get('professeur'):
        professeur = _find_professeur(ctx, data['professeur'])
        if professeur:
            data['professeur'] = f'{professeur.prenom} {professeur.nom}'.strip()
            data['professeur_id'] = professeur.id
        else:
            data['professeur_introuvable'] = data['professeur']
            data.pop('professeur_id', None)
    if data.get('salle'):
        salle = _find_salle(ctx, data['salle'])
        if salle:
            data['salle'] = salle.nom or salle.numero
            data['salle_id'] = salle.id
        else:
            data['salle_introuvable'] = data['salle']
            data.pop('salle_id', None)

    data['manquants'] = _manquants_creneau(data)
    data['resume'] = _resume_creneau(data)
    if data['manquants']:
        data['statut'] = 'incomplet'
    else:
        data['statut'] = 'en_attente_confirmation'
        data['message'] = (
            'Rien n’a encore été enregistré. Demande une confirmation explicite.'
        )
    return data


def _classe_from_item(ctx, item):
    from school_admin.model.classe_model import Classe

    classe_id = (item or {}).get('classe_id') or (item or {}).get('id') or (item or {}).get('pk')
    if not classe_id:
        return None
    return Classe.objects.filter(
        pk=classe_id,
        etablissement=ctx.etablissement,
        actif=True,
    ).first()


def tool_creer_emploi_du_temps(ctx, args):
    """Prépare la création d’un emploi du temps. N’écrit rien."""
    return enrich_emploi_draft(ctx, args if isinstance(args, dict) else {})


def tool_ajouter_creneau_emploi(ctx, args):
    """Prépare un créneau. N’écrit rien tant que le directeur n’a pas confirmé."""
    return enrich_creneau_draft(ctx, args if isinstance(args, dict) else {})


def apply_emploi_du_temps_draft(ctx, draft):
    from school_admin.model.emploi_du_temps_model import EmploiDuTemps

    data = enrich_emploi_draft(ctx, draft)
    if data.get('erreur') and not data.get('suggestions_possibles'):
        return {'erreur': data['erreur']}
    if data.get('plusieurs_classes') or not data.get('classe_id'):
        return _lookup_incomplete_payload(data, data)
    if not ctx.annee_scolaire:
        return {'erreur': 'Aucune année scolaire active.'}

    classe = _classe_from_item(ctx, data)
    if classe is None:
        return {'erreur': 'Classe introuvable.'}

    existing = _emploi_actif(ctx, classe)
    url = emploi_detail_url(classe.id)
    if existing:
        return {
            'deja_existant': True,
            'classe': classe.nom,
            'classe_id': classe.id,
            'emploi_id': existing.id,
            'url': url,
            'message': f'La classe {classe.nom} a déjà un emploi du temps actif.',
        }

    notes = (data.get('notes') or '').strip() or None
    try:
        with transaction.atomic():
            emploi = EmploiDuTemps.objects.create(
                classe=classe,
                annee_scolaire=ctx.annee_scolaire.libelle,
                annee_scolaire_fk=ctx.annee_scolaire,
                est_actif=True,
                notes=notes,
            )
    except Exception:
        logger.exception("Création emploi du temps Aria")
        return {'erreur': "Impossible de créer l’emploi du temps pour le moment."}

    return {
        'cree': True,
        'classe': classe.nom,
        'classe_id': classe.id,
        'emploi_id': emploi.id,
        'url': url,
        'session': ctx.annee_scolaire.libelle,
        'message': f'Emploi du temps créé pour {classe.nom}.',
    }


def apply_creneau_draft(ctx, draft):
    from school_admin.controllers.emploi_du_temps_controller import EmploiDuTempsController
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.professeur_model import Professeur
    from school_admin.model.salle_model import Salle

    data = enrich_creneau_draft(ctx, draft)
    if data.get('erreur') and not data.get('suggestions_possibles'):
        return {'erreur': data['erreur']}
    if data.get('plusieurs_classes'):
        return _lookup_incomplete_payload(data, data)
    missing = data.get('manquants') or []
    if missing:
        labels = {
            'classe': 'la classe',
            'jour': 'le jour',
            'heure_debut': 'l’heure de début',
            'heure_fin': 'l’heure de fin',
        }
        return {'erreur': 'Il manque ' + ', '.join(labels[item] for item in missing) + '.'}
    if not ctx.annee_scolaire:
        return {'erreur': 'Aucune année scolaire active.'}

    classe = _classe_from_item(ctx, data)
    if classe is None:
        return {'erreur': 'Classe introuvable.'}

    debut = _time_obj(data.get('heure_debut'))
    fin = _time_obj(data.get('heure_fin'))
    if not debut or not fin:
        return {'erreur': 'Les heures sont invalides.'}
    if fin <= debut:
        return {'erreur': 'L’heure de fin doit être après l’heure de début.'}

    jour = data['jour']
    type_cours = _normalize_type_cours(data.get('type_cours'))
    notes = (data.get('notes') or '').strip() or None

    matiere = None
    if data.get('matiere_id'):
        matiere = Matiere.objects.filter(
            pk=data['matiere_id'],
            etablissement=ctx.etablissement,
        ).first()
        if matiere and not EmploiDuTempsController._matiere_est_autorisee_emploi_superieur(
            ctx.etablissement, classe, matiere
        ):
            return {
                'erreur': (
                    "Cette matière n’est pas associée à cette classe. "
                    "Liez-la d’abord dans la gestion pédagogique."
                ),
            }
    elif data.get('matiere_introuvable'):
        return {'erreur': f"Matière introuvable : {data['matiere_introuvable']}."}

    professeur = None
    if data.get('professeur_id'):
        professeur = Professeur.objects.filter(
            pk=data['professeur_id'],
            etablissement=ctx.etablissement,
        ).first()
    elif data.get('professeur_introuvable'):
        return {'erreur': f"Professeur introuvable : {data['professeur_introuvable']}."}

    salle = None
    if data.get('salle_id'):
        salle = Salle.objects.filter(
            pk=data['salle_id'],
            etablissement=ctx.etablissement,
        ).first()
    elif data.get('salle_introuvable'):
        return {'erreur': f"Salle introuvable : {data['salle_introuvable']}."}

    jour_label = dict(CreneauEmploiDuTemps.JOUR_CHOICES).get(jour, jour).capitalize()
    debut_str = debut.strftime('%H:%M')
    fin_str = fin.strftime('%H:%M')

    try:
        with transaction.atomic():
            emploi = _emploi_actif(ctx, classe)
            created_emploi = False
            if emploi is None:
                emploi = EmploiDuTemps.objects.create(
                    classe=classe,
                    annee_scolaire=ctx.annee_scolaire.libelle,
                    annee_scolaire_fk=ctx.annee_scolaire,
                    est_actif=True,
                )
                created_emploi = True

            for existant in CreneauEmploiDuTemps.objects.filter(
                emploi_du_temps=emploi,
                jour=jour,
            ):
                if existant.heure_debut and existant.heure_fin and _heures_chevauchent(
                    debut, fin, existant.heure_debut, existant.heure_fin
                ):
                    matiere_existante = existant.matiere.nom if existant.matiere_id else 'Sans matière'
                    return {
                        'erreur': (
                            f"Un créneau existe déjà {jour_label} de {debut_str} à {fin_str} "
                            f"dans cette classe ({matiere_existante})."
                        ),
                    }

            if professeur:
                conflits = CreneauEmploiDuTemps.objects.filter(
                    professeur=professeur,
                    jour=jour,
                    emploi_du_temps__est_actif=True,
                    emploi_du_temps__annee_scolaire_fk=ctx.annee_scolaire,
                ).exclude(emploi_du_temps=emploi).select_related('matiere')
                for existant in conflits:
                    if existant.heure_debut and existant.heure_fin and _heures_chevauchent(
                        debut, fin, existant.heure_debut, existant.heure_fin
                    ):
                        matiere_conflict = existant.matiere.nom if existant.matiere_id else 'Sans matière'
                        return {
                            'erreur': (
                                f"Ce professeur est déjà programmé {jour_label} "
                                f"de {debut_str} à {fin_str} ({matiere_conflict})."
                            ),
                        }

            creneau = CreneauEmploiDuTemps(
                emploi_du_temps=emploi,
                jour=jour,
                heure_debut=debut,
                heure_fin=fin,
                type_cours=type_cours,
                notes=notes,
                matiere=matiere,
                professeur=professeur,
                salle=salle,
            )
            creneau.save()
            emploi.marquer_comme_modifie()
    except Exception:
        logger.exception("Ajout créneau Aria")
        return {'erreur': "Impossible d’ajouter ce créneau pour le moment."}

    return {
        'cree': True,
        'emploi_cree': created_emploi,
        'classe': classe.nom,
        'classe_id': classe.id,
        'emploi_id': emploi.id,
        'creneau_id': creneau.id,
        'jour': jour_label,
        'heure_debut': debut_str,
        'heure_fin': fin_str,
        'matiere': matiere.nom if matiere else None,
        'professeur': f'{professeur.prenom} {professeur.nom}'.strip() if professeur else None,
        'salle': (salle.nom or salle.numero) if salle else None,
        'url': emploi_detail_url(classe.id),
        'message': (
            f"Créneau ajouté {jour_label} de {debut_str} à {fin_str}"
            + (f" ({matiere.nom})" if matiere else '')
            + f" pour {classe.nom}."
        ),
    }


def _prompt_class_suggestions(draft, action_label):
    data = draft or {}
    rows = data.get('suggestions_possibles') or data.get('classes') or []
    names = []
    for item in rows[:3]:
        if not isinstance(item, dict):
            continue
        label = item.get('libelle') or item.get('nom') or item.get('titre')
        if label:
            names.append(label)
    if len(names) == 1:
        return (
            f"Je n’ai pas trouvé la classe exacte. "
            f"Vous voulez {action_label} {names[0]} ?"
        )
    if len(names) == 2:
        return (
            f"Je n’ai pas trouvé la classe exacte. "
            f"Vous voulez {names[0]} ou {names[1]} ?"
        )
    if len(names) >= 3:
        return (
            f"Je n’ai pas trouvé la classe exacte. "
            f"Ça correspond plutôt à {names[0]}, {names[1]} ou {names[2]} ?"
        )
    return "Je n’ai pas trouvé la classe exacte. Laquelle voulez-vous ?"


def next_emploi_prompt(draft):
    data = draft or {}
    if data.get('plusieurs_classes') or data.get('suggestions_possibles'):
        return _prompt_class_suggestions(data, "l’emploi du temps de")
    if not data.get('classe'):
        return "Pour quelle classe dois-je créer l’emploi du temps ?"
    if data.get('deja_existant'):
        return (
            f"La classe {data['classe']} a déjà un emploi du temps. "
            "Je l’ouvre. Voulez-vous y ajouter un créneau ?"
        )
    session = data.get('session') or ''
    extra = f" pour {session}" if session else ''
    return (
        f"Je crée l’emploi du temps de {data['classe']}{extra}. "
        "C’est bon ?"
    )


def next_creneau_prompt(draft):
    data = draft or {}
    if data.get('plusieurs_classes') or data.get('suggestions_possibles'):
        return _prompt_class_suggestions(data, "ajouter ce créneau pour")
    if not data.get('classe'):
        return "Pour quelle classe dois-je ajouter ce créneau ?"
    if not data.get('jour'):
        return "Quel jour dois-je placer ce cours ?"
    if not data.get('heure_debut') or not data.get('heure_fin'):
        return "De quelle heure à quelle heure ?"
    if data.get('matiere_introuvable'):
        return f"Je ne trouve pas la matière {data['matiere_introuvable']}. Quel nom exact ?"
    if data.get('professeur_introuvable'):
        return f"Je ne trouve pas le professeur {data['professeur_introuvable']}. Quel nom exact ?"
    if data.get('salle_introuvable'):
        return f"Je ne trouve pas la salle {data['salle_introuvable']}. Quel numéro ?"
    extra = ''
    if data.get('emploi_manquant'):
        extra = " L’emploi du temps n’existe pas encore : je le créerai en même temps."
    return f"Je place {_resume_creneau(data)}.{extra} C’est bon ?"


def choices_for_emploi(draft, kind='creer_emploi_du_temps'):
    data = draft or {}
    if data.get('plusieurs_classes') or data.get('suggestions_possibles'):
        from school_admin.services.assistant_search import choices_from_class_lookup

        return choices_from_class_lookup(data)
    if not data.get('classe'):
        return []
    if kind == 'ajouter_creneau_emploi' and not data.get('jour'):
        return [
            {'label': jour.capitalize(), 'value': jour, 'intent': 'chat'}
            for jour in JOURS[:6]
        ]
    if kind == 'creer_emploi_du_temps' and data.get('deja_existant'):
        return [
            {'label': 'Ajouter un créneau', 'value': 'Ajoute un créneau.', 'intent': 'chat'},
            {'label': 'Ouvrir', 'value': 'Oui, ouvre-le.', 'intent': 'confirm'},
            {'label': 'Annuler', 'value': 'Annuler.', 'intent': 'cancel'},
        ]
    if data.get('statut') == 'en_attente_confirmation' or (
        kind == 'ajouter_creneau_emploi' and not _manquants_creneau(data)
    ):
        return [
            {'label': 'Oui, c’est bon', 'value': 'Oui, c’est bon.', 'intent': 'confirm'},
            {'label': 'Modifier', 'value': 'Je veux modifier.', 'intent': 'modify'},
            {'label': 'Annuler', 'value': 'Annuler.', 'intent': 'cancel'},
        ]
    return []
