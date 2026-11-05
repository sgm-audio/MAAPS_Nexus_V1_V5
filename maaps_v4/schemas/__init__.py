"""
MAAPS v4.0 - Strict Pydantic Schemas for Enterprise-Ready Audio Production

All schemas are immutable where possible, with full validation for:
- Sonic signatures (BPM, key, LUFS, spectral features)
- Generation requests (HeartMuLa-optimized prompts, section control)
- Mastering parameters (deterministic LUFS, true-peak safety)
- REAPER telemetry (real-time track state)
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from datetime import datetime
import re


class AudioQuality(Enum):
    """Audio quality presets"""
    DRAFT = "draft"  # Fast iteration
    STANDARD = "standard"  # Production ready
    MASTER = "master"  # Final delivery


class StemType(Enum):
    """Stem types for isolated generation"""
    DRUMS = "drums"
    BASS = "bass"
    VOCALS = "vocals"
    GUITAR = "guitar"
    KEYS = "keys"
    SYNTH = "synth"
    FX = "fx"
    FULL_MIX = "full_mix"


class SectionType(Enum):
    """Song section types (powers-of-2 bars)"""
    INTRO = "intro"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    OUTRO = "outro"
    BREAKDOWN = "breakdown"
    BUILDUP = "buildup"
    DROP = "drop"


# =====================================
# Sonic Signature (Auditor Output)
# =====================================

class SonicSignature(BaseModel):
    """
    Immutable sonic fingerprint from Auditor Agent
    
    Extracted via librosa.beat, chromagram correlation, pyloudnorm BS.1770
    """
    model_config = ConfigDict(frozen=True)
    
    # Core metrics
    bpm: float = Field(ge=40.0, le=220.0, description="Beats per minute")
    key: str = Field(pattern=r'^[A-G][#b]?\s?(major|minor)$', description="Musical key e.g., 'C# minor' or 'Cmajor'")
    loudness_lufs: float = Field(ge=-70.0, le=0.0, description="Integrated loudness LUFS")
    true_peak_dbtp: float = Field(ge=-70.0, le=10.0, description="True peak dBTP")
    
    # Spectral features
    spectral_centroid_hz: float = Field(ge=0.0, description="Spectral centroid in Hz")
    spectral_rolloff_hz: float = Field(ge=0.0, description="Spectral rolloff frequency")
    zero_crossing_rate: float = Field(ge=0.0, le=1.0, description="Zero crossing rate")
    
    # Quality flags
    acceptable: bool = True
    rejection_reason: Optional[str] = None
    clipping_detected: bool = False
    noise_floor_db: float = Field(default=-60.0, ge=-100.0, le=0.0)
    
    # Metadata
    duration_seconds: float = Field(ge=0.0)
    sample_rate: int = Field(default=44100, ge=8000, le=192000)
    bit_depth: int = Field(default=24, ge=16, le=32)
    channels: int = Field(default=2, ge=1, le=8)
    
    @field_validator('key')
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Normalize key notation - accepts 'C major', 'Cmajor', 'C# minor', etc."""
        # Normalize: lowercase, remove spaces, expand abbreviations
        v_lower = v.lower().replace(' ', '')
        
        # Expand abbreviations carefully (check for exact matches)
        if v_lower.endswith('maj'):
            v_lower = v_lower[:-3] + 'major'
        elif v_lower.endswith('min'):
            v_lower = v_lower[:-3] + 'minor'
        
        # Validate against pattern
        if not re.match(r'^[a-g][#b]?(major|minor)$', v_lower):
            raise ValueError(f"Invalid key format: {v}. Use format like 'C major', 'C#minor', 'A minor'")
        
        # Return normalized format with space: "C major" or "C# minor"
        match = re.match(r'^([a-g][#b]?)(major|minor)$', v_lower)
        if match:
            return f"{match.group(1).capitalize()} {match.group(2)}"
        return v


# =====================================
# Generation Request (Composer → Alchemist)
# =====================================

class SectionPlan(BaseModel):
    """
    Song structure plan from Composer Agent
    
    HeartMuLa-optimized with section-aware tags and lyrics
    """
    section_type: SectionType
    bar_count: int = Field(ge=1, description="Must be power of 2: 1, 2, 4, 8, 16, 32")
    intensity: float = Field(ge=0.0, le=1.0, description="Relative intensity 0-1")
    heartmula_prompt: str = Field(min_length=10, description="Optimized prompt for HeartMuLa")
    style_tags: List[str] = Field(default_factory=list, description="Style descriptors")
    lyrics: Optional[str] = Field(None, min_length=1, description="Lyrics with [Verse]/[Chorus] tags")
    bpm: Optional[float] = Field(None, ge=40.0, le=220.0)
    key: Optional[str] = Field(None, pattern=r'^[A-G][#b]?(major|minor)$')
    
    @field_validator('bar_count')
    @classmethod
    def validate_power_of_two(cls, v: int) -> int:
        if v & (v - 1) != 0:
            raise ValueError(f"bar_count must be power of 2, got {v}")
        return v


