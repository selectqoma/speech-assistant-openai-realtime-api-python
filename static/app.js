class SpeechAssistant {
    constructor() {
        this.ws = null;
        this.mediaRecorder = null;
        this.audioContext = null;
        this.audioQueue = [];
        this.isRecording = false;
        this.isConnected = false;
        
        this.initializeElements();
        this.bindEvents();
    }

    initializeElements() {
        this.micButton = document.getElementById('micButton');
        this.connectButton = document.getElementById('connectButton');
        this.disconnectButton = document.getElementById('disconnectButton');
        this.statusDiv = document.getElementById('status');
        this.errorDiv = document.getElementById('error');
        this.volumeSlider = document.getElementById('volumeSlider');
    }

    bindEvents() {
        this.connectButton.addEventListener('click', () => this.connect());
        this.disconnectButton.addEventListener('click', () => this.disconnect());
        this.micButton.addEventListener('click', () => this.toggleRecording());
        this.volumeSlider.addEventListener('input', (e) => {
            this.setVolume(e.target.value);
        });
    }

    updateStatus(message, className) {
        this.statusDiv.textContent = message;
        this.statusDiv.className = `status ${className}`;
    }

    showError(message) {
        this.errorDiv.textContent = message;
        this.errorDiv.classList.remove('hidden');
    }

    hideError() {
        this.errorDiv.classList.add('hidden');
    }

    async connect() {
        try {
            this.updateStatus('Connecting...', 'connecting');
            this.hideError();
            
            // Check if we're in a secure context (HTTPS or localhost)
            const isLocalhost = window.location.hostname === 'localhost' || 
                               window.location.hostname === '127.0.0.1' ||
                               window.location.hostname === '[::1]' ||
                               window.location.hostname === '0.0.0.0' ||
                               window.location.hostname.startsWith('192.168.') ||
                               window.location.hostname.startsWith('10.') ||
                               window.location.hostname.startsWith('172.');
            
            if (!window.isSecureContext && !isLocalhost) {
                throw new Error('Microphone access requires a secure context (HTTPS or localhost). Please access this page via HTTPS or localhost.');
            }
            
            // Check if getUserMedia is available (with fallback for older browsers)
            if (!navigator.mediaDevices) {
                // Fallback for older browsers
                navigator.mediaDevices = {};
            }
            
            if (!navigator.mediaDevices.getUserMedia) {
                // Fallback for older browsers
                navigator.mediaDevices.getUserMedia = function(constraints) {
                    const getUserMedia = navigator.webkitGetUserMedia || navigator.mozGetUserMedia;
                    
                    if (!getUserMedia) {
                        throw new Error('getUserMedia is not supported in this browser. Please use a modern browser with microphone support.');
                    }
                    
                    return new Promise(function(resolve, reject) {
                        getUserMedia.call(navigator, constraints, resolve, reject);
                    });
                };
            }
            
            // Get microphone permission with flexible audio settings
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            // Initialize audio context
            if (!window.AudioContext && !window.webkitAudioContext) {
                throw new Error('Web Audio API is not supported in this browser.');
            }
            
            // Create audio context with 8kHz sample rate
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            
            // Try to create with specific sample rate (not all browsers support this)
            try {
                this.audioContext = new AudioContextClass({
                    sampleRate: 8000,
                    latencyHint: 'interactive'
                });
            } catch (e) {
                // Fallback to default sample rate
                console.log('Could not set sample rate to 8kHz, using default:', e.message);
                this.audioContext = new AudioContextClass();
            }
            
            // Resume audio context if it's suspended (required for Chrome)
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
            
            console.log('Audio context sample rate:', this.audioContext.sampleRate);

            // Create WebSocket connection
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                this.isConnected = true;
                this.updateStatus('Connected', 'connected');
                this.connectButton.disabled = true;
                this.disconnectButton.disabled = false;
                this.micButton.disabled = false;
                console.log('WebSocket connected');
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };

            this.ws.onclose = () => {
                this.isConnected = false;
                this.updateStatus('Disconnected', 'disconnected');
                this.connectButton.disabled = false;
                this.disconnectButton.disabled = true;
                this.micButton.disabled = true;
                this.stopRecording();
                console.log('WebSocket disconnected');
            };

            this.ws.onerror = (error) => {
                this.showError('WebSocket connection error');
                console.error('WebSocket error:', error);
            };

            // Store the stream for recording
            this.audioStream = stream;

        } catch (error) {
            let errorMessage = 'Connection failed';
            
            if (error.name === 'NotAllowedError') {
                errorMessage = 'Microphone access denied. Please allow microphone permissions and try again.';
            } else if (error.name === 'NotFoundError') {
                errorMessage = 'No microphone found. Please connect a microphone and try again.';
            } else if (error.name === 'NotSupportedError') {
                errorMessage = 'Your browser does not support the required audio features. Please use a modern browser.';
            } else if (error.message) {
                errorMessage = error.message;
            }
            
            this.showError(errorMessage);
            this.updateStatus('Connection failed', 'disconnected');
            console.error('Connection error:', error);
        }
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
        }
        if (this.audioContext) {
            this.audioContext.close();
        }
        this.stopRecording();
    }

    async toggleRecording() {
        if (!this.isConnected) return;

        if (this.isRecording) {
            this.stopRecording();
        } else {
            this.startRecording();
        }
    }

    startRecording() {
        if (!this.audioStream || !this.ws) return;

        try {
            // Create MediaRecorder with appropriate settings
            const options = {
                mimeType: 'audio/webm;codecs=opus'
            };
            
            // Try to set audio settings if supported
            if (this.audioStream.getAudioTracks().length > 0) {
                const audioTrack = this.audioStream.getAudioTracks()[0];
                const capabilities = audioTrack.getCapabilities();
                if (capabilities.sampleRate) {
                    console.log('Available sample rates:', capabilities.sampleRate);
                }
            }
            
            this.mediaRecorder = new MediaRecorder(this.audioStream, options);

            this.mediaRecorder.ondataavailable = async (event) => {
                if (event.data.size > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
                    // Convert audio to mu-law format
                    const audioBuffer = await this.convertToMulaw(event.data);
                    const base64Audio = this.arrayBufferToBase64(audioBuffer);
                    
                    this.ws.send(JSON.stringify({
                        type: 'audio',
                        audio: base64Audio,
                        timestamp: Date.now()
                    }));
                }
            };

            // Send start message
            this.ws.send(JSON.stringify({ type: 'start' }));

            // Start recording
            this.mediaRecorder.start(100); // Collect data every 100ms
            this.isRecording = true;
            this.micButton.classList.add('recording');
            this.micButton.textContent = '⏹️';

        } catch (error) {
            this.showError(`Recording failed: ${error.message}`);
            console.error('Recording error:', error);
        }
    }

    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
            this.micButton.classList.remove('recording');
            this.micButton.textContent = '🎤';

            // Send stop message
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'stop' }));
            }
        }
    }

    async convertToMulaw(audioBlob) {
        // Convert audio blob to mu-law format
        const arrayBuffer = await audioBlob.arrayBuffer();
        const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
        
        // Get the audio data
        const channelData = audioBuffer.getChannelData(0);
        
        // Convert to mu-law
        const mulawData = new Uint8Array(channelData.length);
        for (let i = 0; i < channelData.length; i++) {
            mulawData[i] = this.linearToMulaw(channelData[i]);
        }
        
        return mulawData.buffer;
    }

    linearToMulaw(sample) {
        // Convert linear PCM to mu-law
        const MULAW_BIAS = 0x84;
        const MULAW_CLIP = 32635;
        
        let sign = (sample >> 8) & 0x80;
        if (sign !== 0) sample = -sample;
        if (sample > MULAW_CLIP) sample = MULAW_CLIP;
        
        sample += MULAW_BIAS;
        let exponent = 7;
        let mask = 0x4000;
        
        while ((sample & mask) === 0 && exponent > 0) {
            exponent--;
            mask >>= 1;
        }
        
        let mantissa = (sample >> (exponent + 3)) & 0x0F;
        let mulaw = ~(sign | (exponent << 4) | mantissa);
        
        return mulaw & 0xFF;
    }

    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'audio':
                this.playAudio(data.audio);
                break;
            case 'clear':
                this.clearAudioQueue();
                break;
            default:
                console.log('Received message:', data);
        }
    }

    async playAudio(base64Audio) {
        try {
            // Decode base64 audio
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Convert mu-law to linear PCM
            const linearData = new Float32Array(bytes.length);
            for (let i = 0; i < bytes.length; i++) {
                linearData[i] = this.mulawToLinear(bytes[i]);
            }

            // Create audio buffer with the actual sample rate
            const audioBuffer = this.audioContext.createBuffer(1, linearData.length, this.audioContext.sampleRate);
            audioBuffer.getChannelData(0).set(linearData);

            // Create audio source and play
            const source = this.audioContext.createBufferSource();
            const gainNode = this.audioContext.createGain();
            
            source.buffer = audioBuffer;
            source.connect(gainNode);
            gainNode.connect(this.audioContext.destination);
            
            // Set volume
            gainNode.gain.value = this.volumeSlider.value;
            
            source.start();
            
        } catch (error) {
            console.error('Audio playback error:', error);
        }
    }

    mulawToLinear(mulaw) {
        // Convert mu-law to linear PCM
        mulaw = ~mulaw;
        const sign = mulaw & 0x80;
        const exponent = (mulaw >> 4) & 0x07;
        const mantissa = mulaw & 0x0F;
        
        let sample = mantissa << (exponent + 3);
        sample += 0x84;
        
        if (exponent !== 0) {
            sample += (1 << (exponent + 2));
        }
        
        if (sign !== 0) {
            sample = -sample;
        }
        
        return sample / 32768.0; // Normalize to [-1, 1]
    }

    clearAudioQueue() {
        // Stop any currently playing audio
        if (this.audioContext) {
            this.audioContext.resume();
        }
    }

    setVolume(volume) {
        // Volume is applied when creating new audio sources
        console.log('Volume set to:', volume);
    }
}

