"""
Cahier de texte des enseignants (primaire, collège-lycée, supérieur).

* Les cours à renseigner viennent de l'emploi du temps publié (pas besoin du pointage).
* Une entrée = une séance : leçon, objectifs, déroulement, travail à faire.
* Aria peut rédiger l'entrée à partir de quelques notes de l'enseignant, en tenant
  compte du niveau de la classe et des leçons précédentes (progression).
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from school_admin.model.cahier_texte_model import CahierTexte

logger = logging.getLogger(__name__)
JOURS = ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')


def type_etablissement(etablissement):
    t = (getattr(etablissement, 'type_etablissement', '') or '').lower()
    if t in ('primaire', 'primary', 'ecole_primaire'):
        return 'primaire'
    if 'sup' in t or 'univ' in t:
        return 'superieur'
    return 'secondaire'


def libelles(etablissement):
    t = type_etablissement(etablissement)
    return {
        'type': t,
        'apprenants': 'étudiants' if t == 'superieur' else 'élèves',
        'seance': 'séance de cours' if t == 'superieur' else 'cours',
        'sous_titre': {
            'primaire': "Le journal de la classe : leçons du jour, activités et devoirs.",
            'superieur': "Le contenu de chaque séance, les objectifs et le travail personnel des étudiants.",
            'secondaire': "Ce qui a été fait à chaque cours et le travail donné aux élèves.",
        }[t],
    }


# --------------------------------------------------------------------------- cours à renseigner
def _heures(creneau):
    pe = creneau.periode_etablissement
    debut = creneau.heure_debut or (pe.heure_debut if pe else None)
    fin = creneau.heure_fin or (pe.heure_fin if pe else None)
    return debut, fin


def cours_du_professeur(professeur, du, au, annee_scolaire=None):
    """Cours de l'emploi du temps publié entre deux dates, avec l'entrée déjà saisie s'il y en a une."""
    from school_admin.services.pointage import creneaux_publies

    creneaux = [c for c in creneaux_publies(professeur.etablissement, annee_scolaire, professeur=professeur)
                if not (c.periode_etablissement and getattr(c.periode_etablissement, 'est_pause', False))]
    entrees = {(e.classe_id, e.date, e.heure_debut): e
               for e in CahierTexte.objects.filter(professeur=professeur, date__gte=du, date__lte=au)}
    cours = []
    jour = du
    while jour <= au:
        nom = JOURS[jour.weekday()]
        for c in creneaux:
            if c.jour != nom:
                continue
            debut, fin = _heures(c)
            classe = getattr(c.emploi_du_temps, 'classe', None)
            if not debut or classe is None:
                continue
            cours.append({'date': jour, 'debut': debut, 'fin': fin, 'classe': classe, 'matiere': c.matiere,
                          'entree': entrees.get((classe.id, jour, debut))})
        jour += timedelta(days=1)
    cours.sort(key=lambda x: (x['date'], x['debut']), reverse=True)
    return cours


def stats_professeur(professeur, annee_scolaire=None, jours=30):
    today = timezone.localdate()
    cours = [c for c in cours_du_professeur(professeur, today - timedelta(days=jours), today, annee_scolaire)
             if (c['date'], c['debut']) <= (today, timezone.localtime().time()) or c['date'] < today]
    faits = sum(1 for c in cours if c['entree'])
    return {
        'cours': len(cours), 'renseignes': faits, 'manquants': len(cours) - faits,
        'taux': round(faits / len(cours) * 100) if cours else None,
        'travaux': CahierTexte.objects.filter(professeur=professeur, date__gte=today - timedelta(days=jours))
        .exclude(travail_a_faire='').count(),
        'brouillons': CahierTexte.objects.filter(professeur=professeur, statut='brouillon').count(),
        'demandes': CahierTexte.objects.filter(professeur=professeur, demande_statut='en_attente').count(),
    }


# --------------------------------------------------------------------------- enregistrement
def _seance_liee(professeur, classe, jour, debut):
    from school_admin.model.pointage_model import SeanceCours

    if not debut:
        return None
    return SeanceCours.objects.filter(professeur=professeur, classe=classe, date=jour, heure_debut=debut).first()


