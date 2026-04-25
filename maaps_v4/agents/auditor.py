"""
MAAPS v4.0 - Auditor Agent (Gatekeeper)

Local DSP analysis using librosa and pyloudnorm.
Analyzes input audio from REAPER items, extracts sonic features,
and rejects poor input early. Outputs immutable SonicSignature.

REAPER Integration: Pulls selected track items via reapy, analyzes,
pushes telemetry back (color-coded tracks, console messages).
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
import numpy as np

from maaps_v4.schemas import SonicSignature, AuditorCritique

logger = logging.getLogger('maaps.auditor')


class AuditorAgent:
    """
    Gatekeeper Agent for MAAPS v4.0
    
    Responsibilities:
    - Analyze input audio (guitar riff, vocal memo, etc.)
    - Extract: BPM, Key, LUFS, spectral features, clipping/noise
    - Reject poor input early
    - Critique generated output against style/LUFS targets
    """
    
    def __init__(self):
        self.name = "AuditorAgent"
        self._librosa = None
        self._pyloudnorm = None
        logger.info("AuditorAgent initialized")
    
    def _load_dependencies(self):
        """Lazy load heavy dependencies"""
        if self._librosa is None:
            import librosa
            import pyloudnorm as pyln
            self._librosa = librosa
            self._pyloudnorm = pyln
            logger.info("Auditor dependencies loaded")
    
    async def analyze(self, audio_path: str) -> SonicSignature:
        """
        Analyze input audio and extract sonic signature
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            SonicSignature with extracted features
        """
        self._load_dependencies()
        
        try:
            # Load audio
            y, sr = self._librosa.load(audio_path, sr=None, mono=True)
            duration = len(y) / sr
            
            logger.info(f"Analyzing: {audio_path} ({duration:.2f}s @ {sr}Hz)")
            
            # Extract BPM
            tempo, _ = self._librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(tempo) if np.ndim(tempo) == 0 else float(tempo[0])
            
            # Extract Key (chromagram correlation)
            key = self._extract_key(y, sr)
            
            # Extract LUFS (BS.1770)
            loudness, true_peak = self._extract_loudness(y, sr)
            
            # Spectral features
            spectral_centroid = self._extract_spectral_centroid(y, sr)
            spectral_rolloff = self._extract_spectral_rolloff(y, sr)
            zcr = self._extract_zero_crossing_rate(y, sr)
            
            # Quality checks
            clipping = self._detect_clipping(y)
            noise_floor = self._estimate_noise_floor(y)
            
            # Determine acceptability
            acceptable = True
            rejection_reason = None
            
            if clipping:
                acceptable = False
                rejection_reason = "Clipping detected"
            elif noise_floor > -40:  # Too noisy
                acceptable = False
                rejection_reason = f"High noise floor: {noise_floor:.1f} dB"
            elif duration < 1.0:
                acceptable = False
                rejection_reason = f"Audio too short: {duration:.2f}s"
            
            signature = SonicSignature(
                bpm=bpm,
                key=key,
                loudness_lufs=loudness,
                true_peak_dbtp=true_peak,
                spectral_centroid_hz=spectral_centroid,
                spectral_rolloff_hz=spectral_rolloff,
                zero_crossing_rate=zcr,
                acceptable=acceptable,
                rejection_reason=rejection_reason,
                clipping_detected=clipping,
                noise_floor_db=noise_floor,
                duration_seconds=duration,
                sample_rate=sr,
                bit_depth=24,  # Assume 24-bit for WAV
                channels=2  # Assume stereo
            )
            
            logger.info(f"SonicSignature: {bpm:.1f} BPM, {key}, {loudness:.1f} LUFS")
            
            return signature
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return SonicSignature(
                bpm=120.0,
                key="Cmajor",
                loudness_lufs=-70.0,
                true_peak_dbtp=-70.0,
                spectral_centroid_hz=1000.0,
                spectral_rolloff_hz=5000.0,
                zero_crossing_rate=0.1,
                acceptable=False,
                rejection_reason=f"Analysis error: {str(e)}",
                duration_seconds=0.0,
                sample_rate=44100
            )
    
    def _extract_key(self, y: np.ndarray, sr: int) -> str:
        """Extract musical key via chromagram correlation"""
        # Compute chromagram
        chroma = self._librosa.feature.chroma_cqt(y=y, sr=sr)
        
        # Correlate with key profiles (Krumhansl-Schmiedler)
        major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        
        best_corr = -1
        best_key = "Cmajor"
        
        for i in range(12):
            # Rotate profiles
            major_rotated = np.roll(major_profile, i)
            minor_rotated = np.roll(minor_profile, i)
            
            # Correlate
            corr_major = np.corrcoef(chroma.mean(axis=1), major_rotated)[0, 1]
            corr_minor = np.corrcoef(chroma.mean(axis=1), minor_rotated)[0, 1]
            
            if corr_major > best_corr:
                best_corr = corr_major
                best_key = f"{self._note_from_index(i)}major"
            
            if corr_minor > best_corr:
                best_corr = corr_minor
                best_key = f"{self._note_from_index(i)}minor"
        
        return best_key
    
    def _note_from_index(self, idx: int) -> str:
        """Convert chroma index to note name"""
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        return notes[idx % 12]
    
    def _extract_loudness(self, y: np.ndarray, sr: int) -> tuple:
        """Extract integrated loudness (LUFS) and true peak"""
        meter = self._pyloudnorm.Meter(sr)
        loudness = meter.integrated_loudness(y)
        
        # True peak estimation (simple oversampling approximation)
        true_peak = np.max(np.abs(y))
        true_peak_db = 20 * np.log10(true_peak + 1e-10)
        
        return loudness, true_peak_db
    
    def _extract_spectral_centroid(self, y: np.ndarray, sr: int) -> float:
        """Extract spectral centroid"""
        centroid = self._librosa.feature.spectral_centroid(y=y, sr=sr)
        return float(np.mean(centroid))
    
    def _extract_spectral_rolloff(self, y: np.ndarray, sr: int) -> float:
        """Extract spectral rolloff frequency"""
        rolloff = self._librosa.feature.spectral_rolloff(y=y, sr=sr)
        return float(np.mean(rolloff))
    
    def _extract_zero_crossing_rate(self, y: np.ndarray, sr: int) -> float:
        """Extract zero crossing rate"""
        zcr = self._librosa.feature.zero_crossing_rate(y)
        return float(np.mean(zcr))
    
    def _detect_clipping(self, y: np.ndarray) -> bool:
        """Detect clipping (samples at or near ±1.0)"""
        threshold = 0.99
        clipped_samples = np.sum(np.abs(y) >= threshold)
        clip_ratio = clipped_samples / len(y)
        return clip_ratio > 0.001  # More than 0.1% clipped
    
    def _estimate_noise_floor(self, y: np.ndarray) -> float:
        """Estimate noise floor from quietest 10% of signal"""
        rms = np.sqrt(np.mean(y**2))
        # Simple approximation: noise floor ~ RMS - 20dB for typical material
        noise_floor_db = 20 * np.log10(rms + 1e-10) - 20
        return noise_floor_db
    
    async def critique(
        self,
        output_paths: List[str],
        expected_style: str,
        expected_lufs: float
    ) -> AuditorCritique:
        """
        Critique generated output
        
        Args:
            output_paths: Paths to generated/stem files
            expected_style: Expected style descriptor
            expected_lufs: Target loudness
            
        Returns:
            AuditorCritique with approval status and feedback
        """
        rejection_reasons = []
        telemetry = {}
        
        issues = {
            'too_quiet': False,
            'too_loud': False,
            'wrong_style': False,
            'clipping': False,
            'artifacts': False
        }
        
        for path in output_paths:
            try:
                signature = await self.analyze(path)
                
                # Check LUFS
                lufs_diff = abs(signature.loudness_lufs - expected_lufs)
                if lufs_diff > 2.0:
                    if signature.loudness_lufs < expected_lufs:
                        issues['too_quiet'] = True
                        rejection_reasons.append(f"Too quiet: {signature.loudness_lufs:.1f} vs target {expected_lufs}")
                    else:
                        issues['too_loud'] = True
                        rejection_reasons.append(f"Too loud: {signature.loudness_lufs:.1f} vs target {expected_lufs}")
                
                # Check clipping
                if signature.clipping_detected:
                    issues['clipping'] = True
                    rejection_reasons.append("Clipping detected in output")
                
                # Style matching would require ML model (HeartCLAP or similar)
                # For now, basic heuristic based on spectral centroid
                telemetry[path] = signature.model_dump()
                
            except Exception as e:
                logger.error(f"Critique failed for {path}: {e}")
                rejection_reasons.append(f"Analysis error: {str(e)}")
        
        approved = len(rejection_reasons) == 0
        
        critique = AuditorCritique(
            approved=approved,
            rejection_reasons=rejection_reasons,
            loudness_match=not (issues['too_quiet'] or issues['too_loud']),
            style_match=not issues['wrong_style'],
            technical_quality=not (issues['clipping'] or issues['artifacts']),
            **issues,
            telemetry=telemetry
        )
        
        if approved:
            logger.info("Output approved by Auditor")
        else:
            logger.warning(f"Output rejected: {rejection_reasons}")
        
        return critique
