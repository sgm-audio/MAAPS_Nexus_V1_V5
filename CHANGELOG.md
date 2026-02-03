# MAAPS Nexus V1-V5 Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-02-03

### Added
- **Core Infrastructure**
  - `core/` module with `BaseAgent`, `MessageBus`, `Message`, `Topics`, `Priority`, `Config`
  - Singleton pub/sub `MessageBus` with priority queuing and wildcard subscriptions
  - Abstract `BaseAgent` class with lifecycle methods and request/response patterns

- **V1: CI/CD Umbilical**
  - `OrchestrationAgent` with GitHub webhook receiver
  - Automated git pull on push to main/master
  - Hot-reload signal broadcasting to agents
  - Deployment tracking and status publishing

- **V2: Ghost Outbound Engine**
  - `ScraperAgent` with Selenium Grid integration
  - Realtor.ca lead extraction (placeholder selectors)
  - `OutboundAgent` for campaign management
  - Lead personalization and email automation
  - Voice generation hook (HeartMuLa/ElevenLabs ready)

- **V3: Sub-Sonic Mastering Chain**
  - `AudioWorkerAgent` with GPU detection
  - Demucs v4 stem separation integration
  - BS.1770 LUFS normalization via pyloudnorm
  - HeartMuLa AI music generation (placeholder)
  - RVC voice cloning (placeholder)

- **RAG Knowledge Base**
  - `RAGAgent` with Qdrant vector storage
  - BGE-M3 embeddings for semantic search
  - Document chunking and indexing

- **Infrastructure**
  - `docker-compose.yml` with Postgres, Qdrant, Selenium, GPU Worker
  - `Dockerfile.orchestrator` for agent container
  - `init.sql` for database schema
  - `.env.example` with all configuration options

### Changed
- **Replaced n8n** with native Python agent orchestration
- **Replaced Suno** references with HeartMuLa throughout

### Removed
- All n8n workflow dependencies
- All Suno API references

## [Unreleased]

### Planned: V4 - Distributed Agent Mesh
- Ray cluster integration
- Agent-to-actor migration
- Concurrent GPU job handling

### Planned: V5 - API-fication
- Kong/Traefik API gateway
- Public REST API endpoints
- Rate limiting and authentication
