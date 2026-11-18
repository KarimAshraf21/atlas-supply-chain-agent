"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { api } from "@/lib/api";
import { useAtlas } from "@/lib/store";

const COLORS: Record<string, string> = {
  Supplier: "#38bdf8",
  Company: "#2dd4bf",
  Customer: "#a78bfa",
  Factory: "#2dd4bf",
  Warehouse: "#5eead4",
  Component: "#fbbf24",
  Material: "#f59e0b",
  Product: "#fb7185",
  Chokepoint: "#f43f5e",
  Port: "#6f7ba3",
  ShippingLane: "#45527c",
  RiskEvent: "#f43f5e",
  Contract: "#c6cde6",
  SalesOrder: "#9aa4c7",
  Document: "#e6e9f5",
  Country: "#2a3760",
  LogisticsProvider: "#6f7ba3",
  Tariff: "#fb7185",
};

interface GNode {
  id: string;
  label: string;
  name: string;
  seed: boolean;
  x?: number;
  y?: number;
}
interface GLink {
  source: string | GNode;
  target: string | GNode;
  type: string;
}

const DEFAULT_SEEDS = ["SUP-DAEGU", "SUP-FORMOSIC", "CMP-SICMOS", "CMP-LFPCELL"];

export default function GraphPanel() {
  const { highlight, setFocus, focus } = useAtlas();
  const wrap = useRef<HTMLDivElement>(null);
  const fg = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [data, setData] = useState<{ nodes: GNode[]; links: GLink[] }>({ nodes: [], links: [] });
  const [hover, setHover] = useState<string | null>(null);
  const fitted = useRef(false);

  const seeds = useMemo(() => {
    const ids = highlight
      .filter((id) => /^(SUP|CMP|MAT|PRD|FAC|RE|ORG)-/.test(id) || /^[A-Z_]+$/.test(id))
      .filter((id) => !id.startsWith("FAC-") || ["FAC-SOKHNA", "FAC-10RAM", "FAC-TANGIER"].includes(id))
      .slice(0, 12);
    return ids.length ? ids : DEFAULT_SEEDS;
  }, [highlight]);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .graph(seeds, 1)
      .then((g) => {
        if (cancelled) return;
        const seedSet = new Set(seeds);
        const noise = new Set(["SalesOrder", "Document", "Country", "ShippingLane", "Port", "LogisticsProvider", "Contract"]);
        const keep = g.nodes.filter((n) => !noise.has(n.label) || seedSet.has(n.id));
        const ids = new Set(keep.map((n) => n.id));
        setData({
          nodes: keep.map((n) => ({ ...n, seed: seedSet.has(n.id) })),
          links: g.edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ ...e })),
        });
        fg.current?.d3Force("charge")?.strength(-160);
        fg.current?.d3Force("link")?.distance(46);
        fitted.current = false;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [seeds]);

  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const l of data.links) {
      const s = typeof l.source === "string" ? l.source : l.source.id;
      const t = typeof l.target === "string" ? l.target : l.target.id;
      if (!m.has(s)) m.set(s, new Set());
      if (!m.has(t)) m.set(t, new Set());
      m.get(s)!.add(t);
      m.get(t)!.add(s);
    }
    return m;
  }, [data]);

  const active = hover ?? focus;
  const isLit = (id: string) => !active || id === active || neighbours.get(active)?.has(id);

  return (
    <div ref={wrap} className="relative h-full w-full overflow-hidden rounded-2xl bg-ink-950/60">
      <ForceGraph2D<GNode, GLink>
        ref={fg}
        width={size.w}
        height={size.h}
        graphData={data}
        backgroundColor="rgba(0,0,0,0)"
        cooldownTicks={120}
        onEngineStop={() => {
          if (!fitted.current) {
            fitted.current = true;
            fg.current?.zoomToFit(500, 70);
          }
        }}
        linkColor={(l) => {
          const s = typeof l.source === "string" ? l.source : l.source.id;
          const t = typeof l.target === "string" ? l.target : l.target.id;
          return active && (s === active || t === active) ? "rgba(251,191,36,0.7)" : "rgba(154,164,199,0.14)";
        }}
        linkWidth={(l) => {
          const s = typeof l.source === "string" ? l.source : l.source.id;
          return active && s === active ? 1.6 : 0.6;
        }}
        linkDirectionalParticles={(l) => {
          const s = typeof l.source === "string" ? l.source : l.source.id;
          const t = typeof l.target === "string" ? l.target : l.target.id;
          return active && (s === active || t === active) ? 2 : 0;
        }}
        linkDirectionalParticleColor={() => "#fbbf24"}
        linkDirectionalParticleWidth={2}
        onNodeHover={(n) => setHover(n?.id ?? null)}
        onNodeClick={(n) => setFocus(n.id)}
        nodeCanvasObject={(node, ctx, scale) => {
          const r = node.seed ? 6 : 4;
          const lit = isLit(node.id);
          const color = COLORS[node.label] ?? "#9aa4c7";
          ctx.globalAlpha = lit ? 1 : 0.15;
          if (node.seed) {
            ctx.beginPath();
            ctx.arc(node.x!, node.y!, r + 5, 0, 2 * Math.PI);
            ctx.fillStyle = `${color}22`;
            ctx.fill();
          }
          ctx.beginPath();
          ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.lineWidth = 1.2;
          ctx.strokeStyle = "#05080f";
          ctx.stroke();
          if (scale > 2.6 || node.seed || node.id === active || (active && neighbours.get(active)?.has(node.id))) {
            const label = node.name.length > 26 ? `${node.name.slice(0, 25)}…` : node.name;
            ctx.font = `${node.seed ? 600 : 400} ${11 / scale}px ui-sans-serif, system-ui, sans-serif`;
            ctx.textAlign = "center";
            ctx.fillStyle = lit ? "#e6e9f5" : "#45527c";
            ctx.fillText(label, node.x!, node.y! + r + 11 / scale);
          }
          ctx.globalAlpha = 1;
        }}
        nodePointerAreaPaint={(node, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x!, node.y!, 8, 0, 2 * Math.PI);
          ctx.fill();
        }}
      />
      <div className="panel absolute bottom-3 left-3 flex max-w-[70%] flex-wrap gap-x-3 gap-y-1 rounded-xl px-3 py-2 text-[11px] text-ink-300">
        {["Supplier", "Factory", "Component", "Material", "Product", "Customer", "Chokepoint", "RiskEvent"].map((l) => (
          <span key={l} className="flex items-center gap-1.5">
            <span className="size-2 rounded-full" style={{ background: COLORS[l] }} />
            {l}
          </span>
        ))}
      </div>
      <div className="panel absolute right-3 top-3 rounded-xl px-3 py-2 text-[11px] text-ink-400">
        {data.nodes.length} nodes · {data.links.length} relationships · {highlight.length ? "following the agent" : "watch list"}
      </div>
    </div>
  );
}
