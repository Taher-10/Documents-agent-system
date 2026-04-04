"""Tests for the retrieval-scope classification engine."""

from __future__ import annotations

import unittest

from agent_compliance.pdf_parser.parsed_document import ParsedSection, SectionType

from agent_compliance.classification import classify_for_retrieval, derive_scope_from_metadata
from agent_compliance.classification.section_topic_mapper import map_section_to_clauses


class DeriveFromMetadataTests(unittest.TestCase):
    def test_qes_systeme_maps_all_three_domains(self) -> None:
        domains, domain_conf, _, _ = derive_scope_from_metadata({"systeme": "QES"})
        self.assertEqual(domains, ["ISO9001", "ISO14001", "ISO45001"])
        self.assertEqual(domain_conf, 1.0)

    def test_q_only_maps_iso9001(self) -> None:
        domains, domain_conf, _, _ = derive_scope_from_metadata({"systeme": "Q"})
        self.assertEqual(domains, ["ISO9001"])
        self.assertEqual(domain_conf, 1.0)

    def test_missing_systeme_falls_back_to_all_domains_low_confidence(self) -> None:
        domains, domain_conf, _, _ = derive_scope_from_metadata({})
        self.assertEqual(set(domains), {"ISO9001", "ISO14001", "ISO45001"})
        self.assertAlmostEqual(domain_conf, 0.3)

    def test_procedure_doc_type_from_metadata(self) -> None:
        _, _, doc_type, doc_type_conf = derive_scope_from_metadata(
            {"systeme": "Q", "types_documents": "PROCÉDURE", "domaines_documents": "QUALITE"}
        )
        self.assertEqual(doc_type, "procedure")
        self.assertEqual(doc_type_conf, 1.0)

    def test_record_doc_type_from_fiche_de_poste(self) -> None:
        _, _, doc_type, doc_type_conf = derive_scope_from_metadata(
            {"types_documents": "FICHE DE POSTE", "domaines_documents": "PERSONNEL"}
        )
        self.assertEqual(doc_type, "record")
        self.assertEqual(doc_type_conf, 1.0)

    def test_policy_doc_type_from_politique(self) -> None:
        _, _, doc_type, doc_type_conf = derive_scope_from_metadata(
            {"types_documents": "POLITIQUE QUALITÉ"}
        )
        self.assertEqual(doc_type, "policy")
        self.assertEqual(doc_type_conf, 1.0)

    def test_empty_metadata_returns_none_doc_type(self) -> None:
        _, _, doc_type, doc_type_conf = derive_scope_from_metadata(
            {"types_documents": "", "domaines_documents": ""}
        )
        self.assertIsNone(doc_type)
        self.assertEqual(doc_type_conf, 0.0)


class SectionTopicMapperTests(unittest.TestCase):
    def test_internal_audit_title_maps_to_family_9_and_clause_9_2(self) -> None:
        families, specific, evidence, _ = map_section_to_clauses(
            section_title="Audit interne",
            section_text="Le programme d'audit interne définit le calendrier.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.97,
        )
        self.assertIn("9", families)
        self.assertIn("9.2", specific)
        self.assertTrue(len(evidence) >= 1)

    def test_competence_maps_to_family_7_and_clause_7_2(self) -> None:
        families, specific, evidence, _ = map_section_to_clauses(
            section_title="Compétence du personnel",
            section_text="La compétence est évaluée annuellement.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.95,
        )
        self.assertIn("7", families)
        self.assertIn("7.2", specific)

    def test_multiple_families_returned_for_multi_topic_section(self) -> None:
        families, _, _, _ = map_section_to_clauses(
            section_title="Communication et formation",
            section_text="La communication interne inclut la sensibilisation et la compétence.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.9,
        )
        self.assertIn("7", families)

    def test_empty_section_returns_all_empty_with_zero_confidence(self) -> None:
        families, specific, evidence, confidence = map_section_to_clauses(
            section_title="",
            section_text="",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.95,
        )
        self.assertEqual(families, [])
        self.assertEqual(specific, [])
        self.assertEqual(evidence, [])
        self.assertEqual(confidence, 0.0)

    def test_extraction_dampening_reduces_confidence_for_low_quality(self) -> None:
        _, _, _, high_conf = map_section_to_clauses(
            section_title="Audit interne",
            section_text="Le programme d'audit interne.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.95,
        )
        _, _, _, low_conf = map_section_to_clauses(
            section_title="Audit interne",
            section_text="Le programme d'audit interne.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.35,
        )
        self.assertGreater(high_conf, low_conf)

    def test_corrective_action_maps_to_family_10_and_clause_10_2(self) -> None:
        families, specific, _, _ = map_section_to_clauses(
            section_title="Traitement des non-conformités",
            section_text="Les actions correctives sont documentées et suivies.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.9,
        )
        self.assertIn("10", families)
        self.assertIn("10.2", specific)

    def test_management_review_maps_to_family_9_and_clause_9_3(self) -> None:
        families, specific, _, _ = map_section_to_clauses(
            section_title="Revue de direction",
            section_text="La revue de direction est organisée annuellement par la direction.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.9,
        )
        self.assertIn("9", families)
        self.assertIn("9.3", specific)


