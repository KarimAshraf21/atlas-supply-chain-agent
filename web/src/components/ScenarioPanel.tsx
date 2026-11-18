"use client";

import clsx from "clsx";
import { Loader2, Play, Plus, Trash2, Zap } from "lucide-react";
import { useMemo, useState } from "react";
import { api, type Disruption } from "@/lib/api";
import { useAtlas } from "@/lib/store";
import { ImpactPanel } from "./ImpactPanel";

const PRESETS: { label: string; sub: string; body: Parameters<typeof api.scenario>[0] }[] = [
  { label: "Red Sea closure", sub: "active · Bab el-Mandeb", body: { event_ids: ["RE-REDSEA"] } },
  { label: "Red Sea + Suez", sub: "compound disruption", body: { event_ids: ["RE-REDSEA", "RE-SUEZ"] } },
  { label: "Hormuz closure", sub: "forecast · 20% likely", body: { event_ids: ["RE-HORMUZ"] } },
  { label: "Copper-foil insolvency", sub: "hidden tier-2 dependency", body: { event_ids: ["RE-DAEGU"] } },
  {
    label: "FormoSiC outage 60d",
    sub: "single-source chips",
    body: { disruptions: [{ target: "SUP-FORMOSIC", impact: "capacity_reduction", duration_days: 60, magnitude: 1 }] },
  },
  { label: "Suez closed 45d", sub: "what-if", body: { disruptions: [{ target: "SUEZ", impact: "closure", duration_days: 45 }] } },
];

const IMPACTS: Disruption["impact"][] = ["closure", "delay", "capacity_reduction", "insolvency"];

export function ScenarioPanel() {
  const { overview, impact, setImpact } = useAtlas();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [custom, setCustom] = useState<Disruption[]>([{ target: "SUEZ", impact: "closure", duration_days: 30, magnitude: 1 }]);

  const targets = useMemo(() => {
    if (!overview) return [];
    return [
      ...overview.chokepoints.map((c) => ({ id: c.id, name: c.name, group: "Chokepoints" })),
      ...overview.ports.map((p) => ({ id: p.id, name: p.name, group: "Ports" })),
      ...overview.suppliers.map((s) => ({ id: s.id, name: `${s.name} (T${s.tier})`, group: "Suppliers" })),
      ...overview.sites.filter((s) => s.ours && s.kind === "Factory").map((s) => ({ id: s.id, name: s.name, group: "Our plants" })),
    ];
  }, [overview]);

  const run = async (key: string, body: Parameters<typeof api.scenario>[0]) => {
    setLoading(key);
    setError(null);
    try {
      setImpact(await api.scenario(body));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="grid h-full min-h-0 gap-4 lg:grid-cols-[320px_1fr]">
      <div className="scroll-thin min-h-0 space-y-4 overflow-y-auto pe-1">
        <div>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Presets</div>
          <div className="grid grid-cols-2 gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => run(p.label, p.body)}
                className="group rounded-xl border hairline bg-white/[0.02] p-2.5 text-start transition hover:border-signal-500/30 hover:bg-signal-500/[0.06]"
              >
                <div className="flex items-center gap-1.5 text-xs font-medium text-ink-100">
                  {loading === p.label ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} className="text-signal-400" />}
                  {p.label}
                </div>
                <div className="mt-0.5 text-[11px] text-ink-500">{p.sub}</div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Build a what-if</div>
          <div className="space-y-2">
            {custom.map((d, i) => (
              <div key={i} className="space-y-2 rounded-xl border hairline bg-white/[0.02] p-2.5">
                <div className="flex gap-2">
                  <select
                    value={d.target}
                    onChange={(e) => setCustom((c) => c.map((x, j) => (j === i ? { ...x, target: e.target.value } : x)))}
                    className="min-w-0 flex-1 rounded-lg border hairline bg-ink-900 px-2 py-1.5 text-xs text-ink-100"
                  >
                    {["Chokepoints", "Ports", "Suppliers", "Our plants"].map((g) => (
                      <optgroup key={g} label={g}>
                        {targets.filter((t) => t.group === g).map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  {custom.length > 1 && (
                    <button onClick={() => setCustom((c) => c.filter((_, j) => j !== i))} className="rounded-lg p-1.5 text-ink-500 hover:text-alarm-400" aria-label="Remove">
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-1">
                  {IMPACTS.map((imp) => (
                    <button
                      key={imp}
                      onClick={() => setCustom((c) => c.map((x, j) => (j === i ? { ...x, impact: imp } : x)))}
                      className={clsx("rounded-md px-2 py-1 text-[11px] capitalize transition", d.impact === imp ? "bg-signal-500/20 text-signal-400" : "bg-white/[0.03] text-ink-400 hover:text-ink-200")}
                    >
                      {imp.replace("_", " ")}
                    </button>
                  ))}
                </div>
                <Slider label="Duration" value={d.duration_days} min={3} max={120} unit="days" onChange={(v) => setCustom((c) => c.map((x, j) => (j === i ? { ...x, duration_days: v } : x)))} />
                {(d.impact === "capacity_reduction" || d.impact === "insolvency") && (
                  <Slider label="Capacity lost" value={Math.round((d.magnitude ?? 1) * 100)} min={10} max={100} unit="%" onChange={(v) => setCustom((c) => c.map((x, j) => (j === i ? { ...x, magnitude: v / 100 } : x)))} />
                )}
                {d.impact === "delay" && (
                  <Slider label="Added transit" value={d.added_days ?? 7} min={1} max={30} unit="days" onChange={(v) => setCustom((c) => c.map((x, j) => (j === i ? { ...x, added_days: v } : x)))} />
                )}
              </div>
            ))}
            <div className="flex gap-2">
              <button
                onClick={() => setCustom((c) => [...c, { target: targets[0]?.id ?? "SUEZ", impact: "closure", duration_days: 30, magnitude: 1 }])}
                className="flex items-center gap-1 rounded-lg border hairline px-2.5 py-1.5 text-xs text-ink-300 hover:text-ink-100"
              >
                <Plus size={12} /> Add disruption
              </button>
              <button
                onClick={() => run("custom", { disruptions: custom })}
                className="ms-auto flex items-center gap-1.5 rounded-lg bg-signal-500 px-3 py-1.5 text-xs font-semibold text-ink-950 hover:bg-signal-400"
              >
                {loading === "custom" ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                Simulate
              </button>
            </div>
          </div>
        </div>
        {error && <div className="rounded-lg bg-alarm-500/10 p-2 text-xs text-alarm-400">{error}</div>}
        <p className="text-[11px] leading-relaxed text-ink-500">
          Runs the deterministic reasoning engine directly — no LLM. Lanes reroute around closed chokepoints, inventory is simulated day by day, and mitigations (qualified alternates, supplier surge) are applied.
        </p>
      </div>

      <div className="scroll-thin min-h-0 overflow-y-auto pe-1">
        {impact ? (
          <ImpactPanel impact={impact} onClose={() => setImpact(null)} />
        ) : (
          <div className="grid h-full place-items-center text-center text-sm text-ink-500">
            <div>
              <Zap className="mx-auto mb-2 text-signal-500/60" />
              Pick a preset or build a what-if to see the impact.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, unit, onChange }: { label: string; value: number; min: number; max: number; unit: string; onChange: (v: number) => void }) {
  return (
    <label className="block text-[11px] text-ink-400">
      <div className="mb-1 flex justify-between">
        <span>{label}</span>
        <span className="num text-ink-200">
          {value} {unit}
        </span>
      </div>
      <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-amber-500" />
    </label>
  );
}
