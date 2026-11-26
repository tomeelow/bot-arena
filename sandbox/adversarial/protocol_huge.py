"""Writes a 16 MiB line into the protocol pipe. Expected: invalid_output."""

import os
import stat

from arena import Bot


class ProtocolHuge(Bot):
    def act(self, obs):
        for fd in range(3, 64):
            try:
                if stat.S_ISFIFO(os.fstat(fd).st_mode):
                    os.write(fd, b"[" * 16 * 2**20)
            except OSError:
                pass
        return []
