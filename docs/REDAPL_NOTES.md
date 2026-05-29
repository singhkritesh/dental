# REDAPL Source Notes (Initial Discovery)

Date: 2026-05-04  
Source folder reviewed: `/Users/kritesh/Downloads/redaplsiligentproject`

## Files Reviewed

1. `ApptConfirm.png`
2. `FriendlyReminder.png`
3. `HealthHistory.png`
4. `NewPatientFormFillOut.png`
5. `ComprehensiveInvFinanceOptions.xlsx`
6. `InvisalignPaymentOptionsFINAL.xlsx`

## Observations from PNG Files (Messaging Templates)

These are short-form patient communication templates (SMS-style) with variable chips and a 320-char limit.  
Common variables shown:
- `First Name`
- `Last Name`
- `Location Phone Number`
- `Location Name`
- `Month Day`
- `Time`

### Template Themes

- Appointment confirmation/reminder
- Health history update prompt
- New patient forms completion prompt

### Compliance/Operational Pattern

All samples include opt-out language and compliance warning references:
- Opt-out keywords shown include `STOP`/`STOPtoOptOut`
- Carrier compliance warning mentions `CANCEL, STOP, UNSUBSCRIBE, STOPALL, END, QUIT`

This is relevant if we produce any companion SMS/short-message assets, even though the current request is for a letter template.

## Observations from XLSX Files (Finance Option Documents)

Both spreadsheets are structured as patient-facing financial option handouts for orthodontic/Invisalign treatment.

### Common Sections Identified

- Header: `Payment Options`
- Patient/date lines
- Treatment type and estimated treatment time
- Average treatment cost range
- "Your Treatment Includes" bullet list
- Promotional offer/coupon language + expiry field
- Insurance benefit estimate line
- Down payment line
- Financing options table (12/18/24 month examples, monthly payment, total financed)
- Retention section (Vivera-related options)
- Signature / Date / Team Member Initials
- Liability clause around insurance shortfall responsibility

### Key Numeric Anchors Found (Raw Source Values)

Comprehensive sheet:
- Included package figure: `6599`
- Down payment: `500`
- Financed total shown: `6099`
- Retention options: `839` / `439`

Invisalign sheet:
- Included package figure: `4599`
- Down payment: `500`
- Financed total shown: `4099`
- Retention options: `839` / `439`

Note: these appear as examples in source files and should be represented as placeholders in reusable templates unless business rules define fixed values.

## Initial Conclusion

The source package mixes:
- short message templates (PNG UI captures)
- financial estimate/payment option documents (XLSX)

For the requested "letter template", the strongest direct source alignment is a **financial options letter** (or treatment investment summary letter) that uses placeholders for patient/treatment/financial values.

## Placeholder Candidate Pool (Draft)

- `[[Patient Name]]`
- `[[Date]]`
- `[[Treatment Type]]`
- `[[Estimated Treatment Duration]]`
- `[[Average Cost Range]]`
- `[[Treatment Package Amount]]`
- `[[Insurance Estimate Amount]]`
- `[[Down Payment Amount]]`
- `[[Financed Amount]]`
- `[[Plan 12 Month Payment]]`
- `[[Plan 18 Month Payment]]`
- `[[Plan 24 Month Payment]]`
- `[[Retention Option 1 Amount]]`
- `[[Retention Option 2 Amount]]`
- `[[Promo Offer Text]]`
- `[[Promo Expiry Date]]`
- `[[Clinic Name]]`
- `[[Clinic Phone]]`
- `[[Team Member Name]]`
- `[[Signature Line]]`

