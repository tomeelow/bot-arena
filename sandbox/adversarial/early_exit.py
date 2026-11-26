"""Exits mid-match. Expected: crash."""

import os

from arena import Bot


class EarlyExit(Bot):
    def act(self, obs):
        if obs.turn == 3:
            os._exit(0)
        return []
