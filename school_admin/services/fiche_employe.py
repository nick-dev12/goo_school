"""
Fiche employé côté direction : rassemble en un seul endroit ce qui concerne un enseignant
(classes, emploi du temps, pointage et paie, cahier de texte, dossier RH) ou un membre du
personnel administratif, pour tous les types d'établissement.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

JOURS = ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')
JOURS_LIB = {'lundi': 'Lundi', 'mardi': 'Mardi', 'mercredi': 'Mercredi', 'jeudi': 'Jeudi',
             'vendredi': 'Vendredi', 'samedi': 'Samedi', 'dimanche': 'Dimanche'}

# Champs du dossier RH pris en compte dans le taux de complétude, groupés pour indiquer ce qui manque.
CHAMPS_DOSSIER = [
    ('date_naissance', 'Date de naissance'), ('lieu_naissance', 'Lieu de naissance'),
    ('nationalite', 'Nationalité'), ('adresse', 'Adresse'), ('numero_cni', "Pièce d'identité"),
    ('numero_cnss', 'N° CNSS'), ('type_contrat', 'Type de contrat'), ('diplome_plus_eleve', 'Diplôme'),
    ('banque', 'Banque'), ('numero_compte_bancaire', 'Compte bancaire'),
    ('contact_urgence_nom', "Contact d'urgence"), ('contact_urgence_telephone', "Téléphone d'urgence"),
]


def _minutes(debut, fin):
    if not debut or not fin:
        return 0
    return max((fin.hour * 60 + fin.minute) - (debut.hour * 60 + debut.minute), 0)


def anciennete(date_embauche, today=None):
    """« 3 ans et 2 mois », « 5 mois » ou « Moins d'un mois »."""
    if not date_embauche:
        return ''
    today = today or timezone.localdate()
    mois = (today.year - date_embauche.year) * 12 + today.month - date_embauche.month
    if today.day < date_embauche.day:
        mois -= 1
    if mois < 1:
        return "Moins d'un mois"
    ans, reste = divmod(mois, 12)
    parts = []
    if ans:
        parts.append(f"{ans} an{'s' if ans > 1 else ''}")
    if reste:
        parts.append(f"{reste} mois")
    return ' et '.join(parts)


def completude_dossier(employe, dossier, documents=()):
    """Pourcentage de complétude du dossier RH et liste de ce qui manque (coordonnées comprises)."""
    manquants = []
    if not getattr(employe, 'email', ''):
        manquants.append('Email')
    if not getattr(employe, 'date_embauche', None):
        manquants.append("Date d'embauche")
    if not getattr(employe, 'sexe', ''):
        manquants.append('Sexe')
    for champ, libelle in CHAMPS_DOSSIER:
        if not dossier or not getattr(dossier, champ, None):
            manquants.append(libelle)
    if not documents:
        manquants.append('Pièces justificatives')
    total = len(CHAMPS_DOSSIER) + 4
    return {'taux': round(100 * (total - len(manquants)) / total), 'manquants': manquants}


def echeance_contrat(dossier, today=None):
    """Fin de contrat RH : jours restants et niveau d'alerte (expiré, < 60 jours)."""
    fin = getattr(dossier, 'date_fin_contrat', None)
    if not fin:
        return None
    today = today or timezone.localdate()
    jours = (fin - today).days
    return {'fin': fin, 'jours': jours, 'expire': jours < 0, 'proche': 0 <= jours <= 60}


def _effectif(classe, cache):
    if classe.id not in cache:
        cache[classe.id] = classe.nombre_eleves
    return cache[classe.id]


