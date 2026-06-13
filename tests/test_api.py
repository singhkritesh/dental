from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    TestClient = None  # type: ignore[assignment]

if TestClient is not None:
    import api.main as api_main
    from services.audit_store import AuditStore
    from services.auth_store import AuthStore
    from services.config import Settings
    from services.field_dictionary_store import FieldDictionaryStore
    from services.model_preferences_store import ModelPreferencesStore
    from services.template_store import TemplateStore
    from services.template_type_store import TemplateTypeStore
    from services.upload_store import UploadStore


class _FakeOllamaClient:
    def list_models(self) -> list[str]:
        return ["gemma:7b"]

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "model_configured": "gemma:7b",
            "model_available": True,
            "available_models": ["gemma:7b"],
        }

    def generate(self, prompt: str, **_: object) -> str:
        if "Return ONLY one valid JSON object" in prompt:
            return (
                '{"coverage_verdict":"Covered","verdict_rationale":"Exam appears in reference.",'
                '"requested_procedure":"Exam","requested_condition":"Preventive visit",'
                '"covered_procedures":["Exam"],"estimated_copay":"20%",'
                '"prior_authorization_required":"No","annual_maximum":"$1000",'
                '"waiting_periods":"None","notable_exclusions_limitations":"Cosmetic excluded"}'
            )
        if "email thread analysis assistant" in prompt:
            return (
                '{"intent":"appointment_confirmation","confidence":0.88,'
                '"urgency":"normal","tone":"professional",'
                '"thread_summary":"Patient asked to confirm appointment.",'
                '"latest_message":"Can you confirm my appointment?",'
                '"extracted_entities":{"patient_name":"Jane Doe"},'
                '"missing_fields":[],"risk_flags":[],'
                '"recommended_action":"Draft a confirmation reply."}'
            )
        if "professional dental office email drafting assistant" in prompt:
            return "Hi Jane, your appointment is confirmed for {{appointment_date}}."
        if "Available template types:" in prompt:
            return '{"detected_type":"email","confidence":0.91,"rationale":"Test classifier"}'
        if "Template type:" in prompt and "Style/template reference:" in prompt:
            return (
                '{"title":"Generated Draft","purpose":"Test purpose",'
                '"key_points":["Point A"],'
                '"sections":[{"heading":"Intro","content":"Body"}],'
                '"action_items":["Action A"],'
                '"final_draft":"Dear {{patient_name}}, member {member_id}."}'
            )
        return "Generated text"


class _FakeOllamaUngroundedEmail(_FakeOllamaClient):
    def generate(self, prompt: str, **_: object) -> str:
        if "Context:" in prompt:
            return (
                "Subject: Appointment Reminder\n\n"
                "Hello,\n\n"
                "We are reminding you of your appointment on 2027-01-01 at 11:00 AM.\n\n"
                "Best regards,\nSiligent Dental Provider Team"
            )
        return super().generate(prompt, **_)


class _FakeOllamaEmailNotProvided(_FakeOllamaClient):
    def generate(self, prompt: str, **_: object) -> str:
        if "email thread analysis assistant" in prompt:
            return (
                '{"intent":"appointment_confirmation","confidence":0.88,'
                '"urgency":"normal","tone":"professional",'
                '"thread_summary":"Patient asked to confirm appointment.",'
                '"latest_message":"Can you confirm my appointment?",'
                '"extracted_entities":{},'
                '"missing_fields":["appointment_date"],"risk_flags":[],'
                '"recommended_action":"Ask for missing details."}'
            )
        if "professional dental office email drafting assistant" in prompt or "DRAFT TO REWRITE" in prompt:
            return (
                "Subject: Appointment Confirmation\n\n"
                "Hello,\n\n"
                "We are confirming your appointment date is Not provided.\n\n"
                "Best regards,\nSiligent Dental Provider Team"
            )
        return super().generate(prompt, **_)


