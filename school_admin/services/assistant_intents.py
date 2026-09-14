"""
Interception locale des demandes d'ouverture (page ou classe).
Évite l'aller-retour DeepSeek quand l'intention est explicite.
"""
import re

from school_admin.services.assistant_pages import find_page, list_pages

OPEN_VERB_RE = re.compile(
    r"(?:ouvre[rz]?|afficher?|montre[- ]moi|montre[rz]?|"
    r"va(?:s)?\s+(?:sur|à|a|dans)|aller?\s+(?:sur|à|a|dans))",
    re.IGNORECASE,
)
CLASS_OPEN_RE = re.compile(
    r"(?:classe|promotion)\s+(?:de\s+|d['’]|des\s+|la\s+|le\s+)?"
    r"(.+)$",
    re.IGNORECASE,
)
BARE_CLASS_RE = re.compile(
    r"(\d+\s*(?:e|è|eme|ème)?\s*[A-Za-z]\b)"
    r"|([A-Za-z]{1,8}\s+L[1-3]\s+[A-Za-z0-9]{1,4})"
    r"|(terminale|seconde|premi[eè]re)\s*[A-Za-z]?",
    re.IGNORECASE,
)
LIST_CLASSES_RE = re.compile(
    r"^(?:la\s+|les\s+|l['’]|une\s+|des\s+)?(?:page\s+(?:des?\s+)?)?classes?$",
    re.IGNORECASE,
)
BARE_OPEN_CLASS_RE = re.compile(
    r"(?:ouvre[rz]?|afficher?|montre[- ]moi|montre[rz]?).{0,24}classes?",
    re.IGNORECASE,
)
ANNONCE_CREATE_RE = re.compile(
    r"(cr[ée]e[rz]?|r[ée]dige[rz]?|publie[rz]?|faire|pr[ée]pare[rz]?|lance[rz]?)"
    r".{0,60}annonce",
    re.IGNORECASE,
)
EDT_CREATE_RE = re.compile(
    r"(cr[ée]e[rz]?|pr[ée]pare[rz]?|lance[rz]?|fais|faire|g[ée]n[èe]re[rz]?)"
    r".{0,50}(?:emploi(?:s)?\s+du\s+temps|edt)\b",
    re.IGNORECASE,
)
CRENEAU_ADD_RE = re.compile(
    r"(ajoute[rz]?|mets|mettre|inscrire|programme[rz]?|place[rz]?|cr[ée]e[rz]?)"
    r".{0,60}(?:cr[ée]neau|cours|td\b|tp\b|s[ée]ance)",
    re.IGNORECASE,
)
JOUR_EXTRACT_RE = re.compile(
    r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)s?\b",
    re.IGNORECASE,
)
TIME_SPAN_RE = re.compile(
    r"(?:de\s+|à\s+partir\s+de\s+)?"
    r"(\d{1,2})\s*(?:h|:|heures?)?\s*(\d{0,2})"
    r"\s*(?:à|a|-|–|jusqu['’]à)\s*"
    r"(\d{1,2})\s*(?:h|:|heures?)?\s*(\d{0,2})",
    re.IGNORECASE,
)
SALLE_EXTRACT_RE = re.compile(
    r"\bsalle\s+([A-Za-z0-9][A-Za-z0-9\- ]{0,20})",
    re.IGNORECASE,
)
AVEC_PROF_RE = re.compile(
    r"\bavec\s+(?:le\s+prof(?:esseur)?\s+|m(?:me|\.)\s+)?"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\- ]{1,40}?)"
    r"(?=\s+(?:en\s+salle|salle|le\s+\w+di|de\s+\d|à\s+\d|,|$))",
    re.IGNORECASE,
)
MATIERE_EXTRACT_RE = re.compile(
    r"(?:cours|cr[ée]neau|s[ée]ance|td|tp|mati[eè]re)\s+"
    r"(?:de\s+|d['’]|en\s+)?"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9'\- ]{1,40}?)"
    r"(?=\s+(?:le\s+|lundi|mardi|mercredi|jeudi|vendredi|samedi|"
    r"dimanche|de\s+\d|à\s+\d|avec|salle|pour|,|$))",
    re.IGNORECASE,
)
ANNONCE_BODY_RE = re.compile(
    r"(?:pour\s+dire\s+que|pour\s+annoncer\s+que|qui\s+dit\s+que|"
    r"sur\s+le\s+fait\s+que|pour\s+dire\s+|annon(?:ce|cer)\s+que)\s+(.+)",
    re.IGNORECASE,
)
DEST_HINTS = (
    ('tout le monde', 'tous'),
    ('toute le monde', 'tous'),
    ('tous', 'tous'),
    ('enseignants', 'enseignants'),
    ('enseignant', 'enseignants'),
    ('professeurs', 'enseignants'),
    ('professeur', 'enseignants'),
    ('profs', 'enseignants'),
    ('prof', 'enseignants'),
    ('parents', 'parents'),
    ('parent', 'parents'),
    ('élèves', 'eleves'),
    ('eleves', 'eleves'),
    ('élève', 'eleves'),
    ('eleve', 'eleves'),
    ('étudiants', 'eleves'),
    ('etudiants', 'eleves'),
    ('personnel', 'personnel_administratif'),
    ('administratif', 'personnel_administratif'),
)

