import type { Overview } from "./api";

type LngLat = [number, number];
const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

/** Great-circle interpolation between two points (n segments). */
function gc(a: LngLat, b: LngLat, n: number): LngLat[] {
  const [l1, p1] = [rad(a[0]), rad(a[1])];
  const [l2, p2] = [rad(b[0]), rad(b[1])];
  const d = 2 * Math.asin(Math.sqrt(Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2));
  if (d < 1e-6) return [a, b];
  const out: LngLat[] = [];
  for (let i = 0; i <= n; i++) {
    const f = i / n;
    const A = Math.sin((1 - f) * d) / Math.sin(d);
    const B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
    const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
    const z = A * Math.sin(p1) + B * Math.sin(p2);
    out.push([deg(Math.atan2(y, x)), deg(Math.atan2(z, Math.sqrt(x * x + y * y)))]);
  }
  return out;
}

/** Smooth a waypoint polyline and unwrap longitudes so lines never jump across the antimeridian. */
export function smoothPath(points: LngLat[]): LngLat[] {
  const out: LngLat[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const seg = gc(points[i], points[i + 1], 12);
    out.push(...(i === 0 ? seg : seg.slice(1)));
  }
  for (let i = 1; i < out.length; i++) {
    let lon = out[i][0];
    while (lon - out[i - 1][0] > 180) lon -= 360;
    while (lon - out[i - 1][0] < -180) lon += 360;
    out[i] = [lon, out[i][1]];
  }
  return out;
}

export interface GeoIndex {
  /** entity id -> coordinate (sites, ports, chokepoints; suppliers/customers resolved to their site/port) */
  point: Map<string, LngLat>;
  lanePaths: Map<string, LngLat[]>;
}

export function buildGeoIndex(o: Overview): GeoIndex {
  const point = new Map<string, LngLat>();
  for (const s of o.sites) point.set(s.id, [s.lon, s.lat]);
  for (const p of o.ports) point.set(p.id, [p.lon, p.lat]);
  for (const c of o.chokepoints) point.set(c.id, [c.lon, c.lat]);
  for (const s of o.suppliers) if (s.site && point.has(s.site)) point.set(s.id, point.get(s.site)!);
  for (const c of o.customers) if (c.port && point.has(c.port)) point.set(c.id, point.get(c.port)!);
  const lanePaths = new Map<string, LngLat[]>();
  for (const l of o.lanes) lanePaths.set(l.id, smoothPath(l.path));
  return { point, lanePaths };
}
