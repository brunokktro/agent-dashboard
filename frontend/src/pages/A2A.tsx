/** A2A page: the inter-agent protocol, as it actually is on disk.
 *
 *  Two files, deliberately both: `handoffs.jsonl` is append-only AUDIT and
 *  `agents-state/queue` is the real TRANSPORT. Showing only the audit is what
 *  let a handoff sit `pending` for ten days with nothing to execute it, so the
 *  Drift panel exists to make that exact disagreement visible.
 *
 *  ACCESSIBILITY: every status renders an ICON PLUS THE WORD. Colour is
 *  decoration here, never the carrier of meaning - `stale` and `failed` must be
 *  distinguishable without perceiving hue, and they have distinct glyphs
 *  (TimerOff vs XCircle) rather than the same shape in two colours.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Activity, AlertTriangle, Ban, Bookmark, CheckCircle2, CircleDashed, Clock, ExternalLink,
  FileWarning, Inbox, Loader2, Megaphone, Network, PauseCircle, RefreshCw, TimerOff, XCircle,
} from "lucide-react"
import { api, relativeTime, type A2AData, type Discovery, type Drift, type Handoff } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"

/** Icon + word + tone for every status the canonical reader can emit.
 *  `stale` is the one that is DERIVED (timeout_sec elapsed while still
 *  pending/running), so it says so in its tooltip - otherwise a reader would
 *  hunt for a "stale" value in the JSONL that is not there. */
const STATUS_META: Record<string, {
  icon: typeof CheckCircle2; text: string; cls: string; spin?: boolean; hint: string
}> = {
  done: {
    icon: CheckCircle2, text: "done", cls: "text-emerald-600 dark:text-emerald-400",
    hint: "completed; the worker appended a result event",
  },
  running: {
    icon: Loader2, text: "running", cls: "text-blue-600 dark:text-blue-400", spin: true,
    hint: "picked up and executing",
  },
  pending: {
    icon: CircleDashed, text: "pending", cls: "text-amber-600 dark:text-amber-400",
    hint: "queued, still inside its timeout_sec",
  },
  stale: {
    icon: TimerOff, text: "stale", cls: "text-orange-600 dark:text-orange-400",
    hint: "DERIVED, not stored: still open past timeout_sec (read-handoffs.py)",
  },
  failed: {
    icon: XCircle, text: "failed", cls: "text-red-600 dark:text-red-400",
    hint: "the worker reported a failure",
  },
  canceled: {
    icon: Ban, text: "canceled", cls: "text-muted-foreground",
    hint: "withdrawn, usually superseded by another handoff",
  },
  deferred: {
    icon: PauseCircle, text: "deferred", cls: "text-muted-foreground",
    hint: "accepted but intentionally postponed",
  },
  unknown: {
    icon: AlertTriangle, text: "unknown", cls: "text-muted-foreground",
    hint: "no status on the latest event for this id",
  },
}

