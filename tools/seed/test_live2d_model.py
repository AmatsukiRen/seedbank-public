"""User-run asset-reference tests. No Qt, GL, real model or life pack is loaded."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from seedbank.live2d_model import descriptor


class Live2DModelTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="seedbank-avatar-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "模型目录"
        self.root.mkdir()
        self.path = self.root / "大肥鱼.model3.json"
        (self.root / "model.moc3").write_bytes(b"fixture only; never passed to SDK")
        (self.root / "texture.png").write_bytes(b"fixture only; never rendered")
        self.data = {"Version": 3, "FileReferences": {"Moc": "model.moc3", "Textures": ["texture.png"]}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def test_reads_unicode_paths_without_writing_or_copying_originals(self):
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        content, registry = descriptor(self.path)
        self.assertEqual(registry, {"motions": set(), "expressions": set()})
        loaded = json.loads(content)
        self.assertEqual(loaded["FileReferences"]["Moc"], (self.root / "model.moc3").as_posix())
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})

    def test_registers_known_original_motions_and_expressions_only_in_memory(self):
        (self.root / "Animation").mkdir()
        (self.root / "Exp3").mkdir()
        (self.root / "Animation" / "IDLE.motion3.json").write_text("{}", encoding="utf-8")
        (self.root / "Exp3" / "加载.exp3.json").write_text("{}", encoding="utf-8")
        (self.root / "Exp3" / "体型1.exp3.json").write_text("{}", encoding="utf-8")
        original = self.path.read_bytes()
        content, registry = descriptor(self.path)
        self.assertEqual(registry["motions"], {"SeedIdle"})
        self.assertEqual(registry["expressions"], {"SeedThink"})
        self.assertNotIn("体型1", content)
        self.assertEqual(original, self.path.read_bytes())

    def test_missing_texture_fails_before_native_loading(self):
        (self.root / "texture.png").unlink()
        with self.assertRaisesRegex(ValueError, "缺失"):
            descriptor(self.path)

    def test_mood_expressions_register_without_costume_or_body_switches(self):
        (self.root / "Exp3").mkdir()
        for name in ("流泪", "流冷汗", "黑脸", "体型1", "裙子切换", "爱心眼"):
            (self.root / "Exp3" / (name + ".exp3.json")).write_text("{}", encoding="utf-8")
        original = self.path.read_bytes()
        _, registry = descriptor(self.path)
        self.assertEqual(registry["expressions"], {"SeedSad", "SeedNervous", "SeedAngry"})
        self.assertEqual(original, self.path.read_bytes())

    def test_hand_transitions_deliver_full_end_pose_without_rewriting_assets(self):
        animation = self.root / "Animation"
        animation.mkdir()
        for filename, duration, start, end in (
                ("默认手切举手", 1.133, 0, 1), ("举手切默认手", 1.017, 1, 0)):
            motion = {"Version": 3, "Meta": {"Duration": duration}, "Curves": [
                {"Target": "Parameter", "Id": "Movement2",
                 "Segments": [0, start, 0, duration, end]}]}
            (animation / (filename + ".motion3.json")).write_text(json.dumps(motion), encoding="utf-8")
        (animation / "IDLE.motion3.json").write_text("{}", encoding="utf-8")
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}

        content, registry = descriptor(self.path)
        motions = json.loads(content)["FileReferences"]["Motions"]
        for group, filename in (("SeedWave", "默认手切举手"), ("SeedReturn", "举手切默认手")):
            # Cubism otherwise defaults to a one-second fade-out: the saved
            # pose can retain a partial hand layer after a one-second gesture.
            self.assertEqual(motions[group], [{
                "File": (animation / (filename + ".motion3.json")).as_posix(),
                "FadeOutTime": 0.0}])
        self.assertEqual(motions["SeedIdle"], [{"File": (animation / "IDLE.motion3.json").as_posix()}])
        self.assertEqual(registry["motions"], {"SeedIdle", "SeedWave", "SeedReturn"})
        self.assertEqual(before, {path.relative_to(self.root): path.read_bytes()
                                  for path in self.root.rglob("*") if path.is_file()})

    def test_explicit_hand_motion_settings_are_preserved(self):
        animation = self.root / "Animation"
        animation.mkdir()
        (animation / "默认手切举手.motion3.json").write_text("{}", encoding="utf-8")
        (animation / "举手切默认手.motion3.json").write_text("{}", encoding="utf-8")
        chosen = self.root / "chosen.motion3.json"
        chosen.write_text("{}", encoding="utf-8")
        self.data["FileReferences"]["Motions"] = {
            "SeedWave": [{"File": chosen.name, "FadeInTime": 0.2, "FadeOutTime": 0.6}],
            "SeedReturn": []}
        self.save()
        content, registry = descriptor(self.path)
        self.assertEqual(json.loads(content)["FileReferences"]["Motions"], {
            "SeedWave": [{"File": chosen.as_posix(), "FadeInTime": 0.2, "FadeOutTime": 0.6}],
            "SeedReturn": []})
        self.assertEqual(registry["motions"], {"SeedWave"})

    def test_model_references_cannot_escape_selected_directory(self):
        outside = self.root.parent / "outside.moc3"
        outside.write_bytes(b"outside")
        self.data["FileReferences"]["Moc"] = "../outside.moc3"
        self.save()
        with self.assertRaises(ValueError):
            descriptor(self.path)

    def test_remote_texture_is_rejected_without_network(self):
        self.data["FileReferences"]["Textures"] = ["https://invalid.example/texture.png"]
        self.save()
        with self.assertRaises(ValueError):
            descriptor(self.path)

    def test_custom_model_keeps_its_own_registry(self):
        custom = self.root / "another.model3.json"
        custom.write_bytes(self.path.read_bytes())
        (self.root / "Animation").mkdir()
        (self.root / "Animation" / "IDLE.motion3.json").write_text("{}", encoding="utf-8")
        _, registry = descriptor(custom)
        self.assertEqual(registry["motions"], set())

    def test_malformed_registry_is_rejected(self):
        for key, value in (("Motions", []), ("Expressions", {}), ("Textures", "texture.png")):
            with self.subTest(key=key):
                self.data["FileReferences"] = {"Moc": "model.moc3", "Textures": ["texture.png"], key: value}
                self.save()
                with self.assertRaises(ValueError):
                    descriptor(self.path)

    def test_existing_named_motion_is_not_replaced_by_builtin_registry(self):
        (self.root / "Animation").mkdir()
        (self.root / "Animation" / "IDLE.motion3.json").write_text("{}", encoding="utf-8")
        chosen = self.root / "chosen.motion3.json"
        chosen.write_text("{}", encoding="utf-8")
        self.data["FileReferences"]["Motions"] = {"SeedIdle": [{"File": chosen.name, "FadeInTime": 0.8}]}
        self.save()
        before = self.path.read_bytes()
        content, registry = descriptor(self.path)
        self.assertEqual(json.loads(content)["FileReferences"]["Motions"]["SeedIdle"],
                         [{"File": chosen.as_posix(), "FadeInTime": 0.8}])
        self.assertIn("SeedIdle", registry["motions"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_motion_group_is_preserved_but_never_offered_to_renderer(self):
        (self.root / "Animation").mkdir()
        (self.root / "Animation" / "IDLE.motion3.json").write_text("{}", encoding="utf-8")
        self.data["FileReferences"]["Motions"] = {"SeedIdle": [], "SeedWave": []}
        self.save()
        content, registry = descriptor(self.path)
        self.assertEqual(json.loads(content)["FileReferences"]["Motions"]["SeedIdle"], [])
        self.assertEqual(registry["motions"], set())


if __name__ == "__main__":
    unittest.main()
