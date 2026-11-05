# MAAPS Nexus

**Multi-Agent Audio Production System.** Python agents on a pub/sub message bus. No n8n. No Suno. No babysitting.

This is proprietary infrastructure built by [SGM Studios](https://sgmstudios.ca). It runs audio pipelines (stem separation, loudness normalization, AI generation), lead-gen (scrape → qualify → personalized outreach), and a RAG knowledge base — as cooperating agents, not a pile of scripts.

---

## One command. That's the docs.

```bash
python run.py
```

That checks Docker, writes `.env` if you don't have one, boots the stack, waits for health, and tells you what's running. Double-click `start.bat` if you don't want a terminal.

Everything else:

```bash
python run.py status    # what's up, what's healthy
python run.py logs      # follow the logs
python run.py down      # stop everything
python run.py doctor    # why isn't it working
```

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/) and Python 3.10+. That's the list.

---

## The stack

| Piece | Job |
|-------|-----|
| **Agent Orchestrator** | Pub/sub message bus + agent lifecycle. Replaced n8n. |
| **GPU Audio Worker** | FastAPI + PyTorch. HeartMuLa generation, Demucs stems, RVC, BS.1770 LUFS. |
| **Hunter-Killer Scraper** | Playwright + Groq (Llama 3 70B). Scrapes, qualifies, extracts emails in one pass. |
| **Ghost Outbound** | 4 A/B email variants, open-rate pixels, burn-rate personalization, LLM copy. |
| **RAG Agent** | Qdrant + BGE-M3 embeddings. The system knows its own docs. |
| **Postgres** | State. |

Infrastructure: Docker Compose for single-box, Kubernetes manifests in `k8s/` when you outgrow it.

---

## The phases

- **V1 — CI/CD Umbilical.** GitHub webhook → git pull → hot reload. Ship without SSH.
- **V2 — Ghost Outbound Engine.** Leads in, personalized pitches out. *This works today.*
- **V3 — Sub-Sonic Mastering Chain.** Demucs + LUFS + auto-export. *This works today.*
- **V4 — Titan (Distributed Agent Mesh).** Ray cluster, concurrent agent execution. *Lives in its own repo.*
- **V5 — API-fication.** Public REST API. Operator → platform.

---

## For operators (me)

Setup/deploy history and checklists live in [`docs/internal/`](docs/internal/) — kept for the record, not for reading. The live docs are this file and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Tests: `python -m pytest tests/ -v`

## License

**Proprietary — SGM Studios.** All rights reserved. See [LICENSE](LICENSE). This is not open source, and it's not yours to fork.
