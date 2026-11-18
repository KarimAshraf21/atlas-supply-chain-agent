"use client";

import clsx from "clsx";
import { ShieldAlert, ShieldCheck, Ship, Sparkles, X } from "lucide-react";
import { motion } from "motion/react";
import type { ImpactSummary } from "@/lib/api";

const money = (s: string) => {
  const m = s.replace(/[$,]/g, "");
  const n = parseFloat(m);
  return m.endsWith("M") ? n * 1e6 : m.endsWith("B") ? n * 1e9 : m.endsWith("k") ? n * 1e3 : n;
};

export function ImpactPanel({ impact, onClose, compact }: { impact: ImpactSummary; onClose?: () => void; compact?: boolean }) {
  const h = impact.headline;
  const horizon = Math.max(45, ...impact.component_stockouts.map((s) => s.stockout_in_days + s.shortage_days + 5));
  const maxLost = Math.max(1, ...impact.products.map((p) => money(p.lost_revenue)));
  const unprotected = money(h.penalties_without_force_majeure) > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-ink-400">Impact assessment · as of {impact.as_of}</div>
          <div className="mt-0.5 text-sm text-ink-300">
            {impact.ui.report.disruptions
              .slice(0, 3)
              .map((d) => `${d.target.replaceAll("_", " ")} · ${d.impact.replace("_", " ")} · ${d.duration_days}d`)
              .join("  ·  ")}
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="rounded-lg p-1 text-ink-400 hover:bg-white/5 hover:text-ink-100" aria-label="Close">
            <X size={16} />
          </button>
        )}
      </div>

      {/* headline */}
      <div className={clsx("grid gap-2", compact ? "grid-cols-2" : "grid-cols-2 xl:grid-cols-4")}>
        <Stat label="Revenue at risk" value={h.lost_revenue} tone="alarm" sub={`${h.lost_revenue_after_mitigation} after mitigation`} />
        <Stat label="Orders at risk" value={String(h.orders_at_risk)} sub={`${h.order_value_at_risk} order value`} tone="signal" />
        <Stat label="Penalty exposure" value={h.penalty_exposure} sub={unprotected ? `${h.penalties_without_force_majeure} without force majeure` : "all covered by force majeure"} tone={unprotected ? "alarm" : "tide"} />
        <Stat label="Lanes disrupted" value={String(h.lanes_affected)} sub={h.lanes_blocked ? `${h.lanes_blocked} blocked` : "all rerouted"} tone="violet" />
      </div>

      {/* stock-out timeline */}
      {impact.component_stockouts.length > 0 && (
        <Section title="Stock-out timeline" hint="inventory cover → run-out → shortage">
          <div className="space-y-2">
            {impact.component_stockouts.map((s, i) => {
              const pct = (d: number) => `${Math.min(100, (d / horizon) * 100)}%`;
              return (
                <div key={i} className="group">
                  <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
                    <span className="truncate text-ink-200">
                      {s.component} <span className="text-ink-500">· {s.factory}</span>
                    </span>
                    <span className="shrink-0 num text-alarm-400">day {s.stockout_in_days}</span>
                  </div>
                  <div className="relative h-2.5 rounded-full bg-white/[0.04]">
                    <motion.div
                      className="absolute inset-y-0 left-0 rounded-full bg-tide-500/50"
                      initial={{ width: 0 }}
                      animate={{ width: pct(s.days_of_cover) }}
                      transition={{ duration: 0.7, delay: i * 0.05 }}
                    />
                    <motion.div
                      className="absolute inset-y-0 rounded-full bg-alarm-500/80"
                      style={{ left: pct(s.stockout_in_days) }}
                      initial={{ width: 0 }}
                      animate={{ width: pct(Math.max(1, s.shortage_days)) }}
                      transition={{ duration: 0.6, delay: 0.4 + i * 0.05 }}
                    />
                    {s.with_mitigation_stockout_in_days === null && (
                      <span className="absolute -top-0.5 h-3.5 w-0.5 rounded bg-tide-300" style={{ left: pct(s.stockout_in_days) }} title="mitigation avoids the stock-out" />
                    )}
                  </div>
                  <div className="mt-1 hidden text-[11px] text-ink-500 group-hover:block">{s.why}</div>
                </div>
              );
            })}
            <div className="flex justify-between pt-1 text-[10px] text-ink-500 num">
              <span>today</span>
              <span>day {Math.round(horizon / 2)}</span>
              <span>day {horizon}</span>
            </div>
          </div>
        </Section>
      )}

      <div className={clsx("grid gap-4", !compact && "xl:grid-cols-2")}>
        {impact.products.length > 0 && (
          <Section title="Products hit">
            <div className="space-y-2">
              {impact.products.map((p) => (
                <div key={p.product} className="text-xs">
                  <div className="mb-1 flex justify-between gap-2">
                    <span className="truncate text-ink-200">{p.product}</span>
                    <span className="shrink-0 num text-ink-100">{p.lost_revenue}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/[0.04]">
                    <div className="h-full rounded-full bg-gradient-to-r from-signal-500 to-alarm-500" style={{ width: `${(money(p.lost_revenue) / maxLost) * 100}%` }} />
                  </div>
                  <div className="mt-0.5 text-[11px] text-ink-500 num">
                    {p.lost_units.toLocaleString()} units · from day {p.first_impact_in_days} · {p.after_mitigation} after mitigation
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {impact.mitigations.length > 0 && (
          <Section title="Recommended actions">
            <ol className="space-y-2">
              {impact.mitigations.slice(0, 6).map((m, i) => (
                <li key={i} className="flex gap-2.5 text-xs">
                  <span className="grid size-5 shrink-0 place-items-center rounded-md bg-tide-500/15 text-[10px] font-semibold text-tide-300 num">{i + 1}</span>
                  <div>
                    <div className="font-medium text-ink-100">{m.action}</div>
                    <div className="text-ink-400">{m.detail}</div>
                    {m.cost && <div className="text-[11px] text-signal-400/80">{m.cost}</div>}
                  </div>
                </li>
              ))}
            </ol>
          </Section>
        )}
      </div>

      {impact.top_orders_at_risk.length > 0 && (
        <Section title="Orders at risk">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase tracking-wider text-ink-500">
                <tr className="border-b hairline">
                  <th className="py-1.5 text-start font-medium">Customer</th>
                  <th className="text-start font-medium">Product</th>
                  <th className="text-end font-medium">Value</th>
                  <th className="text-end font-medium">Slip</th>
                  <th className="text-end font-medium">Penalty</th>
                  <th className="pe-1 text-end font-medium">FM</th>
                </tr>
              </thead>
              <tbody>
                {impact.top_orders_at_risk.map((o) => (
                  <tr key={o.order} className="border-b hairline last:border-0">
                    <td className="py-1.5 pe-2 text-ink-200">
                      {o.customer}
                      <div className="text-[10px] text-ink-500 num">
                        {o.order} · due {o.due}
                      </div>
                    </td>
                    <td className="pe-2 text-ink-300">{o.product}</td>
                    <td className="text-end num text-ink-100">{o.value}</td>
                    <td className="text-end num text-signal-400">{o.slip_days}d</td>
                    <td className="text-end num text-ink-200">{o.penalty}</td>
                    <td className="pe-1 text-end">
                      {o.force_majeure ? <ShieldCheck size={14} className="ms-auto text-tide-400" /> : <ShieldAlert size={14} className="ms-auto text-alarm-400" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {impact.lanes.length > 0 && (
        <Section title="Shipping lanes">
          <div className="space-y-1.5">
            {impact.lanes.slice(0, 6).map((l, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <Ship size={12} className={l.blocked ? "text-alarm-400" : "text-signal-400"} />
                <span className="truncate text-ink-200">{l.lane}</span>
                <span className="ms-auto shrink-0 num text-ink-300">
                  +{l.added_days}d{l.extra_cost_pct ? ` · +${Math.round(l.extra_cost_pct)}% cost` : ""}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {impact.market_signals.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {impact.market_signals.map((m) => (
            <span key={m} className="inline-flex items-center gap-1 rounded-lg bg-violet-400/10 px-2 py-1 text-[11px] text-violet-400">
              <Sparkles size={11} />
              {m}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const tones = {
  alarm: "from-alarm-500/20 text-alarm-400",
  signal: "from-signal-500/20 text-signal-400",
  tide: "from-tide-500/20 text-tide-400",
  violet: "from-violet-400/20 text-violet-400",
};

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: keyof typeof tones }) {
  return (
    <div className={clsx("rounded-xl border hairline bg-gradient-to-b to-transparent p-3", tones[tone].split(" ")[0])}>
      <div className="text-[10px] font-medium uppercase tracking-wider text-ink-400">{label}</div>
      <div className={clsx("mt-1 text-xl font-semibold num", tones[tone].split(" ")[1])}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-ink-400">{sub}</div>}
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border hairline bg-white/[0.015] p-3">
      <div className="mb-2.5 flex items-baseline justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-300">{title}</div>
        {hint && <div className="text-[10px] text-ink-500">{hint}</div>}
      </div>
      {children}
    </div>
  );
}
