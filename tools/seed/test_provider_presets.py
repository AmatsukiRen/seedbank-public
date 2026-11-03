"""User-run offline service compatibility checks; no real credentials/network."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from seedbank import brain, settings
from seedbank.pack import hatch
from seedbank.providers import ADDITIONAL_PRESETS, validate_connection


def reply(content='{"reply":"人工回答"}', finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


class ProviderTest(unittest.TestCase):
    def test_every_new_service_routes_one_request_with_own_config(self):
        for preset in ADDITIONAL_PRESETS:
            with self.subTest(provider=preset["provider"]):
                config = {**preset, "model": "artificial-model"}
                with mock.patch.object(brain, "_key_for", return_value="artificial-key"), \
                        mock.patch.object(brain, "_post_json", return_value=reply()) as post:
                    self.assertIn("人工回答", brain.openai_transport(config, "Return JSON", "Hello"))
                post.assert_called_once()
                endpoint, headers, payload = post.call_args.args
                self.assertEqual(endpoint, preset["base_url"] + "/chat/completions")
                self.assertEqual(headers["authorization"], "Bearer artificial-key")
                self.assertEqual(payload["model"], "artificial-model")
                self.assertNotIn("temperature", payload)
                self.assertNotIn("response_format", payload)
                self.assertNotIn("artificial-key", str(payload))

    def test_empty_model_is_rejected_before_loading_credentials(self):
        with mock.patch.object(brain, "_key_for") as key, mock.patch.object(brain, "_post_json") as post:
            for preset in ADDITIONAL_PRESETS:
                with self.subTest(provider=preset["provider"]), self.assertRaises(brain.BrainConfigError):
                    brain.openai_transport(preset, "JSON", "hello")
            key.assert_not_called()
            post.assert_not_called()

    def test_invalid_root_address_is_rejected(self):
        for url in ("https://host/v1/chat/completions", "https://host/v1/responses", "https://host/v1/messages",
                    "https://name:secret@host/v1", "https://host/v1?key=secret", "https://<workspace>.host/v1",
                    "https://host:wrong/v1", "https://host/v1#key"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_connection({"adapter": "openai-compatible", "base_url": url})

    def test_legacy_temperature_and_json_mode_are_preserved(self):
        with mock.patch.object(brain, "_post_json", return_value=reply()) as post:
            brain.openai_transport({"adapter": "openai-compatible", "base_url": "http://localhost:1234/v1",
                                    "temperature": .3}, "JSON", "hello")
        payload = post.call_args.args[2]
        self.assertEqual(payload["temperature"], .3)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("authorization", post.call_args.args[1])

    def test_parameter_failure_is_not_retried(self):
        with mock.patch.object(brain, "_post_json", side_effect=RuntimeError("HTTP 400: response_format unsupported")) as post:
            with self.assertRaises(RuntimeError):
                brain.openai_transport({"base_url": "http://localhost:1234/v1"}, "JSON", "hello")
        post.assert_called_once()

    def test_minimax_separates_reasoning_and_ignores_inline_think_json(self):
        config = {**next(p for p in ADDITIONAL_PRESETS if p["provider"] == "minimax"), "model": "artificial-model"}
        answer = '<think>{"reply":"not the answer"}</think> {"reply":"answer"}'
        with mock.patch.object(brain, "_key_for", return_value="fake-key"), \
                mock.patch.object(brain, "_post_json", return_value=reply(answer)) as post:
            result = brain.openai_transport(config, "JSON", "hello")
        self.assertTrue(post.call_args.args[2]["reasoning_split"])
        self.assertEqual(brain.parse_json_loose(result)["reply"], "answer")

    def test_minimax_parameters_are_not_sent_to_lookalike_hosts(self):
        with mock.patch.object(brain, "_key_for", return_value="fake-key"), \
                mock.patch.object(brain, "_post_json", return_value=reply()) as post:
            brain.openai_transport({"base_url": "https://api.minimax.cn.example.invalid/v1"}, "JSON", "hello")
        self.assertNotIn("reasoning_split", post.call_args.args[2])

    def test_text_content_blocks_exclude_reasoning(self):
        content = [{"type": "reasoning", "text": "hidden"}, {"type": "text", "text": '{"reply":'},
                   {"type": "text", "text": '"hello"}'}]
        with mock.patch.object(brain, "_post_json", return_value=reply(content)):
            result = brain.openai_transport({"base_url": "http://localhost:1234/v1"}, "JSON", "hello")
        self.assertEqual(result, '{"reply":"hello"}')

    def test_empty_reasoning_only_and_truncated_responses_fail(self):
        responses = [reply(None), reply(""), reply('{"reply":"partial"}', "length"), reply("blocked", "content_filter")]
        responses[0]["choices"][0]["message"]["reasoning_content"] = '{"reply":"must not use"}'
        for response in responses:
            with self.subTest(response=response), mock.patch.object(brain, "_post_json", return_value=response):
                with self.assertRaises(RuntimeError):
                    brain.openai_transport({"base_url": "http://localhost:1234/v1"}, "JSON", "hello")

    def test_images_do_not_enable_json_mode(self):
        with mock.patch.object(brain, "_post_json", return_value=reply("an artificial image")) as post:
            brain.openai_transport({"base_url": "http://localhost:1234/v1", "response_format_mode": "json_object"},
                                   "describe", "image", image={"mime": "image/png", "data": "FAKE"})
        payload = post.call_args.args[2]
        self.assertNotIn("response_format", payload)
        self.assertEqual(payload["messages"][1]["content"][1]["type"], "image_url")

    def test_anthropic_can_use_service_default_temperature(self):
        with mock.patch.object(brain, "_post_json", return_value={"content": [{"type": "text", "text": "hello"}]}) as post:
            brain.anthropic_transport({"base_url": "http://localhost:1234", "temperature_mode": "default"}, "hello", "hi")
        self.assertNotIn("temperature", post.call_args.args[2])
        self.assertEqual(post.call_args.args[0], "http://localhost:1234/v1/messages")

    def test_options_persist_and_birth_remains_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="seedbank-providers-") as directory:
            pack = Path(directory) / "artificial.life"
            hatch(pack, Path(__file__).resolve().parents[2] / "eggs" / "open.egg", "人工接入")
            birth = (pack / "birth.json").read_bytes()
            result = settings.save_settings(pack, {**ADDITIONAL_PRESETS[0], "model": "artificial-model"})
            self.assertEqual(result["provider"], "gemini")
            self.assertEqual(result["response_format_mode"], "prompt")
            self.assertEqual(result["temperature_mode"], "default")
            self.assertEqual(settings.load_settings(pack), result)
            self.assertEqual((pack / "birth.json").read_bytes(), birth)

    def test_connection_check_prompts_for_json_without_changing_saved_config(self):
        with mock.patch.object(settings, "_merged_brain_config", return_value={"adapter": "openai-compatible"}), \
                mock.patch.object(settings, "openai_transport", return_value='{"message":"好"}') as transport:
            success, _message = settings.test_brain("unused-artificial-path")
        self.assertTrue(success)
        self.assertIn("JSON", transport.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
