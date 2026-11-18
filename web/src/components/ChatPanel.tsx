"use client";

import clsx from "clsx";
import { AlertTriangle, ArrowUp, Check, Loader2, Mic, Square, Volume2, VolumeX, Wrench } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamChat, type AgentEvent, type ImpactSummary } from "@/lib/api";
import { useAtlas } from "@/lib/store";
import { useVoice } from "@/lib/useVoice";
import { VoiceOrb } from "./VoiceOrb";

interface Step {
  id: string;
  specialist: string;
  tool: string;
  args: Record<string, unknown>;
  done: boolean;
  ok?: boolean;
  seconds?: number;
}
interface Turn {
  id: string;
  role: "user" | "assistant";
  text: string;
  spoken?: string;
  language?: string;
  steps?: Step[];
  route?: { specialists: string[]; language: string };
  status?: string;
  error?: string;
  pending?: boolean;
}

const SUGGESTIONS = [
  "What does the Red Sea closure mean for our revenue?",
  "Where are we single-sourced, and what would an outage cost?",
  "Close the Suez Canal for 45 days — who gets hurt?",
  "Which customer contracts have no force-majeure protection?",
  "ما هي أكبر نقاط الضعف في سلسلة التوريد لدينا؟",
];

const TOOL_LABEL: Record<string, string> = {
  assess_risk_events: "Quantifying impact",
  simulate_scenario: "Simulating scenario",
  structural_risks: "Scanning structural risk",
  trace_dependencies: "Tracing dependencies",
  find_alternatives: "Finding alternatives",
  search_documents: "Searching documents",
  search_entities: "Resolving entities",
  get_entity: "Reading entity",
  list_risk_events: "Listing risk events",
  query_graph: "Querying the graph",
};

const isArabic = (s: string) => /[؀-ۿ]/.test(s);

