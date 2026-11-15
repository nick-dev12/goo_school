"""Reconstruit school_admin/static/school_admin/vendor/ : polices Inter / Poppins et Font Awesome 6.4.0 hébergés
localement (plus aucun appel à Google Fonts ni à cdnjs), avec une police d'icônes réduite aux icônes utilisées
par le site. La police complète reste en secours pour une icône absente de la liste.

À relancer après l'ajout de nouvelles icônes (sinon elles s'affichent quand même, via la police complète, plus
lourde). Outils requis, hors requirements.txt :  pip install fonttools brotli

    python scripts/build_vendor_assets.py . <dossier_de_telechargement>
"""
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(sys.argv[1])
DL = Path(sys.argv[2])
APP = ROOT / 'school_admin'
VENDOR = APP / 'static' / 'school_admin' / 'vendor'
UA = {'User-Agent': 'Mozilla/5.0'}


def fetch(url, dest):
    if not dest.exists():
        req = urllib.request.Request(url, headers=UA)
        dest.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    return dest


# ---------- Polices de texte ----------
def build_text_font(name, css_path):
    out = VENDOR / 'fonts'
    out.mkdir(parents=True, exist_ok=True)
    css = css_path.read_text(encoding='utf-8')
    blocks = re.findall(r'/\* ([a-z-]+) \*/\s*@font-face \{(.*?)\}', css, re.S)
    seen, faces = {}, []
    for subset, body in blocks:
        if subset not in ('latin', 'latin-ext'):
            continue
        url = re.search(r'url\((https://[^)]+)\)', body).group(1)
        weight = re.search(r'font-weight: (\d+)', body).group(1)
        urange = re.search(r'unicode-range: ([^;]+);', body).group(1)
        if url in seen:  # police variable : un seul fichier pour toutes les graisses
            seen[url]['weights'].append(int(weight))
            continue
        face = {'subset': subset, 'url': url, 'weights': [int(weight)], 'range': urange}
        seen[url] = face
        faces.append(face)
    lines = [f'/* {name.capitalize()} — hébergée localement (licence SIL OFL). Sous-ensembles latin et latin étendu. */']
    for f in faces:
        variable = len(f['weights']) > 1
        fname = f"{name}-{'var' if variable else f['weights'][0]}-{f['subset']}.woff2"
        fetch(f['url'], out / fname)
        weight = '100 900' if variable else str(f['weights'][0])
        lines.append(
            f"@font-face{{font-family:'{name.capitalize()}';font-style:normal;font-weight:{weight};"
            f"font-display:swap;src:url({fname}) format('woff2');unicode-range:{f['range']}}}")
    (out / f'{name}.css').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(name, len(faces), 'fichiers')


