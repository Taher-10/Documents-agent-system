"""Tests for the RetrievalScope Pydantic model."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent_compliance.classification import RetrievalScope


class RetrievalScopeModelTests(unittest.TestCase):
    def test_accepts_valid_payload(self) -> None:
        scope = RetrievalScope(
            domains=["ISO9001", "ISO14001"],
            domain_confidence=0.9,
            doc_type="procedure",
            doc_type_confidence=1.0,
            clause_families=["9"],
            specific_clauses=["9.2"],
            confidence=0.76,
            evidence=["audit interne", "programme d'audit"],
        )
        self.assertEqual(scope.domains, ["ISO9001", "ISO14001"])
        self.assertEqual(scope.clause_families, ["9"])
        self.assertEqual(scope.specific_clauses, ["9.2"])

    def test_deduplicates_domains_preserving_order(self) -> None:
        scope = RetrievalScope(
            domains=["ISO9001", "ISO14001", "ISO9001"],
            domain_confidence=1.0,
            confidence=0.7,
        )
        self.assertEqual(scope.domains, ["ISO9001", "ISO14001"])

    def test_empty_notes_becomes_none(self) -> None:
        scope = RetrievalScope(
            domains=["ISO9001"],
            domain_confidence=0.3,
            confidence=0.5,
            notes="",
        )
        self.assertIsNone(scope.notes)

    def test_rejects_confidence_out_of_range(self) -> None:
        with self.assertRaises(ValidationError):
            RetrievalScope(
                domains=["ISO9001"],
                domain_confidence=0.5,
                confidence=1.5,
            )

    def test_rejects_domain_confidence_out_of_range(self) -> None:
        with self.assertRaises(ValidationError):
            RetrievalScope(
                domains=["ISO9001"],
                domain_confidence=-0.1,
                confidence=0.5,
            )

    def test_optional_fields_have_sensible_defaults(self) -> None:
        scope = RetrievalScope(
            domains=["ISO45001"],
            domain_confidence=1.0,
            confidence=0.6,
        )
        self.assertIsNone(scope.doc_type)
        self.assertEqual(scope.doc_type_confidence, 0.0)
        self.assertEqual(scope.clause_families, [])
        self.assertEqual(scope.specific_clauses, [])
        self.assertEqual(scope.evidence, [])
        self.assertIsNone(scope.notes)


if __name__ == "__main__":
    unittest.main()
