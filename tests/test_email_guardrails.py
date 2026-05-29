from __future__ import annotations

import unittest

from services.email_guardrails import (
    build_enforced_email_prompt,
    generate_with_guardrails,
    is_role_and_purpose_compliant,
)


class _FakeOllama:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.prompts: list[str] = []

    def generate(self, prompt: str, **_: object) -> str:
        self.prompts.append(prompt)
        if self._responses:
            return self._responses.pop(0)
        return ""


class EmailGuardrailTests(unittest.TestCase):
    def test_enforced_prompt_contains_role_and_purpose(self) -> None:
        prompt = build_enforced_email_prompt(
            base_prompt="Write an email.",
            purpose_label="Appointment Reminder",
        )
        self.assertIn("Identity lock:", prompt)
        self.assertIn("Required purpose: Appointment Reminder", prompt)
        self.assertIn("BASE TEMPLATE INSTRUCTIONS", prompt)

    def test_compliance_rejects_ai_disclaimer(self) -> None:
        compliant = is_role_and_purpose_compliant(
            draft="As an AI language model, I cannot access your records.",
            purpose_label="General Inquiry Response",
        )
        self.assertFalse(compliant)

    def test_generate_rewrites_when_first_pass_misses_purpose(self) -> None:
        fake = _FakeOllama(
            responses=[
                "Hello, thank you for your message.",
                "Subject: Appointment Reminder\n\nHello,\n\n"
                "We are writing to remind you of your appointment on Tuesday.\n\n"
                "Best regards,\nSiligent Dental Front Office",
            ]
        )
        output = generate_with_guardrails(
            ollama_client=fake,
            base_prompt="Draft appointment reminder.",
            model_name="qwen3.5:4b",
            purpose_label="Appointment Reminder",
        )
        self.assertEqual(len(fake.prompts), 2)
        self.assertIn("appointment", output.lower())
        self.assertIn("we are", output.lower())

    def test_generate_accepts_first_pass_when_purpose_is_met(self) -> None:
        fake = _FakeOllama(
            responses=[
                "Subject: Appointment Confirmation\n\nHi Jane,\n\n"
                "We are confirming your appointment for Friday at 10:00 AM.\n\n"
                "Please let us know if you need to reschedule.\n\n"
                "Best regards,\nSiligent Dental Front Office"
            ]
        )
        output = generate_with_guardrails(
            ollama_client=fake,
            base_prompt="Draft appointment confirmation.",
            model_name="qwen3.5:4b",
            purpose_label="appointment_confirmation",
        )
        self.assertEqual(len(fake.prompts), 1)
        self.assertIn("appointment", output.lower())


if __name__ == "__main__":
    unittest.main()
