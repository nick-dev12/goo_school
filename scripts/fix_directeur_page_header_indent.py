from pathlib import Path

ROOT = Path(r"c:\wamp64\www\goo_school\school_admin\templates\school_admin\directeur")
PARTIAL = "{% include 'school_admin/directeur/partials/page_header_back.html' %}"
PARTIAL_DASH = (
    "{% include 'school_admin/directeur/partials/page_header_back.html' "
    "with back_url=directeur_dashboard_url %}"
)

fixed = 0
for path in ROOT.rglob("*.html"):
    text = path.read_text(encoding="utf-8")
    original = text

    for include_line in (PARTIAL, PARTIAL_DASH):
        text = text.replace(
            f"{include_line}\n<div class=\"page-title-section\">",
            f"{include_line}\n          <div class=\"page-title-section\">",
        )
        text = text.replace(
            f"{include_line}\n<div class=\"page-header-main\">",
            f"{include_line}\n          <div class=\"page-header-main\">",
        )

    if text != original:
        path.write_text(text, encoding="utf-8")
        fixed += 1

print(f"fixed {fixed}")
