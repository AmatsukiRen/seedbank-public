"""Retired sidebar stage; preserve callers without reactivating PNG artwork."""

from ..desktop.pet import PetStage


class _PetStage(PetStage):
    REQUEST_H = 250

    def __init__(self, master, *, bg=None):
        super().__init__(master, bg=bg)
        self.configure(height=self.REQUEST_H)

    def set_compact(self, compact):
        self.configure(height=180 if compact else self.REQUEST_H)

    def play(self, state="idle", loop=True):
        return super().play(state)

    def play_once(self, state):
        return self.play(state, loop=False)

    def greet(self):
        return self.play("wave")

    def happy(self):
        return self.play("happy")

    def celebrate(self):
        return self.play("dance")

    def idle(self):
        return self.play("idle")

    def toggle_dance(self):
        return self.play("dance")

    def wake(self):
        return self.play("idle")

    def touch(self):
        pass
