# Atlas web app

Next.js 16 · React 19 · Tailwind 4 · MapLibre · react-force-graph · Motion.

```bash
npm install
npm run dev          # http://localhost:3000 (expects the API on :8000 — `atlas serve`)
```

Set `NEXT_PUBLIC_API_URL` to point at a different API.

- **Copilot** — streaming chat with a live trace of the agent's routing and tool calls; voice in English or Arabic
  (browser speech recognition, falling back to Whisper on Groq) and spoken answers.
- **World map** — real sea lanes routed through chokepoints; the agent's findings light up lanes, sites and
  chokepoints, and the map flies to them.
- **Scenario lab** — presets and a what-if builder that call the deterministic reasoning engine directly.
- **Risk radar** — risk events (EN/AR), hidden tier-2 dependencies, single points of failure, chokepoint concentration.
- **Knowledge graph** — force-directed view of whatever the agent is looking at.
