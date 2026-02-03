"""
Orchestration Agent

Central coordinator for all MAAPS operations.
Replaces n8n as the workflow orchestration layer.

Responsibilities:
- V1: CI/CD webhook handling, git pull, hot-reload
- Route messages between other agents
- Manage agent lifecycle
- Handle system startup/shutdown
"""

import hashlib
import hmac
import subprocess
import threading
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

from core import BaseAgent, Message, Topics, Priority

logger = logging.getLogger(__name__)


class DeploymentStatus(Enum):
    """Deployment status values"""
    PENDING = "pending"
    PULLING = "pulling"
    BUILDING = "building"
    RELOADING = "reloading"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class Deployment:
    """Deployment tracking"""
    commit_sha: str
    branch: str
    status: DeploymentStatus
    logs: List[str]
    started_at: float
    completed_at: Optional[float] = None


class OrchestrationAgent(BaseAgent):
    """
    Central orchestration agent for MAAPS.
    
    V1 Features:
    - GitHub webhook receiver
    - Git pull automation
    - Container hot-reload
    
    Core Features:
    - Message routing
    - Agent coordination
    - System health monitoring
    """
    
    def __init__(self):
        super().__init__(
            agent_id="orchestration_agent",
            agent_name="MAAPS Orchestration Agent"
        )
        
        # Deployment tracking
        self.deployments: Dict[str, Deployment] = {}
        self.deployments_lock = threading.Lock()
        
        # Registered agents
        self.registered_agents: Dict[str, Dict] = {}
        self.agents_lock = threading.Lock()
        
        # Health check state
        self.last_health_check = 0.0
        self.health_check_interval = 30.0  # seconds
        
        # Background thread
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_active = False
    
    def setup(self):
        """Initialize orchestration agent"""
        # V1: CI/CD Topics
        self.subscribe(Topics.DEPLOY_WEBHOOK_RECEIVED)
        self.subscribe(Topics.DEPLOY_STATUS)
        
        # System topics
        self.subscribe(Topics.SYSTEM_STARTUP)
        self.subscribe(Topics.SYSTEM_SHUTDOWN)
        self.subscribe(Topics.SYSTEM_HEALTH_CHECK)
        
        # Agent registration
        self.subscribe("agent.register")
        self.subscribe("agent.deregister")
        
        # Start monitor thread
        self._start_monitor()
        
        self.log("INFO", "Orchestration Agent initialized")
        
        # Publish system startup
        self.publish(Topics.SYSTEM_STARTUP, {
            'timestamp': time.time(),
            'orchestrator': self.agent_id
        }, priority=Priority.HIGH)
    
    def teardown(self):
        """Cleanup orchestration agent"""
        # Stop monitor thread
        self._stop_monitor()
        
        # Publish system shutdown
        self.publish(Topics.SYSTEM_SHUTDOWN, {
            'timestamp': time.time()
        }, priority=Priority.CRITICAL)
        
        self.log("INFO", "Orchestration Agent shutdown complete")
    
    def handle_message(self, message: Message):
        """Process incoming messages"""
        try:
            if message.topic == Topics.DEPLOY_WEBHOOK_RECEIVED:
                self._handle_webhook(message)
            
            elif message.topic == Topics.SYSTEM_HEALTH_CHECK:
                self._handle_health_check(message)
            
            elif message.topic == "agent.register":
                self._handle_agent_register(message)
            
            elif message.topic == "agent.deregister":
                self._handle_agent_deregister(message)
            
            else:
                self.log("DEBUG", f"Unhandled topic: {message.topic}")
        
        except Exception as e:
            self.log("ERROR", f"Error handling message: {e}", {
                'topic': message.topic
            })
    
    def _handle_webhook(self, message: Message):
        """
        Handle GitHub webhook for CI/CD (V1)
        
        Expected payload:
            - signature: X-Hub-Signature-256 header
            - ref: git ref (e.g., refs/heads/main)
            - after: commit SHA
        """
        payload = message.payload
        
        # Verify webhook signature
        if not self._verify_webhook_signature(payload):
            self.log("WARNING", "Invalid webhook signature")
            self.publish(Topics.DEPLOY_FAILED, {
                'error': 'Invalid signature'
            })
            return
        
        commit_sha = payload.get('after', 'unknown')
        branch = payload.get('ref', '').replace('refs/heads/', '')
        
        # Only deploy from main/master
        if branch not in ['main', 'master']:
            self.log("INFO", f"Ignoring push to branch: {branch}")
            return
        
        # Create deployment
        deployment = Deployment(
            commit_sha=commit_sha,
            branch=branch,
            status=DeploymentStatus.PENDING,
            logs=[],
            started_at=time.time()
        )
        
        with self.deployments_lock:
            self.deployments[commit_sha] = deployment
        
        # Start deployment pipeline
        threading.Thread(
            target=self._run_deployment,
            args=(deployment,),
            daemon=True
        ).start()
    
    def _verify_webhook_signature(self, payload: Dict) -> bool:
        """Verify GitHub webhook signature"""
        secret = self.config.github_webhook_secret
        if not secret:
            # No secret configured, skip verification
            return True
        
        signature = payload.get('signature', '')
        body = payload.get('raw_body', '')
        
        if not signature or not body:
            return False
        
        expected = 'sha256=' + hmac.new(
            secret.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)
    
    def _run_deployment(self, deployment: Deployment):
        """Run deployment pipeline in background"""
        try:
            # Step 1: Git Pull
            deployment.status = DeploymentStatus.PULLING
            self._publish_deploy_status(deployment)
            
            result = subprocess.run(
                ['git', 'pull', 'origin', deployment.branch],
                capture_output=True,
                text=True,
                timeout=60
            )
            deployment.logs.append(f"git pull: {result.stdout}")
            
            if result.returncode != 0:
                raise Exception(f"Git pull failed: {result.stderr}")
            
            # Step 2: Rebuild containers (if needed)
            deployment.status = DeploymentStatus.BUILDING
            self._publish_deploy_status(deployment)
            
            # Skip build for now, just reload
            deployment.logs.append("Skipping container rebuild")
            
            # Step 3: Hot reload
            deployment.status = DeploymentStatus.RELOADING
            self._publish_deploy_status(deployment)
            
            # Notify all agents to reload
            self.publish(Topics.DEPLOY_HOT_RELOAD, {
                'commit_sha': deployment.commit_sha
            }, priority=Priority.HIGH)
            
            deployment.logs.append("Hot reload signal sent")
            
            # Complete
            deployment.status = DeploymentStatus.COMPLETE
            deployment.completed_at = time.time()
            self._publish_deploy_status(deployment)
            
            self.log("INFO", f"Deployment complete: {deployment.commit_sha[:8]}")
        
        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.logs.append(f"Error: {str(e)}")
            deployment.completed_at = time.time()
            self._publish_deploy_status(deployment)
            
            self.publish(Topics.DEPLOY_FAILED, {
                'commit_sha': deployment.commit_sha,
                'error': str(e)
            })
            
            self.log("ERROR", f"Deployment failed: {e}")
    
    def _publish_deploy_status(self, deployment: Deployment):
        """Publish deployment status update"""
        self.publish(Topics.DEPLOY_STATUS, {
            'commit_sha': deployment.commit_sha,
            'branch': deployment.branch,
            'status': deployment.status.value,
            'logs': deployment.logs[-5:],  # Last 5 log entries
            'duration': time.time() - deployment.started_at
        })
    
    def _handle_health_check(self, message: Message):
        """Handle health check request"""
        with self.agents_lock:
            agent_count = len(self.registered_agents)
            agent_list = list(self.registered_agents.keys())
        
        self.respond(message, {
            'status': 'healthy',
            'agent_id': self.agent_id,
            'registered_agents': agent_count,
            'agents': agent_list,
            'uptime': time.time() - self.last_health_check
        })
    
    def _handle_agent_register(self, message: Message):
        """Handle agent registration"""
        payload = message.payload
        agent_id = payload.get('agent_id')
        agent_name = payload.get('agent_name')
        
        with self.agents_lock:
            self.registered_agents[agent_id] = {
                'name': agent_name,
                'registered_at': time.time()
            }
        
        self.log("INFO", f"Agent registered: {agent_name} ({agent_id})")
        
        self.respond(message, {
            'success': True,
            'agent_id': agent_id
        })
    
    def _handle_agent_deregister(self, message: Message):
        """Handle agent deregistration"""
        payload = message.payload
        agent_id = payload.get('agent_id')
        
        with self.agents_lock:
            if agent_id in self.registered_agents:
                del self.registered_agents[agent_id]
        
        self.log("INFO", f"Agent deregistered: {agent_id}")
    
    def _start_monitor(self):
        """Start background monitoring thread"""
        self._monitor_active = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="Orchestrator_Monitor",
            daemon=True
        )
        self._monitor_thread.start()
    
    def _stop_monitor(self):
        """Stop background monitoring thread"""
        self._monitor_active = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self._monitor_active:
            try:
                current_time = time.time()
                
                # Periodic health check
                if current_time - self.last_health_check > self.health_check_interval:
                    self.last_health_check = current_time
                    self.publish(Topics.SYSTEM_HEALTH_REPORT, {
                        'orchestrator': 'healthy',
                        'timestamp': current_time
                    }, priority=Priority.LOW)
                
                time.sleep(5.0)
            
            except Exception as e:
                self.log("ERROR", f"Monitor loop error: {e}")
