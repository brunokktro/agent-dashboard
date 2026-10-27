import { jsxs as c, Fragment as d, jsx as s } from "react/jsx-runtime";
import { useAppApi as u } from "@kirocrew/app-sdk";
import { PageHeader as h, Card as f, CardTitle as m } from "@kirocrew/app-sdk/ui";
import { useState as p, useEffect as b } from "react";
const g = (n) => new Promise((t) => setTimeout(t, n));
async function w(n, { attempts: t = 30, delayMs: i = 500, wait: l = g } = {}) {
  if (t < 1) throw new Error("attempts must be at least 1");
  let e;
  for (let r = 1; r <= t; r += 1)
    try {
      const a = await n();
      if (a.status !== "ok" || !Number.isInteger(a.port) || a.port < 1 || a.port > 65535)
        throw new Error("app host returned an invalid status or port");
      return a;
    } catch (a) {
      e = a, r < t && await l(i);
    }
  const o = e instanceof Error ? e.message : String(e);
  throw new Error(`backend did not become reachable after ${t} attempts: ${o}`);
}
function A() {
  const n = u(), [t, i] = p(null), [l, e] = p(null);
  return b(() => {
    let o = !1;
    return e(null), w(() => n.get("/apps/agent-dashboard/api/apphost")).then((r) => {
      o || i(r.port);
    }).catch((r) => {
      o || e(r.message);
    }), () => {
      o = !0;
    };
  }, []), l ? /* @__PURE__ */ c(d, { children: [
    /* @__PURE__ */ s(h, { title: "Agent Dashboard", subtitle: "Local-first observability for your agent fleet" }),
    /* @__PURE__ */ s("div", { className: "px-6 pb-8", children: /* @__PURE__ */ c(f, { children: [
      /* @__PURE__ */ s(m, { children: "Backend not reachable" }),
      /* @__PURE__ */ c("p", { className: "text-sm text-muted", children: [
        "The dashboard backend did not answer its health check yet: ",
        l
      ] }),
      /* @__PURE__ */ s("p", { className: "text-sm text-muted", children: "If this is the first start, the frontend may still be building (onEnable runs npm install + build once). Check the app logs and reload." })
    ] }) })
  ] }) : t === null ? /* @__PURE__ */ s(d, { children: /* @__PURE__ */ s(h, { title: "Agent Dashboard", subtitle: "Connecting to the dashboard backend..." }) }) : /* @__PURE__ */ s(
    "iframe",
    {
      src: `http://127.0.0.1:${t}/`,
      title: "Agent Dashboard",
      className: "h-full w-full flex-1 border-0",
      style: { minHeight: 0 }
    }
  );
}
export {
  A as default
};
