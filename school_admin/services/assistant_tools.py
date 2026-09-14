"""
Outils ORM scopés à l'établissement pour l'assistant vocal directeur.
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from school_admin.services.assistant_search import CLASSE_PARAM_DESCRIPTION

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 12
NOTES_LIMIT = 10
ANNONCE_CONTENU_MAX = 8000

DESTINATAIRE_VALIDES = {
    'tous',
    'enseignants',
    'parents',
    'eleves',
    'personnel_administratif',
}
DESTINATAIRE_ALIASES = {
    'tous': 'tous',
    'tout': 'tous',
    'toute': 'tous',
    'tout le monde': 'tous',
    'enseignants': 'enseignants',
    'enseignant': 'enseignants',
    'professeurs': 'enseignants',
    'professeur': 'enseignants',
    'profs': 'enseignants',
    'prof': 'enseignants',
    'parents': 'parents',
    'parent': 'parents',
    'eleves': 'eleves',
    'eleve': 'eleves',
    'élève': 'eleves',
    'élèves': 'eleves',
    'etudiants': 'eleves',
    'etudiant': 'eleves',
    'étudiants': 'eleves',
    'étudiant': 'eleves',
    'personnel': 'personnel_administratif',
    'personnel administratif': 'personnel_administratif',
    'administratif': 'personnel_administratif',
    'admin': 'personnel_administratif',
}


@dataclass
class AssistantContext:
    etablissement: object
    annee_scolaire: object
    est_superieur: bool
    est_primaire: bool
    libelle_eleve: str
    personnel: object = None


def build_assistant_context(etablissement, session_store=None, personnel=None):
    """Construit le contexte établissement + session consultée."""
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    annee = None
    session_id = None
    if session_store is not None:
        session_id = session_store.get('annee_scolaire_consultee_id')
    if session_id:
        annee = AnneeScolaire.objects.filter(
            pk=session_id,
            etablissement=etablissement,
        ).first()
    if annee is None:
        annee = AnneeScolaire.get_session_active(etablissement)

    type_etab = (etablissement.type_etablissement or '').lower()
    est_superieur = type_etab == 'superieur'
    est_primaire = type_etab == 'primary'
    return AssistantContext(
        etablissement=etablissement,
        annee_scolaire=annee,
        est_superieur=est_superieur,
        est_primaire=est_primaire,
        libelle_eleve='étudiant' if est_superieur else 'élève',
        personnel=personnel,
    )


def context_snapshot(ctx):
    """Résumé court injecté dans le system prompt."""
    etab = ctx.etablissement
    return {
        'nom': etab.nom,
        'code': etab.code_etablissement,
        'type': etab.type_etablissement,
        'ville': etab.ville,
        'pays': etab.pays,
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'libelle_apprenant': ctx.libelle_eleve,
        'est_superieur': ctx.est_superieur,
        'est_primaire': ctx.est_primaire,
    }


def _inscrits_ids(ctx):
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    if not ctx.annee_scolaire:
        return None
    return list(
        InscriptionEleve.objects.filter(
            annee_scolaire=ctx.annee_scolaire,
            etablissement=ctx.etablissement,
            eleve_id__isnull=False,
        ).values_list('eleve_id', flat=True)
    )


def _eleves_qs(ctx):
    from school_admin.model.eleve_model import Eleve

    qs = Eleve.objects.filter(etablissement=ctx.etablissement, actif=True)
    ids = _inscrits_ids(ctx)
    if ids is not None:
        qs = qs.filter(id__in=ids)
    return qs


def _find_eleve(ctx, query):
    from school_admin.model.eleve_model import Eleve

    if not query:
        return None
    qs = _eleves_qs(ctx).select_related('classe')
    q = query.strip()
    found = qs.filter(
        Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(matricule_eleve__icontains=q)
    ).first()
    if found:
        return found
    return Eleve.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
    ).filter(
        Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(matricule_eleve__icontains=q)
    ).select_related('classe').first()


def _find_classe(ctx, query):
    from school_admin.services.assistant_search import find_classe

    return find_classe(ctx, query)


def _safe_decimal(value):
    if value is None:
        return None
    return float(value)


def _count_by_sexe(qs):
    return qs.aggregate(
        total=Count('id'),
        filles=Count('id', filter=Q(sexe='F')),
        garcons=Count('id', filter=Q(sexe='M')),
        non_renseigne=Count('id', filter=~Q(sexe__in=['F', 'M'])),
    )


def tool_effectifs(ctx, args):
    from school_admin.model.classe_model import Classe
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur

    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, (args.get('classe') or args.get('query') or '').strip())
    eleves = _eleves_qs(ctx)
    if classe:
        eleves = eleves.filter(classe=classe)
    sexes = _count_by_sexe(eleves)

    classes = Classe.objects.filter(etablissement=ctx.etablissement, actif=True)
    par_classe = []
    if classe:
        par_classe.append({
            'nom': classe.nom,
            'niveau': classe.get_niveau_display(),
            'effectif': sexes['total'],
            'filles': sexes['filles'],
            'garcons': sexes['garcons'],
        })
    else:
        rows = (
            eleves.filter(classe_id__isnull=False)
            .values('classe__nom', 'classe__niveau')
            .annotate(
                effectif=Count('id'),
                filles=Count('id', filter=Q(sexe='F')),
                garcons=Count('id', filter=Q(sexe='M')),
            )
            .order_by('classe__niveau', 'classe__nom')[:30]
        )
        for row in rows:
            par_classe.append({
                'nom': row['classe__nom'],
                'effectif': row['effectif'],
                'filles': row['filles'],
                'garcons': row['garcons'],
            })

    return {
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'perimetre': classe.nom if classe else 'etablissement',
        'nb_eleves_actifs': sexes['total'],
        'nb_filles': sexes['filles'],
        'nb_garcons': sexes['garcons'],
        'nb_sexe_non_renseigne': sexes['non_renseigne'],
        'nb_classes': classes.count(),
        'nb_professeurs': Professeur.objects.filter(
            etablissement=ctx.etablissement, actif=True
        ).count(),
        'nb_personnel': PersonnelAdministratif.objects.filter(
            etablissement=ctx.etablissement, actif=True
        ).count(),
        'classes': par_classe,
    }


def tool_rechercher_eleves(ctx, args):
    query = (args.get('query') or '').strip()
    classe_nom = (args.get('classe') or '').strip()
    qs = _eleves_qs(ctx).select_related('classe')
    if query:
        qs = qs.filter(
            Q(nom__icontains=query)
            | Q(prenom__icontains=query)
            | Q(matricule_eleve__icontains=query)
        )
    if classe_nom:
        qs = qs.filter(classe__nom__icontains=classe_nom)
    results = []
    for eleve in qs.order_by('nom', 'prenom')[:SEARCH_LIMIT]:
        results.append({
            'nom': eleve.nom_complet,
            'matricule': eleve.matricule_eleve,
            'classe': eleve.classe.nom if eleve.classe_id else None,
        })
    return {'nb_trouves': qs.count(), 'eleves': results}


def _classes_qs(ctx):
    from school_admin.model.classe_model import Classe

    return Classe.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
    ).select_related('department', 'academic_level')


def _classe_item(ctx, classe):
    item = {
        'id': classe.id,
        'nom': classe.nom,
        'niveau': classe.get_niveau_display(),
        'code': classe.code_classe,
        'effectif': _eleves_qs(ctx).filter(classe=classe).count(),
        'capacite_max': classe.capacite_max,
        'url': _classe_url(classe),
    }
    if ctx.est_superieur:
        item['niveau_lmd'] = classe.niveau_lmd or None
        if classe.department_id:
            item['departement'] = classe.department.nom
            item['sigle'] = classe.department.sigle or None
        extras = []
        if classe.niveau_lmd:
            extras.append(classe.niveau_lmd)
        if classe.department_id:
            extras.append(classe.department.sigle or classe.department.nom)
        if extras:
            item['libelle'] = f"{classe.nom} — {' '.join(extras)}"
        else:
            item['libelle'] = classe.nom
    item.setdefault('libelle', classe.nom)
    return item


def _classe_url(classe):
    from django.urls import reverse

    return reverse('administrateur_etablissement:detail_classe', args=[classe.id])


def list_classe_choices(ctx, limit=5):
    """Propose des classes cliquables quand l’utilisateur n’a pas précisé laquelle."""
    classes = list(_classes_qs(ctx).order_by('niveau', 'nom')[:limit])
    return [
        {
            'label': classe.nom,
            'value': f'Ouvre la classe {classe.nom}',
            'url': _classe_url(classe),
            'intent': 'open',
        }
        for classe in classes
    ]


def tool_rechercher_classes(ctx, args):
    from school_admin.services.assistant_search import search_classes

    query = (args.get('query') or '').strip()
    if query:
        result = search_classes(ctx, query, limit=SEARCH_LIMIT)
        items = result.get('classes') or []
        if result.get('statut') == 'ok':
            items = [{
                key: result[key]
                for key in (
                    'id', 'nom', 'niveau', 'code', 'effectif',
                    'capacite_max', 'url', 'niveau_lmd',
                    'departement', 'sigle', 'libelle',
                )
                if key in result
            }]
        return {
            'classes': items,
            'trouve': bool(items),
            'query_normalisee': result.get('query_normalisee'),
            'suggestions_possibles': result.get('suggestions_possibles') or items,
        }
    items = [_classe_item(ctx, classe) for classe in _classes_qs(ctx).order_by('niveau', 'nom')[:SEARCH_LIMIT]]
    return {'classes': items}


def _normalize_class_query(query):
    text = (query or '').strip()
    text = re.sub(r'(\d+)\s*(?:e|è|eme|ème)\b', r'\1ème', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    return text


def tool_ouvrir_classe(ctx, args):
    """Trouve une classe et renvoie l’URL de sa fiche pour navigation."""
    from school_admin.services.assistant_search import search_classes

    query = (args.get('query') or args.get('classe') or '').strip()
    result = search_classes(ctx, query)
    if result.get('statut') == 'ok':
        ouvrir = args.get('ouvrir')
        if ouvrir is None:
            ouvrir = True
        result['ouvrir'] = bool(ouvrir)
        result['titre'] = result.get('nom')
        return result
    return result


def tool_rechercher_professeurs(ctx, args):
    from school_admin.model.professeur_model import Professeur

    query = (args.get('query') or '').strip()
    qs = Professeur.objects.filter(
        etablissement=ctx.etablissement, actif=True
    ).select_related('matiere_principale')
    if query:
        qs = qs.filter(
            Q(nom__icontains=query)
            | Q(prenom__icontains=query)
            | Q(numero_employe__icontains=query)
        )
    items = []
    for prof in qs.order_by('nom', 'prenom')[:SEARCH_LIMIT]:
        items.append({
            'nom': f'{prof.prenom} {prof.nom}',
            'matiere': prof.matiere_principale.nom if prof.matiere_principale_id else None,
            'telephone': prof.telephone,
        })
    return {'professeurs': items}


def tool_rechercher_personnel(ctx, args):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif

    query = (args.get('query') or '').strip()
    qs = PersonnelAdministratif.objects.filter(
        etablissement=ctx.etablissement, actif=True
    )
    if query:
        qs = qs.filter(Q(nom__icontains=query) | Q(prenom__icontains=query))
    items = [
        {
            'nom': f'{p.prenom} {p.nom}',
            'fonction': p.get_fonction_display(),
        }
        for p in qs.order_by('nom', 'prenom')[:SEARCH_LIMIT]
    ]
    return {'personnel': items}


def tool_notes_eleve(ctx, args):
    query = (args.get('query') or '').strip()
    eleve = _find_eleve(ctx, query)
    if not eleve:
        return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}

    notes = []
    if ctx.est_primaire:
        from school_admin.model.note_primaire_model import NotePrimaire

        qs = NotePrimaire.objects.filter(
            eleve=eleve,
            statut_publication=NotePrimaire.STATUT_PUBLIEE,
        ).select_related('evaluation_primaire', 'evaluation_primaire__matiere')
        if ctx.annee_scolaire:
            qs = qs.filter(
                Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
            )
        for note in qs.order_by('-id')[:NOTES_LIMIT]:
            evaluation = note.evaluation_primaire
            notes.append({
                'matiere': evaluation.matiere.nom if evaluation and evaluation.matiere_id else None,
                'evaluation': evaluation.titre if evaluation else None,
                'note': _safe_decimal(note.note),
            })
    else:
        from school_admin.model.evaluation_model import Note

        qs = Note.objects.filter(
            eleve=eleve,
            statut_publication=Note.STATUT_PUBLIEE,
            evaluation__classe__etablissement=ctx.etablissement,
        ).select_related('evaluation', 'evaluation__matiere', 'matiere')
        if ctx.annee_scolaire:
            qs = qs.filter(
                Q(evaluation__annee_scolaire=ctx.annee_scolaire)
                | Q(evaluation__annee_scolaire__isnull=True)
            )
        for note in qs.order_by('-id')[:NOTES_LIMIT]:
            matiere = note.matiere or (note.evaluation.matiere if note.evaluation_id else None)
            notes.append({
                'matiere': matiere.nom if matiere else None,
                'evaluation': note.evaluation.titre if note.evaluation_id else None,
                'note': _safe_decimal(note.note),
                'bareme': _safe_decimal(note.evaluation.bareme) if note.evaluation_id else 20,
            })

    moyennes = []
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    moy_qs = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=ctx.etablissement,
        est_moyenne_generale=True,
    ).select_related('periode')
    if ctx.annee_scolaire:
        moy_qs = moy_qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    for moy in moy_qs.order_by('-id')[:6]:
        moyennes.append({
            'periode': moy.periode.nom_periode if moy.periode_id else None,
            'moyenne': _safe_decimal(moy.moyenne_generale),
            'rang': moy.rang,
        })

    return {
        'eleve': eleve.nom_complet,
        'classe': eleve.classe.nom if eleve.classe_id else None,
        'notes': notes,
        'moyennes_periode': moyennes,
    }


def tool_emploi_du_temps(ctx, args):
    from school_admin.model.emploi_du_temps_model import EmploiDuTemps

    classe = _find_classe(ctx, args.get('classe') or '')
    if not classe:
        return {'erreur': 'Classe introuvable. Précisez le nom exact de la classe.'}

    qs = EmploiDuTemps.objects.filter(classe=classe, est_actif=True)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire_fk=ctx.annee_scolaire)
            | Q(annee_scolaire=ctx.annee_scolaire.libelle)
        )
    emploi = qs.order_by('-date_modification').first()
    if not emploi:
        return {'classe': classe.nom, 'emploi': None, 'message': 'Aucun emploi du temps actif.'}

    creneaux = []
    for creneau in emploi.creneaux.select_related('matiere', 'professeur', 'salle').order_by(
        'jour', 'heure_debut'
    )[:40]:
        creneaux.append({
            'jour': creneau.get_jour_display(),
            'debut': creneau.heure_debut.strftime('%H:%M') if creneau.heure_debut else None,
            'fin': creneau.heure_fin.strftime('%H:%M') if creneau.heure_fin else None,
            'matiere': creneau.matiere.nom if creneau.matiere_id else None,
            'professeur': (
                f'{creneau.professeur.prenom} {creneau.professeur.nom}'
                if creneau.professeur_id else None
            ),
            'salle': creneau.salle.nom if creneau.salle_id else None,
        })
    return {
        'classe': classe.nom,
        'statut': emploi.get_statut_publication_display(),
        'creneaux': creneaux,
    }


def tool_presences(ctx, args):
    from school_admin.model.presence_model import Presence

    jours = int(args.get('jours') or 7)
    jours = max(1, min(jours, 31))
    since = timezone.now().date() - timedelta(days=jours)
    qs = Presence.objects.filter(etablissement=ctx.etablissement, date__gte=since)
    query = (args.get('query') or '').strip()
    if query:
        eleve = _find_eleve(ctx, query)
        if not eleve:
            return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}
        qs = qs.filter(eleve=eleve)
        details = [
            {
                'date': p.date.isoformat(),
                'statut': p.get_statut_display(),
                'classe': p.classe.nom if p.classe_id else None,
            }
            for p in qs.select_related('classe').order_by('-date')[:20]
        ]
        return {
            'eleve': eleve.nom_complet,
            'periode_jours': jours,
            'details': details,
        }

    stats = list(qs.values('statut').annotate(nb=Count('id')))
    return {
        'periode_jours': jours,
        'totaux': {row['statut']: row['nb'] for row in stats},
        'nb_enregistrements': qs.count(),
    }


def tool_annonces(ctx, _args):
    from school_admin.model.annonce_model import Annonce

    qs = Annonce.objects.filter(
        etablissement=ctx.etablissement,
        statut='publiee',
    )
    if ctx.annee_scolaire:
        qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
    items = [
        {
            'titre': a.titre,
            'date': a.date_publication.isoformat() if a.date_publication else None,
            'destinataires': a.destinataires,
        }
        for a in qs.order_by('-date_publication', '-date_creation')[:8]
    ]
    return {'annonces': items}


def _normalize_destinataires(raw):
    if raw is None or raw == '':
        return ['tous']
    if isinstance(raw, str):
        pieces = [part.strip() for part in re.split(r'[,;/]| et ', raw) if part.strip()]
    elif isinstance(raw, (list, tuple)):
        pieces = [str(part).strip() for part in raw if str(part).strip()]
    else:
        pieces = []

    result = []
    for item in pieces:
        key = DESTINATAIRE_ALIASES.get(item.lower(), item.lower())
        if key in DESTINATAIRE_VALIDES and key not in result:
            result.append(key)
    if 'tous' in result:
        return ['tous']
    return result or ['tous']


def _destinataires_libelle(codes):
    from school_admin.model.annonce_model import Annonce

    labels = dict(Annonce.DESTINATAIRES_CHOICES)
    if 'tous' in codes:
        return labels['tous']
    return ', '.join(labels.get(code, code) for code in codes)


def _prepare_annonce_draft(ctx, args):
    titre = (args.get('titre') or '').strip()
    contenu = (args.get('contenu') or '').strip()
    if not contenu:
        return {'erreur': 'Le contenu de l’annonce est obligatoire.'}
    if len(contenu) > ANNONCE_CONTENU_MAX:
        return {
            'erreur': f'Le contenu est trop long ({ANNONCE_CONTENU_MAX} caractères maximum).',
        }
    if not titre:
        titre = contenu[:80]
        if len(contenu) > 80:
            titre = titre.rsplit(' ', 1)[0] or titre
    titre = titre[:255]
    destinataires = _normalize_destinataires(args.get('destinataires'))
    publier = args.get('publier')
    if publier is None:
        publier = True
    return {
        'statut': 'en_attente_confirmation',
        'action': 'creer_publier_annonce',
        'titre': titre,
        'contenu': contenu,
        'destinataires': destinataires,
        'destinataires_libelle': _destinataires_libelle(destinataires),
        'publier': bool(publier),
        'message': (
            'Rien n’a encore été créé. Lis ce brouillon à voix haute et demande '
            'une confirmation explicite avant publication.'
        ),
    }


def tool_creer_publier_annonce(ctx, args):
    """Prépare une annonce. L’écriture réelle n’a lieu qu’après confirmation."""
    return _prepare_annonce_draft(ctx, args)


def apply_annonce_draft(ctx, draft):
    """Crée l’annonce (même logique que le formulaire directeur)."""
    from school_admin.model.annonce_model import Annonce

    titre = (draft.get('titre') or '').strip()
    contenu = (draft.get('contenu') or '').strip()
    if not titre or not contenu:
        return {'erreur': 'Titre et contenu sont obligatoires.'}

    destinataires = _normalize_destinataires(draft.get('destinataires'))
    annonce = Annonce.objects.create(
        etablissement=ctx.etablissement,
        auteur_directeur=ctx.etablissement,
        auteur_personnel=ctx.personnel,
        titre=titre,
        contenu=contenu,
        destinataires=destinataires,
        statut='brouillon',
        annee_scolaire=ctx.annee_scolaire,
    )
    if draft.get('publier', True):
        annonce.publier()

    logger.info(
        "Assistant: annonce %s id=%s etab=%s",
        annonce.statut,
        annonce.id,
        ctx.etablissement.pk,
    )
    from django.urls import reverse

    return {
        'statut': 'ok',
        'id': annonce.id,
        'titre': annonce.titre,
        'publiee': annonce.statut == 'publiee',
        'destinataires': destinataires,
        'destinataires_libelle': annonce.get_destinataires_display(),
        'url': reverse('directeur:apercu_annonce', args=[annonce.id]),
    }


def tool_periodes(ctx, _args):
    from school_admin.model.periode_model import PeriodeScolaire

    periode_active = PeriodeScolaire.get_periode_active(ctx.etablissement)
    qs = PeriodeScolaire.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire_fk=ctx.annee_scolaire)
            | Q(annee_scolaire=ctx.annee_scolaire.libelle)
        )
    items = [
        {
            'nom': p.nom_periode,
            'type': p.get_type_periode_display(),
            'debut': p.date_debut.isoformat() if p.date_debut else None,
            'fin': p.date_fin.isoformat() if p.date_fin else None,
            'active': bool(periode_active and p.pk == periode_active.pk),
        }
        for p in qs.order_by('date_debut')[:16]
    ]
    return {
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'periode_active': periode_active.nom_periode if periode_active else None,
        'periodes': items,
    }


def tool_comptabilite(ctx, args):
    from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve

    query = (args.get('query') or '').strip()
    qs = ComptabiliteEleve.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)

    if query:
        eleve = _find_eleve(ctx, query)
        if not eleve:
            return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}
        fiche = qs.filter(eleve=eleve).first()
        if not fiche:
            return {
                'eleve': eleve.nom_complet,
                'message': 'Aucune fiche de comptabilité pour cette session.',
            }
        total_du = fiche.calculer_total_du()
        total_paye = fiche.calculer_total_paye()
        annexes = []
        for frais in fiche.frais_annexes.all():
            annexes.append({
                'id': frais.id,
                'code': frais.code,
                'libelle': frais.libelle,
                'montant': _safe_decimal(frais.montant),
                'paye': _safe_decimal(frais.montant_paye),
                'reste': _safe_decimal(frais.get_reste_a_payer()),
                'statut': frais.get_statut_display(),
                'periodicite': frais.get_periodicite_display(),
            })
        return {
            'eleve': eleve.nom_complet,
            'statut': fiche.get_statut_paiement_display(),
            'total_du': _safe_decimal(total_du),
            'total_paye': _safe_decimal(total_paye),
            'reste': _safe_decimal(total_du - total_paye),
            'frais_annexes': annexes,
        }

    impayes = qs.filter(statut_paiement__in=['en_retard', 'impaye']).select_related('eleve')
    items = []
    for fiche in impayes.order_by('statut_paiement')[:SEARCH_LIMIT]:
        total_du = fiche.calculer_total_du()
        total_paye = fiche.calculer_total_paye()
        items.append({
            'eleve': fiche.eleve.nom_complet,
            'statut': fiche.get_statut_paiement_display(),
            'reste': _safe_decimal(total_du - total_paye),
        })
    return {
        'nb_a_jour': qs.filter(statut_paiement='a_jour').count(),
        'nb_en_retard': qs.filter(statut_paiement='en_retard').count(),
        'nb_impaye': qs.filter(statut_paiement='impaye').count(),
        'impayes': items,
    }


def tool_structure_superieur(ctx, args):
    if not ctx.est_superieur:
        return {'erreur': 'Cet établissement n’est pas un établissement supérieur.'}

    from school_admin.model.academic_structure_model import Department
    from school_admin.model.module_model import Module

    query = (args.get('query') or '').strip()
    deps = Department.objects.filter(etablissement=ctx.etablissement)
    modules = Module.objects.filter(etablissement=ctx.etablissement)
    if query:
        deps = deps.filter(Q(nom__icontains=query) | Q(sigle__icontains=query))
        modules = modules.filter(Q(nom__icontains=query) | Q(code__icontains=query))

    return {
        'departements': [
            {'nom': d.nom, 'sigle': d.sigle or None}
            for d in deps.order_by('ordre', 'nom')[:20]
        ],
        'modules': [
            {'nom': m.nom, 'code': m.code}
            for m in modules.order_by('nom')[:20]
        ],
    }


def tool_chercher_en_base(ctx, args):
    """Cherche une donnée scolaire en base quand elle n'est pas déjà connue."""
    args = args if isinstance(args, dict) else {}
    question = (args.get('question') or args.get('query') or '').strip()
    lowered = question.lower()
    payload = {
        'query': question,
        'classe': (args.get('classe') or '').strip(),
    }

    if any(
        token in lowered
        for token in (
            'fille', 'garçon', 'garcon', 'sexe', 'féminin', 'feminin',
            'masculin', 'genre', 'effectif', 'inscrit',
        )
    ):
        found = tool_effectifs(ctx, payload)
        return {'trouve': True, 'source': 'effectifs', **found}
    if any(token in lowered for token in ('note', 'moyenne', 'bulletin', 'résultat', 'resultat')):
        found = tool_notes_eleve(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'notes', **found}
    if any(token in lowered for token in ('absence', 'présent', 'present', 'présence', 'presence')):
        found = tool_presences(ctx, payload)
        return {'trouve': True, 'source': 'presences', **found}
    if any(token in lowered for token in ('paiement', 'impay', 'frais', 'scolarité', 'scolarite', 'dette')):
        found = tool_comptabilite(ctx, payload)
        return {'trouve': True, 'source': 'comptabilite', **found}
    if any(token in lowered for token in ('emploi du temps', 'edt', 'cours du')):
        found = tool_emploi_du_temps(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'emploi', **found}
    if any(token in lowered for token in ('période', 'periode', 'semestre', 'trimestre')):
        found = tool_periodes(ctx, payload)
        return {'trouve': True, 'source': 'periodes', **found}
    if any(token in lowered for token in ('annonce',)):
        found = tool_annonces(ctx, payload)
        return {'trouve': True, 'source': 'annonces', **found}
    if any(token in lowered for token in ('département', 'departement', 'module', 'spécialité', 'specialite')):
        found = tool_structure_superieur(ctx, payload)
        return {'trouve': True, 'source': 'structure', **found}
    if any(token in lowered for token in ('professeur', 'enseignant', 'prof ')):
        found = tool_rechercher_professeurs(ctx, payload)
        return {'trouve': bool(found.get('professeurs')), 'source': 'professeurs', **found}
    if any(token in lowered for token in ('personnel', 'secrétaire', 'secretaire')):
        found = tool_rechercher_personnel(ctx, payload)
        return {'trouve': bool(found.get('personnel')), 'source': 'personnel', **found}
    if any(token in lowered for token in ('classe', 'promotion', 'filière', 'filiere')):
        found = tool_rechercher_classes(ctx, payload)
        return {'trouve': bool(found.get('classes')), 'source': 'classes', **found}
    if any(token in lowered for token in ('élève', 'eleve', 'étudiant', 'etudiant', 'matricule')):
        found = tool_rechercher_eleves(ctx, payload)
        return {'trouve': bool(found.get('eleves')), 'source': 'eleves', **found}

    found = tool_effectifs(ctx, payload)
    return {
        'trouve': True,
        'source': 'effectifs',
        'precision': (
            "Recherche générale : voici les effectifs. "
            "Reformule si tu visais une autre donnée."
        ),
        **found,
    }


