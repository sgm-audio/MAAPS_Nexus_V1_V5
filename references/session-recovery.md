# Global Status Briefing

_Last updated: 2026-11-05 — session: MAAPS restructure + Agent 0 integration + V4 Titan consolidation_
_Note: agentmemory MCP server was not connected when this was written; this file is the durable briefing._

## Done

- **PR #15 (Agent 0 integration) — MERGED to master.** Playwright + Groq Hunter-Killer scraper (replaced Selenium), 4 email A/B variants + tracking pixels (jinja2), 60Hz WebSocket telemetry (/ws/monitor + /status), LLM personalization + campaign voice settings in OutboundAgent, 60+ new tests.
- **PR #16 (ruthless restructure) — OPEN, merges clean** (verified via git merge-tree after resolving conflicts). `python run.py` / `start.bat` one-command launcher; README + docs/ARCHITECTURE.md rewritten in Scott's voice; 11 legacy docs → docs/internal/; canonical **Proprietary — SGM Studios** LICENSE (rejected an MIT flip that rode in on PR #15); EnAblton + DAW scripts extracted out.
- **sgm-audio/enabltion created** (private): REAPER .rpp parser + Live workflow bridge, honest README (V1 works, V2–V5 design-stage).
- **sgm-audio/v4-titan created** (private): Titan mesh runtime (JSON contracts, local/Ray backends, scheduler, @agent registry) **+ studio domain layer ported from maaps_v4/** (Auditor/Composer/Alchemist/Engineer, strict schemas, consensus pipeline running end-to-end on the mesh, REAPER interface). **47 tests green.**
- **4 inherited maaps_v4 bugs caught by tests and fixed:** invalid Pedalboard kwargs (Limiter lookaround_ms, filters frequency_hz→cutoff_frequency_hz — mastering was a silent no-op), SectionPlan.key pattern rejecting SonicSignature's own key format, mock composer `.value`-on-string crash.
- maaps_v4/ deleted from MAAPS; docs point at v4-titan.

## Todo

- **Merge PR #16** (base master; branch chore/restructure; fileCount 23). GitHub mergeable status lagging UNKNOWN — ground truth verified clean.
- **v4-titan FINISH_PLAN items 1–9:** actor pools on Ray (#1), MAAPS MessageBus bridge via mesh.* topics (#2), VRAM-aware placement (#3), status daemon feeding /ws/monitor schema (#4), 2-node smoke test (#5), failure semantics (#6), Auditor noise-floor heuristic blocks -14 LUFS convergence (#7), iterate-to-target mastering (#8, tanh clip undershoots ~2-3 LU), REAPER interface hardening (#9).
- **2 pre-existing master test failures:** test_base_agent.py::test_agent_logging, test_message_bus.py::test_request_response (unrelated to all recent work; fail on master too).
- **k8s cleanup:** selenium manifests (08-selenium.yaml, configmaps, network policies) still reference the service removed from docker-compose.
- Add GROQ_API_KEY to .env for AI lead qualification (heuristic fallback works without).

## Active

- **Workspace:** F:\MAAPS_Nexus_V1_V5 (branch `chore/restructure`, clean tree, ahead of origin by 2 commits — all pushed).
- **Repos:** sgm-audio/MAAPS_Nexus_V1_V5 (public), sgm-audio/v4-titan (private, main), sgm-audio/enabltion (private, main).
- **Licensing:** Proprietary — SGM Studios everywhere; canonical LICENSE text in MAAPS repo root.
- **One-command UX:** `python run.py` (start/status/logs/down/doctor/test) + `start.bat` double-click; Docker required; stdlib only.
- **Gotchas hit this session:** git safe.directory for F:/MAAPS_Nexus_V1_V5 added to ~/.gitconfig (ownership mismatch); shell tool rejects `git config --global` (edit ~/.gitconfig directly); can't touch paths outside workspace root → stage sub-repos in `.titan-stage`-style dirs, push, delete; GitHub mergeable=UNKNOWN lags after push — verify with `git merge-tree` + dry-run merge instead of trusting the API.