ACTION_INTENT_RES = (
    (re.compile(r'justifie[rz]?.{0,50}absence', re.I), 'justifier_absence'),
    (re.compile(r'approuve[rz]?.{0,50}liaison', re.I), 'approuver_liaison'),
    (re.compile(r'(rejette[rz]?|refuse[rz]?).{0,50}liaison', re.I), 'rejeter_liaison'),
    (re.compile(r'(valide[rz]?|accepte[rz]?).{0,50}pr[ée]inscription', re.I), 'valider_preinscription'),
    (re.compile(r'(rejette[rz]?|refuse[rz]?).{0,50}pr[ée]inscription', re.I), 'rejeter_preinscription'),
    (re.compile(r'publie[rz]?.{0,40}bulletin', re.I), 'publier_bulletins'),
    (re.compile(r'calcule[rz]?.{0,40}moyenne', re.I), 'calculer_moyennes_classe'),
    (re.compile(r'(enregistre[rz]?|ajoute[rz]?).{0,40}paiement', re.I), 'enregistrer_paiement'),
    (re.compile(
        r'(cr[ée]e[rz]?|ajoute[rz]?).{0,50}param[eè]tres?.{0,40}(comptab|scolar|groupe)',
        re.I,
    ), 'creer_parametres_comptabilite'),
    (re.compile(
        r'(modifie[rz]?|change[rz]?|mets? [àa] jour).{0,50}param[eè]tres?.{0,40}(comptab|scolar|groupe)',
        re.I,
    ), 'modifier_parametres_comptabilite'),
    (re.compile(
        r'supprime[rz]?.{0,50}param[eè]tres?.{0,40}(comptab|scolar|groupe)',
        re.I,
    ), 'supprimer_parametres_comptabilite'),
    (re.compile(r'(cr[ée]e[rz]?|ajoute[rz]?).{0,30}ann[ée]e scolaire', re.I), 'creer_annee_scolaire'),
    (re.compile(r'active[rz]?.{0,30}ann[ée]e', re.I), 'activer_annee_scolaire'),
    (re.compile(r'(cr[ée]e[rz]?|ajoute[rz]?).{0,30}p[ée]riode', re.I), 'creer_periode'),
    (re.compile(r'(cr[ée]e[rz]?|ajoute[rz]?).{0,30}classe', re.I), 'creer_classe'),
    (re.compile(r'(cr[ée]e[rz]?|ajoute[rz]?).{0,30}salle', re.I), 'creer_salle'),
    (re.compile(r'(cr[ée]e[rz]?|ajoute[rz]?).{0,30}mati[eè]re', re.I), 'creer_matiere'),
    (re.compile(r'(cr[ée]e[rz]?|ajoute[rz]?).{0,40}session.{0,20}examen', re.I), 'creer_session_examen'),
    (re.compile(r'g[ée]n[eè]re[rz]?.{0,40}(certificat|attestation|convocation|fiche)', re.I), 'generer_document'),
    (re.compile(r'publie[rz]?.{0,40}annonce', re.I), 'publier_annonce'),
    (re.compile(r'archive[rz]?.{0,40}annonce', re.I), 'archiver_annonce'),
    (re.compile(r'supprime[rz]?.{0,40}annonce', re.I), 'supprimer_annonce'),
)


