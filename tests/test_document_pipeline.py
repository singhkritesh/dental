from __future__ import annotations

import unittest

from services.document_pipeline import (
    MAX_IMAGE_BYTES_FOR_LLM,
    PreparedDocument,
    _is_draft_structurally_valid,
    _is_summary_bullet_draft,
    build_document_generation_context,
    extract_document_content,
    extract_text_from_payload,
    stabilize_structured_output,
    validate_upload_constraints,
)
from services.errors import AppError


class DocumentPipelineTests(unittest.TestCase):
    def test_validate_upload_constraints(self) -> None:
        with self.assertRaises(AppError):
            validate_upload_constraints(0)
        with self.assertRaises(AppError):
            validate_upload_constraints(4)
        validate_upload_constraints(3)

    def test_extract_text_plain_file(self) -> None:
        text = extract_text_from_payload("sample.txt", b"hello world")
        self.assertEqual(text, "hello world")

    def test_extract_text_eml_file(self) -> None:
        text = extract_text_from_payload("thread.eml", b"Subject: Hello\n\nBody")
        self.assertIn("Subject: Hello", text)

    def test_doc_binary_files_are_not_advertised_as_supported(self) -> None:
        with self.assertRaises(AppError) as ctx:
            extract_text_from_payload("legacy.doc", b"\xd0\xcf\x11\xe0binary")
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_FILE_TYPE")

    def test_image_payload_attached_for_llm_when_under_limit(self) -> None:
        item = extract_document_content(
            filename="small.png",
            content_type="image/png",
            payload=b"a" * 1024,
        )
        self.assertEqual(len(item.image_base64_list), 1)

    def test_image_payload_skipped_for_llm_when_over_limit(self) -> None:
        item = extract_document_content(
            filename="large.png",
            content_type="image/png",
            payload=b"a" * (MAX_IMAGE_BYTES_FOR_LLM + 1),
        )
        self.assertEqual(item.image_base64_list, [])

    def test_stabilize_structured_output_fills_low_signal_payload(self) -> None:
        stabilized = stabilize_structured_output(
            structured={
                "title": "Generated Draft",
                "purpose": "Document response",
                "key_points": [],
                "sections": [],
                "action_items": [],
                "final_draft": "Document response",
            },
            detected_template_type="email",
            context_text="[Document: resume.txt] Kritesh Singh is a software engineer with Python and AI experience. "
            "He has led automation projects and improved workflow efficiency.",
        )
        self.assertEqual(stabilized["title"], "Email Draft")
        self.assertIn("Compose a clear email", stabilized["purpose"])
        self.assertGreater(len(stabilized["key_points"]), 0)
        self.assertGreater(len(stabilized["sections"]), 0)
        self.assertIn("Subject:", stabilized["final_draft"])

    def test_summary_bullets_detected_as_invalid_draft(self) -> None:
        draft = "\n".join(
            [
                "- Point one about context",
                "- Point two about context",
                "- Point three about context",
                "- Point four about context",
            ]
        )
        self.assertTrue(_is_summary_bullet_draft(draft))
        self.assertFalse(_is_draft_structurally_valid(template_type="email", final_draft=draft))

    def test_email_structure_validation(self) -> None:
        valid_email = "\n".join(
            [
                "Subject: Appointment confirmation",
                "",
                "Hello Patient,",
                "",
                "We are writing to confirm your appointment details.",
                "",
                "Please reply to confirm.",
                "",
                "Best regards,",
                "Siligent Dental Front Office",
            ]
        )
        self.assertTrue(_is_draft_structurally_valid(template_type="email", final_draft=valid_email))

    def test_build_document_generation_context_separates_runtime_and_sources(self) -> None:
        context = build_document_generation_context(
            documents=[
                PreparedDocument(
                    upload_id="u1",
                    original_name="eob.txt",
                    content_type="text/plain",
                    size_bytes=25,
                    extension=".txt",
                    extracted_text="Claim was denied for missing narrative.",
                    image_base64_list=[],
                )
            ],
            runtime_fields={"patient_name": "Jane Doe", "claim_id": "CLM-1"},
            selected_template_type="denial_letter",
            selected_template_name="Denial Appeal",
        )
        self.assertIn("[Structured Generation Context JSON]", context)
        self.assertIn('"selected_template_type": "denial_letter"', context)
        self.assertIn('"trusted_runtime_fields"', context)
        self.assertIn('"patient_name": "Jane Doe"', context)
        self.assertIn('"source_documents"', context)
        self.assertIn("Claim was denied for missing narrative.", context)


if __name__ == "__main__":
    unittest.main()
