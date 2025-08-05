import os
import json
import base64
import asyncio
import time
import websockets
from websockets.asyncio.connection import State
from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dataclasses import asdict

from .config import (
    OPENAI_API_KEY, PORT, SYSTEM_MESSAGE, VOICE, LOG_EVENT_TYPES,
    GREETING, SHOW_TIMING_MATH, STATIC_DIR, TEMPLATES_DIR
)
from .simple_call_logger import simple_call_logger

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
    import os
    import glob
    
    # Get all complete call log files
    call_log_files = glob.glob(os.path.join(CALL_LOG_DIR, "*_complete.json"))
    call_logs = []
    
    for file_path in call_log_files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                call_logs.append(data)
        except Exception as e:
            print(f"Error loading call log {file_path}: {e}")
    
    # Add active calls
    active_call_ids = simple_call_logger.get_active_call_ids()
    
    return {
        "call_logs": call_logs,
        "total_logs": len(call_logs),
        "active_calls": len(active_call_ids),
        "active_call_ids": active_call_ids
    }

@app.get("/call-logs/{log_id}", response_class=JSONResponse)
async def get_call_log(log_id: str):
    """Get a specific call log."""
    import os
    
    # Try to load from file
    call_log_file = os.path.join(CALL_LOG_DIR, f"{log_id}_complete.json")
    if os.path.exists(call_log_file):
        with open(call_log_file, 'r') as f:
            return json.load(f)
    
    raise HTTPException(status_code=404, detail="Call log not found")

@app.post("/call-logs/{log_id}/end", response_class=JSONResponse)
async def end_call(log_id: str):
    """End a call and generate summary."""
    summary = await simple_call_logger.end_call_and_summarize(log_id)
    if summary == "Call not found":
        raise HTTPException(status_code=404, detail="Call not found")
    
    return {
        "message": "Call ended successfully",
        "summary": summary,
        "call_id": log_id
    }

@app.post("/end-current-call", response_class=JSONResponse)
async def end_current_call():
    """End the most recent active call (for testing)."""
    active_call_ids = simple_call_logger.get_active_call_ids()
    if not active_call_ids:
        raise HTTPException(status_code=404, detail="No active calls found")
    
    # Get the most recent call
    call_id = active_call_ids[-1]
    summary = await simple_call_logger.end_call_and_summarize(call_id)
    
    return {
        "message": "Current call ended successfully",
        "summary": summary,
        "call_id": call_id
    }

@app.websocket("/ws")
async def handle_websocket(websocket: WebSocket):
    """Handle WebSocket connections for local speech assistant."""
    print("Client connected")
    await websocket.accept()

    # Start call logging
    call_id = simple_call_logger.start_call()
    print(f"Started call logging with ID: {call_id}")

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
    response_in_progress = False
    assistant_speaking = False  # Track if assistant is currently speaking
    last_tts_sent_at = 0.0  # Track when we last sent TTS to client
    client_recording = False  # Track if client is currently recording
    current_response_id = None  # Track current response ID
    
    # Use global conversation store
    global conversation_store
    print(f"WebSocket connected.")
    
    async with websockets.connect(uri, additional_headers=headers) as openai_ws:
        await initialize_session(openai_ws)
        # Don't send initial trigger here - wait for user to start recording
        
        async def receive_from_client():
            """Receive audio data from client and send it to the OpenAI Realtime API."""
            nonlocal latest_media_timestamp, client_recording
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
                        client_recording = True
                        response_start_timestamp = None
                        latest_media_timestamp = 0
                        last_assistant_item = None
                        
                        # Have the AI speak first like in the example
                        await send_initial_conversation_item(openai_ws)
                    elif data['type'] == 'stop':
                        print("Audio session stopped")
                        client_recording = False
                        # Send input_audio_buffer.end to signal user is done speaking
                        if openai_ws.state == State.OPEN:
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.end"}))
                            print("Sent input_audio_buffer.end")
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.state != State.CLOSED:
                    await openai_ws.close()

        async def send_to_client():
            """Receive events from the OpenAI Realtime API, send audio back to client."""
            nonlocal response_start_timestamp, last_assistant_item, assistant_speaking, last_tts_sent_at, current_response_id
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
                                assistant_speaking = False  # Mark assistant as done speaking

                        if response.get('type') == 'response.audio.delta' and 'delta' in response:
                            print(f"Received audio delta, length: {len(response['delta'])}")
                            audio_delta = {
                                "type": "audio",
                                "audio": response['delta']
                            }
                            await websocket.send_json(audio_delta)
                            last_tts_sent_at = time.monotonic()  # Track when we sent TTS

                            if response_start_timestamp is None:
                                response_start_timestamp = latest_media_timestamp
                                assistant_speaking = True  # Mark assistant as speaking

                            # Update last_assistant_item safely
                            if response.get('item_id'):
                                last_assistant_item = response['item_id']
                                current_response_id = response['item_id']
                        
                        # Handle assistant text responses for logging
                        if response.get('type') == 'response.audio_transcript.delta':
                            # This captures the assistant's speech as text
                            transcript_delta = response.get('delta', '')
                            if transcript_delta.strip():
                                # We'll accumulate the full transcript when response is done
                                pass
                        
                        # Handle completed assistant responses
                        if response.get('type') == 'response.audio_transcript.done':
                            # Get the full transcript from the response
                            full_transcript = response.get('transcript', '')
                            print(f"Eva transcription event received: '{full_transcript}' (length: {len(full_transcript)})")
                            if full_transcript.strip():
                                print(f"Eva transcript saved: '{full_transcript}'")
                                # Log assistant transcript
                                simple_call_logger.add_transcript_entry(
                                    call_id, 
                                    "assistant", 
                                    full_transcript
                                )
                            else:
                                print("Eva transcript was empty, not saving")

                        # Handle interruption when user starts speaking
                        if response.get('type') == 'input_audio_buffer.speech_started':
                            now = time.monotonic()
                            # ignore echo while we're actively outputting TTS
                            echo_window = 0.35  # 350ms works well; tune 300–500ms
                            if client_recording and assistant_speaking and (now - last_tts_sent_at) > echo_window:
                                print(f"User barged in; cancelling response {last_assistant_item or current_response_id}")
                                await openai_ws.send(json.dumps({"type": "response.cancel"}))
                                await websocket.send_json({"type": "clear"})
                                last_assistant_item = None
                                response_start_timestamp = None
                                assistant_speaking = False
                            else:
                                print("Speech started ignored (likely echo or not recording)")
                        
                        # Handle transcription completion
                        if response.get('type') == 'conversation.item.input_audio_transcription.completed':
                            transcript = response.get('transcript', '')
                            print(f"User transcription event received: '{transcript}' (length: {len(transcript)})")
                            if transcript.strip():
                                print(f"User transcript saved: '{transcript}'")
                                # Log user transcript
                                simple_call_logger.add_transcript_entry(
                                    call_id, 
                                    "user", 
                                    transcript
                                )
                            else:
                                print("User transcript was empty, not saving")
                                
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

        try:
            await asyncio.gather(receive_from_client(), send_to_client())
        except Exception as e:
            print(f"WebSocket error: {e}")
        finally:
            # Auto-save call when connection ends
            if call_id:
                print(f"Auto-ending call {call_id}")
                try:
                    summary = await simple_call_logger.end_call_and_summarize(call_id)
                    print(f"Call auto-ended with summary: {summary}")
                except Exception as e:
                    print(f"Error auto-ending call: {e}")

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
            "turn_detection": {
                "type": "server_vad",
                "silence_duration_ms": 800  # Wait 0.8 seconds of silence before assistant speaks
            },
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
