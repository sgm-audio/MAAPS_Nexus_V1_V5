"""
Message Data Structure

Defines the standard message format for inter-agent communication.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Dict

from .priority import Priority


@dataclass
class Message:
    """
    Standard message structure for the MAAPS MessageBus.
    
    Attributes:
        topic: The message topic (e.g., 'audio.job.start')
        payload: The message data
        priority: Message priority for queue ordering
        sender: Agent ID of the sender
        message_id: Unique message identifier
        correlation_id: ID linking request/response pairs
        timestamp: Unix timestamp of creation
        ttl: Time-to-live in seconds (0 = no expiry)
    """
    
    topic: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.MEDIUM
    sender: str = ""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    ttl: int = 0
    
    def is_expired(self) -> bool:
        """Check if message has expired based on TTL"""
        if self.ttl == 0:
            return False
        return time.time() > (self.timestamp + self.ttl)
    
    def create_response(self, payload: Dict[str, Any]) -> 'Message':
        """Create a response message linked to this request"""
        return Message(
            topic=f"{self.topic}.response",
            payload=payload,
            priority=self.priority,
            correlation_id=self.message_id,
            sender=self.sender
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize message to dictionary"""
        return {
            'topic': self.topic,
            'payload': self.payload,
            'priority': self.priority.value,
            'sender': self.sender,
            'message_id': self.message_id,
            'correlation_id': self.correlation_id,
            'timestamp': self.timestamp,
            'ttl': self.ttl
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Deserialize message from dictionary"""
        return cls(
            topic=data['topic'],
            payload=data.get('payload', {}),
            priority=Priority(data.get('priority', Priority.MEDIUM.value)),
            sender=data.get('sender', ''),
            message_id=data.get('message_id', str(uuid.uuid4())),
            correlation_id=data.get('correlation_id'),
            timestamp=data.get('timestamp', time.time()),
            ttl=data.get('ttl', 0)
        )
