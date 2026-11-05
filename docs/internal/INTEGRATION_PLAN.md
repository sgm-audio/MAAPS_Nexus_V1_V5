# Integration Plan: D:\[Agent 0] → MAAPS Nexus V1-V5

## Overview
Three independent migrations from the Agent 0 prototype into the production MAAPS codebase.

---

## Commit 1: Scraper Migration (Playwright + Groq/Llama 3)

**Files to Modify:**
- `agents/scraper_agent.py` — Full replacement
- `requirements.txt` — Add `playwright`, `groq`, `beautifulsoup4`, `lxml`
- Remove Selenium dependency

**New Capabilities:**
- Playwright-based Google Maps scraping (10x faster, more reliable)
- Groq API (free Llama 3 70B) for AI qualification
- Deep scan: finds contact pages, extracts emails
- Hunter-Killer logic: qualifies/rejects in single pass
- Returns structured leads with: segment, hook, email, confidence

**Architecture:**
```
SCRAPER_JOB_START → Playwright scrape → Groq qualification → SCRAPER_LEADS_FOUND
```

**Breaking Changes:**
- Input payload: `{"target": "realtor", "url": "..."}` → `{"query": "Audio Post Production Studio in Los Angeles", "max_results": 8}`
- Output: `leads` array now includes `segment`, `hook`, `email`, `confidence`

---

## Commit 2: Outbound Migration (4 Variants + Tracking)

**Files to Modify:**
- `agents/outbound_agent.py` — Replace templates, add tracking
- `core/config.py` — Add tracking config
- `requirements.txt` — Add `jinja2`

**New Capabilities:**
- 4 email variants (A: Advice, B: Margin Killer, C: Architect, D: Founding Seat)
- Burn rate calculation (quantifies manual QC cost)
- Tracking pixels (open rates)
- UTM parameters (attribution)
- Jinja2 rendering with full context
- A/B test rotation via campaign config

**Architecture:**
```
Campaign config: {"variant": "variant_b_margin", "rotation": "sequential"}
OUTBOUND_LEAD_PROCESS → render_email() → SMTP send + pixel log
```

**Breaking Changes:**
- Campaign payload adds `variant`, `rotation`, `sender`, `loom_url`
- Lead processing uses `hook`, `segment`, `volume` from scraper

---

## Commit 3: WebSocket Telemetry (60Hz Dashboard)

**Files to Modify:**
- `audio_worker/server.py` — Add `/ws/monitor` endpoint
- `core/message.py` — Add telemetry message types
- `core/topics.py` — Add `SYSTEM_TELEMETRY`, `AGENT_METRICS`
- `scripts/monitor.sh` — Deprecate in favor of WebSocket dashboard

**New Capabilities:**
- 60Hz WebSocket stream: CPU, agent status, queue depth, latency
- Real-time agent registry with circuit breaker state
- Compatible with Grafana/Grafana Live or custom dashboard
- Replaces `scripts/monitor.sh` polling

**Architecture:**
```
WebSocket /ws/monitor → system_bus.get_registered_agents() → JSON stream
```

---

## Dependencies Between Commits

| Commit | Depends On | Can Run In Parallel |
|--------|------------|---------------------|
| 1 (Scraper) | None | Yes |
| 2 (Outbound) | Commit 1 (uses scraper's `hook`, `segment`) | No |
| 3 (Telemetry) | None | Yes |

---

## Testing Strategy

Each commit includes:
- Unit tests for new logic
- Integration test for message flow
- Backwards compatibility check (old payloads still work)

---

## Rollback Plan

Each commit is atomic. To rollback:
```bash
git revert <commit-hash>
```

No database migrations required.

---

## Estimated Effort

| Commit | Lines Changed | Est. Time |
|--------|---------------|-----------|
| 1 Scraper | ~300 | 45 min |
| 2 Outbound | ~250 | 30 min |
| 3 Telemetry | ~150 | 30 min |
| **Total** | **~700** | **~2 hours** |