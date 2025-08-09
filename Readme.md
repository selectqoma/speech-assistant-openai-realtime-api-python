# Speech Assistant with OpenAI Realtime API

A real-time speech assistant built with FastAPI and OpenAI's Realtime API, designed for a moving company receptionist named Eva.

## Features

- Real-time speech-to-speech conversation
- WebSocket-based communication
- Real-time call transcription
- Automatic call summarization with LLM
- Professional receptionist AI (Eva)
- Containerized deployment

## Prerequisites

- Docker and Docker Compose
- OpenAI API key with access to the Realtime API

## Quick Start with Docker

### 1. Set up environment variables

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your_openai_api_key_here
PORT=5050
```

The Docker setup will automatically load the `.env` file.

### 2. Build and run with Docker Compose

For production:
```bash
docker-compose -f docker/docker-compose.yml up --build
```

For development (with hot reload):
```bash
docker-compose -f docker/docker-compose.dev.yml up --build
```

### 3. Access the application

Open your browser and navigate to: `http://localhost:5050`

## Manual Docker Commands

### Build the image
```bash
docker build -t speech-assistant docker/
```

### Run the container
```bash
docker run -p 5050:5050 --env-file .env speech-assistant
```

Or simply:
```bash
docker run -p 5050:5050 speech-assistant
```

## Development

### Local Development (without Docker)

1. Run the setup script:
```bash
./scripts/setup.sh
```

2. Or manually:
   - Create virtual environment: `python3 -m venv .venv`
   - Activate it: `source .venv/bin/activate`
   - Install package: `pip install -e .`
   - Set up environment variables in `.env` file

3. Run the application:
```bash
python main.py
```

## API Endpoints

- `GET /` - Main application interface
- `GET /health` - Health check endpoint
- `GET /call-logs` - Get all call logs
- `GET /call-logs/{log_id}` - Get specific call log
- `POST /call-logs/{log_id}/end` - End a call and generate summary
- `GET /reset-conversation` - Reset conversation state (for testing)
- `WS /ws` - WebSocket endpoint for real-time communication

## Environment Variables

- `OPENAI_API_KEY` - Your OpenAI API key (required)
- `PORT` - Port to run the server on (default: 5050)

## Project Structure

```
speech-assistant-openai-realtime-api-python/
├── src/
│   └── speech_assistant/   # Main package
│       ├── __init__.py     # Package initialization
│       ├── main.py         # FastAPI application
│       ├── moving_agent.py # Moving request management
│       └── config.py       # Configuration settings
├── static/                 # Static files (JS, CSS)
├── templates/              # HTML templates
├── tests/                  # Test files
├── docker/                 # Docker configuration files
├── docs/                   # Documentation
├── scripts/                # Utility scripts
├── call_log/              # Call logging data
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project configuration
└── README.md               # This file
```

## Health Check

The application includes a health check endpoint at `/health` that returns:

```json
{
  "status": "healthy",
  "message": "Speech Assistant is running!"
}
```

## Call Logging

The application automatically logs all conversations in real-time:

- **Real-time Transcription**: Every spoken word is captured and logged
- **Speaker Identification**: Distinguishes between customer and assistant (Eva)
- **Automatic Summarization**: When a call ends, an LLM generates a professional summary
- **Persistent Storage**: All call logs are saved to JSON files in the `call_log/` directory

### Call Log Structure

Each call log contains:
- Call ID and timestamps
- Full conversation transcript
- Call duration
- AI-generated summary
- Metadata

### Ending a Call

To end a call and generate a summary, make a POST request to:
```
POST /call-logs/{call_id}/end
```

This will return the generated summary and save the complete call log.

## Troubleshooting

### Common Issues

1. **OpenAI API Key not set**: Make sure your `.env` file contains a valid `OPENAI_API_KEY`
2. **Port already in use**: Change the `PORT` environment variable or stop other services using port 5050
3. **WebSocket connection issues**: Ensure your browser supports WebSockets and check the browser console for errors

### Docker Issues

1. **Build fails**: Make sure all files are present and the Dockerfile is in the project root
2. **Container won't start**: Check the logs with `docker-compose logs`
3. **Permission issues**: Ensure the `moving_requests` directory has proper permissions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with Docker
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
