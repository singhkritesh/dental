# REDAPL Templates Draft v1

Date: 2026-05-04  
Scope: Scenario-specific templates based on source assets in `/Users/kritesh/Downloads/redaplsiligentproject`

## 1) Appointment Confirmation (SMS)

Template Type: `appointment_confirmation_sms`  
Channel: SMS (target <= 320 chars)

```text
Hi [[First Name]], this is a friendly reminder that you have an appointment at [[Clinic Name]] on [[Appointment Date]] at [[Appointment Time]]. Reply C to confirm or call [[Clinic Phone]]. STOPtoOptOut
```

## 2) Appointment Reminder (SMS)

Template Type: `appointment_reminder_sms`  
Channel: SMS (target <= 320 chars)

```text
Hi [[First Name]], this is a reminder that your appointment with [[Clinic Name]] is on [[Appointment Date]] at [[Appointment Time]]. If you need help, call [[Clinic Phone]]. STOPtoOptOut
```

## 3) Health History Update (SMS)

Template Type: `health_history_update_sms`  
Channel: SMS (target <= 320 chars)

```text
Hi [[First Name]], it has been a while since your last visit. Please update your health history and insurance information before your appointment on [[Appointment Date]] at [[Appointment Time]]: [[Form Link]]. Questions? Call [[Clinic Phone]]. STOPtoOptOut
```

## 4) New Patient Form Fill-Out (SMS)

Template Type: `new_patient_forms_sms`  
Channel: SMS (target <= 320 chars)

```text
Hi [[First Name]], we look forward to seeing you at [[Clinic Name]] on [[Appointment Date]] at [[Appointment Time]]. Please complete your new patient forms here: [[Form Link]]. If unable, arrive [[Early Arrival Minutes]] minutes early. STOPtoOptOut
```

## 5) Comprehensive Orthodontic Investment Options (Letter)

Template Type: `comprehensive_investment_letter`  
Channel: Letter / PDF / Email

```text
[[Date]]

[[Patient Name]]
[[Patient Address Line 1]]
[[Patient Address Line 2]]

Subject: Comprehensive Orthodontic Treatment Investment and Payment Options

Dear [[Patient Name]],

Thank you for meeting with our team at [[Clinic Name]]. This letter summarizes your proposed comprehensive orthodontic treatment and available payment options.

Treatment Summary
- Treatment Type: [[Treatment Type]]
- Estimated Treatment Time: [[Estimated Treatment Duration]]
- Average Treatment Cost Range: [[Average Cost Range]]
- Proposed Treatment Package Amount: [[Treatment Package Amount]]

Your treatment package may include:
- Comprehensive orthodontic exam
- 3D scan and simulation
- Clinical photographs
- Orthodontic X-rays
- Follow-up aligner/orthodontic checks
- Additional items as clinically indicated by your provider

Financial Overview
- Estimated Orthodontic Insurance Benefit: [[Insurance Benefit Estimate]]
- Required Down Payment: [[Down Payment Amount]]
- Estimated Amount to Finance: [[Amount Financed]]

Estimated Payment Options (subject to approval)
- 12-month plan: [[Plan 12 Monthly Payment]] per month (Total Financed: [[Amount Financed]])
- 18-month plan: [[Plan 18 Monthly Payment]] per month (Total Financed: [[Amount Financed]])
- 24-month plan: [[Plan 24 Monthly Payment]] per month (Total Financed: [[Amount Financed]])

Retention Options
- Option 1: [[Retention Option 1 Description]] - [[Retention Option 1 Amount]]
- Option 2: [[Retention Option 2 Description]] - [[Retention Option 2 Amount]]

Promotional Terms (if applicable)
- Offer: [[Promo Offer]]
- Expiration Date: [[Promo Expiry Date]]
- Restrictions: [[Promo Restrictions]]

Important Note
Insurance benefit amounts are estimates only. Any unpaid balance not covered by insurance remains the patient’s responsibility.

Please contact us at [[Clinic Phone]] if you would like to proceed or if you have questions.

Sincerely,  
[[Team Member Name]]  
[[Team Member Title]]  
[[Clinic Name]]
```

## 6) Invisalign Payment Options (Letter)

Template Type: `invisalign_investment_letter`  
Channel: Letter / PDF / Email

```text
[[Date]]

[[Patient Name]]
[[Patient Address Line 1]]
[[Patient Address Line 2]]

Subject: Invisalign Treatment Investment and Payment Options

Dear [[Patient Name]],

Thank you for choosing [[Clinic Name]]. This letter provides a summary of your Invisalign treatment investment and financing options.

Treatment Summary
- Treatment Type: [[Treatment Type]]
- Estimated Treatment Time: [[Estimated Treatment Duration]]
- Average Invisalign Cost Range: [[Average Cost Range]]
- Proposed Treatment Package Amount: [[Treatment Package Amount]]

Your treatment package may include:
- Comprehensive orthodontic exam
- 3D scan and projected outcome simulation
- Clinical photographs
- Orthodontic X-rays
- Invisalign aligner checks
- Additional provider-recommended services

Financial Overview
- Estimated Orthodontic Insurance Benefit: [[Insurance Benefit Estimate]]
- Required Down Payment: [[Down Payment Amount]]
- Estimated Amount to Finance: [[Amount Financed]]

Estimated Payment Options (subject to approval)
- 12-month plan: [[Plan 12 Monthly Payment]] per month (Total Financed: [[Amount Financed]])
- 18-month plan: [[Plan 18 Monthly Payment]] per month (Total Financed: [[Amount Financed]])
- 24-month plan: [[Plan 24 Monthly Payment]] per month (Total Financed: [[Amount Financed]])

Retention Options
- Option 1: [[Retention Option 1 Description]] - [[Retention Option 1 Amount]]
- Option 2: [[Retention Option 2 Description]] - [[Retention Option 2 Amount]]

Promotional Terms (if applicable)
- Offer: [[Promo Offer]]
- Expiration Date: [[Promo Expiry Date]]
- Restrictions: [[Promo Restrictions]]

Important Note
Insurance benefit amounts are estimates only. Any unpaid balance not covered by insurance remains the patient’s responsibility.

Please contact us at [[Clinic Phone]] for next steps or to finalize your payment plan.

Sincerely,  
[[Team Member Name]]  
[[Team Member Title]]  
[[Clinic Name]]
```

## Suggested Core Variable Set

Use this minimum reusable set across scenarios:

- `[[First Name]]`
- `[[Patient Name]]`
- `[[Clinic Name]]`
- `[[Clinic Phone]]`
- `[[Appointment Date]]`
- `[[Appointment Time]]`
- `[[Form Link]]`
- `[[Date]]`
- `[[Treatment Type]]`
- `[[Estimated Treatment Duration]]`
- `[[Average Cost Range]]`
- `[[Treatment Package Amount]]`
- `[[Insurance Benefit Estimate]]`
- `[[Down Payment Amount]]`
- `[[Amount Financed]]`
- `[[Plan 12 Monthly Payment]]`
- `[[Plan 18 Monthly Payment]]`
- `[[Plan 24 Monthly Payment]]`
- `[[Retention Option 1 Description]]`
- `[[Retention Option 1 Amount]]`
- `[[Retention Option 2 Description]]`
- `[[Retention Option 2 Amount]]`
- `[[Team Member Name]]`
- `[[Team Member Title]]`

