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

from rag.shared.vocabulary.scanner import scan_iso_vocabulary


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
