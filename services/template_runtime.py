from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

PLACEHOLDER_TOKEN_PATTERN = r"[A-Za-z][A-Za-z0-9_.-]{0,79}"
_PLACEHOLDER_PATTERN = re.compile(
    rf"\{{\{{\s*({PLACEHOLDER_TOKEN_PATTERN})\s*\}}\}}|"
    rf"(?<!\{{)\{{({PLACEHOLDER_TOKEN_PATTERN})\}}(?!\}})"
)


@dataclass(frozen=True)
class TemplateRenderResult:
    rendered: str
    placeholders: list[str]
    missing: list[str]
    used: dict[str, str]


def extract_template_placeholders(content: str) -> list[str]:
    found: set[str] = set()
    for match in _PLACEHOLDER_PATTERN.finditer(content):
        token = (match.group(1) or match.group(2) or "").strip()
        if token:
            found.add(token)
    return sorted(found)


def normalize_runtime_fields(raw: Mapping[str, Any] | None) -> dict[str, str]:
    if not raw:
        return {}
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        token = str(key).strip()
        if not token:
            continue
        normalized[token] = _coerce_runtime_value(value)
    return normalized


def _coerce_runtime_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value).strip()
    return json.dumps(value, ensure_ascii=False)


def render_template_with_runtime_fields(
    content: str,
    runtime_fields: Mapping[str, str] | None,
    *,
    keep_unresolved: bool = True,
) -> TemplateRenderResult:
    placeholders = extract_template_placeholders(content)
    if not placeholders:
        return TemplateRenderResult(
            rendered=content,
            placeholders=[],
            missing=[],
            used={},
        )

    runtime = dict(runtime_fields or {})
    lower_lookup = {key.lower(): key for key in runtime}
    missing: set[str] = set()
    used: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        token = (match.group(1) or match.group(2) or "").strip()
        if not token:
            return match.group(0)

        if token in runtime:
            value = runtime[token]
            used[token] = value
            return value

        lowered = token.lower()
        if lowered in lower_lookup:
            resolved_key = lower_lookup[lowered]
            value = runtime[resolved_key]
            used[token] = value
            return value

        missing.add(token)
        return match.group(0) if keep_unresolved else ""

    rendered = _PLACEHOLDER_PATTERN.sub(_replace, content)
    return TemplateRenderResult(
        rendered=rendered,
        placeholders=placeholders,
        missing=sorted(missing),
        used=used,
    )


def runtime_fields_to_context_block(
    runtime_fields: Mapping[str, str] | None,
    *,
    max_chars: int = 4_000,
) -> str:
    values = runtime_fields or {}
    if not values:
        return ""

    lines = ["[Runtime Patient Data]"]
    for key in sorted(values.keys()):
        lines.append(f"- {key}: {values[key]}")
    block = "\n".join(lines)
    return block[:max_chars]
