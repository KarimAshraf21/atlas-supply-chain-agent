"use client";

import clsx from "clsx";
import { Activity, Boxes, Globe2, Network, Radar, Ship, Users, X, Zap } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { api, usd } from "@/lib/api";
import { useAtlas, type Tab } from "@/lib/store";
import { ChatPanel } from "./ChatPanel";
import { ImpactPanel } from "./ImpactPanel";
import { RisksPanel } from "./RisksPanel";
import { ScenarioPanel } from "./ScenarioPanel";

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <div className="shimmer h-full rounded-2xl" /> });
const GraphPanel = dynamic(() => import("./GraphPanel"), { ssr: false, loading: () => <div className="shimmer h-full rounded-2xl" /> });

const TABS: { id: Tab; label: string; icon: typeof Globe2 }[] = [
  { id: "map", label: "World map", icon: Globe2 },
  { id: "scenario", label: "Scenario lab", icon: Zap },
  { id: "risks", label: "Risk radar", icon: Radar },
  { id: "graph", label: "Knowledge graph", icon: Network },
];

export function Shell() {
  const { overview, health, error, tab, setTab, impact, setImpact, highlight, setHighlight } = useAtlas();

  return (
    <div className="flex min-h-dvh flex-col gap-3 p-3 lg:h-dvh lg:p-4">
      {/* header */}
      <header className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <Logo />
          <div>
            <div className="text-[15px] font-semibold tracking-tight">Atlas</div>
            <div className="text-[11px] text-ink-400">Talk to your supply chain</div>
          </div>
        </div>
        <div className="hidden h-8 w-px bg-white/10 md:block" />
        <div className="hidden md:block">
          <div className="text-xs font-medium text-ink-200">{overview?.company.name ?? "…"}</div>
          <div className="text-[11px] text-ink-500">Fictional demo company · data as of 18 Nov 2026</div>
        </div>
        <div className="ms-auto flex items-center gap-2 text-[11px]">
          <StatusPill ok={!!health?.graph.ok} label={health?.graph.ok ? `Graph · ${health.graph.nodes?.toLocaleString()} nodes` : "Graph offline"} />
          <StatusPill ok={!!health?.llm.configured} label={health?.llm.configured ? `LLM · ${health.llm.reasoning.split("/").pop()}` : "LLM key missing"} warn />
        </div>
      </header>

      {error && (
        <div className="rounded-xl border border-alarm-500/30 bg-alarm-500/10 px-4 py-3 text-sm text-alarm-400">
          Can’t reach the Atlas API ({error}). Start it with <code className="num">atlas serve</code>.
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi icon={Boxes} label="Open order book" value={overview ? usd(overview.kpis.open_order_value_usd) : "—"} sub={overview ? `${overview.kpis.open_orders} orders` : ""} />
        <Kpi icon={Activity} label="Active risk events" value={overview ? String(overview.kpis.active_risks) : "—"} tone="alarm" sub="+ forecasts on watch" />
        <Kpi icon={Users} label="Suppliers" value={overview ? String(overview.kpis.suppliers) : "—"} sub="3 tiers · 18 countries" />
        <Kpi icon={Ship} label="Shipping lanes" value={overview ? String(overview.kpis.lanes) : "—"} sub="8 chokepoints monitored" />
        <Kpi icon={Zap} label="Revenue at risk" value={impact?.headline.lost_revenue ?? "—"} tone="signal" sub={impact ? `${impact.headline.lost_revenue_after_mitigation} after mitigation` : "run a scenario"} />
        <Kpi icon={Radar} label="Penalty exposure" value={impact?.headline.penalty_exposure ?? "—"} tone="violet" sub={impact ? `${impact.headline.penalties_without_force_majeure} unprotected` : "liquidated damages"} />
      </div>

      {/* main */}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[400px_1fr] xl:grid-cols-[440px_1fr]">
        <div className="h-[78dvh] min-h-0 lg:h-auto">
          <ChatPanel />
        </div>
        <section className="panel flex min-h-[520px] flex-col rounded-2xl p-3">
          <div className="mb-3 flex items-center gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  "relative flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition",
                  tab === t.id ? "text-ink-100" : "text-ink-400 hover:text-ink-200",
                )}
              >
                {tab === t.id && <motion.span layoutId="tab" className="absolute inset-0 rounded-lg bg-white/[0.07]" transition={{ type: "spring", duration: 0.4 }} />}
                <t.icon size={14} className="relative" />
                <span className="relative">{t.label}</span>
              </button>
            ))}
            {highlight.length > 0 && (
              <button onClick={() => { setHighlight([]); setImpact(null); }} className="ms-auto flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] text-ink-400 hover:bg-white/5 hover:text-ink-100">
                <X size={12} /> Clear focus ({highlight.length})
              </button>
            )}
          </div>
          <div className="relative min-h-0 flex-1">
            <div className={clsx("absolute inset-0", tab !== "map" && "pointer-events-none invisible opacity-0")}>
              <MapView />
              <AnimatePresence>
                {impact && tab === "map" && (
                  <motion.div
                    initial={{ opacity: 0, x: 24 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 24 }}
                    className="panel scroll-thin absolute bottom-3 right-3 top-3 w-[min(440px,60%)] overflow-y-auto rounded-2xl p-4"
                  >
                    <ImpactPanel impact={impact} compact onClose={() => setImpact(null)} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            {tab === "scenario" && <ScenarioPanel />}
            {tab === "risks" && <RisksPanel />}
            {tab === "graph" && <GraphPanel />}
            <EntityDrawer />
          </div>
        </section>
      </div>
    </div>
  );
}

