"""Configuration for the dashboard.

Every environment-specific value lives here, overridable via env vars
(prefix ``DASHBOARD_``) or a ``.env`` file. No hardcoded usernames,
absolute paths, or service names anywhere else in the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_", env_file=".env", extra="ignore")

    # Root of the agent ecosystem this dashboard observes.
    agents_dir: Path = Path.home() / ".kiro" / "agents"

    host: str = "127.0.0.1"
    port: int = 7780

    # Service name of the scheduler process (used for status lookup via launchctl/systemctl).
    supervisor_service: str = ""

    # Job-id -> agent-name overrides for jobs whose id does not follow "<agent>-<suffix>".
    job_agent_overrides: dict[str, str] = {}

    # Agent name -> human description of its dependencies (shown on detail page).
    agent_deps: dict[str, str] = {}

    # Alert thresholds
    big_log_mb: int = 50
    stuck_after_minutes: int = 30

    # ── Derived paths ────────────────────────────────────────────────
    @property
    def db_path(self) -> Path:
        return self.agents_dir / "runs.db"

    @property
    def log_dir(self) -> Path:
        return self.agents_dir / "logs"

    @property
    def schedule_path(self) -> Path:
        return self.agents_dir / "scripts" / "schedule.json"

    @property
    def lock_dir(self) -> Path:
        return self.agents_dir / "locks"

    @property
    def queue_dir(self) -> Path:
        return self.agents_dir / "queue"

    @property
    def scripts_dir(self) -> Path:
        return self.agents_dir / "scripts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
