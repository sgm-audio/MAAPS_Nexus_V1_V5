"""
MAAPS v4.0 - Multi-Agent Audio Production System
Production-grade, self-hosted, scalable audio generation with REAPER 7+ integration

Core Philosophy:
- Atomic Agents + Consensus Loops (no linear pipelines)
- REAPER as the UI/DAW Layer via reapy
- Self-Hosted & High-Margin via HeartMuLa on Ray GPU swarm
- No Vendor Lock-In - full local control
- Enterprise-Ready with strict Pydantic schemas and deterministic LUFS
"""

import logging
import signal
import sys
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import asyncio

# Ray for distributed compute
import ray
from ray import serve
from ray.serve.deployment import Deployment

# Core MAAPS imports
from maaps_v4.schemas import SonicSignature, GenerationRequest, MasteringParams, ReaperTelemetry
from maaps_v4.agents.auditor import AuditorAgent
from maaps_v4.agents.composer import ComposerAgent
from maaps_v4.agents.alchemist import AlchemistAgent
from maaps_v4.agents.engineer import EngineerAgent
from maaps_v4.reaper_interface import ReaperNeuralInterface

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('maaps_v4.log')
    ]
)

logger = logging.getLogger('maaps.v4')


class AgentState(Enum):
    """Agent lifecycle states"""
    IDLE = "idle"
    PROCESSING = "processing"
    CRITIQUING = "critiquing"
    ERROR = "error"


@dataclass
class ConsensusLoopResult:
    """Result from agent consensus loop"""
    success: bool
    iterations: int
    max_iterations: int = 5
    auditor_approved: bool = False
    final_output_paths: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    telemetry: Dict[str, Any] = field(default_factory=dict)


