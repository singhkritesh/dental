from __future__ import annotations

import unittest

from services.template_runtime import (
    extract_template_placeholders,
    normalize_runtime_fields,
    render_template_with_runtime_fields,
)


class TemplateRuntimeTests(unittest.TestCase):
    def test_extract_placeholders_supports_double_and_single_braces(self) -> None:
        content = (
            "Patient: {{patient_name}}\n"
            "Member: {member_id}\n"
            "Payer: {{ payer_name }}\n"
            "Literal json: {\"a\": 1}"
        )
        placeholders = extract_template_placeholders(content)
        self.assertEqual(placeholders, ["member_id", "patient_name", "payer_name"])

    def test_render_template_with_runtime_fields_and_missing(self) -> None:
        result = render_template_with_runtime_fields(
            "Hi {{patient_name}}, member {member_id}, plan {{plan_type}}",
            {"patient_name": "Jane Doe", "member_id": "A123"},
            keep_unresolved=True,
        )
        self.assertEqual(result.rendered, "Hi Jane Doe, member A123, plan {{plan_type}}")
        self.assertEqual(result.missing, ["plan_type"])
        self.assertEqual(result.used["patient_name"], "Jane Doe")
        self.assertEqual(result.used["member_id"], "A123")

    def test_normalize_runtime_fields_serializes_nested_values(self) -> None:
        normalized = normalize_runtime_fields(
            {
                "patient_name": " Jane Doe ",
                "coverage": {"annual_max": 1200},
                "active": True,
                "attempts": 2,
            }
        )
        self.assertEqual(normalized["patient_name"], "Jane Doe")
        self.assertEqual(normalized["active"], "true")
        self.assertEqual(normalized["attempts"], "2")
        self.assertIn('"annual_max": 1200', normalized["coverage"])


if __name__ == "__main__":
    unittest.main()