def enregistrer(professeur, classe, jour, donnees, matiere=None, debut=None, fin=None, entree=None,
                annee_scolaire=None, redige_par_ia=False):
    """Crée ou met à jour une entrée. `donnees` : titre, objectifs, contenu, travail_a_faire, date_travail, …"""
    titre = (donnees.get('titre') or '').strip()
    contenu = (donnees.get('contenu') or '').strip()
    if not titre:
        raise ValueError("Indiquez la leçon ou le chapitre.")
    if not contenu:
        raise ValueError("Décrivez ce qui a été fait pendant la séance.")
    date_travail = donnees.get('date_travail') or None
    if isinstance(date_travail, str):
        try:
            date_travail = date.fromisoformat(date_travail[:10]) if date_travail else None
        except ValueError:
            date_travail = None
    if date_travail and date_travail < jour:
        raise ValueError("La date du travail à faire ne peut pas précéder la date du cours.")
    if entree is None:
        entree = CahierTexte.objects.filter(professeur=professeur, classe=classe, date=jour,
                                            heure_debut=debut).first()
        if entree is None:
            entree = CahierTexte(
            etablissement=professeur.etablissement, professeur=professeur, classe=classe, date=jour,
            heure_debut=debut, heure_fin=fin, annee_scolaire=annee_scolaire)
    if entree.pk and not entree.modifiable:
        raise ValueError(MESSAGE_VERROUILLE)
    entree.matiere = matiere or entree.matiere
    entree.titre = titre[:200]
    entree.objectifs = (donnees.get('objectifs') or '').strip()
    entree.contenu = contenu
    entree.travail_a_faire = (donnees.get('travail_a_faire') or '').strip()
    entree.date_travail = date_travail
    entree.observations = (donnees.get('observations') or '').strip()
    if donnees.get('statut') == 'valide':
        entree.statut = 'valide'
        entree.date_validation = timezone.now()
    else:
        entree.statut = 'brouillon'
    entree.redige_par_ia = entree.redige_par_ia or bool(redige_par_ia)
    seance = _seance_liee(professeur, classe, jour, entree.heure_debut)
    if seance and (entree.seance_id is None or entree.seance_id == seance.id):
        if not CahierTexte.objects.filter(seance=seance).exclude(pk=entree.pk).exists():
            entree.seance = seance
    entree.save()
    if entree.seance_id and not entree.seance.cahier_texte:
        # Le pointage considère le cahier de texte comme rempli.
        type(entree.seance).objects.filter(pk=entree.seance_id).update(cahier_texte=f"{entree.titre} — {entree.contenu}"[:2000])
    return entree


MESSAGE_VERROUILLE = ("Cette entrée est validée et envoyée à la direction : elle ne peut plus être modifiée. "
                      "Faites une demande de modification à la direction si vous devez corriger une erreur.")
AIDE_VALIDATION = (
    "Brouillon : vous pouvez modifier ou supprimer l'entrée autant que vous voulez ; elle n'est visible "
    "que par vous. Valider : l'entrée est envoyée à la direction et publiée pour les élèves et les parents ; "
    "elle ne peut plus être modifiée. En cas d'erreur, faites une demande de modification : si la direction "
    "l'accepte, l'entrée redevient un brouillon."
)


def valider(entree):
    if entree.statut == 'valide':
        raise ValueError("Cette entrée est déjà validée.")
    entree.statut = 'valide'
    entree.date_validation = timezone.now()
    entree.save(update_fields=['statut', 'date_validation', 'date_modification'])
    return entree


def supprimer(entree):
    if not entree.modifiable:
        raise ValueError(MESSAGE_VERROUILLE)
    entree.delete()


def demander_modification(entree, professeur, motif):
    if entree.professeur_id != professeur.id:
        raise ValueError("Cette entrée n'est pas la vôtre.")
    if entree.statut != 'valide':
        raise ValueError("Une entrée en brouillon se modifie directement.")
    if entree.demande_statut == 'en_attente':
        raise ValueError("Une demande est déjà en attente pour cette entrée.")
    motif = (motif or '').strip()
    if len(motif) < 10:
        raise ValueError("Expliquez en quelques mots ce qu'il faut corriger.")
    entree.demande_statut = 'en_attente'
    entree.demande_motif = motif[:2000]
    entree.demande_le = timezone.now()
    entree.demande_reponse = ''
    entree.save(update_fields=['demande_statut', 'demande_motif', 'demande_le', 'demande_reponse'])
    return entree


