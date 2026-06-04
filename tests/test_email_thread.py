from __future__ import annotations

import unittest

from services.email_thread import (
    EmailThreadAnalysis,
    ensure_email_reply_has_no_missing_markers,
    extract_latest_message,
    heuristic_analyze_email_thread,
    normalize_email_thread,
    recommend_email_templates,
)


class EmailThreadTests(unittest.TestCase):
    def test_extract_latest_message_removes_quoted_history(self) -> None:
        thread = (
            "Hi, can you confirm my appointment for Friday?\n\n"
            "Thanks,\nJane\n\n"
            "On Thu, Office wrote:\n"
            "> Your appointment is scheduled."
        )
        latest = extract_latest_message(thread)
        self.assertIn("confirm my appointment", latest)
        self.assertNotIn("Your appointment is scheduled", latest)

    def test_heuristic_analysis_detects_billing_intent(self) -> None:
        analysis = heuristic_analyze_email_thread("Why do I owe this balance on my bill?")
        self.assertEqual(analysis.intent, "billing_inquiry")
        self.assertGreater(analysis.confidence, 0)

    def test_normalize_email_thread_limits_size(self) -> None:
        text = normalize_email_thread("x" * 20_000, max_chars=100)
        self.assertEqual(len(text), 100)

    def test_recommend_email_templates_prioritizes_intent_and_email(self) -> None:
        analysis = heuristic_analyze_email_thread("Can you confirm my appointment?")
        ranked = recommend_email_templates(
            templates=[
                {"index": 0, "name": "Billing", "type": "billing_inquiry", "content": "balance"},
                {"index": 1, "name": "Appointment", "type": "appointment_confirmation", "content": "appointment confirm"},
            ],
            analysis=analysis,
            context_text="appointment confirm",
        )
        self.assertEqual(ranked[0]["name"], "Appointment")

    def test_final_email_reply_falls_back_when_missing_markers_remain(self) -> None:
        analysis = EmailThreadAnalysis(
            intent="appointment_confirmation",
            confidence=0.8,
            urgency="normal",
            tone="professional",
            thread_summary="Patient asked to confirm an appointment.",
            latest_message="Can you confirm my appointment?",
            extracted_entities={},
            missing_fields=["appointment_date", "patient_name"],
            risk_flags=[],
            recommended_action="Ask for missing details.",
        )
        cleaned = ensure_email_reply_has_no_missing_markers(
            draft="Subject: Appointment\n\nHello,\n\nYour appointment is Not provided.\n\nBest regards,\nSiligent Dental Provider Team",
            analysis=analysis,
            runtime_fields={},
        )
        self.assertNotIn("Not provided", cleaned)
        self.assertIn("appointment date", cleaned)
        self.assertIn("patient name", cleaned)


if __name__ == "__main__":
    unittest.main()
