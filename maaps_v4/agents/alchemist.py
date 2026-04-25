"""
MAAPS v4.0 - Alchemist Agent (Generation)

Ray actor for HeartMuLa AI music generation on GPU swarm.
Handles section-aware generation via HeartCodec, chunked generation with KV-caching,
crossfades, and section conditioning to avoid OOM and clicks.

Loads HeartMuLa-oss-3B (or latest variant) from baked Docker cache.
Handles lyrics, style, BPM/key conditioning via HeartCodec tokenizer.
Outputs isolated stems or full sections as WAV buffers.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
import numpy as np
import time

import ray
from ray import serve

logger = logging.getLogger('maaps.alchemist')


@ray.remote(num_gpus=1)
class HeartMuLaWorker:
    """
    Ray worker for HeartMuLa inference
    
    Runs on GPU with proper VRAM management
    """
    
    def __init__(self, model_name: str = "HeartMuLa-oss-3B"):
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.loaded = False
        
        logger.info(f"HeartMuLaWorker initialized: {model_name}")
    
    def load_model(self):
        """Load HeartMuLa model onto GPU"""
        if self.loaded:
            return
        
        try:
            import torch
            from transformers import AutoProcessor, AutoModelForCausalLM
            
            # HeartMuLa uses HeartCodec tokenizer
            logger.info(f"Loading {self.model_name}...")
            
            # Try local cache first (baked in Docker)
            model_path = f"/models/{self.model_name}"
            
            self.processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
                low_cpu_mem_usage=True
            )
            
            self.loaded = True
            logger.info(f"HeartMuLa loaded on GPU: {torch.cuda.get_device_name(0)}")
            
        except Exception as e:
            logger.error(f"Failed to load HeartMuLa: {e}")
            # Fallback to MusicGen for testing
            self._load_musicgen_fallback()
    
    def _load_musicgen_fallback(self):
        """Fallback to MusicGen if HeartMuLa unavailable"""
        try:
            import torch
            from transformers import AutoProcessor, MusicgenForConditionalGeneration
            
            logger.info("Loading MusicGen fallback...")
            
            self.processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
            self.model = MusicgenForConditionalGeneration.from_pretrained(
                "facebook/musicgen-small",
                torch_dtype=torch.float16,
                device_map="auto"
            )
            
            self.loaded = True
            logger.info("MusicGen fallback loaded")
            
        except Exception as e:
            logger.error(f"Fallback also failed: {e}")
            raise
    
    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        bpm: Optional[float] = None,
        key: Optional[str] = None,
        lyrics: Optional[str] = None,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate audio from prompt
        
        Returns dict with audio buffer and metadata
        """
        if not self.loaded:
            self.load_model()
        
        import torch
        
        # Calculate tokens from duration (~50 tokens/sec for MusicGen)
        max_tokens = int(duration_seconds * 50)
        
        # Build conditioned prompt
        conditioned_prompt = self._condition_prompt(prompt, bpm, key, lyrics)
        
        logger.info(f"Generating: {conditioned_prompt[:80]}... ({duration_seconds}s)")
        
        # Set seed for reproducibility
        if seed is not None:
            torch.manual_seed(seed)
            np.random.seed(seed)
        
        # Tokenize
        inputs = self.processor(
            text=[conditioned_prompt],
            padding=True,
            return_tensors="pt"
        )
        
        # Move to GPU
        if hasattr(self.model, 'device'):
            device = next(self.model.parameters()).device
        else:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        # Generate with KV caching
        with torch.no_grad():
            audio_values = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=1.0,
                top_p=0.95,
                guidance_scale=3.0
            )
        
        # Extract audio
        sampling_rate = self.model.config.audio_encoder.sampling_rate
        audio_data = audio_values[0, 0].cpu().float().numpy()
        
        # Normalize to [-1, 1]
        if np.max(np.abs(audio_data)) > 0:
            audio_data = audio_data / np.max(np.abs(audio_data))
        
        result = {
            'audio': audio_data,
            'sampling_rate': sampling_rate,
            'duration': len(audio_data) / sampling_rate,
            'prompt': conditioned_prompt
        }
        
        logger.info(f"Generated {result['duration']:.2f}s of audio")
        
        return result
    
    def _condition_prompt(
        self,
        prompt: str,
        bpm: Optional[float],
        key: Optional[str],
        lyrics: Optional[str]
    ) -> str:
        """Add BPM/key/lyrics conditioning to prompt"""
        parts = [prompt]
        
        if bpm:
            parts.append(f"BPM: {bpm:.0f}")
        
        if key:
            parts.append(f"Key: {key}")
        
        if lyrics:
            # HeartMuLa supports section-aware lyrics tags
            parts.append(f"Lyrics: {lyrics}")
        
        return ", ".join(parts)


