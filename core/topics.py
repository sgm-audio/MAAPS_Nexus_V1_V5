"""
Standard Topic Definitions

Centralized topic namespace for the MAAPS message bus.
All agents use these topics for inter-agent communication.
"""


class Topics:
    """Standard MAAPS topic definitions"""
    
    # ==========================================
    # SYSTEM
    # ==========================================
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_HEALTH_CHECK = "system.health.check"
    SYSTEM_HEALTH_REPORT = "system.health.report"
    
    # ==========================================
    # ORCHESTRATION (V1: CI/CD)
    # ==========================================
    DEPLOY_WEBHOOK_RECEIVED = "deploy.webhook.received"
    DEPLOY_GIT_PULL = "deploy.git.pull"
    DEPLOY_CONTAINER_REBUILD = "deploy.container.rebuild"
    DEPLOY_HOT_RELOAD = "deploy.hot.reload"
    DEPLOY_STATUS = "deploy.status"
    DEPLOY_FAILED = "deploy.failed"
    
    # ==========================================
    # SCRAPER (V2: Lead Gen)
    # ==========================================
    SCRAPER_JOB_START = "scraper.job.start"
    SCRAPER_JOB_COMPLETE = "scraper.job.complete"
    SCRAPER_JOB_FAILED = "scraper.job.failed"
    SCRAPER_LEADS_FOUND = "scraper.leads.found"
    
    # ==========================================
    # OUTBOUND (V2: Ghost Engine)
    # ==========================================
    OUTBOUND_CAMPAIGN_START = "outbound.campaign.start"
    OUTBOUND_LEAD_PROCESS = "outbound.lead.process"
    OUTBOUND_VOICE_GENERATE = "outbound.voice.generate"
    OUTBOUND_EMAIL_SEND = "outbound.email.send"
    OUTBOUND_COMPLETE = "outbound.complete"
    
    # ==========================================
    # AUDIO (V3: Mastering Chain)
    # ==========================================
    AUDIO_JOB_START = "audio.job.start"
    AUDIO_JOB_PROGRESS = "audio.job.progress"
    AUDIO_JOB_COMPLETE = "audio.job.complete"
    AUDIO_JOB_FAILED = "audio.job.failed"
    
    # Stem Separation
    AUDIO_DEMUCS_START = "audio.demucs.start"
    AUDIO_DEMUCS_COMPLETE = "audio.demucs.complete"
    
    # HeartMuLa (replaces Suno)
    AUDIO_HEARTMULA_GENERATE = "audio.heartmula.generate"
    AUDIO_HEARTMULA_COMPLETE = "audio.heartmula.complete"
    
    # RVC Voice Cloning
    AUDIO_RVC_CLONE = "audio.rvc.clone"
    AUDIO_RVC_COMPLETE = "audio.rvc.complete"
    
    # Mastering
    AUDIO_LUFS_NORMALIZE = "audio.lufs.normalize"
    AUDIO_MASTER_EXPORT = "audio.master.export"
    
    # ==========================================
    # RAG (Knowledge Retrieval)
    # ==========================================
    RAG_QUERY = "rag.query"
    RAG_RESPONSE = "rag.response"
    RAG_INDEX_DOC = "rag.index.doc"
    RAG_INDEX_COMPLETE = "rag.index.complete"
    
    # ==========================================
    # AGENT MESH (V4: Ray Distribution)
    # ==========================================
    MESH_ACTOR_SPAWN = "mesh.actor.spawn"
    MESH_ACTOR_READY = "mesh.actor.ready"
    MESH_JOB_DISTRIBUTE = "mesh.job.distribute"
    MESH_JOB_RESULT = "mesh.job.result"
    
    # ==========================================
    # API GATEWAY (V5: SaaS)
    # ==========================================
    API_REQUEST_RECEIVED = "api.request.received"
    API_REQUEST_VALIDATED = "api.request.validated"
    API_RESPONSE_READY = "api.response.ready"
    API_RATE_LIMITED = "api.rate.limited"
