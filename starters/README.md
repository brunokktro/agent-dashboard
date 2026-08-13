# Starter agents and jobs

A fresh dashboard observes an empty ecosystem, so it looks dead: no agents, no
runs, flat charts. These starters give it a heartbeat and a routine on day one -
and each one does real work while exercising a feature you would otherwise have
to take on faith.

Install them with [`bin/install-starters`](../bin/install-starters) (opt-in,
non-destructive, `--force` backs your copies up first).

| Starter | Kind | Cadence | What it does |
|---------|------|---------|--------------|
| `heartbeat` | shell job | every 15 min | Verifies the server serves the app (200 **and** HTML) and that the API reads your ecosystem. Also gives the Overview, heatmap and health score genuine data immediately. |
| `log-hygiene` | shell job | weekly | Compresses logs past `DASHBOARD_BIG_LOG_MB` and keeps the tail live. Never deletes - it archives, verifies the archive, and only then truncates. |
| `failure-triage` | agent | on demand / daily | Diagnoses the last 24h of failed runs through the dashboard's own `/api/runs/{id}/diagnose`, groups repeats into one incident, and reports what needs a human. Read-only. |
| `dashboard-support` | agent | on demand | Guided install and troubleshooting, locally or over a chat DM. Lives in [`../agents`](../agents). |

The two shell jobs need **no LLM and no kiro-cli** - they are plain scripts your
scheduler (or the Supervisor's Run button) executes through
`scripts/run-scheduled.sh`. The agents need kiro-cli.

## Writing your own from these

Copy a starter and edit it - that is the intended path, and the reason each one
is small enough to read in a minute.

Two rules worth keeping:

1. **Anything tied to a system only you can reach stays in YOUR ecosystem.**
   An agent that talks to your company's internal account tooling, a private
   API, an intranet dashboard - keep it in `$DASHBOARD_AGENTS_DIR`, not in a
   public repo. It would not work for anyone else, and it leaks how your
   internals are shaped. The starters here are deliberately generic for the
   same reason: the dashboard ships the *shape*, you keep the specifics.

2. **A job that reports must distinguish "I checked and found nothing" from "I
   could not check."** Both starters do: `heartbeat` fails loudly when the
   server answers 200 with something that is not the app, and `log-hygiene`
   keeps the original when an archive fails verification. A run that reports
   success it did not verify is worse than a run that fails.
