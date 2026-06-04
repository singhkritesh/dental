from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from services.errors import AppError
from services.template_type_store import normalize_template_type

SUPPORTED_DENTRIX_TEMPLATE_TYPES = {
    "denial_letter",
    "rebuttal_letter",
    "insurance_verification",
}


@dataclass
class DentrixTemplateResolution:
    template_type: str
    resolved_fields: dict[str, str]
    missing_required_fields: list[str]
    missing_optional_fields: list[str]

    @property
    def can_generate(self) -> bool:
        return not self.missing_required_fields


@lru_cache(maxsize=8)
def _load_spec(spec_path: str) -> dict[str, Any]:
    path = Path(spec_path)
    if not path.exists():
        raise AppError(
            code="SPEC_NOT_FOUND",
            message=f"Dentrix mapping spec not found: {path}",
            status_code=500,
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError(
            code="INVALID_SPEC",
            message=f"Dentrix mapping spec is invalid JSON: {path}",
            status_code=500,
        ) from exc


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return re.sub(r"\s+", " ", text)


def _as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _read_path(obj: object, parts: list[str]) -> list[str]:
    if not parts:
        text = _clean_text(obj)
        return [text] if text else []

    if isinstance(obj, list):
        out: list[str] = []
        for item in obj:
            out.extend(_read_path(item, parts))
        return out

    if not isinstance(obj, dict):
        return []

    nxt = obj.get(parts[0])
    return _read_path(nxt, parts[1:])


def _get_path_values(records: dict[str, Any], path_expr: str) -> list[str]:
    parts = [part for part in path_expr.split(".") if part]
    if len(parts) < 2:
        return []
    root = parts[0]
    if root not in records:
        return []
    return _read_path(records[root], parts[1:])


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _find_master_record(master_obj: object, lookup_value: str) -> dict[str, Any] | None:
    key = _clean_text(lookup_value)
    if not key:
        return None

    if isinstance(master_obj, dict):
        direct = master_obj.get(key)
        if isinstance(direct, dict):
            return direct
        candidates = master_obj.values()
    elif isinstance(master_obj, list):
        candidates = master_obj
    else:
        return None

    identity_fields = {
        "id",
        "patid",
        "provid",
        "insid",
        "inspartyid",
        "claimid",
        "external_id",
        "key",
    }
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for field_name, field_value in candidate.items():
            if field_name.lower() not in identity_fields:
                continue
            if _clean_text(field_value).casefold() == key.casefold():
                return candidate
    return None


def _master_value(master_refs: dict[str, Any], namespace: str, fn_name: str, arg_value: str) -> list[str]:
    master_obj = master_refs.get(namespace)
    if master_obj is None:
        return []

    record = _find_master_record(master_obj, arg_value)
    if record is None:
        return []

    if namespace == "patient_master":
        if fn_name == "full_name_by_patid":
            first = _clean_text(record.get("first_name"))
            last = _clean_text(record.get("last_name"))
            full = _clean_text(record.get("full_name"))
            if full:
                return [full]
            if first or last:
                return [_clean_text(f"{first} {last}")]
            return []
        if fn_name == "dob_by_patid":
            return [_clean_text(record.get("dob"))]

    if namespace == "provider_master":
        if fn_name == "name_by_provid":
            return [_clean_text(record.get("name") or record.get("provider_name"))]
        if fn_name == "npi_by_provid":
            return [_clean_text(record.get("npi") or record.get("provider_npi"))]

    if namespace == "payer_master":
        if fn_name in {"name_by_insid", "name_by_inspartyid"}:
            return [_clean_text(record.get("name") or record.get("payer_name"))]
        if fn_name in {"address_by_insid", "address_by_inspartyid"}:
            return [_clean_text(record.get("address") or record.get("payer_address"))]

    if namespace == "procedure_table":
        if fn_name == "cdt_code_by_claimid":
            return [_clean_text(record.get("procedure_code") or record.get("cdt_code"))]
        if fn_name == "description_by_claimid":
            return [_clean_text(record.get("procedure_description") or record.get("description"))]

    return []


def _filter_rows_by_claim_id(rows: list[dict[str, Any]], claim_id: str) -> list[dict[str, Any]]:
    if not claim_id:
        return rows
    filtered = [
        row
        for row in rows
        if _clean_text(row.get("claimid", "")).casefold() == claim_id.casefold()
    ]
    return filtered


def _filter_notes_by_status_links(
    notes: list[dict[str, Any]],
    status_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    note_ids = {
        _clean_text(item.get("noteid", "")).casefold()
        for item in status_links
        if _clean_text(item.get("noteid", ""))
    }
    if not note_ids:
        return notes
    filtered: list[dict[str, Any]] = []
    for note in notes:
        note_id = _clean_text(note.get("cnotesid", "")).casefold()
        if note_id and note_id in note_ids:
            filtered.append(note)
    return filtered


def _eval_expr_values(
    expr: str,
    *,
    records: dict[str, Any],
    master_refs: dict[str, Any],
    today: date,
) -> list[str]:
    text = expr.strip()
    if not text:
        return []
    if text == "system.current_date":
        return [today.isoformat()]

    fn_match = re.fullmatch(r"([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\(([^)]*)\)", text)
    if fn_match:
        namespace, fn_name, arg_expr = fn_match.groups()
        arg_values = _eval_expr_values(
            arg_expr.strip(),
            records=records,
            master_refs=master_refs,
            today=today,
        )
        arg_value = _first_non_empty(arg_values)
        if not arg_value:
            return []
        return _master_value(master_refs, namespace, fn_name, arg_value)

    if text == "clinicalnote.notetext_excerpt":
        notes = _get_path_values(records, "clinicalnote.notetext")
        snippet = _clean_text(" ".join(_dedupe_preserve(notes)))
        if not snippet:
            return []
        return [snippet[:500]]

    return _get_path_values(records, text)


def resolve_dentrix_template_fields(
    *,
    template_type: str,
    claim: dict[str, Any],
    claiminfo: dict[str, Any] | None = None,
    claimadjreason: list[dict[str, Any]] | None = None,
    claimstatusnotelink: list[dict[str, Any]] | None = None,
    clinicalnote: list[dict[str, Any]] | None = None,
    master_refs: dict[str, Any] | None = None,
    spec_path: Path,
    today: date | None = None,
) -> DentrixTemplateResolution:
    normalized_type = normalize_template_type(template_type)
    if normalized_type not in SUPPORTED_DENTRIX_TEMPLATE_TYPES:
        raise AppError(
            code="INVALID_TEMPLATE_TYPE",
            message=(
                "Dentrix mapping currently supports: "
                f"{', '.join(sorted(SUPPORTED_DENTRIX_TEMPLATE_TYPES))}."
            ),
            status_code=400,
        )

    spec = _load_spec(str(spec_path.resolve()))
    mappings = spec.get("template_mappings", {})
    template_map = mappings.get(normalized_type, {})
    inherited_from = template_map.get("inherits")

    variables: dict[str, Any] = {}
    if inherited_from:
        parent_map = mappings.get(normalize_template_type(str(inherited_from)), {})
        parent_vars = parent_map.get("variables", {})
        if isinstance(parent_vars, dict):
            variables.update(parent_vars)

    current_vars = template_map.get("variables", {})
    if isinstance(current_vars, dict):
        variables.update(current_vars)

    if not variables:
        raise AppError(
            code="INVALID_SPEC",
            message=f"No variable mapping found for template type: {normalized_type}",
            status_code=500,
        )

    records: dict[str, Any] = {
        "claim": claim or {},
        "claiminfo": claiminfo or {},
        "claimadjreason": _as_list(claimadjreason),
        "claimstatusnotelink": _as_list(claimstatusnotelink),
        "clinicalnote": _as_list(clinicalnote),
    }
    refs = master_refs or {}
    now = today or date.today()

    claim_id = _clean_text(claim.get("claimid", ""))
    if claim_id:
        records["claimadjreason"] = _filter_rows_by_claim_id(
            list(records["claimadjreason"]),
            claim_id,
        )
        records["claimstatusnotelink"] = _filter_rows_by_claim_id(
            list(records["claimstatusnotelink"]),
            claim_id,
        )
        records["clinicalnote"] = _filter_notes_by_status_links(
            list(records["clinicalnote"]),
            list(records["claimstatusnotelink"]),
        )

    resolved: dict[str, str] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []

    for variable_name, variable_spec_raw in variables.items():
        if not isinstance(variable_spec_raw, dict):
            continue
        variable_spec = variable_spec_raw
        required = bool(variable_spec.get("required", False))
        value = ""

        priority_list = variable_spec.get("priority")
        if isinstance(priority_list, list):
            for expr in priority_list:
                values = _eval_expr_values(
                    str(expr),
                    records=records,
                    master_refs=refs,
                    today=now,
                )
                value = _first_non_empty(_dedupe_preserve(values))
                if value:
                    break

        composition_list = variable_spec.get("composition")
        if (not value) and isinstance(composition_list, list):
            fragments: list[str] = []
            for expr in composition_list:
                values = _eval_expr_values(
                    str(expr),
                    records=records,
                    master_refs=refs,
                    today=now,
                )
                deduped = _dedupe_preserve(values)
                if deduped:
                    fragments.append(", ".join(deduped))
            value = "; ".join(fragments).strip()

        resolved[variable_name] = value
        if not value:
            if required:
                missing_required.append(variable_name)
            else:
                missing_optional.append(variable_name)

    return DentrixTemplateResolution(
        template_type=normalized_type,
        resolved_fields=resolved,
        missing_required_fields=sorted(set(missing_required)),
        missing_optional_fields=sorted(set(missing_optional)),
    )
