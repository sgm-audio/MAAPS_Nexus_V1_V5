"""
Audio Worker FastAPI Server

HTTP API for the GPU Audio Worker.
Exposes endpoints for audio processing, RAG queries, and real-time telemetry.

Telemetry (migrated from Agent 0 "Visual_feedback_layer.py"):
- /ws/monitor: 60Hz WebSocket stream of system + GPU + job metrics
- /status: single-shot JSON snapshot (polling fallback)
"""

import time
import logging
import asyncio
from collections import deque
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('maaps.audio_worker')

app = FastAPI(
    title="MAAPS Audio Worker API",
    description="GPU-accelerated audio processing for HeartMuLa, Demucs, RVC, and LUFS normalization",
    version="1.1.0"
)

# Optional psutil (telemetry degrades gracefully without it)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not installed - CPU/memory telemetry disabled")


# =====================================
# Request Models
# =====================================

class AudioJobRequest(BaseModel):
    """Audio processing job request"""
    job_type: str  # 'heartmula_generate', 'demucs_split', 'rvc_clone', 'lufs_normalize'
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    params: Dict[str, Any] = {}


class RAGQueryRequest(BaseModel):
    """RAG knowledge base query"""
    query: str
    top_k: int = 3


class RAGIndexRequest(BaseModel):
    """Document indexing request"""
    content: str
    metadata: Dict[str, Any] = {}
    chunk_size: int = 1000


# =====================================
# Health Check
# =====================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    import torch
    
    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else "N/A"
    
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "gpu_available": gpu_available,
        "gpu_device": gpu_name
    }


# =====================================
# Telemetry (from Agent 0 Visual Feedback Layer)
# =====================================

# In-memory job metrics: rolling window of recent jobs + counters
JOB_METRICS = {
    'counts': {'submitted': 0, 'complete': 0, 'error': 0},
    'by_type': {},                      # job_type -> count
    'recent': deque(maxlen=100),        # [{ts, job_type, ms, status}]
}
# Monotonic latency tracker for last N jobs (ms)
JOB_LATENCY_MS = deque(maxlen=50)


def record_job_submitted(job_type: str):
    JOB_METRICS['counts']['submitted'] += 1
    JOB_METRICS['by_type'][job_type] = JOB_METRICS['by_type'].get(job_type, 0) + 1
    JOB_METRICS['recent'].append({
        'ts': time.time(), 'job_type': job_type, 'status': 'submitted', 'ms': None
    })


def record_job_finished(job_type: str, started_at: float, success: bool):
    ms = (time.time() - started_at) * 1000.0
    JOB_METRICS['counts']['complete' if success else 'error'] += 1
    JOB_METRICS['recent'].append({
        'ts': time.time(), 'job_type': job_type,
        'status': 'complete' if success else 'error', 'ms': round(ms, 1),
    })
    JOB_LATENCY_MS.append(ms)


