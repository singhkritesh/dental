from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.errors import AppError
from services.prompt_engine import compose_prompt, validate_required_fields


class PromptEngineTests(unittest.TestCase):
    def test_validate_required_fields_raises(self) -> None:
        with self.assertRaises(AppError) as ctx:
            validate_required_fields({"patient_name": ""}, ("patient_name",))
        self.assertEqual(ctx.exception.code, "MISSING_VARIABLES")

    def test_compose_prompt_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp)
            (prompt_dir / "sample.txt").write_text("Hello {name}", encoding="utf-8")
            value = compose_prompt(prompt_dir, "sample", {"name": "Alex"})
            self.assertEqual(value, "Hello Alex")

    def test_compose_prompt_missing_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AppError) as ctx:
                compose_prompt(Path(tmp), "missing", {})
            self.assertEqual(ctx.exception.code, "TEMPLATE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()

