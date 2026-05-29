import type { InsuranceVerificationSummary } from "./types";

export function verificationSummaryToText(summary: InsuranceVerificationSummary): string {
  const covered = summary.covered_procedures.length
    ? summary.covered_procedures.map((item) => `- ${item}`).join("\n")
    : "- Not available";

  return [
    "Insurance Verification Summary",
    "",
    "Covered Procedures:",
    covered,
    "",
    `Estimated Co-Pay: ${summary.estimated_copay}`,
    `Prior Authorization Required: ${summary.prior_authorization_required}`,
    `Annual Maximum: ${summary.annual_maximum}`,
    `Waiting Periods: ${summary.waiting_periods}`,
    `Notable Exclusions/Limitations: ${summary.notable_exclusions_limitations}`
  ].join("\n");
}

