import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { AlertTriangle, CheckCircle2, Info, Play, XCircle } from "lucide-react"
import { Bar, BarChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis } from "recharts"
import { toast } from "sonner"
import { useState } from "react"
import { api, fmtDuration, relativeTime } from "@/lib/api"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { StatCard, StatusBadge, TrendIcon, scoreColor } from "@/components/shared"

interface Diagnosis {
  run: { job_id: string; exit_code: number | null; duration_sec: number | null; started_at: string }
  exit_meaning: string
  hints: string[]
  error_lines: string[]
  segment_tail: string[]
  log: string | null
}

export default function OverviewPage() {
  const [diag, setDiag] = useState<Diagnosis | null>(null)
  const [diagLoading, setDiagLoading] = useState(false)
  const diagnose = async (id: number) => {
    setDiagLoading(true)
    try {
      const r = await fetch(`/api/runs/${id}/diagnose`)
      setDiag(await r.json())
    } finally { setDiagLoading(false) }
  }
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ["overview"], queryFn: api.overview })

  const ack = useMutation({
    mutationFn: (ids: string[]) => api.ackAlerts(ids),
    onSuccess: () => {
      toast.success("Alerts acknowledged")
      qc.invalidateQueries({ queryKey: ["overview"] })
    },
  })

  const trigger = useMutation({
    mutationFn: (name: string) => api.triggerAgent(name),
    onSuccess: (_d, name) => toast.success(`Triggered ${name}`),
    onError: (e) => toast.error(String(e)),
  })

  if (isLoading || !data) return <OverviewSkeleton />

  const { metrics, alerts, agents, timeline, chart } = data

  if (metrics.total_runs === 0 && agents.length === 0) {
    return (
      <div className="mx-auto max-w-xl space-y-4 py-16 text-center">
        <h2 className="text-lg font-semibold">Welcome! Nothing recorded yet.</h2>
        <p className="text-sm text-muted-foreground">
          Point <code className="rounded bg-muted px-1">DASHBOARD_AGENTS_DIR</code> at your
          agent ecosystem, or record your first run with the universal adapter:
        </p>
        <pre className="rounded-lg bg-muted p-3 text-left text-xs">
          bin/record-run my-first-job echo "hello dashboard"
        </pre>
        <p className="text-sm text-muted-foreground">
          Full onboarding guide in the <Link className="text-blue-500 hover:underline" to="/help">Help tab</Link>.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Metrics */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Total runs" value={metrics.total_runs.toLocaleString()} />
        <StatCard label="OK · 24h" value={metrics.ok_24h} tone="ok" />
        <StatCard label="Failed · 24h" value={metrics.fail_24h} tone={metrics.fail_24h ? "fail" : undefined} />
        <StatCard
          label="Running now"
          value={
            metrics.running.length ? (
              <span className="text-blue-500">{metrics.running.length}</span>
            ) : (
              "0"
            )
          }
        />
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((a, i) => (
            <div
              key={i}
              className={`flex items-start justify-between gap-3 rounded-lg border p-3 text-sm ${
                a.type === "fail"
                  ? "border-red-500/30 bg-red-500/5"
                  : a.type === "warn"
                    ? "border-amber-500/30 bg-amber-500/5"
                    : "border-blue-500/20 bg-blue-500/5"
              }`}
            >
              <div className="flex items-start gap-2">
                {a.type === "fail" ? (
                  <XCircle className="mt-0.5 size-4 shrink-0 text-red-500" />
                ) : a.type === "warn" ? (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" />
                ) : (
                  <Info className="mt-0.5 size-4 shrink-0 text-blue-500" />
                )}
                <div>
                  <div>{a.message}</div>
                  {a.items && (
                    <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
                      {a.items.map((f) => (
                        <li key={f.id} className="flex flex-wrap items-center gap-x-2">
                          <span className="font-medium text-foreground">{f.job_id}</span>
                          <span>{relativeTime(f.started_at)}</span>
                          <span>exit {f.exit_code ?? "?"}</span>
                          {f.duration_sec != null && <span>after {fmtDuration(f.duration_sec)}</span>}
                          <button
                            className="text-blue-500 hover:underline"
                            disabled={diagLoading}
                            onClick={() => diagnose(f.id)}
                          >
                            diagnose
                          </button>
                          {f.log_path && (
                            <Link
                              className="text-blue-500 hover:underline"
                              to={`/logs?file=${encodeURIComponent(f.log_path.split("/").pop() ?? "")}`}
                            >
                              view log →
                            </Link>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
              {a.ids && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => ack.mutate(a.ids!.split(","))}
                  disabled={ack.isPending}
                >
                  <CheckCircle2 className="size-3.5" /> Ack
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 7-day chart */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Runs · last 7 days
          </CardTitle>
        </CardHeader>
        <CardContent className="h-36">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} barCategoryGap="25%">
              <XAxis dataKey="day" tickLine={false} axisLine={false} fontSize={12} />
              <ChartTooltip
                cursor={{ fill: "hsl(var(--muted))", opacity: 0.4 }}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Bar isAnimationActive={false} dataKey="ok" stackId="a" fill="#10b981" radius={[0, 0, 4, 4]} />
              <Bar isAnimationActive={false} dataKey="fail" stackId="a" fill="#ef4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Agents grid */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Agents ({agents.length})
          </h2>
          <Link to="/agents" className="text-xs text-blue-500 hover:underline">View all →</Link>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {agents.slice(0, 6).map((a) => (
            <Link key={a.name} to={`/agent/${a.name}`} className="block">
            <Card
              className={`h-full cursor-pointer transition-shadow hover:shadow-md ${a.is_running ? "border-blue-500/50 shadow-[0_0_12px_-3px_rgb(59_130_246/0.5)]" : ""}`}
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium">{a.name}</span>
                  <div className="flex items-center gap-2">
                    {a.is_running && <StatusBadge status="running" />}
                    <TrendIcon trend={a.stats.trend} />
                  </div>
                </div>
                <p className="mt-1 line-clamp-2 min-h-8 text-xs text-muted-foreground">
                  {a.description || "No description"}
                </p>
                <div className="mt-3 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3 text-muted-foreground">
                    <span className={scoreColor(a.stats.score, a.stats.total)}>
                      {a.stats.total ? `${a.stats.score}%` : "no data"}
                    </span>
                    <span>{a.stats.total} runs</span>
                    <span>{a.stats.last ? relativeTime(a.stats.last.started_at) : ""}</span>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); trigger.mutate(a.name) }}
                    disabled={trigger.isPending || a.is_running}
                    title="Run now"
                  >
                    <Play className="size-3.5" />
                  </Button>
                </div>
              </CardContent>
            </Card>
            </Link>
          ))}
        </div>
      </section>

      {/* Timeline */}
      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Recent runs
        </h2>
        <Card>
          <CardContent className="divide-y p-0">
            {timeline.map((r) => (
              <div key={r.id} className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
                <div className="flex min-w-0 items-center gap-3">
                  <StatusBadge status={r.status} />
                  <span className="truncate font-medium">{r.job_id}</span>
                </div>
                <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                  <span>{fmtDuration(r.duration_sec)}</span>
                  <span>{relativeTime(r.started_at)}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <Dialog open={!!diag} onOpenChange={(o) => !o && setDiag(null)}>
        <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col overflow-hidden">
          {diag && (
            <>
              <DialogHeader>
                <DialogTitle>Why did {diag.run.job_id} fail?</DialogTitle>
                <DialogDescription>
                  {relativeTime(diag.run.started_at)} · exit {diag.run.exit_code}
                  {diag.run.duration_sec != null && <> · ran {fmtDuration(diag.run.duration_sec)}</>}
                </DialogDescription>
              </DialogHeader>
              <div className="min-h-0 space-y-4 overflow-y-auto pr-1 text-sm">
                {diag.hints.length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase text-muted-foreground">Probable cause</div>
                    {diag.hints.map((h, i) => (
                      <div key={i} className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                        {h}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-lg border p-3 text-muted-foreground">
                    Exit {diag.run.exit_code}: {diag.exit_meaning || "no known pattern detected - the run's log segment is below"}
                  </div>
                )}
                {diag.error_lines.length > 0 && (
                  <div>
                    <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">
                      Error lines (this run only)
                    </div>
                    <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-zinc-950 p-3 text-[11px] leading-relaxed text-red-300">
                      {diag.error_lines.join("\n")}
                    </pre>
                  </div>
                )}
                <div>
                  <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">
                    Last lines of the run
                  </div>
                  <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-zinc-950 p-3 text-[11px] leading-relaxed text-zinc-300">
                    {diag.segment_tail.join("\n") || "log not found"}
                  </pre>
                </div>
                {diag.log && (
                  <Link to={`/logs?file=${encodeURIComponent(diag.log)}`}
                    className="text-xs text-blue-500 hover:underline" onClick={() => setDiag(null)}>
                    Open full log →
                  </Link>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Schedule summary (full view lives in /supervisor) */}
      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Schedule
        </h2>
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4 text-sm">
            <div className="flex items-center gap-4">
              <span>{data.schedule.length} jobs</span>
              <span className="text-emerald-500">
                {data.schedule.filter((j) => j.last_run?.status === "success").length} healthy
              </span>
              {data.schedule.filter((j) => j.last_run?.status === "failed").length > 0 && (
                <span className="text-red-500">
                  {data.schedule.filter((j) => j.last_run?.status === "failed").length} failing
                </span>
              )}
            </div>
            <Button asChild variant="outline" size="sm">
              <Link to="/supervisor">Open Supervisor →</Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    </div>
  )
}

function OverviewSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-44" />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    </div>
  )
}
