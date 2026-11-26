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

    @classmethod
    def load(cls) -> Settings:
        data = tomllib.loads(files("arena_server").joinpath("settings.toml").read_text())
        return cls(**data["queue"], **data["validation"])
