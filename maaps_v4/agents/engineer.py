"""
MAAPS v4.0 - Engineer Agent (Mastering)

Headless DSP mastering using Pedalboard (Spotify's C++ engine).
Applies highpass, shelves, compression, limiting with strict LUFS normalization
and true-peak safety. Genre/brand-specific presets for broadcast-ready masters
(-9 to -14 LUFS).

Post-processes Alchemist output into final deliverables.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import numpy as np

from maaps_v4.schemas import MasteringParams

logger = logging.getLogger('maaps.engineer')


class EngineerAgent:
    """
    Mastering Agent for MAAPS v4.0
    
    Responsibilities:
    - Apply EQ (highpass, shelves)
    - Compression with genre-appropriate settings
    - Limiting with true-peak ceiling
    - BS.1770 LUFS normalization
    - Genre/brand preset chains
    """
    
    def __init__(
        self,
        target_lufs: float = -14.0,
        true_peak: float = -1.0
    ):
        self.name = "EngineerAgent"
        self.default_target_lufs = target_lufs
        self.default_true_peak = true_peak
        self._pedalboard = None
        
        logger.info(f"EngineerAgent initialized (target: {target_lufs} LUFS)")
    
    def _load_pedalboard(self):
        """Lazy load Pedalboard"""
        if self._pedalboard is None:
            from pedalboard import Pedalboard
            self._pedalboard = Pedalboard
            logger.info("Pedalboard loaded")
    
    async def master(
        self,
        input_paths: List[str],
        params: Optional[MasteringParams] = None
    ) -> List[str]:
        """
        Master audio files
        
        Args:
            input_paths: Paths to generated audio
            params: Mastering parameters (optional, uses defaults if not provided)
            
        Returns:
            List of mastered file paths
        """
        self._load_pedalboard()
        
        if params is None:
            params = MasteringParams(
                target_lufs=self.default_target_lufs,
                true_peak_limit=self.default_true_peak
            )
        
        output_paths = []
        
        for input_path in input_paths:
            try:
                logger.info(f"Mastering: {input_path}")
                
                output_path = self._master_file(input_path, params)
                output_paths.append(output_path)
                
                logger.info(f"Mastered: {output_path}")
                
            except Exception as e:
                logger.error(f"Mastering failed for {input_path}: {e}", exc_info=True)
                # Return original if mastering fails
                output_paths.append(input_path)
        
        return output_paths
    
    def _master_file(
        self,
        input_path: str,
        params: MasteringParams
    ) -> str:
        """Master a single file"""
        import soundfile as sf
        import pyloudnorm as pyln
        
        # Load audio
        audio, sr = sf.read(input_path)
        
        # Convert to mono if needed for processing
        if audio.ndim == 1:
            audio = audio[:, np.newaxis]
        
        # Build pedalboard chain
        board = self._build_chain(params, sr)
        
        # Process
        processed = board.process(audio, sr)
        
        # LUFS normalization
        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(processed)
        
        if loudness > -70:  # Valid measurement
            normalized = pyln.normalize.loudness(
                processed,
                loudness,
                params.target_lufs
            )
        else:
            normalized = processed
        
        # True peak limiting (simple clip prevention)
        normalized = self._apply_true_peak_limit(normalized, params.true_peak_limit)
        
        # Save
        output_path = self._get_output_path(input_path, "mastered")
        
        # Convert back to original channels if needed
        if audio.shape[1] == 1 and normalized.ndim == 2:
            normalized = normalized[:, 0]
        
        sf.write(output_path, normalized, sr)
        
        return output_path
    
    def _build_chain(self, params: MasteringParams, sample_rate: int):
        """Build Pedalboard effects chain"""
        from pedalboard import (
            Pedalboard,
            HighpassFilter,
            LowShelfFilter,
            HighShelfFilter,
            Compressor,
            Limiter
        )
        
        board = Pedalboard()
        
        # Highpass filter (remove sub-bass rumble)
        board.append(HighpassFilter(
            frequency_hz=params.highpass_hz
        ))
        
        # Low shelf (warmth control)
        if params.lowshelf_gain_db != 0:
            board.append(LowShelfFilter(
                frequency_hz=params.lowshelf_hz,
                gain_db=params.lowshelf_gain_db,
                q=0.7
            ))
        
        # High shelf (air/brightness)
        if params.highshelf_gain_db != 0:
            board.append(HighShelfFilter(
                frequency_hz=params.highshelf_hz,
                gain_db=params.highshelf_gain_db,
                q=0.7
            ))
        
        # Compression
        board.append(Compressor(
            threshold_db=params.compression_threshold_db,
            ratio=params.compression_ratio,
            attack_ms=params.compression_attack_ms,
            release_ms=params.compression_release_ms
        ))
        
        # Limiter (true peak ceiling)
        board.append(Limiter(
            threshold_db=params.limiter_ceiling_db,
            lookaround_ms=1.0
        ))
        
        logger.debug(f"Built chain: HPF@{params.highpass_hz}Hz, Comp@{params.compression_threshold_db}dB, Lim@{params.limiter_ceiling_db}dB")
        
        return board
    
    def _apply_true_peak_limit(
        self,
        audio: np.ndarray,
        limit_dbtp: float
    ) -> np.ndarray:
        """Apply true peak limiting (soft clipping)"""
        # Convert dBTP to linear
        limit_linear = 10 ** (limit_dbtp / 20)
        
        # Soft clip
        clipped = np.tanh(audio / limit_linear) * limit_linear
        
        return clipped
    
    def _get_output_path(
        self,
        input_path: str,
        suffix: str
    ) -> str:
        """Generate output path with suffix"""
        input_p = Path(input_path)
        output_p = input_p.parent / f"{input_p.stem}_{suffix}{input_p.suffix}"
        return str(output_p)
    
    def get_preset(self, preset_name: str) -> MasteringParams:
        """Get genre-specific mastering preset"""
        presets = {
            'modern_metal': MasteringParams(
                target_lufs=-9.0,
                true_peak_limit=-1.0,
                highpass_hz=40.0,
                lowshelf_hz=120.0,
                lowshelf_gain_db=2.0,
                highshelf_hz=10000.0,
                highshelf_gain_db=3.0,
                compression_threshold_db=-24.0,
                compression_ratio=4.0,
                compression_attack_ms=5.0,
                compression_release_ms=50.0,
                limiter_ceiling_db=-0.3
            ),
            'electronic_dance': MasteringParams(
                target_lufs=-10.0,
                true_peak_limit=-1.0,
                highpass_hz=30.0,
                lowshelf_hz=100.0,
                lowshelf_gain_db=3.0,
                highshelf_hz=8000.0,
                highshelf_gain_db=2.0,
                compression_threshold_db=-20.0,
                compression_ratio=3.0,
                compression_attack_ms=10.0,
                compression_release_ms=100.0,
                limiter_ceiling_db=-0.3
            ),
            'broadcast_podcast': MasteringParams(
                target_lufs=-16.0,
                true_peak_limit=-2.0,
                highpass_hz=80.0,
                lowshelf_hz=150.0,
                lowshelf_gain_db=0.0,
                highshelf_hz=5000.0,
                highshelf_gain_db=1.0,
                compression_threshold_db=-15.0,
                compression_ratio=2.5,
                compression_attack_ms=5.0,
                compression_release_ms=50.0,
                limiter_ceiling_db=-1.0
            ),
            'cinematic': MasteringParams(
                target_lufs=-14.0,
                true_peak_limit=-2.0,
                highpass_hz=30.0,
                lowshelf_hz=80.0,
                lowshelf_gain_db=1.0,
                highshelf_hz=12000.0,
                highshelf_gain_db=2.0,
                compression_threshold_db=-18.0,
                compression_ratio=2.0,
                compression_attack_ms=20.0,
                compression_release_ms=200.0,
                limiter_ceiling_db=-1.0
            ),
            'lofi_hiphop': MasteringParams(
                target_lufs=-12.0,
                true_peak_limit=-1.0,
                highpass_hz=50.0,
                lowshelf_hz=200.0,
                lowshelf_gain_db=2.0,
                highshelf_hz=4000.0,
                highshelf_gain_db=-2.0,
                compression_threshold_db=-12.0,
                compression_ratio=3.0,
                compression_attack_ms=15.0,
                compression_release_ms=150.0,
                limiter_ceiling_db=-0.5
            )
        }
        
        return presets.get(preset_name, MasteringParams())
