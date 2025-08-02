import os
import json
import base64
import asyncio
import websockets
from websockets.asyncio.connection import State
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))
SYSTEM_MESSAGE = (
    "You are a multilingual assistant that represents AwesomeManicure and helps book meeting using a fictional calendar you pretend exists. "
    "You're concise and prioritize listening to talking. "
    "Your name is Jane. Only greet with 'Hi, thanks for calling AwesomeManicure, my name is Jane, how can I help you?' if this is the very first interaction. "
    "After that, respond naturally to what the user says without repeating the greeting."
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]
SHOW_TIMING_MATH = False

# Global conversation store to maintain context across connections
conversation_store = {
    'last_assistant_item': None,
    'session_id': None,
    'server_start_time': None
}

app = FastAPI()

# Initialize server start time
if conversation_store['server_start_time'] is None:
    import time
    conversation_store['server_start_time'] = time.time()
    print(f"Server started at {conversation_store['server_start_time']}")

# Add endpoint to reset conversation (for testing)
@app.get("/reset-conversation", response_class=JSONResponse)
async def reset_conversation():
    """Reset the conversation state for testing."""
    global conversation_store
    conversation_store['last_assistant_item'] = None
    return {"message": "Conversation reset"}

# Create static and templates directories
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Serve the main HTML page with the speech assistant interface."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health", response_class=JSONResponse)
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "Speech Assistant is running!"}

@app.websocket("/ws")
async def handle_websocket(websocket: WebSocket):
    """Handle WebSocket connections for local speech assistant."""
    print("Client connected")
    await websocket.accept()

    # Create connection with proper headers
    uri = 'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01'
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    async with websockets.connect(uri, additional_headers=headers) as openai_ws:
        await initialize_session(openai_ws)
        # Let server VAD handle all responses automatically

        # Connection specific state
        latest_media_timestamp = 0
        mark_queue = []
        response_start_timestamp = None
        response_in_progress = False
        
        # Use global conversation store
        global conversation_store
        print(f"WebSocket connected.")
        
        
        async def receive_from_client():
            """Receive audio data from client and send it to the OpenAI Realtime API."""
            nonlocal latest_media_timestamp
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['type'] == 'audio' and openai_ws.state == State.OPEN:
                        latest_media_timestamp = int(data.get('timestamp', 0))
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['audio']
                        }
                        print(f"Received audio chunk: {len(data['audio'])} chars")
                        await openai_ws.send(json.dumps(audio_append))
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        

                    elif data['type'] == 'start':
                        
                        print("Audio session started")
                        response_start_timestamp = None
                        latest_media_timestamp = 0
                        # Don't reset last_assistant_item to maintain conversation context
                        
                        # Let server VAD handle all responses automatically
                        print("Audio session started - server VAD will handle responses")
                    elif data['type'] == 'stop':
                        if openai_ws.state == State.OPEN:
                            # No manual clear; server VAD will close the turn
                            # Let OpenAI handle the conversation flow automatically
                            # Only create response if this isn't the first greeting
                            # Let server VAD handle response creation automatically
                            print("User finished speaking - letting server VAD handle response")
                        print("Audio session stopped")
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.state != State.CLOSED:
                    await openai_ws.close()

        async def send_to_client():
            """Receive events from the OpenAI Realtime API, send audio back to client."""
            nonlocal response_start_timestamp, response_in_progress
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}")
                        if response['type'] == 'error':
                            print(f"Error from OpenAI: {response}")
                        elif response['type'] == 'response.done':
                            print(f"Response completed. Conversation ID: {response.get('response', {}).get('conversation_id', 'unknown')}")
                            response_start_timestamp = None  # Reset for next response
                            response_in_progress = False
                            print("Response finished - ready for next interaction")

                    if response.get('type') == 'response.audio.delta' and 'delta' in response:
                        audio_delta = {
                            "type": "audio",
                            "audio": response['delta']
                        }
                        print(f"Sending AI audio chunk: {len(response['delta'])} chars")
                        await websocket.send_json(audio_delta)

                        if response_start_timestamp is None:
                            response_start_timestamp = latest_media_timestamp
                            response_in_progress = True
                            mark_queue.append(True)  # Mark that we're in a response
                            print(f"Starting new AI response at timestamp: {response_start_timestamp}ms")

                        # Update last_assistant_item safely
                        if response.get('item_id'):
                            conversation_store['last_assistant_item'] = response['item_id']
                            print(f"Updated last_assistant_item: {response['item_id']}")

                    # Handle interruption when user starts speaking
                    if response.get('type') == 'input_audio_buffer.speech_started':
                        print("Speech started detected.")
                        if response_in_progress:
                            print("Interrupting response with response.cancel")
                            # Graceful interruption: cancel the response and
                            # flush the local speaker buffer.
                            await openai_ws.send(json.dumps({"type": "response.cancel"}))
                            await websocket.send_json({"type": "clear"})
                            
                            mark_queue.clear()
                            conversation_store['last_assistant_item'] = None
                            response_start_timestamp = None
                            response_in_progress = False
                            print("AI response interrupted - stopped talking")
            except Exception as e:
                print(f"Error in send_to_client: {e}")

        await asyncio.gather(receive_from_client(), send_to_client())

async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {
                "type": "server_vad",
                "create_response": True,
                "threshold": 0.5,
                "prefix_padding_ms": 200
            },
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
