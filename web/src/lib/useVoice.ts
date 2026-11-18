"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export type VoiceState = "idle" | "listening" | "transcribing" | "speaking";
export type VoiceLang = "en-US" | "ar-EG";

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
}

function getRecognition(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as (new () => SpeechRecognitionLike) | null;
}

/**
 * Voice I/O. Speech-to-text uses the browser's recogniser when available (instant, free) and falls back to
 * recording + server-side Whisper. Text-to-speech uses the platform's voices (Arabic and English).
 */
export function useVoice(onFinal: (text: string) => void) {
  const [state, setState] = useState<VoiceState>("idle");
  const [interim, setInterim] = useState("");
  const [level, setLevel] = useState(0);
  const [lang, setLang] = useState<VoiceLang>("en-US");
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef(0);
  const onFinalRef = useRef(onFinal);
  useEffect(() => {
    onFinalRef.current = onFinal;
  }, [onFinal]);

  const stopMeter = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setLevel(0);
  }, []);

  const startMeter = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) sum += ((v - 128) / 128) ** 2;
      setLevel(Math.min(1, Math.sqrt(sum / data.length) * 4));
      rafRef.current = requestAnimationFrame(tick);
    };
    tick();
    return stream;
  }, []);

  const start = useCallback(async () => {
    window.speechSynthesis?.cancel();
    setInterim("");
    const Rec = getRecognition();
    try {
      const stream = await startMeter();
      if (Rec) {
        const rec = new Rec();
        rec.lang = lang;
        rec.interimResults = true;
        rec.continuous = false;
        let finalText = "";
        rec.onresult = (e) => {
          let text = "";
          for (let i = 0; i < e.results.length; i++) {
            text += e.results[i][0].transcript;
            if (e.results[i].isFinal) finalText = text;
          }
          setInterim(text);
        };
        rec.onend = () => {
          stopMeter();
          setState("idle");
          if (finalText.trim()) onFinalRef.current(finalText.trim());
        };
        rec.onerror = () => {
          stopMeter();
          setState("idle");
        };
        recRef.current = rec;
        rec.start();
      } else {
        const rec = new MediaRecorder(stream);
        const chunks: Blob[] = [];
        rec.ondataavailable = (e) => chunks.push(e.data);
        rec.onstop = async () => {
          stopMeter();
          setState("transcribing");
          try {
            const { text } = await api.transcribe(new Blob(chunks, { type: rec.mimeType }), lang.slice(0, 2));
            if (text.trim()) onFinalRef.current(text.trim());
          } finally {
            setState("idle");
          }
        };
        mediaRef.current = rec;
        rec.start();
      }
      setState("listening");
    } catch {
      stopMeter();
      setState("idle");
    }
  }, [lang, startMeter, stopMeter]);

  const stop = useCallback(() => {
    recRef.current?.stop();
    if (mediaRef.current?.state === "recording") mediaRef.current.stop();
  }, []);

  const speak = useCallback((text: string, language: string) => {
    const synth = window.speechSynthesis;
    if (!synth || !text) return;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const want = language.startsWith("ar") ? "ar" : "en";
    const voices = synth.getVoices().filter((v) => v.lang.toLowerCase().startsWith(want));
    u.voice = voices.find((v) => /natural|premium|enhanced|google/i.test(v.name)) ?? voices[0] ?? null;
    u.lang = want === "ar" ? "ar-EG" : "en-US";
    u.rate = 1.03;
    u.onstart = () => setState("speaking");
    u.onend = () => setState("idle");
    u.onerror = () => setState("idle");
    synth.speak(u);
  }, []);

  const silence = useCallback(() => {
    window.speechSynthesis?.cancel();
    setState("idle");
  }, []);

  useEffect(() => () => stopMeter(), [stopMeter]);

  return { state, interim, level, lang, setLang, start, stop, speak, silence };
}
