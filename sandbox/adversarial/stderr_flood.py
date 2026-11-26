"""Writes hundreds of megabytes straight to stderr. The host keeps only a short tail.
Expected: plays on."""

import os

from arena import Bot


class StderrFlood(Bot):
    def act(self, obs):
        if obs.turn == 0:
            chunk = b"y" * 2**20
            for _ in range(256):
                os.write(2, chunk)
        return []
