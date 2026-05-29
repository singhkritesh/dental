from __future__ import annotations

from pathlib import Path

from services.errors import AppError


def validate_required_fields(
    variables: dict[str, str], required_fields: tuple[str, ...]
) -> None:
    missing = [
        field
        for field in required_fields
        if not str(variables.get(field, "")).strip()
    ]
    if missing:
        raise AppError(
            code="MISSING_VARIABLES",
            message=f"Missing required fields: {', '.join(missing)}",
            status_code=400,
        )


def resolve_prompt_path(prompts_dir: Path, template_name: str) -> Path:
    candidate = (prompts_dir / f"{template_name}.txt").resolve()
    try:
        candidate.relative_to(prompts_dir.resolve())
    except ValueError as exc:
        raise AppError(
            code="TEMPLATE_NOT_FOUND",
            message=f"Template path is invalid: {template_name}",
            status_code=500,
        ) from exc
    return candidate


def load_prompt_template(prompts_dir: Path, template_name: str) -> str:
    path = resolve_prompt_path(prompts_dir, template_name)
    if not path.exists():
        raise AppError(
            code="TEMPLATE_NOT_FOUND",
            message=f"Template file not found: {path}",
            status_code=500,
        )
    return path.read_text(encoding="utf-8")


def compose_prompt(
    prompts_dir: Path, template_name: str, variables: dict[str, str]
) -> str:
    template = load_prompt_template(prompts_dir, template_name)
    try:
        return template.format(**variables)
    except KeyError as exc:
        raise AppError(
            code="MISSING_VARIABLES",
            message=f"Missing required variable in template: {exc}",
            status_code=400,
        ) from exc

