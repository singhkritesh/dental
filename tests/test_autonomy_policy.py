from __future__ import annotations

import unittest

from services.autonomy_policy import evaluate_draft_grounding
from services.errors import AppError
from services.autonomy_policy import enforce_draft_grounding_or_raise


class AutonomyPolicyTests(unittest.TestCase):
    def test_grounding_allows_facts_present_in_trusted_sources(self) -> None:
        draft = (
            "Subject: Appointment Confirmation\n\n"
            "Your appointment is on 2026-05-14 at 10:30 AM. "
            "Member ID: M-8844."
        )
        trusted = [
            "appointment_date: 2026-05-14",
            "appointment_time: 10:30 AM",
            "member_id: M-8844",
        ]
        result = evaluate_draft_grounding(draft=draft, trusted_sources=trusted)
        self.assertEqual(result.ungrounded_values, [])

    def test_grounding_flags_untrusted_facts(self) -> None:
        draft = "Call us at (555) 123-4567 on 2026-08-19."
        trusted = ["No phone in context", "No date in context"]
        result = evaluate_draft_grounding(draft=draft, trusted_sources=trusted)
        self.assertIn("(555) 123-4567", result.ungrounded_values)
        self.assertIn("2026-08-19", result.ungrounded_values)

    def test_enforcement_raises_on_ungrounded_facts(self) -> None:
        with self.assertRaises(AppError):
            enforce_draft_grounding_or_raise(
                draft="Estimated copay is $300.",
                trusted_sources=["copay unknown"],
                use_case="insurance response",
            )


if __name__ == "__main__":
    unittest.main()