def extract_action_args(name, text):
    """Extrait les arguments évidents d’une phrase pour un outil d’action."""
    raw = text or ''
    args = {}
    if name == 'generer_document':
        lowered = raw.lower()
        if 'réussite' in lowered or 'reussite' in lowered:
            args['type'] = 'attestation_reussite'
        elif 'conduite' in lowered:
            args['type'] = 'attestation_conduite'
        elif 'radiation' in lowered or 'transfert' in lowered:
            args['type'] = 'certificat_radiation'
        elif 'fiche' in lowered:
            args['type'] = 'fiche_inscription'
        elif 'convocation' in lowered:
            args['type'] = 'convocation'
        else:
            args['type'] = 'certificat_scolarite'
    pour = re.search(
        r'(?:pour|de|du|d[\'’])\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\'\- ]{1,40})$',
        raw.strip().rstrip('.!?'),
        re.I,
    )
    if pour and name in (
        'justifier_absence',
        'valider_preinscription',
        'enregistrer_paiement',
        'generer_document',
        'approuver_liaison',
        'rejeter_liaison',
    ):
        args['query'] = pour.group(1).strip()
    class_match = CLASS_OPEN_RE.search(raw)
    if class_match and name in (
        'publier_bulletins',
        'calculer_moyennes_classe',
        'creer_classe',
        'valider_preinscription',
    ):
        args.setdefault('classe', _clean_class_query(class_match.group(1)))
    montant = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:f|fcfa|xof|euros?)?', raw, re.I)
    if montant and name == 'enregistrer_paiement':
        args['montant'] = montant.group(1)
    if name in (
        'creer_parametres_comptabilite',
        'modifier_parametres_comptabilite',
        'supprimer_parametres_comptabilite',
    ):
        named = re.search(r'[«"](.+?)[»"]', raw)
        if named:
            args['nom' if name != 'supprimer_parametres_comptabilite' else 'query'] = named.group(1).strip()
        groupes = re.search(
            r'(?:groupe[s]?|pour(?:\s+les)?(?:\s+classes)?)\s+([A-Za-zÀ-ÿ0-9 ,;/]+)',
            raw,
            re.I,
        )
        if groupes and name != 'supprimer_parametres_comptabilite':
            args['groupes_classes'] = groupes.group(1).strip()
        if montant and name != 'supprimer_parametres_comptabilite':
            lowered = raw.lower()
            if 'inscription' in lowered:
                args['montant_frais_inscription'] = montant.group(1)
            elif 'mensual' in lowered:
                args['montant_mensualite'] = montant.group(1)
            else:
                args.setdefault('montant_mensualite', montant.group(1))
    return args


def resolve_action_intent(question):
    """
    Détecte une action mutante explicite (hors annonce / EDT déjà gérés).
    Retourne (nom_outil, arguments) ou None.
    """
    text = (question or '').strip()
    if not text:
        return None
    if ANNONCE_CREATE_RE.search(text) or EDT_CREATE_RE.search(text) or CRENEAU_ADD_RE.search(text):
        return None
    for pattern, name in ACTION_INTENT_RES:
        if pattern.search(text):
            return name, extract_action_args(name, text)
    return None


