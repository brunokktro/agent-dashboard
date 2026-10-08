# Pizza Bot Kiro bridge

The `/pizza` tab embeds a Pizza Bot sidecar (see [`docs/pizza.md`](../../docs/pizza.md)). Upstream
Pizza Bot has no idea this dashboard exists: it exposes no endpoint for agents to publish inbox
messages, and no way to address a message to a specific agent. This directory carries the patch that
adds those, so a fresh checkout produces a tab that actually works instead of an empty chat.

## Why a patch and not a fork or a subtree

Upstream is [`pizza-bot-app/pizza-bot`](https://github.com/pizza-bot-app/pizza-bot), Apache-2.0, and
it is not ours. Vendoring it here would copy ~72,000 lines of UI and runtime into this repo, which is
the thing [`docs/pizza.md`](../../docs/pizza.md) deliberately avoids, and it would create a sync debt
with a project that keeps moving. The bridge itself is 27 files. Shipping only the bridge keeps the
boundary honest: upstream stays upstream, ours stays ours, and the base it applies to is written down.

## Contents

| file | what |
|---|---|
| `kiro-bridge.patch` | the bridge, as a single diff against the pinned base |
| `UPSTREAM` | repo URL, pinned base commit, license |
| `apply.sh` | applies the patch, refusing the wrong project and detecting an already-patched tree |

## Use

```bash
git clone https://github.com/pizza-bot-app/pizza-bot.git ../pizza-bot
cd ../pizza-bot && git checkout "$(grep '^base=' ../agent-dashboard/integrations/pizza-bot/UPSTREAM | cut -d= -f2)"
cd - && integrations/pizza-bot/apply.sh ../pizza-bot
```

Then build and run the headless backend on 7782, which is what the dashboard embeds:

```bash
cd ../pizza-bot
npm install
npm run build && npm run backend:bundle
PORT=7782 node dist/backend/start.mjs
```

`npm run dev` starts the Electron desktop shell instead, which this integration never uses and whose
first launch downloads a ~295MB binary.

## What the bridge adds

**`POST /notifications`** lets an agent publish a durable inbox message without spending a model call.
Idempotent by key, routes routine messages to `Agent Updates` and actionable ones to `Action
Required`, pins critical ones. It deliberately does not set Pizza Bot's native `awaitingAction`, which
belongs to a real LangGraph HITL interrupt.

**`POST /kiro/handoffs`, `GET /kiro/handoffs/pending`, `POST /kiro/responses`, `GET /kiro/agents`** are
the request/return path for addressing a message to one agent and getting an answer back into the same
thread. Delivery is durable: the request is queued by an external handoff script and the mapping under
`bridge/pending/` is the record of what is outstanding.

**Mail semantics.** A handoff conversation behaves like mail, not chat: sending files it under an
auto-created `Sent` folder and closes the pane; the reply pulls it back to the inbox as unread with
the whole exchange concatenated; replying re-files it under Sent. The recipient preselects the
conversation's counterpart, the sidebar has a selection mode with bulk delete, and needs-input
replies still land in `Action Required`.

**Sent-and-waiting visibility** in the web UI: a per-thread badge naming the target and where the
letter sits in the delivery queue (`Queued · N ahead`, then `is working · 3m`; `PIZZA_KIRO_QUEUE_DIR`
overrides the queue path), a `Waiting` filter, and hydration for state the bridge appends outside the protocol
stream. A thread only counts as waiting while its last message is the user's, because the return
watcher posts the reply before it moves the mapping, so the mapping alone would keep claiming a
delivered handoff is still in flight.

**A resizable conversation list.** Upstream pins the pane at 320px, which truncates almost every
agent subject (`[ACTION] [REVIEW] Long-running deployment...`). A handle between the list and the reading pane
sizes it by drag, double-click or arrow keys; the width persists under `pizza-sidebar-layout` and is
clamped against the current window rather than stored pre-clamped, so one preference works on a
monitor and on a laptop. Mobile does not render the handle: there the list is the whole view.

## Updating the patch

Regenerate from the branch that carries the bridge:

```bash
cd ../pizza-bot
git diff --binary "$(git merge-base origin/main HEAD)"..HEAD > \
  ../agent-dashboard/integrations/pizza-bot/kiro-bridge.patch
```

Then update `base` in `UPSTREAM` if the merge-base moved, and re-run `apply.sh` against a pristine
checkout to confirm it still applies. The fixtures use neutral agent names on purpose; keep real
agent inventory out of anything published here.
