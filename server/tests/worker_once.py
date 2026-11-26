"""Runs one worker step in its own process, so a test can kill it mid-match."""

import sys
from pathlib import Path

import plays
from arena_server.db import connect
from arena_server.store import Store
from arena_server.worker import Worker

Worker(connect(Path(sys.argv[1])), Store(Path(sys.argv[2])), plays.local).step()