function StatusChip({ status, className = "" }: { status: string; className?: string }) {
  const meta = STATUS_META[status] ?? STATUS_META.unknown
  const Icon = meta.icon
  return (
    <span
      title={`${status}: ${meta.hint}`}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium ${meta.cls} ${className}`}
    >
      <Icon className={`size-3.5 shrink-0 ${meta.spin ? "animate-spin" : ""}`} aria-hidden />
      {meta.text}
    </span>
  )
}

/** Queue counter. Shows the A2A number big, and the whole-queue total small:
 *  the delivery queue is SHARED with ordinary backlog work, so "3" without
 *  "of 152" invites the wrong conclusion about how busy the queue is. */
function QueueCounter({
  label, a2a, total, icon: Icon, cls, capped,
}: {
  label: string; a2a: number; total: number
  icon: typeof Inbox; cls: string; capped: boolean
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <Icon className={`size-3.5 ${cls}`} aria-hidden />
          {label}
          {capped && (
            <span title="scan capped: this count is a lower bound">
              <AlertTriangle className="size-3 text-amber-500" aria-hidden />
            </span>
          )}
        </div>
        <div className="mt-1 flex items-baseline gap-1.5">
          <span className="text-2xl font-semibold tabular-nums">{a2a}</span>
          <span className="text-xs text-muted-foreground">
            A2A{total !== a2a && <> · of {total} total</>}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}

const QUEUE_COLUMNS = [
  { key: "pending", label: "Pending", icon: CircleDashed, cls: "text-amber-500" },
  { key: "running", label: "Running", icon: Loader2, cls: "text-blue-500" },
  { key: "done", label: "Done", icon: CheckCircle2, cls: "text-emerald-500" },
  { key: "failed", label: "Failed", icon: XCircle, cls: "text-red-500" },
] as const

/** Drift: audit and transport disagree. Highest-value panel on the page, so it
 *  sits above the raw lists and is absent (not empty) when healthy. */
function DriftPanel({ drift }: { drift: Drift[] }) {
  return (
    <Card className="border-amber-500/40">
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <FileWarning className="size-4 text-amber-500" aria-hidden />
          Audit / transport drift
          <Badge variant="outline" className="tabular-nums">{drift.length}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          <code>handoffs.jsonl</code> and <code>agents-state/queue</code> disagree. An open
          handoff with no queue item will never execute, whatever the audit says.
        </p>
        <div className="space-y-1.5">
          {drift.map((d) => (
            <div key={`${d.kind}-${d.id}`}
              className="flex flex-wrap items-center gap-2 rounded-md border bg-amber-500/5 px-2.5 py-2 text-xs">
              <Badge variant="outline" className="font-mono text-[10px]">
                {d.kind === "orphan_audit" ? "audit only" : "queue only"}
              </Badge>
              <code className="font-mono">{d.id}</code>
              <StatusChip status={d.status} />
              {d.to && <span className="text-muted-foreground">to {d.to}</span>}
              <span className="text-muted-foreground">{d.detail}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function HandoffsTable({ data }: { data: A2AData }) {
  const items: Handoff[] = data.handoffs.items
  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center gap-2 border-b px-4 py-3">
          <ArrowIcon />
          <span className="text-sm font-semibold">Latest handoffs</span>
          <span className="text-xs text-muted-foreground">
            {data.handoffs.shown} of {data.handoffs.total}
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {Object.entries(data.handoffs.counts)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([status, n]) => (
                <span key={status} className="inline-flex items-center gap-1">
                  <StatusChip status={status} />
                  <span className="text-xs tabular-nums text-muted-foreground">{n}</span>
                </span>
              ))}
          </div>
        </div>
        <ScrollArea className="max-h-[26rem]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[7.5rem]">Status</TableHead>
                <TableHead>Route</TableHead>
                <TableHead>Skill</TableHead>
                <TableHead className="w-[6rem]">When</TableHead>
                <TableHead>Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((h) => (
                <TableRow key={h.id}>
                  <TableCell><StatusChip status={h.status} /></TableCell>
                  <TableCell className="text-xs">
                    <span className="font-medium">{h.from ?? "?"}</span>
                    <span className="mx-1 text-muted-foreground">&rarr;</span>
                    <span className="font-medium">{h.to ?? "?"}</span>
                    <div className="font-mono text-[10px] text-muted-foreground" title={h.id}>
                      {h.id}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">
                    {h.skill ?? <span className="text-muted-foreground">&mdash;</span>}
                    {h.acceptance_pattern && (
                      <Badge variant="outline" className="ml-1.5 px-1 py-0 text-[10px]"
                        title={`acceptance_pattern: ${h.acceptance_pattern}`}>
                        verified
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground" title={h.ts}>
                    {relativeTime(h.ts)}
                    {h.timeout_sec != null && (
                      <div className="text-[10px]">timeout {h.timeout_sec}s</div>
                    )}
                  </TableCell>
                  <TableCell className="max-w-[22rem] text-xs text-muted-foreground">
                    <span className="line-clamp-2" title={h.result ?? h.expected_output ?? ""}>
                      {h.result ?? (
                        <span className="italic">
                          expected: {h.expected_output ?? "unspecified"}
                        </span>
                      )}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
              {items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-10 text-center text-xs text-muted-foreground">
                    No handoffs recorded yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

function ArrowIcon() {
  return <Network className="size-4 text-muted-foreground" aria-hidden />
}

function DiscoveriesPanel({ data }: { data: A2AData }) {
  const items: Discovery[] = data.discoveries.items
  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center gap-2 border-b px-4 py-3">
          <Megaphone className="size-4 text-muted-foreground" aria-hidden />
          <span className="text-sm font-semibold">Discoveries</span>
          <span className="text-xs text-muted-foreground">
            {data.discoveries.total} active · last {Math.round(data.discoveries.since_hours / 24)}d
          </span>
        </div>
        <ScrollArea className="max-h-[26rem]">
          <div className="divide-y">
            {items.map((d, i) => (
              <div key={`${d.ts}-${i}`} className="space-y-1.5 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium">{d.from ?? "?"}</span>
                  {d.broadcast ? (
                    <Badge variant="outline" className="gap-1 px-1.5 py-0 text-[10px]"
                      title="no `to` field: every consumer receives it">
                      <Megaphone className="size-2.5" aria-hidden /> broadcast
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="px-1.5 py-0 text-[10px]"
                      title={`addressed to: ${d.to.join(", ")}`}>
                      to {d.to.join(", ")}
                    </Badge>
                  )}
                  <span className="ml-auto text-[11px] text-muted-foreground" title={d.ts}>
                    {relativeTime(d.ts)}
                  </span>
                </div>
                <div className="font-mono text-[11px] text-muted-foreground">{d.topic}</div>
                <p className="line-clamp-3 text-xs" title={d.content}>{d.content}</p>
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <Clock className="size-2.5" aria-hidden /> ttl {d.ttl_days}d
                  {d.truncated && <span>· {d.content_chars} chars, truncated for display</span>}
                </div>
              </div>
            ))}
            {items.length === 0 && (
              <div className="py-10 text-center text-xs text-muted-foreground">
                No active discoveries in the window.
              </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

/** Consumer watermarks. Lists anyone holding a cursor PLUS anyone addressed by
 *  a discovery, so "targeted but never consumed" is visible - a consumer with
 *  no cursor would otherwise not appear at all. */
function WatermarksPanel({ data }: { data: A2AData }) {
  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center gap-2 border-b px-4 py-3">
          <Bookmark className="size-4 text-muted-foreground" aria-hidden />
          <span className="text-sm font-semibold">Consumer watermarks</span>
          <span className="text-xs text-muted-foreground">
            {data.watermarks.length} consumer{data.watermarks.length === 1 ? "" : "s"}
          </span>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Consumer</TableHead>
              <TableHead className="w-[8rem]">Backlog</TableHead>
              <TableHead>Cursor</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.watermarks.map((w) => (
              <TableRow key={w.consumer}>
                <TableCell className="text-xs font-medium">{w.consumer}</TableCell>
                <TableCell>
                  {w.lag === 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="size-3.5" aria-hidden /> caught up
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400"
                      title="unread discoveries this consumer would receive on its next preflight">
                      <Inbox className="size-3.5" aria-hidden />
                      {w.lag}{w.lag_capped ? "+" : ""} unread
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {w.never_acked ? (
                    <span className="inline-flex items-center gap-1.5 text-amber-600 dark:text-amber-400"
                      title="no entry in discovery-watermarks.json: never acked anything">
                      <AlertTriangle className="size-3.5" aria-hidden /> never acked
                    </span>
                  ) : (
                    <span title={w.watermark ?? ""}>
                      through {relativeTime(w.watermark)}
                    </span>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data.watermarks.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-xs text-muted-foreground">
                  No consumers have a cursor and none are addressed by name.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function WorkerHealth({ data }: { data: A2AData }) {
  const worker = data.worker
  return (
    <Card className={worker.healthy ? "" : "border-amber-500/40"}>
      <CardContent className="flex flex-wrap items-center gap-3 p-4">
        <Activity className="size-4 text-muted-foreground" aria-hidden />
        <div>
          <p className="text-sm font-semibold">Delivery worker</p>
          <p className="text-xs text-muted-foreground">
            Last cycle {relativeTime(worker.last_cycle_at)}
            {worker.last_cycle_started != null && ` · started ${worker.last_cycle_started}`}
          </p>
        </div>
        <span className={`ml-auto inline-flex items-center gap-1.5 text-xs font-medium ${
          worker.healthy ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"
        }`}>
          {worker.healthy ? <CheckCircle2 className="size-3.5" aria-hidden /> : <TimerOff className="size-3.5" aria-hidden />}
          {worker.healthy ? "healthy" : "needs attention"}
        </span>
        {worker.last_error && (
          <p className="w-full border-t pt-2 text-xs text-muted-foreground">
            Last error {relativeTime(worker.last_error_at)}: {worker.last_error}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/** Which files produced this page, and which reader parsed them. On an
 *  observability page the provenance IS part of the data: a number with no
 *  traceable source cannot be acted on. */
function SourcesPanel({ data }: { data: A2AData }) {
  const rows: [string, string, boolean | null][] = [
    ["handoffs (audit)", data.sources.handoffs, data.sources.handoffs_exists],
    ["discoveries", data.sources.discoveries, data.sources.discoveries_exists],
    ["watermarks", data.sources.watermarks, null],
    ["queue (transport)", data.sources.queue, null],
  ]
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ExternalLink className="size-4 text-muted-foreground" aria-hidden />
          Sources
        </div>
        <div className="space-y-1 font-mono text-[11px]">
          {rows.map(([label, path, exists]) => (
            <div key={label} className="flex flex-wrap items-center gap-2">
              <span className="w-[8.5rem] shrink-0 font-sans text-muted-foreground">{label}</span>
              <code className="break-all">{path}</code>
              {exists === false && (
                <span className="inline-flex items-center gap-1 font-sans text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="size-3" aria-hidden /> not created yet
                </span>
              )}
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="w-[8.5rem] shrink-0 font-sans text-muted-foreground">parsed by</span>
            <code className="break-all">
              {Object.values(data.sources.parsers).join("  ·  ")}
            </code>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          This page runs the ecosystem's own readers rather than its own parser, so
          <code className="mx-1">stale</code> and TTL expiry mean exactly what the CLI means.
        </p>
      </CardContent>
    </Card>
  )
}

export default function A2APage() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ["a2a"], queryFn: api.a2a })

  if (isLoading) {
    return <div className="py-16 text-center text-sm text-muted-foreground">Loading A2A state…</div>
  }
  if (error || !data) {
    return (
      <Card className="border-red-500/40">
        <CardContent className="flex items-center gap-2 p-4 text-sm">
          <XCircle className="size-4 text-red-500" aria-hidden />
          Could not read A2A state: {String(error)}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold">
            <Network className="size-5" aria-hidden /> A2A protocol
          </h1>
          <p className="text-xs text-muted-foreground">
            Handoffs, discoveries and consumer cursors, read through the ecosystem's
            canonical <code>read-handoffs.py</code> / <code>read-discoveries.py</code>.
          </p>
        </div>
        <div className="ml-auto">
          <Button variant="outline" size="sm" title="Refresh"
            onClick={() => qc.invalidateQueries({ queryKey: ["a2a"] })}>
            <RefreshCw className="size-3.5" aria-hidden />
          </Button>
        </div>
      </div>

      <WorkerHealth data={data} />

      {/* Degradation is stated, never silently rendered as "nothing happening". */}
      {!data.available && (
        <Card className="border-red-500/40">
          <CardContent className="space-y-1 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <XCircle className="size-4 text-red-500" aria-hidden />
              A2A readers unavailable
            </div>
            {data.degraded.map((d) => (
              <p key={d} className="font-mono text-xs text-muted-foreground">{d}</p>
            ))}
            <p className="text-xs text-muted-foreground">
              Counts below are empty because nothing could be parsed - this is not the same
              as an idle protocol.
            </p>
          </CardContent>
        </Card>
      )}
      {data.available && data.degraded.length > 0 && (
        <Card className="border-amber-500/40">
          <CardContent className="space-y-1 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <AlertTriangle className="size-4 text-amber-500" aria-hidden /> Partial data
            </div>
            {data.degraded.map((d) => (
              <p key={d} className="font-mono text-xs text-muted-foreground">{d}</p>
            ))}
          </CardContent>
        </Card>
      )}

      {/* KPIs first: delivery queue is where work actually moves. */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {QUEUE_COLUMNS.map(({ key, label, icon, cls }) => (
          <QueueCounter
            key={key}
            label={label}
            icon={icon}
            cls={cls}
            a2a={data.queue.counts[key] ?? 0}
            total={data.queue.queue_totals[key] ?? 0}
            capped={data.queue.capped.includes(key)}
          />
        ))}
      </div>

      {data.drift.length > 0 && <DriftPanel drift={data.drift} />}

      <HandoffsTable data={data} />

      <div className="grid gap-4 lg:grid-cols-2">
        <DiscoveriesPanel data={data} />
        <WatermarksPanel data={data} />
      </div>

      <SourcesPanel data={data} />
    </div>
  )
}