@unittest.skipIf(TestClient is None, "fastapi is not installed in this environment")
class _ApiTestBase(unittest.TestCase):
    auth_enabled = False

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.prompts_dir = self.root / "prompts"
        self.payer_dir = self.root / "data" / "payer_references"
        self.data_dir = self.root / "data"

        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        (self.prompts_dir / "denial_letters").mkdir(parents=True, exist_ok=True)
        (self.prompts_dir / "emails").mkdir(parents=True, exist_ok=True)
        (self.prompts_dir / "document_pipeline").mkdir(parents=True, exist_ok=True)
        (self.prompts_dir / "email_thread").mkdir(parents=True, exist_ok=True)
        self.payer_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "templates.json").write_text("[]", encoding="utf-8")

        (self.prompts_dir / "denial_letters" / "CO-45.txt").write_text(
            "Patient: {patient_name}",
            encoding="utf-8",
        )
        (self.prompts_dir / "emails" / "appointment_reminder.txt").write_text(
            "Context: {additional_context}",
            encoding="utf-8",
        )
        (self.prompts_dir / "insurance_verification.txt").write_text(
            "Return ONLY one valid JSON object\n{payer_reference_text}",
            encoding="utf-8",
        )
        (self.prompts_dir / "document_pipeline" / "detect_template_type.txt").write_text(
            "Available template types: {available_types}\nDocument content:\n{context_text}",
            encoding="utf-8",
        )
        (self.prompts_dir / "document_pipeline" / "structured_output.txt").write_text(
            "Template type: {detected_template_type}\nStyle/template reference:\n"
            "{template_content}\nSource material:\n{context_text}",
            encoding="utf-8",
        )
        (self.prompts_dir / "email_thread" / "analyze_thread.txt").write_text(
            "You are an email thread analysis assistant.\n{thread_context}",
            encoding="utf-8",
        )
        (self.prompts_dir / "email_thread" / "generate_reply.txt").write_text(
            "You are a professional dental office email drafting assistant.\n"
            "{analysis_json}\n{runtime_context}\n{template_content}\n{thread_context}",
            encoding="utf-8",
        )
        (self.payer_dir / "delta_dental.txt").write_text("Delta ref", encoding="utf-8")

        self.settings = Settings(
            root_dir=self.root,
            ollama_url="http://localhost:11434",
            model_name="gemma:7b",
            ollama_health_timeout_sec=5,
            ollama_generate_timeout_sec=180,
            ollama_num_predict=1024,
            ollama_think=False,
            api_key="",
            cors_origins=("http://localhost:3000",),
            prompts_dir=self.prompts_dir,
            data_dir=self.data_dir,
            templates_path=self.data_dir / "templates.json",
            payer_refs_dir=self.payer_dir,
            auth_enabled=self.auth_enabled,
        )

        self._configure_api_globals()
        self.client = TestClient(api_main.create_app())

    def _configure_api_globals(self) -> None:
        api_main.settings = self.settings
        api_main.ollama_client = _FakeOllamaClient()
        api_main.template_store = TemplateStore(self.settings.templates_path)
        api_main.template_type_store = TemplateTypeStore(
            self.settings.data_dir / "template_types.json"
        )
        api_main.field_dictionary_store = FieldDictionaryStore(
            self.settings.data_dir / "field_dictionary.json"
        )
        api_main.model_preferences_store = ModelPreferencesStore(
            self.settings.data_dir / "model_preferences.json",
            self.settings.model_name,
        )
        api_main.auth_store = AuthStore(
            self.settings.data_dir / "users.json",
            self.settings.data_dir / "sessions.json",
            session_hours=self.settings.auth_session_hours,
        )
        api_main.upload_store = UploadStore(
            self.settings.data_dir / "uploads",
            self.settings.data_dir / "uploads_index.json",
        )
        api_main.audit_store = AuditStore(self.settings.data_dir / "audit_events.jsonl")

    @staticmethod
    def _auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


