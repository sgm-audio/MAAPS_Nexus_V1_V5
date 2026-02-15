import pytest
import time
from core import BaseAgent, Message, MessageBus

class MockAgent(BaseAgent):
    """Mock agent for testing"""
    def __init__(self):
        super().__init__("mock_agent", "Mock Agent")
        self.received_messages = []
        
    def setup(self):
        self.subscribe("test.topic")
        
    def teardown(self):
        pass
        
    def handle_message(self, message):
        self.received_messages.append(message)

@pytest.fixture
def agent():
    # Reset singleton to ensure clean state
    if MessageBus._instance:
        MessageBus._instance.stop()
        MessageBus._instance = None
        
    bus = MessageBus()
    bus.start()
    
    agent = MockAgent()
    agent.start()
    yield agent
    
    agent.stop()
    bus.stop()
    MessageBus._instance = None

def test_agent_lifecycle(agent):
    """Test agent startup and shutdown"""
    assert agent.is_running
    assert "test.topic" in agent._subscribed_topics

def test_agent_receive_message(agent):
    """Test agent receiving messages"""
    # Agent publishes to itself via bus
    agent.publish("test.topic", {"data": 123})
    
    time.sleep(0.1)
    
    assert len(agent.received_messages) == 1
    assert agent.received_messages[0].payload["data"] == 123
    assert agent.received_messages[0].sender == "mock_agent"

def test_agent_logging(agent, caplog):
    """Test agent logging"""
    agent.log("INFO", "Test log message")
    
    assert "Test log message" in caplog.text
    assert "maaps.mock_agent" in caplog.text

def test_agent_request_response(agent):
    """Test agent request wrapper"""
    # Setup a responder
    def responder(msg):
        if msg.topic == "request.topic":
            response = msg.create_response({"status": "ok"})
            agent._bus.publish(response)
            
    agent._bus.subscribe("request.topic", responder)
    
    response = agent.request("request.topic", {"data": "req"}, timeout=1.0)
    
    assert response is not None
    assert response.payload["status"] == "ok"
