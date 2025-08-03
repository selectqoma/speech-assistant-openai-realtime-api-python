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
from moving_agent import (
    create_moving_request, save_client_name, save_move_date, 
    save_locations, save_volume, save_floors, set_price_estimate,
    set_requires_on_site_check, complete_request, get_current_request
)
from dataclasses import asdict

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))
SYSTEM_MESSAGE = (
    "You are **Eva**, the virtual assistant for **Movers.be**, a Belgian moving company.\n\n"
    "**Purpose**\n"
    "• Help visitors understand, price, and book our moving services.\n"
    "• Give clear, concise answers; escalate to a human when necessary.\n\n"
    "**Tone**\n"
    "• Friendly, professional, straight to the point.\n"
    "• No fluff, no hard‑sell, no jargon.\n\n"
    "**Core tasks**\n"
    "1. **Instant quotes** – Ask only what's required (origin, destination, move date, dwelling size).\n"
    "2. **Booking** – Collect contact details, confirm availability, summarize costs, and send a confirmation.\n"
    "3. **Service questions** – Explain packing help, storage, insurance, and EU cross‑border moves.\n"
    "4. **Move prep tips** – Short, practical checklists (e.g., labeling, utilities, fragile items).\n"
    "5. **Problem‑solving** – Track & update existing bookings, handle changes, reschedule, or cancel.\n"
    "6. **Escalation** – Route edge cases or dissatisfied customers to a human agent without delay.\n\n"
    "**Rules**\n"
    "• Stick to verified company info; if unsure, escalate.\n"
    "• Never invent prices, policies, or availability.\n"
    "• Respect privacy (GDPR); request only necessary data, and remind users we protect it.\n"
    "• Refuse any request unrelated to moving services.\n"
    "• Keep replies under 200 words unless user asks for detail.\n\n"
    "**CRITICAL GREETING RULE**: Only greet with 'Hi, I'm Eva from Movers.be, how can I help you?' if this is the very first user interaction of the session. "
    "After that, never repeat this greeting under any circumstance. Always respond naturally to what the user says without repeating the greeting. "
    "If the user has already spoken or if this is not the first interaction, respond directly to their request without any greeting.\n\n"
    "**CRITICAL: ONE QUESTION AT A TIME RULE**: You MUST ask only ONE question per response. NEVER ask multiple questions in the same response. Wait for the customer's answer before asking the next question.\n\n"
    "**FUNCTION CALLING**: You have access to these functions to save information:\n"
    "- create_moving_request(): Creates a new request and returns it with an ID\n"
    "- save_move_date(request_id, date): Saves when they want to move\n"
    "- save_locations(request_id, from_location, to_location): Saves origin and destination\n"
    "- save_volume(request_id, volume): Saves description of items to move\n"
    "- save_floors(request_id, from_floor, to_floor): Saves floor info and determines if lift needed\n"
    "- save_client_name(request_id, name): Saves client's name\n"
    "- set_price_estimate(request_id, estimate): Saves price estimate\n"
    "- set_requires_on_site_check(request_id, true/false): Marks if on-site check needed\n"
    "- complete_request(request_id): Finalizes and saves the request to file\n"
    "- get_current_request(request_id): Gets current request data\n\n"
    "Always call these functions when you receive the relevant information from the customer.\n\n"
    "**End every interaction with a clear next step** (\"Would you like to book that date?\")."
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created', 'conversation.item.audio_transcription.completed',
    'input_audio_buffer.appended'
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

@app.get("/moving-requests", response_class=JSONResponse)
async def get_moving_requests():
    """Get all moving requests."""
    from moving_agent import moving_agent
    requests = moving_agent.get_all_requests()
    return {
        "active_requests": {req_id: asdict(req) for req_id, req in requests.items()},
        "total_active": len(requests)
    }

@app.get("/moving-requests/{request_id}", response_class=JSONResponse)
async def get_moving_request(request_id: str):
    """Get a specific moving request."""
    from moving_agent import moving_agent
    request = moving_agent.get_current_request(request_id)
    if request:
        return asdict(request)
    else:
        # Try to load from file
        request = moving_agent.load_request_from_file(request_id)
        if request:
            return asdict(request)
        else:
            return {"error": "Request not found"}, 404

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
    conversation_started = False  # THIS IS PER CONNECTION
    last_assistant_item_id = None  # Track the last assistant response for threading
    message_history = []  # Track conversation history (system message sent via session.update)
    waiting_for_response = False  # Track if we're waiting for an AI response
    audio_buffer = []  # Buffer to accumulate audio chunks before committing
    audio_chunks_since_commit = 0  # Track how many chunks we've received since last commit
    audio_appended = False  # Track if audio was successfully appended
    greeting_start_time = None  # Track when greeting starts to protect it
    
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
            nonlocal latest_media_timestamp, audio_buffer, audio_chunks_since_commit, audio_appended
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['type'] == 'audio' and openai_ws.state == State.OPEN:
                        latest_media_timestamp = int(data.get('timestamp', 0))
                        
                        # Append audio to buffer
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['audio']
                        }
                        print(f"Received audio chunk: {len(data['audio'])} chars")
                        await openai_ws.send(json.dumps(audio_append))
                        audio_chunks_since_commit += 1
                        audio_appended = False  # Reset flag until we get confirmation
                        print(f"Appended audio chunk {audio_chunks_since_commit}")
                        
                        # Commit after accumulating enough audio and getting confirmation
                        if audio_chunks_since_commit >= 2 and audio_appended:  # Commit after 2 chunks to ensure enough audio
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                            audio_chunks_since_commit = 0
                            audio_appended = False
                            print("Committed audio buffer")

                    elif data['type'] == 'start':
                        print("Audio session started")
                        response_start_timestamp = None
                        latest_media_timestamp = 0
                        audio_chunks_since_commit = 0
                        audio_appended = False
                        # Don't reset last_assistant_item to maintain conversation context
                        
                        # Send initial conversation trigger to start the greeting
                        print("Sending initial conversation trigger for greeting")
                        await send_initial_conversation_item(openai_ws)
                        
                        # Let server VAD handle all responses automatically
                        print("Audio session started - server VAD will handle responses")
                    elif data['type'] == 'stop':
                        if openai_ws.state == State.OPEN:
                            # Commit any remaining audio before stopping
                            if audio_chunks_since_commit > 0 and audio_appended:
                                await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                                audio_chunks_since_commit = 0
                                audio_appended = False
                                print("Committed final audio buffer")
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
            nonlocal response_start_timestamp, response_in_progress, conversation_started, last_assistant_item_id, waiting_for_response, audio_appended
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
                                response_start_timestamp = None  # Reset for next response
                                response_in_progress = False
                                waiting_for_response = False
                                print(f"Response finished - flags reset: response_in_progress={response_in_progress}, waiting_for_response={waiting_for_response}")
                                print("Response finished - ready for next interaction")
                            elif response['type'] == 'input_audio_buffer.appended':
                                print("Audio successfully appended to buffer")
                                # Set flag to indicate audio was appended
                                audio_appended = True

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
                                waiting_for_response = True
                                mark_queue.append(True)  # Mark that we're in a response
                                print(f"Starting new AI response at timestamp: {response_start_timestamp}ms")
                                print(f"Flags set: response_in_progress={response_in_progress}, waiting_for_response={waiting_for_response}")
                                
                                # Mark that conversation has started
                                if not conversation_started:
                                    conversation_started = True
                                    print("Conversation started - first response from assistant")
                                    # Set greeting start time to protect it from interruption
                                    import time
                                    greeting_start_time = time.time()

                            # Update last_assistant_item_id when we get the item_id
                            if response.get('item_id'):
                                last_assistant_item_id = response['item_id']
                                print(f"[THREAD] Updated last_assistant_item_id: {last_assistant_item_id}")

                        # Handle interruption when user starts speaking
                        if response.get('type') == 'input_audio_buffer.speech_started':
                            print("Speech started detected.")
                            # Add protection for greeting - don't interrupt during first 4 seconds of greeting
                            import time
                            current_time = time.time()
                            if greeting_start_time and (current_time - greeting_start_time) < 6:
                                print("Protecting greeting from interruption - too early")
                                continue
                            
                            # Interrupt if AI is responding OR if we're waiting for a response
                            if response_in_progress or waiting_for_response:
                                print("Interrupting response with response.cancel")
                                # Graceful interruption: cancel the response and
                                # flush the local speaker buffer.
                                await openai_ws.send(json.dumps({"type": "response.cancel"}))
                                await websocket.send_json({"type": "clear"})
                                
                                mark_queue.clear()
                                # Do NOT reset last_assistant_item_id here! It must always point to the last completed AI message.
                                response_start_timestamp = None
                                response_in_progress = False
                                waiting_for_response = False
                                print("AI response interrupted - stopped talking")
                            else:
                                print("User started speaking but no AI response in progress")
                        
                        # Handle transcription completion
                        if response.get('type') == 'conversation.item.audio_transcription.completed':
                            transcript = response.get('transcript', '')
                            if transcript.strip():
                                print(f"Transcription completed: '{transcript}'")
                                if waiting_for_response:
                                    print("[IGNORED] Still waiting for assistant reply to finish. Please wait.")
                                elif not last_assistant_item_id:
                                    print("[IGNORED] No assistant reply yet (no parent_id). Waiting for greeting to finish.")
                                else:
                                    await create_threaded_conversation_item(openai_ws, transcript, last_assistant_item_id)
                                
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
            nonlocal message_history
            
            # Add user message to history
            message_history.append({"role": "user", "content": transcript})
            
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

        await asyncio.gather(receive_from_client(), send_to_client())

async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item to trigger the assistant's greeting."""
    print("=== SENDING EMPTY PROMPT TO TRIGGER GREETING ===")
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": ""
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    print("=== EMPTY PROMPT SENT ===")
    
    # Manually trigger response since empty prompt might not trigger server VAD
    await openai_ws.send(json.dumps({"type": "response.create"}))
    print("=== RESPONSE CREATE SENT ===")

async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {
                "type": "server_vad",
                "create_response": True,
                "threshold": 0.3,
                "prefix_padding_ms": 1000,
                "suffix_padding_ms": 500
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
