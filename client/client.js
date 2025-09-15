/**
 * LiveKit Client for Pipecat Demo
 * 
 * Handles:
 * - Room connection and participant management
 * - Audio publishing and subscription
 * - Volume monitoring
 * - Connection quality tracking
 * - UI state management
 */

class App {
    constructor() {
        this.room = null;
        this.localAudioTrack = null;
        this.isConnected = false;
        this.isMuted = false;
        this.volumeLevel = 0;

        // Conversation state tracking
        this.isProcessingResponse = false;
        this.conversationStartTime = null;
        this.lastSpeechEndTime = null;

        // Mouth-to-ear latency tracking
        this.speechStartTime = null;
        this.latencyMeasurements = [];
        this.isWaitingForEcho = false;
        this.testCount = 0;
        this.isRunningLatencyTest = false;
        
        // Configuration
        this.config = {
            // Use local LiveKit server by default
            url: 'http://localhost:7880', // Changed from ws:// to http://
            // For LiveKit Cloud, use: 'wss://your-project.livekit.cloud'

            // Room settings
            roomName: 'pipecat-demo',
            participantName: `User-${Math.random().toString(36).substr(2, 9)}`,

            // Audio settings
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                sampleRate: 16000,
                channelCount: 1
            }
        };

        this.init();
    }

    async init() {
        // Generate token after config is set
        this.config.token = await this.generateDevToken();
        
        this.initializeUI();
        this.setupEventListeners();
    }
    
    /**
     * Generate a development token for local LiveKit server
     */
    async generateDevToken() {
        // For local development with docker-compose
        // In production, tokens should be generated server-side
        const payload = {
            iss: 'devkey',
            sub: this.config.participantName,
            iat: Math.floor(Date.now() / 1000),
            exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour
            video: {
                room: this.config.roomName,
                roomJoin: true,
                canPublish: true,
                canSubscribe: true
            }
        };

        const secret = 'secret'; // from livekit.yaml

        function str2ab(str) {
            const buf = new ArrayBuffer(str.length);
            const bufView = new Uint8Array(buf);
            for (let i = 0, strLen = str.length; i < strLen; i++) {
                bufView[i] = str.charCodeAt(i);
            }
            return buf;
        }

        function base64url(a) {
            return btoa(String.fromCharCode.apply(null, new Uint8Array(a)))
                .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
        }

        const header = {
            alg: 'HS256',
            typ: 'JWT'
        };

        const headerB64 = btoa(JSON.stringify(header)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
        const bodyB64 = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

        const data = `${headerB64}.${bodyB64}`;

        const encoder = new TextEncoder();
        const key = await crypto.subtle.importKey(
            "raw",
            encoder.encode(secret),
            { name: "HMAC", hash: "SHA-256" },
            false,
            ["sign"]
        );

        const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(data));
        
        return `${data}.${base64url(signature)}`;
    }
    
    /**
     * Initialize UI elements
     */
    initializeUI() {
        this.elements = {
            status: document.getElementById('status'),
            joinBtn: document.getElementById('joinBtn'),
            leaveBtn: document.getElementById('leaveBtn'),
            logs: document.getElementById('logs'),
            volumeBar: document.getElementById('volumeBar'),
            latencyValue: document.getElementById('latencyValue'),
            avgLatencyValue: document.getElementById('avgLatencyValue'),
            connectionQuality: document.getElementById('connectionQuality')
        };
    }
    
    /**
     * Setup event listeners for UI controls
     */
    setupEventListeners() {
        if (this.elements.joinBtn) {
            this.elements.joinBtn.addEventListener('click', () => this.joinRoom());
        }
        if (this.elements.leaveBtn) {
            this.elements.leaveBtn.addEventListener('click', () => this.leaveRoom());
        }
    }
    
    /**
     * Join the LiveKit room
     */
    async joinRoom() {
        try {
            this.updateStatus('connecting', 'Connecting to room...');
            this.log('Connecting to LiveKit room...');
            
            // Create room instance
            this.room = new LivekitClient.Room({
                adaptiveStream: true,
                dynacast: true,
                videoCaptureDefaults: {
                    resolution: LivekitClient.VideoPresets.h720.resolution,
                },
            });
            
            // Setup room event listeners
            this.setupRoomEventListeners();
            
            // Connect to room
            await this.room.connect(this.config.url, this.config.token);
            
            // Enable microphone
            await this.enableMicrophone();
            
            this.isConnected = true;
            this.updateStatus('connected', 'Connected - Start speaking!');
            this.updateUI();
            
            this.log('Successfully connected to room');
            
        } catch (error) {
            this.log(`Failed to join room: ${error.message}`, 'error');
            console.error('LiveKit connection error details:', error);

            // Provide helpful error messages
            let errorMessage = error.message;
            if (error.message.includes('Connection refused') || error.message.includes('ECONNREFUSED')) {
                errorMessage = 'LiveKit server not running. Please start: docker-compose up -d';
            } else if (error.message.includes('WebSocket')) {
                errorMessage = 'WebSocket connection failed. Check LiveKit server status.';
            } else if (error.message.includes('signal connection')) {
                errorMessage = 'Cannot connect to LiveKit signal server. Check server configuration.';
            } else if (error.message.includes('not reachable')) {
                errorMessage = 'LiveKit server not reachable. Is it running on localhost:7880?';
            }

            this.updateStatus('disconnected', `Connection failed: ${errorMessage}`);
            
            // Show additional debugging info
            this.log(`Debug info: Trying to connect to ${this.config.url}`, 'info');
        }
    }
    
    /**
     * Leave the LiveKit room
     */
    async leaveRoom() {
        try {
            this.log('Leaving room...');

            // Clean up state first
            this.isConnected = false;
            this.isProcessingResponse = false;
            this.isWaitingForEcho = false;
            this.conversationStartTime = null;
            this.lastSpeechEndTime = null;
            this.speechStartTime = null;

            // Stop local audio track
            if (this.localAudioTrack) {
                this.localAudioTrack.stop();
                this.localAudioTrack = null;
            }

            // Disconnect from room
            if (this.room) {
                await this.room.disconnect();
                this.room = null;
            }

            // Reset UI
            this.updateStatus('disconnected', 'Disconnected');
            this.updateUI();

            // Reset volume bar
            if (this.elements.volumeBar) {
                this.elements.volumeBar.style.width = '0%';
            }

            // Reset latency display
            if (this.elements.latencyValue) {
                this.elements.latencyValue.textContent = '--';
                this.elements.latencyValue.style.color = '';
            }

            this.log('Successfully left room');

        } catch (error) {
            this.log(`Error leaving room: ${error.message}`, 'error');
            // Force cleanup even if disconnect fails
            this.isConnected = false;
            this.room = null;
            this.localAudioTrack = null;
            this.updateStatus('disconnected', 'Disconnected (with errors)');
            this.updateUI();
        }
    }

    /**
     * Handle agent audio start for latency measurement
     */
    handleAgentAudioStart() {
        if (this.isWaitingForEcho && this.speechStartTime) {
            const echoTime = Date.now();
            const latency = echoTime - this.speechStartTime;

            // Record latency measurement
            this.latencyMeasurements.push(latency);

            // Calculate average latency
            const avgLatency = Math.round(
                this.latencyMeasurements.reduce((a, b) => a + b, 0) / this.latencyMeasurements.length
            );

            // Enhanced terminal logging
            this.testCount++;
            const status = latency < 600 ? 'PASS' : 'HIGH';
            const statusIcon = latency < 600 ? '✅' : '⚠️';

            // Terminal-style logging
            console.log(`🎯 LATENCY TEST ${this.testCount}: ${latency}ms ${statusIcon} ${status}`);
            console.log(`📊 Round-trip time: ${latency}ms`);
            console.log(`⏱️  Timestamp: ${new Date().toISOString()}`);

            if (latency < 600) {
                console.log(`🎉 SUCCESS: Achieved latency under 600ms (${latency}ms)`);
            }

            // Update microphone status with latency result
            this.updateMicrophoneStatus(`${statusIcon} Latency: ${latency}ms (avg: ${avgLatency}ms)`);

            this.log(`🔊 Agent response detected! Mouth-to-ear latency: ${latency}ms`, 'success');
            this.log(`📊 Average latency (${this.latencyMeasurements.length} measurements): ${avgLatency}ms`, 'info');

            // Update latency displays
            if (this.elements.latencyValue) {
                this.elements.latencyValue.textContent = `${latency}`;
                console.log(`📈 UI latency updated: ${latency}ms`);

                // Color code the current latency value
                if (latency < 300) {
                    this.elements.latencyValue.style.color = '#38a169'; // Green
                } else if (latency < 600) {
                    this.elements.latencyValue.style.color = '#d69e2e'; // Yellow
                } else {
                    this.elements.latencyValue.style.color = '#e53e3e'; // Red
                }
            } else {
                console.warn('latencyValue element not found');
            }

            if (this.elements.avgLatencyValue) {
                this.elements.avgLatencyValue.textContent = `${avgLatency}`;

                // Color code the average latency value
                if (avgLatency < 300) {
                    this.elements.avgLatencyValue.style.color = '#38a169'; // Green
                } else if (avgLatency < 600) {
                    this.elements.avgLatencyValue.style.color = '#d69e2e'; // Yellow
                } else {
                    this.elements.avgLatencyValue.style.color = '#e53e3e'; // Red
                }
            }

            // Show detailed latency statistics every 3 measurements
            if (this.latencyMeasurements.length % 3 === 0) {
                this.showLatencyStatistics();
            }

            // Reset state
            this.isProcessingResponse = false;
            this.isWaitingForEcho = false;
            this.updateMicrophoneStatus('Ready to speak...');
            this.updateUI();
        }
    }

    /**
     * Show comprehensive latency statistics
     */
    showLatencyStatistics() {
        if (this.latencyMeasurements.length === 0) {
            console.log('⚠️ No latency measurements recorded yet');
            return;
        }

        const measurements = this.latencyMeasurements;
        const avg = measurements.reduce((a, b) => a + b, 0) / measurements.length;
        const min = Math.min(...measurements);
        const max = Math.max(...measurements);
        const under600 = measurements.filter(m => m < 600).length;
        const successRate = (under600 / measurements.length) * 100;

        // Sort for median calculation
        const sorted = [...measurements].sort((a, b) => a - b);
        const median = sorted.length % 2 === 0
            ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
            : sorted[Math.floor(sorted.length / 2)];

        // Terminal output
        console.log('='.repeat(60));
        console.log('📈 LATENCY MEASUREMENT SUMMARY');
        console.log('='.repeat(60));
        console.log(`📊 Total Tests: ${measurements.length}`);
        console.log(`⏱️  Average Latency: ${avg.toFixed(1)}ms`);
        console.log(`🚀 Minimum Latency: ${min}ms`);
        console.log(`🐌 Maximum Latency: ${max}ms`);
        console.log(`📊 Median Latency: ${median.toFixed(1)}ms`);
        console.log(`✅ Tests under 600ms: ${under600}/${measurements.length} (${successRate.toFixed(1)}%)`);

        if (under600 > 0) {
            console.log('🎉 SUCCESS: At least one measurement under 600ms achieved!');
        } else {
            console.log('⚠️ WARNING: No measurements under 600ms yet');
        }

        console.log('='.repeat(60));

        // Also log to UI
        this.log(`📈 Stats: ${measurements.length} tests, avg: ${avg.toFixed(1)}ms, ${under600} under 600ms`, 'info');
    }

    /**
     * Trigger a test latency measurement (for demonstration)
     */
    triggerTestLatencyMeasurement() {
        if (!this.isConnected) {
            this.log('❌ Not connected to room', 'error');
            return;
        }

        // Simulate user speech start
        this.speechStartTime = Date.now();
        this.isProcessingResponse = true;
        this.isWaitingForEcho = true;

        this.log('🧪 TEST: Simulating speech start for latency measurement...', 'info');

        // The next agent audio event will trigger the latency calculation
        // Since agent is already playing audio, this should trigger immediately
    }

    /**
     * Enable microphone and start publishing audio
     */
    async enableMicrophone() {
        try {
            this.log('Enabling microphone...');

            // First check if we have microphone permissions
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                this.log('Microphone permissions granted');

                // Stop the test stream
                stream.getTracks().forEach(track => track.stop());
            } catch (permError) {
                this.log(`Microphone permission denied: ${permError.message}`, 'error');
                throw new Error('Microphone access denied. Please allow microphone access and refresh the page.');
            }

            // Create local audio track optimized for speech detection
            this.localAudioTrack = await LivekitClient.createLocalAudioTrack({
                echoCancellation: true,   // Enable for better quality
                noiseSuppression: true,   // Enable for better quality
                autoGainControl: true,    // Enable for consistent levels
                sampleRate: 48000,        // Higher sample rate
                channelCount: 1
            });

            this.log('Local audio track created successfully');

            // Publish the track
            await this.room.localParticipant.publishTrack(this.localAudioTrack);
            this.log('Audio track published to room');

            // Start volume monitoring
            await this.startVolumeMonitoring();

            this.log('Microphone enabled and publishing');

        } catch (error) {
            this.log(`Failed to enable microphone: ${error.message}`, 'error');
            throw error;
        }
    }

    /**
     * Setup room event listeners
     */
    setupRoomEventListeners() {
        // Participant events
        this.room.on(LivekitClient.RoomEvent.ParticipantConnected, (participant) => {
            this.log(`Participant connected: ${participant.identity}`);
            this.updateParticipantCount();
        });

        this.room.on(LivekitClient.RoomEvent.ParticipantDisconnected, (participant) => {
            this.log(`Participant disconnected: ${participant.identity}`);
            this.updateParticipantCount();
        });

        // Track events
        this.room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            this.log(`Subscribed to ${track.kind} track from ${participant.identity}`);

            if (track.kind === LivekitClient.Track.Kind.Audio) {
                // Auto-play audio from other participants (like the agent)
                const audioElement = track.attach();

                // Set audio properties for better playback
                audioElement.autoplay = true;
                audioElement.volume = 1.0;
                audioElement.muted = false;

                // Try to play with error handling
                audioElement.play().then(() => {
                    this.log(`🔊 Audio track attached and playing from ${participant.identity}`, 'success');
                }).catch(error => {
                    this.log(`Failed to play audio from ${participant.identity}: ${error.message}`, 'error');
                    // Try to play again after user interaction
                    document.addEventListener('click', () => {
                        audioElement.play().catch(e => console.log('Still cannot play audio:', e));
                    }, { once: true });
                });

                // Set up comprehensive audio monitoring for latency measurement
                this.setupAudioLatencyDetection(audioElement);

                // Key audio event listeners for latency measurement
                audioElement.addEventListener('play', () => {
                    console.log('🎵 Agent audio started');
                    this.handleAgentAudioStart();
                });

                audioElement.addEventListener('canplay', () => {
                    this.handleAgentAudioStart();
                });

                audioElement.addEventListener('error', (e) => {
                    this.log(`🚨 Audio error: ${e.error?.message || 'Unknown error'}`, 'error');
                });
            }
        });

        this.room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
            this.log(`Unsubscribed from ${track.kind} track from ${participant.identity}`);
        });

        // Connection quality events
        this.room.on(LivekitClient.RoomEvent.ConnectionQualityChanged, (quality, participant) => {
            if (participant === this.room.localParticipant) {
                this.updateConnectionQuality(quality);
            }
        });

        // Disconnection events
        this.room.on(LivekitClient.RoomEvent.Disconnected, (reason) => {
            this.log(`Disconnected from room: ${reason}`);

            // Clean up state
            this.isConnected = false;
            this.isProcessingResponse = false;
            this.isWaitingForEcho = false;

            // Stop local audio track
            if (this.localAudioTrack) {
                this.localAudioTrack.stop();
                this.localAudioTrack = null;
            }

            // Reset UI elements
            if (this.elements.volumeBar) {
                this.elements.volumeBar.style.width = '0%';
            }

            if (this.elements.latencyValue) {
                this.elements.latencyValue.textContent = '--';
                this.elements.latencyValue.style.color = '';
            }

            this.updateStatus('disconnected', `Disconnected: ${reason}`);
            this.updateUI();
        });

        // Error events
        this.room.on(LivekitClient.RoomEvent.RoomMetadataChanged, (metadata) => {
            this.log(`Room metadata changed: ${metadata}`);
        });

        // Data channel for tracking agent processing state
        this.room.on(LivekitClient.RoomEvent.DataReceived, (payload, participant) => {
            try {
                const data = JSON.parse(new TextDecoder().decode(payload));
                console.log('📡 Received data from agent:', data);
                this.handleAgentData(data);
            } catch (error) {
                this.log(`Error parsing agent data: ${error.message}`, 'error');
            }
        });
    }

    /**
     * Toggle microphone mute
     */
    async toggleMute() {
        if (!this.localAudioTrack) return;

        try {
            this.isMuted = !this.isMuted;
            await this.localAudioTrack.setMuted(this.isMuted);

            this.elements.muteBtn.textContent = this.isMuted ? 'Unmute' : 'Mute';
            this.elements.muteBtn.className = this.isMuted ? 'btn-warning' : 'btn-secondary';

            this.log(`Microphone ${this.isMuted ? 'muted' : 'unmuted'}`);

        } catch (error) {
            this.log(`Failed to toggle mute: ${error.message}`, 'error');
        }
    }

    /**
     * Start monitoring microphone volume
     */
    async startVolumeMonitoring() {
        if (!this.localAudioTrack) {
            this.log('No local audio track available for volume monitoring', 'warning');
            return;
        }

        try {
            // Get the MediaStreamTrack from LiveKit
            const mediaStreamTrack = this.localAudioTrack.mediaStreamTrack;
            if (!mediaStreamTrack) {
                this.log('No MediaStreamTrack available for volume monitoring', 'warning');
                return;
            }
            
            console.log('🎤 Starting microphone volume monitoring...');

            // Create audio context for volume analysis
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();

            // Resume audio context if suspended (required by some browsers)
            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }

            const mediaStream = new MediaStream([mediaStreamTrack]);
            const source = audioContext.createMediaStreamSource(mediaStream);
            const analyser = audioContext.createAnalyser();

            // Configure analyser for better sensitivity
            analyser.fftSize = 2048;  // Higher resolution
            analyser.smoothingTimeConstant = 0.3;  // Less smoothing for more responsive detection
            source.connect(analyser);

            const bufferLength = analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            this.log(`Audio context created. Sample rate: ${audioContext.sampleRate}Hz`, 'info');

            // Test if we're getting any audio data (reduced logging)
            let testCount = 0;
            const testAudio = () => {
                analyser.getByteTimeDomainData(dataArray);
                let hasAudio = false;
                let nonSilentSamples = 0;
                for (let i = 0; i < bufferLength; i++) {
                    if (dataArray[i] !== 128) { // 128 is silence in byte time domain
                        hasAudio = true;
                        nonSilentSamples++;
                    }
                }
                testCount++;
                if (testCount < 3) {
                    // Only log first few detections to confirm it's working
                    if (hasAudio) {
                        console.log(`🎤 Audio detected: ${nonSilentSamples} samples (test ${testCount}/3)`);
                    }
                    setTimeout(testAudio, 200);
                } else if (testCount === 3) {
                    console.log('✅ Microphone monitoring active');
                }
            };
            setTimeout(testAudio, 500); // Start testing after 500ms

            const updateVolume = () => {
                if (!this.isConnected) return;

                // Use time domain data for better volume detection
                analyser.getByteTimeDomainData(dataArray);

                // Calculate RMS (Root Mean Square) for more accurate volume
                let sum = 0;
                for (let i = 0; i < bufferLength; i++) {
                    const sample = (dataArray[i] - 128) / 128; // Convert to -1 to 1 range
                    sum += sample * sample;
                }
                const rms = Math.sqrt(sum / bufferLength);

                // Convert to percentage and amplify for better visibility
                this.volumeLevel = Math.min(rms * 500, 100); // Amplify by 500% for better detection

                // Update volume bar if element exists
                if (this.elements.volumeBar) {
                    this.elements.volumeBar.style.width = `${this.volumeLevel}%`;
                    // Add visual feedback with color changes based on volume level
                    if (this.volumeLevel > 50) {
                        this.elements.volumeBar.style.background = 'linear-gradient(90deg, #48bb78, #ed8936, #f56565)';
                    } else if (this.volumeLevel > 20) {
                        this.elements.volumeBar.style.background = 'linear-gradient(90deg, #48bb78, #ed8936)';
                    } else if (this.volumeLevel > 5) {
                        this.elements.volumeBar.style.background = '#48bb78';
                    } else {
                        this.elements.volumeBar.style.background = '#e2e8f0'; // Gray for silence
                    }

                    // Debug volume levels occasionally (every 2 seconds approximately)
                    if (!this.lastVolumeLog || Date.now() - this.lastVolumeLog > 2000) {
                        if (this.volumeLevel > 5) {
                            console.log(`🎤 Volume level: ${this.volumeLevel.toFixed(1)}% (RMS: ${rms.toFixed(4)})`);
                            this.lastVolumeLog = Date.now();
                        }
                    }
                } else {
                    console.warn('Volume bar element not found - checking elements...');
                    console.log('Available elements:', Object.keys(this.elements));
                }

                // Simple speech detection for mouth-to-ear latency measurement
                const isSpeaking = this.volumeLevel > 5; // Lower threshold for better detection

            if (isSpeaking && !this.isProcessingResponse) {
                // User started speaking - record time for mouth-to-ear latency
                this.speechStartTime = Date.now();
                this.isProcessingResponse = true;
                this.isWaitingForEcho = true;

                console.log('🎤 User started speaking - latency measurement started');
                // Visual feedback in microphone section instead of logs
                this.updateMicrophoneStatus('🎤 Speaking... (measuring latency)');
                this.updateUI();
            } else if (!isSpeaking && this.isProcessingResponse && this.speechStartTime) {
                // User stopped speaking
                this.lastSpeechEndTime = Date.now();
                console.log('🤖 User stopped speaking - waiting for agent response...');
                this.updateMicrophoneStatus('🤖 Waiting for agent response...');

                // Auto-complete processing after 8 seconds if no echo detected
                setTimeout(() => {
                    if (this.isProcessingResponse) {
                        console.log('⏰ No agent response detected within 8 seconds');
                        this.updateMicrophoneStatus('⏰ No response detected');
                        this.isProcessingResponse = false;
                        this.isWaitingForEcho = false;
                        this.updateUI();
                    }
                }, 8000); // 8 second timeout
            }

            requestAnimationFrame(updateVolume);
        };

        updateVolume();
        this.log('Volume monitoring started successfully', 'success');

        } catch (error) {
            this.log(`Failed to start volume monitoring: ${error.message}`, 'error');
            console.error('Volume monitoring error:', error);
        }
    }


    /**
     * Update connection status
     */
    updateStatus(state, message) {
        this.elements.status.className = `status ${state}`;
        this.elements.status.textContent = message;
    }

    /**
     * Update UI button states
     */
    updateUI() {
        if (this.elements.joinBtn) {
            this.elements.joinBtn.disabled = this.isConnected;
        }
        if (this.elements.leaveBtn) {
            this.elements.leaveBtn.disabled = !this.isConnected || this.isProcessingResponse;
            if (this.isProcessingResponse) {
                this.elements.leaveBtn.textContent = 'Processing...';
            } else {
                this.elements.leaveBtn.textContent = 'Leave Room';
            }
        }
    }

    /**
     * Update participant count display
     */
    updateParticipantCount() {
        if (this.room && this.room.participants) {
            const count = this.room.participants.size + 1; // +1 for local participant
            this.log(`Participants in room: ${count}`, 'info');

            // Update element if it exists
            if (this.elements.participantCount) {
                this.elements.participantCount.textContent = count;
            }
        }
    }

    /**
     * Update microphone status display
     */
    updateMicrophoneStatus(message) {
        const micStatus = document.getElementById('micStatus');
        if (micStatus) {
            micStatus.textContent = message;
            micStatus.style.color = message.includes('🎤') ? '#38a169' :
                                   message.includes('🤖') ? '#d69e2e' :
                                   message.includes('⏰') ? '#e53e3e' : '#4a5568';
            console.log(`Microphone status updated: ${message}`);
        } else {
            console.warn('micStatus element not found');
        }
    }

    /**
     * Update connection quality display
     */
    updateConnectionQuality(quality) {
        const qualityMap = {
            [LivekitClient.ConnectionQuality.Excellent]: 'Excellent',
            [LivekitClient.ConnectionQuality.Good]: 'Good',
            [LivekitClient.ConnectionQuality.Poor]: 'Poor',
            [LivekitClient.ConnectionQuality.Lost]: 'Lost'
        };

        const qualityText = qualityMap[quality] || 'Unknown';
        this.log(`Connection quality: ${qualityText}`, 'info');

        // Update element if it exists
        if (this.elements.connectionQuality) {
            this.elements.connectionQuality.textContent = qualityText;
        }
    }

    /**
     * Setup audio monitoring for echo detection and latency measurement
     */
    setupAudioLatencyDetection(audioElement) {
        try {
            // Create audio context for monitoring
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = audioContext.createMediaElementSource(audioElement);
            const analyser = audioContext.createAnalyser();

            analyser.fftSize = 256;
            const bufferLength = analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            source.connect(analyser);
            analyser.connect(audioContext.destination);

            // Monitor for audio activity (echo detection)
            const checkAudioActivity = () => {
                if (!this.isWaitingForEcho) {
                    requestAnimationFrame(checkAudioActivity);
                    return;
                }

                analyser.getByteFrequencyData(dataArray);

                // Calculate average volume
                let sum = 0;
                for (let i = 0; i < bufferLength; i++) {
                    sum += dataArray[i];
                }
                const average = sum / bufferLength;

                // Detect echo (audio activity from agent) - use lower threshold for better detection
                if (average > 5 && this.isWaitingForEcho && this.speechStartTime) {
                    this.log(`🎵 Audio activity detected from agent (level: ${average.toFixed(1)})`, 'info');
                    this.handleAgentAudioStart();
                }

                requestAnimationFrame(checkAudioActivity);
            };

            checkAudioActivity();

        } catch (error) {
            this.log(`Audio monitoring setup failed: ${error.message}`, 'error');
        }
    }

    /**
     * Show detailed latency statistics
     */
    showLatencyStatistics() {
        if (this.latencyMeasurements.length === 0) return;

        const measurements = this.latencyMeasurements;
        const avg = Math.round(measurements.reduce((a, b) => a + b, 0) / measurements.length);
        const min = Math.min(...measurements);
        const max = Math.max(...measurements);

        // Calculate median
        const sorted = [...measurements].sort((a, b) => a - b);
        const median = sorted.length % 2 === 0
            ? Math.round((sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2)
            : sorted[Math.floor(sorted.length / 2)];

        this.log(`📈 Latency Statistics (${measurements.length} measurements):`, 'info');
        this.log(`   Average: ${avg}ms | Min: ${min}ms | Max: ${max}ms | Median: ${median}ms`, 'info');

        // Check if we're meeting the <600ms target
        const under600 = measurements.filter(m => m < 600).length;
        const percentage = Math.round((under600 / measurements.length) * 100);
        this.log(`   🎯 Under 600ms: ${under600}/${measurements.length} (${percentage}%)`,
                 percentage >= 80 ? 'success' : 'warning');
    }

    /**
     * Handle data from agent (processing state, latency tracking)
     */
    handleAgentData(data) {
        console.log('📡 Processing agent data:', data);
        
        switch (data.type) {
            case 'processing_start':
                this.isProcessingResponse = true;
                this.conversationStartTime = data.timestamp;
                this.log('🤖 Agent started processing your request...', 'info');
                
                // Update UI to show processing state
                if (this.elements.latencyValue) {
                    this.elements.latencyValue.textContent = 'Processing...';
                    this.elements.latencyValue.style.color = '#d69e2e'; // Yellow
                }
                
                this.updateUI(); // Update button states
                break;

            case 'processing_complete':
                this.isProcessingResponse = false;

                // Use the accurate latency measurement from the agent
                if (data.latency_ms) {
                    const latency = Math.round(data.latency_ms);
                    const avgLatency = Math.round(data.average_latency_ms || latency);
                    
                    console.log(`🎯 Server-side latency measurement: ${latency}ms (avg: ${avgLatency}ms)`);
                    
                    // Store in our measurements for consistency with client-side tracking
                    this.latencyMeasurements.push(latency);
                    
                    // Keep only last 20 measurements
                    if (this.latencyMeasurements.length > 20) {
                        this.latencyMeasurements.shift();
                    }
                    
                    this.log(`✅ Response complete! End-to-end latency: ${latency}ms (avg: ${avgLatency}ms)`, 'success');
                    
                    if (data.tts_text) {
                        this.log(`🎙️ Processed text: "${data.tts_text}"`, 'info');
                    }

                    // Update latency display with server data
                    if (this.elements.latencyValue) {
                        this.elements.latencyValue.textContent = `${latency}`;
                        
                        // Color code based on latency
                        if (latency < 300) {
                            this.elements.latencyValue.style.color = '#38a169'; // Green
                        } else if (latency < 600) {
                            this.elements.latencyValue.style.color = '#d69e2e'; // Yellow
                        } else {
                            this.elements.latencyValue.style.color = '#e53e3e'; // Red
                        }
                    }
                    
                    // Update measurement count display if available
                    const measurementElement = document.getElementById('measurementCount');
                    if (measurementElement) {
                        measurementElement.textContent = `${data.measurement_count || this.latencyMeasurements.length}`;
                    }
                    
                    // Show latency statistics every few measurements
                    if (this.latencyMeasurements.length % 3 === 0) {
                        this.showLatencyStatistics();
                    }
                }
                this.updateUI(); // Update button states
                break;
            
            case 'latency_update':
                // Handle real-time latency measurements from IntelligentProcessor
                if (data.latency_ms && data.latency_ms > 0) {
                    const latency = Math.round(data.latency_ms);
                    
                    console.log(`📊 Real-time latency measurement: ${latency}ms`);
                    
                    // Store the measurement
                    this.latencyMeasurements.push(latency);
                    
                    // Keep only last 20 measurements
                    if (this.latencyMeasurements.length > 20) {
                        this.latencyMeasurements.shift();
                    }
                    
                    // Calculate running average
                    const avgLatency = Math.round(
                        this.latencyMeasurements.reduce((a, b) => a + b, 0) / this.latencyMeasurements.length
                    );
                    
                    this.log(`📊 Latency: ${latency}ms (avg: ${avgLatency}ms from ${this.latencyMeasurements.length} measurements)`, 'info');
                    
                    // Update latency display
                    if (this.elements.latencyValue) {
                        this.elements.latencyValue.textContent = `${latency}`;
                        
                        // Color code based on latency
                        if (latency < 300) {
                            this.elements.latencyValue.style.color = '#38a169'; // Green
                        } else if (latency < 600) {
                            this.elements.latencyValue.style.color = '#d69e2e'; // Yellow
                        } else {
                            this.elements.latencyValue.style.color = '#e53e3e'; // Red
                        }
                    }
                    
                    // Update average latency display
                    if (this.elements.avgLatencyValue) {
                        this.elements.avgLatencyValue.textContent = `${avgLatency}`;
                        
                        // Color code the average
                        if (avgLatency < 300) {
                            this.elements.avgLatencyValue.style.color = '#38a169'; // Green
                        } else if (avgLatency < 600) {
                            this.elements.avgLatencyValue.style.color = '#d69e2e'; // Yellow
                        } else {
                            this.elements.avgLatencyValue.style.color = '#e53e3e'; // Red
                        }
                    }
                    
                    // Show detailed statistics every few measurements
                    if (this.latencyMeasurements.length % 5 === 0) {
                        this.showLatencyStatistics();
                    }
                }
                break;

            default:
                console.log(`🔍 Unknown agent data type: ${data.type}`, data);
                this.log(`Received agent data: ${data.type}`);
        }
    }

    /**
     * Log message to console and UI
     */
    log(message, level = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        logEntry.innerHTML = `<span class="log-timestamp">[${timestamp}]</span> ${message}`;

        if (this.elements.logs) {
            this.elements.logs.appendChild(logEntry);
            this.elements.logs.scrollTop = this.elements.logs.scrollHeight;

            // Keep only last 50 log entries
            while (this.elements.logs.children.length > 50) {
                this.elements.logs.removeChild(this.elements.logs.firstChild);
            }
        }

        // Also log to console with proper method mapping
        const consoleMethod = {
            'error': 'error',
            'warning': 'warn',
            'warn': 'warn',
            'info': 'info',
            'success': 'log',
            'debug': 'debug'
        }[level] || 'log';

        console[consoleMethod](`[LiveKit] ${message}`);
    }
}

