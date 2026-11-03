"""Sequence the SDK's cached motions without overlapping the same instance."""
from __future__ import annotations

from .. import startup_log


class MotionPlayback:
    def __init__(self):
        self.state = None
        self.current_group = None
        self.pending_group = None
        self.inflight = set()

    def update(self, model, state, available):
        # IsMotionFinished() covers the whole native queue, including motions
        # fading out. StartMotion() reuses a cached motion and its callback data;
        # do not reuse that object until all earlier entries have drained.
        finished = model.IsMotionFinished()
        if finished:
            self.inflight.clear()
            self.current_group = None

        if state != self.state:
            group = ("SeedWave" if state == "wave" else
                     "SeedReturn" if self.state == "wave" else "SeedIdle")
            self.pending_group = group if group in available else None
            self.state = state

        # An expression change does not restart the idle animation.
        if self.pending_group == self.current_group:
            self.pending_group = None
        if self.pending_group is None and finished and "SeedIdle" in available:
            self.pending_group = "SeedIdle"

        group = self.pending_group
        if group is None or group in self.inflight:
            return
        # Idle has lower priority than gestures. Wait for the queue to drain
        # rather than treating a rejected low-priority start as a new motion.
        if group == "SeedIdle" and not finished:
            return
        stage = {"SeedIdle": "idle", "SeedWave": "wave", "SeedReturn": "return"}[group]
        startup_log.mark("live2d.motion." + stage + ".begin")
        model.StartMotion(group, 0, 1 if group == "SeedIdle" else 3)
        startup_log.mark("live2d.motion." + stage + ".ready")
        self.inflight.add(group)
        self.current_group = group
        self.pending_group = None