PAGE_ALIASES = {
    'accueil': 'dashboard',
    'tableau de bord': 'dashboard',
    'annonces': 'annonces',
    'annonce': 'annonces',
    'élèves': 'eleves',
    'eleves': 'eleves',
    'étudiants': 'eleves',
    'etudiants': 'eleves',
    'professeurs': 'professeurs',
    'enseignants': 'professeurs',
    'emplois du temps': 'emplois_du_temps',
    'emploi du temps': 'emplois_du_temps',
    'matières': 'matieres',
    'matieres': 'matieres',
    'modules': 'matieres',
    'examens': 'examens',
    'scolarité': 'comptabilite',
    'scolarite': 'comptabilite',
    'comptabilité': 'comptabilite',
    'comptabilite': 'comptabilite',
    'paramètres de scolarité': 'parametres_comptabilite',
    'parametres de scolarite': 'parametres_comptabilite',
    'paramètres de comptabilité': 'parametres_comptabilite',
    'parametres de comptabilite': 'parametres_comptabilite',
    'paramètres comptabilité': 'parametres_comptabilite',
    'bulletins': 'bulletins',
    'périodes': 'periodes',
    'periodes': 'periodes',
    'préinscriptions': 'preinscriptions',
    'preinscriptions': 'preinscriptions',
    'notifications': 'notifications',
    'certificats': 'certificats',
    'convocations': 'convocations',
    'réinscription': 'reinscription',
    'reinscription': 'reinscription',
    'facturation': 'facturation',
    'salles': 'salles',
    'personnel': 'personnel',
}


def _clean_target(raw):
    text = (raw or '').strip().rstrip('.!?…')
    text = re.sub(r"^(?:moi\s+)?(?:la\s+|le\s+|les\s+|l['’])", '', text, flags=re.I)
    text = re.sub(r"^(?:page\s+(?:des?\s+|de\s+|du\s+|d['’])?)", '', text, flags=re.I)
    return text.strip()


def _clean_class_query(raw):
    text = _clean_target(raw)
    text = re.sub(r"^(?:de\s+|d['’]|des\s+|la\s+|le\s+|l['’])+", '', text, flags=re.I)
    return text.strip()


def _looks_like_class_name(text):
    return bool(BARE_CLASS_RE.search(text or ''))


def infer_destinataires(text):
    lowered = (text or '').lower()
    found = []
    for hint, code in DEST_HINTS:
        if re.search(r'\b' + re.escape(hint) + r'\b', lowered):
            if code not in found:
                found.append(code)
    if 'tous' in found:
        return ['tous']
    return found or None


def extract_annonce_draft(text):
    draft = {
        'titre': '',
        'contenu': '',
        'destinataires': infer_destinataires(text),
    }
    match = ANNONCE_BODY_RE.search(text or '')
    if match:
        body = match.group(1).strip().rstrip('.!?')
        body = re.sub(
            r'\s+(?:pour|à)\s+(?:tout\s+le\s+monde|tous|les\s+profs?|'
            r'les\s+enseignants?|les\s+parents?|les\s+[eé]l[eè]ves?)\s*$',
            '',
            body,
            flags=re.I,
        ).strip()
        if body:
            draft['contenu'] = body
            draft['titre'] = body[:70]
    return draft


def resolve_annonce_intent(question):
    text = (question or '').strip()
    if not text or not ANNONCE_CREATE_RE.search(text):
        return None
    return extract_annonce_draft(text)


def _format_extracted_time(hour, minute):
    try:
        heures = int(hour)
        minutes = int(minute) if minute else 0
    except (TypeError, ValueError):
        return ''
    if heures > 23 or minutes > 59:
        return ''
    return f'{heures:02d}:{minutes:02d}'


def _is_time_like_class(text):
    return bool(re.match(r'^\d+\s*h\b', text or '', re.I))


def extract_emploi_draft(text):
    from school_admin.services.assistant_search import clean_class_query

    draft = {'classe': '', 'notes': ''}
    raw = text or ''
    pour = re.search(
        r'(?:pour|dans)\s+(?:la\s+)?(?:classe\s+|promotion\s+)?(.+)$',
        raw,
        re.I,
    )
    if pour:
        candidate = clean_class_query(pour.group(1))
        if candidate and not _is_time_like_class(candidate):
            draft['classe'] = candidate
            return draft
    class_match = CLASS_OPEN_RE.search(raw)
    if class_match:
        candidate = clean_class_query(class_match.group(1))
        if candidate and not _is_time_like_class(candidate):
            draft['classe'] = candidate
            return draft
    for match in BARE_CLASS_RE.finditer(raw):
        candidate = clean_class_query(match.group(0))
        if candidate and not _is_time_like_class(candidate):
            draft['classe'] = candidate
            return draft
    leftover = clean_class_query(raw)
    if leftover and not _is_time_like_class(leftover):
        draft['classe'] = leftover
    return draft


