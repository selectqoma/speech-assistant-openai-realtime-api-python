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
    "You are a helpful and bubbly AI assistant who loves to chat about "
    "anything the user is interested in and is prepared to offer them facts. "
    "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
    "Always stay positive, but work in a joke when appropriate."
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]
SHOW_TIMING_MATH = False

app = FastAPI()

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

        # Connection specific state
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp = None
        
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
                        last_assistant_item = None
                    elif data['type'] == 'stop':
                        print("Audio session stopped")
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.state != State.CLOSED:
                    await openai_ws.close()

        async def send_to_client():
            """Receive events from the OpenAI Realtime API, send audio back to client."""
            nonlocal last_assistant_item, response_start_timestamp
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)

                    if response.get('type') == 'response.audio.delta' and 'delta' in response:
                        audio_delta = {
                            "type": "audio",
                            "audio": response['delta']
                        }
                        print(f"Sending AI audio chunk: {len(response['delta'])} chars")
                        await websocket.send_json(audio_delta)

                        if response_start_timestamp is None:
                            response_start_timestamp = latest_media_timestamp
                            if SHOW_TIMING_MATH:
                                print(f"Setting start timestamp for new response: {response_start_timestamp}ms")

                        # Update last_assistant_item safely
                        if response.get('item_id'):
                            last_assistant_item = response['item_id']

                    # Handle interruption when user starts speaking
                    if response.get('type') == 'input_audio_buffer.speech_started':
                        print("Speech started detected.")
                        if last_assistant_item:
                            print(f"Interrupting response with id: {last_assistant_item}")
                            await handle_speech_started_event()
            except Exception as e:
                print(f"Error in send_to_client: {e}")

        async def handle_speech_started_event():
            """Handle interruption when the user's speech starts."""
            nonlocal response_start_timestamp, last_assistant_item
            print("Handling speech started event.")
            if mark_queue and response_start_timestamp is not None:
                elapsed_time = latest_media_timestamp - response_start_timestamp
                if SHOW_TIMING_MATH:
                    print(f"Calculating elapsed time for truncation: {latest_media_timestamp} - {response_start_timestamp} = {elapsed_time}ms")

                if last_assistant_item:
                    if SHOW_TIMING_MATH:
                        print(f"Truncating item with ID: {last_assistant_item}, Truncated at: {elapsed_time}ms")

                    truncate_event = {
                        "type": "conversation.item.truncate",
                        "item_id": last_assistant_item,
                        "content_index": 0,
                        "audio_end_ms": elapsed_time
                    }
                    await openai_ws.send(json.dumps(truncate_event))

                await websocket.send_json({
                    "type": "clear"
                })

                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp = None

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
                    "text": "Greet the user with 'Hello there! I am an AI voice assistant powered by the OpenAI Realtime API. You can ask me for facts, jokes, or anything you can imagine. How can I help you?'"
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))

async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": {"type": "pcm16", "sample_rate": 16000},
            "output_audio_format": {"type": "pcm16", "sample_rate": 16000},
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

    # Uncomment the next line to have the AI speak first
    # await send_initial_conversation_item(openai_ws)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
