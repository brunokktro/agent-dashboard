"""The support agent's playbook must not drift from the product.

The failure this prevents actually happened: bin/collect-diagnostics,
bin/init-ecosystem and bin/install-starters were added, the Run button learned to
disable itself, /health moved to /healthz and agents grew a cli_name - and the
agent kept teaching the old manual path, because nothing failed when the docs
went stale.

These are cheap string assertions on purpose: they catch the drift that silently
turns a support agent into a source of wrong instructions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "agents/dashboard-support.md"
CONFIG = REPO / "agents/dashboard-support.json"
REFS = REPO / "agents/dashboard-support-data/references"

# every operator-facing tool must be known to the agent, or it will hand out a
# manual sequence for something that has a command
SHIPPED_TOOLS = ["collect-diagnostics", "init-ecosystem", "install-starters",
                 "record-run", "sweep", "await-reply"]

# behaviours a supporter cannot afford to be wrong about
CURRENT_SEMANTICS = [
    "cli_name",    # kiro-cli resolves --agent by the config's internal name
    "/healthz",    # the liveness probe; /health is the SPA page
    "release",     # App Store installs come from the release branch
    "INCLUDE_AGENTS",  # scoping a shared agents dir
]


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC.read_text()


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG.read_text())


def test_the_tools_exist_where_the_playbook_says(spec_text):
    for tool in SHIPPED_TOOLS:
        assert (REPO / "bin" / tool).is_file(), f"bin/{tool} is referenced but missing"


def test_spec_knows_every_shipped_tool(spec_text):
    missing = [t for t in SHIPPED_TOOLS if t not in spec_text]
    assert not missing, f"the spec never mentions: {missing}"


def test_config_prompt_knows_every_shipped_tool(config):
    """The .json prompt is what kiro-cli actually loads - a fresh .md does not
    help if the prompt still describes the old world."""
    prompt = config["prompt"]
    missing = [t for t in SHIPPED_TOOLS if t not in prompt]
    assert not missing, f"the loaded prompt never mentions: {missing}"


def test_current_semantics_are_in_both(spec_text, config):
    for term in CURRENT_SEMANTICS:
        assert term in spec_text, f"spec is stale: no mention of {term}"
        assert term in config["prompt"], f"prompt is stale: no mention of {term}"


def test_references_are_reachable(spec_text, config):
    for f in REFS.glob("*.md"):
        assert f.name in spec_text, f"{f.name} exists but the spec never links it"
    for res in config["resources"]:
        path = REPO / res.removeprefix("file://")
        assert path.is_file(), f"resource does not exist: {res}"


def test_agent_still_acts_rather_than_only_advising(spec_text):
    """The whole point of a local support agent: it runs the fix. If this
    section disappears, the agent regresses into a chatbot that dictates."""
    assert "Do the work, do not narrate it" in spec_text
    assert "ask first" in spec_text  # the blast-radius line is still drawn


def test_nothing_identifying_leaked_into_the_agent_files():
    """The repo is public: ids, handles and personal paths are runtime inputs."""
    import re

    bad = re.compile(r"/Users/[a-z]|/home/[a-z]|@[a-z0-9.-]+\.(com|dev)\b|\b[UW][A-Z0-9]{8,}\b")
    for f in [SPEC, CONFIG, *REFS.glob("*.md")]:
        hits = [ln for ln in f.read_text().splitlines() if bad.search(ln)]
        # the placeholder convention is allowed to be named
        hits = [h for h in hits if "SLACK_USER_ID" not in h and "CONVERSATION_ID" not in h]
        assert not hits, f"{f.name} carries an identifying value: {hits[:2]}"
