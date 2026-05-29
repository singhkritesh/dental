from __future__ import annotations

import unittest

from services.verification import (
    enforce_grounded_verification_summary,
    extract_json_object,
    normalize_verification_summary,
)


class VerificationTests(unittest.TestCase):
    def test_extract_json_object(self) -> None:
        raw = 'prefix {"covered_procedures":["Exam"],"estimated_copay":"20%","prior_authorization_required":"No","annual_maximum":"$1000","waiting_periods":"None","notable_exclusions_limitations":"Cosmetic excluded"} suffix'
        obj = extract_json_object(raw)
        self.assertEqual(obj["estimated_copay"], "20%")

    def test_normalize_adds_missing_fields(self) -> None:
        normalized = normalize_verification_summary({"covered_procedures": ["Exam"]})
        self.assertEqual(normalized["covered_procedures"], ["Exam"])
        self.assertEqual(normalized["annual_maximum"], "Not available")

    def test_enforce_grounded_covered_procedures_filters_unseen_values(self) -> None:
        summary = {
            "covered_procedures": [
                "Periodic Oral Exam",
                "Implant Placement",
            ],
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


if __name__ == "__main__":
    unittest.main()
