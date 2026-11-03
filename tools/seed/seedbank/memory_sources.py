"""Source reads shared only during one policy load or enclosing read operation.

The container supplies read-only inputs to suppression folds and is never
kept on a policy, shared between packs, or reused by a later operation. A policy
retains its memory records as before. Readers keep their usual format/version
checks; this is not a persistent derived cache.
"""
from functools import cached_property


class PolicySources:
    def __init__(self, pack):
        self.pack = pack

    @cached_property
    def memories(self):
        from .util import read_memories
        return read_memories(self.pack)

    @cached_property
    def experiences(self):
        from .experience import read
        return read(self.pack)

    @cached_property
    def originals(self):
        return {row["id"]: row for row in self.experiences}

    @cached_property
    def nodes(self):
        return {**{row["id"]: row for row in self.memories}, **self.originals,
                **self.action_rows, **self.goal_rows, **self.judgment_rows}

    @cached_property
    def judgment_rows(self):
        from .judgment_history import project
        return {row["id"]: projected for row in self.development_events if (projected := project(row)) is not None}

    @cached_property
    def goal_rows(self):
        from .goal_history import project
        return {row["id"]: projected for row in self.development_events if (projected := project(row)) is not None}

    @cached_property
    def action_rows(self):
        from .action_archive import project
        return {key: projected for key, row in self.outcomes.items() if (projected := project(row)) is not None}

    @cached_property
    def learning(self):
        from .learning import read
        return read(self.pack)

    @cached_property
    def development_events(self):
        from .development import events
        return events(self.pack)

    @cached_property
    def outcomes(self):
        from .development import load_development
        return {row["id"]: row for row in load_development(self.pack, _events=self.development_events)["outcomes"]}