def extract_creneau_draft(text):
    raw = text or ''
    draft = extract_emploi_draft(raw)
    jour_match = JOUR_EXTRACT_RE.search(raw)
    if jour_match:
        draft['jour'] = jour_match.group(1).lower()
    span = TIME_SPAN_RE.search(raw)
    if span:
        draft['heure_debut'] = _format_extracted_time(span.group(1), span.group(2))
        draft['heure_fin'] = _format_extracted_time(span.group(3), span.group(4))
    salle_match = SALLE_EXTRACT_RE.search(raw)
    if salle_match:
        draft['salle'] = salle_match.group(1).strip()
    prof_match = AVEC_PROF_RE.search(raw)
    if prof_match:
        draft['professeur'] = prof_match.group(1).strip(' ,.')
    matiere_match = MATIERE_EXTRACT_RE.search(raw)
    if matiere_match:
        nom = matiere_match.group(1).strip(' ,.')
        if nom.lower() not in ('le', 'la', 'un', 'une', 'des'):
            draft['matiere'] = nom
    if re.search(r'\btd\b|travaux dirig', raw, re.I):
        draft['type_cours'] = 'td'
    elif re.search(r'\btp\b|travaux prat', raw, re.I):
        draft['type_cours'] = 'tp'
    return draft


def resolve_emploi_intent(question):
    """
    Détecte une demande de création d’emploi du temps ou d’ajout de créneau.
    Retourne un dict {action, ...champs} ou None.
    """
    text = (question or '').strip()
    if not text:
        return None
    if OPEN_VERB_RE.search(text) and not EDT_CREATE_RE.search(text) and not CRENEAU_ADD_RE.search(text):
        return None
    create = bool(EDT_CREATE_RE.search(text))
    add = bool(CRENEAU_ADD_RE.search(text))
    if not create and not add:
        return None
    extracted = extract_creneau_draft(text)
    if add or extracted.get('jour') or extracted.get('heure_debut'):
        extracted['action'] = 'ajouter_creneau_emploi'
        return extracted
    draft = extract_emploi_draft(text)
    draft['action'] = 'creer_emploi_du_temps'
    return draft


def resolve_open_intent(question):
    """
    Si la question demande clairement d'ouvrir une page ou une classe,
    retourne (nom_outil, arguments). Sinon None.
    """
    text = (question or '').strip()
    if not text or not OPEN_VERB_RE.search(text):
        return None

    class_match = CLASS_OPEN_RE.search(text)
    if class_match:
        query = _clean_class_query(class_match.group(1))
        if query and not LIST_CLASSES_RE.match(query) and _looks_like_class_name(query):
            return 'ouvrir_classe', {'query': query, 'ouvrir': True}
        if query and LIST_CLASSES_RE.match(query):
            return 'ouvrir_page', {'page_key': 'classes', 'ouvrir': True}
        if BARE_OPEN_CLASS_RE.search(text) and not _looks_like_class_name(query or ''):
            return 'choisir_classe', {}

    verb_match = OPEN_VERB_RE.search(text)
    target = _clean_target(text[verb_match.end():]) if verb_match else ''
    if not target:
        return None

    if LIST_CLASSES_RE.match(target):
        if re.search(r'\bles\s+classes\b', text, re.I) or re.search(r'page\s+des?\s+classes', text, re.I):
            return 'ouvrir_page', {'page_key': 'classes', 'ouvrir': True}
        return 'choisir_classe', {}

    if BARE_OPEN_CLASS_RE.search(text) and not _looks_like_class_name(target):
        return 'choisir_classe', {}

    if _looks_like_class_name(target):
        return 'ouvrir_classe', {'query': target, 'ouvrir': True}

    alias = PAGE_ALIASES.get(target.lower())
    if alias:
        return 'ouvrir_page', {'page_key': alias, 'ouvrir': True}

    page = find_page(target) or find_page(target.replace(' ', '_'))
    if page:
        return 'ouvrir_page', {'page_key': page['key'], 'ouvrir': True}

    for item in list_pages():
        haystack = f"{item['titre']} {item.get('mots') or ''}".lower()
        if target.lower() in haystack:
            return 'ouvrir_page', {'page_key': item['key'], 'ouvrir': True}

    return None


