import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { GitBranch, Plus, Radio, SquareTerminal, X } from "lucide-react"
import { api } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import TerminalPane from "@/components/TerminalPane"
import PipeMode from "@/components/PipeMode"

interface Session {
  id: string
  agent: string | null // null = plain shell
}

const STORE_KEY = "console-sessions"
const loadSessions = (): Session[] => {
  try { return JSON.parse(sessionStorage.getItem(STORE_KEY) ?? "[]") } catch { return [] }
}

export default function ConsolePage() {
  const { data } = useQuery({ queryKey: ["overview"], queryFn: api.overview })
  const [sessions, setSessionsRaw] = useState<Session[]>(loadSessions)
  const setSessions = (s: Session[]) => {
    setSessionsRaw(s)
    sessionStorage.setItem(STORE_KEY, JSON.stringify(s))
  }
  const [pick, setPick] = useState<string>("shell")
  const [broadcast, setBroadcast] = useState("")
  const [showPipe, setShowPipe] = useState(() => new URLSearchParams(location.search).has("pipe"))

  // only agents with a kiro-cli JSON config can be chatted with
  const agents = (data?.agents ?? []).filter((a) => a.has_config).map((a) => a.name).sort()

  // ?demo=N opens N plain shells (used for docs screenshots)
  useEffect(() => {
    const n = Number(new URLSearchParams(location.search).get("demo") || 0)
    if (n > 0 && sessions.length === 0)
      setSessions(Array.from({ length: Math.min(n, 6) }, (_, i) => ({
        id: `demo-${Date.now()}-${i}`, agent: null,
      })))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // drop saved sessions pointing at agents that no longer exist / lost config
  useEffect(() => {
    if (!data) return
    const valid = sessions.filter((s) => !s.agent || agents.includes(s.agent))
    if (valid.length !== sessions.length) setSessions(valid)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  const add = () => {
    if (sessions.length >= 6) return
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    setSessions([...sessions, { id, agent: pick === "shell" ? null : pick }])
  }
  const close = (id: string) => {
    window.dispatchEvent(new CustomEvent("console-kill", { detail: id }))
    setSessions(sessions.filter((s) => s.id !== id))
  }

  const sendBroadcast = () => {
    if (!broadcast.trim()) return
    // each TerminalPane exposes its ws via a custom event bus (simplest: DOM event)
    window.dispatchEvent(new CustomEvent("console-broadcast", { detail: broadcast }))
    setBroadcast("")
  }

  const cols = sessions.length <= 1 ? 1 : sessions.length <= 4 ? 2 : 3

  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col gap-2">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <Select value={pick} onValueChange={setPick}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="shell">Plain shell</SelectItem>
            {agents.map((a) => (
              <SelectItem key={a} value={a}>{a}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button onClick={add} disabled={sessions.length >= 6}>
          <Plus className="size-4" /> Open session
        </Button>
        <Badge variant="secondary" className="tabular-nums">{sessions.length}/6</Badge>
        <Button variant={showPipe ? "secondary" : "outline"} onClick={() => setShowPipe(!showPipe)}>
          <GitBranch className="size-4" /> Pipe mode
        </Button>
        <div className="flex-1" />
        {sessions.length > 1 && (
          <div className="flex w-96 items-center gap-2">
            <Radio className="size-4 shrink-0 text-blue-500" />
            <Input
              placeholder="Broadcast to all sessions… (Enter)"
              value={broadcast}
              onChange={(e) => setBroadcast(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendBroadcast()}
              className="h-9"
            />
          </div>
        )}
      </div>

      {showPipe && <PipeMode agents={agents} />}

      {/* Grid */}
      {sessions.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-dashed text-muted-foreground">
          <SquareTerminal className="size-10" />
          <p className="text-sm">Open up to 6 simultaneous sessions - plain shell or straight into an agent chat.</p>
          <Button onClick={add}><Plus className="size-4" /> Open first session</Button>
        </div>
      ) : (
        <div className={`grid min-h-0 flex-1 gap-3 ${cols === 1 ? "grid-cols-1" : cols === 2 ? "grid-cols-2" : "grid-cols-3"}`}>
          {sessions.map((s) => (
            <div key={s.id} className="flex min-h-0 flex-col overflow-hidden rounded-xl border">
              <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5">
                <SquareTerminal className="size-3.5 text-muted-foreground" />
                <span className="text-xs font-medium">{s.agent ?? "shell"}</span>
                <Button size="sm" variant="ghost" className="ml-auto h-5 w-5 p-0"
                  onClick={() => close(s.id)}>
                  <X className="size-3" />
                </Button>
              </div>
              <div className="min-h-0 flex-1">
                <TerminalPane
                  fill
                  broadcastChannel
                  sessionId={s.id}
                  initialCommand={s.agent ? `kiro-cli chat --agent ${s.agent} --trust-all-tools` : undefined}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
