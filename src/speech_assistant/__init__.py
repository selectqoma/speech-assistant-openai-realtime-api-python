"""
Speech Assistant with OpenAI Realtime API

A real-time speech assistant built with FastAPI and OpenAI's Realtime API,
designed for a moving company receptionist named Eva.
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .main import app
from .call_logger import call_logger

__all__ = ["app", "call_logger"] 