# ---------- Font Awesome ----------
def used_codepoints():
    css = (DL / 'fa' / 'all.min.css').read_text(encoding='utf-8')
    name_to_cp = {}
    for selectors, cp in re.findall(r'((?:\.fa-[a-z0-9-]+:before,?)+)\{content:"\\([0-9a-f]+)"\}', css):
        for n in re.findall(r'\.fa-([a-z0-9-]+):before', selectors):
            name_to_cp[n] = int(cp, 16)
    names, raw = set(), set()
    for path in list(APP.rglob('*.html')) + list(APP.rglob('*.js')) + list(APP.rglob('*.css')) + list(APP.rglob('*.py')):
        if 'vendor' in path.parts or '__pycache__' in path.parts:
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        names.update(re.findall(r'\bfa-([a-z0-9-]+)', text))
        # Noms construits dynamiquement (« fa-{% if ok %}check{% else %}times{% endif %} », icônes renvoyées par
        # du code) : tout mot du fichier qui est aussi un nom d'icône est gardé. Trop large, mais sans risque.
        if path.suffix in ('.html', '.js', '.py'):
            names.update(t for t in set(re.findall(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', text)) if t in name_to_cp)
        raw.update(int(c, 16) for c in re.findall(r'\\(f[0-9a-f]{3}|e[0-9a-f]{3})\b', text, re.I))
    connues = {n for n in names if n in name_to_cp}
    cps = {name_to_cp[n] for n in connues} | raw
    print('icônes connues utilisées :', len(connues), '— codes directs :', len(raw))
    return cps, connues


def prune_css(css, connues):
    """Ne garde que les règles « .fa-nom:before{content} » des icônes utilisées (les trois quarts du fichier)."""
    def regle(m):
        gardes = [sel for sel in m.group(1).split(',') if re.match(r'\.fa-([a-z0-9-]+):before$', sel).group(1) in connues]
        return ','.join(gardes) + '{content:"' + chr(92) + m.group(2) + '"}' if gardes else ''
    return re.sub(r'((?:\.fa-[a-z0-9-]+:before,?)+)\{content:"' + chr(92) * 2 + r'([0-9a-f]+)"\}', regle, css)


def ranges(cps):
    cps = sorted(cps)
    out, start, prev = [], cps[0], cps[0]
    for c in cps[1:]:
        if c != prev + 1:
            out.append((start, prev))
            start = c
        prev = c
    out.append((start, prev))
    return ','.join(f'U+{a:X}' if a == b else f'U+{a:X}-{b:X}' for a, b in out)


def build_fa():
    out = VENDOR / 'fontawesome'
    (out / 'css').mkdir(parents=True, exist_ok=True)
    (out / 'webfonts').mkdir(parents=True, exist_ok=True)
    cps, connues = used_codepoints()
    extra = []
    families = {
        'fa-solid-900': ('Font Awesome 6 Free', 900, ['Font Awesome 5 Free']),
        'fa-regular-400': ('Font Awesome 6 Free', 400, ['Font Awesome 5 Free']),
        'fa-brands-400': ('Font Awesome 6 Brands', 400, ['Font Awesome 5 Brands']),
    }
    for stem, (family, weight, aliases) in families.items():
        src = DL / 'fa' / f'{stem}.woff2'
        (out / 'webfonts' / f'{stem}.woff2').write_bytes(src.read_bytes())
        cmap = set(TTFont(src).getBestCmap())
        keep = cps & cmap
        if not keep:
            continue
        sub = out / 'webfonts' / f'{stem}-aria.woff2'
        r = subprocess.run([sys.executable, '-m', 'fontTools.subset', str(src), f'--output-file={sub}',
                        '--unicodes=' + ','.join(f'{c:X}' for c in sorted(keep)), '--flavor=woff2',
                        '--layout-features=', '--no-hinting', '--desubroutinize'], capture_output=True)
        if not sub.exists():  # fichier d'origine illisible par l'outil : la police complète (petite) suffit
            print(stem, 'non réduite')
            continue
        for fam in [family] + aliases:
            extra.append(
                f'@font-face{{font-family:"{fam}";font-style:normal;font-weight:{weight};font-display:block;'
                f'src:url(../webfonts/{stem}-aria.woff2) format("woff2");unicode-range:{ranges(keep)}}}')
        print(stem, len(keep), 'glyphes', sub.stat().st_size, 'octets (complète :', src.stat().st_size, ')')
    (out / 'webfonts' / 'fa-v4compatibility.woff2').write_bytes((DL / 'fa' / 'fa-v4compatibility.woff2').read_bytes())
    css = (DL / 'fa' / 'all.min.css').read_text(encoding='utf-8')
    # Seul le format woff2 est hébergé (tous les navigateurs pris en charge le lisent).
    css = re.sub(r',url\(\.\./webfonts/[a-z0-9-]+\.ttf\) format\("truetype"\)', '', css)
    assert '.ttf' not in css
    # Fichier d'origine complet, non chargé par les pages : référence pour le test de non-régression des icônes.
    (out / 'css' / 'all.full.min.css').write_text(css, encoding='utf-8')
    css = prune_css(css, connues)
    css += ('\n/* Aria : police réduite aux icônes utilisées par le site ; la police complète ci-dessus ne se'
            ' télécharge que pour une icône absente de cette liste. */\n' + '\n'.join(extra) + '\n')
    (out / 'css' / 'all.min.css').write_text(css, encoding='utf-8')


def telecharger_sources():
    """Récupère une fois les fichiers d'origine (cdnjs, Google Fonts) dans le dossier de téléchargement."""
    (DL / 'fa').mkdir(parents=True, exist_ok=True)
    (DL / 'fonts').mkdir(parents=True, exist_ok=True)
    base = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/'
    for chemin in ('css/all.min.css', 'webfonts/fa-solid-900.woff2', 'webfonts/fa-regular-400.woff2',
                   'webfonts/fa-brands-400.woff2', 'webfonts/fa-v4compatibility.woff2'):
        fetch(base + chemin, DL / 'fa' / chemin.split('/')[-1])
    global UA  # Google Fonts ne renvoie du woff2 qu'à un navigateur récent
    UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/126.0 Safari/537.36'}
    for nom, famille in (('inter', 'Inter'), ('poppins', 'Poppins')):
        fetch(f'https://fonts.googleapis.com/css2?family={famille}:wght@300;400;500;600;700;800&display=swap',
              DL / 'fonts' / f'{nom}.css')


telecharger_sources()
build_text_font('inter', DL / 'fonts' / 'inter.css')
build_text_font('poppins', DL / 'fonts' / 'poppins.css')
build_fa()