def tool_lister_pages(_ctx, _args):
    from school_admin.services.assistant_pages import list_pages

    return {
        'pages': [
            {'key': page['key'], 'titre': page['titre']}
            for page in list_pages()
        ],
    }


def tool_ouvrir_page(_ctx, args):
    from school_admin.services.assistant_pages import find_page, related_pages

    page = find_page(args.get('page_key') or args.get('query'))
    if not page:
        return {
            'erreur': 'Page inconnue. Utilise lister_pages pour voir les clés valides.',
        }
    ouvrir = args.get('ouvrir')
    if ouvrir is None:
        ouvrir = True
    return {
        'statut': 'ok',
        'key': page['key'],
        'titre': page['titre'],
        'url': page['url'],
        'ouvrir': bool(ouvrir),
        'suggestions': related_pages(page['key']),
    }


TOOL_HANDLERS = {
    'chercher_en_base': tool_chercher_en_base,
    'get_effectifs': tool_effectifs,
    'rechercher_eleves': tool_rechercher_eleves,
    'rechercher_classes': tool_rechercher_classes,
    'ouvrir_classe': tool_ouvrir_classe,
    'rechercher_professeurs': tool_rechercher_professeurs,
    'rechercher_personnel': tool_rechercher_personnel,
    'get_notes_eleve': tool_notes_eleve,
    'get_emploi_du_temps': tool_emploi_du_temps,
    'get_presences': tool_presences,
    'get_annonces': tool_annonces,
    'creer_publier_annonce': tool_creer_publier_annonce,
    'get_periodes': tool_periodes,
    'get_comptabilite': tool_comptabilite,
    'get_structure_superieur': tool_structure_superieur,
    'lister_pages': tool_lister_pages,
    'ouvrir_page': tool_ouvrir_page,
}

