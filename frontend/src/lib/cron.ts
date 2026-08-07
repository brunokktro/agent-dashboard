import { CronExpressionParser } from "cron-parser"
import cronstrue from "cronstrue"

/** "0 8,13,18 * * 1-5" -> "At 8:00 AM, 1:00 PM and 6:00 PM, Monday through Friday" */
export function humanizeCron(cron: string): string {
  try {
    return cronstrue.toString(cron, { verbose: false, use24HourTimeFormat: true })
  } catch {
    return cron
  }
}

/** Next fire Date for a cron expression, or null if unparsable. */
export function nextRun(cron: string): Date | null {
  try {
    return CronExpressionParser.parse(cron).next().toDate()
  } catch {
    return null
  }
}

/** "in 2h 15m" style countdown. */
export function countdown(date: Date | null): string {
  if (!date) return "—"
  const s = Math.floor((date.getTime() - Date.now()) / 1000)
  if (s < 0) return "now"
  if (s < 60) return `in ${s}s`
  if (s < 3600) return `in ${Math.floor(s / 60)}m`
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h < 24) return `in ${h}h${m ? ` ${m}m` : ""}`
  return `in ${Math.floor(h / 24)}d ${h % 24}h`
}

export type Frequency = "hourly" | "daily" | "weekly" | "monthly"

/** Rough bucket for filtering: how often does this cron fire? */
export function cronFrequency(cron: string): Frequency {
  const parts = cron.trim().split(/\s+/)
  if (parts.length < 5) return "daily"
  const [, hour, dom, , dow] = parts
  if (hour.includes("-") || hour.includes(",") && hour.split(",").length > 3 || hour === "*")
    return "hourly"
  if (dom !== "*") return "monthly"
  if (dow !== "*" && !dow.includes("-") && !dow.includes(",")) return "weekly"
  return "daily"
}
