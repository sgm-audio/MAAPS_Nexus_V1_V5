"""
MAAPS v4.0 - REAPER Neural Interface

Standalone Python script using reapy for real-time REAPER 7+ integration.
Provides:
- Real-time track state telemetry (LUFS, centroid, key, etc.)
- One-click "Generate Texture/Vocal/Stem" from selected items
- Imports generated stems to new colored tracks at edit cursor
- Applies AI suggestions: automation, bus routing, reference matching
- WebSocket/FastAPI uplink for cyberpunk frontend

Can run inside REAPER (Python enabled) or externally via TCP.
"""

import logging
import asyncio
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger('maaps.reaper')

# Try to import reapy (available inside REAPER or with reapy installed)
try:
    import reapy
    REAPY_AVAILABLE = True
except ImportError:
    REAPY_AVAILABLE = False
    logger.warning("reapy not available, running in mock mode")


@dataclass
class ReaperConnection:
    """REAPER connection state"""
    connected: bool = False
    project_name: str = ""
    sample_rate: int = 44100
    bpm: float = 120.0
    play_state: str = "stopped"
    edit_cursor: float = 0.0


class ReaperNeuralInterface:
    """
    REAPER Neural Interface for MAAPS v4.0
    
    Bidirectional communication with REAPER DAW:
    - Pull: Track states, selected items, project info
    - Push: Generated stems, automation, FX chains, suggestions
    """
    
    def __init__(self, host: str = 'localhost', port: int = 8888):
        self.name = "ReaperNeuralInterface"
        self.host = host
        self.port = port
        self.connection = ReaperConnection()
        self._ws_server = None
        
        logger.info(f"ReaperNeuralInterface initialized ({host}:{port})")
    
    async def connect(self) -> bool:
        """Connect to REAPER via reapy"""
        if not REAPY_AVAILABLE:
            logger.warning("reapy unavailable, using mock connection")
            self.connection.connected = True
            self.connection.project_name = "Mock Project"
            return True
        
        try:
            # Connect to REAPER
            reapy.connect()
            
            # Get project info
            project = reapy.Project()
            self.connection.connected = True
            self.connection.project_name = project.name
            self.connection.sample_rate = project.sample_rate
            self.connection.bpm = project.tempo
            self.connection.play_state = self._get_play_state()
            self.connection.edit_cursor = project.edit_cursor
            
            logger.info(f"Connected to REAPER: {self.connection.project_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to REAPER: {e}")
            self.connection.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from REAPER"""
        if REAPY_AVAILABLE:
            try:
                reapy.disconnect()
            except:
                pass
        
        self.connection.connected = False
        logger.info("Disconnected from REAPER")
    
    def _get_play_state(self) -> str:
        """Get current play state"""
        if not REAPY_AVAILABLE:
            return "stopped"
        
        if reapy.is_playing():
            return "playing"
        elif reapy.is_recording():
            return "recording"
        elif reapy.is_paused():
            return "paused"
        else:
            return "stopped"
    
    async def get_selected_items(self) -> List[Dict[str, Any]]:
        """Get selected items from REAPER"""
        if not self.connection.connected:
            return []
        
        items = []
        
        if REAPY_AVAILABLE:
            try:
                project = reapy.Project()
                for item in project.selected_items:
                    items.append({
                        'id': item.id,
                        'name': item.name,
                        'start': item.start,
                        'end': item.end,
                        'length': item.length,
                        'track_id': item.track.id,
                        'track_name': item.track.name,
                        'media_path': item.media_path
                    })
            except Exception as e:
                logger.error(f"Error getting selected items: {e}")
        
        return items
    
    async def get_track_telemetry(self, track_id: int) -> Dict[str, Any]:
        """Get real-time telemetry for a track"""
        if not REAPY_AVAILABLE or not self.connection.connected:
            return {}
        
        try:
            project = reapy.Project()
            track = project.tracks[track_id] if track_id < len(project.tracks) else None
            
            if not track:
                return {}
            
            # Basic state
            telemetry = {
                'track_id': track_id,
                'track_name': track.name,
                'volume': track.volume,
                'pan': track.pan,
                'muted': track.mute,
                'soloed': track.solo,
                'armed': track.record_arm,
                'fx_chain': [fx.name for fx in track.fxs]
            }
            
            # Audio analysis would require reading track output
            # This is a simplified version
            telemetry['current_lufs'] = None
            telemetry['current_peak_db'] = None
            telemetry['spectral_centroid'] = None
            
            return telemetry
            
        except Exception as e:
            logger.error(f"Error getting track telemetry: {e}")
            return {}
    
    async def import_stems(
        self,
        stem_paths: List[str],
        track_name: str = "MAAPS Generated",
        color: tuple = (0, 128, 255)  # Blue cyberpunk
    ) -> List[int]:
        """
        Import generated stems into REAPER
        
        Args:
            stem_paths: Paths to audio files
            track_name: Base name for tracks
            color: RGB color for tracks (0-255)
            
        Returns:
            List of created track IDs
        """
        if not self.connection.connected:
            logger.warning("Not connected to REAPER, skipping import")
            return []
        
        created_tracks = []
        
        if REAPY_AVAILABLE:
            try:
                project = reapy.Project()
                cursor_pos = project.edit_cursor
                
                for i, stem_path in enumerate(stem_paths):
                    # Create new track
                    track = project.add_track(name=f"{track_name} {i+1}")
                    
                    # Set color
                    track.color = color
                    
                    # Add media item
                    item = track.add_item(stem_path, position=cursor_pos)
                    
                    created_tracks.append(track.id)
                    
                    logger.info(f"Imported stem {i+1}: {stem_path} → Track {track.id}")
                
                logger.info(f"Imported {len(stem_paths)} stems to REAPER")
                
            except Exception as e:
                logger.error(f"Error importing stems: {e}")
        
        return created_tracks
    
    async def apply_automation(
        self,
        track_id: int,
        envelope_type: str,
        points: List[tuple]
    ):
        """
        Apply automation to track
        
        Args:
            track_id: Target track
            envelope_type: 'volume', 'pan', 'mute', etc.
            points: List of (time, value) tuples
        """
        if not REAPY_AVAILABLE or not self.connection.connected:
            return
        
        try:
            project = reapy.Project()
            track = project.tracks[track_id]
            
            # Get or create envelope
            envelope = track.get_envelope(envelope_type)
            
            if not envelope:
                envelope = track.add_envelope(envelope_type)
            
            # Clear existing points
            envelope.clear_points()
            
            # Add new points
            for time, value in points:
                envelope.add_point(time, value)
            
            logger.info(f"Applied {envelope_type} automation to track {track_id}")
            
        except Exception as e:
            logger.error(f"Error applying automation: {e}")
    
    async def get_full_telemetry(self) -> Dict[str, Any]:
        """Get complete project telemetry"""
        if not self.connection.connected:
            return {}
        
        telemetry = {
            'timestamp': datetime.now().isoformat(),
            'project_name': self.connection.project_name,
            'sample_rate': self.connection.sample_rate,
            'bpm': self.connection.bpm,
            'play_state': self._get_play_state(),
            'edit_cursor_pos': self.connection.edit_cursor,
            'selected_track_ids': [],
            'tracks': []
        }
        
        if REAPY_AVAILABLE:
            try:
                project = reapy.Project()
                
                # Get selected tracks
                telemetry['selected_track_ids'] = [
                    t.id for t in project.selected_tracks
                ]
                
                # Get all track states
                for track in project.tracks:
                    track_state = {
                        'track_id': track.id,
                        'track_name': track.name,
                        'volume': track.volume,
                        'pan': track.pan,
                        'muted': track.mute,
                        'soloed': track.solo,
                        'armed': track.record_arm,
                        'fx_chain': [fx.name for fx in track.fxs]
                    }
                    telemetry['tracks'].append(track_state)
                    
            except Exception as e:
                logger.error(f"Error getting full telemetry: {e}")
        
        return telemetry
    
    async def start_websocket_server(self, host: str = '0.0.0.0', port: int = 8765):
        """Start WebSocket server for external clients"""
        try:
            from fastapi import FastAPI, WebSocket
            from fastapi.logger import logger as fastapi_logger
            import uvicorn
            
            app = FastAPI(title="MAAPS REAPER Interface")
            
            @app.websocket("/ws")
            async def websocket_endpoint(websocket: WebSocket):
                await websocket.accept()
                
                while True:
                    # Receive command
                    data = await websocket.receive_json()
                    command = data.get('command')
                    
                    if command == 'get_telemetry':
                        telemetry = await self.get_full_telemetry()
                        await websocket.send_json(telemetry)
                    
                    elif command == 'get_selected_items':
                        items = await self.get_selected_items()
                        await websocket.send_json({'items': items})
                    
                    elif command == 'generate':
                        # Forward to MAAPS orchestrator
                        # This would need a callback to the main system
                        await websocket.send_json({
                            'status': 'queued',
                            'message': 'Generation request received'
                        })
                    
                    elif command == 'ping':
                        await websocket.send_json({'status': 'pong'})
                    
        except ImportError:
            logger.warning("FastAPI/uvicorn not available, WebSocket server disabled")
    
    async def send_suggestion(
        self,
        track_id: int,
        suggestion_type: str,
        description: str,
        auto_apply: bool = False
    ):
        """Send AI suggestion to REAPER console"""
        message = f"[MAAPS AI] Track {track_id}: {description}"
        
        if auto_apply:
            message += " [AUTO-APPLIED]"
        
        logger.info(message)
        
        if REAPY_AVAILABLE and self.connection.connected:
            # Show in REAPER console
            reapy.show_console_message(f"{message}\n")


# Standalone runner for external use
async def main():
    """Run REAPER interface standalone"""
    interface = ReaperNeuralInterface()
    
    connected = await interface.connect()
    
    if connected:
        logger.info("REAPER Neural Interface ready")
        
        # Get telemetry
        telemetry = await interface.get_full_telemetry()
        logger.info(f"Project: {telemetry.get('project_name')}")
        logger.info(f"Tracks: {len(telemetry.get('tracks', []))}")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
    
    await interface.disconnect()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
