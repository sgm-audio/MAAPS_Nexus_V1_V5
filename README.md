# MAAPS Nexus V1-V5 (Isolated Build)

## Multi-Agent Audio Production System - Antigravity Edition

**NO n8n. NO Suno. Pure Python Agent Orchestration + HeartMuLa Integration.**

---

## Architecture Overview

This is a ground-up rebuild replacing n8n workflow orchestration with native Python agent nodes powered by a pub/sub message bus. All AI music generation references Suno have been replaced with **HeartMuLa**.

```
┌─────────────────────────────────────────────────────────────────┐
│                    MAAPS Nexus V1-V5 Stack                      │
├─────────────────────────────────────────────────────────────────┤
│  V5: API-fication Layer (Kong/Traefik Gateway)                  │
│  V4: Distributed Agent Mesh (Ray Cluster)                       │
│  V3: Sub-Sonic Mastering Chain (Demucs + LUFS Normalization)    │
│  V2: Ghost Outbound Engine (Lead Gen + Voice Personalization)   │
│  V1: CI/CD Umbilical (GitOps Zero-Downtime Deploys)             │
├─────────────────────────────────────────────────────────────────┤
│                 Core Infrastructure                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Postgres │ │ Qdrant  │ │Selenium │ │  GPU    │ │ Agent   │   │
│  │  (DB)   │ │ (RAG)   │ │(Scraper)│ │ Worker  │ │Orchestr.│   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase Breakdown

### V1: CI/CD Umbilical (Zero-Downtime Deployments)
- GitHub webhook → Agent Orchestrator
- Auto git pull, container rebuild, hot-reload FastAPI
- No SSH required for deployments

### V2: Ghost Outbound Engine (Sell by Chat at Scale)
- Selenium scrapes leads (Realtor.ca, etc.)
- LLM summarizes lead bios
- HeartMuLa generates personalized voice clones
- Auto-email MP3 pitches

### V3: Sub-Sonic Mastering Chain (DSP Automation)
- Demucs v4 stem separation
- BS.1770 LUFS normalization to -14 LUFS
- Auto-export to SGM Studios network drive

### V4: Distributed Agent Mesh (Ray Cluster)
- Replace single FastAPI with Ray actors
- Concurrent agent execution across GPU VRAM pool
- Enterprise-scale job handling

### V5: API-fication (SaaS Moat)
- Kong/Traefik API gateway
- Public REST API for external clients
- Transition from operator to platform founder

---

## Quick Start

```bash
# 1. Clone and enter
cd d:\hivyr\MAAPS_Nexus_V1_V5

# 2. Start infrastructure
docker-compose up -d

# 3. Verify services
docker ps

# 4. Run orchestrator
python -m agents.orchestrator
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Orchestration** | Python Agent Nodes (pub/sub) |
| **Database** | PostgreSQL 16 |
| **Vector Memory** | Qdrant |
| **GPU Inference** | PyTorch + FastAPI |
| **Scraping** | Selenium Grid |
| **AI Music** | HeartMuLa |
| **Mastering** | Demucs v4 + Pedalboard |

---

## License

Proprietary - Hivyr / SGM Studios
