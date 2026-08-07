import { useEffect, useRef } from "react"
import { Terminal } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import "@xterm/xterm/css/xterm.css"

export default function TerminalPane({
  initialCommand,
  fill = false,
  broadcastChannel = false,
  sessionId,
}: {
  initialCommand?: string
  fill?: boolean
  broadcastChannel?: boolean
  /** stable id => PTY survives refresh/reconnect (server keeps it 15min) */
  sessionId?: string
}) {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!hostRef.current) return
    const term = new Terminal({
      fontSize: 13,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      theme: { background: "#09090b" },
      cursorBlink: true,
      scrollback: 5000,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(hostRef.current)
    fit.fit()
    // refit after layout settles (grid panes size late)
    setTimeout(() => { fit.fit(); ws.readyState === WebSocket.OPEN && ws.send(`\x01${term.cols},${term.rows}`) }, 300)

    const proto = location.protocol === "https:" ? "wss" : "ws"
    const qs = sessionId ? `?session=${encodeURIComponent(sessionId)}` : ""
    const ws = new WebSocket(`${proto}://${location.host}/ws/terminal${qs}`)
    ws.binaryType = "arraybuffer"

    ws.onopen = () => ws.send(`\x01${term.cols},${term.rows}`)
    ws.onmessage = (e) => {
      if (typeof e.data === "string") {
        // control frame: only run initialCommand on a NEW session (not reattach)
        try {
          const ctl = JSON.parse(e.data)
          if (ctl.control === "ready") {
            if (ctl.new && initialCommand) ws.send(`${initialCommand}\n`)
            return
          }
        } catch { /* plain text output */ }
        term.write(e.data)
        return
      }
      term.write(new Uint8Array(e.data))
    }
    ws.onclose = () => term.write("\r\n\x1b[33m[session closed]\x1b[0m\r\n")

    const dispose = term.onData((d) => ws.readyState === WebSocket.OPEN && ws.send(d))

    const onBroadcast = (e: Event) => {
      const text = (e as CustomEvent<string>).detail
      if (ws.readyState === WebSocket.OPEN) ws.send(`${text}\n`)
    }
    if (broadcastChannel) window.addEventListener("console-broadcast", onBroadcast)

    const onKill = (e: Event) => {
      if ((e as CustomEvent<string>).detail === sessionId && ws.readyState === WebSocket.OPEN)
        ws.send("\x02kill")
    }
    window.addEventListener("console-kill", onKill)

    const onResize = () => {
      fit.fit()
      if (ws.readyState === WebSocket.OPEN) ws.send(`\x01${term.cols},${term.rows}`)
    }
    const ro = new ResizeObserver(onResize)
    ro.observe(hostRef.current)

    return () => {
      if (broadcastChannel) window.removeEventListener("console-broadcast", onBroadcast)
      window.removeEventListener("console-kill", onKill)
      ro.disconnect()
      dispose.dispose()
      ws.close()
      term.dispose()
    }
  }, [initialCommand, broadcastChannel])

  return (
    <div
      ref={hostRef}
      className={`w-full overflow-hidden bg-[#09090b] p-1 ${fill ? "h-full" : "h-[60vh] rounded-lg"}`}
    />
  )
}