def profil_enseignant(professeur, annee_scolaire=None):
    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.services import pointage as pt

    etab = professeur.etablissement
    type_etab = etab.type_etablissement
    today = timezone.localdate()
    effectifs = {}
    classes = {}

    def ligne(classe):
        if classe.id not in classes:
            classes[classe.id] = {'classe': classe, 'matieres': {}, 'minutes': 0, 'creneaux': 0,
                                  'statut': '', 'sources': set()}
        return classes[classe.id]

    # 1. Affectations officielles (secondaire / supérieur : une ligne par classe et matière).
    aff = AffectationProfesseur.objects.filter(professeur=professeur, actif=True).select_related('classe', 'matiere')
    if annee_scolaire is not None:
        aff = aff.filter(Q(annee_scolaire=annee_scolaire) | Q(annee_scolaire__isnull=True))
    for a in aff:
        if not a.classe_id:
            continue
        lg = ligne(a.classe)
        lg['sources'].add('affectation')
        if a.matiere_id:
            lg['matieres'][a.matiere_id] = a.matiere
        if a.statut and not lg['statut']:
            lg['statut'] = a.get_statut_display()

    # 2. Primaire : maître de classe et matières confiées.
    if type_etab == 'primary':
        from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

        for a in (AffectationProfesseurPrimaire.objects.filter(professeur=professeur, actif=True)
                  .select_related('classe').prefetch_related('matieres')):
            lg = ligne(a.classe)
            lg['sources'].add('affectation')
            lg['statut'] = a.get_statut_display()
            for m in a.matieres.all():
                lg['matieres'][m.id] = m

    # 3. Classes rattachées directement à la fiche.
    for c in professeur.classes.all():
        ligne(c)['sources'].add('fiche')

    # 4. Emploi du temps publié : heures réelles et matières effectivement enseignées.
    creneaux = list(pt.creneaux_publies(etab, annee_scolaire, professeur=professeur)
                    .order_by('heure_debut'))
    par_jour = {j: [] for j in JOURS}
    minutes_semaine = 0
    for cr in creneaux:
        classe = cr.emploi_du_temps.classe
        duree = _minutes(cr.heure_debut, cr.heure_fin)
        minutes_semaine += duree
        lg = ligne(classe)
        lg['sources'].add('edt')
        lg['minutes'] += duree
        lg['creneaux'] += 1
        if cr.matiere_id:
            lg['matieres'][cr.matiere_id] = cr.matiere
        if cr.jour in par_jour:
            par_jour[cr.jour].append({
                'debut': cr.heure_debut, 'fin': cr.heure_fin, 'classe': classe, 'matiere': cr.matiere,
                'salle': getattr(cr.salle, 'nom', '') if getattr(cr, 'salle_id', None) else '',
                'type': cr.get_type_cours_display() if hasattr(cr, 'get_type_cours_display') else '',
                'duree': duree,
            })

    lignes = []
    for lg in classes.values():
        lg['effectif'] = _effectif(lg['classe'], effectifs)
        lg['matieres'] = sorted(lg['matieres'].values(), key=lambda m: m.nom)
        lg['heures'] = round(lg['minutes'] / 60, 1)
        lg['hors_edt'] = 'edt' not in lg['sources']
        lignes.append(lg)
    lignes.sort(key=lambda lg: lg['classe'].nom)

    # Lundi à vendredi toujours affichés, le week-end seulement s'il y a cours.
    semaine = [{'jour': j, 'libelle': JOURS_LIB[j], 'cours': par_jour[j],
                'heures': round(sum(c['duree'] for c in par_jour[j]) / 60, 1),
                'aujourd_hui': JOURS[today.weekday()] == j}
               for j in JOURS if par_jour[j] or j not in ('samedi', 'dimanche')]

    # Matières : principale, secondaires, et celles réellement enseignées.
    enseignees = {}
    for lg in lignes:
        for m in lg['matieres']:
            enseignees[m.id] = m

    # Pointage et paie du mois en cours.
    debut_mois = today.replace(day=1)
    activation = pt.date_activation(etab)
    try:
        paie = pt.calculer_paie(professeur, debut_mois, today, annee_scolaire, activation)
    except Exception:  # fiche lisible même si le contrat est incomplet
        paie = None
    from school_admin.model.pointage_model import SeanceCours

    seances = list(SeanceCours.objects.filter(professeur=professeur, date__lte=today)
                   .exclude(statut='prevue').select_related('classe', 'matiere')
                   .order_by('-date', '-heure_debut')[:8])
    stats_seances = {k: 0 for k, _l in SeanceCours.STATUT_CHOICES}
    for s in SeanceCours.objects.filter(professeur=professeur, date__gte=debut_mois, date__lte=today).values_list(
            'statut', flat=True):
        stats_seances[s] = stats_seances.get(s, 0) + 1
    faites = stats_seances['validee'] + stats_seances['remplacee']
    dues = sum(v for k, v in stats_seances.items() if k not in ('prevue', 'annulee'))

    declarees = {m.id for m in professeur.matieres_secondaires.all()}
    if professeur.matiere_principale_id:
        declarees.add(professeur.matiere_principale_id)
    non_declarees = ([m for m in enseignees.values() if m.id not in declarees]
                     if type_etab != 'primary' else [])

    from school_admin.services.cahier_texte import profil_direction

    contrat_heures = professeur.heures_contrat_semaine
    return {
        'type_etab': type_etab,
        'classes': lignes,
        'nb_classes': len(lignes),
        'nb_eleves': sum(lg['effectif'] for lg in lignes),
        'heures_semaine': round(minutes_semaine / 60, 1),
        'nb_creneaux': len(creneaux),
        'charge_pct': (round(100 * minutes_semaine / 60 / float(contrat_heures))
                       if contrat_heures else None),
        'semaine': semaine,
        'aujourd_hui': par_jour[JOURS[today.weekday()]],
        'edt_vide': not creneaux,
        'matieres_enseignees': sorted(enseignees.values(), key=lambda m: m.nom),
        'matieres_non_declarees': sorted(non_declarees, key=lambda m: m.nom),
        'paie': paie,
        'pointage_actif': activation is not None,
        'seances': seances,
        'stats_seances': stats_seances,
        'assiduite': round(100 * faites / dues) if dues else None,
        'cahier': profil_direction(professeur),
        'anciennete': anciennete(professeur.date_embauche, today),
        'mois': debut_mois,
    }


def profil_personnel(personnel, user_permissions=()):
    today = timezone.localdate()
    return {
        'anciennete': anciennete(personnel.date_embauche, today),
        'nb_permissions': len(user_permissions or ()),
        'jamais_connecte': not personnel.last_login,
        'derniere_connexion': personnel.last_login,
    }
