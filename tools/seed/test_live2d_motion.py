"""User-run regression cases; no Qt window, native SDK or real model."""
import unittest
from unittest.mock import Mock, call

from seedbank.quick.live2d_motion import MotionPlayback


GROUPS = {"SeedIdle", "SeedWave", "SeedReturn"}


class MotionPlaybackTest(unittest.TestCase):
    def setUp(self):
        self.player = MotionPlayback()
        self.model = Mock()
        self.model.IsMotionFinished.return_value = True

    def start_idle(self):
        self.player.update(self.model, "idle", GROUPS)
        self.model.IsMotionFinished.return_value = False

    def test_expression_changes_do_not_restart_the_active_idle_motion(self):
        self.start_idle()
        for state in ("think", "idle", "happy", "curious", "idle"):
            self.player.update(self.model, state, GROUPS)
        self.model.StartMotion.assert_called_once_with("SeedIdle", 0, 1)

    def test_quick_repeat_waits_for_all_fading_entries_to_drain(self):
        self.start_idle()
        for state in ("wave", "idle", "wave", "wave"):
            self.player.update(self.model, state, GROUPS)
        self.assertEqual(self.model.StartMotion.call_args_list,
                         [call("SeedIdle", 0, 1), call("SeedWave", 0, 3), call("SeedReturn", 0, 3)])
        self.assertEqual(self.player.pending_group, "SeedWave")
        self.model.IsMotionFinished.return_value = True
        self.player.update(self.model, "wave", GROUPS)
        self.assertEqual(self.model.StartMotion.call_args, call("SeedWave", 0, 3))
        self.assertEqual(self.player.inflight, {"SeedWave"})

    def test_latest_request_replaces_a_waiting_gesture(self):
        self.start_idle()
        for state in ("wave", "idle", "wave", "idle"):
            self.player.update(self.model, state, GROUPS)
        self.model.IsMotionFinished.return_value = True
        self.player.update(self.model, "idle", GROUPS)
        # The repeated wave was withdrawn while waiting; the return gesture
        # is still active until the SDK reports its entire queue finished.
        self.assertEqual(sum(c == call("SeedWave", 0, 3) for c in self.model.StartMotion.call_args_list), 1)
        self.assertEqual(self.model.StartMotion.call_args, call("SeedIdle", 0, 1))

    def test_idle_waits_until_a_gesture_finishes(self):
        self.player.update(self.model, "wave", GROUPS)
        self.model.IsMotionFinished.return_value = False
        self.player.update(self.model, "idle", GROUPS)
        self.player.update(self.model, "think", GROUPS)
        self.assertNotIn(call("SeedIdle", 0, 1), self.model.StartMotion.call_args_list)
        self.model.IsMotionFinished.return_value = True
        self.player.update(self.model, "think", GROUPS)
        self.assertEqual(self.model.StartMotion.call_args, call("SeedIdle", 0, 1))

    def test_finished_idle_restarts_once_and_missing_groups_are_never_started(self):
        self.start_idle()
        self.model.IsMotionFinished.return_value = True
        self.player.update(self.model, "idle", GROUPS)
        self.assertEqual(self.model.StartMotion.call_count, 2)
        self.model.IsMotionFinished.return_value = False
        self.player.update(self.model, "idle", GROUPS)
        self.assertEqual(self.model.StartMotion.call_count, 2)
        empty = Mock()
        empty.IsMotionFinished.return_value = True
        fresh = MotionPlayback()
        for state in ("idle", "wave", "think"):
            fresh.update(empty, state, set())
        empty.StartMotion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
