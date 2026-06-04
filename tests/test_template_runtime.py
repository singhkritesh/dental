from __future__ import annotations

import unittest

from services.template_runtime import (
    expand_runtime_field_aliases,
    extract_template_placeholders,
    normalize_runtime_fields,
    render_template_with_runtime_fields,
    runtime_fields_to_json_context,
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

    def test_runtime_fields_to_json_context_is_structured(self) -> None:
        block = runtime_fields_to_json_context(
            {
                "member_id": "A123",
                "empty": "",
                "patient_name": "Jane Doe",
            }
        )
        self.assertIn('"trusted_runtime_fields"', block)
        self.assertIn('"member_id": "A123"', block)
        self.assertIn('"patient_name": "Jane Doe"', block)
        self.assertNotIn('"empty"', block)
        self.assertIn("Do not invent missing values", block)

    def test_expand_runtime_field_aliases_adds_canonical_denial_fields(self) -> None:
        expanded = expand_runtime_field_aliases(
            {
                "appeal_reason": "Narrative supports medical necessity.",
                "claim_id": "CLM-123",
                "co_code": "CO-45",
                "dos": "2026-05-01",
                "payer": "Delta Dental",
                "reason_for_denial": "Charge exceeds allowable.",
                "npi": "1234567890",
            }
        )
        self.assertEqual(expanded["appeal_basis"], "Narrative supports medical necessity.")
        self.assertEqual(expanded["claim_or_reference"], "CLM-123")
        self.assertEqual(expanded["date_of_service"], "2026-05-01")
        self.assertEqual(expanded["denial_code"], "CO-45")
        self.assertEqual(expanded["denial_reason"], "Charge exceeds allowable.")
        self.assertEqual(expanded["payer_name"], "Delta Dental")
        self.assertEqual(expanded["provider_npi"], "1234567890")

    def test_expand_runtime_field_aliases_adds_email_exchange_fields(self) -> None:
        expanded = expand_runtime_field_aliases(
            {
                "dob": "1980-01-01",
                "patient_email": "jane@example.test",
                "patient_phone": "555-0100",
                "sender_name": "Jane Doe",
            }
        )
        self.assertEqual(expanded["date_of_birth"], "1980-01-01")
        self.assertEqual(expanded["email"], "jane@example.test")
        self.assertEqual(expanded["phone"], "555-0100")
        self.assertEqual(expanded["requester_name"], "Jane Doe")


if __name__ == "__main__":
    unittest.main()
