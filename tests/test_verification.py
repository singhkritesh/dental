from __future__ import annotations

import unittest

from services.verification import (
    enforce_grounded_verification_summary,
    extract_json_object,
    normalize_verification_summary,
)


class VerificationTests(unittest.TestCase):
    def test_extract_json_object(self) -> None:
        raw = (
            'prefix {"coverage_verdict":"Covered","verdict_rationale":"Exam appears.",'
            '"requested_procedure":"Exam","requested_condition":"Preventive",'
            '"covered_procedures":["Exam"],"estimated_copay":"20%",'
            '"prior_authorization_required":"No","annual_maximum":"$1000",'
            '"waiting_periods":"None","notable_exclusions_limitations":"Cosmetic excluded"} suffix'
        )
        obj = extract_json_object(raw)
        self.assertEqual(obj["estimated_copay"], "20%")

    def test_normalize_adds_missing_fields(self) -> None:
        normalized = normalize_verification_summary({"covered_procedures": ["Exam"]})
        self.assertEqual(normalized["covered_procedures"], ["Exam"])
        self.assertEqual(normalized["annual_maximum"], "Not available")
        self.assertEqual(normalized["coverage_verdict"], "Not available")

    def test_enforce_grounded_covered_procedures_filters_unseen_values(self) -> None:
        summary = {
            "covered_procedures": [
                "Periodic Oral Exam",
                "Implant Placement",
            ],
            "coverage_verdict": "Covered",
            "verdict_rationale": "Periodic oral exam appears in policy.",
            "requested_procedure": "Periodic Oral Exam",
            "requested_condition": "Preventive visit",
            "estimated_copay": "20%",
            "prior_authorization_required": "No",
            "annual_maximum": "$1000",
            "waiting_periods": "None",
            "notable_exclusions_limitations": "Cosmetic excluded",
        }
        payer_ref = (
            "Covered procedures include periodic oral exam and bitewing radiographs. "
            "Major services require authorization."
        )
        grounded = enforce_grounded_verification_summary(summary, payer_ref)
        self.assertEqual(grounded["covered_procedures"], ["Periodic Oral Exam"])
        self.assertEqual(grounded["coverage_verdict"], "Covered")

    def test_verdict_needs_manual_review_when_requested_procedure_not_grounded(self) -> None:
        grounded = enforce_grounded_verification_summary(
            {
                "coverage_verdict": "Covered",
                "verdict_rationale": "Implant appears covered.",
                "requested_procedure": "Implant Placement",
                "requested_condition": "Missing tooth",
                "covered_procedures": ["Implant Placement"],
                "estimated_copay": "20%",
                "prior_authorization_required": "No",
                "annual_maximum": "$1000",
                "waiting_periods": "None",
                "notable_exclusions_limitations": "None",
            },
            "Covered procedures include periodic oral exam and bitewing radiographs.",
        )
        self.assertEqual(grounded["coverage_verdict"], "Needs manual review")
        self.assertIn("not explicitly confirmed", grounded["verdict_rationale"])


if __name__ == "__main__":
    unittest.main()
