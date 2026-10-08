# Pizza Bot Inbox integration

Dashboard route: `/pizza`. Health API: `GET /api/pizza/status`.

## Architecture

Pizza Bot runs as a separate loopback sidecar because it owns a stateful DeepAgents/LangGraph
runtime, SQLite stores, HTTP/SSE protocol, skills, MCP connections and human approval state. The
Agent Dashboard owns navigation and sidecar health, then embeds the complete upstream web app in the
Pizza tab. This avoids copying or forking 72,000 lines of Pizza Bot UI/runtime into the dashboard.

```text
Agent Dashboard :7780 /pizza
  -> GET /api/pizza/status
  -> iframe, full Pizza web app
Pizza Bot :7782
  -> Hono API + HTTP/SSE
  -> DeepAgents/LangGraph
  -> ~/.kiro/agents-state/pizza-bot
```

The iframe is an isolation boundary, not an unauthenticated remote embed. Both services bind only to
`127.0.0.1`. The Dashboard adapter rejects non-loopback `DASHBOARD_PIZZA_URL` values.

## Mail semantics

The inbox behaves like mail, not chat, because the agents behind it are long-running. Sending a
handoff files the conversation under an auto-created `Sent` folder and closes the pane; the reply
returns it to the inbox as unread, threaded like a mail conversation; replying re-files it under
`Sent` and the cycle repeats. A reply that needs the user's input lands in `Action Required`
instead, the `Waiting` filter counts what is still out, and the sidebar has a selection mode for
bulk delete. Messages addressed to the Pizza Bot itself remain a streaming chat.

## Pane width

The conversation list is resizable, because 320px truncates almost every agent subject. The handle
between the list and the reading pane responds to drag, double-click (collapse and restore) and
arrow keys; the preference lives in `localStorage` under `pizza-sidebar-layout` and is re-clamped
against the current window, so it survives moving between a monitor and the laptop. It is a Pizza
Bot preference, not a Dashboard one: the `/pizza` tab only embeds the sidecar.

## Bridge for a fresh checkout

Upstream Pizza Bot has none of the endpoints agents publish through. The patch that adds them —
and everything above — ships in [`integrations/pizza-bot/`](../integrations/pizza-bot/), pinned to
the upstream base it applies to. A checkout without it renders an inbox nothing can reach.

## Runtime

- Source: a sibling Pizza Bot checkout, pinned by `integrations/pizza-bot/UPSTREAM`.
- Version tested: commit `2c5f0fd`, package version 1.0.0.
- Service: any user-level service manager that keeps the sidecar bound to loopback.
- URL: `http://127.0.0.1:7782`.
- Data: a local state directory outside the source checkout.
- Provider and model: configured in Pizza Bot, not hardcoded by the Dashboard integration.

## Security

- Loopback only. Never bind to `0.0.0.0`.
- No default filesystem grant. Add individual roots read-only unless a workflow requires writes.
- Do not place bearer tokens in URLs.
- MCP servers and plugins execute as the local user and require review before installation.
- Routine thread content and customer data stay out of Dashboard logs.

## Notification direction

After the inbox is proven stable, agents publish routine completion, report and needs-input events to
Pizza Bot. macOS Reminders remain only for critical findings and one deduplicated escalation when
Action/Unread has not been checked for the agreed threshold. Migration must use a single notification
adapter, not edits duplicated across every agent.

## Theme integration

The Dashboard observes its root `dark` class and sends `light` or `dark` to the embedded Pizza app.
Pizza validates the parent origin, applies the same theme and reasserts it if its stored preference
tries to override the Dashboard. Both modes were verified from the rendered iframe DOM and screenshots.

## Direct agent bridge pilot

The Pizza Composer has a `To` field with `Pizza Bot` plus exact Kiro agent names. A Kiro target uses
the durable A2A queue and returns the semantic result to the same Pizza thread. The return watcher
runs every 15 seconds and deduplicates by handoff ID. `NEEDS_INPUT` responses become unread and move
to the `Action Required` folder. Native Pizza `Action` remains reserved for genuine LangGraph HITL.

The integration was validated with simple results, long-running analysis, review flows, pending
responses and response redelivery. Attachments remain disabled for Kiro recipients until the
pointer and classification contract is defined.
