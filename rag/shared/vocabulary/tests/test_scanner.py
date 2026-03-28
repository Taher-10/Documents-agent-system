"""
tests/test_scanner.py
─────────────────────
Unit tests for scan_iso_vocabulary() word-boundary matching.

Critical invariant: short surface forms like "NC" must only match as
standalone words, never as substrings inside longer words ("influencer",
"performances", "fonctions").

Run:
    pytest rag/shared/vocabulary/tests/test_scanner.py -v
"""
import unittest

from rag.shared.vocabulary.scanner import (
    scan_iso_vocabulary,
    MODAL_TERMS,
    MODAL_TERMS_EN,
    MODAL_TERMS_FR,
)


class TestNCFalsePositiveFR(unittest.TestCase):
    """'NC' inside common French words must NOT trigger non-conformité."""

    def test_nc_inside_influencer_no_hit(self):
        text = "L'organisme doit influencer ses processus externes."
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)

    def test_nc_inside_performances_no_hit(self):
        text = "surveiller les performances de l'organisme"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)

    def test_nc_inside_fonctions_no_hit(self):
        text = "les fonctions et responsabilités définies"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)

    def test_nc_inside_lancement_no_hit(self):
        text = "le lancement du nouveau produit est planifié"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)

    def test_nc_inside_tendances_no_hit(self):
        text = "analyser les tendances des résultats"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)


class TestNCTruePositiveFR(unittest.TestCase):
    """Standalone 'NC' MUST trigger non-conformité."""

    def test_standalone_nc_hits(self):
        text = "un NC a été détecté lors de l'audit"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertIn("non-conformité", hits)

    def test_nc_at_start_of_text_hits(self):
        text = "NC détectée sur la ligne de production"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertIn("non-conformité", hits)

    def test_nc_at_end_of_text_hits(self):
        text = "le produit a été rejeté pour NC"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertIn("non-conformité", hits)

    def test_nc_with_punctuation_hits(self):
        text = "traitement de la NC, clôture de l'action"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertIn("non-conformité", hits)


class TestNCFalsePositiveEN(unittest.TestCase):
    """'NC' inside common English words must NOT trigger nonconformity."""

    def test_nc_inside_incremental_no_hit(self):
        text = "an incremental approach to improvement"
        hits = scan_iso_vocabulary(text, language="EN", norm_filter=["ISO9001"])
        self.assertNotIn("nonconformity", hits)

    def test_nc_inside_balanced_no_hit(self):
        text = "balanced scorecard for performance management"
        hits = scan_iso_vocabulary(text, language="EN", norm_filter=["ISO9001"])
        self.assertNotIn("nonconformity", hits)


class TestNCTruePositiveEN(unittest.TestCase):
    """Standalone 'NC' MUST trigger nonconformity in EN."""

    def test_standalone_nc_hits(self):
        text = "the NC was identified during the audit"
        hits = scan_iso_vocabulary(text, language="EN", norm_filter=["ISO9001"])
        self.assertIn("nonconformity", hits)

    def test_nc_uppercase_hits(self):
        text = "Track each NC through to closure"
        hits = scan_iso_vocabulary(text, language="EN", norm_filter=["ISO9001"])
        self.assertIn("nonconformity", hits)


class TestModalTermsFR(unittest.TestCase):
    """French modal terms: true positives and word-boundary guards."""

    def test_doit_standalone_hits(self):
        text = "L'organisme doit établir une procédure documentée."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("doit", hits)

    def test_doit_inside_endroit_no_hit(self):
        text = "l'endroit où les documents sont conservés"
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertNotIn("doit", hits)

    def test_doivent_standalone_hits(self):
        text = "Les parties intéressées doivent être identifiées."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("doivent", hits)

    def test_peut_standalone_hits(self):
        text = "L'organisme peut choisir de documenter."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("peut", hits)

    def test_peuvent_standalone_hits(self):
        text = "Ces méthodes peuvent être combinées."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("peuvent", hits)

    def test_peut_does_not_match_inside_peuvent(self):
        text = "Les critères peuvent être définis localement."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("peuvent", hits)
        self.assertNotIn("peut", hits)

    def test_il_convient_hits(self):
        text = "Il convient d'évaluer les risques associés."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("il convient", hits)

    def test_est_tenu_de_hits(self):
        text = "L'organisme est tenu de conserver des informations documentées."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("est tenu de", hits)

    def test_est_permis_hits(self):
        text = "Il est permis d'utiliser d'autres méthodes."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("est permis", hits)

    def test_il_est_possible_de_hits(self):
        text = "Il est possible de combiner les processus."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("il est possible de", hits)


class TestModalTermsEN(unittest.TestCase):
    """English modal terms must continue to work after the FR split."""

    def test_shall_hits(self):
        text = "The organization shall establish a QMS."
        hits = scan_iso_vocabulary(text, language="EN")
        self.assertIn("shall", hits)

    def test_should_hits(self):
        text = "The organization should consider stakeholder needs."
        hits = scan_iso_vocabulary(text, language="EN")
        self.assertIn("should", hits)

    def test_may_hits(self):
        text = "The organization may choose to document this."
        hits = scan_iso_vocabulary(text, language="EN")
        self.assertIn("may", hits)

    def test_must_hits(self):
        text = "Records must be retained for a defined period."
        hits = scan_iso_vocabulary(text, language="EN")
        self.assertIn("must", hits)

    def test_is_required_to_hits(self):
        text = "The supplier is required to demonstrate conformity."
        hits = scan_iso_vocabulary(text, language="EN")
        self.assertIn("is required to", hits)

    def test_can_hits(self):
        text = "The audit team can include external members."
        hits = scan_iso_vocabulary(text, language="EN")
        self.assertIn("can", hits)

    def test_modal_terms_alias_is_en_list(self):
        """MODAL_TERMS backward-compat alias must be the same object as MODAL_TERMS_EN."""
        self.assertIs(MODAL_TERMS, MODAL_TERMS_EN)


class TestModalLanguageIsolation(unittest.TestCase):
    """Language gate must prevent cross-language modal hits."""

    def test_fr_modal_text_with_en_language_no_fr_hits(self):
        text = "L'organisme doit établir une procédure."
        hits = scan_iso_vocabulary(text, language="EN")
        self.assertNotIn("doit", hits)

    def test_en_modal_text_with_fr_language_no_en_hits(self):
        text = "The organization shall document its processes."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertNotIn("shall", hits)

    def test_mixed_text_en_language_only_en_modals(self):
        text = "The organization shall comply. L'organisme doit aussi."
        hits = scan_iso_vocabulary(text, language="EN")
        self.assertIn("shall", hits)
        self.assertNotIn("doit", hits)

    def test_mixed_text_fr_language_only_fr_modals(self):
        text = "The organization shall comply. L'organisme doit aussi."
        hits = scan_iso_vocabulary(text, language="FR")
        self.assertIn("doit", hits)
        self.assertNotIn("shall", hits)

    def test_default_language_is_en(self):
        text = "The organization shall establish procedures."
        hits = scan_iso_vocabulary(text)
        self.assertIn("shall", hits)
        self.assertNotIn("doit", hits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
