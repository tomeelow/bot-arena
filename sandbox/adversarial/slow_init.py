"""Spins forever in setup. Expected: timeout."""

from arena import Bot


class SlowInit(Bot):
    def setup(self):
        while True:
            pass

    def act(self, obs):
        return []
