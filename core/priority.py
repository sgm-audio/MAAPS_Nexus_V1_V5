"""
Message Priority Levels

Used to control message processing order in the MessageBus.
"""

from enum import IntEnum


class Priority(IntEnum):
    """Message priority levels (lower = higher priority)"""
    
    CRITICAL = 0    # System failures, emergency stops
    HIGH = 1        # Real-time audio/MIDI, UI updates
    MEDIUM = 2      # Standard agent communication
    LOW = 3         # Background tasks, logging
    BACKGROUND = 4  # Cleanup, analytics, non-urgent
