"""
MAAPS v4.0 - Root Package Init
"""

__version__ = "4.0.0"
__author__ = "MAAPS Team"

from maaps_v4.schemas import (
    SonicSignature,
    SectionPlan,
    MasteringParams,
    GenerationRequest,
    ReaperTelemetry,
    AuditorCritique,
    GenerationResult,
    AudioQuality,
    StemType,
    SectionType
)

from maaps_v4.agents import (
    AuditorAgent,
    ComposerAgent,
    AlchemistAgent,
    EngineerAgent
)

from maaps_v4.reaper_interface import ReaperNeuralInterface

__all__ = [
    # Schemas
    'SonicSignature',
    'SectionPlan',
    'MasteringParams',
    'GenerationRequest',
    'ReaperTelemetry',
    'AuditorCritique',
    'GenerationResult',
    'AudioQuality',
    'StemType',
    'SectionType',
    
    # Agents
    'AuditorAgent',
    'ComposerAgent',
    'AlchemistAgent',
    'EngineerAgent',
    
    # Interface
    'ReaperNeuralInterface'
]
