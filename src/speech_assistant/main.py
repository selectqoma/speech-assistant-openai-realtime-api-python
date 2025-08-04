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
from dataclasses import asdict

from .config import (
    OPENAI_API_KEY, PORT, SYSTEM_MESSAGE, VOICE, LOG_EVENT_TYPES,
    GREETING, SHOW_TIMING_MATH, STATIC_DIR, TEMPLATES_DIR
)
# Moving agent functionality removed - will be replaced with call logging

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
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# OpenAI API key is validated in config.py

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Serve the main HTML page with the speech assistant interface."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health", response_class=JSONResponse)
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "Speech Assistant is running!"}

@app.get("/call-logs", response_class=JSONResponse)
async def get_call_logs():
    """Get all call logs."""
    # TODO: Implement call logging functionality
    return {
        "message": "Call logging functionality coming soon",
        "total_logs": 0
    }

@app.get("/call-logs/{log_id}", response_class=JSONResponse)
async def get_call_log(log_id: str):
    """Get a specific call log."""
    from fastapi import HTTPException
    
    # TODO: Implement call log retrieval
    raise HTTPException(status_code=404, detail="Call logging not yet implemented")

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
    
    # Connection specific state
    latest_media_timestamp = 0
    last_assistant_item = None
    mark_queue = []
    response_start_timestamp = None
    
    async with websockets.connect(uri, additional_headers=headers) as openai_ws:
        await initialize_session(openai_ws)
        # Don't send initial trigger here - wait for user to start recording

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
                        await openai_ws.send(json.dumps(audio_append))

                    elif data['type'] == 'start':
                        print("Audio session started")
                        response_start_timestamp = None
                        latest_media_timestamp = 0
                        last_assistant_item = None
                        
                        # Have the AI speak first like in the example
                        await send_initial_conversation_item(openai_ws)
                    elif data['type'] == 'audio':
                        print(f"Received audio chunk, length: {len(data.get('audio', ''))}")
                        if openai_ws.state == State.OPEN:
                            latest_media_timestamp = int(data.get('timestamp', 0))
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['audio']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                    elif data['type'] == 'stop':
                        print("Audio session stopped")
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.state != State.CLOSED:
                    await openai_ws.close()

        async def send_to_client():
            """Receive events from the OpenAI Realtime API, send audio back to client."""
            nonlocal response_start_timestamp, last_assistant_item
            try:
                async for openai_message in openai_ws:
                    try:
                        response = json.loads(openai_message)
                        print(f"Received OpenAI message: {response.get('type', 'unknown')}")
                        
                        if response['type'] in LOG_EVENT_TYPES:
                            print(f"Received event: {response['type']}")
                            if response['type'] == 'error':
                                print(f"Error from OpenAI: {response}")
                            elif response['type'] == 'response.done':
                                print(f"Response completed. Conversation ID: {response.get('response', {}).get('conversation_id', 'unknown')}")
                                response_start_timestamp = None

                        if response.get('type') == 'response.audio.delta' and 'delta' in response:
                            print(f"Received audio delta, length: {len(response['delta'])}")
                            audio_delta = {
                                "type": "audio",
                                "audio": response['delta']
                            }
                            await websocket.send_json(audio_delta)

                            if response_start_timestamp is None:
                                response_start_timestamp = latest_media_timestamp

                            # Update last_assistant_item safely
                            if response.get('item_id'):
                                last_assistant_item = response['item_id']

                        # Handle interruption when user starts speaking
                        if response.get('type') == 'input_audio_buffer.speech_started':
                            print("Speech started detected.")
                            if last_assistant_item:
                                print(f"Interrupting response with id: {last_assistant_item}")
                                await openai_ws.send(json.dumps({"type": "response.cancel"}))
                                await websocket.send_json({"type": "clear"})
                                last_assistant_item = None
                                response_start_timestamp = None
                        
                        # Handle transcription completion
                        if response.get('type') == 'conversation.item.audio_transcription.completed':
                            transcript = response.get('transcript', '')
                            if transcript.strip():
                                print(f"Transcription completed: '{transcript}'")
                                
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse OpenAI message: {e}")
                        print(f"Raw message: {openai_message}")
                    except Exception as e:
                        print(f"Error processing OpenAI message: {e}")
                        
            except websockets.exceptions.ConnectionClosed as e:
                print(f"OpenAI WebSocket connection closed: {e}")
                if websocket.client_state.value != 3:  # Not CLOSED
                    await websocket.send_json({"type": "error", "message": "Connection to AI service lost"})
            except Exception as e:
                print(f"Error in send_to_client: {e}")
                if websocket.client_state.value != 3:  # Not CLOSED
                    await websocket.send_json({"type": "error", "message": f"Server error: {str(e)}"})

        async def create_threaded_conversation_item(openai_ws, transcript, parent_id=None):
            """Create a conversation item with proper threading."""
            
            # Create conversation item with threading
            conversation_item = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": transcript
                        }
                    ]
                }
            }
            
            # Add parent_id for threading if available
            if parent_id:
                conversation_item["parent_id"] = parent_id
                print(f"Creating threaded conversation item with parent_id: {parent_id}")
            else:
                print("Creating conversation item without parent_id (first message)")
            
            await openai_ws.send(json.dumps(conversation_item))
            print(f"Sent conversation item: '{transcript}'")
            
            # Text input needs an explicit response trigger
            await openai_ws.send(json.dumps({"type": "response.create"}))
            print("Sent response.create for text input")

        await asyncio.gather(receive_from_client(), send_to_client())

async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item if AI talks first."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Greet the user with 'Hello there! I am an AI voice assistant powered by Twilio and the OpenAI Realtime API. You can ask me for facts, jokes, or anything you can imagine. How can I help you?'"
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))
    print("Sent initial conversation item to trigger greeting")


async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.6,
        }
    }
    print(f'Using voice: {VOICE}')
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
