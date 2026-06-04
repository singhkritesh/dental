from __future__ import annotations

import unittest
from pathlib import Path

from services.dentrix_mapping import resolve_dentrix_template_fields


class DentrixMappingTests(unittest.TestCase):
    def test_resolve_denial_letter_fields(self) -> None:
        result = resolve_dentrix_template_fields(
            template_type="denial_letter",
            claim={
                "claimid": "CLM-1",
                "dateofclaim": "2026-05-03",
                "patid": "PAT-1",
                "insid": "INS-1",
                "provid": "PROV-1",
            },
            claimadjreason=[
                {
                    "claimadjgroup": "CO",
                    "claimadjreason": "Benefit not covered",
                    "claimadjamount": "80.00",
                }
            ],
            clinicalnote=[{"notetext": "Additional x-rays submitted."}],
            master_refs={
                "patient_master": {"PAT-1": {"id": "PAT-1", "full_name": "John Carter"}},
                "payer_master": {
                    "INS-1": {"id": "INS-1", "name": "Delta Dental", "address": "PO Box 500"}
                },
                "provider_master": {
                    "PROV-1": {"id": "PROV-1", "name": "Dr. Adams", "npi": "1234567890"}
                },
            },
            spec_path=Path("docs/DENTRIX_FIELD_MAPPING_SPEC.json"),
        )
        self.assertEqual(result.template_type, "denial_letter")
        self.assertTrue(result.can_generate)
        self.assertEqual(result.missing_required_fields, [])
        self.assertEqual(result.resolved_fields["claim_or_reference"], "CLM-1")
        self.assertEqual(result.resolved_fields["patient_name"], "John Carter")
        self.assertEqual(result.resolved_fields["payer_name"], "Delta Dental")

    def test_missing_required_fields_are_reported(self) -> None:
        result = resolve_dentrix_template_fields(
            template_type="insurance_verification",
            claim={"claimid": "CLM-2", "insid": "INS-2"},
            master_refs={"payer_master": {"INS-2": {"id": "INS-2", "name": "Payer 2"}}},
            spec_path=Path("docs/DENTRIX_FIELD_MAPPING_SPEC.json"),
        )
        self.assertFalse(result.can_generate)
        self.assertIn("member_id", result.missing_required_fields)
        self.assertIn("patient_dob", result.missing_required_fields)

    def test_claim_scoping_filters_unrelated_rows(self) -> None:
        result = resolve_dentrix_template_fields(
            template_type="denial_letter",
            claim={
                "claimid": "CLM-1",
                "dateofclaim": "2026-05-03",
                "patid": "PAT-1",
                "insid": "INS-1",
            },
            claimadjreason=[
                {
                    "claimid": "CLM-1",
                    "claimadjgroup": "CO",
                    "claimadjreason": "Coverage limit reached",
                    "claimadjamount": "30.00",
                },
                {
                    "claimid": "CLM-OTHER",
                    "claimadjgroup": "PR",
                    "claimadjreason": "Unrelated claim reason",
                    "claimadjamount": "999.00",
                },
            ],
            claimstatusnotelink=[
                {"claimid": "CLM-1", "noteid": "N-1", "notestatus": "pending"},
                {"claimid": "CLM-OTHER", "noteid": "N-2", "notestatus": "denied"},
            ],
            clinicalnote=[
                {"cnotesid": "N-1", "notetext": "Relevant note"},
                {"cnotesid": "N-2", "notetext": "Unrelated note"},
            ],
            master_refs={
                "patient_master": {"PAT-1": {"id": "PAT-1", "full_name": "John Carter"}},
                "payer_master": {"INS-1": {"id": "INS-1", "name": "Delta Dental"}},
            },
            spec_path=Path("docs/DENTRIX_FIELD_MAPPING_SPEC.json"),
        )
        rationale = result.resolved_fields["supporting_rationale"]
        self.assertIn("Coverage limit reached", rationale)
        self.assertIn("Relevant note", rationale)
        self.assertNotIn("Unrelated claim reason", rationale)
        self.assertNotIn("Unrelated note", rationale)


if __name__ == "__main__":
    unittest.main()
