# REDAPL Letter Template Plan

Date: 2026-05-04

## Goal

Create a reusable professional **letter template** for REDAPL/Siligent use, based on the reviewed assets, with strict placeholder-based variable insertion (no hardcoded patient-specific values).

## Proposed Letter Type (Primary)

`Treatment Investment & Payment Options Letter`

Reason:
- Most structured source material is payment/investment-oriented (the two XLSX files).
- This can be reused across both comprehensive orthodontic and Invisalign scenarios.
- It maps naturally to variable-driven generation in the current app architecture.

## Output Structure (Planned)

1. Header block
- Clinic identity
- Date
- Patient name

2. Purpose statement
- Explain this letter summarizes treatment investment and payment options.

3. Treatment summary
- Treatment type
- Estimated duration
- Estimated cost range
- Included services section

4. Financial options summary
- Down payment
- Insurance estimate note
- Financing options table/list (12/18/24 months)
- Total financed amount

5. Retention and additional options
- Retention option lines

6. Compliance and responsibility note
- Insurance estimate responsibility language
- Promotional offer limitations where applicable

7. Action and close
- Next step instructions
- Contact details
- Signature/team member line

## Variable/Placeholder Strategy

All patient/case-specific or numeric values should be placeholders:
- `[[...]]` natural labels in authored template
- canonical mapped forms `{{...}}` at runtime via app pipeline

No literal dates, phones, amounts, IDs, or patient names should remain in template body.

## Validation Checklist (Before Finalizing Template)

1. Placeholder completeness:
- Every dynamic field is tokenized.

2. Tone/voice:
- Professional dental admin voice, clear and non-technical for patient readers.

3. Financial clarity:
- Monthly options and totals are unambiguous.

4. Legal/compliance language:
- Insurance estimate caveat retained.
- No contradictory promotional terms.

5. Reusability:
- Works for both comprehensive orthodontic and Invisalign variants with optional sections.

## Working Approach (Next Execution Steps)

1. Draft v1 template text with placeholders only.
2. Map placeholder list to canonical field keys for runtime population.
3. Run one sample rendering with mock values to verify flow and readability.
4. Refine section wording for brevity and patient clarity.
5. Freeze v1 and add optional variant notes (Comprehensive vs Invisalign).

## Open Decisions for You (Before Drafting v1)

1. Should the first template be:
- one unified "investment options" letter, or
- two separate templates (Comprehensive and Invisalign)?

2. Do you want promotional/coupon sections always present or conditional?

3. Should signature be:
- team-member named signature, or
- generic front-office signature block?

