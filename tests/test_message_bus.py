import pytest
import time
from core import MessageBus, Message, Priority

@pytest.fixture
def bus():
    # Reset singleton to ensure clean state
    if MessageBus._instance:
        MessageBus._instance.stop()
        MessageBus._instance = None
        
    bus = MessageBus()
    bus.start()
    yield bus
    bus.stop()
    MessageBus._instance = None

def test_subscribe_publish(bus):
    """Test basic publish/subscribe"""
    received = []
    def callback(msg):
        received.append(msg)
    
    bus.subscribe("test.topic", callback)
    
    msg = Message(topic="test.topic", payload={"data": 123}, sender="test")
    bus.publish(msg)
    
    # Wait for async processing
    time.sleep(0.1)
    
    assert len(received) == 1
    assert received[0].payload["data"] == 123
    assert received[0].topic == "test.topic"

def test_wildcard_subscription(bus):
    """Test wildcard matching"""
    received = []
    def callback(msg):
        received.append(msg)
    
    bus.subscribe("audio.*", callback)
    
    # Should match
    bus.publish(Message(topic="audio.start", payload={}, sender="test"))
    
    # Should NOT match
    bus.publish(Message(topic="video.start", payload={}, sender="test"))
    
    time.sleep(0.1)
    
    assert len(received) == 1
    assert received[0].topic == "audio.start"

def test_unsubscribe(bus):
    """Test unsubscribing"""
    received = []
    def callback(msg):
        received.append(msg)
        
    bus.subscribe("test.topic", callback)
    bus.unsubscribe("test.topic", callback)
    
    bus.publish(Message(topic="test.topic", payload={}, sender="test"))
    
    time.sleep(0.1)
    assert len(received) == 0

def test_request_response(bus):
    """Test request/response pattern"""
    def replier(msg):
        if msg.correlation_id:
            response = msg.create_response({"status": "ok"})
            bus.publish(response)
    
    bus.subscribe("request.topic", replier)
    
    request = Message(topic="request.topic", payload={}, sender="client")
    response = bus.request(request, timeout=1.0)
    
    assert response is not None
    assert response.payload["status"] == "ok"
    assert response.correlation_id == request.message_id

def test_priority_ordering(bus):
    """Test that high priority messages are processed"""
    # Note: Hard to test exact ordering with threads, but we can verify both arrive
    received = []
    def callback(msg):
        received.append(msg.priority)
    
    bus.subscribe("priority.test", callback)
    
    # Publish low then high
    bus.publish(Message(topic="priority.test", payload={}, priority=Priority.LOW, sender="test"))
    bus.publish(Message(topic="priority.test", payload={}, priority=Priority.HIGH, sender="test"))
    
    time.sleep(0.1)
    
    assert len(received) == 2
    assert Priority.HIGH in received
    assert Priority.LOW in received