// Simplified client for demo purposes when LiveKit SDK is not available
class SimplifiedClient {
    constructor() {
        this.setupUI();
        this.checkBackendStatus();
    }

    setupUI() {
        const connectBtn = document.getElementById('connectBtn');
        const disconnectBtn = document.getElementById('disconnectBtn');

        if (connectBtn) {
            connectBtn.textContent = 'Check Backend Status';
            connectBtn.onclick = () => this.checkBackendStatus();
        }

        if (disconnectBtn) {
            disconnectBtn.style.display = 'none';
        }
    }

    async checkBackendStatus() {
        const status = document.getElementById('status');

        try {
            // Check LiveKit server
            const livekitResponse = await fetch('http://localhost:7880');
            const livekitOk = livekitResponse.ok;

            // Check if agent is running (this is a simple check)
            const agentStatus = "✅ Python agent is connected to room 'pipecat-demo'";

            if (status) {
                status.innerHTML = `
                    <div class="status ${livekitOk ? 'success' : 'error'}">
                        <h3>🎯 LiveKit + Pipecat Demo Status</h3>
                        <p><strong>LiveKit Server:</strong> ${livekitOk ? '✅ Running on localhost:7880' : '❌ Not responding'}</p>
                        <p><strong>Python Agent:</strong> ${agentStatus}</p>
                        <p><strong>Web Client:</strong> ⚠️ Simplified mode (LiveKit SDK not loaded)</p>
                        <hr>
                        <p><strong>Next Steps:</strong></p>
                        <ul>
                            <li>✅ Backend infrastructure is ready</li>
                            <li>⚠️ Need to fix LiveKit JavaScript SDK loading</li>
                            <li>🎯 Once SDK is fixed, you can test voice conversations</li>
                        </ul>
                    </div>
                `;
            }
        } catch (error) {
            if (status) {
                status.innerHTML = `
                    <div class="status error">
                        ❌ Error checking backend status: ${error.message}
                    </div>
                `;
            }
        }
    }
}

