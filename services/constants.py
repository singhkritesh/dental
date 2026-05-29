from __future__ import annotations

DENIAL_CODES: list[dict[str, str]] = [
    {
        "code": "CO-4",
        "description": "The procedure code is inconsistent with the modifier used",
    },
    {
        "code": "CO-6",
        "description": "The procedure/revenue code is inconsistent with the patient's age",
    },
    {
        "code": "CO-16",
        "description": "Claim/service lacks information or has submission errors",
    },
    {
        "code": "CO-22",
        "description": "This care may be covered by another payer per coordination of benefits",
    },
    {
        "code": "CO-29",
        "description": "The time limit for filing has expired",
    },
    {
        "code": "CO-45",
        "description": "Charge exceeds fee schedule/maximum allowable",
    },
    {
        "code": "CO-50",
        "description": "These are non-covered services because this is not deemed a medical necessity",
    },
    {
        "code": "CO-97",
        "description": "The benefit for this service is included in another service/procedure",
    },
    {
        "code": "CO-109",
        "description": "Claim/service not covered by this payer/contractor",
    },
    {
        "code": "CO-119",
        "description": "Benefit maximum for this time period or occurrence has been reached",
    },
]

DENIAL_REQUIRED_FIELDS: tuple[str, ...] = (
    "patient_name",
    "date_of_service",
    "procedure_description",
    "payer_name",
)

VERIFICATION_REQUIRED_FIELDS: tuple[str, ...] = (
    "payer_name",
    "member_id",
    "patient_dob",
)

PLAN_TYPES: tuple[str, ...] = ("PPO", "HMO", "DHMO", "Indemnity", "Other")

VERIFICATION_FIELDS: tuple[str, ...] = (
    "covered_procedures",
    "estimated_copay",
    "prior_authorization_required",
    "annual_maximum",
    "waiting_periods",
    "notable_exclusions_limitations",
)
