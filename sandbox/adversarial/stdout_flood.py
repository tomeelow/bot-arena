"""Prints hundreds of megabytes in one turn into its log. Expected: memory."""

from arena import Bot


class StdoutFlood(Bot):
    def act(self, obs):
        chunk = "x" * 2**20
        for _ in range(1024):
            print(chunk)
        return []
