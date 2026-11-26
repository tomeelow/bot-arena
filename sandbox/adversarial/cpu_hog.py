"""Uses 300 ms of CPU every turn: under the backstop, over the budget. The time bank drains.
Expected: timeout (time bank)."""

import time

from arena import Bot


class CpuHog(Bot):
    def act(self, obs):
        end = time.process_time() + 0.3
        while time.process_time() < end:
            pass
        return []
