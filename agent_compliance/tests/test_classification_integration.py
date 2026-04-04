"""Integration test: parser → classification engine end-to-end.

Parses real PDFs from agent_compliance/qhme_docs/ and passes every extracted
section through classify_for_retrieval().  No ground-truth clause assertions —
the test verifies structural correctness of the output and that the pipeline
does not raise.
"""

from __future__ import annotations

import unittest
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parents[1] / "qhme_docs"

# Fixtures: (filename, registry_metadata_hint)
FIXTURES: list[tuple[str, dict]] = [
    (
        "PQ-PROD-01 02 Procédure de gestion des gabarits.pdf",
        {"systeme": "Q", "types_documents": "PROCÉDURE", "langue": "FR"},
    ),
    (
        "ReportJobDescriptionFiche01 (1).pdf",
        {"types_documents": "FICHE DE POSTE", "domaines_documents": "PERSONNEL", "langue": "FR"},
    ),
    (
        "3.-Environmental-_-Quality-Management-System-Manual.pdf",
        {"systeme": "QE", "types_documents": "MANUEL", "langue": "EN"},
    ),
]


def _load_parser():
    """Import parse_document and docling_to_sections; skip if docling unavailable."""
    try:
        from agent_compliance.pdf_parser import docling_to_sections, parse_document

        return parse_document, docling_to_sections
    except ImportError:
        return None, None


class ClassificationIntegrationTests(unittest.TestCase):
    """Parse real documents then classify every section."""

    @classmethod
    def setUpClass(cls) -> None:
        parse_document, docling_to_sections = _load_parser()
        if parse_document is None:
            cls._skip_reason = "docling not installed"
            return

        cls._skip_reason = None
        cls._parse_document = staticmethod(parse_document)
        cls._docling_to_sections = staticmethod(docling_to_sections)

        from agent_compliance.classification import classify_for_retrieval

        cls._classify = staticmethod(classify_for_retrieval)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _skip_if_unavailable(self) -> None:
        if getattr(self, "_skip_reason", None):
            self.skipTest(self._skip_reason)

    def _parse_and_classify(
        self, filename: str, metadata: dict
    ) -> list[tuple[object, object]]:
        """Parse one fixture file and classify all its sections.

        Returns list of (section, scope) pairs.
        """
        path = DOCS_DIR / filename
        if not path.exists():
            self.skipTest(f"Fixture not found: {path}")

        parse_result = self._parse_document(str(path))
        sections = self._docling_to_sections(parse_result)
        self.assertGreater(len(sections), 0, "Parser returned no sections")

        results = []
        for section in sections:
            scope = self._classify(section, metadata)
            results.append((section, scope))
        return results

    # ------------------------------------------------------------------
    # Structural validity assertions (domain-agnostic)
    # ------------------------------------------------------------------

    def _assert_scope_valid(self, scope, *, section_title: str) -> None:
        from agent_compliance.classification import RetrievalScope

        self.assertIsInstance(scope, RetrievalScope, f"Expected RetrievalScope for '{section_title}'")

        self.assertGreater(len(scope.domains), 0, f"No domains for '{section_title}'")
        self.assertGreaterEqual(scope.domain_confidence, 0.0)
        self.assertLessEqual(scope.domain_confidence, 1.0)
        self.assertGreaterEqual(scope.confidence, 0.0)
        self.assertLessEqual(scope.confidence, 1.0)

        for family in scope.clause_families:
            self.assertRegex(family, r"^\d+$", f"Bad family '{family}' in '{section_title}'")
            self.assertIn(int(family), range(4, 11), f"Family {family} outside 4–10 for '{section_title}'")

        for clause in scope.specific_clauses:
            self.assertRegex(clause, r"^\d+\.\d+$", f"Bad specific clause '{clause}' in '{section_title}'")
            family_of = clause.split(".")[0]
            self.assertIn(
                family_of,
                scope.clause_families,
                f"Specific clause {clause} has no parent family in clause_families for '{section_title}'",
            )

        if scope.doc_type is not None:
            self.assertIn(
                scope.doc_type,
                ("policy", "procedure", "record"),
                f"Unknown doc_type '{scope.doc_type}' for '{section_title}'",
            )
            self.assertGreater(scope.doc_type_confidence, 0.0)

    # ------------------------------------------------------------------
    # Per-fixture tests
    # ------------------------------------------------------------------

    def test_procedure_document_classifies_all_sections(self) -> None:
        self._skip_if_unavailable()
        filename, metadata = FIXTURES[0]
        results = self._parse_and_classify(filename, metadata)

        for section, scope in results:
            self._assert_scope_valid(scope, section_title=section.title)

        # At least one section should resolve doc_type = "procedure"
        doc_types = {scope.doc_type for _, scope in results}
        self.assertIn("procedure", doc_types, "Expected at least one section classified as procedure")

        # Domain must be ISO9001 (systeme=Q)
        for _, scope in results:
            self.assertEqual(scope.domains, ["ISO9001"])
            self.assertEqual(scope.domain_confidence, 1.0)

    def test_job_description_classifies_all_sections(self) -> None:
        self._skip_if_unavailable()
        filename, metadata = FIXTURES[1]
        results = self._parse_and_classify(filename, metadata)

        for section, scope in results:
            self._assert_scope_valid(scope, section_title=section.title)

        # Missing systeme → all 3 domains at low confidence, OR record doc_type
        for _, scope in results:
            self.assertGreater(len(scope.domains), 0)

    def test_qe_manual_classifies_all_sections(self) -> None:
        self._skip_if_unavailable()
        filename, metadata = FIXTURES[2]
        results = self._parse_and_classify(filename, metadata)

        for section, scope in results:
            self._assert_scope_valid(scope, section_title=section.title)

        # systeme=QE → ISO9001 + ISO14001 on every section
        for _, scope in results:
            self.assertIn("ISO9001", scope.domains)
            self.assertIn("ISO14001", scope.domains)
            self.assertEqual(scope.domain_confidence, 1.0)

    # ------------------------------------------------------------------
    # Cross-fixture: at least some sections must match clauses
    # ------------------------------------------------------------------

    def test_at_least_one_section_produces_clause_families(self) -> None:
        """Sanity check: the QHSE keyword map fires at least once per document."""
        self._skip_if_unavailable()
        for filename, metadata in FIXTURES:
            with self.subTest(file=filename):
                results = self._parse_and_classify(filename, metadata)
                any_families = any(len(scope.clause_families) > 0 for _, scope in results)
                self.assertTrue(
                    any_families,
                    f"No clause families matched in any section of {filename}",
                )


if __name__ == "__main__":
    unittest.main()