def _gpu_metrics() -> Dict[str, Any]:
    """GPU telemetry (torch optional, degrades gracefully)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {'gpu_available': False, 'gpu_name': None,
                    'vram_used_mb': None, 'vram_total_mb': None,
                    'util_pct': None}
        name = torch.cuda.get_device_name(0)
        vram_used = torch.cuda.memory_allocated(0) / (1024 * 1024)
        vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
        util = None
        try:
            util = torch.cuda.utilization(0)  # requires pynvml; optional
        except Exception:
            pass
        return {'gpu_available': True, 'gpu_name': name,
                'vram_used_mb': round(vram_used, 1),
                'vram_total_mb': round(vram_total, 1),
                'util_pct': util}
    except ImportError:
        return {'gpu_available': False, 'gpu_name': None,
                'vram_used_mb': None, 'vram_total_mb': None, 'util_pct': None}


def _system_metrics() -> Dict[str, Any]:
    """CPU/memory telemetry (psutil optional)."""
    if not HAS_PSUTIL:
        return {'cpu_load': None, 'mem_used_pct': None, 'mem_used_mb': None}
    return {
        'cpu_load': psutil.cpu_percent(interval=None),
        'mem_used_pct': psutil.virtual_memory().percent,
        'mem_used_mb': round(psutil.virtual_memory().used / (1024 * 1024), 1),
    }


def _latency_stats() -> Dict[str, Optional[float]]:
    if not JOB_LATENCY_MS:
        return {'avg_ms': None, 'p95_ms': None, 'last_ms': None}
    ordered = sorted(JOB_LATENCY_MS)
    p95_idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return {
        'avg_ms': round(sum(ordered) / len(ordered), 1),
        'p95_ms': round(ordered[p95_idx], 1),
        'last_ms': round(ordered[-1], 1),
    }


def collect_metrics() -> Dict[str, Any]:
    """One telemetry snapshot: system + GPU + jobs. Used by /status and /ws/monitor."""
    return {
        'timestamp': time.time(),
        'system': _system_metrics(),
        'gpu': _gpu_metrics(),
        'jobs': {
            'counts': dict(JOB_METRICS['counts']),
            'by_type': dict(JOB_METRICS['by_type']),
            'latency': _latency_stats(),
            'recent': list(JOB_METRICS['recent'])[-10:],
        },
    }


@app.get("/status")
async def status_snapshot():
    """Single-shot telemetry snapshot (polling fallback for /ws/monitor)."""
    return collect_metrics()


@app.websocket("/ws/monitor")
async def monitor_agents(websocket: WebSocket):
    """
    Real-time telemetry stream (60Hz target, 1Hz floor).

    Streams collect_metrics() JSON. Client may send:
      - {"action": "set_interval", "interval": 0.5}  (seconds, clamped 0.016-1.0)
      - {"action": "pause"} / {"action": "resume"}
    """
    await websocket.accept()
    interval = 1 / 60  # 60Hz default
    paused = False
    try:
        while True:
            # Non-blocking receive: handle client control messages if any
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=interval)
                action = msg.get('action')
                if action == 'set_interval':
                    interval = max(0.016, min(1.0, float(msg.get('interval', interval))))
                elif action == 'pause':
                    paused = True
                elif action == 'resume':
                    paused = False
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            if not paused:
                await websocket.send_json(collect_metrics())
            else:
                await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Monitor websocket closed: {e}")


# =====================================
# Model Management
# =====================================

MODELS = {}

def get_heartmula_model():
    """Lazy load HeartMuLa (MusicGen) model"""
    if 'heartmula' not in MODELS:
        logger.info("Loading HeartMuLa (MusicGen) model...")
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
        import torch
        
        processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
        model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small")
        
        if torch.cuda.is_available():
            model = model.to("cuda")
            logger.info("HeartMuLa loaded on GPU")
        else:
            logger.info("HeartMuLa loaded on CPU")
            
        MODELS['heartmula'] = (processor, model)
        
    return MODELS['heartmula']


# =====================================
# Audio Processing
# =====================================

@app.post("/process")
async def process_audio(request: AudioJobRequest):
    """
    Submit audio processing job.
    
    Job types:
    - heartmula_generate: AI music generation
    - demucs_split: Stem separation
    - rvc_clone: Voice cloning
    - lufs_normalize: Loudness normalization
    """
    logger.info(f"Received job: {request.job_type}")
    
    started_at = time.time()
    record_job_submitted(request.job_type)
    
    success = False
    try:
        if request.job_type == "heartmula_generate":
            result = await _process_heartmula(request)
        elif request.job_type == "demucs_split":
            result = await _process_demucs(request)
        elif request.job_type == "rvc_clone":
            result = await _process_rvc(request)
        elif request.job_type == "lufs_normalize":
            result = await _process_lufs(request)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown job type: {request.job_type}"
            )
        
        # Handlers may return {"status": "error", ...} instead of raising
        success = isinstance(result, dict) and result.get('status') == 'complete'
        return result
    
    except HTTPException:
        record_job_finished(request.job_type, started_at, success=False)
        raise
    except Exception as e:
        logger.error(f"Processing error: {e}")
        record_job_finished(request.job_type, started_at, success=False)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if not JOB_METRICS['recent'] or JOB_METRICS['recent'][-1]['status'] == 'submitted':
            record_job_finished(request.job_type, started_at, success=success)


async def _process_heartmula(request: AudioJobRequest):
    """Process HeartMuLa generation job"""
    prompt = request.params.get('prompt', '')
    duration = request.params.get('duration', 10)  # Default 10s for speed
    
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")
        
    output_path = request.output_path or f"/files/heartmula_{int(time.time())}.wav"
    
    logger.info(f"HeartMuLa generate: {prompt[:50]}... ({duration}s)")
    
    def _generate():
        try:
            import torch
            import soundfile as sf
            
            processor, model = get_heartmula_model()
            
            inputs = processor(
                text=[prompt],
                padding=True,
                return_tensors="pt",
            )
            
            if torch.cuda.is_available():
                inputs = inputs.to("cuda")
            
            # 50 tokens approx 1 second
            max_tokens = int(duration * 50)
            
            audio_values = model.generate(**inputs, max_new_tokens=max_tokens)
            
            # Save to file (taking first sample, first channel)
            sampling_rate = model.config.audio_encoder.sampling_rate
            audio_data = audio_values[0, 0].cpu().numpy()
            
            sf.write(output_path, audio_data, sampling_rate)
            return True
        except Exception as e:
            logger.error(f"HeartMuLa generation failed: {e}")
            raise e

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _generate)
        
        return {
            "status": "complete",
            "job_type": "heartmula_generate",
            "output_path": output_path,
            "params": {
                "prompt": prompt,
                "duration": duration
            }
        }
    except Exception as e:
         return {
            "status": "error",
            "message": str(e)
        }


async def _process_demucs(request: AudioJobRequest):
    """Process Demucs stem separation job"""
    if not request.input_path:
        raise HTTPException(status_code=400, detail="input_path required")
    
    logger.info(f"Demucs split: {request.input_path}")
    
    try:
        import demucs.separate
        
        model = request.params.get('model', 'htdemucs')
        output_dir = request.output_path or '/files/stems'
        
        # Build args
        args = ['-n', model, '-o', output_dir, request.input_path]
        
        # Run demucs in thread pool to prevent blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, demucs.separate.main, args)
        
        return {
            "status": "complete",
            "job_type": "demucs_split",
            "output_dir": output_dir,
            "stems": ["bass", "drums", "other", "vocals"]
        }
    
    except ImportError:
        return {
            "status": "error",
            "message": "Demucs not installed"
        }


async def _process_rvc(request: AudioJobRequest):
    """Process RVC voice cloning job"""
    logger.info(f"RVC clone: {request.input_path}")
    
    if not request.input_path:
        raise HTTPException(status_code=400, detail="input_path required")
        
    output_path = request.output_path or request.input_path.replace('.wav', '_rvc.wav')
    
    # NOTE: Real RVC inference requires external RVC codebase/weights.
    # For this isolated build, we simulate a voice change using Pedalboard
    # to ensure the pipeline is functional.
    
    def _simulate_voice_conversion():
        try:
            from pedalboard import Pedalboard, PitchShift, Reverb, Compressor
            import soundfile as sf
            
            # Read audio
            data, rate = sf.read(request.input_path)
            
            # Simple effects chain to change voice character
            board = Pedalboard([
                Compressor(threshold_db=-20, ratio=2.5),
                PitchShift(semitones=-2), # Deepen voice slightly
                Reverb(room_size=0.05, wet_level=0.1) # Slight room presence
            ])
            
            # Process
            processed = board(data, rate)
            
            # Write
            sf.write(output_path, processed, rate)
            return True
            
        except ImportError:
            raise Exception("Pedalboard not installed")
        except Exception as e:
            logger.error(f"RVC simulation failed: {e}")
            raise e

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _simulate_voice_conversion)
        
        return {
            "status": "complete",
            "job_type": "rvc_clone_simulated",
            "output_path": output_path,
            "message": "Processed with Pedalboard (RVC simulation)"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


async def _process_lufs(request: AudioJobRequest):
    """Process LUFS normalization job"""
    if not request.input_path:
        raise HTTPException(status_code=400, detail="input_path required")
    
    target_lufs = request.params.get('target_lufs', -14.0)
    
    logger.info(f"LUFS normalize: {request.input_path} -> {target_lufs} LUFS")
    
    try:
        import pyloudnorm as pyln
        import soundfile as sf
        
        output_path = request.output_path or request.input_path.replace('.wav', '_normalized.wav')

        def _run_normalization():
            # Read audio
            data, rate = sf.read(request.input_path)
            
            # Measure loudness
            meter = pyln.Meter(rate)
            loudness = meter.integrated_loudness(data)
            
            # Normalize
            normalized = pyln.normalize.loudness(data, loudness, target_lufs)
            
            # Write output
            sf.write(output_path, normalized, rate)
            return loudness

        # Run in thread pool
        loop = asyncio.get_event_loop()
        original_loudness = await loop.run_in_executor(None, _run_normalization)
        
        return {
            "status": "complete",
            "job_type": "lufs_normalize",
            "original_lufs": original_loudness,
            "target_lufs": target_lufs,
            "output_path": output_path
        }
    
    except ImportError:
        return {
            "status": "error",
            "message": "pyloudnorm or soundfile not installed"
        }


# =====================================
# RAG Helpers
# =====================================

def get_rag_components():
    """Get Qdrant client and embedding model (cached)"""
    if 'rag' not in MODELS:
        from qdrant_client import QdrantClient
        from sentence_transformers import SentenceTransformer
        import os
        import torch
        
        # Connect to Qdrant
        qdrant_host = os.getenv('QDRANT_HOST', 'qdrant')
        qdrant_port = os.getenv('QDRANT_PORT', '6333')
        qdrant_url = f"http://{qdrant_host}:{qdrant_port}"
        
        client = QdrantClient(url=qdrant_url)
        
        # Load embedding model
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model = SentenceTransformer('BAAI/bge-m3', device=device)
        
        MODELS['rag'] = (client, model)
        
    return MODELS['rag']


# =====================================
# RAG Endpoints
# =====================================

@app.post("/query_docs")
async def query_knowledge_base(request: RAGQueryRequest):
    """
    Query the vector knowledge base.
    
    Uses BGE-M3 embeddings and Qdrant for semantic search.
    """
    logger.info(f"RAG query: {request.query[:50]}...")
    
    try:
        client, model = get_rag_components()
        
        # Generate query embedding
        query_vector = model.encode(request.query, normalize_embeddings=True).tolist()
        
        # Search
        results = client.search(
            collection_name="maaps_knowledge",
            query_vector=query_vector,
            limit=request.top_k
        )
        
        # Format response
        context_chunks = [r.payload.get('content', '') for r in results]
        
        return {
            "status": "success",
            "query": request.query,
            "context": "\n\n".join(context_chunks),
            "sources": [r.payload.get('metadata', {}).get('source', '') for r in results],
            "count": len(results)
        }
    
    except Exception as e:
        logger.error(f"RAG query error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/index_docs")
async def index_document(request: RAGIndexRequest):
    """
    Index a document to the knowledge base.
    """
    logger.info(f"Indexing document: {request.metadata.get('title', 'untitled')}")
    
    try:
        import uuid
        from qdrant_client.http import models
        
        client, model = get_rag_components()
        collection_name = "maaps_knowledge"
        
        # Ensure collection exists
        try:
            client.get_collection(collection_name)
        except:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=1024,  # BGE-M3 dimension
                    distance=models.Distance.COSINE
                )
            )
            
        # Chunk text (simple paragraph split for now)
        chunks = []
        paragraphs = request.content.split('\n\n')
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < request.chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        # Index chunks
        points = []
        for i, chunk in enumerate(chunks):
            embedding = model.encode(chunk, normalize_embeddings=True).tolist()
            
            point_id = str(uuid.uuid4())
            points.append(models.PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    'content': chunk,
                    'metadata': request.metadata,
                    'chunk_index': i,
                    'indexed_at': time.time()
                }
            ))
            
        # Batch upsert
        client.upsert(
            collection_name=collection_name,
            points=points
        )
        
        return {
            "status": "success",
            "chunks_indexed": len(points),
            "message": f"Indexed {len(points)} chunks"
        }
        
    except Exception as e:
        logger.error(f"Indexing error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


# =====================================
# Run Server
# =====================================

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1
    )
