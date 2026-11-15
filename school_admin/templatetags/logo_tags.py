"""Logo de l'établissement dans les en-têtes des documents à imprimer."""
import logging
from io import BytesIO

from django import template
from django.core.files.base import ContentFile

register = template.Library()
logger = logging.getLogger(__name__)

COTE_MAX = 320            # pixels : net à l'impression pour un logo de 2 cm de haut
POIDS_DEJA_LEGER = 60_000  # octets : en dessous, l'image d'origine est servie telle quelle


@register.simple_tag
def logo_impression(etablissement):
    """Adresse d'une version légère du logo (créée une fois, puis réutilisée) ; '' sans logo.

    Un logo envoyé en haute définition pèse souvent plusieurs centaines de Ko : inutile pour une vignette
    d'en-tête. En cas d'échec (fichier absent, format illisible), l'image d'origine est utilisée.
    """
    logo = getattr(etablissement, 'logo', None)
    if not logo:
        return ''
    try:
        stockage = logo.storage
        if not stockage.exists(logo.name):
            return ''
        if stockage.size(logo.name) <= POIDS_DEJA_LEGER:
            return logo.url
        version = int(stockage.get_modified_time(logo.name).timestamp())
        base = f'etablissements/logos/impression/{etablissement.pk}-{version}'
        for extension in ('.jpg', '.png'):
            if stockage.exists(base + extension):
                return stockage.url(base + extension)
        from PIL import Image

        with stockage.open(logo.name, 'rb') as fichier:
            origine = fichier.read()
        image = Image.open(BytesIO(origine))
        image.load()
        transparent = image.mode in ('RGBA', 'LA', 'P') and 'transparency' in image.info or image.mode in ('RGBA', 'LA')
        image = image.convert('RGBA' if transparent else 'RGB')
        image.thumbnail((COTE_MAX, COTE_MAX), Image.LANCZOS)
        tampon = BytesIO()
        if transparent:  # la transparence impose le PNG ; sinon le JPEG est bien plus léger
            image.save(tampon, 'PNG', optimize=True)
            extension = '.png'
        else:
            image.save(tampon, 'JPEG', quality=85, optimize=True)
            extension = '.jpg'
        if tampon.tell() >= len(origine):  # réduction sans gain : l'image d'origine reste la meilleure
            return logo.url
        vignette = stockage.save(base + extension, ContentFile(tampon.getvalue()))
        return stockage.url(vignette)
    except Exception:
        logger.warning('Vignette du logo indisponible (établissement %s)', getattr(etablissement, 'pk', '?'),
                       exc_info=True)
        try:
            return logo.url
        except Exception:
            return ''