SMALL_TALK_RE = re.compile(
    r'^\s*(?:'
    r'(?:bonjour|bonsoir|salut|hello|hey|coucou)\b.*|'
    r'(?:merci(?:\s+beaucoup)?|thanks)\s*[.!?]*|'
    r'(?:au\s+revoir|à\s+bientôt|bonne\s+(?:journée|soirée))\s*[.!?]*|'
    r'(?:comment\s+(?:ça|ca)\s+va|ça\s+va|ca\s+va|comment\s+allez[- ]vous)'
    r'(?:\s|[.!?]|$).*'
    r')\s*$',
    re.IGNORECASE,
)


def is_small_talk(question):
    """Salutations et conversation, sans demande administrative."""
    return bool(SMALL_TALK_RE.match((question or '').strip()))


TOPIC_SWITCH_RE = re.compile(
    r"^(?:en\s+fait|au\s+fait|autre\s+chose|plut[oô]t|oublie(?:\s+[çc]a)?|"
    r"laisse\s+(?:tomber|faire)|on\s+change|nouvelle\s+question|"
    r"sinon|et\s+sinon|passe\s+[àa]|arr[êe]te)\b",
    re.IGNORECASE,
)
NEW_QUESTION_RE = re.compile(
    r"^(?:combien|qui|quand|o[uù]|pourquoi|comment|quel(?:le|s)?|"
    r"est[- ]ce\s+que|peux[- ]tu|pouvez[- ]vous|dis[- ]moi|"
    r"j['’]ai\s+(?:une\s+)?(?:autre\s+)?(?:question|demande))\b",
    re.IGNORECASE,
)


