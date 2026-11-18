"use client";

import { motion } from "motion/react";
import type { VoiceState } from "@/lib/useVoice";

const palette: Record<VoiceState | "thinking", [string, string]> = {
  idle: ["#2dd4bf", "#a78bfa"],
  listening: ["#5eead4", "#38bdf8"],
  transcribing: ["#a78bfa", "#38bdf8"],
  thinking: ["#a78bfa", "#f59e0b"],
  speaking: ["#fbbf24", "#2dd4bf"],
};

export function VoiceOrb({
  state,
  level,
  thinking,
  size = 72,
  onClick,
}: {
  state: VoiceState;
  level: number;
  thinking: boolean;
  size?: number;
  onClick?: () => void;
}) {
  const mode = thinking && state === "idle" ? "thinking" : state;
  const [a, b] = palette[mode];
  const active = mode !== "idle";
  const scale = 1 + (state === "listening" ? level * 0.35 : 0);

  return (
    <button
      onClick={onClick}
      aria-label={state === "listening" ? "Stop listening" : "Talk to Atlas"}
      className="relative grid place-items-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-tide-400"
      style={{ width: size, height: size }}
    >
      {/* aura */}
      <motion.span
        className="absolute inset-0 rounded-full"
        style={{ background: `radial-gradient(circle, ${a}55 0%, transparent 70%)` }}
        animate={{ scale: active ? [1.1, 1.45, 1.1] : [1, 1.15, 1], opacity: active ? [0.8, 0.35, 0.8] : [0.45, 0.25, 0.45] }}
        transition={{ duration: active ? 1.6 : 4, repeat: Infinity, ease: "easeInOut" }}
      />
      {/* core */}
      <motion.span
        className="absolute rounded-full"
        style={{
          inset: size * 0.14,
          background: `conic-gradient(from 0deg, ${a}, ${b}, ${a})`,
          filter: "blur(0.5px)",
          boxShadow: `0 0 30px ${a}66, inset 0 0 18px rgba(0,0,0,.35)`,
        }}
        animate={{ rotate: 360, scale }}
        transition={{ rotate: { duration: mode === "thinking" ? 2.2 : 9, repeat: Infinity, ease: "linear" }, scale: { duration: 0.08 } }}
      />
      {/* glass */}
      <span
        className="absolute rounded-full"
        style={{
          inset: size * 0.2,
          background: "radial-gradient(circle at 35% 30%, rgba(255,255,255,.55), rgba(255,255,255,.05) 45%, rgba(5,8,15,.35) 100%)",
        }}
      />
    </button>
  );
}
