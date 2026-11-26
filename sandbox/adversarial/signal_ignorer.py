"""Ignores every signal it can, then hangs. Only SIGKILL (cgroup.kill) ends it.
Expected: timeout, and nothing leaks."""

import signal
import time

from arena import Bot


class SignalIgnorer(Bot):
    def setup(self):
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT):
            signal.signal(sig, signal.SIG_IGN)

    def act(self, obs):
        time.sleep(3600)
        return []
