import { jsxs as r, Fragment as n, jsx as e } from "react/jsx-runtime";
import { useAppApi as c } from "@kirocrew/app-sdk";
import { PageHeader as l, Card as p, CardTitle as m } from "@kirocrew/app-sdk/ui";
import { useState as i, useEffect as u } from "react";
function A() {
  const o = c(), [a, d] = i(null), [s, h] = i(null);
  return u(() => {
    o.get("/apps/agent-dashboard/api/apphost").then((t) => d(t.port)).catch((t) => h(t.message));
  }, []), s ? /* @__PURE__ */ r(n, { children: [
    /* @__PURE__ */ e(l, { title: "Agent Dashboard", subtitle: "Local-first observability for your agent fleet" }),
    /* @__PURE__ */ e("div", { className: "px-6 pb-8", children: /* @__PURE__ */ r(p, { children: [
      /* @__PURE__ */ e(m, { children: "Backend not reachable" }),
      /* @__PURE__ */ r("p", { className: "text-sm text-muted", children: [
        "The dashboard backend did not answer its health check yet: ",
        s
      ] }),
      /* @__PURE__ */ e("p", { className: "text-sm text-muted", children: "If this is the first start, the frontend may still be building (onEnable runs npm install + build once). Check the app logs and reload." })
    ] }) })
  ] }) : a === null ? /* @__PURE__ */ e(n, { children: /* @__PURE__ */ e(l, { title: "Agent Dashboard", subtitle: "Connecting to the dashboard backend..." }) }) : /* @__PURE__ */ e(
    "iframe",
    {
      src: `http://127.0.0.1:${a}/`,
      title: "Agent Dashboard",
      className: "h-full w-full flex-1 border-0",
      style: { minHeight: 0 }
    }
  );
}
export {
  A as default
};
