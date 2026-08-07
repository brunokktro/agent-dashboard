import { useQuery } from "@tanstack/react-query"
import {
  Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip as ChartTooltip, XAxis, YAxis,
} from "recharts"
import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${url}: ${r.status}`)
  return r.json()
}

interface SeriesPoint {
  date: string
  p50: number
  p95: number
  p99: number
  runs: number
  success_rate: number | null
}

export function DurationPercentiles({ agent }: { agent: string }) {
  const { data } = useQuery({
    queryKey: ["obs", agent],
    queryFn: () => fetchJson<{ series: SeriesPoint[] }>(`/api/observability/agent/${agent}`),
  })
  if (!data || data.series.length < 2) return null
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Duration · P50 / P95 / P99 (30d)
          </CardTitle>
        </CardHeader>
        <CardContent className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.series}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" fontSize={10} tickFormatter={(d) => d.slice(5)} />
              <YAxis fontSize={10} tickFormatter={(v) => `${v}s`} width={44} />
              <ChartTooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Area isAnimationActive={false} dataKey="p99" stroke="#f59e0b" fill="#f59e0b22" name="P99" />
              <Area isAnimationActive={false} dataKey="p95" stroke="#8b5cf6" fill="#8b5cf622" name="P95" />
              <Area isAnimationActive={false} dataKey="p50" stroke="#10b981" fill="#10b98144" name="P50" />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Success rate (30d)
          </CardTitle>
        </CardHeader>
        <CardContent className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.series}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" fontSize={10} tickFormatter={(d) => d.slice(5)} />
              <YAxis fontSize={10} domain={[0, 100]} tickFormatter={(v) => `${v}%`} width={40} />
              <ChartTooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Line isAnimationActive={false} dataKey="success_rate" stroke="#10b981"
                strokeWidth={2} dot={false} connectNulls name="success %" />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}

interface HeatCell { dow: number; hour: number; runs: number; fails: number }
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

export function RunHeatmap() {
  const [hover, setHover] = useState<string | null>(null)
  const { data } = useQuery({
    queryKey: ["heatmap"],
    queryFn: () => fetchJson<{ cells: HeatCell[] }>("/api/observability/heatmap"),
  })
  if (!data) return null
  const map = new Map(data.cells.map((c) => [`${c.dow}-${c.hour}`, c]))
  const max = Math.max(1, ...data.cells.map((c) => c.runs))

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Run activity · day × hour (30d) - red tint = failures
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-2 h-5 text-xs font-medium tabular-nums text-muted-foreground">
          {hover ?? "Hover a cell for details"}
        </div>
        <div className="grid gap-[2px]" style={{ gridTemplateColumns: "38px repeat(24, 1fr)", maxWidth: "100%" }}>
          <div />
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} className="pb-1 text-center text-[9px] text-muted-foreground">
              {h % 3 === 0 ? h : ""}
            </div>
          ))}
          {Array.from({ length: 7 }, (_, dow) => (
            <>
              <div key={`l${dow}`} className="pr-2 text-right text-[10px] leading-4 text-muted-foreground">
                {DOW[dow]}
              </div>
              {Array.from({ length: 24 }, (_, hour) => {
                const c = map.get(`${dow}-${hour}`)
                const intensity = c ? Math.max(0.15, c.runs / max) : 0
                const failRatio = c && c.runs ? c.fails / c.runs : 0
                const color = failRatio > 0.3 ? "239 68 68" : "16 185 129"
                return (
                  <div
                    key={`${dow}-${hour}`}
                    onMouseEnter={() => setHover(c
                      ? `${DOW[dow]} ${String(hour).padStart(2, "0")}:00 - ${c.runs} runs, ${c.fails} failed (${c.runs ? Math.round((c.runs - c.fails) * 100 / c.runs) : 0}% ok)`
                      : `${DOW[dow]} ${String(hour).padStart(2, "0")}:00 - no runs`)}
                    onMouseLeave={() => setHover(null)}
                    className="h-7 w-full cursor-default rounded-[1px] transition-all hover:ring-2 hover:ring-foreground/50"
                    style={{
                      backgroundColor: c
                        ? `rgb(${color} / ${intensity})`
                        : "rgb(115 115 115 / 0.08)",
                    }}
                  />
                )
              })}
            </>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
