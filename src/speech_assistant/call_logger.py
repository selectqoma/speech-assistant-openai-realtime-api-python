"""
Call logging functionality for real-time transcription and summarization.
"""

import json
import uuid
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import aiohttp
from .config import OPENAI_API_KEY, CALL_LOG_DIR
import os

@dataclass
class CallLog:
    """Data structure for call log information."""
    id: str
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    transcript: List[Dict] = None
    summary: Optional[str] = None
    status: str = "active"  # active, completed, failed
    metadata: Dict = None

class CallLogger:
    """Handles real-time call transcription and summarization."""
    
    def __init__(self, storage_dir: str = CALL_LOG_DIR):
        self.storage_dir = storage_dir
        self.active_calls: Dict[str, CallLog] = {}
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self):
        """Ensure the storage directory exists."""
        os.makedirs(self.storage_dir, exist_ok=True)
    
    def start_call(self) -> CallLog:
        """Start a new call log."""
        call_id = str(uuid.uuid4())
        call_log = CallLog(
            id=call_id,
            start_time=datetime.now().isoformat(),
            transcript=[],
            metadata={}
        )
        self.active_calls[call_id] = call_log
        print(f"Started call log: {call_id}")
        return call_log
    
    def add_transcript_entry(self, call_id: str, speaker: str, text: str, timestamp: float):
        """Add a transcript entry to the call log."""
        if call_id in self.active_calls:
            entry = {
                "speaker": speaker,  # "user" or "assistant"
                "text": text,
                "timestamp": timestamp,
                "time": datetime.now().isoformat()
            }
            self.active_calls[call_id].transcript.append(entry)
            print(f"Added transcript entry: {speaker}: {text[:50]}...")
    
    async def end_call(self, call_id: str) -> Optional[str]:
        """End a call and generate summary."""
        if call_id not in self.active_calls:
            return None
        
        call_log = self.active_calls[call_id]
        call_log.end_time = datetime.now().isoformat()
        call_log.status = "completed"
        
        # Calculate duration
        start_time = datetime.fromisoformat(call_log.start_time)
        end_time = datetime.fromisoformat(call_log.end_time)
        call_log.duration_seconds = (end_time - start_time).total_seconds()
        
        # Generate summary
        summary = await self._generate_summary(call_log)
        call_log.summary = summary
        
        # Save to file
        self._save_call_log(call_log)
        
        # Remove from active calls
        del self.active_calls[call_id]
        
        print(f"Call {call_id} ended. Duration: {call_log.duration_seconds:.1f}s")
        return summary
    
    async def _generate_summary(self, call_log: CallLog) -> str:
        """Generate a summary of the call using OpenAI."""
        if not call_log.transcript:
            return "No conversation recorded."
        
        # Format transcript for LLM
        conversation_text = ""
        for entry in call_log.transcript:
            speaker_label = "Customer" if entry["speaker"] == "user" else "Eva"
            conversation_text += f"{speaker_label}: {entry['text']}\n"
        
        # Create prompt for summarization
        prompt = f"""
Please provide a concise summary of this customer service call between Eva (the assistant) and a customer.

Call Duration: {call_log.duration_seconds:.1f} seconds

Conversation:
{conversation_text}

Please summarize:
1. The main topic or issue discussed
2. Key information gathered from the customer
3. Any actions taken or decisions made
4. The overall outcome of the call

Keep the summary professional and concise (2-3 sentences).
"""
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a professional call summarizer. Provide clear, concise summaries of customer service calls."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 200,
                    "temperature": 0.3
                }
                
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=data
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        summary = result["choices"][0]["message"]["content"].strip()
                        return summary
                    else:
                        error_text = await response.text()
                        print(f"Error generating summary: {error_text}")
                        return "Summary generation failed."
                        
        except Exception as e:
            print(f"Error generating summary: {e}")
            return "Summary generation failed due to technical error."
    
    def _save_call_log(self, call_log: CallLog):
        """Save call log to file."""
        file_path = os.path.join(self.storage_dir, f"{call_log.id}.json")
        with open(file_path, 'w') as f:
            json.dump(asdict(call_log), f, indent=2)
        print(f"Call log saved to {file_path}")
    
    def get_active_call(self, call_id: str) -> Optional[CallLog]:
        """Get an active call log."""
        return self.active_calls.get(call_id)
    
    def get_all_active_calls(self) -> Dict[str, CallLog]:
        """Get all active call logs."""
        return self.active_calls.copy()
    
    def load_call_log(self, call_id: str) -> Optional[CallLog]:
        """Load a call log from file."""
        file_path = os.path.join(self.storage_dir, f"{call_id}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = json.load(f)
                return CallLog(**data)
        return None

# Global call logger instance
call_logger = CallLogger() 