"""
REAPER Project (.rpp) Parser and Converter
Converts REAPER projects to Ableton Live format with semantic preservation
"""

import xml.etree.ElementTree as ET
import gzip
import json
import re
from typing import Dict, List, Any, Optional
import os

class ReaperProjectParser:
    """
    Parses REAPER .rpp project files and extracts structural information
    """
    
    def __init__(self, rpp_file_path: str):
        self.rpp_file_path = rpp_file_path
        self.project_data = {}
        self.tracks = []
        self.items = []
        self.routing_matrix = {}
        
    def parse(self) -> Dict[str, Any]:
        """
        Parse the REAPER project file and extract all relevant information
        """
        try:
            with open(self.rpp_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the RPP content
            self.project_data = self._parse_rpp_content(content)
            
            return self.project_data
        except Exception as e:
            raise Exception(f"Error parsing REAPER project: {str(e)}")
    
    def _parse_rpp_content(self, content: str) -> Dict[str, Any]:
        """
        Parse the raw RPP content into structured data
        """
        lines = content.split('\n')
        project_data = {
            'header': {},
            'tracks': [],
            'routing': [],
            'time_selection': {},
            'markers': [],
            'regions': [],
            'tempo_map': []
        }
        
        current_track = None
        current_item = None
        
        stack = []  # To handle nested sections
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('<!') or line.startswith('#'):
                continue
                
            # Handle opening/closing of sections
            if line.startswith('<'):
                tag = line[1:].split()[0]
                stack.append(tag)
                
                if tag == 'TRACK':
                    current_track = {
                        'id': len(project_data['tracks']),
                        'name': '',
                        'volume': 1.0,
                        'pan': 0.0,
                        'muted': False,
                        'soloed': False,
                        'fx_chain': [],
                        'sends': [],
                        'receives': [],
                        'color': None,
                        'items': []
                    }
                    project_data['tracks'].append(current_track)
                elif tag == 'ITEM' and current_track is not None:
                    current_item = {
                        'id': len(current_track['items']),
                        'position': 0.0,
                        'length': 1.0,
                        'name': '',
                        'source': '',
                        'take': None,
                        'envelopes': []
                    }
                    current_track['items'].append(current_item)
                    
            elif line.startswith('>'):
                # Closing tag
                if stack:
                    closed_tag = stack.pop()
                    
                    if closed_tag == 'TRACK':
                        current_track = None
                    elif closed_tag == 'ITEM':
                        current_item = None
            else:
                # Regular property line
                parts = line.split(None, 1)
                if len(parts) >= 1:
                    prop_name = parts[0]
                    
                    # Extract value
                    value = parts[1] if len(parts) > 1 else ''
                    
                    # Handle different properties
                    if current_track is not None:
                        if prop_name == 'NAME':
                            current_track['name'] = value
                        elif prop_name == 'MAINSEND':
                            current_track['main_send_disabled'] = int(value) == 0
                        elif prop_name == 'VOLUME':
                            current_track['volume'] = float(value)
                        elif prop_name == 'PAN':
                            current_track['pan'] = float(value)
                        elif prop_name == 'MUTESOLO':
                            flags = value.split()
                            if len(flags) >= 1:
                                current_track['muted'] = int(flags[0]) == 1
                            if len(flags) >= 2:
                                current_track['soloed'] = int(flags[1]) in [1, 2]  # 1=solo, 2=solo exclusive
                        elif prop_name == 'COLOR':
                            try:
                                color_int = int(value)
                                # Convert REAPER color format to RGB
                                if color_int > 0:
                                    r = color_int & 0xFF
                                    g = (color_int >> 8) & 0xFF
                                    b = (color_int >> 16) & 0xFF
                                    current_track['color'] = (r, g, b)
                            except ValueError:
                                pass
                        elif prop_name.startswith('FXCHAIN'):
                            # Extract FX chain information
                            fx_info = self._parse_fx_chain(value)
                            current_track['fx_chain'].append(fx_info)
                        elif prop_name.startswith('SEND'):
                            # Parse send information
                            send_info = self._parse_send(value)
                            current_track['sends'].append(send_info)
                            
                    elif current_item is not None:
                        if prop_name == 'POSITION':
                            current_item['position'] = float(value)
                        elif prop_name == 'LENGTH':
                            current_item['length'] = float(value)
                        elif prop_name == 'NAME':
                            current_item['name'] = value
                        elif prop_name.startswith('SOURCE'):
                            current_item['source'] = value
                        elif prop_name.startswith('TAKE'):
                            current_item['take'] = self._parse_take(value)
                        elif prop_name.startswith('POOLEDEVTVOL'):
                            # Automation envelope for volume
                            env = self._parse_envelope(value, 'volume')
                            current_item['envelopes'].append(env)
        
        return project_data
    
    def _parse_fx_chain(self, fx_string: str) -> Dict[str, Any]:
        """
        Parse FX chain information from REAPER format
        """
        fx_info = {
            'name': '',
            'enabled': True,
            'parameters': {}
        }
        
        # Basic parsing - in real implementation would parse full FX state
        fx_info['name'] = fx_string.split('"')[1] if '"' in fx_string else fx_string
        
        return fx_info
    
    def _parse_send(self, send_string: str) -> Dict[str, Any]:
        """
        Parse send information from REAPER format
        """
        parts = send_string.split()
        send_info = {
            'dest_track': int(parts[0]) if len(parts) > 0 else 0,
            'volume': float(parts[1]) if len(parts) > 1 else 1.0,
            'pan': float(parts[2]) if len(parts) > 2 else 0.0,
            'mute': int(parts[3]) if len(parts) > 3 else 0,
            'mode': int(parts[4]) if len(parts) > 4 else 0  # 0=post-fader, 1=pre-fader
        }
        
        return send_info
    
    def _parse_take(self, take_string: str) -> Dict[str, Any]:
        """
        Parse take information from REAPER format
        """
        take_info = {
            'name': '',
            'source_type': '',
            'file_path': ''
        }
        
        # Very basic parsing
        if 'FILE' in take_string:
            take_info['source_type'] = 'file'
            # Extract file path
            match = re.search(r'"([^"]*)"', take_string)
            if match:
                take_info['file_path'] = match.group(1)
        
        return take_info
    
    def _parse_envelope(self, env_string: str, param_type: str) -> Dict[str, Any]:
        """
        Parse automation envelope information
        """
        envelope = {
            'param_type': param_type,
            'points': [],
            'shape': 'linear'  # default
        }
        
        # Basic parsing - would implement full envelope parsing in real version
        # Format: POOLEDEVTVOL shape num_points point1_time point1_value point1_shape ...
        
        return envelope


class LiveProjectGenerator:
    """
    Generates Ableton Live .als project files from REAPER project data
    """
    
    def __init__(self):
        self.live_namespace = {
            'ns': 'http://www.ableton.com/ns/abl-live-set'
        }
    
    def generate_live_project(self, reaper_data: Dict[str, Any], als_file_path: str):
        """
        Generate a Live .als file from REAPER project data
        """
        try:
            # Create root element
            root = ET.Element('Ableton', attrib={
                'MinorVersion': '1',
                'MajorVersion': '4',
                'SchemaChangeCount': '0',
                'Creator': 'REAPER to Live Converter',
                'Revision': '1.0'
            })
            
            # Create LiveSet element
            live_set = ET.SubElement(root, 'LiveSet')
            
            # Add header info
            self._add_header_info(live_set, reaper_data)
            
            # Add tracks
            self._add_tracks(live_set, reaper_data['tracks'])
            
            # Add tempo map
            self._add_tempo_map(live_set, reaper_data.get('tempo_map', []))
            
            # Write to ALS file (gzipped XML)
            tree = ET.ElementTree(root)
            
            # Write as gzipped file
            with gzip.open(als_file_path, 'wb') as f:
                ET.ElementTree(root).write(f, encoding='utf-8', xml_declaration=True)
                
        except Exception as e:
            raise Exception(f"Error generating Live project: {str(e)}")
    
    def _add_header_info(self, live_set_element: ET.Element, reaper_data: Dict[str, Any]):
        """
        Add header information to the Live set
        """
        # Global settings
        ET.SubElement(live_set_element, 'HasSessionAudioCallbackGate', attrib={'Value': 'false'})
        ET.SubElement(live_set_element, 'HasTrackGate', attrib={'Value': 'true'})
        
        # Creator info
        creator_info = ET.SubElement(live_set_element, 'CreatorInfo')
        ET.SubElement(creator_info, 'CreatorName', attrib={'Value': 'REAPER to Live Converter'})
        ET.SubElement(creator_info, 'IsModified', attrib={'Value': 'true'})
    
    def _add_tracks(self, live_set_element: ET.Element, reaper_tracks: List[Dict[str, Any]]):
        """
        Add tracks from REAPER data to Live project
        """
        tracks_container = ET.SubElement(live_set_element, 'Tracks')
        
        for track_data in reaper_tracks:
            if 'audio_output_routing' in track_data.get('name', '').lower():
                # Create Audio Track
                track_element = ET.SubElement(tracks_container, 'AudioTrack')
                
                # Add track ID
                id_elem = ET.SubElement(track_element, 'Id')
                id_elem.text = str(track_data.get('id', 0))
                
                # Add track name
                name_elem = ET.SubElement(track_element, 'Name')
                name_value = ET.SubElement(name_elem, 'UserName')
                name_value.text = track_data.get('name', f'Track {track_data.get("id", 0)}')
                
                # Add color if available
                if track_data.get('color'):
                    color_elem = ET.SubElement(track_element, 'ColorIndex')
                    r, g, b = track_data['color']
                    # Convert RGB to Live's color index (simplified)
                    color_index = self._rgb_to_live_color_index(r, g, b)
                    color_elem.text = str(color_index)
                
                # Add mixer settings
                mixer = ET.SubElement(track_element, 'Mixer')
                volume = ET.SubElement(mixer, 'Volume')
                volume.text = str(track_data.get('volume', 1.0))
                
                pan = ET.SubElement(mixer, 'Pan')
                pan.text = str(track_data.get('pan', 0.0))
                
                # Add mute/solo status
                if track_data.get('muted'):
                    mute_elem = ET.SubElement(track_element, 'Muted')
                    mute_elem.text = 'true'
                
                # Add items/clips
                self._add_items_to_track(track_element, track_data.get('items', []))
                
                # Add sends
                self._add_sends_to_track(track_element, track_data.get('sends', []))
                
                # Add effects
                self._add_effects_to_track(track_element, track_data.get('fx_chain', []))
    
    def _add_items_to_track(self, track_element: ET.Element, items: List[Dict[str, Any]]):
        """
        Add items (clips) to a track
        """
        # Create a clip slot for each item
        clip_slots = ET.SubElement(track_element, 'ClipSlots')
        
        for item in items:
            clip_slot = ET.SubElement(clip_slots, 'ClipSlot')
            
            # Create an audio clip
            audio_clip = ET.SubElement(clip_slot, 'AudioClip')
            
            # Set clip properties
            name_elem = ET.SubElement(audio_clip, 'Name')
            name_elem.text = item.get('name', 'Unnamed Clip')
            
            start_time = ET.SubElement(audio_clip, 'StartTime')
            start_time.text = str(item.get('position', 0.0))
            
            length = ET.SubElement(audio_clip, 'Length')
            length.text = str(item.get('length', 1.0))
            
            # Add file source if available
            if item.get('source'):
                # This would need to create a SampleRef element in a real implementation
                pass
    
    def _add_sends_to_track(self, track_element: ET.Element, sends: List[Dict[str, Any]]):
        """
        Add send information to a track
        """
        if not sends:
            return
            
        mixer = track_element.find('Mixer')
        if mixer is None:
            mixer = ET.SubElement(track_element, 'Mixer')
        
        sends_container = ET.SubElement(mixer, 'Sends')
        
        for send in sends:
            send_element = ET.SubElement(sends_container, 'TrackSendHolder')
            
            # Destination track reference would go here
            # In a real implementation, this would reference the actual destination track
            send_volume = ET.SubElement(send_element, 'Send')
            send_volume.text = str(send.get('volume', 1.0))
    
    def _add_effects_to_track(self, track_element: ET.Element, fx_chain: List[Dict[str, Any]]):
        """
        Add effects from REAPER to Live track
        """
        if not fx_chain:
            return
            
        device_chain = ET.SubElement(track_element, 'DeviceChain')
        devices_list = ET.SubElement(device_chain, 'Devices')
        
        for fx in fx_chain:
            # Create a generic effect device
            effect_device = ET.SubElement(devices_list, 'AudioEffectGroupDevice')
            
            device_name = ET.SubElement(effect_device, 'Name')
            device_name.text = fx.get('name', 'Unknown Effect')
            
            # In a real implementation, we'd map REAPER effects to Live equivalents
            # and preserve parameters where possible
    
    def _add_tempo_map(self, live_set_element: ET.Element, tempo_map: List[Dict[str, Any]]):
        """
        Add tempo information to Live project
        """
        if not tempo_map:
            # Add default tempo
            tempo_info = ET.SubElement(live_set_element, 'Tempo')
            tempo_value = ET.SubElement(tempo_info, 'Tempo')
            tempo_value.text = '120.0'
            return
            
        # Add tempo information from REAPER project
        for tempo_point in tempo_map:
            # This would implement tempo changes in a real version
            pass
    
    def _rgb_to_live_color_index(self, r: int, g: int, b: int) -> int:
        """
        Convert RGB values to Ableton Live's color index system
        This is a simplified implementation
        """
        # Live uses a predefined color palette, so we find the closest match
        # This is a very basic approximation
        brightness = (r + g + b) / 3
        
        if brightness < 50:
            return 0  # Dark colors
        elif brightness < 150:
            return 1  # Medium colors
        else:
            return 2  # Bright colors


class ReaperToLiveConverter:
    """
    Main converter class that orchestrates the REAPER to Live conversion process
    """
    
    def __init__(self):
        self.parser = ReaperProjectParser("")
        self.generator = LiveProjectGenerator()
    
    def convert(self, rpp_file_path: str, als_file_path: str):
        """
        Convert a REAPER project to Ableton Live format
        """
        print(f"Converting REAPER project '{rpp_file_path}' to Live project '{als_file_path}'")
        
        # Parse the REAPER project
        self.parser.rpp_file_path = rpp_file_path
        reaper_data = self.parser.parse()
        
        print(f"Parsed {len(reaper_data['tracks'])} tracks from REAPER project")
        
        # Generate the Live project
        self.generator.generate_live_project(reaper_data, als_file_path)
        
        print(f"Successfully converted project to Live format: {als_file_path}")
        
        # Report conversion status
        self._report_conversion_status(reaper_data)
    
    def _report_conversion_status(self, reaper_data: Dict[str, Any]):
        """
        Report the status of the conversion
        """
        tracks = reaper_data['tracks']
        total_tracks = len(tracks)
        tracks_with_items = sum(1 for t in tracks if len(t['items']) > 0)
        tracks_with_fx = sum(1 for t in tracks if len(t['fx_chain']) > 0)
        total_items = sum(len(t['items']) for t in tracks)
        
        print("\nConversion Summary:")
        print(f"- Total tracks: {total_tracks}")
        print(f"- Tracks with items: {tracks_with_items}")
        print(f"- Tracks with effects: {tracks_with_fx}")
        print(f"- Total items: {total_items}")
        
        print("\nNote: Some REAPER-specific features may not have direct equivalents in Live.")
        print("Please review the converted project for optimal results.")


# Example usage and testing
if __name__ == "__main__":
    # Example of how to use the converter
    converter = ReaperToLiveConverter()
    
    # Example conversion (these files don't actually exist in this context)
    # converter.convert("input_project.rpp", "output_project.als")
    
    print("REAPER to Live Converter initialized.")
    print("To use: converter.convert('input.rpp', 'output.als')")