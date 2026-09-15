"""Checks the text cleanup shared by the source-document import tools."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.textjoin import join_wrapped, mend_hyphen


class TextJoinTests(unittest.TestCase):
    def test_wrapped_hyphens_keep_the_intended_spacing(self):
        self.assertEqual(
            join_wrapped(["security-", "and privacy-related"]),
            "security- and privacy-related",
        )
        self.assertEqual(
            join_wrapped(["hardware-", "or software-based"]),
            "hardware- or software-based",
        )
        self.assertEqual(
            join_wrapped(["enterprise-", "wide risk"]),
            "enterprise-wide risk",
        )
        self.assertEqual(
            mend_hyphen("security-\nand\nprivacy"),
            "security- and\nprivacy",
        )


if __name__ == "__main__":
    unittest.main()
