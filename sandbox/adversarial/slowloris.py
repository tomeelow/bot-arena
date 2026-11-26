"""Writes half a reply, then stalls. Expected: timeout."""

import os
import stat
import time

from arena import Bot


class Slowloris(Bot):
    def act(self, obs):
        for fd in range(3, 64):
            try:
                if stat.S_ISFIFO(os.fstat(fd).st_mode):
                    os.write(fd, b'{"t":"orders",')
            except OSError:
                pass
        time.sleep(3600)
        return []
