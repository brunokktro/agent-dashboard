import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle, CheckCircle2, CircleDashed, Loader2, Plus, RefreshCw, RotateCcw, Search, X, XCircle,
} from "lucide-react"
import { toast } from "sonner"
import { api, relativeTime, type QueueItem } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet"
import { StatusBadge } from "@/components/shared"
import BacklogPage from "@/pages/Backlog"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

const COLUMNS = [
  { key: "running", label: "Running", icon: Loader2, accent: "text-blue-500", spin: true },
  { key: "pending", label: "Pending", icon: CircleDashed, accent: "text-amber-500" },
  { key: "failed", label: "Failed", icon: XCircle, accent: "text-red-500" },
  { key: "done", label: "Done · 24h", icon: CheckCircle2, accent: "text-emerald-500" },
] as const

export default function QueuePage() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ["queue"], queryFn: api.queue })
  const { data: overview } = useQuery({ queryKey: ["overview"], queryFn: api.overview })
  const agentNames = (overview?.agents ?? []).map((a) => a.name)
  const [priority, setPriority] = useState("medium")
  const [search, setSearch] = useState("")
  const [open, setOpen] = useState(false)
  const [agent, setAgent] = useState("")
  const [input, setInput] = useState("")
  const [selected, setSelected] = useState<QueueItem | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["queue"] })
  const retry = useMutation({
    mutationFn: api.queueRetry,
    onSuccess: () => { toast.success("Moved to pending"); invalidate() },
    onError: (e) => toast.error(String(e)),
  })
  const cancel = useMutation({
    mutationFn: api.queueCancel,
    onSuccess: () => { toast.success("Cancelled"); invalidate() },
    onError: (e) => toast.error(String(e)),
  })
  const enqueue = useMutation({
    mutationFn: () => api.enqueue(agent, input, priority),
    onSuccess: (d) => {
      toast.success(`Enqueued ${d.id}`)
      setOpen(false); setAgent(""); setInput(""); invalidate()
    },
    onError: (e) => toast.error(String(e)),
  })

  const byState = useMemo(() => {
    const q = search.trim().toLowerCase()
    const items = (data?.items ?? []).filter(
      (i) => !q || i.agent.toLowerCase().includes(q) || i.input.toLowerCase().includes(q),
    )
    const map: Record<string, QueueItem[]> = { running: [], pending: [], failed: [], done: [] }
    for (const i of items) {
      const bucket = i.status === "cancelled" ? "done" : i.status
      ;(map[bucket] ?? map.done).push(i)
    }
    return map
  }, [data, search])

  const [view, setView] = useState<"work" | "backlog">("work")

  if (!data) return null

  if (view === "backlog") {
    return (
      <div className="space-y-4">
        <BoardTabs view={view} setView={setView} />
        <BacklogPage />
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-7.5rem)] flex-col gap-4">
      <BoardTabs view={view} setView={setView} />
      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder="Filter by agent or input…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
        {data.stuck.length > 0 && (
          <Badge variant="outline" className="gap-1 border-amber-500/40 text-amber-600">
            <AlertTriangle className="size-3" /> {data.stuck.length} stuck &gt;30min
          </Badge>
        )}
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={() => invalidate()} title="Refresh">
          <RefreshCw className="size-3.5" />
        </Button>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button><Plus className="size-4" /> Enqueue</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Enqueue work item</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Agent</label>
                <Select value={agent} onValueChange={setAgent}>
                  <SelectTrigger className="w-full"><SelectValue placeholder="Pick an agent…" /></SelectTrigger>
                  <SelectContent>
                    {agentNames.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Task</label>
                <Textarea rows={4} placeholder="Describe what the agent should do…"
                  value={input} onChange={(e) => setInput(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Priority</label>
                <Select value={priority} onValueChange={setPriority}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="high">high</SelectItem>
                    <SelectItem value="medium">medium</SelectItem>
                    <SelectItem value="low">low</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                onClick={() => enqueue.mutate()}
                disabled={!agent.trim() || !input.trim() || enqueue.isPending}
                className="w-full"
              >
                Enqueue
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Board */}
      <div className="grid min-h-0 flex-1 grid-cols-4 gap-3">
        {COLUMNS.map(({ key, label, icon: Icon, accent, ...col }) => {
          const items = byState[key]
          return (
            <div key={key} className="flex min-h-0 flex-col rounded-xl border bg-muted/30">
              <div className="flex items-center gap-2 border-b px-3 py-2.5">
                <Icon className={`size-4 ${accent} ${"spin" in col && col.spin && items.length ? "animate-spin" : ""}`} />
                <span className="text-sm font-medium">{label}</span>
                <Badge variant="secondary" className="ml-auto tabular-nums">{items.length}</Badge>
              </div>
              <ScrollArea className="min-h-0 flex-1">
                <div className="space-y-2 p-2">
                  {(key === "done" ? items.slice(0, 30) : items).map((item) => (
                    <div
                      key={item.id}
                      onClick={() => setSelected(item)}
                      className={`group cursor-pointer rounded-lg border bg-background p-3 shadow-sm transition-shadow hover:shadow ${
                        key === "failed" ? "border-red-500/30" : ""
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium">{item.agent}</span>
                        <span className="shrink-0 text-[11px] text-muted-foreground">
                          {relativeTime(item.created)}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground" title={item.input}>
                        {item.input}
                      </p>
                      {item.result && key === "failed" && (
                        <p className="mt-1.5 line-clamp-2 rounded bg-red-500/10 px-2 py-1 text-[11px] text-red-600 dark:text-red-400">
                          {item.result}
                        </p>
                      )}
                      {(key === "failed" || key === "pending") && (
                        <div className="mt-2 flex justify-end opacity-0 transition-opacity group-hover:opacity-100">
                          {key === "failed" && (
                            <Button size="sm" variant="outline" className="h-6 text-xs"
                              onClick={(e) => { e.stopPropagation(); retry.mutate(item.id) }}>
                              <RotateCcw className="size-3" /> Retry
                            </Button>
                          )}
                          {key === "pending" && (
                            <Button size="sm" variant="ghost" className="h-6 text-xs text-muted-foreground"
                              onClick={(e) => { e.stopPropagation(); cancel.mutate(item.id) }}>
                              <X className="size-3" /> Cancel
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                  {items.length === 0 && (
                    <div className="py-10 text-center text-xs text-muted-foreground">Empty</div>
                  )}
                  {key === "done" && items.length > 30 && (
                    <div className="py-2 text-center text-[11px] text-muted-foreground">
                      +{items.length - 30} older items (last 24h kept on disk)
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
          )
        })}
      </div>

      {/* Item detail drawer */}
      <Sheet open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <SheetContent className="w-[440px] sm:max-w-[440px]">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  {selected.agent} <StatusBadge status={selected.status} />
                </SheetTitle>
                <SheetDescription className="font-mono text-xs">{selected.id}</SheetDescription>
              </SheetHeader>
              <div className="space-y-4 px-4 text-sm">
                <div>
                  <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">Input</div>
                  <p className="whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs">{selected.input}</p>
                </div>
                {selected.result && (
                  <div>
                    <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">Result</div>
                    <p className="whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs">{selected.result}</p>
                  </div>
                )}
                <div className="space-y-1 text-xs text-muted-foreground">
                  <div>Created: {selected.created}</div>
                  {selected.completedAt && <div>Completed: {selected.completedAt}</div>}
                  <div>Priority: {selected.priority}</div>
                </div>
                <div className="flex gap-2">
                  {selected.status === "failed" && (
                    <Button className="flex-1" onClick={() => { retry.mutate(selected.id); setSelected(null) }}>
                      <RotateCcw className="size-4" /> Retry
                    </Button>
                  )}
                  {selected.status === "pending" && (
                    <Button variant="outline" className="flex-1" onClick={() => { cancel.mutate(selected.id); setSelected(null) }}>
                      <X className="size-4" /> Cancel
                    </Button>
                  )}
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}


function BoardTabs({ view, setView }: { view: string; setView: (v: "work" | "backlog") => void }) {
  return (
    <Tabs value={view} onValueChange={(v) => setView(v as "work" | "backlog")}>
      <TabsList>
        <TabsTrigger value="work">Work items</TabsTrigger>
        <TabsTrigger value="backlog">Backlog & Review notes</TabsTrigger>
      </TabsList>
    </Tabs>
  )
}