from school_admin.services.assistant_emploi import (  # noqa: E402
    tool_ajouter_creneau_emploi,
    tool_creer_emploi_du_temps,
)

TOOL_HANDLERS['creer_emploi_du_temps'] = tool_creer_emploi_du_temps
TOOL_HANDLERS['ajouter_creneau_emploi'] = tool_ajouter_creneau_emploi

from school_admin.services.assistant_actions import (  # noqa: E402
    tool_creer_parametres_comptabilite,
    tool_enregistrer_paiement,
    tool_get_parametres_comptabilite,
    tool_modifier_parametres_comptabilite,
    tool_supprimer_parametres_comptabilite,
)

TOOL_HANDLERS['get_parametres_comptabilite'] = tool_get_parametres_comptabilite
TOOL_HANDLERS['creer_parametres_comptabilite'] = tool_creer_parametres_comptabilite
TOOL_HANDLERS['modifier_parametres_comptabilite'] = tool_modifier_parametres_comptabilite
TOOL_HANDLERS['supprimer_parametres_comptabilite'] = tool_supprimer_parametres_comptabilite
TOOL_HANDLERS['enregistrer_paiement'] = tool_enregistrer_paiement


TOOLS_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'chercher_en_base',
            'description': (
                'Cherche une donnée scolaire en base quand elle n’est pas déjà connue. '
                'À appeler dès qu’une question porte sur des chiffres, des listes ou '
                'un détail (filles, garçons, élèves, notes, absences, classes, etc.). '
                'Si la donnée existe, elle est renvoyée. Sinon trouve=false.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'question': {
                        'type': 'string',
                        'description': 'La question ou la donnée à chercher',
                    },
                    'classe': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                },
                'required': ['question'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_effectifs',
            'description': (
                'Effectifs de l’établissement ou d’une classe : nombre d’élèves, '
                'filles (sexe F), garçons (sexe M), classes, professeurs, personnel, '
                'et répartition par classe. À utiliser pour toute question sur '
                'les filles, les garçons ou le sexe des inscrits.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_eleves',
            'description': 'Recherche des élèves ou étudiants par nom, prénom, matricule ou classe.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom, prénom ou matricule'},
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_classes',
            'description': 'Liste ou recherche les classes / promotions.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_professeurs',
            'description': 'Recherche des professeurs par nom.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_personnel',
            'description': 'Recherche du personnel administratif.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_notes_eleve',
            'description': 'Notes publiées et moyennes de période d’un élève ou étudiant.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Nom, prénom ou matricule',
                    },
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_emploi_du_temps',
            'description': 'Emploi du temps actif d’une classe.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'creer_emploi_du_temps',
            'description': (
                'Prépare la création de l’emploi du temps d’une classe. '
                'Ne crée rien tout de suite : une confirmation est obligatoire. '
                'À utiliser quand le directeur demande de créer un emploi du temps.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                    'notes': {
                        'type': 'string',
                        'description': 'Note optionnelle sur l’emploi du temps',
                    },
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ajouter_creneau_emploi',
            'description': (
                'Prépare un créneau (cours) dans l’emploi du temps d’une classe. '
                'Ne l’enregistre pas tout de suite : une confirmation est obligatoire. '
                'Si l’emploi du temps n’existe pas encore, il sera créé après confirmation. '
                'Jours : lundi à samedi. Heures au format HH:MM.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                    'jour': {
                        'type': 'string',
                        'enum': [
                            'lundi',
                            'mardi',
                            'mercredi',
                            'jeudi',
                            'vendredi',
                            'samedi',
                            'dimanche',
                        ],
                    },
                    'heure_debut': {
                        'type': 'string',
                        'description': 'Heure de début, ex. 08:00',
                    },
                    'heure_fin': {
                        'type': 'string',
                        'description': 'Heure de fin, ex. 10:00',
                    },
                    'matiere': {'type': 'string', 'description': 'Nom de la matière'},
                    'professeur': {'type': 'string', 'description': 'Nom du professeur'},
                    'salle': {'type': 'string', 'description': 'Nom ou numéro de salle'},
                    'type_cours': {
                        'type': 'string',
                        'enum': [
                            'cours',
                            'td',
                            'tp',
                            'controle',
                            'examen',
                            'sport',
                            'pause',
                            'autre',
                        ],
                    },
                    'notes': {'type': 'string'},
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_presences',
            'description': (
                'Présences / absences récentes. Avec query : détail d’un élève. '
                'Sans query : totaux de l’établissement.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'jours': {'type': 'integer', 'description': 'Nombre de jours (1-31), défaut 7'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_annonces',
            'description': 'Annonces publiées récemment.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'creer_publier_annonce',
            'description': (
                'Prépare une annonce officielle (titre, contenu, destinataires). '
                'Ne crée rien tout de suite : une confirmation du directeur est obligatoire. '
                'À utiliser quand le directeur demande de créer, rédiger ou publier une annonce.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'titre': {
                        'type': 'string',
                        'description': 'Titre court de l’annonce',
                    },
                    'contenu': {
                        'type': 'string',
                        'description': 'Texte complet de l’annonce',
                    },
                    'destinataires': {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'enum': [
                                'tous',
                                'enseignants',
                                'parents',
                                'eleves',
                                'personnel_administratif',
                            ],
                        },
                        'description': 'Public visé. Défaut : tous.',
                    },
                    'publier': {
                        'type': 'boolean',
                        'description': (
                            'true pour publier après confirmation, '
                            'false pour un brouillon. Défaut : true.'
                        ),
                    },
                },
                'required': ['contenu'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_periodes',
            'description': 'Périodes scolaires (trimestres / semestres) et période active.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_comptabilite',
            'description': (
                'Comptabilité élèves : inscription, mensualités et frais annexes '
                '(tenue, carte, assurance…). Avec query : fiche d’un élève. '
                'Sans query : résumé des impayés.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_parametres_comptabilite',
            'description': (
                'Lit les paramètres de scolarité par groupe de classes, '
                'y compris les frais annexes (tenue, carte, dossier, assurance, '
                'examen, transport, cantine, apport, autres).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Nom du jeu ou groupe de classes (ex. 6e, CE1)',
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'creer_parametres_comptabilite',
            'description': (
                'Prépare un jeu de paramètres de scolarité (montants + frais annexes). '
                'Ne crée rien tout de suite : une confirmation est obligatoire.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'nom': {'type': 'string'},
                    'groupes_classes': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Groupes concernés, ex. ["6e", "5e"]',
                    },
                    'montant_frais_inscription': {'type': 'number'},
                    'montant_mensualite': {'type': 'number'},
                    'montant_frais_reinscription': {'type': 'number'},
                    'type_facturation': {
                        'type': 'string',
                        'enum': ['mensuel', 'annuel'],
                    },
                    'frais_annexes': {
                        'type': 'array',
                        'description': (
                            'Liste de frais : code (tenue, carte_scolaire, dossier, '
                            'assurance, examen, transport, cantine, apport, autre), '
                            'montant, actif, periodicite (inscription|annuel|ponctuel), libelle.'
                        ),
                        'items': {
                            'type': 'object',
                            'properties': {
                                'code': {'type': 'string'},
                                'libelle': {'type': 'string'},
                                'montant': {'type': 'number'},
                                'actif': {'type': 'boolean'},
                                'periodicite': {
                                    'type': 'string',
                                    'enum': ['inscription', 'annuel', 'ponctuel'],
                                },
                            },
                        },
                    },
                },
                'required': ['nom', 'groupes_classes'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'modifier_parametres_comptabilite',
            'description': (
                'Prépare une modification des paramètres (montants ou frais annexes). '
                'Confirmation obligatoire avant écriture.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'parametre_id': {'type': 'integer'},
                    'query': {'type': 'string'},
                    'nom': {'type': 'string'},
                    'groupes_classes': {
                        'type': 'array',
                        'items': {'type': 'string'},
                    },
                    'montant_frais_inscription': {'type': 'number'},
                    'montant_mensualite': {'type': 'number'},
                    'frais_annexes': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'code': {'type': 'string'},
                                'libelle': {'type': 'string'},
                                'montant': {'type': 'number'},
                                'actif': {'type': 'boolean'},
                                'periodicite': {
                                    'type': 'string',
                                    'enum': ['inscription', 'annuel', 'ponctuel'],
                                },
                            },
                        },
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'supprimer_parametres_comptabilite',
            'description': (
                'Prépare la suppression d’un jeu de paramètres. Confirmation obligatoire.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'parametre_id': {'type': 'integer'},
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'enregistrer_paiement',
            'description': (
                'Prépare l’enregistrement d’un paiement (inscription, mensualité '
                'ou frais annexe : tenue, carte, assurance…). Confirmation obligatoire.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve': {'type': 'string', 'description': 'Nom, prénom ou matricule'},
                    'query': {'type': 'string'},
                    'montant': {'type': 'number'},
                    'type_paiement': {
                        'type': 'string',
                        'enum': [
                            'frais_inscription',
                            'mensualite',
                            'frais_annexe',
                            'tenue',
                            'carte',
                            'assurance',
                        ],
                    },
                    'frais_annexe_code': {
                        'type': 'string',
                        'description': 'Code du frais annexe (tenue, carte_scolaire, ...)',
                    },
                    'periode': {'type': 'string', 'description': 'Période de mensualité'},
                    'mode_paiement': {'type': 'string'},
                },
                'required': ['montant'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_structure_superieur',
            'description': 'Départements (spécialités) et modules LMD. Uniquement en supérieur.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'lister_pages',
            'description': 'Liste les pages de l’espace directeur que tu peux ouvrir.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_classe',
            'description': (
                'Ouvre la fiche d’une classe précise (ex. 6e A, CF L1 A). '
                'À utiliser dès que le directeur demande d’ouvrir, afficher '
                'ou aller dans une classe nommée.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                    'ouvrir': {
                        'type': 'boolean',
                        'description': 'true pour ouvrir la fiche tout de suite',
                    },
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_page',
            'description': (
                'Ouvre une page de l’application (liste des classes, annonces, etc.). '
                'Pour une classe nommée, utilise ouvrir_classe. '
                'Clés : dashboard, etablissement, classes, salles, matieres, '
                'emplois_du_temps, pedagogie, professeurs, personnel, eleves, '
                'gestion_eleves, notes, presences, periodes, bulletins, annonces, '
                'creer_annonce, examens, emploi_examens, comptabilite, administration, '
                'convocations, certificats, preinscriptions, liaisons, notifications, '
                'profil, annees. '
                'Mettre ouvrir à true seulement si le directeur demande d’y aller.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'page_key': {
                        'type': 'string',
                        'description': 'Clé de la page, par exemple annonces ou eleves',
                    },
                    'ouvrir': {
                        'type': 'boolean',
                        'description': 'true pour ouvrir, false pour seulement suggérer',
                    },
                },
                'required': ['page_key'],
            },
        },
    },
]


def execute_tool(ctx, name, arguments):
    """Exécute un outil et renvoie un dict JSON-serializable."""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return {'erreur': f'Outil inconnu : {name}'}
    try:
        args = arguments if isinstance(arguments, dict) else {}
        return handler(ctx, args)
    except Exception:
        logger.exception("Erreur outil assistant %s", name)
        return {'erreur': f'Impossible d’exécuter {name} pour le moment.'}


def dumps_tool_result(payload):
    return json.dumps(payload, ensure_ascii=False, default=str)
