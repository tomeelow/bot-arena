"""Lifts the recursion limit and recurses forever. Python frames live on the heap since 3.11,
so this ends in the memory limit, or in a stack overflow. Expected: memory or crash."""

import sys

from arena import Bot


def dive(n):
    return dive(n + 1) + 1


class RecursionBomb(Bot):
    def act(self, obs):
        sys.setrecursionlimit(10**8)
        dive(0)
        return []
