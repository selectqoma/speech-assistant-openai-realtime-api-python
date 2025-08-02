# AI Speech Assistant with OpenAI Realtime API (Python)

This application demonstrates how to use Python, FastAPI, and [OpenAI's Realtime API](https://platform.openai.com/docs/) to create a local web-based speech assistant that runs entirely in your browser.

The application opens a WebSocket connection with the OpenAI Realtime API and handles real-time audio streaming between your microphone and the AI assistant, enabling a two-way conversation without requiring any external services like Twilio.

## Features

- **Local Web Interface**: Beautiful, modern UI that runs entirely in your browser
- **Real-time Speech**: Instant voice interaction with the AI assistant
- **Interruption Handling**: The AI can be interrupted when you start speaking
- **Volume Control**: Adjustable audio output volume
- **Cross-platform**: Works on any modern browser with microphone support

## Prerequisites

To use the app, you will need:

- **Python 3.9+** We used `3.9.13` for development; download from [here](https://www.python.org/downloads/).
- **An OpenAI account and an OpenAI API Key.** You can sign up [here](https://platform.openai.com/).
  - **OpenAI Realtime API access.**
- **A modern web browser** with microphone support (Chrome, Firefox, Safari, Edge)

## Local Setup

### (Optional) Create and use a virtual environment

To reduce cluttering your global Python environment on your machine, you can create a virtual environment. On your command line, enter:

```
python3 -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
```

### Install required packages

In the terminal (with the virtual environment, if you set it up) run:
```
pip install -r requirements.txt
```

### Update the .env file

Create a `.env` file, or copy the `.env.example` file to `.env`:

```
cp .env.example .env
```

In the .env file, update the `OPENAI_API_KEY` to your OpenAI API key from the **Prerequisites**.

## Run the app

Once dependencies are installed and the `.env` is set up, run the development server with the following command:
```
python main.py
```

The server will start on `http://localhost:5050` by default.

## Test the app

1. Open your web browser and navigate to `http://localhost:5050`
2. Click the "Connect" button to establish a connection with the AI assistant
3. Grant microphone permissions when prompted
4. Click the microphone button to start talking with the AI assistant
5. Use the volume slider to adjust the AI's voice volume

## How it works

1. **WebSocket Connection**: The browser establishes a WebSocket connection to the Python server
2. **Audio Capture**: Your microphone audio is captured and converted to mu-law format
3. **OpenAI Processing**: Audio is sent to OpenAI's Realtime API for processing
4. **AI Response**: The AI generates a response and sends audio back
5. **Audio Playback**: The response audio is converted and played through your speakers

## Special features

### Have the AI speak first
To have the AI voice assistant talk before the user, uncomment the line `# await send_initial_conversation_item(openai_ws)` in `main.py`. The initial greeting is controlled in `async def send_initial_conversation_item(openai_ws)`.

### Interruption handling/AI preemption
When the user speaks and OpenAI sends `input_audio_buffer.speech_started`, the code will clear the audio buffer and send OpenAI `conversation.item.truncate`.

Depending on your application's needs, you may want to use the [`input_audio_buffer.speech_stopped`](https://platform.openai.com/docs/api-reference/realtime-server-events/input-audio-buffer-speech-stopped) event, instead, or a combination of the two.

### Customization

You can customize the AI assistant by modifying the `SYSTEM_MESSAGE` in `main.py`. This controls the AI's personality and behavior.

## Troubleshooting

- **Microphone not working**: Make sure your browser has permission to access your microphone
- **No audio output**: Check that your speakers/headphones are connected and not muted
- **Connection errors**: Verify your OpenAI API key is correct and you have access to the Realtime API
- **Browser compatibility**: This app requires a modern browser with WebRTC support

## Development

The application consists of:
- `main.py`: FastAPI server that handles WebSocket connections and OpenAI API communication
- `templates/index.html`: The main web interface
- `static/app.js`: JavaScript code that handles browser audio and WebSocket communication
- `requirements.txt`: Python dependencies
