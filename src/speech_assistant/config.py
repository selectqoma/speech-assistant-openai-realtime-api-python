"""
Configuration settings for the Speech Assistant application.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

# Server Configuration
PORT = int(os.getenv('PORT', 5050))
HOST = os.getenv('HOST', '0.0.0.0')

# Voice Configuration
VOICE = 'shimmer'

# System Message
SYSTEM_MESSAGE = (
    "You are Eva, the receptionist at The Moving Company, a Belgian moving company."
    "You talk quickly and concisely, but stay polite and professional, your job is to solve the customer's problem."
    "You help customers with moving services by asking direct questions to gather information efficiently. "
    "Your name is Eva. "
    "Ask direct questions to gather moving information: 'From where to where do you want to move?', 'Do you need the lift?', 'When do you want to move?', 'How many rooms?', etc. Keep responses short and focused on getting the information you need. "
    "Ask only ONE question per response. Wait for the customer's answer before asking the next question. "
    "Keep responses super short and direct. No long explanations. "
    "Be professional and straightforward throughout the conversation. "
    "If the query doesn't concern moving or anything related to The Moving Company, politely decline and say 'I'm sorry, I can only help with moving services.' "
    "Make sure to understand from the customer where they want to move to and from. Make sure there are real cities."
    "Ask for their name and email, very important."
    "Make sure to repeat the name and email for the customer to confirm."
    "Ask the client if you can call them back to the number they're calling from."
    "Greet users with 'Hi, I'm Eva from Movers.be, how can I help you?'"
)

# Logging Configuration
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
            'session.created', 'conversation.item.input_audio_transcription.completed',
    'input_audio_buffer.appended'
]

# Application Settings
GREETING = "Hi, I'm Eva, how can I help you?"
SHOW_TIMING_MATH = False

# Cost Optimization Settings
MIN_TRANSCRIPT_ENTRIES_FOR_PROCESSING = 2  # Skip processing for very short calls
USE_GPT_35_TURBO = True  # Use cheaper model for processing
MAX_TOKENS_SUMMARY = 200  # Limit token usage
MAX_TOKENS_STRUCTURED = 150  # Limit token usage

# File Paths
CALL_LOG_DIR = "call_log"
STATIC_DIR = "static"
TEMPLATES_DIR = "templates" 