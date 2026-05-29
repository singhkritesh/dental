from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    ollama_url: str
    model_name: str
    ollama_health_timeout_sec: int
    ollama_generate_timeout_sec: int
    ollama_num_predict: int
    ollama_think: bool
    api_key: str
    cors_origins: tuple[str, ...]
    prompts_dir: Path
    data_dir: Path
    templates_path: Path
    payer_refs_dir: Path
    auth_enabled: bool = True
    auth_session_hours: int = 12
    allow_self_register: bool = False
    ollama_keep_alive: str = "0"
    database_url: str = ""
    db_pool_min_size: int = 1
    db_pool_max_size: int = 5


def _resolve_within_root(raw_path: str | None, default_rel: str) -> Path:
    rel = raw_path or default_rel
    candidate = Path(rel)
    if not candidate.is_absolute():
        candidate = (ROOT_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(ROOT_DIR)
    except ValueError as exc:
        raise ValueError(
            f"Path {candidate} is outside the project directory {ROOT_DIR}"
        ) from exc
    return candidate


def _load_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _load_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def load_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env")

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model_name = os.getenv("MODEL_NAME", "qwen3.5:4b").strip() or "qwen3.5:4b"
    ollama_health_timeout_sec = _load_positive_int_env("OLLAMA_HEALTH_TIMEOUT_SEC", 5)
    ollama_generate_timeout_sec = _load_positive_int_env(
        "OLLAMA_GENERATE_TIMEOUT_SEC",
        180,
    )
    ollama_num_predict = _load_positive_int_env("OLLAMA_NUM_PREDICT", 1024)
    ollama_think = _load_bool_env("OLLAMA_THINK", False)
    ollama_keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "0").strip() or "0"
    api_key = os.getenv("API_KEY", "").strip()
    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    cors_origins = tuple(
        origin.strip()
        for origin in raw_origins.split(",")
        if origin.strip()
    )
    prompts_dir = _resolve_within_root(os.getenv("PROMPTS_DIR"), "prompts")
    data_dir = _resolve_within_root(os.getenv("DATA_DIR"), "data")
    payer_refs_dir = data_dir / "payer_references"
    templates_path = data_dir / "templates.json"
    auth_enabled = _load_bool_env("AUTH_ENABLED", True)
    auth_session_hours = _load_positive_int_env("AUTH_SESSION_HOURS", 12)
    allow_self_register = _load_bool_env("ALLOW_SELF_REGISTER", False)
    database_url = os.getenv("DATABASE_URL", "").strip()
    db_pool_min_size = _load_positive_int_env("DB_POOL_MIN_SIZE", 1)
    db_pool_max_size = _load_positive_int_env("DB_POOL_MAX_SIZE", 5)

    prompts_dir.mkdir(parents=True, exist_ok=True)
    payer_refs_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    if not templates_path.exists():
        templates_path.write_text("[]", encoding="utf-8")

    return Settings(
        root_dir=ROOT_DIR,
        ollama_url=ollama_url,
        model_name=model_name,
        ollama_health_timeout_sec=ollama_health_timeout_sec,
        ollama_generate_timeout_sec=ollama_generate_timeout_sec,
        ollama_num_predict=ollama_num_predict,
        ollama_think=ollama_think,
        api_key=api_key,
        cors_origins=cors_origins,
        prompts_dir=prompts_dir,
        data_dir=data_dir,
        templates_path=templates_path,
        payer_refs_dir=payer_refs_dir,
        auth_enabled=auth_enabled,
        auth_session_hours=auth_session_hours,
        allow_self_register=allow_self_register,
        ollama_keep_alive=ollama_keep_alive,
        database_url=database_url,
        db_pool_min_size=db_pool_min_size,
        db_pool_max_size=db_pool_max_size,
    )
