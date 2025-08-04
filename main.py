#!/usr/bin/env python3
"""
Entry point for the Speech Assistant application.
"""

import uvicorn
from speech_assistant.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("speech_assistant.main:app", host=HOST, port=PORT) 