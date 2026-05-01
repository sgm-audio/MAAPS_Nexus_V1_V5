"""
Audio Worker Agent

GPU-accelerated audio processing agent.
Handles HeartMuLa generation, Demucs stem separation, RVC cloning, and LUFS normalization.

V3: Sub-Sonic Mastering Chain
"""

import os
import threading
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging
import httpx

from core import BaseAgent, Message, Topics, Priority

logger = logging.getLogger(__name__)


class JobType(Enum):
    """Audio job types"""
    HEARTMULA_GENERATE = "heartmula_generate"  # Replaces suno_generate
    RVC_CLONE = "rvc_clone"
    DEMUCS_SPLIT = "demucs_split"
    LUFS_NORMALIZE = "lufs_normalize"


class JobStatus(Enum):
    """Job execution status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class AudioJob:
    """Audio processing job"""
    job_id: str
    job_type: JobType
    input_path: str
    output_path: str
    params: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    result: Optional[Dict] = None
    error: Optional[str] = None
    created_at: float = 0.0
    completed_at: Optional[float] = None


class AudioWorkerAgent(BaseAgent):
    """
    GPU Audio Processing Agent.
    
    Capabilities:
    - HeartMuLa AI music generation (replaces Suno)
    - Demucs v4 stem separation
    - RVC voice cloning
    - BS.1770 LUFS normalization
    - Auto-export to network drive
    """
    
    def __init__(self):
        super().__init__(
            agent_id="audio_worker_agent",
            agent_name="GPU Audio Worker Agent"
        )
        
        # Job queue
        self.jobs: Dict[str, AudioJob] = {}
        self.jobs_lock = threading.Lock()
        
        # Worker thread
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_active = False
        
        # GPU availability (check on startup)
        self.gpu_available = False
        self.gpu_device = "cpu"
    
    def setup(self):
        """Initialize audio worker agent"""
        # Subscribe to audio topics
        self.subscribe(Topics.AUDIO_JOB_START)
        self.subscribe(Topics.AUDIO_HEARTMULA_GENERATE)
        self.subscribe(Topics.AUDIO_DEMUCS_START)
        self.subscribe(Topics.AUDIO_RVC_CLONE)
        self.subscribe(Topics.AUDIO_LUFS_NORMALIZE)
        
        # Start worker thread
        self._start_worker()
        
        self.log("INFO", "Audio Worker Agent initialized (Proxy Mode)")
    
    def teardown(self):
        """Cleanup audio worker agent"""
        self._stop_worker()
        self.log("INFO", "Audio Worker Agent shutdown complete")
    
    def _call_worker_api(self, job_type: str, params: Dict, input_path: Optional[str] = None, output_path: Optional[str] = None) -> Dict:
        """Call GPU Worker API"""
        worker_host = os.getenv('GPU_WORKER_HOST', 'audio_worker')
        worker_port = os.getenv('GPU_WORKER_PORT', '8000')
        url = f"http://{worker_host}:{worker_port}/process"
        
        payload = {
            "job_type": job_type,
            "input_path": input_path,
            "output_path": output_path,
            "params": params
        }
        
        self.log("INFO", f"Calling Worker API: {job_type}")
        
        try:
            with httpx.Client(timeout=600.0) as client: # 10 min timeout for heavy jobs
                response = client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            self.log("ERROR", f"Worker API call failed: {e}")
            raise e
    
    def handle_message(self, message: Message):
        """Process incoming audio job messages"""
        try:
            if message.topic == Topics.AUDIO_JOB_START:
                self._handle_job_start(message)
            
            elif message.topic == Topics.AUDIO_HEARTMULA_GENERATE:
                self._handle_heartmula_generate(message)
            
            elif message.topic == Topics.AUDIO_DEMUCS_START:
                self._handle_demucs_split(message)
            
            elif message.topic == Topics.AUDIO_RVC_CLONE:
                self._handle_rvc_clone(message)
            
            elif message.topic == Topics.AUDIO_LUFS_NORMALIZE:
                self._handle_lufs_normalize(message)
            
            else:
                self.log("DEBUG", f"Unhandled topic: {message.topic}")
        
        except Exception as e:
            self.log("ERROR", f"Error handling message: {e}")
    
    def _check_gpu(self):
        """Check if GPU is available"""
        try:
            import torch
            self.gpu_available = torch.cuda.is_available()
            if self.gpu_available:
                self.gpu_device = f"cuda:{torch.cuda.current_device()}"
                gpu_name = torch.cuda.get_device_name(0)
                self.log("INFO", f"GPU detected: {gpu_name}")
            else:
                self.gpu_device = "cpu"
                self.log("WARNING", "No GPU detected, using CPU")
        except ImportError:
            self.gpu_device = "cpu"
            self.log("WARNING", "PyTorch not available, using CPU")
    
    def _handle_job_start(self, message: Message):
        """Handle generic audio job start"""
        payload = message.payload
        job_type = JobType(payload.get('job_type'))
        
        # Route to specific handler
        if job_type == JobType.HEARTMULA_GENERATE:
            self._handle_heartmula_generate(message)
        elif job_type == JobType.DEMUCS_SPLIT:
            self._handle_demucs_split(message)
        elif job_type == JobType.RVC_CLONE:
            self._handle_rvc_clone(message)
        elif job_type == JobType.LUFS_NORMALIZE:
            self._handle_lufs_normalize(message)
    
    def _handle_heartmula_generate(self, message: Message):
        """
        Handle HeartMuLa AI music generation.
        
        Expected payload:
            - prompt: Text prompt for music generation
            - duration: Length in seconds
            - style: Music style/genre
            - output_path: Where to save generated audio
        """
        payload = message.payload
        
        job = AudioJob(
            job_id=message.message_id,
            job_type=JobType.HEARTMULA_GENERATE,
            input_path="",  # HeartMuLa generates from prompt
            output_path=payload.get('output_path', '/files/generated.wav'),
            params={
                'prompt': payload.get('prompt', ''),
                'duration': payload.get('duration', 30),
                'style': payload.get('style', 'electronic')
            },
            created_at=time.time()
        )
        
        self._queue_job(job)
        
        self.respond(message, {
            'success': True,
            'job_id': job.job_id,
            'status': 'queued'
        })
    
    def _handle_demucs_split(self, message: Message):
        """
        Handle Demucs v4 stem separation.
        
        Expected payload:
            - input_path: Path to audio file
            - output_dir: Directory for stems
            - model: Demucs model (htdemucs, htdemucs_ft)
        """
        payload = message.payload
        
        job = AudioJob(
            job_id=message.message_id,
            job_type=JobType.DEMUCS_SPLIT,
            input_path=payload.get('input_path', ''),
            output_path=payload.get('output_dir', '/files/stems'),
            params={
                'model': payload.get('model', 'htdemucs'),
                'two_stems': payload.get('two_stems'),  # Optional: 'vocals', 'drums', etc.
                'shifts': payload.get('shifts', 1)
            },
            created_at=time.time()
        )
        
        self._queue_job(job)
        
        self.respond(message, {
            'success': True,
            'job_id': job.job_id,
            'status': 'queued'
        })
    
    def _handle_rvc_clone(self, message: Message):
        """
        Handle RVC voice cloning.
        
        Expected payload:
            - input_path: Path to audio to convert
            - model_path: Path to RVC model
            - output_path: Where to save output
            - pitch_shift: Semitones to shift (+/-)
        """
        payload = message.payload
        
        job = AudioJob(
            job_id=message.message_id,
            job_type=JobType.RVC_CLONE,
            input_path=payload.get('input_path', ''),
            output_path=payload.get('output_path', '/files/rvc_output.wav'),
            params={
                'model_path': payload.get('model_path', ''),
                'pitch_shift': payload.get('pitch_shift', 0),
                'index_rate': payload.get('index_rate', 0.5)
            },
            created_at=time.time()
        )
        
        self._queue_job(job)
        
        self.respond(message, {
            'success': True,
            'job_id': job.job_id,
            'status': 'queued'
        })
    
    def _handle_lufs_normalize(self, message: Message):
        """
        Handle BS.1770 LUFS normalization.
        
        Expected payload:
            - input_path: Path to audio file
            - output_path: Where to save normalized audio
            - target_lufs: Target loudness (default: -14)
        """
        payload = message.payload
        
        job = AudioJob(
            job_id=message.message_id,
            job_type=JobType.LUFS_NORMALIZE,
            input_path=payload.get('input_path', ''),
            output_path=payload.get('output_path', '/files/normalized.wav'),
            params={
                'target_lufs': payload.get('target_lufs', -14.0),
                'true_peak': payload.get('true_peak', -1.0)
            },
            created_at=time.time()
        )
        
        self._queue_job(job)
        
        self.respond(message, {
            'success': True,
            'job_id': job.job_id,
            'status': 'queued'
        })
    
    def _queue_job(self, job: AudioJob):
        """Add job to processing queue"""
        with self.jobs_lock:
            self.jobs[job.job_id] = job
        
        self.log("INFO", f"Job queued: {job.job_type.value} ({job.job_id[:8]})")
    
    def _start_worker(self):
        """Start job processing worker thread"""
        self._worker_active = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="AudioWorker_JobProcessor",
            daemon=True
        )
        self._worker_thread.start()
    
    def _stop_worker(self):
        """Stop job processing worker thread"""
        self._worker_active = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
    
    def _worker_loop(self):
        """Main job processing loop"""
        while self._worker_active:
            try:
                # Find next pending job
                job = self._get_next_job()
                
                if job:
                    self._process_job(job)
                else:
                    time.sleep(0.5)
            
            except Exception as e:
                self.log("ERROR", f"Worker loop error: {e}")
                time.sleep(1.0)
    
    def _get_next_job(self) -> Optional[AudioJob]:
        """Get next pending job from queue"""
        with self.jobs_lock:
            for job in self.jobs.values():
                if job.status == JobStatus.PENDING:
                    return job
        return None
    
    def _process_job(self, job: AudioJob):
        """Process a single audio job"""
        job.status = JobStatus.PROCESSING
        self._publish_progress(job)
        
        try:
            if job.job_type == JobType.HEARTMULA_GENERATE:
                self._run_heartmula(job)
            
            elif job.job_type == JobType.DEMUCS_SPLIT:
                self._run_demucs(job)
            
            elif job.job_type == JobType.RVC_CLONE:
                self._run_rvc(job)
            
            elif job.job_type == JobType.LUFS_NORMALIZE:
                self._run_lufs_normalize(job)
            
            job.status = JobStatus.COMPLETE
            job.completed_at = time.time()
            
            self.publish(Topics.AUDIO_JOB_COMPLETE, {
                'job_id': job.job_id,
                'job_type': job.job_type.value,
                'output_path': job.output_path,
                'result': job.result
            })
            
            self.log("INFO", f"Job complete: {job.job_id[:8]}")
        
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = time.time()
            
            self.publish(Topics.AUDIO_JOB_FAILED, {
                'job_id': job.job_id,
                'job_type': job.job_type.value,
                'error': str(e)
            })
            
            self.log("ERROR", f"Job failed: {job.job_id[:8]} - {e}")
    
    def _publish_progress(self, job: AudioJob):
        """Publish job progress update"""
        self.publish(Topics.AUDIO_JOB_PROGRESS, {
            'job_id': job.job_id,
            'job_type': job.job_type.value,
            'status': job.status.value,
            'progress': job.progress
        })
    
    def _run_heartmula(self, job: AudioJob):
        """Run HeartMuLa via Worker API"""
        result = self._call_worker_api(
            "heartmula_generate",
            job.params,
            output_path=job.output_path
        )
        job.result = result
    
    def _run_demucs(self, job: AudioJob):
        """Run Demucs via Worker API"""
        result = self._call_worker_api(
            "demucs_split",
            job.params,
            input_path=job.input_path,
            output_path=job.output_path
        )
        job.result = result
    
    def _run_rvc(self, job: AudioJob):
        """Run RVC via Worker API"""
        result = self._call_worker_api(
            "rvc_clone",
            job.params,
            input_path=job.input_path,
            output_path=job.output_path
        )
        job.result = result
    
    def _run_lufs_normalize(self, job: AudioJob):
        """Run LUFS via Worker API"""
        result = self._call_worker_api(
            "lufs_normalize",
            job.params,
            input_path=job.input_path,
            output_path=job.output_path
        )
        job.result = result
