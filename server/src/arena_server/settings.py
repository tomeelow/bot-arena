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
    upload_max_bytes: int
    uploads_per_day: int
    comparisons_per_day: int
    compare_max_seed_pairs: int
    viewers_per_match: int
    viewers_total: int
    session_max_age_s: int
    live_poll_s: float
    live_wait_s: float
    matches_per_day: int
    egress_month_bytes: int
    disk_pause_fraction: float
    logs_keep_days: int
    live_keep_days: int
    stats_days: int
    stats_cache_s: float
    health_window_h: int
    alert_disk_fraction: float
    alert_queue_wait_s: float

    @classmethod
    def load(cls) -> Settings:
        data = tomllib.loads(files("arena_server").joinpath("settings.toml").read_text())
        return cls(**{k: v for section in data.values() for k, v in section.items()})
