"""The seccomp deny-list for jailed bots (ADR-002), compiled to BPF when the sandbox image is
built. It runs under Debian's python3-seccomp, not the project's interpreter:

    python3 sandbox/seccomp_policy.py /opt/arena/seccomp.bpf

Namespaces already keep a bot away from the network, the filesystem and other processes.
This takes away the kernel interfaces a jailbreak would start from.

Keep it valid for Debian's Python (3.13), not just the project's 3.14: the image build runs it
with that interpreter, so a 3.14-only construct fails `make sandbox-check`.
"""

import contextlib
import errno
import sys

import seccomp  # Debian's python3-seccomp; only present in the image build stage

DENIED = [
    # kernel and system administration
    "acct", "bpf", "clock_adjtime", "clock_settime", "create_module", "delete_module",
    "finit_module", "get_kernel_syms", "init_module", "kexec_file_load", "kexec_load",
    "lookup_dcookie", "nfsservctl", "perf_event_open", "quotactl", "quotactl_fd", "reboot",
    "settimeofday", "swapoff", "swapon", "syslog", "uselib", "vhangup",
    # mounts and namespaces
    "fsconfig", "fsmount", "fsopen", "fspick", "mount", "mount_setattr", "move_mount",
    "open_tree", "pivot_root", "setns", "umount", "umount2", "unshare",
    # other processes and the kernel's own memory
    "kcmp", "process_vm_readv", "process_vm_writev", "ptrace", "userfaultfd",
    # keyrings, raw file handles, io_uring, personality tricks
    "add_key", "keyctl", "request_key", "name_to_handle_at", "open_by_handle_at",
    "io_uring_enter", "io_uring_register", "io_uring_setup", "personality",
]  # fmt: skip

CLONE_NAMESPACE_FLAGS = [
    0x00000080,  # CLONE_NEWTIME
    0x00020000,  # CLONE_NEWNS
    0x02000000,  # CLONE_NEWCGROUP
    0x04000000,  # CLONE_NEWUTS
    0x08000000,  # CLONE_NEWIPC
    0x10000000,  # CLONE_NEWUSER
    0x20000000,  # CLONE_NEWPID
    0x40000000,  # CLONE_NEWNET
]
AF_UNIX = 1
TIOCSTI = 0x5412


def build() -> seccomp.SyscallFilter:
    f = seccomp.SyscallFilter(defaction=seccomp.ALLOW)
    for name in DENIED:
        with contextlib.suppress(RuntimeError, ValueError):  # not a syscall on this arch
            f.add_rule(seccomp.ERRNO(errno.EPERM), name)
    # clone3 passes its flags in a struct seccomp can't read: refuse it, and libc falls
    # back to clone, whose flags it can.
    f.add_rule(seccomp.ERRNO(errno.ENOSYS), "clone3")
    for flag in CLONE_NAMESPACE_FLAGS:
        f.add_rule(
            seccomp.ERRNO(errno.EPERM), "clone", seccomp.Arg(0, seccomp.MASKED_EQ, flag, flag)
        )
    only_unix = seccomp.Arg(0, seccomp.NE, AF_UNIX)
    f.add_rule(seccomp.ERRNO(errno.EAFNOSUPPORT), "socket", only_unix)
    f.add_rule(
        seccomp.ERRNO(errno.EPERM), "ioctl", seccomp.Arg(1, seccomp.MASKED_EQ, 0xFFFFFFFF, TIOCSTI)
    )
    return f


if __name__ == "__main__":
    with open(sys.argv[1], "wb") as out:
        build().export_bpf(out)
