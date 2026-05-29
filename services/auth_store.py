from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.errors import AppError
from services.file_store import JsonFileStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@dataclass(frozen=True)
class AuthUser:
    id: str
    username: str
    role: str
    created_at: str


class AuthStore:
    def __init__(
        self,
        users_path: Path,
        sessions_path: Path,
        *,
        session_hours: int = 12,
        pbkdf2_rounds: int = 200_000,
    ) -> None:
        self._users = JsonFileStore(users_path, [])
        self._sessions = JsonFileStore(sessions_path, [])
        self.session_hours = max(1, session_hours)
        self.pbkdf2_rounds = pbkdf2_rounds

    def bootstrap_required(self) -> bool:
        users = self._read_users()
        return len(users) == 0

    def _read_users(self) -> list[dict[str, str]]:
        data = self._users.read()
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _write_users(self, users: list[dict[str, str]]) -> None:
        self._users.write(users)

    def _read_sessions(self) -> list[dict[str, str]]:
        data = self._sessions.read()
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _write_sessions(self, sessions: list[dict[str, str]]) -> None:
        self._sessions.write(sessions)

    def _hash_password(self, password: str, salt_hex: str) -> str:
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            self.pbkdf2_rounds,
        )
        return key.hex()

    def _normalize_username(self, username: str) -> str:
        normalized = username.strip().lower()
        if not normalized:
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Username is required.",
                status_code=400,
            )
        return normalized

    def register(
        self,
        username: str,
        password: str,
        *,
        role: str | None = None,
    ) -> AuthUser:
        normalized = self._normalize_username(username)
        if len(password) < 8:
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Password must be at least 8 characters.",
                status_code=400,
            )

        users = self._read_users()
        for item in users:
            if item.get("username", "").lower() == normalized:
                raise AppError(
                    code="USER_EXISTS",
                    message="A user with this username already exists.",
                    status_code=409,
                )

        if not users:
            assigned_role = "admin"
        else:
            assigned_role = (role or "staff").strip().lower()
            if assigned_role not in {"admin", "staff"}:
                assigned_role = "staff"

        salt_hex = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt_hex)
        created_at = _to_iso(_utc_now())
        user = {
            "id": secrets.token_hex(12),
            "username": normalized,
            "password_salt": salt_hex,
            "password_hash": password_hash,
            "role": assigned_role,
            "created_at": created_at,
        }
        users.append(user)
        self._write_users(users)
        return AuthUser(
            id=user["id"],
            username=user["username"],
            role=user["role"],
            created_at=user["created_at"],
        )

    def authenticate(self, username: str, password: str) -> AuthUser:
        normalized = self._normalize_username(username)
        users = self._read_users()
        for item in users:
            if item.get("username", "").lower() != normalized:
                continue
            expected = item.get("password_hash", "")
            salt_hex = item.get("password_salt", "")
            provided = self._hash_password(password, salt_hex)
            if hmac.compare_digest(expected, provided):
                return AuthUser(
                    id=str(item.get("id", "")),
                    username=str(item.get("username", "")),
                    role=str(item.get("role", "staff")),
                    created_at=str(item.get("created_at", "")),
                )
            break
        raise AppError(
            code="INVALID_CREDENTIALS",
            message="Invalid username or password.",
            status_code=401,
        )

    def _cleanup_sessions(self, sessions: list[dict[str, str]]) -> list[dict[str, str]]:
        now = _utc_now()
        clean: list[dict[str, str]] = []
        for session in sessions:
            try:
                expires = _parse_iso(str(session.get("expires_at", "")))
            except ValueError:
                continue
            if expires > now:
                clean.append(session)
        return clean

    def create_session(self, user: AuthUser) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = _utc_now()
        expires = now + timedelta(hours=self.session_hours)
        sessions = self._cleanup_sessions(self._read_sessions())
        sessions.append(
            {
                "token_hash": token_hash,
                "user_id": user.id,
                "created_at": _to_iso(now),
                "expires_at": _to_iso(expires),
            }
        )
        self._write_sessions(sessions)
        return token

    def _find_user(self, user_id: str) -> AuthUser | None:
        users = self._read_users()
        for item in users:
            if item.get("id") != user_id:
                continue
            return AuthUser(
                id=str(item.get("id", "")),
                username=str(item.get("username", "")),
                role=str(item.get("role", "staff")),
                created_at=str(item.get("created_at", "")),
            )
        return None

    def get_user_for_token(self, token: str) -> AuthUser | None:
        if not token.strip():
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        sessions = self._cleanup_sessions(self._read_sessions())
        self._write_sessions(sessions)
        for session in sessions:
            if not hmac.compare_digest(str(session.get("token_hash", "")), token_hash):
                continue
            user_id = str(session.get("user_id", ""))
            return self._find_user(user_id)
        return None

    def revoke_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        sessions = self._cleanup_sessions(self._read_sessions())
        kept = [
            session
            for session in sessions
            if not hmac.compare_digest(str(session.get("token_hash", "")), token_hash)
        ]
        self._write_sessions(kept)

