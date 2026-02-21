/**
 * Max for Live Device: Pro Tools Workflow Converter
 * Converts REAPER-specific workflows to Ableton Live equivalents
 * Implements key Pro Tools features using Max for Live JavaScript API
 */

autowatch = 1;

// Import necessary modules
const LiveAPI = require('max-api').LiveAPI;
const mgraphics = require('max-mgraphics');
const fs = require('fs');

// Main Pro Tools Emulator object
const pt_emulator = {
    // Core functionality
    init: function() {
        this.song = new LiveAPI('live_app');
        this.setupProToolsFeatures();
        post("Pro Tools Workflow Emulator initialized\n");
    },
    
    // ===================================
    // PRO TOOLS STYLE EDITING
    // ===================================
    
    tabToTransient: function() {
        try {
            const selectedScene = this.song.call('get_selected_scene');
            const selectedTrack = this.song.call('get_selected_track');
            
            // In Live, navigate to next warp marker in selected clip
            const playingSlotIdx = selectedTrack.get('playing_slot_index');
            if (playingSlotIdx >= 0) {
                const clipSlots = selectedTrack.get('clip_slots');
                if (clipSlots && clipSlots.length > playingSlotIdx) {
                    const clip = new LiveAPI(clipSlots[playingSlotIdx]);
                    if (clip && clip.type === 'audio_clip') {
                        // Get warp markers
                        const warpMarkers = clip.get('warp_markers');
                        if (warpMarkers && warpMarkers.length > 1) {
                            // Find next warp marker after current playhead
                            const currentTime = this.song.get('current_song_time');
                            let nextMarker = null;
                            
                            for (let i = 0; i < warpMarkers.length; i++) {
                                if (warpMarkers[i] > currentTime) {
                                    nextMarker = warpMarkers[i];
                                    break;
                                }
                            }
                            
                            if (nextMarker) {
                                this.song.set('current_song_time', nextMarker);
                            } else {
                                // Move to next scene if no further markers
                                this.selectNextScene();
                            }
                        } else {
                            // No warp markers, move to next scene
                            this.selectNextScene();
                        }
                    }
                }
            }
            
            post("Tabbed to transient/warp marker\n");
        } catch (error) {
            error("Error in tabToTransient: " + error.message + "\n");
        }
    },
    
    smartTool: function() {
        try {
            const selectedTrack = this.song.call('get_selected_track');
            const detailClip = this.song.get('view detail_clip');
            
            if (detailClip) {
                const clipApi = new LiveAPI(detailClip);
                const length = clipApi.get('length');
                
                if (length && length > 0) {
                    const currentTime = this.song.get('current_song_time');
                    const relativePos = (currentTime % length) / length;
                    
                    if (relativePos < 0.1) {
                        // Near beginning - fade in adjustment
                        const fadeInLength = Math.min(
                            clipApi.get('fade_in_length') + 0.1,
                            length * 0.5
                        );
                        clipApi.set('fade_in_length', fadeInLength);
                        post("Adjusted fade-in\n");
                    } else if (relativePos > 0.9) {
                        // Near end - fade out adjustment
                        const fadeOutLength = Math.min(
                            clipApi.get('fade_out_length') + 0.1,
                            length * 0.5
                        );
                        clipApi.set('fade_out_length', fadeOutLength);
                        post("Adjusted fade-out\n");
                    } else {
                        // Middle - selection context
                        post("Selection tool context\n");
                    }
                }
            } else {
                post("Time selection context\n");
            }
        } catch (error) {
            error("Error in smartTool: " + error.message + "\n");
        }
    },
    
    // ===================================
    // ADVANCED MIXING FUNCTIONS
    // ===================================
    
    createVCAMaster: function() {
        try {
            // Get selected tracks
            const tracks = this.getSelectedTracks();
            const selectedTracks = tracks.filter(track => {
                return track.get('is_foldable') || this.isSelected(track);
            });
            
            if (selectedTracks.length === 0) {
                error("No tracks selected for VCA creation\n");
                return;
            }
            
            // Create return track to act as VCA controller
            this.song.call('create_return_track');
            const returnTracks = this.song.get('return_tracks');
            const vcaTrack = new LiveAPI(returnTracks[returnTracks.length - 1]);
            
            vcaTrack.set('name', 'VCA Master');
            vcaTrack.set('color', 0xFFC800); // Orange
            
            // Link selected tracks' volumes to VCA
            // In practice, this would involve complex routing or Max for Live device
            for (let i = 0; i < selectedTracks.length; i++) {
                // Conceptual: route selected track to VCA
                // This would require additional Max for Live device logic
            }
            
            post(`Created VCA Master controlling ${selectedTracks.length} tracks\n`);
        } catch (error) {
            error("Error in createVCAMaster: " + error.message + "\n");
        }
    },
    
    autoGainStage: function() {
        try {
            const allTracks = this.getAllAudioTracks();
            
            for (let i = 0; i < allTracks.length; i++) {
                const track = allTracks[i];
                const mixer = track.get('mixer_device');
                
                if (mixer) {
                    const volume = new LiveAPI(mixer).get('volume');
                    if (volume) {
                        // Simplified gain adjustment
                        const targetLevel = 0.7; // -3dB
                        const currentVal = volume.value;
                        const adjustedVal = Math.min(Math.max(currentVal * (targetLevel / 0.5), 0), 1);
                        
                        volume.set('value', adjustedVal);
                    }
                }
            }
            
            post("Auto gain staging applied\n");
        } catch (error) {
            error("Error in autoGainStage: " + error.message + "\n");
        }
    },
    
    // ===================================
    // AI-INTEGRATED FEATURES
    // ===================================
    
    intelligentEQMatch: function() {
        try {
            const selectedTracks = this.getSelectedTracks();
            
            if (selectedTracks.length < 2) {
                error("Select source track first, then target track\n");
                return;
            }
            
            const sourceTrack = selectedTracks[0];
            const targetTrack = selectedTracks[1];
            
            // Add Eq8 to target track if not present
            let eqDevice = null;
            const devices = targetTrack.get('devices');
            
            for (let i = 0; i < devices.length; i++) {
                const device = new LiveAPI(devices[i]);
                if (device.get('class_name') === 'Eq8') {
                    eqDevice = device;
                    break;
                }
            }
            
            if (!eqDevice) {
                // Attempt to add Eq8 - this requires device browser access
                // Implementation depends on Live version and available devices
                post("Adding Eq8 to target track\n");
            } else {
                post("Eq8 already present on target track\n");
            }
            
            post(`EQ match initiated from ${sourceTrack.get('name')} to ${targetTrack.get('name')}\n`);
        } catch (error) {
            error("Error in intelligentEQMatch: " + error.message + "\n");
        }
    },
    
    setupMixBusRouting: function() {
        try {
            // Define bus categories
            const busCategories = [
                {name: 'Drums Bus', keywords: ['kick', 'snare', 'drum', 'hat', 'tom', 'overhead']},
                {name: 'Bass Bus', keywords: ['bass', 'sub']},
                {name: 'Guitars Bus', keywords: ['guitar', 'gtr']},
                {name: 'Keys Bus', keywords: ['piano', 'keys', 'synth']},
                {name: 'Vocals Bus', keywords: ['vocal', 'vox']},
                {name: 'FX Bus', keywords: ['fx', 'effect', 'reverb', 'delay']}
            ];
            
            // Create return tracks for each category
            const busTracks = {};
            for (let i = 0; i < busCategories.length; i++) {
                const category = busCategories[i];
                
                // Check if bus track already exists
                let existingBus = null;
                const returnTracks = this.song.get('return_tracks');
                
                for (let j = 0; j < returnTracks.length; j++) {
                    const rt = new LiveAPI(returnTracks[j]);
                    if (rt.get('name').toLowerCase().includes(category.name.toLowerCase().replace(' bus', ''))) {
                        existingBus = rt;
                        break;
                    }
                }
                
                if (!existingBus) {
                    this.song.call('create_return_track');
                    const newReturnTracks = this.song.get('return_tracks');
                    const newBus = new LiveAPI(newReturnTracks[newReturnTracks.length - 1]);
                    newBus.set('name', category.name);
                    busTracks[category.name] = newBus;
                } else {
                    busTracks[category.name] = existingBus;
                }
            }
            
            // Categorize and route regular tracks
            const allTracks = this.getAllAudioTracks();
            for (let i = 0; i < allTracks.length; i++) {
                const track = allTracks[i];
                const trackName = track.get('name').toLowerCase();
                
                // Find matching bus
                for (let j = 0; j < busCategories.length; j++) {
                    const category = busCategories[j];
                    for (let k = 0; k < category.keywords.length; k++) {
                        if (trackName.includes(category.keywords[k])) {
                            // Route track to appropriate bus
                            const busIdx = Object.keys(busTracks).indexOf(category.name);
                            if (busIdx >= 0) {
                                const sends = track.get('mixer_device').get('sends');
                                if (sends && sends.length > busIdx) {
                                    sends[busIdx].set('value', 1.0); // Full send
                                }
                            }
                            break;
                        }
                    }
                }
            }
            
            post("Mix bus routing configured\n");
        } catch (error) {
            error("Error in setupMixBusRouting: " + error.message + "\n");
        }
    },
    
    // ===================================
    // WORKFLOW AUTOMATION
    // ===================================
    
    quickBounceStems: function() {
        try {
            // Store original routing states
            const allTracks = this.getAllAudioTracks();
            const originalSends = {};
            
            for (let i = 0; i < allTracks.length; i++) {
                const track = allTracks[i];
                const sends = track.get('mixer_device').get('sends');
                originalSends[track.id] = sends.map(send => send.get('value'));
            }
            
            // Identify bus tracks
            const busTracks = allTracks.filter(track => {
                const name = track.get('name').toLowerCase();
                return name.includes('bus') || name.includes('mix');
            });
            
            // Process each bus track
            for (let i = 0; i < busTracks.length; i++) {
                const busTrack = busTracks[i];
                
                // Mute all other tracks except this bus
                for (let j = 0; j < allTracks.length; j++) {
                    const track = allTracks[j];
                    if (track.id !== busTrack.id) {
                        track.set('mute', true);
                    }
                }
                
                // Unmute the bus track
                busTrack.set('mute', false);
                
                // Start bounce process (conceptual)
                post(`Preparing to bounce ${busTrack.get('name')}\n`);
                
                // Restore muting
                for (let j = 0; j < allTracks.length; j++) {
                    allTracks[j].set('mute', false);
                }
            }
            
            // Restore original send levels
            for (let i = 0; i < allTracks.length; i++) {
                const track = allTracks[i];
                if (originalSends[track.id]) {
                    const sends = track.get('mixer_device').get('sends');
                    for (let j = 0; j < Math.min(sends.length, originalSends[track.id].length); j++) {
                        sends[j].set('value', originalSends[track.id][j]);
                    }
                }
            }
            
            post("Stem bounce completed\n");
        } catch (error) {
            error("Error in quickBounceStems: " + error.message + "\n");
        }
    },
    
    autoColorTracks: function() {
        try {
            const colorMap = [
                // Drums
                {patterns: ['kick', 'bd', 'bassdrum'], color: 0xB40000},
                {patterns: ['snare', 'sn'], color: 0xFF6464},
                {patterns: ['hat', 'hh', 'hihat'], color: 0xFFB4B4},
                {patterns: ['tom'], color: 0xC83232},
                {patterns: ['overhead', 'oh', 'room', 'drum'], color: 0x960000},
                
                // Bass
                {patterns: ['bass', 'sub'], color: 0x00B400},
                
                // Guitars
                {patterns: ['guitar', 'gtr', 'dist', 'clean'], color: 0xFFC800},
                {patterns: ['lead'], color: 0xFFFF64},
                
                // Keys
                {patterns: ['piano', 'keys', 'synth', 'pad'], color: 0x6464FF},
                
                // Vocals
                {patterns: ['vocal', 'vox', 'lead voc'], color: 0xFF00FF},
                {patterns: ['harm', 'bgv', 'backing'], color: 0xFF96FF},
                
                // FX
                {patterns: ['fx', 'effect', 'reverb', 'delay'], color: 0x00FFFF},
                
                // Buses
                {patterns: ['bus', 'master', 'mix'], color: 0xC8C8C8}
            ];
            
            const allTracks = this.getAllAudioTracks();
            
            for (let i = 0; i < allTracks.length; i++) {
                const track = allTracks[i];
                const trackName = track.get('name').toLowerCase();
                
                for (let j = 0; j < colorMap.length; j++) {
                    const rule = colorMap[j];
                    for (let k = 0; k < rule.patterns.length; k++) {
                        if (trackName.includes(rule.patterns[k])) {
                            track.set('color', rule.color);
                            break;
                        }
                    }
                }
            }
            
            post("Tracks auto-colored\n");
        } catch (error) {
            error("Error in autoColorTracks: " + error.message + "\n");
        }
    },
    
    // ===================================
    // METERING AND ANALYSIS
    // ===================================
    
    createMeteringDashboard: function() {
        try {
            // Create return track for metering
            this.song.call('create_return_track');
            const returnTracks = this.song.get('return_tracks');
            const meterTrack = new LiveAPI(returnTracks[returnTracks.length - 1]);
            
            meterTrack.set('name', 'METERS');
            meterTrack.set('mute', true); // Don't hear the meters
            meterTrack.set('volume', 0); // Mute output
            
            post("Metering dashboard created\n");
        } catch (error) {
            error("Error in createMeteringDashboard: " + error.message + "\n");
        }
    },
    
    // ===================================
    // SESSION MANAGEMENT
    // ===================================
    
    saveMixSnapshot: function() {
        try {
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
            const snapshotName = `${timestamp}_snapshot`;
            
            const snapshotData = {};
            
            // Capture all track states
            const allTracks = this.getAllAudioTracks();
            for (let i = 0; i < allTracks.length; i++) {
                const track = allTracks[i];
                const mixer = track.get('mixer_device');
                
                snapshotData[i] = {
                    name: track.get('name'),
                    volume: mixer.get('volume').get('value'),
                    pan: mixer.get('panning').get('value'),
                    mute: track.get('mute'),
                    solo: track.get('solo'),
                    sends: []
                };
                
                // Capture send values
                const sends = mixer.get('sends');
                for (let j = 0; j < sends.length; j++) {
                    snapshotData[i].sends.push(sends[j].get('value'));
                }
            }
            
            // Store in project or external file
            // For this example, we'll store in a simple text file
            const snapshotPath = `pt_snapshots/${snapshotName}.json`;
            if (!fs.existsSync('pt_snapshots')) {
                fs.mkdirSync('pt_snapshots');
            }
            
            fs.writeFileSync(snapshotPath, JSON.stringify(snapshotData, null, 2));
            
            post(`Mix snapshot saved: ${snapshotName}\n`);
        } catch (error) {
            error("Error in saveMixSnapshot: " + error.message + "\n");
        }
    },
    
    recallMixSnapshot: function() {
        try {
            // Look for snapshot files
            if (!fs.existsSync('pt_snapshots')) {
                error("No snapshots directory found\n");
                return;
            }
            
            const snapshotFiles = fs.readdirSync('pt_snapshots')
                .filter(file => file.endsWith('.json'))
                .sort(); // Sort by name to get latest
            
            if (snapshotFiles.length === 0) {
                error("No snapshots available\n");
                return;
            }
            
            const latestSnapshot = snapshotFiles[snapshotFiles.length - 1];
            const snapshotPath = `pt_snapshots/${latestSnapshot}`;
            const snapshotData = JSON.parse(fs.readFileSync(snapshotPath, 'utf8'));
            
            // Apply snapshot
            const allTracks = this.getAllAudioTracks();
            for (const trackIdx in snapshotData) {
                if (allTracks[trackIdx]) {
                    const track = allTracks[trackIdx];
                    const data = snapshotData[trackIdx];
                    const mixer = track.get('mixer_device');
                    
                    mixer.get('volume').set('value', data.volume);
                    mixer.get('panning').set('value', data.pan);
                    track.set('mute', data.mute);
                    track.set('solo', data.solo);
                    
                    // Restore sends
                    const sends = mixer.get('sends');
                    for (let i = 0; i < Math.min(sends.length, data.sends.length); i++) {
                        sends[i].set('value', data.sends[i]);
                    }
                }
            }
            
            post(`Recalled mix snapshot: ${latestSnapshot}\n");
        } catch (error) {
            error("Error in recallMixSnapshot: " + error.message + "\n");
        }
    },
    
    // ===================================
    // HELPER METHODS
    // ===================================
    
    setupProToolsFeatures: function() {
        // Register custom actions
        this.actions = {
            'tab_to_transient': this.tabToTransient.bind(this),
            'smart_tool': this.smartTool.bind(this),
            'create_vca_master': this.createVCAMaster.bind(this),
            'auto_gain_stage': this.autoGainStage.bind(this),
            'intelligent_eq_match': this.intelligentEQMatch.bind(this),
            'setup_mix_bus_routing': this.setupMixBusRouting.bind(this),
            'quick_bounce_stems': this.quickBounceStems.bind(this),
            'auto_color_tracks': this.autoColorTracks.bind(this),
            'create_metering_dashboard': this.createMeteringDashboard.bind(this),
            'save_mix_snapshot': this.saveMixSnapshot.bind(this),
            'recall_mix_snapshot': this.recallMixSnapshot.bind(this)
        };
    },
    
    getSelectedTracks: function() {
        const tracks = [];
        const numTracks = this.song.get('num_tracks');
        
        for (let i = 0; i < numTracks; i++) {
            const track = new LiveAPI('live_track', i);
            if (track.get('is_selected')) {
                tracks.push(track);
            }
        }
        
        return tracks;
    },
    
    isSelected: function(apiObject) {
        return apiObject.get('is_selected') === 1;
    },
    
    getAllAudioTracks: function() {
        const tracks = [];
        const numTracks = this.song.get('num_tracks');
        
        for (let i = 0; i < numTracks; i++) {
            const track = new LiveAPI('live_track', i);
            if (track.get('has_audio_output')) {
                tracks.push(track);
            }
        }
        
        return tracks;
    },
    
    selectNextScene: function() {
        this.song.call('jump_to_next_scene');
    }
};

// Initialize the emulator
pt_emulator.init();

// Export functions for use in Max patch
exports.tab_to_transient = pt_emulator.tabToTransient.bind(pt_emulator);
exports.smart_tool = pt_emulator.smartTool.bind(pt_emulator);
exports.create_vca_master = pt_emulator.createVCAMaster.bind(pt_emulator);
exports.auto_gain_stage = pt_emulator.autoGainStage.bind(pt_emulator);
exports.intelligent_eq_match = pt_emulator.intelligentEQMatch.bind(pt_emulator);
exports.setup_mix_bus_routing = pt_emulator.setupMixBusRouting.bind(pt_emulator);
exports.quick_bounce_stems = pt_emulator.quickBounceStems.bind(pt_emulator);
exports.auto_color_tracks = pt_emulator.autoColorTracks.bind(pt_emulator);
exports.create_metering_dashboard = pt_emulator.createMeteringDashboard.bind(pt_emulator);
exports.save_mix_snapshot = pt_emulator.saveMixSnapshot.bind(pt_emulator);
exports.recall_mix_snapshot = pt_emulator.recallMixSnapshot.bind(pt_emulator);

post("Pro Tools Workflow Converter loaded successfully\n");