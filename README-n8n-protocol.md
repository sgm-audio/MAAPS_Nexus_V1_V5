# MAAPS/HIVYR n8n Architecture Protocol

## The Refusal of Service Standards

This repository contains the production-grade n8n architecture patterns for **MAAPS** and **Hivyr** — enterprise audio infrastructure systems.

---

## Core Principles

### 1. ❌ Refuse to Compute in the Canvas
**Problem:** Processing large datasets or binary audio in JavaScript nodes kills the single-threaded event loop.

**Solution:** n8n is the **Conductor**, not the Orchestra.
- Heavy compute → Python microservices (Librosa, PyTorch, Pandas)
- n8n → Payload routing only
- Result: Zero memory pressure on n8n instance

```
Client → n8n → Python Service → n8n → Response
              (routing only)    (returns result)
```

### 2. ❌ Refuse "The Monolith"
**Problem:** 150+ node workflows that look like the London Underground.

**Solution:** **Atomic Sub-Workflows**
- Each logical step = standalone workflow with Webhook Trigger + Response
- Reusable API endpoints: `Execute Workflow` nodes chain together
- Clean, readable, scalable architecture

```
[Ingest Audio] → [Transcribe] → [Analyze] → [Update CRM] → [Notify]
     (each is a separate workflow with defined interface)
```

### 3. ❌ Refuse Fragile Webhooks
**Problem:** Data loss when webhooks miss requests during blips.

**Solution:** **Decoupled Ingestion with Message Queues**
```
Client → API Gateway → Redis/RabbitMQ Queue → n8n Worker
                                    (holds data if n8n is down)
```
- Zero data loss during maintenance/updates
- Backlog processing on recovery

### 4. ❌ Refuse Magic Numbers & Hardcoding
**Problem:** Hunting through 40 workflows to update credentials.

**Solution:** **Global Environment Variables**
```javascript
// BAD
folder_id: "1a2b3c4d5e6f"

// GOOD
folder_id: "{{ $env.HIVYR_PROD_STORAGE_ID }}"
```
- All configuration at Docker/K8s level
- Single source of truth for credentials

### 5. ❌ Refuse to Guess "What Happened?"
**Problem:** Failures without context = debugging nightmares.

**Solution:** **Standardized Error Handling**
- Every workflow wraps logic in Try/Catch (Error Trigger)
- Failure dumps full execution JSON to:
  - Dedicated Slack/Discord channel
  - Database table (Supabase/Postgres)
  - Specific error codes for immediate triage

---

## Architecture Summary

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Orchestration** | n8n | IO + Routing only |
| **Logic/Compute** | Python (FastAPI) | Librosa, PyTorch, Pandas |
| **State** | Postgres/Supabase | Persistent data |
| **Queue** | Redis/RabbitMQ | Decoupled ingestion |
| **Logging** | Slack + DB | Error tracking |

**n8n's Job:** Pass the butter. Nothing more.

---

## Templates Included

### `atomic-audio-processor-template.json`
A reusable sub-workflow template demonstrating:
- ✅ Webhook trigger with defined input schema
- ✅ HTTP request to offload compute to Python service
- ✅ Immediate response return
- ✅ Global error catch with Slack logging
- ✅ No inline JavaScript processing
- ✅ Environment variable placeholders

**Usage:** Import into n8n, replace `your-python-microservice.internal` with your actual service endpoint, set environment variables.

---

## Implementation Checklist

Before deploying any workflow to production:

- [ ] Does this workflow exceed 20 nodes? → Break into atomic sub-workflows
- [ ] Is there any JavaScript code processing data? → Move to Python service
- [ ] Are there hardcoded IDs, keys, or URLs? → Convert to `{{ $env.VARIABLE }}`
- [ ] Is there an Error Trigger node? → Add standardized error handling
- [ ] Is this webhook exposed directly to clients? → Add queue layer
- [ ] Can I understand the entire flow in <10 seconds? → Simplify further

---

## Revenue Impact

**Before:** Debugging JSON parsing errors at 2 AM, lost leads from failed webhooks, memory leaks crashing instances.

**After:** 
- High-margin scale without headaches
- Revenue-per-hour maximized (no debugging tax)
- Building the future of AI audio, not fighting tools

---

*This protocol keeps MAAPS and Hivyr operating at enterprise grade. No exceptions.*
