"""User-run offline credential regressions. Only artificial keys/temp homes."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from seedbank import brain, credentials, settings
from seedbank.pack import hatch

KEY = "seedbank-artificial-key-not-a-real-secret"
CONFIG = {"adapter": "openai-compatible", "model": "example-model",
          "base_url": "https://example.invalid/v1", "api_key_source": "local"}
EGG = Path(__file__).resolve().parents[2] / "eggs" / "open.egg"


class CredentialTest(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix="seedbank-credential-test-")
        self.addCleanup(workspace.cleanup)
        self.home = Path(workspace.name)
        patch = mock.patch.object(credentials.Path, "home", return_value=self.home)
        patch.start()
        self.addCleanup(patch.stop)

    def test_legacy_environment_key_still_resolves(self):
        with mock.patch.dict(os.environ, {"SEEDBANK_ARTIFICIAL_TEST_KEY": KEY}):
            self.assertEqual(brain._key_for({"api_key_env": "SEEDBANK_ARTIFICIAL_TEST_KEY"}), KEY)

    def test_local_endpoint_never_reads_saved_key(self):
        with mock.patch.object(credentials, "load", side_effect=AssertionError("must not decrypt")):
            self.assertEqual(brain._key_for({**CONFIG, "base_url": "http://localhost:1234/v1", "api_key_ref": "x"}), "")

    def test_missing_local_key_does_not_fall_back_to_environment(self):
        with mock.patch.dict(os.environ, {"SEEDBANK_API_KEY": KEY}):
            with self.assertRaises(brain.BrainConfigError):
                brain._key_for({**CONFIG, "api_key_env": "SEEDBANK_API_KEY"})

    def test_reference_cannot_escape_store(self):
        for reference in ("../outside", "C:/outside", "", "a" * 31, "g" * 32):
            with self.subTest(reference=reference), self.assertRaises(credentials.CredentialError):
                credentials._path(reference)

    def test_invalid_endpoint_rejected_before_encryption(self):
        with mock.patch.object(credentials, "_crypt", side_effect=AssertionError("must not encrypt")):
            for address in ("http://example.invalid/v1", "https://name:secret@example.invalid", "https://example.invalid?key=x", "bad"):
                with self.subTest(address=address), self.assertRaises(credentials.CredentialError):
                    credentials.store(KEY, {**CONFIG, "base_url": address})

    def test_failed_encryption_does_not_write_plaintext(self):
        with mock.patch.object(credentials, "_crypt", side_effect=credentials.CredentialError("unavailable")):
            with self.assertRaises(credentials.CredentialError):
                credentials.store(KEY, CONFIG)
        self.assertFalse((self.home / ".seedbank" / "credentials").exists())

    def test_brain_configuration_refuses_plaintext_key_fields(self):
        for field in ("api_key", "api_key_draft"):
            with self.subTest(field=field), self.assertRaises(brain.BrainConfigError):
                brain.save_brain_config(self.home, {field: KEY})
        self.assertFalse((self.home / "mind" / "brain.json").exists())

    def test_http_error_does_not_echo_key(self):
        failure = urllib.error.HTTPError("https://example.invalid", 401, "Unauthorized", {}, io.BytesIO(("invalid key " + KEY).encode()))
        with mock.patch("urllib.request.urlopen", side_effect=failure):
            with self.assertRaises(RuntimeError) as result:
                brain._post_json("https://example.invalid", {"authorization": "Bearer " + KEY}, {})
        self.assertNotIn(KEY, str(result.exception))
        self.assertIn("401", str(result.exception))

    def test_api_key_is_sent_to_original_endpoint_but_not_copied_on_redirect(self):
        for header, value in (("authorization", "Bearer " + KEY), ("x-api-key", KEY)):
            with self.subTest(header=header):
                response = mock.MagicMock()
                response.__enter__.return_value = response
                response.read.return_value = b'{}'
                with mock.patch("urllib.request.urlopen", return_value=response) as send:
                    brain._post_json("https://example.invalid/v1/chat/completions",
                                     {header: value, "Content-Type": "application/json"}, {"text": "artificial"})
                original = send.call_args.args[0]
                self.assertEqual(original.get_header(header.capitalize()), value)
                redirected = urllib.request.HTTPRedirectHandler().redirect_request(
                    original, None, 302, "Found", {}, "https://another.invalid/redirected")
                self.assertNotIn(KEY, str(redirected.header_items()))
                self.assertIsNone(redirected.data)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_dpapi_roundtrip_and_encrypted_storage(self):
        reference = credentials.store(KEY, CONFIG)
        self.assertEqual(credentials.load(reference, CONFIG), KEY)
        self.assertTrue(credentials.available(reference))
        self.assertNotIn(KEY.encode(), credentials._path(reference).read_bytes())
        self.assertEqual(brain._key_for({**CONFIG, "api_key_ref": reference}), KEY)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_key_cannot_be_reused_at_changed_endpoint_or_protocol(self):
        reference = credentials.store(KEY, CONFIG)
        for patch in ({"base_url": "https://other.invalid/v1"}, {"base_url": "https://example.invalid/v2"}, {"adapter": "anthropic"}):
            with self.subTest(patch=patch), self.assertRaises(credentials.CredentialError):
                credentials.load(reference, {**CONFIG, **patch})
        self.assertEqual(credentials.load(reference, {**CONFIG, "model": "other-model"}), KEY)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_save_keeps_key_out_of_pack_journal_and_settings(self):
        pack = self.home / "artificial.life"
        hatch(pack, EGG, "人工测试")
        birth = (pack / "birth.json").read_bytes()
        result = settings.save_settings(pack, CONFIG, api_key=KEY)
        self.assertEqual(result["api_key_source"], "local")
        self.assertNotIn(KEY, json.dumps(result))
        cfg = brain.load_brain_config(pack)
        self.assertEqual(brain._key_for(cfg), KEY)
        for path in pack.rglob("*"):
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes(), str(path))
        self.assertEqual((pack / "birth.json").read_bytes(), birth)
        ref = cfg["api_key_ref"]
        unchanged = settings.save_settings(pack, {"temperature": .4})
        self.assertEqual(unchanged["api_key_ref"], ref)
        replacement = settings.save_settings(pack, CONFIG, api_key=KEY + "-replacement")
        self.assertNotEqual(replacement["api_key_ref"], ref)
        self.assertEqual(brain._key_for(brain.load_brain_config(pack)), KEY + "-replacement")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_missing_or_corrupt_local_file_has_safe_error(self):
        reference = credentials.store(KEY, CONFIG)
        path = credentials._path(reference)
        path.write_bytes(b"not-dpapi")
        with self.assertRaises(credentials.CredentialError):
            credentials.load(reference, CONFIG)
        path.unlink()
        with self.assertRaises(credentials.CredentialError):
            credentials.load(reference, CONFIG)


if __name__ == "__main__":
    unittest.main()
