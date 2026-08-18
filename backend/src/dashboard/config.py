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

    # Glob patterns of agent names to HIDE from every view (e.g. vendor-installed
    # agents you do not operate). Env format is JSON: '["vendor-*","kiroom-*"]'.
    exclude_agents: list[str] = []

    # Glob patterns of the ONLY agent names to show. Empty means "show all".
    # Useful when the agents dir is shared with other tools: an allowlist beats
    # chasing a growing exclude list. Exclusions still win over inclusions.
    include_agents: list[str] = []

    # Upstream repo for the on-demand update check ("owner/name"). Set it to
    # your fork to check against your own releases; empty disables the check.
    upstream_repo: str = "brunokktro/agent-dashboard"

    # Site-specific failure hints for the run diagnosis: [regex, hint] pairs
    # matched against the failing run's log segment. Keeps internal tool names
    # out of the code. Env format: '[["corp-sso","SSO expired - reauth"]]'.
    extra_hints: list[list[str]] = []

    # Paths this dashboard no longer serves, mapped to where they now live:
    # {"/old-page": "http://localhost:7781/old-page"}. A page that moved must
    # forward instead of becoming a not-found - a bookmark should never dead-end.
    # Site-specific destinations stay in config, out of the code.
    redirects: dict[str, str] = {}

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
    return build_settings()


# Settings keys an app-host config file may override (user-facing knobs only -
# paths and service wiring stay env/manifest-owned).
_HOST_CONFIG_KEYS = ("exclude_agents", "include_agents", "extra_hints",
                     "big_log_mb", "stuck_after_minutes", "job_agent_overrides",
                     "agent_deps", "upstream_repo", "redirects")


def build_settings() -> Settings:
    """Env-driven Settings, optionally overridden by an app-host config file.

    Under an app host like KiroCrew the backend is spawned with a minimal
    environment - DASHBOARD_* vars cannot reach it. The host persists per-app
    settings at ``$KIROCREW_HOME/apps/$KIROCREW_APP_NAME/data/config.json``
    (editable via its ``PUT /api/apps/{name}/config``), so recognized keys
    from that file win over the (empty) env. Absent or malformed files fall
    back to plain env behavior; unknown keys are ignored.
    """
    import json
    import os

    settings = Settings()
    home, app = os.environ.get("KIROCREW_HOME"), os.environ.get("KIROCREW_APP_NAME")
    if home and app:
        cfg = Path(home) / "apps" / app / "data" / "config.json"
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        overrides = {k: v for k, v in data.items() if k in _HOST_CONFIG_KEYS}
        if overrides:
            settings = Settings(**{**settings.model_dump(), **overrides})
    return settings
