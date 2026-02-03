"""
Base Agent - Abstract Agent Class

All MAAPS agents inherit from this base class.
Provides standard lifecycle, messaging, and logging.
"""

import threading
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable

from .message import Message
from .message_bus import MessageBus, get_bus
from .priority import Priority
from .config import Config

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all MAAPS agents.
    
    Lifecycle:
        1. __init__() - Constructor, set agent_id and agent_name
        2. setup() - Subscribe to topics, initialize resources
        3. handle_message() - Process incoming messages
        4. teardown() - Cleanup resources
    
    Subclasses must implement:
        - setup()
        - teardown()
        - handle_message(message)
    """
    
    def __init__(self, agent_id: str, agent_name: str):
        """
        Initialize the agent.
        
        Args:
            agent_id: Unique identifier (e.g., 'audio_worker_agent')
            agent_name: Human-readable name (e.g., 'Audio Worker Agent')
        """
        self.agent_id = agent_id
        self.agent_name = agent_name
        
        # Get message bus
        self._bus: MessageBus = get_bus()
        
        # Configuration
        self._config: Config = Config.from_env()
        
        # Running state
        self._running = False
        self._lock = threading.Lock()
        
        # Subscribed topics (for cleanup)
        self._subscribed_topics: List[str] = []
        
        # Agent logger
        self._logger = logging.getLogger(f"maaps.{agent_id}")
    
    @abstractmethod
    def setup(self):
        """
        Initialize the agent.
        
        Override to:
        - Subscribe to topics via self.subscribe()
        - Initialize external connections
        - Start background threads
        """
        pass
    
    @abstractmethod
    def teardown(self):
        """
        Cleanup agent resources.
        
        Override to:
        - Close connections
        - Stop background threads
        - Release resources
        """
        pass
    
    @abstractmethod
    def handle_message(self, message: Message):
        """
        Process an incoming message.
        
        Args:
            message: The received message
            
        Override to handle messages for subscribed topics.
        """
        pass
    
    def start(self):
        """Start the agent"""
        with self._lock:
            if self._running:
                return
            self._running = True
        
        self.log("INFO", f"Starting agent: {self.agent_name}")
        self.setup()
        self.log("INFO", f"Agent started: {self.agent_name}")
    
    def stop(self):
        """Stop the agent"""
        with self._lock:
            if not self._running:
                return
            self._running = False
        
        self.log("INFO", f"Stopping agent: {self.agent_name}")
        
        # Unsubscribe from all topics
        for topic in self._subscribed_topics:
            self._bus.unsubscribe(topic, self._message_callback)
        self._subscribed_topics.clear()
        
        self.teardown()
        self.log("INFO", f"Agent stopped: {self.agent_name}")
    
    def subscribe(self, topic: str):
        """
        Subscribe to a topic.
        
        Args:
            topic: Topic to subscribe to (supports wildcards)
        """
        self._bus.subscribe(topic, self._message_callback)
        self._subscribed_topics.append(topic)
        self.log("DEBUG", f"Subscribed to topic: {topic}")
    
    def publish(
        self, 
        topic: str, 
        payload: Dict[str, Any], 
        priority: Priority = Priority.MEDIUM,
        ttl: int = 0
    ):
        """
        Publish a message.
        
        Args:
            topic: Target topic
            payload: Message data
            priority: Message priority
            ttl: Time-to-live in seconds (0 = no expiry)
        """
        message = Message(
            topic=topic,
            payload=payload,
            priority=priority,
            sender=self.agent_id,
            ttl=ttl
        )
        self._bus.publish(message)
    
    def request(
        self, 
        topic: str, 
        payload: Dict[str, Any],
        timeout: float = 30.0
    ) -> Optional[Message]:
        """
        Send a request and wait for response.
        
        Args:
            topic: Target topic
            payload: Request data
            timeout: Max seconds to wait
            
        Returns:
            Response message or None if timeout
        """
        message = Message(
            topic=topic,
            payload=payload,
            priority=Priority.HIGH,
            sender=self.agent_id
        )
        return self._bus.request(message, timeout=timeout)
    
    def respond(self, original: Message, payload: Dict[str, Any]):
        """
        Send a response to a request.
        
        Args:
            original: The original request message
            payload: Response data
        """
        response = original.create_response(payload)
        response.sender = self.agent_id
        self._bus.publish(response)
    
    def log(self, level: str, message: str, data: Optional[Dict] = None):
        """
        Log a message.
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            message: Log message
            data: Optional structured data
        """
        log_func = getattr(self._logger, level.lower(), self._logger.info)
        
        if data:
            log_func(f"{message} | {data}")
        else:
            log_func(message)
    
    def _message_callback(self, message: Message):
        """Internal callback for message bus"""
        try:
            self.handle_message(message)
        except Exception as e:
            self.log("ERROR", f"Error handling message: {e}", {
                'topic': message.topic,
                'payload': message.payload
            })
    
    @property
    def config(self) -> Config:
        """Get agent configuration"""
        return self._config
    
    @property
    def is_running(self) -> bool:
        """Check if agent is running"""
        with self._lock:
            return self._running
