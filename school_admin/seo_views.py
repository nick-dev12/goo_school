"""Vues robots.txt et sitemap.xml pour la plateforme ARIA."""

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

SITE_URL = getattr(settings, "SITE_URL", "https://aria-edu.com").rstrip("/")

# Pages publiques indexables (application Django)
PUBLIC_URLS = [
    {"loc": f"{SITE_URL}/connexion/", "priority": "0.9", "changefreq": "monthly"},
    {"loc": f"{SITE_URL}/inscription/", "priority": "0.8", "changefreq": "monthly"},
    {"loc": f"{SITE_URL}/politiques-utilisation/", "priority": "0.5", "changefreq": "yearly"},
    {"loc": f"{SITE_URL}/suppression-compte/", "priority": "0.4", "changefreq": "yearly"},
    {"loc": f"{SITE_URL}/", "priority": "0.7", "changefreq": "weekly"},
]


@require_GET
def robots_txt(request):
    """robots.txt – autorise les pages publiques, limite l'indexation des espaces privés."""
    lines = [
        "# ARIA – Plateforme de gestion scolaire",
        "User-agent: *",
        "Allow: /connexion/",
        "Allow: /inscription/",
        "Allow: /politiques-utilisation/",
        "Allow: /suppression-compte/",
        "Disallow: /dashboard/",
        "Disallow: /directeur/",
        "Disallow: /enseignant/",
        "Disallow: /eleve/",
        "Disallow: /parent/",
        "Disallow: /gestion-",
        "Disallow: /gestion_comptable/",
        "Disallow: /commercial/",
        "Disallow: /comptabilite/",
        "Disallow: /etablissements/",
        "Disallow: /api/",
        "Disallow: /admin/",
        "",
        f"Sitemap: {SITE_URL}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_xml(request):
    """Sitemap des pages publiques de l'application Django."""
    lastmod = timezone.now().date().isoformat()
    urls_xml = []
    for entry in PUBLIC_URLS:
        urls_xml.append(
            f"""  <url>
    <loc>{entry['loc']}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>{entry['changefreq']}</changefreq>
    <priority>{entry['priority']}</priority>
  </url>"""
        )

    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls_xml)}
</urlset>"""
    return HttpResponse(body, content_type="application/xml; charset=utf-8")
