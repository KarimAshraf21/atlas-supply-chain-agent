"use client";

import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildGeoIndex } from "@/lib/geo";
import { useAtlas } from "@/lib/store";

const STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json";
type FC = GeoJSON.FeatureCollection;
const empty: FC = { type: "FeatureCollection", features: [] };

export default function MapView() {
  const { overview, highlight, setFocus, names, impact } = useAtlas();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [layers, setLayers] = useState({ inbound: true, outbound: true, contingency: false });

  const geo = useMemo(() => (overview ? buildGeoIndex(overview) : null), [overview]);

  // ------------------------------------------------------------------ init
  useEffect(() => {
    if (!container.current || mapRef.current) return;
    // the worker is served from /public (bundlers can't resolve maplibre's worker URL)
    maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");
    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [55, 22],
      zoom: 1.7,
      minZoom: 1.2,
      attributionControl: { compact: true },
      renderWorldCopies: true,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    mapRef.current = map;
    if (process.env.NODE_ENV === "development") (window as unknown as { __atlasMap: MLMap }).__atlasMap = map;
    map.on("load", () => {
      for (const id of ["lanes", "lanes-hl", "sites", "chokepoints", "ports", "hl-points"]) {
        map.addSource(id, { type: "geojson", data: empty });
      }
      map.addLayer({
        id: "lanes",
        type: "line",
        source: "lanes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["match", ["get", "kind"], "outbound", "#a78bfa", "contingency", "#6f7ba3", "#2dd4bf"],
          "line-opacity": ["case", ["get", "dim"], 0.07, 0.32],
          "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.6, 5, 1.6],
          "line-dasharray": ["case", ["==", ["get", "kind"], "contingency"], ["literal", [2, 2]], ["literal", [1, 0]]],
        },
      });
      map.addLayer({
        id: "lanes-hl-glow",
        type: "line",
        source: "lanes-hl",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#f59e0b", "line-width": 7, "line-opacity": 0.18, "line-blur": 4 },
      });
      map.addLayer({
        id: "lanes-hl",
        type: "line",
        source: "lanes-hl",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["case", ["get", "contingency"], "#5eead4", "#fbbf24"],
          "line-width": 2,
          "line-dasharray": [0, 4, 3],
        },
      });
      map.addLayer({
        id: "ports",
        type: "circle",
        source: "ports",
        paint: { "circle-radius": 2.2, "circle-color": "#6f7ba3", "circle-opacity": 0.7 },
      });
      map.addLayer({
        id: "sites",
        type: "circle",
        source: "sites",
        paint: {
          "circle-radius": ["case", ["get", "ours"], 6, 3.5],
          "circle-color": ["case", ["get", "ours"], "#2dd4bf", ["match", ["get", "tier"], 1, "#38bdf8", 2, "#a78bfa", "#f472b6"]],
          "circle-stroke-width": ["case", ["get", "ours"], 2, 0.5],
          "circle-stroke-color": ["case", ["get", "ours"], "#05080f", "rgba(5,8,15,0.6)"],
          "circle-opacity": ["case", ["get", "dim"], 0.25, 0.95],
        },
      });
      map.addLayer({
        id: "chokepoints-halo",
        type: "circle",
        source: "chokepoints",
        paint: {
          "circle-radius": ["case", ["get", "hit"], 18, 9],
          "circle-color": ["case", ["get", "hit"], "#f43f5e", "#f59e0b"],
          "circle-opacity": ["case", ["get", "hit"], 0.22, 0.08],
          "circle-blur": 0.6,
        },
      });
      map.addLayer({
        id: "chokepoints",
        type: "circle",
        source: "chokepoints",
        paint: {
          "circle-radius": 4,
          "circle-color": ["case", ["get", "hit"], "#f43f5e", "#f59e0b"],
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#05080f",
        },
      });
      map.addLayer({
        id: "chokepoint-labels",
        type: "symbol",
        source: "chokepoints",
        layout: {
          "text-field": ["get", "name"],
          "text-size": 10.5,
          "text-offset": [0, 1.2],
          "text-anchor": "top",
          "text-font": ["Open Sans Semibold", "Noto Sans Regular"],
        },
        paint: { "text-color": ["case", ["get", "hit"], "#fb7185", "#c6cde6"], "text-halo-color": "#05080f", "text-halo-width": 1.4 },
      });
      map.addLayer({
        id: "hl-points",
        type: "circle",
        source: "hl-points",
        paint: {
          "circle-radius": 8,
          "circle-color": "transparent",
          "circle-stroke-color": "#fbbf24",
          "circle-stroke-width": 1.5,
          "circle-stroke-opacity": 0.9,
        },
      });

      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
      for (const layer of ["sites", "chokepoints", "ports", "lanes-hl"]) {
        map.on("mousemove", layer, (e) => {
          const f = e.features?.[0];
          if (!f) return;
          map.getCanvas().style.cursor = "pointer";
          const p = f.properties as Record<string, string>;
          popup
            .setLngLat(e.lngLat)
            .setHTML(
              `<div style="font-weight:600">${p.name}</div>${p.name_ar ? `<div dir="rtl" style="opacity:.75">${p.name_ar}</div>` : ""}<div style="opacity:.6;font-size:11px;margin-top:2px">${p.sub ?? ""}</div>`,
            )
            .addTo(map);
        });
        map.on("mouseleave", layer, () => {
          map.getCanvas().style.cursor = "";
          popup.remove();
        });
        map.on("click", layer, (e) => {
          const id = (e.features?.[0]?.properties as { id?: string })?.id;
          if (id) setFocus(id);
        });
      }
      setReady(true);
    });

    // marching-ants animation on highlighted lanes
    const seq = [
      [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0],
      [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5],
    ];
    let step = 0;
    let raf = 0;
    let last = 0;
    const animate = (t: number) => {
      if (t - last > 60 && map.getLayer("lanes-hl")) {
        step = (step + 1) % seq.length;
        map.setPaintProperty("lanes-hl", "line-dasharray", seq[step]);
        const pulse = 14 + 6 * Math.sin(t / 380);
        map.setPaintProperty("chokepoints-halo", "circle-radius", ["case", ["get", "hit"], pulse, 9]);
        last = t;
      }
      raf = requestAnimationFrame(animate);
    };
    raf = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(raf);
      map.remove();
      mapRef.current = null;
    };
  }, [setFocus]);

  // ------------------------------------------------------------------ data
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !overview || !geo) return;
    const hl = new Set(highlight);
    const has = hl.size > 0;
    const ourSites = new Set(overview.sites.filter((s) => s.ours).map((s) => s.id));
    const supplierSite = new Map(overview.suppliers.map((s) => [s.site, s] as const));

    const lanes: GeoJSON.Feature[] = [];
    const lanesHl: GeoJSON.Feature[] = [];
    for (const l of overview.lanes) {
      const outbound = l.shippers.some((s) => ourSites.has(s));
      const kind = l.contingency ? "contingency" : outbound ? "outbound" : "inbound";
      const coords = geo.lanePaths.get(l.id)!;
      const isHl = hl.has(l.id);
      if (isHl) {
        lanesHl.push({ type: "Feature", properties: { id: l.id, name: l.name, contingency: l.contingency,
          sub: `${l.transit_days} days · ${l.mode}` }, geometry: { type: "LineString", coordinates: coords } });
      }
      if ((kind === "contingency" && !layers.contingency) || (kind === "inbound" && !layers.inbound) || (kind === "outbound" && !layers.outbound)) continue;
      if (l.mode === "air") continue;
      lanes.push({ type: "Feature", properties: { id: l.id, kind, dim: has && !isHl }, geometry: { type: "LineString", coordinates: coords } });
    }
    const sites: GeoJSON.Feature[] = overview.sites.map((s) => {
      const sup = supplierSite.get(s.id);
      const isHl = hl.has(s.id) || (sup ? hl.has(sup.id) : false);
      return {
        type: "Feature",
        properties: { id: sup?.id ?? s.id, name: sup?.name ?? s.name, ours: s.ours, tier: s.tier ?? 0, dim: has && !isHl,
          sub: s.ours ? `Nilewave · ${s.kind}` : sup ? `Tier ${sup.tier} · ${sup.category} · ${sup.health}` : s.kind },
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      };
    });
    const chokes: GeoJSON.Feature[] = overview.chokepoints.map((c) => ({
      type: "Feature",
      properties: { id: c.id, name: c.name, name_ar: c.name_ar, hit: hl.has(c.id), sub: `${c.share_of_global_trade_pct}% of global trade` },
      geometry: { type: "Point", coordinates: [c.lon, c.lat] },
    }));
    const ports: GeoJSON.Feature[] = overview.ports.map((p) => ({
      type: "Feature",
      properties: { id: p.id, name: p.name, name_ar: p.name_ar, sub: `Port · ${p.id}` },
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    }));
    const hlPoints: GeoJSON.Feature[] = [...hl]
      .filter((id) => geo.point.has(id) && !overview.chokepoints.some((c) => c.id === id))
      .map((id) => ({ type: "Feature", properties: { id, name: names.get(id) ?? id }, geometry: { type: "Point", coordinates: geo.point.get(id)! } }));

    (map.getSource("lanes") as GeoJSONSource).setData({ type: "FeatureCollection", features: lanes });
    (map.getSource("lanes-hl") as GeoJSONSource).setData({ type: "FeatureCollection", features: lanesHl });
    (map.getSource("sites") as GeoJSONSource).setData({ type: "FeatureCollection", features: sites });
    (map.getSource("chokepoints") as GeoJSONSource).setData({ type: "FeatureCollection", features: chokes });
    (map.getSource("ports") as GeoJSONSource).setData({ type: "FeatureCollection", features: ports });
    (map.getSource("hl-points") as GeoJSONSource).setData({ type: "FeatureCollection", features: hlPoints });

    // fit to highlighted geography
    const pts: [number, number][] = [
      ...lanesHl.flatMap((f) => (f.geometry as GeoJSON.LineString).coordinates as [number, number][]),
      ...hlPoints.map((f) => (f.geometry as GeoJSON.Point).coordinates as [number, number]),
    ];
    if (pts.length > 1) {
      const lons = pts.map((p) => p[0]);
      const lats = pts.map((p) => p[1]);
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], {
        padding: { top: 70, bottom: 60, left: 200, right: impact ? Math.min(480, map.getContainer().clientWidth * 0.6) + 30 : 60 }, maxZoom: 4.5, duration: 1400,
      });
    }
  }, [ready, overview, geo, highlight, layers, names, impact]);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl">
      <div ref={container} className="h-full w-full" />
      <div className="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/5" />
      <div className="absolute left-3 top-3 flex flex-col gap-2">
        <div className="panel rounded-xl px-3 py-2 text-[11px] text-ink-300">
          <div className="mb-1.5 font-medium uppercase tracking-wider text-ink-400">Legend</div>
          <Legend color="#2dd4bf" label="Nilewave plant" big />
          <Legend color="#38bdf8" label="Tier-1 supplier" />
          <Legend color="#a78bfa" label="Tier-2 supplier" />
          <Legend color="#f472b6" label="Tier-3 supplier" />
          <Legend color="#f59e0b" label="Chokepoint" />
        </div>
        <div className="panel flex gap-1 rounded-xl p-1 text-[11px]">
          {(["inbound", "outbound", "contingency"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setLayers((s) => ({ ...s, [k]: !s[k] }))}
              className={`rounded-lg px-2 py-1 capitalize transition ${layers[k] ? "bg-white/10 text-ink-100" : "text-ink-400 hover:text-ink-200"}`}
            >
              {k}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label, big }: { color: string; label: string; big?: boolean }) {
  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className="inline-block rounded-full" style={{ background: color, width: big ? 10 : 7, height: big ? 10 : 7 }} />
      {label}
    </div>
  );
}
