from __future__ import annotations

from urllib.parse import urlparse

import requests

from services.errors import AppError


# Allow only local endpoints:
# - localhost loopback for host-mode runs
# - docker local aliases when API runs in a container and Ollama runs on host
LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "ollama",
    "host.docker.internal",
    "host.containers.internal",
}


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model_name: str,
        *,
        health_timeout_sec: int = 5,
        generate_timeout_sec: int = 180,
        num_predict: int = 1024,
        think: bool = False,
        keep_alive: str = "0",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.health_timeout_sec = health_timeout_sec
        self.generate_timeout_sec = generate_timeout_sec
        self.num_predict = num_predict
        self.think = think
        self.keep_alive = keep_alive.strip() or "0"
        self._validate_local_url(self.base_url)

    @staticmethod
    def _validate_local_url(base_url: str) -> None:
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        if host not in LOCAL_HOSTS:
            raise ValueError(
                "Only local Ollama URLs are allowed. "
                f"Received host: {host or '<empty>'}"
            )

    def health(self) -> dict[str, object]:
        model_names = self.list_models()
        return {
            "status": "ok",
            "model_configured": self.model_name,
            "model_available": self.model_name in model_names,
            "available_models": model_names,
        }

    def list_models(self) -> list[str]:
        tags_url = f"{self.base_url}/api/tags"
        try:
            response = requests.get(tags_url, timeout=self.health_timeout_sec)
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise AppError(
                code="OLLAMA_TIMEOUT",
                message="Model health check timed out.",
                status_code=504,
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise AppError(
                code="OLLAMA_UNREACHABLE",
                message="AI model is not running. Please contact your administrator.",
                status_code=503,
            ) from exc
        except requests.RequestException as exc:
            raise AppError(
                code="GENERATION_FAILED",
                message=f"Could not reach Ollama: {exc}",
                status_code=502,
            ) from exc

        data = response.json()
        return [
            str(model.get("name", "")).strip()
            for model in data.get("models", [])
            if str(model.get("name", "")).strip()
        ]

    def generate(
        self,
        prompt: str,
        *,
        model_name: str | None = None,
        images: list[str] | None = None,
        num_predict: int | None = None,
        think: bool | None = None,
        timeout_sec: int | None = None,
    ) -> str:
        selected_model = (model_name or self.model_name).strip() or self.model_name
        try:
            resolved_num_predict = int(num_predict or self.num_predict)
            resolved_think = self.think if think is None else bool(think)
            payload = self._build_generate_payload(
                prompt=prompt,
                selected_model=selected_model,
                images=images,
                num_predict=resolved_num_predict,
                think=resolved_think,
            )

            timeout_value = timeout_sec or self.generate_timeout_sec
            fallback_attempts: list[dict[str, object]] = []
            if images:
                fallback_attempts.append(
                    self._build_generate_payload(
                        prompt=prompt,
                        selected_model=selected_model,
                        images=None,
                        num_predict=max(256, resolved_num_predict // 2),
                        think=False,
                    )
                )
            fallback_attempts.append(
                self._build_generate_payload(
                    prompt=prompt,
                    selected_model=selected_model,
                    images=None,
                    num_predict=min(256, resolved_num_predict),
                    think=False,
                )
            )

            tried_signatures = {self._payload_signature(payload)}
            for fallback in fallback_attempts:
                signature = self._payload_signature(fallback)
                if signature in tried_signatures:
                    continue
                tried_signatures.add(signature)
                try:
                    body = self._post_generate(payload, timeout_value)
                    return self._extract_response_text(body)
                except AppError as exc:
                    if not self._is_runner_resource_failure(exc.message):
                        raise
                    payload = fallback

            try:
                body = self._post_generate(payload, timeout_value)
                return self._extract_response_text(body)
            except AppError as exc:
                if self._is_runner_resource_failure(exc.message):
                    raise AppError(
                        code="GENERATION_FAILED",
                        message=(
                            "Model runner stopped due to resource pressure. "
                            "Try a smaller model, smaller files/images, or retry."
                        ),
                        status_code=502,
                    ) from exc
                raise
        finally:
            self._offload_model_if_needed(selected_model)

    @staticmethod
    def _payload_signature(payload: dict[str, object]) -> tuple[bool, int, bool]:
        has_images = bool(payload.get("images"))
        options = payload.get("options", {})
        num_predict = 0
        if isinstance(options, dict):
            num_predict = int(options.get("num_predict", 0) or 0)
        return has_images, num_predict, bool(payload.get("think"))

    def _build_generate_payload(
        self,
        *,
        prompt: str,
        selected_model: str,
        images: list[str] | None,
        num_predict: int,
        think: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "think": bool(think),
            "options": {
                "temperature": 0.3,
                "num_predict": max(64, int(num_predict)),
            },
        }
        if images:
            payload["images"] = images
        return payload

    def _post_generate(self, payload: dict[str, object], timeout_sec: int) -> dict[str, object]:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=timeout_sec,
            )
        except requests.exceptions.Timeout as exc:
            raise AppError(
                code="OLLAMA_TIMEOUT",
                message="Model response timed out. Please try again.",
                status_code=504,
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise AppError(
                code="OLLAMA_UNREACHABLE",
                message="AI model is not running. Please contact your administrator.",
                status_code=503,
            ) from exc
        except requests.RequestException as exc:
            raise AppError(
                code="GENERATION_FAILED",
                message=f"Model request failed: {exc}",
                status_code=502,
            ) from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            if not detail:
                detail = f"HTTP {response.status_code}"
            raise AppError(
                code="GENERATION_FAILED",
                message=f"Model request failed: {detail}",
                status_code=502,
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise AppError(
                code="GENERATION_FAILED",
                message="Model returned an unusable response. Please try again.",
                status_code=502,
            ) from exc

        if not isinstance(body, dict):
            raise AppError(
                code="GENERATION_FAILED",
                message="Model returned an unusable response. Please try again.",
                status_code=502,
            )
        model_error = str(body.get("error", "")).strip()
        if model_error:
            raise AppError(
                code="GENERATION_FAILED",
                message=f"Model request failed: {model_error}",
                status_code=502,
            )
        return body

    def _offload_model_if_needed(self, selected_model: str) -> None:
        if not selected_model or not self._should_offload_after_request():
            return
        unload_payload = {
            "model": selected_model,
            "prompt": "",
            "stream": False,
            "keep_alive": "0",
        }
        try:
            requests.post(
                f"{self.base_url}/api/generate",
                json=unload_payload,
                timeout=max(1, self.health_timeout_sec),
            )
        except requests.RequestException:
            # Best-effort cleanup only; generation result has already been finalized.
            return

    def _should_offload_after_request(self) -> bool:
        keep_alive = self.keep_alive.strip().lower()
        return keep_alive in {"0", "0s", "0m", "0h"}

    @staticmethod
    def _extract_response_text(body: dict[str, object]) -> str:
        text = str(body.get("response", "")).strip()
        if not text:
            raise AppError(
                code="GENERATION_FAILED",
                message="Model returned an unusable response. Please try again.",
                status_code=502,
            )
        return text

    @staticmethod
    def _is_runner_resource_failure(message: str) -> bool:
        normalized = message.lower()
        return any(
            marker in normalized
            for marker in (
                "model runner has unexpectedly stopped",
                "out of memory",
                "resource",
                "signal: killed",
            )
        )
