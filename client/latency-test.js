/**
 * Latency Testing for LiveKit + Pipecat Demo
 * 
 * Measures round-trip latency by:
 * 1. Generating a beep sound
 * 2. Publishing it through LiveKit
 * 3. Measuring time until we receive audio back from the agent
 * 4. Calculating and displaying the latency
 */

class LatencyTester {
    constructor() {
        this.isTestRunning = false;
        this.testStartTime = null;
        this.beepFrequency = 1000; // 1kHz beep
        this.beepDuration = 0.1; // 100ms beep
        this.latencyHistory = [];
        this.maxHistorySize = 10;
        
        this.setupAudioContext();
    }
    
    /**
     * Setup Web Audio API context for beep generation
     */
    setupAudioContext() {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    
    /**
     * Generate and send a beep for latency testing
     */
    async sendBeep() {
        if (this.isTestRunning) {
            console.log('Latency test already running');
            return;
        }
        
        if (!window.livekitClient || !window.livekitClient.isConnected) {
            console.log('Not connected to LiveKit room');
            return;
        }
        
        try {
            this.isTestRunning = true;
            this.testStartTime = performance.now();
            
            console.log('🔊 Sending beep for latency test...');
            
            // Generate beep audio
            const beepBuffer = this.generateBeep();
            
            // Create audio track from buffer
            const audioTrack = await this.createAudioTrackFromBuffer(beepBuffer);
            
            // Publish the beep
            await this.publishBeep(audioTrack);
            
            // Start listening for the echo
            this.startEchoDetection();
            
            // Timeout after 5 seconds
            setTimeout(() => {
                if (this.isTestRunning) {
                    this.endTest('Timeout - no response received');
                }
            }, 5000);
            
        } catch (error) {
            console.error('Failed to send beep:', error);
            this.isTestRunning = false;
        }
    }
    
    /**
     * Generate a beep audio buffer
     */
    generateBeep() {
        const sampleRate = this.audioContext.sampleRate;
        const numSamples = Math.floor(sampleRate * this.beepDuration);
        const buffer = this.audioContext.createBuffer(1, numSamples, sampleRate);
        const channelData = buffer.getChannelData(0);
        
        // Generate sine wave
        for (let i = 0; i < numSamples; i++) {
            const time = i / sampleRate;
            channelData[i] = Math.sin(2 * Math.PI * this.beepFrequency * time) * 0.3;
        }
        
        return buffer;
    }
    
    /**
     * Create a LiveKit audio track from an audio buffer
     */
    async createAudioTrackFromBuffer(audioBuffer) {
        // Convert AudioBuffer to MediaStream
        const offlineContext = new OfflineAudioContext(
            audioBuffer.numberOfChannels,
            audioBuffer.length,
            audioBuffer.sampleRate
        );
        
        const source = offlineContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(offlineContext.destination);
        source.start();
        
        const renderedBuffer = await offlineContext.startRendering();
        
        // Create a MediaStreamAudioDestinationNode to get a MediaStream
        const mediaStreamContext = new AudioContext();
        const destination = mediaStreamContext.createMediaStreamDestination();
        
        const bufferSource = mediaStreamContext.createBufferSource();
        bufferSource.buffer = renderedBuffer;
        bufferSource.connect(destination);
        bufferSource.start();
        
        // Get the audio track from the MediaStream
        const mediaStream = destination.stream;
        const audioTrack = mediaStream.getAudioTracks()[0];
        
        return audioTrack;
    }
    
    /**
     * Publish the beep audio track
     */
    async publishBeep(audioTrack) {
        const room = window.livekitClient.room;
        if (!room) throw new Error('No room available');
        
        // Create a temporary audio track
        const livekitTrack = new LiveKit.LocalAudioTrack(audioTrack);
        
        // Publish it temporarily
        await room.localParticipant.publishTrack(livekitTrack);
        
        // Stop the track after the beep duration
        setTimeout(() => {
            livekitTrack.stop();
            room.localParticipant.unpublishTrack(livekitTrack);
        }, this.beepDuration * 1000 + 100); // Add 100ms buffer
    }
    
    /**
     * Start listening for the echo from the agent
     */
    startEchoDetection() {
        const room = window.livekitClient.room;
        if (!room) return;
        
        // Listen for new audio tracks from participants (the agent)
        const onTrackSubscribed = (track, publication, participant) => {
            if (track.kind === LiveKit.Track.Kind.Audio && 
                participant.identity !== room.localParticipant.identity) {
                
                console.log('📡 Received audio from agent, analyzing...');
                this.analyzeIncomingAudio(track);
            }
        };
        
        room.on(LiveKit.RoomEvent.TrackSubscribed, onTrackSubscribed);
        
        // Clean up listener when test ends
        this.cleanupListener = () => {
            room.off(LiveKit.RoomEvent.TrackSubscribed, onTrackSubscribed);
        };
    }
    
    /**
     * Analyze incoming audio for beep detection
     */
    analyzeIncomingAudio(track) {
        if (!this.isTestRunning) return;
        
        // For simplicity, we'll assume any audio response from the agent
        // after our beep is the echo response
        const latency = performance.now() - this.testStartTime;
        this.endTest(`Latency: ${Math.round(latency)}ms`);
    }
    
    /**
     * End the latency test
     */
    endTest(result) {
        if (!this.isTestRunning) return;
        
        this.isTestRunning = false;
        
        if (this.cleanupListener) {
            this.cleanupListener();
            this.cleanupListener = null;
        }
        
        const latency = performance.now() - this.testStartTime;
        
        // Update UI
        this.updateLatencyDisplay(latency);
        
        // Store in history
        this.latencyHistory.push(latency);
        if (this.latencyHistory.length > this.maxHistorySize) {
            this.latencyHistory.shift();
        }
        
        console.log(`🎯 ${result}`);
        
        // Log statistics
        this.logStatistics();
    }
    
    /**
     * Update the latency display in the UI
     */
    updateLatencyDisplay(latency) {
        const latencyElement = document.getElementById('latencyValue');
        if (latencyElement) {
            latencyElement.textContent = `${Math.round(latency)}ms`;
            
            // Color code based on latency
            if (latency < 300) {
                latencyElement.style.color = '#38a169'; // Green
            } else if (latency < 600) {
                latencyElement.style.color = '#d69e2e'; // Yellow
            } else {
                latencyElement.style.color = '#e53e3e'; // Red
            }
        }
    }
    
    /**
     * Log latency statistics
     */
    logStatistics() {
        if (this.latencyHistory.length === 0) return;
        
        const avg = this.latencyHistory.reduce((a, b) => a + b, 0) / this.latencyHistory.length;
        const min = Math.min(...this.latencyHistory);
        const max = Math.max(...this.latencyHistory);
        
        console.log(`📊 Latency Stats (last ${this.latencyHistory.length} tests):`);
        console.log(`   Average: ${Math.round(avg)}ms`);
        console.log(`   Min: ${Math.round(min)}ms`);
        console.log(`   Max: ${Math.round(max)}ms`);
        
        // Log to UI as well
        if (window.livekitClient) {
            window.livekitClient.log(
                `Latency stats - Avg: ${Math.round(avg)}ms, Min: ${Math.round(min)}ms, Max: ${Math.round(max)}ms`
            );
        }
    }
    
    /**
     * Get latency statistics
     */
    getStats() {
        if (this.latencyHistory.length === 0) {
            return { average: 0, min: 0, max: 0, count: 0 };
        }
        
        const avg = this.latencyHistory.reduce((a, b) => a + b, 0) / this.latencyHistory.length;
        const min = Math.min(...this.latencyHistory);
        const max = Math.max(...this.latencyHistory);
        
        return {
            average: Math.round(avg),
            min: Math.round(min),
            max: Math.round(max),
            count: this.latencyHistory.length
        };
    }
}

// Initialize latency tester when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.latencyTester = new LatencyTester();
});
