"""Smoke test: parser → classification engine, correct results verified.

Run directly:
    python agent_compliance/tests/smoketest/smoke_classification.py

Parses real QHSE documents, prints a full classification table for each
section, then runs explicit spot-checks to verify that well-known sections
map to the expected HLS clause families and specific clauses.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repo root is on the path when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DOCS_DIR = _REPO_ROOT / "agent_compliance" / "qhme_docs"

# ---------------------------------------------------------------------------
# Colour helpers (ANSI, no deps)
# ---------------------------------------------------------------------------

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")


# ---------------------------------------------------------------------------
# Table printer
# ---------------------------------------------------------------------------

def _print_table(doc_name: str, results: list[tuple]) -> None:
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}  {doc_name}{RESET}")
    print(f"{BOLD}{'='*80}{RESET}")
    header = f"  {'SECTION TYPE':<16}  {'TITLE':<48}  {'FAM':<10}  {'SPECIFIC':<18}  CONF"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for section, scope in results:
        fam = ",".join(scope.clause_families) or "-"
        spec = ",".join(scope.specific_clauses) or "-"
        title = section.title[:46] + ".." if len(section.title) > 48 else section.title
        print(
            f"  {section.section_type.value:<16}  {title:<48}  {fam:<10}  {spec:<18}  {scope.confidence:.2f}"
        )


# ---------------------------------------------------------------------------
# Spot-check engine
# ---------------------------------------------------------------------------

_failures: list[str] = []


def _check(condition: bool, description: str) -> None:
    if condition:
        _ok(description)
    else:
        _fail(description)
        _failures.append(description)


def _find_section_scope(results: list[tuple], title_fragment: str):
    """Return the scope for the first section whose title contains title_fragment."""
    for section, scope in results:
        if title_fragment.lower() in section.title.lower():
            return section, scope
    return None, None


def _assert_families(results, title_fragment: str, *expected_families: str) -> None:
    section, scope = _find_section_scope(results, title_fragment)
    if scope is None:
        _check(False, f"Section containing '{title_fragment}' not found in document")
        return
    for fam in expected_families:
        _check(
            fam in scope.clause_families,
            f"'{section.title}' → clause family '{fam}' in {scope.clause_families}",
        )


def _assert_specific(results, title_fragment: str, *expected_clauses: str) -> None:
    section, scope = _find_section_scope(results, title_fragment)
    if scope is None:
        _check(False, f"Section containing '{title_fragment}' not found in document")
        return
    for clause in expected_clauses:
        _check(
            clause in scope.specific_clauses,
            f"'{section.title}' → specific clause '{clause}' in {scope.specific_clauses}",
        )


def _assert_doc_type(results, title_fragment: str, expected_doc_type: str) -> None:
    section, scope = _find_section_scope(results, title_fragment)
    if scope is None:
        _check(False, f"Section containing '{title_fragment}' not found in document")
        return
    _check(
        scope.doc_type == expected_doc_type,
        f"'{section.title}' → doc_type='{scope.doc_type}' == '{expected_doc_type}'",
    )


def _assert_domains(results, title_fragment: str, *expected_domains: str) -> None:
    section, scope = _find_section_scope(results, title_fragment)
    if scope is None:
        _check(False, f"Section containing '{title_fragment}' not found in document")
        return
    for domain in expected_domains:
        _check(
            domain in scope.domains,
            f"'{section.title}' → domain '{domain}' in {scope.domains}",
        )


# ---------------------------------------------------------------------------
# Document runners
# ---------------------------------------------------------------------------

def _run_qe_manual(parse_document, docling_to_sections, classify_for_retrieval) -> list[tuple]:
    filename = "3.-Environmental-_-Quality-Management-System-Manual.pdf"
    path = DOCS_DIR / filename
    if not path.exists():
        print(f"{YELLOW}  SKIP{RESET}  {filename} not found — skipping")
        return []

    print(f"\n{BOLD}Parsing:{RESET} {filename}")
    result = parse_document(str(path))
    sections = docling_to_sections(result)
    meta = {"systeme": "QE", "types_documents": "MANUEL", "langue": "EN"}

    results = [(s, classify_for_retrieval(s, meta)) for s in sections]
    _print_table(filename, results)

    print(f"\n{BOLD}--- Spot-checks: QE Manual ---{RESET}")

    # Domain wiring — systeme=QE must always give ISO9001 + ISO14001
    _assert_domains(results, "Leadership", "ISO9001", "ISO14001")
    _assert_domains(results, "Performance Evaluation", "ISO9001", "ISO14001")

    # Clause 5 — Leadership section
    _assert_families(results, "5. Leadership", "5")

    # Clause 6 — Environmental Aspects → 6.1
    _assert_families(results, "Environmental Aspects", "6")
    _assert_specific(results, "Environmental Aspects", "6.1")

    # Clause 6.1.3 — Compliance Obligations → 6.1
    _assert_families(results, "Compliance Obligations", "6")
    _assert_specific(results, "Compliance Obligations", "6.1")

    # Clause 7.5 — Documented Information
    _assert_families(results, "Documented Information", "7")
    _assert_specific(results, "Documented Information", "7.5")

    # Clause 7.2 — Competence/training
    # Use "7.1.2 People" (no dot after 2) to skip the TOC stub "7.1.2. People"
    # that appears earlier with an empty body.
    _assert_families(results, "7.1.2 People", "7")
    _assert_specific(results, "7.1.2 People", "7.2")

    # Clause 8.4 — Outsourced Processes
    _assert_families(results, "Outsourced Processes", "8")
    _assert_specific(results, "Outsourced Processes", "8.4")

    # Clause 9 — Performance Evaluation top-level
    _assert_families(results, "Performance Evaluation", "9")

    # Clause 9.1 — Customer Satisfaction
    _assert_specific(results, "Customer Satisfaction", "9.1")

    # Clause 9.3 — Management Review
    _assert_families(results, "Management Review", "9")
    _assert_specific(results, "Management Review", "9.3")

    # Clause 10 — Improvement
    _assert_families(results, "10. Improvement", "10")

    # Clause 10.2 — Nonconformity & Corrective Action
    _assert_families(results, "Non-conformity", "10")
    _assert_specific(results, "Non-conformity", "10.2")

    return results


def _run_procedure(parse_document, docling_to_sections, classify_for_retrieval) -> list[tuple]:
    filename = "PQ-PROD-01 02 Procédure de gestion des gabarits.pdf"
    path = DOCS_DIR / filename
    if not path.exists():
        print(f"{YELLOW}  SKIP{RESET}  {filename} not found — skipping")
        return []

    print(f"\n{BOLD}Parsing:{RESET} {filename}")
    result = parse_document(str(path))
    sections = docling_to_sections(result)
    meta = {"systeme": "Q", "types_documents": "PROCÉDURE", "langue": "FR"}

    results = [(s, classify_for_retrieval(s, meta)) for s in sections]
    _print_table(filename, results)

    print(f"\n{BOLD}--- Spot-checks: Procédure gabarits ---{RESET}")

    # Domain always ISO9001 (systeme=Q)
    for section, scope in results:
        _check(
            scope.domains == ["ISO9001"],
            f"'{section.title}' → domains=['ISO9001'] (got {scope.domains})",
        )
        break  # one representative check is enough

    # All sections classified as procedure
    procedure_count = sum(1 for _, scope in results if scope.doc_type == "procedure")
    _check(
        procedure_count == len(results),
        f"All {len(results)} sections → doc_type='procedure' ({procedure_count}/{len(results)})",
    )

    # Scope section → family 4 or 8 (domaine d'application)
    _assert_families(results, "Domaine d'application", "4")

    # At least one section fires a clause family
    any_families = any(len(scope.clause_families) > 0 for _, scope in results)
    _check(any_families, "At least one section produces clause families")

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        from agent_compliance.pdf_parser import docling_to_sections, parse_document
    except ImportError as exc:
        print(f"{RED}ERROR{RESET}: cannot import parser — {exc}")
        print("Install docling: pip install docling")
        return 1

    from agent_compliance.classification import classify_for_retrieval

    print(f"{BOLD}Classification smoke test{RESET}")
    print(f"Repo root: {_REPO_ROOT}")

    _run_qe_manual(parse_document, docling_to_sections, classify_for_retrieval)
    _run_procedure(parse_document, docling_to_sections, classify_for_retrieval)

    print(f"\n{BOLD}{'='*80}{RESET}")
    if _failures:
        print(f"{RED}{BOLD}FAILED — {len(_failures)} check(s) did not pass:{RESET}")
        for msg in _failures:
            print(f"  • {msg}")
        return 1
    else:
        print(f"{GREEN}{BOLD}ALL CHECKS PASSED{RESET}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
