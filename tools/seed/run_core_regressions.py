"""Explicit user entry: source regression suite, never part of app startup/build."""
from contextlib import ExitStack, redirect_stderr
import argparse
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    "test_template_memory", "test_multilingual_recall", "test_memory_evolution", "test_resource_status",
    "test_action_outcomes", "test_action_proposals", "test_action_archive", "test_durability", "test_backup", "test_continuity",
    "test_lifecycle", "test_learning", "test_learning_strategies", "test_learning_observations", "test_same_goal_observations", "test_learning_retrieval", "test_learning_choices", "test_life_story", "test_seedbank.ClockTest",
    "test_development", "test_goal_provenance", "test_goal_history", "test_judgment_history", "test_initiative_calendar", "test_disclosure", "test_story_lineage", "test_memory_policy_loading", "test_codex_transport", "test_model_budget",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--goal-provenance", action="store_true", help="Run only the offline goal provenance module.")
    scope.add_argument("--learning-choices", action="store_true", help="Run offline learning, retrieval and strategy-choice regressions.")
    scope.add_argument("--initiative-calendar", action="store_true", help="Run offline clock, initiative and goal provenance checks.")
    args = parser.parse_args()
    modules = ("test_goal_provenance",) if args.goal_provenance else MODULES
    if args.learning_choices:
        modules = ("test_learning", "test_learning_observations", "test_same_goal_observations", "test_learning_retrieval", "test_learning_choices")
    if args.initiative_calendar:
        modules = ("test_initiative_calendar", "test_seedbank.ClockTest", "test_seedbank.AgencyTest", "test_goal_provenance")
    print("SEEDbank offline core regressions — source snapshot, not the packaged UI", flush=True)
    print("Snapshot: " + str(ROOT), flush=True)
    print("Modules: " + ", ".join(modules), flush=True)
    print("Temporary life packs and isolated process configuration; network access blocked.", flush=True)
    with tempfile.TemporaryDirectory(prefix="seedbank-user-regressions-") as directory, ExitStack() as stack:
        # Preserve diagnostics without PowerShell treating normal simulated
        # failure warnings on Python stderr as NativeCommandError records.
        stack.enter_context(redirect_stderr(sys.stdout))
        test_root = Path(directory)
        isolated_home = test_root / "home"
        isolated_home.mkdir()
        guard = ROOT / "packaging/test_support"
        stack.enter_context(patch.dict(os.environ, {
            "HOME": str(isolated_home), "USERPROFILE": str(isolated_home),
            "APPDATA": str(isolated_home / "AppData/Roaming"),
            "LOCALAPPDATA": str(isolated_home / "AppData/Local"),
            "SEEDBANK_LANG": "zh_CN", "SEEDBANK_OFFLINE_REGRESSION": "1",
            "PYTHONPATH": os.pathsep.join((str(guard), str(ROOT / "tools/seed"))),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
        }))
        sys.path.insert(0, str(guard))
        # Install in this interpreter as well as the crash-recovery child interpreters.
        spec = importlib.util.spec_from_file_location("seedbank_test_network_guard", guard / "sitecustomize.py")
        network_guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(network_guard)
        suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
        result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
        if any(name.startswith(("test_quick", "test_live2d", "test_window_geometry")) for name in modules):
            print("Scope: isolated source logic / Qt tests; SDK mocks where specified. No real model API, QQ or long-run acceptance.", flush=True)
        else:
            print("Scope: offline Python logic only. No GUI, Live2D, real model, QQ or long-run acceptance.", flush=True)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
