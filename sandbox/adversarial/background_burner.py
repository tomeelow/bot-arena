"""Answers instantly, but a background thread burns CPU between turns. All of a bot's CPU
counts: against a fast opponent the stolen time per turn is tiny and it plays on; against
one that takes its time, the bank drains (see test_adversarial.py). Expected: plays on, or
timeout."""

import threading

from arena import Bot


def burn():
    while True:
        pass


class BackgroundBurner(Bot):
    def setup(self):
        threading.Thread(target=burn, daemon=True).start()

    def act(self, obs):
        return []
