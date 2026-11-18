export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ------------------------------------------------------------------ types
export interface Site {
  id: string;
  kind: "Factory" | "Warehouse";
  name: string;
  lat: number;
  lon: number;
  ours: boolean;
  owner: string | null;
  tier: number | null;
}
export interface Port {
  id: string;
  name: string;
  name_ar?: string;
  lat: number;
  lon: number;
  congestion?: number;
}
export interface Chokepoint {
  id: string;
  name: string;
  name_ar: string;
  lat: number;
  lon: number;
  share_of_global_trade_pct: number;
}
export interface Lane {
  id: string;
  name: string;
  mode: "sea" | "air" | "road" | "rail";
  contingency: boolean;
  transit_days: number;
  from: string;
  to: string;
  via: string[];
  shippers: string[];
  path: [number, number][];
}
export interface Supplier {
  id: string;
  name: string;
  tier: number;
  country: string;
  health: string;
  category: string;
  site: string | null;
}
export interface Customer {
  id: string;
  name: string;
  country: string;
  region: string;
  strategic: boolean;
  port: string | null;
}
export interface Overview {
  company: { id: string; name: string; annual_revenue_usd: number };
  sites: Site[];
  ports: Port[];
  chokepoints: Chokepoint[];
  lanes: Lane[];
  suppliers: Supplier[];
  customers: Customer[];
  products: { id: string; name: string; family: string; price: number }[];
  kpis: {
    suppliers: number;
    customers: number;
    lanes: number;
    open_orders: number;
    open_order_value_usd: number;
    active_risks: number;
  };
}

export interface RiskEvent {
  id: string;
  title: string;
  title_ar?: string;
  type: string;
  status: "active" | "forecast" | "resolved";
  severity: number;
  probability: number;
  start_date: string;
  expected_duration_days: number;
  affects: string[];
}

export interface ImpactSummary {
  as_of: string;
  headline: {
    lost_revenue: string;
    lost_revenue_after_mitigation: string;
    orders_at_risk: number;
    order_value_at_risk: string;
    penalty_exposure: string;
    penalties_without_force_majeure: string;
    lanes_affected: number;
    lanes_blocked: number;
    scenario_probability: number;
  };
  lanes: { lane: string; added_days: number; blocked: boolean; rerouted_via: string | null; extra_cost_pct: number }[];
  component_stockouts: {
    component: string;
    factory: string;
    days_of_cover: number;
    stockout_in_days: number;
    shortage_days: number;
    with_mitigation_stockout_in_days: number | null;
    why: string;
  }[];
  products: {
    product: string;
    first_impact_in_days: number;
    lost_units: number;
    lost_revenue: string;
    after_mitigation: string;
  }[];
  top_orders_at_risk: {
    order: string;
    customer: string;
    product: string;
    due: string;
    value: string;
    slip_days: number;
    reason: string;
    penalty: string;
    force_majeure: boolean;
  }[];
  mitigations: { action: string; detail: string; cost: string | null }[];
  market_signals: string[];
  assumptions: string[];
  ui: {
    type: "impact";
    highlight: string[];
    report: { totals: Record<string, number>; disruptions: { target: string; impact: string; duration_days: number }[] };
  };
}

export interface Structural {
  single_points: {
    item: string;
    supplier: string;
    tier: number;
    country: string;
    qualified_alternative: boolean;
    revenue_dependent: string;
    products: number;
  }[];
  hidden_dependencies: { upstream: string; health: string; explanation: string }[];
  concentration: { dimension: string; name: string; share_of_inbound_lanes_pct: number; suppliers: number }[];
  ui: { highlight: string[] };
}

export interface Health {
  version: string;
  graph: { ok: boolean; nodes?: number; error?: string };
  llm: { provider: string; configured: boolean; reasoning: string; fast: string };
}

export interface Disruption {
  target: string;
  impact: "closure" | "delay" | "capacity_reduction" | "insolvency";
  duration_days: number;
  magnitude?: number;
  added_days?: number | null;
}

export type AgentEvent =
  | { type: "thread"; thread_id: string }
  | { type: "status"; stage: string; specialist?: string }
  | { type: "route"; language: string; task: string; specialists: string[]; direct: boolean }
  | { type: "tool_start"; specialist: string; id: string; tool: string; args: Record<string, unknown> }
  | {
      type: "tool_end";
      specialist: string;
      id: string;
      tool: string;
      ok: boolean;
      seconds: number;
      ui?: { type: string; highlight?: string[]; report?: unknown; summary?: unknown } | null;
    }
  | { type: "finding"; specialist: string; seconds: number; tool_calls: number }
  | { type: "spoken"; text: string }
  | { type: "token"; text: string }
  | { type: "answer"; answer: string; spoken: string; language: string; highlight: string[] }
  | { type: "error"; message: string }
  | { type: "done" };

// ------------------------------------------------------------------ fetchers
async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/api/health"),
  overview: () => get<Overview>("/api/overview"),
  risks: () => get<{ events: RiskEvent[] }>("/api/risks"),
  structural: () => get<Structural>("/api/structural"),
  graph: (ids: string[], hops = 1) =>
    get<{ nodes: { id: string; label: string; name: string }[]; edges: { source: string; target: string; type: string }[] }>(
      `/api/graph?ids=${encodeURIComponent(ids.join(","))}&hops=${hops}`,
    ),
  entity: (id: string) => get<{ labels: string[]; properties: Record<string, unknown>; neighbours: unknown[] }>(
    `/api/entity/${encodeURIComponent(id)}`,
  ),
  scenario: async (body: { event_ids?: string[]; disruptions?: Disruption[]; duration_days?: number | null }) => {
    const res = await fetch(`${API_URL}/api/scenario`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return (await res.json()) as ImpactSummary;
  },
  transcribe: async (audio: Blob, language?: string) => {
    const form = new FormData();
    form.append("file", audio, "speech.webm");
    if (language) form.append("language", language);
    const res = await fetch(`${API_URL}/api/transcribe`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return (await res.json()) as { text: string; language?: string };
  },
};

/** POST a chat message and yield server-sent events as they arrive. */
export async function* streamChat(message: string, threadId?: string, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Chat failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = raw.split("\n").find((l) => l.startsWith("data:"));
      if (line) yield JSON.parse(line.slice(5).trim()) as AgentEvent;
    }
  }
}

// ------------------------------------------------------------------ format
export const usd = (v: number) =>
  Math.abs(v) >= 1e9
    ? `$${(v / 1e9).toFixed(2)}B`
    : Math.abs(v) >= 1e6
      ? `$${(v / 1e6).toFixed(1)}M`
      : Math.abs(v) >= 1e3
        ? `$${(v / 1e3).toFixed(0)}k`
        : `$${v.toFixed(0)}`;
