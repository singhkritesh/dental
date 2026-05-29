from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.errors import AppError
from services.generation import load_payer_reference


class GenerationSecurityTests(unittest.TestCase):
    def test_load_payer_reference_blocks_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payer_dir = Path(tmp)
            with self.assertRaises(AppError) as ctx:
                load_payer_reference(payer_dir, "../prompts/emails/general_inquiry")
            self.assertEqual(ctx.exception.code, "PAYER_REFERENCE_INVALID_NAME")

    def test_load_payer_reference_reads_valid_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payer_dir = Path(tmp)
            (payer_dir / "delta_dental.txt").write_text("coverage", encoding="utf-8")
            text = load_payer_reference(payer_dir, "Delta Dental")
            self.assertEqual(text, "coverage")


if __name__ == "__main__":
    unittest.main()

