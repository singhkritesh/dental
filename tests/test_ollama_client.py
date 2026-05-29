from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import requests

from services.errors import AppError
from services.ollama_client import OllamaClient


class OllamaClientValidationTests(unittest.TestCase):
    def test_accepts_localhost_urls(self) -> None:
        OllamaClient("http://localhost:11434", "qwen3.5:4b")

    def test_accepts_docker_host_alias(self) -> None:
        OllamaClient("http://host.docker.internal:11434", "qwen3.5:4b")

    def test_rejects_non_local_host(self) -> None:
        with self.assertRaises(ValueError):
            OllamaClient("https://example.com", "qwen3.5:4b")

    @patch("services.ollama_client.requests.post")
    def test_generate_uses_configured_timeout_and_num_predict(self, post: MagicMock) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "ok"}
        post.return_value = response

        client = OllamaClient(
            "http://localhost:11434",
            "qwen3.5:4b",
            generate_timeout_sec=210,
            num_predict=900,
        )
        with patch.object(client, "_offload_model_if_needed") as offload:
            text = client.generate("hello")
            offload.assert_called_once_with("qwen3.5:4b")

        self.assertEqual(text, "ok")
        _, kwargs = post.call_args_list[0]
        self.assertEqual(kwargs["timeout"], 210)
        self.assertEqual(kwargs["json"]["keep_alive"], "0")
        self.assertFalse(kwargs["json"]["think"])
        self.assertEqual(kwargs["json"]["options"]["num_predict"], 900)

    @patch("services.ollama_client.requests.post")
    def test_generate_uses_custom_keep_alive(self, post: MagicMock) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "ok"}
        post.return_value = response

        client = OllamaClient(
            "http://localhost:11434",
            "qwen3.5:4b",
            keep_alive="30s",
        )
        client.generate("hello")

        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["keep_alive"], "30s")

    @patch("services.ollama_client.requests.get")
    def test_health_uses_configured_timeout(self, get: MagicMock) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"models": [{"name": "qwen3.5:4b"}]}
        get.return_value = response

        client = OllamaClient(
            "http://localhost:11434",
            "qwen3.5:4b",
            health_timeout_sec=9,
        )
        health = client.health()

        self.assertEqual(health["status"], "ok")
        _, kwargs = get.call_args
        self.assertEqual(kwargs["timeout"], 9)

    @patch("services.ollama_client.requests.post")
    def test_generate_retries_without_images_when_runner_stops(self, post: MagicMock) -> None:
        first = MagicMock()
        first.raise_for_status.return_value = None
        first.json.return_value = {
            "error": "model runner has unexpectedly stopped, this may be due to resource limitations"
        }
        second = MagicMock()
        second.raise_for_status.return_value = None
        second.json.return_value = {"response": "ok after retry"}
        post.side_effect = [first, second]

        client = OllamaClient(
            "http://localhost:11434",
            "qwen3.5:4b",
            num_predict=512,
        )
        with patch.object(client, "_offload_model_if_needed") as offload:
            text = client.generate("hello", images=["abc123"])
            offload.assert_called_once_with("qwen3.5:4b")

        self.assertEqual(text, "ok after retry")
        self.assertEqual(post.call_count, 2)
        first_payload = post.call_args_list[0].kwargs["json"]
        second_payload = post.call_args_list[1].kwargs["json"]
        self.assertIn("images", first_payload)
        self.assertNotIn("images", second_payload)
        self.assertEqual(second_payload["options"]["num_predict"], 256)
        self.assertFalse(second_payload["think"])

    @patch("services.ollama_client.requests.post")
    def test_generate_raises_clear_error_after_resource_failures(self, post: MagicMock) -> None:
        failure = MagicMock()
        failure.raise_for_status.return_value = None
        failure.json.return_value = {
            "error": "model runner has unexpectedly stopped, this may be due to resource limitations"
        }
        post.side_effect = [failure, failure, failure]

        client = OllamaClient(
            "http://localhost:11434",
            "qwen3.5:4b",
            num_predict=600,
        )
        with patch.object(client, "_offload_model_if_needed") as offload:
            with self.assertRaises(AppError) as ctx:
                client.generate("hello", images=["abc123"])
            offload.assert_called_once_with("qwen3.5:4b")

        self.assertEqual(post.call_count, 3)
        self.assertEqual(ctx.exception.code, "GENERATION_FAILED")
        self.assertIn("resource pressure", ctx.exception.message.lower())

    @patch("services.ollama_client.requests.post")
    def test_generate_offloads_model_when_keep_alive_zero(self, post: MagicMock) -> None:
        generated = MagicMock()
        generated.raise_for_status.return_value = None
        generated.json.return_value = {"response": "ok"}
        unloaded = MagicMock()
        unloaded.raise_for_status.return_value = None
        unloaded.json.return_value = {"response": ""}
        post.side_effect = [generated, unloaded]

        client = OllamaClient(
            "http://localhost:11434",
            "qwen3.5:4b",
            keep_alive="0",
        )
        text = client.generate("hello")

        self.assertEqual(text, "ok")
        self.assertEqual(post.call_count, 2)
        first_call = post.call_args_list[0].kwargs
        second_call = post.call_args_list[1].kwargs
        self.assertEqual(first_call["json"]["prompt"], "hello")
        self.assertEqual(second_call["json"]["model"], "qwen3.5:4b")
        self.assertEqual(second_call["json"]["keep_alive"], "0")
        self.assertEqual(second_call["json"]["prompt"], "")

    @patch("services.ollama_client.requests.post")
    def test_generate_does_not_offload_when_keep_alive_nonzero(self, post: MagicMock) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "ok"}
        post.return_value = response

        client = OllamaClient(
            "http://localhost:11434",
            "qwen3.5:4b",
            keep_alive="30s",
        )
        text = client.generate("hello")

        self.assertEqual(text, "ok")
        self.assertEqual(post.call_count, 1)

    @patch("services.ollama_client.requests.post")
    def test_generate_ignores_offload_errors(self, post: MagicMock) -> None:
        generated = MagicMock()
        generated.raise_for_status.return_value = None
        generated.json.return_value = {"response": "ok"}
        post.side_effect = [generated, requests.exceptions.ConnectionError("unreachable")]

        client = OllamaClient(
            "http://localhost:11434",
            "qwen3.5:4b",
            keep_alive="0",
        )
        text = client.generate("hello")

        self.assertEqual(text, "ok")
        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
