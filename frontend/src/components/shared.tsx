import { ArrowRight, Minus, TrendingDown, TrendingUp } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
    failed: "bg-red-500/15 text-red-600 dark:text-red-400",
    running: "bg-blue-500/15 text-blue-600 dark:text-blue-400 animate-pulse",
    pending: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    done: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
    cancelled: "bg-muted text-muted-foreground",
    timeout: "bg-orange-500/15 text-orange-600 dark:text-orange-400",
  }
  return (
    <Badge variant="secondary" className={`${map[status] ?? ""} border-0 font-medium`}>
      {status}
    </Badge>
  )
}

export function TrendIcon({ trend }: { trend: string }) {
  if (trend === "up") return <TrendingUp className="size-3.5 text-emerald-500" />
  if (trend === "down") return <TrendingDown className="size-3.5 text-red-500" />
  if (trend === "flat") return <ArrowRight className="size-3.5 text-muted-foreground" />
  return <Minus className="size-3.5 text-muted-foreground/50" />
}

export function StatCard({
  label,
  value,
  tone,
}: {
  label: string
  value: React.ReactNode
  tone?: "ok" | "fail" | "info"
}) {
  const toneCls =
    tone === "fail" ? "text-red-500" : tone === "ok" ? "text-emerald-500" : ""
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div className={`mt-1 text-2xl font-semibold tabular-nums ${toneCls}`}>{value}</div>
      </CardContent>
    </Card>
  )
}

export function scoreColor(score: number, total: number): string {
  if (total === 0) return "text-muted-foreground"
  if (score >= 90) return "text-emerald-500"
  if (score >= 70) return "text-amber-500"
  return "text-red-500"
}
