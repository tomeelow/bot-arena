"""Server parameters, read from settings.toml next to this file."""

import tomllib
from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True)
class Settings:
    lease_s: float
    reap_every_s: float
    idle_sleep_s: float
    smoke_turns: int
    error_max_bytes: int
    mu: float
    sigma: float
    beta: float
    tau: float
    conservative_k: float
    provisional_sigma: float
    explore_floor: float
    pair_cap: int
    pair_window: int
    placement_seed_pairs: int
    placement_priority: int
    queue_target: int

    @classmethod
    def load(cls) -> Settings:
        data = tomllib.loads(files("arena_server").joinpath("settings.toml").read_text())
        return cls(**{k: v for section in data.values() for k, v in section.items()})
