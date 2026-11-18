"use client";

import clsx from "clsx";
import { AlertOctagon, CloudLightning, Factory, Flame, Gavel, Landmark, Loader2, Network, ShieldAlert, Swords, Wifi } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type RiskEvent, type Structural } from "@/lib/api";
import { useAtlas } from "@/lib/store";

const TYPE_ICON: Record<string, typeof Flame> = {
  conflict: Swords,
  geopolitical: Landmark,
  weather: CloudLightning,
  labor_strike: Factory,
  regulatory: Gavel,
  financial: AlertOctagon,
  cyber: Wifi,
  infrastructure: Network,
};

export function RisksPanel() {
  const { setImpact, setTab, setHighlight } = useAtlas();
  const [events, setEvents] = useState<RiskEvent[]>([]);
  const [structural, setStructural] = useState<Structural | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [filter, setFilter] = useState<"open" | "all">("open");

  useEffect(() => {
    api.risks().then((r) => setEvents(r.events)).catch(() => {});
    api.structural().then(setStructural).catch(() => {});
  }, []);

  const assess = async (id: string) => {
    setRunning(id);
    try {
      setImpact(await api.scenario({ event_ids: [id] }));
      setTab("scenario");
    } finally {
      setRunning(null);
    }
  };

  const shown = events.filter((e) => filter === "all" || e.status !== "resolved");

  return (
    <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[1.1fr_1fr]">
      <div className="scroll-thin min-h-0 overflow-y-auto pe-1">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-300">Risk events</div>
          <div className="flex rounded-lg bg-white/5 p-0.5 text-[11px]">
            {(["open", "all"] as const).map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={clsx("rounded-md px-2 py-0.5 capitalize", filter === f ? "bg-white/10 text-ink-100" : "text-ink-400")}>
                {f}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          {shown.map((e) => {
            const Icon = TYPE_ICON[e.type] ?? Flame;
            const score = e.severity * (e.probability ?? 1);
            return (
              <button
                key={e.id}
                onClick={() => assess(e.id)}
                onMouseEnter={() => setHighlight(e.affects.length ? [e.id] : [])}
                className="group w-full rounded-xl border hairline bg-white/[0.02] p-3 text-start transition hover:border-signal-500/30 hover:bg-white/[0.04]"
              >
                <div className="flex gap-3">
                  <div className={clsx("grid size-8 shrink-0 place-items-center rounded-lg", score >= 4 ? "bg-alarm-500/15 text-alarm-400" : score >= 2 ? "bg-signal-500/15 text-signal-400" : "bg-white/5 text-ink-400")}>
                    {running === e.id ? <Loader2 size={15} className="animate-spin" /> : <Icon size={15} />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-medium leading-snug text-ink-100">{e.title}</div>
                    {e.title_ar && (
                      <div dir="rtl" className="mt-0.5 truncate text-xs text-ink-400">
                        {e.title_ar}
                      </div>
                    )}
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10.5px]">
                      <Chip className={e.status === "active" ? "bg-alarm-500/15 text-alarm-400" : e.status === "forecast" ? "bg-sky-400/15 text-sky-400" : "bg-white/5 text-ink-400"}>{e.status}</Chip>
                      <Chip className="bg-white/5 text-ink-300">sev {e.severity}/5</Chip>
                      {e.probability < 1 && <Chip className="bg-white/5 text-ink-300">{Math.round(e.probability * 100)}% likely</Chip>}
                      <span className="truncate text-ink-500">{e.affects.join(", ")}</span>
                    </div>
                  </div>
                  <SeverityBar value={score} />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="scroll-thin min-h-0 space-y-4 overflow-y-auto pe-1">
        {!structural ? (
          <div className="shimmer h-40 rounded-xl" />
        ) : (
          <>
            <Block title="Hidden dependencies" icon={<Network size={13} />}>
              {structural.hidden_dependencies.slice(0, 3).map((h) => (
                <div key={h.upstream} className={clsx("rounded-lg p-2.5 text-xs leading-relaxed", h.health === "distressed" ? "bg-alarm-500/10 text-alarm-400" : "bg-white/[0.03] text-ink-300")}>
                  {h.explanation}
                </div>
              ))}
            </Block>
            <Block title="Single points of failure" icon={<ShieldAlert size={13} />}>
              <div className="space-y-1">
                {structural.single_points.slice(0, 7).map((s) => (
                  <div key={s.item} className="flex items-center gap-2 rounded-lg px-1 py-1 text-xs hover:bg-white/[0.03]">
                    <span className={clsx("size-1.5 shrink-0 rounded-full", s.qualified_alternative ? "bg-signal-400" : "bg-alarm-400")} />
                    <span className="min-w-0 flex-1 truncate text-ink-200">
                      {s.item} <span className="text-ink-500">← {s.supplier} · T{s.tier} · {s.country}</span>
                    </span>
                    <span className="shrink-0 num text-ink-300">{s.revenue_dependent}</span>
                  </div>
                ))}
              </div>
            </Block>
            <Block title="Chokepoint concentration" icon={<AlertOctagon size={13} />}>
              <div className="space-y-2">
                {structural.concentration.filter((c) => c.dimension === "chokepoint").slice(0, 5).map((c) => (
                  <div key={c.name} className="text-xs">
                    <div className="mb-1 flex justify-between text-ink-300">
                      <span>{c.name}</span>
                      <span className="num">{c.share_of_inbound_lanes_pct}% of inbound lanes</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/[0.04]">
                      <div className="h-full rounded-full bg-gradient-to-r from-signal-500 to-alarm-500" style={{ width: `${c.share_of_inbound_lanes_pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </Block>
          </>
        )}
      </div>
    </div>
  );
}

function Chip({ children, className }: { children: React.ReactNode; className: string }) {
  return <span className={clsx("rounded-md px-1.5 py-0.5 font-medium capitalize", className)}>{children}</span>;
}

function SeverityBar({ value }: { value: number }) {
  return (
    <div className="flex h-8 shrink-0 items-end gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={clsx("w-1 rounded-sm", i <= Math.round(value) ? (value >= 4 ? "bg-alarm-400" : "bg-signal-400") : "bg-white/10")} style={{ height: `${i * 6 + 2}px` }} />
      ))}
    </div>
  );
}

function Block({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border hairline bg-white/[0.015] p-3">
      <div className="mb-2.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-300">
        {icon}
        {title}
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}
