import { useEffect, useMemo, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { toast } from "sonner"
import {
  Check, CheckCircle2, ChevronDown, ChevronUp, ClipboardList, Copy, Loader,
  MessageSquareText, Search, Trash2, TriangleAlert, X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"

interface Item {
  file: string
  title: string
  autonomy: string
  agent: string
  priority: string
  created: string
  state?: string
}

const AUTONOMY_TONE: Record<string, string> = {
  autonomous: "bg-emerald-500/15 text-emerald-600",
  review: "bg-amber-500/15 text-amber-600",
  blocked: "bg-red-500/15 text-red-600",
}

function ItemCard({ it, onOpen, drag }: {
  it: Item
  onOpen: () => void
  drag?: {
    onDragStart: () => void
    onDragOver: (e: React.DragEvent) => void
    onDrop: () => void
    onDragEnd: () => void
    dragging: boolean
  }
}) {
  return (
    <button
      onClick={onOpen}
      draggable={!!drag}
      onDragStart={drag?.onDragStart}
      onDragOver={drag?.onDragOver}
      onDrop={drag?.onDrop}
      onDragEnd={drag?.onDragEnd}
      className={`w-full rounded-lg border bg-background p-3 text-left shadow-sm transition-all hover:border-foreground/25 hover:shadow ${
        drag ? "cursor-grab active:cursor-grabbing" : ""
      } ${drag?.dragging ? "opacity-40" : ""}`}
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

/** Split a markdown document into ## sections for the side TOC (variant B).
 *  The leading `# title` is dropped - the modal header already shows it. */
function splitSections(md: string): { heading: string; body: string }[] {
  const src = md.replace(/^\s*#\s+[^\n]+\n/, "")
  const out: { heading: string; body: string }[] = []
  let heading = "Overview"
  let buf: string[] = []
  for (const line of src.split("\n")) {
    const m = /^##\s+(.+?)\s*$/.exec(line)
    if (m) {
      if (buf.join("").trim()) out.push({ heading, body: buf.join("\n") })
      heading = m[1]
      buf = []
    } else buf.push(line)
  }
  out.push({ heading, body: buf.join("\n") })
  return out
}

const PROSE =
  `prose prose-sm dark:prose-invert max-w-none
   prose-headings:mt-5 prose-headings:mb-2 prose-h1:text-lg prose-h2:text-base
   prose-p:my-2 prose-li:my-0.5 prose-pre:my-2 prose-pre:rounded-lg
   prose-pre:bg-zinc-950 prose-pre:p-3 prose-pre:text-[11px] prose-pre:overflow-x-auto
   prose-code:before:content-none prose-code:after:content-none
   prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:text-xs
   [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-inherit`

function ItemReader({ item, bucket, siblings, onNavigate, onClose }: {
  item: Item
  bucket: string
  siblings: Item[]
  onNavigate: (item: Item) => void
  onClose: () => void
}) {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ["backlog-item", bucket, item.file],
    queryFn: () =>
      fetch(`/api/backlog/item?bucket=${bucket}&file=${encodeURIComponent(item.file)}`)
        .then((r) => r.json()),
  })
  const [active, setActive] = useState(0)
  const [discussing, setDiscussing] = useState(false)
  const [feedback, setFeedback] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)
  const sections = useMemo(() => (data?.content ? splitSections(data.content) : []), [data])
  const idx = siblings.findIndex((s) => s.file === item.file)
  const isNote = bucket === "review_notes"

  const step = (d: number) => {
    if (siblings.length < 2) return
    onNavigate(siblings[(idx + d + siblings.length) % siblings.length])
    setActive(0)
    setDiscussing(false)
    scrollRef.current?.scrollTo({ top: 0 })
  }

  // keyboard: j/k or arrows navigate between items (Esc close comes from Dialog)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "TEXTAREA") return
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); step(1) }
      if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); step(-1) }
    }
    window.addEventListener("keydown", h)
    return () => window.removeEventListener("keydown", h)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, siblings])

  // scroll-spy: highlight the TOC entry of the section under the reading line;
  // at the bottom the last section wins even if too short to reach the top
  const onScroll = () => {
    const sc = scrollRef.current
    if (!sc) return
    const marks = sc.querySelectorAll<HTMLElement>("[data-sec]")
    if (sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 4) {
      setActive(marks.length - 1)
      return
    }
    let cur = 0
    const top = sc.getBoundingClientRect().top
    marks.forEach((m, i) => { if (m.getBoundingClientRect().top - top < 90) cur = i })
    setActive(cur)
  }

  const jump = (i: number) => {
    scrollRef.current?.querySelectorAll<HTMLElement>("[data-sec]")[i]
      ?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  const act = async (path: string, body: object, done: string) => {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: item.file, ...body }),
    })
    if (!r.ok) { toast.error(`${path}: HTTP ${r.status}`); return }
    toast.success(done)
    qc.invalidateQueries({ queryKey: ["backlog"] })
    onClose()
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="flex h-[88vh] max-w-5xl flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="border-b px-5 pb-3 pt-4">
          <div className="flex items-start gap-2">
            <DialogTitle className="flex-1 pr-2 leading-snug">{item.title}</DialogTitle>
            {siblings.length > 1 && (
              <div className="mr-6 flex shrink-0 items-center gap-1">
                <Button size="sm" variant="outline" className="h-7 w-7 p-0"
                  title="Previous (K)" onClick={() => step(-1)}>
                  <ChevronUp className="size-4" />
                </Button>
                <Button size="sm" variant="outline" className="h-7 w-7 p-0"
                  title="Next (J)" onClick={() => step(1)}>
                  <ChevronDown className="size-4" />
                </Button>
                <span className="px-1 text-[11px] tabular-nums text-muted-foreground">
                  {idx + 1}/{siblings.length}
                </span>
              </div>
            )}
          </div>
          <DialogDescription className="flex flex-wrap items-center gap-2">
            {item.autonomy && (
              <Badge variant="secondary" className={`border-0 ${AUTONOMY_TONE[item.autonomy] ?? ""}`}>
                {item.autonomy}
              </Badge>
            )}
            {item.agent && <Badge variant="outline">{item.agent}</Badge>}
            {item.priority && <Badge variant="outline">{item.priority}</Badge>}
            {item.created && <span className="text-xs">{item.created}</span>}
            <button
              className="inline-flex items-center gap-1 rounded-md border bg-muted/60 px-1.5 py-0.5
                text-[10px] text-muted-foreground transition-colors hover:text-foreground"
              title="Copy file path"
              onClick={() => { navigator.clipboard?.writeText(item.file); toast.success("Path copied") }}
            >
              <Copy className="size-3" /> {item.file}
            </button>
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1">
          {/* side TOC (variant B) */}
          {sections.length > 1 && (
            <nav className="w-52 shrink-0 overflow-y-auto border-r bg-muted/30 px-2 py-3">
              <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                In this note
              </p>
              {sections.map((s, i) => (
                <button key={i} onClick={() => jump(i)}
                  className={`block w-full rounded-md border-l-2 px-2.5 py-1.5 text-left text-xs transition-colors ${
                    i === active
                      ? "border-foreground bg-background font-medium shadow-sm"
                      : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}>
                  {s.heading}
                </button>
              ))}
            </nav>
          )}

          {/* document */}
          <div ref={scrollRef} onScroll={onScroll}
            className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-5 py-4">
            {!data ? (
              <div className="space-y-2 py-2">
                <Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" /><Skeleton className="h-24 w-full" />
              </div>
            ) : (
              sections.map((s, i) => (
                <section key={i} data-sec>
                  {(i > 0 || s.heading !== "Overview") && (
                    <h2 className="mb-2 mt-5 text-sm font-semibold first:mt-0">{s.heading}</h2>
                  )}
                  <article className={PROSE}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.body}</ReactMarkdown>
                  </article>
                </section>
              ))
            )}
          </div>
        </div>

        {/* decision bar */}
        <div className="flex items-center gap-2 border-t bg-muted/30 px-4 py-3">
          {isNote && !discussing && (
            <>
              <Button size="sm" className="bg-emerald-600 text-white hover:bg-emerald-600/90"
                onClick={() => act("/api/backlog/review-note/approve", {},
                  "Approved - will apply on next meta-agent run")}>
                <Check className="size-4" /> Approve
              </Button>
              <Button size="sm" variant="outline"
                className="border-amber-300 bg-amber-500/10 text-amber-700 hover:bg-amber-500/20"
                onClick={() => setDiscussing(true)}>
                <MessageSquareText className="size-4" /> Discuss
              </Button>
              <Button size="sm" variant="outline"
                className="border-red-200 text-red-600 hover:bg-red-500/10"
                onClick={() => act("/api/backlog/review-note/reject", {},
                  "Rejected - agent will not regenerate")}>
                <X className="size-4" /> Reject
              </Button>
            </>
          )}
          {isNote && discussing && (
            <div className="flex flex-1 items-end gap-2">
              <Textarea autoFocus rows={2} value={feedback}
                placeholder="Feedback for the agent - the note regenerates on the next run..."
                onChange={(e) => setFeedback(e.target.value)}
                className="min-h-0 flex-1 resize-none text-sm" />
              <Button size="sm" disabled={!feedback.trim()}
                onClick={() => act("/api/backlog/review-note/discuss", { feedback },
                  "Feedback saved - will regenerate on next run")}>
                Send
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setDiscussing(false)}>Cancel</Button>
            </div>
          )}
          {!isNote && bucket !== "done" && item.autonomy && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              autonomy:
              {["auto", "review", "blocked"].map((v) => (
                <button key={v}
                  onClick={() => act("/api/backlog/autonomy", { autonomy: v }, `Autonomy set to ${v}`)}
                  className={`rounded-full border px-2.5 py-0.5 capitalize transition-colors ${
                    (item.autonomy === "autonomous" ? "auto" : item.autonomy) === v
                      ? "border-foreground font-medium text-foreground"
                      : "hover:bg-muted"
                  }`}>
                  {v}
                </button>
              ))}
            </div>
          )}
          <div className="flex-1" />
          {!discussing && bucket !== "review_notes" && (
            <Button size="sm" variant="ghost"
              className="text-muted-foreground hover:text-red-600"
              onClick={() => act("/api/backlog/delete", { bucket },
                "Moved to backlog/deleted/ (reversible)")}>
              <Trash2 className="size-4" /> Delete
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default function BacklogPage() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ["backlog"],
    queryFn: () => fetch("/api/backlog").then((r) => r.json()),
  })
  const [search, setSearch] = useState("")
  const [facet, setFacet] = useState<string>("")
  const [open, setOpen] = useState<{ item: Item; bucket: string } | null>(null)
  const dragFile = useRef<string | null>(null)
  const [dragging, setDragging] = useState<string | null>(null)

  // Drop `moved` right before `target` inside the FULL active list (not the
  // filtered view), then persist the whole order and refetch.
  const reorder = async (target: string) => {
    const moved = dragFile.current
    if (!moved || moved === target || !data) return
    const files = (data.active as Item[]).map((i) => i.file)
    const from = files.indexOf(moved)
    if (from < 0) return
    files.splice(from, 1)
    const to = files.indexOf(target)
    files.splice(to < 0 ? files.length : to, 0, moved)
    const r = await fetch("/api/backlog/reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    })
    if (!r.ok) { toast.error(`reorder: HTTP ${r.status}`); return }
    qc.invalidateQueries({ queryKey: ["backlog"] })
  }

  const dragProps = (file: string) => ({
    onDragStart: () => { dragFile.current = file; setDragging(file) },
    onDragOver: (e: React.DragEvent) => e.preventDefault(),
    onDrop: () => reorder(file),
    onDragEnd: () => { dragFile.current = null; setDragging(null) },
    dragging: dragging === file,
  })

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
    { key: "running", label: "Running", icon: Loader, items: filter((data.running ?? []) as Item[]) },
    { key: "failed", label: "Failed", icon: TriangleAlert, items: filter((data.failed ?? []) as Item[]) },
    { key: "review_notes", label: "Review notes", icon: MessageSquareText, items: filter((data.review_notes ?? []) as Item[]) },
    { key: "done", label: "Done", icon: CheckCircle2, items: filter((data.done as Item[])).slice(0, 40) },
  ].filter((c) => c.items.length > 0 || ["active", "review_notes", "done"].includes(c.key))

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

      <div className="grid min-h-0 flex-1 gap-4" style={{ gridTemplateColumns: `repeat(${cols.length}, minmax(0, 1fr))` }}>
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
                  <ItemCard key={it.file} it={it}
                    onOpen={() => setOpen({ item: it, bucket: key })}
                    drag={key === "active" ? dragProps(it.file) : undefined} />
                ))}
                {items.length === 0 && (
                  <div className="py-10 text-center text-xs text-muted-foreground">Empty</div>
                )}
              </div>
            </ScrollArea>
          </div>
        ))}
      </div>

      {open && (
        <ItemReader
          item={open.item}
          bucket={open.bucket}
          siblings={cols.find((c) => c.key === open.bucket)?.items ?? [open.item]}
          onNavigate={(item) => setOpen({ item, bucket: open.bucket })}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}
