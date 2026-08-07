import { useEffect, useRef, useState } from "react"
import { ArrowRight, GitBranch, Loader2, Plus, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { StatusBadge } from "@/components/shared"

interface Step { agent: string; status: string; output: string; received?: string }

export default function PipeMode({ agents: agentsProp }: { agents: string[] }) {
  const agents = [...agentsProp].sort()
  const [chain, setChain] = useState<string[]>(["", ""])
  const [prompt, setPrompt] = useState("")
  const [steps, setSteps] = useState<Step[] | null>(null)
  const [jobStatus, setJobStatus] = useState<string | null>(null)
  const [fullView, setFullView] = useState<Step | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = (id: string) => {
    if (timer.current) clearInterval(timer.current)
    timer.current = setInterval(async () => {
      const r = await fetch(`/api/pipe/${id}`)
      if (!r.ok) { if (timer.current) clearInterval(timer.current); localStorage.removeItem("pipe-job"); return }
      const s = await r.json()
      setSteps(s.steps); setJobStatus(s.status)
      if (s.status !== "running") {
        if (timer.current) clearInterval(timer.current)
        localStorage.removeItem("pipe-job")
        if (s.status === "lost") toast.error("Backend restarted - the pipe job was lost. Run it again.")
      }
    }, 2000)
  }

  // resume a job that kept running server-side across refresh/navigation
  useEffect(() => {
    const saved = localStorage.getItem("pipe-job")
    if (saved) { setJobStatus("running"); poll(saved) }
    return () => { if (timer.current) clearInterval(timer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const run = async () => {
    const list = chain.filter(Boolean)
    if (!prompt.trim() || list.length === 0) return
    const r = await fetch("/api/pipe/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, agents: list }),
    })
    if (!r.ok) { toast.error(`pipe: HTTP ${r.status}`); return }
    const { id } = await r.json()
    localStorage.setItem("pipe-job", id)
    setJobStatus("running")
    setSteps(list.map((a) => ({ agent: a, status: "pending", output: "" })))
    poll(id)
  }

  return (
    <div className="rounded-xl border p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium">
        <GitBranch className="size-4 text-violet-500" /> Pipe mode
        <span className="text-xs font-normal text-muted-foreground">
          - the output of each agent becomes the prompt of the next
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {chain.map((v, i) => (
          <div key={i} className="flex items-center gap-2">
            {i > 0 && <ArrowRight className="size-4 text-muted-foreground" />}
            <Select value={v} onValueChange={(nv) => setChain(chain.map((c, j) => (j === i ? nv : c)))}>
              <SelectTrigger className="w-48"><SelectValue placeholder={`Agent ${i + 1}`} /></SelectTrigger>
              <SelectContent>
                {agents.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
              </SelectContent>
            </Select>
            {chain.length > 2 && (
              <button onClick={() => setChain(chain.filter((_, j) => j !== i))}
                className="text-muted-foreground hover:text-foreground">
                <X className="size-3.5" />
              </button>
            )}
          </div>
        ))}
        {chain.length < 4 && (
          <Button size="sm" variant="ghost" onClick={() => setChain([...chain, ""])}>
            <Plus className="size-3.5" />
          </Button>
        )}
      </div>

      <Textarea rows={2} placeholder="What should the chain work on?"
        value={prompt} onChange={(e) => setPrompt(e.target.value)} className="mt-3" />
      <Button className="mt-2" onClick={run}
        disabled={jobStatus === "running" || !prompt.trim() || chain.filter(Boolean).length === 0}>
        {jobStatus === "running" ? <Loader2 className="size-4 animate-spin" /> : <GitBranch className="size-4" />}
        Run chain
      </Button>

      <Dialog open={!!fullView} onOpenChange={(o) => !o && setFullView(null)}>
        <DialogContent className="flex h-[85vh] max-w-4xl flex-col overflow-hidden">
          <DialogHeader><DialogTitle>{fullView?.agent} - full output</DialogTitle></DialogHeader>
          <pre className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap break-words rounded bg-zinc-950 p-3 text-[11px] leading-relaxed text-zinc-300">
            {fullView?.output}
          </pre>
        </DialogContent>
      </Dialog>

      {steps && (
        <div className="mt-5">
          {/* Flow visualization */}
          <div className="flex items-center justify-center gap-0 overflow-x-auto py-4">
            {/* prompt node */}
            <div className="flex shrink-0 flex-col items-center gap-1">
              <div className="flex size-12 items-center justify-center rounded-full border-2 border-muted-foreground/30 bg-muted text-lg">
                💬
              </div>
              <span className="text-[10px] text-muted-foreground">prompt</span>
            </div>
            {steps.map((s, i) => (
              <div key={i} className="flex items-center">
                {/* animated edge */}
                <div className="relative mx-1 h-0.5 w-16 overflow-hidden rounded bg-muted">
                  {(s.status === "running" || s.status === "done") && (
                    <div
                      className={`absolute inset-0 ${
                        s.status === "running"
                          ? "animate-[flow_1.2s_linear_infinite] bg-gradient-to-r from-transparent via-violet-500 to-transparent"
                          : "bg-emerald-500/60"
                      }`}
                      style={{ backgroundSize: "50% 100%" }}
                    />
                  )}
                </div>
                {/* agent node */}
                <div className="flex shrink-0 flex-col items-center gap-1">
                  <div
                    className={`flex size-14 items-center justify-center rounded-2xl border-2 text-xs font-semibold transition-all duration-500 ${
                      s.status === "running"
                        ? "border-violet-500 bg-violet-500/10 shadow-[0_0_24px_-4px_rgb(139_92_246/0.9)]"
                        : s.status === "done"
                          ? "border-emerald-500 bg-emerald-500/10"
                          : s.status === "failed"
                            ? "border-red-500 bg-red-500/10"
                            : "border-muted-foreground/25 opacity-50"
                    }`}
                  >
                    {s.status === "running" ? (
                      <Loader2 className="size-5 animate-spin text-violet-500" />
                    ) : s.status === "done" ? (
                      <span className="text-emerald-500">✓</span>
                    ) : s.status === "failed" ? (
                      <span className="text-red-500">✗</span>
                    ) : (
                      i + 1
                    )}
                  </div>
                  <span className="max-w-24 truncate text-[10px] font-medium">{s.agent}</span>
                  {s.status === "running" && <ElapsedTimer />}
                </div>
              </div>
            ))}
          </div>
          <style>{`@keyframes flow { from { transform: translateX(-100%);} to { transform: translateX(100%);} }`}</style>

          {/* Step outputs */}
          <div className="space-y-3">
            {steps.filter((s) => s.output || s.status !== "pending").map((s, i) => (
              <div key={i} className={`rounded-lg border p-3 transition-colors ${
                s.status === "running" ? "border-violet-500/40" : ""
              }`}>
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">{s.agent}</span>
                  <StatusBadge status={s.status === "done" ? "success" : s.status} />
                </div>
                {s.received && (
                  <details className="mt-2 text-[11px] text-muted-foreground">
                    <summary className="cursor-pointer">received from previous agent</summary>
                    <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-muted/60 p-2">{s.received}</pre>
                  </details>
                )}
                {s.status === "running" && !s.output && (
                  <div className="mt-2 space-y-1.5">
                    <div className="h-2 w-3/4 animate-pulse rounded bg-muted" />
                    <div className="h-2 w-1/2 animate-pulse rounded bg-muted" />
                  </div>
                )}
                {s.output && (
                  <>
                    <pre className="mt-2 overflow-hidden whitespace-pre-wrap break-words rounded bg-muted p-2 text-[11px] leading-relaxed">
                      {s.output.split("\n").slice(-15).join("\n")}
                    </pre>
                    <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>{s.status === "running" ? "live tail - last 15 lines" : "last 15 lines"}</span>
                      <button className="text-blue-500 hover:underline" onClick={() => setFullView(s)}>
                        View full output ({s.output.split("\n").length} lines)
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ElapsedTimer() {
  const [sec, setSec] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setSec((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [])
  return (
    <span className="tabular-nums text-[10px] text-violet-500">
      {sec < 60 ? `${sec}s` : `${Math.floor(sec / 60)}m${sec % 60}s`}
    </span>
  )
}
