import re
from pathlib import Path

ROOT = Path(r"c:\wamp64\www\goo_school\school_admin\templates\school_admin\directeur")
PARTIAL_MARKER = "page_header_back.html"

back_link_pattern = re.compile(
    r"\n[ \t]*<a[^>]*class=\"[^\"]*(?:btn-back|btn-secondary)[^\"]*\"[^>]*>\s*"
    r"<i class=\"fas fa-arrow-left\"[^>]*></i>\s*"
    r"(?:<span>)?\s*(?:\{% trans \"[^\"]+\" %\}|[^<]+?)\s*(?:</span>)?\s*"
    r"</a>",
    re.MULTILINE,
)

empty_page_actions_pattern = re.compile(
    r"\n[ \t]*<div class=\"page-actions\"[^>]*>\s*\n[ \t]*</div>",
    re.MULTILINE,
)

updated = 0
for path in ROOT.rglob("*.html"):
    if path.parent.name == "partials":
        continue
    text = path.read_text(encoding="utf-8")
    if PARTIAL_MARKER not in text:
        continue
    original = text
    text = back_link_pattern.sub("", text)
    text = empty_page_actions_pattern.sub("", text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        updated += 1
        print(path.relative_to(ROOT))

print(f"\nRemoved duplicates in {updated} files")
