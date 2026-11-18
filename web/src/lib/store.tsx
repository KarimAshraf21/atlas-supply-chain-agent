"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type Health, type ImpactSummary, type Overview } from "./api";

export type Tab = "map" | "scenario" | "risks" | "graph";

interface AtlasState {
  overview: Overview | null;
  health: Health | null;
  error: string | null;
  highlight: string[];
  setHighlight: (ids: string[]) => void;
  impact: ImpactSummary | null;
  setImpact: (impact: ImpactSummary | null) => void;
  tab: Tab;
  setTab: (tab: Tab) => void;
  focus: string | null;
  setFocus: (id: string | null) => void;
  names: Map<string, string>;
}

const Ctx = createContext<AtlasState | null>(null);

export function AtlasProvider({ children }: { children: ReactNode }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlightState] = useState<string[]>([]);
  const [impact, setImpactState] = useState<ImpactSummary | null>(null);
  const [tab, setTab] = useState<Tab>("map");
  const [focus, setFocus] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.overview(), api.health()])
      .then(([o, h]) => {
        if (cancelled) return;
        setOverview(o);
        setHealth(h);
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const setHighlight = useCallback((ids: string[]) => setHighlightState([...new Set(ids)]), []);
  const setImpact = useCallback(
    (i: ImpactSummary | null) => {
      setImpactState(i);
      if (i) setHighlight(i.ui.highlight);
    },
    [setHighlight],
  );

  const names = useMemo(() => {
    const m = new Map<string, string>();
    if (!overview) return m;
    for (const list of [overview.sites, overview.ports, overview.chokepoints, overview.lanes, overview.suppliers,
      overview.customers, overview.products] as { id: string; name: string }[][]) {
      for (const x of list) m.set(x.id, x.name);
    }
    return m;
  }, [overview]);

  const value = useMemo<AtlasState>(
    () => ({ overview, health, error, highlight, setHighlight, impact, setImpact, tab, setTab, focus, setFocus, names }),
    [overview, health, error, highlight, setHighlight, impact, setImpact, tab, focus, names],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAtlas(): AtlasState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAtlas must be used inside <AtlasProvider>");
  return v;
}