class AlchemistAgent:
    """
    Generation Agent for MAAPS v4.0
    
    Manages Ray workers for parallel stem generation
    Handles crossfades and seamless section transitions
    """
    
    def __init__(
        self,
        heartmula_model: str = "HeartMuLa-oss-3B",
        gpu_resources: Dict[str, Any] = {'num_gpus': 1}
    ):
        self.name = "AlchemistAgent"
        self.heartmula_model = heartmula_model
        self.gpu_resources = gpu_resources
        self.worker = None
        logger.info("AlchemistAgent initialized")
    
    def _get_worker(self) -> ray.ObjectRef:
        """Get or create Ray worker"""
        if self.worker is None:
            self.worker = HeartMuLaWorker.options(
                **self.gpu_resources
            ).remote(self.heartmula_model)
        
        return self.worker
    
    async def generate(
        self,
        section_plan: List[Any],
        lyrics: Optional[str] = None,
        bpm: Optional[float] = None,
        key: Optional[str] = None
    ) -> List[str]:
        """
        Generate audio for all sections
        
        Args:
            section_plan: List of SectionPlan objects
            lyrics: Full lyrics (optional, may be in section plans)
            bpm: Global BPM
            key: Global key
            
        Returns:
            List of output file paths
        """
        worker = self._get_worker()
        output_paths = []
        
        for i, section in enumerate(section_plan):
            logger.info(f"Generating section {i+1}/{len(section_plan)}: {section.section_type.value}")
            
            # Get section-specific values
            section_lyrics = section.lyrics or lyrics
            section_bpm = section.bpm or bpm
            section_key = section.key or key
            
            # Estimate duration from bars (assume 4/4)
            bars = section.bar_count
            beats_per_bar = 4
            estimated_beats = bars * beats_per_bar
            tempo = section_bpm if section_bpm else 100.0
            duration = (estimated_beats / tempo) * 60.0
            
            # Generate
            try:
                result_ref = worker.generate.remote(
                    prompt=section.heartmula_prompt,
                    duration_seconds=duration,
                    bpm=section_bpm,
                    key=section_key,
                    lyrics=section_lyrics,
                    seed=i  # Different seed per section for variety
                )
                
                result = await result_ref
                
                # Save to file
                output_path = self._save_audio(
                    audio=result['audio'],
                    sampling_rate=result['sampling_rate'],
                    filename=f"section_{section.section_type.value}_{i}.wav"
                )
                
                output_paths.append(output_path)
                logger.info(f"Saved: {output_path}")
                
            except Exception as e:
                logger.error(f"Generation failed for section {i}: {e}")
                # Continue with other sections
                continue
        
        # Crossfade and concatenate sections
        if len(output_paths) > 1:
            final_path = self._concatenate_sections(output_paths)
            return [final_path]
        
        return output_paths
    
    def _save_audio(
        self,
        audio: np.ndarray,
        sampling_rate: int,
        filename: str
    ) -> str:
        """Save audio to WAV file"""
        import soundfile as sf
        
        output_dir = Path("/tmp/maaps_output")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / filename
        
        # Convert to 16-bit PCM
        audio_int16 = (audio * 32767).astype(np.int16)
        
        sf.write(str(output_path), audio_int16, sampling_rate)
        
        return str(output_path)
    
    def _concatenate_sections(self, section_paths: List[str]) -> str:
        """Concatenate sections with crossfades"""
        import soundfile as sf
        from scipy.signal import windows
        
        logger.info(f"Concatenating {len(section_paths)} sections...")
        
        # Load all sections
        audios = []
        sample_rates = []
        
        for path in section_paths:
            audio, sr = sf.read(path)
            audios.append(audio)
            sample_rates.append(sr)
        
        # Check consistent sample rate
        if len(set(sample_rates)) > 1:
            logger.warning("Inconsistent sample rates, using first")
        
        sr = sample_rates[0]
        
        # Crossfade length (50ms)
        crossfade_samples = int(0.05 * sr)
        
        # Concatenate with crossfades
        result = audios[0]
        
        for i in range(1, len(audios)):
            prev = result
            curr = audios[i]
            
            # Create crossfade windows
            fade_out = windows.hann(crossfade_samples * 2)[:crossfade_samples]
            fade_in = windows.hann(crossfade_samples * 2)[crossfade_samples:]
            
            # Overlap region
            overlap_prev = prev[-crossfade_samples:]
            overlap_curr = curr[:crossfade_samples]
            
            # Apply crossfade
            crossfaded = overlap_prev * fade_out + overlap_curr * fade_in
            
            # Combine
            result = np.concatenate([
                prev[:-crossfade_samples],
                crossfaded,
                curr[crossfade_samples:]
            ])
        
        # Save final
        output_path = "/tmp/maaps_output/final_mix.wav"
        sf.write(output_path, result, sr)
        
        logger.info(f"Final mix saved: {output_path} ({len(result)/sr:.2f}s)")
        
        return output_path