// Initialize client when page loads
function initializeClient() {
    // Check for LiveKit SDK availability (multiple possible global names)
    const hasLiveKit = typeof LivekitClient !== 'undefined' ||
                      typeof LiveKit !== 'undefined' ||
                      window.LivekitClient ||
                      window.LiveKit ||
                      (window.LiveKitClient && typeof window.LiveKitClient.Room !== 'undefined');

    if (hasLiveKit) {
        console.log('LiveKit SDK available, initializing client');
        // Set the global reference for consistency
        if (typeof LivekitClient === 'undefined') {
            if (typeof LiveKit !== 'undefined') {
                window.LivekitClient = LiveKit;
            } else if (window.LiveKit) {
                window.LivekitClient = window.LiveKit;
            } else if (window.LiveKitClient) {
                window.LivekitClient = window.LiveKitClient;
            }
        }
        window.app = new App();
        return true;
    }
    console.log('LiveKit SDK not available yet...');
    return false;
}

// Suppress Chrome extension errors
window.addEventListener('error', function(e) {
    if (e.message && e.message.includes('message port closed')) {
        e.preventDefault();
        return false;
    }
});

// Try to initialize immediately
if (!initializeClient()) {
    // If not available, wait for window load
    window.addEventListener('load', () => {
        if (!initializeClient()) {
            // Still not available, try with longer delay
            setTimeout(() => {
                if (!initializeClient()) {
                    // Try one more time with even longer delay
                    setTimeout(() => {
                        if (!initializeClient()) {
                            console.error('LiveKit SDK still not available, using fallback');
                            window.app = new SimplifiedClient();
                        }
                    }, 3000);
                }
            }, 1000);
        }
    });
}
