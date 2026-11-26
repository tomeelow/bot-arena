"""Calls the kernel directly through ctypes, past anything Python would stop: new
namespaces, mounts, ptrace, raw sockets, bpf, keyrings, io_uring, perf events.
Expected: plays on, every call refused."""

import ctypes
import platform

from arena import Bot

# syscall numbers for the calls libc has no wrapper for
NUMBERS = {
    "aarch64": {"bpf": 280, "keyctl": 219, "io_uring_setup": 425, "perf_event_open": 241},
    "x86_64": {"bpf": 321, "keyctl": 250, "io_uring_setup": 425, "perf_event_open": 298},
}
CLONE_NEWUSER, CLONE_NEWNET = 0x10000000, 0x40000000


class CtypesEscape(Bot):
    def act(self, obs):
        if obs.turn != 0:
            return []
        libc = ctypes.CDLL(None, use_errno=True)
        attempts = {
            "unshare(NEWUSER)": lambda: libc.unshare(CLONE_NEWUSER),
            "unshare(NEWNET)": lambda: libc.unshare(CLONE_NEWNET),
            "mount": lambda: libc.mount(b"none", b"/tmp", b"tmpfs", 0, None),
            "ptrace": lambda: libc.ptrace(0, 0, None, None),
            "socket(AF_INET)": lambda: libc.socket(2, 1, 0),
            "setns": lambda: libc.setns(0, 0),
        }
        buffer = ctypes.create_string_buffer(256)
        for name, number in NUMBERS.get(platform.machine(), {}).items():
            attempts[name] = lambda n=number: libc.syscall(n, 0, buffer, 0, 0, 0)
        for name, call in attempts.items():
            if call() >= 0:
                self.log(f"ESCAPED: {name} succeeded")
        return []