function EntityDrawer() {
  const { focus, setFocus, setHighlight } = useAtlas();
  const [data, setData] = useState<Awaited<ReturnType<typeof api.entity>> | null>(null);
  useEffect(() => {
    if (!focus) return;
    let cancelled = false;
    api.entity(focus).then((d) => !cancelled && setData(d)).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [focus]);
  if (!focus || !data || data.properties.id !== focus) return null;
  const p = data.properties;
  const neighbours = data.neighbours as { rel: string; direction: string; id: string; name: string }[];
  const groups = neighbours.reduce<Record<string, typeof neighbours>>((acc, n) => {
    const k = `${n.direction === "out" ? "→" : "←"} ${n.rel}`;
    (acc[k] ??= []).push(n);
    return acc;
  }, {});
  const skip = new Set(["id", "name", "title", "text_excerpt", "lat", "lon", "website", "path"]);
  return (
    <motion.aside initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="panel scroll-thin absolute bottom-3 left-3 z-10 max-h-[70%] w-80 overflow-y-auto rounded-2xl p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-wider text-tide-400">{data.labels.filter((l) => !["Organization", "Item", "Facility"].includes(l)).join(" · ")}</div>
          <div className="text-sm font-semibold leading-snug">{String(p.name ?? p.title ?? focus)}</div>
          {typeof p.name_ar === "string" && <div dir="rtl" className="text-xs text-ink-400">{p.name_ar}</div>}
        </div>
        <button onClick={() => setFocus(null)} className="rounded-lg p-1 text-ink-400 hover:bg-white/5" aria-label="Close">
          <X size={14} />
        </button>
      </div>
      <dl className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
        {Object.entries(p).filter(([k]) => !skip.has(k)).slice(0, 12).map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-ink-500">{k.replaceAll("_", " ")}</dt>
            <dd className="truncate num text-ink-200">{typeof v === "number" ? v.toLocaleString() : String(v)}</dd>
          </div>
        ))}
      </dl>
      {typeof p.text_excerpt === "string" && <p className="mb-3 whitespace-pre-line text-[11px] leading-relaxed text-ink-300">{p.text_excerpt.slice(0, 600)}…</p>}
      <div className="space-y-2">
        {Object.entries(groups).slice(0, 8).map(([k, ns]) => (
          <div key={k}>
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-ink-500">{k} · {ns.length}</div>
            <div className="flex flex-wrap gap-1">
              {ns.slice(0, 10).map((n) => (
                <button key={n.id} onClick={() => { setFocus(n.id); setHighlight([focus, n.id]); }} className="rounded-md bg-white/[0.05] px-1.5 py-0.5 text-[11px] text-ink-200 hover:bg-tide-500/15 hover:text-tide-300">
                  {n.name ?? n.id}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </motion.aside>
  );
}

function Kpi({ icon: Icon, label, value, sub, tone = "tide" }: { icon: typeof Globe2; label: string; value: string; sub?: string; tone?: "tide" | "alarm" | "signal" | "violet" }) {
  const color = { tide: "text-tide-400", alarm: "text-alarm-400", signal: "text-signal-400", violet: "text-violet-400" }[tone];
  return (
    <div className="panel rounded-2xl px-4 py-3">
      <div className="flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-wider text-ink-400">
        <Icon size={12} className={color} />
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tracking-tight num">{value}</div>
      {sub && <div className="truncate text-[11px] text-ink-500">{sub}</div>}
    </div>
  );
}

function StatusPill({ ok, label, warn }: { ok: boolean; label: string; warn?: boolean }) {
  return (
    <span className={clsx("flex items-center gap-1.5 rounded-full border px-2.5 py-1", ok ? "border-tide-500/25 text-tide-300" : warn ? "border-signal-500/30 text-signal-400" : "border-alarm-500/30 text-alarm-400")}>
      <span className={clsx("size-1.5 rounded-full", ok ? "bg-tide-400" : warn ? "bg-signal-400" : "bg-alarm-400")} />
      {label}
    </span>
  );
}

function Logo() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2dd4bf" />
          <stop offset="1" stopColor="#a78bfa" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="14" fill="none" stroke="url(#lg)" strokeWidth="2" />
      <ellipse cx="16" cy="16" rx="6" ry="14" fill="none" stroke="url(#lg)" strokeWidth="1.2" opacity=".7" />
      <path d="M2.5 12h27M2.5 20h27" stroke="url(#lg)" strokeWidth="1.2" opacity=".5" />
      <circle cx="22" cy="10" r="2.6" fill="#f59e0b" />
    </svg>
  );
}
