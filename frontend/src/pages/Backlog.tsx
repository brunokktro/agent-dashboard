import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { CheckCircle2, ClipboardList, MessageSquareText, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"

interface Item {
  file: string
  title: string
  autonomy: string
  agent: string
  priority: string
  created: string
}

const AUTONOMY_TONE: Record<string, string> = {
  autonomous: "bg-emerald-500/15 text-emerald-600",
  review: "bg-amber-500/15 text-amber-600",
  blocked: "bg-red-500/15 text-red-600",
}

function ItemCard({ it, onOpen }: { it: Item; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="w-full rounded-lg border bg-background p-3 text-left shadow-sm transition-all hover:border-foreground/25 hover:shadow"
    >
      <div className="text-sm font-medium leading-snug">{it.title}</div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
        {it.autonomy && (
          <Badge variant="secondary" className={`border-0 ${AUTONOMY_TONE[it.autonomy] ?? ""}`}>
            {it.autonomy}
          </Badge>
        )}
        {it.agent && <span>{it.agent}</span>}
        {it.priority && <span>· {it.priority}</span>}
        {it.created && <span>· {it.created}</span>}
      </div>
    </button>
  )
}

function ItemReader({ item, bucket, onClose }: { item: Item; bucket: string; onClose: () => void }) {
  const { data } = useQuery({
    queryKey: ["backlog-item", bucket, item.file],
    queryFn: () =>
      fetch(`/api/backlog/item?bucket=${bucket}&file=${encodeURIComponent(item.file)}`)
        .then((r) => r.json()),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="flex h-[88vh] max-w-5xl flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle className="pr-6 leading-snug">{item.title}</DialogTitle>
          <DialogDescription className="flex flex-wrap items-center gap-2">
            {item.autonomy && (
              <Badge variant="secondary" className={`border-0 ${AUTONOMY_TONE[item.autonomy] ?? ""}`}>
                {item.autonomy}
              </Badge>
            )}
            {item.agent && <Badge variant="outline">{item.agent}</Badge>}
            {item.priority && <Badge variant="outline">{item.priority}</Badge>}
            {item.created && <span className="text-xs">{item.created}</span>}
            <code className="text-[10px] text-muted-foreground">{item.file}</code>
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 overflow-y-auto pr-2">
          {!data ? (
            <div className="space-y-2 py-2">
              <Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" /><Skeleton className="h-24 w-full" />
            </div>
          ) : (
            <article className="prose prose-sm dark:prose-invert max-w-none
              prose-headings:mt-5 prose-headings:mb-2 prose-h1:text-lg prose-h2:text-base
              prose-p:my-2 prose-li:my-0.5 prose-pre:my-2 prose-pre:rounded-lg
              prose-pre:bg-zinc-950 prose-pre:p-3 prose-pre:text-[11px]
              prose-code:before:content-none prose-code:after:content-none
              prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:text-xs">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.content}</ReactMarkdown>
            </article>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default function BacklogPage() {
  const { data } = useQuery({
    queryKey: ["backlog"],
    queryFn: () => fetch("/api/backlog").then((r) => r.json()),
  })
  const [search, setSearch] = useState("")
  const [facet, setFacet] = useState<string>("")
  const [open, setOpen] = useState<{ item: Item; bucket: string } | null>(null)

  const filter = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (items: Item[]) =>
      items.filter(
        (i) =>
          (!q || i.title.toLowerCase().includes(q) || i.agent.toLowerCase().includes(q)) &&
          (!facet || i.autonomy === facet),
      )
  }, [search, facet])

  if (!data) return null

  const cols = [
    { key: "active", label: "Active backlog", icon: ClipboardList, items: filter(data.active as Item[]) },
    { key: "review_notes", label: "Review notes", icon: MessageSquareText, items: filter((data.review_notes ?? []) as Item[]) },
    { key: "done", label: "Done", icon: CheckCircle2, items: filter((data.done as Item[])).slice(0, 40) },
  ]

  const chip = (label: string) => (
    <button key={label}
      onClick={() => setFacet(facet === label ? "" : label)}
      className={`rounded-full border px-3 py-1 text-xs capitalize transition-colors ${
        facet === label ? `border-primary font-medium ${AUTONOMY_TONE[label]}` : "hover:bg-muted"
      }`}
    >
      {label}
    </button>
  )

  return (
    <div className="flex h-[calc(100vh-11rem)] flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input placeholder="Search backlog…" value={search}
            onChange={(e) => setSearch(e.target.value)} className="pl-8" />
        </div>
        {["autonomous", "review", "blocked"].map(chip)}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-3 gap-4">
        {cols.map(({ key, label, icon: Icon, items }) => (
          <div key={key} className="flex min-h-0 flex-col rounded-xl border bg-muted/30">
            <div className="flex items-center gap-2 border-b px-3 py-2.5">
              <Icon className="size-4 text-muted-foreground" />
              <span className="text-sm font-medium">{label}</span>
              <Badge variant="secondary" className="ml-auto tabular-nums">{items.length}</Badge>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="space-y-2 p-2">
                {items.map((it) => (
                  <ItemCard key={it.file} it={it} onOpen={() => setOpen({ item: it, bucket: key })} />
                ))}
                {items.length === 0 && (
                  <div className="py-10 text-center text-xs text-muted-foreground">Empty</div>
                )}
              </div>
            </ScrollArea>
          </div>
        ))}
      </div>

      {open && <ItemReader item={open.item} bucket={open.bucket} onClose={() => setOpen(null)} />}
    </div>
  )
}