class MAAPSV4Orchestrator:
    """
    MAAPS v4.0 Orchestrator with Consensus Loop Architecture
    
    Flow:
    1. Auditor analyzes input → SonicSignature
    2. Composer structures → Section plan with HeartMuLa prompts
    3. Alchemist generates → Stems/audio buffers
    4. Engineer masters → Broadcast-ready output
    5. Auditor critiques → Loop back if rejected
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.state = AgentState.IDLE
        self.ray_initialized = False
        
        # Initialize agents
        self.auditor = AuditorAgent()
        self.composer = ComposerAgent(llm_provider=config.get('llm_provider', 'gemini'))
        self.alchemist = AlchemistAgent(
            heartmula_model=config.get('heartmula_model', 'HeartMuLa-oss-3B'),
            gpu_resources=config.get('gpu_resources', {'num_gpus': 1})
        )
        self.engineer = EngineerAgent(
            target_lufs=config.get('target_lufs', -14.0),
            true_peak=config.get('true_peak', -1.0)
        )
        
        # REAPER interface (optional)
        self.reaper_interface: Optional[ReaperNeuralInterface] = None
        if config.get('enable_reaper', True):
            self.reaper_interface = ReaperNeuralInterface()
        
        logger.info("MAAPS v4.0 Orchestrator initialized")
    
    def initialize_ray(self):
        """Initialize Ray cluster for distributed compute"""
        if not self.ray_initialized:
            ray.init(
                address=self.config.get('ray_address', 'auto'),
                ignore_reinit_error=True
            )
            self.ray_initialized = True
            logger.info("Ray cluster connected")
    
    async def process_request(self, request: GenerationRequest) -> ConsensusLoopResult:
        """
        Main processing pipeline with consensus loop
        
        Args:
            request: Generation request with input audio or prompt
            
        Returns:
            ConsensusLoopResult with final outputs and telemetry
        """
        self.state = AgentState.PROCESSING
        result = ConsensusLoopResult(success=False, iterations=0)
        
        try:
            # Step 1: Auditor analyzes input (or skip if prompt-only)
            sonic_signature = None
            if request.input_audio_path:
                logger.info("Auditor analyzing input audio...")
                sonic_signature = await self.auditor.analyze(request.input_audio_path)
                
                if not sonic_signature.acceptable:
                    result.rejection_reasons.append(f"Input rejected: {sonic_signature.rejection_reason}")
                    return result
            
            # Consensus loop
            for iteration in range(result.max_iterations):
                result.iterations = iteration + 1
                logger.info(f"Consensus loop iteration {iteration + 1}/{result.max_iterations}")
                
                # Step 2: Composer structures
                logger.info("Composer generating structure...")
                section_plan = await self.composer.compose(
                    sonic_signature=sonic_signature,
                    user_prompt=request.prompt,
                    style=request.style,
                    duration=request.duration
                )
                
                # Step 3: Alchemist generates
                logger.info("Alchemist generating audio...")
                generated_stems = await self.alchemist.generate(
                    section_plan=section_plan,
                    lyrics=request.lyrics,
                    bpm=sonic_signature.bpm if sonic_signature else request.bpm,
                    key=sonic_signature.key if sonic_signature else request.key
                )
                
                # Step 4: Engineer masters
                logger.info("Engineer mastering...")
                mastered_outputs = await self.engineer.master(
                    input_paths=generated_stems,
                    params=request.mastering_params
                )
                
                # Step 5: Auditor critiques
                logger.info("Auditor critiquing output...")
                critique = await self.auditor.critique(
                    output_paths=mastered_outputs,
                    expected_style=request.style,
                    expected_lufs=request.mastering_params.target_lufs
                )
                
                if critique.approved:
                    result.success = True
                    result.auditor_approved = True
                    result.final_output_paths = mastered_outputs
                    result.telemetry = critique.telemetry
                    logger.info(f"Consensus reached after {iteration + 1} iterations")
                    break
                else:
                    result.rejection_reasons.extend(critique.rejection_reasons)
                    logger.warning(f"Output rejected: {critique.rejection_reasons}")
                    
                    # Update request for next iteration (refine prompts)
                    request = self._refine_request(request, critique)
            
            # Push to REAPER if enabled
            if result.success and self.reaper_interface:
                await self.reaper_interface.import_stems(
                    stem_paths=result.final_output_paths,
                    track_name=request.track_name or "MAAPS Generated"
                )
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            result.rejection_reasons.append(str(e))
        
        finally:
            self.state = AgentState.IDLE
        
        return result
    
    def _refine_request(self, request: GenerationRequest, critique: Dict) -> GenerationRequest:
        """Refine generation parameters based on auditor critique"""
        # Simple refinement strategy - can be enhanced with LLM feedback
        refined = request.model_copy()
        
        if critique.get('too_quiet'):
            refined.mastering_params.target_lufs = min(
                refined.mastering_params.target_lufs + 2,
                -9.0  # Max loudness
            )
        
        if critique.get('wrong_style'):
            # Strengthen style prompt
            refined.prompt = f"{refined.prompt}, more {critique.get('style_mismatch', 'intense')}"
        
        return refined
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down MAAPS v4.0...")
        self.state = AgentState.ERROR
        
        if self.ray_initialized:
            ray.shutdown()
        
        if self.reaper_interface:
            await self.reaper_interface.disconnect()
        
        logger.info("MAAPS v4.0 shutdown complete")


@serve.deployment(ray_actor_options={"num_cpus": 2})
class MAAPSV4Service:
    """Ray Serve deployment for MAAPS v4.0"""
    
    def __init__(self, config: Dict[str, Any]):
        self.orchestrator = MAAPSV4Orchestrator(config)
        self.orchestrator.initialize_ray()
    
    async def __call__(self, request: GenerationRequest) -> ConsensusLoopResult:
        return await self.orchestrator.process_request(request)


def main():
    """Main entry point"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    config = {
        'llm_provider': os.getenv('LLM_PROVIDER', 'gemini'),
        'heartmula_model': os.getenv('HEARTMULA_MODEL', 'HeartMuLa-oss-3B'),
        'target_lufs': float(os.getenv('TARGET_LUFS', '-14.0')),
        'true_peak': float(os.getenv('TRUE_PEAK', '-1.0')),
        'enable_reaper': os.getenv('ENABLE_REAPER', 'true').lower() == 'true',
        'ray_address': os.getenv('RAY_ADDRESS', 'auto')
    }
    
    orchestrator = MAAPSV4Orchestrator(config)
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.run(orchestrator.shutdown())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 60)
    logger.info("MAAPS v4.0 TITAN REBUILT - Starting")
    logger.info("=" * 60)
    logger.info(f"Configuration: {config}")
    logger.info("Agents loaded: Auditor, Composer, Alchemist, Engineer")
    logger.info("REAPER Neural Interface: Ready")
    logger.info("=" * 60)
    
    # Keep running
    try:
        while True:
            asyncio.run(asyncio.sleep(1))
    except KeyboardInterrupt:
        pass
    finally:
        asyncio.run(orchestrator.shutdown())


if __name__ == '__main__':
    main()
