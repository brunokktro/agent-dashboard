# Remote troubleshooting reference

Protocol detail for action 2 of `dashboard-support`: driving the install
diagnosis over a chat DM, asynchronously, with a bounded reply window.

The transport is Slack; the client is not named. Any Slack MCP server configured
in the environment can back it, as long as it provides the four capabilities
below. No tool name, user id, workspace id or handle belongs in this file.

## Inputs, all at runtime

| Input | Source | Never |
|-------|--------|-------|
| `<SLACK_USER_ID>` | argument from the operator, or an environment variable | hardcoded in a file |
| `<CONVERSATION_ID>` | returned when the DM is opened/resolved | hardcoded in a file |
| language | profile locale first, then mirrored from the reply | assumed permanently |

If the operator did not pass a user id, ask for it. Do not pick one.

## Required capabilities

1. **Open or resolve a direct conversation** from a user id.
2. **Post a message** to that conversation.
3. **Read history since a known point** (timestamp, cursor or "since last read")
   so polling sees only new material.
4. **Download a file** shared in the conversation.

Missing capability 3 is fatal for the wait window - say which one is missing and
stop. Never simulate a reply, and never report a conversation that was not
actually opened.

## Message format

```text
:kiro: _message text_
```

- Prefix `:kiro:`, then the message in italics (mrkdwn italics is `_underscore_`).
- Blank line between blocks. Whitespace is legibility.
- Short. Verdict plus the one thing you need, not a report.
- Code, logs and paths in backticks or a fenced block - do not italicise those.
- No emoji beyond `:kiro:`. This is a 1:1 technical conversation.
- Never propose a call, in any language.

## Language handling

| Turn | Rule |
|------|------|
| First message | guess from profile timezone/locale: America/Sao_Paulo -> pt-BR, most of Spanish-speaking LatAm -> es, otherwise en-US |
| After their first reply | mirror the language they wrote in, even if the guess was wrong. Do not comment on the switch |

Minimum support pt-BR, en-US, es. Technical terms stay in English in every
language: `build`, `port`, `log`, `dist`, `frontend`, `backend`, `record-run`.

For Spanish, do not use the opening `¿` / `¡`.

## The 5-minute window

### First message must announce it

The window is stated in the first message, so silence is unambiguous. Shape,
per language - one block for the ask, one for what to send, one for the window:

pt-BR:

```text
:kiro: _Oi! Sou o agent de suporte do Agent Dashboard. Vim ajudar a colocar o teu dashboard de pe._

:kiro: _Me conta o que esta acontecendo: a mensagem de erro, o log, ou um print da tela. Se preferir, anexa o arquivo de log aqui mesmo._

:kiro: _Vou aguardar tua resposta por 5 minutos. Se nao der agora, sem problema - me chama de novo quando tiver os dados em maos._
```

en-US:

```text
:kiro: _Hi! I am the Agent Dashboard support agent, here to get your dashboard running._

:kiro: _Tell me what is happening: the error message, the log, or a screenshot. You can attach the log file right here._

:kiro: _I will wait 5 minutes for your reply. If now is not a good time, no problem - ping me again when you have the data at hand._
```

es:

```text
:kiro: _Hola! Soy el agent de soporte del Agent Dashboard, vengo a ayudarte a dejar tu dashboard funcionando._

:kiro: _Contame que esta pasando: el mensaje de error, el log, o una captura. Podes adjuntar el archivo de log aca mismo._

:kiro: _Voy a esperar tu respuesta por 5 minutos. Si ahora no es buen momento, no hay problema - escribime de nuevo cuando tengas los datos._
```

### Driving the window

`bin/await-reply` owns the timing so the agent does not busy-wait or hang. It
polls a fetch command supplied by the environment - a small wrapper that prints
new messages from the conversation on stdout and exits non-zero when the read
itself failed.

```bash
bin/await-reply --timeout 300 --interval 15 -- <read-new-messages-command> "<CONVERSATION_ID>"
```

| Exit | Meaning | Action |
|------|---------|--------|
| 0 | payload on stdout | continue triage. A file reference means download, then analyse |
| 3 | 5 minutes of silence | send the closing message, end the session, exit cleanly |
| 4 | every poll failed | report the read failure. Never say "no reply" - that is a different fact |

Exit 4 exists because a failed check reported as "no messages" is a silent
failure: it looks like the person ignored you when in fact nothing was read.

### Closing message on silence

Polite, no blame, no pressure, and it ends the session.

```text
:kiro: _Vou fechar a janela por aqui para nao ficar te esperando._

:kiro: _Quando tiver o log ou a mensagem de erro em maos, me chama de novo que a gente resolve na hora._
```

Then stop. Do not keep polling, do not schedule a follow-up.

## Triage over chat

Same logic as the local action, asked instead of executed. One question at a
time; a list of eight commands in a DM gets ignored.

1. **Platform and versions.** Ask for the output of a single line:
   `uname -srm; python3 --version; node --version; uv --version; sqlite3 --version`
2. **Symptom class.** Blank page / connection refused / empty UI / stale UI.
3. **Route by symptom** - the mapping in
   [`install-diagnostics.md`](install-diagnostics.md) phase 3 is the reference.
   Blank page with a working API is `dist/` not built, far and away the most
   common. Empty UI on a fresh clone is expected behaviour, not a bug.
4. **Ask for the artifact, not the interpretation.** The tail of the server
   output, or the log file attached. `tail -n 50` is enough and safe to paste.
5. **One fix at a time**, with the exact command to run, then ask for the result.
6. **Close on the real validation**: root returns 200 with HTML, and a
   `record-run` test shows up in the UI. Their screenshot of a working Overview
   is the acceptance evidence - not their "it worked".

Each further wait uses the same `bin/await-reply` window. Announce it whenever
the wait is longer than the natural rhythm of the conversation, and never let a
session hang without a bound.

## What never happens

- No message is sent without an explicit instruction to run this action.
- No call, meeting or screen share is proposed. Resolution is asynchronous.
- No user id, handle, email or real name is written to a file in the repository -
  including examples and commit messages.
- No claim that a message was delivered without the post confirming it.
- No "fixed" without the person's own evidence that it is fixed.
