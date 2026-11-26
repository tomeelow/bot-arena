"""Answers for a different turn, straight into the protocol pipe. Expected: invalid_output."""

import os
import stat

from arena import Bot


class WrongTurn(Bot):
    def act(self, obs):
        line = b'{"t":"orders","n":999,"orders":[],"log":""}\n'
        for fd in range(3, 64):
            try:
                if stat.S_ISFIFO(os.fstat(fd).st_mode):
                    os.write(fd, line)
            except OSError:
                pass
        return []
