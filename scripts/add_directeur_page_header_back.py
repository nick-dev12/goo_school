import re
from pathlib import Path

ROOT = Path(r"c:\wamp64\www\goo_school\school_admin\templates\school_admin\directeur")
PARTIAL = "{% include 'school_admin/directeur/partials/page_header_back.html' %}"

SKIP = {
    "dashboard_directeur.html",
    "header_directeur.html",
    "bottom_nav_directeur.html",
    "page_header_back.html",
}

patterns = [
    re.compile(r'(<div class="page-header">)\s*\n(\s*)(?!(?:{% include .*page_header_back))'),
    re.compile(r'(<header class="page-header">)\s*\n(\s*)(?!(?:{% include .*page_header_back))'),
    re.compile(r'(<div class="page-header-modern">)\s*\n(\s*)(?!(?:{% include .*page_header_back))'),
    re.compile(r'(<div class="page-header-reinscription">)\s*\n(\s*)(?!(?:{% include .*page_header_back))'),
    re.compile(r'(<div class="ec-page-header">)\s*\n(\s*)(?!(?:{% include .*page_header_back))'),
]

updated = []
skipped = []

for path in sorted(ROOT.rglob("*.html")):
    if path.name in SKIP:
        continue
    if path.parent.name == "partials":
        continue

    text = path.read_text(encoding="utf-8")
    if PARTIAL in text:
        skipped.append(str(path.relative_to(ROOT)))
        continue
    if 'class="page-header' not in text and "ec-page-header" not in text:
        continue

    original = text
    for pattern in patterns:
        def repl(match, _pattern=pattern):
            indent = match.group(2)
            include_line = f"{indent}{PARTIAL}\n"
            return f"{match.group(1)}\n{include_line}"

        text = pattern.sub(repl, text, count=1)

    if text != original:
        path.write_text(text, encoding="utf-8")
        updated.append(str(path.relative_to(ROOT)))

print(f"Updated {len(updated)} files")
for file_path in updated:
    print(f" + {file_path}")
print(f"Skipped (already had partial): {len(skipped)}")