def traiter_demande(entree, user, accepter, reponse=''):
    """Acceptée : l'entrée redevient un brouillon modifiable. Refusée : elle reste validée."""
    if entree.demande_statut != 'en_attente':
        raise ValueError("Aucune demande en attente pour cette entrée.")
    from school_admin.services.pointage import _acteur

    entree.demande_statut = 'acceptee' if accepter else 'refusee'
    entree.demande_reponse = (reponse or '').strip()[:255]
    entree.demande_traitee_par = _acteur(user)[:120]
    entree.demande_traitee_le = timezone.now()
    champs = ['demande_statut', 'demande_reponse', 'demande_traitee_par', 'demande_traitee_le']
    if accepter:
        entree.statut = 'brouillon'
        entree.date_validation = None
        champs += ['statut', 'date_validation']
    entree.save(update_fields=champs)
    return entree


def entree_depuis_seance(seance):
    """Le texte saisi en terminant une séance devient une entrée du cahier (si aucune n'existe)."""
    texte = (seance.cahier_texte or '').strip()
    if not texte or CahierTexte.objects.filter(seance=seance).exists():
        return None
    titre, _, reste = texte.partition(' — ')
    return CahierTexte.objects.create(
        etablissement=seance.etablissement, annee_scolaire=seance.annee_scolaire, professeur=seance.professeur,
        classe=seance.classe, matiere=seance.matiere, seance=seance, date=seance.date,
        heure_debut=seance.heure_debut, heure_fin=seance.heure_fin,
        titre=(titre if reste else texte)[:200], contenu=reste or texte,
    )


# --------------------------------------------------------------------------- consultation
def entrees_classe(classe, matiere=None, publiees=True, limite=60):
    qs = CahierTexte.objects.filter(classe=classe).select_related('professeur', 'matiere')
    if matiere is not None:
        qs = qs.filter(matiere=matiere)
    if publiees:
        qs = qs.filter(statut='valide')
    return list(qs.order_by('-date', '-heure_debut')[:limite])


def precedentes(professeur, classe, matiere=None, avant=None, n=4):
    qs = CahierTexte.objects.filter(professeur=professeur, classe=classe)
    if matiere is not None:
        qs = qs.filter(matiere=matiere)
    if avant is not None:
        qs = qs.filter(date__lte=avant)
    return list(qs.order_by('-date', '-heure_debut')[:n])


# --------------------------------------------------------------------------- rédaction par Aria
CONSIGNE_IA = """Tu es Aria, assistante pédagogique d'un établissement scolaire au Sénégal.
Rédige l'entrée du cahier de texte d'une séance, en français clair, à la place de l'enseignant.
Règles :
- Appuie-toi d'abord sur les notes de l'enseignant ; n'invente pas de faits contraires.
- Respecte le niveau de la classe ({niveau}) et la matière ({matiere}). Programme officiel sénégalais si pertinent.
- Assure la continuité avec les leçons précédentes listées.
- Rédige toujours en français. Pour un cours de langue, seuls les exemples et le vocabulaire étudié peuvent être dans cette langue.
- Si les notes ne correspondent manifestement pas à la matière, suis quand même les notes de l'enseignant.
- Style sobre et professionnel, sans emoji, sans markdown (pas de **, pas de #).
- « contenu » : déroulement concret de la séance en 3 à 6 étapes courtes, une par ligne, commençant par « - ».
- « objectifs » : 2 à 4 objectifs, un par ligne, commençant par « - », formulés avec un verbe d'action.
- « travail_a_faire » : travail donné aux {apprenants} (exercices, leçon à apprendre) ou chaîne vide si rien n'est indiqué ni utile.
- « date_travail » : date ISO AAAA-MM-JJ si un travail est donné (prochaine séance ou date indiquée), sinon chaîne vide.
Réponds uniquement avec un objet JSON : {{"titre": "...", "objectifs": "...", "contenu": "...", "travail_a_faire": "...", "date_travail": "..."}}"""


def _niveau(classe):
    return getattr(classe, 'get_libelle_niveau_complet_pour_eleve', lambda: '')() or classe.nom


