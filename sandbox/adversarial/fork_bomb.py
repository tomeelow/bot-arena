"""Forks as fast as it can; the children sleep forever. The task limit stops it, and the
match goes on. Expected: plays on, nothing leaks."""

import os
import time

from arena import Bot


class ForkBomb(Bot):
    def act(self, obs):
        if obs.turn == 0:
            forked = 0
            for _ in range(1000):
                try:
                    if os.fork() == 0:
                        time.sleep(10**6)
                        os._exit(0)
                    forked += 1
                except OSError:
                    pass
            if forked > 16:
                self.log(f"ESCAPED: forked {forked} processes")
        return []
