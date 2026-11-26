"""Finds the protocol pipe and writes junk into it. Expected: invalid_output."""

import os
import stat

from arena import Bot


def protocol_fds():
    return [fd for fd in range(3, 64) if _is_pipe(fd)]


def _is_pipe(fd):
    try:
        return stat.S_ISFIFO(os.fstat(fd).st_mode)
    except OSError:
        return False


class ProtocolGarbage(Bot):
    def act(self, obs):
        for fd in protocol_fds():
            os.write(fd, b"this is not json\n")
        return []