@unittest.skipIf(TestClient is None, "fastapi is not installed in this environment")
class ApiTests(_ApiTestBase):
    auth_enabled = False

    def test_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_field_dictionary_is_available(self) -> None:
        response = self.client.get("/api/field-dictionary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("entries", payload)
        self.assertTrue(
            any(item.get("key") == "patient_name" for item in payload.get("entries", []))
        )

    def test_templates_crud(self) -> None:
        save_resp = self.client.post(
            "/api/templates",
            json={"name": "T1", "type": "email", "content": "Body {{patient_name}}"},
        )
        self.assertEqual(save_resp.status_code, 200)
        list_resp = self.client.get("/api/templates")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()), 1)
        self.assertEqual(list_resp.json()[0]["placeholders"], ["patient_name"])

    def test_insurance_generation_blocks_path_traversal(self) -> None:
        response = self.client.post(
            "/api/insurance-verification/generate",
            json={
                "payer_name": "../prompts/emails/general_inquiry",
                "member_id": "123",
                "group_number": "",
                "patient_dob": "1990-01-01",
                "plan_type": "PPO",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "PAYER_REFERENCE_INVALID_NAME")

    def test_insurance_generation_returns_coverage_verdict(self) -> None:
        response = self.client.post(
            "/api/insurance-verification/generate",
            json={
                "payer_name": "Delta Dental",
                "member_id": "123",
                "group_number": "",
                "patient_dob": "1990-01-01",
                "plan_type": "PPO",
                "requested_procedure": "Exam",
                "requested_condition": "Preventive visit",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["summary"]["coverage_verdict"], ["Covered", "Needs manual review"])
        self.assertEqual(payload["summary"]["requested_procedure"], "Exam")

    def test_dentrix_template_field_resolution(self) -> None:
        response = self.client.post(
            "/api/dentrix/resolve-template-fields",
            json={
                "template_type": "denial_letter",
                "claim": {
                    "claimid": "C-1001",
                    "dateofclaim": "2026-05-01",
                    "patid": "P-10",
                    "insid": "INS-9",
                    "provid": "DR-7",
                },
                "claimadjreason": [
                    {
                        "claimadjgroup": "CO",
                        "claimadjreason": "Not covered under plan",
                        "claimadjamount": "125.00",
                    }
                ],
                "clinicalnote": [{"notetext": "Patient completed required documentation."}],
                "master_refs": {
                    "patient_master": {
                        "P-10": {
                            "id": "P-10",
                            "full_name": "Jane Doe",
                            "dob": "1990-01-02",
                        }
                    },
                    "payer_master": {
                        "INS-9": {
                            "id": "INS-9",
                            "name": "Delta Dental",
                            "address": "PO Box 1000",
                        }
                    },
                    "provider_master": {
                        "DR-7": {"id": "DR-7", "name": "Dr. Smith", "npi": "1234567890"}
                    },
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["can_generate"])
        self.assertEqual(payload["template_type"], "denial_letter")
        self.assertEqual(payload["resolved_fields"]["claim_or_reference"], "C-1001")
        self.assertEqual(payload["resolved_fields"]["patient_name"], "Jane Doe")
        self.assertEqual(payload["resolved_fields"]["payer_name"], "Delta Dental")
        self.assertEqual(payload["missing_required_fields"], [])

    def test_document_pipeline_invalid_upload_does_not_persist_files(self) -> None:
        upload_dir = self.data_dir / "uploads"
        index_path = self.data_dir / "uploads_index.json"
        self.assertEqual(list(upload_dir.glob("*")), [])
        self.assertFalse(index_path.exists())

        response = self.client.post(
            "/api/document-pipeline/generate",
            files=[("files", ("script.exe", b"echo hacked", "application/octet-stream"))],
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "UNSUPPORTED_FILE_TYPE")
        self.assertEqual(list(upload_dir.glob("*")), [])
        self.assertFalse(index_path.exists())

        oversized_payload = b"x" * (20 * 1024 * 1024 + 1)
        response = self.client.post(
            "/api/document-pipeline/generate",
            files=[("files", ("oversized.txt", oversized_payload, "text/plain"))],
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "FILE_TOO_LARGE")
        self.assertEqual(list(upload_dir.glob("*")), [])
        self.assertFalse(index_path.exists())

        response = self.client.post(
            "/api/document-pipeline/generate",
            files=[
                ("files", ("valid.txt", b"example context", "text/plain")),
                ("files", ("empty.txt", b"", "text/plain")),
            ],
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_FILE")
        self.assertEqual(list(upload_dir.glob("*")), [])
        self.assertFalse(index_path.exists())

    def test_document_pipeline_applies_runtime_fields_to_template_and_output(self) -> None:
        save_resp = self.client.post(
            "/api/templates",
            json={
                "name": "Patient Update",
                "type": "email",
                "content": "Template for {{patient_name}} ({member_id})",
            },
        )
        self.assertEqual(save_resp.status_code, 200)
        template_index = save_resp.json()["index"]

        response = self.client.post(
            "/api/document-pipeline/generate",
            data={
                "selected_template_index": str(template_index),
                "runtime_fields": json.dumps(
                    {"patient_name": "Jane Doe", "member_id": "M-8844"}
                ),
            },
            files=[("files", ("input.txt", b"example context", "text/plain"))],
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["runtime_fields_used"]["patient_name"], "Jane Doe")
        self.assertEqual(payload["runtime_fields_used"]["member_id"], "M-8844")
        self.assertEqual(payload["missing_runtime_fields"], [])
        self.assertIn("Jane Doe", payload["rendered_template_preview"])
        self.assertEqual(payload["structured_output"]["final_draft"], "Dear Jane Doe, member M-8844.")

    def test_document_pipeline_rejects_invalid_runtime_fields_json(self) -> None:
        response = self.client.post(
            "/api/document-pipeline/generate",
            data={"runtime_fields": "not-json"},
            files=[("files", ("input.txt", b"example context", "text/plain"))],
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_RUNTIME_FIELDS")

    def test_email_thread_generation_personalizes_from_runtime_fields(self) -> None:
        save_resp = self.client.post(
            "/api/templates",
            json={
                "name": "Appointment Reply",
                "type": "appointment_confirmation",
                "content": "Appointment reply for {{patient_name}} on {{appointment_date}}",
            },
        )
        self.assertEqual(save_resp.status_code, 200)

        response = self.client.post(
            "/api/email-thread/generate",
            data={
                "thread_text": "Can you confirm my appointment?",
                "runtime_fields": json.dumps(
                    {"patient_name": "Jane Doe", "appointment_date": "2026-05-02"}
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["analysis"]["intent"], "appointment_confirmation")
        self.assertEqual(payload["selected_model"], "gemma:7b")
        self.assertIn("2026-05-02", payload["draft"])
        self.assertIn("appointment_date", payload["template_placeholders"])

    def test_email_thread_uses_extracted_entities_for_template_fields(self) -> None:
        save_resp = self.client.post(
            "/api/templates",
            json={
                "name": "Appointment Reply",
                "type": "appointment_confirmation",
                "content": "Appointment reply for {{patient_name}} on {{appointment_date}}",
            },
        )
        self.assertEqual(save_resp.status_code, 200)

        response = self.client.post(
            "/api/email-thread/generate",
            data={
                "thread_text": "Can you confirm my appointment? This is Jane Doe.",
                "runtime_fields": json.dumps({"appointment_date": "2026-05-02"}),
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["runtime_fields_used"]["patient_name"], "Jane Doe")
        self.assertEqual(payload["runtime_fields_used"]["appointment_date"], "2026-05-02")
        self.assertEqual(payload["missing_runtime_fields"], [])

    def test_email_thread_never_returns_not_provided_in_draft(self) -> None:
        api_main.ollama_client = _FakeOllamaEmailNotProvided()
        response = self.client.post(
            "/api/email-thread/generate",
            data={"thread_text": "Can you confirm my appointment?"},
        )
        self.assertEqual(response.status_code, 200)
        draft = response.json()["draft"]
        self.assertNotIn("Not provided", draft)
        self.assertIn("appointment date", draft)

    def test_email_thread_requested_intent_alias_does_not_block_generation(self) -> None:
        response = self.client.post(
            "/api/email-thread/generate",
            data={
                "thread_text": "Can you check whether my insurance is on file?",
                "requested_intent": "insurance_verification",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis"]["intent"], "insurance_update")

    def test_email_thread_unknown_requested_intent_falls_back_to_detection(self) -> None:
        response = self.client.post(
            "/api/email-thread/generate",
            data={
                "thread_text": "Can you confirm my appointment?",
                "requested_intent": "custom_saved_template_type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis"]["intent"], "appointment_confirmation")

    def test_email_thread_requires_text_or_file(self) -> None:
        response = self.client.post("/api/email-thread/generate", data={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "MISSING_VARIABLES")

    def test_email_thread_invalid_upload_does_not_persist_files(self) -> None:
        upload_dir = self.data_dir / "uploads"
        index_path = self.data_dir / "uploads_index.json"

        response = self.client.post(
            "/api/email-thread/generate",
            files=[
                ("files", ("valid.txt", b"example context", "text/plain")),
                ("files", ("empty.txt", b"", "text/plain")),
            ],
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_FILE")
        self.assertEqual(list(upload_dir.glob("*")), [])
        self.assertFalse(index_path.exists())

    def test_email_generation_blocks_ungrounded_facts(self) -> None:
        original_client = api_main.ollama_client
        api_main.ollama_client = _FakeOllamaUngroundedEmail()
        try:
            response = self.client.post(
                "/api/emails/generate",
                json={
                    "scenario": "Appointment Reminder",
                    "additional_context": "Patient requested reminder but no date has been provided.",
                },
            )
        finally:
            api_main.ollama_client = original_client

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "UNGROUNDED_FACTS")

    def test_document_pipeline_invalid_selected_template_falls_back_to_recommendation(self) -> None:
        save_resp = self.client.post(
            "/api/templates",
            json={
                "name": "Fallback Template",
                "type": "email",
                "content": "Fallback {{patient_name}} with {member_id}",
            },
        )
        self.assertEqual(save_resp.status_code, 200)

        response = self.client.post(
            "/api/document-pipeline/generate",
            data={
                "selected_template_index": "9999",
                "runtime_fields": json.dumps(
                    {"patient_name": "Jane Doe", "member_id": "M-8844"}
                ),
            },
            files=[("files", ("input.txt", b"example context", "text/plain"))],
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("Jane Doe", payload["rendered_template_preview"])
        self.assertIn("M-8844", payload["rendered_template_preview"])
        self.assertIn("patient_name", payload["template_placeholders"])


@unittest.skipIf(TestClient is None, "fastapi is not installed in this environment")
class ApiAdminAuthorizationTests(_ApiTestBase):
    auth_enabled = True

    def setUp(self) -> None:
        super().setUp()
        self.admin_token = self._register_and_login("admin", "password123")
        self.staff_token = self._create_staff_user_and_login("staff", "password123")

    def _register_and_login(self, username: str, password: str) -> str:
        register = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "role": "admin"},
        )
        self.assertEqual(register.status_code, 200)
        login = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(login.status_code, 200)
        return str(login.json()["token"])

    def _create_staff_user_and_login(self, username: str, password: str) -> str:
        create = self.client.post(
            "/api/auth/register",
            headers=self._auth(self.admin_token),
            json={"username": username, "password": password, "role": "staff"},
        )
        self.assertEqual(create.status_code, 200)
        login = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(login.status_code, 200)
        return str(login.json()["token"])

    def test_staff_cannot_modify_model_preferences_or_template_types(self) -> None:
        pref_response = self.client.put(
            "/api/model-preferences",
            headers=self._auth(self.staff_token),
            json={
                "use_global_model_for_all": True,
                "global_model": "gemma:7b",
                "per_use_case": {},
            },
        )
        self.assertEqual(pref_response.status_code, 403)

        type_response = self.client.post(
            "/api/template-types",
            headers=self._auth(self.staff_token),
            json={"template_type": "appeal_response"},
        )
        self.assertEqual(type_response.status_code, 403)

        field_response = self.client.put(
            "/api/field-dictionary/custom_field",
            headers=self._auth(self.staff_token),
            json={"label": "Custom Field", "aliases": ["custom"]},
        )
        self.assertEqual(field_response.status_code, 403)

        admin_pref = self.client.put(
            "/api/model-preferences",
            headers=self._auth(self.admin_token),
            json={
                "use_global_model_for_all": False,
                "global_model": "gemma:7b",
                "per_use_case": {
                    "document_ingestion": "gemma:7b",
                },
            },
        )
        self.assertEqual(admin_pref.status_code, 200)

        admin_type = self.client.post(
            "/api/template-types",
            headers=self._auth(self.admin_token),
            json={"template_type": "appeal_response"},
        )
        self.assertEqual(admin_type.status_code, 200)
        self.assertIn("appeal_response", admin_type.json()["template_types"])

        admin_field = self.client.put(
            "/api/field-dictionary/custom_field",
            headers=self._auth(self.admin_token),
            json={"label": "Custom Field", "aliases": ["custom"]},
        )
        self.assertEqual(admin_field.status_code, 200)
        self.assertEqual(admin_field.json()["key"], "custom_field")

        list_field = self.client.get(
            "/api/field-dictionary",
            headers=self._auth(self.admin_token),
        )
        self.assertEqual(list_field.status_code, 200)
        self.assertTrue(
            any(item.get("key") == "custom_field" for item in list_field.json()["entries"])
        )

    def test_staff_cannot_access_admin_operations(self) -> None:
        staff_health = self.client.get("/api/health", headers=self._auth(self.staff_token))
        self.assertEqual(staff_health.status_code, 403)

        admin_health = self.client.get("/api/health", headers=self._auth(self.admin_token))
        self.assertEqual(admin_health.status_code, 200)

    def test_template_visibility_and_delete_permissions(self) -> None:
        shared_resp = self.client.post(
            "/api/templates",
            headers=self._auth(self.admin_token),
            json={
                "name": "Shared Appointment",
                "type": "appointment_confirmation",
                "content": "Shared body",
                "visibility": "shared",
                "tags": ["appointments", "insurance"],
            },
        )
        self.assertEqual(shared_resp.status_code, 200)
        shared_index = shared_resp.json()["index"]

        personal_resp = self.client.post(
            "/api/templates",
            headers=self._auth(self.staff_token),
            json={
                "name": "My Draft",
                "type": "email",
                "content": "Personal body",
            },
        )
        self.assertEqual(personal_resp.status_code, 200)
        personal_index = personal_resp.json()["index"]

        staff_list = self.client.get("/api/templates", headers=self._auth(self.staff_token))
        self.assertEqual(staff_list.status_code, 200)
        staff_templates = staff_list.json()
        self.assertIn("Shared Appointment", [item["name"] for item in staff_templates])
        self.assertIn("My Draft", [item["name"] for item in staff_templates])
        shared_template = next(item for item in staff_templates if item["name"] == "Shared Appointment")
        self.assertEqual(shared_template["tags"], ["appointments", "insurance"])
        self.assertEqual(
            next(item for item in staff_templates if item["name"] == "My Draft")["visibility"],
            "personal",
        )

        other_staff_token = self._create_staff_user_and_login("otherstaff", "password123")
        other_list = self.client.get("/api/templates", headers=self._auth(other_staff_token))
        self.assertEqual(other_list.status_code, 200)
        self.assertIn("Shared Appointment", [item["name"] for item in other_list.json()])
        self.assertNotIn("My Draft", [item["name"] for item in other_list.json()])

        staff_shared_delete = self.client.delete(
            f"/api/templates/{shared_index}",
            headers=self._auth(self.staff_token),
        )
        self.assertEqual(staff_shared_delete.status_code, 403)

        other_personal_delete = self.client.delete(
            f"/api/templates/{personal_index}",
            headers=self._auth(other_staff_token),
        )
        self.assertEqual(other_personal_delete.status_code, 403)

        own_personal_delete = self.client.delete(
            f"/api/templates/{personal_index}",
            headers=self._auth(self.staff_token),
        )
        self.assertEqual(own_personal_delete.status_code, 200)

        admin_shared_delete = self.client.delete(
            f"/api/templates/{shared_index}",
            headers=self._auth(self.admin_token),
        )
        self.assertEqual(admin_shared_delete.status_code, 200)

    def test_omitted_template_visibility_defaults_to_personal_for_admin(self) -> None:
        save_response = self.client.post(
            "/api/templates",
            headers=self._auth(self.admin_token),
            json={
                "name": "Admin Generated Draft",
                "type": "email",
                "content": "Patient-specific content",
            },
        )
        self.assertEqual(save_response.status_code, 200)

        admin_list = self.client.get("/api/templates", headers=self._auth(self.admin_token))
        self.assertEqual(admin_list.status_code, 200)
        admin_template = next(
            item for item in admin_list.json() if item["name"] == "Admin Generated Draft"
        )
        self.assertEqual(admin_template["visibility"], "personal")
        self.assertEqual(admin_template["tags"], [])

        staff_list = self.client.get("/api/templates", headers=self._auth(self.staff_token))
        self.assertEqual(staff_list.status_code, 200)
        self.assertNotIn("Admin Generated Draft", [item["name"] for item in staff_list.json()])

    def test_staff_can_create_custom_template_type_for_personal_save(self) -> None:
        unknown_type_response = self.client.post(
            "/api/templates",
            headers=self._auth(self.staff_token),
            json={
                "name": "New Type Draft",
                "type": "new_staff_type",
                "content": "Body",
            },
        )
        self.assertEqual(unknown_type_response.status_code, 200)

        list_response = self.client.get("/api/templates", headers=self._auth(self.staff_token))
        self.assertEqual(list_response.status_code, 200)
        saved = next(item for item in list_response.json() if item["name"] == "New Type Draft")
        self.assertEqual(saved["type"], "new_staff_type")

        shared_response = self.client.post(
            "/api/templates",
            headers=self._auth(self.staff_token),
            json={
                "name": "Shared Draft",
                "type": "email",
                "content": "Body",
                "visibility": "shared",
            },
        )
        self.assertEqual(shared_response.status_code, 403)

    def test_staff_manual_unknown_template_type_is_allowed(self) -> None:
        upload_dir = self.data_dir / "uploads"
        index_path = self.data_dir / "uploads_index.json"

        response = self.client.post(
            "/api/document-pipeline/generate",
            headers=self._auth(self.staff_token),
            data={"requested_template_type": "staff_created_type"},
            files=[("files", ("input.txt", b"example context", "text/plain"))],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detected_template_type"], "staff_created_type")
        self.assertTrue(list(upload_dir.glob("*")))
        self.assertTrue(index_path.exists())

    def test_self_registration_cannot_create_public_admin(self) -> None:
        self.settings = replace(self.settings, allow_self_register=True)
        api_main.settings = self.settings

        response = self.client.post(
            "/api/auth/register",
            json={"username": "public-admin", "password": "password123", "role": "admin"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "staff")

    def test_admin_can_create_admin_when_self_registration_enabled(self) -> None:
        self.settings = replace(self.settings, allow_self_register=True)
        api_main.settings = self.settings

        response = self.client.post(
            "/api/auth/register",
            headers=self._auth(self.admin_token),
            json={"username": "created-admin", "password": "password123", "role": "admin"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "admin")


if __name__ == "__main__":
    unittest.main()