class ConcentrationHeuristicTests(unittest.TestCase):
    """Verify that concentrated specific-clause evidence outscores scattered evidence."""

    def test_concentrated_evidence_scores_higher_than_scattered(self) -> None:
        # Concentrated: 3 keywords all from 9.2 → strong bonus for family "9"
        families_conc, _, _, conf_conc = map_section_to_clauses(
            section_title="Audit interne",
            section_text="Le programme d'audit interne est planifié par l'auditeur désigné.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.95,
        )
        # Scattered: 1 keyword from 9.2, 1 from 9.3, no title weight
        families_scat, _, _, conf_scat = map_section_to_clauses(
            section_title="Pilotage système",
            section_text="La revue de direction et l'audit sont planifiés annuellement.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.95,
        )
        self.assertIn("9", families_conc)
        self.assertIn("9", families_scat)
        self.assertGreaterEqual(conf_conc, conf_scat)

    def test_specific_clause_alone_promotes_its_family(self) -> None:
        # No direct family-keyword match for "6", but 6.2 specific keywords fire
        families, specific, _, _ = map_section_to_clauses(
            section_title="Objectifs qualité et cibles annuelles",
            section_text="Les objectifs qualité sont mesurables et mis à jour chaque année.",
            domains=["ISO9001"],
            languages=["FR"],
            extraction_confidence=0.95,
        )
        self.assertIn("6", families)
        self.assertIn("6.2", specific)


class ClassifyForRetrievalTests(unittest.TestCase):
    def _make_section(
        self,
        title: str,
        raw_text: str,
        extraction_confidence: float = 0.95,
        section_type: SectionType = SectionType.PROCEDURE_TEXT,
    ) -> ParsedSection:
        return ParsedSection(
            id="test_section",
            section_type=section_type,
            title=title,
            raw_text=raw_text,
            page_range=(1, 2),
            extraction_confidence=extraction_confidence,
        )

    def test_returns_retrieval_scope_instance(self) -> None:
        from agent_compliance.classification import RetrievalScope

        section = self._make_section("Audit interne", "Programme d'audit défini annuellement.")
        scope = classify_for_retrieval(section, {"systeme": "Q", "langue": "FR"})
        self.assertIsInstance(scope, RetrievalScope)

    def test_domains_from_metadata_take_priority(self) -> None:
        section = self._make_section("Texte quelconque", "Contenu de la section.")
        scope = classify_for_retrieval(section, {"systeme": "QE"})
        self.assertEqual(scope.domains, ["ISO9001", "ISO14001"])
        self.assertEqual(scope.domain_confidence, 1.0)

    def test_high_domain_confidence_raises_overall_confidence(self) -> None:
        meta_good = {"systeme": "Q", "types_documents": "PROCÉDURE", "langue": "FR"}
        meta_bad = {"langue": "FR"}
        section = self._make_section("Audit interne", "audit interne programme")
        scope_good = classify_for_retrieval(section, meta_good)
        scope_bad = classify_for_retrieval(section, meta_bad)
        self.assertGreater(scope_good.confidence, scope_bad.confidence)

    def test_audit_section_produces_correct_families_and_clauses(self) -> None:
        section = self._make_section(
            title="Audit interne",
            raw_text="Le programme d'audit interne est planifié chaque année.",
        )
        scope = classify_for_retrieval(
            section,
            {"systeme": "Q", "types_documents": "PROCÉDURE", "langue": "FR"},
        )
        self.assertIn("9", scope.clause_families)
        self.assertIn("9.2", scope.specific_clauses)
        self.assertEqual(scope.doc_type, "procedure")
        self.assertEqual(scope.doc_type_confidence, 1.0)

    def test_accepts_plain_mapping_as_section(self) -> None:
        section_dict = {
            "title": "Audit interne",
            "raw_text": "Programme d'audit interne annuel.",
            "extraction_confidence": 0.9,
        }
        scope = classify_for_retrieval(section_dict, {"systeme": "Q", "langue": "FR"})
        self.assertIn("9", scope.clause_families)

    def test_missing_systeme_falls_back_gracefully(self) -> None:
        section = self._make_section(
            "Action corrective",
            "Traitement de la non-conformité et correction.",
        )
        scope = classify_for_retrieval(section, {"langue": "FR"})
        self.assertEqual(len(scope.domains), 3)
        self.assertAlmostEqual(scope.domain_confidence, 0.3)
        self.assertIsNotNone(scope.notes)


if __name__ == "__main__":
    unittest.main()
