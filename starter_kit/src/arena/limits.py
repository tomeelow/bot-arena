"""Bot limits, read from limits.toml next to this file."""

import tomllib
from dataclasses import dataclass, fields
from importlib.resources import files


@dataclass(frozen=True)
class Limits:
    init_ms: int
    turn_ms: int
    time_bank_ms: int
    turn_backstop_ms: int
    local_backstop_ms: int
    reply_max_bytes: int
    max_orders: int
    log_max_bytes_per_turn: int
    log_max_bytes_per_match: int

    @classmethod
    def load(cls) -> Limits:
        data = tomllib.loads(files("arena").joinpath("limits.toml").read_text())
        expected = {f.name for f in fields(cls)}
        if set(data) != expected:
            raise ValueError(f"limits.toml must set exactly {sorted(expected)}")
        return cls(**data)
