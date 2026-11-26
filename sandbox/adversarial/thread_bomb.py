"""Starts threads until it can't. Expected: plays on, nothing leaks."""

import threading
import time

from arena import Bot


class ThreadBomb(Bot):
    def act(self, obs):
        if obs.turn == 0:
            started = 0
            for _ in range(1000):
                try:
                    threading.Thread(target=time.sleep, args=(10**6,), daemon=True).start()
                    started += 1
                except RuntimeError:
                    break
            if started > 16:
                self.log(f"ESCAPED: started {started} threads")
        return []