// Check browser compatibility
function checkBrowserCompatibility() {
    const issues = [];
    
    // Debug logging
    console.log('Checking browser compatibility...');
    console.log('isSecureContext:', window.isSecureContext);
    console.log('navigator.mediaDevices:', !!navigator.mediaDevices);
    console.log('getUserMedia:', !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia));
    console.log('AudioContext:', !!(window.AudioContext || window.webkitAudioContext));
    console.log('WebSocket:', !!window.WebSocket);
    
    // Check if we're on localhost or a local IP
    const isLocalhost = window.location.hostname === 'localhost' || 
                       window.location.hostname === '127.0.0.1' ||
                       window.location.hostname === '[::1]' ||
                       window.location.hostname === '0.0.0.0' ||
                       window.location.hostname.startsWith('192.168.') ||
                       window.location.hostname.startsWith('10.') ||
                       window.location.hostname.startsWith('172.');
    
    console.log('Hostname:', window.location.hostname);
    console.log('Is localhost:', isLocalhost);
    
    if (!window.isSecureContext && !isLocalhost) {
        issues.push('This page must be accessed via HTTPS or localhost for microphone access.');
    }
    
    // Check for getUserMedia with fallback support
    const hasGetUserMedia = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) ||
                           !!(navigator.webkitGetUserMedia || navigator.mozGetUserMedia) ||
                           !!(navigator.getUserMedia); // Very old browsers
    
    if (!hasGetUserMedia) {
        issues.push('Your browser does not support microphone access. Please use a modern browser.');
    }
    
    if (!window.AudioContext && !window.webkitAudioContext) {
        issues.push('Your browser does not support Web Audio API. Please use a modern browser.');
    }
    
    if (!window.WebSocket) {
        issues.push('Your browser does not support WebSockets. Please use a modern browser.');
    }
    
    console.log('Compatibility issues found:', issues);
    return issues;
}

// Initialize the speech assistant when the page loads
document.addEventListener('DOMContentLoaded', () => {
    const compatibilityIssues = checkBrowserCompatibility();
    
    if (compatibilityIssues.length > 0) {
        const errorDiv = document.getElementById('error');
        errorDiv.textContent = 'Browser compatibility issues: ' + compatibilityIssues.join(' ');
        errorDiv.classList.remove('hidden');
        return;
    }
    
    new SpeechAssistant();
}); 