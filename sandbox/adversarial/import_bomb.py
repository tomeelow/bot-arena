"""Allocates at import time, before setup: the jail and its limits must already apply.
Expected: memory."""

hoard = []
while True:
    hoard.append(bytearray(16 * 2**20))
