"""
Configuration et résolution SEO pour la plateforme ARIA (school_admin).
Détection automatique par chemin d'URL + surcharge possible dans les vues.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

SITE_NAME = getattr(settings, "SITE_NAME", "ARIA")
SITE_TAGLINE = getattr(
    settings,
    "SITE_TAGLINE",
    "Logiciel de gestion scolaire tout-en-un",
)

DEFAULT_KEYWORDS = (
    "ARIA, gestion scolaire, logiciel école, plateforme éducative, ERP scolaire, "
    "application gestion établissement, notes en ligne, bulletins scolaires, "
    "présences élèves, emploi du temps, portail parents, espace enseignant, "
    "administration scolaire, digitalisation école, éducation numérique, "
    "école Sénégal, Afrique francophone"
)

PUBLIC_ROBOTS = "index, follow, max-image-preview:large"
PRIVATE_ROBOTS = "noindex, nofollow"


@dataclass
class SeoMeta:
    title: str
    description: str
    keywords: str = DEFAULT_KEYWORDS
    robots: str = PRIVATE_ROBOTS
    section: str = "application"
    og_enabled: bool = False
    canonical_path: str | None = None

    def to_context(self, request) -> dict[str, Any]:
        canonical = None
        if self.canonical_path:
            base = getattr(settings, "SITE_URL", "").rstrip("/")
            canonical = f"{base}{self.canonical_path}"

        return {
            "title": self.title,
            "description": self.description,
            "keywords": self.keywords,
            "robots": self.robots,
            "section": self.section,
            "og_enabled": self.og_enabled,
            "canonical_url": canonical,
            "site_name": SITE_NAME,
            "og_image": getattr(
                settings,
                "SEO_DEFAULT_OG_IMAGE",
                "https://aria-edu.com/static/school_admin/img/logo.jpeg",
            ),
        }


def _title(*parts: str) -> str:
    cleaned = [p.strip() for p in parts if p and p.strip()]
    return " – ".join(cleaned) if cleaned else SITE_NAME


# --- Espaces utilisateurs (zones privées : noindex) ---

ZONE_DIRECTEUR = SeoMeta(
    title=_title("Espace Directeur", SITE_NAME),
    description=(
        "Espace directeur ARIA : tableau de bord, gestion des élèves, bulletins, "
        "examens, personnel, comptabilité et administration complète de votre "
        "établissement scolaire."
    ),
    keywords=DEFAULT_KEYWORDS + ", espace directeur, direction école, gestion administrative",
    section="directeur",
)

ZONE_ENSEIGNANT = SeoMeta(
    title=_title("Espace Enseignant", SITE_NAME),
    description=(
        "Espace enseignant ARIA : saisie des notes, évaluations, présences, "
        "devoirs à la maison, suivi des élèves et communication pédagogique."
    ),
    keywords=DEFAULT_KEYWORDS + ", espace enseignant, notes, évaluations, cahier de textes numérique",
    section="enseignant",
)

ZONE_ENSEIGNANT_PRIMAIRE = SeoMeta(
    title=_title("Espace Enseignant Primaire", SITE_NAME),
    description=(
        "Espace enseignant du primaire sur ARIA : gestion des classes, notes, "
        "évaluations et suivi pédagogique adapté au cycle primaire."
    ),
    keywords=DEFAULT_KEYWORDS + ", enseignant primaire, école primaire, notes CP CE CM",
    section="enseignant_primaire",
)

ZONE_ELEVE = SeoMeta(
    title=_title("Espace Élève", SITE_NAME),
    description=(
        "Espace élève ARIA : consulter ses notes, bulletins, devoirs, emploi du "
        "temps, absences et notifications de l'établissement."
    ),
    keywords=DEFAULT_KEYWORDS + ", espace élève, portail élève, notes, bulletin en ligne",
    section="eleve",
)

ZONE_PARENT = SeoMeta(
    title=_title("Espace Parent", SITE_NAME),
    description=(
        "Espace parent ARIA : suivi scolaire des enfants, bulletins, convocations, "
        "annonces et communication avec l'établissement."
    ),
    keywords=DEFAULT_KEYWORDS + ", espace parent, suivi enfant, bulletins parents",
    section="parent",
)

ZONE_ADMIN = SeoMeta(
    title=_title("Administration plateforme", SITE_NAME),
    description=(
        "Administration ARIA : gestion des établissements scolaires, comptes, "
        "équipes et paramètres de la plateforme de gestion scolaire."
    ),
    keywords=DEFAULT_KEYWORDS + ", administration, multi-établissements",
    section="administrateur",
)

ZONE_COMMERCIAL = SeoMeta(
    title=_title("Espace Commercial", SITE_NAME),
    description=(
        "Interface commerciale ARIA : prospection, suivi des établissements "
        "scolaires et accompagnement à la digitalisation."
    ),
    section="commercial",
)

ZONE_COMPTABLE = SeoMeta(
    title=_title("Gestion Comptable", SITE_NAME),
    description=(
        "Espace comptable ARIA : facturation, suivi des paiements de scolarité, "
        "rapports financiers et gestion budgétaire des établissements."
    ),
    keywords=DEFAULT_KEYWORDS + ", comptabilité scolaire, frais de scolarité, facturation",
    section="comptable",
)

ZONE_PERSONNEL = SeoMeta(
    title=_title("Personnel administratif", SITE_NAME),
    description=(
        "Espace personnel administratif ARIA : gestion des élèves, enseignants "
        "et tâches quotidiennes de l'établissement."
    ),
    section="personnel",
)

ZONE_SECRETAIRE = SeoMeta(
    title=_title("Secrétariat", SITE_NAME),
    description=(
        "Espace secrétariat ARIA : inscriptions, certificats, cartes scolaires "
        "et gestion administrative des dossiers élèves."
    ),
    section="secretaire",
)


# --- Pages publiques (indexables) ---

PUBLIC_CONNEXION = SeoMeta(
    title=_title("Connexion", SITE_TAGLINE),
    description=(
        "Connectez-vous à ARIA, la plateforme de gestion scolaire pour directeurs, "
        "enseignants, élèves, parents et personnel administratif. Accès sécurisé "
        "à votre espace établissement."
    ),
    robots=PUBLIC_ROBOTS,
    section="connexion",
    og_enabled=True,
    canonical_path="/connexion/",
)

PUBLIC_INSCRIPTION = SeoMeta(
    title=_title("Inscription établissement", SITE_TAGLINE),
    description=(
        "Inscrivez votre établissement scolaire sur ARIA. Logiciel de gestion "
        "complète pour écoles, collèges et lycées au Sénégal et en Afrique."
    ),
    robots=PUBLIC_ROBOTS,
    section="inscription",
    og_enabled=True,
    canonical_path="/inscription/",
)

PUBLIC_PREINSCRIPTION = SeoMeta(
    title=_title("Préinscription en ligne", SITE_TAGLINE),
    description=(
        "Formulaire de préinscription scolaire en ligne via ARIA. Inscrivez votre "
        "enfant simplement pour les écoles, collèges et lycées partenaires."
    ),
    robots=PUBLIC_ROBOTS,
    section="preinscription",
    og_enabled=True,
)

PUBLIC_POLITIQUES = SeoMeta(
    title=_title("Politiques d'utilisation", SITE_NAME),
    description=(
        "Politiques d'utilisation et conditions de la plateforme ARIA de gestion "
        "scolaire. Protection des données et règles d'usage."
    ),
    robots=PUBLIC_ROBOTS,
    section="legal",
    og_enabled=False,
    canonical_path="/politiques-utilisation/",
)

PUBLIC_PASSWORD_RESET = SeoMeta(
    title=_title("Réinitialisation du mot de passe", SITE_NAME),
    description=(
        "Réinitialisez votre mot de passe ARIA pour accéder à votre espace "
        "directeur, enseignant, élève ou parent."
    ),
    robots="noindex, follow",
    section="auth",
)

PUBLIC_SUPPRESSION_COMPTE = SeoMeta(
    title=_title("Suppression de compte", SITE_NAME),
    description=(
        "Demande de suppression de compte utilisateur sur la plateforme ARIA "
        "conformément à la réglementation sur les données personnelles."
    ),
    robots=PUBLIC_ROBOTS,
    section="legal",
    canonical_path="/suppression-compte/",
)


def _replace(base: SeoMeta, **kwargs) -> SeoMeta:
    data = {
        "title": base.title,
        "description": base.description,
        "keywords": base.keywords,
        "robots": base.robots,
        "section": base.section,
        "og_enabled": base.og_enabled,
        "canonical_path": base.canonical_path,
    }
    data.update(kwargs)
    return SeoMeta(**data)


DEFAULT_PRIVATE = SeoMeta(
    title=_title(SITE_TAGLINE),
    description=(
        "Plateforme ARIA de gestion scolaire : administration, pédagogie, "
        "notes, bulletins, présences et communication pour tout l'établissement."
    ),
    section="application",
)


# Règles détaillées (regex sur le chemin, première correspondance gagne)
_PATH_RULES: list[tuple[re.Pattern[str], SeoMeta]] = [
    # Public
    (re.compile(r"^/connexion/"), PUBLIC_CONNEXION),
    (re.compile(r"^/inscription/"), PUBLIC_INSCRIPTION),
    (re.compile(r"^/politiques-utilisation/"), PUBLIC_POLITIQUES),
    (re.compile(r"^/suppression-compte/"), PUBLIC_SUPPRESSION_COMPTE),
    (re.compile(r"^/password-reset/"), PUBLIC_PASSWORD_RESET),
    (re.compile(r"^/preinscription/"), PUBLIC_PREINSCRIPTION),
    (re.compile(r"^/connexion/professeurs/otp"), PUBLIC_CONNEXION),
    # Sous-pages métier (descriptions spécifiques, toujours noindex)
    (re.compile(r".*/bulletin"), _replace(ZONE_ELEVE, title=_title("Bulletins scolaires", "Espace Élève", SITE_NAME),
        description="Consultation des bulletins et relevés de notes sur l'espace élève ARIA.")),
    (re.compile(r".*/notes"), _replace(ZONE_ENSEIGNANT, title=_title("Notes et évaluations", "Espace Enseignant", SITE_NAME),
        description="Saisie et gestion des notes, moyennes et évaluations des élèves avec ARIA.")),
    (re.compile(r".*/emploi-du-temps"), _replace(ZONE_ELEVE, title=_title("Emploi du temps", SITE_NAME),
        description="Emploi du temps scolaire en ligne pour élèves, enseignants et administration.")),
    (re.compile(r".*/gestion-eleves"), _replace(ZONE_DIRECTEUR, title=_title("Gestion des élèves", "Espace Directeur", SITE_NAME),
        description="Inscription, réinscription et suivi complet des élèves de l'établissement.")),
    (re.compile(r".*/bulletins"), _replace(ZONE_DIRECTEUR, title=_title("Bulletins et résultats", "Espace Directeur", SITE_NAME),
        description="Génération des bulletins, moyennes et résultats scolaires par classe.")),
    (re.compile(r".*/comptabilite"), _replace(ZONE_DIRECTEUR, title=_title("Comptabilité scolaire", SITE_NAME),
        description="Suivi des frais de scolarité, paiements et facturation des élèves.")),
    (re.compile(r".*/annonces"), _replace(ZONE_PARENT, title=_title("Annonces", "Espace Parent", SITE_NAME),
        description="Annonces et communications de l'établissement vers les parents d'élèves.")),
    # Zones principales
    (re.compile(r"^/dashboard/directeur/"), ZONE_DIRECTEUR),
    (re.compile(r"^/gestion-"), ZONE_DIRECTEUR),
    (re.compile(r"^/bulletins/"), ZONE_DIRECTEUR),
    (re.compile(r"^/directeur/"), ZONE_DIRECTEUR),
    (re.compile(r"^/enseignant/primaire/"), ZONE_ENSEIGNANT_PRIMAIRE),
    (re.compile(r"^/enseignant/"), ZONE_ENSEIGNANT),
    (re.compile(r"^/dashboard/enseignant/"), ZONE_ENSEIGNANT),
    (re.compile(r"^/eleve/"), ZONE_ELEVE),
    (re.compile(r"^/parent/"), ZONE_PARENT),
    (re.compile(r"^/dashboard/commercial/"), ZONE_COMMERCIAL),
    (re.compile(r"^/commercial/"), ZONE_COMMERCIAL),
    (re.compile(r"^/dashboard/comptable/"), ZONE_COMPTABLE),
    (re.compile(r"^/gestion_comptable/"), ZONE_COMPTABLE),
    (re.compile(r"^/comptabilite/"), ZONE_COMPTABLE),
    (re.compile(r"^/secretaire/"), ZONE_SECRETAIRE),
    (re.compile(r"^/personnel/"), ZONE_PERSONNEL),
    (re.compile(r"^/etablissements/"), ZONE_ADMIN),
    (re.compile(r"^/dashboard/(support|developpeur|marketing|rh)/"), ZONE_ADMIN),
    (re.compile(r"^/$"), ZONE_ADMIN),
]


def resolve_seo(request, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Résout les métadonnées SEO pour la requête courante.
    Les vues peuvent passer seo_overrides dans le contexte template.
    """
    path = request.path if request else "/"
    meta = DEFAULT_PRIVATE

    for pattern, zone_meta in _PATH_RULES:
        if pattern.search(path):
            meta = zone_meta
            break

    ctx = meta.to_context(request)

    if overrides:
        ctx.update({k: v for k, v in overrides.items() if v is not None})

    if request and not ctx.get("canonical_url") and meta.robots.startswith("index"):
        ctx["canonical_url"] = request.build_absolute_uri(request.path)

    return ctx


def seo_for_section(section: str, page_title: str | None = None) -> dict[str, str]:
    """Helper pour les vues : surcharge manuelle par section."""
    zones = {
        "directeur": ZONE_DIRECTEUR,
        "enseignant": ZONE_ENSEIGNANT,
        "enseignant_primaire": ZONE_ENSEIGNANT_PRIMAIRE,
        "eleve": ZONE_ELEVE,
        "parent": ZONE_PARENT,
        "admin": ZONE_ADMIN,
        "commercial": ZONE_COMMERCIAL,
        "comptable": ZONE_COMPTABLE,
    }
    zone = zones.get(section, DEFAULT_PRIVATE)
    overrides: dict[str, str] = {}
    if page_title:
        overrides["title"] = _title(page_title, SITE_NAME)
    return {**zone.to_context(None), **overrides}