export function ChatPanel() {
  const { setHighlight, setImpact, setTab, health } = useAtlas();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const threadRef = useRef<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const update = useCallback((id: string, fn: (t: Turn) => Turn) => {
    setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)));
  }, []);

  const voiceRef = useRef<ReturnType<typeof useVoice> | null>(null);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy) return;
      setInput("");
      setBusy(true);
      const aid = crypto.randomUUID();
      setTurns((ts) => [
        ...ts,
        { id: crypto.randomUUID(), role: "user", text: message },
        { id: aid, role: "assistant", text: "", steps: [], pending: true, status: "Understanding the question" },
      ]);
      abortRef.current = new AbortController();
      try {
        for await (const ev of streamChat(message, threadRef.current, abortRef.current.signal)) {
          handle(ev, aid);
        }
      } catch (e) {
        update(aid, (t) => ({ ...t, pending: false, error: (e as Error).message }));
      } finally {
        update(aid, (t) => ({ ...t, pending: false }));
        setBusy(false);
      }

      function handle(ev: AgentEvent, id: string) {
        switch (ev.type) {
          case "thread":
            threadRef.current = ev.thread_id;
            break;
          case "status":
            update(id, (t) => ({
              ...t,
              status: ev.stage === "routing" ? "Understanding the question" : ev.stage === "composing" ? "Writing the answer" : `Consulting ${ev.specialist} analyst`,
            }));
            break;
          case "route":
            update(id, (t) => ({ ...t, route: { specialists: ev.specialists, language: ev.language } }));
            break;
          case "tool_start":
            update(id, (t) => ({ ...t, steps: [...(t.steps ?? []), { id: ev.id, specialist: ev.specialist, tool: ev.tool, args: ev.args, done: false }] }));
            break;
          case "tool_end":
            update(id, (t) => ({ ...t, steps: (t.steps ?? []).map((s) => (s.id === ev.id ? { ...s, done: true, ok: ev.ok, seconds: ev.seconds } : s)) }));
            if (ev.ui?.highlight?.length) setHighlight(ev.ui.highlight);
            if (ev.ui?.type === "impact" && ev.ui.summary) {
              setImpact({ ...(ev.ui.summary as Omit<ImpactSummary, "ui">), ui: ev.ui as ImpactSummary["ui"] });
              setTab("map");
            }
            break;
          case "spoken":
            update(id, (t) => ({ ...t, spoken: ev.text }));
            if (autoSpeak) voiceRef.current?.speak(ev.text, isArabic(ev.text) ? "ar" : "en");
            break;
          case "token":
            update(id, (t) => ({ ...t, text: t.text + ev.text, status: undefined }));
            break;
          case "answer":
            update(id, (t) => ({ ...t, text: ev.answer, spoken: ev.spoken, language: ev.language, status: undefined }));
            if (ev.highlight?.length) setHighlight(ev.highlight);
            break;
          case "error":
            update(id, (t) => ({ ...t, error: ev.message, status: undefined }));
            break;
        }
      }
    },
    [busy, update, setHighlight, setImpact, setTab, autoSpeak],
  );

  const voice = useVoice(send);
  useEffect(() => {
    voiceRef.current = voice;
  }, [voice]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const llmMissing = health && !health.llm.configured;

  return (
    <section className="panel flex h-full min-h-0 flex-col rounded-2xl">
      {/* header with orb */}
      <div className="flex items-center gap-4 border-b hairline px-5 py-4">
        <VoiceOrb
          state={voice.state}
          level={voice.level}
          thinking={busy}
          size={60}
          onClick={() => (voice.state === "listening" ? voice.stop() : voice.state === "speaking" ? voice.silence() : voice.start())}
        />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold tracking-tight">Atlas Copilot</div>
          <div className="truncate text-xs text-ink-400">
            {voice.state === "listening"
              ? voice.interim || (voice.lang === "ar-EG" ? "أنا أستمع…" : "Listening…")
              : voice.state === "transcribing"
                ? "Transcribing…"
                : voice.state === "speaking"
                  ? "Speaking — tap the orb to stop"
                  : busy
                    ? "Reasoning over the knowledge graph…"
                    : "Tap the orb and ask, in English or Arabic"}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <div className="flex rounded-lg bg-white/5 p-0.5 text-[11px]">
            {(["en-US", "ar-EG"] as const).map((l) => (
              <button
                key={l}
                onClick={() => voice.setLang(l)}
                className={clsx("rounded-md px-2 py-1 transition", voice.lang === l ? "bg-white/10 text-ink-100" : "text-ink-400")}
              >
                {l === "en-US" ? "EN" : "ع"}
              </button>
            ))}
          </div>
          <button
            onClick={() => setAutoSpeak((v) => !v)}
            className="rounded-lg p-1.5 text-ink-400 transition hover:bg-white/5 hover:text-ink-100"
            aria-label={autoSpeak ? "Mute spoken answers" : "Speak answers aloud"}
          >
            {autoSpeak ? <Volume2 size={15} /> : <VolumeX size={15} />}
          </button>
        </div>
      </div>

      {llmMissing && (
        <div className="mx-4 mt-3 flex gap-2 rounded-xl border border-signal-500/25 bg-signal-500/10 px-3 py-2 text-xs text-signal-400">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>
            No LLM key configured — chat is disabled. Add <code className="num">GROQ_API_KEY</code> to <code className="num">.env</code>.
            The map, scenario simulator and risk radar work without it.
          </span>
        </div>
      )}

      {/* thread */}
      <div ref={scrollRef} className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          <div className="space-y-2 pt-2">
            <div className="px-1 text-xs font-medium uppercase tracking-wider text-ink-400">Try asking</div>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                dir={isArabic(s) ? "rtl" : "ltr"}
                onClick={() => send(s)}
                className="block w-full rounded-xl border hairline bg-white/[0.02] px-3 py-2.5 text-start text-sm text-ink-200 transition hover:border-tide-500/30 hover:bg-tide-500/[0.06]"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <AnimatePresence initial={false}>
          {turns.map((t) => (
            <motion.div key={t.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
              {t.role === "user" ? (
                <div className="flex justify-end">
                  <div dir={isArabic(t.text) ? "rtl" : "ltr"} className="max-w-[85%] rounded-2xl rounded-ee-md bg-tide-500/15 px-3.5 py-2 text-sm text-ink-100">
                    {t.text}
                  </div>
                </div>
              ) : (
                <AssistantTurn turn={t} onSpeak={() => t.spoken && voice.speak(t.spoken, t.language ?? "en")} />
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t hairline p-3"
      >
        <div className="flex items-end gap-2 rounded-xl border hairline bg-ink-950/60 p-1.5 focus-within:border-tide-500/40">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            dir="auto"
            placeholder="Ask about risks, scenarios, suppliers, contracts…"
            className="max-h-32 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-ink-100 placeholder:text-ink-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => (voice.state === "listening" ? voice.stop() : voice.start())}
            className={clsx("grid size-9 place-items-center rounded-lg transition", voice.state === "listening" ? "bg-alarm-500/20 text-alarm-400" : "text-ink-400 hover:bg-white/5 hover:text-ink-100")}
            aria-label="Voice input"
          >
            {voice.state === "listening" ? <Square size={14} /> : <Mic size={16} />}
          </button>
          <button
            type="submit"
            disabled={!input.trim() || busy}
            className="grid size-9 place-items-center rounded-lg bg-tide-500 text-ink-950 transition hover:bg-tide-400 disabled:bg-white/5 disabled:text-ink-500"
            aria-label="Send"
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowUp size={16} />}
          </button>
        </div>
      </form>
    </section>
  );
}

function AssistantTurn({ turn, onSpeak }: { turn: Turn; onSpeak: () => void }) {
  const rtl = turn.language === "ar" || isArabic(turn.text);
  return (
    <div className="space-y-2">
      {(turn.route || (turn.steps && turn.steps.length > 0)) && (
        <div className="rounded-xl border hairline bg-white/[0.02] px-3 py-2">
          {turn.route && turn.route.specialists.length > 0 && (
            <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-400">
              <span>Routing to</span>
              {turn.route.specialists.map((s) => (
                <span key={s} className="rounded-md bg-violet-400/10 px-1.5 py-0.5 font-medium capitalize text-violet-400">
                  {s}
                </span>
              ))}
              <span className="ms-auto uppercase">{turn.route.language}</span>
            </div>
          )}
          <div className="space-y-1">
            {turn.steps?.map((s) => (
              <div key={s.id} className="flex items-center gap-2 text-xs">
                {s.done ? (
                  s.ok ? <Check size={12} className="text-tide-400" /> : <AlertTriangle size={12} className="text-signal-400" />
                ) : (
                  <Loader2 size={12} className="animate-spin text-ink-400" />
                )}
                <Wrench size={11} className="text-ink-500" />
                <span className="text-ink-200">{TOOL_LABEL[s.tool] ?? s.tool}</span>
                <span className="truncate text-ink-500 num">{argSummary(s.args)}</span>
                {s.seconds !== undefined && <span className="ms-auto shrink-0 text-ink-500 num">{s.seconds.toFixed(1)}s</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {turn.status && turn.pending && !turn.text && (
        <div className="flex items-center gap-2 px-1 text-xs text-ink-400">
          <span className="shimmer h-1.5 w-16 rounded-full" />
          {turn.status}
        </div>
      )}

      {turn.spoken && (
        <button onClick={onSpeak} dir={rtl ? "rtl" : "ltr"} className="group flex w-full gap-2 rounded-xl bg-signal-500/[0.07] px-3 py-2 text-start text-[13px] italic text-signal-400/90 transition hover:bg-signal-500/[0.12]">
          <Volume2 size={14} className="mt-0.5 shrink-0 opacity-70 group-hover:opacity-100" />
          {turn.spoken}
        </button>
      )}

      {turn.text && (
        <div dir={rtl ? "rtl" : "ltr"} className="prose-atlas px-1">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.text}</ReactMarkdown>
        </div>
      )}

      {turn.error && (
        <div className="flex gap-2 rounded-xl border border-alarm-500/25 bg-alarm-500/10 px-3 py-2 text-xs text-alarm-400">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          {turn.error}
        </div>
      )}
    </div>
  );
}

function argSummary(args: Record<string, unknown>): string {
  const v = Object.values(args)[0];
  if (v === undefined) return "";
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 48 ? `${s.slice(0, 48)}…` : s;
}

export type { ImpactSummary };
