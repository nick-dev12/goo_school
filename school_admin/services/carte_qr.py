"""QR de carte compact : adresse seule, marge blanche et modules carres."""
import base64
from functools import lru_cache
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage


@lru_cache(maxsize=512)
def qr_svg_data_uri(payload):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image(image_factory=SvgPathImage).save(output)
    # Fond blanc explicite, y compris avec une couleur de carte personnalisee.
    svg = output.getvalue().decode('utf-8')
    svg = svg.replace('><path', '><rect width="100%" height="100%" fill="white"/><path', 1)
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode('ascii')
