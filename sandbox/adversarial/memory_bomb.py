"""Allocates until something stops it. Expected: memory."""

from arena import Bot


class MemoryBomb(Bot):
    def act(self, obs):
        hoard = []
        while True:
            hoard.append(bytearray(16 * 2**20))
