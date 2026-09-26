"""Aligne les JS liste Vague 1 sur le noyau certificat (hidden + persist)."""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "school_admin" / "static" / "school_admin" / "js" / "directeur"
CORE = (BASE / "certificat_scolarite_liste.js").read_text(encoding="utf-8")

VARIANTS = [
    ("attestation_reussite_liste.js", "atr-niveau-tab", "filterStudentsAttestation", "directeur:attestation-reussite", "Attestations de réussite"),
    ("attestation_conduite_liste.js", "acd-niveau-tab", "filterStudentsAttestationConduite", "directeur:attestation-conduite", "Attestations de conduite"),
    ("fiche_inscription_liste.js", "fic-niveau-tab", "filterStudentsFiche", "directeur:fiche-inscription", "Fiches inscription"),
    ("convocation_liste.js", "cnv-niveau-tab", "filterStudentsConvocation", "directeur:convocation-liste", "Convocations"),
]

for filename, niveau_sel, filter_fn, storage, title in VARIANTS:
    text = CORE.replace("csc-niveau-tab", niveau_sel)
    text = text.replace("filterStudentsCertificat", filter_fn)
    text = text.replace("csc-filter-select", niveau_sel.split("-")[0] + "-filter-select")
    text = text.replace("csc-search-input", niveau_sel.split("-")[0] + "-search-input")
    text = text.replace("directeur:certificat-scolarite", storage)
    text = text.replace("Certificats de scolarité", title)
    (BASE / filename).write_text(text, encoding="utf-8")
    print("patched", filename)
