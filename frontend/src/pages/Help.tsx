import { useEffect, useState } from "react"
import {
  Activity, Bot, GitBranch, HeartPulse, Keyboard, ListTodo, Rocket,
  ScrollText, Settings2, SquareTerminal, Stethoscope, Zap,
} from "lucide-react"

interface Sub { id: string; title: string; body: React.ReactNode; img?: string }
interface Section { id: string; title: string; icon: React.ElementType; subs: Sub[] }

const P = ({ children }: { children: React.ReactNode }) => (
  <p className="text-sm leading-relaxed text-muted-foreground">{children}</p>
)
const K = ({ children }: { children: React.ReactNode }) => (
  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{children}</code>
)
const UL = ({ items }: { items: React.ReactNode[] }) => (
  <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
    {items.map((it, i) => <li key={i}>{it}</li>)}
  </ul>
)

const SECTIONS: Section[] = [
  {
    id: "getting-started", title: "Getting started", icon: Rocket,
    subs: [
      {
        id: "what-is", title: "What is this?",
        body: (
          <>
            <P>A local-first observability dashboard for AI agent ecosystems. It watches the
            artifacts your agent scheduler already produces (a SQLite runs database, queue
            folders, a schedule file) and turns them into live views: what ran, what failed,
            what is queued, and when everything happens.</P>
            <P>It is a <b>consumer</b>: it never modifies your agents. The only writes are
            queue actions (retry/cancel/enqueue) and alert acknowledgements.</P>
          </>
        ),
      },
      {
        id: "onboarding", title: "I already have agents (Kiro CLI / Claude Code)",
        body: (
          <>
            <UL items={[
              <>Run it locally - that is the intended model. Your agent data are local files;
              the dashboard reads them from disk. No cloud, no account, no telemetry.</>,
              <><b>Kiro CLI users:</b> point <K>DASHBOARD_AGENTS_DIR=~/.kiro/agents</K>. Agents
              (markdown specs with YAML frontmatter + JSON configs) appear immediately, and the
              Console can chat with any agent that has a JSON config.</>,
              <><b>Run history:</b> the dashboard reads a <K>runs</K> table from
              <K>runs.db</K>. If the file does not exist, it is created empty on first use -
              the app works from day zero. To populate it, record your runs (see data
              contracts below) from whatever scheduler you use (cron, launchd, Claude Code
              hooks).</>,
              <><b>Universal adapter - <K>bin/record-run</K>:</b> wrap ANY command and it gets
              recorded (job id, duration, status, exit code, log). Works with cron, launchd,
              Claude Code hooks, Makefiles: <K>record-run nightly-backup ./backup.sh</K>. Runs
              recorded this way show up everywhere: Overview, Health, heatmap, diagnosis.</>,
            ]} />
          </>
        ),
      },
      {
        id: "contracts", title: "Data contracts",
        body: (
          <UL items={[
            <><K>runs.db</K> - SQLite, table <K>runs</K>: <K>job_id, started_at, duration_sec,
            status, exit_code, log_path</K></>,
            <><K>queue/pending|running|done|failed/*.json</K> - work items with
            <K>id, agent, input, priority, created, status</K></>,
            <><K>scripts/schedule.json</K> - <K>{"{jobs: [{id, script, cron, timeout_sec, enabled}]}"}</K></>,
            <><K>locks/*.lock</K> - PID files marking running agents</>,
            <><K>*.md</K> - agent specs with YAML frontmatter (<K>name</K>, <K>description</K>)</>,
            <><K>*.json</K> - bare kiro-cli agent configs (with <K>name</K> + <K>tools</K>) are
            first-class agents too; an .md + .json pair counts once</>,
          ]} />
        ),
      },
      {
        id: "starters", title: "Starters - so day one is not empty",
        body: (
          <UL items={[
            <><K>bin/install-starters --all</K> installs a small routine that does real work:
            <K>heartbeat</K> (every 15 min - checks the server serves the app and the API reads
            your ecosystem, and gives these charts data immediately), <K>log-hygiene</K> (weekly -
            compresses logs past the threshold, never deletes), plus the <K>failure-triage</K> and
            <K>dashboard-support</K> agents.</>,
            "The two scheduled ones are plain shell scripts - no LLM, no kiro-cli. The agents need kiro-cli.",
            "Schedule entries are merged: a job id you already have is never rewritten, and existing files are kept (--force backs yours up first).",
            "They double as templates. Anything tied to a system only you can reach belongs in your own ecosystem, not in a public repo.",
          ]} />
        ),
      },
      {
        id: "keep-running", title: "Keep it running (and enable the Run buttons)",
        body: (
          <UL items={[
            <>One command sets up both: <K>bin/init-ecosystem --all</K> writes the two runner
            scripts the Run buttons need and installs a service unit (launchd on macOS,
            systemd --user on Linux) so the dashboard comes back after a reboot.</>,
            <>It is non-destructive: an existing file is reported as <K>KEPT</K> and never
            overwritten, so running it twice is safe. Without arguments it only reports what
            is missing.</>,
            "Run buttons stay disabled until the runners exist - the dashboard observes your ecosystem, it does not invent how your agents are executed.",
            <>WSL2 note: the distro shuts down when its last process exits - keep a session
            open (<K>tmux</K>) or set <K>systemd=true</K> in <K>/etc/wsl.conf</K>.</>,
          ]} />
        ),
      },
      {
        id: "settings", title: "Settings",
        body: (
          <UL items={[
            <>Everything is environment-driven: <K>DASHBOARD_AGENTS_DIR</K> (which ecosystem to
            observe), <K>DASHBOARD_PORT</K>, <K>DASHBOARD_EXCLUDE_AGENTS</K> (glob patterns to hide
            agents you do not operate), <K>DASHBOARD_EXTRA_HINTS</K> (site-specific failure hints
            for the diagnosis).</>,
            <><b>Seeing agents that are not yours?</b> A shared agents dir also holds agents
            installed by other tools. Either point <K>DASHBOARD_AGENTS_DIR</K> at a dedicated
            directory (full isolation), or filter the shared one with
            <K>DASHBOARD_INCLUDE_AGENTS</K> (allowlist - usually easier) and
            <K>DASHBOARD_EXCLUDE_AGENTS</K> (denylist). Exclusions win over inclusions.</>,
            <>The version button in the header checks the upstream repo for a newer release -
            only when you click it, so nothing phones home in the background. A failed check
            reports as failed, never as "up to date". Aim it at your fork with
            <K>DASHBOARD_UPSTREAM_REPO</K>, or set it empty to turn it off.</>,
            <>Running as a KiroCrew app, use the per-app settings file instead - the host writes
            <K>data/config.json</K> and the same keys (<K>exclude_agents</K>, <K>extra_hints</K>,
            thresholds) override the environment.</>,
            "The README's Configuration table is the complete reference.",
          ]} />
        ),
      },
      {
        id: "kirocrew", title: "Run it inside KiroCrew",
        body: (
          <UL items={[
            "This dashboard is also a KiroCrew app: install it from the App Store registry (or from a local clone) and it appears in the sidebar, terminals included.",
            <>One-click by design: the built UI ships in the repo, so the install needs no Node on
            your machine; the backend spawns on an automatic port with a <K>/health</K> check.</>,
            "The sidebar page embeds the dashboard same-origin, which keeps the WebSocket terminals and live log streams working.",
          ]} />
        ),
      },
    ],
  },
  {
    id: "overview", title: "Overview", icon: Activity,
    subs: [
      {
        id: "overview-tour", title: "Home base tour", img: "/help/overview.png",
        body: (
          <UL items={[
            "Top cards: all-time runs, last-24h successes/failures, and what is running right now.",
            "The 7-day chart shows daily volume - green stacked with red failures.",
            "Agent cards are sorted smartly: running first, then most recently active. The home shows the top 6; the Agents tab has everyone.",
          ]} />
        ),
      },
      {
        id: "alerts", title: "Failure alerts & diagnosis",
        body: (
          <UL items={[
            "Every failed run in the last 24h is listed with when it happened, how long it ran, and the exit code.",
            <><b>diagnose</b> opens an instant explanation: what the exit code means (124 =
            timeout, 127 = command not found, 137 = out of memory…) plus the relevant error
            lines extracted from the log.</>,
            <><b>view log →</b> jumps to the Logs page with the right file already open.</>,
            "Ack hides an alert batch until a NEW failure happens.",
          ]} />
        ),
      },
    ],
  },
  {
    id: "agents", title: "Agents", icon: Bot,
    subs: [
      {
        id: "agents-tab", title: "Agents tab", img: "/help/agents.png",
        body: (
          <UL items={[
            "Searchable grid of every agent, with facet chips: Running, Scheduled (has a cron job), Chat-ready (has a kiro-cli JSON config).",
            "The whole card is clickable - it opens the agent's page. The inner buttons act on the agent without navigating.",
            "Play button triggers a background run; the card glows blue while running. It renders DISABLED when your ecosystem has no scripts/run-agent.sh - the tooltip names the file, and `bin/init-ecosystem --runners` scaffolds it (non-destructive: it never overwrites an existing file).",
            "Terminal icon (chat-ready agents) jumps straight to that agent's page with the terminal already open.",
          ]} />
        ),
      },
      {
        id: "agent-detail", title: "Agent detail page",
        body: (
          <UL items={[
            "KPIs: health score (7-day success rate), total runs, failures, average duration, last run.",
            <>Duration percentiles (30d): <b>P50</b> is the typical run; <b>P95/P99</b> are the
            slow outliers. P99 growing while P50 stays flat = something is intermittently slow.</>,
            <><b>CLI</b> copies <K>kiro-cli chat --agent NAME --trust-all-tools</K>.
            <b> Terminal</b> opens an embedded session already connected to the agent.</>,
          ]} />
        ),
      },
    ],
  },
  {
    id: "board", title: "Board", icon: ListTodo,
    subs: [
      {
        id: "board-tabs", title: "Two views in one",
        body: (
          <UL items={[
            "'Work items': the runtime kanban below.",
            "'Backlog & Review notes': planning items from backlog/*.md (with autonomy badges: autonomous / review / blocked) and the review-notes flow, plus completed items.",
          ]} />
        ),
      },
      {
        id: "board", title: "The work-items kanban", img: "/help/queue.png",
        body: (
          <UL items={[
            "Four columns - Running, Pending, Failed, Done (24h) - each scrolling independently.",
            "Click any card for the full detail panel (complete input, result/error, timestamps, actions).",
            "Failed cards preview the error inline; hover shows quick Retry/Cancel.",
            "Enqueue: pick the agent from a dropdown, describe the task, set priority - done.",
          ]} />
        ),
      },
      {
        id: "backlog-reader", title: "Backlog reader & decisions",
        body: (
          <UL items={[
            "Click any backlog or review-note card to open the reader: side table of contents with scroll-spy, J/K (or arrows) to move between items, and the file path one click away.",
            "Review notes carry a decision bar: Approve flips the item's autonomy to auto (applied on the agent's next run), Discuss saves your feedback into the note for regeneration, Reject stops it.",
            "Backlog items expose the autonomy switch (auto / review / blocked) and a soft Delete - items move to backlog/deleted/, nothing is destroyed.",
            "Drag and drop cards in the 'Active backlog' column to reorder them - the order persists in each file's frontmatter and survives a refresh.",
            "Running and Failed columns appear when an item carries state: running or state: failed in its frontmatter - written by whoever executes it, through POST /api/backlog/state. The item never moves on disk, so its note, order and history stay attached.",
            "The full loop: backlog-reviewer writes the note, you decide here (Approve flips the item to auto), an executor picks it up and marks it running, then done or failed. The agent proposes, the human approves - always in that order.",
            "'Propose item' puts YOUR work on the board without leaving the UI. It always enters as review - the API refuses to let the creator pick auto, so the review step stays real even for your own items.",
          ]} />
        ),
      },
    ],
  },
  {
    id: "health", title: "Health & Observability", icon: HeartPulse,
    subs: [
      {
        id: "heatmap", title: "Activity heatmap", img: "/help/health.png",
        body: (
          <UL items={[
            "Columns = hour of day, rows = day of week, last 30 days. Green intensity = run volume; red tint = failures concentrated there.",
            "Hover any cell: the info bar above the grid shows exact counts and success rate for that hour.",
            "Use it to spot patterns: a red block at Sunday 8am means something scheduled there keeps breaking.",
          ]} />
        ),
      },
      {
        id: "scores", title: "Health scores",
        body: (
          <UL items={[
            "Score = success rate over the last 7 days. Green ≥90%, amber ≥70%, red below.",
            "Cards are sorted worst-first so problems surface. Click a card to open the agent.",
          ]} />
        ),
      },
    ],
  },
  {
    id: "supervisor", title: "Supervisor", icon: Settings2,
    subs: [
      {
        id: "command-center", title: "Command center", img: "/help/supervisor.png",
        body: (
          <UL items={[
            "The 4 big numbers are FILTERS - click 'Failing' to isolate broken jobs; click again to clear.",
            "'Up next' chips show the next scheduled runs with a live countdown.",
            "Schedules are written in plain English ('At 08:00, Monday through Friday'); the raw cron lives in the side panel.",
            "Click any job card for details + Run now. Jobs whose last run failed are pinned first.",
          ]} />
        ),
      },
    ],
  },
  {
    id: "console", title: "Console & Pipe mode", icon: SquareTerminal,
    subs: [
      {
        id: "multi-terminal", title: "Multi-terminal", img: "/help/console.png",
        body: (
          <UL items={[
            "Up to 6 terminals side by side. 'Plain shell' or pick an agent - agent sessions open kiro-cli chat automatically with tool confirmations off.",
            <><b>Sessions survive refresh:</b> the server keeps each terminal alive for 15
            minutes and replays the recent output when you reconnect. The X button kills a
            session for real.</>,
            "Broadcast bar (2+ terminals): type once, Enter, and the text goes to ALL sessions - ask several agents the same thing simultaneously.",
          ]} />
        ),
      },
      {
        id: "pipe", title: "Pipe mode (agent → agent)", img: "/help/pipe.png",
        body: (
          <>
            <P>Chain up to 4 agents: your prompt goes to agent 1; its full answer becomes the
            prompt of agent 2, and so on. The flow view animates the hand-off (glowing node =
            running, with elapsed timer), output STREAMS live (~1s latency) so you watch the
            agent working, and each step shows exactly what it received from the previous one.
            Jobs survive page refreshes and even backend restarts (persisted server-side).
            Great for review chains ("devex-agent builds it → guardian-reviewer audits it").</P>
            <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <GitBranch className="size-3.5" /> Console → Pipe mode button
            </div>
          </>
        ),
      },
    ],
  },
  {
    id: "logs", title: "Logs", icon: ScrollText,
    subs: [
      {
        id: "live-tail", title: "Live tail", img: "/help/logs.png",
        body: (
          <UL items={[
            "Pick a file on the left; it streams live on the right (new lines within 1 second).",
            "Errors are red, warnings amber, successes green. 'Pause follow' stops auto-scroll.",
            <>The URL carries <K>?file=name.log</K> - links from failure alerts land here with
            the right file open, and you can bookmark/share a specific log.</>,
          ]} />
        ),
      },
    ],
  },
  {
    id: "extras", title: "Real-time & shortcuts", icon: Zap,
    subs: [
      {
        id: "realtime", title: "Real-time updates",
        body: (
          <P>A WebSocket event channel watches runs, work items and locks server-side. When a run
          finishes or an agent starts, every open page updates in about 1 second - no refresh.
          If the connection drops it reconnects with backoff; 10s polling remains as a safety
          net.</P>
        ),
      },
      {
        id: "shortcuts", title: "Shortcuts",
        body: (
          <UL items={[
            <><K>Cmd+K</K> / <K>Ctrl+K</K>: command palette - jump to any page or agent.</>,
            "Moon/Sun icon: dark mode (remembered between visits).",
          ]} />
        ),
      },
      {
        id: "diagnose-ref", title: "Exit code cheat-sheet",
        body: (
          <UL items={[
            <><K>1</K> generic error · <K>2</K> bad arguments</>,
            <><K>124</K> TIMEOUT (killed by timeout_sec)</>,
            <><K>126</K> not executable · <K>127</K> command not found (PATH)</>,
            <><K>137</K> SIGKILL (often out-of-memory) · <K>143</K> SIGTERM</>,
          ]} />
        ),
      },
    ],
  },
]

// icon needed by section header render
void Stethoscope, void Keyboard

export default function HelpPage() {
  const [active, setActive] = useState(SECTIONS[0].id)

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries)
          if (e.isIntersecting) setActive(e.target.id.replace("sec-", ""))
      },
      { rootMargin: "-10% 0px -85% 0px", threshold: 0 },
    )
    for (const s of SECTIONS) {
      const el = document.getElementById(`sec-${s.id}`)
      if (el) obs.observe(el)
    }
    return () => obs.disconnect()
  }, [])

  return (
    <div className="grid grid-cols-[220px_1fr] gap-8">
      {/* Sidebar */}
      <nav className="sticky top-20 h-fit space-y-1 text-sm">
        {SECTIONS.map((s) => (
          <div key={s.id}>
            <a
              href={`#sec-${s.id}`}
              className={`flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors ${
                active === s.id
                  ? "bg-secondary font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <s.icon className="size-3.5" /> {s.title}
            </a>
            {active === s.id && (
              <div className="ml-4 mt-0.5 space-y-0.5 border-l pl-3">
                {s.subs.map((sub) => (
                  <a key={sub.id} href={`#${sub.id}`} onClick={() => setActive(s.id)}
                    className="block py-0.5 text-xs text-muted-foreground hover:text-foreground">
                    {sub.title}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* Content */}
      <div className="max-w-3xl space-y-12 pb-24">
        <div>
          <h1 className="text-2xl font-semibold">Documentation</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Everything the dashboard can do, in plain language. No prior knowledge required.
          </p>
        </div>
        {SECTIONS.map((s) => (
          <section key={s.id} id={`sec-${s.id}`} className="scroll-mt-20">
            <h2 className="mb-4 flex items-center gap-2 border-b pb-2 text-lg font-semibold">
              <s.icon className="size-5 text-muted-foreground" /> {s.title}
            </h2>
            <div className="space-y-8">
              {s.subs.map((sub) => (
                <div key={sub.id} id={sub.id} className="scroll-mt-20">
                  <h3 className="mb-2 text-sm font-semibold">{sub.title}</h3>
                  <div className="space-y-2">{sub.body}</div>
                  {sub.img && (
                    <div className="mt-3 aspect-[1400/860] overflow-hidden rounded-lg border shadow-sm">
                      <img src={sub.img} alt={sub.title} className="h-full w-full object-cover" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
