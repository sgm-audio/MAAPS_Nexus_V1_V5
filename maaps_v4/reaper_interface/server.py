"""
MAAPS v4.0 - FastAPI WebSocket Server for REAPER Neural Interface

Serves the cyberpunk HTML frontend and handles real-time WebSocket communication
with the MAAPS orchestrator and REAPER.
"""

import logging
import asyncio
import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

logger = logging.getLogger('maaps.websocket')

app = FastAPI(
    title="MAAPS v4.0 REAPER Neural Interface",
    description="WebSocket API for real-time audio production control",
    version="4.0.0"
)

# Store active connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.agent_states = {
            'auditor': 'idle',
            'composer': 'idle',
            'alchemist': 'idle',
            'engineer': 'idle'
        }
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict[str, Any]):
        """Send message to all connected clients"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
    
    async def send_personal(self, message: Dict[str, Any], websocket: WebSocket):
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    def update_agent_state(self, agent: str, state: str):
        """Update agent state and broadcast to all clients"""
        self.agent_states[agent] = state
        asyncio.create_task(self.broadcast({
            'type': 'agent_state',
            'agent_state': self.agent_states.copy()
        }))

manager = ConnectionManager()


# Request/Response Models
class GenerationRequest(BaseModel):
    prompt: str
    style: str = "electronic"
    duration: float = 60.0
    bpm: Optional[float] = None
    key: Optional[str] = None
    lyrics: Optional[str] = None
    target_lufs: float = -14.0
    dry_run: bool = False


class CommandRequest(BaseModel):
    command: str
    request: Optional[GenerationRequest] = None


# Routes
@app.get("/")
async def get_frontend():
    """Serve the main frontend HTML"""
    frontend_path = Path(__file__).parent / "frontend.html"
    if frontend_path.exists():
        return FileResponse(str(frontend_path))
    raise HTTPException(status_code=404, detail="Frontend not found")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "connections": len(manager.active_connections),
        "agents": manager.agent_states
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time communication"""
    await manager.connect(websocket)
    
    # Send initial state
    await manager.send_personal({
        'type': 'init',
        'agent_state': manager.agent_states,
        'message': 'Connected to MAAPS v4.0'
    }, websocket)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            command = data.get('command')
            
            logger.info(f"Received command: {command}")
            
            if command == 'ping':
                await manager.send_personal({'status': 'pong'}, websocket)
            
            elif command == 'get_telemetry':
                # Get telemetry from REAPER interface
                telemetry = await get_reaper_telemetry()
                await manager.send_personal(telemetry, websocket)
            
            elif command == 'get_selected_items':
                items = await get_selected_items()
                await manager.send_personal({'items': items}, websocket)
            
            elif command == 'generate':
                # Handle generation request
                request_data = data.get('request', {})
                await handle_generation_request(request_data, websocket)
            
            elif command == 'refresh_tracks':
                tracks = await get_track_list()
                await manager.send_personal({'tracks': tracks}, websocket)
            
            else:
                await manager.send_personal({
                    'error': f'Unknown command: {command}'
                }, websocket)
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)


# Mock functions - these would integrate with actual MAAPS orchestrator
async def get_reaper_telemetry() -> Dict[str, Any]:
    """Get current REAPER project telemetry"""
    # This would call the actual ReaperNeuralInterface
    return {
        'type': 'telemetry',
        'timestamp': asyncio.get_event_loop().time(),
        'project_name': 'Demo Project',
        'sample_rate': 44100,
        'bpm': 120.0,
        'play_state': 'stopped',
        'edit_cursor_pos': 0.0,
        'tracks': [],
        'current_lufs': None,
        'spectral_centroid': None
    }


async def get_selected_items() -> List[Dict[str, Any]]:
    """Get selected items from REAPER"""
    # This would call the actual ReaperNeuralInterface
    return []


async def get_track_list() -> List[Dict[str, Any]]:
    """Get list of tracks from REAPER"""
    # This would call the actual ReaperNeuralInterface
    return []


async def handle_generation_request(request_data: Dict[str, Any], websocket: WebSocket):
    """Handle audio generation request through MAAPS pipeline"""
    try:
        # Validate request
        gen_request = GenerationRequest(**request_data)
        
        # Send acknowledgment
        await manager.send_personal({
            'status': 'queued',
            'message': 'Generation request received'
        }, websocket)
        
        # Simulate agent state updates (would be real in production)
        manager.update_agent_state('auditor', 'processing')
        await asyncio.sleep(1)
        
        manager.update_agent_state('auditor', 'idle')
        manager.update_agent_state('composer', 'processing')
        await asyncio.sleep(1)
        
        manager.update_agent_state('composer', 'idle')
        manager.update_agent_state('alchemist', 'processing')
        await asyncio.sleep(2)
        
        manager.update_agent_state('alchemist', 'idle')
        manager.update_agent_state('engineer', 'processing')
        await asyncio.sleep(1)
        
        manager.update_agent_state('engineer', 'idle')
        
        # Send mock result
        await manager.send_personal({
            'type': 'result',
            'result': {
                'success': True,
                'output_paths': [
                    '/tmp/maaps_output/final_mix_mastered.wav'
                ],
                'iterations': 1,
                'auditor_approved': True
            }
        }, websocket)
        
        logger.info(f"Generation complete for: {gen_request.prompt[:50]}...")
        
    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
        await manager.send_personal({
            'error': str(e),
            'status': 'failed'
        }, websocket)


# Background task to broadcast agent states periodically
async def broadcast_status():
    """Periodically broadcast system status"""
    while True:
        await asyncio.sleep(5)
        if manager.active_connections:
            await manager.broadcast({
                'type': 'status',
                'connections': len(manager.active_connections),
                'agent_state': manager.agent_states
            })


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("MAAPS v4.0 WebSocket Server starting...")
    # Start background tasks
    asyncio.create_task(broadcast_status())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("MAAPS v4.0 WebSocket Server shutting down...")


def run_server(host: str = '0.0.0.0', port: int = 8765):
    """Run the server with uvicorn"""
    import uvicorn
    
    logger.info(f"Starting MAAPS v4.0 server on {host}:{port}")
    logger.info(f"Frontend: http://localhost:{port}/")
    logger.info(f"WebSocket: ws://localhost:{port}/ws")
    logger.info(f"Health: http://localhost:{port}/health")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == '__main__':
    run_server()