def _normalize_choice(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def matches_pending_choice(question, pending):
    query = _normalize_choice(question)
    if not query:
        return False
    for item in (pending or {}).get('choices') or []:
        if not isinstance(item, dict):
            continue
        label = _normalize_choice(item.get('label') or item.get('value'))
        if label and (query == label or query in label or label in query):
            return True
    return False


def decide_pending_reply(question, pending):
    """
    continue = le message répond à l'action en cours.
    switch = nouveau sujet, il faut abandonner l'action.
    ask = laisser DeepSeek trancher.
    """
    text = (question or '').strip()
    if not text or not pending:
        return 'switch'

    name = pending.get('name')
    if TOPIC_SWITCH_RE.search(text):
        return 'switch'
    if is_small_talk(text):
        return 'switch'
    if resolve_annonce_intent(text) and name == 'choisir_classe':
        return 'switch'
    open_intent = resolve_open_intent(text)
    if open_intent:
        tool_name = open_intent[0]
        if name == 'choisir_classe' and tool_name in ('ouvrir_classe', 'choisir_classe'):
            return 'continue'
        return 'switch'

    if name == 'choisir_classe':
        if matches_pending_choice(text, pending) or _looks_like_class_name(text):
            return 'continue'
        if NEW_QUESTION_RE.search(text):
            return 'switch'
        if len(text) <= 40 and not text.endswith('?'):
            return 'continue'
        return 'ask'

    if name in ('annonce_guidee', 'creer_publier_annonce'):
        if infer_destinataires(text):
            return 'continue'
        if ANNONCE_CREATE_RE.search(text):
            return 'continue'
        if NEW_QUESTION_RE.search(text):
            return 'switch'
        return 'ask'

    if name in ('creer_emploi_du_temps', 'ajouter_creneau_emploi'):
        if resolve_emploi_intent(text):
            return 'continue'
        if JOUR_EXTRACT_RE.search(text) or TIME_SPAN_RE.search(text):
            return 'continue'
        if matches_pending_choice(text, pending) or _looks_like_class_name(text):
            return 'continue'
        if NEW_QUESTION_RE.search(text):
            return 'switch'
        return 'ask'

    from school_admin.services.assistant_actions import is_write_action

    if is_write_action(name):
        if resolve_action_intent(text):
            other = resolve_action_intent(text)
            if other and other[0] != name:
                return 'switch'
            return 'continue'
        if matches_pending_choice(text, pending):
            return 'continue'
        if NEW_QUESTION_RE.search(text):
            return 'switch'
        return 'ask'

    if NEW_QUESTION_RE.search(text):
        return 'switch'
    return 'ask'


def infer_working_ack(question, pending=None):
    """Phrase courte affichée tout de suite, pendant que le travail démarre."""
    text = (question or '').strip()
    lowered = text.lower()
    name = (pending or {}).get('name') if isinstance(pending, dict) else ''

    if re.match(r"^\s*(annul|laisse\s+tomber|oublie)", text, re.I):
        return "J’annule."
    if name in ('annonce_guidee', 'creer_publier_annonce'):
        if re.match(r"^\s*(oui|ok|okay|c['’ ]est bon|publie)", text, re.I):
            return "Je publie l’annonce."
        if infer_destinataires(text):
            return "Je mets à jour les destinataires."
        if re.search(r'modifi', lowered):
            return "Je corrige le brouillon."
    if name == 'choisir_classe' and (
        matches_pending_choice(text, pending) or _looks_like_class_name(text)
    ):
        return "J’ouvre cette classe."

    if name in ('creer_emploi_du_temps', 'ajouter_creneau_emploi'):
        if re.match(r"^\s*(oui|ok|okay|c['’ ]est bon)", text, re.I):
            return "Je valide."
        return "Je prépare l’emploi du temps."
    if EDT_CREATE_RE.search(text):
        return "Je prépare l’emploi du temps."
    if CRENEAU_ADD_RE.search(text):
        return "Je prépare ce créneau."
    if ANNONCE_CREATE_RE.search(text):
        return "Je prépare l’annonce."
    action_intent = resolve_action_intent(text)
    if action_intent:
        return "Je prépare cette action."
    open_intent = resolve_open_intent(text)
    if open_intent:
        tool_name = open_intent[0]
        if tool_name == 'ouvrir_classe':
            return "J’ouvre cette classe."
        if tool_name == 'choisir_classe':
            return "Je liste les classes."
        return "J’ouvre cette page."
    if any(token in lowered for token in ('fille', 'garçon', 'garcon', 'sexe', 'féminin', 'feminin')):
        return "Je compte les filles et les garçons."
    if any(token in lowered for token in ('effectif', 'combien', 'nombre')):
        return "Je consulte les effectifs."
    if any(token in lowered for token in ('note', 'moyenne', 'bulletin')):
        return "Je regarde les notes."
    if any(token in lowered for token in ('absence', 'présence', 'presence', 'présent')):
        return "Je vérifie les présences."
    if any(
        token in lowered
        for token in (
            'paramètres de scolarité',
            'parametres de scolarite',
            'paramètres de comptabilité',
            'paramètres comptab',
        )
    ):
        return "Je consulte les paramètres de scolarité."
    if any(token in lowered for token in ('paiement', 'impay', 'frais', 'scolarité', 'scolarite')):
        return "Je consulte la scolarité."
    if any(token in lowered for token in ('emploi du temps', 'edt')):
        return "Je cherche l’emploi du temps."
    if any(token in lowered for token in ('professeur', 'enseignant')):
        return "Je cherche parmi les enseignants."
    if any(token in lowered for token in ('élève', 'eleve', 'étudiant', 'etudiant', 'matricule')):
        return "Je cherche cet élève."
    if any(token in lowered for token in ('classe', 'promotion')):
        return "Je consulte les classes."
    if any(token in lowered for token in ('période', 'periode', 'semestre', 'trimestre')):
        return "Je regarde les périodes."
    if 'annonce' in lowered:
        return "Je consulte les annonces."
    return "Je cherche ça."
