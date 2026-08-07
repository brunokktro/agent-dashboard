import { useMemo, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Play, Search, SquareTerminal } from "lucide-react"
import { toast } from "sonner"
import { api, relativeTime } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { StatusBadge, TrendIcon, scoreColor } from "@/components/shared"

type Facet = "all" | "running" | "scheduled" | "chat"

export default function AgentsPage() {
  const { data } = useQuery({ queryKey: ["overview"], queryFn: api.overview })
  const [search, setSearch] = useState("")
  const [facet, setFacet] = useState<Facet>("all")

  const trigger = useMutation({
    mutationFn: (name: string) => api.triggerAgent(name),
    onSuccess: (_d, name) => toast.success(`Triggered ${name}`),
    onError: (e) => toast.error(String(e)),
  })

  const agents = useMemo(() => {
    let list = data?.agents ?? []
    const q = search.trim().toLowerCase()
    if (q)
      list = list.filter(
        (a) => a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q),
      )
    if (facet === "running") list = list.filter((a) => a.is_running)
    if (facet === "scheduled") list = list.filter((a) => a.job)
    if (facet === "chat") list = list.filter((a) => a.has_config)
    return list
  }, [data, search, facet])

  if (!data) return null

  const chip = (label: string, f: Facet, count: number) => (
    <button
      onClick={() => setFacet(facet === f ? "all" : f)}
      className={`rounded-full border px-3 py-1 text-xs transition-colors ${
        facet === f ? "border-primary bg-secondary font-medium" : "hover:bg-muted"
      }`}
    >
      {label} <span className="tabular-nums text-muted-foreground">{count}</span>
    </button>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input placeholder="Search agents…" value={search}
            onChange={(e) => setSearch(e.target.value)} className="pl-8" />
        </div>
        {chip("All", "all", data.agents.length)}
        {chip("Running", "running", data.agents.filter((a) => a.is_running).length)}
        {chip("Scheduled", "scheduled", data.agents.filter((a) => a.job).length)}
        {chip("Chat-ready", "chat", data.agents.filter((a) => a.has_config).length)}
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {agents.map((a) => (
          <Card
            key={a.name}
            className={a.is_running ? "border-blue-500/50 shadow-[0_0_12px_-3px_rgb(59_130_246/0.5)]" : ""}
          >
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-2">
                <Link to={`/agent/${a.name}`} className="font-medium hover:underline">
                  {a.name}
                </Link>
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
                  {a.job && <Badge variant="outline" className="text-[10px]">scheduled</Badge>}
                </div>
                <div className="flex items-center">
                  {a.has_config && (
                    <Button asChild size="sm" variant="ghost" className="h-6 px-2" title="Open terminal">
                      <Link to={`/agent/${a.name}?terminal=1`}><SquareTerminal className="size-3.5" /></Link>
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" className="h-6 px-2"
                    onClick={() => trigger.mutate(a.name)}
                    disabled={trigger.isPending || a.is_running} title="Run now">
                    <Play className="size-3.5" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {agents.length === 0 && (
          <div className="col-span-full py-12 text-center text-sm text-muted-foreground">
            No agents match
          </div>
        )}
      </div>
    </div>
  )
}