class MasteringParams(BaseModel):
    """
    Mastering chain parameters for Engineer Agent
    
    Deterministic LUFS normalization with true-peak safety
    """
    target_lufs: float = Field(default=-14.0, ge=-24.0, le=-9.0, description="Target integrated loudness")
    true_peak_limit: float = Field(default=-1.0, ge=-3.0, le=0.0, description="True peak ceiling dBTP")
    loudness_range: Optional[float] = Field(None, ge=0.0, le=20.0, description="Optional LRA target")
    
    # Pedalboard chain
    highpass_hz: float = Field(default=30.0, ge=20.0, le=100.0, description="Highpass filter")
    lowshelf_hz: float = Field(default=100.0, ge=50.0, le=200.0)
    lowshelf_gain_db: float = Field(default=0.0, ge=-6.0, le=6.0)
    highshelf_hz: float = Field(default=8000.0, ge=4000.0, le=16000.0)
    highshelf_gain_db: float = Field(default=0.0, ge=-6.0, le=6.0)
    
    compression_threshold_db: float = Field(default=-18.0, ge=-40.0, le=0.0)
    compression_ratio: float = Field(default=2.0, ge=1.0, le=20.0)
    compression_attack_ms: float = Field(default=10.0, ge=1.0, le=100.0)
    compression_release_ms: float = Field(default=100.0, ge=10.0, le=1000.0)
    
    limiter_ceiling_db: float = Field(default=-0.3, ge=-3.0, le=0.0)
    
    # Preset name for genre-specific chains
    preset_name: Optional[str] = Field(None, description="e.g., 'modern_metal', 'broadcast_podcast'")


class GenerationRequest(BaseModel):
    """
    Main generation request from REAPER or API
    
    Supports prompt-only or audio-informed generation
    """
    # Input
    input_audio_path: Optional[str] = Field(None, description="Path to input audio for analysis")
    prompt: str = Field(min_length=5, description="User creative prompt")
    style: str = Field(default="electronic", description="Genre/style descriptor")
    
    # Structure
    duration: float = Field(ge=5.0, le=600.0, description="Target duration in seconds")
    sections: List[SectionPlan] = Field(default_factory=list, description="Optional explicit section plan")
    
    # Conditioning
    bpm: Optional[float] = Field(None, ge=40.0, le=220.0)
    key: Optional[str] = Field(None, pattern=r'^[A-G][#b]?(major|minor)$')
    lyrics: Optional[str] = Field(None, description="Full lyrics with section tags")
    
    # Output
    track_name: Optional[str] = Field(None, description="REAPER track name")
    stem_types: List[StemType] = Field(default=[StemType.FULL_MIX], description="Which stems to generate")
    quality: AudioQuality = Field(default=AudioQuality.STANDARD)
    
    # Mastering
    mastering_params: MasteringParams = Field(default_factory=MasteringParams)
    
    # Control
    dry_run: bool = Field(default=False, description="Validate only, no generation")
    max_iterations: int = Field(default=5, ge=1, le=10, description="Consensus loop max iterations")
    
    @field_validator('sections')
    @classmethod
    def validate_sections_duration(cls, sections: List[SectionPlan]) -> List[SectionPlan]:
        """Ensure sections don't exceed reasonable duration"""
        total_bars = sum(s.bar_count for s in sections)
        if total_bars > 256:
            raise ValueError(f"Total bars {total_bars} exceeds maximum 256")
        return sections


# =====================================
# REAPER Telemetry
# =====================================

class ReaperTrackState(BaseModel):
    """Real-time REAPER track state"""
    track_id: int
    track_name: str
    volume: float = Field(ge=0.0, le=1.0)
    pan: float = Field(ge=-1.0, le=1.0)
    muted: bool
    soloed: bool
    armed: bool
    fx_chain: List[str] = Field(default_factory=list, description="FX plugin names")
    
    # Audio features (from real-time analysis)
    current_lufs: Optional[float] = None
    current_peak_db: Optional[float] = None
    spectral_centroid: Optional[float] = None


class ReaperTelemetry(BaseModel):
    """Full REAPER project telemetry"""
    timestamp: datetime
    project_name: str
    sample_rate: int
    bpm: float
    play_state: Literal["stopped", "playing", "recording", "paused"]
    edit_cursor_pos: float  # Seconds
    selected_track_ids: List[int]
    
    tracks: List[ReaperTrackState] = Field(default_factory=list)
    
    # AI suggestions
    suggested_actions: List[Dict[str, Any]] = Field(default_factory=list)


# =====================================
# Consensus Loop Results
# =====================================

class AuditorCritique(BaseModel):
    """Auditor feedback on generated output"""
    approved: bool
    rejection_reasons: List[str] = Field(default_factory=list)
    
    # Quality metrics
    loudness_match: bool = True
    style_match: bool = True
    technical_quality: bool = True
    
    # Specific issues
    too_quiet: bool = False
    too_loud: bool = False
    wrong_style: bool = False
    style_mismatch: Optional[str] = None
    clipping: bool = False
    artifacts: bool = False
    
    telemetry: Dict[str, Any] = Field(default_factory=dict)


class GenerationResult(BaseModel):
    """Final generation result"""
    success: bool
    iterations: int
    auditor_approved: bool
    
    output_paths: List[str] = Field(default_factory=list)
    stem_paths: Dict[StemType, str] = Field(default_factory=dict)
    
    rejection_history: List[str] = Field(default_factory=list)
    final_telemetry: Dict[str, Any] = Field(default_factory=dict)
    
    reaper_imported: bool = False
    reaper_track_ids: List[int] = Field(default_factory=list)
    
    processing_time_seconds: float = Field(ge=0.0)
    gpu_memory_peak_gb: Optional[float] = Field(None, ge=0.0)