def construire_prompt(professeur, classe, matiere, jour, notes, duree_min=None):
    lib = libelles(professeur.etablissement)
    consigne = CONSIGNE_IA.format(niveau=_niveau(classe), matiere=getattr(matiere, 'nom', '') or 'non précisée',
                                  apprenants=lib['apprenants'])
    prec = precedentes(professeur, classe, matiere, avant=jour)
    histo = '\n'.join(f"- {e.date:%d/%m} : {e.titre}" + (f" (travail donné : {e.travail_a_faire[:80]})"
                                                         if e.travail_a_faire else '') for e in prec) or '- aucune'
    contexte = (
        f"Établissement : {professeur.etablissement.nom} ({lib['type']}).\n"
        f"Classe : {classe.nom} — niveau {_niveau(classe)}.\n"
        f"Matière : {getattr(matiere, 'nom', '') or 'non précisée'}.\n"
        f"Date de la séance : {jour:%A %d/%m/%Y}" + (f", durée {duree_min} minutes" if duree_min else '') + ".\n"
        f"Leçons précédentes (de la plus récente à la plus ancienne) :\n{histo}\n"
        f"Notes de l'enseignant : {notes.strip() or '(aucune : propose la suite logique de la progression)'}"
    )
    return consigne, contexte


def _nettoyer(texte):
    return '\n'.join(l.replace('**', '').replace('#', '').rstrip() for l in str(texte or '').strip().splitlines()).strip()


def rediger(professeur, classe, matiere, jour, notes='', duree_min=None):
    """Brouillon d'entrée rédigé par Gemini. Lève ValueError si le service n'est pas disponible."""
    if not getattr(settings, 'GEMINI_API_KEY', '') and not getattr(settings, 'GOOGLE_API_KEY', ''):
        raise ValueError("La rédaction par Aria n'est pas configurée (clé Gemini manquante).")
    consigne, contexte = construire_prompt(professeur, classe, matiere, jour, notes, duree_min)
    try:
        from google.genai import types

        from school_admin.services.gemini_context_cache import _get_native_client

        reponse = _get_native_client().models.generate_content(
            model=getattr(settings, 'GEMINI_MODEL', 'gemini-3.6-flash') or 'gemini-3.6-flash',
            contents=[contexte],
            config=types.GenerateContentConfig(
                system_instruction=consigne, temperature=0.5, response_mime_type='application/json',
                thinking_config=types.ThinkingConfig(thinking_level='low'),
            ),
        )
        data = json.loads(reponse.text or '{}')
    except Exception as exc:
        logger.exception("Rédaction du cahier de texte impossible")
        raise ValueError("Aria n'a pas pu rédiger pour le moment. Réessayez dans un instant.") from exc
    return interpreter(data, jour)


def interpreter(data, jour):
    """Nettoie la réponse du modèle et valide la date du travail."""
    if not isinstance(data, dict):
        data = {}
    date_travail = str(data.get('date_travail') or '').strip()[:10]
    try:
        if date_travail and date.fromisoformat(date_travail) < jour:
            date_travail = ''
    except ValueError:
        date_travail = ''
    resultat = {
        'titre': _nettoyer(data.get('titre'))[:200],
        'objectifs': _nettoyer(data.get('objectifs')),
        'contenu': _nettoyer(data.get('contenu')),
        'travail_a_faire': _nettoyer(data.get('travail_a_faire')),
        'date_travail': date_travail,
    }
    if not resultat['titre'] or not resultat['contenu']:
        raise ValueError("La proposition d'Aria est incomplète. Ajoutez quelques notes et réessayez.")
    return resultat


def profil_direction(professeur):
    """Section « Cahier de texte » de la fiche enseignant côté direction : entrées validées seulement."""
    today = timezone.localdate()
    entrees = list(CahierTexte.objects.filter(professeur=professeur, statut='valide')
                   .select_related('classe', 'matiere').order_by('-date', '-heure_debut'))
    classes = {e.classe_id: e.classe for e in entrees}
    try:
        taux = stats_professeur(professeur)['taux']
    except Exception:  # emploi du temps incomplet : la section reste lisible
        taux = None
    return {
        'entrees': entrees,
        'total': len(entrees),
        'mois': sum(1 for e in entrees if e.date >= today.replace(day=1)),
        'derniere': max((e.date_validation for e in entrees if e.date_validation), default=None),
        'taux': taux,
        'classes': sorted(classes.values(), key=lambda c: c.nom),
        'demandes': CahierTexte.objects.filter(professeur=professeur, demande_statut='en_attente').count(),
    }
