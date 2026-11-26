"""Spins forever on its first turn. Expected: timeout (wall-clock backstop)."""

from arena import Bot


class InfiniteLoop(Bot):
    def act(self, obs):
        while True:
            pass
