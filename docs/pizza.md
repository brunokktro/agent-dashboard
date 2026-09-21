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

## Runtime

- Source: `~/Repos/pizza-bot`, upstream `pizza-bot-app/pizza-bot`.
- Version tested: commit `2c5f0fd`, package version 1.0.0.
- Service: a launchd/systemd unit of your choice (e.g. `com.example.pizza-bot`).
- Wrapper: `~/.kiro/agents/scripts/pizza-bot-service.sh`.
- URL: `http://127.0.0.1:7782`.
- Data: `~/.kiro/agents-state/pizza-bot`.
- Provider: Amazon Bedrock through your AWS profile / region.
- Model selected by Pizza Bot: `global.anthropic.claude-sonnet-5`.

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
