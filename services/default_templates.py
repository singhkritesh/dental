from __future__ import annotations

from services.template_type_store import normalize_template_type


def _default_template_name(template_type: str) -> str:
    pretty = " ".join(part.capitalize() for part in template_type.split("_") if part)
    return f"Default {pretty} Template".strip()


def _default_template_tags(template_type: str) -> list[str]:
    return ["default", "starter", template_type]


def _default_template_content(template_type: str) -> str:
    if template_type == "appointment_confirmation_sms":
        return (
            "Hi {first_name}, this is a friendly reminder that you have an appointment "
            "at {clinic_name} on {appointment_date} at {appointment_time}. "
            "Reply C to confirm or call {clinic_phone}. STOPtoOptOut"
        )
    if template_type == "appointment_reminder_sms":
        return (
            "Hi {first_name}, this is a reminder that your appointment with {clinic_name} "
            "is on {appointment_date} at {appointment_time}. "
            "If you need assistance, call {clinic_phone}. STOPtoOptOut"
        )
    if template_type == "health_history_update_sms":
        return (
            "Hi {first_name}, please update your health history and insurance information "
            "before your appointment on {appointment_date} at {appointment_time}: {form_link}. "
            "Questions? Call {clinic_phone}. STOPtoOptOut"
        )
    if template_type == "new_patient_forms_sms":
        return (
            "Hi {first_name}, we look forward to seeing you at {clinic_name} on "
            "{appointment_date} at {appointment_time}. Please complete your new patient "
            "forms here: {form_link}. If unable, arrive {early_arrival_minutes} minutes early. "
            "STOPtoOptOut"
        )
    if template_type == "comprehensive_investment_letter":
        return (
            "{today_date}\n\n"
            "{patient_name}\n"
            "{patient_address_line_1}\n"
            "{patient_address_line_2}\n\n"
            "Subject: Comprehensive Orthodontic Treatment Investment and Payment Options\n\n"
            "Dear {patient_name},\n\n"
            "Thank you for meeting with our team at {clinic_name}. This letter summarizes your "
            "proposed comprehensive orthodontic treatment and available payment options.\n\n"
            "Treatment Summary\n"
            "- Treatment Type: {treatment_type}\n"
            "- Estimated Treatment Time: {estimated_treatment_duration}\n"
            "- Average Treatment Cost Range: {average_cost_range}\n"
            "- Proposed Treatment Package Amount: {treatment_package_amount}\n\n"
            "Financial Overview\n"
            "- Estimated Orthodontic Insurance Benefit: {insurance_benefit_estimate}\n"
            "- Required Down Payment: {down_payment_amount}\n"
            "- Estimated Amount to Finance: {amount_financed}\n\n"
            "Estimated Payment Options (subject to approval)\n"
            "- 12-month plan: {plan_12_monthly_payment} per month\n"
            "- 18-month plan: {plan_18_monthly_payment} per month\n"
            "- 24-month plan: {plan_24_monthly_payment} per month\n\n"
            "Retention Options\n"
            "- {retention_option_1_description}: {retention_option_1_amount}\n"
            "- {retention_option_2_description}: {retention_option_2_amount}\n\n"
            "Important Note\n"
            "Insurance benefit amounts are estimates only. Any unpaid balance not covered by "
            "insurance remains the patient's responsibility.\n\n"
            "Please contact us at {clinic_phone} if you would like to proceed.\n\n"
            "Sincerely,\n"
            "{team_member_name}\n"
            "{team_member_title}\n"
            "{clinic_name}\n"
        )
    if template_type == "invisalign_investment_letter":
        return (
            "{today_date}\n\n"
            "{patient_name}\n"
            "{patient_address_line_1}\n"
            "{patient_address_line_2}\n\n"
            "Subject: Invisalign Treatment Investment and Payment Options\n\n"
            "Dear {patient_name},\n\n"
            "Thank you for choosing {clinic_name}. This letter summarizes your Invisalign "
            "treatment investment and financing options.\n\n"
            "Treatment Summary\n"
            "- Treatment Type: {treatment_type}\n"
            "- Estimated Treatment Time: {estimated_treatment_duration}\n"
            "- Average Invisalign Cost Range: {average_cost_range}\n"
            "- Proposed Treatment Package Amount: {treatment_package_amount}\n\n"
            "Financial Overview\n"
            "- Estimated Orthodontic Insurance Benefit: {insurance_benefit_estimate}\n"
            "- Required Down Payment: {down_payment_amount}\n"
            "- Estimated Amount to Finance: {amount_financed}\n\n"
            "Estimated Payment Options (subject to approval)\n"
            "- 12-month plan: {plan_12_monthly_payment} per month\n"
            "- 18-month plan: {plan_18_monthly_payment} per month\n"
            "- 24-month plan: {plan_24_monthly_payment} per month\n\n"
            "Retention Options\n"
            "- {retention_option_1_description}: {retention_option_1_amount}\n"
            "- {retention_option_2_description}: {retention_option_2_amount}\n\n"
            "Important Note\n"
            "Insurance benefit amounts are estimates only. Any unpaid balance not covered by "
            "insurance remains the patient's responsibility.\n\n"
            "Please contact us at {clinic_phone} for next steps.\n\n"
            "Sincerely,\n"
            "{team_member_name}\n"
            "{team_member_title}\n"
            "{clinic_name}\n"
        )
    if template_type == "email":
        return (
            "Subject: {subject}\n\n"
            "Dear {patient_name},\n\n"
            "We are reaching out regarding {topic}. {message_body}\n\n"
            "Next step: {next_step}\n\n"
            "Sincerely,\n"
            "Siligent Dental Front Office\n"
            "Phone: {office_phone}\n"
            "Email: {office_email}\n"
        )
    if template_type in {"denial_letter", "rebuttal_letter"}:
        return (
            "{today_date}\n\n"
            "{payer_name}\n"
            "{payer_address}\n\n"
            "RE: {patient_name} | DOS: {date_of_service} | Claim: {claim_or_reference}\n\n"
            "Dear Claims Review Team,\n\n"
            "We request reconsideration of the denial identified as {denial_code}: "
            "{denial_reason}. The denied service was {procedure_description} "
            "(procedure code: {procedure_code}).\n\n"
            "Reason for Appeal\n"
            "{appeal_basis}\n\n"
            "Supporting Rationale\n"
            "{supporting_rationale}\n\n"
            "Please reprocess this claim and advise if any additional documentation is required.\n\n"
            "Sincerely,\n"
            "{provider_name}\n"
            "NPI: {provider_npi}\n"
            "Siligent Dental Front Office\n"
        )
    if template_type == "insurance_verification":
        return (
            "Insurance Verification Memo\n\n"
            "Patient: {patient_name}\n"
            "DOB: {patient_dob}\n"
            "Payer: {payer_name}\n"
            "Member ID: {member_id}\n"
            "Group Number: {group_number}\n"
            "Plan Type: {plan_type}\n\n"
            "Coverage Findings:\n"
            "{coverage_findings}\n\n"
            "Notable Limits/Exclusions:\n"
            "{limitations}\n\n"
            "Next Actions:\n"
            "{next_actions}\n"
        )
    if template_type == "appointment_confirmation":
        return (
            "Subject: Appointment Confirmation - {appointment_date}\n\n"
            "Dear {patient_name},\n\n"
            "This is to confirm your appointment on {appointment_date} at {appointment_time}.\n"
            "Provider: {provider_name}\n"
            "Location: {office_location}\n\n"
            "Please arrive {arrival_time_note} and bring {required_items}.\n\n"
            "If you need to reschedule, contact us at {office_phone}.\n\n"
            "Sincerely,\n"
            "Siligent Dental Provider Team\n"
        )
    return (
        "Subject: {subject}\n\n"
        "Dear {patient_name},\n\n"
        "{message_body}\n\n"
        "Next step: {next_step}\n\n"
        "Sincerely,\n"
        "Siligent Dental Front Office\n"
    )


def ensure_default_templates(
    *,
    template_store: object,
    template_types: list[str],
) -> int:
    existing = template_store.list_templates(role="admin")  # type: ignore[attr-defined]
    shared_types = {
        normalize_template_type(str(item.get("type", "")))
        for item in existing
        if str(item.get("visibility", "")).strip().lower() == "shared"
    }

    created = 0
    for raw_type in template_types:
        template_type = normalize_template_type(raw_type)
        if not template_type or template_type in shared_types:
            continue
        template_store.save_template(  # type: ignore[attr-defined]
            name=_default_template_name(template_type),
            template_type=template_type,
            content=_default_template_content(template_type),
            visibility="shared",
            tags=_default_template_tags(template_type),
        )
        shared_types.add(template_type)
        created += 1
    return created
