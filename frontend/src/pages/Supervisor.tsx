import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { CalendarClock, Play, Search } from "lucide-react"
import { toast } from "sonner"
import { api, relativeTime, type ScheduleJob } from "@/lib/api"
import { countdown, humanizeCron, nextRun } from "@/lib/cron"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet"
import { StatusBadge } from "@/components/shared"

type Facet = "all" | "failing" | "disabled" | "ok"

export default function SupervisorPage() {
  const { data } = useQuery({ queryKey: ["supervisor"], queryFn: api.supervisor })
  const [, setTick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 1000)
    return () => clearInterval(t)
  }, [])
  const [facet, setFacet] = useState<Facet>("all")
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState<ScheduleJob | null>(null)

  const [cronDraft, setCronDraft] = useState("")
  const editCron = useMutation({
    mutationFn: ({ id, cron }: { id: string; cron: string }) =>
      fetch(`/api/supervisor/job/${id}/cron`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cron }),
      }).then(async (r) => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() }),
    onSuccess: () => toast.success("Cron updated - takes effect on the supervisor's next reload"),
    onError: (e) => toast.error(String(e)),
  })
  const toggle = useMutation({
    mutationFn: (id: string) =>
      fetch(`/api/supervisor/job/${id}/toggle`, { method: "POST" }).then((r) => r.json()),
    onSuccess: (d) => toast.success(d.enabled ? "Job enabled" : "Job disabled"),
    onError: (e) => toast.error(String(e)),
  })
  const trigger = useMutation({
    mutationFn: api.triggerJob,
    onSuccess: (d) => toast.success(`Triggered (agent: ${d.agent})`),
    onError: (e) => toast.error(String(e)),
  })

  const jobs = useMemo(() => {
    let list = data?.schedule ?? []
    const q = search.trim().toLowerCase()
    if (q) list = list.filter((j) => j.id.toLowerCase().includes(q))
    if (facet === "failing") list = list.filter((j) => j.last_run?.status === "failed")
    if (facet === "disabled") list = list.filter((j) => !j.enabled)
    if (facet === "ok") list = list.filter((j) => j.enabled && j.last_run?.status === "success")
    // failing pinned first, then by next run
    return [...list].sort((a, b) => {
      const aFail = a.last_run?.status === "failed" ? 0 : 1
      const bFail = b.last_run?.status === "failed" ? 0 : 1
      if (aFail !== bFail) return aFail - bFail
      const an = nextRun(a.cron)?.getTime() ?? Infinity
      const bn = nextRun(b.cron)?.getTime() ?? Infinity
      return an - bn
    })
  }, [data, facet, search])

  const upNext = useMemo(() => {
    return (data?.schedule ?? [])
      .filter((j) => j.enabled)
      .map((j) => ({ job: j, at: nextRun(j.cron) }))
      .filter((x): x is { job: ScheduleJob; at: Date } => x.at !== null)
      .sort((a, b) => a.at.getTime() - b.at.getTime())
      .slice(0, 6)
  }, [data])

  if (!data) return null

  const failing = data.schedule.filter((j) => j.last_run?.status === "failed").length
  const disabled = data.schedule.filter((j) => !j.enabled).length
  const healthy = data.schedule.filter((j) => j.enabled && j.last_run?.status === "success").length

  const kpi = (label: string, value: React.ReactNode, f: Facet, tone = "") => (
    <button
      onClick={() => setFacet(facet === f ? "all" : f)}
      className={`rounded-xl border p-4 text-left transition-colors hover:bg-muted/50 ${
        facet === f ? "border-primary bg-muted/60" : ""
      }`}
    >
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
    </button>
  )

  return (
    <div className="space-y-6">
      {/* Supervisor status line */}
      <div className="flex items-center gap-3 text-sm">
        <span className={`inline-flex size-2.5 rounded-full ${
          data.status === "running" ? "bg-emerald-500" : "bg-red-500"
        }`} />
        <span className="font-medium">Supervisor {data.status}</span>
        {data.pid && <span className="text-muted-foreground">pid {data.pid} · up {data.uptime}</span>}
        <span className="ml-auto text-muted-foreground">
          {data.today_runs} runs today · {data.total_runs.toLocaleString()} all-time
        </span>
      </div>

      {/* Clickable KPI filters */}
      <div className="grid grid-cols-4 gap-4">
        {kpi("All jobs", data.schedule.length, "all")}
        {kpi("Healthy", healthy, "ok", "text-emerald-500")}
        {kpi("Failing", failing, "failing", failing ? "text-red-500" : "")}
        {kpi("Disabled", disabled, "disabled", "text-muted-foreground")}
      </div>

      {/* Up next - live timeline */}
      <div>
        <h2 className="mb-3 flex items-center gap-1.5 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          <CalendarClock className="size-4" /> Up next
        </h2>
        <div className="relative rounded-xl border bg-muted/20 px-5 py-4">
          {/* timeline axis */}
          <div className="absolute left-5 right-5 top-[38px] h-px bg-border" />
          <div className="relative flex items-start justify-between gap-2">
            {/* NOW marker */}
            <div className="flex flex-col items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase text-emerald-500">now</span>
              <span className="relative flex size-3">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex size-3 rounded-full bg-emerald-500" />
              </span>
            </div>
            {upNext.map(({ job }, i) => (
              <button key={job.id} onClick={() => setSelected(job)}
                className="group flex flex-col items-center gap-1.5">
                <span className="max-w-28 truncate text-[11px] font-medium group-hover:text-blue-500">
                  {job.id}
                </span>
                <span className={`size-2.5 rounded-full border-2 bg-background transition-colors ${
                  i === 0 ? "animate-pulse border-blue-500" : "border-muted-foreground/40 group-hover:border-blue-500"
                }`} />
                <span className={`tabular-nums text-[10px] ${i === 0 ? "font-semibold text-blue-500" : "text-muted-foreground"}`}>
                  {countdown(nextRun(job.cron))}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
        <Input placeholder="Filter jobs…" value={search}
          onChange={(e) => setSearch(e.target.value)} className="pl-8" />
      </div>

      {/* Job cards */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {jobs.map((j) => {
          const next = nextRun(j.cron)
          const failedLast = j.last_run?.status === "failed"
          return (
            <Card
              key={j.id}
              onClick={() => setSelected(j)}
              className={`cursor-pointer transition-shadow hover:shadow-md ${
                failedLast ? "border-red-500/40" : ""
              } ${!j.enabled ? "opacity-60" : ""}`}
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <span className="truncate font-medium">{j.id}</span>
                  {!j.enabled ? (
                    <Badge variant="outline">disabled</Badge>
                  ) : j.last_run ? (
                    <StatusBadge status={j.last_run.status} />
                  ) : (
                    <Badge variant="outline">never ran</Badge>
                  )}
                </div>
                <p className="mt-1.5 line-clamp-2 min-h-8 text-xs text-muted-foreground">
                  {humanizeCron(j.cron)}
                </p>
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span>
                    {j.last_run ? `last ${relativeTime(j.last_run.started_at)}` : ""}
                  </span>
                  <span className="tabular-nums font-medium text-foreground">
                    {j.enabled ? countdown(next) : ""}
                  </span>
                </div>
              </CardContent>
            </Card>
          )
        })}
        {jobs.length === 0 && (
          <div className="col-span-full py-12 text-center text-sm text-muted-foreground">
            No jobs match the current filter
          </div>
        )}
      </div>

      {/* Detail drawer */}
      <Sheet open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <SheetContent className="w-[420px] sm:max-w-[420px]">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  {selected.id}
                  {!selected.enabled && <Badge variant="outline">disabled</Badge>}
                </SheetTitle>
                <SheetDescription>{humanizeCron(selected.cron)}</SheetDescription>
              </SheetHeader>
              <div className="space-y-4 px-4">
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="shrink-0 text-muted-foreground">Cron</span>
                    <Input
                      className="h-7 flex-1 font-mono text-xs"
                      defaultValue={selected.cron}
                      onChange={(e) => setCronDraft(e.target.value)}
                    />
                    <Button size="sm" variant="outline" className="h-7 text-xs"
                      disabled={!cronDraft || cronDraft === selected.cron || editCron.isPending}
                      onClick={() => editCron.mutate({ id: selected.id, cron: cronDraft })}>
                      Save
                    </Button>
                  </div>
                  {cronDraft && cronDraft !== selected.cron && (
                    <div className="text-xs text-muted-foreground">→ {humanizeCron(cronDraft)}</div>
                  )}
                  <DrawerRow k="Next run" v={countdown(nextRun(selected.cron))} />
                  <DrawerRow
                    k="Last run"
                    v={selected.last_run
                      ? <span className="flex items-center gap-2">
                          <StatusBadge status={selected.last_run.status} />
                          {relativeTime(selected.last_run.started_at)}
                        </span>
                      : "never"}
                  />
                  {selected.timeout_sec && (
                    <DrawerRow k="Timeout" v={`${Math.round(selected.timeout_sec / 60)}m`} />
                  )}
                  {selected.description && <DrawerRow k="About" v={selected.description} />}
                </div>
                <div className="flex gap-2">
                  <Button
                    className="flex-1"
                    onClick={() => { trigger.mutate(selected.id); setSelected(null) }}
                    disabled={trigger.isPending}
                  >
                    <Play className="size-4" /> Run now
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => { toggle.mutate(selected.id); setSelected(null) }}
                    disabled={toggle.isPending}
                  >
                    {selected.enabled ? "Disable" : "Enable"}
                  </Button>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}

function DrawerRow({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="shrink-0 text-muted-foreground">{k}</span>
      <span className="text-right">{v}</span>
    </div>
  )
}
