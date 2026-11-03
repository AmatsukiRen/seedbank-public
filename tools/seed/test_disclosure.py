"""User-run disclosure regressions. Temporary archives and fake transports only.

These cases have been authored, not executed by the agent.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import disclosure, experience, facts, learning, relationships, semantic, requests, persona
from seedbank.brain import RemoteBrain, build_chat_prompt, create_stub_brain
from seedbank.bridge import Bridge
from seedbank.cognition import build_context, chat_turn, start_day, forget_memory, sense_media
from seedbank.memory_state import MemoryPolicy
from seedbank.pack import hatch
from seedbank.retrieval import search
from seedbank.util import SeedError, append_memories, write_file_atomic, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class CapturingBrain:
    name = "stub-fixture"  # Explicitly avoid embedding calls during chat.

    def __init__(self, result=None):
        self.contexts = []
        self.result = result or {"reply": "这次交流已记录。", "memory_writes": []}

    def chat(self, ctx):
        self.contexts.append(deepcopy(ctx))
        return deepcopy(self.result)

    def compose(self, ctx):
        self.contexts.append(deepcopy(ctx))
        return {"title": "交流中的创作", "text": "这是一段在当前范围内完成的文字。"}


class DisclosureTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-disclosure-")
        self.addCleanup(folder.cleanup)
        self.pack = Path(folder.name) / "isolated.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "PRIVATE_NAME", seed_override="private-seed",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("No network"))
        guard.start()
        self.addCleanup(guard.stop)

    def event(self, text, **kwargs):
        return experience.record(self.pack, kind=kwargs.pop("kind", "conversation"), text=text,
                                 day=self.day["dayNo"], source="mind/experiences.jsonl", actor="user", **kwargs)

    def share(self, original=None, text="PUBLIC_EXCERPT", scope="public", **kwargs):
        data = {"scope": scope, "text": text, "reason": "用户选择分享这部分", **kwargs}
        if original:
            data.update(source_id=original["id"], source_hash=disclosure._hash(original))
        return disclosure.perform(self.pack, "excerpt" if original else "profile", data)["record"]

    def revoke(self, record):
        return disclosure.perform(self.pack, "revoke", {"target": record["key"], "expected": record["id"],
                                  "reason": "结束这条分享"})["record"]

    def context(self, scope="qq-group:123", person="", query=""):
        return build_context(self.pack, self.day["dayNo"], self.day["date"], query, use_semantic=False,
                             person_id=person, audience_id=scope)

    def test_private_prose_and_unscoped_sources_never_enter_guest_context(self):
        marker = "PRIVATE_RECORD_74"
        for file in ("mind/self.md", "mind/beliefs.md", "genome/identity.md", "genome/values.md", "world/bible.md"):
            write_file_atomic(self.pack / file, marker)
        self.event(marker)
        append_memories(self.pack, [{"id": "m_private", "text": marker, "day": 1, "kind": "thought"}])
        facts.perform(self.pack, "add", {"subject": "owner", "aspect": "私事", "value": marker})
        # Query does not itself contain the secret; test the actual material supplied.
        ctx = self.context(query="我们以前的私事")
        raw = json.dumps(ctx, ensure_ascii=False)
        self.assertNotIn(marker, raw)
        self.assertNotIn("PRIVATE_NAME", raw)
        self.assertEqual(ctx["recentDays"], [])
        self.assertEqual(ctx["birth"], {})
        self.assertTrue(search(self.pack, marker, use_semantic=False))

    def test_excerpts_do_not_authorize_parents_and_scopes_are_distinct(self):
        original = self.event("PRIVATE_PARENT. PUBLIC_EXCERPT. PRIVATE_SUFFIX.")
        person = relationships.perform(self.pack, "person", {"label": "PRIVATE_PERSON_LABEL"})["person_id"]
        shared = self.share(original, scope="person:" + person)
        own = self.context("person:" + person, person)
        self.assertIn("PUBLIC_EXCERPT", json.dumps(own))
        for secret in ("PRIVATE_PARENT", "PRIVATE_SUFFIX", "PRIVATE_PERSON_LABEL", "PRIVATE_NAME"):
            self.assertNotIn(secret, json.dumps(own))
        self.assertNotIn("PUBLIC_EXCERPT", json.dumps(self.context()))
        policy = disclosure.policy_for(self.pack, "person:" + person, person)
        self.assertFalse(policy.allows(original))
        self.assertTrue(policy.allows(policy.nodes[shared["event_id"]]))

    def test_revocation_hides_derivatives_and_prevents_cached_reply_replay(self):
        shared = self.share()
        brain = CapturingBrain({"reply": "我读到了 PUBLIC_EXCERPT。", "memory_writes": [{"text": "记住 PUBLIC_EXCERPT", "importance": .6}]})
        result = chat_turn(self.pack, "你好", brain, "访客", person_id="", audience_id="qq-group:123", request_id="one")
        self.assertTrue(result["responseEventId"])
        self.assertIn("PUBLIC_EXCERPT", json.dumps(self.context()))
        self.revoke(shared)
        self.assertNotIn("PUBLIC_EXCERPT", json.dumps(self.context()))
        with self.assertRaises(SeedError):
            chat_turn(self.pack, "你好", brain, "访客", person_id="", audience_id="qq-group:123", request_id="one")
        self.assertEqual(len(brain.contexts), 1)
        self.assertEqual(requests.get(self.pack, "one")["status"], "complete")

    def test_changed_forgotten_or_superseded_source_invalidates_sharing(self):
        original = {"id": "m_source", "text": "PUBLIC_EXCERPT PRIVATE_TAIL", "day": 1, "kind": "thought"}
        append_memories(self.pack, [original])
        self.share(original)
        forget_memory(self.pack, original["id"])
        self.assertEqual(self.context()["disclosed"], [])
        source = self.event("SECOND_EXCERPT")
        self.share(source, "SECOND_EXCERPT")
        rows = experience.read(self.pack)
        rows = [{**r, "text": "Changed source"} if r["id"] == source["id"] else r for r in rows]
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        self.assertNotIn("SECOND_EXCERPT", json.dumps(self.context()))
        third = {"id": "m_third", "text": "THIRD_EXCERPT", "day": 1, "kind": "thought"}
        append_memories(self.pack, [third])
        self.share(third, "THIRD_EXCERPT")
        append_memories(self.pack, [{"id": "m_new", "text": "Different", "day": 1, "kind": "correction", "supersedes": "m_third"}])
        self.assertNotIn("THIRD_EXCERPT", json.dumps(self.context()))

    def test_mixed_dependencies_and_legacy_derivatives_are_not_disclosed(self):
        private = self.event("PRIVATE_BASE")
        allowed = self.event("GROUP_INPUT", metadata=disclosure.stamp("qq-group:123"))
        mixed = self.event("MIXED_DERIVATIVE", metadata=disclosure.stamp("qq-group:123"), depends_on=[private["id"], allowed["id"]])
        old = self.event("LEGACY_DERIVATIVE", depends_on=[allowed["id"]])
        policy = disclosure.policy_for(self.pack, "qq-group:123")
        self.assertFalse(policy.allows(mixed))
        self.assertFalse(policy.allows(old))
        self.assertEqual(policy.supports([{"id": r["id"], "source": experience.source_of(r)} for r in (private, allowed)]), [])

    def test_unknown_visitors_do_not_share_history_but_registered_person_does(self):
        brain = CapturingBrain()
        chat_turn(self.pack, "ANONYMOUS_A", brain, "访客", request_id="anon-a")
        chat_turn(self.pack, "hello", brain, "访客", request_id="anon-b")
        self.assertNotIn("ANONYMOUS_A", json.dumps(brain.contexts[-1]))
        person = relationships.perform(self.pack, "person", {"label": "甲"})["person_id"]
        chat_turn(self.pack, "KNOWN_A", brain, "甲", person_id=person)
        chat_turn(self.pack, "hello", brain, "甲", person_id=person)
        self.assertIn("KNOWN_A", json.dumps(brain.contexts[-1]))
        chat_turn(self.pack, "hello", brain, "甲", person_id=person, audience_id="qq-group:123")
        self.assertNotIn("KNOWN_A", json.dumps(brain.contexts[-1]))

    def test_owner_speaking_in_group_does_not_get_private_context(self):
        private = self.event("PRIVATE_OWNER_CONTENT")
        brain = CapturingBrain()
        chat_turn(self.pack, "hello", brain, person_id="owner", audience_id="qq-group:123")
        self.assertNotIn(private["text"], json.dumps(brain.contexts[-1]))
        self.assertEqual(brain.contexts[-1]["bond"], {})
        with self.assertRaises(SeedError):
            chat_turn(self.pack, "hello", brain, "访客", person_id="", audience_id="owner")

    def test_private_report_about_person_does_not_authorize_disclosure_to_them(self):
        person = relationships.perform(self.pack, "person", {"label": "甲"})["person_id"]
        brain = CapturingBrain()
        chat_turn(self.pack, "PRIVATE_REPORT_ABOUT_A", brain, "甲", person_id=person, interaction_kind="reported")
        self.assertEqual(brain.contexts[-1]["_audience_id"], "owner")
        ctx = self.context("person:" + person, person)
        self.assertNotIn("PRIVATE_REPORT_ABOUT_A", json.dumps(ctx))

    def test_model_search_rewrites_and_fallback_keep_same_audience(self):
        self.event("PRIVATE_SEARCH_MARKER")
        self.share()
        prompts = []

        def transport(cfg, system, user):
            prompts.append(system + user)
            if len(prompts) == 1:
                return json.dumps({"memory_search": {"query": "往事", "historical": True}})
            return json.dumps({"reply": "目前只有明确分享的内容。", "memory_writes": []})

        remote = RemoteBrain("fixture", transport)
        chat_turn(self.pack, "回想一下", remote, "访客", audience_id="qq-group:123")
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:
            self.assertNotIn("PRIVATE_SEARCH_MARKER", prompt)
            self.assertNotIn("PRIVATE_NAME", prompt)
        failed = RemoteBrain("fixture", Mock(side_effect=OSError("offline")))
        result = chat_turn(self.pack, "你叫什么", failed, "访客", audience_id="qq-group:123")
        self.assertNotIn("PRIVATE_NAME", result["reply"])

    def test_semantic_refresh_and_index_batch_never_send_private_corpus(self):
        self.event("PRIVATE_EMBEDDING_MARKER")
        self.share(text="PUBLIC_DOCUMENT")
        semantic.configure(self.pack, {"enabled": True, "model": "fixture-embedding", "min_similarity": .5})
        sent = []

        def embed(cfg, texts):
            sent.extend(texts)
            return {"data": [{"index": i, "embedding": [1, 0]} for i in range(len(texts))], "model": "fixture-embedding"}

        with patch("seedbank.semantic._request", side_effect=embed):
            results = search(self.pack, "shared", policy=disclosure.policy_for(self.pack, "qq-group:123"))
        self.assertTrue(results)
        self.assertIn("PUBLIC_DOCUMENT", " ".join(sent))
        self.assertNotIn("PRIVATE_EMBEDDING_MARKER", " ".join(sent))

    def test_guest_cannot_edit_hidden_goals_or_create_private_reminders(self):
        goal = learning.perform(self.pack, "plan", {"title": "PRIVATE_GOAL", "skill": "写作", "reason": "私人计划",
                       "next_step": "继续", "criteria": [{"text": "完成一封信"}]})["goal_id"]
        brain = CapturingBrain({"reply": "继续聊一聊。", "memory_writes": [],
            "development": {"goals": [{"id": goal, "title": "Changed", "status": "abandoned", "reason": "guest", "evidence": ["current"]}]},
            "actions": [{"type": "remind", "text": "SHOULD_NOT_CREATE", "after_days": 1}]})
        with patch("seedbank.cognition.due_reminders", side_effect=AssertionError("private reminder read")):
            result = chat_turn(self.pack, "hello", brain, "访客", audience_id="qq-group:123")
        self.assertEqual(result["developmentChanges"], 0)
        self.assertEqual(result["actionResults"][0]["data"]["status"], "blocked")
        self.assertNotIn("PRIVATE_GOAL", json.dumps(brain.contexts[-1]))

    def test_revocation_applies_to_interpretations_with_partial_citations(self):
        shared = self.share()
        person = relationships.perform(self.pack, "person", {"label": "甲"})["person_id"]
        brain = CapturingBrain({"reply": "我记下了。", "memory_writes": [],
            "development": {"beliefs": [{"text": "PUBLIC_EXCERPT 的理解", "reason": "根据对话", "evidence": ["current"]}]},
            "relationship_notes": [{"person_id": person, "type": "reflection", "text": "PUBLIC_EXCERPT 的相处理解", "quote": "hello"}]})
        chat_turn(self.pack, "hello", brain, "甲", person_id=person)
        self.revoke(shared)
        ctx = self.context("person:" + person, person)
        self.assertEqual(ctx["development"]["beliefs"], [])
        self.assertEqual(ctx["relationships"]["notes"], [])

    def test_sharing_is_local_idempotent_and_requires_unchanged_exact_excerpt(self):
        original = self.event("PRIVATE_PARENT PUBLIC_EXCERPT")
        data = {"scope": "public", "text": "PUBLIC_EXCERPT", "source_id": original["id"],
                "source_hash": disclosure._hash(original), "reason": "选择这段"}
        with patch("seedbank.bridge.create_brain", side_effect=AssertionError("no model")):
            bridge = Bridge(self.pack)
            first = bridge.handle({"op": "disclosure", "action": "excerpt", "data": data, "request_id": "share-once"})
            second = bridge.handle({"op": "disclosure", "action": "excerpt", "data": data, "request_id": "share-once"})
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(len(disclosure.read(self.pack)), 1)
            self.assertTrue(bridge.handle({"op": "disclosure"})["ok"])
        with self.assertRaises(SeedError):
            disclosure.perform(self.pack, "excerpt", {**data, "text": "not in the source"})
        with self.assertRaises(SeedError):
            disclosure.perform(self.pack, "excerpt", {**data, "source_hash": "outdated"})

    def test_failed_save_keeps_explicit_resumable_input(self):
        with patch("seedbank.disclosure.experience.record", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                disclosure.perform(self.pack, "profile", {"scope": "public", "text": "shared intro", "reason": "approve"}, request_id="retry-share")
        self.assertEqual(requests.pending(self.pack)[0]["id"], "retry-share")
        result = Bridge(self.pack, "stub").handle({"op": "resume", "request_id": "retry-share"})
        self.assertTrue(result["ok"])
        self.assertEqual(len(disclosure.read(self.pack)), 1)

    def test_sharing_expires_continuity_sample_and_history_never_reactivates(self):
        persona.capture(self.pack)
        shared = self.share()
        with patch("seedbank.persona.create_brain", side_effect=AssertionError("stale sample")):
            report = persona.check(self.pack)
        self.assertEqual(report["reason"], "stale_sample")
        self.assertIn("mind/disclosure.jsonl", report["archive"]["changed"])
        self.revoke(shared)
        records = disclosure.listing(self.pack, history=True)["records"]
        self.assertEqual(len(records), 2)
        self.assertFalse(any(r["available"] for r in records))
        self.assertEqual(self.context()["disclosed"], [])

    def test_group_media_is_recallable_only_within_its_delivery_scope(self):
        sense_media(self.pack, note="GROUP_MEDIA_NOTE", person_id="", audience_id="qq-group:123", vision=False)
        policy = disclosure.policy_for(self.pack, "qq-group:123")
        self.assertTrue(search(self.pack, "GROUP_MEDIA_NOTE", policy=policy, use_semantic=False))
        other = disclosure.policy_for(self.pack, "qq-group:456")
        self.assertEqual(search(self.pack, "GROUP_MEDIA_NOTE", policy=other, use_semantic=False), [])

    def test_long_dependency_chain_and_cycles(self):
        from seedbank import jsonl
        first = self.event("chain root", metadata=disclosure.stamp("qq-group:123"))
        rows, parent = [], first["id"]
        for i in range(1500):
            identifier = "x_chain_" + str(i)
            rows.append({**first, "id": identifier, "text": "derived", "depends_on": [parent]})
            parent = identifier
        rows.extend([{**first, "id": "x_cycle_a", "depends_on": ["x_cycle_b"]},
                     {**first, "id": "x_cycle_b", "depends_on": ["x_cycle_a"]}])
        jsonl.append(self.pack, experience.path(self.pack), rows, experience._validate)
        policy = disclosure.policy_for(self.pack, "qq-group:123")
        self.assertTrue(policy.allows(policy.nodes[parent]))
        self.assertFalse(policy.allows(policy.nodes["x_cycle_a"]))

    def test_qq_owner_group_and_image_routes_use_group_scope(self):
        from seedbank.qq import QQAdapter
        from test_qq import group_event, private_event
        bridge, sender = Mock(), Mock()
        sender.send_group.return_value = sender.send_private.return_value = {"status": "ok", "retcode": 0}
        bridge.call.return_value = {"reply": "safe", "lines": ["safe image"]}
        adapter = QQAdapter(str(self.pack), "7", ["123"], bridge=bridge, sender=sender, log=lambda value: None)
        self.assertTrue(adapter.handle(group_event(123, 7))["ok"])
        self.assertEqual(bridge.call.call_args.kwargs["audience_id"], "qq-group:123")
        self.assertEqual(bridge.call.call_args.kwargs["person_id"], "")
        adapter.handle(private_event(7))
        self.assertEqual(bridge.call.call_args.kwargs["audience_id"], "owner")
        event = group_event(123, 7)
        event["message"].append({"type": "image", "data": {"url": "https://example.invalid/fixture.png"}})
        image_dir = self.pack.parent / "image-fixture"
        image_dir.mkdir()
        image_file = image_dir / "fixture.png"
        image_file.write_bytes(b"fixture")
        with patch.object(adapter, "_download", return_value=image_file):
            self.assertTrue(adapter.handle(event)["ok"])
        self.assertEqual(bridge.call.call_args.args[0], "image")
        self.assertEqual(bridge.call.call_args.kwargs["audience_id"], "qq-group:123")


if __name__ == "__main__":
    unittest.main()
