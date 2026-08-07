/** Typed client for the dashboard backend API. */

export interface RunRow {
  id: number
  job_id: string
  started_at: string | null
  duration_sec: number | null
  status: string
  exit_code: number | null
  log_path: string | null
}

export interface AgentStats {
  total: number
  ok: number
  fail: number
  avg_dur: number
  last: RunRow | null
  trend: "up" | "down" | "flat" | "none"
  score: number
  recent: RunRow[]
}

export interface AgentSummary {
  name: string
  has_config?: boolean
  description: string
  stats: AgentStats
  is_running: boolean
  job: { id: string; cron: string } | null
}

export interface Alert {
  type: "info" | "warn" | "fail"
  message: string
  items?: { id: number; job_id: string; started_at: string; exit_code: number | null; duration_sec?: number | null; log_path?: string | null }[]
  ids?: string
}

export interface ScheduleJob {
  id: string
  cron: string
  timeout_sec?: number
  enabled: boolean
  description?: string
  last_run: { started_at: string; status: string } | null
  is_running?: boolean
}

export interface Overview {
  agents: AgentSummary[]
  metrics: { total_runs: number; ok_24h: number; fail_24h: number; running: string[] }
  alerts: Alert[]
  timeline: RunRow[]
  schedule: ScheduleJob[]
  chart: { day: string; date: string; ok: number; fail: number }[]
}

export interface AgentDetail {
  info: {
    name: string
    description: string
    md_lines: number
    has_json: boolean
    data_files: number
    deps: string
  }
  stats: AgentStats
  runs: RunRow[]
  job: { id: string; cron: string; timeout_sec: number } | null
}

export interface QueueItem {
  id: string
  agent: string
  input: string
  priority: string
  status: string
  created: string
  result?: string
  completedAt?: string
}

export interface QueueData {
  counts: { pending: number; running: number; done: number; failed: number }
  stuck: string[]
  items: QueueItem[]
}

export interface HealthAgent {
  name: string
  score: number
  total: number
  ok: number
  fail: number
  avg_dur: number
  trend: string
  last_run: string | null
}

export interface SupervisorData {
  status: string
  pid: string | null
  uptime: string | null
  today_runs: number
  total_runs: number
  schedule: (ScheduleJob & { script?: string })[]
}

export interface LogFile {
  name: string
  size_kb: number
  mtime: string
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return r.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return r.json()
}

export const api = {
  overview: () => get<Overview>("/api/overview"),
  agent: (name: string) => get<AgentDetail>(`/api/agent/${name}`),
  queue: () => get<QueueData>("/api/queue"),
  health: () => get<{ agents: HealthAgent[] }>("/api/health"),
  supervisor: () => get<SupervisorData>("/api/supervisor"),
  logs: () => get<{ files: LogFile[] }>("/api/logs"),

  triggerJob: (jobId: string) => post<{ ok: boolean; agent: string }>(`/api/trigger/${jobId}`),
  triggerAgent: (name: string) => post<{ ok: boolean; log: string }>(`/api/trigger-agent/${name}`),
  ackAlerts: (ids: string[]) => post<{ ok: boolean }>("/api/alerts/ack", { ids }),
  queueRetry: (id: string) => post<{ ok: boolean }>(`/api/queue/retry/${id}`),
  queueCancel: (id: string) => post<{ ok: boolean }>(`/api/queue/cancel/${id}`),
  enqueue: (agent: string, input: string, priority = "medium") =>
    post<{ ok: boolean; id: string }>("/api/queue/enqueue", { agent, input, priority }),
}

/** "2026-08-06 12:00:00" -> "3h ago" */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const then = new Date(iso.replace(" ", "T")).getTime()
  if (Number.isNaN(then)) return iso
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function fmtDuration(sec: number | null | undefined): string {
  if (sec == null) return "—"
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m${sec % 60 ? ` ${sec % 60}s` : ""}`
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
}
