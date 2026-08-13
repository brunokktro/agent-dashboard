import { useMutation, useQuery } from "@tanstack/react-query"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { lazy, Suspense, useState } from "react"
import { ArrowLeft, Copy, Play, SquareTerminal } from "lucide-react"
import { toast } from "sonner"
import { RUNNER_HINT, api, fmtDuration, relativeTime } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { StatCard, StatusBadge, TrendIcon, scoreColor } from "@/components/shared"

const TerminalPane = lazy(() => import("@/components/TerminalPane"))
import { DurationPercentiles } from "@/components/observability"

export default function AgentPage() {
  const { name = "" } = useParams()
  const { data } = useQuery({ queryKey: ["agent", name], queryFn: () => api.agent(name) })

  const trigger = useMutation({
    mutationFn: () => api.triggerAgent(name),
    onSuccess: () => toast.success(`Triggered ${name}`),
    onError: (e) => toast.error(String(e)),
  })

  const [params] = useSearchParams()
  const [showTerminal, setShowTerminal] = useState(params.get("terminal") === "1")

  if (!data) return null
  const { info, stats, runs, job } = data
  const cliCommand = `kiro-cli chat --agent ${name} --trust-all-tools`

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button asChild variant="ghost" size="sm">
            <Link to="/"><ArrowLeft className="size-4" /></Link>
          </Button>
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold">
              {info.name} <TrendIcon trend={stats.trend} />
            </h1>
            <p className="text-sm text-muted-foreground">{info.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => {
            navigator.clipboard.writeText(cliCommand)
            toast.success("CLI command copied")
          }}>
            <Copy className="size-4" /> CLI
          </Button>
          <Button variant="outline" onClick={() => setShowTerminal(!showTerminal)}>
            <SquareTerminal className="size-4" /> Terminal
          </Button>
          <Button onClick={() => trigger.mutate()}
            disabled={!(data.capabilities?.run_agent ?? true) || trigger.isPending}
            title={(data.capabilities?.run_agent ?? true) ? "Run now" : RUNNER_HINT}>
            <Play className="size-4" /> Run now
          </Button>
        </div>
      </div>

      {showTerminal && (
        <Suspense fallback={<div className="h-72 animate-pulse rounded-lg bg-muted" />}>
          <TerminalPane sessionId={`agent-${name}`} initialCommand={cliCommand} />
        </Suspense>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <StatCard
          label="Health score"
          value={
            <span className={scoreColor(stats.score, stats.total)}>
              {stats.total ? `${stats.score}%` : "—"}
            </span>
          }
        />
        <StatCard label="Total runs" value={stats.total} />
        <StatCard label="Failures" value={stats.fail} tone={stats.fail ? "fail" : undefined} />
        <StatCard label="Avg duration" value={fmtDuration(stats.avg_dur)} />
        <StatCard label="Last run" value={stats.last ? relativeTime(stats.last.started_at) : "never"} />
      </div>

      <DurationPercentiles agent={name} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <Row k="Spec size" v={`${info.md_lines} lines`} />
            <Row k="JSON config" v={info.has_json ? "yes" : "no"} />
            <Row k="Data files" v={String(info.data_files)} />
            {info.deps && <Row k="Dependencies" v={info.deps} />}
            {job && (
              <>
                <Row k="Schedule" v={job.cron} mono />
                <Row k="Timeout" v={fmtDuration(job.timeout_sec)} />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Run history
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Exit</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell><StatusBadge status={r.status} /></TableCell>
                    <TableCell className="text-xs">{relativeTime(r.started_at)}</TableCell>
                    <TableCell className="text-xs">{fmtDuration(r.duration_sec)}</TableCell>
                    <TableCell className="text-xs tabular-nums">{r.exit_code ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{k}</span>
      <span className={mono ? "font-mono text-xs" : ""}>{v}</span>
    </div>
  )
}
