import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { api, fmtDuration, relativeTime } from "@/lib/api"
import { Card, CardContent } from "@/components/ui/card"
import { StatusBadge, TrendIcon, scoreColor } from "@/components/shared"
import { RunHeatmap } from "@/components/observability"

export default function HealthPage() {
  const { data } = useQuery({ queryKey: ["health"], queryFn: api.health })
  if (!data) return null

  return (
    <div className="space-y-6">
    <RunHeatmap />
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {data.agents.map((a) => (
        <Link key={a.name} to={`/agent/${a.name}`} className="block">
        <Card className={`h-full cursor-pointer transition-shadow hover:shadow-md ${a.total > 0 && a.score < 70 ? "border-red-500/40" : ""}`}>
          <CardContent className="p-4">
            <div className="flex items-start justify-between">
              <span className="font-medium">{a.name}</span>
              <TrendIcon trend={a.trend} />
            </div>
            <div className={`mt-2 text-3xl font-semibold tabular-nums ${scoreColor(a.score, a.total)}`}>
              {a.total ? `${a.score}%` : "—"}
            </div>
            <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
              <span className="text-emerald-500">{a.ok} ok</span>
              {a.fail > 0 && <span className="text-red-500">{a.fail} fail</span>}
              <span>avg {fmtDuration(a.avg_dur)}</span>
              <span>{a.last_run ? relativeTime(a.last_run) : "never ran"}</span>
            </div>
            {a.total === 0 && (
              <div className="mt-2"><StatusBadge status="pending" /></div>
            )}
          </CardContent>
        </Card>
        </Link>
      ))}
    </div>
    </div>
  )
}
