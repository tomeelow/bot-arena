"""Sleeps instead of answering: no CPU used, so only the wall clock catches it.
Expected: timeout."""

import time

from arena import Bot


class Sleeper(Bot):
    def act(self, obs):
        time.sleep(3600)
        return []
