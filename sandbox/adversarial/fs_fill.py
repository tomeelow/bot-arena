"""Writes to /tmp until it's full. Expected: plays on, or loses on memory: either way only
inside its own small tmpfs."""

from arena import Bot


class FsFill(Bot):
    def act(self, obs):
        if obs.turn == 0:
            written = 0
            try:
                with open("/tmp/fill", "wb") as f:
                    while written < 2**30:
                        f.write(b"\0" * 2**20)
                        written += 2**20
            except OSError:
                pass
            if written > 64 * 2**20:
                self.log(f"ESCAPED: wrote {written >> 20} MiB to /tmp")
        return []
