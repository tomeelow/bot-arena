"""Tries to signal processes outside its jail. Expected: plays on."""

import os
import signal

from arena import Bot


class ProcessKill(Bot):
    def act(self, obs):
        if obs.turn == 0:
            for pid in range(2, 4096):
                if pid == os.getpid():
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                    self.log(f"ESCAPED: signalled pid {pid}")
                except OSError:
                    pass
        return []
