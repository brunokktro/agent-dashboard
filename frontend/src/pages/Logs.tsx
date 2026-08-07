import { useEffect, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { FileText, Pause, Play, Search } from "lucide-react"
import { api, relativeTime } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"

export default function LogsPage() {
  const { data } = useQuery({ queryKey: ["logs"], queryFn: api.logs })
  const [params, setParams] = useSearchParams()
  const [selected, setSelectedRaw] = useState<string | null>(params.get("file"))
  const setSelected = (name: string | null) => {
    setSelectedRaw(name)
    setParams(name ? { file: name } : {}, { replace: true })
  }
  const [filter, setFilter] = useState("")
  const [following, setFollowing] = useState(true)
  const [lines, setLines] = useState<string[]>([])
  const viewRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  // SSE live tail
  useEffect(() => {
    esRef.current?.close()
    setLines([])
    if (!selected) return
    const es = new EventSource(`/logs/stream/${selected}`)
    es.onmessage = (e) => setLines((prev) => [...prev.slice(-2000), e.data])
    esRef.current = es
    return () => es.close()
  }, [selected])

  // auto-scroll when following
  useEffect(() => {
    if (following && viewRef.current)
      viewRef.current.scrollTop = viewRef.current.scrollHeight
  }, [lines, following])

  const files = (data?.files ?? []).filter(
    (f) => !filter || f.name.toLowerCase().includes(filter.toLowerCase()),
  )

  return (
    <div className="grid h-[calc(100vh-7.5rem)] grid-cols-[300px_1fr] gap-4">
      {/* File list */}
      <div className="flex min-h-0 flex-col rounded-xl border">
        <div className="border-b p-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input placeholder="Filter files…" value={filter}
              onChange={(e) => setFilter(e.target.value)} className="h-9 pl-8" />
          </div>
        </div>
        <ScrollArea className="min-h-0 flex-1">
          <div className="p-1.5">
            {files.map((f) => (
              <button
                key={f.name}
                onClick={() => setSelected(f.name)}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors ${
                  selected === f.name ? "bg-secondary font-medium" : "hover:bg-muted"
                }`}
              >
                <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <span className="shrink-0 text-[10px] text-muted-foreground">
                  {relativeTime(f.mtime)}
                </span>
              </button>
            ))}
            {files.length === 0 && (
              <div className="py-8 text-center text-xs text-muted-foreground">No log files</div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Viewer */}
      <div className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-zinc-950">
        <div className="flex items-center gap-2 border-b border-zinc-800 px-3 py-2">
          <span className="truncate font-mono text-xs text-zinc-300">
            {selected ?? "Select a log file"}
          </span>
          {selected && (
            <>
              <Badge variant="secondary" className="bg-zinc-800 text-zinc-300">
                live · {lines.length} lines
              </Badge>
              <div className="flex-1" />
              <Button size="sm" variant="ghost"
                className="h-6 text-xs text-zinc-400 hover:text-zinc-100"
                onClick={() => setFollowing(!following)}>
                {following ? <><Pause className="size-3" /> Pause follow</> : <><Play className="size-3" /> Follow</>}
              </Button>
            </>
          )}
        </div>
        <div ref={viewRef} className="min-h-0 flex-1 overflow-auto p-3 font-mono text-[11px] leading-relaxed text-zinc-300">
          {lines.map((l, i) => (
            <div key={i} className={
              /error|fail|exception|traceback/i.test(l) ? "text-red-400"
              : /warn/i.test(l) ? "text-amber-400"
              : /success|ok|done|✓/i.test(l) ? "text-emerald-400" : ""
            }>
              {l || "\u00A0"}
            </div>
          ))}
          {selected && lines.length === 0 && (
            <div className="text-zinc-600">Waiting for content…</div>
          )}
        </div>
      </div>
    </div>
  )
}
