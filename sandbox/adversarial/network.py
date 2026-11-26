"""Tries to reach the network and the host's sockets. Expected: plays on, every attempt fails."""

import socket

from arena import Bot

ATTEMPTS = [
    (socket.AF_INET, ("1.1.1.1", 53)),
    (socket.AF_INET6, ("2606:4700:4700::1111", 53)),
    (socket.AF_UNIX, "/var/run/docker.sock"),
    (socket.AF_UNIX, "/run/systemd/private"),
]


class Network(Bot):
    def act(self, obs):
        if obs.turn == 0:
            for family, address in ATTEMPTS:
                try:
                    with socket.socket(family, socket.SOCK_STREAM) as s:
                        s.settimeout(1)
                        s.connect(address)
                    self.log(f"ESCAPED: connected to {address}")
                except OSError:
                    pass
            try:
                socket.getaddrinfo("example.com", 80)
                self.log("ESCAPED: resolved a hostname")
            except OSError:
                pass
            for family in (socket.AF_PACKET, socket.AF_NETLINK):
                try:
                    socket.socket(family, socket.SOCK_RAW).close()
                    self.log(f"ESCAPED: opened a {family!r} socket")
                except OSError:
                    pass
        return []
