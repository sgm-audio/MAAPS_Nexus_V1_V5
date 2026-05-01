"""
Message Bus - Pub/Sub System

The central nervous system for MAAPS agent communication.
Replaces n8n orchestration with native Python pub/sub.
"""

import threading
import queue
import time
import logging
import re
from typing import Dict, Set, Callable, Optional, List, Pattern
from collections import defaultdict
from dataclasses import dataclass, field

from .message import Message
from .priority import Priority

logger = logging.getLogger(__name__)


@dataclass
class MessageBusStats:
    """Statistics tracking for message bus operations"""
    messages_published: int = 0
    messages_delivered: int = 0
    messages_expired: int = 0
    subscriptions_active: int = 0
    messages_dropped: int = 0
    last_reset: float = field(default_factory=time.time)
    
    def reset(self):
        """Reset all statistics"""
        self.messages_published = 0
        self.messages_delivered = 0
        self.messages_expired = 0
        self.subscriptions_active = 0
        self.messages_dropped = 0
        self.last_reset = time.time()


class MessageBus:
    """
    Thread-safe publish/subscribe message bus.
    
    Features:
    - Priority-based message queuing
    - Wildcard topic subscriptions (e.g., 'audio.*')
    - Request/response correlation
    - Message TTL expiration
    - Statistics tracking
    
    Usage:
        # Get singleton instance
        bus = get_bus()
        
        # Or create new instance (for testing)
        bus = MessageBus()
        
        # Start processing
        bus.start()
        
        # Subscribe and publish
        bus.subscribe('topic', callback)
        bus.publish(message)
    """
    
    _instance: Optional['MessageBus'] = None
    _lock = threading.Lock()
    
    def __new__(cls, force_new: bool = False) -> 'MessageBus':
        """
        Singleton pattern - one bus per process.
        
        Args:
            force_new: If True, bypass singleton and create new instance (for testing)
        """
        if force_new:
            instance = super().__new__(cls)
            instance._initialized = False
            return instance
            
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self, force_new: bool = False):
        if self._initialized:
            return
        
        # Subscriptions: topic -> set of callbacks
        self._subscriptions: Dict[str, Set[Callable[[Message], None]]] = defaultdict(set)
        self._subscriptions_lock = threading.RLock()  # Reentrant lock for nested operations
        
        # Priority queues (one per priority level)
        self._queues: Dict[Priority, queue.Queue] = {
            p: queue.Queue(maxsize=10000) for p in Priority  # Prevent memory overflow
        }
        
        # Response waiters: correlation_id -> Event + Response
        self._response_waiters: Dict[str, Dict] = {}
        self._waiters_lock = threading.Lock()
        
        # Worker thread
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._stats = MessageBusStats()
        self._stats_lock = threading.Lock()
        
        # Compiled regex patterns for topic matching (performance optimization)
        self._pattern_cache: Dict[str, Pattern] = {}
        self._cache_lock = threading.Lock()
        
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
            
        Raises:
            ValueError: If callback is not callable
        """
        if not callable(callback):
            raise ValueError("Callback must be callable")
            
        with self._subscriptions_lock:
            self._subscriptions[topic].add(callback)
            self._update_stats()
        logger.debug(f"Subscribed to topic: {topic}")
    
    def unsubscribe(self, topic: str, callback: Callable[[Message], None]):
        """
        Unsubscribe from a topic.
        
        Args:
            topic: Topic to unsubscribe from
            callback: Callback function to remove
        """
        with self._subscriptions_lock:
            if topic in self._subscriptions:
                self._subscriptions[topic].discard(callback)
                if not self._subscriptions[topic]:
                    del self._subscriptions[topic]
                self._update_stats()
    
    def unsubscribe_all(self, callback: Callable[[Message], None]):
        """
        Remove callback from all subscriptions.
        
        Args:
            callback: Callback function to remove from all topics
        """
        with self._subscriptions_lock:
            topics_to_remove = []
            for topic, callbacks in self._subscriptions.items():
                callbacks.discard(callback)
                if not callbacks:
                    topics_to_remove.append(topic)
            
            for topic in topics_to_remove:
                del self._subscriptions[topic]
            
            self._update_stats()
    
    def publish(self, message: Message) -> bool:
        """
        Publish a message to subscribers.
        
        Args:
            message: The message to publish
            
        Returns:
            True if message was queued successfully, False otherwise
        """
        if message.is_expired():
            with self._stats_lock:
                self._stats.messages_expired += 1
            return False
        
        try:
            self._queues[message.priority].put_nowait(message)
            with self._stats_lock:
                self._stats.messages_published += 1
            return True
        except queue.Full:
            # Queue is full, drop message
            with self._stats_lock:
                self._stats.messages_dropped += 1
            logger.warning(f"Message dropped: queue full for priority {message.priority}")
            return False
    
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
            
        Raises:
            RuntimeError: If message bus is not running
        """
        if not self._running:
            raise RuntimeError("MessageBus is not running")
        
        # Setup waiter
        event = threading.Event()
        with self._waiters_lock:
            self._response_waiters[message.message_id] = {
                'event': event,
                'response': None
            }
        
        try:
            # Publish request
            self.publish(message)
            
            # Wait for response
            event.wait(timeout=timeout)
            
            # Get response
            with self._waiters_lock:
                waiter = self._response_waiters.pop(message.message_id, {})
                return waiter.get('response')
        except Exception:
            # Cleanup on error
            with self._waiters_lock:
                self._response_waiters.pop(message.message_id, None)
            raise
    
    def _worker_loop(self):
        """Main worker loop - processes messages by priority"""
        while self._running:
            try:
                # Process in priority order (CRITICAL to BACKGROUND)
                processed = False
                for priority in Priority:
                    try:
                        message = self._queues[priority].get_nowait()
                        self._deliver_message(message)
                        processed = True
                    except queue.Empty:
                        continue
                
                # Small sleep to prevent CPU spin if no messages
                if not processed:
                    time.sleep(0.001)
                
            except Exception as e:
                logger.error(f"MessageBus worker error: {e}", exc_info=True)
    
    def _deliver_message(self, message: Message):
        """Deliver message to matching subscribers"""
        if message.is_expired():
            with self._stats_lock:
                self._stats.messages_expired += 1
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
        delivered = 0
        for callback in callbacks:
            try:
                callback(message)
                delivered += 1
            except Exception as e:
                logger.error(f"Error delivering message to subscriber: {e}", exc_info=True)
        
        # Update stats
        if delivered > 0:
            with self._stats_lock:
                self._stats.messages_delivered += delivered
    
    def _update_stats(self):
        """Update subscription statistics"""
        with self._stats_lock:
            self._stats.subscriptions_active = sum(
                len(subs) for subs in self._subscriptions.values()
            )
    
    def _get_matching_callbacks(self, topic: str) -> List[Callable]:
        """Get all callbacks matching a topic (including wildcards)"""
        callbacks = []
        
        with self._subscriptions_lock:
            for pattern, subs in self._subscriptions.items():
                if self._topic_matches(pattern, topic):
                    callbacks.extend(subs)
        
        return callbacks
    
    def _topic_matches(self, pattern: str, topic: str) -> bool:
        """
        Check if topic matches pattern (supports * wildcard).
        
        Uses cached compiled regex patterns for performance.
        
        Args:
            pattern: Subscription pattern (e.g., 'audio.*', '*.complete')
            topic: Message topic to match
            
        Returns:
            True if topic matches pattern
        """
        # Exact match is fastest
        if pattern == topic:
            return True
        
        # No wildcard - no match
        if '*' not in pattern:
            return False
        
        # Check cache first
        with self._cache_lock:
            if pattern not in self._pattern_cache:
                # Convert pattern to regex
                # Escape special regex chars except *
                regex_pattern = re.escape(pattern)
                # Replace escaped \\* with .*
                regex_pattern = regex_pattern.replace(r'\*', r'[^.]+')
                
                # Handle specific cases
                if pattern.endswith('.*'):
                    # audio.* should match audio.job.start
                    prefix = pattern[:-2]
                    regex_pattern = f'^{re.escape(prefix)}\\..+$'
                elif pattern.startswith('*.'):
                    # *.complete should match audio.complete
                    suffix = pattern[2:]
                    regex_pattern = f'^.+\\.{re.escape(suffix)}$'
                else:
                    # General case: audio.*.complete
                    parts = pattern.split('.')
                    regex_parts = []
                    for part in parts:
                        if part == '*':
                            regex_parts.append('[^.]+')
                        else:
                            regex_parts.append(re.escape(part))
                    regex_pattern = '^' + r'\.'.join(regex_parts) + '$'
                
                try:
                    self._pattern_cache[pattern] = re.compile(regex_pattern)
                except re.error:
                    logger.warning(f"Invalid pattern: {pattern}")
                    return False
            
            compiled_pattern = self._pattern_cache[pattern]
        
        return bool(compiled_pattern.match(topic))
    
    def clear_pattern_cache(self):
        """Clear the compiled pattern cache (useful for testing)"""
        with self._cache_lock:
            self._pattern_cache.clear()
    
    def get_stats(self) -> MessageBusStats:
        """Get message bus statistics"""
        with self._stats_lock:
            return MessageBusStats(
                messages_published=self._stats.messages_published,
                messages_delivered=self._stats.messages_delivered,
                messages_expired=self._stats.messages_expired,
                subscriptions_active=self._stats.subscriptions_active,
                messages_dropped=self._stats.messages_dropped,
                last_reset=self._stats.last_reset
            )
    
    def reset_stats(self):
        """Reset all statistics"""
        with self._stats_lock:
            self._stats.reset()
    
    @property
    def queue_sizes(self) -> Dict[Priority, int]:
        """Get current queue sizes by priority"""
        return {p: q.qsize() for p, q in self._queues.items()}
    
    @property
    def is_running(self) -> bool:
        """Check if message bus is running"""
        return self._running


# Global bus instance
def get_bus(force_new: bool = False) -> MessageBus:
    """
    Get the global MessageBus instance.
    
    Args:
        force_new: If True, create new instance instead of singleton (for testing)
        
    Returns:
        MessageBus instance
    """
    return MessageBus(force_new=force_new)
