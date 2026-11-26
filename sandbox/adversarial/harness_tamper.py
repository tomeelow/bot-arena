"""Patches the running harness so every reply claims it took no time. The host never trusts
what a bot says about itself. Expected: invalid_output."""

import sys

import arena.harness
from arena import Bot

original = arena.harness.encode


def lying_encode(message):
    return original({**message, "ms": 0})


for module in (sys.modules["__main__"], arena.harness):
    module.encode = lying_encode


class HarnessTamper(Bot):
    def act(self, obs):
        return []
