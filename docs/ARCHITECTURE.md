# MAAPS Nexus — Architecture

One page. The real structure, not the vision board.

## What actually runs

```
                    ┌──────────────────────┐
                    │   Orchestrator       │
                    │   main.py            │
                    │   MessageBus (pub/sub, in-process)
                    │   + 5 agents         │
                    └──────────┬───────────┘
                               │ HTTP (httpx)
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌────────────────┐    ┌───────────────┐
│ Audio Worker  │    │  Postgres      │    │  Qdrant       │
│ FastAPI:8000  │    │  :5432         │    │  :6333        │
│ GPU jobs + RAG│    │  state         │    │  vectors      │
└───────────────┘    └────────────────┘    └───────────────┘
```

- **MessageBus** (`core/message_bus.py`): in-process pub/sub, priority queues, wildcard topics, request/response correlation, TTL. Singleton per process. It is *not* a network bus — agents live in one process, by design. Distribution is V4's problem.
- **BaseAgent** (`core/base_agent.py`): lifecycle (setup → handle_message → teardown), typed publish/request/respond helpers. All five agents subclass it.
- **Audio Worker** (`audio_worker/server.py`): the only thing that touches GPU. Also serves `/ws/monitor` telemetry (60Hz) and `/status`.

## The agents

| Agent | Subscribes to | Does |
|-------|--------------|------|
| `orchestration_agent` | deploy.*, system.*, agent.register | GitHub webhook → git pull → hot reload. Agent registry. Health reports. |
| `scraper_agent` | scraper.job.start | Playwright + Google Maps → Groq/Llama-3 qualification (heuristic fallback) → `scraper.leads.found` |
| `outbound_agent` | outbound.*, scraper.leads.found | Personalizes (LLM → variant template → legacy), optional voice gen, SMTP send |
| `audio_worker_agent` | audio.* | Queues jobs, proxies to the FastAPI worker |
| `rag_agent` | rag.* | Chunks docs, BGE-M3 embeds, Qdrant upsert/search |

## Message flow (V2 outbound, end to end)

```
scraper.job.start
  → Playwright scrape + Groq qualify
  → scraper.leads.found
  → outbound_agent queues leads
  → per lead: LLM/template personalization (+ optional voice via audio worker)
  → SMTP send (tracking pixel in body)
  → outbound.complete {variant, lead_email}
```

## Design rules (enforced, not aspirational)

1. **No stubs.** If it returns fake data, it doesn't ship.
2. **Optional deps degrade to null, never 500.** psutil/torch/pynvml are all optional in telemetry.
3. **HTTPException must never be swallowed** by generic exception handlers (this bit us once — see `/process`).
4. **Getters return None legitimately — guard everything.**
5. **Every new agent gets tests.** `tests/test_<agent>.py`, message-bus fixtures, mocked bus.

## V4 — Titan (separate repo)

V4 is the distributed mesh: Ray actors replacing the in-process bus, concurrent agent execution across a GPU VRAM pool. The topic hooks (`mesh.actor.spawn`, `mesh.job.distribute`, `mesh.job.result`) exist in `core/topics.py` and are reserved.

**Titan lives at [sgm-audio/v4-titan](https://github.com/sgm-audio/v4-titan)** — mesh runtime *and* the audio domain (Auditor/Composer/Alchemist/Engineer consensus pipeline) ported out of this repo, with 47 tests. The former `maaps_v4/` folder was the same idea pre-extraction; its bugs (silent mastering no-ops, schema inconsistencies) are documented and fixed over there.

## V5 — API-fication

Public REST surface via Kong/Traefik in front of the orchestrator. Not started. The WebSocket telemetry (`/ws/monitor`, `/status`) is the first piece of observable surface — build the gateway around it.
