import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from "react-router-dom"
import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Activity, Bot, HeartPulse, ListTodo, CircleHelp, Moon, ScrollText, Settings2, SquareTerminal, Sun } from "lucide-react"
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command"
import { Toaster } from "@/components/ui/sonner"
import OverviewPage from "@/pages/Overview"
import AgentPage from "@/pages/Agent"
import AgentsPage from "@/pages/Agents"
import QueuePage from "@/pages/Queue"
import HealthPage from "@/pages/Health"
import SupervisorPage from "@/pages/Supervisor"
import LogsPage from "@/pages/Logs"
import ConsolePage from "@/pages/Console"
import HelpPage from "@/pages/Help"
import { UpdateCheck } from "@/components/UpdateCheck"

/** Any unknown path. Without this an unmatched route renders a blank page - the
 *  worst possible answer, because it is indistinguishable from a crash. Names
 *  the path so a stale bookmark or a typo is obvious. */
function NotFound() {
  const { pathname } = useLocation()
  return (
    <div className="mx-auto max-w-lg space-y-3 py-16 text-center">
      <h1 className="text-lg font-semibold">Nothing at this address</h1>
      <p className="text-sm text-muted-foreground">
        The dashboard has no page at{" "}
        <code className="rounded bg-muted px-1.5 py-0.5">{pathname}</code>.
      </p>
      <p className="text-sm text-muted-foreground">
        If you followed a bookmark, the page may have moved - the tabs above are the
        full set. The <Link className="text-blue-500 hover:underline" to="/help">Help tab</Link>{" "}
        documents every one of them.
      </p>
      <Link to="/" className="inline-block text-sm text-blue-500 hover:underline">
        Back to the Overview
      </Link>
    </div>
  )
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchInterval: 10_000, staleTime: 5_000, retry: 1 },
  },
})

const tabs = [
  { to: "/", label: "Overview", icon: Activity },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/queue", label: "Board", icon: ListTodo },
  { to: "/health", label: "Health", icon: HeartPulse },
  { to: "/supervisor", label: "Supervisor", icon: Settings2 },
  { to: "/console", label: "Console", icon: SquareTerminal },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/help", label: "Help", icon: CircleHelp },
]

function useLiveEvents() {
  const qc = useQueryClient()
  useEffect(() => {
    let ws: WebSocket | null = null
    let retry = 1000
    let closed = false
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws"
      ws = new WebSocket(`${proto}://${location.host}/ws/events`)
      ws.onopen = () => { retry = 1000 }
      ws.onmessage = (e) => {
        const ev = JSON.parse(e.data)
        if (ev.type === "run.finished") {
          qc.invalidateQueries({ queryKey: ["overview"] })
          qc.invalidateQueries({ queryKey: ["health"] })
          qc.invalidateQueries({ queryKey: ["supervisor"] })
        }
        if (ev.type === "queue.changed") qc.invalidateQueries({ queryKey: ["queue"] })
        if (ev.type === "agents.running_changed") qc.invalidateQueries({ queryKey: ["overview"] })
      }
      ws.onclose = () => {
        if (!closed) { setTimeout(connect, retry); retry = Math.min(retry * 2, 15000) }
      }
    }
    connect()
    const ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 25000)
    return () => { closed = true; clearInterval(ping); ws?.close() }
  }, [qc])
}

function CommandPalette() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const { data } = useQuery({ queryKey: ["overview"], queryFn: api.overview })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setOpen((o) => !o) }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])
  const pages = useMemo(() => tabs.map((t) => ({ label: t.label, to: t.to })), [])
  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Jump to page or agent…" />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        <CommandGroup heading="Pages">
          {pages.map((p) => (
            <CommandItem key={p.to} onSelect={() => { navigate(p.to); setOpen(false) }}>
              {p.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Agents">
          {(data?.agents ?? []).map((a) => (
            <CommandItem key={a.name} onSelect={() => { navigate(`/agent/${a.name}`); setOpen(false) }}>
              {a.name}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}

function DarkToggle() {
  const [dark, setDark] = useState(() => localStorage.getItem("theme") === "dark")
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
    localStorage.setItem("theme", dark ? "dark" : "light")
  }, [dark])
  return (
    <button onClick={() => setDark(!dark)}
      className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground">
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  useLiveEvents()
  const isConsole = useLocation().pathname.startsWith("/console")
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <div className="flex items-center gap-2 font-semibold">
            <Bot className="size-5" />
            <span>Agent Dashboard</span>
          </div>
          <nav className="flex items-center gap-1">
            {tabs.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors ${
                    isActive
                      ? "bg-secondary font-medium text-foreground"
                      : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                  }`
                }
              >
                <Icon className="size-4" />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <UpdateCheck />
            <kbd className="hidden rounded border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground md:inline">⌘K</kbd>
            <DarkToggle />
          </div>
        </div>
      </header>
      <CommandPalette />
      <main className={`mx-auto px-4 py-4 ${isConsole ? "max-w-full" : "max-w-7xl py-6"}`}>{children}</main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/agents" element={<AgentsPage />} />
            <Route path="/agent/:name" element={<AgentPage />} />
            <Route path="/queue" element={<QueuePage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/supervisor" element={<SupervisorPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/console" element={<ConsolePage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Shell>
        <Toaster position="bottom-right" />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
