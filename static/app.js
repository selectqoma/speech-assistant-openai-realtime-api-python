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
        this.errorDiv = document.getElementById('error');
    }

    bindEvents() {
        this.micButton.addEventListener('click', () => this.toggleRecording());
    }

    updateStatus(message) {
        console.log('[STATUS]', message);
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
            this.updateStatus('Connecting...');
            this.hideError();
            
// Auto-connecting to backend on page load
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
            
            // Get microphone permission with specific audio settings for OpenAI
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    sampleRate: 8000,
                    channelCount: 1,
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
                this.updateStatus('Connected');
                                this.micButton.disabled = false;
                console.log('WebSocket connected');
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };

            this.ws.onclose = () => {
                this.isConnected = false;
                this.updateStatus('Disconnected');
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
            this.updateStatus('Connection failed');
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
                    try {
                        // Convert audio blob to PCM16 format
                        const arrayBuffer = await event.data.arrayBuffer();
                        const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
                        const pcm16Data = this.convertToPCM16(audioBuffer);
                        const base64Audio = this.arrayBufferToBase64(pcm16Data);
                        
                        console.log('Sending audio chunk:', pcm16Data.length, 'bytes');
                        
                        this.ws.send(JSON.stringify({
                            type: 'audio',
                            audio: base64Audio,
                            timestamp: Date.now()
                        }));
                    } catch (error) {
                        console.error('Error processing audio:', error);
                    }
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



    convertToPCM16(audioBuffer) {
        // Get the audio data from the first channel
        const channelData = audioBuffer.getChannelData(0);
        
        // Convert to PCM16 (16-bit signed integers)
        const pcm16Data = new Int16Array(channelData.length);
        for (let i = 0; i < channelData.length; i++) {
            // Convert float [-1, 1] to int16 [-32768, 32767]
            pcm16Data[i] = Math.max(-32768, Math.min(32767, Math.round(channelData[i] * 32767)));
        }
        
        return pcm16Data.buffer;
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

            // Convert PCM16 to linear PCM
            const pcm16Data = new Int16Array(bytes.buffer);
            const linearData = new Float32Array(pcm16Data.length);
            for (let i = 0; i < pcm16Data.length; i++) {
                // Convert int16 [-32768, 32767] to float [-1, 1]
                linearData[i] = pcm16Data[i] / 32767.0;
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
            gainNode.gain.value = 1.0;
            
            source.start();
            
            console.log('Playing audio chunk:', linearData.length, 'samples');
            
        } catch (error) {
            console.error('Audio playback error:', error);
        }
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
    
    const assistant = new SpeechAssistant();
    assistant.connect();
}); 