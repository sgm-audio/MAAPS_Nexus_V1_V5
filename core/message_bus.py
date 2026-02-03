"""
Message Bus - Pub/Sub System

The central nervous system for MAAPS agent communication.
Replaces n8n orchestration with native Python pub/sub.
"""

import threading
import queue
import time
import logging
from typing import Dict, Set, Callable, Optional, List
from collections import defaultdict

from .message import Message
from .priority import Priority

logger = logging.getLogger(__name__)


class MessageBus:
    """
    Thread-safe publish/subscribe message bus.
    
    Features:
    - Priority-based message queuing
    - Wildcard topic subscriptions (e.g., 'audio.*')
    - Request/response correlation
    - Message TTL expiration
    - Statistics tracking
    """
    
    _instance: Optional['MessageBus'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'MessageBus':
        """Singleton pattern - one bus per process"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Subscriptions: topic -> set of callbacks
        self._subscriptions: Dict[str, Set[Callable[[Message], None]]] = defaultdict(set)
        self._subscriptions_lock = threading.Lock()
        
        # Priority queues (one per priority level)
        self._queues: Dict[Priority, queue.Queue] = {
            p: queue.Queue() for p in Priority
        }
        
        # Response waiters: correlation_id -> Event + Response
        self._response_waiters: Dict[str, Dict] = {}
        self._waiters_lock = threading.Lock()
        
        # Worker thread
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._stats = {
            'messages_published': 0,
            'messages_delivered': 0,
            'messages_expired': 0,
            'subscriptions_active': 0
        }
        self._stats_lock = threading.Lock()
        
        self._initialized = True
        logger.info("MessageBus initialized")
    
    def start(self):
        """Start the message bus worker thread"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="MessageBus_Worker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("MessageBus worker started")
    
    def stop(self):
        """Stop the message bus worker thread"""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        logger.info("MessageBus worker stopped")
    
    def subscribe(self, topic: str, callback: Callable[[Message], None]):
        """
        Subscribe to a topic.
        
        Args:
            topic: Topic pattern (supports wildcards: 'audio.*' matches 'audio.job.start')
            callback: Function to call when message received
        """
        with self._subscriptions_lock:
            self._subscriptions[topic].add(callback)
            with self._stats_lock:
                self._stats['subscriptions_active'] = sum(
                    len(subs) for subs in self._subscriptions.values()
                )
        logger.debug(f"Subscribed to topic: {topic}")
    
    def unsubscribe(self, topic: str, callback: Callable[[Message], None]):
        """Unsubscribe from a topic"""
        with self._subscriptions_lock:
            if topic in self._subscriptions:
                self._subscriptions[topic].discard(callback)
                if not self._subscriptions[topic]:
                    del self._subscriptions[topic]
    
    def publish(self, message: Message):
        """
        Publish a message to subscribers.
        
        Args:
            message: The message to publish
        """
        if message.is_expired():
            with self._stats_lock:
                self._stats['messages_expired'] += 1
            return
        
        self._queues[message.priority].put(message)
        
        with self._stats_lock:
            self._stats['messages_published'] += 1
    
    def request(
        self, 
        message: Message, 
        timeout: float = 30.0
    ) -> Optional[Message]:
        """
        Publish a request and wait for response.
        
        Args:
            message: The request message
            timeout: Max seconds to wait for response
            
        Returns:
            Response message or None if timeout
        """
        # Setup waiter
        event = threading.Event()
        with self._waiters_lock:
            self._response_waiters[message.message_id] = {
                'event': event,
                'response': None
            }
        
        # Publish request
        self.publish(message)
        
        # Wait for response
        event.wait(timeout=timeout)
        
        # Get response
        with self._waiters_lock:
            waiter = self._response_waiters.pop(message.message_id, {})
            return waiter.get('response')
    
    def _worker_loop(self):
        """Main worker loop - processes messages by priority"""
        while self._running:
            try:
                # Process in priority order
                for priority in Priority:
                    try:
                        message = self._queues[priority].get_nowait()
                        self._deliver_message(message)
                    except queue.Empty:
                        continue
                
                # Small sleep to prevent CPU spin
                time.sleep(0.001)
                
            except Exception as e:
                logger.error(f"MessageBus worker error: {e}")
    
    def _deliver_message(self, message: Message):
        """Deliver message to matching subscribers"""
        if message.is_expired():
            with self._stats_lock:
                self._stats['messages_expired'] += 1
            return
        
        # Check for response correlation
        if message.correlation_id:
            with self._waiters_lock:
                if message.correlation_id in self._response_waiters:
                    self._response_waiters[message.correlation_id]['response'] = message
                    self._response_waiters[message.correlation_id]['event'].set()
        
        # Find matching subscribers
        with self._subscriptions_lock:
            callbacks = self._get_matching_callbacks(message.topic)
        
        # Deliver to each subscriber
        for callback in callbacks:
            try:
                callback(message)
                with self._stats_lock:
                    self._stats['messages_delivered'] += 1
            except Exception as e:
                logger.error(f"Error delivering message to subscriber: {e}")
    
    def _get_matching_callbacks(self, topic: str) -> List[Callable]:
        """Get all callbacks matching a topic (including wildcards)"""
        callbacks = []
        
        for pattern, subs in self._subscriptions.items():
            if self._topic_matches(pattern, topic):
                callbacks.extend(subs)
        
        return callbacks
    
    def _topic_matches(self, pattern: str, topic: str) -> bool:
        """Check if topic matches pattern (supports * wildcard)"""
        if pattern == topic:
            return True
        
        if '*' not in pattern:
            return False
        
        # Handle 'audio.*' matching 'audio.job.start'
        if pattern.endswith('.*'):
            prefix = pattern[:-2]
            return topic.startswith(prefix + '.')
        
        # Handle 'audio.*.complete' matching 'audio.job.complete'
        pattern_parts = pattern.split('.')
        topic_parts = topic.split('.')
        
        if len(pattern_parts) != len(topic_parts):
            return False
        
        for p, t in zip(pattern_parts, topic_parts):
            if p != '*' and p != t:
                return False
        
        return True
    
    def get_stats(self) -> Dict:
        """Get message bus statistics"""
        with self._stats_lock:
            return self._stats.copy()


# Global bus instance
def get_bus() -> MessageBus:
    """Get the global MessageBus instance"""
    return MessageBus()
