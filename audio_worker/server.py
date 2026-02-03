"""
Audio Worker FastAPI Server

HTTP API for the GPU Audio Worker.
Exposes endpoints for audio processing and RAG queries.
"""

import time
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('maaps.audio_worker')

app = FastAPI(
    title="MAAPS Audio Worker API",
    description="GPU-accelerated audio processing for HeartMuLa, Demucs, RVC, and LUFS normalization",
    version="1.0.0"
)


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
    
    try:
        if request.job_type == "heartmula_generate":
            return await _process_heartmula(request)
        
        elif request.job_type == "demucs_split":
            return await _process_demucs(request)
        
        elif request.job_type == "rvc_clone":
            return await _process_rvc(request)
        
        elif request.job_type == "lufs_normalize":
            return await _process_lufs(request)
        
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown job type: {request.job_type}"
            )
    
    except Exception as e:
        logger.error(f"Processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _process_heartmula(request: AudioJobRequest):
    """Process HeartMuLa generation job"""
    prompt = request.params.get('prompt', '')
    duration = request.params.get('duration', 30)
    
    logger.info(f"HeartMuLa generate: {prompt[:50]}...")
    
    # TODO: Integrate with HeartMuLa API
    # Placeholder response
    return {
        "status": "queued",
        "job_type": "heartmula_generate",
        "message": "HeartMuLa integration pending",
        "params": {
            "prompt": prompt,
            "duration": duration
        }
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
        
        # Run demucs (blocking for now)
        demucs.separate.main(args)
        
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
    
    # TODO: Integrate with RVC inference
    return {
        "status": "queued",
        "job_type": "rvc_clone",
        "message": "RVC integration pending"
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
        
        # Read audio
        data, rate = sf.read(request.input_path)
        
        # Measure loudness
        meter = pyln.Meter(rate)
        loudness = meter.integrated_loudness(data)
        
        # Normalize
        normalized = pyln.normalize.loudness(data, loudness, target_lufs)
        
        # Write output
        output_path = request.output_path or request.input_path.replace('.wav', '_normalized.wav')
        sf.write(output_path, normalized, rate)
        
        return {
            "status": "complete",
            "job_type": "lufs_normalize",
            "original_lufs": loudness,
            "target_lufs": target_lufs,
            "output_path": output_path
        }
    
    except ImportError:
        return {
            "status": "error",
            "message": "pyloudnorm or soundfile not installed"
        }


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
        from qdrant_client import QdrantClient
        from sentence_transformers import SentenceTransformer
        import os
        
        # Connect to Qdrant
        qdrant_url = os.getenv('QDRANT_HOST', 'qdrant') + ':' + os.getenv('QDRANT_PORT', '6333')
        client = QdrantClient(url=f"http://{qdrant_url}")
        
        # Load embeddings model
        model = SentenceTransformer('BAAI/bge-m3', device='cuda')
        
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
    
    # TODO: Implement document indexing
    return {
        "status": "queued",
        "message": "Document indexing pending implementation",
        "content_length": len(request.content)
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
