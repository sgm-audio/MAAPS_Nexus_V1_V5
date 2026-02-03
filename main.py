"""
MAAPS Nexus V1-V5 Main Entry Point

Starts the agent orchestration system.
"""

import logging
import signal
import sys
import time
from typing import List

from core import MessageBus, get_bus, Config
from agents import (
    OrchestrationAgent,
    AudioWorkerAgent,
    ScraperAgent,
    RAGAgent
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('maaps.log')
    ]
)

logger = logging.getLogger('maaps.main')


class MAAPSSystem:
    """
    MAAPS Nexus System Controller.
    
    Manages agent lifecycle and message bus.
    """
    
    def __init__(self):
        self.config = Config.from_env()
        self.bus = get_bus()
        self.agents: List = []
        self._running = False
    
    def start(self):
        """Start the MAAPS system"""
        logger.info("=" * 60)
        logger.info("MAAPS Nexus V1-V5 Starting...")
        logger.info("=" * 60)
        
        # Start message bus
        self.bus.start()
        logger.info("MessageBus started")
        
        # Initialize agents
        self.agents = [
            OrchestrationAgent(),
            AudioWorkerAgent(),
            ScraperAgent(),
            RAGAgent()
        ]
        
        # Start all agents
        for agent in self.agents:
            try:
                agent.start()
                logger.info(f"Agent started: {agent.agent_name}")
            except Exception as e:
                logger.error(f"Failed to start {agent.agent_name}: {e}")
        
        self._running = True
        logger.info("=" * 60)
        logger.info("MAAPS Nexus V1-V5 Running")
        logger.info(f"Agents active: {len(self.agents)}")
        logger.info("=" * 60)
    
    def stop(self):
        """Stop the MAAPS system"""
        logger.info("Shutting down MAAPS Nexus...")
        
        self._running = False
        
        # Stop all agents
        for agent in reversed(self.agents):
            try:
                agent.stop()
                logger.info(f"Agent stopped: {agent.agent_name}")
            except Exception as e:
                logger.error(f"Error stopping {agent.agent_name}: {e}")
        
        # Stop message bus
        self.bus.stop()
        logger.info("MessageBus stopped")
        
        logger.info("MAAPS Nexus shutdown complete")
    
    def run_forever(self):
        """Run until interrupted"""
        try:
            while self._running:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def main():
    """Main entry point"""
    system = MAAPSSystem()
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        system.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start and run
    system.start()
    system.run_forever()


if __name__ == '__main__':
    main()
